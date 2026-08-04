"""Unit tests for module_icons.py — expansion-card marks and classification.

The icons are drawn, not shipped, so what there is to test is the path data
being present and well-formed and the classifier being conservative: an
unrecognised description has to come back UNKNOWN rather than picking a
plausible-looking card, because a wrong icon is a worse answer than a
neutral one.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import module_icons  # noqa: E402


class TestIcons(unittest.TestCase):

    def test_every_type_except_storage_has_paths(self):
        for name in (module_icons.USB_C, module_icons.USB_A,
                     module_icons.HDMI, module_icons.DISPLAYPORT,
                     module_icons.MICROSD, module_icons.SD,
                     module_icons.ETHERNET, module_icons.AUDIO,
                     module_icons.UNKNOWN):
            self.assertIn(name, module_icons.ICONS)
            self.assertTrue(module_icons.ICONS[name])

    def test_storage_has_no_icon_on_purpose(self):
        # One storage card looks exactly like another; the capacity is the
        # only thing worth showing, so those rows get text instead.
        self.assertNotIn(module_icons.STORAGE, module_icons.ICONS)

    def test_paths_start_with_a_move(self):
        for name, paths in module_icons.ICONS.items():
            for path in paths:
                self.assertTrue(path.startswith("M"),
                                "{} has a path that does not start with a "
                                "move command".format(name))

    def test_paths_use_only_svg_path_commands(self):
        allowed = re.compile(r"^[MmLlHhVvAaCcZz0-9.,\s-]+$")
        for name, paths in module_icons.ICONS.items():
            for path in paths:
                self.assertRegex(path, allowed,
                                 "{} has an unexpected path command".format(
                                     name))

    def test_coordinates_stay_inside_the_18px_box(self):
        for name, paths in module_icons.ICONS.items():
            for number in re.findall(r"-?\d+(?:\.\d+)?", " ".join(paths)):
                self.assertLessEqual(
                    abs(float(number)), 18,
                    "{} draws outside its 18x18 viewBox".format(name))

    def test_paths_for_falls_back_to_the_neutral_mark(self):
        self.assertEqual(module_icons.paths_for("nonsense"),
                         module_icons.ICONS[module_icons.UNKNOWN])
        self.assertEqual(module_icons.paths_for(module_icons.STORAGE),
                         module_icons.ICONS[module_icons.UNKNOWN])


class TestClassify(unittest.TestCase):

    def test_recognises_each_type(self):
        cases = {
            "USB-C expansion card": module_icons.USB_C,
            "USB Type-C": module_icons.USB_C,
            "USB-A card": module_icons.USB_A,
            "HDMI (3rd gen)": module_icons.HDMI,
            "DisplayPort expansion card": module_icons.DISPLAYPORT,
            "Port 3 · DP alt mode": module_icons.DISPLAYPORT,
            "microSD reader": module_icons.MICROSD,
            "Ethernet expansion card": module_icons.ETHERNET,
            "Audio expansion card": module_icons.AUDIO,
            "1 TB storage card": module_icons.STORAGE,
        }
        for text, expected in cases.items():
            self.assertEqual(module_icons.classify(text), expected, text)

    def test_microsd_wins_over_sd(self):
        self.assertEqual(module_icons.classify("microSD"),
                         module_icons.MICROSD)

    def test_nothing_recognisable_is_unknown(self):
        for text in ("", None, "expansion card", "bay 2 populated"):
            self.assertEqual(module_icons.classify(text),
                             module_icons.UNKNOWN)

    def test_classification_is_case_insensitive(self):
        self.assertEqual(module_icons.classify("HDMI"),
                         module_icons.classify("hdmi"))


class TestCapacity(unittest.TestCase):

    def test_reads_a_capacity(self):
        self.assertEqual(module_icons.capacity("1 TB storage card"), "1 TB")
        self.assertEqual(module_icons.capacity("256GB Expansion Card"),
                         "256 GB")

    def test_normalises_the_unit(self):
        self.assertEqual(module_icons.capacity("250gb card"), "250 GB")

    def test_nothing_to_read(self):
        for text in ("", None, "USB-C expansion card", "port 1"):
            self.assertEqual(module_icons.capacity(text), "")


if __name__ == "__main__":
    unittest.main()
