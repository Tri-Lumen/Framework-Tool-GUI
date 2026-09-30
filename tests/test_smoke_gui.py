"""
End-to-end smoke tests for the Qt app: build App() for real, run an actual
event loop, point it at a stub framework_tool script, and assert on the
capability dict plus which controls survive gating.

Qt has no equivalent of Tkinter's cross-thread marshalling problem, but the
same shape of test still applies: the device scan runs on a worker thread and
reports back through a signal, so the test has to let the event loop run
until the signal has been delivered rather than polling the app object.

Needs a display (or Qt's offscreen platform). On headless Linux either of:

    QT_QPA_PLATFORM=offscreen python3 -m unittest tests.test_smoke_gui -v
    xvfb-run -a python3 -m unittest tests.test_smoke_gui -v

Skips automatically if PySide6 is missing or no platform plugin will start,
and on Windows, where the POSIX stub binary cannot run - rather than failing
the whole suite in either case.
"""

import os
import stat
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# The stub binary below is an extension-less script with a shebang: Windows
# neither resolves it via PATHEXT nor executes it, so these tests are POSIX
# only. Skipped rather than failed on Windows - the logic modules' own tests
# still cover the gating rules there.
STUB_SUPPORTED = not sys.platform.startswith("win")

# The app persists its appearance and drawer height through appstate.py,
# which reads the environment for the config location. Point that at a
# throwaway directory before importing anything: without this the tests
# rewrite the settings of whoever is running them, and the drawer-clamp test
# in particular would leave their drawer at its 70px minimum.
_CONFIG_DIR = tempfile.mkdtemp(prefix="framework-gui-tests-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG_DIR
os.environ["LOCALAPPDATA"] = _CONFIG_DIR

QT_AVAILABLE = False
if STUB_SUPPORTED:
    # A headless runner has no display; offscreen is the platform plugin
    # that needs none, and it renders the same widget tree.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

        _probe = QApplication.instance() or QApplication([])
        QT_AVAILABLE = True
    except Exception:  # noqa: BLE001 - no PySide6, no platform plugin, ...
        QT_AVAILABLE = False

CAN_RUN = QT_AVAILABLE and STUB_SUPPORTED

if CAN_RUN:
    from frameworkgui import app as fg  # noqa: E402
    from frameworkgui import device_images, navigation, parsers  # noqa: E402,I001


def make_stub_binary(tmpdir, versions_output):
    """Write a fake `framework_tool` that answers --versions and prints a
    placeholder for anything else, then return the directory to prepend to
    PATH."""
    path = os.path.join(tmpdir, "framework_tool")
    script = textwrap.dedent('''\
        #!/usr/bin/env python3
        import sys
        if "--versions" in sys.argv:
            print({versions!r})
            sys.exit(0)
        if "--version" in sys.argv:
            print("framework_tool 0.4.2")
            sys.exit(0)
        print("stub output")
        sys.exit(0)
        ''').format(versions=versions_output)
    with open(path, "w") as fh:
        fh.write(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP
             | stat.S_IXOTH)
    return tmpdir


# Generous: the first run in a cold environment pays for .pyc compilation
# and for spawning the stub binary (itself a Python process). A tight
# timeout here shows up as a flaky, hard-to-read failure in CI, not as a
# faster test run - the watcher quits the loop as soon as detection lands.
DETECT_TIMEOUT_MS = 30000


def buttons_in(widget):
    """Every button label under a widget, in tree order."""
    return [b.text() for b in widget.findChildren(QPushButton) if b.text()]


def labels_in(widget):
    """Every non-empty QLabel string under a widget."""
    from PySide6.QtWidgets import QLabel
    return [le.text() for le in widget.findChildren(QLabel) if le.text()]


def settle(app, window, timeout_ms=DETECT_TIMEOUT_MS):
    """Spin the event loop until the launch device scan has reported back.

    Tests that build an App directly need this for the same reason
    `_drive_app` waits: App.__init__ schedules a scan on a background
    thread, and tearing the window down while that thread is still going to
    emit into it is a race, not a clean exit.
    """
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(app.quit)
    deadline.start(timeout_ms)

    def watcher():
        if window.caps.get("model") != "Detecting…" and not window._busy:
            app.quit()
        else:
            QTimer.singleShot(25, watcher)

    QTimer.singleShot(25, watcher)
    app.exec()
    deadline.stop()


def _drive_app(timeout_ms):
    """Run a real App through a real event loop until the device scan has
    settled, then snapshot caps and the controls on each section.

    Raises if detection never completed, so a timeout reads as a timeout
    rather than as a KeyError further down the test.
    """
    app = QApplication.instance() or QApplication([])
    window = fg.App()
    results = {}

    def snapshot():
        results["caps"] = dict(window.caps)
        results["cpu"] = dict(window.cpu)
        results["driver_entry"] = dict(window.driver_entry)
        results["driver_all"] = list(window.driver_all)
        results["power_backend"] = window.power_backend
        results["tool_keys"] = sorted(window.tool_rows)
        results["port_keys"] = sorted(window.port_buttons)
        results["settings_keys"] = sorted(window.settings_widgets)
        results["sections"] = sorted(window.pages)
        results["title"] = window.windowTitle()
        results["tool_version"] = window.tool_version
        results["firmware"] = dict(window.firmware)
        results["scanned_label"] = window.scanned_label.text()
        for section, page in window.pages.items():
            results["buttons:" + section] = buttons_in(page)
            results["labels:" + section] = labels_in(page)

    def watcher():
        # "Detecting…" is the pre-scan placeholder; anything else means the
        # scan thread has reported back (success or fail-open). Also wait
        # for _busy: running as root (true in most CI/sandbox containers),
        # _apply_detection kicks off a second background thread to read
        # sensors right after detection finishes, and closing the window
        # while that thread is still going raced it into emitting a signal
        # into a torn-down QObject - the same race settle() below already
        # guards against.
        if window.caps.get("model") != "Detecting…" and not window._busy:
            snapshot()
            app.quit()
        else:
            QTimer.singleShot(50, watcher)

    QTimer.singleShot(50, watcher)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(app.quit)
    timeout.start(timeout_ms)
    app.exec()

    # Each test builds a fresh App in the same process. Qt cleans up on
    # deletion, but the window has to go before the next one is built or
    # the two share the application's style sheet and the second one's
    # assertions read the first one's widgets.
    timeout.stop()
    window.close()
    window.deleteLater()
    app.processEvents()

    if "caps" not in results:
        raise AssertionError(
            "device detection did not complete within {} ms".format(
                timeout_ms))
    return results


def run_app_and_capture(versions_output, timeout_ms=DETECT_TIMEOUT_MS):
    """As _drive_app, with PATH pointed at a stub framework_tool that prints
    `versions_output` for --versions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        make_stub_binary(tmpdir, versions_output)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = tmpdir + os.pathsep + old_path
        try:
            return _drive_app(timeout_ms)
        finally:
            os.environ["PATH"] = old_path


VERSIONS_L12 = """Mainboard Hardware
  Type:           Laptop 12 (13th Gen Intel Core)
EC Firmware
  Build version: hx20 0.0.9
Touchscreen
  Firmware Version: v7.0.0.5.0.0.0.0
Stylus
  Firmware Version: FF.FF
"""

VERSIONS_L16 = """Mainboard Hardware
  Type:           Laptop 16 (AMD Ryzen 7040HS Series)
Laptop 16 Numpad
  Location: [X] [ ] [ ]       [ ] [ ]
"""

VERSIONS_DESKTOP = """Mainboard Hardware
  Type:           Desktop (AMD Ryzen AI Max 300 Series)
"""


@unittest.skipUnless(
    CAN_RUN,
    "PySide6 unavailable or no Qt platform plugin" if STUB_SUPPORTED
    else "stub framework_tool binary is POSIX-only")
class TestGuiSmoke(unittest.TestCase):

    def test_laptop12_shows_everything(self):
        r = run_app_and_capture(VERSIONS_L12)
        caps = r["caps"]
        self.assertTrue(caps["detected"])
        self.assertTrue(caps["is_laptop12"])
        self.assertTrue(caps["has_touchscreen"])
        self.assertTrue(caps["has_stylus"])
        self.assertEqual(len(r["tool_keys"]), 12)
        self.assertIn("input_power", r["tool_keys"])
        self.assertIn("tablet_mode", r["settings_keys"])
        self.assertIn("touchscreen", r["settings_keys"])

    def test_laptop16_hides_stylus_shows_expansion_bay(self):
        r = run_app_and_capture(VERSIONS_L16)
        caps = r["caps"]
        self.assertTrue(caps["has_expansion_bay"])
        self.assertFalse(caps["has_touchscreen"])
        self.assertFalse(caps["has_stylus"])
        self.assertIn("expansion_bay", r["port_keys"])
        self.assertNotIn("stylus", r["port_keys"])
        self.assertEqual(len(r["tool_keys"]), 12)  # is_laptop: nothing hidden

    def test_desktop_hides_battery_tools_shows_rgb(self):
        r = run_app_and_capture(VERSIONS_DESKTOP)
        caps = r["caps"]
        self.assertFalse(caps["is_laptop"])
        self.assertTrue(caps["has_rgbkbd"])
        for key in ("input_power", "battery_health", "charge_speed",
                    "kblight_sweep", "fpled_cycle"):
            self.assertNotIn(key, r["tool_keys"])
        self.assertEqual(len(r["tool_keys"]), 7)
        self.assertNotIn("expansion_bay", r["port_keys"])
        self.assertEqual(r["settings_keys"], ["rgbkbd"])

    def test_every_section_is_built(self):
        r = run_app_and_capture(VERSIONS_L16)
        self.assertEqual(r["sections"], sorted(navigation.SECTIONS))

    def test_helper_tool_sections_are_never_gated(self):
        # CPU limits/Setup/Drivers drive tools other than framework_tool, so
        # they are not gated on the board model the way the others are.
        r = run_app_and_capture(VERSIONS_DESKTOP)
        for section in ("power", "setup", "drivers"):
            self.assertIn(section, r["sections"])
        self.assertIn("Open downloads list", r["buttons:drivers"])
        self.assertIn("Re-check what is installed", r["buttons:setup"])

    def test_window_title_names_the_device(self):
        r = run_app_and_capture(VERSIONS_L16)
        # Overview is the section selected at launch, and it titles the
        # window with the chassis rather than the section name.
        self.assertEqual(r["title"], "Framework System GUI — Laptop 16")

    def test_overview_reads_the_firmware_versions(self):
        r = run_app_and_capture(VERSIONS_L12)
        self.assertEqual(r["firmware"]["ec"], "hx20 0.0.9")

    def test_overview_shows_when_it_was_last_scanned(self):
        # There is no background refresh - "Rescan device" is the only way
        # the readings change - so without this a five-minute-old reading
        # looks identical to a fresh one.
        r = run_app_and_capture(VERSIONS_L12)
        self.assertRegex(r["scanned_label"],
                         r"^Last scanned \d{2}:\d{2}:\d{2}$")

    def test_status_bar_learns_the_tool_version(self):
        r = run_app_and_capture(VERSIONS_L16)
        self.assertEqual(r["tool_version"], "0.4.2")

    def test_drivers_offers_every_build_not_just_the_detected_one(self):
        r = run_app_and_capture(VERSIONS_L16)
        self.assertIn(r["driver_entry"]["label"], r["buttons:drivers"])
        self.assertEqual(len(r["driver_all"]), len(fg.drivers.CATALOG) + 1)

    def test_drivers_matches_the_detected_board(self):
        r = run_app_and_capture(VERSIONS_L16)
        entry = r["driver_entry"]
        self.assertTrue(entry["exact"])
        self.assertIn("laptop-16", entry["url"])
        self.assertIn("7040", entry["url"])

    def test_drivers_falls_back_when_the_board_is_unknown(self):
        with tempfile.TemporaryDirectory() as empty_dir:
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = empty_dir
            try:
                r = _drive_app(DETECT_TIMEOUT_MS)
            finally:
                os.environ["PATH"] = old_path
        # No framework_tool, so no board string - the pane still offers the
        # index of every download rather than showing nothing.
        self.assertFalse(r["driver_entry"]["exact"])
        self.assertIn("Open downloads list", r["buttons:drivers"])

    def test_power_reports_a_backend_or_explains_itself(self):
        r = run_app_and_capture(VERSIONS_DESKTOP)
        backend = r["power_backend"]
        if backend is None:
            # No usable backend on this machine: the pane must offer the way
            # forward instead of a dead end.
            self.assertIn("Open the Setup section", r["buttons:power"])
        else:
            self.assertIn(backend, fg.power.BACKENDS)
            self.assertIn("Apply limits", r["buttons:power"])

    def test_console_blocks_the_flash_flags_in_writing(self):
        r = run_app_and_capture(VERSIONS_L16)
        blocked = [t for t in r["labels:console"] if "--flash-ec" in t]
        self.assertTrue(blocked, "the console pane does not say what is "
                                 "blocked")

    def test_binary_missing_fails_open(self):
        # Point PATH somewhere with no framework_tool at all.
        with tempfile.TemporaryDirectory() as empty_dir:
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = empty_dir
            try:
                r = _drive_app(DETECT_TIMEOUT_MS)
            finally:
                os.environ["PATH"] = old_path

        caps = r["caps"]
        self.assertFalse(caps["detected"])
        self.assertTrue(caps["is_laptop"])
        self.assertTrue(caps["has_touchscreen"])
        self.assertTrue(caps["has_stylus"])
        self.assertTrue(caps["has_expansion_bay"])
        self.assertEqual(len(r["tool_keys"]), 12)
        self.assertEqual(len(r["port_keys"]), 9)


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestAppearance(unittest.TestCase):
    """The acrylic toggle, and the rule that it never lies about itself."""

    def test_opaque_is_forced_when_the_platform_cannot_composite(self):
        window = fg.App()
        try:
            window.compositing = False
            window._set_appearance(fg.theme.ACRYLIC)
            # The request is refused, not honoured-and-hidden: a translucent
            # surface with nothing behind it is worse than an opaque one.
            self.assertEqual(window.appearance, fg.theme.OPAQUE)
        finally:
            window.close()
            window.deleteLater()

    def test_the_toggle_flips_and_the_status_bar_agrees(self):
        window = fg.App()
        try:
            window.compositing = True
            window.segment.set_choices_enabled(True)
            window._set_appearance(fg.theme.ACRYLIC)
            self.assertEqual(window.status_appearance.text(), "Acrylic on")
            window._toggle_appearance()
            self.assertEqual(window.appearance, fg.theme.OPAQUE)
            self.assertEqual(window.status_appearance.text(), "Opaque")
        finally:
            window.close()
            window.deleteLater()

    def test_the_drawer_height_stays_inside_its_bounds(self):
        window = fg.App()
        try:
            window._resize_drawer(10000)
            self.assertEqual(window.drawer_height, fg.theme.DRAWER_MAX)
            window._resize_drawer(-5)
            self.assertEqual(window.drawer_height, fg.theme.DRAWER_MIN)
        finally:
            window.close()
            window.deleteLater()


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestNavigationWiring(unittest.TestCase):

    def test_selecting_a_rail_group_selects_its_first_section(self):
        window = fg.App()
        try:
            for group in navigation.RAIL_GROUPS:
                window._select_rail(group["key"])
                self.assertEqual(window.section, group["items"][0][1])
                self.assertEqual(window.rail_key, group["key"])
        finally:
            window.close()
            window.deleteLater()

    def test_every_section_can_be_shown(self):
        window = fg.App()
        try:
            for section in navigation.SECTIONS:
                window._select_section(section)
                self.assertEqual(window.section, section)
                self.assertIs(window.stack.currentWidget(),
                              window.pages[section])
        finally:
            window.close()
            window.deleteLater()

    def test_the_pane_list_follows_the_rail(self):
        window = fg.App()
        try:
            window._select_section("settings")
            combo = window.section_combo
            self.assertEqual(
                [combo.itemData(i) for i in range(combo.count())],
                [key for _label, key in
                 navigation.group_for_section("settings")["items"]])
            self.assertIsInstance(combo, QComboBox)
        finally:
            window.close()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(CAN_RUN,
                     "PySide6 unavailable or no Qt platform plugin")
class TestBusyGuard(unittest.TestCase):
    """Starting a tool while one is running must leave no UI stranded.

    `run_tool` refuses while busy, but `_start_tool` used to do its work
    first: it marked the row as running, showed the detail panel and started
    the spinner and the progress bar, *then* called `run_tool`, which
    returned without starting a thread. Nothing then emitted sig_tool_done,
    so the row stayed lit and the bar kept animating for the rest of the
    session. Clicking Run on a second tool was all it took.
    """

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()
        settle(self.app, self.window)

    def tearDown(self):
        # These tests set _busy by hand to simulate a running tool and no
        # worker ever clears it, so release it before settling or the wait
        # below just burns its whole timeout.
        self.window._busy = False
        # Let the launch scan finish before the window goes. A detect thread
        # that reports into a deleted window is CLAUDE.md gotcha #6, and it
        # shows up as an intermittent signal-arity TypeError rather than as
        # a failure, which is worse than a plain crash.
        settle(self.app, self.window)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def tool(self, key):
        return next(t for t in navigation.TOOLS if t["key"] == key)

    def test_a_second_tool_does_not_strand_the_row(self):
        window = self.window
        window._busy = True                      # pretend one is running
        burst = self.tool("fan_burst")
        window._start_tool(burst)
        frame = window.tool_rows.get(burst["key"])
        if frame is not None:
            self.assertNotEqual(frame.property("running"), "true",
                                "row was marked running with no worker")
        self.assertIsNone(getattr(window, "_current_tool", None))

    def test_a_second_tool_does_not_start_the_progress_bar(self):
        window = self.window
        window._busy = True
        window._start_tool(self.tool("fan_burst"))
        self.assertFalse(window.tool_detail.bar._timer.isActive(),
                         "the progress bar is animating with no tool running")
        self.assertFalse(window.tool_detail._clock.isActive())

    def test_a_preset_does_not_fill_rows_it_did_not_write(self):
        window = self.window
        if "charge_limit" not in window.settings_widgets:
            self.skipTest("no charge rows on this detected model")
        before = window._editor_value("charge_limit")
        window._busy = True
        window._apply_preset(navigation.SETTINGS_PRESETS[0])
        self.assertEqual(window._editor_value("charge_limit"), before,
                         "the editor shows a value no command ever wrote")

    def test_a_failed_preset_command_does_not_fill_the_row_with_a_lie(self):
        window = self.window
        if "charge_limit" not in window.settings_widgets:
            self.skipTest("no charge rows on this detected model")
        limit_before = window._editor_value("charge_limit")
        rate_before = window._editor_value("charge_rate")
        window._exec = lambda args, timeout=60, echo=True: (1, "refused")
        window.tool_preset("80", "1")
        self.assertEqual(
            window._editor_value("charge_limit"), limit_before,
            "the row shows a value the device never confirmed setting")
        self.assertEqual(
            window._editor_value("charge_rate"), rate_before,
            "the row shows a rate the device never confirmed setting")

    def test_a_successful_preset_fills_from_the_confirmed_readback(self):
        window = self.window
        if "charge_limit" not in window.settings_widgets:
            self.skipTest("no charge rows on this detected model")

        def fake_exec(args, timeout=60, echo=True):
            if args == ["--charge-limit"]:
                # The firmware clamped the request - the row must show
                # what it actually confirmed, not the 80 that was asked
                # for, which is the whole point of reading it back.
                return (0, "Minimum 0%, Maximum 65%")
            return (0, "")
        window._exec = fake_exec
        window.tool_preset("80", "1")
        self.assertEqual(window._editor_value("charge_limit"), "65")
        if "charge_rate" in window.settings_widgets:
            self.assertEqual(window._editor_value("charge_rate"), "1")


@unittest.skipUnless(CAN_RUN,
                     "PySide6 unavailable or no Qt platform plugin")
class TestChassisFollowsTheModel(unittest.TestCase):
    """The bay drawing has to be the detected machine, not a default.

    It is shaped in _fill_bays, which only runs once readings arrive — and
    the sensor read needs elevation, so on an unelevated session it may
    never run at all. A Laptop 16 was drawn as a Laptop 13 until then.
    """

    def chassis_of(self, versions):
        with tempfile.TemporaryDirectory() as tmpdir:
            make_stub_binary(tmpdir, versions)
            old = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old
            try:
                app = QApplication.instance() or QApplication([])
                window = fg.App()
                settle(app, window)
                shape = (window.chassis.bay_count(),
                         window.chassis.width(), window.chassis.height())
                window.close()
                window.deleteLater()
                app.processEvents()
                return shape
            finally:
                os.environ["PATH"] = old

    def test_a_laptop_16_is_drawn_with_six_bays(self):
        bays, _w, _h = self.chassis_of(VERSIONS_L16)
        self.assertEqual(bays, 6)

    def test_a_desktop_is_drawn_with_two_bays(self):
        bays, _w, _h = self.chassis_of(VERSIONS_DESKTOP)
        self.assertEqual(bays, 2)

    def test_a_bigger_chassis_is_drawn_bigger(self):
        _b, w16, h16 = self.chassis_of(VERSIONS_L16)
        _b, w12, h12 = self.chassis_of(VERSIONS_L12)
        self.assertGreater(w16, w12,
                           "the Laptop 16 is not drawn wider than the 12")
        self.assertGreater(h16, h12)


# Named exactly as a real Laptop 13 AMD reported them (--pdports-chromebook),
# in the order that machine's EC happened to print them — not the same order
# `_ordered_by_bay`'s canonical slots use, which is the point of the test.
FOUR_BAY_PDPORTS = """USB-C Port 0 (Right Back):
  Role:          Source
  Voltage Now:   5000 mV
  Current Lim:   0 mA
  Charging Type: None
  Max Power:     0.0 W
USB-C Port 1 (Right Front):
  Role:          Disconnected
  Voltage Now:   0 mV
  Current Lim:   0 mA
  Charging Type: None
  Max Power:     0.0 W
USB-C Port 2 (Left Front):
  Role:          Source
  Voltage Now:   5000 mV
  Current Lim:   0 mA
  Charging Type: None
  Max Power:     0.0 W
USB-C Port 3 (Left Back):
  Role:          Disconnected
  Voltage Now:   0 mV
  Current Lim:   0 mA
  Charging Type: None
  Max Power:     0.0 W
"""


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestBayOrdering(unittest.TestCase):
    """A bay's row and its chassis-diagram marker have to land in the same
    slot — the real bug behind a real Laptop 13's "disconnected" markers
    showing up in the wrong corner once the CLI's port order didn't match
    the drawing's old index-based assumption.
    """

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_four_bay_sides_chassis_is_reordered_by_name(self):
        ports = parsers.parse_ports(FOUR_BAY_PDPORTS)
        chassis = device_images.chassis_for("Laptop 13")
        ordered = self.window._ordered_by_bay(ports, chassis)
        self.assertEqual(
            [p["name"] for p in ordered],
            ["Left Back", "Left Front", "Right Back", "Right Front"])

    def test_a_six_bay_chassis_is_left_in_cli_order(self):
        # Laptop 16 has no real-hardware evidence for this naming scheme,
        # so it keeps the original positional fallback untouched.
        ports = parsers.parse_ports(FOUR_BAY_PDPORTS)
        chassis = device_images.chassis_for("Laptop 16")
        ordered = self.window._ordered_by_bay(ports, chassis)
        self.assertEqual(
            [p["name"] for p in ordered],
            ["Right Back", "Right Front", "Left Front", "Left Back"])

    def test_an_unplaceable_name_keeps_its_slot_rather_than_crash(self):
        ports = parsers.parse_ports(FOUR_BAY_PDPORTS)
        ports[0]["name"] = "Weird Bay"
        chassis = device_images.chassis_for("Laptop 13")
        ordered = self.window._ordered_by_bay(ports, chassis)
        self.assertEqual(len(ordered), 4)

    def test_a_fifth_port_on_a_four_bay_chassis_is_not_dropped(self):
        # The four named slots are all taken before a fifth, differently
        # named port is even considered - it used to fall out of the
        # `slots` list entirely once every slot was full, which silently
        # threw a real port away instead of just showing it unordered.
        ports = parsers.parse_ports(FOUR_BAY_PDPORTS)
        extra = dict(ports[0])
        extra["port"] = "4"
        extra["name"] = "Extra Bay"
        ports.append(extra)
        chassis = device_images.chassis_for("Laptop 13")
        ordered = self.window._ordered_by_bay(ports, chassis)
        self.assertEqual(len(ordered), 5)
        self.assertIn("Extra Bay", [p["name"] for p in ordered])


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestManufacturerTdpRange(unittest.TestCase):
    """A wattage outside the detected chip's own cTDP range is refused the
    same way any other invalid input is: through PowerError, before a
    command is ever built."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()
        self.window.tdp_limits = {"min_w": 15, "default_w": 28, "max_w": 30}

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_within_range_is_accepted(self):
        self.assertEqual(self.window._check_manufacturer_range("30"), 30)

    def test_above_the_manufacturer_max_is_refused(self):
        from frameworkgui import power
        self.assertRaises(power.PowerError,
                          self.window._check_manufacturer_range, "45")

    def test_below_the_manufacturer_min_is_refused(self):
        from frameworkgui import power
        self.assertRaises(power.PowerError,
                          self.window._check_manufacturer_range, "5")


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestCloseDuringBackgroundWork(unittest.TestCase):
    """A worker thread's next report must not crash once the window is
    closing - see App._emit/closeEvent. Real trigger: closing the app while
    Rescan, a Diagnostics tool, a Settings write or the updater is still
    running on its daemon thread. Reproduced (before the fix) as a bare
    `TypeError: only accepts 0 argument(s), 3 given!` out of _log whenever
    this suite ran as root, because _apply_detection starts a second
    background thread (_read_sensors) that _drive_app's old watcher did not
    wait for before tearing the window down.
    """

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_closing_stops_further_log_and_status_reports(self):
        window = self.window
        before_status = window.status_message.text()
        window.close()
        self.assertTrue(window._closing)
        # Exactly what a worker thread still running in the background
        # would call next - none of these may raise, and none may reach a
        # widget once closeEvent has run.
        window._log("framework_tool", "late output\n")
        window.set_status("late status")
        window._emit(window.sig_tool_done)
        self.assertEqual(window.status_message.text(), before_status)

    def test_emit_survives_a_signal_that_raises_runtimeerror(self):
        # The actual PySide6 failure mode - emitting into a QObject whose
        # C++ side is already gone - without needing to force real object
        # deletion, which is timing-dependent and not reproducible on
        # demand.
        class ExplodingSignal:
            def emit(self, *args):
                raise RuntimeError("Internal C++ object already deleted.")

        self.window._emit(ExplodingSignal())  # must not raise


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestRailButtonHover(unittest.TestCase):
    """A RailButton is fully self-painted, so unlike a QPushButton it gets
    no hover feedback for free - enterEvent/leaveEvent have to ask for a
    repaint themselves."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def test_enter_and_leave_do_not_raise_and_request_a_repaint(self):
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QEnterEvent

        from frameworkgui.navigation import RAIL_GROUPS
        from frameworkgui.widgets import RailButton
        button = RailButton(RAIL_GROUPS[0])
        origin = QPointF(0, 0)
        button.enterEvent(QEnterEvent(origin, origin, origin))
        button.leaveEvent(QEvent(QEvent.Type.Leave))

    def test_hover_and_active_use_different_icon_tints(self):
        from frameworkgui.navigation import RAIL_GROUPS
        from frameworkgui.widgets import RailButton
        button = RailButton(RAIL_GROUPS[0])
        self.assertIsNot(button._pixmap("icon"),
                         button._pixmap("text.secondary"))
        self.assertIsNot(button._pixmap("text.secondary"),
                         button._pixmap("accent.icon"))


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestDriversCopyLink(unittest.TestCase):
    """The Drivers pane's "Copy link" buttons - the same URLs "Open"
    already reaches, for someone who wants to paste the link elsewhere
    (a chat, a ticket) rather than have it opened here."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_both_copy_link_buttons_are_present(self):
        buttons = buttons_in(self.window.pages["drivers"])
        self.assertEqual(buttons.count("Copy link"), 2)

    def test_copying_the_selected_build_puts_its_url_on_the_clipboard(self):
        window = self.window
        url = window.driver_choice.currentData()
        self.assertTrue(url)
        window._copy_selected_driver_link()
        self.assertEqual(fg.QGuiApplication.clipboard().text(), url)


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestLastReportPath(unittest.TestCase):
    """The Diagnostics pane remembers where the last "Full system report"
    landed, so a second look does not mean re-running the whole report to
    find the path again - and that state survives _build_pages() rebuilding
    the page after every rescan, the same way the updater panel's state
    does."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def report_row_texts(self):
        row = self.window.report_row
        return [row.itemAt(i).widget().text() for i in range(row.count())
               if row.itemAt(i).widget() is not None]

    def test_nothing_shown_before_a_report_has_been_saved(self):
        self.assertEqual(self.report_row_texts(), [])

    def test_a_saved_report_shows_its_path_and_a_copy_button(self):
        self.window._show_report_path("/tmp/framework_report_x.txt")
        texts = self.report_row_texts()
        self.assertIn("Last report: /tmp/framework_report_x.txt", texts)
        self.assertIn("Copy path", texts)

    def test_the_path_survives_a_page_rebuild(self):
        window = self.window
        window._show_report_path("/tmp/framework_report_x.txt")
        window._build_pages()
        self.assertIn("Last report: /tmp/framework_report_x.txt",
                      self.report_row_texts())


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestSettingsBackup(unittest.TestCase):
    """Export/Import on the Settings pane - a local backup of the field
    values, never a read of or write to the device by itself."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()
        if "charge_limit" not in self.window.settings_widgets:
            self.skipTest("no charge rows on this detected model")

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_export_writes_every_rows_current_value(self):
        import json
        import tempfile
        from unittest import mock
        window = self.window
        window.settings_widgets["charge_limit"].setText("77")
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "settings.json")
            with mock.patch.object(fg.QFileDialog, "getSaveFileName",
                                   return_value=(target, "")):
                window._export_settings()
            with open(target, encoding="utf-8") as fh:
                data = json.load(fh)
        self.assertEqual(data["charge_limit"], "77")

    def test_import_fills_matching_rows_without_running_anything(self):
        import json
        import tempfile
        from unittest import mock
        window = self.window
        window.run = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "settings.json")
            with open(target, "w", encoding="utf-8") as fh:
                json.dump({"charge_limit": "55",
                          "not_a_real_row": "x"}, fh)
            with mock.patch.object(fg.QFileDialog, "getOpenFileName",
                                   return_value=(target, "")):
                window._import_settings()
        self.assertEqual(window._editor_value("charge_limit"), "55")
        window.run.assert_not_called()

    def test_import_ignores_a_non_string_value(self):
        import json
        import tempfile
        from unittest import mock
        window = self.window
        before = window._editor_value("charge_limit")
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "settings.json")
            with open(target, "w", encoding="utf-8") as fh:
                json.dump({"charge_limit": 80}, fh)  # not a string
            with mock.patch.object(fg.QFileDialog, "getOpenFileName",
                                   return_value=(target, "")):
                window._import_settings()
        self.assertEqual(window._editor_value("charge_limit"), before)

    def test_import_of_a_non_dict_file_warns_instead_of_crashing(self):
        import json
        import tempfile
        from unittest import mock
        window = self.window
        window._warn = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "settings.json")
            with open(target, "w", encoding="utf-8") as fh:
                json.dump([1, 2, 3], fh)
            with mock.patch.object(fg.QFileDialog, "getOpenFileName",
                                   return_value=(target, "")):
                window._import_settings()
        window._warn.assert_called_once()

    def test_import_of_invalid_json_warns_instead_of_crashing(self):
        import tempfile
        from unittest import mock
        window = self.window
        window._warn = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "settings.json")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("{not json,")
            with mock.patch.object(fg.QFileDialog, "getOpenFileName",
                                   return_value=(target, "")):
                window._import_settings()
        window._warn.assert_called_once()

    def test_cancelling_export_or_import_does_nothing(self):
        from unittest import mock
        window = self.window
        with mock.patch.object(fg.QFileDialog, "getSaveFileName",
                               return_value=("", "")):
            window._export_settings()  # must not raise
        with mock.patch.object(fg.QFileDialog, "getOpenFileName",
                               return_value=("", "")):
            window._import_settings()  # must not raise


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestCustomCommandHistory(unittest.TestCase):
    """The Console pane's History row - what this user actually ran,
    distinct from navigation.RECENT_SUGGESTIONS' curated defaults."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def chip_texts(self):
        return [self.window.history_layout.itemAt(i).widget().text()
               for i in range(self.window.history_layout.count())
               if self.window.history_layout.itemAt(i).widget() is not None]

    def test_history_is_hidden_until_something_has_run(self):
        # isVisible() reflects the whole ancestor chain, and these tests
        # never call window.show() - isHidden() is the widget's own
        # explicit flag, which is what setVisible() in _refresh_history_row
        # actually controls.
        self.assertTrue(self.window.history_wrap.isHidden())

    def test_running_a_command_shows_it_in_history(self):
        self.window._remember_custom_command("--thermal")
        self.assertFalse(self.window.history_wrap.isHidden())
        self.assertIn("--thermal", self.chip_texts())

    def test_repeating_a_command_moves_it_to_the_front_without_duplicating(self):
        window = self.window
        window._remember_custom_command("--versions")
        window._remember_custom_command("--thermal")
        window._remember_custom_command("--versions")
        self.assertEqual(window._custom_history,
                         ["--versions", "--thermal"])

    def test_history_is_capped(self):
        window = self.window
        for i in range(window.HISTORY_LIMIT + 3):
            window._remember_custom_command("--cmd{}".format(i))
        self.assertEqual(len(window._custom_history), window.HISTORY_LIMIT)
        # Most recent first, oldest fell off the end.
        self.assertEqual(window._custom_history[0],
                         "--cmd{}".format(window.HISTORY_LIMIT + 2))

    def test_a_history_chip_fills_the_custom_command_field(self):
        window = self.window
        window._remember_custom_command("--pdports")
        chip = next(window.history_layout.itemAt(i).widget()
                   for i in range(window.history_layout.count())
                   if window.history_layout.itemAt(i).widget() is not None
                   and window.history_layout.itemAt(i).widget().text()
                   == "--pdports")
        chip.click()
        self.assertEqual(window.custom.text(), "--pdports")

    def test_run_custom_records_history_before_running(self):
        from unittest import mock
        window = self.window
        window.run = mock.Mock()
        window.custom.setText("--power -vv")
        window._run_custom()
        self.assertIn("--power -vv", window._custom_history)
        window.run.assert_called_once_with(["--power", "-vv"])

    def test_a_blocked_command_is_not_remembered(self):
        from unittest import mock
        window = self.window
        window.run = mock.Mock()
        window._warn = mock.Mock()  # a real QMessageBox.warning() would block
        window.custom.setText("--flash-ec")
        window._run_custom()
        self.assertNotIn("--flash-ec", window._custom_history)
        window.run.assert_not_called()
        window._warn.assert_called_once()


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestRgbValidation(unittest.TestCase):
    """The RGB row's hex field is free text a person typed, not CLI output -
    _set_rgb_all has to refuse something that is not a 6-digit hex colour
    rather than handing framework_tool a bogus --rgbkbd argument."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_a_valid_hex_colour_runs_the_command(self):
        from unittest import mock
        window = self.window
        window.settings_widgets["rgbkbd"].setText("00ff00")
        window.run = mock.Mock()
        window._set_rgb_all()
        window.run.assert_called_once_with(
            ["--rgbkbd", "0"] + ["0x00ff00"] * 8)

    def test_a_leading_hash_is_accepted(self):
        from unittest import mock
        window = self.window
        window.settings_widgets["rgbkbd"].setText("#00FF00")
        window.run = mock.Mock()
        window._set_rgb_all()
        window.run.assert_called_once()

    def test_an_invalid_colour_is_refused_without_running_anything(self):
        from unittest import mock
        window = self.window
        window.settings_widgets["rgbkbd"].setText("not-a-colour")
        window.run = mock.Mock()
        window._warn = mock.Mock()
        window._set_rgb_all()
        window.run.assert_not_called()
        window._warn.assert_called_once()


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestSensorOrdering(unittest.TestCase):
    """The Fans pane's sensor list, hottest first - --thermal's own order
    is neither sorted nor stable between boards."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def rows_top_to_bottom(self):
        holder = self.window.sensor_holder
        names = []
        for i in range(holder.count()):
            widget = holder.itemAt(i).widget()
            for name, row in self.window.sensor_rows.items():
                if row is widget:
                    names.append(name)
        return names

    def test_the_hottest_sensor_is_listed_first(self):
        self.window._apply_readings({"thermal":
            "Cool_Zone: 30 C\nHot_Zone: 78 C\nWarm_Zone: 52 C\n"})
        self.assertEqual(self.rows_top_to_bottom(),
                         ["Hot_Zone", "Warm_Zone", "Cool_Zone"])

    def test_reordering_on_a_later_read_moves_existing_rows(self):
        window = self.window
        window._apply_readings({"thermal": "A: 30 C\nB: 78 C\n"})
        self.assertEqual(self.rows_top_to_bottom(), ["B", "A"])
        # The same two sensors, temperatures now reversed.
        window._apply_readings({"thermal": "A: 90 C\nB: 20 C\n"})
        self.assertEqual(self.rows_top_to_bottom(), ["A", "B"])


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestPortsSourceNote(unittest.TestCase):
    """The Ports & modules pane says which command actually answered, the
    same thing the Overview's bay_source caption already says - an EC that
    only supports the --pdports-chromebook fallback is not obvious from the
    table rows alone."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_the_fallback_command_is_named(self):
        self.window._apply_readings(
            {"ports_source": "--pdports-chromebook", "ports": []})
        text = self.window.ports_source_note.text()
        self.assertIn("--pdports-chromebook", text)
        self.assertIn("does not implement --pdports", text)

    def test_the_primary_command_is_named_without_a_fallback_note(self):
        self.window._apply_readings(
            {"ports_source": "--pdports", "ports": []})
        text = self.window.ports_source_note.text()
        self.assertIn("--pdports", text)
        self.assertNotIn("does not implement", text)

    def test_nothing_read_yet_shows_no_note(self):
        self.assertEqual(self.window.ports_source_note.text(), "")


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestPersistedSection(unittest.TestCase):
    """Relaunching the app returns to the section it was last showing,
    rather than always landing back on Overview. Neither test lets the
    launch scan's QTimer fire (no app.exec(), no settle()), so there is no
    worker thread to race with teardown."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        fg.appstate.save(fg.appstate.DEFAULTS)

    def test_a_stored_section_is_restored_on_launch(self):
        state = dict(fg.appstate.DEFAULTS)
        state["last_section"] = "settings"
        fg.appstate.save(state)
        window = fg.App()
        try:
            self.assertEqual(window.section, "settings")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_selecting_a_section_persists_it(self):
        window = fg.App()
        try:
            window._select_section("power")
            self.assertEqual(fg.appstate.load()["last_section"], "power")
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestKeyboardShortcuts(unittest.TestCase):
    """F5 and Ctrl+N mirror the Rescan button and the rail, for anyone
    driving the app from the keyboard rather than the mouse."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window._busy = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def _shortcut(self, sequence):
        target = fg.QKeySequence(sequence)
        return next(s for s in self.window.findChildren(fg.QShortcut)
                   if s.key() == target)

    def test_f5_triggers_a_rescan(self):
        # Marking it busy first stops _rescan from actually spawning the
        # detect thread - this only has to prove the shortcut reaches
        # _rescan, the same guard TestBusyGuard exercises another way.
        self.window._busy = True
        self._shortcut("F5").activated.emit()
        self.assertEqual(self.window.status_message.text(),
                         "Busy — wait or cancel the running tool.")

    def test_ctrl_number_keys_select_each_rail_group(self):
        for index, group in enumerate(navigation.RAIL_GROUPS, start=1):
            self._shortcut("Ctrl+{}".format(index)).activated.emit()
            self.assertEqual(self.window.rail_key, group["key"])


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestDrawerCopy(unittest.TestCase):
    """The drawer's "copy" button, alongside its existing wrap/clear."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_copy_puts_the_current_tabs_text_on_the_clipboard(self):
        self.window.drawer.append("framework_tool", "hello from a test\n")
        self.window.drawer.select("framework_tool")
        self.window.drawer._copy()
        self.assertIn("hello from a test",
                      fg.QGuiApplication.clipboard().text())

    def test_current_stream_names_the_selected_tab(self):
        self.window.drawer.append("ryzenadj", "x\n")
        self.window.drawer.select("ryzenadj")
        self.assertEqual(self.window.drawer._current_stream(), "ryzenadj")

    def test_save_writes_the_current_tabs_text_to_the_chosen_path(self):
        import tempfile
        from unittest import mock
        self.window.drawer.append("framework_tool", "saved output\n")
        self.window.drawer.select("framework_tool")
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "out.txt")
            with mock.patch.object(fg.QFileDialog, "getSaveFileName",
                                   return_value=(target, "")):
                self.window.drawer._save()
            with open(target, encoding="utf-8") as fh:
                self.assertIn("saved output", fh.read())

    def test_cancelling_the_save_dialog_writes_nothing(self):
        from unittest import mock
        self.window.drawer.append("framework_tool", "x\n")
        with mock.patch.object(fg.QFileDialog, "getSaveFileName",
                               return_value=("", "")):
            self.window.drawer._save()  # must not raise


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestDeviceSummary(unittest.TestCase):
    """The Overview's two support-request actions: "Copy summary" (a
    bug-report paste of the board/CPU/firmware detail plus the six stat
    cards, without asking someone to retype what is on their screen) and
    "Save diagram…" (the chassis/bay drawing as a PNG)."""

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_save_diagram_writes_a_png(self):
        import tempfile
        from unittest import mock
        window = self.window
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "chassis.png")
            with mock.patch.object(fg.QFileDialog, "getSaveFileName",
                                   return_value=(target, "")):
                window._save_chassis_image()
            self.assertTrue(os.path.isfile(target))
            self.assertGreater(os.path.getsize(target), 0)

    def test_cancelling_save_diagram_writes_nothing(self):
        from unittest import mock
        with mock.patch.object(fg.QFileDialog, "getSaveFileName",
                               return_value=("", "")):
            self.window._save_chassis_image()  # must not raise

    def test_summary_includes_board_detail_and_stat_cards(self):
        window = self.window
        window.caps["model"] = "Laptop 13 (AMD Ryzen 7040Series)"
        window.firmware["ec"] = "azalea_v3.4.113405"
        window.stat_cards["battery"].set_value("68% · 91.7% health")
        window._copy_device_summary()
        text = fg.QGuiApplication.clipboard().text()
        self.assertIn("Laptop 13", text)
        self.assertIn("azalea_v3.4.113405", text)
        self.assertIn("Battery: 68% · 91.7% health", text)


@unittest.skipUnless(CAN_RUN, "PySide6 unavailable or no Qt platform plugin")
class TestUpdater(unittest.TestCase):
    """The Setup pane's self-updater: check and download, never install.

    Every test drives `_apply_update_check`/`_show_update_path` directly
    with canned results rather than a real network call - the same
    boundary `updater.describe()` itself is tested at, and the same
    reason `TestManufacturerTdpRange` calls `_check_manufacturer_range`
    directly instead of clicking a button that spawns a worker thread.
    """

    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.window = fg.App()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def result(self, newer, asset_url="https://example/asset",
               latest="9.9.9"):
        return {"current": fg.__version__, "latest": latest, "newer": newer,
               "html_url": "https://example/release",
               "asset_name": "FrameworkGUI-Setup.exe",
               "asset_url": asset_url if newer else None}

    def action_texts(self):
        """What `update_actions` currently holds, read from the layout
        itself rather than findChildren() - a widget `_rebuild_update_actions`
        just took out with deleteLater() stays a live child of the panel
        until the event loop actually turns, so findChildren() can still
        report it. The layout's own contents are what is actually shown."""
        layout = self.window.update_actions
        return [layout.itemAt(i).widget().text() for i in range(layout.count())]

    def test_setup_shows_the_current_version_and_a_check_button(self):
        page = self.window.pages["setup"]
        self.assertIn("Check for updates", buttons_in(page))
        self.assertIn("v" + fg.__version__, labels_in(page))

    def test_an_available_update_offers_a_download_button(self):
        self.window.sig_update_checked.emit(self.result(newer=True))
        self.assertIn("Download v9.9.9",
                      buttons_in(self.window.pages["setup"]))
        self.assertIn("Release notes",
                      buttons_in(self.window.pages["setup"]))

    def test_being_up_to_date_offers_no_download_button(self):
        self.window.sig_update_checked.emit(
            self.result(newer=False, latest=fg.__version__))
        texts = self.action_texts()
        self.assertFalse([t for t in texts if t.startswith("Download")])
        self.assertIn("Release notes", texts)
        self.assertIn(fg.__version__, self.window.update_status.text())

    def test_a_release_with_no_matching_asset_says_so_instead_of_a_button(self):
        self.window.sig_update_checked.emit(self.result(newer=True,
                                                         asset_url=None))
        texts = self.action_texts()
        self.assertFalse([t for t in texts if t.startswith("Download")])
        self.assertIn("No FrameworkGUI-Setup.exe in that release yet.", texts)

    def test_a_finished_download_shows_a_copyable_path_and_no_longer_the_button(self):
        self.window.sig_update_checked.emit(self.result(newer=True))
        self.window.sig_update_downloaded.emit("/tmp/FrameworkGUI-Setup.exe")
        texts = self.action_texts()
        self.assertIn("Copy path", texts)
        self.assertFalse([t for t in texts if t.startswith("Download")])
        self.assertIn("/tmp/FrameworkGUI-Setup.exe", texts)

    def test_rechecking_clears_a_previous_download_state(self):
        self.window.sig_update_checked.emit(self.result(newer=True))
        self.window.sig_update_downloaded.emit("/tmp/FrameworkGUI-Setup.exe")
        self.window.sig_update_checked.emit(self.result(newer=True))
        self.assertIn("Download v9.9.9", self.action_texts())
