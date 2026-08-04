"""
The reusable pieces of the redesigned UI.

Everything here is generic: a card, a panel, a bar, a badge, a rail button.
None of it knows what a fan or a charge limit is — `framework_gui.py` builds
the panes out of these. Colours come from `theme` by token name; there is no
colour literal in this file, which is what keeps the two appearances honest.

Widgets that Qt style sheets cannot express (a progress bar with a
threshold colour, the rail's 2px selection bar, the chassis line drawing)
paint themselves; everything else is styled by the sheet and carries only a
`role` property.
"""

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import module_icons
import theme

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
    'viewBox="0 0 18 18" fill="none" stroke="{colour}" stroke-width="1.2" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


def stroke_pixmap(path_d, colour, size=18, ratio=1.0):
    """Render one stroked SVG path into a pixmap at the given colour."""
    body = "".join('<path d="{}"/>'.format(d) for d in _as_paths(path_d))
    svg = _SVG.format(size=size, colour=colour, body=body).encode("utf-8")
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    QSvgRenderer(svg).render(painter)
    painter.end()
    return pixmap


def stroke_icon(path_d, colour, size=18):
    return QIcon(stroke_pixmap(path_d, colour, size))


def _as_paths(path_d):
    return (path_d,) if isinstance(path_d, str) else tuple(path_d)


# The appearance the self-painting widgets should sample surfaces from.
# The style sheet carries this for everything Qt styles; widgets that paint
# themselves have no sheet to read, so the app sets it here when the
# appearance changes and they pick it up on their next repaint.
_appearance = theme.OPAQUE
_palette = theme.palette(_appearance)


def set_appearance(appearance):
    global _appearance, _palette
    _appearance = appearance
    _palette = theme.palette(appearance)


def colour(token):
    """A token's CSS value, for the appearance currently in force."""
    return _palette[token]


def qcolour(token):
    """A token as a QColor, translucent surfaces included."""
    return QColor(*theme.parse_colour(colour(token)))


def label(text, role, parent=None):
    """A QLabel carrying one of the sheet's type roles."""
    widget = QLabel(text, parent)
    widget.setProperty("role", role)
    return widget


def section_label(text, parent=None):
    return label(text.upper(), "section", parent)


def rule(parent=None):
    """A 1px horizontal divider."""
    line = QFrame(parent)
    line.setObjectName("rule")
    line.setFixedHeight(1)
    line.setFrameShape(QFrame.NoFrame)
    return line


def restyle(widget):
    """Re-apply the style sheet to a widget whose properties just changed.

    Qt does not re-evaluate property selectors on its own; without this a
    row that becomes the running one keeps its old colours.
    """
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class Panel(QFrame):
    """A bordered section container — the design's 6px-radius panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        pad_x, pad_y = theme.PANEL_PADDING
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        self.body.setSpacing(theme.SPACE[3])


class Card(QFrame):
    """A stat card: 11px muted label over a 15px mono value."""

    def __init__(self, name, value="—", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        pad_x, pad_y = theme.CARD_PADDING
        box = QVBoxLayout(self)
        box.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        box.setSpacing(theme.SPACE[0])
        self.name = label(name, "caption", self)
        self.value = label(value, "stat", self)
        box.addWidget(self.name)
        box.addWidget(self.value)

    def set_value(self, text):
        self.value.setText(text)


class Bar(QWidget):
    """A rounded progress/sensor bar with a threshold-coloured fill."""

    def __init__(self, height=5, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._fraction = 0.0
        self._colour = colour("accent")

    def set_fraction(self, fraction, fill=None):
        self._fraction = max(0.0, min(1.0, float(fraction or 0.0)))
        self._colour = fill or theme.bar_colour(self._fraction)
        self.update()

    def set_accent(self, fraction):
        self.set_fraction(fraction, colour("accent"))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        radius = self.height() / 2.0
        track = QRectF(0, 0, self.width(), self.height())
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolour("track"))
        painter.drawRoundedRect(track, radius, radius)
        if self._fraction > 0:
            fill = QRectF(0, 0, self.width() * self._fraction, self.height())
            painter.setBrush(QColor(*theme.parse_colour(self._colour)))
            painter.drawRoundedRect(fill, radius, radius)
        painter.end()


class Badge(QLabel):
    """A pill: `detected`, `Backend: RyzenAdj`, `not found`."""

    def __init__(self, text, variant="ok", parent=None):
        super().__init__(text, parent)
        self.setProperty("role", "badge")
        self.setProperty("badge", variant)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set_variant(self, variant):
        self.setProperty("badge", variant)
        restyle(self)


class ModuleIcon(QWidget):
    """The mark on an expansion-bay row.

    Two shapes, because the modules divide into two: everything with a
    recognisable port face gets its stroke icon from `module_icons`, tinted
    by the port's state; a storage card gets its capacity in a bordered box,
    because one storage card looks exactly like another and the number is
    the only thing worth showing.
    """

    SIZE = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.SIZE)
        self.setMinimumWidth(self.SIZE)
        self._type = module_icons.UNKNOWN
        self._capacity = ""
        self._token = "icon"
        self._cache = {}

    def set_module(self, module_type, capacity="", token="icon"):
        self._type = module_type
        self._capacity = capacity
        self._token = token
        self._cache = {}
        self.setFixedWidth(self._width())
        self.updateGeometry()
        self.update()

    def _is_text(self):
        return self._type == module_icons.STORAGE and bool(self._capacity)

    def _width(self):
        if not self._is_text():
            return self.SIZE
        metrics = self.fontMetrics()
        return metrics.horizontalAdvance(self._capacity) + 14

    def sizeHint(self):
        return QSize(self._width(), self.SIZE)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._is_text():
            rect = QRectF(0.5, 1.5, self.width() - 1, self.height() - 3)
            painter.setPen(qcolour(self._token))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 3, 3)
            font = painter.font()
            font.setPixelSize(theme.FONT_SIZES["caption"])
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, self._capacity)
        else:
            if self._token not in self._cache:
                ratio = self.devicePixelRatioF() or 1.0
                self._cache[self._token] = stroke_pixmap(
                    module_icons.paths_for(self._type), colour(self._token),
                    18, ratio)
            painter.drawPixmap(1, 1, self._cache[self._token])
        painter.end()


class RailButton(QAbstractButton):
    """One of the five rail groups: 40x38, 2px accent bar when selected."""

    def __init__(self, group, parent=None):
        super().__init__(parent)
        self.group_key = group["key"]
        self.setToolTip(group["label"])
        self.setCheckable(True)
        self.setCursor(Qt.ArrowCursor)
        self.setFixedSize(*theme.RAIL_ITEM)
        self._icon = group["icon"]
        self._cache = {}

    def _pixmap(self, active):
        token = "accent.icon" if active else "icon"
        if token not in self._cache:
            ratio = self.devicePixelRatioF() or 1.0
            self._cache[token] = stroke_pixmap(self._icon, colour(token),
                                               18, ratio)
        return self._cache[token]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        active = self.isChecked()
        if active:
            painter.fillRect(self.rect(), qcolour("accent.rail"))
            painter.fillRect(0, 0, 2, self.height(),
                             qcolour("accent.bright"))
        pixmap = self._pixmap(active)
        x = (self.width() - 18) // 2
        y = (self.height() - 18) // 2
        painter.drawPixmap(x, y, pixmap)
        painter.end()

    def sizeHint(self):
        return QSize(*theme.RAIL_ITEM)


class PaneItem(QAbstractButton):
    """A row in the 190px pane list."""

    HEIGHT = 26

    def __init__(self, text, section, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.section = section
        self.setCheckable(True)
        self.setCursor(Qt.ArrowCursor)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        active = self.isChecked()
        if active:
            painter.fillRect(self.rect(), qcolour("accent.selected"))
            painter.fillRect(0, 0, 2, self.height(),
                             qcolour("accent.bright"))
        font = painter.font()
        font.setPixelSize(theme.FONT_SIZES["body"])
        painter.setFont(font)
        painter.setPen(QColor(colour("text.primary" if active
                                     else "text.secondary")))
        painter.drawText(self.rect().adjusted(12, 0, -8, 0),
                         Qt.AlignVCenter | Qt.AlignLeft, self.text())
        painter.end()


class Segmented(QWidget):
    """The two-option Acrylic | Opaque control in the pane footer."""

    chosen = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self._options = tuple(options)
        self._value = self._options[0]
        self._enabled_choices = True

    def set_value(self, value):
        if value in self._options:
            self._value = value
            self.update()

    def set_choices_enabled(self, enabled):
        self._enabled_choices = bool(enabled)
        self.update()

    def mousePressEvent(self, event):
        if not self._enabled_choices:
            return
        index = int(event.position().x() // max(1, self.width() //
                                                len(self._options)))
        index = max(0, min(len(self._options) - 1, index))
        self.chosen.emit(self._options[index])

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(1.0 if self._enabled_choices else 0.45)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        painter.setClipPath(path)
        width = self.width() / len(self._options)
        font = painter.font()
        font.setPixelSize(theme.FONT_SIZES["caption"])
        painter.setFont(font)
        for i, option in enumerate(self._options):
            cell = QRectF(i * width, 0, width, self.height())
            active = option == self._value
            if active:
                painter.fillRect(cell, qcolour("accent.rail"))
            if i:
                painter.setPen(qcolour("button.border"))
                painter.drawLine(cell.topLeft(), cell.bottomLeft())
            painter.setPen(QColor(colour("accent.text" if active
                                         else "text.faint")))
            painter.drawText(cell, Qt.AlignCenter, option.capitalize())
        painter.setClipping(False)
        painter.setPen(qcolour("button.border"))
        painter.drawPath(path)
        painter.end()


class Spinner(QWidget):
    """The 10px running indicator inside the Diagnostics progress badge.

    The timer runs only while a tool is running and is stopped the moment it
    finishes — this is a repaint tick, not a background worker, and nothing
    is left ticking when the app is idle.
    """

    PERIOD_MS = 1100
    STEPS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        if not self._timer.isActive():
            self._timer.start(self.PERIOD_MS // self.STEPS)

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._angle = (self._angle + 360 // self.STEPS) % 360
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        pen = painter.pen()
        pen.setWidthF(1.6)
        pen.setColor(qcolour("warn.border"))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)
        pen.setColor(qcolour("warn"))
        painter.setPen(pen)
        painter.drawArc(rect, -self._angle * 16, 90 * 16)
        painter.end()


class Grabber(QWidget):
    """The 6px drawer resize handle. Emits the new height as it is dragged."""

    dragged = Signal(int)

    def __init__(self, height_of, parent=None):
        super().__init__(parent)
        self.setFixedHeight(theme.GRABBER_HEIGHT)
        self.setCursor(Qt.SizeVerCursor)
        self._height_of = height_of
        self._origin = None
        self._start = 0

    def mousePressEvent(self, event):
        self._origin = event.globalPosition().y()
        self._start = self._height_of()

    def mouseMoveEvent(self, event):
        if self._origin is None:
            return
        delta = self._origin - event.globalPosition().y()
        self.dragged.emit(int(self._start + delta))

    def mouseReleaseEvent(self, _event):
        self._origin = None

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(0, 0, self.width(), 1, qcolour("track"))
        handle_w, handle_h = theme.GRABBER_HANDLE
        x = (self.width() - handle_w) / 2.0
        y = (self.height() - handle_h) / 2.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolour("grabber"))
        painter.drawRoundedRect(QRectF(x, y, handle_w, handle_h), 1, 1)
        painter.end()


class ChassisDiagram(QWidget):
    """The 300x112 line drawing of the chassis with its four bays.

    Bay outline colour carries the port's state, which is the only reason
    the drawing is here at all: it is a legend for the module rows beside
    it, not decoration.
    """

    # x, y of each bay, in the order the design lists them: left front,
    # left rear, right front, right rear.
    BAYS = ((8, 24), (8, 54), (280, 24), (280, 54))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 112)
        self._states = ["idle"] * 4

    def set_states(self, states):
        """states: one of 'sink', 'source', 'idle', 'empty' per bay."""
        self._states = (list(states) + ["empty"] * 4)[:4]
        self.update()

    def _bay_colour(self, state):
        return {
            "sink": colour("accent.bright"),
            "source": colour("ok.bar"),
            "idle": colour("warn"),
        }.get(state, colour("icon"))

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(Qt.NoBrush)
        pen = painter.pen()
        pen.setColor(qcolour("icon"))
        pen.setWidthF(1.3)
        painter.setPen(pen)
        painter.drawRoundedRect(QRectF(20, 14, 260, 72), 6, 6)
        painter.drawLine(6, 98, 294, 98)
        pen.setColor(qcolour("track"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(QRectF(34, 26, 232, 46), 3, 3)
        for (x, y), state in zip(self.BAYS, self._states):
            pen.setColor(QColor(self._bay_colour(state)))
            pen.setWidthF(1.1)
            painter.setPen(pen)
            painter.setBrush(qcolour("inset") if state != "empty"
                             else Qt.NoBrush)
            painter.drawRoundedRect(QRectF(x, y, 12, 22), 2, 2)
        painter.end()


class MetricPanel(Panel):
    """A 210px metric tile: caption, big mono value + unit, bar, actions.

    `editable=True` swaps the value label for a field styled the same way.
    The design draws these numbers once and puts a Set button under them;
    making the number itself the input is what keeps the tile to one number
    instead of a value and a separate box that must agree with it.
    """

    def __init__(self, name, unit="", editable=False, parent=None):
        super().__init__(parent)
        self.setFixedWidth(theme.METRIC_PANEL_WIDTH)
        self.body.setSpacing(theme.SPACE[3])
        self.body.addWidget(label(name, "caption", self))

        value_row = QHBoxLayout()
        value_row.setSpacing(theme.SPACE[2])
        value_row.setContentsMargins(0, 0, 0, 0)
        self.field = None
        self.value = None
        if editable:
            self.field = QLineEdit(self)
            self.field.setProperty("role", "metric")
            self.field.setMaximumWidth(120)
            value_row.addWidget(self.field)
        else:
            self.value = label("—", "metric", self)
            value_row.addWidget(self.value)
        self.unit = label(unit, "unit", self)
        value_row.addWidget(self.unit, 0, Qt.AlignBottom)
        value_row.addStretch(1)
        self.body.addLayout(value_row)

        self.bar = Bar(5, self)
        self.body.addWidget(self.bar)
        self.actions = QVBoxLayout()
        self.actions.setSpacing(theme.SPACE[2])
        self.body.addLayout(self.actions)

    def set_value(self, text, fraction=None, accent=True):
        target = self.value if self.value is not None else self.field
        target.setText(text)
        if fraction is None:
            self.bar.set_fraction(0)
        elif accent:
            self.bar.set_accent(fraction)
        else:
            self.bar.set_fraction(fraction)

    def add_action(self, button):
        self.actions.addWidget(button)
        return button


class SensorRow(QWidget):
    """80px name, a bar, a 46px right-aligned mono value."""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SPACE[4])
        # Wider than the design's 80px: real sensor names off a Framework
        # board are `F75303_Local`, not `CPU`, and clipping them would make
        # two rows indistinguishable.
        name_label = label(name, "cell", self)
        name_label.setFixedWidth(110)
        row.addWidget(name_label)
        self.bar = Bar(5, self)
        row.addWidget(self.bar, 1)
        self.value = label("—", "cellmono", self)
        self.value.setFixedWidth(46)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self.value)

    def set_reading(self, text, fraction):
        self.value.setText(text)
        self.bar.set_fraction(fraction)


class ImageSlot(QFrame):
    """The 420x206 device image, with the text fallback the design asks for.

    The app ships no device photography — see CLAUDE.md — so this is the
    fallback state until licensed images exist. Call `set_image()` with a
    QPixmap once there is one.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("hero")
        self.setFixedSize(*theme.HERO_IMAGE)
        box = QVBoxLayout(self)
        box.setContentsMargins(theme.SPACE[6], theme.SPACE[6],
                               theme.SPACE[6], theme.SPACE[6])
        box.addStretch(1)
        self.caption = label("", "caption", self)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setWordWrap(True)
        box.addWidget(self.caption)
        box.addStretch(1)
        self._pixmap = None

    def set_device(self, name):
        self.caption.setText(
            "No photograph bundled for {}\n"
            "(device imagery is not shipped — see CLAUDE.md)".format(
                name or "this device"))

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self.caption.setVisible(pixmap is None)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()
