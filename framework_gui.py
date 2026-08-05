#!/usr/bin/env python3
"""
Launcher for Framework System GUI.

The app itself is the `frameworkgui` package beside this file; this is the
one-line entry point every packaging path points at — PyInstaller's script,
the Inno Setup and script installs' Start Menu shortcut, and the Flatpak's
launcher. Keeping it here means those paths name a file rather than needing
`python -m`, and a source checkout still runs with:

    python3 framework_gui.py
"""

import sys

from frameworkgui.app import main

if __name__ == "__main__":
    sys.exit(main())
