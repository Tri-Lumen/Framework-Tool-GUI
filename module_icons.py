"""
Expansion-card artwork, drawn rather than shipped.

The Overview's bay rows need a mark per module type. These are stroke paths
in the same 18x18 / 1.2px idiom as the rail icons, so the app carries no
image files for them, they tint to whatever colour the port's state calls
for, and they stay sharp at any scale.

Storage cards are the exception and deliberately so: a 1 TB card and a
256 GB card are the same object to look at, so an icon would say nothing
that matters. Those rows get the capacity as text instead — see
`STORAGE`, which callers render as a small bordered box.

Stdlib only, no toolkit import: the paths are data and the classifier is a
pure function, so both are testable without a display. `widgets.ModuleIcon`
is what turns them into pixels.
"""

import re

USB_C = "usb_c"
USB_A = "usb_a"
HDMI = "hdmi"
DISPLAYPORT = "displayport"
MICROSD = "microsd"
SD = "sd"
ETHERNET = "ethernet"
AUDIO = "audio"
STORAGE = "storage"
UNKNOWN = "unknown"

# Paths are drawn in an 18x18 box, stroked (never filled), so they read at
# the row's icon size and at 2x without a second asset.
ICONS = {
    USB_C: ("M4 7h10a2 2 0 0 1 0 4H4a2 2 0 0 1 0-4z", "M6.2 9h5.6"),
    USB_A: ("M3.5 6h11v6h-11z", "M5.6 8.1h7.2v1.9H5.6z"),
    HDMI: ("M3.5 6.9h11v2.7l-1.7 1.5H5.2L3.5 9.6z", "M6 8.2h6"),
    DISPLAYPORT: ("M3.5 6.9h11v4.2H5.1L3.5 9.6z", "M6 8.6h5.5"),
    MICROSD: ("M5.5 4.2h4.7l2.3 2.3v7.3h-7z", "M7.1 4.2v2.4"),
    SD: ("M4.4 3.6h5.9l3.3 3.3v7.5h-9.2z", "M6.2 3.6v2.8", "M8 3.6v2.8"),
    ETHERNET: ("M3.8 7h10.4v5H3.8z", "M6.8 7V4.9h4.4V7", "M6.2 12v1.4",
               "M11.8 12v1.4"),
    AUDIO: ("M9 3.4v6.3", "M6.9 11.9a2.1 2.1 0 1 1 4.2 0 2.1 2.1 0 0 1-4.2 0",
            "M7.4 6.1h3.2"),
    UNKNOWN: ("M4 6.4h10v5.2H4z", "M7 9h4"),
}

# Substrings that name a module type, most specific first — "microsd" has
# to be tested before "sd", and "displayport" before "port".
_MATCHES = (
    (MICROSD, ("microsd", "micro sd", "micro-sd")),
    (SD, ("sd card", "sd reader", " sd ")),
    (DISPLAYPORT, ("displayport", "display port", "dp alt", " dp ")),
    (HDMI, ("hdmi",)),
    (ETHERNET, ("ethernet", "rj45", "rj-45", "lan")),
    (AUDIO, ("audio", "headphone", "3.5mm", "jack")),
    (STORAGE, ("storage", "ssd", "nvme", " tb", "gb card")),
    (USB_A, ("usb-a", "usb a", "type-a", "type a")),
    (USB_C, ("usb-c", "usb c", "type-c", "type c")),
)

RE_CAPACITY = re.compile(r"\b(\d+(?:\.\d+)?)\s*(TB|GB)\b", re.IGNORECASE)


def classify(text):
    """Module type from whatever the CLI said about a bay.

    Returns UNKNOWN rather than guessing when nothing matches: framework_tool
    does not report per-bay module identity on every board, and a wrong icon
    is a worse answer than a neutral one.
    """
    body = " {} ".format((text or "").lower())
    for module_type, fragments in _MATCHES:
        if any(fragment in body for fragment in fragments):
            return module_type
    return UNKNOWN


def capacity(text):
    """`1 TB` / `256 GB` out of a storage card's description, or ''."""
    m = RE_CAPACITY.search(text or "")
    if not m:
        return ""
    size = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) \
        else m.group(1)
    return "{} {}".format(size, m.group(2).upper())


def paths_for(module_type):
    """The stroke paths for a type; the neutral module for anything else.

    Storage has no icon on purpose — callers check for it and draw the
    capacity text instead — so asking for its paths gets the neutral mark.
    """
    return ICONS.get(module_type, ICONS[UNKNOWN])
