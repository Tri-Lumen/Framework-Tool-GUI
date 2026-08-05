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

from frameworkgui import power  # noqa: E402

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

    def test_a_brand_string_beats_both(self):
        # Windows has no /proc/cpuinfo and %PROCESSOR_IDENTIFIER% is a
        # CPUID dump; the registry's ProcessorNameString is the real name.
        self.assertEqual(
            power.cpu_label("", WIN_AMD, "AMD Ryzen 7 7840U w/ Radeon 780M "
                                         "Graphics"),
            "AMD Ryzen 7 7840U w/ Radeon 780M Graphics")

    def test_an_empty_brand_string_is_not_a_name(self):
        self.assertEqual(power.cpu_label("", WIN_INTEL, "   "), WIN_INTEL)


class TestShortCpuLabel(unittest.TestCase):
    """The Overview heading has one line, and these strings do not fit it.

    On a real Laptop 13 the sub-line read "Laptop 13 (AMD Ryzen 7040Series)
    · AMD64 Family 25 Model 116 Stepping 1, AuthenticAMD · EC azalea_v3.4…"
    and wrapped onto three lines, most of it saying nothing.
    """

    def test_amd_marketing_string(self):
        self.assertEqual(
            power.short_cpu_label("AMD Ryzen 7 7840U w/ Radeon 780M Graphics"),
            "Ryzen 7 7840U")

    def test_amd_with_the_other_spelling(self):
        self.assertEqual(
            power.short_cpu_label("AMD Ryzen 5 7640U with Radeon Graphics"),
            "Ryzen 5 7640U")

    def test_intel_marketing_string(self):
        self.assertEqual(
            power.short_cpu_label("Intel(R) Core(TM) i7-1260P CPU @ 2.10GHz"),
            "Core i7-1260P")

    def test_intel_generation_prefix_is_kept(self):
        self.assertEqual(
            power.short_cpu_label("13th Gen Intel(R) Core(TM) i5-1340P"),
            "13th Gen Core i5-1340P")

    def test_a_desktop_part(self):
        self.assertEqual(
            power.short_cpu_label("AMD Ryzen 9 7950X 16-Core Processor"),
            "Ryzen 9 7950X")

    def test_a_cpuid_dump_is_not_a_name(self):
        # The whole reason this exists: it names a family, not a chip, so
        # there is nothing in it worth the width.
        self.assertEqual(power.short_cpu_label(WIN_AMD), "")
        self.assertEqual(power.short_cpu_label(WIN_INTEL), "")
        self.assertEqual(
            power.short_cpu_label("ARM64 Family 8 Model 1 Stepping 0"), "")

    def test_nothing_to_shorten(self):
        for value in ("", None, "   "):
            self.assertEqual(power.short_cpu_label(value), "")

    def test_an_unrecognised_name_is_passed_through(self):
        # This trims known noise; it does not invent names.
        self.assertEqual(power.short_cpu_label("Snapdragon X Elite"),
                         "Snapdragon X Elite")

    def test_whitespace_is_normalised(self):
        self.assertEqual(power.short_cpu_label("  AMD   Ryzen 7  7840U  "),
                         "Ryzen 7 7840U")


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


class TestPersistence(unittest.TestCase):
    """The app never sets persistence up — it links to how. These guard the
    links, and guard the one backend that is *already* persistent from being
    described as volatile."""

    def test_powercfg_is_the_persistent_one(self):
        # powercfg edits the saved power scheme, so Windows restores it
        # itself. Telling a user to re-apply it every boot would be wrong.
        self.assertFalse(power.is_volatile("powercfg"))
        self.assertTrue(power.is_volatile("ryzenadj"))
        self.assertTrue(power.is_volatile("rapl"))

    def test_every_backend_has_links_for_every_os_it_runs_on(self):
        for bid, backend in power.BACKENDS.items():
            for os_name in backend["platforms"]:
                with self.subTest(backend=bid, os=os_name):
                    links = power.persistence_links(bid, os_name)
                    self.assertTrue(links, "no persistence links")
                    for label, url in links:
                        self.assertTrue(label)
                        self.assertTrue(url.startswith("https://"))

    def test_ryzenadj_links_differ_by_os(self):
        # systemd on Linux, Task Scheduler on Windows — handing a Windows
        # user a systemd page would be useless.
        linux = dict(power.persistence_links("ryzenadj", "linux"))
        windows = dict(power.persistence_links("ryzenadj", "windows"))
        self.assertTrue(any("systemd" in u.lower() for u in linux.values()))
        self.assertTrue(any("schtasks" in u.lower() for u in windows.values()))

    def test_every_backend_has_a_note(self):
        for bid in power.BACKENDS:
            self.assertTrue(power.persistence_note(bid))

    def test_unknown_backend_degrades_quietly(self):
        # The tab renders before a backend is chosen; None must not raise.
        self.assertEqual(power.persistence_links(None, "linux"), [])
        self.assertEqual(power.persistence_note("nonsense"), "")
        self.assertTrue(power.is_volatile(None))  # assume the risky answer

    def test_no_links_for_an_os_the_backend_does_not_run_on(self):
        self.assertEqual(power.persistence_links("rapl", "windows"), [])


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
