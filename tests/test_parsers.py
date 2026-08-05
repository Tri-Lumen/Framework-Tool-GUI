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

from frameworkgui.parsers import (  # noqa: E402
    ac_connected,
    bay_orientation,
    detect_model,
    parse_charge_limit,
    parse_firmware,
    parse_fp_brightness,
    parse_fp_level,
    parse_ports,
    parse_setting_value,
    parse_tool_version,
    port_attached,
    port_is_live,
    port_watts,
    sections,
    short_firmware,
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
        from frameworkgui.parsers import (
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
        from frameworkgui.parsers import RE_DESIGN, RE_LFCC
        lfcc = int(RE_LFCC.search(POWER_VV).group(1))
        design = int(RE_DESIGN.search(POWER_VV).group(1))
        health = 100.0 * lfcc / design
        self.assertAlmostEqual(health, 94.84, places=1)


class TestThermalParser(unittest.TestCase):
    def test_temps_and_rpm(self):
        from frameworkgui.parsers import RE_RPM, RE_TEMP
        temps = dict(RE_TEMP.findall(THERMAL))
        self.assertEqual(temps["APU"], "62")
        self.assertEqual(temps["F75303_CPU"], "44")
        self.assertEqual(RE_RPM.search(THERMAL).group(1), "7281")

    def test_zero_rpm_still_matches(self):
        from frameworkgui.parsers import RE_RPM
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


# `--pdports-chromebook`: the generic Chromium EC path, used when the
# Framework-specific command the app asks for first is not implemented by
# this EC firmware. Different header, different keys, no "Negotiated:" line.
PDPORTS_CHROMEBOOK = """USB-C Port 0 (Right Back):
  Role:          Sink
  Charging Type: PD
  Voltage Now:   20.000 V, Max: 20.000 V
  Current Lim:   5000 mA, Max: 5000 mA
  Dual Role:     DRP
  Max Power:     100.0 W
USB-C Port 1 (Right Front):
  Role:          Disconnected
  Charging Type: None
  Voltage Now:   0.0 V, Max: 0.0 V
  Current Lim:   0 mA, Max: 0 mA
  Dual Role:     Charger
  Max Power:     0.0 W
"""

# What --pdports actually prints on an EC without the command: it still
# exits 0, having named no port at all. This is why the app falls back.
PDPORTS_UNSUPPORTED = """Failed to send host command
EC returned error: InvalidCommand
"""


class TestPortsChromebookFormat(unittest.TestCase):
    """The second port format has to parse, or the fallback buys nothing."""

    def test_ports_and_bay_names_are_read(self):
        ports = parse_ports(PDPORTS_CHROMEBOOK)
        self.assertEqual([p["port"] for p in ports], ["0", "1"])
        self.assertEqual(ports[0]["name"], "Right Back")
        self.assertEqual(ports[1]["name"], "Right Front")

    def test_role_is_not_confused_with_data_or_dual_role(self):
        ports = parse_ports(PDPORTS_CHROMEBOOK)
        self.assertEqual(ports[0]["role"], "Sink")
        self.assertEqual(ports[1]["role"], "Disconnected")

    def test_watts_are_derived_from_voltage_and_current(self):
        ports = parse_ports(PDPORTS_CHROMEBOOK)
        self.assertAlmostEqual(ports[0]["watts"], 100.0)
        self.assertAlmostEqual(ports[0]["volts"], 20.0)
        self.assertEqual(ports[0]["ma"], 5000)

    def test_max_power_is_kept_apart_from_negotiated_power(self):
        # The ceiling is not the contract; showing it as one would overstate
        # what an idle port is delivering.
        ports = parse_ports(PDPORTS_CHROMEBOOK)
        self.assertEqual(ports[0]["max_watts"], 100.0)
        self.assertNotIn("watts", ports[1])

    def test_a_disconnected_port_is_not_live(self):
        ports = parse_ports(PDPORTS_CHROMEBOOK)
        self.assertTrue(port_is_live(ports[0]))
        self.assertFalse(port_is_live(ports[1]))

    def test_the_original_format_still_parses(self):
        ports = parse_ports(PDPORTS)
        self.assertEqual([p["port"] for p in ports], ["0", "1", "3"])
        self.assertAlmostEqual(ports[0]["watts"], 240.0)
        self.assertTrue(port_is_live(ports[0]))
        self.assertFalse(port_is_live(ports[2]))   # no Negotiated line

    def test_an_unsupported_command_names_no_ports(self):
        # Exits 0 and prints errors — the app must see "nothing here" and
        # move on to the fallback rather than treat it as a successful read.
        self.assertEqual(parse_ports(PDPORTS_UNSUPPORTED), [])

    def test_port_is_live_tolerates_junk(self):
        self.assertFalse(port_is_live(None))
        self.assertFalse(port_is_live({}))
        self.assertFalse(port_attached(None))
        self.assertIsNone(port_watts({}))

    def test_the_charging_type_is_kept(self):
        ports = parse_ports(PDPORTS_CHROMEBOOK)
        self.assertEqual(ports[0]["charging"], "PD")
        # "None" is not a charging type worth repeating.
        self.assertNotIn("charging", ports[1])


# The shape that broke the Overview on a real Laptop 13: the port the
# machine was charging on reported its role and nothing else usable, and
# every bay showed "disconnected · idle" while the AC card read 51.5 W.
PDPORTS_SINK_WITHOUT_FIGURES = """USB-C Port 0 (Right Back):
  Role:          Sink
  Charging Type: PD
  Voltage Now:   20.0 V, Max: 20.0 V
  Current Lim:   0 mA, Max: 0 mA
  Dual Role:     DRP
  Max Power:     0.0 W
USB-C Port 1 (Right Front):
  Role:          Disconnected
  Charging Type: None
  Voltage Now:   0.0 V, Max: 0.0 V
  Current Lim:   0 mA, Max: 0 mA
"""


class TestAttachedWithoutFigures(unittest.TestCase):
    """A port can be in use and still report no usable wattage.

    The role is the only reliable statement either command makes about
    whether something is plugged in, so it — not a derived wattage — is
    what decides. Asking for watts first reported the port the machine was
    running on as idle.
    """

    def setUp(self):
        self.ports = parse_ports(PDPORTS_SINK_WITHOUT_FIGURES)

    def test_a_sink_with_no_current_is_still_attached(self):
        self.assertTrue(port_attached(self.ports[0]))
        self.assertFalse(port_is_live(self.ports[0]))

    def test_the_voltage_survives_on_its_own(self):
        # Voltage and current used to be taken as a pair, so a port with
        # one and not the other came back with neither.
        self.assertEqual(self.ports[0]["volts"], 20.0)
        self.assertEqual(self.ports[0]["ma"], 0)
        self.assertNotIn("watts", self.ports[0])

    def test_no_wattage_is_reported_rather_than_zero(self):
        self.assertIsNone(port_watts(self.ports[0]))

    def test_a_disconnected_port_is_still_disconnected(self):
        # The fail-open direction has a limit: a voltage rail on an empty
        # port must not read as something plugged in.
        self.assertFalse(port_attached(self.ports[1]))
        self.assertIsNone(port_watts(self.ports[1]))

    def test_a_role_of_none_reads_as_idle(self):
        self.assertFalse(port_attached({"role": "None"}))
        self.assertFalse(port_attached({"role": "", "watts": 60.0}))

    def test_an_unrecognised_role_is_treated_as_attached(self):
        # Fail open: a firmware that invents a connected state should not
        # make the bay disappear.
        self.assertTrue(port_attached({"role": "SinkStandby"}))


class TestBayOrientation(unittest.TestCase):
    """(side, position) out of a --pdports-chromebook bay name."""

    def test_all_four_combinations(self):
        self.assertEqual(bay_orientation("Right Back"), ("right", "back"))
        self.assertEqual(bay_orientation("Right Front"), ("right", "front"))
        self.assertEqual(bay_orientation("Left Back"), ("left", "back"))
        self.assertEqual(bay_orientation("Left Front"), ("left", "front"))

    def test_case_insensitive(self):
        self.assertEqual(bay_orientation("left front"), ("left", "front"))

    def test_missing_name_is_unknown_not_a_guess(self):
        # Plain --pdports never names a bay at all.
        self.assertEqual(bay_orientation(None), (None, None))
        self.assertEqual(bay_orientation(""), (None, None))

    def test_unrecognised_words_are_unknown(self):
        # A board using different vocabulary must not be guessed into a
        # side or a position it never named.
        self.assertEqual(bay_orientation("Rear Panel"), (None, None))
        self.assertEqual(bay_orientation("Right"), ("right", None))


class TestShortFirmware(unittest.TestCase):
    """An EC version string is mostly provenance, and it does not fit."""

    FULL = ("azalea_v3.4.113405-ec:e0a4f2,os:7b88e1,cmsis:4aa3ff "
            "2026-05-20 05:29:08 marigold1@ip-172-26-3-226")

    def test_the_version_survives_and_the_rest_does_not(self):
        self.assertEqual(short_firmware(self.FULL), "azalea_v3.4.113405")

    def test_a_short_version_is_left_alone(self):
        self.assertEqual(short_firmware("3.03"), "3.03")
        self.assertEqual(short_firmware("hx30 0.1.4"), "hx30")

    def test_anything_still_too_long_is_cut_not_dropped(self):
        value = "a" * 60
        self.assertEqual(len(short_firmware(value)), 28)
        self.assertTrue(short_firmware(value).endswith("…"))

    def test_nothing_to_shorten(self):
        for value in ("", None, "   "):
            self.assertEqual(short_firmware(value), "")


class TestChargeLimit(unittest.TestCase):
    """--charge-limit prints two percentages and the app means the second."""

    def test_the_maximum_is_the_charge_limit(self):
        self.assertEqual(parse_charge_limit("Minimum 0%, Maximum 80%"), "80")

    def test_a_full_charge_limit_is_not_reported_as_zero(self):
        # The bug this exists for: the generic reader took the first
        # percentage, so a machine limited to 100% displayed "0%".
        self.assertEqual(parse_charge_limit("Minimum 0%, Maximum 100%"),
                         "100")

    def test_an_unexpected_shape_falls_back_rather_than_fail(self):
        self.assertEqual(parse_charge_limit("Charge limit: 75%"), "75")

    def test_nothing_parseable_is_empty(self):
        self.assertEqual(parse_charge_limit(""), "")


FP_BLOCK = """Fingerprint LED Brightness
  Requested:  UltraLow
  Brightness: 55%
"""
FP_AUTO = """Fingerprint LED Brightness
  Requested:  Auto
  Brightness: 100%
"""


class TestFingerprintLed(unittest.TestCase):
    """Both fingerprint reads print a level *and* a percentage."""

    def test_the_level_comes_back_as_the_cli_spells_it(self):
        # The CLI prints the Rust enum name; it accepts the kebab-case form,
        # and the combo box lists what it accepts.
        self.assertEqual(parse_fp_level(FP_BLOCK), "ultra-low")

    def test_auto_is_read_back(self):
        self.assertEqual(parse_fp_level(FP_AUTO), "auto")

    def test_the_percentage_is_read_separately(self):
        self.assertEqual(parse_fp_brightness(FP_BLOCK), "55")
        self.assertEqual(parse_fp_brightness(FP_AUTO), "100")

    def test_nothing_parseable_is_empty(self):
        self.assertEqual(parse_fp_level("no such block"), "")
        self.assertEqual(parse_fp_brightness("no such block"), "")


class TestAcConnected(unittest.TestCase):
    """The charger registers read non-zero on battery, so ask first."""

    def test_connected(self):
        self.assertIs(ac_connected("  AC is:            connected"), True)

    def test_not_connected(self):
        self.assertIs(ac_connected("  AC is:            not connected"),
                      False)

    def test_unstated_is_none(self):
        # None, not False: "it did not say" is not "there is no adapter".
        self.assertIsNone(ac_connected("Fan Speed: 0 RPM"))

    def test_the_sample_output_is_connected(self):
        self.assertIs(ac_connected(POWER_VV), True)
