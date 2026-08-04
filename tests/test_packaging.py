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
        self.assertEqual(APP_MODULES, [
            "appstate.py", "backdrop.py", "deps.py", "device_images.py",
            "drivers.py", "framework_gui.py", "module_icons.py",
            "navigation.py", "parsers.py", "power.py", "theme.py",
            "widgets.py"])

    def test_only_the_ui_layer_imports_the_toolkit(self):
        """The logic modules stay testable without a display.

        parsers/power/deps/drivers/navigation/theme/appstate/backdrop/
        device_images/module_icons are all unit-tested on machines with no
        Qt platform plugin. An import of PySide6 in any of them would take
        that away, and it is an easy thing to add by accident.
        """
        ui_layer = {"framework_gui.py", "widgets.py"}
        for mod in APP_MODULES:
            if mod in ui_layer:
                continue
            self.assertNotIn(
                "PySide6", read(mod),
                f"{mod} imports the UI toolkit — keep it display-free")


class TestAssets(unittest.TestCase):
    """The Overview's device photographs have to reach every build.

    They are data, not code, so the module-list checks above miss them: an
    exe or a Flatpak without them launches fine and then shows a blank hero
    slot on the home screen.
    """

    ASSETS = sorted(os.listdir(os.path.join(REPO, "assets", "devices")))

    def test_assets_exist(self):
        self.assertTrue(self.ASSETS, "no device images in assets/devices")

    def test_build_bat_bundles_the_assets(self):
        build = read("windows", "build.bat")
        self.assertIn("assets", build)
        self.assertIn("--add-data", build,
                      "PyInstaller is not told to bundle assets/")

    def test_install_ps1_copies_the_assets(self):
        self.assertIn("assets", read("windows", "install.ps1"))

    def test_manifest_installs_every_asset(self):
        manifest = read(TestFlatpakPackaging.MANIFEST)
        for name in self.ASSETS:
            self.assertIn(
                f"install -Dm644 {name}", manifest,
                f"Flatpak manifest has no install command for {name}")
            self.assertIn(
                f"path: ../assets/devices/{name}", manifest,
                f"Flatpak manifest does not list {name} as a source")


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

    def test_manifest_installs_the_toolkit(self):
        """The Flatpak has to carry PySide6; the runtime has no Python Qt.

        This is the check that would have caught shipping a bundle that
        launches straight into ModuleNotFoundError: No module named
        'PySide6'.
        """
        manifest = read(self.MANIFEST)
        self.assertIn("PySide6", manifest)
        self.assertIn("shiboken6", manifest)

    def test_wheel_sources_are_pinned_by_hash(self):
        # An unpinned wheel URL makes the build non-reproducible and is a
        # supply-chain hole; flatpak-builder requires the hash anyway.
        manifest = read(self.MANIFEST)
        wheels = [line for line in manifest.splitlines()
                  if line.strip().startswith("url:") and ".whl" in line]
        self.assertTrue(wheels, "no wheel sources found")
        self.assertEqual(len(wheels),
                         manifest.count("sha256:"),
                         "a pinned wheel is missing its sha256")

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


class TestUninstallerIsInstalled(unittest.TestCase):
    """Every Windows install path has to leave an uninstaller behind.

    The scripts are often run from a network share that will not still be
    mounted (or still exist) when someone wants to remove the app, so an
    uninstaller that only lives next to the installer is not good enough.
    """

    INSTALLERS = ("install.ps1", "install-exe.ps1")

    def test_install_scripts_copy_the_uninstaller(self):
        for script in self.INSTALLERS:
            text = read("windows", script)
            for f in ("uninstall.ps1", "uninstall.cmd"):
                self.assertIn(
                    f, text,
                    f"windows/{script} does not install {f} into the app "
                    f"directory — the user would have no way to uninstall")

    def test_install_scripts_create_a_start_menu_entry(self):
        for script in self.INSTALLERS:
            text = read("windows", script)
            self.assertIn("Start Menu\\Programs", text,
                          f"windows/{script} creates no Start Menu entry")
            self.assertIn(
                "Uninstall Framework System GUI.lnk", text,
                f"windows/{script} creates no Start Menu uninstall entry")

    def test_install_scripts_register_in_apps_and_features(self):
        for script in self.INSTALLERS:
            text = read("windows", script)
            self.assertIn("CurrentVersion\\Uninstall\\FrameworkGUI", text)
            self.assertIn("UninstallString", text)

    def test_setup_exe_puts_both_entries_in_the_start_menu(self):
        iss = read("windows", "installer.iss")
        self.assertIn('Name: "{group}\\{#AppName}"', iss)
        self.assertIn("{uninstallexe}", iss,
                      "installer.iss has no Start Menu uninstall shortcut")

    def test_setup_exe_has_a_stable_appid(self):
        # Inno ties upgrades and the Apps & features entry to AppId; losing
        # it orphans every previous install's uninstaller.
        self.assertIn("AppId={{", read("windows", "installer.iss"))


class TestLicense(unittest.TestCase):

    def test_license_file_exists_and_is_mit(self):
        text = read("LICENSE")
        self.assertIn("MIT License", text)
        self.assertIn("Permission is hereby granted, free of charge", text)

    def test_readme_links_the_license(self):
        self.assertIn("(LICENSE)", read("README.md"))

    def test_license_ships_with_the_packages(self):
        self.assertIn("LicenseFile=..\\LICENSE", read("windows", "installer.iss"))
        manifest = read(TestFlatpakPackaging.MANIFEST)
        self.assertIn("install -Dm644 LICENSE", manifest)
        self.assertIn("path: ../LICENSE", manifest)


class TestReleaseWorkflow(unittest.TestCase):
    """The release workflow is what the README's download links depend on.

    Those links are /releases/latest/download/<asset>, so the asset
    filenames are a contract between the workflow and the README.
    """

    WORKFLOW = os.path.join(".github", "workflows", "release.yml")
    ASSETS = (
        "FrameworkGUI-Setup.exe",
        "FrameworkGUI.exe",
        "FrameworkGUI.flatpak",
    )

    def test_fires_when_a_release_is_published(self):
        text = read(self.WORKFLOW)
        self.assertIn("release:", text)
        self.assertIn("types: [published]", text)

    def test_uploads_every_advertised_asset(self):
        text = read(self.WORKFLOW)
        for asset in self.ASSETS:
            self.assertIn(
                asset, text,
                f"{self.WORKFLOW} never produces {asset}, but README links it")

    def test_readme_links_every_asset(self):
        readme = read("README.md")
        for asset in self.ASSETS:
            self.assertIn(
                f"releases/latest/download/{asset}", readme,
                f"README does not link the {asset} download")

    def test_can_write_release_assets(self):
        self.assertIn("contents: write", read(self.WORKFLOW))

    def test_workflows_are_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for path in (self.WORKFLOW,
                     os.path.join(".github", "workflows", "ci.yml"),
                     os.path.join(".github", "actions", "build-windows",
                                  "action.yml")):
            with self.subTest(path=path):
                self.assertTrue(yaml.safe_load(read(path)))

    def test_ci_and_release_share_one_windows_build(self):
        # Both must go through the composite action; a hand-rolled copy in
        # one of them is how the shipped artifact drifts from the tested one.
        action = "./.github/actions/build-windows"
        self.assertIn(action, read(self.WORKFLOW))
        self.assertIn(action, read(".github", "workflows", "ci.yml"))


if __name__ == "__main__":
    unittest.main()
