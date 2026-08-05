"""Unit tests for appstate.py — the two persisted UI choices.

Every path here is exercised with injected I/O, so no test touches a real
home directory. The behaviour that matters most is what happens to a bad
file: losing a remembered drawer height must never stop the app launching.
"""

import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frameworkgui import appstate, theme  # noqa: E402


def reader(text):
    """An `open`-alike that yields fixed text."""
    def _open(_path, *_args, **_kwargs):
        return io.StringIO(text)
    return _open


def failing_reader(error):
    def _open(*_args, **_kwargs):
        raise error
    return _open


class Writer:
    """An `open`-alike that captures what was written."""

    def __init__(self):
        self.text = ""

    def __call__(self, _path, _mode="r", **_kwargs):
        writer = self

        class Sink(io.StringIO):
            def close(self):
                writer.text = self.getvalue()
                super().close()

        return Sink()


class TestConfigPath(unittest.TestCase):

    def test_windows_uses_localappdata(self):
        path = appstate.config_dir({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"})
        self.assertIn("FrameworkGUI", path)

    def test_linux_prefers_xdg_config_home(self):
        path = appstate.config_dir({"XDG_CONFIG_HOME": "/xdg"})
        self.assertEqual(path, os.path.join("/xdg", "framework-gui"))

    def test_linux_falls_back_to_dot_config(self):
        path = appstate.config_dir({"HOME": "/home/someone"})
        self.assertEqual(path,
                         os.path.join("/home/someone", ".config",
                                      "framework-gui"))

    def test_path_is_inside_the_directory(self):
        env = {"XDG_CONFIG_HOME": "/xdg"}
        self.assertTrue(appstate.config_path(env).startswith(
            appstate.config_dir(env)))


class TestClampDrawer(unittest.TestCase):

    def test_inside_the_range_is_kept(self):
        self.assertEqual(appstate.clamp_drawer(200), 200)

    def test_too_small_clamps_up(self):
        self.assertEqual(appstate.clamp_drawer(10), theme.DRAWER_MIN)

    def test_too_large_clamps_down(self):
        self.assertEqual(appstate.clamp_drawer(9000), theme.DRAWER_MAX)

    def test_floats_round(self):
        self.assertEqual(appstate.clamp_drawer(199.6), 200)

    def test_rubbish_falls_back_to_the_default(self):
        for value in (None, "tall", "", [], object()):
            self.assertEqual(appstate.clamp_drawer(value),
                             appstate.DEFAULTS["drawer_height"])


class TestNormalise(unittest.TestCase):

    def test_empty_gives_defaults(self):
        self.assertEqual(appstate.normalise({}), appstate.DEFAULTS)

    def test_non_dict_gives_defaults(self):
        for value in (None, [], "acrylic", 3):
            self.assertEqual(appstate.normalise(value), appstate.DEFAULTS)

    def test_unknown_appearance_is_ignored(self):
        state = appstate.normalise({"appearance": "mica"})
        self.assertEqual(state["appearance"], appstate.DEFAULTS["appearance"])

    def test_known_appearance_is_kept(self):
        state = appstate.normalise({"appearance": theme.OPAQUE})
        self.assertEqual(state["appearance"], theme.OPAQUE)

    def test_drawer_height_is_clamped(self):
        self.assertEqual(appstate.normalise({"drawer_height": 5000})[
            "drawer_height"], theme.DRAWER_MAX)


class TestLoad(unittest.TestCase):

    def test_reads_a_good_file(self):
        text = json.dumps({"appearance": "opaque", "drawer_height": 320})
        state = appstate.load("/nowhere", opener=reader(text))
        self.assertEqual(state, {"appearance": "opaque", "drawer_height": 320})

    def test_missing_file_gives_defaults(self):
        state = appstate.load("/nowhere",
                              opener=failing_reader(FileNotFoundError()))
        self.assertEqual(state, appstate.DEFAULTS)

    def test_corrupt_file_gives_defaults(self):
        # A hand-edited or truncated file is a normal thing to find on disk;
        # it must not be a reason to fail to launch.
        state = appstate.load("/nowhere", opener=reader("{not json,"))
        self.assertEqual(state, appstate.DEFAULTS)

    def test_unreadable_file_gives_defaults(self):
        state = appstate.load("/nowhere",
                              opener=failing_reader(PermissionError()))
        self.assertEqual(state, appstate.DEFAULTS)


class TestSave(unittest.TestCase):

    def test_writes_normalised_state(self):
        writer = Writer()
        made = []
        ok = appstate.save({"appearance": "opaque", "drawer_height": 9000},
                           "/nowhere/settings.json", opener=writer,
                           makedirs=made.append)
        self.assertTrue(ok)
        self.assertEqual(json.loads(writer.text),
                         {"appearance": "opaque",
                          "drawer_height": theme.DRAWER_MAX})
        self.assertEqual(made, ["/nowhere"])

    def test_a_failed_write_is_reported_not_raised(self):
        ok = appstate.save(appstate.DEFAULTS, "/nowhere/settings.json",
                           opener=failing_reader(PermissionError()),
                           makedirs=lambda _d: None)
        self.assertFalse(ok)

    def test_a_failed_mkdir_is_reported_not_raised(self):
        def explode(_directory):
            raise OSError("read-only filesystem")
        self.assertFalse(appstate.save(appstate.DEFAULTS, "/nowhere/x.json",
                                       opener=Writer(), makedirs=explode))

    def test_round_trip(self):
        writer = Writer()
        appstate.save({"appearance": "opaque", "drawer_height": 300},
                      "/nowhere/settings.json", opener=writer,
                      makedirs=lambda _d: None)
        self.assertEqual(
            appstate.load("/nowhere/settings.json",
                          opener=reader(writer.text)),
            {"appearance": "opaque", "drawer_height": 300})


if __name__ == "__main__":
    unittest.main()
