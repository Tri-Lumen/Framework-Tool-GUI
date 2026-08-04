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

## Download

Prebuilt Windows and Linux packages are attached to every
[release](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases). These
links always resolve to the newest one:

| Platform | Download | What you get |
| --- | --- | --- |
| **Windows** (recommended) | [FrameworkGUI-Setup.exe](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases/latest/download/FrameworkGUI-Setup.exe) | Installer — Start Menu entry, uninstaller, Apps & features entry |
| **Windows** (portable) | [FrameworkGUI.exe](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases/latest/download/FrameworkGUI.exe) | Single self-contained exe, nothing installed |
| **Linux** | [FrameworkGUI.flatpak](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases/latest/download/FrameworkGUI.flatpak) | Flatpak bundle — `flatpak install --user FrameworkGUI.flatpak` |

Windows SmartScreen will warn about the unsigned installer ("More info" →
"Run anyway"); there is no code-signing certificate for this project.

Both builds are produced by
[`.github/workflows/release.yml`](.github/workflows/release.yml), which runs
when a release is published and attaches the artifacts to it.

## Repository layout

```
framework_gui.py   Tk app — UI, command execution, the 14 "Tools" workflows
parsers.py         Regex parsers + device detection
power.py           CPU power-limit (TDP) backends: RyzenAdj, Linux powercap,
                   Windows powercfg
deps.py            Registry of helper tools and how to install each one
drivers.py         Framework driver-page catalog + download scraping
                   (none of the four import tkinter, so all are unit-testable
                   without a display)
tests/             Parser tests, GUI smoke tests, packaging checks
windows/           PyInstaller build, Inno Setup script, install/uninstall
flatpak/           Manifest, .desktop, launcher, icon, its own README
.github/           CI, the release workflow, the shared Windows build action
LICENSE            MIT
CLAUDE.md          Architecture notes, gotchas, and what is still unverified
```

## Windows

**Normal install:** download
[FrameworkGUI-Setup.exe](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases/latest/download/FrameworkGUI-Setup.exe)
and run it. It installs the app, adds a **Start Menu** group
("Framework System GUI") containing the app *and* an **Uninstall** entry,
and registers in Settings → Apps. The app self-elevates (one UAC prompt per
launch), no console window.

Everything below is for building or deploying it yourself.

**Build it yourself** (any Windows machine with Python):
Double-click `windows\build.bat`. It builds locally in `%TEMP%` (SMB-safe) and
puts `FrameworkGUI.exe` in `windows\dist\`.
Note: build.bat ONLY builds — it does not install anything anywhere.
To get the installer too, compile `windows\installer.iss` with
[Inno Setup](https://jrsoftware.org/isinfo.php) afterwards
(`ISCC.exe /DAppVersion=1.2.3 windows\installer.iss`).

CI does both on every push; you can download them from the
**FrameworkGUI-windows** artifact of a green
[CI run](https://github.com/Tri-Lumen/Framework-Tool-GUI/actions/workflows/ci.yml)
instead of building them yourself.

**Deploy from a share, without the installer:**
double-click `windows\install-exe.cmd` — copies the exe to
`%LOCALAPPDATA%\FrameworkGUI` along with a copy of the uninstaller, creates
the same Start Menu group (app + Uninstall entry), and registers in
Settings → Apps.

**No-build alternative** (needs Python on every device):
double-click `windows\install.cmd` — installs the Python script version
with a run-as-admin Start Menu shortcut, uninstaller included the same way.

**Uninstall:** Start Menu → Framework System GUI → *Uninstall Framework
System GUI*, or Settings → Apps. Installs made by `FrameworkGUI-Setup.exe`
use the installer's own uninstaller; installs made by the `.cmd` scripts use
`%LOCALAPPDATA%\FrameworkGUI\uninstall.cmd`, which those scripts put there.

All .cmd wrappers exist because PowerShell's execution policy blocks .ps1
files launched directly from network shares; the wrappers bypass that.

## Linux — Flatpak

Download
[FrameworkGUI.flatpak](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases/latest/download/FrameworkGUI.flatpak)
from the latest release, then:

```bash
flatpak install --user FrameworkGUI.flatpak     # install
flatpak uninstall --user io.github.frameworkgui.FrameworkGUI   # uninstall
```

To build the bundle yourself see `flatpak/README.md` — build on a LOCAL disk
(flatpak-builder cannot build on CIFS/SMB mounts) and export
`FrameworkGUI.flatpak`.

The sandbox cannot touch the embedded controller, so the app runs the
host's `framework_tool` via `flatpak-spawn --host`
(`--talk-name=org.freedesktop.Flatpak` permission). Install `framework_tool`
on every host.

## Beyond framework_tool

`framework_tool` talks to the embedded controller, which does not own
everything worth changing on these machines. Three tabs drive other tools:

**Power (TDP)** — sustained and boost power limits. The EC cannot set these,
so the app picks a backend from the CPU and OS:

| Backend | CPU | OS | Sets |
| --- | --- | --- | --- |
| [RyzenAdj](https://github.com/FlyGoat/RyzenAdj) | AMD | Windows, Linux | STAPM / PPT fast / PPT slow — real watts |
| Linux powercap (RAPL) | Intel, some AMD | Linux | Kernel long/short power limits — real watts |
| `powercfg` | any | Windows | Max processor state % — a frequency cap, not a wattage |

Limits set here are **volatile**: a reboot clears them, and sleep or an
AC/battery transition often does too. Re-applying automatically would need a
service or scheduled task, which this project deliberately does not have —
the tab says so and you click Apply again. ARM has no equivalent tool to
shell out to, and the tab says that too rather than showing dead controls.

**Setup** — detects the helper tools and installs them. Every install shows
the exact command (or the page it will open) and waits for you to confirm;
nothing installs silently. Where a distro genuinely has no package — RyzenAdj
is not in Debian, Ubuntu or Fedora — you get upstream's instructions instead
of a package-manager command that would only fail confusingly. Downloaded
helpers go in a per-user tools directory, never into the app's own install
directory.

**Drivers** — maps the detected board to its Framework Knowledge Base page,
scrapes the driver-bundle link off it, and downloads it to your Downloads
folder. If the page can't be fetched or its markup has changed, it opens the
page in your browser rather than failing. The app never runs an installer for
you. There is also a list of vendor driver pages for parts the bundle does
not cover — a replacement Wi-Fi card, a Graphics Module, an aftermarket GPU.

## Device detection

On launch (and via the "Rescan device" button) the GUI runs `--versions`
once, parses the mainboard type, and shows only the controls that apply —
e.g. stylus/touchscreen on Laptop 12, expansion bay on Laptop 16, RGB LEDs
on Desktop, and battery/keyboard-light/fingerprint controls only on
laptops (Desktop has none of those). If detection fails or the board
string is not recognized, every control is shown rather than guessing.

## Background footprint

None. No services, timers, tray icons, or autostart entries. A process is
spawned per button press and exits when the command finishes. This is why
power limits do not survive a reboot — see the Power tab above.

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

## Cutting a release

1. Publish a GitHub Release with a tag like `v1.0.0`.
2. `.github/workflows/release.yml` fires on *publish*, builds
   `FrameworkGUI.exe` + `FrameworkGUI-Setup.exe` (stamped with the tag's
   version) and `FrameworkGUI.flatpak`, and uploads all three to that
   release.
3. The download links above start serving them as soon as the run finishes.

Run the workflow manually (`workflow_dispatch`) to rehearse the builds
without publishing anything — it produces the same artifacts and skips only
the upload step.

## License

[MIT](LICENSE) — fork it, reuse it, ship it, no permission needed. This is
an unofficial project and is not affiliated with or endorsed by Framework
Computer Inc.
