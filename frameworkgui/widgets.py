"""
The reusable pieces of the redesigned UI.

Everything here is generic: a card, a panel, a bar, a badge, a rail button.
None of it knows what a fan or a charge limit is — `app.py` builds
the panes out of these. Colours come from `theme` by token name; there is no
colour literal in this file, which is what keeps the two appearances honest.

Widgets that Qt style sheets cannot express (a progress bar with a
threshold colour, the rail's 2px selection bar, the chassis line drawing)
paint themselves; everything else is styled by the sheet and carries only a
`role` property.
"""

import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
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

from . import device_images, iconpaths, module_icons, theme

# Every icon is drawn in this box and scaled from it.
ICON_BOX = 18.0
ICON_STROKE = 1.2


def icon_path(path_d):
    """One or more path strings as a single QPainterPath in the 18x18 box.

    The path language is parsed by `iconpaths`, not by Qt: QSvgRenderer
    dropped most of every path on the Qt in the packaged Windows build,
    which is what made four of the five rail icons render as a bare
    diagonal stroke on a real machine. See that module's docstring.
    """
    painter_path = QPainterPath()
    for one in _as_paths(path_d):
        for op in iconpaths.parse(one):
            if op[0] == "move":
                painter_path.moveTo(op[1], op[2])
            elif op[0] == "line":
                painter_path.lineTo(op[1], op[2])
            elif op[0] == "cubic":
                painter_path.cubicTo(*op[1:])
            else:
                painter_path.closeSubpath()
    return painter_path


def stroke_pixmap(path_d, colour, size=18, ratio=1.0):
    """Render one stroked icon path into a pixmap at the given colour."""
    pixmap = QPixmap(max(int(round(size * ratio)), 1),
                     max(int(round(size * ratio)), 1))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(size / ICON_BOX, size / ICON_BOX)
    pen = QPen(QColor(colour), ICON_STROKE)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(icon_path(path_d))
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


class TimedBar(QWidget):
    """A determinate progress bar for a tool whose length is known up front.

    A thirty-second fan burst is a wall-clock wait, not a sequence of
    stages, and drawing it as six countdown cells said "6 steps" when the
    honest answer was "30 seconds". This fills smoothly against elapsed
    time, so the picture matches what is actually happening.

    Animation is deliberate and twofold: the fill advances every tick rather
    than once per step, and a soft highlight travels along the filled part
    so the bar reads as *running* even while the fill barely moves. Both
    stop dead when the tool does — the timer is a repaint tick, never a
    background worker, and nothing ticks while the app is idle.

    `elapsed()` is injectable-free but monotonic: a wall-clock change part
    way through a burst must not make the bar jump.
    """

    HEIGHT = 8
    TICK_MS = 40
    SHEEN_PERIOD_MS = 1600
    SHEEN_WIDTH = 0.18          # fraction of the full track

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._duration = 0.0
        self._started = None
        self._fraction = 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self, duration):
        self._duration = max(0.0, float(duration or 0.0))
        self._started = time.monotonic()
        self._fraction = 0.0
        self._phase = 0.0
        if not self._timer.isActive():
            self._timer.start(self.TICK_MS)
        self.update()

    def stop(self, complete=True):
        """Freeze the bar — full if the tool ran to the end, where it is if
        it was cancelled, so a cancelled run does not read as a finished one.
        """
        self._timer.stop()
        if complete:
            self._fraction = 1.0
        self._started = None
        self.update()

    def elapsed(self):
        return 0.0 if self._started is None else time.monotonic() - self._started

    def remaining(self):
        return max(0.0, self._duration - self.elapsed())

    def fraction(self):
        return self._fraction

    def _tick(self):
        if self._duration > 0 and self._started is not None:
            self._fraction = min(1.0, self.elapsed() / self._duration)
        self._phase = (self._phase
                       + self.TICK_MS / float(self.SHEEN_PERIOD_MS)) % 1.0
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        radius = self.height() / 2.0
        width = self.width()
        painter.setPen(Qt.NoPen)
        painter.setBrush(qcolour("track"))
        painter.drawRoundedRect(QRectF(0, 0, width, self.height()),
                                radius, radius)
        if self._fraction <= 0:
            painter.end()
            return
        filled = width * self._fraction
        painter.setBrush(qcolour("accent"))
        painter.drawRoundedRect(QRectF(0, 0, filled, self.height()),
                                radius, radius)
        # The travelling highlight, clipped to the filled part so it never
        # paints over empty track.
        if self._timer.isActive() and filled > 1:
            painter.save()
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, filled, self.height()),
                                radius, radius)
            painter.setClipPath(clip)
            sheen = width * self.SHEEN_WIDTH
            x = self._phase * (filled + sheen) - sheen
            painter.setBrush(qcolour("accent.bright"))
            painter.drawRoundedRect(QRectF(x, 0, sheen, self.height()),
                                    radius, radius)
            painter.restore()
        painter.end()


class Badge(QLabel):
    """A pill: `detected`, `Backend: RyzenAdj`, `not found`.

    `elide` caps how wide the pill may get and truncates from the left when
    the text is longer. The Setup pane puts an installed tool's *full path*
    in one of these, and a real one is long —
    `C:\\Users\\…\\AppData\\Local\\Microsoft\\WinGet\\Links\\framework_tool.EXE` —
    which stretched the row until the Install and Homepage buttons beside it
    were pushed off the pane entirely. Truncating from the left keeps the
    end of the path, which is the part that identifies the binary; the full
    text stays available as the tooltip.
    """

    def __init__(self, text, variant="ok", parent=None, elide=0):
        super().__init__(text, parent)
        self.setProperty("role", "badge")
        self.setProperty("badge", variant)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._elide = elide
        self._full = text
        if elide:
            self.setMaximumWidth(elide)
            self.setToolTip(text)

    def setText(self, text):
        self._full = text
        if self._elide:
            self.setToolTip(text)
        super().setText(text)

    def paintEvent(self, event):
        if self._elide:
            metrics = self.fontMetrics()
            # 18px for the pill's own horizontal padding.
            room = max(0, self.width() - 18)
            shown = metrics.elidedText(self._full, Qt.ElideLeft, room)
            if shown != super().text():
                super().setText(shown)
        super().paintEvent(event)

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
    """A line drawing of *this* chassis, with the bays it actually has.

    Bay outline colour carries the port's state, which is the only reason
    the drawing is here at all: it is a legend for the module rows beside
    it, not decoration.

    The drawing used to be one fixed 300x112 rectangle with four bays at
    hard-coded coordinates, identical for every machine. It now takes its
    proportions from `device_images.chassis_for()` — width against the
    widest Framework chassis, height from that model's own width:depth
    ratio — and lays out the number of slots the chassis really carries.
    A Laptop 12 is visibly smaller than a Laptop 16, the 16 shows its six
    slots rather than four, and the Desktop is drawn as the cube it is with
    its two front slots.
    """

    MAX_WIDTH = 300
    MAX_HEIGHT = 150
    BAY_W, BAY_H = 12, 22       # a side slot; the front layout swaps these
    MARGIN = 10                 # room for the slot tabs outside the body
    # Room for the "Back"/"Front" captions on a clamshell. Added on top of
    # the body's own scaled size rather than taken out of it, so it does
    # not shrink the drawing every model already scales against.
    TAG_H = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._chassis = dict(device_images.DEFAULT_CHASSIS)
        self._states = []
        self._apply_geometry()

    def set_chassis(self, chassis):
        """Reshape for a detected board. Safe to call on every rescan."""
        self._chassis = dict(chassis or device_images.DEFAULT_CHASSIS)
        self._apply_geometry()
        self.update()

    def bay_count(self):
        return int(self._chassis.get("bays", 4))

    @classmethod
    def pixels_per_mm(cls):
        """One scale for every chassis, sized so the largest just fits.

        It has to be shared. Fitting each model to the box independently
        makes them all come out the same size — which is the bug this whole
        widget exists to fix, since the Framework laptops have nearly
        identical width:depth ratios and differ mainly in absolute size.
        """
        avail_w = cls.MAX_WIDTH - 2 * cls.MARGIN - cls.BAY_W
        avail_h = cls.MAX_HEIGHT - 2 * cls.MARGIN - 6
        widest = max(c["width_mm"] for c in device_images.CHASSIS)
        deepest = max(c["depth_mm"] for c in device_images.CHASSIS)
        return min(avail_w / widest, avail_h / deepest)

    def _apply_geometry(self):
        scale = self.pixels_per_mm()
        body_w = float(self._chassis["width_mm"]) * scale
        body_h = float(self._chassis["depth_mm"]) * scale
        # A desktop has no front/back to mark, so it gets none of the extra
        # vertical room the caption reserves.
        top_tag = self.TAG_H if self._chassis.get("layout") != "front" else 0
        self._body = QRectF(self.MARGIN + self.BAY_W / 2.0,
                            self.MARGIN + top_tag, body_w, body_h)
        self.setFixedSize(
            int(body_w + 2 * self.MARGIN + self.BAY_W),
            int(body_h + 2 * self.MARGIN + 6 + 2 * top_tag))

    def set_states(self, states):
        """states: one of 'sink', 'source', 'idle', 'empty' per bay.

        Fewer states than slots is normal and not an error — every platform
        reports at most four PD ports while the Laptop 16 has six slots, so
        the extra slots are simply drawn unreported.
        """
        self._states = list(states)
        self.update()

    def _state(self, index):
        return self._states[index] if index < len(self._states) else "empty"

    def _bay_colour(self, state):
        return {
            "sink": colour("accent.bright"),
            "source": colour("ok.bar"),
            "idle": colour("warn"),
        }.get(state, colour("icon"))

    def bay_rects(self):
        """Where each slot is drawn. Split out so the layout is testable."""
        body, count = self._body, self.bay_count()
        rects = []
        if self._chassis.get("layout") == "front":
            # Front-facing slots along the bottom edge, lying flat.
            w, h = self.BAY_H, self.BAY_W
            for i in range(count):
                x = body.left() + body.width() * (i + 1) / (count + 1) - w / 2
                rects.append(QRectF(x, body.bottom() - h / 2, w, h))
            return rects
        # Side slots, split evenly between the two edges, back to front
        # (index 0 nearest the top/hinge edge) — `App._ordered_by_bay`
        # sorts the states this widget is given into that same order for
        # the one chassis it is confirmed to hold for a 4-bay "sides"
        # layout, so a bay's row and its marker here land in the same slot.
        left = (count + 1) // 2
        for i in range(count):
            side_index = i if i < left else i - left
            per_side = left if i < left else count - left
            x = (body.left() - self.BAY_W / 2.0 if i < left
                 else body.right() - self.BAY_W / 2.0)
            y = (body.top() + body.height() * (side_index + 1) / (per_side + 1)
                 - self.BAY_H / 2.0)
            rects.append(QRectF(x, y, self.BAY_W, self.BAY_H))
        return rects

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(Qt.NoBrush)
        body = self._body
        pen = painter.pen()
        pen.setColor(qcolour("icon"))
        pen.setWidthF(1.3)
        painter.setPen(pen)
        painter.drawRoundedRect(body, 6, 6)
        # Two hinge caps and a speaker grille between them, plus explicit
        # captions — a desktop has no front/back axis to mark. Bay names
        # like "Left Back" are meaningless without a fixed, visible answer
        # to which edge of this drawing they mean, so the words are
        # spelled out rather than left to a decorative line to imply.
        if self._chassis.get("layout") != "front":
            tab_w = body.width() * 0.12
            pen.setWidthF(2.2)
            painter.setPen(pen)
            for x in (body.left() + body.width() * 0.06,
                     body.right() - body.width() * 0.06 - tab_w):
                painter.drawLine(int(x), int(body.top()),
                                 int(x + tab_w), int(body.top()))
            grille_left = body.center().x() - body.width() * 0.16
            grille_right = body.center().x() + body.width() * 0.16
            pen.setWidthF(1.0)
            painter.setPen(pen)
            ticks = 7
            for i in range(ticks):
                x = grille_left + (grille_right - grille_left) * i / (ticks - 1)
                painter.drawLine(QPointF(x, body.top() - 1),
                                 QPointF(x, body.top() + 2))
            font = painter.font()
            font.setPixelSize(theme.FONT_SIZES["caption"] - 2)
            painter.setFont(font)
            pen.setColor(qcolour("text.muted"))
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.drawText(
                QRectF(body.left(), 0, body.width(), body.top() - 2),
                Qt.AlignHCenter | Qt.AlignBottom, "BACK")
            painter.drawText(
                QRectF(body.left(), body.bottom() + 2, body.width(),
                       self.height() - body.bottom() - 2),
                Qt.AlignHCenter | Qt.AlignTop, "FRONT")
        pen.setColor(qcolour("track"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        inset = body.adjusted(body.width() * 0.06, body.height() * 0.16,
                              -body.width() * 0.06, -body.height() * 0.20)
        painter.drawRoundedRect(inset, 3, 3)
        if self._chassis.get("layout") == "front":
            self._paint_desktop_front(painter, pen, body)
        else:
            self._paint_clamshell_deck(painter, pen, inset)
        for index, rect in enumerate(self.bay_rects()):
            state = self._state(index)
            pen.setColor(QColor(self._bay_colour(state)))
            pen.setWidthF(1.1)
            painter.setPen(pen)
            painter.setBrush(qcolour("inset") if state != "empty"
                             else Qt.NoBrush)
            painter.drawRoundedRect(rect, 2, 2)
        painter.end()

    def _paint_clamshell_deck(self, painter, pen, inset):
        """Keyboard row lines, a trackpad, and a power button drawn apart
        from them — every Framework laptop's is its own key, separate
        from the main block, top-right above the keyboard.

        Schematic, not a rendering: real keycaps do not survive a deck
        drawn at ~100px wide, so a few row dividers stand in for the whole
        keyboard rather than every key, matching the level of detail the
        rest of this widget already draws at.
        """
        pen.setWidthF(1.0)
        painter.setPen(pen)
        key_area = QRectF(inset.left() + inset.width() * 0.04,
                          inset.top() + inset.height() * 0.08,
                          inset.width() * 0.8, inset.height() * 0.46)
        for i in range(1, 4):
            y = key_area.top() + key_area.height() * i / 4
            painter.drawLine(QPointF(key_area.left(), y),
                             QPointF(key_area.right(), y))
        trackpad_w = inset.width() * 0.32
        trackpad_h = inset.height() * 0.26
        trackpad = QRectF(inset.center().x() - trackpad_w / 2,
                          inset.bottom() - trackpad_h - inset.height() * 0.04,
                          trackpad_w, trackpad_h)
        painter.drawRoundedRect(trackpad, 3, 3)
        power_size = max(min(inset.width(), inset.height()) * 0.13, 6.0)
        power_rect = QRectF(inset.right() - power_size,
                            key_area.top(), power_size, power_size)
        painter.drawRoundedRect(power_rect, 1.5, 1.5)

    def _paint_desktop_front(self, painter, pen, body):
        """A grid of vent tiles, a fan hub mark, and the slide switch.

        Schematic, not a rendering: the real face is a grid of perforated
        tiles in whichever colour the owner picked, which a two-colour
        line drawing can't show — the grid, the hub and the switch are
        what is left that still reads as *this* machine's front panel
        rather than a bare box with two bays cut into the bottom.
        """
        pen.setWidthF(0.8)
        painter.setPen(pen)
        columns, rows = 3, 6
        grid_top = body.top() + body.height() * 0.06
        grid_bottom = body.bottom() - body.height() * 0.18
        cell_w = body.width() / columns
        cell_h = (grid_bottom - grid_top) / rows
        for row in range(rows):
            for col in range(columns):
                cell = QRectF(body.left() + col * cell_w,
                              grid_top + row * cell_h, cell_w, cell_h)
                painter.drawRect(cell.adjusted(1.5, 1.5, -1.5, -1.5))
        hub_r = min(cell_w, cell_h) * 0.32
        hub_center = QPointF(body.left() + cell_w * 1.5,
                             grid_top + cell_h * 2.5)
        painter.drawEllipse(hub_center, hub_r, hub_r)
        switch_w, switch_h = body.width() * 0.22, body.height() * 0.045
        switch = QRectF(body.right() - switch_w - body.width() * 0.08,
                        grid_bottom + (body.bottom() - grid_bottom) / 2
                        - switch_h / 2, switch_w, switch_h)
        painter.drawRoundedRect(switch, switch_h / 2, switch_h / 2)
        thumb_r = switch_h * 0.4
        painter.drawEllipse(
            QPointF(switch.left() + thumb_r * 1.4, switch.center().y()),
            thumb_r, thumb_r)


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
