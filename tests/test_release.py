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
            for name in ("release.py", "caiodock.py", "themes.py", "__init__.py", "updates.py", "updates_contract.py", "orla.py", "panel_layout.py", "search_shortcut.py"):
                shutil.copyfile(source / "scripts" / name, root / "scripts" / name)
            # Source-only helpers are absent from the kit itself; placeholders prove their exclusion.
            for name in ("updates_desktop.py", "updates_desktop_state.py"):
                (root / "scripts" / name).write_text("source-only helper\n", encoding="utf-8")
            for name in ("LICENSE", "README.md", "README.pt-BR.md", "CONTRIBUTING.md",
                         "SECURITY.md", "CHANGELOG.md", "ROADMAP.md", ".gitignore"):
                (root / name).write_text("synthetic fixture\n", encoding="utf-8")
            (root / "package/contents/ui").mkdir(parents=True)
            (root / "package/metadata.json").write_text(json.dumps({
                "KPlugin": {"Id": "org.caiodock.dock", "Version": "1.2.3"}
            }), encoding="utf-8")
            (root / "package/contents/ui/main.qml").write_text("Item {}\n", encoding="utf-8")
            for name in ("contents/code/Theme.js", "contents/code/Appearance.js",
                         "contents/code/theme_format.py", "contents/code/theme_file.py",
                         "contents/ui/AppearanceState.qml", "contents/ui/AppearanceEditor.qml",
                         "contents/ui/EventState.qml", "contents/ui/EventSurface.qml",
                         "contents/controlcenter/qmldir", "contents/controlcenter/Registry.qml",
                         "contents/ui/ControlCenterEntry.qml", "contents/ui/ControlCenterPopup.qml",
                         "contents/ui/ControlCenterSession.qml",
                         "contents/config/main.xml"):
                target = root / "package" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / "package" / name, target)
            profile_files=("scripts/generate_addon_text_profile.py","scripts/data/addon-text-unicode16.json",
                           "package/contents/code/addon_format.py","package/contents/code/AddonText.js",
                           "docs/ADDON_TEXT_PROFILE.md","tests/test_addon_text_profile.py")
            for name in profile_files:
                target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source/name,target)
            shutil.copytree(source / "themes", root / "themes")
            shutil.copytree(source / "addons", root / "addons")
            (root / "docs").mkdir(exist_ok=True)
            shutil.copyfile(source / "docs/theme-format.md", root / "docs/theme-format.md")
            (root / "tests").mkdir(exist_ok=True)
            shutil.copyfile(source / "tests/test_themes.py", root / "tests/test_themes.py")
            for name in ("test_bar.py", "BarHarness.qml", "test_shared_control_center.py",
                         "test_workspace_setup.py", "test_workspace_view.py",
                         "test_workspace_entry.py", "test_workspace_package.py",
                         "test_workspace_install.py", "test_updates_desktop_entry.py", "test_updates_desktop_process.py", "test_updates_desktop_cache.py", "test_updates_desktop_view.py",
                         "SharedControlCenterBarHarness.qml", "test_design_system.py", "design_gallery.py",
                         "native/control_center_audio.py", "native/control_center_audio_session.py",
                         "native/run_control_center_audio.py", "native/control_center_audio.conf.in"):
                (root / "tests" / name).parent.mkdir(parents=True, exist_ok=True)
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
                            "addons/schema/manifest-0.1.schema.json", "addons/fixtures/peripherals-0.1.json",
                            "addons/fixtures/quota-0.1.json",
                            "scripts/themes.py", "scripts/updates.py", "scripts/updates_contract.py", "scripts/__init__.py", "docs/theme-format.md", "tests/test_themes.py",
                            "package/contents/code/Theme.js", "package/contents/code/Appearance.js",
                            "package/contents/code/theme_format.py", "package/contents/code/theme_file.py",
                            "package/contents/ui/AppearanceState.qml", "package/contents/ui/AppearanceEditor.qml",
                            "package/contents/ui/EventState.qml", "package/contents/ui/EventSurface.qml",
                            "package/contents/controlcenter/qmldir", "package/contents/controlcenter/Registry.qml",
                            "package/contents/ui/ControlCenterEntry.qml", "package/contents/ui/ControlCenterPopup.qml",
                            "package/contents/ui/ControlCenterSession.qml",
                            "package/contents/config/main.xml")
                for name in (*required,*profile_files):
                    self.assertEqual(archive.read(prefix + name), (root / name).read_bytes())
                with zipfile.ZipFile(root / "dist/orla-dock-1.2.3.plasmoid") as package_archive:
                    for name in ("contents/ui/EventState.qml", "contents/ui/EventSurface.qml",
                                 "contents/code/theme_format.py", "contents/code/theme_file.py",
                                 "contents/controlcenter/qmldir", "contents/controlcenter/Registry.qml",
                                 "contents/ui/ControlCenterEntry.qml", "contents/ui/ControlCenterPopup.qml",
                                 "contents/ui/ControlCenterSession.qml",
                                 "contents/config/main.xml", "contents/code/addon_format.py", "contents/code/AddonText.js"):
                        self.assertEqual(package_archive.read(name), (root / "package" / name).read_bytes())
                self.assertFalse(any(".runtime/" in name or "private-link" in name
                                     or "__pycache__" in name for name in archive.namelist()))
                profile=json.loads(archive.read(prefix+"scripts/data/addon-text-unicode16.json"))
                for name,comment in (("package/contents/code/addon_format.py","# "),("package/contents/code/AddonText.js","// ")):
                    text=archive.read(prefix+name).decode()
                    body=text.split(comment+"BEGIN UNICODE LICENSE\n",1)[1].split(comment+"END UNICODE LICENSE",1)[0]
                    self.assertEqual(''.join(line[len(comment):] for line in body.splitlines(True)),profile['license'])
                for name in ("bar/main.qml", "scripts/updates_desktop.py", "scripts/updates_desktop_state.py",
                             "tests/test_updates_desktop_entry.py", "tests/test_updates_desktop_process.py", "tests/test_updates_desktop_cache.py", "tests/test_updates_desktop_view.py", "tests/test_bar.py", "tests/BarHarness.qml",
                             "tests/test_workspace_setup.py", "tests/test_workspace_view.py",
                             "tests/test_workspace_entry.py", "tests/test_workspace_package.py",
                             "tests/test_workspace_install.py",
                             "tests/test_design_system.py", "tests/design_gallery.py",
                             "tests/test_shared_control_center.py", "tests/SharedControlCenterBarHarness.qml",
                             "tests/native/control_center_audio.py", "tests/native/control_center_audio_session.py",
                             "tests/native/run_control_center_audio.py", "tests/native/control_center_audio.conf.in"):
                    self.assertNotIn(prefix + name, archive.namelist())
                unpacked = root / "unpacked"
                archive.extractall(unpacked)
            kit = unpacked / "orla-dock-1.2.3"
            profile_checked=subprocess.run([sys.executable,"-I","-B",str(kit/"scripts/generate_addon_text_profile.py"),"--check"],
                                           cwd=unpacked,capture_output=True,text=True,timeout=15)
            self.assertEqual(profile_checked.returncode,0,profile_checked.stderr)
            for name in ("essential.json", "mare.json"):
                result = subprocess.run([
                    sys.executable, "-I", "-B", str(kit / "scripts/themes.py"), "validate",
                    str(kit / "themes/examples" / name), "--json"
                ], cwd=unpacked, check=True, capture_output=True, text=True, timeout=10)
                self.assertTrue(json.loads(result.stdout)["valid"])
                loaded = subprocess.run([
                    sys.executable, "-I", "-B", str(kit / "package/contents/code/theme_file.py"),
                    (kit / "themes/examples" / name).as_uri()
                ], cwd=unpacked, check=True, capture_output=True, text=True, timeout=10)
                self.assertEqual(json.loads(loaded.stdout)["theme"], json.loads(result.stdout)["theme"])
            checked = subprocess.run([sys.executable, "-I", "-B", str(kit / "scripts/updates.py"), "check", "--installed-version", "invalid"], cwd=unpacked, capture_output=True, text=True, timeout=10)
            self.assertEqual(checked.returncode, 2, checked.stderr)
            self.assertEqual(json.loads(checked.stdout)["reason"], "invalid_input")
            refused = subprocess.run([sys.executable, "-S", "-B", str(kit / "scripts/orla.py"), "updates", "desktop"], cwd=unpacked, capture_output=True, text=True, timeout=10)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("complete source checkout", refused.stderr)
            self.assertNotIn("Traceback", refused.stderr)
            for line in first["SHA256SUMS"].decode("utf-8").splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256(first[name]).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
