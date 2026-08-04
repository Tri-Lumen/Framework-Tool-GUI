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
RE_PORT = re.compile(r"USB-C Port (\d+):")
RE_NEGO = re.compile(r"Negotiated:\s*([\d.]+)\s*V,\s*(\d+)\s*mA,\s*([\d.]+)\s*W")
RE_ROLE = re.compile(r"Power Role:\s*(\w+)")

# ---------- device detection (--versions) ----------

RE_TYPE = re.compile(r"^\s*Type:\s*(.+)$", re.MULTILINE)
RE_TOUCHSCREEN = re.compile(r"^\s*Touchscreen\b", re.MULTILINE)
RE_STYLUS = re.compile(r"^\s*Stylus\b", re.MULTILINE)


def parse_ports(text):
    """Return list of dicts per USB-C port from --pdports output."""
    ports = []
    matches = list(RE_PORT.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.start():end]
        d = {"port": m.group(1)}
        r = RE_ROLE.search(block)
        d["role"] = r.group(1) if r else "?"
        n = RE_NEGO.search(block)
        if n:
            d["volts"] = float(n.group(1))
            d["ma"] = int(n.group(2))
            d["watts"] = float(n.group(3))
        ports.append(d)
    return ports


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
        "detected": known,
        "is_laptop": is_laptop,
        "is_desktop": is_desktop,
        "is_laptop12": (model == "Laptop 12") if known else True,
        "has_touchscreen": bool(RE_TOUCHSCREEN.search(versions_text)) if known else True,
        "has_stylus": bool(RE_STYLUS.search(versions_text)) if known else True,
        "has_expansion_bay": (model == "Laptop 16") if known else True,
        "has_rgbkbd": is_desktop,
    }
