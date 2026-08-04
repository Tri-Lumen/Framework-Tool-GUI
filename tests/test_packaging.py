"""Packaging checks — cheap guards against shipping a broken build.

The app is more than one file: framework_gui.py imports parsers.py. Every
packaging path (PyInstaller build, script install, Flatpak manifest) has to
carry both, and a miss doesn't show up until the app launches on a target
machine and dies with ModuleNotFoundError. These tests are the stand-in for
the Windows/Flatpak builds that CI can't fully exercise; they need no
display, no tkinter, and no build tooling.

If you add another module at the repo root, these fail until every
packaging path knows about it — that's the point.
"""

import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Modules that make up the app itself (tests/ and tooling excluded).
APP_MODULES = sorted(
    f for f in os.listdir(REPO)
    if f.endswith(".py") and not f.startswith("test_")
)


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestAppModules(unittest.TestCase):

    def test_expected_modules_present(self):
        # A sanity anchor: if this changes, the rest of the file needs a look.
        self.assertEqual(APP_MODULES, ["framework_gui.py", "parsers.py"])


class TestWindowsPackaging(unittest.TestCase):

    def test_build_bat_copies_every_module(self):
        build = read("windows", "build.bat")
        for mod in APP_MODULES:
            self.assertIn(
                mod, build,
                f"windows/build.bat does not copy {mod} into the PyInstaller "
                f"work dir — the exe would fail to import it")

    def test_install_ps1_copies_every_module(self):
        install = read("windows", "install.ps1")
        for mod in APP_MODULES:
            self.assertIn(
                mod, install,
                f"windows/install.ps1 does not install {mod}")


class TestFlatpakPackaging(unittest.TestCase):

    MANIFEST = os.path.join("flatpak", "io.github.frameworkgui.FrameworkGUI.yml")

    def test_manifest_installs_every_module(self):
        manifest = read(self.MANIFEST)
        for mod in APP_MODULES:
            self.assertIn(
                f"install -Dm644 {mod} /app/share/framework-gui/{mod}", manifest,
                f"Flatpak manifest has no install command for {mod}")
            self.assertIn(
                f"path: ../{mod}", manifest,
                f"Flatpak manifest does not list {mod} as a source")

    def test_manifest_referenced_files_exist(self):
        """Every `path:` in the manifest must resolve, relative to flatpak/."""
        manifest = read(self.MANIFEST)
        flatpak_dir = os.path.join(REPO, "flatpak")
        paths = [
            line.split("path:", 1)[1].strip()
            for line in manifest.splitlines() if line.strip().startswith("path:")
        ]
        self.assertTrue(paths, "no file sources found in the manifest")
        for p in paths:
            self.assertTrue(
                os.path.exists(os.path.join(flatpak_dir, p)),
                f"manifest references {p}, which does not exist")

    def test_launcher_and_desktop_entry_agree(self):
        desktop = read("flatpak", "io.github.frameworkgui.FrameworkGUI.desktop")
        manifest = read(self.MANIFEST)
        self.assertIn("Exec=framework-gui", desktop)
        self.assertIn("command: framework-gui", manifest)

    def test_manifest_is_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        data = yaml.safe_load(read(self.MANIFEST))
        self.assertEqual(data["app-id"], "io.github.frameworkgui.FrameworkGUI")
        self.assertTrue(data["modules"])


if __name__ == "__main__":
    unittest.main()
