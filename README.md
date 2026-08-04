# Framework-Tool-GUI

[![CI](https://github.com/Tri-Lumen/Framework-Tool-GUI/actions/workflows/ci.yml/badge.svg)](https://github.com/Tri-Lumen/Framework-Tool-GUI/actions/workflows/ci.yml)

A graphical user interface to be used in conjunction with the `framework_tool`
Rust libraries — a Tkinter front-end for
[framework_tool](https://github.com/FrameworkComputer/framework-system),
packaged for Windows and Linux (Flatpak).

`framework_tool` itself must be installed on each target machine
(Windows: `winget install framework_tool --source winget`; Linux: your
distro's `framework-system` package). The GUI shells out to that CLI — it has
no other way to talk to the hardware.

## Repository layout

```
framework_gui.py   Tk app — UI, command execution, the 14 "Tools" workflows
parsers.py         Regex parsers + device detection. No tkinter import, so it
                   is unit-testable without a display
tests/             Parser tests, GUI smoke tests, packaging checks
windows/           PyInstaller build, Inno Setup script, install/uninstall
flatpak/           Manifest, .desktop, launcher, icon, its own README
CLAUDE.md          Architecture notes, gotchas, and what is still unverified
```

## Windows

**Step 1 — build once** (any Windows machine with Python):
Double-click `windows\build.bat`. It builds locally in `%TEMP%` (SMB-safe) and
puts `FrameworkGUI.exe` in `windows\dist\`.
Note: build.bat ONLY builds — it does not install anything anywhere.

CI also builds this exe on every push; you can download it from the
**FrameworkGUI-exe** artifact of a green
[CI run](https://github.com/Tri-Lumen/Framework-Tool-GUI/actions/workflows/ci.yml)
instead of building it yourself.

**Step 2 — deploy on each device** (pick one):
- Double-click `windows\install-exe.cmd` — copies the exe to
  `%LOCALAPPDATA%\FrameworkGUI` and creates the Start Menu shortcut.
  This is the step that adds it to the Start Menu.
- Or compile `windows\installer.iss` with [Inno Setup](https://jrsoftware.org/isinfo.php)
  once to get `FrameworkGUI-Setup.exe` (Start Menu entry + uninstaller built in),
  then run that setup on each device.

The exe self-elevates (one UAC prompt per launch), no console window.

**No-build alternative** (needs Python on every device):
double-click `windows\install.cmd` — installs the Python script version
with a run-as-admin Start Menu shortcut.

**Uninstall:** double-click `windows\uninstall.cmd`.

All .cmd wrappers exist because PowerShell's execution policy blocks .ps1
files launched directly from network shares; the wrappers bypass that.

## Linux — Flatpak

See `flatpak/README.md`. Build on a LOCAL disk (flatpak-builder cannot build
on CIFS/SMB mounts), export `FrameworkGUI.flatpak`, then per device:

```bash
flatpak install --user FrameworkGUI.flatpak
```

The sandbox cannot touch the embedded controller, so the app runs the
host's `framework_tool` via `flatpak-spawn --host`
(`--talk-name=org.freedesktop.Flatpak` permission). Install `framework_tool`
on every host.

## Device detection

On launch (and via the "Rescan device" button) the GUI runs `--versions`
once, parses the mainboard type, and shows only the controls that apply —
e.g. stylus/touchscreen on Laptop 12, expansion bay on Laptop 16, RGB LEDs
on Desktop, and battery/keyboard-light/fingerprint controls only on
laptops (Desktop has none of those). If detection fails or the board
string is not recognized, every control is shown rather than guessing.

## Background footprint

None. No services, timers, tray icons, or autostart entries. A process is
spawned per button press and exits when the command finishes.

## Running from source / development

```bash
python3 framework_gui.py                             # needs python3-tk installed
python3 -m unittest discover tests -v                # parser + packaging tests
xvfb-run -a python3 -m unittest discover tests -v    # full suite, headless Linux
ruff check .                                         # lint
```

The GUI smoke tests skip themselves when no display is available (and on
Windows, where their stub binary can't run), so the suite is safe to run
anywhere.

`framework_gui.py` is the Tk app; `parsers.py` holds the regex parsers and
device-detection logic and has no tkinter dependency, so its tests run
without a display. See `CLAUDE.md` for architecture notes, known gotchas,
and what hasn't been verified yet (this project has not been run against
real Framework hardware).
