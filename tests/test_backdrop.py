"""Unit tests for backdrop.py — the compositing decision table.

Every input is injected, so the whole table is checked on any machine. The
direction that matters: an uncertain answer must be "no". A translucent
window over a compositor that is not running is a window with nothing
behind it, which is worse than an opaque one.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backdrop  # noqa: E402


class TestWindowsBuild(unittest.TestCase):

    def test_windows_11_22h2_and_later_support_it(self):
        self.assertTrue(backdrop.windows_supports_backdrop(22621))
        self.assertTrue(backdrop.windows_supports_backdrop(26100))

    def test_earlier_windows_11_and_windows_10_do_not(self):
        self.assertFalse(backdrop.windows_supports_backdrop(22000))
        self.assertFalse(backdrop.windows_supports_backdrop(19045))

    def test_an_unknown_build_is_not_supported(self):
        for value in (None, "", "twenty-two thousand", object()):
            self.assertFalse(backdrop.windows_supports_backdrop(value))


class TestSupportsTranslucency(unittest.TestCase):

    def test_windows_11(self):
        self.assertTrue(backdrop.supports_translucency(
            platform="win32", environ={}, windows_build=22621))

    def test_windows_10(self):
        self.assertFalse(backdrop.supports_translucency(
            platform="win32", environ={}, windows_build=19045))

    def test_wayland_always_composites(self):
        self.assertTrue(backdrop.supports_translucency(
            platform="linux", environ={"XDG_SESSION_TYPE": "wayland"}))
        self.assertTrue(backdrop.supports_translucency(
            platform="linux", environ={"WAYLAND_DISPLAY": "wayland-0"}))

    def test_x11_asks_the_compositor(self):
        env = {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
        self.assertTrue(backdrop.supports_translucency(
            platform="linux", environ=env, x11_probe=lambda: True))
        self.assertFalse(backdrop.supports_translucency(
            platform="linux", environ=env, x11_probe=lambda: False))

    def test_linux_with_no_session_at_all(self):
        self.assertFalse(backdrop.supports_translucency(
            platform="linux", environ={}))

    def test_other_platforms_get_the_opaque_path(self):
        # Not distribution targets; claiming an untested capability there
        # would be a guess, and the guess costs a broken-looking window.
        for platform in ("darwin", "freebsd13", "sunos5"):
            self.assertFalse(backdrop.supports_translucency(
                platform=platform, environ={}))


class TestStatusLabel(unittest.TestCase):

    def test_acrylic_on(self):
        self.assertEqual(backdrop.status_label("acrylic", True), "Acrylic on")

    def test_opaque_by_choice(self):
        self.assertEqual(backdrop.status_label("opaque", True), "Opaque")

    def test_opaque_by_necessity_says_so(self):
        # The user needs to know the toggle is disabled for a reason.
        self.assertEqual(backdrop.status_label("acrylic", False),
                         "Acrylic unavailable — opaque")
        self.assertEqual(backdrop.status_label("opaque", False),
                         "Acrylic unavailable — opaque")

    def test_unavailable_message_is_not_empty(self):
        self.assertIn("opaque", backdrop.unavailable_message())


class TestApplyBackdrop(unittest.TestCase):

    def test_a_null_window_is_a_no_op(self):
        # Called before the window has a handle; must not raise.
        self.assertFalse(backdrop.apply_windows_backdrop(0, True))
        self.assertFalse(backdrop.apply_windows_backdrop(None, False))

    @unittest.skipIf(sys.platform.startswith("win"),
                     "dwmapi really exists here")
    def test_off_windows_it_declines_rather_than_raising(self):
        self.assertFalse(backdrop.apply_windows_backdrop(1234, True))

    def test_backdrop_values_match_the_sdk(self):
        self.assertEqual(backdrop.DWMWA_SYSTEMBACKDROP_TYPE, 38)
        self.assertEqual(backdrop.DWMSBT_ACRYLIC, 3)
        self.assertEqual(backdrop.DWMSBT_NONE, 1)


if __name__ == "__main__":
    unittest.main()
