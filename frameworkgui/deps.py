"""
External helper tools this GUI can drive, and how to install each one.

The GUI only ever *runs* other programs — it has no direct hardware access —
so "can I do X on this machine" reduces to "is the tool for X installed".
This module is that registry: what each helper is for, how to detect it, and
what installing it would actually run. It builds commands and URLs; it does
not execute anything and does not import the toolkit, so it is testable without
a display.

Two rules the GUI depends on:

* Nothing installs silently. Every entry produces an install *plan* that the
  caller shows to the user (the exact command, or the page that will open)
  before anything runs.
* An unknown answer is "manual", never a guess. Where a distro genuinely has
  no package — RyzenAdj is not in Debian, Ubuntu or Fedora's repos — the plan
  says so and points at upstream's instructions instead of running a package
  manager command that would only fail confusingly.
"""

import os
import re
import urllib.request
import zipfile

# GitHub's API rejects requests without one.
USER_AGENT = "FrameworkGUI/1.0 (+https://github.com/Tri-Lumen/Framework-Tool-GUI)"

# Kinds of install plan a dependency can produce.
KIND_PACKAGE = "package"    # run a package-manager command
KIND_WINGET = "winget"      # run winget (a package command, named for clarity)
KIND_DOWNLOAD = "download"  # fetch a release archive and unpack it locally
KIND_MANUAL = "manual"      # open a page; a human has to take it from here

DEPENDENCIES = (
    {
        "id": "framework_tool",
        "name": "framework_tool",
        "why": "The Framework CLI everything else in this app drives. "
               "Without it this app can do nothing at all.",
        "probe": ("framework_tool", "framework-tool"),
        "vendors": None,          # relevant on every machine
        "homepage": "https://github.com/FrameworkComputer/framework-system",
        "windows": {"kind": KIND_WINGET, "package": "framework_tool",
                    "source": "winget"},
        # Packaged for a few distros under different names, absent from most.
        # Upstream's README is the honest answer rather than a command that
        # fails on whatever the user is actually running.
        "linux": {"kind": KIND_MANUAL,
                  "note": "Packaged as framework-system on some distros "
                          "(AUR: framework-system-git). If yours does not "
                          "have it, build it from upstream's README."},
    },
    {
        "id": "ryzenadj",
        "name": "RyzenAdj",
        "why": "Sets real sustained/boost power limits (STAPM, PPT) on AMD "
               "Ryzen APUs — the TDP control on the CPU limits pane.",
        "probe": ("ryzenadj",),
        "vendors": ("amd",),
        "homepage": "https://github.com/FlyGoat/RyzenAdj",
        # Asset names change between releases, so the release is resolved at
        # runtime through the GitHub API and matched on a substring instead
        # of hardcoding a filename that will rot.
        #
        # "win64" alone is ambiguous: the release carries both
        # `ryzenadj-win64.zip` (the CLI) and `libryzenadj-win64.zip` (the
        # library — DLL, .lib and header, no ryzenadj.exe at all). The
        # matcher used to take whichever came first, which was the library,
        # so the download "succeeded" and then reported that ryzenadj.exe
        # was nowhere in the tools directory. `binary` is what breaks the
        # tie — see pick_asset.
        "windows": {"kind": KIND_DOWNLOAD, "repo": "FlyGoat/RyzenAdj",
                    "asset_match": "win64", "binary": "ryzenadj.exe"},
        "linux": {"kind": KIND_PACKAGE, "packages": {"yay": "ryzenadj",
                                                     "paru": "ryzenadj"},
                  "note": "In the AUR only. On other distros build it from "
                          "upstream's README — it needs pciutils and cmake."},
    },
    {
        "id": "throttlestop",
        "name": "ThrottleStop",
        "why": "Intel power/turbo tuning on Windows. It has no command line, "
               "so this app can install and launch it but cannot drive it.",
        "probe": ("ThrottleStop", "ThrottleStop.exe"),
        "vendors": ("intel",),
        "homepage": "https://www.techpowerup.com/download/techpowerup-throttlestop/",
        "windows": {"kind": KIND_MANUAL,
                    "note": "Downloaded as a zip you unpack yourself; it is "
                            "not in winget."},
        "linux": None,  # Windows-only program
    },
)

_BY_ID = {d["id"]: d for d in DEPENDENCIES}

# Package managers, most preferred first. AUR helpers come before pacman
# because the packages we want on Arch live in the AUR, which pacman itself
# will not install.
LINUX_MANAGERS = ("yay", "paru", "pacman", "apt-get", "dnf", "zypper")


def get(dep_id):
    return _BY_ID[dep_id]


def relevant(os_name, vendor=None):
    """Dependencies worth showing on this machine.

    Vendor-specific tools are hidden on the wrong CPU, but only when the
    vendor is actually known — an unknown vendor shows everything, the same
    fail-open direction parsers.detect_model() takes.
    """
    out = []
    for dep in DEPENDENCIES:
        if dep.get(os_name, "missing") is None:
            continue  # explicitly not applicable to this OS
        vendors = dep.get("vendors")
        if vendors and vendor and vendor not in vendors and vendor != "unknown":
            continue
        out.append(dep)
    return out


def find(dep, which):
    """Installed path of a dependency, or None. `which` is shutil.which."""
    for name in dep["probe"]:
        p = which(name)
        if p:
            return p
    return None


def linux_manager(which):
    """First supported package manager present, or None."""
    for name in LINUX_MANAGERS:
        if which(name):
            return name
    return None


def install_plan(dep, os_name, manager=None):
    """How to install `dep` here.

    Returns a dict with 'kind', a human 'summary', and depending on kind a
    'cmd' (argv list), a 'url', and/or a 'note'. Never returns None: an
    entry with no automated path still yields a manual plan pointing at its
    homepage, because "there is nothing I can do" is more useful phrased as
    "here is the page you need".
    """
    spec = dep.get(os_name)
    manual = {
        "kind": KIND_MANUAL,
        "url": dep["homepage"],
        "summary": f"Open the {dep['name']} download page",
        "note": (spec or {}).get("note") if isinstance(spec, dict) else None,
    }
    if not spec:
        manual["note"] = f"{dep['name']} is not available for this platform."
        return manual

    kind = spec["kind"]
    if kind == KIND_WINGET:
        cmd = ["winget", "install", "--exact", spec["package"]]
        if spec.get("source"):
            cmd += ["--source", spec["source"]]
        cmd += ["--accept-package-agreements", "--accept-source-agreements"]
        return {"kind": KIND_WINGET, "cmd": cmd,
                "summary": " ".join(cmd), "note": spec.get("note")}

    if kind == KIND_PACKAGE:
        package = (spec.get("packages") or {}).get(manager)
        if not package:
            manual["note"] = spec.get("note") or manual["note"]
            return manual
        if manager in ("yay", "paru"):
            cmd = [manager, "-S", "--needed", package]
        elif manager == "pacman":
            cmd = ["pacman", "-S", "--needed", package]
        elif manager == "apt-get":
            cmd = ["apt-get", "install", "-y", package]
        elif manager == "dnf":
            cmd = ["dnf", "install", "-y", package]
        else:
            cmd = [manager, "install", "-y", package]
        return {"kind": KIND_PACKAGE, "cmd": cmd,
                "summary": " ".join(cmd), "note": spec.get("note")}

    if kind == KIND_DOWNLOAD:
        return {"kind": KIND_DOWNLOAD, "repo": spec["repo"],
                "asset_match": spec["asset_match"],
                "binary": spec.get("binary"),
                "summary": f"Download the latest {spec['asset_match']} release "
                           f"of {spec['repo']} from GitHub into "
                           f"{tools_dir()}",
                "note": spec.get("note")}

    return manual


# ---------- GitHub release downloads ----------

def github_latest_api(repo):
    return f"https://api.github.com/repos/{repo}/releases/latest"


# Asset name fragments that mark a build which is *related to* the tool but
# is not the tool: the library packaging, debug symbols, a source tarball.
# Matched at the start of the name or after a - or _ so a legitimate asset
# that merely contains the letters (…-libre-…) is not penalised.
ASSET_PENALTY = ("lib", "debug", "symbols", "dev", "src", "source", "pdb")

ARCHIVE_SUFFIXES = (".zip", ".7z", ".tar.gz", ".tgz", ".tar.xz")

# Whole words only. A bare substring test marks `tool-win64-device.zip` as a
# "dev" build and `my-devkit-win64.zip` too — the fragment has to be the
# whole token, not merely inside one. `lib` is the exception and is matched
# as a prefix as well, because that is how library packaging is named:
# `libryzenadj-win64.zip`, no separator.
_PENALTY_RE = re.compile(
    r"(?:^|[-_.])(?:{})(?:$|[-_.])".format("|".join(ASSET_PENALTY)))


def _penalised(name):
    low = name.lower()
    return bool(_PENALTY_RE.search(low)) or low.startswith("lib")


def asset_score(name, match, binary=None):
    """How well a release asset answers "the build containing `binary`".

    Higher is better. Split out from pick_asset so the ranking is directly
    testable — the RyzenAdj release is the case that matters, where two
    assets match the substring and only one carries the executable.
    """
    low = (name or "").lower()
    if match.lower() not in low:
        return None
    score = 0
    if low.endswith(ARCHIVE_SUFFIXES):
        score += 8
    stem = (binary or "").rsplit(".", 1)[0].lower()
    if stem:
        if low.startswith(stem):
            score += 4      # ryzenadj-win64.zip — this is the one
        elif stem in low:
            score += 1      # libryzenadj-win64.zip — related, not it
    if _penalised(low):
        score -= 6
    return score


def pick_asset(assets, match, binary=None):
    """Pick a release asset by case-insensitive substring.

    `assets` is the GitHub API's asset list. Returns the asset dict or None;
    None means the caller should fall back to opening the releases page,
    which is what happens when upstream renames its artifacts.

    `binary` is the executable the caller is actually after. Passing it is
    what stops a release that ships both a library and a CLI under matching
    names from handing back the library. Ties keep the API's own order, so
    the choice is deterministic.
    """
    scored = []
    for index, asset in enumerate(assets or []):
        score = asset_score(asset.get("name") or "", match, binary)
        if score is not None:
            scored.append((-score, index, asset))
    if not scored:
        return None
    scored.sort(key=lambda row: (row[0], row[1]))
    return scored[0][2]


def tools_dir(environ=None):
    """Where downloaded helper binaries go.

    Under the user's own data directory, never next to the app: on Windows
    the app may live in Program Files, and on Linux inside a read-only
    Flatpak.
    """
    env = environ if environ is not None else os.environ
    local = env.get("LOCALAPPDATA")
    if local:
        return os.path.join(local, "FrameworkGUI", "tools")
    base = env.get("XDG_DATA_HOME") or os.path.join(
        env.get("HOME", os.path.expanduser("~")), ".local", "share")
    return os.path.join(base, "framework-gui", "tools")


# Path traversal guard for archive members: a crafted zip with ../ entries
# would otherwise write outside the tools directory.
RE_UNSAFE_MEMBER = re.compile(r"(^/)|(^[A-Za-z]:)|(\.\.[\\/])")


def safe_members(names):
    return [n for n in names if not RE_UNSAFE_MEMBER.search(n)]


def extract_zip(archive_path, dest_dir):
    """Unpack a downloaded release zip, skipping unsafe member paths.

    Returns the list of extracted names.
    """
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(archive_path) as zf:
        members = safe_members(zf.namelist())
        zf.extractall(dest_dir, members=members)
    return members


# ---------- cleanup ----------
#
# Unpacking leaves the archive behind, and every reinstall drops another
# one, so the tools directory accumulated a copy of every release ever
# downloaded. The unpacked payload is what the app uses; the archive is
# spent the moment extraction succeeds.
#
# Only the archives go. The DLLs beside ryzenadj.exe (WinRing0x64, inpoutx64)
# are what let it talk to the SoC at all, so "tidying" the unpacked tree
# would break the tool this just installed.

def is_archive(path):
    return (path or "").lower().endswith(ARCHIVE_SUFFIXES)


def cleanup_targets(dest_dir, keep=(), lister=None, isfile=None):
    """Archives in the tools directory that installing has finished with.

    `keep` names files to spare. I/O is injected so the decision is
    testable without a filesystem.
    """
    ls = lister or (lambda d: os.listdir(d) if os.path.isdir(d) else [])
    isf = isfile or os.path.isfile
    spared = {os.path.basename(k) for k in keep}
    out = []
    for name in sorted(ls(dest_dir)):
        if name in spared or not is_archive(name):
            continue
        path = os.path.join(dest_dir, name)
        if isf(path):
            out.append(path)
    return out


def cleanup(dest_dir, keep=(), lister=None, isfile=None, remove=None):
    """Delete spent archives. Returns (removed, failed) as name lists.

    Never raises: a file the OS will not let go of is reported and skipped,
    because a failed tidy-up must not turn a successful install into an
    error.
    """
    rm = remove or os.remove
    removed, failed = [], []
    for path in cleanup_targets(dest_dir, keep, lister, isfile):
        try:
            rm(path)
            removed.append(os.path.basename(path))
        except OSError:
            failed.append(os.path.basename(path))
    return removed, failed


# ---------- fetching ----------
#
# The only network access in the whole app: resolving a helper's latest
# GitHub release and pulling down its archive. `opener` is injected so these
# are testable without a network — pass anything with the
# urlopen(request, timeout) signature.

def _open(url, opener, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return (opener or urllib.request.urlopen)(req, timeout=timeout)


def fetch_text(url, opener=None, timeout=30, limit=4_000_000):
    """GET a URL as text. `limit` caps how much is read into memory."""
    with _open(url, opener, timeout) as resp:
        raw = resp.read(limit)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return raw


def filename_for(url, fallback="download"):
    """Filename to save a URL as, sanitised for both OSes."""
    path = url.split("?", 1)[0].split("#", 1)[0]
    name = path.rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or fallback


def download_file(url, dest_dir, opener=None, timeout=120, progress=None,
                  chunk=64 * 1024):
    """Stream a URL to `dest_dir`, returning the path written.

    Streams rather than reading into memory. `progress(done, total_or_None)`
    is called as it goes so the GUI can report something during a long
    download; a total of None means the server sent no Content-Length.
    """
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, filename_for(url))
    with _open(url, opener, timeout) as resp:
        total = resp.headers.get("Content-Length") if hasattr(
            resp, "headers") else None
        total = int(total) if total and str(total).isdigit() else None
        done = 0
        with open(path, "wb") as fh:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                fh.write(block)
                done += len(block)
                if progress:
                    progress(done, total)
    return path


def find_in_tree(root, filename, walker=None):
    """Locate a binary inside an unpacked release tree (they nest it)."""
    walk = walker or os.walk
    target = filename.lower()
    for dirpath, _dirs, files in walk(root):
        for f in files:
            if f.lower() == target:
                return os.path.join(dirpath, f)
    return None
