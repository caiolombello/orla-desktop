"""Guard the design system: token copies, style lint and contrast (docs/DESIGN_SYSTEM.md)."""

import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("design", ROOT / "scripts/design.py")
design = importlib.util.module_from_spec(spec)
spec.loader.exec_module(design)


class DesignSystemTests(unittest.TestCase):
    def copy_tree(self, directory):
        root = Path(directory)
        for relative in (design.CANONICAL, *design.COPIES, Path("package/contents/code/Appearance.js")):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, root / relative)
        return root

    def test_repository_passes_the_design_check(self):
        self.assertEqual(design.check(), [])

    def test_lint_rejects_hardcoded_style_values(self):
        cases = {
            'color: "#69d7c2"': "hex-color",
            "color: 'white'": "named-color",
            "color: Qt.rgba(0.5, 0.6, 0.8, 0.2)": "rgba",
            "font.pixelSize: 14": "pixel-size",
            "radius: 9": "radius",
            "background: Rectangle { radius: 12; color: \"transparent\" }": "radius",
        }
        for line, rule in cases.items():
            with self.subTest(line=line):
                errors = design.lint_text("Sample.qml", line)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn(f"[{rule}]", errors[0])

    def test_lint_accepts_tokens_derived_values_and_explicit_exemptions(self):
        accepted = (
            "color: Style.schemes.dark.text",
            "color: Style.alpha(tile.foreground, Style.state.hover)",
            "font.pixelSize: Style.type.caption",
            "radius: Style.radius.card",
            "radius: width / 2",
            "radius: 0",
            "color: \"transparent\"",
            "source: \"https://example.test/#fragment\"",
            "// a comment may mention #69d7c2",
            'color: "#123456" // design-exempt: fixture colour',
        )
        for line in accepted:
            with self.subTest(line=line):
                self.assertEqual(design.lint_text("Sample.qml", line), [])

    def test_javascript_lint_only_rejects_colors_outside_the_token_files(self):
        self.assertEqual(design.lint_text("Logic.js", "var radius = 9; size: 12", True), [])
        self.assertEqual(len(design.lint_text("Logic.js", 'var tint = "#ffffff";', True)), 1)

    def test_drifted_copy_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_tree(directory)
            self.assertEqual(design.copy_errors(root), [])
            (root / design.COPIES[0]).write_text("// stale\n", encoding="utf-8")
            errors = design.copy_errors(root)
            self.assertEqual(len(errors), 1)
            self.assertIn(design.COPIES[0].as_posix(), errors[0])
            design.sync(root)
            self.assertEqual(design.copy_errors(root), [])

    def test_low_contrast_and_dock_theme_drift_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_tree(directory)
            self.assertEqual(design.contrast_errors(root), [])
            source = (root / design.CANONICAL).read_text(encoding="utf-8")
            source = source.replace('textMuted: "#a5b4bf"', 'textMuted: "#33404c"', 1)
            source = source.replace('muted: "#606c79"', 'muted: "#606c7a"', 1)
            source = source.replace('coral: {top: "#d9736c"', 'coral: {top: "#f2b8b0"', 1)
            (root / design.CANONICAL).write_text(source, encoding="utf-8")
            errors = "\n".join(design.contrast_errors(root))
            self.assertIn("Style.schemes.dark.textMuted on surface", errors)
            self.assertIn("Style.dockThemes.paper.muted", errors)
            self.assertIn("Style.iconTiles.coral.ink on top", errors)

    def test_scheme_selection_follows_background_lightness(self):
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtQml import QJSEngine
        QCoreApplication.instance() or QCoreApplication([])
        engine = QJSEngine()
        style = design._load(engine, ROOT, design.CANONICAL, ("schemeFor", "alpha"))
        scheme_for = style.property("schemeFor")
        self.assertEqual(scheme_for.call(["#eff0f1"]).toString(), "light")
        self.assertEqual(scheme_for.call(["#202326"]).toString(), "dark")
        # Hidden Kirigami samplers report black; that must read as dark, not crash.
        self.assertEqual(scheme_for.call(["#000000"]).toString(), "dark")
        alpha = style.property("alpha")
        self.assertEqual(alpha.call(["#69D7C2", 0.14]).toString(), "#2469d7c2")
        self.assertEqual(alpha.call(["#db283542", 1]).toString(), "#ff283542")


if __name__ == "__main__":
    unittest.main()
