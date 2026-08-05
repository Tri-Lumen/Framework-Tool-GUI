"""Packaging checks — cheap guards against shipping a broken build.

The app is a package of fourteen modules plus its assets, and every
packaging path (PyInstaller build, script install, Flatpak manifest) has to
carry all of it. A miss doesn't show up until the app launches on a target
machine and dies with ModuleNotFoundError. These tests are the stand-in for
the Windows/Flatpak builds that CI can't fully exercise; they need no
display, no toolkit, and no build tooling.

The package is what makes this tractable: a path that copies the
`frameworkgui/` directory carries a new module automatically, so these
tests check that each path takes the directory rather than listing files —
which is what they used to have to do, and what fell behind the repo every
time a module was added.
"""

import ast
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from frameworkgui import app_icon  # noqa: E402

# The package the whole app lives in, and the launcher every packaging path
# points at.
PACKAGE = "frameworkgui"
LAUNCHER = "framework_gui.py"

# Modules that make up the app itself (tests/ and tooling excluded).
APP_MODULES = sorted(
    f for f in os.listdir(os.path.join(REPO, PACKAGE))
    if f.endswith(".py")
)


def read(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return fh.read()


class TestAppModules(unittest.TestCase):

    def test_expected_modules_present(self):
        # A sanity anchor: if this changes, the rest of the file needs a look.
        self.assertEqual(APP_MODULES, [
            "__init__.py", "__main__.py", "app.py", "app_icon.py",
            "appstate.py", "backdrop.py", "deps.py", "device_images.py",
            "drivers.py", "iconpaths.py", "module_icons.py", "navigation.py",
            "parsers.py", "power.py", "theme.py", "widgets.py"])

    def test_the_launcher_is_the_only_python_file_at_the_root(self):
        """One entry point, and the app itself in the package beside it.

        Every packaging path names this file, so it staying put is what
        keeps PyInstaller, Inno Setup, the script installers and the
        Flatpak launcher all pointing at the same thing.
        """
        at_root = sorted(f for f in os.listdir(REPO) if f.endswith(".py"))
        self.assertEqual(at_root, [LAUNCHER])
        self.assertIn("from frameworkgui.app import main", read(LAUNCHER))

    def test_the_package_can_be_run_as_a_module(self):
        self.assertIn("from .app import main",
                      read(PACKAGE, "__main__.py"))

    def test_only_the_ui_layer_imports_the_toolkit(self):
        """The logic modules stay testable without a display.

        parsers/power/deps/drivers/navigation/theme/appstate/backdrop/
        device_images/module_icons are all unit-tested on machines with no
        Qt platform plugin. An import of PySide6 in any of them would take
        that away, and it is an easy thing to add by accident.
        """
        ui_layer = {"app.py", "widgets.py", "__main__.py"}
        for mod in APP_MODULES:
            if mod in ui_layer:
                continue
            # The imports, not the text: a module is free to *mention*
            # PySide6 in a comment explaining why it does not import it.
            tree = ast.parse(read(PACKAGE, mod))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add(node.module or "")
            self.assertFalse(
                [name for name in imported if name.startswith("PySide6")],
                f"{mod} imports the UI toolkit — keep it display-free")


class TestAssets(unittest.TestCase):
    """The Overview's device photographs have to reach every build.

    They are data, not code, so the module-list checks above miss them: an
    exe or a Flatpak without them launches fine and then shows a blank hero
    slot on the home screen.
    """

    ASSETS = sorted(os.listdir(os.path.join(REPO, PACKAGE, "assets",
                                            "devices")))

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
                f"path: ../{PACKAGE}/assets/devices/{name}", manifest,
                f"Flatpak manifest does not list {name} as a source")


class TestWindowsPackaging(unittest.TestCase):
    """Both Windows paths have to carry the package, not a list of files.

    The list is what used to fall behind: adding a module meant editing
    three packaging scripts, and forgetting one produced an exe that died
    with ModuleNotFoundError on a machine that had never seen the source.
    """

    def test_build_bat_copies_the_package_and_the_launcher(self):
        build = read("windows", "build.bat")
        self.assertIn(PACKAGE, build,
                      "windows/build.bat does not copy the app package into "
                      "the PyInstaller work dir — the exe could not import it")
        self.assertIn(LAUNCHER, build,
                      "windows/build.bat does not name the entry script")

    def test_install_ps1_copies_the_package_and_the_launcher(self):
        install = read("windows", "install.ps1")
        self.assertIn(PACKAGE, install,
                      "windows/install.ps1 does not install the app package")
        self.assertIn(LAUNCHER, install,
                      "windows/install.ps1 does not install the launcher")


class TestFlatpakPackaging(unittest.TestCase):

    MANIFEST = os.path.join("flatpak", "io.github.frameworkgui.FrameworkGUI.yml")

    def test_manifest_installs_every_module(self):
        """Each module by name, because YAML sources cannot take a directory.

        flatpak-builder's `file` source type is one file; a `dir` source
        would copy the checkout wholesale. So this manifest is the one
        packaging path that still lists modules, and this test is what keeps
        the list current.
        """
        manifest = read(self.MANIFEST)
        for mod in APP_MODULES:
            self.assertIn(
                f"install -Dm644 {mod} "
                f"/app/share/framework-gui/{PACKAGE}/{mod}", manifest,
                f"Flatpak manifest has no install command for {mod}")
            self.assertIn(
                f"path: ../{PACKAGE}/{mod}", manifest,
                f"Flatpak manifest does not list {mod} as a source")

    def test_manifest_installs_the_launcher(self):
        manifest = read(self.MANIFEST)
        self.assertIn(
            f"install -Dm644 {LAUNCHER} /app/share/framework-gui/{LAUNCHER}",
            manifest)
        self.assertIn(f"path: ../{LAUNCHER}", manifest)

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


class TestAppIcon(unittest.TestCase):
    """The app icon is data too, and every path has to carry it.

    The app shipped without one: the exe took PyInstaller's generic icon,
    the window and taskbar showed Qt's default, and the Flatpak carried a
    placeholder SVG. These assert the artwork exists and that each packaging
    path actually installs it, since a missing icon is invisible from a
    source checkout — `app_icon` falls back silently by design, so nothing
    fails loudly when a build forgets it.
    """

    ICON_DIR = os.path.join(REPO, PACKAGE, "assets", "icons")

    def test_every_named_icon_file_is_shipped(self):
        for name in app_icon.FILES:
            self.assertTrue(
                os.path.isfile(os.path.join(self.ICON_DIR, name)),
                f"app_icon names {name} but the package\'s assets/icons "
                f"does not have it")

    def test_the_windows_icon_is_a_real_ico(self):
        with open(os.path.join(self.ICON_DIR, app_icon.ICO), "rb") as fh:
            header = fh.read(4)
        # ICONDIR: reserved=0, type=1 (icon).
        self.assertEqual(header[:4], b"\x00\x00\x01\x00")

    def test_the_ico_carries_the_small_sizes(self):
        """A single 256px image scales badly to a 16px taskbar mark."""
        path = os.path.join(self.ICON_DIR, app_icon.ICO)
        with open(path, "rb") as fh:
            blob = fh.read()
        count = int.from_bytes(blob[4:6], "little")
        widths = {blob[6 + n * 16] or 256 for n in range(count)}
        self.assertIn(16, widths)
        self.assertIn(32, widths)
        self.assertIn(256, widths)

    def test_pyinstaller_is_told_to_use_the_icon(self):
        build = read("windows", "build.bat")
        self.assertIn("--icon", build,
                      "the exe would ship with PyInstaller's default icon")
        self.assertIn(app_icon.ICO, build)

    def test_inno_setup_uses_the_icon(self):
        iss = read("windows", "installer.iss")
        self.assertIn("SetupIconFile", iss)
        self.assertIn(app_icon.ICO, iss)

    def test_the_script_install_gives_its_shortcut_the_icon(self):
        # Otherwise the Start Menu entry shows pythonw.exe's icon.
        install = read("windows", "install.ps1")
        self.assertIn("IconLocation", install)
        self.assertIn(app_icon.ICO, install)

    def test_the_flatpak_installs_the_icon_into_the_theme(self):
        manifest = read(TestFlatpakPackaging.MANIFEST)
        for size in app_icon.SIZES:
            self.assertIn(
                f"/app/share/icons/hicolor/{size}x{size}/apps/", manifest,
                f"no hicolor {size}px icon in the Flatpak manifest")

    def test_the_flatpak_ships_the_icons_for_the_app_to_load(self):
        manifest = read(TestFlatpakPackaging.MANIFEST)
        for name in app_icon.PNG_SIZED:
            self.assertIn(f"path: ../{PACKAGE}/assets/icons/{name}", manifest,
                          f"Flatpak manifest does not list {name} as a source")

    def test_the_placeholder_svg_is_gone(self):
        # It was a crude stand-in; real artwork replaced it.
        self.assertFalse(os.path.isfile(os.path.join(
            REPO, "flatpak", "io.github.frameworkgui.FrameworkGUI.svg")))
        self.assertNotIn("FrameworkGUI.svg",
                         read(TestFlatpakPackaging.MANIFEST))
