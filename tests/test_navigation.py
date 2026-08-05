"""Unit tests for navigation.py — the rail/pane model and the gated rows.

The point of keeping this as data is that gating can be tested without a
display: these assertions are the same ones the GUI smoke tests make about
which controls a given board gets, but they run everywhere and in
milliseconds.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import navigation  # noqa: E402

LAPTOP_13 = {
    "model": "Laptop 13 (AMD Ryzen AI 300 Series)", "chassis": "Laptop 13",
    "detected": True, "is_laptop": True, "is_desktop": False,
    "is_laptop12": False, "has_touchscreen": False, "has_stylus": False,
    "has_expansion_bay": False, "has_rgbkbd": False,
}
LAPTOP_16 = dict(LAPTOP_13, model="Laptop 16 (AMD Ryzen 7040 Series)",
                 chassis="Laptop 16", has_expansion_bay=True)
DESKTOP = dict(LAPTOP_13, model="Desktop (AMD Ryzen AI Max 300 Series)",
               chassis="Desktop", is_laptop=False, is_desktop=True,
               has_rgbkbd=True)
FAIL_OPEN = {"model": "Unknown", "chassis": "", "detected": False,
             "is_laptop": True, "is_desktop": False, "is_laptop12": True,
             "has_touchscreen": True, "has_stylus": True,
             "has_expansion_bay": True, "has_rgbkbd": True}


class TestStructure(unittest.TestCase):

    def test_five_rail_groups(self):
        self.assertEqual(len(navigation.RAIL_GROUPS), 5)

    def test_nine_sections(self):
        self.assertEqual(len(navigation.SECTIONS), 9)
        self.assertEqual(len(set(navigation.SECTIONS)), 9,
                         "a section is listed under two rail groups")

    def test_every_group_has_an_icon_and_items(self):
        for group in navigation.RAIL_GROUPS:
            self.assertTrue(group["icon"])
            self.assertTrue(group["items"])

    def test_first_section_is_the_groups_first_item(self):
        for group in navigation.RAIL_GROUPS:
            self.assertEqual(navigation.first_section(group["key"]),
                             group["items"][0][1])

    def test_group_for_section_round_trips(self):
        for group in navigation.RAIL_GROUPS:
            for _label, section in group["items"]:
                self.assertEqual(navigation.group_for_section(section)["key"],
                                 group["key"])

    def test_unknown_section_falls_back_to_the_first_group(self):
        self.assertEqual(navigation.group_for_section("nope")["key"],
                         navigation.RAIL_GROUPS[0]["key"])

    def test_every_section_except_overview_has_a_title(self):
        for section in navigation.SECTIONS:
            if section == "overview":
                continue
            self.assertIn(section, navigation.SECTION_TITLES)


class TestWindowTitle(unittest.TestCase):

    def test_overview_uses_the_device_name(self):
        self.assertEqual(navigation.window_title("overview", "Laptop 13"),
                         "Framework System GUI — Laptop 13")

    def test_overview_without_a_device(self):
        self.assertEqual(navigation.window_title("overview", ""),
                         "Framework System GUI — Overview")

    def test_other_sections_use_the_section_name(self):
        self.assertEqual(navigation.window_title("power"),
                         "Framework System GUI — Power")


class TestTools(unittest.TestCase):

    def test_twelve_tools(self):
        # Twelve, not fourteen: the two charge presets moved to the Settings
        # pane, which is the pane whose rows they overwrite.
        self.assertEqual(len(navigation.TOOLS), 12)

    def test_keys_are_unique(self):
        keys = [t["key"] for t in navigation.TOOLS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_laptop_gets_everything(self):
        self.assertEqual(len(navigation.tools_for(LAPTOP_13)), 12)

    def test_desktop_loses_the_battery_and_keyboard_tools(self):
        labels = [t["label"] for t in navigation.tools_for(DESKTOP)]
        for hidden in ("Power input wattage", "Battery health report",
                       "Charging speed check", "Keyboard backlight sweep",
                       "Fingerprint LED test"):
            self.assertNotIn(hidden, labels)
        self.assertEqual(len(labels), 7)

    def test_detection_failure_shows_everything(self):
        self.assertEqual(len(navigation.tools_for(FAIL_OPEN)), 12)

    def test_missing_capability_key_still_shows_the_row(self):
        # Fail open: an unknown capability is not a reason to hide a control.
        self.assertEqual(len(navigation.tools_for({})), 12)

    def test_the_destructive_tool_is_marked(self):
        burst = next(t for t in navigation.TOOLS if t["key"] == "fan_burst")
        self.assertTrue(burst["danger"])

    def test_multi_step_tools_declare_their_step_count(self):
        for key, steps in (("fan_test", 5), ("thermal_monitor", 6),
                           ("kblight_sweep", 11), ("fpled_cycle", 4)):
            tool = next(t for t in navigation.TOOLS if t["key"] == key)
            self.assertEqual(tool["steps"], steps)

    def test_single_shot_tools_have_no_step_panel(self):
        for key in ("input_power", "battery_health", "port_map", "security"):
            tool = next(t for t in navigation.TOOLS if t["key"] == key)
            self.assertIsNone(tool["steps"])


class TestPortQueries(unittest.TestCase):

    def test_laptop_16_gets_the_expansion_bay(self):
        keys = [q["key"] for q in navigation.port_queries_for(LAPTOP_16)]
        self.assertIn("expansion_bay", keys)
        self.assertNotIn("stylus", keys)

    def test_laptop_13_has_no_expansion_bay(self):
        keys = [q["key"] for q in navigation.port_queries_for(LAPTOP_13)]
        self.assertNotIn("expansion_bay", keys)

    def test_desktop_loses_the_laptop_only_queries(self):
        keys = [q["key"] for q in navigation.port_queries_for(DESKTOP)]
        for hidden in ("inputdeck", "privacy", "expansion_bay", "stylus"):
            self.assertNotIn(hidden, keys)

    def test_detection_failure_shows_all_nine(self):
        self.assertEqual(len(navigation.port_queries_for(FAIL_OPEN)), 9)


class TestSettingsRows(unittest.TestCase):

    def test_desktop_has_only_the_rgb_row(self):
        keys = [r["key"] for r in navigation.settings_rows_for(DESKTOP)]
        self.assertEqual(keys, ["rgbkbd"])

    def test_laptop_13_without_a_touchscreen_loses_that_row(self):
        keys = [r["key"] for r in navigation.settings_rows_for(LAPTOP_13)]
        self.assertNotIn("touchscreen", keys)
        self.assertNotIn("tablet_mode", keys)
        self.assertIn("charge_limit", keys)

    def test_input_deck_off_is_the_destructive_row(self):
        danger = [r["key"] for r in navigation.SETTINGS_ROWS if r["danger"]]
        self.assertEqual(danger, ["deck_mode"])

    def test_every_row_can_set_something(self):
        for row in navigation.SETTINGS_ROWS:
            self.assertTrue(row["set"], "{} sets nothing".format(row["key"]))

    def test_choice_rows_default_to_one_of_their_choices(self):
        for row in navigation.SETTINGS_ROWS:
            if row["kind"] == "choice":
                self.assertIn(row["default"], row["choices"])


if __name__ == "__main__":
    unittest.main()


class TestIconPaths(unittest.TestCase):
    """Every icon path has to spell its commands out.

    SVG lets a path imply a lineto by putting extra coordinate pairs after a
    moveto ("M2.5 8 9 3"), and lets an arc repeat without its letter. Both
    are legal SVG and neither is reliably handled by the Qt bundled with the
    packaged Windows build: it drew the first segment and silently dropped
    the rest of the path, which is exactly how four of the five rail icons
    came out as a bare diagonal stroke on a real machine. The two that
    rendered correctly were the two already written longhand.

    Nothing warns you about this — the paths are strings, they render fine
    under the Qt used in CI, and the failure only appears in the shipped
    build. So it is asserted instead.
    """

    # A command letter, then its arguments. Counting the numbers after each
    # letter is what catches an implicit repeat.
    ARGS_PER_COMMAND = {
        "M": 2, "m": 2, "L": 2, "l": 2, "H": 1, "h": 1, "V": 1, "v": 1,
        "C": 6, "c": 6, "S": 4, "s": 4, "Q": 4, "q": 4, "T": 2, "t": 2,
        "A": 7, "a": 7, "Z": 0, "z": 0,
    }

    @classmethod
    def segments(cls, path_d):
        """(letter, argument count) for each command in a path."""
        import re
        out = []
        for letter, body in re.findall(r"([A-Za-z])([^A-Za-z]*)", path_d):
            numbers = re.findall(r"-?\d*\.?\d+", body)
            out.append((letter, len(numbers)))
        return out

    def assert_explicit(self, path_d, where):
        for letter, count in self.segments(path_d):
            expected = self.ARGS_PER_COMMAND.get(letter)
            self.assertIsNotNone(expected,
                                 "{}: unknown path command {!r}".format(
                                     where, letter))
            if expected == 0:
                self.assertEqual(count, 0,
                                 "{}: {} takes no arguments".format(where,
                                                                    letter))
                continue
            self.assertEqual(
                count, expected,
                "{}: '{}' carries {} numbers, not {} — that is an implicit "
                "repeat/lineto, which Qt's SVG parser drops the rest of the "
                "path on. Write the command letter out.".format(
                    where, letter, count, expected))

    def test_rail_icons_are_explicit(self):
        for group in navigation.RAIL_GROUPS:
            self.assert_explicit(group["icon"], group["key"])

    def test_appearance_icon_is_explicit(self):
        for path in navigation.APPEARANCE_ICON:
            self.assert_explicit(path, "appearance")

    def test_every_group_has_a_distinct_icon(self):
        icons = [g["icon"] for g in navigation.RAIL_GROUPS]
        self.assertEqual(len(icons), len(set(icons)))


class TestToolParameters(unittest.TestCase):
    """The numbers that used to be hard-coded inside each tool body."""

    def tool(self, key):
        return next(t for t in navigation.TOOLS if t["key"] == key)

    def test_timed_tools_declare_a_duration(self):
        for tool in navigation.TOOLS:
            if tool.get("mode") == navigation.MODE_BAR:
                self.assertGreater(
                    navigation.duration_for(tool), 0,
                    "{} draws a progress bar but has no length".format(
                        tool["key"]))

    def test_step_tools_have_no_timing(self):
        # A tool whose steps take an unknowable time must not claim a length.
        for tool in navigation.TOOLS:
            if tool.get("mode") == navigation.MODE_STEPS:
                self.assertEqual(navigation.duration_for(tool), 0)

    def test_fan_burst_defaults_to_thirty_seconds(self):
        self.assertEqual(navigation.duration_for(self.tool("fan_burst")), 30)

    def test_overriding_a_param_changes_the_duration(self):
        burst = self.tool("fan_burst")
        self.assertEqual(navigation.duration_for(burst, {"duration": 90}), 90)

    def test_thermal_monitor_multiplies_samples_by_interval(self):
        monitor = self.tool("thermal_monitor")
        self.assertEqual(
            navigation.duration_for(monitor, {"samples": 12, "interval": 10}),
            120)

    def test_params_are_clamped_to_their_bounds(self):
        spec = self.tool("thermal_monitor")["params"][0]
        self.assertEqual(navigation.clamp_param(spec, 10 ** 6), spec["max"])
        self.assertEqual(navigation.clamp_param(spec, -5), spec["min"])

    def test_a_nonsense_param_falls_back_to_the_default(self):
        spec = self.tool("fan_burst")["params"][0]
        self.assertEqual(navigation.clamp_param(spec, "not a number"),
                         spec["default"])

    def test_counts_stay_integers(self):
        spec = next(p for p in self.tool("thermal_monitor")["params"]
                    if p["key"] == "samples")
        self.assertIsInstance(navigation.clamp_param(spec, 7.6), int)

    def test_param_keys_are_unique_within_a_tool(self):
        for tool in navigation.TOOLS:
            keys = [p["key"] for p in navigation.params_for(tool)]
            self.assertEqual(len(keys), len(set(keys)), tool["key"])


class TestSettingsPresets(unittest.TestCase):
    """The presets moved off Diagnostics and onto the pane they rewrite."""

    def test_presets_are_not_diagnostics_tools(self):
        keys = [t["key"] for t in navigation.TOOLS]
        self.assertNotIn("preset_longevity", keys)
        self.assertNotIn("preset_full", keys)

    def test_presets_exist_on_the_settings_pane(self):
        keys = [p["key"] for p in navigation.presets_for(LAPTOP_13)]
        self.assertEqual(keys, ["preset_longevity", "preset_full"])

    def test_a_desktop_has_no_charge_presets(self):
        self.assertEqual(navigation.presets_for(DESKTOP), [])

    def test_every_preset_writes_rows_that_exist(self):
        row_keys = {row["key"] for row in navigation.SETTINGS_ROWS}
        for preset in navigation.SETTINGS_PRESETS:
            for key in preset["sets"]:
                self.assertIn(key, row_keys,
                              "{} writes unknown row {}".format(preset["key"],
                                                                key))
