import configparser
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QPointF, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
TESTS = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "window_decoration.py"
sys.path.insert(0, str(ROOT / "scripts"))
import window_decoration  # noqa: E402


class DecorationQmlTests(unittest.TestCase):
    """The decoration QML against a test double of KWin's decoration module."""

    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.engine.addImportPath(str(TESTS / "kwin-decoration-mock"))
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(TESTS / "WindowDecorationHarness.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.client = self.window.findChild(QObject, "clientFixture")
        self.deco = self.window.property("decorationItem")
        self.assertIsNotNone(self.deco, self.warnings)
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()

    @staticmethod
    def visual(root, name):
        # Loader-made buttons live in the visual tree, not under findChild.
        for child in root.childItems():
            if child.objectName() == name:
                return child
            found = DecorationQmlTests.visual(child, name)
            if found is not None:
                return found
        return None

    def item(self, name):
        found = self.visual(self.deco, name)
        self.assertIsNotNone(found, name)
        return found

    def lights(self):
        return [self.item(name) for name in ("orlaClose", "orlaMinimize", "orlaMaximize")]

    def test_geometry_matches_macos_title_bar(self):
        borders = self.deco.property("borders")
        self.assertEqual([borders.property(k) for k in ("left", "right", "bottom", "title")], [1, 1, 1, 28])
        padding = self.deco.property("padding")
        self.assertEqual([padding.property(k) for k in ("left", "top", "right", "bottom")], [24, 18, 24, 32])
        self.assertEqual(self.deco.property("extendedBorders").property("left"), 4)
        title = self.item("orlaTitleRow")
        self.assertEqual(self.window.findChild(QObject, "decorationFixture").property("titleItem"), title)
        # Close, minimize and zoom from the left: 12 px discs every 20 px, centered in the bar.
        centers = []
        for light in self.lights():
            disc = self.visual(light, "disc")
            self.assertEqual((disc.width(), disc.height()), (12, 12))
            center = disc.mapToItem(title, QPointF(6, 6))
            centers.append((center.x(), center.y()))
        self.assertEqual([round(x) for x, _ in centers], [14, 34, 54])
        self.assertTrue(all(y == 14 for _, y in centers))
        caption = self.item("orlaCaption")
        left = caption.x()
        right = title.width() - caption.x() - caption.width()
        self.assertEqual(left, right)
        self.assertEqual(caption.property("text"), "Janela sintética")
        self.assertEqual(self.warnings, [])

    def test_glyphs_show_while_any_light_is_hovered(self):
        glyphs = [self.visual(light, "glyph") for light in self.lights()]
        self.assertFalse(any(glyph.isVisible() for glyph in glyphs))
        self.lights()[2].setProperty("hovered", True)
        self.assertTrue(all(glyph.isVisible() for glyph in glyphs))
        self.lights()[2].setProperty("hovered", False)
        self.assertFalse(any(glyph.isVisible() for glyph in glyphs))
        self.assertEqual(self.deco.property("hoveredLights"), 0)

    def test_inactive_windows_turn_gray_until_hovered(self):
        close = self.visual(self.lights()[0], "disc")
        self.assertEqual(close.property("color").name(), "#ff5f57")
        self.client.setProperty("active", False)
        QTest.qWait(20)
        gray = close.property("color")
        self.assertLess(gray.alphaF(), 0.3)
        self.lights()[1].setProperty("hovered", True)
        self.assertEqual(close.property("color").name(), "#ff5f57")
        self.lights()[1].setProperty("hovered", False)
        self.assertEqual(self.warnings, [])

    def test_maximized_windows_drop_shadow_and_corners(self):
        shadow = self.item("orlaShadow")
        self.assertEqual(shadow.property("count"), 10)
        self.client.setProperty("maximized", True)
        QTest.qWait(20)
        self.assertEqual(shadow.property("count"), 0)
        self.assertEqual(self.item("orlaTitleRow").x(), 0)
        self.assertEqual(self.warnings, [])


FAKE_KWRITECONFIG = textwrap.dedent("""\
    #!/usr/bin/env python3
    import configparser, os, sys
    args = sys.argv[1:]
    path = os.path.join(os.environ["XDG_CONFIG_HOME"], args[args.index("--file") + 1])
    group, key = args[args.index("--group") + 1], args[args.index("--key") + 1]
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(path)
    if "--delete" in args:
        if config.has_section(group):
            config.remove_option(group, key)
    else:
        if not config.has_section(group):
            config.add_section(group)
        config.set(group, key, args[-1])
    with open(path, "w") as handle:
        config.write(handle, space_around_delimiters=False)
    """)


class DecorationScriptTests(unittest.TestCase):
    """The install/apply/restore commands with fake KDE tools and a private home."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.bin = base / "bin"
        self.bin.mkdir()
        for name, body in (("kwriteconfig6", FAKE_KWRITECONFIG),
                           ("busctl", "#!/bin/sh\necho \"$@\" >> \"$XDG_STATE_HOME/busctl.log\"\n")):
            path = self.bin / name
            path.write_text(body, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                        XDG_CONFIG_HOME=str(base / "config"), XDG_DATA_HOME=str(base / "data"),
                        XDG_STATE_HOME=str(base / "state"))
        for key in ("config", "data", "state"):
            (base / key).mkdir()
        self.base = base

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args, expect=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env, capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, expect, result.stderr)
        return result.stdout

    def kwinrc(self):
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str
        config.read(self.base / "config" / "kwinrc")
        return dict(config["org.kde.kdecoration2"]) if config.has_section("org.kde.kdecoration2") else {}

    def test_install_apply_restore_round_trip(self):
        (self.base / "config" / "kwinrc").write_text("[org.kde.kdecoration2]\nButtonsOnLeft=M\n", encoding="utf-8")
        self.run_script("apply", expect=1)  # refuses before installing
        target = Path(self.run_script("install").strip())
        ident = window_decoration.plugin_id()
        self.assertEqual(target.name, ident)
        metadata = json.loads((target / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["KPlugin"]["Id"], ident)
        self.assertTrue((target / "contents/ui/main.qml").exists())
        self.run_script("apply")
        self.assertEqual(self.kwinrc(), {"ButtonsOnLeft": "XIA", "library": "org.kde.kwin.aurorae",
                                         "theme": ident, "ButtonsOnRight": ""})
        # Applying again keeps the first saved state.
        self.run_script("apply")
        saved = json.loads((self.base / "state/orla/window-decoration.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["previous"], {"library": None, "theme": None, "ButtonsOnLeft": "M", "ButtonsOnRight": None})
        self.run_script("restore")
        self.assertEqual(self.kwinrc(), {"ButtonsOnLeft": "M"})
        self.assertFalse((self.base / "state/orla/window-decoration.json").exists())
        self.run_script("restore", expect=1)
        self.assertIn("reconfigure", (self.base / "state/busctl.log").read_text(encoding="utf-8"))

    def test_each_content_version_installs_under_its_own_id(self):
        package = self.base / "package"
        shutil.copytree(window_decoration.PACKAGE, package)
        first = window_decoration.plugin_id(package)
        self.assertEqual(first, window_decoration.plugin_id(package))
        self.assertTrue(first.startswith("kwin4_decoration_qml_orla_"))
        main = package / "contents/ui/main.qml"
        main.write_text(main.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assertNotEqual(first, window_decoration.plugin_id(package))
        # A newer install replaces older Orla versions only.
        decorations = self.base / "data/kwin/decorations"
        (decorations / "kwin4_decoration_qml_orla_0000000000").mkdir(parents=True)
        (decorations / "kwin4_decoration_qml_plastik").mkdir()
        target = Path(self.run_script("install").strip())
        self.assertEqual(sorted(path.name for path in decorations.iterdir()),
                         sorted([target.name, "kwin4_decoration_qml_plastik"]))

    def test_unknown_commands_are_refused(self):
        self.run_script(expect=2)
        self.run_script("remove", expect=2)


if __name__ == "__main__":
    unittest.main()
