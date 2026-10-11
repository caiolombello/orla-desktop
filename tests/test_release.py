"""Verify the distributed contributor kit, using a clean synthetic checkout."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


class ReleaseBundleTests(unittest.TestCase):
    def test_bundle_includes_theme_kit_and_excludes_private_runtime(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            for name in ("release.py", "caiodock.py", "themes.py"):
                shutil.copyfile(source / "scripts" / name, root / "scripts" / name)
            for name in ("LICENSE", "README.md", "README.pt-BR.md", "CONTRIBUTING.md",
                         "SECURITY.md", "CHANGELOG.md", "ROADMAP.md", ".gitignore"):
                (root / name).write_text("synthetic fixture\n", encoding="utf-8")
            (root / "package/contents/ui").mkdir(parents=True)
            (root / "package/metadata.json").write_text(json.dumps({
                "KPlugin": {"Id": "org.caiodock.dock", "Version": "1.2.3"}
            }), encoding="utf-8")
            (root / "package/contents/ui/main.qml").write_text("Item {}\n", encoding="utf-8")
            shutil.copytree(source / "themes", root / "themes")
            (root / "docs").mkdir()
            shutil.copyfile(source / "docs/theme-format.md", root / "docs/theme-format.md")
            (root / "tests").mkdir()
            shutil.copyfile(source / "tests/test_themes.py", root / "tests/test_themes.py")
            for name in ("test_bar.py", "BarHarness.qml"):
                (root / "tests" / name).write_text("source-only fixture\n", encoding="utf-8")
            (root / "bar").mkdir()
            (root / "bar/main.qml").write_text("source-only applet\n", encoding="utf-8")
            (root / ".runtime").mkdir()
            (root / ".runtime/private.json").write_text("private", encoding="utf-8")
            (root / "themes/private-link.json").symlink_to(root / ".runtime/private.json")
            (root / "themes/__pycache__").mkdir()
            (root / "themes/__pycache__/theme.pyc").write_bytes(b"private")

            def build():
                subprocess.run([sys.executable, str(root / "scripts/release.py")],
                               check=True, capture_output=True, timeout=30)
                return {path.name: path.read_bytes() for path in (root / "dist").iterdir()}

            first = build()
            second = build()
            self.assertEqual(first, second)
            archive_path = root / "dist/orla-dock-1.2.3.zip"
            prefix = "orla-dock-1.2.3/"
            with zipfile.ZipFile(archive_path) as archive:
                required = ("themes/examples/essential.json", "themes/examples/mare.json",
                            "themes/schema/theme-0.1-experimental.schema.json",
                            "scripts/themes.py", "docs/theme-format.md", "tests/test_themes.py")
                for name in required:
                    self.assertEqual(archive.read(prefix + name), (root / name).read_bytes())
                self.assertFalse(any(".runtime/" in name or "private-link" in name
                                     or "__pycache__" in name for name in archive.namelist()))
                for name in ("bar/main.qml", "tests/test_bar.py", "tests/BarHarness.qml"):
                    self.assertNotIn(prefix + name, archive.namelist())
                unpacked = root / "unpacked"
                archive.extractall(unpacked)
            kit = unpacked / "orla-dock-1.2.3"
            for name in ("essential.json", "mare.json"):
                result = subprocess.run([
                    sys.executable, str(kit / "scripts/themes.py"), "validate",
                    str(kit / "themes/examples" / name), "--json"
                ], check=True, capture_output=True, text=True, timeout=10)
                self.assertTrue(json.loads(result.stdout)["valid"])
            for line in first["SHA256SUMS"].decode("utf-8").splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(first[name]).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
