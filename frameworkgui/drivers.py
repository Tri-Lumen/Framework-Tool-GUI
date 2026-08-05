"""
Framework driver/BIOS download pages, per device build.

This module is a link catalog and nothing else. It deliberately does not
fetch, scrape or download: Framework publishes a downloads list per device
build, those lists are always current, and pointing a browser at the right
one is both more reliable and more honest than trying to guess which file on
the page is "the" bundle.

Two catalogs:

* CATALOG maps the board string framework_tool reports (`--versions` ->
  `Type: Laptop 13 (AMD Ryzen AI 300 Series)`) to that build's downloads
  page. The board strings and the page titles line up almost word for word,
  so matching is substring-based and stays readable. The whole catalog is
  also shown in the UI, so a user whose board is misdetected — or who is
  fetching drivers for a different machine — can still get there.
* EXTRA maps *swappable* parts to their vendor's download page — a
  replacement Wi-Fi card, a Graphics Module, an expansion bay. The driver
  bundle covers what the machine shipped with; it does not necessarily
  cover what someone put in afterwards.

URLs rot. They are all in these two tables and nowhere else, so fixing one
is a one-line change, and every lookup falls back to the Knowledge Base
index rather than dead-ending.
"""

KB_INDEX = "https://knowledgebase.frame.work/bios-and-drivers-downloads-rJ3PaCexh"

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


def all_resources():
    """Every device build's downloads page, plus the index, in menu order.

    The whole catalog is offered, not just the detected build: detection can
    miss, and people fetch drivers for machines they are not sitting at.
    """
    return [dict(entry) for entry in CATALOG] + [dict(INDEX_ENTRY)]
