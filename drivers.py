"""
Framework driver/BIOS resources for a detected system, plus the ones for
parts a user may have added themselves.

Two catalogs:

* CATALOG maps the board string framework_tool reports (`--versions` ->
  `Type: Laptop 13 (AMD Ryzen AI 300 Series)`) to that system's Framework
  Knowledge Base page, which is where the Windows driver bundle and BIOS
  live. The board strings and the page titles line up almost word for word,
  so matching is substring-based and stays readable.
* EXTRA maps *swappable* parts to their vendor's download page — a
  replacement Wi-Fi card, a Graphics Module, an expansion bay. The driver
  bundle covers what the machine shipped with; it does not necessarily
  cover what someone put in afterwards.

URLs rot. They are all in these two tables and nowhere else, so fixing one
is a one-line change, and every lookup falls back to the Knowledge Base
index rather than dead-ending.

Downloading is best-effort in exactly the way the CLI parsers are: the page
is fetched and scanned for a bundle link, and if that fails for any reason —
the site changed, a bot check, no network — the caller opens the page in a
browser instead. This module contains the URL logic and the scraping; the
GUI owns the threading and the browser.
"""

import os
import re
import urllib.request

KB_INDEX = "https://knowledgebase.frame.work/bios-and-drivers-downloads-rJ3PaCexh"

# Sites serving driver bundles reject the stdlib's default User-Agent.
USER_AGENT = "FrameworkGUI/1.0 (+https://github.com/Tri-Lumen/Framework-Tool-GUI)"

# Most specific first: the first entry whose every `match` fragment appears
# in the board string wins, so "Laptop 13 Pro" must precede "Laptop 13".
CATALOG = (
    {"match": ("laptop 13 pro", "ryzen ai 300"),
     "label": "Framework Laptop 13 Pro (AMD Ryzen AI 300 Series)",
     "url": "https://knowledgebase.frame.work/framework-laptop-13-pro-bios-and-driver-releases-amd-ryzen-ai-300-series-S1HadESpbl"},
    {"match": ("laptop 13 pro", "core ultra"),
     "label": "Framework Laptop 13 Pro (Intel Core Ultra Series 3)",
     "url": "https://knowledgebase.frame.work/framework-laptop-13-pro-bios-and-driver-releases-intel-core-ultra-series-3-SytO_NS6Wl"},
    {"match": ("laptop 16", "ryzen ai 300"),
     "label": "Framework Laptop 16 (AMD Ryzen AI 300 Series)",
     "url": "https://knowledgebase.frame.work/framework-laptop-16-bios-and-driver-releases-amd-ryzen-ai-300-series-SJ72iJntel"},
    {"match": ("laptop 16",),
     "label": "Framework Laptop 16 (AMD Ryzen 7040 Series)",
     "url": "https://knowledgebase.frame.work/framework-laptop-16-bios-and-driver-releases-amd-ryzen-7040-series-BkeqkVovp"},
    {"match": ("laptop 12",),
     "label": "Framework Laptop 12 (13th Gen Intel Core)",
     "url": "https://knowledgebase.frame.work/framework-laptop-12-bios-and-driver-releases-13th-gen-intel-core-HyrqeX2ex"},
    {"match": ("desktop",),
     "label": "Framework Desktop (AMD Ryzen AI Max 300 Series)",
     "url": "https://knowledgebase.frame.work/en_us/framework-desktop-bios-and-driver-releases-amd-ryzen-ai-max-300-series-BJHcn1Y4gg"},
    {"match": ("ryzen ai 300",),
     "label": "Framework Laptop 13 (AMD Ryzen AI 300 Series)",
     "url": "https://knowledgebase.frame.work/en_us/framework-laptop-13-bios-and-driver-releases-amd-ryzen-ai-300-series-r1wqKAs1e"},
    {"match": ("ryzen 7040",),
     "label": "Framework Laptop 13 (AMD Ryzen 7040 Series)",
     "url": "https://knowledgebase.frame.work/en_us/framework-laptop-13-bios-and-driver-releases-amd-ryzen-7040-series-r1rXGVL16"},
    {"match": ("core ultra",),
     "label": "Framework Laptop 13 (Intel Core Ultra Series 1)",
     "url": "https://knowledgebase.frame.work/en_us/framework-laptop-bios-and-driver-releases-intel-core-ultra-series-1-H1nZQdxYR"},
    {"match": ("13th gen",),
     "label": "Framework Laptop 13 (13th Gen Intel Core)",
     "url": "https://knowledgebase.frame.work/framework-laptop-bios-and-driver-releases-13th-gen-intel-core-BkQBvKWr3"},
    {"match": ("12th gen",),
     "label": "Framework Laptop 13 (12th Gen Intel Core)",
     "url": "https://knowledgebase.frame.work/framework-laptop-bios-and-driver-releases-12th-gen-intel-core-Bkx2kosqq"},
    {"match": ("11th gen",),
     "label": "Framework Laptop 13 (11th Gen Intel Core)",
     "url": "https://knowledgebase.frame.work/en_us/framework-laptop-bios-releases-S1dMQt6F"},
)

INDEX_ENTRY = {
    "match": (),
    "label": "All Framework BIOS and driver downloads",
    "url": KB_INDEX,
}

# Parts people swap in. Vendor support hubs rather than direct file links:
# the hubs survive driver releases, the file links do not.
EXTRA = (
    {"id": "amd-gpu",
     "label": "AMD graphics driver (Graphics Module / Radeon)",
     "why": "The Laptop 16 Graphics Module and AMD iGPUs get newer drivers "
            "from AMD than the Framework bundle carries.",
     "vendors": ("amd",),
     "url": "https://www.amd.com/en/support"},
    {"id": "intel-gpu",
     "label": "Intel graphics driver",
     "why": "Arc/Iris Xe driver updates ship from Intel between Framework "
            "bundle releases.",
     "vendors": ("intel",),
     "url": "https://www.intel.com/content/www/us/en/download-center/home.html"},
    {"id": "intel-wifi",
     "label": "Intel Wi-Fi / Bluetooth driver (AX210, BE200, …)",
     "why": "For an Intel card fitted to a machine that did not ship with "
            "one — common on AMD boards, whose bundle carries the MediaTek "
            "driver instead.",
     "vendors": None,
     "url": "https://www.intel.com/content/www/us/en/download-center/home.html"},
    {"id": "mediatek-wifi",
     "label": "MediaTek Wi-Fi driver (RZ616, RZ717)",
     "why": "The card AMD Framework laptops ship with. Its driver is inside "
            "the Framework bundle above; MediaTek does not publish a "
            "standalone consumer download, so use the bundle or Windows "
            "Update.",
     "vendors": ("amd",),
     "url": KB_INDEX},
    {"id": "qualcomm-wifi",
     "label": "Qualcomm/Atheros Wi-Fi driver",
     "why": "For an aftermarket Qualcomm card.",
     "vendors": None,
     "url": "https://www.qualcomm.com/support"},
)

# Files worth offering off a Knowledge Base page. .cab and .msi show up for
# firmware/driver installers; .7z and .tar.gz never have so far but cost
# nothing to accept.
DOWNLOAD_EXTS = (".exe", ".zip", ".msi", ".cab", ".7z", ".tar.gz")

RE_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
RE_TAG = re.compile(r"<[^>]+>")


def resource_for(board):
    """Knowledge Base entry for a board string from `--versions`.

    Falls back to the index page, never to nothing: an unrecognised board is
    a reason to hand someone the list of all downloads, not to tell them
    there is nothing available.
    """
    text = (board or "").lower()
    for entry in CATALOG:
        if entry["match"] and all(frag in text for frag in entry["match"]):
            return dict(entry, exact=True)
    return dict(INDEX_ENTRY, exact=False)


def extras_for(vendor=None):
    """Add-in-part driver links, filtered to a known CPU vendor."""
    out = []
    for entry in EXTRA:
        vendors = entry.get("vendors")
        if vendors and vendor and vendor not in vendors and vendor != "unknown":
            continue
        out.append(entry)
    return out


def _absolute(url, base):
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return "https:" + url
    m = re.match(r"(https?://[^/]+)", base or "")
    root = m.group(1) if m else ""
    if url.startswith("/"):
        return root + url
    return base.rsplit("/", 1)[0] + "/" + url if base else url


def find_downloads(html, base_url=""):
    """Downloadable links on a Knowledge Base page, in page order.

    Returns [{'url', 'name'}]. Duplicates are collapsed, since these pages
    link the same bundle from a button and from body text. An empty list is
    the expected outcome when the page markup changes — the caller opens the
    page in a browser rather than guessing.
    """
    seen = set()
    out = []
    for m in RE_HREF.finditer(html or ""):
        raw = m.group(1).strip()
        if not raw or raw.startswith(("#", "mailto:", "javascript:")):
            continue
        url = _absolute(raw, base_url)
        path = url.split("?", 1)[0].split("#", 1)[0]
        if not path.lower().endswith(DOWNLOAD_EXTS):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "name": filename_for(url)})
    return out


def filename_for(url, fallback="download"):
    """Filename to save a URL as, sanitised for both OSes."""
    path = url.split("?", 1)[0].split("#", 1)[0]
    name = path.rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or fallback


def download_dir(environ=None):
    """The user's Downloads folder, falling back to the home directory."""
    env = environ if environ is not None else os.environ
    home = env.get("USERPROFILE") or env.get("HOME") or os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    return downloads if os.path.isdir(downloads) else home


# ---------- fetching ----------
#
# `opener` is injected so these are testable without a network: pass
# anything with the urlopen(request, timeout) signature.

def _open(url, opener, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return (opener or urllib.request.urlopen)(req, timeout=timeout)


def fetch_text(url, opener=None, timeout=30, limit=4_000_000):
    """GET a page as text. `limit` caps how much is read into memory."""
    with _open(url, opener, timeout) as resp:
        raw = resp.read(limit)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return raw


def download_file(url, dest_dir, opener=None, timeout=120, progress=None,
                  chunk=64 * 1024):
    """Stream a URL to `dest_dir`, returning the path written.

    Streams rather than reading into memory — driver bundles run to hundreds
    of megabytes. `progress(bytes_done, total_or_None)` is called as it goes
    so the GUI can report something during a long download; a total of None
    means the server sent no Content-Length.
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
