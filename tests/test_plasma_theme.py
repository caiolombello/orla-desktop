import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_theme  # noqa: E402

TILES = ("topleft", "top", "topright", "left", "center", "right", "bottomleft", "bottom", "bottomright")
SHADOWS = ("topleft", "top", "topright", "left", "right", "bottomleft", "bottom", "bottomright")


class PlasmaThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.theme = plasma_theme.build(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def renderer(self, relative):
        return QSvgRenderer(QByteArray(gzip.decompress((self.theme / relative).read_bytes())))

    def test_layout_and_metadata(self):
        files = sorted(str(path.relative_to(self.theme)) for path in self.theme.rglob("*") if path.is_file())
        self.assertEqual(files, sorted([
            "metadata.json", "plasmarc", "widgets/plasmoidheading.svgz",
            *(f"{base}{name}.svgz" for name in plasma_theme.FRAMES for base in ("", "translucent/")),
        ]))
        metadata = json.loads((self.theme / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["KPlugin"]["Id"], "orla")
        self.assertEqual(metadata["KPlugin"]["License"], "MIT")
        # No colors file: the theme follows the system color scheme, light or dark.
        self.assertFalse((self.theme / "colors").exists())
        plasmarc = (self.theme / "plasmarc").read_text(encoding="utf-8")
        for line in ("[ContrastEffect]", "saturation=1.8", "[BlurBehindEffect]", "enabled=true"):
            self.assertIn(line, plasmarc)

    def test_builds_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as other:
            again = plasma_theme.build(Path(other))
            for path in self.theme.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (again / path.relative_to(self.theme)).read_bytes(), path)

    def test_frames_have_exact_tiles_masks_and_margins(self):
        for name, spec in plasma_theme.FRAMES.items():
            for relative in (f"{name}.svgz", f"translucent/{name}.svgz"):
                with self.subTest(frame=relative):
                    svg = self.renderer(relative)
                    self.assertTrue(svg.isValid())
                    r = spec["radius"]
                    for prefix in ("", "mask-"):
                        for tile in TILES:
                            element = prefix + tile
                            self.assertTrue(svg.elementExists(element), element)
                            bounds = svg.boundsOnElement(element)
                            # Integral, exact bounds: Plasma stretches edges and pins corners.
                            for value in (bounds.x(), bounds.y(), bounds.width(), bounds.height()):
                                self.assertEqual(value, round(value), element)
                            if tile in ("topleft", "topright", "bottomleft", "bottomright"):
                                self.assertEqual((bounds.width(), bounds.height()), (r, r), element)
                    for side in ("top", "bottom", "left", "right"):
                        hint = svg.boundsOnElement(f"hint-{side}-margin")
                        size = hint.height() if side in ("top", "bottom") else hint.width()
                        self.assertEqual(size, spec["margin"], side)
                    for tile in SHADOWS:
                        self.assertEqual(svg.elementExists(f"shadow-{tile}"), spec["shadow"] > 0, tile)

    def test_panel_keeps_breeze_margins_and_no_shadow(self):
        # The bar layout tests assume 24 of its 32 px go to applets.
        self.assertEqual(plasma_theme.FRAMES["widgets/panel-background"]["margin"], 4)
        self.assertEqual(plasma_theme.FRAMES["widgets/panel-background"]["shadow"], 0)

    def test_corner_is_round_and_translucent_and_mask_is_opaque(self):
        svg = self.renderer("translucent/dialogs/background.svgz")
        r = plasma_theme.FRAMES["dialogs/background"]["radius"]

        def alpha(element, x, y):
            image = QImage(r * 4, r * 4, QImage.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            svg.render(painter, element, QRectF(0, 0, r * 4, r * 4))
            painter.end()
            return image.pixelColor(x, y).alpha()

        # Outside the rounded corner stays clear; the glass inside is translucent.
        self.assertEqual(alpha("topleft", 1, 1), 0)
        inside = alpha("topleft", r * 4 - 2, r * 4 - 2)
        self.assertGreater(inside, 120)
        self.assertLess(inside, 230)
        self.assertEqual(alpha("mask-topleft", r * 4 - 2, r * 4 - 2), 255)
        self.assertEqual(alpha("mask-topleft", 1, 1), 0)
        base = self.renderer("dialogs/background.svgz")
        image = QImage(8, 8, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        base.render(painter, "center", QRectF(0, 0, 8, 8))
        painter.end()
        self.assertGreater(image.pixelColor(4, 4).alpha(), inside)

    def test_shadow_stays_outside_the_glass(self):
        svg = self.renderer("translucent/dialogs/background.svgz")
        spec = plasma_theme.FRAMES["dialogs/background"]
        corner = spec["radius"] + spec["shadow"]
        bounds = svg.boundsOnElement("shadow-topleft")
        self.assertEqual((round(bounds.width(), 6), round(bounds.height(), 6)), (corner, corner))
        image = QImage(corner, corner, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        svg.render(painter, "shadow-topleft", QRectF(0, 0, corner, corner))
        painter.end()
        # Under the glass (the tile's inner corner) there is no shadow to darken it.
        self.assertEqual(image.pixelColor(corner - 2, corner - 2).alpha(), 0)
        # Just outside the glass edge the shadow is darkest; it fades outward.
        near = image.pixelColor(corner - 2, spec["shadow"] - 1).alpha()
        far = image.pixelColor(corner - 2, 1).alpha()
        self.assertGreater(near, far)
        self.assertEqual(svg.boundsOnElement("shadow-hint-top-margin").height(), spec["shadow"])

    def test_heading_is_transparent_with_a_hairline(self):
        svg = self.renderer("widgets/plasmoidheading.svgz")
        for prefix in ("header-", "footer-"):
            for tile in TILES:
                self.assertTrue(svg.elementExists(prefix + tile), prefix + tile)
        image = QImage(40, 40, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        svg.render(painter, "header-center", QRectF(0, 0, 40, 40))
        painter.end()
        self.assertEqual(image.pixelColor(20, 20).alpha(), 0)

    def test_cli_refuses_unknown_commands(self):
        self.assertEqual(plasma_theme.main(["plasma_theme.py"]), 2)
        self.assertEqual(plasma_theme.main(["plasma_theme.py", "build"]), 2)
        self.assertEqual(plasma_theme.main(["plasma_theme.py", "remove-everything"]), 2)


if __name__ == "__main__":
    unittest.main()
