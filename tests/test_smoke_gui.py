"""
End-to-end smoke tests for the Tk app: launch App() for real, drive it
through an actual mainloop() (not manual .update() polling — Tkinter only
marshals cross-thread Tk calls while mainloop() is really running, so
polling with .update() produces a spurious
"RuntimeError: main thread is not in main loop"), point it at a stub
framework_tool script, and assert on the capability dict + which tab
widgets survive gating.

Requires a display. On headless Linux:

    xvfb-run -a python3 -m unittest tests.test_smoke_gui -v

Skips automatically if tkinter can't open a display (e.g. plain CI without
Xvfb), and on Windows, where the POSIX stub binary can't run — rather than
failing the whole suite in either case.
"""

import gc
import os
import stat
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import tkinter as tk
    _tk_root = tk.Tk()
    _tk_root.destroy()
    TK_AVAILABLE = True
except Exception:  # noqa: BLE001 — no display, no tkinter, etc.
    TK_AVAILABLE = False

# The stub binary below is an extension-less script with a shebang: Windows
# neither resolves it via PATHEXT nor executes it, so these tests are POSIX
# only. Skipped rather than failed on Windows — test_parsers.py and
# test_packaging.py still cover the logic there.
STUB_SUPPORTED = not sys.platform.startswith("win")
CAN_RUN = TK_AVAILABLE and STUB_SUPPORTED

if CAN_RUN:
    import framework_gui as fg  # noqa: E402


def make_stub_binary(tmpdir, versions_output):
    """Write a fake `framework_tool` that answers --versions and prints a
    placeholder for anything else, then return the directory to prepend to
    PATH."""
    path = os.path.join(tmpdir, "framework_tool")
    script = textwrap.dedent(f'''\
        #!/usr/bin/env python3
        import sys
        if "--versions" in sys.argv:
            print({versions_output!r})
            sys.exit(0)
        print("stub output")
        sys.exit(0)
        ''')
    with open(path, "w") as fh:
        fh.write(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return tmpdir


# Generous: the first run in a cold environment pays for .pyc compilation
# and for spawning the stub binary (itself a Python process). A tight
# timeout here shows up as a flaky, hard-to-read failure in CI, not as a
# faster test run — the watcher quits the loop as soon as detection lands.
DETECT_TIMEOUT_MS = 30000


def _drive_app(timeout_ms):
    """Run a real App through a real mainloop() until device detection has
    settled, then snapshot caps + the buttons on each tab.

    Returns (caps, tab_name -> [button texts]) as one dict. Raises if
    detection never completed, so a timeout reads as a timeout rather than
    as a KeyError further down the test."""
    app = fg.App()
    results = {}

    def snapshot():
        results["caps"] = dict(app.caps)
        results["cpu"] = dict(app.cpu)
        results["driver_entry"] = dict(app._driver_entry)
        results["driver_all"] = list(app._driver_all)
        results["power_backend"] = app.power_backend
        results["detected_var"] = app.detected_var.get()
        results["tabs"] = [app.nb.tab(t, "text") for t in app.nb.tabs()]
        for tab_id in app.nb.tabs():
            name = app.nb.tab(tab_id, "text")
            frame = app.nb.nametowidget(tab_id)
            results[name] = [
                w["text"] for w in frame.winfo_children()
                if isinstance(w, fg.ttk.Button)
            ]

    def watcher():
        # "Detecting…" is the pre-scan placeholder; anything else means the
        # scan thread has reported back (success or fail-open).
        if app.caps.get("model") != "Detecting…":
            snapshot()
            app.quit()
        else:
            app.after(50, watcher)

    app.after(50, watcher)
    timeout_id = app.after(timeout_ms, app.quit)  # safety net against a hang
    app.mainloop()

    # Tear down deliberately. Each test builds a fresh App (a fresh Tk
    # interpreter) in the same process, and leftovers from the previous one
    # are not harmless: a pending `after` callback fires against a dead
    # interpreter ("invalid command name ...quit"), and Tk variables left for
    # the GC to reap whenever it likes get their __del__ — which calls into
    # Tcl — run at an arbitrary later moment, possibly from the *next* app's
    # worker thread. That corrupts Tcl's async state and the next app's
    # device scan then never lands, i.e. an intermittent 30-second timeout in
    # whichever test happens to run later. Cancel, destroy, and collect here,
    # on the main thread with no mainloop running, so it can't happen there.
    try:
        app.after_cancel(timeout_id)
    except tk.TclError:
        pass
    app.destroy()
    app = None  # drop the last strong reference before collecting
    gc.collect()

    if "caps" not in results:
        raise AssertionError(
            f"device detection did not complete within {timeout_ms} ms")
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
    "no display available for tkinter" if STUB_SUPPORTED
    else "stub framework_tool binary is POSIX-only")
class TestGuiSmoke(unittest.TestCase):

    def test_laptop12_shows_everything(self):
        r = run_app_and_capture(VERSIONS_L12)
        caps = r["caps"]
        self.assertTrue(caps["detected"])
        self.assertTrue(caps["is_laptop12"])
        self.assertTrue(caps["has_touchscreen"])
        self.assertTrue(caps["has_stylus"])
        self.assertEqual(len(r["Tools"]), 14)
        self.assertIn("Power input wattage", r["Tools"])

    def test_laptop16_hides_stylus_shows_expansion_bay(self):
        r = run_app_and_capture(VERSIONS_L16)
        caps = r["caps"]
        self.assertTrue(caps["has_expansion_bay"])
        self.assertFalse(caps["has_touchscreen"])
        self.assertFalse(caps["has_stylus"])
        self.assertIn("Expansion bay (L16)", r["Ports & Modules"])
        self.assertNotIn("Stylus battery", r["Ports & Modules"])
        self.assertEqual(len(r["Tools"]), 14)  # is_laptop -> nothing hidden

    def test_desktop_hides_battery_tools_shows_rgb(self):
        r = run_app_and_capture(VERSIONS_DESKTOP)
        caps = r["caps"]
        self.assertFalse(caps["is_laptop"])
        self.assertTrue(caps["has_rgbkbd"])
        hidden = ("Power input wattage", "Battery health report",
                  "Charging speed check", "Keyboard backlight sweep",
                  "Fingerprint LED test", "Preset: Longevity (limit 80%)",
                  "Preset: Full charge (100%)")
        for label in hidden:
            self.assertNotIn(label, r["Tools"])
        self.assertEqual(len(r["Tools"]), 7)
        self.assertNotIn("Power / battery", r["Info"])
        self.assertNotIn("Expansion bay (L16)", r["Ports & Modules"])

    def test_helper_tool_tabs_are_always_present(self):
        # Power/Setup/Drivers drive tools other than framework_tool, so they
        # are not gated on the board model the way the other tabs are.
        r = run_app_and_capture(VERSIONS_L16)
        for tab in ("Power (TDP)", "Setup", "Drivers"):
            self.assertIn(tab, r["tabs"])
        self.assertIn("Open downloads list", r["Drivers"])
        self.assertIn("Re-check what is installed", r["Setup"])

    def test_drivers_tab_offers_every_build_not_just_the_detected_one(self):
        r = run_app_and_capture(VERSIONS_L16)
        # The detected build is the top button; the rest are in the dropdown.
        self.assertIn(r["driver_entry"]["label"], r["Drivers"])
        self.assertEqual(len(r["driver_all"]), len(fg.drivers.CATALOG) + 1)

    def test_drivers_tab_matches_the_detected_board(self):
        r = run_app_and_capture(VERSIONS_L16)
        entry = r["driver_entry"]
        self.assertTrue(entry["exact"])
        self.assertIn("laptop-16", entry["url"])
        self.assertIn("7040", entry["url"])

    def test_drivers_tab_falls_back_when_the_board_is_unknown(self):
        with tempfile.TemporaryDirectory() as empty_dir:
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = empty_dir
            try:
                r = _drive_app(DETECT_TIMEOUT_MS)
            finally:
                os.environ["PATH"] = old_path
        # No framework_tool, so no board string — the tab still offers the
        # index of every download rather than showing nothing.
        self.assertFalse(r["driver_entry"]["exact"])
        self.assertIn("Open downloads list", r["Drivers"])

    def test_power_tab_reports_a_backend_or_explains_itself(self):
        r = run_app_and_capture(VERSIONS_DESKTOP)
        backend = r["power_backend"]
        if backend is None:
            # No usable backend on this test machine: the tab must offer the
            # way forward instead of a dead end.
            self.assertIn("Open the Setup tab", r["Power (TDP)"])
        else:
            self.assertIn(backend, fg.power.BACKENDS)
            self.assertIn("Apply limits", r["Power (TDP)"])

    def test_binary_missing_fails_open(self):
        # Point PATH somewhere with no framework_tool at all.
        with tempfile.TemporaryDirectory() as empty_dir:
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = empty_dir
            try:
                results = _drive_app(DETECT_TIMEOUT_MS)
            finally:
                os.environ["PATH"] = old_path

        caps = results["caps"]
        self.assertFalse(caps["detected"])
        self.assertTrue(caps["is_laptop"])
        self.assertTrue(caps["has_touchscreen"])
        self.assertTrue(caps["has_stylus"])
        self.assertTrue(caps["has_expansion_bay"])
        self.assertEqual(len(results["Tools"]), 14)
        self.assertEqual(len(results["Ports & Modules"]), 9)


if __name__ == "__main__":
    unittest.main()
