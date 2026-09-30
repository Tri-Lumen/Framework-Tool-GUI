"""Unit tests for updater.py — version comparison and asset selection.

No network here: `describe()` takes an already-parsed release body, the same
shape `json.loads(deps.fetch_text(...))` produces, so the whole decision
(is there something newer, and where is its asset) is testable without
mocking HTTP.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frameworkgui import updater  # noqa: E402


class TestDownloadsDir(unittest.TestCase):

    def test_is_a_sibling_of_the_tools_dir(self):
        from frameworkgui import deps
        env = {"XDG_DATA_HOME": "/xdg-data"}
        tools = deps.tools_dir(env)
        downloads = updater.downloads_dir(env)
        self.assertEqual(os.path.dirname(downloads), os.path.dirname(tools))
        self.assertEqual(os.path.basename(downloads), "updates")
        self.assertNotEqual(downloads, tools)


class TestParseVersion(unittest.TestCase):

    def test_plain_version(self):
        self.assertEqual(updater.parse_version("1.2.3"), (1, 2, 3))

    def test_leading_v_is_accepted(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))

    def test_trailing_suffix_is_ignored(self):
        self.assertEqual(updater.parse_version("v1.2.3-rc1"), (1, 2, 3))

    def test_garbage_returns_none(self):
        for text in ("", "not-a-version", None, "v", "latest"):
            self.assertIsNone(updater.parse_version(text))


class TestIsNewer(unittest.TestCase):

    def test_a_higher_patch_is_newer(self):
        self.assertTrue(updater.is_newer("1.0.0", "1.0.1"))

    def test_a_higher_minor_beats_a_higher_patch_on_the_old_side(self):
        self.assertTrue(updater.is_newer("1.0.9", "1.1.0"))

    def test_equal_versions_are_not_newer(self):
        self.assertFalse(updater.is_newer("1.0.0", "1.0.0"))

    def test_an_older_release_is_not_newer(self):
        self.assertFalse(updater.is_newer("1.2.0", "1.1.0"))

    def test_v_prefix_does_not_matter(self):
        self.assertTrue(updater.is_newer("1.0.0", "v1.0.1"))

    def test_unparseable_current_is_not_newer(self):
        # Would rather stay silent than tell someone running a dev build
        # that a release exists when it cannot even compare against it.
        self.assertFalse(updater.is_newer("dev", "1.0.0"))

    def test_unparseable_latest_is_not_newer(self):
        self.assertFalse(updater.is_newer("1.0.0", "not-a-version"))


class TestAssetUrl(unittest.TestCase):

    RELEASE = {
        "assets": [
            {"name": "FrameworkGUI.exe", "browser_download_url": "u/exe"},
            {"name": "FrameworkGUI-Setup.exe", "browser_download_url": "u/setup"},
            {"name": "FrameworkGUI.flatpak", "browser_download_url": "u/flatpak"},
        ],
    }

    def test_finds_the_named_asset(self):
        self.assertEqual(updater.asset_url(self.RELEASE, "FrameworkGUI.flatpak"),
                         "u/flatpak")

    def test_no_match_is_none(self):
        self.assertIsNone(updater.asset_url(self.RELEASE, "nope.zip"))

    def test_no_assets_key_is_none(self):
        self.assertIsNone(updater.asset_url({}, "FrameworkGUI.exe"))

    def test_none_release_is_none(self):
        self.assertIsNone(updater.asset_url(None, "FrameworkGUI.exe"))


class TestDescribe(unittest.TestCase):

    def release(self, tag, assets=None):
        return {"tag_name": tag, "html_url": "https://example/" + tag,
               "assets": assets or []}

    def test_a_newer_release_is_reported(self):
        result = updater.describe(self.release("v1.1.0"), "windows", "1.0.0")
        self.assertTrue(result["newer"])
        self.assertEqual(result["latest"], "1.1.0")
        self.assertEqual(result["current"], "1.0.0")

    def test_the_current_release_is_not_newer(self):
        result = updater.describe(self.release("v1.0.0"), "windows", "1.0.0")
        self.assertFalse(result["newer"])

    def test_asset_for_the_right_platform_is_picked(self):
        assets = [{"name": "FrameworkGUI-Setup.exe",
                  "browser_download_url": "u/win"},
                 {"name": "FrameworkGUI.flatpak",
                  "browser_download_url": "u/linux"}]
        windows = updater.describe(self.release("v2.0.0", assets),
                                   "windows", "1.0.0")
        linux = updater.describe(self.release("v2.0.0", assets),
                                 "linux", "1.0.0")
        self.assertEqual(windows["asset_url"], "u/win")
        self.assertEqual(linux["asset_url"], "u/linux")

    def test_unknown_platform_has_no_asset(self):
        result = updater.describe(self.release("v2.0.0"), "bsd", "1.0.0")
        self.assertIsNone(result["asset_name"])
        self.assertIsNone(result["asset_url"])

    def test_missing_asset_for_a_known_platform_is_none_not_an_error(self):
        # release.yml renamed or dropped the asset - not this module's job
        # to guess at a replacement.
        result = updater.describe(self.release("v2.0.0", assets=[]),
                                  "windows", "1.0.0")
        self.assertIsNone(result["asset_url"])

    def test_empty_release_describes_as_nothing_newer(self):
        result = updater.describe({}, "windows", "1.0.0")
        self.assertFalse(result["newer"])
        self.assertIsNone(result["latest"])

    def test_none_release_does_not_raise(self):
        result = updater.describe(None, "windows", "1.0.0")
        self.assertFalse(result["newer"])


if __name__ == "__main__":
    unittest.main()
