# Flatpak build

Build once on any Linux machine, produce a `.flatpak` bundle, install that
single file everywhere else with one command.

## You probably don't need to build this yourself

Every published GitHub Release carries a prebuilt bundle
([`FrameworkGUI.flatpak`](https://github.com/Tri-Lumen/Framework-Tool-GUI/releases/latest/download/FrameworkGUI.flatpak),
built by `.github/workflows/release.yml`). Download it and skip to
"Install on any device". The rest of this file is for building from source.

## IMPORTANT: do not build on an SMB/CIFS mount

flatpak-builder uses OSTree, which requires hardlinks and extended
attributes that network filesystems do not support. Copy the folder to a
local disk first, build there, then copy only the bundle back:

```bash
cp -r /path/to/share/framework-gui-installer ~/fwgui
cd ~/fwgui/flatpak
```

## One-time setup (build machine)

```bash
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y flathub org.kde.Platform//6.7 org.kde.Sdk//6.7
sudo apt install flatpak-builder   # or dnf/pacman equivalent
```

## Build + bundle (from the LOCAL copy)

```bash
flatpak-builder --force-clean --repo=repo build io.github.frameworkgui.FrameworkGUI.yml
flatpak build-bundle repo FrameworkGUI.flatpak io.github.frameworkgui.FrameworkGUI
cp FrameworkGUI.flatpak /path/to/share/   # bundle is just a file - share is fine
```

Nothing is compiled from source: the UI toolkit comes from pinned PySide6
wheels installed against the KDE runtime's Qt. The first build still spends
a while downloading the runtime and the ~90 MB PySide6 wheel; rebuilds are
cached.

The runtime is `org.kde` rather than `org.freedesktop` on purpose. PySide6's
wheels carry Qt, but not the platform plugins' system dependencies; the KDE
runtime already ships Qt 6, its xcb/wayland plugins, fonts and an icon theme,
so the app starts there and does not on the plain freedesktop runtime.

## Install on any device

```bash
flatpak install --user /path/to/share/FrameworkGUI.flatpak
```

Launch "Framework System GUI" from the app menu.

## Uninstall

Flatpak is the uninstaller here - there is no separate script:

```bash
flatpak uninstall --user io.github.frameworkgui.FrameworkGUI
```

## Notes

- `framework_tool` must be installed **on the host** of each device
  (e.g. `pacman -S framework-system`, `dnf install framework-system`).
  The sandbox cannot reach the EC, so the app runs the host binary via
  `flatpak-spawn --host` - that is what the
  `--talk-name=org.freedesktop.Flatpak` permission in the manifest is for.
  This is an intentional sandbox escape; without it the app is useless.
- There is deliberately no `--share=network`. The Drivers section only opens
  links, which goes through the portal, and the only code path that
  downloads anything (fetching a helper tool's GitHub release) is
  Windows-only. Nothing in the Flatpak build needs network access.
- The Setup section's installs run on the *host* (same `flatpak-spawn --host`
  path as every other command, plus pkexec), so a helper installed from here
  lands in the host's package manager, not in the sandbox. That is what you
  want: the sandbox cannot reach the EC or the SoC either way.
- The window is translucent ("acrylic") only where the session has a
  compositing manager. Under Wayland that is always; under X11 the app
  checks for an owner of the `_NET_WM_CM_S0` selection and falls back to the
  opaque appearance, with a strip at the top of the window saying so, when
  there is none. There is no portable blur on Linux, so acrylic there means
  translucency without one.
- Elevation uses the host's pkexec, so expect a polkit password prompt per
  command unless you install a polkit policy with `auth_admin_keep` for the
  framework_tool path on the host.
- The app id `io.github.frameworkgui.FrameworkGUI` is a placeholder; rename
  consistently across the manifest/desktop/icon files if you publish it.
