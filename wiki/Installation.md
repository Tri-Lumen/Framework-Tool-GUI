# Installation

## 1. Install `framework_tool` first

The GUI drives the CLI. Without it the app starts and can do nothing.

**Windows**

```
winget install framework_tool --source winget
```

**Linux** — packaged under different names, and absent from most distros:

- Arch (AUR): `framework-system-git`
- Otherwise: build it from
  [upstream's README](https://github.com/FrameworkComputer/framework-system)

The app's **Setup** section detects whether it is installed and will show you
the exact install command before running anything.

## 2. Install the GUI

Prebuilt packages are attached to every
[release](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases).

| Platform | Download | What you get |
| --- | --- | --- |
| Windows (recommended) | `FrameworkGUI-Setup.exe` | Start Menu entry, uninstaller, Apps & features entry |
| Windows (portable) | `FrameworkGUI.exe` | One self-contained exe, nothing installed |
| Linux | `FrameworkGUI.flatpak` | `flatpak install --user FrameworkGUI.flatpak` |

Windows SmartScreen warns about the unsigned installer — "More info" → "Run
anyway". There is no code-signing certificate for this project.

### Running from source

```bash
pip install -r requirements.txt      # PySide6-Essentials, the only dependency
python3 framework_gui.py
```

On a bare Linux box Qt also needs the X/EGL libraries its wheels link
against: `libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0` and the rest of
the list in `.github/workflows/ci.yml`.

## 3. Elevation

Most of what `framework_tool` does needs to talk to the embedded controller,
which needs administrator/root.

- **Windows** — the packaged exe carries a `--uac-admin` manifest and asks
  once at launch. The script install marks its Start Menu shortcut
  run-as-administrator.
- **Linux** — the app wraps commands in `pkexec` when it is not already
  root. You can turn that off in the status bar if you would rather launch
  the whole app elevated; running it as root means one prompt instead of
  one per command.

The status bar always says which of the two you have.

### A note on the Flatpak

The sandbox cannot reach the EC at all, so the Flatpak runs `framework_tool`
on the **host** via `flatpak-spawn --host`. That is a deliberate, unavoidable
hole in the sandbox and it is documented in `flatpak/README.md`. The CLI has
to be installed on the host, not in the sandbox.
