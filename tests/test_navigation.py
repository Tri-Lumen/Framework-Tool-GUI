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

    def test_fourteen_tools(self):
        self.assertEqual(len(navigation.TOOLS), 14)

    def test_keys_are_unique(self):
        keys = [t["key"] for t in navigation.TOOLS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_laptop_gets_everything(self):
        self.assertEqual(len(navigation.tools_for(LAPTOP_13)), 14)

    def test_desktop_loses_the_battery_and_keyboard_tools(self):
        labels = [t["label"] for t in navigation.tools_for(DESKTOP)]
        for hidden in ("Power input wattage", "Battery health report",
                       "Charging speed check", "Keyboard backlight sweep",
                       "Fingerprint LED test",
                       "Preset: Longevity (limit 80%)",
                       "Preset: Full charge (100%)"):
            self.assertNotIn(hidden, labels)
        self.assertEqual(len(labels), 7)

    def test_detection_failure_shows_everything(self):
        self.assertEqual(len(navigation.tools_for(FAIL_OPEN)), 14)

    def test_missing_capability_key_still_shows_the_row(self):
        # Fail open: an unknown capability is not a reason to hide a control.
        self.assertEqual(len(navigation.tools_for({})), 14)

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
