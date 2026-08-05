"""
The handful of UI choices that survive a relaunch.

Two things persist, both from the design's State table: which appearance the
user picked (`acrylic` or `opaque`) and how tall they dragged the output
drawer. Nothing about the hardware is cached here — every reading in the app
comes from running a command, and a stale cached one would be worse than a
blank field.

Stdlib only, no toolkit import, and every read and write goes through an
injectable callable so the whole module is testable without touching a real
home directory. A missing, unreadable or corrupt settings file is not an
error: it means "no preference yet", and DEFAULTS apply. Failing to launch
because a JSON file has a stray comma would be a poor trade for remembering
a drawer height.
"""

import json
import os

from . import theme

DEFAULTS = {
    "appearance": theme.ACRYLIC,
    "drawer_height": theme.DRAWER_DEFAULT,
}

FILENAME = "settings.json"


def config_dir(environ=None):
    """Where the settings file lives.

    Mirrors `deps.tools_dir()`: the user's own config location on each OS,
    never next to the app, which may be in Program Files or a read-only
    Flatpak. Inside the sandbox XDG_CONFIG_HOME already points at the app's
    private directory, so this needs no Flatpak special case.
    """
    env = environ if environ is not None else os.environ
    local = env.get("LOCALAPPDATA")
    if local:
        return os.path.join(local, "FrameworkGUI")
    base = env.get("XDG_CONFIG_HOME") or os.path.join(
        env.get("HOME", os.path.expanduser("~")), ".config")
    return os.path.join(base, "framework-gui")


def config_path(environ=None):
    return os.path.join(config_dir(environ), FILENAME)


def clamp_drawer(height):
    """Drawer height inside the design's 70–460px bounds.

    Anything unparseable falls back to the default rather than raising: the
    value comes off disk, where a hand-edited or truncated file is a normal
    thing to find.
    """
    try:
        value = int(round(float(height)))
    except (TypeError, ValueError):
        return DEFAULTS["drawer_height"]
    return max(theme.DRAWER_MIN, min(theme.DRAWER_MAX, value))


def normalise(raw):
    """A stored dict (or anything at all) into a complete, valid state."""
    state = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return state
    appearance = raw.get("appearance")
    if appearance in theme.APPEARANCES:
        state["appearance"] = appearance
    if "drawer_height" in raw:
        state["drawer_height"] = clamp_drawer(raw["drawer_height"])
    return state


def load(path=None, opener=None):
    """Read the settings file. Never raises — a bad file means DEFAULTS."""
    target = path or config_path()
    open_file = opener or open
    try:
        with open_file(target, encoding="utf-8") as fh:
            return normalise(json.load(fh))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(state, path=None, opener=None, makedirs=None):
    """Write the settings file. Returns True when it landed.

    A failed write is reported, not raised: losing a remembered drawer
    height is not worth an error dialog, and the caller shows nothing.
    """
    target = path or config_path()
    open_file = opener or open
    make = makedirs or (lambda d: os.makedirs(d, exist_ok=True))
    try:
        make(os.path.dirname(target))
        with open_file(target, "w", encoding="utf-8") as fh:
            json.dump(normalise(state), fh, indent=2, sort_keys=True)
        return True
    except (OSError, ValueError, TypeError):
        return False
