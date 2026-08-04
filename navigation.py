"""
The navigation model, and the declarative content of the gated panes.

The redesigned app navigates with a 52px icon rail (five groups) and a 190px
pane list (the sections inside the selected group). That structure, and
everything the panes are gated on, is data — which keeps it testable without
a display and keeps `framework_gui.py` to layout and plumbing.

Rows here name a *key*; the UI maps the key to a method or a widget. That
indirection is deliberate: a tool list holding bound methods could only be
tested by constructing the app, which needs a display.

Gating follows the same fail-open rule as `parsers.detect_model`: a row with
`requires=None` is always shown, and a row whose capability key is missing
from `caps` is shown too, because `caps.get(key)` on a fail-open dict returns
the permissive default. Hiding a control that does apply is worse than
showing one that does not.
"""

# Rail icons are 18x18, 1.2px stroke, drawn from these SVG path commands so
# the app carries no icon files and no icon dependency.
RAIL_GROUPS = (
    {
        "key": "overview",
        "label": "Overview",
        "icon": "M2.5 8 9 3l6.5 5v6.5a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1z",
        "items": (("Device", "overview"), ("Diagnostics", "tools")),
    },
    {
        "key": "hardware",
        "label": "Hardware",
        "icon": "M3 5h12M3 9h12M3 13h12",
        "items": (("Fans", "fans"), ("Ports & modules", "ports"),
                  ("Settings", "settings")),
    },
    {
        "key": "power",
        "label": "Power",
        "icon": "M10 2 5 10h3.5L8 16l5-8H9.5z",
        "items": (("CPU limits", "power"),),
    },
    {
        "key": "software",
        "label": "Software",
        "icon": "M9 2v9m0 0 3.5-3.5M9 11 5.5 7.5M3 14h12",
        "items": (("Drivers", "drivers"), ("Setup", "setup")),
    },
    {
        "key": "console",
        "label": "Console",
        "icon": "M5 7.5 7 9.5 5 11.5M9 11.5h4",
        "items": (("Custom command", "console"),),
    },
)

# The appearance toggle pinned to the bottom of the rail.
APPEARANCE_ICON = ("M9 3a6 6 0 0 0 0 12zM9 3a6 6 0 0 1 0 12", )

SECTIONS = tuple(section for group in RAIL_GROUPS
                 for _label, section in group["items"])

# Shown in the window title after "Framework System GUI — ". The Overview
# uses the detected device name instead, which is why it is not here.
SECTION_TITLES = {
    "tools": "Diagnostics",
    "fans": "Fans",
    "ports": "Ports & modules",
    "settings": "Settings",
    "power": "Power",
    "drivers": "Drivers",
    "setup": "Setup",
    "console": "Console",
}

APP_NAME = "Framework System GUI"


def group_for_section(section):
    """The rail group a section belongs to, or the first group if unknown."""
    for group in RAIL_GROUPS:
        for _label, key in group["items"]:
            if key == section:
                return group
    return RAIL_GROUPS[0]


def first_section(rail_key):
    """The section a rail click selects — the group's first pane item."""
    for group in RAIL_GROUPS:
        if group["key"] == rail_key:
            return group["items"][0][1]
    return RAIL_GROUPS[0]["items"][0][1]


def window_title(section, model=""):
    """`Framework System GUI — <section>`, or the device name on Overview."""
    if section == "overview":
        suffix = model or "Overview"
    else:
        suffix = SECTION_TITLES.get(section, section)
    return "{} — {}".format(APP_NAME, suffix)


def _keep(rows, caps):
    return [row for row in rows
            if row["requires"] is None or caps.get(row["requires"], True)]


# ---------- Diagnostics ----------
#
# The same fourteen workflows, in the same order, with the same tips. Each
# names the App method that runs it. `steps` is how many progress cells the
# detail panel draws; None means single-shot — no panel, straight to the
# drawer.

TOOLS = (
    {"key": "input_power", "label": "Power input wattage",
     "tip": "AC contract + measured input/charge power",
     "requires": "is_laptop", "steps": None},
    {"key": "fan_test", "label": "Fan speed test",
     "tip": "Ramp 0→100% duty, log RPM per step, restore auto",
     "requires": None, "steps": 5},
    {"key": "fan_burst", "label": "Fan max burst (30 s)",
     "tip": "100% duty for 30 s (dust blow-out), then auto",
     "requires": None, "steps": 6, "danger": True},
    {"key": "battery_health", "label": "Battery health report",
     "tip": "Full-charge vs design capacity, cycle count",
     "requires": "is_laptop", "steps": None},
    {"key": "charge_speed", "label": "Charging speed check",
     "tip": "Current charge rate in C and est. 0→100% time",
     "requires": "is_laptop", "steps": None},
    {"key": "thermal_monitor", "label": "Thermal monitor (30 s)",
     "tip": "6 samples; min/max per sensor + fan RPM",
     "requires": None, "steps": 6},
    {"key": "port_map", "label": "Port power map",
     "tip": "Per-port role and negotiated wattage summary",
     "requires": None, "steps": None},
    {"key": "kblight_sweep", "label": "Keyboard backlight sweep",
     "tip": "0→100→0 in steps (visual check), restores 0",
     "requires": "is_laptop", "steps": 11},
    {"key": "fpled_cycle", "label": "Fingerprint LED test",
     "tip": "Cycle high/medium/low/ultra-low, restore auto",
     "requires": "is_laptop", "steps": 4},
    {"key": "ec_health", "label": "EC health check",
     "tip": "Self-test + EC firmware image/version",
     "requires": None, "steps": None},
    {"key": "security", "label": "Security check",
     "tip": "Privacy switches + chassis intrusion in one view",
     "requires": None, "steps": None},
    {"key": "full_report", "label": "Full system report → file",
     "tip": "Versions, power, thermal, ports… saved as .txt",
     "requires": None, "steps": 6},
    {"key": "preset_longevity", "label": "Preset: Longevity (limit 80%)",
     "tip": "Charge limit 80%, rate 0.8C",
     "requires": "is_laptop", "steps": None},
    {"key": "preset_full", "label": "Preset: Full charge (100%)",
     "tip": "Charge limit 100%, rate 1C",
     "requires": "is_laptop", "steps": None},
)


def tools_for(caps):
    return _keep(TOOLS, caps)


# ---------- Ports & modules ----------

PORT_QUERIES = (
    {"key": "pdports", "label": "USB-C PD ports", "args": ("--pdports",),
     "requires": None},
    {"key": "pd_info", "label": "PD controllers", "args": ("--pd-info",),
     "requires": None},
    {"key": "dp_hdmi", "label": "DP / HDMI card", "args": ("--dp-hdmi-info",),
     "requires": None},
    {"key": "audio", "label": "Audio card", "args": ("--audio-card-info",),
     "requires": None},
    {"key": "inputdeck", "label": "Input deck", "args": ("--inputdeck",),
     "requires": "is_laptop"},
    {"key": "expansion_bay", "label": "Expansion bay",
     "args": ("--expansion-bay",), "requires": "has_expansion_bay"},
    {"key": "intrusion", "label": "Intrusion switch", "args": ("--intrusion",),
     "requires": None},
    {"key": "privacy", "label": "Privacy switches", "args": ("--privacy",),
     "requires": "is_laptop"},
    {"key": "stylus", "label": "Stylus battery", "args": ("--stylus-battery",),
     "requires": "has_stylus"},
)


def port_queries_for(caps):
    return _keep(PORT_QUERIES, caps)


# ---------- Settings ----------
#
# `kind` picks the editor: "number" a text field, "choice" a combo box,
# "rgb" the hex field with its own two buttons. `get` is the args that read
# the current value back; None means the CLI has no read for it, and the
# row shows no Get button rather than one that runs something adjacent and
# claims it is the answer.
#
# `danger` marks a Set that can leave the machine unusable — the input deck
# carries the keyboard and trackpad, so switching it off is a destructive
# act and gets the destructive treatment, including a confirmation.

SETTINGS_ROWS = (
    {"key": "charge_limit", "label": "Max charge limit",
     "note": "Held by the EC across reboots", "kind": "number",
     "unit": "%", "default": "80",
     "get": ("--charge-limit",), "set": ("--charge-limit",),
     "requires": "is_laptop", "danger": False},
    {"key": "charge_rate", "label": "Charge rate limit",
     "note": "In C — 1C fills the pack in an hour", "kind": "number",
     "unit": "C", "default": "1",
     "get": None, "set": ("--charge-rate-limit",),
     "requires": "is_laptop", "danger": False},
    {"key": "kblight", "label": "Keyboard backlight",
     "note": "Percentage, 0 turns it off", "kind": "number",
     "unit": "%", "default": "20",
     "get": ("--kblight",), "set": ("--kblight",),
     "requires": "is_laptop", "danger": False},
    {"key": "fp_level", "label": "Fingerprint LED level",
     "note": "auto / high / medium / low / ultra-low", "kind": "choice",
     "choices": ("auto", "high", "medium", "low", "ultra-low"),
     "default": "auto",
     "get": ("--fp-brightness",), "set": ("--fp-led-level",),
     "requires": "is_laptop", "danger": False},
    {"key": "fp_pct", "label": "Fingerprint brightness",
     "note": "Percentage override of the level", "kind": "number",
     "unit": "%", "default": "55",
     "get": None, "set": ("--fp-brightness",),
     "requires": "is_laptop", "danger": False},
    {"key": "deck_mode", "label": "Input deck mode",
     "note": "auto / on / off / reset — off disables the deck",
     "kind": "choice", "choices": ("auto", "on", "off", "reset"),
     "default": "auto",
     "get": ("--inputdeck",), "set": ("--inputdeck-mode",),
     "requires": "is_laptop", "danger": True},
    {"key": "tablet_mode", "label": "Tablet mode override",
     "note": "auto / tablet / laptop", "kind": "choice",
     "choices": ("auto", "tablet", "laptop"), "default": "auto",
     "get": None, "set": ("--tablet-mode",),
     "requires": "is_laptop12", "danger": False},
    {"key": "touchscreen", "label": "Touchscreen",
     "note": "Enable or disable the panel", "kind": "choice",
     "choices": ("true", "false"), "default": "true",
     "get": None, "set": ("--touchscreen-enable",),
     "requires": "has_touchscreen", "danger": False},
    {"key": "rgbkbd", "label": "RGB LEDs",
     "note": "Hex colour, e.g. FF0000 — applied to all eight zones",
     "kind": "rgb", "default": "FF0000",
     "get": None, "set": ("--rgbkbd",),
     "requires": "has_rgbkbd", "danger": False},
)


def settings_rows_for(caps):
    return _keep(SETTINGS_ROWS, caps)


# ---------- Custom command ----------

RECENT_SUGGESTIONS = ("--versions", "--power -vv", "--pdports", "--thermal",
                      "--privacy")
