"""
Which product photograph to show for a detected board.

The Overview's hero image exists so a user can confirm the app identified
the right machine. What it needs is therefore the *chassis*, not the
mainboard: a Laptop 13 looks the same whichever mainboard is in it, so one
image covers every 13 in the catalog rather than the eleven the design
handoff originally asked for.

Two things do change the outside, and both are detectable, so both get their
own image: the Laptop 13 Pro ships in black where the Laptop 13 is silver,
and a Laptop 16 with a Graphics Module fitted is visibly longer than one
without.

Filenames only — this module does no I/O and imports nothing but the
stdlib's path handling, so the whole mapping is unit-testable. Resolving a
name to bytes on disk is `path_for()`, which is the one function that
touches the filesystem and returns None rather than raising when a build
shipped without the images.
"""

import os
import sys

ASSET_DIR = os.path.join("assets", "devices")

FALLBACK = "unknown.png"

# Most specific first, exactly like drivers.CATALOG: every fragment in
# `match` has to appear in the lowercased board string for the entry to win,
# so "laptop 13 pro" is tested before the entry that matches any 13.
CATALOG = (
    {"match": ("laptop 13 pro",), "image": "laptop-13-pro.png",
     "label": "Framework Laptop 13 Pro"},
    {"match": ("laptop 13",), "image": "laptop-13.png",
     "label": "Framework Laptop 13"},
    {"match": ("laptop 16",), "image": "laptop-16.png",
     "label": "Framework Laptop 16"},
    {"match": ("laptop 12",), "image": "laptop-12.png",
     "label": "Framework Laptop 12"},
    {"match": ("desktop",), "image": "desktop.png",
     "label": "Framework Desktop"},
)

# The Laptop 16 with a Graphics Module in the expansion bay.
LAPTOP_16_GPU = "laptop-16-gpu.png"

IMAGES = tuple(entry["image"] for entry in CATALOG) + (LAPTOP_16_GPU, FALLBACK)


def image_for(board, has_gpu_module=False):
    """The image filename for a board string from `--versions`.

    Falls back to the mainboard photograph rather than to nothing: an
    unrecognised board is still a Framework board, and a blank slot next to
    "Unknown device" reads as a broken app rather than as an honest one.
    """
    text = (board or "").lower()
    for entry in CATALOG:
        if all(fragment in text for fragment in entry["match"]):
            if entry["image"] == "laptop-16.png" and has_gpu_module:
                return LAPTOP_16_GPU
            return entry["image"]
    return FALLBACK


def asset_root():
    """The directory the images live in, packaged build or source checkout.

    PyInstaller unpacks bundled data into a temporary tree it advertises as
    `sys._MEIPASS`; everywhere else the assets sit next to the modules.
    """
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(
        os.path.abspath(__file__))
    return os.path.join(base, ASSET_DIR)


def path_for(board, has_gpu_module=False, exists=None):
    """Full path to the image for a board, or None when it is not shipped."""
    check = exists or os.path.isfile
    path = os.path.join(asset_root(), image_for(board, has_gpu_module))
    return path if check(path) else None
