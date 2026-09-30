"""
The handful of UI choices that survive a relaunch.

Five things persist: which appearance the user picked (`acrylic` or
`opaque`), both from the design's State table; how tall they dragged the
output drawer; which section they last had open, so relaunching the app
returns to where they left off instead of always landing on Overview; which
unit temperature readings display in (`C` or `F`); and per-bay labels a
person typed for their own expansion cards. Nothing about the *hardware* is
cached here — every reading in the app comes from running a command, and a
stale cached one would be worse than a blank field — but a bay label is not
a reading at all: the CLI cannot identify a passive USB-C/USB-A card (see
CLAUDE.md), so "my 1TB SSD" is local metadata the app has no other way to
ever learn, keyed by board string and bay name so it never gets shown
against the wrong machine or the wrong slot.

Stdlib only, no toolkit import, and every read and write goes through an
injectable callable so the whole module is testable without touching a real
home directory. A missing, unreadable or corrupt settings file is not an
error: it means "no preference yet", and DEFAULTS apply. Failing to launch
because a JSON file has a stray comma would be a poor trade for remembering
a drawer height.
"""

import json
import os

from . import navigation, theme

TEMP_UNITS = ("C", "F")

DEFAULTS = {
    "appearance": theme.ACRYLIC,
    "drawer_height": theme.DRAWER_DEFAULT,
    "last_section": navigation.SECTIONS[0],
    "temp_unit": TEMP_UNITS[0],
    "bay_labels": {},
}

# How long a typed bay label may be - long enough for "Samsung 990 Pro 2TB",
# short enough that it cannot push a bay row's layout around.
BAY_LABEL_MAX = 40

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
    section = raw.get("last_section")
    if section in navigation.SECTIONS:
        state["last_section"] = section
    unit = raw.get("temp_unit")
    if unit in TEMP_UNITS:
        state["temp_unit"] = unit
    state["bay_labels"] = _clean_bay_labels(raw.get("bay_labels"))
    return state


def _clean_bay_labels(raw):
    """A `{board: {bay_name: label}}` dict with anything malformed dropped —
    a hand-edited file, or an older/newer version of this app disagreeing
    about the shape, must not be a reason to lose every other setting.
    """
    clean = {}
    if not isinstance(raw, dict):
        return clean
    for board, bays in raw.items():
        if not isinstance(board, str) or not isinstance(bays, dict):
            continue
        clean_bays = {
            name: text[:BAY_LABEL_MAX] for name, text in bays.items()
            if isinstance(name, str) and isinstance(text, str) and text.strip()
        }
        if clean_bays:
            clean[board] = clean_bays
    return clean


def bay_label(state, board, bay_name):
    """The label a person set for one bay on one board, or ""."""
    return state.get("bay_labels", {}).get(board, {}).get(bay_name, "")


def set_bay_label(state, board, bay_name, text):
    """`state["bay_labels"]` with one bay's label set (or cleared, for an
    empty `text`) — mutates and returns `state` so a caller can save it
    straight back with `appstate.save`.
    """
    labels = state.setdefault("bay_labels", {})
    text = (text or "").strip()
    if text:
        labels.setdefault(board, {})[bay_name] = text[:BAY_LABEL_MAX]
    elif board in labels:
        labels[board].pop(bay_name, None)
        if not labels[board]:
            del labels[board]
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
