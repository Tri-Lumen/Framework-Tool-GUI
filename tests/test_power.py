"""Unit tests for power.py — CPU detection, backend selection, and every
command the app can build to change a power limit.

No display, no subprocess, no filesystem: power.py takes its I/O in as
arguments precisely so these can run anywhere. The command builders matter
most — a wrong unit here (watts where the tool wants milliwatts) is the kind
of bug that silently asks an SoC for 25 mW.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import power  # noqa: E402

CPUINFO_AMD = """\
processor\t: 0
vendor_id\t: AuthenticAMD
cpu family\t: 25
model name\t: AMD Ryzen 7 7840U w/ Radeon 780M Graphics
"""

CPUINFO_INTEL = """\
processor\t: 0
vendor_id\t: GenuineIntel
model name\t: 13th Gen Intel(R) Core(TM) i5-1340P
"""

CPUINFO_ARM = """\
processor\t: 0
BogoMIPS\t: 50.00
CPU implementer\t: 0x41
CPU architecture: 8
"""

WIN_AMD = "AMD64 Family 25 Model 116 Stepping 1, AuthenticAMD"
WIN_INTEL = "Intel64 Family 6 Model 186 Stepping 2, GenuineIntel"

# Trimmed from RyzenAdj's own README sample output.
RYZENADJ_INFO = """\
CPU Family: Phoenix
SMU BIOS Interface Version: 22
|        Name         |   Value   |     Parameter      |
|---------------------|-----------|--------------------|
| STAPM LIMIT         |    28.000 | stapm-limit        |
| STAPM VALUE         |     7.822 |                    |
| PPT LIMIT FAST      |    35.000 | fast-limit         |
| PPT LIMIT SLOW      |    28.000 | slow-limit         |
| THM LIMIT CORE      |    95.000 | tctl-temp          |
"""


class TestVendorDetection(unittest.TestCase):

    def test_amd_from_cpuinfo(self):
        self.assertEqual(power.detect_vendor(cpuinfo=CPUINFO_AMD),
                         power.VENDOR_AMD)

    def test_intel_from_cpuinfo(self):
        self.assertEqual(power.detect_vendor(cpuinfo=CPUINFO_INTEL),
                         power.VENDOR_INTEL)

    def test_arm_from_cpuinfo(self):
        self.assertEqual(power.detect_vendor(cpuinfo=CPUINFO_ARM),
                         power.VENDOR_ARM)

    def test_windows_processor_identifier(self):
        self.assertEqual(power.detect_vendor(processor_identifier=WIN_AMD),
                         power.VENDOR_AMD)
        self.assertEqual(power.detect_vendor(processor_identifier=WIN_INTEL),
                         power.VENDOR_INTEL)

    def test_arm64_machine_alone_is_enough(self):
        self.assertEqual(power.detect_vendor(machine="arm64"),
                         power.VENDOR_ARM)

    def test_nothing_is_unknown_not_a_guess(self):
        self.assertEqual(power.detect_vendor(), power.VENDOR_UNKNOWN)

    def test_cpu_label_prefers_model_name(self):
        self.assertEqual(power.cpu_label(CPUINFO_AMD, WIN_AMD),
                         "AMD Ryzen 7 7840U w/ Radeon 780M Graphics")

    def test_cpu_label_falls_back_to_windows_string(self):
        self.assertEqual(power.cpu_label("", WIN_INTEL), WIN_INTEL)


class TestBackendSelection(unittest.TestCase):

    def test_amd_linux_prefers_ryzenadj(self):
        got = power.available_backends(power.VENDOR_AMD, "linux",
                                       have=lambda _d: True, rapl_present=True)
        self.assertEqual(got[0], "ryzenadj")

    def test_missing_ryzenadj_is_filtered_out(self):
        got = power.available_backends(power.VENDOR_AMD, "linux",
                                       have=lambda _d: False, rapl_present=True)
        self.assertEqual(got, ["rapl"])

    def test_rapl_needs_the_sysfs_to_exist(self):
        got = power.available_backends(power.VENDOR_INTEL, "linux",
                                       have=lambda _d: False,
                                       rapl_present=False)
        self.assertEqual(got, [])

    def test_rapl_is_never_offered_on_windows(self):
        got = power.available_backends(power.VENDOR_INTEL, "windows",
                                       have=lambda _d: False,
                                       rapl_present=True)
        self.assertEqual(got, ["powercfg"])

    def test_arm_gets_only_the_windows_fallback(self):
        self.assertEqual(
            power.available_backends(power.VENDOR_ARM, "linux"), [])
        self.assertEqual(
            power.available_backends(power.VENDOR_ARM, "windows"),
            ["powercfg"])

    def test_powercfg_is_not_advertised_as_setting_watts(self):
        self.assertFalse(power.BACKENDS["powercfg"]["sets_watts"])
        self.assertTrue(power.BACKENDS["ryzenadj"]["sets_watts"])


class TestValidation(unittest.TestCase):

    def test_watts_round_trip(self):
        self.assertEqual(power.check_watts("25"), 25)
        self.assertEqual(power.check_watts(30.4), 30)

    def test_watts_out_of_range_refused(self):
        for bad in (0, 4, 201, 5000):
            with self.subTest(bad=bad):
                self.assertRaises(power.PowerError, power.check_watts, bad)

    def test_non_numeric_watts_refused(self):
        self.assertRaises(power.PowerError, power.check_watts, "lots")

    def test_percent_bounds(self):
        self.assertEqual(power.check_percent(100), 100)
        self.assertRaises(power.PowerError, power.check_percent, 5)
        self.assertRaises(power.PowerError, power.check_percent, 101)


class TestRyzenadj(unittest.TestCase):

    def test_watts_are_converted_to_milliwatts(self):
        args = power.ryzenadj_args(25, 35)
        self.assertIn("--stapm-limit=25000", args)
        self.assertIn("--slow-limit=25000", args)
        self.assertIn("--fast-limit=35000", args)

    def test_boost_defaults_to_sustained(self):
        self.assertIn("--fast-limit=15000", power.ryzenadj_args(15))

    def test_boost_below_sustained_refused(self):
        self.assertRaises(power.PowerError, power.ryzenadj_args, 30, 20)

    def test_tctl_included_only_when_asked(self):
        self.assertNotIn("--tctl-temp=95", power.ryzenadj_args(25, 25))
        self.assertIn("--tctl-temp=85", power.ryzenadj_args(25, 25, 85))

    def test_absurd_tctl_refused(self):
        self.assertRaises(power.PowerError, power.ryzenadj_args, 25, 25, 130)

    def test_parse_info_table(self):
        table = power.parse_ryzenadj_info(RYZENADJ_INFO)
        self.assertEqual(table["STAPM LIMIT"], 28.0)
        self.assertEqual(table["PPT LIMIT FAST"], 35.0)
        self.assertEqual(table["THM LIMIT CORE"], 95.0)
        self.assertNotIn("Name", table)  # header row skipped

    def test_parse_info_of_junk_is_empty_not_wrong(self):
        # Empty is the signal for "show the raw output instead".
        self.assertEqual(power.parse_ryzenadj_info("command not found"), {})
        self.assertEqual(power.parse_ryzenadj_info(""), {})


class TestRapl(unittest.TestCase):

    ZONES = ["intel-rapl:0", "intel-rapl:0:0", "intel-rapl:1",
             "intel-rapl-mmio:0", "idle_inject"]

    def test_only_package_zones_are_used(self):
        zones = power.rapl_constraint_files(self.ZONES)
        self.assertEqual([z["zone"] for z in zones],
                         ["intel-rapl:0", "intel-rapl:1"])

    def test_constraint_paths(self):
        zone = power.rapl_constraint_files(["intel-rapl:0"])[0]
        self.assertTrue(zone["long"].endswith(
            "intel-rapl:0/constraint_0_power_limit_uw"))
        self.assertTrue(zone["short"].endswith(
            "intel-rapl:0/constraint_1_power_limit_uw"))

    def test_write_command_uses_microwatts(self):
        cmd = power.rapl_write_cmd("/sys/x", 28)
        self.assertEqual(cmd[:2], ["sh", "-c"])
        self.assertIn("28000000", cmd[2])

    def test_write_command_validates_first(self):
        self.assertRaises(power.PowerError, power.rapl_write_cmd, "/sys/x", 900)

    def test_parse_microwatts(self):
        self.assertEqual(power.parse_rapl_uw("28000000\n"), 28.0)
        self.assertIsNone(power.parse_rapl_uw(""))


class TestPowercfg(unittest.TestCase):

    def test_sets_both_ac_and_dc_then_activates(self):
        cmds = power.powercfg_cmds(60)
        self.assertEqual(len(cmds), 3)
        self.assertIn("/setacvalueindex", cmds[0])
        self.assertIn("/setdcvalueindex", cmds[1])
        self.assertIn("/setactive", cmds[2])
        self.assertEqual(cmds[0][-1], "60")

    def test_parse_query_output(self):
        text = ("    Current AC Power Setting Index: 0x0000003c\n"
                "    Current DC Power Setting Index: 0x00000032\n")
        self.assertEqual(power.parse_powercfg_percent(text), 60)

    def test_parse_query_junk(self):
        self.assertIsNone(power.parse_powercfg_percent("nope"))


if __name__ == "__main__":
    unittest.main()
