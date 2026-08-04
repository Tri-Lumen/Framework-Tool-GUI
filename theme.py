"""
Design tokens and the Qt style sheet built from them.

One table, referenced by name — no colour literals anywhere in the UI code.
The design ships two appearances of the same palette: `acrylic`, where the
window surfaces are translucent and composited over whatever is behind the
window, and `opaque`, where they are flat. Only the surface colours differ;
text, accents and state colours are identical in both, so they live in one
table and the surfaces live in another keyed by appearance.

Like parsers.py this module imports nothing but the stdlib and never touches
a UI toolkit, so the whole token table and the generated style sheet are
unit-testable without a display.

Qt style sheets have no variables of their own, so `stylesheet()` renders a
template against the palette. That means a typo in a token name fails loudly
at render time (KeyError) instead of silently producing an unstyled widget,
which is what a hand-written sheet full of literals would do.
"""

ACRYLIC = "acrylic"
OPAQUE = "opaque"
APPEARANCES = (ACRYLIC, OPAQUE)

# Fonts. Vendored rather than assumed: see FONT_FILES in the packaging
# notes. The fallbacks are what the app looks like on a machine where the
# vendored files are missing, which is a real state, not a hypothetical.
FONT_SANS = "IBM Plex Sans"
FONT_MONO = "IBM Plex Mono"
FALLBACK_SANS = "Segoe UI, Cantarell, DejaVu Sans, sans-serif"
FALLBACK_MONO = "Consolas, DejaVu Sans Mono, monospace"

# Type scale (px). The UI reads these by name; nothing hardcodes a size.
FONT_SIZES = {
    "heading": 18,
    "device": 22,
    "metric": 26,
    "stat": 15,
    "body": 13,
    "cell": 12,
    "terminal": 12.5,
    "caption": 11,
    "section": 11,
    "badge": 11,
}

# Spacing scale. Layout code picks from this list and nothing else — a
# hardcoded pixel nudge to fix an alignment bug is a sign the layout is
# wrong, not that the scale is missing a value.
SPACE = (2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22)

# Fixed chrome metrics from the handoff.
RAIL_WIDTH = 52
RAIL_ITEM = (40, 38)
PANE_WIDTH = 190
BANNER_HEIGHT = 30
FALLBACK_STRIP_HEIGHT = 28
DRAWER_TABS_HEIGHT = 32
STATUS_HEIGHT = 24
GRABBER_HEIGHT = 6
GRABBER_HANDLE = (38, 2)
HERO_IMAGE = (420, 206)
METRIC_PANEL_WIDTH = 210
CONTENT_MARGINS = (22, 18, 22, 18)   # left, top, right, bottom
PANEL_PADDING = (16, 14)
CARD_PADDING = (11, 9)

# Window geometry. Below MIN_PANE_WIDTH the pane list collapses and the rail
# alone drives navigation; see navigation.py.
WINDOW_SIZE = (1180, 780)
MIN_WINDOW_SIZE = (980, 640)
PANE_COLLAPSE_WIDTH = 1040

# Drawer height bounds, persisted between launches.
DRAWER_MIN = 70
DRAWER_MAX = 460
DRAWER_DEFAULT = 200

# Colours that do not change with the appearance.
COMMON = {
    "text.primary": "#e9eaec",
    "text.body": "#dcdee1",
    "text.secondary": "#a5a8ad",
    "text.muted": "#9a9ea5",
    "text.faint": "#8b8f96",
    "accent": "#4f8cc9",
    "accent.bright": "#6ea8dc",
    "accent.text": "#c5dcf2",
    "accent.icon": "#a3cdec",
    "accent.fill": "rgba(79, 140, 201, 0.18)",
    "accent.selected": "rgba(79, 140, 201, 0.16)",
    "accent.rail": "rgba(79, 140, 201, 0.20)",
    "accent.link": "#8fb2d4",
    "accent.link.border": "#2f4257",
    "accent.row.fill": "rgba(79, 140, 201, 0.14)",
    "accent.row.border": "#3b5b7c",
    "ok": "#8ec48f",
    "ok.border": "#3c5c3d",
    "ok.bar": "#5fa860",
    "warn": "#d9b445",
    "warn.text": "#e6d5a0",
    "warn.text.dim": "#e0cd99",
    "warn.fill": "rgba(120, 88, 20, 0.18)",
    "warn.fill.strong": "rgba(120, 88, 20, 0.24)",
    "warn.border": "#4a3a15",
    "warn.button": "rgba(58, 53, 32, 0.70)",
    "warn.button.border": "#6b5c2a",
    "warn.button.text": "#e6d9a4",
    "warn.bar": "#c9873f",
    "danger.fill": "#5a2a24",
    "danger.border": "#9c4a3f",
    "danger.text": "#f3c9c2",
    "danger.subtle.fill": "rgba(90, 42, 36, 0.35)",
    "danger.subtle.border": "#7d3b34",
    "danger.subtle.text": "#e79a92",
    "danger.notice.fill": "rgba(90, 42, 36, 0.22)",
    "danger.notice.border": "#6d3a32",
    "danger.notice.text": "#e3bdb4",
    "button.border": "#43474f",
    "button.text": "#dfe1e4",
    "input.border": "#43474f",
    "track": "#33363c",
    "grabber": "#4a4e56",
    "icon": "#93979e",
    "terminal.out": "#b9bbc0",
    "chip.border": "#3a3e46",
}

# Surfaces, per appearance. Acrylic values are translucent on purpose: they
# only look right when something is composited behind them, which is why
# backdrop.py has to say the platform can do that before this set is used.
SURFACES = {
    ACRYLIC: {
        "window": "rgba(24, 26, 31, 0.72)",
        "rail": "rgba(20, 22, 26, 0.35)",
        "pane": "rgba(30, 32, 38, 0.30)",
        "drawer": "rgba(18, 20, 24, 0.55)",
        "status": "rgba(24, 25, 28, 0.50)",
        "card": "rgba(32, 34, 39, 0.45)",
        "panel": "rgba(32, 34, 39, 0.40)",
        "inset": "rgba(26, 28, 32, 0.45)",
        "hero": "rgba(26, 28, 32, 0.50)",
        "row": "rgba(32, 34, 39, 0.35)",
        "button": "rgba(42, 45, 52, 0.70)",
        "input": "rgba(20, 22, 26, 0.70)",
        "border": "#33363c",
        "border.subtle": "#33363c",
        "border.window": "#3a3e44",
    },
    OPAQUE: {
        "window": "#191b1f",
        "rail": "#16181b",
        "pane": "#1b1d21",
        "drawer": "#141619",
        "status": "#1c1d21",
        "card": "#212328",
        "panel": "#212328",
        "inset": "#1c1e22",
        "hero": "#1a1c20",
        "row": "#1e2024",
        "button": "#2a2d34",
        "input": "#16181b",
        "border": "#2b2e34",
        "border.subtle": "#2f3238",
        "border.window": "#32353a",
    },
}


def palette(appearance):
    """Every token for one appearance, surfaces merged over the common set.

    Raises ValueError rather than falling back to a default: an unknown
    appearance means a caller has invented a third mode, and silently
    rendering it as one of the two would hide that.
    """
    if appearance not in SURFACES:
        raise ValueError(
            "appearance must be one of {}, got {!r}".format(
                ", ".join(APPEARANCES), appearance))
    merged = dict(COMMON)
    merged.update(SURFACES[appearance])
    return merged


# The sheet is written against token names in `%(name)s` form and rendered
# by stylesheet(). Widget variants are selected on the `role` dynamic
# property so the Python side never assembles a colour string itself.
_TEMPLATE = """
* {
    font-family: '%(font.sans)s', %(font.fallback.sans)s;
    font-size: %(size.cell)spx;
    color: %(text.body)s;
}

QWidget#window, QDialog {
    background: %(window)s;
}

QLabel { background: transparent; }
QLabel[role="heading"] {
    font-size: %(size.heading)spx;
    font-weight: 600;
    color: %(text.primary)s;
}
QLabel[role="device"] {
    font-size: %(size.device)spx;
    font-weight: 600;
    letter-spacing: -0.2px;
    color: %(text.primary)s;
}
QLabel[role="sub"] {
    font-size: %(size.body)spx;
    color: %(text.secondary)s;
}
QLabel[role="intro"] {
    font-size: %(size.cell)spx;
    color: %(text.muted)s;
}
QLabel[role="caption"] {
    font-size: %(size.caption)spx;
    color: %(text.faint)s;
}
QLabel[role="section"] {
    font-size: %(size.section)spx;
    color: %(text.muted)s;
    letter-spacing: 1px;
}
QLabel[role="metric"] {
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.metric)spx;
    color: %(text.primary)s;
}
QLabel[role="stat"] {
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.stat)spx;
    color: %(text.primary)s;
}
QLabel[role="mono"] {
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.caption)spx;
    color: %(accent.link)s;
}
QLabel[role="cell"] {
    font-size: %(size.cell)spx;
    color: %(text.body)s;
}
QLabel[role="cellmono"] {
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.cell)spx;
    color: %(text.body)s;
}
QLabel[role="rowtitle"] {
    font-size: %(size.cell)spx;
    color: %(text.primary)s;
}
QLabel[role="name"] {
    font-size: %(size.body)spx;
    font-weight: 600;
    color: %(text.primary)s;
}
QLabel[role="unit"] {
    font-size: %(size.cell)spx;
    color: %(text.muted)s;
}
QLabel[role="badge"] {
    font-size: %(size.badge)spx;
    border-radius: 10px;
    padding: 2px 8px;
}
QLabel[badge="ok"] {
    color: %(ok)s;
    border: 1px solid %(ok.border)s;
}
QLabel[badge="warn"] {
    color: %(warn)s;
    background: %(warn.fill)s;
    border: 1px solid %(warn.border)s;
}
QLabel[badge="accent"] {
    color: %(accent.text)s;
    background: %(accent.fill)s;
    border: 1px solid %(accent)s;
}
QLabel[badge="danger"] {
    color: %(danger.subtle.text)s;
    background: %(danger.subtle.fill)s;
    border: 1px solid %(danger.subtle.border)s;
}
QLabel[badge="muted"] {
    color: %(text.faint)s;
    border: 1px solid %(border)s;
}
QLabel[role="chip"] {
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.caption)spx;
    color: %(text.secondary)s;
    border: 1px solid %(chip.border)s;
    border-radius: 3px;
    padding: 2px 8px;
}
QLabel[role="inlineNote"] {
    font-size: %(size.caption)spx;
    color: %(warn.text.dim)s;
    background: %(warn.fill)s;
    border: 1px solid %(warn.border)s;
    border-radius: 4px;
    padding: 3px 9px;
}
QLabel[role="warnText"] {
    font-size: %(size.cell)spx;
    color: %(warn.text.dim)s;
}
QLabel[role="dangerText"] {
    font-size: %(size.cell)spx;
    color: %(danger.notice.text)s;
}
QLabel[role="prompt"] {
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.terminal)spx;
    color: %(accent.bright)s;
}

QFrame#card {
    background: %(card)s;
    border: 1px solid %(border.subtle)s;
    border-radius: 5px;
}
QFrame#panel {
    background: %(panel)s;
    border: 1px solid %(border.subtle)s;
    border-radius: 6px;
}
QFrame#inset {
    background: %(inset)s;
    border: 1px solid %(border)s;
    border-radius: 4px;
}
QFrame#hero {
    background: %(hero)s;
    border: 1px solid %(border.subtle)s;
    border-radius: 6px;
}
QFrame#toolRow {
    background: %(row)s;
    border: 1px solid %(border)s;
    border-radius: 5px;
}
QFrame#toolRow[running="true"] {
    background: %(accent.row.fill)s;
    border: 1px solid %(accent.row.border)s;
}
QFrame#warnNotice {
    background: %(warn.fill)s;
    border: 1px solid %(warn.border)s;
    border-radius: 4px;
}
QFrame#dangerNotice {
    background: %(danger.notice.fill)s;
    border: 1px solid %(danger.notice.border)s;
    border-radius: 4px;
}
QFrame#rule {
    background: %(border)s;
    border: none;
}
QFrame#divider {
    background: %(border)s;
    border: none;
}

QPushButton {
    background: %(button)s;
    border: 1px solid %(button.border)s;
    border-radius: 4px;
    color: %(button.text)s;
    padding: 5px 11px;
    font-size: %(size.cell)spx;
}
QPushButton:hover { border-color: %(text.faint)s; }
QPushButton:disabled { color: %(text.faint)s; border-color: %(border)s; }
QPushButton[role="accent"] {
    background: %(accent.fill)s;
    border: 1px solid %(accent)s;
    color: %(accent.text)s;
}
QPushButton[role="primary"] {
    background: %(danger.fill)s;
    border: 1px solid %(danger.border)s;
    color: %(danger.text)s;
    padding: 8px 16px;
}
QPushButton[role="danger"] {
    background: %(danger.fill)s;
    border: 1px solid %(danger.border)s;
    color: %(danger.text)s;
}
QPushButton[role="dangerSubtle"] {
    background: %(danger.subtle.fill)s;
    border: 1px solid %(danger.subtle.border)s;
    color: %(danger.subtle.text)s;
    padding: 3px 9px;
    font-size: %(size.caption)spx;
}
QPushButton[role="link"] {
    background: transparent;
    border: 1px solid %(accent.link.border)s;
    border-radius: 3px;
    color: %(accent.link)s;
    padding: 3px 9px;
    font-size: %(size.caption)spx;
}
QPushButton[role="compact"], QPushButton[compact="true"] {
    padding: 4px 10px;
    font-size: %(size.caption)spx;
}
QPushButton[role="warn"] {
    background: %(warn.button)s;
    border: 1px solid %(warn.button.border)s;
    color: %(warn.button.text)s;
    padding: 3px 9px;
    font-size: %(size.caption)spx;
}
QPushButton[role="preset"] {
    padding: 4px 10px;
    font-size: %(size.cell)spx;
}
QPushButton[role="preset"][selected="true"] {
    background: %(accent.fill)s;
    border: 1px solid %(accent)s;
    color: %(accent.text)s;
}
QPushButton[role="drawerTool"] {
    background: transparent;
    border: none;
    color: %(text.faint)s;
    padding: 2px 6px;
    font-size: %(size.caption)spx;
}
QPushButton[role="drawerTool"]:hover { color: %(text.body)s; }
QPushButton[role="drawerTab"] {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: %(text.muted)s;
    padding: 0 12px;
    font-size: %(size.cell)spx;
}
QPushButton[role="drawerTab"][selected="true"] {
    color: %(text.primary)s;
    border-bottom: 2px solid %(accent.bright)s;
}
QPushButton[role="dismiss"] {
    background: transparent;
    border: none;
    color: %(text.faint)s;
    padding: 2px 8px;
}

QLineEdit, QComboBox, QSpinBox {
    background: %(input)s;
    border: 1px solid %(input.border)s;
    border-radius: 4px;
    color: %(text.primary)s;
    padding: 5px 9px;
    selection-background-color: %(accent)s;
}
QLineEdit[role="mono"], QComboBox[role="mono"] {
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
}
/* The big editable numbers on the Fans and CPU-limits panes. The design
   draws them as plain 26px mono values; making them the input as well is
   what stops the pane needing a second field beside every metric. */
QLineEdit[role="metric"] {
    background: transparent;
    border: none;
    border-bottom: 1px solid transparent;
    border-radius: 0;
    padding: 0;
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.metric)spx;
    color: %(text.primary)s;
}
QLineEdit[role="metric"]:focus { border-bottom: 1px solid %(accent)s; }
QComboBox QAbstractItemView {
    background: %(panel)s;
    border: 1px solid %(border)s;
    color: %(text.body)s;
    selection-background-color: %(accent.selected)s;
    selection-color: %(text.primary)s;
}
QSlider::groove:horizontal {
    height: 5px;
    background: %(track)s;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: %(accent)s;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: %(text.body)s;
    width: 10px;
    margin: -4px 0;
    border-radius: 5px;
}

QWidget#rail {
    background: %(rail)s;
    border-right: 1px solid %(border)s;
}
QWidget#pane {
    background: %(pane)s;
    border-right: 1px solid %(border)s;
}
QWidget#drawer {
    background: %(drawer)s;
    border-top: 1px solid %(border)s;
}
QWidget#statusBar {
    background: %(status)s;
    border-top: 1px solid %(border)s;
}
QWidget#banner {
    background: %(warn.fill.strong)s;
    border-bottom: 1px solid %(warn.border)s;
}
QWidget#fallbackStrip {
    background: %(status)s;
    border-bottom: 1px solid %(border)s;
}
QWidget#content { background: transparent; }
QWidget#drawerTabs { border-bottom: 1px solid %(border)s; }

QLabel[role="status"] {
    font-size: %(size.caption)spx;
    color: %(text.muted)s;
}
QLabel[role="bannerText"] {
    font-size: %(size.cell)spx;
    color: %(warn.text)s;
}

QTextEdit#terminal {
    background: transparent;
    border: none;
    font-family: '%(font.mono)s', %(font.fallback.mono)s;
    font-size: %(size.terminal)spx;
    color: %(terminal.out)s;
    selection-background-color: %(accent)s;
}

QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QScrollArea { border: none; }
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: %(track)s;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: %(grabber)s; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: %(track)s;
    border-radius: 5px;
    min-width: 24px;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QToolTip {
    background: %(panel)s;
    border: 1px solid %(border)s;
    color: %(text.body)s;
    padding: 4px 8px;
}

QMessageBox { background: %(window)s; }
QMessageBox QLabel { color: %(text.body)s; }
"""


def _render_values(appearance):
    values = palette(appearance)
    values["font.sans"] = FONT_SANS
    values["font.mono"] = FONT_MONO
    values["font.fallback.sans"] = FALLBACK_SANS
    values["font.fallback.mono"] = FALLBACK_MONO
    for name, size in FONT_SIZES.items():
        values["size." + name] = size
    return values


def stylesheet(appearance):
    """The whole application style sheet for one appearance."""
    return _TEMPLATE % _render_values(appearance)


_RGBA_PREFIX = "rgba("


def parse_colour(value):
    """A token's value as an (r, g, b, a) tuple, alpha 0-255.

    Both notations in the tables have to survive this: `#rrggbb` for the
    flat colours and `rgba(r, g, b, a)` for the translucent surfaces. Qt's
    painter API takes components, not CSS strings, so widgets that paint
    themselves come through here rather than parsing colours of their own.
    """
    text = (value or "").strip()
    if text.startswith(_RGBA_PREFIX) and text.endswith(")"):
        parts = [p.strip() for p in text[len(_RGBA_PREFIX):-1].split(",")]
        if len(parts) not in (3, 4):
            raise ValueError("malformed rgba colour: {!r}".format(value))
        red, green, blue = (int(float(p)) for p in parts[:3])
        alpha = int(round(float(parts[3]) * 255)) if len(parts) == 4 else 255
        return (red, green, blue, alpha)
    if text.startswith("#") and len(text) == 7:
        return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16), 255)
    raise ValueError("unrecognised colour: {!r}".format(value))


def bar_colour(fraction, warm_at=0.60):
    """Fill colour for a sensor/progress bar, by how full it is.

    One rule for every bar in the app so a 90%-full bar means the same thing
    on the Fans pane as it does on the Overview. The threshold is set where
    the design puts it: a 61 C package reads as hot, a 54 C one does not.
    """
    if fraction >= warm_at:
        return COMMON["warn.bar"]
    return COMMON["ok.bar"]
