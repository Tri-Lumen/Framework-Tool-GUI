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

    def test_keyboard_focus_is_visible(self):
        # A style sheet suppresses Qt's own focus rectangle, so a button or
        # field reached by Tab (or the F5/Ctrl+N shortcuts) needs its own
        # indication that it is the one that will fire on Enter.
        sheet = theme.stylesheet(theme.OPAQUE)
        self.assertIn("QPushButton:focus", sheet)
        self.assertIn("QPushButton:pressed", sheet)
        self.assertIn("QLineEdit:focus", sheet)


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


class TestContrastRatio(unittest.TestCase):

    def test_identical_colours_have_a_ratio_of_one(self):
        self.assertAlmostEqual(theme.contrast_ratio("#808080", "#808080"), 1.0,
                               places=3)

    def test_black_on_white_is_the_maximum(self):
        self.assertAlmostEqual(theme.contrast_ratio("#000000", "#ffffff"),
                               21.0, places=1)

    def test_order_of_arguments_does_not_matter(self):
        a = theme.contrast_ratio("#e9eaec", "#191b1f")
        b = theme.contrast_ratio("#191b1f", "#e9eaec")
        self.assertAlmostEqual(a, b, places=6)


class TestTextContrast(unittest.TestCase):
    """WCAG AA contrast (>= 4.5:1) for the text roles actually painted over
    a real surface in the opaque appearance — the one where a token's
    literal colour is what lands on screen. Acrylic's surfaces are
    translucent by design (see theme.py's SURFACES docstring), so the true
    contrast there depends on whatever the window is composited over, which
    this module cannot know; CLAUDE.md's "Not yet verified" section already
    flags acrylic as unverified for that reason.

    Found by an audit that computed every text token against every opaque
    surface: everything text is actually set in clears AA comfortably
    except `accent`, which never appears as a `color:` value in the style
    sheet (only as a border/fill) and only needs the 3.0 non-text threshold,
    which it clears. This test pins the pairs that matter so a future token
    change gets caught here instead of on a real screen.
    """

    AA_NORMAL = 4.5

    # (text token, surface token) pairs as the style sheet actually pairs
    # them - not every text token against every surface, which flags
    # combinations nothing ever renders (accent-as-border against card).
    PAIRS = (
        ("text.primary", "window"), ("text.primary", "card"),
        ("text.primary", "panel"), ("text.body", "window"),
        ("text.secondary", "window"), ("text.secondary", "pane"),
        ("text.muted", "window"), ("text.faint", "window"),
        ("text.faint", "card"), ("terminal.out", "drawer"),
        ("accent.text", "card"), ("accent.link", "window"),
        ("ok", "window"), ("warn", "window"),
        ("danger.subtle.text", "window"), ("danger.notice.text", "window"),
        ("warn.text", "window"), ("warn.text.dim", "window"),
    )

    def test_text_roles_meet_aa_against_their_surfaces(self):
        palette = theme.palette(theme.OPAQUE)
        for text_token, surface_token in self.PAIRS:
            ratio = theme.contrast_ratio(palette[text_token],
                                         palette[surface_token])
            self.assertGreaterEqual(
                ratio, self.AA_NORMAL,
                "{} on {} is only {:.2f}:1, below WCAG AA's {}:1".format(
                    text_token, surface_token, ratio, self.AA_NORMAL))


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
