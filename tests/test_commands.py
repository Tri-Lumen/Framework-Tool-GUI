"""Every command the app can issue has to be a real one.

The GUI's whole job is shelling out to other programs, so a typo in an
argument is not a crash — it is a button that runs something, gets a
non-zero exit and an unhelpful error, and looks like a hardware problem.
Nothing else in the suite catches that: `navigation.py` is data, and the
smoke tests run against a stub binary that accepts anything.

So this file holds the flags framework_tool actually publishes, transcribed
from upstream's `--help` and its clap definitions, and asserts that every
argument the app builds appears in it. The list is checked in rather than
discovered at run time on purpose — the tests must not need framework_tool
installed, a network, or a Framework device.

Where a flag takes a fixed set of values, the values are here too: those
come from the Rust enums upstream derives its parser from, which are the
authority, not the `--help` text (the help for --inputdeck-mode is missing
one of its own modes).

If upstream renames a flag, this file is where that shows up — update it
alongside the caller, and read the "not yet verified" note in CLAUDE.md
about output formats before assuming the rest still works.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import framework_gui  # noqa: E402
import navigation  # noqa: E402
import power  # noqa: E402

# ---------------------------------------------------------------------------
# framework_tool's published interface.
# ---------------------------------------------------------------------------

FRAMEWORK_TOOL_FLAGS = {
    # informational
    "--versions", "--version", "--info", "--sysinfo", "--uptimeinfo",
    "--s0ix-counter", "--hello", "--protoinfo", "--switches", "--port80read",
    "--panicinfo", "--sensors", "--power", "--thermal", "--thermalget",
    "--thermalset", "--privacy", "--intrusion", "--inputdeck",
    "--expansion-bay", "--nvidia", "--stylus-battery", "--get-gpio",
    "--meinfo", "--console", "--dump-ec-flash", "--driver", "--pd-addrs",
    "--pd-ports", "--dry-run", "--verbose",
    # ports and expansion cards
    "--pdports", "--pdports-chromebook", "--pd-info", "--pd-reset",
    "--pd-disable", "--pd-enable", "--dp-hdmi-info", "--dp-hdmi-update",
    "--audio-card-info",
    # fans
    "--fansetduty", "--fansetrpm", "--autofanctrl",
    # battery / charging
    "--charge-limit", "--charge-current-limit", "--charge-rate-limit",
    # input and LEDs
    "--fp-led-level", "--fp-brightness", "--kblight", "--rgbkbd",
    "--remap-key", "--inputdeck-mode", "--tablet-mode", "--touchscreen-enable",
    # self-test
    "-t", "--test", "--test-retimer",
    # firmware (blocked in this app, listed so the BLOCKED set can be
    # asserted against real flags rather than invented ones)
    "--flash-ec", "--flash-ro-ec", "--flash-rw-ec", "--flash-gpu-descriptor",
    "--flash-gpu-descriptor-file", "--dump-gpu-descriptor-file",
    "--reboot-ec", "--ec-hib-delay", "--hash", "--capsule", "--dump",
    "--h2o-capsule", "--pd-bin", "--ec-bin", "--compare-version", "--device",
    "-f", "--force",
}

# Repeatable short verbosity: -v, -vv, -vvv are all valid.
VERBOSITY = re.compile(r"^-v+$")

# Fixed value sets, from the clap ValueEnums upstream derives.
FLAG_VALUES = {
    "--inputdeck-mode": {"auto", "off", "on", "reset"},
    "--tablet-mode": {"auto", "tablet", "laptop"},
    "--fp-led-level": {"high", "medium", "low", "ultra-low", "auto"},
    "--console": {"recent", "follow"},
    "--touchscreen-enable": {"true", "false"},
}


# Flags in framework_gui.py that belong to a *different* program. The
# source sweep below is deliberately broad — it matches every quoted flag in
# every argument list rather than only the framework_tool call sites — so
# these are declared rather than filtered by guesswork. Anything not listed
# here and not a framework_tool flag fails the sweep, which is the point.
OTHER_PROGRAM_FLAGS = {
    "--host": "flatpak-spawn --host, the sandbox escape for host commands",
    "-c": "sh -c, used to write a RAPL constraint file through pkexec",
    "-i": "ryzenadj -i, the limit read-back after Apply",
}


def is_known_flag(token):
    return (token in FRAMEWORK_TOOL_FLAGS
            or bool(VERBOSITY.match(token)))


def flags_in(args):
    return [a for a in args if str(a).startswith("-")]


class TestSettingsRowsUseRealFlags(unittest.TestCase):

    def test_every_set_command_is_a_real_flag(self):
        for row in navigation.SETTINGS_ROWS:
            for flag in flags_in(row["set"]):
                self.assertTrue(is_known_flag(flag),
                                f"{row['key']} sets with unknown {flag}")

    def test_every_get_command_is_a_real_flag(self):
        for row in navigation.SETTINGS_ROWS:
            for flag in flags_in(row["get"] or ()):
                self.assertTrue(is_known_flag(flag),
                                f"{row['key']} reads with unknown {flag}")

    def test_every_auto_command_is_a_real_flag_with_a_real_value(self):
        for row in navigation.SETTINGS_ROWS:
            auto = row.get("auto")
            if not auto:
                continue
            flag, value = auto[0], auto[1]
            self.assertTrue(is_known_flag(flag),
                            f"{row['key']} autos with unknown {flag}")
            allowed = FLAG_VALUES.get(flag)
            self.assertIsNotNone(allowed, f"{flag} takes no fixed values")
            self.assertIn(value, allowed,
                          f"{row['key']} passes {flag} {value!r}")

    def test_choice_rows_offer_only_values_the_cli_accepts(self):
        """A combo entry the CLI rejects is a Set button that always fails."""
        for row in navigation.SETTINGS_ROWS:
            if row["kind"] != "choice":
                continue
            allowed = FLAG_VALUES.get(row["set"][0])
            if allowed is None:
                continue
            for choice in row["choices"]:
                self.assertIn(
                    choice, allowed,
                    f"{row['key']} offers {choice!r}, which "
                    f"{row['set'][0]} does not accept")

    def test_a_rows_default_is_one_of_its_choices(self):
        for row in navigation.SETTINGS_ROWS:
            if row["kind"] == "choice":
                self.assertIn(row["default"], row["choices"], row["key"])

    def test_a_row_naming_a_parser_names_one_that_exists(self):
        for row in navigation.SETTINGS_ROWS:
            name = row.get("parse")
            if name is not None:
                self.assertIn(name, framework_gui.App.SETTING_PARSERS,
                              f"{row['key']} names unknown parser {name!r}")

    def test_a_row_with_no_read_offers_no_get(self):
        """`get: None` means the CLI genuinely cannot read it back.

        The alternative — running something adjacent and calling it the
        answer — is what made the fingerprint level read return a
        percentage.
        """
        for row in navigation.SETTINGS_ROWS:
            if row["get"] is None:
                self.assertIsNone(row.get("parse"), row["key"])


class TestPortQueriesUseRealFlags(unittest.TestCase):

    def test_every_port_query_is_a_real_flag(self):
        for query in navigation.PORT_QUERIES:
            for flag in flags_in(query["args"]):
                self.assertTrue(is_known_flag(flag),
                                f"{query['key']} runs unknown {flag}")


class TestAppCommandsUseRealFlags(unittest.TestCase):
    """Sweep the source for argument lists handed to _exec/run."""

    SOURCE = None

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(__file__), "..",
                            "framework_gui.py")
        with open(path, encoding="utf-8") as fh:
            cls.SOURCE = fh.read()

    def emitted_flags(self):
        """Every framework_tool flag that appears in an argument list.

        Commands reach the CLI three ways — a literal `_exec([...])`, a
        helper like `_read_into(..., [...])`, and a loop over several
        argument lists — so this matches the *lists*, not the call sites.
        Anything quoted in a list next to a known flag counts.
        """
        found = set()
        for body in re.findall(r"\[([^\[\]]*)\]", self.SOURCE):
            tokens = re.findall(r'"(-[^"\s]*)"', body)
            found.update(tokens)
        return found

    def test_the_sweep_finds_something(self):
        # Guard against the regex silently matching nothing and the whole
        # class passing vacuously.
        self.assertGreater(len(self.emitted_flags()), 10)

    def test_every_emitted_flag_is_real(self):
        for flag in sorted(self.emitted_flags()):
            if flag in OTHER_PROGRAM_FLAGS:
                continue
            self.assertTrue(
                is_known_flag(flag),
                f"framework_gui.py runs '{flag}', which framework_tool does "
                f"not publish. If it belongs to another program, declare it "
                f"in OTHER_PROGRAM_FLAGS with what it is for.")

    def test_the_other_program_flags_are_all_still_used(self):
        """Keeps the exemption list from silently outliving its callers."""
        emitted = self.emitted_flags()
        for flag in OTHER_PROGRAM_FLAGS:
            self.assertIn(flag, emitted,
                          f"{flag} is exempted but no longer emitted — "
                          f"drop it from OTHER_PROGRAM_FLAGS")

    def test_the_recent_suggestions_are_real(self):
        for suggestion in navigation.RECENT_SUGGESTIONS:
            for flag in flags_in(suggestion.split()):
                self.assertTrue(is_known_flag(flag),
                                f"suggested command uses unknown {flag}")

    def test_blocked_flags_are_flags_that_exist(self):
        """Blocking a misspelled flag protects nothing."""
        for flag in framework_gui.App.BLOCKED:
            self.assertIn(flag, FRAMEWORK_TOOL_FLAGS,
                          f"{flag} is blocked but is not a real flag")

    def test_nothing_blocked_is_reachable_from_a_button(self):
        self.assertEqual(
            framework_gui.App.BLOCKED & self.emitted_flags(), set(),
            "a blocked flag is wired to a control")

    def test_the_port_fallback_is_wired_up(self):
        # The reason bays read "not read" on an EC without the Framework
        # -specific command: --pdports exits 0 having printed only errors.
        self.assertIn("--pdports-chromebook", self.emitted_flags())


class TestPowerBackendCommands(unittest.TestCase):
    """The CPU-limit backends drive other programs, with their own flags."""

    RYZENADJ_FLAGS = {"--stapm-limit", "--fast-limit", "--slow-limit",
                      "--tctl-temp", "--info", "-i"}

    def test_ryzenadj_commands_use_published_flags(self):
        for args in (power.ryzenadj_args(25),
                     power.ryzenadj_args(25, 35),
                     power.ryzenadj_args(25, 35, tctl_c=85)):
            for token in args:
                flag = str(token).split("=", 1)[0]
                self.assertIn(flag, self.RYZENADJ_FLAGS,
                              f"ryzenadj called with unknown {flag}")

    def test_every_backend_names_a_dependency_that_exists(self):
        import deps
        for backend_id, backend in power.BACKENDS.items():
            dependency = backend["dependency"]
            if dependency is None:
                continue
            try:
                deps.get(dependency)
            except KeyError:                       # pragma: no cover
                self.fail(f"{backend_id} needs unknown dependency "
                          f"{dependency!r}")

    def test_intel_has_a_backend_on_both_platforms(self):
        """Intel is not left with nothing on either OS.

        Linux gets RAPL, which sets real watts and needs nothing installed.
        Windows gets powercfg only — a frequency cap, not a wattage — because
        no Intel tool with a scriptable command line can be shipped this way;
        `sets_watts` is what stops the UI calling it watts.
        """
        linux = power.available_backends(power.VENDOR_INTEL, "linux",
                                         rapl_present=True)
        self.assertIn("rapl", linux)
        self.assertTrue(power.BACKENDS["rapl"]["sets_watts"])

        windows = power.available_backends(power.VENDOR_INTEL, "windows")
        self.assertEqual(windows, ["powercfg"])
        self.assertFalse(power.BACKENDS["powercfg"]["sets_watts"])

    def test_amd_gets_a_real_tdp_backend_on_both_platforms(self):
        for os_name in ("linux", "windows"):
            backends = power.available_backends(power.VENDOR_AMD, os_name,
                                                rapl_present=True)
            self.assertEqual(backends[0], "ryzenadj", os_name)


if __name__ == "__main__":
    unittest.main()
