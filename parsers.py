"""
Pure-Python parsing and device-detection logic for Framework System GUI.

Deliberately has zero dependency on tkinter (or anything else non-stdlib) so
it can be unit-tested without a display, Xvfb, or tkinter being installed.
framework_gui.py imports everything it needs from here.

The framework_tool CLI does not guarantee a stable output format (the
upstream repo says so explicitly), so every regex here is best-effort:
callers should always have a fallback path that shows raw output when a
parse comes back empty. See EXAMPLES.md in the framework-system repo for
the sample outputs these regexes were written against.
"""

import re

# ---------- output parsers (--power, --thermal, --pdports) ----------

RE_CHG_V = re.compile(r"Charger Voltage:\s*(\d+)\s*mV")
RE_CHG_A = re.compile(r"Charger Current:\s*(\d+)\s*mA")
RE_IN_A = re.compile(r"Chg Input Current:\s*(\d+)\s*mA")
RE_SOC = re.compile(r"Battery SoC:\s*(\d+)\s*%")
RE_LFCC = re.compile(r"Battery LFCC:\s*(\d+)\s*mAh")
RE_DESIGN = re.compile(r"Design Capacity:\s*(\d+)\s*mAh")
RE_CYCLES = re.compile(r"Cycle Count:\s*(\d+)")
RE_AC = re.compile(r"AC is:\s*(\w[\w ]*)")
RE_RPM = re.compile(r"Fan Speed:\s*(\d+)\s*RPM")
RE_TEMP = re.compile(r"^\s*(\S+):\s+(-?\d+)\s*C\s*$", re.MULTILINE)
# Two different commands report the USB-C ports, and they do not agree on
# the format:
#
#   --pdports              "USB-C Port 0:"                 Power Role / Negotiated
#   --pdports-chromebook   "USB-C Port 0 (Right Back):"    Role / Voltage Now / Current Lim
#
# The first is the Framework-specific EC command and the one the app asks
# for; it is not implemented by every EC firmware, and where it is missing
# the CLI still exits 0 having printed only errors. The second goes through
# the generic Chromium EC path, so it answers on boards the first does not —
# which is why `parse_ports` reads both and the app falls back to it.
RE_PORT = re.compile(r"USB-C Port (\d+)(?:\s*\(([^)]*)\))?\s*:")
RE_NEGO = re.compile(r"Negotiated:\s*([\d.]+)\s*V,\s*(\d+)\s*mA,\s*([\d.]+)\s*W")
# "Power Role:" (--pdports) and "Role:" (--pdports-chromebook), but never
# "Data Role:" or "Dual Role:" — hence the line anchor rather than a bare
# optional prefix.
RE_ROLE = re.compile(r"^\s*(?:Power\s+)?Role:\s*(\w+)", re.MULTILINE)
RE_VOLTAGE_NOW = re.compile(r"Voltage Now:\s*([\d.]+)\s*V")
RE_CURRENT_LIM = re.compile(r"Current Lim:\s*(\d+)\s*mA")
RE_MAX_POWER = re.compile(r"Max Power:\s*([\d.]+)\s*W")

# Roles that mean "nothing is attached to this port".
IDLE_ROLES = frozenset(("disconnected", "nothing", "unknown", "?"))

# ---------- device detection (--versions) ----------

RE_TYPE = re.compile(r"^\s*Type:\s*(.+)$", re.MULTILINE)
RE_TOUCHSCREEN = re.compile(r"^\s*Touchscreen\b", re.MULTILINE)
RE_STYLUS = re.compile(r"^\s*Stylus\b", re.MULTILINE)

# `--version` prints the tool's own version; the exact wording has changed
# between releases, so match a bare vN.N.N anywhere in the first line.
RE_TOOL_VERSION = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)*)\b")

# Firmware versions, for the Overview sub-line. Two shapes are accepted
# because `--versions` groups values under a section header on current
# releases but has printed them inline before:
#
#   EC Firmware              EC Firmware: hx30 0.1.4
#     Build version: hx30    BIOS: 3.03
RE_FLAT_VALUE = r"^\s*{}\s*:\s*\"?([^\"\n]+?)\"?\s*$"


def parse_ports(text):
    """Return list of dicts per USB-C port, from either --pdports format.

    Keys: `port` always; `name` when the CLI labelled the bay; `role`;
    `volts`/`ma`/`watts` when the port reported a live contract, and
    `max_watts` when it reported only a ceiling. A port with no power keys
    negotiated nothing, which the UI shows as idle.
    """
    ports = []
    matches = list(RE_PORT.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.start():end]
        d = {"port": m.group(1)}
        if m.group(2):
            d["name"] = m.group(2).strip()
        r = RE_ROLE.search(block)
        d["role"] = r.group(1) if r else "?"
        n = RE_NEGO.search(block)
        if n:
            # --pdports: the contract is stated outright.
            d["volts"] = float(n.group(1))
            d["ma"] = int(n.group(2))
            d["watts"] = float(n.group(3))
            ports.append(d)
            continue
        # --pdports-chromebook: no contract line, so derive it. Voltage and
        # current limit are what the port is actually carrying; Max Power is
        # only the ceiling, kept separate so the UI never shows a headline
        # wattage the port is not delivering.
        volts = RE_VOLTAGE_NOW.search(block)
        amps = RE_CURRENT_LIM.search(block)
        if volts and amps:
            d["volts"] = float(volts.group(1))
            d["ma"] = int(amps.group(1))
            watts = d["volts"] * d["ma"] / 1000.0
            if watts:
                d["watts"] = round(watts, 1)
        power = RE_MAX_POWER.search(block)
        if power:
            d["max_watts"] = float(power.group(1))
        ports.append(d)
    return ports


def port_is_live(port):
    """Did this bay negotiate anything, or is it sitting idle?

    A port with a wattage but a disconnected role is still idle — the
    chromebook path reports a voltage rail on ports with nothing in them.
    """
    if not port:
        return False
    if (port.get("role") or "?").lower() in IDLE_ROLES:
        return False
    return bool(port.get("watts"))


# A settings "Get" prints one value in one of a few shapes. These cover the
# ones in EXAMPLES.md; anything else leaves the field alone rather than
# filling it with a guess.
RE_SETTING_PCT = re.compile(r"(\d+)\s*%")
RE_SETTING_KV = re.compile(r":\s*([A-Za-z0-9.\-]+)\s*$", re.MULTILINE)

# `--charge-limit` prints *two* percentages — "Minimum 0%, Maximum 80%" —
# and the one the app means by "charge limit" is the maximum. Taking the
# first percentage on the line reported every machine as limited to 0%.
RE_CHARGE_MAX = re.compile(r"Maximum\s*(\d+)\s*%", re.IGNORECASE)

# `--fp-led-level` and `--fp-brightness` both print the same block:
#
#   Fingerprint LED Brightness
#     Requested:  Auto
#     Brightness: 55%
#
# so the level and the percentage each need pulling out by name. Reading
# either one with the generic parser returned the percentage, which is not
# a value the level combo box has an entry for.
RE_FP_LEVEL = re.compile(r"Requested:\s*([A-Za-z-]+)", re.IGNORECASE)
RE_FP_PCT = re.compile(r"Brightness:\s*(\d+)\s*%", re.IGNORECASE)


def ac_connected(power_text):
    """Is an adapter attached? True / False / None when it did not say.

    `--power` prints "AC is: connected" or "AC is: not connected". The
    charger voltage and input current are printed either way and are not
    zero on battery, so multiplying them without checking this reported a
    few watts of phantom AC draw on an unplugged machine.
    """
    m = RE_AC.search(power_text or "")
    if not m:
        return None
    value = m.group(1).strip().lower()
    if value.startswith("not"):
        return False
    return value.startswith("connected")


def parse_charge_limit(text):
    """The maximum charge percentage from `--charge-limit`, or ''."""
    m = RE_CHARGE_MAX.search(text or "")
    return m.group(1) if m else parse_setting_value(text)


def parse_fp_level(text):
    """The fingerprint LED level, lowercased to match the combo's entries.

    The CLI prints the Rust enum name (`UltraLow`), the CLI *accepts* the
    kebab-case form (`ultra-low`), and the combo box lists what it accepts —
    so the round trip needs the conversion.
    """
    m = RE_FP_LEVEL.search(text or "")
    if not m:
        return ""
    value = m.group(1)
    if "-" not in value:
        value = re.sub(r"(?<=[a-z])(?=[A-Z])", "-", value)
    return value.lower()


def parse_fp_brightness(text):
    """The fingerprint LED brightness percentage, or ''."""
    m = RE_FP_PCT.search(text or "")
    return m.group(1) if m else ""


def parse_setting_value(text):
    """The single value a settings read printed, or '' if it is unclear.

    Used to fill a Settings row from its Get button. Empty means the row
    keeps whatever it had — the raw output is in the drawer either way, so
    nothing is hidden by declining to guess.
    """
    body = text or ""
    m = RE_SETTING_PCT.search(body)
    if m:
        return m.group(1)
    m = None
    for m in RE_SETTING_KV.finditer(body):
        pass                     # the last key: value line is the answer
    return m.group(1) if m else ""


def sections(text):
    """Split `--versions` output into {section header: [indented lines]}.

    The CLI groups values under an unindented header with indented rows
    beneath it. Headers repeat across releases even when the row labels
    change, so keying on them survives more format drift than one big regex
    would.
    """
    out = {}
    current = None
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        if line[:1].strip():                      # unindented: a new header
            current = line.strip().rstrip(":")
            out.setdefault(current, [])
        elif current is not None:
            out[current].append(line.strip())
    return out


def _labelled(lines, labels):
    for label in labels:
        pattern = re.compile(RE_FLAT_VALUE.format(re.escape(label)),
                             re.IGNORECASE)
        for line in lines:
            m = pattern.match(line)
            if m and m.group(1).strip():
                return m.group(1).strip()
    return ""


def parse_firmware(versions_text):
    """EC and BIOS versions from `--versions`, '' for whatever is not there.

    Best-effort like every parser here: the Overview drops a field it cannot
    read rather than printing a placeholder that looks like a reading.
    """
    text = versions_text or ""
    found = sections(text)
    out = {}
    for key, header, labels in (
            ("ec", "EC Firmware", ("Build version", "Current version",
                                   "Version")),
            ("bios", "BIOS", ("Version", "Current version"))):
        value = _labelled(found.get(header, ()), labels)
        if not value:
            # The inline shape: `EC Firmware: hx30 0.1.4` on one line.
            value = _labelled(text.splitlines(), (header,))
        out[key] = value
    return out


def parse_tool_version(version_text):
    """The framework_tool version for the status bar, or ''."""
    first = (version_text or "").strip().splitlines()
    if not first:
        return ""
    m = RE_TOOL_VERSION.search(first[0])
    return m.group(1) if m else ""


def detect_model(versions_text):
    """Parse `--versions` output into a capability dict.

    Fail-open by design: any field that can't be determined defaults to
    True (show the control) rather than False (hide it) — hiding a
    control that actually applies is worse than showing one that doesn't.
    """
    m = RE_TYPE.search(versions_text)
    raw = m.group(1).strip() if m else ""
    if "Laptop 12" in raw:
        model = "Laptop 12"
    elif "Laptop 13" in raw:
        model = "Laptop 13"
    elif "Laptop 16" in raw:
        model = "Laptop 16"
    elif "Desktop" in raw:
        model = "Desktop"
    else:
        model = None  # unparsed / unrecognized board string

    known = model is not None
    is_laptop = (model in ("Laptop 12", "Laptop 13", "Laptop 16")) if known else True
    is_desktop = (model == "Desktop") if known else False
    return {
        "model": raw or "Unknown",
        # The chassis on its own, for anywhere the full board string is too
        # long to read as a name — the Overview heading, mainly. Empty when
        # the board was not recognised, so callers can say so themselves.
        "chassis": model or "",
        "detected": known,
        "is_laptop": is_laptop,
        "is_desktop": is_desktop,
        "is_laptop12": (model == "Laptop 12") if known else True,
        "has_touchscreen": bool(RE_TOUCHSCREEN.search(versions_text)) if known else True,
        "has_stylus": bool(RE_STYLUS.search(versions_text)) if known else True,
        "has_expansion_bay": (model == "Laptop 16") if known else True,
        "has_rgbkbd": is_desktop,
    }
