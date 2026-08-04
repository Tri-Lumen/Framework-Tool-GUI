# Framework-Tool-GUI

[![CI](https://github.com/Tri-Lumen/Framework-Tool-GUI/actions/workflows/ci.yml/badge.svg)](https://github.com/Tri-Lumen/Framework-Tool-GUI/actions/workflows/ci.yml)

A graphical user interface to be used in conjunction with the `framework_tool`
Rust libraries — a PySide6/Qt front-end for
[framework_tool](https://github.com/FrameworkComputer/framework-system),
packaged for Windows and Linux (Flatpak).

The window is an icon rail (five groups) selecting a pane list (the sections
inside that group), a content column, and a resizable output drawer that
shows every command the app runs and what it printed, verbatim. It is dark
only, with a translucent "acrylic" appearance where the platform can
composite one and a flat opaque appearance everywhere else — the app probes
at startup, forces opaque when it cannot, and says which one you have got in
the status bar rather than leaving a translucent window over nothing.

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
framework_gui.py   Qt app — layout, command execution, the 14 diagnostics
widgets.py         Reusable UI pieces: cards, panels, bars, badges, the rail
theme.py           Design tokens and the Qt style sheet built from them
navigation.py      Rail/pane model and every capability-gated row
appstate.py        The two UI choices that persist: appearance, drawer height
backdrop.py        Can this platform composite a translucent window, and how
device_images.py   Board string → which product photograph to show
module_icons.py    Expansion-card marks, drawn as SVG paths rather than files
parsers.py         Regex parsers + device detection
power.py           CPU power-limit (TDP) backends: RyzenAdj, Linux powercap,
                   Windows powercfg
deps.py            Registry of helper tools and how to install each one
drivers.py         Catalog of Framework's per-build download pages
                   (only framework_gui.py and widgets.py import the toolkit,
                   so everything else is unit-testable without a display)
assets/devices/    Product photographs for the Overview, one per chassis
tests/             Logic tests, GUI smoke tests, packaging checks
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
It installs PySide6 into that Python if it is not already there; the
packaged exe has the toolkit built in and needs none of this.

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
everything worth changing on these machines. Three sections drive other
tools:

**CPU limits** — sustained and boost power limits. The EC cannot set these,
so the app picks a backend from the CPU and OS:

| Backend | CPU | OS | Sets |
| --- | --- | --- | --- |
| [RyzenAdj](https://github.com/FlyGoat/RyzenAdj) | AMD | Windows, Linux | STAPM / PPT fast / PPT slow — real watts |
| Linux powercap (RAPL) | Intel, some AMD | Linux | Kernel long/short power limits — real watts |
| `powercfg` | any | Windows | Max processor state % — a frequency cap, not a wattage |

RyzenAdj and RAPL limits are **volatile**: a reboot clears them, and sleep or
an AC/battery transition often does too. Re-applying automatically would need
a service or scheduled task, which this project deliberately does not have —
so the pane links to the documentation for making it stick with *the tool it
actually used*: a systemd unit for RyzenAdj or RAPL on Linux, a Task
Scheduler task for RyzenAdj on Windows. `powercfg` is the exception: it edits
the saved power scheme, so Windows restores it across reboots on its own, and
the pane says so instead of telling you to re-apply it.

ARM has no equivalent tool to shell out to, and the pane says that rather
than showing dead controls.

**Setup** — detects the helper tools and installs them. Every install shows
the exact command (or the page it will open) and waits for you to confirm;
nothing installs silently. Where a distro genuinely has no package — RyzenAdj
is not in Debian, Ubuntu or Fedora — you get upstream's instructions instead
of a package-manager command that would only fail confusingly. Downloaded
helpers go in a per-user tools directory, never into the app's own install
directory.

**Drivers** — links, nothing more. Framework publishes one downloads list per
device build, always carrying the current BIOS and driver bundle, so the pane
opens the right one rather than trying to guess which file on the page you
want. The detected build is offered at the top; every other build is in a
dropdown below it, for when detection misses or you are fetching drivers for
a different machine. Vendor pages for parts the bundle does not cover — a
replacement Wi-Fi card, a Graphics Module, an aftermarket GPU — are listed
separately.

## Device detection

On launch (and via the "Rescan device" button on the Overview) the GUI runs
`--versions` once, parses the mainboard type, and shows only the controls
that apply —
e.g. stylus/touchscreen on Laptop 12, expansion bay on Laptop 16, RGB LEDs
on Desktop, and battery/keyboard-light/fingerprint controls only on
laptops (Desktop has none of those). If detection fails or the board
string is not recognized, every control is shown rather than guessing.

The Overview also shows a photograph of the detected machine so you can see
at a glance whether the app got it right. Those are per *chassis*, not per
mainboard — swapping the mainboard does not change what a Laptop 13 looks
like — with two exceptions that do change the outside: the Laptop 13 Pro's
black lid, and a Laptop 16 carrying a Graphics Module.

The six stat cards and the expansion-bay panel need `--power`, `--thermal`
and `--pdports` as well, which is three more elevated commands. When the app
is already running as root it reads them on launch; behind `pkexec` that
would mean three extra password prompts every time you open the window, so
there it waits for you to press "Rescan device".

## Background footprint

None. No services, timers, tray icons, or autostart entries. A process is
spawned per button press and exits when the command finishes. This is why
power limits do not survive a reboot — see the CPU limits section above.

## Running from source / development

```bash
pip install -r requirements.txt                      # PySide6, the one dependency
python3 framework_gui.py                             # run it
python3 -m unittest discover tests -v                # logic + packaging tests
xvfb-run -a python3 -m unittest discover tests -v    # full suite, headless Linux
QT_QPA_PLATFORM=offscreen python3 -m unittest discover tests -v   # or this
ruff check .                                         # lint
```

The GUI smoke tests skip themselves when PySide6 is missing or no Qt platform
plugin will start (and on Windows, where their stub binary can't run), so the
suite is safe to run anywhere. Qt's wheels bring Qt but not the X/EGL
libraries it links against; on a bare Linux box install `libegl1 libgl1
libxkbcommon-x11-0 libxcb-cursor0` and friends, as CI does.

Only `framework_gui.py` and `widgets.py` import the toolkit. Everything else
— parsers, power, deps, drivers, navigation, theme, appstate, backdrop,
device_images, module_icons — is standard library only and tested without a
display, and `tests/test_packaging.py` fails if an import of PySide6 creeps
into one of them. See `CLAUDE.md` for architecture notes, known gotchas, and
what hasn't been verified yet (this project has not been run against real
Framework hardware).

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
