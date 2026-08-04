"""Unit tests for drivers.py — the catalog of Framework download pages.

The board strings here are the same ones test_parsers.py feeds to
detect_model(), so the two stay in step: whatever framework_tool reports as
`Type:` is exactly what resource_for() has to match.

There is nothing to mock: the module is links only. It used to fetch and
scrape those pages, and TestNoNetworking keeps it that way.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import drivers  # noqa: E402


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


class TestAllResources(unittest.TestCase):

    def test_lists_every_build_plus_the_index(self):
        got = drivers.all_resources()
        self.assertEqual(len(got), len(drivers.CATALOG) + 1)
        self.assertEqual(got[-1]["url"], drivers.KB_INDEX)

    def test_labels_are_unique(self):
        # The UI keys its combobox off the label, so duplicates would make
        # one of the builds unreachable.
        labels = [e["label"] for e in drivers.all_resources()]
        self.assertEqual(len(labels), len(set(labels)))

    def test_urls_are_unique(self):
        urls = [e["url"] for e in drivers.all_resources()]
        self.assertEqual(len(urls), len(set(urls)))

    def test_callers_cannot_mutate_the_catalog(self):
        got = drivers.all_resources()
        got[0]["url"] = "https://example.invalid"
        self.assertNotEqual(drivers.CATALOG[0]["url"], "https://example.invalid")

    def test_every_detected_build_is_also_in_the_list(self):
        # resource_for() and the dropdown must agree, or the tab would show
        # a build at the top that cannot be selected below.
        labels = {e["label"] for e in drivers.all_resources()}
        for board in ("Laptop 12 (13th Gen Intel Core)",
                      "Laptop 13 (AMD Ryzen AI 300 Series)",
                      "Laptop 16 (AMD Ryzen 7040HS Series)",
                      "Desktop (AMD Ryzen AI Max 300 Series)",
                      "Something unrecognised"):
            with self.subTest(board=board):
                self.assertIn(drivers.resource_for(board)["label"], labels)


class TestNoNetworking(unittest.TestCase):

    def test_module_does_not_fetch_anything(self):
        """This module is a link catalog — nothing here should hit the net.

        Framework's Knowledge Base 403s scripted fetches anyway, so the app
        links to the downloads lists instead of scraping them. If a fetch
        creeps back in, it belongs in deps.py with the rest of the I/O.
        """
        with open(drivers.__file__, encoding="utf-8") as fh:
            source = fh.read()
        for forbidden in ("urllib", "http.client", "requests", "socket"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
