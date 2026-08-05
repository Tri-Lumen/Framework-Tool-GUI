"""
Framework System GUI — a Qt front-end for the framework_tool CLI.

The whole app lives in this package. `app` is the window and the command
plumbing; `widgets` is the reusable UI pieces. Everything else is stdlib
only and imports no toolkit, which is what keeps the parsers, the gating
rules, the token table and the icon geometry testable in milliseconds on a
machine with no Qt platform plugin — `tests/test_packaging.py` fails if a
PySide6 import appears outside those two modules.

Run it with `python -m frameworkgui`, or through the `framework_gui.py`
launcher at the repository root, which is what every packaging path uses as
its entry point.
"""

__version__ = "1.0.0"
