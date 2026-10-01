"""
Checking for a newer release of this app, and downloading it — never
installing it.

Same rules as `deps.py`'s GitHub download path, applied to the app itself:
nothing runs automatically (checking is a button, same as everything else
in this project), and installing what gets downloaded is left to the user.
This app has never executed a downloaded installer on anyone's behalf —
see CLAUDE.md's "Deliberately out of scope" — and a self-updater is not the
exception that changes that; it downloads `FrameworkGUI-Setup.exe` or
`FrameworkGUI.flatpak` next to where `deps.py` already keeps downloaded
helper tools and stops there.

Stdlib only, no toolkit import, so version comparison and asset selection
are testable without a network — the actual HTTP call is made by the
caller (`app.py`) with `deps.fetch_text`, the same function the RyzenAdj
download already uses, so there is exactly one code path in the whole app
that speaks HTTP.
"""

import os
import re

from . import deps

REPO = "Tri-Lumen/Framework-Tool-GUI"

# The exact three names release.yml publishes (see CLAUDE.md's Releasing
# table) — matched verbatim rather than guessed at, so a renamed asset shows
# up as "no asset for this platform" instead of silently downloading the
# wrong file.
ASSET_NAMES = {
    "windows": "FrameworkGUI-Setup.exe",
    "linux": "FrameworkGUI.flatpak",
}

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def parse_version(text):
    """A version string as an (major, minor, patch) tuple, or None.

    Accepts a leading 'v' (release.yml's tag format) and ignores anything
    after the third number (a -rc1 suffix, build metadata) — the same
    "match what the docs promise, fall back rather than guess" instinct the
    CLI-output parsers in parsers.py follow.
    """
    match = _VERSION_RE.search(text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_newer(current, latest):
    """True when `latest` names a newer version than `current`.

    Either side failing to parse compares as "not newer" rather than
    raising: a draft or pre-release tag that does not look like a version
    must not make the app claim an update exists when it cannot even say
    what the update is.
    """
    current_v, latest_v = parse_version(current), parse_version(latest)
    if current_v is None or latest_v is None:
        return False
    return latest_v > current_v


def asset_url(release, name):
    """The browser_download_url of the asset named exactly `name`, or None."""
    for asset in (release or {}).get("assets") or []:
        if asset.get("name") == name:
            return asset.get("browser_download_url")
    return None


def downloads_dir(environ=None):
    """Where a downloaded release asset is saved.

    A sibling of `deps.tools_dir()`, under the same per-OS base directory,
    in its own subfolder so a downloaded app update is never mistaken for
    an installed helper binary.
    """
    return os.path.join(os.path.dirname(deps.tools_dir(environ)), "updates")


def describe(release, os_name, current_version):
    """The GitHub API's `.../releases/latest` body, boiled down to what the
    Setup pane needs to render: whether a newer release exists, what to
    call it, and where its asset for this platform is (if release.yml
    still publishes one under the name this app expects).

    Never raises: a malformed or empty `release` describes itself as
    "nothing newer", the same fail-quiet direction `deps.install_plan`
    takes for a dependency with no install path, rather than surfacing a
    KeyError as if the update check itself were the failure.
    """
    release = release or {}
    tag = release.get("tag_name") or ""
    latest = tag[1:] if tag.startswith("v") else tag
    name = ASSET_NAMES.get(os_name)
    return {
        "current": current_version,
        "latest": latest or None,
        "newer": is_newer(current_version, latest),
        "html_url": release.get("html_url"),
        "asset_name": name,
        "asset_url": asset_url(release, name) if name else None,
    }
