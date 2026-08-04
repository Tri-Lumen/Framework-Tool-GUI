"""Unit tests for drivers.py — matching a detected board to Framework's
download page, and scraping that page for a bundle.

The board strings here are the same ones test_parsers.py feeds to
detect_model(), so the two stay in step: whatever framework_tool reports as
`Type:` is exactly what resource_for() has to match.

Fetching is exercised with a fake opener — no network, and the tests still
cover the parts that actually go wrong (a page that 403s, a page whose
markup changed, a filename with junk in it).
"""

import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import drivers  # noqa: E402


class FakeResponse(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def opener_for(data, headers=None):
    def open_it(_request, timeout=None):
        return FakeResponse(data, headers)
    return open_it


def failing_opener(exc):
    def open_it(_request, timeout=None):
        raise exc
    return open_it


class TestResourceMatching(unittest.TestCase):

    def test_laptop12(self):
        got = drivers.resource_for("Laptop 12 (13th Gen Intel Core)")
        self.assertTrue(got["exact"])
        self.assertIn("laptop-12", got["url"])

    def test_laptop13_ryzen_ai_300(self):
        got = drivers.resource_for("Laptop 13 (AMD Ryzen AI 300 Series)")
        self.assertTrue(got["exact"])
        self.assertIn("laptop-13-bios-and-driver-releases-amd-ryzen-ai-300",
                      got["url"])

    def test_laptop16_7040_and_ai300_differ(self):
        old = drivers.resource_for("Laptop 16 (AMD Ryzen 7040HS Series)")
        new = drivers.resource_for("Laptop 16 (AMD Ryzen AI 300 Series)")
        self.assertNotEqual(old["url"], new["url"])
        self.assertIn("7040", old["url"])

    def test_desktop(self):
        got = drivers.resource_for("Desktop (AMD Ryzen AI Max 300 Series)")
        self.assertTrue(got["exact"])
        self.assertIn("desktop", got["url"])

    def test_pro_boards_beat_the_generic_entry(self):
        # Ordering-sensitive: "Laptop 13 Pro" also contains "ryzen ai 300".
        got = drivers.resource_for("Laptop 13 Pro (AMD Ryzen AI 300 Series)")
        self.assertIn("laptop-13-pro", got["url"])

    def test_intel_generations(self):
        for board, fragment in (
                ("Laptop 13 (12th Gen Intel Core)", "12th-gen"),
                ("Laptop 13 (13th Gen Intel Core)", "13th-gen"),
                ("Laptop 13 (Intel Core Ultra Series 1)", "core-ultra")):
            with self.subTest(board=board):
                self.assertIn(fragment, drivers.resource_for(board)["url"])

    def test_unknown_board_falls_back_to_the_index(self):
        got = drivers.resource_for("Something Framework has not shipped yet")
        self.assertFalse(got["exact"])
        self.assertEqual(got["url"], drivers.KB_INDEX)

    def test_empty_board_falls_back_rather_than_raising(self):
        self.assertEqual(drivers.resource_for("")["url"], drivers.KB_INDEX)
        self.assertEqual(drivers.resource_for(None)["url"], drivers.KB_INDEX)

    def test_every_catalog_url_is_https_and_framework(self):
        for entry in drivers.CATALOG + (drivers.INDEX_ENTRY,):
            with self.subTest(entry=entry["label"]):
                self.assertTrue(entry["url"].startswith(
                    "https://knowledgebase.frame.work/"))


class TestExtras(unittest.TestCase):

    def test_amd_hides_intel_gpu_entry(self):
        ids = [e["id"] for e in drivers.extras_for("amd")]
        self.assertIn("amd-gpu", ids)
        self.assertNotIn("intel-gpu", ids)

    def test_vendor_neutral_entries_always_show(self):
        # A swapped Intel Wi-Fi card in an AMD machine is the whole point.
        for vendor in ("amd", "intel", "unknown", None):
            ids = [e["id"] for e in drivers.extras_for(vendor)]
            self.assertIn("intel-wifi", ids)

    def test_unknown_vendor_shows_everything(self):
        self.assertEqual(len(drivers.extras_for("unknown")),
                         len(drivers.EXTRA))


class TestFindDownloads(unittest.TestCase):

    HTML = """
      <a href="/download/bundle.exe">Driver Bundle</a>
      <a href="https://downloads.frame.work/bios/3.05.zip">BIOS</a>
      <a href="/download/bundle.exe">Driver Bundle (again)</a>
      <a href="/support">Support</a>
      <a href="#top">Top</a>
      <a href="mailto:x@y.z">Mail</a>
      <a href="/x/setup.exe?ver=2">Setup with query</a>
    """

    def test_only_downloadable_extensions(self):
        got = drivers.find_downloads(self.HTML, "https://kb.example/page-abc")
        names = [x["name"] for x in got]
        self.assertEqual(names, ["bundle.exe", "3.05.zip", "setup.exe"])

    def test_relative_links_are_absolutised(self):
        got = drivers.find_downloads(self.HTML, "https://kb.example/page-abc")
        self.assertEqual(got[0]["url"], "https://kb.example/download/bundle.exe")

    def test_duplicates_collapse(self):
        got = drivers.find_downloads(self.HTML, "https://kb.example/p")
        self.assertEqual(len([x for x in got if x["name"] == "bundle.exe"]), 1)

    def test_changed_markup_yields_empty_not_garbage(self):
        # Empty is the signal to open the page in a browser instead.
        self.assertEqual(drivers.find_downloads("<p>no links</p>", "u"), [])
        self.assertEqual(drivers.find_downloads("", ""), [])


class TestFilenames(unittest.TestCase):

    def test_strips_query_and_fragment(self):
        self.assertEqual(
            drivers.filename_for("https://x/y/Bundle_v2.06.exe?t=1#frag"),
            "Bundle_v2.06.exe")

    def test_sanitises_path_separators(self):
        self.assertNotIn("/", drivers.filename_for("https://x/a%2Fb/c:d.exe"))

    def test_empty_path_falls_back(self):
        self.assertEqual(drivers.filename_for("https://x/"), "download")


class TestFetching(unittest.TestCase):

    def test_fetch_text_decodes(self):
        got = drivers.fetch_text("https://x", opener=opener_for(b"<p>hi</p>"))
        self.assertEqual(got, "<p>hi</p>")

    def test_fetch_text_survives_bad_bytes(self):
        got = drivers.fetch_text("https://x", opener=opener_for(b"\xff\xfeok"))
        self.assertIn("ok", got)

    def test_fetch_errors_propagate_for_the_caller_to_fall_back_on(self):
        with self.assertRaises(OSError):
            drivers.fetch_text("https://x",
                               opener=failing_opener(OSError("403")))

    def test_download_streams_to_disk(self):
        payload = b"x" * 5000
        with tempfile.TemporaryDirectory() as tmp:
            path = drivers.download_file(
                "https://x/y/bundle.exe", tmp,
                opener=opener_for(payload, {"Content-Length": "5000"}),
                chunk=1024)
            self.assertEqual(os.path.basename(path), "bundle.exe")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), payload)

    def test_download_reports_progress(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            drivers.download_file(
                "https://x/y/b.zip", tmp,
                opener=opener_for(b"y" * 3000, {"Content-Length": "3000"}),
                progress=lambda done, total: seen.append((done, total)),
                chunk=1000)
        self.assertEqual(seen[-1], (3000, 3000))

    def test_download_without_content_length(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            drivers.download_file(
                "https://x/y/b.zip", tmp, opener=opener_for(b"z" * 10),
                progress=lambda done, total: seen.append(total))
        self.assertEqual(seen, [None])

    def test_download_creates_the_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "nested", "dir")
            drivers.download_file("https://x/f.zip", dest,
                                  opener=opener_for(b"ok"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "f.zip")))


if __name__ == "__main__":
    unittest.main()
