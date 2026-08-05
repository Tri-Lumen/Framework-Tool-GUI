"""Unit tests for device_images.py — board string to product photograph.

The mapping is by chassis, not by mainboard: swapping the mainboard does not
change what the machine looks like, so one image covers every generation of
a given chassis. The two exceptions are the ones that really do change the
outside — the Pro's black lid, and a Laptop 16 carrying a Graphics Module.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frameworkgui import device_images  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The images ship inside the package, next to the module that names them —
# which is exactly how `device_images.asset_root()` finds them at runtime.
PACKAGE = os.path.join(REPO, "frameworkgui")


class TestImageFor(unittest.TestCase):

    def test_every_laptop_13_mainboard_gets_the_same_photo(self):
        for board in ("Laptop 13 (AMD Ryzen AI 300 Series)",
                      "Laptop 13 (Intel Core Ultra Series 1)",
                      "Laptop 13 (12th Gen Intel Core)"):
            self.assertEqual(device_images.image_for(board), "laptop-13.png")

    def test_laptop_13_pro_is_matched_before_laptop_13(self):
        self.assertEqual(
            device_images.image_for("Laptop 13 Pro (AMD Ryzen AI 300 Series)"),
            "laptop-13-pro.png")

    def test_laptop_16(self):
        self.assertEqual(
            device_images.image_for("Laptop 16 (AMD Ryzen 7040 Series)"),
            "laptop-16.png")

    def test_laptop_16_with_a_graphics_module_is_a_different_shape(self):
        self.assertEqual(
            device_images.image_for("Laptop 16 (AMD Ryzen 7040 Series)",
                                    has_gpu_module=True),
            device_images.LAPTOP_16_GPU)

    def test_the_graphics_module_only_changes_the_laptop_16(self):
        for board in ("Laptop 13 (AMD Ryzen AI 300 Series)",
                      "Laptop 12 (13th Gen Intel Core)",
                      "Desktop (AMD Ryzen AI Max 300 Series)"):
            self.assertEqual(device_images.image_for(board, True),
                             device_images.image_for(board, False))

    def test_laptop_12(self):
        self.assertEqual(
            device_images.image_for("Laptop 12 (13th Gen Intel Core)"),
            "laptop-12.png")

    def test_desktop(self):
        self.assertEqual(
            device_images.image_for("Desktop (AMD Ryzen AI Max 300 Series)"),
            "desktop.png")

    def test_case_does_not_matter(self):
        self.assertEqual(device_images.image_for("LAPTOP 16"),
                         device_images.image_for("laptop 16"))

    def test_an_unknown_board_still_gets_an_image(self):
        # Falling back to nothing would read as a broken app, not an honest
        # one — an unrecognised board is still a Framework board.
        for board in ("", None, "Some Other Machine"):
            self.assertEqual(device_images.image_for(board),
                             device_images.FALLBACK)


class TestPathFor(unittest.TestCase):

    def test_returns_the_path_when_the_image_is_shipped(self):
        path = device_images.path_for("Laptop 16", exists=lambda _p: True)
        self.assertTrue(path.endswith("laptop-16.png"))
        self.assertIn(device_images.ASSET_DIR, path)

    def test_returns_none_when_a_build_shipped_without_the_images(self):
        # The text fallback in the UI depends on this being None, not a path
        # to a file that is not there.
        self.assertIsNone(device_images.path_for("Laptop 16",
                                                 exists=lambda _p: False))


class TestShippedAssets(unittest.TestCase):

    def test_every_catalog_image_exists_in_the_repo(self):
        for name in device_images.IMAGES:
            path = os.path.join(PACKAGE, device_images.ASSET_DIR, name)
            self.assertTrue(os.path.isfile(path),
                            "{} is referenced but not shipped".format(name))

    def test_no_orphan_images(self):
        directory = os.path.join(PACKAGE, device_images.ASSET_DIR)
        on_disk = sorted(f for f in os.listdir(directory)
                         if f.endswith(".png"))
        self.assertEqual(on_disk, sorted(device_images.IMAGES),
                         "an image on disk is not in the catalog, or the "
                         "other way round")

    def test_images_are_small_enough_to_ship(self):
        # These go into the exe and the Flatpak bundle; a full-resolution
        # press photo would add megabytes per chassis for a 420x206 slot.
        for name in device_images.IMAGES:
            path = os.path.join(PACKAGE, device_images.ASSET_DIR, name)
            self.assertLess(os.path.getsize(path), 400 * 1024,
                            "{} is too large — downscale it".format(name))


if __name__ == "__main__":
    unittest.main()
