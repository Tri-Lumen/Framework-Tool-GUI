"""
The application icon, and where each packaging path expects to find it.

The app shipped without one: Windows gave the exe the generic PyInstaller
icon, the window and taskbar showed Qt's default, and the Flatpak carried a
placeholder SVG. One source file now answers for all of them —
`assets/icons/` holds the Framework mark as a multi-resolution `.ico` for
Windows and as PNGs for everywhere else.

Filenames and path resolution only, in the same idiom as `device_images`:
stdlib imports, no toolkit, no I/O beyond the `exists` check callers can
inject. `tests/test_packaging.py` is what keeps the packaging paths honest
about carrying these files.

Two resolutions matter beyond the icon simply existing. Windows reads the
`.ico` for the exe, the installer and the Start Menu shortcut, and it needs
the small sizes inside it or the taskbar scales the 256px one badly — the
shipped file carries nine, 16 through 256. Qt wants a `QIcon` built from
several PNGs so the window, the alt-tab switcher and the task switcher each
pick the size they want instead of resampling one.
"""

import os
import sys

ASSET_DIR = os.path.join("assets", "icons")

# The Windows icon resource: exe, installer, Start Menu shortcut.
ICO = "FrameworkGUI.ico"

# The largest PNG, for the Flatpak's hicolor icon and anything wanting one
# file rather than a set.
PNG = "FrameworkGUI.png"

# Sizes bundled as individual PNGs, for building a Qt multi-resolution icon.
# 256 is the one the Flatpak installs; the rest exist so Qt never has to
# resample down to a 16px titlebar mark.
SIZES = (16, 32, 48, 64, 128, 256)

PNG_SIZED = tuple("FrameworkGUI-{}.png".format(size) for size in SIZES)

# Everything a packaging path has to carry.
FILES = (ICO, PNG) + PNG_SIZED


def asset_root():
    """The directory the icons live in, packaged build or source checkout.

    PyInstaller unpacks bundled data into a temporary tree it advertises as
    `sys._MEIPASS`; everywhere else the assets sit next to the modules. Same
    rule as `device_images.asset_root` — loading a data file any other way
    works from a checkout and not from the exe.
    """
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.abspath(__file__))
    return os.path.join(base, ASSET_DIR)


def path_for(name, exists=None):
    """Full path to one icon file, or None when the build did not ship it."""
    check = exists or os.path.isfile
    path = os.path.join(asset_root(), name)
    return path if check(path) else None


def ico_path(exists=None):
    return path_for(ICO, exists)


def png_paths(exists=None):
    """Every sized PNG present, smallest first.

    Empty is a real answer: a build without the icons should fall back to
    Qt's default rather than fail to start, which is why nothing here
    raises.
    """
    found = [path_for(name, exists) for name in PNG_SIZED]
    return [path for path in found if path]
