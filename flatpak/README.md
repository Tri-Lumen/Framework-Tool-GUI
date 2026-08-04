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
flatpak install -y flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
sudo apt install flatpak-builder   # or dnf/pacman equivalent
```

## Build + bundle (from the LOCAL copy)

```bash
flatpak-builder --force-clean --repo=repo build io.github.frameworkgui.FrameworkGUI.yml
flatpak build-bundle repo FrameworkGUI.flatpak io.github.frameworkgui.FrameworkGUI
cp FrameworkGUI.flatpak /path/to/share/   # bundle is just a file - share is fine
```

First build compiles Tcl/Tk and Python (a few minutes); rebuilds are cached.

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
- Elevation uses the host's pkexec, so expect a polkit password prompt per
  command unless you install a polkit policy with `auth_admin_keep` for the
  framework_tool path on the host.
- The app id `io.github.frameworkgui.FrameworkGUI` is a placeholder; rename
  consistently across the manifest/desktop/icon files if you publish it.
