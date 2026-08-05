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
    from frameworkgui import navigation  # noqa: E402,I001


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
        for section, page in window.pages.items():
            results["buttons:" + section] = buttons_in(page)
            results["labels:" + section] = labels_in(page)

    def watcher():
        # "Detecting…" is the pre-scan placeholder; anything else means the
        # scan thread has reported back (success or fail-open).
        if window.caps.get("model") != "Detecting…":
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
