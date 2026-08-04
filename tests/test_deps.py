"""Unit tests for deps.py — the helper-tool registry.

The property that matters here is that no path ever produces a *silent* or
*wrong* install: every plan either has a command the user will be shown, or
degrades to a manual plan with a URL. A plan that quietly returns None, or
an apt command for a package that is not in apt, is the failure mode these
guard against.
"""

import io
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import deps  # noqa: E402


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


def which_none(_name):
    return None


def which_only(*present):
    return lambda name: f"/usr/bin/{name}" if name in present else None


class TestRegistry(unittest.TestCase):

    def test_every_entry_has_the_fields_the_gui_reads(self):
        for dep in deps.DEPENDENCIES:
            with self.subTest(dep=dep["id"]):
                for field in ("id", "name", "why", "probe", "homepage"):
                    self.assertIn(field, dep)
                self.assertTrue(dep["homepage"].startswith("https://"))

    def test_windows_only_tools_are_hidden_on_linux(self):
        ids = [d["id"] for d in deps.relevant("linux")]
        self.assertNotIn("throttlestop", ids)
        self.assertIn("ryzenadj", ids)

    def test_vendor_specific_tools_are_hidden_on_the_wrong_cpu(self):
        ids = [d["id"] for d in deps.relevant("windows", "intel")]
        self.assertNotIn("ryzenadj", ids)
        self.assertIn("throttlestop", ids)

    def test_unknown_vendor_shows_everything(self):
        # Fail-open, the same direction parsers.detect_model() takes.
        ids = [d["id"] for d in deps.relevant("windows", "unknown")]
        self.assertIn("ryzenadj", ids)
        self.assertIn("throttlestop", ids)

    def test_framework_tool_is_relevant_everywhere(self):
        for os_name in ("linux", "windows"):
            for vendor in ("amd", "intel", "arm", "unknown", None):
                ids = [d["id"] for d in deps.relevant(os_name, vendor)]
                self.assertIn("framework_tool", ids)

    def test_find_probes_every_alias(self):
        dep = deps.get("framework_tool")
        self.assertIsNone(deps.find(dep, which_none))
        self.assertEqual(deps.find(dep, which_only("framework-tool")),
                         "/usr/bin/framework-tool")


class TestLinuxManager(unittest.TestCase):

    def test_aur_helper_wins_over_pacman(self):
        # The packages we want on Arch live in the AUR, which pacman itself
        # will not install.
        self.assertEqual(deps.linux_manager(which_only("pacman", "yay")), "yay")

    def test_none_when_nothing_is_installed(self):
        self.assertIsNone(deps.linux_manager(which_none))


class TestInstallPlans(unittest.TestCase):

    def test_winget_plan_is_non_interactive(self):
        plan = deps.install_plan(deps.get("framework_tool"), "windows")
        self.assertEqual(plan["kind"], deps.KIND_WINGET)
        self.assertIn("--accept-package-agreements", plan["cmd"])
        self.assertIn("framework_tool", plan["cmd"])

    def test_aur_plan(self):
        plan = deps.install_plan(deps.get("ryzenadj"), "linux", "yay")
        self.assertEqual(plan["kind"], deps.KIND_PACKAGE)
        self.assertEqual(plan["cmd"][:2], ["yay", "-S"])

    def test_manager_without_the_package_degrades_to_manual(self):
        # RyzenAdj is not in Debian, Ubuntu or Fedora. Emitting an apt
        # command for it would fail confusingly; the manual plan says why.
        plan = deps.install_plan(deps.get("ryzenadj"), "linux", "apt-get")
        self.assertEqual(plan["kind"], deps.KIND_MANUAL)
        self.assertTrue(plan["url"])
        self.assertIn("AUR", plan["note"])

    def test_no_package_manager_at_all_degrades_to_manual(self):
        plan = deps.install_plan(deps.get("ryzenadj"), "linux", None)
        self.assertEqual(plan["kind"], deps.KIND_MANUAL)

    def test_download_plan_carries_what_the_fetcher_needs(self):
        plan = deps.install_plan(deps.get("ryzenadj"), "windows")
        self.assertEqual(plan["kind"], deps.KIND_DOWNLOAD)
        self.assertEqual(plan["repo"], "FlyGoat/RyzenAdj")
        self.assertEqual(plan["binary"], "ryzenadj.exe")

    def test_unsupported_platform_still_returns_a_plan(self):
        plan = deps.install_plan(deps.get("throttlestop"), "linux")
        self.assertEqual(plan["kind"], deps.KIND_MANUAL)
        self.assertTrue(plan["url"])

    def test_every_plan_has_a_summary_to_show_before_running(self):
        for dep in deps.DEPENDENCIES:
            for os_name in ("linux", "windows"):
                for manager in (None, "yay", "apt-get"):
                    plan = deps.install_plan(dep, os_name, manager)
                    with self.subTest(dep=dep["id"], os=os_name, mgr=manager):
                        self.assertTrue(plan.get("summary"))
                        self.assertTrue(plan.get("cmd") or plan.get("url")
                                        or plan.get("repo"))


class TestGithubAssets(unittest.TestCase):

    ASSETS = [
        {"name": "ryzenadj-linux.zip"},
        {"name": "RyzenAdj-win64.zip"},
        {"name": "RyzenAdj-win64.zip.sha256"},
    ]

    def test_pick_by_substring_prefers_archives(self):
        self.assertEqual(deps.pick_asset(self.ASSETS, "win64")["name"],
                         "RyzenAdj-win64.zip")

    def test_case_insensitive(self):
        self.assertIsNotNone(deps.pick_asset(self.ASSETS, "WIN64"))

    def test_no_match_returns_none_so_the_caller_can_fall_back(self):
        self.assertIsNone(deps.pick_asset(self.ASSETS, "macos"))
        self.assertIsNone(deps.pick_asset([], "win64"))

    def test_api_url(self):
        self.assertEqual(deps.github_latest_api("a/b"),
                         "https://api.github.com/repos/a/b/releases/latest")


class TestToolsDir(unittest.TestCase):

    def test_windows_uses_localappdata(self):
        got = deps.tools_dir({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"})
        self.assertTrue(got.endswith(os.path.join("FrameworkGUI", "tools")))

    # Expected values are built with os.path.join, not written as POSIX
    # literals: this suite also runs on the Windows CI runner, where
    # os.path.join joins with a backslash whatever the inputs look like.

    def test_linux_honours_xdg(self):
        got = deps.tools_dir({"XDG_DATA_HOME": "/home/x/.local/share"})
        self.assertEqual(
            got, os.path.join("/home/x/.local/share", "framework-gui", "tools"))

    def test_linux_default(self):
        got = deps.tools_dir({"HOME": "/home/x"})
        self.assertEqual(
            got, os.path.join("/home/x", ".local", "share", "framework-gui",
                              "tools"))


class TestArchiveSafety(unittest.TestCase):

    def test_traversal_members_are_dropped(self):
        names = ["ryzenadj.exe", "../evil.exe", "/etc/passwd",
                 r"..\evil.dll", "C:/windows/x.dll", "lib/win/libryzenadj.dll"]
        self.assertEqual(deps.safe_members(names),
                         ["ryzenadj.exe", "lib/win/libryzenadj.dll"])

    def test_extract_writes_only_safe_members(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            archive = os.path.join(tmp, "a.zip")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("nested/ryzenadj.exe", "binary")
                zf.writestr("../escaped.exe", "nope")
            dest = os.path.join(tmp, "out")
            members = deps.extract_zip(archive, dest)
            self.assertEqual(members, ["nested/ryzenadj.exe"])
            self.assertTrue(os.path.exists(
                os.path.join(dest, "nested", "ryzenadj.exe")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "escaped.exe")))


class TestFetching(unittest.TestCase):
    """The app's only network access: resolving and pulling a GitHub release."""

    def test_fetch_text_decodes(self):
        got = deps.fetch_text("https://x", opener=opener_for(b'{"tag":"v1"}'))
        self.assertEqual(got, '{"tag":"v1"}')

    def test_fetch_text_survives_bad_bytes(self):
        got = deps.fetch_text("https://x", opener=opener_for(b"\xff\xfeok"))
        self.assertIn("ok", got)

    def test_fetch_errors_propagate_for_the_caller_to_fall_back_on(self):
        # _download_dep catches this and points at the homepage instead.
        with self.assertRaises(OSError):
            deps.fetch_text("https://x", opener=failing_opener(OSError("403")))

    def test_filename_strips_query_and_fragment(self):
        self.assertEqual(
            deps.filename_for("https://x/y/RyzenAdj-win64.zip?t=1#f"),
            "RyzenAdj-win64.zip")

    def test_filename_sanitises_separators(self):
        self.assertNotIn("/", deps.filename_for("https://x/a%2Fb/c:d.zip"))

    def test_filename_falls_back(self):
        self.assertEqual(deps.filename_for("https://x/"), "download")

    def test_download_streams_to_disk(self):
        payload = b"x" * 5000
        with tempfile.TemporaryDirectory() as tmp:
            path = deps.download_file(
                "https://x/y/RyzenAdj-win64.zip", tmp,
                opener=opener_for(payload, {"Content-Length": "5000"}),
                chunk=1024)
            self.assertEqual(os.path.basename(path), "RyzenAdj-win64.zip")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), payload)

    def test_download_reports_progress(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            deps.download_file(
                "https://x/y/b.zip", tmp,
                opener=opener_for(b"y" * 3000, {"Content-Length": "3000"}),
                progress=lambda done, total: seen.append((done, total)),
                chunk=1000)
        self.assertEqual(seen[-1], (3000, 3000))

    def test_download_without_content_length(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp:
            deps.download_file("https://x/y/b.zip", tmp,
                               opener=opener_for(b"z" * 10),
                               progress=lambda done, total: seen.append(total))
        self.assertEqual(seen, [None])

    def test_download_creates_the_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "nested", "dir")
            deps.download_file("https://x/f.zip", dest, opener=opener_for(b"ok"))
            self.assertTrue(os.path.isfile(os.path.join(dest, "f.zip")))


class TestFindInTree(unittest.TestCase):

    TREE = [("/tools", ["lib"], ["README.md"]),
            ("/tools/lib", [], ["RyzenAdj.exe"])]

    def test_case_insensitive_match(self):
        got = deps.find_in_tree("/tools", "ryzenadj.exe",
                                walker=lambda _root: iter(self.TREE))
        self.assertEqual(got, os.path.join("/tools/lib", "RyzenAdj.exe"))

    def test_missing_returns_none(self):
        self.assertIsNone(deps.find_in_tree(
            "/tools", "nothere.exe", walker=lambda _root: iter(self.TREE)))


if __name__ == "__main__":
    unittest.main()
