"""
The navigation model, and the declarative content of the gated panes.

The redesigned app navigates with a 52px icon rail (five groups) and a 190px
pane list (the sections inside the selected group). That structure, and
everything the panes are gated on, is data — which keeps it testable without
a display and keeps `app.py` to layout and plumbing.

Rows here name a *key*; the UI maps the key to a method or a widget. That
indirection is deliberate: a tool list holding bound methods could only be
tested by constructing the app, which needs a display.

Gating follows the same fail-open rule as `parsers.detect_model`: a row with
`requires=None` is always shown, and a row whose capability key is missing
from `caps` is shown too, because `caps.get(key)` on a fail-open dict returns
the permissive default. Hiding a control that does apply is worse than
showing one that does not.
"""

# Rail icons are 18x18, 1.2px stroke, drawn from these path commands so the
# app carries no icon files and no icon dependency.
#
# They are drawn by `iconpaths.parse` + `widgets.icon_path`, not by Qt's SVG
# renderer. That renderer dropped most of every path on the Qt bundled with
# the packaged Windows build — four of these five icons came out as a bare
# diagonal stroke on a real machine while rendering perfectly under the Qt
# used in CI — and there is no way to test around a failure that only exists
# in the shipped build. Parsing the paths ourselves removes the variable.
#
# Every segment still carries an explicit command letter, and
# `tests/test_navigation.py` still checks that. It is a readability rule now
# rather than a workaround: the parser handles SVG's implicit repeats
# correctly, but an icon path is easier to edit when each command says what
# it is.
RAIL_GROUPS = (
    {
        "key": "overview",
        "label": "Overview",
        # A house: roof, then the body under it.
        "icon": ("M2.6 8.4L9 3.1L15.4 8.4"
                 "M4.7 9.9V15.1H13.3V9.9"),
        "items": (("Device", "overview"), ("Diagnostics", "tools")),
    },
    {
        "key": "hardware",
        "label": "Hardware",
        # Three sliders — three rails, each with its handle at a different
        # position. A plain three-line stack read as a menu button.
        "icon": ("M3 5.2H15M3 9H15M3 12.8H15"
                 "M6.6 3.9V6.5M11.4 7.7V10.3M8.2 11.5V14.1"),
        "items": (("Fans", "fans"), ("Ports & modules", "ports"),
                  ("Settings", "settings")),
    },
    {
        "key": "power",
        "label": "Power",
        # A bolt, closed so the outline joins cleanly at the top.
        "icon": "M10.4 2.6L5.1 9.7H8.7L7.6 15.4L12.9 8.3H9.3Z",
        "items": (("CPU limits", "power"),),
    },
    {
        "key": "software",
        "label": "Software",
        # A download arrow onto a baseline.
        "icon": ("M9 2.9V10.9M9 10.9L12.2 7.7M9 10.9L5.8 7.7"
                 "M3.4 14.6H14.6"),
        "items": (("Drivers", "drivers"), ("Setup", "setup")),
    },
    {
        "key": "console",
        "label": "Console",
        # A terminal: window outline, prompt chevron, cursor line.
        "icon": ("M2.7 3.9H15.3V14.1H2.7Z"
                 "M5.6 7.4L7.7 9.4L5.6 11.4M9.5 11.5H12.7"),
        "items": (("Custom command", "console"),),
    },
)

# The appearance toggle pinned to the bottom of the rail: a contrast circle
# — the outline, then the diameter that divides it.
APPEARANCE_ICON = ("M9 3.2A5.8 5.8 0 0 0 9 14.8A5.8 5.8 0 0 0 9 3.2",
                   "M9 3.2V14.8")

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
# The same workflows, in the same order, with the same tips. Each names the
# App method that runs it. How a tool reports progress is `mode`:
#
#   MODE_NONE   single-shot — no panel, straight to the drawer.
#   MODE_STEPS  a grid of `steps` cells, one per step. For a sequence whose
#               steps each take as long as they take (a run of commands),
#               where "3 of 6" is the only honest progress there is.
#   MODE_BAR    one animated progress bar. For a tool whose *length is known
#               before it starts* — a 30 s burst, six samples five seconds
#               apart. A countdown of discrete cells was the wrong picture
#               of a wall-clock wait.
#
# `params` are the numbers that used to be hard-coded in the tool body: how
# long the burst runs, how many samples to take, how long to dwell on each
# level. They are editable next to the Run button, so a 30 s burst can be a
# 90 s one without editing the source. Bounds are enforced in the UI.
#
# A MODE_BAR tool's total length is count x interval — see `duration_for`.
# `count` and `interval` are each either a literal or the name of a param.

MODE_NONE = None
MODE_STEPS = "steps"
MODE_BAR = "bar"


def _secs(key, label, default, low, high, step=1.0):
    return {"key": key, "label": label, "default": default,
            "min": low, "max": high, "step": step, "unit": "s",
            "decimals": 1 if step < 1 else 0}


def _count(key, label, default, low, high):
    return {"key": key, "label": label, "default": default,
            "min": low, "max": high, "step": 1, "unit": "x", "decimals": 0}


TOOLS = (
    {"key": "input_power", "label": "Power input wattage",
     "tip": "AC contract + measured input/charge power",
     "requires": "is_laptop", "mode": MODE_NONE, "steps": None},
    {"key": "fan_test", "label": "Fan speed test",
     "tip": "Ramp 0→100% duty, log RPM per step, restore auto",
     "requires": None, "mode": MODE_BAR, "steps": 5,
     "timing": {"count": 5, "interval": "dwell"},
     "params": (_secs("dwell", "Settle", 8, 2, 60),)},
    {"key": "fan_burst", "label": "Fan max burst",
     "tip": "100% duty for a set time (dust blow-out), then auto",
     "requires": None, "mode": MODE_BAR, "steps": 6, "danger": True,
     "timing": {"count": 1, "interval": "duration"},
     "params": (_secs("duration", "Run for", 30, 5, 300),)},
    {"key": "battery_health", "label": "Battery health report",
     "tip": "Full-charge vs design capacity, cycle count",
     "requires": "is_laptop", "mode": MODE_NONE, "steps": None},
    {"key": "charge_speed", "label": "Charging speed check",
     "tip": "Current charge rate in C and est. 0→100% time",
     "requires": "is_laptop", "mode": MODE_NONE, "steps": None},
    {"key": "thermal_monitor", "label": "Thermal monitor",
     "tip": "Repeated samples; min/max per sensor + fan RPM",
     "requires": None, "mode": MODE_BAR, "steps": 6,
     "timing": {"count": "samples", "interval": "interval"},
     "params": (_count("samples", "Samples", 6, 2, 240),
                _secs("interval", "Every", 5, 1, 60))},
    {"key": "port_map", "label": "Port power map",
     "tip": "Per-port role and negotiated wattage summary",
     "requires": None, "mode": MODE_NONE, "steps": None},
    {"key": "kblight_sweep", "label": "Keyboard backlight sweep",
     "tip": "0→100→0 in steps (visual check), restores previous",
     "requires": "is_laptop", "mode": MODE_BAR, "steps": 11,
     "timing": {"count": 11, "interval": "dwell"},
     "params": (_secs("dwell", "Hold", 0.5, 0.1, 10, step=0.1),)},
    {"key": "fpled_cycle", "label": "Fingerprint LED test",
     "tip": "Cycle high/medium/low/ultra-low, restore auto",
     "requires": "is_laptop", "mode": MODE_BAR, "steps": 4,
     "timing": {"count": 4, "interval": "dwell"},
     "params": (_secs("dwell", "Hold", 1.5, 0.2, 20, step=0.1),)},
    {"key": "ec_health", "label": "EC health check",
     "tip": "Self-test + EC firmware image/version",
     "requires": None, "mode": MODE_NONE, "steps": None},
    {"key": "security", "label": "Security check",
     "tip": "Privacy switches + chassis intrusion in one view",
     "requires": None, "mode": MODE_NONE, "steps": None},
    # Six commands whose individual durations are not knowable ahead of
    # time, so this one keeps the step grid: "4 of 6" is the real answer.
    {"key": "full_report", "label": "Full system report → file",
     "tip": "Versions, power, thermal, ports… saved as .txt",
     "requires": None, "mode": MODE_STEPS, "steps": 6},
)


def tools_for(caps):
    return _keep(TOOLS, caps)


def params_for(tool):
    """The overridable numbers a tool exposes, possibly none."""
    return tuple(tool.get("params") or ())


def defaults_for(tool):
    return {p["key"]: p["default"] for p in params_for(tool)}


def clamp_param(spec, value):
    """A param value coerced into its spec's bounds.

    Out-of-range input is pulled to the nearest bound rather than refused:
    these are dwell times and sample counts, and the bounds exist to stop a
    typo asking for a four-hour fan burst, not to police the user.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return spec["default"]
    number = max(spec["min"], min(spec["max"], number))
    return int(round(number)) if spec.get("decimals") == 0 else number


def _resolve(token, values):
    return values.get(token, 0) if isinstance(token, str) else token


def duration_for(tool, values=None):
    """How many seconds a MODE_BAR tool will run for, given its params.

    Returns 0 for a tool that is not time-bounded, which is the caller's
    signal to draw steps instead of a bar.
    """
    timing = tool.get("timing")
    if not timing:
        return 0
    merged = dict(defaults_for(tool))
    merged.update(values or {})
    count = _resolve(timing["count"], merged)
    interval = _resolve(timing["interval"], merged)
    return max(0.0, float(count) * float(interval))


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

# `parse` names the reader in `parsers` that turns a Get's output into the
# editor's value; None means the generic one. Two rows need their own,
# because framework_tool prints more than one number in the block:
# `--charge-limit` prints "Minimum 0%, Maximum 80%" (the generic reader took
# the 0), and both fingerprint reads print a level *and* a percentage under
# one heading (the generic reader took the percentage and handed it to a
# combo box that has no such entry, so the level never filled in at all).
#
# `auto` is the args that hand a setting back to the firmware. Where the CLI
# has an auto mode, the row gets a one-click Auto button rather than
# requiring the user to find "auto" in a list and press Set — and the two
# fingerprint rows share one, because `--fp-brightness` has no auto of its
# own and `--fp-led-level auto` is what releases both. A row whose setting
# genuinely has no automatic mode gets no button rather than a fake one.

SETTINGS_ROWS = (
    {"key": "charge_limit", "label": "Max charge limit",
     "note": "Held by the EC across reboots", "kind": "number",
     "unit": "%", "default": "80",
     "get": ("--charge-limit",), "set": ("--charge-limit",),
     "parse": "charge_limit", "auto": None,
     "requires": "is_laptop", "danger": False},
    {"key": "charge_rate", "label": "Charge rate limit",
     "note": "In C — 1C fills the pack in an hour", "kind": "number",
     "unit": "C", "default": "1",
     # The CLI sets this but has no read for it, so the row shows no Get
     # rather than one that runs something adjacent and calls it the answer.
     "get": None, "set": ("--charge-rate-limit",),
     "parse": None, "auto": None,
     "requires": "is_laptop", "danger": False},
    {"key": "kblight", "label": "Keyboard backlight",
     "note": "Percentage, 0 turns it off", "kind": "number",
     "unit": "%", "default": "20",
     "get": ("--kblight",), "set": ("--kblight",),
     "parse": None, "auto": None,
     "requires": "is_laptop", "danger": False},
    {"key": "fp_level", "label": "Fingerprint LED level",
     "note": "auto / high / medium / low / ultra-low", "kind": "choice",
     "choices": ("auto", "high", "medium", "low", "ultra-low"),
     "default": "auto",
     "get": ("--fp-led-level",), "set": ("--fp-led-level",),
     "parse": "fp_level", "auto": ("--fp-led-level", "auto"),
     "requires": "is_laptop", "danger": False},
    {"key": "fp_pct", "label": "Fingerprint brightness",
     "note": "Percentage override of the level", "kind": "number",
     "unit": "%", "default": "55",
     "get": ("--fp-brightness",), "set": ("--fp-brightness",),
     "parse": "fp_brightness", "auto": ("--fp-led-level", "auto"),
     "requires": "is_laptop", "danger": False},
    {"key": "deck_mode", "label": "Input deck mode",
     "note": "auto / on / off / reset — off disables the deck",
     "kind": "choice", "choices": ("auto", "on", "off", "reset"),
     "default": "auto",
     "get": ("--inputdeck",), "set": ("--inputdeck-mode",),
     "parse": None, "auto": ("--inputdeck-mode", "auto"),
     "requires": "is_laptop", "danger": True},
    {"key": "tablet_mode", "label": "Tablet mode override",
     "note": "auto / tablet / laptop", "kind": "choice",
     "choices": ("auto", "tablet", "laptop"), "default": "auto",
     "get": None, "set": ("--tablet-mode",),
     "parse": None, "auto": ("--tablet-mode", "auto"),
     "requires": "is_laptop12", "danger": False},
    {"key": "touchscreen", "label": "Touchscreen",
     "note": "Enable or disable the panel", "kind": "choice",
     "choices": ("true", "false"), "default": "true",
     "get": None, "set": ("--touchscreen-enable",),
     "parse": None, "auto": None,
     "requires": "has_touchscreen", "danger": False},
    {"key": "rgbkbd", "label": "RGB LEDs",
     "note": "Hex colour, e.g. FF0000 — applied to all eight zones",
     "kind": "rgb", "default": "FF0000",
     "get": None, "set": ("--rgbkbd",),
     "parse": None, "auto": None,
     "requires": "has_rgbkbd", "danger": False},
)


def settings_rows_for(caps):
    return _keep(SETTINGS_ROWS, caps)


# ---------- Settings presets ----------
#
# These were Diagnostics entries, which put them a long way from the rows
# they overwrite: running "Preset: Longevity" changed the charge limit and
# the charge rate on the Settings pane, from a different section, with no
# sign there that anything had moved. They live on the pane they affect
# now, above the rows they set, and the pane re-reads afterwards so the
# change is visible where it happened.
#
# `sets` maps a settings row key to the value the preset writes, which is
# what lets the UI fill those editors in rather than describing the change
# in prose.

SETTINGS_PRESETS = (
    {"key": "preset_longevity", "label": "Longevity",
     "tip": "Charge limit 80%, rate 0.8C — the daily-driver setting",
     "sets": {"charge_limit": "80", "charge_rate": "0.8"},
     "requires": "is_laptop"},
    {"key": "preset_full", "label": "Full charge",
     "tip": "Charge limit 100%, rate 1C — for a day out",
     "sets": {"charge_limit": "100", "charge_rate": "1"},
     "requires": "is_laptop"},
)


def presets_for(caps):
    return _keep(SETTINGS_PRESETS, caps)


# ---------- Custom command ----------

RECENT_SUGGESTIONS = ("--versions", "--power -vv", "--pdports", "--thermal",
                      "--privacy")
