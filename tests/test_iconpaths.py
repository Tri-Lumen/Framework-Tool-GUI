"""Unit tests for iconpaths.py — the path language, parsed by us not by Qt.

This module exists because QSvgRenderer dropped most of every icon path on
the Qt in the packaged Windows build: four of the five rail icons rendered
as a bare diagonal stroke on a real machine, and nothing in CI could see it
because the same strings render correctly under the Qt used there.

So these tests are the check that used to be impossible: every icon the app
ships is parsed here, in milliseconds, with no display and no Qt, and the
geometry is asserted against values worked out by hand. If an icon draws
wrong now, it is wrong in this file's terms and a test can catch it.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frameworkgui import (  # noqa: E402
    iconpaths,
    module_icons,
    navigation,
)


def points(ops):
    """The (x, y) endpoints each operation lands on."""
    return [(round(op[-2], 4), round(op[-1], 4))
            for op in ops if op[0] != "close"]


class TestTokenize(unittest.TestCase):

    def test_letters_and_numbers_split(self):
        self.assertEqual(iconpaths.tokenize("M2.5 8L9 3"),
                         ["M", 2.5, 8.0, "L", 9.0, 3.0])

    def test_numbers_may_run_together(self):
        # "0 1-1 1" is legal SVG and appears in real arc flags: the minus
        # sign is the only separator between two numbers.
        self.assertEqual(iconpaths.tokenize("l5-8"), ["l", 5.0, -8.0])
        self.assertEqual(iconpaths.tokenize("a1 1 0 0 1-1 1"),
                         ["a", 1.0, 1.0, 0.0, 0.0, 1.0, -1.0, 1.0])

    def test_exponent_and_leading_dot_forms(self):
        self.assertEqual(iconpaths.tokenize("M.5 1e1"), ["M", 0.5, 10.0])


class TestStraightCommands(unittest.TestCase):

    def test_absolute_move_and_line(self):
        self.assertEqual(iconpaths.parse("M2 3L8 9"),
                         (("move", 2.0, 3.0), ("line", 8.0, 9.0)))

    def test_relative_commands_accumulate(self):
        ops = iconpaths.parse("m2 3l4 5l-1-1")
        self.assertEqual(points(ops), [(2, 3), (6, 8), (5, 7)])

    def test_horizontal_and_vertical(self):
        ops = iconpaths.parse("M3 5H15V9h-4v-2")
        self.assertEqual(points(ops), [(3, 5), (15, 5), (15, 9), (11, 9),
                                       (11, 7)])

    def test_close_returns_to_the_subpath_start(self):
        ops = iconpaths.parse("M2 2H8V8ZM10 10H12")
        self.assertIn(("close",), ops)
        # The move after the close is absolute, but a relative one would
        # have had to start from (2, 2) — that is what close restores.
        self.assertEqual(points(iconpaths.parse("M2 2H8V8Zm1 1")),
                         [(2, 2), (8, 2), (8, 8), (3, 3)])

    def test_implicit_repeat_is_handled_not_dropped(self):
        # The shorthand Qt's parser mishandled. The icons spell their
        # commands out anyway, but the parser has to be right about it.
        self.assertEqual(iconpaths.parse("M2.5 8 9 3 15.5 8"),
                         iconpaths.parse("M2.5 8L9 3L15.5 8"))
        self.assertEqual(iconpaths.parse("L1 1 2 2"[0:0] + "M0 0l1 1 2 2"),
                         iconpaths.parse("M0 0l1 1l2 2"))

    def test_multiple_subpaths(self):
        ops = iconpaths.parse("M3 5H15M3 9H15")
        self.assertEqual([op[0] for op in ops],
                         ["move", "line", "move", "line"])


class TestCurves(unittest.TestCase):

    def test_cubic_passes_through(self):
        ops = iconpaths.parse("M0 0C1 2 3 4 5 6")
        self.assertEqual(ops, (("move", 0.0, 0.0),
                               ("cubic", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)))

    def test_smooth_cubic_reflects_the_previous_control(self):
        ops = iconpaths.parse("M0 0C1 1 2 2 3 3S5 5 6 6")
        # The reflection of (2, 2) through the current point (3, 3).
        self.assertEqual(ops[-1][1:3], (4.0, 4.0))

    def test_smooth_cubic_without_a_previous_curve_uses_the_point(self):
        ops = iconpaths.parse("M1 1S5 5 6 6")
        self.assertEqual(ops[-1][1:3], (1.0, 1.0))

    def test_quadratic_becomes_an_equivalent_cubic(self):
        ops = iconpaths.parse("M0 0Q3 0 3 3")
        self.assertEqual(ops[-1], ("cubic", 2.0, 0.0, 3.0, 1.0, 3.0, 3.0))


class TestArcs(unittest.TestCase):
    """Arcs are the reason this module does geometry at all.

    Four of the icons draw one, including the appearance toggle's circle and
    the audio jack's sleeve, so the endpoint parameterization has to be
    right and has to land exactly where the path said.
    """

    def test_semicircle_ends_where_it_was_told(self):
        ops = iconpaths.parse("M9 3A6 6 0 0 0 9 15")
        self.assertEqual(points(ops)[-1], (9, 15))

    def test_semicircle_stays_on_the_circle(self):
        ops = iconpaths.parse("M9 3A6 6 0 0 0 9 15")
        for op in ops[1:]:
            for x, y in zip(op[1::2], op[2::2]):
                # Control points sit outside the circle; the endpoints are
                # on it. Checking every point is within a radius of slack
                # catches a mirrored or mis-centred arc.
                self.assertLess(math.hypot(x - 9, y - 9), 6 * 1.4)
        # Sweep 0 from the top goes anticlockwise — left of centre.
        self.assertLess(min(p[0] for p in points(ops)), 9)

    def test_sweep_flag_picks_the_other_side(self):
        left = points(iconpaths.parse("M9 3A6 6 0 0 0 9 15"))
        right = points(iconpaths.parse("M9 3A6 6 0 0 1 9 15"))
        self.assertLess(min(p[0] for p in left), 9)
        self.assertGreater(max(p[0] for p in right), 9)

    def test_two_arcs_make_a_closed_circle(self):
        ops = iconpaths.parse("M9 3.2A5.8 5.8 0 0 0 9 14.8"
                              "A5.8 5.8 0 0 0 9 3.2")
        self.assertEqual(points(ops)[-1], (9, 3.2))
        for op in ops:
            for x, y in zip(op[1::2], op[2::2]):
                self.assertGreater(math.hypot(x - 9, y - 9), 4.0)

    def test_arc_is_split_into_quadrant_sized_cubics(self):
        # A single cubic cannot follow a half circle closely enough, so a
        # 180-degree arc has to come back as more than one.
        ops = iconpaths.parse("M9 3A6 6 0 0 0 9 15")
        self.assertGreaterEqual(len([o for o in ops if o[0] == "cubic"]), 2)

    def test_zero_radius_is_a_straight_line(self):
        self.assertEqual(iconpaths.parse("M2 2A0 0 0 0 1 8 8"),
                         (("move", 2.0, 2.0), ("line", 8.0, 8.0)))

    def test_arc_to_nowhere_draws_nothing(self):
        self.assertEqual(iconpaths.parse("M2 2A3 3 0 0 1 2 2"),
                         (("move", 2.0, 2.0),))

    def test_radii_too_small_are_grown_rather_than_refused(self):
        # The spec says to scale them up until the endpoints are reachable.
        ops = iconpaths.parse("M0 0A1 1 0 0 1 10 0")
        self.assertEqual(points(ops)[-1], (10, 0))

    def test_relative_arc(self):
        ops = iconpaths.parse("M9 3a6 6 0 0 0 0 12")
        self.assertEqual(points(ops)[-1], (9, 15))


class TestErrors(unittest.TestCase):

    def test_a_path_must_start_with_a_command(self):
        with self.assertRaises(iconpaths.PathError):
            iconpaths.parse("2 3L8 9")

    def test_unknown_command_is_refused(self):
        with self.assertRaises(iconpaths.PathError):
            iconpaths.parse("M0 0X5 5")

    def test_a_truncated_command_is_refused(self):
        with self.assertRaises(iconpaths.PathError):
            iconpaths.parse("M0 0L5")

    def test_empty_path_is_empty(self):
        self.assertEqual(iconpaths.parse(""), ())
        self.assertEqual(iconpaths.parse(None), ())


class TestShippedIcons(unittest.TestCase):
    """Every icon the app draws, parsed and measured.

    This is the assertion that could not be made while Qt owned the parsing:
    the whole icon set is checked here without a display.
    """

    def all_icons(self):
        for group in navigation.RAIL_GROUPS:
            yield group["key"], (group["icon"],)
        yield "appearance", navigation.APPEARANCE_ICON
        for module_type, paths in module_icons.ICONS.items():
            yield module_type, paths

    def test_every_icon_parses_and_starts_with_a_move(self):
        for name, paths in self.all_icons():
            for path in paths:
                ops = iconpaths.parse(path)
                self.assertTrue(ops, "{} parsed to nothing".format(name))
                self.assertEqual(ops[0][0], "move",
                                 "{} does not start with a move".format(name))

    def test_every_icon_draws_more_than_one_segment(self):
        # The shipped-build failure looked exactly like this: a path that
        # produced a single stroke and nothing else.
        for name, paths in self.all_icons():
            drawn = sum(len([op for op in iconpaths.parse(p)
                             if op[0] in ("line", "cubic")]) for p in paths)
            self.assertGreater(drawn, 1,
                               "{} draws only {} segment(s)".format(name,
                                                                    drawn))

    def test_every_icon_stays_inside_its_18px_box(self):
        for name, paths in self.all_icons():
            left, top, right, bottom = iconpaths.bounds(paths)
            self.assertGreaterEqual(round(left, 3), 0.0, name)
            self.assertGreaterEqual(round(top, 3), 0.0, name)
            self.assertLessEqual(round(right, 3), 18.0, name)
            self.assertLessEqual(round(bottom, 3), 18.0, name)

    def test_every_icon_fills_a_reasonable_share_of_the_box(self):
        # An icon that collapsed to a corner would still be "inside the
        # box"; the rail is 18px of icon and it should look like it. The
        # bar is low on the short axis because some module marks genuinely
        # are that shape — a USB-C connector face is 10 wide and 4 tall.
        for name, paths in self.all_icons():
            left, top, right, bottom = iconpaths.bounds(paths)
            self.assertGreater(min(right - left, bottom - top), 3.5, name)
            self.assertGreater(max(right - left, bottom - top), 8.0, name)


if __name__ == "__main__":
    unittest.main()
