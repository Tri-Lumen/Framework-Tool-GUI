"""
CPU power-limit (TDP) backends — the part framework_tool cannot do.

`framework_tool` talks to the embedded controller. TDP does not live there:
PL1/PL2 on Intel and STAPM/PPT on AMD are SoC registers the EC does not own,
so every backend here shells out to a *different* tool. Which one is usable
depends on the CPU vendor and the OS:

    backend    vendor        OS       what it actually sets
    ---------  ------------  -------  ----------------------------------
    ryzenadj   AMD           both     STAPM / PPT fast / PPT slow (real TDP)
    rapl       Intel + AMD   Linux    RAPL long/short power limits (real TDP)
    powercfg   any           Windows  max processor state % (a frequency cap,
                                      NOT a wattage — the honest fallback when
                                      no real TDP tool is installed)

Like parsers.py this module imports nothing but the stdlib and never touches
the toolkit, so it is unit-testable without a display. Anything that needs the
filesystem or a subprocess takes an injectable callable.

Nothing here is persistent, deliberately: every limit these backends set is
lost on reboot, and often on resume from sleep or an AC/battery transition
too. Re-applying automatically would need a service, a timer or a scheduled
task, and this project's hard requirement is no background processes. The UI
says so instead of quietly starting one.
"""

import re

# Anything outside this is refused before a command is ever built. These are
# not model-specific tuning values, just a guard against a typo in a text
# box asking the SoC for 4 W (instant throttle) or 900 W.
MIN_WATTS = 5
MAX_WATTS = 200

# Processor-state percentage bounds for the powercfg fallback.
MIN_PERCENT = 20
MAX_PERCENT = 100

VENDOR_AMD = "amd"
VENDOR_INTEL = "intel"
VENDOR_ARM = "arm"
VENDOR_UNKNOWN = "unknown"

# /proc/cpuinfo on x86 and PROCESSOR_IDENTIFIER on Windows both carry these.
RE_AMD = re.compile(r"AuthenticAMD|\bAMD\b", re.IGNORECASE)
RE_INTEL = re.compile(r"GenuineIntel|\bIntel\b", re.IGNORECASE)
RE_ARM = re.compile(r"CPU implementer|\bARM(v8|v9|64)?\b|aarch64", re.IGNORECASE)
RE_MODEL_NAME = re.compile(r"^model name\s*:\s*(.+)$", re.MULTILINE)

# `ryzenadj -i` prints a three-column table:
#   | STAPM LIMIT         |    15.000 | stapm-limit        |
RE_RYZENADJ_ROW = re.compile(
    r"^\|\s*(?P<name>[A-Za-z][A-Za-z0-9 /_-]*?)\s*\|\s*(?P<value>-?[\d.]+)\s*\|",
    re.MULTILINE)


class PowerError(ValueError):
    """A limit was refused before any command was built."""


def detect_vendor(cpuinfo="", processor_identifier="", machine=""):
    """Best-effort CPU vendor from any/all of the three text sources.

    Callers pass whatever they have: /proc/cpuinfo on Linux,
    %PROCESSOR_IDENTIFIER% on Windows, platform.machine() anywhere. Unknown
    is a real answer here — unlike device detection in parsers.py, guessing
    wrong would mean offering a backend that cannot work on this CPU.
    """
    blob = "\n".join(t for t in (cpuinfo, processor_identifier) if t)
    if RE_AMD.search(blob):
        return VENDOR_AMD
    if RE_INTEL.search(blob):
        return VENDOR_INTEL
    if RE_ARM.search(blob) or (machine or "").lower() in ("aarch64", "arm64"):
        return VENDOR_ARM
    return VENDOR_UNKNOWN


def cpu_label(cpuinfo="", processor_identifier="", brand=""):
    """Human-readable CPU name, or '' if no source names one.

    `brand` is the marketing string where the caller could get one — the
    registry's ProcessorNameString on Windows. It wins, because the other
    two sources are worse in different ways: /proc/cpuinfo's model name is
    the same string with the marketing noise still attached, and
    %PROCESSOR_IDENTIFIER% is not a name at all.
    """
    if (brand or "").strip():
        return brand.strip()
    m = RE_MODEL_NAME.search(cpuinfo or "")
    if m:
        return m.group(1).strip()
    return (processor_identifier or "").strip()


# The parts of a CPU brand string that are not the CPU's name. Windows'
# %PROCESSOR_IDENTIFIER% is the extreme case — "AMD64 Family 25 Model 116
# Stepping 1, AuthenticAMD" is 47 characters that identify a whole
# generation rather than a chip, and it pushed the Overview's sub-line onto
# three wrapped lines on a real machine.
RE_CPUID_STRING = re.compile(
    r"^(x86|AMD64|ARM64|Intel64|EM64T)?\s*Family\s+\d+\s+Model\s+\d+"
    r"(\s+Stepping\s+\d+)?\s*(,.*)?$", re.IGNORECASE)
# Trailing hardware the name does not need: the integrated GPU, the clock
# speed, the word "processor", the registered-trademark marks.
RE_CPU_NOISE = re.compile(
    # "w/ Radeon 780M Graphics", "with Radeon Graphics" — the integrated
    # GPU, which is never what someone is looking for in a CPU field.
    r"\s*\b(?:w/|with\b).*$"
    r"|\s*\b\d+-Core Processor\b\s*$"
    r"|\s*\bCPU\b\s*(?:@\s*[\d.]+\s*[GM]Hz)?\s*$"
    r"|\s*@\s*[\d.]+\s*[GM]Hz\s*$"
    r"|\s*\bProcessor\b\s*$",
    re.IGNORECASE)
RE_CPU_MARKS = re.compile(r"\((?:R|TM|C)\)", re.IGNORECASE)
# The vendor's own name, wherever it sits — Intel puts it after the
# generation ("13th Gen Intel Core i5-1340P"), AMD puts it first. The board
# string beside this already says who made the machine, and "Ryzen 7 7840U"
# is how the chip is referred to everywhere except inside a CPUID register.
RE_CPU_VENDOR = re.compile(r"\b(AMD|Intel|Genuine Intel|AuthenticAMD)\b\s*",
                           re.IGNORECASE)


def short_cpu_label(label):
    """A CPU name at the length a heading can carry.

        AMD Ryzen 7 7840U w/ Radeon 780M Graphics  ->  Ryzen 7 7840U
        Intel(R) Core(TM) i7-1260P CPU @ 2.10GHz   ->  Core i7-1260P
        AMD64 Family 25 Model 116 Stepping 1, ...  ->  ''

    The last case is the point: %PROCESSOR_IDENTIFIER% names a family, not
    a processor, so there is nothing in it worth the width. Empty means the
    caller should show nothing rather than a string that reads like a
    reading. Everything unrecognised is passed through untouched — this
    trims known noise, it does not guess at names.
    """
    text = " ".join((label or "").split())
    if not text or RE_CPUID_STRING.match(text):
        return ""
    text = RE_CPU_MARKS.sub("", text)
    text = RE_CPU_VENDOR.sub("", text)
    previous = None
    while previous != text:                 # "... CPU @ 2.10GHz" is two
        previous = text
        text = RE_CPU_NOISE.sub("", text).strip()
    return " ".join(text.split()).strip(" ,-")


# ---------- backend registry ----------

BACKENDS = {
    "ryzenadj": {
        "label": "RyzenAdj (AMD STAPM/PPT)",
        "vendors": (VENDOR_AMD,),
        "platforms": ("linux", "windows"),
        "dependency": "ryzenadj",
        "sets_watts": True,
        "note": "Sets the real sustained (STAPM) and boost (PPT fast) limits.",
        # RyzenAdj writes SoC registers and keeps no state. The platform's
        # own power management overwrites them, so persistence means
        # re-running it — on boot, on resume, or on a timer.
        "volatile": True,
        "persistence": {
            "note": "RyzenAdj holds no settings of its own — making a limit "
                    "stick means re-running it after boot and after resume. "
                    "On Linux that is a systemd service (plus a "
                    "sleep.target hook or a timer); on Windows it is a "
                    "Task Scheduler task triggered at logon and on resume.",
            "links": {
                "linux": (
                    ("RyzenAdj usage notes (upstream)",
                     "https://github.com/FlyGoat/RyzenAdj#readme"),
                    ("Writing a systemd service unit",
                     "https://wiki.archlinux.org/title/Systemd#Writing_unit_files"),
                ),
                "windows": (
                    ("RyzenAdj usage notes (upstream)",
                     "https://github.com/FlyGoat/RyzenAdj#readme"),
                    ("schtasks — run a command at logon",
                     "https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks"),
                ),
            },
        },
    },
    "rapl": {
        "label": "Intel RAPL via powercap (Linux)",
        "vendors": (VENDOR_INTEL, VENDOR_AMD),
        "platforms": ("linux",),
        "dependency": None,  # kernel sysfs, nothing to install
        "sets_watts": True,
        "note": "Writes the kernel's powercap limits; needs root and a "
                "kernel driver that exposes them (Intel always, AMD only on "
                "some models).",
        "volatile": True,
        "persistence": {
            "note": "The kernel restores its own defaults at boot, so the "
                    "sysfs write has to be repeated — a systemd service (or "
                    "a udev rule on the powercap device) is the usual way. "
                    "Some firmware also re-asserts its own limits on "
                    "resume.",
            "links": {
                "linux": (
                    ("Kernel powercap / RAPL documentation",
                     "https://www.kernel.org/doc/html/latest/power/powercap/powercap.html"),
                    ("Writing a systemd service unit",
                     "https://wiki.archlinux.org/title/Systemd#Writing_unit_files"),
                ),
            },
        },
    },
    "powercfg": {
        "label": "Windows max processor state (%)",
        "vendors": (VENDOR_AMD, VENDOR_INTEL, VENDOR_ARM, VENDOR_UNKNOWN),
        "platforms": ("windows",),
        "dependency": None,  # ships with Windows
        "sets_watts": False,
        "note": "A frequency cap, not a wattage. Works everywhere and needs "
                "nothing installed, so it is the fallback when no real TDP "
                "tool is available.",
        # The odd one out: powercfg edits the saved power scheme, so this
        # setting already survives a reboot with nothing extra running.
        "volatile": False,
        "persistence": {
            "note": "Already persistent. powercfg edits the active power "
                    "scheme, which Windows stores and restores across "
                    "reboots — nothing has to re-apply it. It does reset if "
                    "you switch schemes or a vendor utility overwrites "
                    "them.",
            "links": {
                "windows": (
                    ("powercfg command-line options",
                     "https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/powercfg-command-line-options"),
                ),
            },
        },
    },
}


def persistence_links(backend_id, os_name):
    """(label, url) pairs documenting how to make this backend's limit stick.

    Empty for a backend/OS pair with nothing to link. The app does not set
    any of this up — it has no background processes by design — so these are
    pointers for someone who wants to do it themselves.
    """
    backend = BACKENDS.get(backend_id)
    if not backend:
        return []
    return list(backend["persistence"]["links"].get(os_name, ()))


def persistence_note(backend_id):
    backend = BACKENDS.get(backend_id)
    return backend["persistence"]["note"] if backend else ""


def is_volatile(backend_id):
    backend = BACKENDS.get(backend_id)
    return bool(backend["volatile"]) if backend else True

# Best first. available_backends() filters this, it does not reorder it.
_PREFERENCE = ("ryzenadj", "rapl", "powercfg")


def available_backends(vendor, os_name, have=None, rapl_present=False):
    """Backend ids usable on this machine, best first.

    `have(dependency_id) -> bool` answers "is that helper installed?"; when
    it is not passed, backends with a dependency are still listed (the UI
    then offers to install it). `rapl_present` is the caller's filesystem
    check, since this module does no I/O of its own.
    """
    out = []
    for bid in _PREFERENCE:
        b = BACKENDS[bid]
        if os_name not in b["platforms"] or vendor not in b["vendors"]:
            continue
        if bid == "rapl" and not rapl_present:
            continue
        if have is not None and b["dependency"] and not have(b["dependency"]):
            continue
        out.append(bid)
    return out


def check_watts(watts):
    """Validate a wattage, returning it as an int. Raises PowerError."""
    try:
        w = int(round(float(watts)))
    except (TypeError, ValueError):
        raise PowerError(f"{watts!r} is not a number of watts.") from None
    if not MIN_WATTS <= w <= MAX_WATTS:
        raise PowerError(
            f"{w} W is outside the {MIN_WATTS}-{MAX_WATTS} W range this app "
            f"will apply.")
    return w


def check_percent(percent):
    try:
        p = int(round(float(percent)))
    except (TypeError, ValueError):
        raise PowerError(f"{percent!r} is not a percentage.") from None
    if not MIN_PERCENT <= p <= MAX_PERCENT:
        raise PowerError(
            f"{p}% is outside the {MIN_PERCENT}-{MAX_PERCENT}% range.")
    return p


# ---------- ryzenadj ----------

def ryzenadj_args(sustained_w, boost_w=None, tctl_c=None):
    """Args for `ryzenadj`. RyzenAdj takes milliwatts, the UI takes watts.

    sustained -> --stapm-limit and --slow-limit (the long-term budget),
    boost -> --fast-limit (short bursts). Boost defaults to sustained, which
    flattens the curve rather than leaving a stale higher burst limit in
    place.
    """
    s = check_watts(sustained_w)
    b = check_watts(boost_w) if boost_w is not None else s
    if b < s:
        raise PowerError("Boost limit cannot be below the sustained limit.")
    args = [f"--stapm-limit={s * 1000}",
            f"--slow-limit={s * 1000}",
            f"--fast-limit={b * 1000}"]
    if tctl_c is not None:
        t = int(round(float(tctl_c)))
        if not 60 <= t <= 100:
            raise PowerError("Temperature limit must be between 60 and 100 C.")
        args.append(f"--tctl-temp={t}")
    return args


def parse_ryzenadj_info(text):
    """`ryzenadj -i` table -> {'STAPM LIMIT': 15.0, ...}.

    Best-effort like every parser in this project: an empty dict means the
    caller should show the raw output instead of claiming to know anything.
    """
    out = {}
    for m in RE_RYZENADJ_ROW.finditer(text or ""):
        name = m.group("name").strip()
        if name.lower() == "name":  # table header row
            continue
        try:
            out[name] = float(m.group("value"))
        except ValueError:
            continue
    return out


# ---------- Linux RAPL (powercap sysfs) ----------

RAPL_ROOT = "/sys/class/powercap"


def rapl_constraint_files(zones):
    """Map package zone dirs to their long/short power-limit files.

    `zones` is the caller's listing of RAPL_ROOT (this module does no I/O).
    Only `intel-rapl:N` package zones are used; subzones (`intel-rapl:0:1`,
    core/uncore) are skipped because capping those does not cap the package.
    """
    out = []
    for name in sorted(zones):
        if not re.fullmatch(r"intel-rapl:\d+", name):
            continue
        base = f"{RAPL_ROOT}/{name}"
        out.append({
            "zone": name,
            "long": f"{base}/constraint_0_power_limit_uw",
            "short": f"{base}/constraint_1_power_limit_uw",
        })
    return out


def rapl_write_cmd(path, watts):
    """Command that writes a wattage into a powercap file.

    Goes through `sh -c` so the redirect happens *inside* the elevated
    process — `pkexec tee` would work too but pulls the value through
    another program's stdin for no gain.
    """
    w = check_watts(watts)
    return ["sh", "-c", f"echo {w * 1_000_000} > {path}"]


def parse_rapl_uw(text):
    """microwatts as printed by cat -> watts, or None if unparseable."""
    m = re.search(r"-?\d+", text or "")
    if not m:
        return None
    return int(m.group(0)) / 1_000_000.0


# ---------- Windows powercfg fallback ----------

# GUIDs are stable across Windows versions; the friendly names are not
# localised-safe, so use the GUIDs.
_SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
_PROCTHROTTLEMAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"


def powercfg_cmds(percent):
    """Commands to cap the maximum processor state on the active scheme.

    Both AC and DC values are set: capping only one leaves the machine
    jumping back to 100% the moment the charger is plugged in or pulled,
    which looks exactly like the setting silently failing.
    """
    p = check_percent(percent)
    return [
        ["powercfg", "/setacvalueindex", "SCHEME_CURRENT",
         _SUB_PROCESSOR, _PROCTHROTTLEMAX, str(p)],
        ["powercfg", "/setdcvalueindex", "SCHEME_CURRENT",
         _SUB_PROCESSOR, _PROCTHROTTLEMAX, str(p)],
        ["powercfg", "/setactive", "SCHEME_CURRENT"],
    ]


def powercfg_query_cmd():
    return ["powercfg", "/query", "SCHEME_CURRENT", _SUB_PROCESSOR,
            _PROCTHROTTLEMAX]


RE_POWERCFG_AC = re.compile(
    r"Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)")


def parse_powercfg_percent(text):
    """Pull the AC max-processor-state percentage out of `powercfg /query`."""
    m = RE_POWERCFG_AC.search(text or "")
    if not m:
        return None
    return int(m.group(1), 16)
