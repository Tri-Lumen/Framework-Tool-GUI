"""
Unit tests for parsers.py (regex parsing + device detection).

Pure stdlib, no tkinter/display dependency — safe to run in any CI
environment:

    python3 -m unittest discover tests -v

Sample outputs are adapted from EXAMPLES.md in the framework-system repo
(https://github.com/FrameworkComputer/framework-system/blob/main/EXAMPLES.md).
The CLI does not promise a stable output format, so if these start failing
against a real binary, the fix is almost always: update the sample text in
this file to match the new real output, then fix the regex in parsers.py to
match — don't just loosen the assertion.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parsers import (  # noqa: E402
    detect_model,
    parse_firmware,
    parse_ports,
    parse_setting_value,
    parse_tool_version,
    sections,
)

POWER_VV = """Charger Status
  AC is:            connected
  Charger Voltage:  17800mV
  Charger Current:  2000mA
                    0.51C
  Chg Input Current:3084mA
  Battery SoC:      87%
Battery Status
  AC is:            connected
  Battery is:       connected
  Battery LFCC:     3713 mAh (Last Full Charge Capacity)
  Battery Capacity: 3215 mAh
                    56.953 Wh
  Charge level:     86%
  Design Capacity:  3915 mAh
                    60.604 Wh
  Cycle Count:      64
  Battery charging
"""

THERMAL = """  F75303_Local: 43 C
  F75303_CPU:   44 C
  F75303_DDR:   39 C
  APU:          62 C
  Fan Speed:       7281 RPM
"""

PDPORTS = """USB-C Port 0:
  PD Contract:   Yes
  Power Role:    Sink
  Data Role:     Dfp
  VCONN:         Off
  Negotiated:    48.000 V, 5000 mA, 240.0 W
  CC Polarity:   CC1
  Port Partner:  Source
  EPR:           Active (Supported)
  Sink Active:   Yes
USB-C Port 1:
  PD Contract:   No
  Power Role:    Source
  Data Role:     Dfp
  VCONN:         Off
  Negotiated:    5.000 V, 410 mA, 2.50 W
  CC Polarity:   CC1
USB-C Port 3:
  PD Contract:   No
  Power Role:    Sink
  Data Role:     Ufp
"""

VERSIONS_L12 = """Mainboard Hardware
  Type:           Laptop 12 (13th Gen Intel Core)
  Revision:       MassProduction
UEFI BIOS
  Version:        03.00
EC Firmware
  Build version:  test-0.0.0
Touchscreen
  Firmware Version: v7.0.0.5.0.0.0.0
  Protocols:        USI
Stylus
  Serial Number:    28C1A00-12E71DAE
  Vendor ID:        32AC (Framework Computer)
  Product ID:       002B (Framework Stylus)
  Firmware Version: FF.FF
"""

VERSIONS_L13_NO_TOUCH = """Mainboard Hardware
  Type:           Laptop 13 (AMD Ryzen AI 300 Series)
  Revision:       MassProduction
UEFI BIOS
  Version:        03.00
EC Firmware
  Build version:  lilac-3.0.0-1541dc6
Touchpad
  Firmware Version: v0E07
"""

VERSIONS_L13_WITH_TOUCH = VERSIONS_L13_NO_TOUCH + (
    "Touchscreen\n  Firmware Version: v1409\n"
)

VERSIONS_L16 = """Mainboard Hardware
  Type:           Laptop 16 (AMD Ryzen 7040HS Series)
  Revision:       MassProduction
Laptop 16 Numpad
  Firmware Version: 0.2.9
  Location: [X] [ ] [ ]       [ ] [ ]
Laptop 16 ANSI Keyboard
  Firmware Version: 0.2.9
  Location: [ ] [ ] [X]       [ ] [ ]
"""

VERSIONS_DESKTOP = """Mainboard Hardware
  Type:           Desktop (AMD Ryzen AI Max 300 Series)
  Revision:       MassProduction
UEFI BIOS
  Version:        01.00
"""

VERSIONS_GARBAGE = "some completely unrecognized output\nwith no Type: line\n"


class TestPowerParsers(unittest.TestCase):
    def test_charger_and_battery_fields(self):
        from parsers import (
            RE_AC,
            RE_CHG_A,
            RE_CHG_V,
            RE_CYCLES,
            RE_DESIGN,
            RE_IN_A,
            RE_LFCC,
            RE_SOC,
        )
        self.assertEqual(RE_CHG_V.search(POWER_VV).group(1), "17800")
        self.assertEqual(RE_CHG_A.search(POWER_VV).group(1), "2000")
        self.assertEqual(RE_IN_A.search(POWER_VV).group(1), "3084")
        self.assertEqual(RE_SOC.search(POWER_VV).group(1), "87")
        self.assertEqual(RE_LFCC.search(POWER_VV).group(1), "3713")
        self.assertEqual(RE_DESIGN.search(POWER_VV).group(1), "3915")
        self.assertEqual(RE_CYCLES.search(POWER_VV).group(1), "64")
        self.assertIn("connected", RE_AC.search(POWER_VV).group(1))

    def test_battery_health_math(self):
        from parsers import RE_DESIGN, RE_LFCC
        lfcc = int(RE_LFCC.search(POWER_VV).group(1))
        design = int(RE_DESIGN.search(POWER_VV).group(1))
        health = 100.0 * lfcc / design
        self.assertAlmostEqual(health, 94.84, places=1)


class TestThermalParser(unittest.TestCase):
    def test_temps_and_rpm(self):
        from parsers import RE_RPM, RE_TEMP
        temps = dict(RE_TEMP.findall(THERMAL))
        self.assertEqual(temps["APU"], "62")
        self.assertEqual(temps["F75303_CPU"], "44")
        self.assertEqual(RE_RPM.search(THERMAL).group(1), "7281")

    def test_zero_rpm_still_matches(self):
        from parsers import RE_RPM
        text = "  Fan Speed:       0 RPM\n"
        self.assertEqual(RE_RPM.search(text).group(1), "0")


class TestPortParser(unittest.TestCase):
    def test_three_ports_parsed(self):
        ports = parse_ports(PDPORTS)
        self.assertEqual(len(ports), 3)

    def test_sink_port_wattage(self):
        ports = parse_ports(PDPORTS)
        self.assertEqual(ports[0]["role"], "Sink")
        self.assertEqual(ports[0]["watts"], 240.0)
        self.assertEqual(ports[0]["volts"], 48.0)
        self.assertEqual(ports[0]["ma"], 5000)

    def test_source_port_wattage(self):
        ports = parse_ports(PDPORTS)
        self.assertEqual(ports[1]["role"], "Source")
        self.assertEqual(ports[1]["watts"], 2.5)

    def test_port_with_no_contract_has_no_watts(self):
        ports = parse_ports(PDPORTS)
        self.assertNotIn("watts", ports[2])

    def test_empty_input(self):
        self.assertEqual(parse_ports(""), [])


class TestDeviceDetection(unittest.TestCase):
    def test_laptop12(self):
        c = detect_model(VERSIONS_L12)
        self.assertTrue(c["detected"])
        self.assertTrue(c["is_laptop"])
        self.assertFalse(c["is_desktop"])
        self.assertTrue(c["is_laptop12"])
        self.assertTrue(c["has_touchscreen"])
        self.assertTrue(c["has_stylus"])
        self.assertFalse(c["has_expansion_bay"])
        self.assertFalse(c["has_rgbkbd"])

    def test_laptop13_without_touchscreen_bezel(self):
        c = detect_model(VERSIONS_L13_NO_TOUCH)
        self.assertTrue(c["is_laptop"])
        self.assertFalse(c["is_laptop12"])
        self.assertFalse(c["has_touchscreen"])
        self.assertFalse(c["has_stylus"])
        self.assertFalse(c["has_expansion_bay"])

    def test_laptop13_with_touchscreen_bezel(self):
        # A Laptop 13 with the optional touchscreen bezel installed should
        # be detected via output content, not just the model number.
        c = detect_model(VERSIONS_L13_WITH_TOUCH)
        self.assertTrue(c["has_touchscreen"])
        self.assertFalse(c["has_stylus"])  # L13 never has a stylus digitizer

    def test_laptop16(self):
        c = detect_model(VERSIONS_L16)
        self.assertTrue(c["is_laptop"])
        self.assertFalse(c["is_laptop12"])
        self.assertTrue(c["has_expansion_bay"])
        self.assertFalse(c["has_touchscreen"])
        self.assertFalse(c["has_stylus"])
        self.assertFalse(c["has_rgbkbd"])

    def test_desktop(self):
        c = detect_model(VERSIONS_DESKTOP)
        self.assertTrue(c["detected"])
        self.assertFalse(c["is_laptop"])
        self.assertTrue(c["is_desktop"])
        self.assertTrue(c["has_rgbkbd"])
        self.assertFalse(c["has_expansion_bay"])
        self.assertFalse(c["has_touchscreen"])
        self.assertFalse(c["has_stylus"])

    def test_unrecognized_output_fails_open(self):
        c = detect_model(VERSIONS_GARBAGE)
        self.assertFalse(c["detected"])
        # Fail-open: every gate defaults to True so nothing gets hidden
        # just because detection couldn't identify the board.
        self.assertTrue(c["is_laptop"])
        self.assertTrue(c["is_laptop12"])
        self.assertTrue(c["has_touchscreen"])
        self.assertTrue(c["has_stylus"])
        self.assertTrue(c["has_expansion_bay"])
        # has_rgbkbd is the one exception — see parsers.py docstring/README
        # for the rationale (defaults to is_desktop, which is False when
        # the model can't be identified at all).
        self.assertFalse(c["has_rgbkbd"])

    def test_empty_input_fails_open(self):
        c = detect_model("")
        self.assertFalse(c["detected"])
        self.assertTrue(c["is_laptop"])


class TestChassis(unittest.TestCase):
    """The short name the Overview heading uses.

    The full board string carries the mainboard generation too, which is
    what the sub-line is for; 22px of heading only fits the chassis.
    """

    def test_each_recognised_chassis(self):
        for text, expected in ((VERSIONS_L12, "Laptop 12"),
                               (VERSIONS_L13_NO_TOUCH, "Laptop 13"),
                               (VERSIONS_L16, "Laptop 16"),
                               (VERSIONS_DESKTOP, "Desktop")):
            self.assertEqual(detect_model(text)["chassis"], expected)

    def test_an_unrecognised_board_has_no_chassis(self):
        # Empty rather than a guess: the UI says "Unknown device" itself.
        self.assertEqual(detect_model(VERSIONS_GARBAGE)["chassis"], "")

    def test_the_full_board_string_is_still_there(self):
        caps = detect_model(VERSIONS_L16)
        self.assertIn("Laptop 16", caps["model"])
        self.assertIn("7040", caps["model"])


class TestSections(unittest.TestCase):

    def test_groups_indented_rows_under_their_header(self):
        found = sections(VERSIONS_L12)
        self.assertIn("Mainboard Hardware", found)
        self.assertTrue(any(row.startswith("Type:")
                            for row in found["Mainboard Hardware"]))

    def test_blank_lines_are_ignored(self):
        self.assertEqual(sections("A\n\n  x: 1\n"), {"A": ["x: 1"]})

    def test_empty_input(self):
        self.assertEqual(sections(""), {})
        self.assertEqual(sections(None), {})


FIRMWARE_SECTIONED = """Mainboard Hardware
  Type:           Laptop 13 (AMD Ryzen AI 300 Series)
EC Firmware
  Build version:  "hx30 0.1.4"
  Current image:  RO
BIOS
  Version: 3.03
"""

FIRMWARE_INLINE = """Mainboard Type: Laptop 13 (AMD Ryzen AI 300 Series)
EC Firmware: hx30 0.1.4
BIOS: 3.03
"""


class TestFirmware(unittest.TestCase):

    def test_sectioned_output(self):
        self.assertEqual(parse_firmware(FIRMWARE_SECTIONED),
                         {"ec": "hx30 0.1.4", "bios": "3.03"})

    def test_inline_output(self):
        # An older shape of the same information; both are accepted because
        # the CLI does not guarantee its format.
        self.assertEqual(parse_firmware(FIRMWARE_INLINE),
                         {"ec": "hx30 0.1.4", "bios": "3.03"})

    def test_missing_values_come_back_empty(self):
        # The Overview drops a field it cannot read rather than printing a
        # placeholder that looks like a reading.
        self.assertEqual(parse_firmware(VERSIONS_GARBAGE),
                         {"ec": "", "bios": ""})

    def test_empty_input(self):
        self.assertEqual(parse_firmware(""), {"ec": "", "bios": ""})


class TestToolVersion(unittest.TestCase):

    def test_reads_a_version(self):
        for text in ("framework_tool 0.4.2", "framework_tool v0.4.2\n",
                     "Framework Tool 1.0"):
            self.assertTrue(parse_tool_version(text))

    def test_exact_value(self):
        self.assertEqual(parse_tool_version("framework_tool 0.4.2"), "0.4.2")

    def test_nothing_to_read(self):
        for text in ("", None, "no version here"):
            self.assertEqual(parse_tool_version(text), "")


class TestSettingValue(unittest.TestCase):

    def test_percentage(self):
        self.assertEqual(parse_setting_value("Max charge level: 80%"), "80")

    def test_key_value(self):
        self.assertEqual(parse_setting_value("Input Deck Mode: auto"), "auto")

    def test_last_value_wins(self):
        self.assertEqual(
            parse_setting_value("Header: x\nFingerprint LED level: medium"),
            "medium")

    def test_declines_to_guess(self):
        # Empty means the row keeps what it had; the raw output is in the
        # drawer either way, so nothing is hidden by not guessing.
        for text in ("", None, "some prose with no value in it"):
            self.assertEqual(parse_setting_value(text), "")


if __name__ == "__main__":
    unittest.main()
