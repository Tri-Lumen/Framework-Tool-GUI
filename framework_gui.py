#!/usr/bin/env python3
"""
Framework System GUI — a desktop front-end for framework_tool
(https://github.com/FrameworkComputer/framework-system)

Requirements: Python 3.8+, PySide6, framework_tool installed (host-side when
in Flatpak).

Linux: most commands need root — run as root, or use the elevation banner's
"Elevate with pkexec". Windows: run elevated (the packaged exe self-elevates).
Flatpak: commands run on the host via flatpak-spawn.

Multi-step tools (fan test, sweeps, monitors) run many commands in a row.
If you rely on pkexec you will get a prompt per command unless a polkit
policy with auth_admin_keep is installed — for those tools, run elevated.

On launch (and via "Rescan device") the GUI runs `--versions`, parses the
mainboard type, and shows only the controls that apply to that model
(e.g. stylus/touchscreen on Laptop 12, expansion bay on Laptop 16, RGB LEDs
on Desktop, battery/keyboard-light/fingerprint controls only on laptops).
If detection fails or the model string isn't recognized, every control is
shown rather than guessing what to hide.

Navigation is a 52px icon rail (five groups) selecting a 190px pane list
(the sections inside that group), with the content column filling the rest
and a resizable output drawer along its bottom. The structure and every
gated row live in navigation.py; the colours and metrics in theme.py; the
reusable pieces in widgets.py. This file is layout and plumbing.

Four sections drive tools *other* than framework_tool, because the EC does
not own everything a user wants to change:

  CPU limits  Power limits (TDP). framework_tool cannot set these — the SoC
              owns them — so this shells out to RyzenAdj, the Linux powercap
              sysfs, or Windows' own powercfg. See power.py.
  Setup       Detects and installs those helper tools. See deps.py.
  Drivers     Links to Framework's downloads list for each device build,
              plus vendor drivers for swapped-in parts. See drivers.py.

Deliberately excluded: --flash-* / --force. Use the CLI for those.
"""

import datetime
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import appstate
import backdrop
import deps
import device_images
import drivers
import module_icons
import navigation
import power
import theme
import widgets
from parsers import (
    RE_AC,
    RE_CHG_A,
    RE_CHG_V,
    RE_CYCLES,
    RE_DESIGN,
    RE_IN_A,
    RE_LFCC,
    RE_RPM,
    RE_SOC,
    RE_TEMP,
    detect_model,
    parse_firmware,
    parse_ports,
    parse_setting_value,
    parse_tool_version,
)
from widgets import colour, label, rule, section_label

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
IN_FLATPAK = os.path.exists("/.flatpak-info")

APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Sensor bar full-scale values. Bars need a ceiling to be a fraction of
# something; these are display scales, not limits the app enforces.
TEMP_SCALE_C = 100.0
FAN_SCALE_RPM = 7000.0


def find_binary():
    if IN_FLATPAK:
        return "framework_tool"  # resolved on the host by flatpak-spawn
    for name in ("framework_tool", "framework-tool"):
        p = shutil.which(name)
        if p:
            return p
    return "framework_tool"


def is_root():
    if IS_WINDOWS:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:  # noqa: BLE001
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def detect_cpu():
    """CPU vendor/name for the power pane. Safe to call from a worker thread.

    Inside the Flatpak sandbox /proc/cpuinfo is still the host's CPU, so no
    flatpak-spawn round trip is needed here.
    """
    cpuinfo = ""
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            cpuinfo = fh.read(20000)
    except OSError:
        pass
    ident = os.environ.get("PROCESSOR_IDENTIFIER", "")
    return {
        "vendor": power.detect_vendor(cpuinfo, ident, platform.machine()),
        "label": power.cpu_label(cpuinfo, ident),
    }


def rapl_zones():
    """Names of the kernel's powercap zones, or [] where there is no sysfs."""
    try:
        return os.listdir(power.RAPL_ROOT)
    except OSError:
        return []


def read_text_file(path):
    """Read a small sysfs file; '' when it isn't readable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(200)
    except OSError:
        return ""


def load_fonts():
    """Register any vendored IBM Plex faces found next to the app.

    The design specifies IBM Plex Sans/Mono. They are OFL and free to
    bundle, but nothing in this repo ships binary font files yet, so this
    finds them if a build drops them into fonts/ and otherwise leaves the
    style sheet to fall back to the platform's own sans and mono faces.
    """
    font_dir = os.path.join(APP_DIR, "fonts")
    loaded = []
    try:
        names = sorted(os.listdir(font_dir))
    except OSError:
        return loaded
    for name in names:
        if name.lower().endswith((".ttf", ".otf")):
            if QFontDatabase.addApplicationFont(
                    os.path.join(font_dir, name)) != -1:
                loaded.append(name)
    return loaded


# ---------- output parsers live in parsers.py ----------


class LogView(QWidget):
    """The drawer body: verbatim CLI text, one colour per line kind.

    Lines are inserted with a character format rather than as HTML so the
    text stays exactly what the command printed — the design is explicit
    that CLI output is not reformatted.
    """

    KINDS = {
        "command": "text.primary",
        "output": "terminal.out",
        "warn": "warn",
        "ok": "ok",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 10, 14, 6)
        box.setSpacing(0)
        self.view = QTextEdit(self)
        self.view.setObjectName("terminal")
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QTextEdit.NoWrap)
        box.addWidget(self.view, 1)

        # The design's block cursor sits at the tail of the log. Keeping it
        # as its own strip rather than a character in the document means an
        # append never has to rewrite the last line.
        prompt = QWidget(self)
        prompt_row = QHBoxLayout(prompt)
        prompt_row.setContentsMargins(0, 0, 0, 0)
        prompt_row.setSpacing(8)
        prompt_row.addWidget(label("$", "prompt", prompt))
        block = QFrame(prompt)
        block.setFixedSize(7, 15)
        block.setStyleSheet("background: {};".format(colour("accent.bright")))
        prompt_row.addWidget(block)
        prompt_row.addStretch(1)
        box.addWidget(prompt)

    def append(self, text, kind="output"):
        cursor = self.view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(Qt.GlobalColor.white)
        cursor.insertText(text)
        self.view.setTextCursor(cursor)
        self._recolour_tail(kind, len(text))
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _recolour_tail(self, kind, length):
        from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
        cursor = QTextCursor(self.view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.Left,
                            QTextCursor.MoveMode.KeepAnchor, length)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour(self.KINDS.get(kind, "output"))))
        cursor.mergeCharFormat(fmt)

    def clear(self):
        self.view.clear()

    def set_wrap(self, wrap):
        self.view.setLineWrapMode(QTextEdit.WidgetWidth if wrap
                                  else QTextEdit.NoWrap)

    def wraps(self):
        return self.view.lineWrapMode() != QTextEdit.NoWrap


class Drawer(QWidget):
    """Tab strip + one LogView per program the app has run."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drawer")
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        tabs = QWidget(self)
        tabs.setObjectName("drawerTabs")
        tabs.setFixedHeight(theme.DRAWER_TABS_HEIGHT)
        self.tab_row = QHBoxLayout(tabs)
        self.tab_row.setContentsMargins(0, 0, 12, 0)
        self.tab_row.setSpacing(0)
        self.tab_row.addStretch(1)

        self.wrap_btn = QPushButton("wrap", tabs)
        self.wrap_btn.setProperty("role", "drawerTool")
        self.wrap_btn.clicked.connect(self._toggle_wrap)
        self.clear_btn = QPushButton("clear", tabs)
        self.clear_btn.setProperty("role", "drawerTool")
        self.clear_btn.clicked.connect(self._clear)
        self.tab_row.addWidget(self.wrap_btn)
        self.tab_row.addWidget(self.clear_btn)
        box.addWidget(tabs)

        self.stack = QStackedWidget(self)
        box.addWidget(self.stack, 1)

        self._tabs = {}
        self._views = {}
        self.ensure("framework_tool")

    def ensure(self, stream):
        """Create the tab for a program the first time it produces output."""
        if stream in self._views:
            return self._views[stream]
        view = LogView(self)
        self._views[stream] = view
        self.stack.addWidget(view)
        button = QPushButton(stream, self)
        button.setProperty("role", "drawerTab")
        button.setFixedHeight(theme.DRAWER_TABS_HEIGHT)
        button.clicked.connect(lambda _=False, s=stream: self.select(s))
        self._tabs[stream] = button
        self.tab_row.insertWidget(len(self._tabs) - 1, button)
        if len(self._views) == 1:
            self.select(stream)
        return view

    def select(self, stream):
        view = self.ensure(stream)
        self.stack.setCurrentWidget(view)
        for name, button in self._tabs.items():
            button.setProperty("selected", "true" if name == stream else "false")
            widgets.restyle(button)

    def append(self, stream, text, kind="output"):
        self.ensure(stream).append(text, kind)

    def current_view(self):
        return self.stack.currentWidget()

    def _toggle_wrap(self):
        view = self.current_view()
        if view:
            view.set_wrap(not view.wraps())

    def _clear(self):
        view = self.current_view()
        if view:
            view.clear()


class ToolDetail(widgets.Panel):
    """The multi-step tool panel: title, running badge, cancel, step grid."""

    COLUMNS = 6

    def __init__(self, on_cancel, parent=None):
        super().__init__(parent)
        header = QHBoxLayout()
        header.setSpacing(theme.SPACE[4])
        self.title = label("", "name", self)
        header.addWidget(self.title)

        badge = QWidget(self)
        badge_row = QHBoxLayout(badge)
        badge_row.setContentsMargins(8, 2, 8, 2)
        badge_row.setSpacing(theme.SPACE[2])
        self.spinner = widgets.Spinner(badge)
        badge_row.addWidget(self.spinner)
        self.progress = label("", "warnText", badge)
        badge_row.addWidget(self.progress)
        badge.setStyleSheet(
            "background: {}; border: 1px solid {}; border-radius: 10px;".format(
                colour("warn.fill"), colour("warn.border")))
        header.addWidget(badge)
        header.addStretch(1)

        self.cancel = QPushButton("Cancel and restore auto", self)
        self.cancel.setProperty("role", "danger")
        self.cancel.clicked.connect(on_cancel)
        header.addWidget(self.cancel)
        self.body.addLayout(header)

        self.grid = QGridLayout()
        self.grid.setSpacing(theme.SPACE[3])
        self.body.addLayout(self.grid)
        self._cells = []

    def begin(self, title, total):
        self.title.setText(title)
        self._reset_cells(total)
        self.spinner.start()
        self.setVisible(True)

    def _reset_cells(self, total):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cells = []
        for index in range(max(1, total)):
            cell = widgets.Panel(self)
            cell.body.setSpacing(theme.SPACE[1])
            name = label("—", "caption", cell)
            value = label("—", "stat", cell)
            bar = widgets.Bar(4, cell)
            cell.body.addWidget(name)
            cell.body.addWidget(value)
            cell.body.addWidget(bar)
            self.grid.addWidget(cell, index // self.COLUMNS,
                                index % self.COLUMNS)
            self._cells.append((name, value, bar))

    def update_step(self, index, step, total, name, value, fraction):
        self.progress.setText("running · step {} of {}".format(step, total))
        if 0 <= index < len(self._cells):
            cell_name, cell_value, bar = self._cells[index]
            cell_name.setText(name)
            cell_value.setText(value)
            bar.set_accent(fraction)

    def finish(self):
        self.spinner.stop()
        self.progress.setText("finished")


class App(QMainWindow):
    BLOCKED = {"--flash-ec", "--flash-ro-ec", "--flash-rw-ec",
               "--flash-gpu-descriptor", "--flash-gpu-descriptor-file",
               "-f", "--force"}

    # Worker threads never touch a widget; they emit these and Qt delivers
    # them on the UI thread. Same rule the Tk version followed with after().
    sig_log = Signal(str, str, str)
    sig_status = Signal(str)
    sig_detected = Signal(object, object, object)
    sig_tool_done = Signal()
    sig_progress = Signal(object)
    sig_readings = Signal(object)
    sig_fill = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.binary = find_binary()
        self.use_pkexec = (
            IS_LINUX and not is_root()
            and (IN_FLATPAK or shutil.which("pkexec") is not None))
        self._busy = False
        self._cancel = False

        # Fail-open defaults: show every control until (or unless) detection
        # narrows things down.
        self.caps = {
            "model": "Detecting…", "chassis": "", "detected": False,
            "is_laptop": True, "is_desktop": False, "is_laptop12": True,
            "has_touchscreen": True, "has_stylus": True,
            "has_expansion_bay": True, "has_rgbkbd": True,
        }
        # CPU vendor drives which power-limit backends and which helper
        # tools are worth offering. Unknown until the first scan, and
        # "unknown" keeps showing everything rather than hiding it.
        self.cpu = {"vendor": power.VENDOR_UNKNOWN, "label": ""}
        self.firmware = {"ec": "", "bios": ""}
        self.tool_version = ""
        self.readings = {}
        self.power_backend = None
        # Power limits read back before this session changed them, so
        # "Restore previous" is possible without a reboot. Same instinct as
        # the fan/backlight tools, which always restore what they found.
        self._power_saved = {}
        self._preset = None

        self.settings = appstate.load()
        self.appearance = self.settings["appearance"]
        self.drawer_height = self.settings["drawer_height"]
        self.compositing = backdrop.supports_translucency(environ=os.environ)
        if not self.compositing:
            self.appearance = theme.OPAQUE
        self.banner_dismissed = False

        self.section = "overview"
        self.rail_key = "overview"
        self.pages = {}
        self.tool_rows = {}
        self.port_buttons = {}
        self.settings_widgets = {}

        self.setMinimumSize(QSize(*theme.MIN_WINDOW_SIZE))
        self.resize(QSize(*theme.WINDOW_SIZE))
        self._build_chrome()
        self._build_pages()
        self._apply_appearance()
        self._select_section(self.section)

        for signal, slot in (
                (self.sig_log, self._on_log),
                (self.sig_status, self._on_status),
                (self.sig_detected, self._apply_detection),
                (self.sig_tool_done, self._tool_done),
                (self.sig_progress, self._on_progress),
                (self.sig_readings, self._apply_readings),
                (self.sig_fill, self._on_fill)):
            signal.connect(slot)

        if IS_LINUX and not is_root() and not self.use_pkexec:
            self.set_status("Not running as root — most commands will fail.")

        # Defer past the first event loop turn: the scan runs on a worker
        # thread and the window should be up before it reports back.
        QTimer.singleShot(150, self._rescan)

    # ================= chrome =================

    def _build_chrome(self):
        central = QWidget(self)
        central.setObjectName("window")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.banner = self._build_banner(central)
        root.addWidget(self.banner)
        self.fallback_strip = self._build_fallback_strip(central)
        root.addWidget(self.fallback_strip)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        body.addWidget(self._build_rail(central))
        body.addWidget(self._build_pane(central))

        column = QWidget(central)
        column.setObjectName("content")
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        # Shown only when the window is too narrow for the pane list; the
        # rail still selects the group, this selects within it.
        self.section_combo = QComboBox(column)
        self.section_combo.setVisible(False)
        self.section_combo.activated.connect(self._combo_selected)
        combo_wrap = QWidget(column)
        combo_layout = QHBoxLayout(combo_wrap)
        combo_layout.setContentsMargins(theme.CONTENT_MARGINS[0], 8,
                                        theme.CONTENT_MARGINS[2], 0)
        combo_layout.addWidget(self.section_combo)
        combo_layout.addStretch(1)
        self.combo_wrap = combo_wrap
        combo_wrap.setVisible(False)
        col.addWidget(combo_wrap)

        self.stack = QStackedWidget(column)
        col.addWidget(self.stack, 1)

        self.grabber = widgets.Grabber(lambda: self.drawer_height, column)
        self.grabber.dragged.connect(self._resize_drawer)
        col.addWidget(self.grabber)

        self.drawer = Drawer(column)
        self.drawer.setFixedHeight(self.drawer_height)
        col.addWidget(self.drawer)

        col.addWidget(self._build_statusbar(column))
        body.addWidget(column, 1)

    def _build_banner(self, parent):
        bar = QWidget(parent)
        bar.setObjectName("banner")
        bar.setFixedHeight(theme.BANNER_HEIGHT)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(theme.SPACE[4])
        icon = QLabel(bar)
        icon.setPixmap(widgets.stroke_pixmap(
            ("M8 1.5 15 14H1z", "M8 6v4", "M8 11.8v.4"), colour("warn"), 14))
        row.addWidget(icon)
        row.addWidget(label("Not running as root — most commands will fail.",
                            "bannerText", bar))
        if IS_LINUX:
            elevate = QPushButton("Elevate with pkexec", bar)
            elevate.setProperty("role", "warn")
            elevate.clicked.connect(self._enable_pkexec)
            row.addWidget(elevate)
        row.addStretch(1)
        dismiss = QPushButton("✕", bar)
        dismiss.setProperty("role", "dismiss")
        dismiss.clicked.connect(self._dismiss_banner)
        row.addWidget(dismiss)
        bar.setVisible(not is_root())
        return bar

    def _build_fallback_strip(self, parent):
        strip = QWidget(parent)
        strip.setObjectName("fallbackStrip")
        strip.setFixedHeight(theme.FALLBACK_STRIP_HEIGHT)
        row = QHBoxLayout(strip)
        row.setContentsMargins(12, 0, 12, 0)
        row.addWidget(label(backdrop.unavailable_message(), "caption", strip))
        row.addStretch(1)
        strip.setVisible(not self.compositing)
        return strip

    def _build_rail(self, parent):
        rail = QWidget(parent)
        rail.setObjectName("rail")
        rail.setFixedWidth(theme.RAIL_WIDTH)
        box = QVBoxLayout(rail)
        box.setContentsMargins(0, 8, 0, 8)
        box.setSpacing(theme.SPACE[1])
        box.setAlignment(Qt.AlignHCenter)
        self.rail_buttons = {}
        for group in navigation.RAIL_GROUPS:
            button = widgets.RailButton(group, rail)
            button.clicked.connect(
                lambda _=False, key=group["key"]: self._select_rail(key))
            box.addWidget(button, 0, Qt.AlignHCenter)
            self.rail_buttons[group["key"]] = button
        box.addStretch(1)
        toggle = QPushButton(rail)
        toggle.setFlat(True)
        toggle.setFixedSize(*theme.RAIL_ITEM)
        toggle.setToolTip("Toggle acrylic")
        toggle.setStyleSheet("border: none; background: transparent;")
        toggle.clicked.connect(self._toggle_appearance)
        self.appearance_toggle = toggle
        box.addWidget(toggle, 0, Qt.AlignHCenter)
        return rail

    def _build_pane(self, parent):
        pane = QWidget(parent)
        pane.setObjectName("pane")
        pane.setFixedWidth(theme.PANE_WIDTH)
        box = QVBoxLayout(pane)
        box.setContentsMargins(0, 12, 0, 0)
        box.setSpacing(0)
        self.pane_title = section_label("", pane)
        self.pane_title.setContentsMargins(14, 0, 14, 8)
        box.addWidget(self.pane_title)
        self.pane_items = QVBoxLayout()
        self.pane_items.setSpacing(theme.SPACE[0])
        box.addLayout(self.pane_items)
        box.addStretch(1)

        box.addWidget(rule(pane))
        footer = QWidget(pane)
        footer_box = QVBoxLayout(footer)
        footer_box.setContentsMargins(14, 12, 14, 12)
        footer_box.setSpacing(theme.SPACE[2])
        footer_box.addWidget(label("Appearance", "caption", footer))
        self.segment = widgets.Segmented(theme.APPEARANCES, footer)
        self.segment.chosen.connect(self._set_appearance)
        self.segment.set_choices_enabled(self.compositing)
        footer_box.addWidget(self.segment)
        box.addWidget(footer)
        self.pane = pane
        return pane

    def _build_statusbar(self, parent):
        bar = QWidget(parent)
        bar.setObjectName("statusBar")
        bar.setFixedHeight(theme.STATUS_HEIGHT)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(theme.SPACE[6])
        self.status_elevation = label("", "status", bar)
        self.status_binary = label("", "status", bar)
        self.status_modules = label("", "status", bar)
        self.status_message = label("Ready", "status", bar)
        for widget in (self.status_elevation, self.status_binary,
                       self.status_modules, self.status_message):
            row.addWidget(widget)
        row.addStretch(1)
        self.status_appearance = label("", "status", bar)
        row.addWidget(self.status_appearance)
        self._refresh_statusbar()
        return bar

    def _refresh_statusbar(self):
        if is_root():
            elevation = "Elevated"
        elif self.use_pkexec:
            elevation = "pkexec"
        else:
            elevation = "Not elevated"
        self.status_elevation.setText(elevation)
        name = os.path.basename(self.binary) or "framework_tool"
        self.status_binary.setText(
            "{} {}".format(name, self.tool_version).strip())
        ports = self.readings.get("ports")
        self.status_modules.setText(
            "{} modules".format(len(ports)) if ports else "modules not read")
        self.status_appearance.setText(
            backdrop.status_label(self.appearance, self.compositing))

    # ================= appearance =================

    def _apply_appearance(self):
        acrylic = self.appearance == theme.ACRYLIC and self.compositing
        widgets.set_appearance(theme.ACRYLIC if acrylic else theme.OPAQUE)
        self.setStyleSheet(theme.stylesheet(
            theme.ACRYLIC if acrylic else theme.OPAQUE))
        self.setAttribute(Qt.WA_TranslucentBackground, acrylic)
        if IS_WINDOWS:
            backdrop.apply_windows_backdrop(int(self.winId()), acrylic)
        self.segment.set_value(self.appearance)
        self.appearance_toggle.setIcon(widgets.stroke_icon(
            navigation.APPEARANCE_ICON,
            colour("accent.icon") if acrylic else colour("icon")))
        self.appearance_toggle.setIconSize(QSize(18, 18))
        self.status_appearance.setText(
            backdrop.status_label(self.appearance, self.compositing))

    def _set_appearance(self, appearance):
        if not self.compositing and appearance == theme.ACRYLIC:
            return
        self.appearance = appearance
        self.settings["appearance"] = appearance
        appstate.save(self.settings)
        self._apply_appearance()

    def _toggle_appearance(self):
        self._set_appearance(theme.OPAQUE if self.appearance == theme.ACRYLIC
                             else theme.ACRYLIC)

    def _resize_drawer(self, height):
        self.drawer_height = appstate.clamp_drawer(height)
        self.drawer.setFixedHeight(self.drawer_height)
        self.settings["drawer_height"] = self.drawer_height
        appstate.save(self.settings)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        collapsed = self.width() < theme.PANE_COLLAPSE_WIDTH
        self.pane.setVisible(not collapsed)
        self.combo_wrap.setVisible(collapsed)
        self.section_combo.setVisible(collapsed)

    # ================= navigation =================

    def _select_rail(self, rail_key):
        self._select_section(navigation.first_section(rail_key))

    def _combo_selected(self, index):
        section = self.section_combo.itemData(index)
        if section:
            self._select_section(section)

    def _select_section(self, section):
        if section not in self.pages:
            section = navigation.SECTIONS[0]
        self.section = section
        group = navigation.group_for_section(section)
        self.rail_key = group["key"]
        for key, button in self.rail_buttons.items():
            button.setChecked(key == self.rail_key)
            button.update()
        self._rebuild_pane_items(group)
        self.stack.setCurrentWidget(self.pages[section])
        # The chassis, not the full board string: the title bar gets the
        # same short name the Overview heading uses.
        self.setWindowTitle(
            navigation.window_title(section, self.caps.get("chassis", "")))

    def _rebuild_pane_items(self, group):
        while self.pane_items.count():
            item = self.pane_items.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pane_title.setText(group["label"].upper())
        self.section_combo.clear()
        for item_label, section in group["items"]:
            entry = widgets.PaneItem(item_label, section, self.pane)
            entry.setChecked(section == self.section)
            entry.clicked.connect(
                lambda _=False, key=section: self._select_section(key))
            self.pane_items.addWidget(entry)
            self.section_combo.addItem(item_label, section)
        index = self.section_combo.findData(self.section)
        if index >= 0:
            self.section_combo.setCurrentIndex(index)

    # ================= pages =================

    def _build_pages(self):
        """Build every section. Called again after each device scan.

        The whole stack is rebuilt rather than patched: gating changes which
        rows exist, not just whether they are enabled, and rebuilding is the
        same thing the Tk version did with its notebook.
        """
        previous = self.section
        while self.stack.count():
            widget = self.stack.widget(0)
            self.stack.removeWidget(widget)
            widget.deleteLater()
        self.pages = {}
        self.tool_rows = {}
        self.port_buttons = {}
        self.settings_widgets = {}
        builders = {
            "overview": self._page_overview,
            "tools": self._page_tools,
            "fans": self._page_fans,
            "ports": self._page_ports,
            "settings": self._page_settings,
            "power": self._page_power,
            "drivers": self._page_drivers,
            "setup": self._page_setup,
            "console": self._page_console,
        }
        for section in navigation.SECTIONS:
            page = QWidget()
            box = QVBoxLayout(page)
            box.setContentsMargins(*theme.CONTENT_MARGINS)
            box.setSpacing(theme.SPACE[6])
            builders[section](box, page)
            box.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.pages[section] = scroll
            self.stack.addWidget(scroll)
        self._select_section(previous)
        # A rescan rebuilds every widget, so anything already read has to be
        # painted back onto the new ones or the panes would look unread.
        if self.readings:
            self._apply_readings({})

    def _heading(self, box, parent, text, intro=None, badge=None, note=None):
        row = QHBoxLayout()
        row.setSpacing(theme.SPACE[4])
        row.addWidget(label(text, "heading", parent))
        if badge is not None:
            row.addWidget(badge)
        if note:
            row.addWidget(label(note, "inlineNote", parent))
        row.addStretch(1)
        box.addLayout(row)
        if intro:
            text_label = label(intro, "intro", parent)
            text_label.setWordWrap(True)
            text_label.setMaximumWidth(680)
            box.addWidget(text_label)

    # ---- Overview ----

    def _page_overview(self, box, parent):
        hero = QHBoxLayout()
        hero.setSpacing(theme.SPACE[9])
        self.device_image = widgets.ImageSlot(parent)
        self._refresh_device_image()
        hero.addWidget(self.device_image, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(theme.SPACE[2])
        title_row = QHBoxLayout()
        title_row.setSpacing(theme.SPACE[4])
        self.device_name = label(self._device_name(), "device", parent)
        title_row.addWidget(self.device_name)
        self.detected_badge = widgets.Badge(
            "detected" if self.caps.get("detected") else "not detected",
            "ok" if self.caps.get("detected") else "muted", parent)
        title_row.addWidget(self.detected_badge)
        title_row.addStretch(1)
        rescan = QPushButton("Rescan device", parent)
        rescan.clicked.connect(self._rescan)
        title_row.addWidget(rescan)
        right.addLayout(title_row)

        self.device_sub = label(self._device_subline(), "sub", parent)
        self.device_sub.setWordWrap(True)
        right.addWidget(self.device_sub)
        right.addSpacing(theme.SPACE[4])

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACE[8])
        grid.setVerticalSpacing(theme.SPACE[4])
        self.stat_cards = {}
        stats = (("battery", "Battery"), ("cpu", "CPU package"),
                 ("fan", "Fan"), ("charge_limit", "Charge limit"),
                 ("ac", "AC input"), ("cycles", "Cycles"))
        for index, (key, name) in enumerate(stats):
            card = widgets.Card(name, "—", parent)
            grid.addWidget(card, index // 2, index % 2)
            self.stat_cards[key] = card
        right.addLayout(grid)
        right.addStretch(1)
        hero.addLayout(right, 1)
        box.addLayout(hero)

        panel = widgets.Panel(parent)
        header = QHBoxLayout()
        header.addWidget(section_label("Expansion bays", panel))
        header.addStretch(1)
        header.addWidget(label(
            "left front → right rear · negotiated power from --pdports",
            "caption", panel))
        panel.body.addLayout(header)

        bays = QHBoxLayout()
        bays.setSpacing(theme.SPACE[6])
        self.chassis = widgets.ChassisDiagram(panel)
        bays.addWidget(self.chassis, 0, Qt.AlignTop)
        module_grid = QGridLayout()
        module_grid.setSpacing(theme.SPACE[3])
        self.module_rows = []
        for index in range(4):
            row_frame = QFrame(panel)
            row_frame.setObjectName("inset")
            row = QHBoxLayout(row_frame)
            row.setContentsMargins(10, 8, 10, 8)
            row.setSpacing(theme.SPACE[4])
            icon = widgets.ModuleIcon(row_frame)
            row.addWidget(icon, 0, Qt.AlignVCenter)
            text = QVBoxLayout()
            text.setSpacing(0)
            name = label("Port {}".format(index + 1), "cell", row_frame)
            detail = label("not read", "caption", row_frame)
            text.addWidget(name)
            text.addWidget(detail)
            row.addLayout(text, 1)
            module_grid.addWidget(row_frame, index // 2, index % 2)
            self.module_rows.append((icon, name, detail))
        bays.addLayout(module_grid, 1)
        panel.body.addLayout(bays)
        box.addWidget(panel)

    def _device_name(self):
        """The chassis, which is what fits on a 22px heading line.

        The full board string carries the mainboard generation too, which is
        useful but far too long for a title; it goes in the sub-line.
        """
        return self.caps.get("chassis") or "Unknown device"

    def _device_subline(self):
        board = self.caps.get("model", "")
        parts = []
        if board and board != "Unknown":
            parts.append(board)
        if self.cpu.get("label"):
            parts.append(self.cpu["label"])
        if self.firmware.get("ec"):
            parts.append("EC {}".format(self.firmware["ec"]))
        if self.firmware.get("bios"):
            parts.append("BIOS {}".format(self.firmware["bios"]))
        return " · ".join(parts) or "No firmware detail read yet."

    def _has_gpu_module(self):
        """True when the expansion bay reported a Graphics Module.

        Only the Laptop 16 has a bay to report one, and it changes the shape
        of the machine, so it changes which photograph the Overview shows.
        """
        return "graphics" in (self.readings.get("expansion_bay") or "").lower()

    def _refresh_device_image(self):
        path = device_images.path_for(self.caps.get("model", ""),
                                      self._has_gpu_module())
        if path:
            self.device_image.set_image(QPixmap(path))
        else:
            self.device_image.set_device(self._device_name())

    # ---- Diagnostics ----

    def _page_tools(self, box, parent):
        self._heading(
            box, parent, "Diagnostics",
            note="Multi-step tools issue many commands — run elevated to "
                 "avoid repeated prompts.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACE[7])
        grid.setVerticalSpacing(theme.SPACE[3])
        for index, tool in enumerate(navigation.tools_for(self.caps)):
            frame = QFrame(parent)
            frame.setObjectName("toolRow")
            row = QHBoxLayout(frame)
            row.setContentsMargins(11, 9, 11, 9)
            row.setSpacing(theme.SPACE[4])
            text = QVBoxLayout()
            text.setSpacing(theme.SPACE[0])
            text.addWidget(label(tool["label"], "rowtitle", frame))
            text.addWidget(label(tool["tip"], "caption", frame))
            row.addLayout(text, 1)
            run = QPushButton("Run", frame)
            run.setProperty("role",
                            "dangerSubtle" if tool.get("danger") else "link")
            run.clicked.connect(lambda _=False, t=tool: self._start_tool(t))
            row.addWidget(run, 0, Qt.AlignVCenter)
            grid.addWidget(frame, index // 2, index % 2)
            self.tool_rows[tool["key"]] = frame
        box.addLayout(grid)

        self.tool_detail = ToolDetail(self._request_cancel, parent)
        self.tool_detail.setVisible(False)
        box.addWidget(self.tool_detail)

    # ---- Fans ----

    def _page_fans(self, box, parent):
        self._heading(
            box, parent, "Fans & thermals",
            "Duty and RPM are written straight to the EC. Manual control "
            "persists until you restore automatic control or reboot.")
        panels = QHBoxLayout()
        panels.setSpacing(theme.SPACE[6])

        duty = widgets.MetricPanel("Duty cycle", "%", True, parent)
        self.fan_duty = self._metric_field(duty, "50")
        self.fan_duty.textChanged.connect(
            lambda text: duty.bar.set_accent(self._fraction(text, 100)))
        duty.bar.set_accent(0.5)
        set_duty = QPushButton("Set duty", duty)
        set_duty.clicked.connect(
            lambda: self.run(["--fansetduty", self.fan_duty.text().strip()]))
        duty.add_action(set_duty)
        panels.addWidget(duty)

        rpm = widgets.MetricPanel("Target RPM", "rpm", True, parent)
        self.fan_rpm = self._metric_field(rpm, "3000")
        self.fan_rpm.textChanged.connect(
            lambda text: rpm.bar.set_accent(self._fraction(text,
                                                           FAN_SCALE_RPM)))
        rpm.bar.set_accent(3000 / FAN_SCALE_RPM)
        set_rpm = QPushButton("Set RPM", rpm)
        set_rpm.clicked.connect(
            lambda: self.run(["--fansetrpm", self.fan_rpm.text().strip()]))
        rpm.add_action(set_rpm)
        panels.addWidget(rpm)

        control = widgets.Panel(parent)
        control.setFixedWidth(theme.METRIC_PANEL_WIDTH)
        control.body.addWidget(label("Control", "caption", control))
        self.fan_mode = label("Automatic — as found", "cell", control)
        control.body.addWidget(self.fan_mode)
        control.body.addStretch(1)
        restore = QPushButton("Restore automatic control", control)
        restore.setProperty("role", "accent")
        # Compact padding so the design's copy fits the design's 210px panel.
        restore.setProperty("compact", "true")
        restore.clicked.connect(lambda: self.run(["--autofanctrl"]))
        control.body.addWidget(restore)
        burst = QPushButton("Max burst 30 s", control)
        burst.setProperty("role", "danger")
        burst.clicked.connect(
            lambda: self._start_tool_by_key("fan_burst"))
        control.body.addWidget(burst)
        panels.addWidget(control)
        panels.addStretch(1)
        box.addLayout(panels)

        panel = widgets.Panel(parent)
        header = QHBoxLayout()
        header.addWidget(section_label("Sensors", panel))
        header.addStretch(1)
        read = QPushButton("Read thermal", panel)
        read.setProperty("role", "compact")
        read.clicked.connect(self._read_sensors)
        header.addWidget(read)
        panel.body.addLayout(header)
        self.sensor_rows = {}
        self.sensor_holder = QVBoxLayout()
        self.sensor_holder.setSpacing(theme.SPACE[3])
        panel.body.addLayout(self.sensor_holder)
        self.sensor_empty = label(
            "Nothing read yet — Read thermal fills this in.", "caption", panel)
        self.sensor_holder.addWidget(self.sensor_empty)
        box.addWidget(panel)

    @staticmethod
    def _metric_field(panel, default):
        panel.field.setText(default)
        return panel.field

    @staticmethod
    def _fraction(text, scale):
        try:
            return max(0.0, min(1.0, float(text) / float(scale)))
        except (TypeError, ValueError):
            return 0.0

    # ---- Ports & modules ----

    def _page_ports(self, box, parent):
        self._heading(
            box, parent, "Ports & modules",
            "Roles and negotiated power come from --pdports; module identity "
            "from --pd-info, --dp-hdmi-info and --audio-card-info.")
        panel = widgets.Panel(parent)
        panel.body.setSpacing(0)
        panel.body.addWidget(self._port_row(
            [("#", "caption"), ("Module", "caption"), ("Role", "caption"),
             ("Power", "caption"), ("Detail", "caption")], panel))
        panel.body.addWidget(rule(panel))
        self.port_rows = QVBoxLayout()
        self.port_rows.setSpacing(0)
        panel.body.addLayout(self.port_rows)
        self.port_empty = label(
            "No ports read yet — USB-C PD ports fills this in.", "caption",
            panel)
        panel.body.addWidget(self.port_empty)
        box.addWidget(panel)

        buttons = QGridLayout()
        buttons.setSpacing(theme.SPACE[3])
        queries = navigation.port_queries_for(self.caps)
        for index, query in enumerate(queries):
            button = QPushButton(query["label"], parent)
            button.clicked.connect(
                lambda _=False, a=list(query["args"]): self.run(a))
            buttons.addWidget(button, index // 6, index % 6)
            self.port_buttons[query["key"]] = button
        buttons.setColumnStretch(6, 1)
        box.addLayout(buttons)
        self._render_ports()

    # Column widths for the ports table. The Module column takes what is
    # left, which is what the design's `40px 1fr 110px 90px 100px` says.
    PORT_COLUMNS = (40, 0, 110, 90, 100)

    def _port_row(self, cells, parent=None):
        """One table row: fixed columns, its own padding, a divider below."""
        row_widget = QWidget(parent)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(4, 9, 4, 9)
        row.setSpacing(theme.SPACE[4])
        for index, (text, role) in enumerate(cells):
            cell = label(str(text), role, row_widget)
            width = self.PORT_COLUMNS[index]
            if width:
                cell.setFixedWidth(width)
                row.addWidget(cell)
            else:
                row.addWidget(cell, 1)
        return row_widget

    def _render_ports(self):
        ports = self.readings.get("ports") or []
        while self.port_rows.count():
            item = self.port_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.port_empty.setVisible(not ports)
        for index, port in enumerate(ports):
            watts = ("{:.1f} W".format(port["watts"]) if port.get("watts")
                     else "—")
            detail = ("{:.1f} V {:.1f} A".format(port["volts"],
                                                 port["ma"] / 1000.0)
                      if port.get("watts") else "no PD contract")
            module = self._module_name(
                module_icons.classify("usb-c" if port.get("watts") else ""),
                port["port"])
            if index:
                self.port_rows.addWidget(rule())
            self.port_rows.addWidget(self._port_row((
                (port["port"], "cellmono"),
                (module, "rowtitle"),
                (port.get("role", "?").lower(), "cell"),
                (watts, "cellmono"),
                (detail, "caption"),
            )))

    # ---- Settings ----

    def _page_settings(self, box, parent):
        self._heading(
            box, parent, "Settings",
            "Only the controls this mainboard supports are shown. Detection "
            "failing shows everything rather than guessing.")
        panel = widgets.Panel(parent)
        # The rows carry their own vertical padding, so the panel adds none:
        # doubling them would stretch six rows past the fold.
        panel.body.setSpacing(0)
        rows = navigation.settings_rows_for(self.caps)
        for index, row in enumerate(rows):
            if index:
                panel.body.addWidget(rule(panel))
            panel.body.addWidget(self._settings_row(row, panel))
        if not rows:
            panel.body.addWidget(label(
                "No model-specific settings detected for this device.",
                "caption", panel))
        box.addWidget(panel)

    def _settings_row(self, row, parent):
        frame = QWidget(parent)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(theme.SPACE[6])

        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(label(row["label"], "rowtitle", frame))
        text.addWidget(label(row["note"], "caption", frame))
        block = QWidget(frame)
        block.setLayout(text)
        # 30px over the design's 230: the input-deck note is the longest
        # string on the pane and clipping it would hide the word "deck",
        # which is the whole warning.
        block.setFixedWidth(260)
        layout.addWidget(block)

        if row["kind"] == "choice":
            editor = QComboBox(frame)
            editor.addItems(list(row["choices"]))
            editor.setCurrentText(row["default"])
            editor.setFixedWidth(120)
        else:
            editor = QLineEdit(row["default"], frame)
            editor.setProperty("role", "mono")
            editor.setFixedWidth(80 if row["kind"] == "number" else 110)
        layout.addWidget(editor)
        layout.addStretch(1)
        self.settings_widgets[row["key"]] = editor

        if row["kind"] == "rgb":
            set_all = QPushButton("Set all", frame)
            set_all.setProperty("role", "accent")
            set_all.clicked.connect(self._set_rgb_all)
            clear = QPushButton("Clear all", frame)
            clear.clicked.connect(self._clear_rgb_all)
            layout.addWidget(set_all)
            layout.addWidget(clear)
            return frame

        if row["get"]:
            get = QPushButton("Get", frame)
            get.setProperty("role", "compact")
            get.clicked.connect(
                lambda _=False, r=row: self._get_setting(r))
            layout.addWidget(get)
        setter = QPushButton("Set", frame)
        setter.setProperty("role", "danger" if row["danger"] else "accent")
        setter.clicked.connect(lambda _=False, r=row: self._set_setting(r))
        layout.addWidget(setter)
        return frame

    def _editor_value(self, key):
        editor = self.settings_widgets.get(key)
        if isinstance(editor, QComboBox):
            return editor.currentText()
        return editor.text().strip() if editor else ""

    def _get_setting(self, row):
        args = list(row["get"])
        self.run_tool(lambda: self._get_setting_worker(row, args))

    def _get_setting_worker(self, row, args):
        rc, out = self._exec(args)
        self._append(out.strip() + "\n")
        if rc == 0:
            value = parse_setting_value(out)
            if value:
                self.sig_fill.emit(row["key"], value)

    def _on_fill(self, key, value):
        editor = self.settings_widgets.get(key)
        if isinstance(editor, QComboBox):
            index = editor.findText(value)
            if index >= 0:
                editor.setCurrentIndex(index)
        elif editor is not None:
            editor.setText(value)

    def _set_setting(self, row):
        value = self._editor_value(row["key"])
        if not value:
            self._warn("Nothing to set", "Enter a value first.")
            return
        args = list(row["set"]) + [value]
        if row["danger"] and not self._confirm_command(
                "Set {}".format(row["label"]), args,
                "The input deck carries the keyboard and trackpad. Switching "
                "it off leaves the machine without either until you set it "
                "back."):
            return
        self.run(args)

    def _set_rgb_all(self):
        hexval = self._editor_value("rgbkbd").lstrip("#") or "FF0000"
        self.run(["--rgbkbd", "0"] + ["0x{}".format(hexval)] * 8)

    def _clear_rgb_all(self):
        self.run(["--rgbkbd", "0"] + ["0"] * 8)

    # ---- CPU limits ----

    def _page_power(self, box, parent):
        vendor = self.cpu.get("vendor", power.VENDOR_UNKNOWN)
        backends = power.available_backends(
            vendor, "windows" if IS_WINDOWS else "linux",
            have=lambda dep_id: bool(self._which_dep(dep_id)),
            rapl_present=bool(power.rapl_constraint_files(rapl_zones())))
        self.power_backend = backends[0] if backends else None

        if not self.power_backend:
            self._heading(box, parent, "CPU power limits",
                          self._no_backend_reason(vendor))
            open_setup = QPushButton("Open the Setup section", parent)
            open_setup.setProperty("role", "accent")
            open_setup.clicked.connect(lambda: self._select_section("setup"))
            box.addWidget(open_setup, 0, Qt.AlignLeft)
            return

        meta = power.BACKENDS[self.power_backend]
        badge = widgets.Badge("Backend: {}".format(meta["label"]), "accent",
                              parent)
        self._heading(
            box, parent, "CPU power limits",
            "framework_tool cannot set these — the SoC owns them. "
            + meta["note"], badge=badge)

        panels = QHBoxLayout()
        panels.setSpacing(theme.SPACE[6])
        if meta["sets_watts"]:
            sustained = widgets.MetricPanel("Sustained (STAPM)", "W", True, parent)
            self.tdp_sustained = self._metric_field(sustained, "25")
            self.tdp_sustained.textChanged.connect(
                lambda t: sustained.bar.set_accent(
                    self._fraction(t, power.MAX_WATTS)))
            sustained.bar.set_accent(25 / power.MAX_WATTS)
            panels.addWidget(sustained)

            boost = widgets.MetricPanel("Boost (PPT fast)", "W", True, parent)
            self.tdp_boost = self._metric_field(boost, "35")
            self.tdp_boost.textChanged.connect(
                lambda t: boost.bar.set_accent(
                    self._fraction(t, power.MAX_WATTS)))
            boost.bar.set_accent(35 / power.MAX_WATTS)
            panels.addWidget(boost)

            if self.power_backend == "ryzenadj":
                tctl = widgets.MetricPanel("Temp limit (Tctl)", "C", True, parent)
                self.tdp_tctl = self._metric_field(tctl, "")
                self.tdp_tctl.setPlaceholderText("auto")
                self.tdp_tctl.textChanged.connect(
                    lambda t: tctl.bar.set_fraction(self._fraction(t, 110)))
                panels.addWidget(tctl)
        else:
            percent = widgets.MetricPanel("Max processor state", "%", True, parent)
            self.tdp_percent = self._metric_field(percent, "100")
            self.tdp_percent.textChanged.connect(
                lambda t: percent.bar.set_accent(self._fraction(t, 100)))
            percent.bar.set_accent(1.0)
            panels.addWidget(percent)
        panels.addStretch(1)
        box.addLayout(panels)

        if meta["sets_watts"]:
            presets = QHBoxLayout()
            presets.setSpacing(theme.SPACE[3])
            presets.addWidget(label("Presets", "caption", parent))
            self.preset_buttons = {}
            # Filling the fields only: applying is always a separate,
            # deliberate click, because these numbers are a guess at what
            # the machine likes, not a reading from it.
            for name, sustained_w, boost_w in (("Quiet 15 W", 15, 20),
                                               ("Balanced 25 W", 25, 35),
                                               ("Performance 45 W", 45, 60)):
                button = QPushButton(name, parent)
                button.setProperty("role", "preset")
                button.setProperty("selected", "false")
                button.clicked.connect(
                    lambda _=False, n=name, s=sustained_w, b=boost_w:
                    self._fill_tdp(n, s, b))
                presets.addWidget(button)
                self.preset_buttons[name] = button
            presets.addStretch(1)
            box.addLayout(presets)

        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE[3])
        apply_button = QPushButton("Apply limits", parent)
        apply_button.setProperty("role", "primary")
        apply_button.clicked.connect(self._apply_power)
        actions.addWidget(apply_button)
        read = QPushButton("Read current", parent)
        read.clicked.connect(self._read_power)
        actions.addWidget(read)
        restore = QPushButton("Restore previous", parent)
        restore.clicked.connect(self._restore_power)
        actions.addWidget(restore)
        actions.addStretch(1)
        box.addLayout(actions)

        # Only the real-wattage backends can push the SoC past what the
        # cooling carries. powercfg only ever caps frequency downward.
        if meta["sets_watts"]:
            box.addWidget(self._notice(
                parent, "dangerNotice", "dangerText",
                "Raising limits beyond what the cooling can carry can "
                "destabilise the machine; if it locks up, reboot and it "
                "comes back at stock.", icon_token="danger.subtle.text"))

        volatile = power.is_volatile(self.power_backend)
        notice_text = (
            "Volatile: a reboot clears this, and sleep or an AC/battery "
            "change often does too. This app starts no background service "
            "to re-apply it. "
            if volatile else
            "Persistent: this one survives a reboot on its own. "
        ) + power.persistence_note(self.power_backend)
        links = power.persistence_links(
            self.power_backend, "windows" if IS_WINDOWS else "linux")
        box.addWidget(self._notice(parent, "warnNotice", "warnText",
                                   notice_text, links=links))

    def _notice(self, parent, object_name, role, text, links=(),
                icon_token=None):
        frame = QFrame(parent)
        frame.setObjectName(object_name)
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(theme.SPACE[4])
        if icon_token:
            icon = QLabel(frame)
            icon.setPixmap(widgets.stroke_pixmap(
                ("M8 1.5 15 14H1z", "M8 6v4", "M8 11.8v.4"),
                colour(icon_token), 14))
            row.addWidget(icon, 0, Qt.AlignTop)
        body = label(text, role, frame)
        body.setWordWrap(True)
        row.addWidget(body, 1)
        for link_label, url in links:
            button = QPushButton(link_label, frame)
            button.setProperty("role", "compact")
            button.clicked.connect(lambda _=False, u=url: self._open_url(u))
            row.addWidget(button, 0, Qt.AlignVCenter)
        return frame

    def _no_backend_reason(self, vendor):
        if vendor == power.VENDOR_AMD:
            return ("No power-limit backend available. RyzenAdj is not "
                    "installed — install it from the Setup section, then "
                    "rescan.")
        if vendor == power.VENDOR_INTEL:
            if IS_LINUX:
                return ("No power-limit backend available. This kernel is not "
                        "exposing RAPL powercap zones under "
                        "{}.".format(power.RAPL_ROOT))
            return "No power-limit backend available on this machine."
        if vendor == power.VENDOR_ARM:
            return ("ARM CPUs have no power-limit tool this app can drive — "
                    "there is no RyzenAdj or RAPL equivalent to shell out to.")
        return ("CPU vendor could not be determined, so no power-limit "
                "backend was selected. Rescan the device, or check the "
                "Setup section for what is installed.")

    def _fill_tdp(self, name, sustained, boost):
        self.tdp_sustained.setText(str(sustained))
        self.tdp_boost.setText(str(boost))
        self._preset = name
        for label_text, button in self.preset_buttons.items():
            button.setProperty("selected",
                               "true" if label_text == name else "false")
            widgets.restyle(button)

    def _apply_power(self):
        backend = self.power_backend
        try:
            if backend == "ryzenadj":
                tctl = getattr(self, "tdp_tctl", None)
                tctl = (tctl.text().strip() or None) if tctl else None
                args = power.ryzenadj_args(self.tdp_sustained.text(),
                                           self.tdp_boost.text(), tctl)
            elif backend == "rapl":
                sustained = power.check_watts(self.tdp_sustained.text())
                boost = power.check_watts(self.tdp_boost.text())
            else:
                percent = power.check_percent(self.tdp_percent.text())
        except power.PowerError as e:
            self._warn("Not applied", str(e))
            return

        if backend == "ryzenadj":
            binary = self._which_dep("ryzenadj")
            if not self._confirm_command(
                    "Apply power limits", [binary or "ryzenadj"] + args,
                    "Raising limits beyond what the cooling can carry can "
                    "destabilise the machine."):
                return
            self.run_tool(lambda: self._power_tool_ryzenadj(binary, args))
        elif backend == "rapl":
            if not self._confirm_command(
                    "Apply power limits",
                    ["sh", "-c", "echo … > {}/…".format(power.RAPL_ROOT)],
                    "Writes the kernel's powercap limits for every package "
                    "zone."):
                return
            self.run_tool(lambda: self._power_tool_rapl(sustained, boost))
        else:
            if not self._confirm_command(
                    "Cap the processor state", power.powercfg_cmds(percent)[0],
                    "Applied to both the AC and battery profiles of the "
                    "active power scheme."):
                return
            self.run_tool(lambda: self._power_tool_powercfg(percent))

    def _power_tool_ryzenadj(self, binary, args):
        self._append("=== Applying AMD power limits (RyzenAdj) ===\n")
        rc, out = self._exec_external([binary] + args)
        self._append(out.strip() + "\n")
        if rc != 0:
            self._append("RyzenAdj exited {} — limits may not have been "
                         "applied.\n".format(rc))
            return
        self._append("\nReading back what stuck:\n")
        rc, info = self._exec_external([binary, "-i"])
        table = power.parse_ryzenadj_info(info)
        if table:
            for key in ("STAPM LIMIT", "PPT LIMIT FAST", "PPT LIMIT SLOW",
                        "THM LIMIT CORE"):
                if key in table:
                    self._append("  {}: {:.1f}\n".format(key, table[key]))
        else:
            self._append(info.strip() + "\n")

    def _power_tool_rapl(self, sustained, boost):
        self._append("=== Applying RAPL power limits ===\n")
        zones = power.rapl_constraint_files(rapl_zones())
        if not zones:
            self._append("No powercap package zones under {}.\n".format(
                power.RAPL_ROOT))
            return
        for zone in zones:
            for name, watts in (("long", sustained), ("short", boost)):
                path = zone[name]
                if not os.path.exists(path):
                    continue
                self._power_saved.setdefault(path, read_text_file(path))
                rc, out = self._exec_external(power.rapl_write_cmd(path, watts))
                status = "ok" if rc == 0 else "failed (exit {}) {}".format(
                    rc, out.strip())
                self._append("  {} {} -> {} W: {}\n".format(
                    zone["zone"], name, watts, status))
        self._append("\n")
        self._read_rapl()

    def _power_tool_powercfg(self, percent):
        self._append(
            "=== Capping maximum processor state at {}% ===\n".format(percent))
        if not self._power_saved.get("powercfg"):
            rc, out = self._exec_external(power.powercfg_query_cmd(),
                                          elevate=False)
            current = power.parse_powercfg_percent(out)
            if current is not None:
                self._power_saved["powercfg"] = current
        for cmd in power.powercfg_cmds(percent):
            rc, out = self._exec_external(cmd, elevate=False)
            if rc != 0:
                self._append("  {} -> exit {}\n{}\n".format(
                    " ".join(cmd), rc, out.strip()))
                return
        self._append("Applied to both the AC and battery profiles of the "
                     "active power scheme.\n")

    def _read_power(self):
        backend = self.power_backend
        if backend == "ryzenadj":
            binary = self._which_dep("ryzenadj")
            self.run_tool(lambda: self._read_ryzenadj(binary))
        elif backend == "rapl":
            self.run_tool(self._read_rapl)
        else:
            self.run_tool(self._read_powercfg)

    def _read_ryzenadj(self, binary):
        self._append("=== Current AMD power limits ===\n")
        rc, out = self._exec_external([binary, "-i"])
        table = power.parse_ryzenadj_info(out)
        # Same fallback rule as every framework_tool parser here: show the
        # raw text rather than nothing when the format has moved on.
        self._append("".join("  {}: {}\n".format(k, v)
                             for k, v in table.items())
                     if table else out.strip() + "\n")

    def _read_rapl(self):
        self._append("=== Current RAPL limits ===\n")
        for zone in power.rapl_constraint_files(rapl_zones()):
            for name in ("long", "short"):
                watts = power.parse_rapl_uw(read_text_file(zone[name]))
                if watts is not None:
                    self._append("  {} {}: {:.1f} W\n".format(
                        zone["zone"], name, watts))

    def _read_powercfg(self):
        self._append("=== Current maximum processor state ===\n")
        rc, out = self._exec_external(power.powercfg_query_cmd(),
                                      elevate=False)
        percent = power.parse_powercfg_percent(out)
        self._append("  AC: {}%\n".format(percent) if percent is not None
                     else out.strip() + "\n")

    def _restore_power(self):
        if not self._power_saved:
            self._warn(
                "Nothing saved",
                "No limits have been changed in this session.\n\n"
                "RyzenAdj has no 'restore defaults' command — a reboot puts "
                "the SoC back to stock.")
            return
        self.run_tool(self._restore_power_tool)

    def _restore_power_tool(self):
        self._append("=== Restoring the limits found at startup ===\n")
        for key, value in list(self._power_saved.items()):
            if key == "powercfg":
                for cmd in power.powercfg_cmds(value):
                    self._exec_external(cmd, elevate=False)
                self._append("  max processor state -> {}%\n".format(value))
                continue
            watts = power.parse_rapl_uw(value)
            if watts is None:
                continue
            rc, _out = self._exec_external(power.rapl_write_cmd(key, watts))
            self._append("  {} -> {:.1f} W {}\n".format(
                key, watts, "ok" if rc == 0 else "failed"))
        self._power_saved.clear()

    # ---- Drivers ----

    def _page_drivers(self, box, parent):
        self._heading(
            box, parent, "Drivers & BIOS",
            "Framework publishes one downloads list per device build, always "
            "carrying the current BIOS and driver bundle. These are links — "
            "nothing is downloaded here.")
        entry = drivers.resource_for(self.caps.get("model", ""))
        self.driver_entry = entry
        panel = widgets.Panel(parent)

        panel.body.addWidget(section_label("This system", panel))
        this_row = QHBoxLayout()
        this_row.setSpacing(theme.SPACE[6])
        this_button = QPushButton(entry["label"], panel)
        this_button.setProperty("role", "accent")
        this_button.clicked.connect(
            lambda _=False, u=entry["url"]: self._open_url(u))
        this_row.addWidget(this_button)
        explanation = label(
            "Opens Framework's downloads list for this build."
            if entry["exact"] else
            "This board was not matched to a specific build, so this is the "
            "index of every downloads list.", "caption", panel)
        explanation.setWordWrap(True)
        this_row.addWidget(explanation, 1)
        panel.body.addLayout(this_row)
        panel.body.addWidget(rule(panel))

        panel.body.addWidget(section_label("Every device build", panel))
        every_row = QHBoxLayout()
        every_row.setSpacing(theme.SPACE[6])
        self.driver_all = drivers.all_resources()
        self.driver_choice = QComboBox(panel)
        self.driver_choice.setFixedWidth(340)
        for item in self.driver_all:
            self.driver_choice.addItem(item["label"], item["url"])
        index = self.driver_choice.findText(entry["label"])
        if index >= 0:
            self.driver_choice.setCurrentIndex(index)
        every_row.addWidget(self.driver_choice)
        open_button = QPushButton("Open downloads list", panel)
        open_button.clicked.connect(self._open_selected_driver_page)
        every_row.addWidget(open_button)
        every_row.addStretch(1)
        panel.body.addLayout(every_row)
        panel.body.addWidget(rule(panel))

        panel.body.addWidget(section_label("Parts you added yourself", panel))
        for extra in drivers.extras_for(self.cpu.get("vendor")):
            row = QHBoxLayout()
            row.setSpacing(theme.SPACE[6])
            name = label(extra["label"], "cell", panel)
            name.setFixedWidth(300)
            row.addWidget(name)
            why = label(extra["why"], "caption", panel)
            why.setWordWrap(True)
            row.addWidget(why, 1)
            open_extra = QPushButton("Open", panel)
            open_extra.setProperty("role", "link")
            open_extra.clicked.connect(
                lambda _=False, u=extra["url"]: self._open_url(u))
            row.addWidget(open_extra)
            panel.body.addLayout(row)
        box.addWidget(panel)

    def _open_selected_driver_page(self):
        url = self.driver_choice.currentData()
        if url:
            webbrowser.open(url)
            self.set_status("Opened {}".format(url))

    def _open_url(self, url):
        webbrowser.open(url)
        self.set_status("Opened {}".format(url))

    # ---- Setup ----

    def _page_setup(self, box, parent):
        self._heading(
            box, parent, "Setup",
            "This app only ever runs other programs. Nothing is installed "
            "without you clicking Install and confirming the exact command "
            "first.")
        os_name = "windows" if IS_WINDOWS else "linux"
        manager = deps.linux_manager(shutil.which) if IS_LINUX else None
        for dep in deps.relevant(os_name, self.cpu.get("vendor")):
            found = deps.find(dep, self._which)
            plan = deps.install_plan(dep, os_name, manager)
            panel = widgets.Panel(parent)
            header = QHBoxLayout()
            header.setSpacing(theme.SPACE[4])
            header.addWidget(label(dep["name"], "name", panel))
            header.addWidget(widgets.Badge(found or "not found",
                                           "ok" if found else "danger", panel))
            header.addStretch(1)
            install = QPushButton("Reinstall" if found else "Install", panel)
            install.setProperty("role", "accent")
            install.clicked.connect(
                lambda _=False, d=dep, p=plan: self._install_dep(d, p))
            header.addWidget(install)
            homepage = QPushButton("Homepage", panel)
            homepage.clicked.connect(
                lambda _=False, u=dep["homepage"]: self._open_url(u))
            header.addWidget(homepage)
            panel.body.addLayout(header)
            why = label(dep["why"], "caption", panel)
            why.setWordWrap(True)
            panel.body.addWidget(why)
            panel.body.addWidget(label(plan["summary"], "mono", panel))
            box.addWidget(panel)

        recheck = QPushButton("Re-check what is installed", parent)
        recheck.clicked.connect(self._rescan)
        box.addWidget(recheck, 0, Qt.AlignLeft)

    def _install_dep(self, dep, plan):
        note = "\n\nNote: {}".format(plan["note"]) if plan.get("note") else ""
        if plan["kind"] == deps.KIND_MANUAL:
            if self._ask("Install {}".format(dep["name"]),
                         "{} has no automated install here.\n\n"
                         "Open {} in your browser?{}".format(
                             dep["name"], plan["url"], note)):
                webbrowser.open(plan["url"])
            return
        if not self._ask("Install {}".format(dep["name"]),
                         "This will run:\n\n  {}{}\n\nProceed?".format(
                             plan["summary"], note)):
            return
        if plan["kind"] == deps.KIND_DOWNLOAD:
            self.run_tool(lambda: self._download_dep(dep, plan))
        else:
            self.run_tool(lambda: self._package_install(dep, plan))

    def _package_install(self, dep, plan):
        stream = os.path.basename(plan["cmd"][0])
        self._log(stream, "=== Installing {} ===\n$ {}\n\n".format(
            dep["name"], plan["summary"]), "command")
        rc, out = self._exec_external(plan["cmd"], timeout=900, stream=stream)
        self._log(stream, out.strip() + "\n")
        self._log(stream, "\nExit {}. ".format(rc)
                  + ("Installed.\n" if rc == 0 else "Install failed — see "
                     "above.\n"), "ok" if rc == 0 else "warn")

    def _download_dep(self, dep, plan):
        """Fetch a helper's latest release from GitHub into the tools dir."""
        self._append("=== Downloading {} ===\n".format(dep["name"]))
        dest = deps.tools_dir()
        try:
            body = deps.fetch_text(deps.github_latest_api(plan["repo"]),
                                   timeout=30)
            release = json.loads(body)
            asset = deps.pick_asset(release.get("assets"), plan["asset_match"])
            if not asset:
                raise RuntimeError(
                    "No asset matching '{}' in {}".format(
                        plan["asset_match"],
                        release.get("tag_name", "the latest release")))
            self._append("{}: {}\n".format(release.get("tag_name", "?"),
                                           asset["name"]))
            archive = deps.download_file(
                asset["browser_download_url"], dest,
                progress=self._download_progress)
            self._append("Downloaded to {}\n".format(archive))
            if archive.lower().endswith(".zip"):
                deps.extract_zip(archive, dest)
                self._append("Unpacked into {}\n".format(dest))
            binary = plan.get("binary")
            found = deps.find_in_tree(dest, binary) if binary else None
            self._append("{} is at {}\n".format(dep["name"], found) if found
                         else "Unpacked, but {} was not found in {}.\n".format(
                             binary, dest))
        except Exception as e:  # noqa: BLE001
            # Any failure ends the same way: hand over the page and let the
            # user do it by hand, rather than leaving them stuck.
            self._append("Automatic download failed: {}\n\n"
                         "Open {} and install it manually.\n".format(
                             e, dep["homepage"]))

    def _download_progress(self, done, total):
        if total:
            self.set_status("Downloading… {}% ({} of {} MB)".format(
                done * 100 // total, done // 1024 // 1024,
                total // 1024 // 1024))
        else:
            self.set_status("Downloading… {} MB".format(done // 1024 // 1024))

    # ---- Custom command ----

    def _page_console(self, box, parent):
        self._heading(
            box, parent, "Custom command",
            "Arguments are passed straight to framework_tool. The flash and "
            "force flags are blocked here — use the CLI for those.")
        panel = widgets.Panel(parent)

        entry_row = QHBoxLayout()
        entry_row.setSpacing(theme.SPACE[4])
        entry_row.addWidget(label("framework_tool", "mono", panel))
        self.custom = QLineEdit(panel)
        self.custom.setProperty("role", "mono")
        self.custom.setPlaceholderText("--versions")
        self.custom.returnPressed.connect(self._run_custom)
        entry_row.addWidget(self.custom, 1)
        run = QPushButton("Run", panel)
        run.setProperty("role", "accent")
        run.clicked.connect(self._run_custom)
        entry_row.addWidget(run)
        panel.body.addLayout(entry_row)

        recent = QHBoxLayout()
        recent.setSpacing(theme.SPACE[3])
        recent.addWidget(label("Recent", "caption", panel))
        for suggestion in navigation.RECENT_SUGGESTIONS:
            chip = QPushButton(suggestion, panel)
            chip.setProperty("role", "link")
            chip.clicked.connect(
                lambda _=False, s=suggestion: self.custom.setText(s))
            recent.addWidget(chip)
        recent.addStretch(1)
        panel.body.addLayout(recent)
        panel.body.addWidget(rule(panel))

        bottom = QHBoxLayout()
        bottom.setSpacing(theme.SPACE[4])
        console = QPushButton("EC console (recent)", panel)
        console.clicked.connect(lambda: self.run(["--console", "recent"]))
        bottom.addWidget(console)
        bottom.addWidget(label(
            "Blocked: --flash-ec, --flash-ro-ec, --flash-rw-ec, --force",
            "caption", panel))
        bottom.addStretch(1)
        panel.body.addLayout(bottom)
        box.addWidget(panel)

        binary_panel = widgets.Panel(parent)
        binary_panel.body.addWidget(section_label("framework_tool binary",
                                                  binary_panel))
        binary_row = QHBoxLayout()
        binary_row.setSpacing(theme.SPACE[4])
        self.binary_field = QLineEdit(self.binary, binary_panel)
        self.binary_field.setProperty("role", "mono")
        self.binary_field.textChanged.connect(self._set_binary)
        binary_row.addWidget(self.binary_field, 1)
        binary_row.addWidget(label(
            "Where the CLI lives. Inside the Flatpak this is resolved on the "
            "host.", "caption", binary_panel), 1)
        binary_panel.body.addLayout(binary_row)
        box.addWidget(binary_panel)

    def _set_binary(self, text):
        self.binary = text.strip() or "framework_tool"
        self._refresh_statusbar()

    # ================= device detection =================

    def _rescan(self):
        if self._busy:
            self.set_status("Busy — wait or cancel the running tool.")
            return
        self._busy = True
        self.set_status("Scanning device…")
        threading.Thread(target=self._detect_worker, daemon=True).start()

    def _detect_worker(self):
        rc, out = self._exec(["--versions"], timeout=15, echo=False)
        if rc != 0 or not out.strip():
            caps = dict(self.caps)
            caps.update(model="Unknown (detection failed)", detected=False)
            firmware = {"ec": "", "bios": ""}
        else:
            caps = detect_model(out)
            firmware = parse_firmware(out)
        _rc, version_text = self._exec(["--version"], timeout=10, echo=False)
        extras = {
            "firmware": firmware,
            "tool_version": parse_tool_version(version_text),
        }
        self.sig_detected.emit(caps, detect_cpu(), extras)

    def _apply_detection(self, caps, cpu, extras):
        self.caps = caps
        self.cpu = cpu
        self.firmware = extras["firmware"]
        self.tool_version = extras["tool_version"]
        self._busy = False
        if caps["detected"]:
            self.set_status("Device scan complete.")
        else:
            self.set_status(
                "Could not identify the device model — showing all controls.")
        self._build_pages()
        self._refresh_statusbar()
        # Sensor readings need three more commands. Running them
        # automatically when elevated costs nothing; behind pkexec it would
        # mean three extra password prompts on every launch, so there it
        # waits for the user to ask.
        if is_root():
            self._read_sensors()

    # ---- Overview readings ----

    def _read_sensors(self):
        if self._busy:
            self.set_status("Busy — wait or cancel the running tool.")
            return
        self.run_tool(self._readings_worker)

    def _readings_worker(self):
        self._append("=== Reading sensors ===\n")
        readings = {}
        if self.caps.get("is_laptop"):
            rc, out = self._exec(["--power", "-vv"])
            if rc == 0:
                readings["power"] = out
            rc, out = self._exec(["--charge-limit"])
            if rc == 0:
                readings["charge_limit"] = out
        rc, out = self._exec(["--thermal"])
        if rc == 0:
            readings["thermal"] = out
        rc, out = self._exec(["--pdports"])
        if rc == 0:
            readings["ports"] = parse_ports(out)
        if self.caps.get("has_expansion_bay"):
            rc, out = self._exec(["--expansion-bay"])
            if rc == 0:
                readings["expansion_bay"] = out
        self.sig_readings.emit(readings)

    def _apply_readings(self, readings):
        self.readings.update(readings)
        self._refresh_device_image()
        self._fill_stat_cards()
        self._fill_sensors()
        self._render_ports()
        self._fill_bays()
        self._refresh_statusbar()

    def _fill_stat_cards(self):
        power_text = self.readings.get("power", "")
        thermal = self.readings.get("thermal", "")
        soc = RE_SOC.search(power_text)
        lfcc = RE_LFCC.search(power_text)
        design = RE_DESIGN.search(power_text)
        cycles = RE_CYCLES.search(power_text)
        ac = RE_AC.search(power_text)
        rpm = RE_RPM.search(thermal)
        temps = RE_TEMP.findall(thermal)

        battery = []
        if soc:
            battery.append("{}%".format(soc.group(1)))
        if lfcc and design and int(design.group(1)):
            battery.append("{:.1f}% health".format(
                100.0 * int(lfcc.group(1)) / int(design.group(1))))
        self.stat_cards["battery"].set_value(" · ".join(battery) or "—")
        self.stat_cards["cpu"].set_value(self._cpu_temp(temps))
        self.stat_cards["fan"].set_value(
            "{} RPM".format(rpm.group(1)) if rpm else "—")
        self.stat_cards["charge_limit"].set_value(
            parse_setting_value(self.readings.get("charge_limit", "")) + "%"
            if self.readings.get("charge_limit") else "—")
        self.stat_cards["ac"].set_value(self._ac_summary(ac, power_text))
        self.stat_cards["cycles"].set_value(
            cycles.group(1) if cycles else "—")

    @staticmethod
    def _cpu_temp(temps):
        """The package temperature from `--thermal`'s sensor list.

        Sensor names differ per board, so this prefers one that names the
        CPU and otherwise reports the hottest — which is the number someone
        looking at a "CPU package" card actually wants.
        """
        if not temps:
            return "—"
        for name, value in temps:
            if any(tag in name.lower() for tag in ("cpu", "apu", "tctl")):
                return "{} C".format(value)
        return "{} C".format(max(int(v) for _n, v in temps))

    @staticmethod
    def _ac_summary(ac, power_text):
        volts = RE_CHG_V.search(power_text)
        amps = RE_IN_A.search(power_text)
        if volts and amps:
            return "{:.1f} W measured".format(
                int(volts.group(1)) * int(amps.group(1)) / 1e6)
        return ac.group(1).strip() if ac else "—"

    def _fill_sensors(self):
        thermal = self.readings.get("thermal", "")
        temps = RE_TEMP.findall(thermal)
        if not temps:
            return
        self.sensor_empty.setVisible(False)
        for name, value in temps:
            if name not in self.sensor_rows:
                row = widgets.SensorRow(name)
                self.sensor_holder.addWidget(row)
                self.sensor_rows[name] = row
            self.sensor_rows[name].set_reading(
                "{} C".format(value), int(value) / TEMP_SCALE_C)

    def _fill_bays(self):
        """Paint the four bay rows from what --pdports and friends reported.

        framework_tool does not name the card in each bay on every board, so
        the type is classified from whatever description we do have and
        falls back to the neutral module mark. The row is still useful
        without it: the role and negotiated wattage are the reading people
        come here for.
        """
        ports = self.readings.get("ports") or []
        hints = self.readings.get("module_hints") or {}
        states = []
        for index, (icon, name, detail) in enumerate(self.module_rows):
            port = ports[index] if index < len(ports) else None
            if port is None:
                states.append("empty")
                icon.set_module(module_icons.UNKNOWN, token="icon")
                detail.setText("not read")
                continue
            role = (port.get("role") or "?").lower()
            watts = port.get("watts")
            if watts and role == "sink":
                state, token = "sink", "accent.bright"
            elif watts:
                state, token = "source", "ok.bar"
            else:
                state, token = "idle", "warn"
            states.append(state)
            # A bay that negotiated a PD contract has a USB-C card in it:
            # an HDMI or microSD card never negotiates one. That is the only
            # module identity --pdports actually supports, so it is the only
            # one inferred here; `module_hints` is where a real per-bay
            # identification would feed in once the CLI reports one.
            hint = hints.get(str(port["port"])) or ("usb-c" if watts else "")
            module_type = module_icons.classify(hint)
            icon.set_module(module_type, module_icons.capacity(hint), token)
            name.setText(self._module_name(module_type, port["port"]))
            detail.setText("{}{}".format(
                role, " · {:.1f} W".format(watts) if watts else " · idle"))
        self.chassis.set_states(states)

    @staticmethod
    def _module_name(module_type, port):
        """A row title: the module where it is known, the port where it is not."""
        names = {
            module_icons.USB_C: "USB-C", module_icons.USB_A: "USB-A",
            module_icons.HDMI: "HDMI",
            module_icons.DISPLAYPORT: "DisplayPort",
            module_icons.MICROSD: "microSD", module_icons.SD: "SD",
            module_icons.ETHERNET: "Ethernet",
            module_icons.AUDIO: "Audio", module_icons.STORAGE: "Storage",
        }
        return names.get(module_type, "Port {}".format(port))

    # ================= command plumbing =================

    def _build_cmd(self, args):
        cmd = [self.binary.strip() or "framework_tool"] + list(args)
        if IS_LINUX and self.use_pkexec and not is_root():
            cmd = ["pkexec"] + cmd
        if IN_FLATPAK:
            cmd = ["flatpak-spawn", "--host"] + cmd
        return cmd

    def _exec(self, args, timeout=60, echo=True):
        """Synchronous — only call from worker threads. Returns (rc, text)."""
        cmd = self._build_cmd(args)
        if echo:
            self._log("framework_tool", "$ {}\n".format(" ".join(cmd)),
                      "command")
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout)
            return p.returncode, (p.stdout or "") + \
                (("\n" + p.stderr) if p.stderr else "")
        except FileNotFoundError:
            return 127, "Binary not found: {}".format(cmd[0])
        except subprocess.TimeoutExpired:
            return 124, "Command timed out."
        except Exception as e:  # noqa: BLE001
            return 1, "Error: {}".format(e)

    # ---- other programs (helper tools, package managers, powercfg) ----
    #
    # framework_tool goes through _build_cmd/_exec, which prefix the binary
    # from the Console pane. Everything on the CPU limits/Setup panes is a
    # *different* program, so it needs its own path: same pkexec and
    # flatpak-spawn wrapping, no framework_tool binary in front of it.

    def _which(self, name):
        """shutil.which, extended with helpers this app downloaded itself."""
        found = shutil.which(name)
        if found:
            return found
        tools = deps.tools_dir()
        if not os.path.isdir(tools):
            return None
        for candidate in (name, name + ".exe"):
            direct = os.path.join(tools, candidate)
            if os.path.isfile(direct):
                return direct
            nested = deps.find_in_tree(tools, candidate)
            if nested:
                return nested
        return None

    def _which_dep(self, dep_id):
        try:
            return deps.find(deps.get(dep_id), self._which)
        except KeyError:
            return None

    def _build_external(self, cmd, elevate=True):
        out = list(cmd)
        if IS_LINUX and elevate and self.use_pkexec and not is_root():
            out = ["pkexec"] + out
        if IN_FLATPAK:
            out = ["flatpak-spawn", "--host"] + out
        return out

    def _exec_external(self, cmd, timeout=120, elevate=True, stream=None):
        """Synchronous — worker threads only. Returns (rc, text)."""
        full = self._build_external(cmd, elevate=elevate)
        target = stream or os.path.basename(str(cmd[0]) or "external")
        self._log(target, "$ {}\n".format(" ".join(str(c) for c in full)),
                  "command")
        try:
            p = subprocess.run(full, capture_output=True, text=True,
                               timeout=timeout)
            return p.returncode, (p.stdout or "") + \
                (("\n" + p.stderr) if p.stderr else "")
        except FileNotFoundError:
            return 127, "Not found: {}".format(full[0])
        except subprocess.TimeoutExpired:
            return 124, "Command timed out."
        except Exception as e:  # noqa: BLE001
            return 1, "Error: {}".format(e)

    def _run_custom(self):
        args = self.custom.text().split()
        if not args:
            return
        blocked = self.BLOCKED.intersection(args)
        if blocked:
            self._warn("Blocked",
                       "{} can brick hardware and is disabled here. Use the "
                       "CLI directly.".format(", ".join(sorted(blocked))))
            return
        if "--console" in args and "follow" in args:
            self._warn("Blocked", "--console follow never exits; use 'recent'.")
            return
        self.run(args)

    def run(self, args):
        """Single command → echoed into the drawer with its output."""
        if self._busy:
            self.set_status("Busy — wait or cancel the running tool.")
            return
        self._busy = True
        self.set_status("Running: " + " ".join(self._build_cmd(args)))
        threading.Thread(target=self._single_worker, args=(list(args),),
                         daemon=True).start()

    def _single_worker(self, args):
        rc, text = self._exec(args)
        self._log("framework_tool", text.strip() + "\n",
                  "output" if rc == 0 else "warn")
        self.sig_status.emit("Done (exit {})".format(rc))
        self.sig_tool_done.emit()

    # ---- tool (multi-step) plumbing ----

    def _start_tool_by_key(self, key):
        for tool in navigation.TOOLS:
            if tool["key"] == key:
                self._start_tool(tool)
                return

    def _start_tool(self, tool):
        method = getattr(self, "tool_" + tool["key"], None)
        if method is None:
            method = {
                "preset_longevity": lambda: self.tool_preset(80, "0.8"),
                "preset_full": lambda: self.tool_preset(100, "1"),
            }.get(tool["key"])
        if method is None:
            return
        if tool.get("danger") and not self._confirm_command(
                tool["label"], self._build_cmd(["--fansetduty", "100"]),
                "Runs the fan at full duty for 30 seconds, then restores "
                "automatic control."):
            return
        self._current_tool = tool
        if tool["steps"]:
            self.tool_detail.begin(tool["label"], tool["steps"])
        else:
            self.tool_detail.setVisible(False)
        frame = self.tool_rows.get(tool["key"])
        if frame is not None:
            frame.setProperty("running", "true")
            widgets.restyle(frame)
        self.run_tool(method)

    def run_tool(self, fn):
        if self._busy:
            self.set_status("Busy — wait or cancel the running tool.")
            return
        self._busy = True
        self._cancel = False
        threading.Thread(target=self._tool_worker, args=(fn,),
                         daemon=True).start()

    def _tool_worker(self, fn):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self._append("\nTool error: {}\n".format(e))
        finally:
            self.sig_tool_done.emit()

    def _tool_done(self):
        self._busy = False
        self.set_status("Tool finished." if not self._cancel
                        else "Tool cancelled.")
        if hasattr(self, "tool_detail"):
            self.tool_detail.finish()
        current = getattr(self, "_current_tool", None)
        if current:
            frame = self.tool_rows.get(current["key"])
            if frame is not None:
                frame.setProperty("running", "false")
                widgets.restyle(frame)
            self._current_tool = None

    def _request_cancel(self):
        self._cancel = True
        self.set_status("Cancelling after current step…")

    def _sleep(self, seconds):
        """Interruptible sleep; returns False if cancelled."""
        end = time.time() + seconds
        while time.time() < end:
            if self._cancel:
                return False
            time.sleep(0.2)
        return True

    # ---- output ----

    def _append(self, text):
        self._log("framework_tool", text)

    def _log(self, stream, text, kind="output"):
        self.sig_log.emit(stream, text, kind)

    def _on_log(self, stream, text, kind):
        self.drawer.append(stream, text, kind)

    def set_status(self, msg):
        self.sig_status.emit(msg)

    def _on_status(self, msg):
        self.status_message.setText(msg)

    def _progress(self, index, step, total, name, value, fraction):
        self.sig_progress.emit(
            {"index": index, "step": step, "total": total, "name": name,
             "value": value, "fraction": fraction})

    def _on_progress(self, payload):
        self.tool_detail.update_step(
            payload["index"], payload["step"], payload["total"],
            payload["name"], payload["value"], payload["fraction"])

    # ---- dialogs ----

    def _warn(self, title, text):
        QMessageBox.warning(self, title, text)

    def _ask(self, title, text):
        return QMessageBox.question(
            self, title, text,
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

    def _confirm_command(self, title, cmd, why):
        """Confirm a risky action, naming the exact command it will run."""
        return self._ask(title, "{}\n\nThis will run:\n\n  {}\n\nProceed?"
                         .format(why, " ".join(str(c) for c in cmd)))

    def _enable_pkexec(self):
        self.use_pkexec = True
        self.banner.setVisible(False)
        self._refresh_statusbar()
        self.set_status("Commands will be run through pkexec.")

    def _dismiss_banner(self):
        # Session only: it comes back on relaunch while still unelevated,
        # because the reason for it has not gone away.
        self.banner_dismissed = True
        self.banner.setVisible(False)

    # ================= tools =================

    def tool_input_power(self):
        self._append("=== Power input wattage ===\n")
        rc, power_text = self._exec(["--power", "-vv"])
        if rc != 0:
            self._append(power_text + "\n")
            return
        rc2, pdout = self._exec(["--pdports"])
        ac = RE_AC.search(power_text)
        v = RE_CHG_V.search(power_text)
        chg = RE_CHG_A.search(power_text)
        inp = RE_IN_A.search(power_text)
        soc = RE_SOC.search(power_text)
        if ac:
            self._append("AC: {}\n".format(ac.group(1).strip()))
        if soc:
            self._append("Battery SoC: {}%\n".format(soc.group(1)))
        if rc2 == 0:
            for p in parse_ports(pdout):
                if p.get("watts") and p["role"] == "Sink":
                    self._append(
                        "Port {}: adapter contract {:.1f} V × {} mA = "
                        "{:.1f} W max\n".format(p["port"], p["volts"], p["ma"],
                                                p["watts"]))
        if v and inp:
            est = int(v.group(1)) * int(inp.group(1)) / 1e6
            self._append("Measured input draw (est.): {:.1f} W "
                         "({} mV × {} mA)\n".format(est, v.group(1),
                                                    inp.group(1)))
        if v and chg:
            bw = int(v.group(1)) * int(chg.group(1)) / 1e6
            self._append("Battery charge power: {:.1f} W\n".format(bw))
        if not (v and (inp or chg)):
            self._append("Could not parse charger values — raw output:\n"
                         + power_text + "\n")

    def tool_fan_test(self):
        self._append("=== Fan speed test (0→100% duty) ===\n"
                     "Each step: set duty, wait 8 s for spin-up, read RPM.\n\n")
        results = []
        duties = (0, 25, 50, 75, 100)
        try:
            for index, duty in enumerate(duties):
                if self._cancel:
                    break
                rc, out = self._exec(["--fansetduty", str(duty)])
                if rc != 0:
                    self._append("Set duty {}% failed:\n{}\n".format(duty, out))
                    break
                self._append("Duty {:3d}% … ".format(duty))
                self._progress(index, index + 1, len(duties),
                               "{}%".format(duty), "…", 0)
                if not self._sleep(8):
                    self._append("cancelled\n")
                    break
                rc, out = self._exec(["--thermal"])
                m = RE_RPM.search(out)
                rpm = int(m.group(1)) if m else None
                results.append((duty, rpm))
                self._append("{} RPM\n".format(rpm if rpm is not None else "??"))
                self._progress(index, index + 1, len(duties),
                               "{}%".format(duty),
                               str(rpm) if rpm is not None else "??",
                               (rpm or 0) / FAN_SCALE_RPM)
        finally:
            self._exec(["--autofanctrl"])
            self._append("\nAutomatic fan control restored.\n")
        if len(results) >= 2:
            rpms = [r for _, r in results if r is not None]
            if rpms:
                self._append("Range observed: {}–{} RPM\n".format(min(rpms),
                                                                  max(rpms)))
            if results[-1][0] == 100 and results[-1][1] in (None, 0):
                self._append("WARNING: no RPM at 100% duty — fan may be "
                             "faulty/absent.\n")

    def tool_fan_burst(self):
        self._append("=== Fan max burst ===\nFull duty for 30 s, then auto.\n")
        rc, out = self._exec(["--fansetduty", "100"])
        if rc != 0:
            self._append(out + "\n")
            return
        try:
            for index, remaining in enumerate(range(30, 0, -5)):
                self._append("{} s…\n".format(remaining))
                self._progress(index, index + 1, 6, "remaining",
                               "{} s".format(remaining), 1 - remaining / 30.0)
                if not self._sleep(5):
                    break
        finally:
            self._exec(["--autofanctrl"])
            self._append("Automatic fan control restored.\n")

    def tool_battery_health(self):
        self._append("=== Battery health report ===\n")
        rc, out = self._exec(["--power", "-vv"])
        if rc != 0:
            self._append(out + "\n")
            return
        lfcc = RE_LFCC.search(out)
        design = RE_DESIGN.search(out)
        cycles = RE_CYCLES.search(out)
        if lfcc and design:
            health = 100.0 * int(lfcc.group(1)) / int(design.group(1))
            self._append("Design capacity:      {} mAh\n".format(
                design.group(1)))
            self._append("Full-charge capacity: {} mAh\n".format(lfcc.group(1)))
            self._append("Health:               {:.1f}% of design\n".format(
                health))
        else:
            self._append("Could not parse capacities — raw output below.\n")
        if cycles:
            self._append("Cycle count:          {}\n".format(cycles.group(1)))
        if not (lfcc and design):
            self._append("\n" + out + "\n")

    def tool_charge_speed(self):
        self._append("=== Charging speed check ===\n")
        rc, out = self._exec(["--power", "-vv"])
        if rc != 0:
            self._append(out + "\n")
            return
        ac = RE_AC.search(out)
        chg = RE_CHG_A.search(out)
        design = RE_DESIGN.search(out)
        soc = RE_SOC.search(out)
        if ac and "not" in ac.group(1):
            self._append("AC not connected — plug in a charger and rerun.\n")
            return
        if chg and design and int(chg.group(1)) > 0:
            c_rate = int(chg.group(1)) / int(design.group(1))
            self._append("Charge current: {} mA → {:.2f} C\n".format(
                chg.group(1), c_rate))
            self._append("Est. full 0→100% time at this rate: "
                         "{:.0f} min\n".format(60 / c_rate))
            if soc:
                self._append("Current SoC: {}%\n".format(soc.group(1)))
        elif chg and int(chg.group(1)) == 0:
            self._append("Charger current is 0 mA — battery full, "
                         "at charge limit, or not charging.\n")
        else:
            self._append("Could not parse — raw output:\n" + out + "\n")

    def tool_thermal_monitor(self):
        self._append("=== Thermal monitor (6 samples, 5 s apart) ===\n")
        stats = {}
        rpm_seen = []
        for i in range(6):
            if self._cancel:
                break
            rc, out = self._exec(["--thermal"])
            if rc != 0:
                self._append(out + "\n")
                return
            line = ["[{}/6]".format(i + 1)]
            hottest = 0
            for name, val in RE_TEMP.findall(out):
                v = int(val)
                hottest = max(hottest, v)
                lo, hi = stats.get(name, (v, v))
                stats[name] = (min(lo, v), max(hi, v))
                line.append("{}={}C".format(name, v))
            m = RE_RPM.search(out)
            if m:
                rpm_seen.append(int(m.group(1)))
                line.append("fan={}rpm".format(m.group(1)))
            self._append(" ".join(line) + "\n")
            self._progress(i, i + 1, 6, "sample {}".format(i + 1),
                           "{} C".format(hottest), hottest / TEMP_SCALE_C)
            if i < 5 and not self._sleep(5):
                break
        self._append("\nSummary (min–max):\n")
        for name, (lo, hi) in stats.items():
            self._append("  {}: {}–{} C\n".format(name, lo, hi))
        if rpm_seen:
            self._append("  Fan: {}–{} RPM\n".format(min(rpm_seen),
                                                     max(rpm_seen)))

    def tool_port_map(self):
        self._append("=== Port power map ===\n")
        rc, out = self._exec(["--pdports"])
        if rc != 0:
            self._append(out + "\n")
            return
        ports = parse_ports(out)
        if not ports:
            self._append("No ports parsed — raw output:\n" + out + "\n")
            return
        self.sig_readings.emit({"ports": ports})
        for p in ports:
            if p.get("watts"):
                direction = "drawing" if p["role"] == "Sink" else "supplying"
                self._append("Port {}: {:6s} {} {:.1f} W "
                             "({:.1f} V / {} mA)\n".format(
                                 p["port"], p["role"], direction, p["watts"],
                                 p["volts"], p["ma"]))
            else:
                self._append("Port {}: {:6s} no PD contract / nothing "
                             "negotiated\n".format(p["port"], p["role"]))

    def tool_kblight_sweep(self):
        self._append("=== Keyboard backlight sweep ===\n")
        rc, out = self._exec(["--kblight"])
        m = re.search(r"(\d+)\s*%", out) if rc == 0 else None
        original = m.group(1) if m else "0"
        levels = list(range(0, 101, 20)) + list(range(80, -1, -20))
        try:
            for index, lv in enumerate(levels):
                if self._cancel:
                    break
                self._exec(["--kblight", str(lv)])
                self._append("{}% ".format(lv))
                self._progress(index, index + 1, len(levels), "step",
                               "{}%".format(lv), lv / 100.0)
                if not self._sleep(0.5):
                    break
        finally:
            self._exec(["--kblight", original])
            self._append("\nRestored to {}%.\n".format(original))

    def tool_fpled_cycle(self):
        self._append("=== Fingerprint LED test ===\n"
                     "Watch the power button while levels cycle.\n")
        levels = ("high", "medium", "low", "ultra-low")
        try:
            for index, level in enumerate(levels):
                if self._cancel:
                    break
                self._exec(["--fp-led-level", level])
                self._append("{} ".format(level))
                self._progress(index, index + 1, len(levels), "level", level,
                               (index + 1) / len(levels))
                if not self._sleep(1.5):
                    break
        finally:
            self._exec(["--fp-led-level", "auto"])
            self._append("\nRestored to auto.\n")

    def tool_ec_health(self):
        self._append("=== EC health check ===\n")
        rc, out = self._exec(["-t"])
        self._append("Self-test exit code: {}\n{}\n\n".format(rc, out.strip()))
        rc, out = self._exec(["--versions"])
        if rc == 0:
            grab = False
            for line in out.splitlines():
                if line.startswith("EC Firmware"):
                    grab = True
                elif grab and not line.startswith(" "):
                    break
                if grab:
                    self._append(line + "\n")
        else:
            self._append(out + "\n")

    def tool_security(self):
        self._append("=== Security check ===\n")
        if self.caps.get("is_laptop"):
            rc, out = self._exec(["--privacy"])
            self._append("Privacy switches:\n" + out.strip() + "\n\n")
        else:
            self._append("Privacy switches: not applicable on this device.\n\n")
        rc, out = self._exec(["--intrusion"])
        self._append("Chassis intrusion:\n" + out.strip() + "\n")

    def tool_full_report(self):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.expanduser("~"),
                            "framework_report_{}.txt".format(ts))
        sections = [("FIRMWARE VERSIONS", ["--versions"]),
                    ("THERMAL", ["--thermal"]),
                    ("SENSORS", ["--sensors"]),
                    ("USB-C PD PORTS", ["--pdports"]),
                    ("INTRUSION", ["--intrusion"])]
        if self.caps.get("is_laptop"):
            sections[1:1] = [("POWER / BATTERY", ["--power", "-vv"])]
            sections += [("INPUT DECK", ["--inputdeck"]),
                         ("PRIVACY SWITCHES", ["--privacy"]),
                         ("CHARGE LIMIT", ["--charge-limit"])]
        if self.caps.get("has_expansion_bay"):
            sections.append(("EXPANSION BAY", ["--expansion-bay"]))
        self._append("=== Full system report ===\nWriting {}\n\n".format(path))
        lines = ["Framework system report — {}\n".format(ts)]
        for index, (title, args) in enumerate(sections):
            if self._cancel:
                break
            rc, out = self._exec(args)
            lines.append("\n===== {} =====\n{}\n".format(title, out.strip()))
            self._append("{}: {}\n".format(
                title, "ok" if rc == 0 else "exit {}".format(rc)))
            self._progress(index, index + 1, len(sections), title.lower(),
                           "ok" if rc == 0 else "exit {}".format(rc),
                           (index + 1) / len(sections))
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            self._append("\nSaved: {}\n".format(path))
        except OSError as e:
            self._append("\nCould not write file: {}\n".format(e))

    def tool_preset(self, limit, rate):
        self._append("=== Preset: charge limit {}%, rate {}C ===\n".format(
            limit, rate))
        rc, out = self._exec(["--charge-limit", str(limit)])
        self._append(out.strip() + "\n" if out.strip()
                     else "Charge limit → {}% (exit {})\n".format(limit, rc))
        rc, out = self._exec(["--charge-rate-limit", rate])
        self._append(out.strip() + "\n" if out.strip()
                     else "Rate limit → {}C (exit {})\n".format(rate, rc))
        rc, out = self._exec(["--charge-limit"])
        if rc == 0 and out.strip():
            self._append("Verify: " + out.strip() + "\n")


def main():
    QGuiApplication.setDesktopFileName("io.github.frameworkgui.FrameworkGUI")
    app = QApplication(sys.argv)
    app.setApplicationName(navigation.APP_NAME)
    load_fonts()
    window = App()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
