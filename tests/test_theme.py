"""Unit tests for theme.py — the token table and the generated style sheet.

No display and no Qt needed: the sheet is a string, and that is exactly why
it is built from a template rather than written by hand. A token name that
does not exist fails here rather than silently rendering an unstyled widget
on someone's machine.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frameworkgui import theme  # noqa: E402


class TestPalette(unittest.TestCase):

    def test_both_appearances_define_the_same_tokens(self):
        acrylic = set(theme.palette(theme.ACRYLIC))
        opaque = set(theme.palette(theme.OPAQUE))
        self.assertEqual(acrylic, opaque,
                         "an appearance is missing tokens the other has")

    def test_surfaces_override_common(self):
        # 'border' exists only in the surface tables, and differs between
        # them - that difference is the whole point of the two appearances.
        self.assertNotEqual(theme.palette(theme.ACRYLIC)["border"],
                            theme.palette(theme.OPAQUE)["border"])

    def test_common_colours_are_shared(self):
        for token in ("accent", "danger.fill", "ok.bar", "warn"):
            self.assertEqual(theme.palette(theme.ACRYLIC)[token],
                             theme.palette(theme.OPAQUE)[token])

    def test_unknown_appearance_raises(self):
        # A third mode would silently render as one of the two otherwise.
        with self.assertRaises(ValueError):
            theme.palette("mica")

    def test_acrylic_surfaces_are_translucent(self):
        for token in ("window", "rail", "pane", "drawer", "card", "panel"):
            value = theme.palette(theme.ACRYLIC)[token]
            self.assertTrue(value.startswith("rgba("),
                            "{} is opaque in the acrylic palette".format(token))

    def test_opaque_surfaces_are_not_translucent(self):
        for token, value in theme.SURFACES[theme.OPAQUE].items():
            self.assertFalse(
                value.startswith("rgba("),
                "{} is translucent in the opaque palette — it would show "
                "the desktop through a window that cannot composite"
                .format(token))


class TestStylesheet(unittest.TestCase):

    def test_renders_for_every_appearance(self):
        for appearance in theme.APPEARANCES:
            sheet = theme.stylesheet(appearance)
            self.assertIn("QPushButton", sheet)
            self.assertIn("QWidget#rail", sheet)

    def test_no_placeholder_survives_rendering(self):
        for appearance in theme.APPEARANCES:
            leftover = re.findall(r"%\(([^)]+)\)s",
                                  theme.stylesheet(appearance))
            self.assertEqual(leftover, [],
                             "unrendered tokens: {}".format(leftover))

    def test_every_template_token_exists(self):
        names = set(re.findall(r"%\(([^)]+)\)s", theme._TEMPLATE))
        values = theme._render_values(theme.OPAQUE)
        missing = sorted(n for n in names if n not in values)
        self.assertEqual(missing, [], "template references unknown tokens")

    def test_danger_roles_are_present(self):
        # Every destructive control gets the danger treatment; if these
        # selectors go missing, a risky button silently renders neutral.
        sheet = theme.stylesheet(theme.OPAQUE)
        for selector in ('QPushButton[role="primary"]',
                         'QPushButton[role="danger"]',
                         'QPushButton[role="dangerSubtle"]',
                         "QFrame#dangerNotice"):
            self.assertIn(selector, sheet)


class TestParseColour(unittest.TestCase):

    def test_hex(self):
        self.assertEqual(theme.parse_colour("#4f8cc9"), (79, 140, 201, 255))

    def test_rgba(self):
        self.assertEqual(theme.parse_colour("rgba(79, 140, 201, 0.18)"),
                         (79, 140, 201, 46))

    def test_rgb_without_alpha(self):
        self.assertEqual(theme.parse_colour("rgba(1, 2, 3)"), (1, 2, 3, 255))

    def test_every_token_parses(self):
        for appearance in theme.APPEARANCES:
            for token, value in theme.palette(appearance).items():
                try:
                    theme.parse_colour(value)
                except ValueError:
                    self.fail("{} = {!r} cannot be painted".format(token,
                                                                   value))

    def test_rubbish_raises(self):
        for value in ("", "chartreuse", "rgba(1, 2)", "#abc"):
            with self.assertRaises(ValueError):
                theme.parse_colour(value)


class TestBarColour(unittest.TestCase):

    def test_cool_bars_are_healthy(self):
        self.assertEqual(theme.bar_colour(0.31), theme.COMMON["ok.bar"])
        self.assertEqual(theme.bar_colour(0.54), theme.COMMON["ok.bar"])

    def test_hot_bars_warn(self):
        # 61 C on a 100 C scale is the design's example of a hot sensor.
        self.assertEqual(theme.bar_colour(0.61), theme.COMMON["warn.bar"])


class TestMetrics(unittest.TestCase):

    def test_drawer_bounds_match_the_design(self):
        self.assertEqual((theme.DRAWER_MIN, theme.DRAWER_MAX), (70, 460))

    def test_default_drawer_height_is_within_bounds(self):
        self.assertLessEqual(theme.DRAWER_MIN, theme.DRAWER_DEFAULT)
        self.assertLessEqual(theme.DRAWER_DEFAULT, theme.DRAWER_MAX)

    def test_minimum_window_is_smaller_than_the_design_size(self):
        for minimum, design in zip(theme.MIN_WINDOW_SIZE, theme.WINDOW_SIZE):
            self.assertLess(minimum, design)


if __name__ == "__main__":
    unittest.main()
