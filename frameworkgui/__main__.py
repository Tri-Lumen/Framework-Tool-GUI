"""`python -m frameworkgui` — the same entry point as the launcher script."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
