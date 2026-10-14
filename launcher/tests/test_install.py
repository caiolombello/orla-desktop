import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


LAUNCHER = Path(__file__).resolve().parents[1]
_original_path = list(sys.path)
try:
    sys.path[:0] = [str(LAUNCHER), str(LAUNCHER / "tests")]
    # Keep the imported TestCase inside its module alias: do not rediscover it.
    import test_package as package_fixtures
finally:
    sys.path[:] = _original_path


def load_bootstrap(bundle):
    module_name = "_owned_orla_install_bootstrap"
    specification = importlib.util.spec_from_file_location(module_name, bundle / "install.py")
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    old_module = sys.modules.get(module_name)
    old_path = list(sys.path)
    sys.modules[module_name] = module
    try:
        sys.path.insert(0, str(bundle))
        specification.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
    return module, module_name, old_module


class InstallTracerTests(unittest.TestCase):
    def test_owned_archive_install_standalone_status_without_source_and_uninstall_preserves_userdata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home with spaces"
            data_home = home / ".local/share"
            state_home = home / ".local/state"
            data_home.mkdir(parents=True)
            state_home.mkdir(parents=True)
            userdata = {
                home / ".config/orla/aliases.json": b'{"owned": "alias fixture"}\n',
                home / ".config/kglobalshortcutsrc": b"[owned-fixture]\nunchanged=Meta\n",
                data_home / "orla-desktop/user-data/favorites.json": b'{"owned": "favorite fixture"}\n',
                state_home / "orla/layout/first.json": b'{"owned": "immutable bank fixture"}\n',
            }
            for path, data in userdata.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            preserved = {path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in userdata}

            fixture_root = root / "archive fixture"
            fixture_root.mkdir()
            archive, digest = package_fixtures.PackageTests().build_archive(fixture_root)
            commit = "a" * 40
            frozen_bytes = archive.read_bytes()
            self.assertEqual(hashlib.sha256(frozen_bytes).hexdigest(), digest)
            manifest = package_fixtures.package._verify_archive_data(frozen_bytes, expected_commit=commit)
            self.assertEqual(manifest["schema"], "orla-launcher-package-0.3")
            expected_payload = {record["name"]: package_fixtures.package._decode_member(record)
                                for record in package_fixtures.package._archive_records(frozen_bytes)
                                if record["name"] != "manifest.json"}

            # Rename only an owned bootstrap copy; immutable preparation/Source
            # files remain available to Root and are never changed by this test.
            bundle = root / "owned bootstrap bundle"
            bundle.mkdir()
            for name in ("install.py", "package.py"):
                shutil.copyfile(LAUNCHER / name, bundle / name)
            source_bytes = {name: (bundle / name).read_bytes() for name in ("install.py", "package.py")}
            manager, module_name, old_module = load_bootstrap(bundle)
            if old_module is None:
                self.addCleanup(sys.modules.pop, module_name, None)
            else:
                self.addCleanup(sys.modules.__setitem__, module_name, old_module)
            paths = manager.InstallPaths(home=home, data_home=data_home, state_home=state_home)
            with mock.patch("subprocess.Popen", side_effect=AssertionError("install/status cannot execute programs")):
                # Baseline public seam raises InstallError("missing_installer").
                installed = manager.install_archive(archive, expected_sha256=digest, expected_commit=commit, paths=paths)
                current = manager.status(paths)

            version = data_home / "orla-desktop/launcher/versions" / digest
            tools = data_home / "orla-desktop/launcher/tools"
            launcher = home / ".local/bin/orla-launcher"
            controller = home / ".local/bin/orla-launcherctl"
            menu = data_home / "applications/org.orla.Launcher.desktop"
            for report in (installed, current):
                self.assertEqual(report["status"], "installed")
                self.assertEqual(report["runtime"], "unverified")
                self.assertEqual(report["archiveSha256"], digest)
                self.assertEqual(report["versionPath"], str(version))
            self.assertEqual({str(path.relative_to(version)) for path in version.rglob("*") if path.is_file()}, set(expected_payload))
            for relative, mode in package_fixtures.package.PAYLOAD:
                self.assertEqual((version / relative).read_bytes(), expected_payload[relative])
                self.assertEqual(stat.S_IMODE((version / relative).stat().st_mode), mode)
            self.assertEqual({path.name for path in tools.iterdir()}, {"install.py", "package.py"})
            for name, data in source_bytes.items():
                self.assertEqual((tools / name).read_bytes(), data)
            for path in (launcher, controller):
                self.assertTrue(path.is_file())
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
            self.assertIn("[Desktop Entry]", menu.read_text())
            self.assertIn("Exec=", menu.read_text())
            self.assertIn("orla-launcher", menu.read_text())

            bundle.rename(root / "bootstrap bundle hidden")
            self.assertFalse(bundle.exists())
            outside = root / "outside working directory"
            outside.mkdir()
            # Root alone executes this owned CLI test; no launcher/helper starts.
            completed = subprocess.run([str(controller), "status"], cwd=outside,
                                       env={"HOME": str(home), "XDG_DATA_HOME": str(data_home),
                                            "XDG_STATE_HOME": str(state_home), "PATH": "/usr/bin:/bin"},
                                       capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            standalone = json.loads(completed.stdout)
            self.assertEqual(standalone["status"], "installed")
            self.assertEqual(standalone["runtime"], "unverified")
            self.assertEqual(standalone["archiveSha256"], digest)
            self.assertEqual(standalone["versionPath"], str(version))

            with mock.patch("subprocess.Popen", side_effect=AssertionError("uninstall cannot execute programs")):
                removed = manager.uninstall(paths)
            self.assertEqual(removed["status"], "uninstalled")
            for path in (launcher, controller, menu): self.assertFalse(path.exists())
            for relative in expected_payload: self.assertFalse((version / relative).exists())
            for name in source_bytes: self.assertFalse((tools / name).exists())
            for path, expected in preserved.items():
                self.assertEqual((path.read_bytes(), stat.S_IMODE(path.stat().st_mode)), expected)
            self.assertEqual(archive.read_bytes(), frozen_bytes)

    def test_unicode_desktop_special_paths_preserve_configured_roots_without_bootstrap(self):
        # Independent general Desktop-string decoding precedes Exec quoting;
        # literal %% expands only after tokenization. No installer helpers.
        def desktop_exec_argv(raw):
            slash = chr(92)
            general = {"s": " ", "n": "\n", "t": "\t", "r": "\r", slash: slash}
            text = []
            index = 0
            while index < len(raw):
                if raw[index] != slash:
                    text.append(raw[index]); index += 1; continue
                index += 1
                self.assertLess(index, len(raw), "truncated Desktop string escape")
                self.assertIn(raw[index], general, "invalid Desktop string escape")
                text.append(general[raw[index]]); index += 1
            value = "".join(text)
            words = []
            index = 0
            quote = chr(34)
            reserved = set(quote + chr(39) + slash + "><~|&;$*?#()`")
            while index < len(value):
                while index < len(value) and value[index] in " \t": index += 1
                if index == len(value): break
                word = []
                if value[index] == quote:
                    index += 1
                    while index < len(value) and value[index] != quote:
                        char = value[index]
                        if char == slash:
                            index += 1
                            self.assertLess(index, len(value), "truncated quoted Exec escape")
                            char = value[index]
                            self.assertIn(char, quote + "`$" + slash, "invalid quoted Exec escape")
                        elif char in "`$":
                            self.fail("unescaped reserved character in quoted Exec word")
                        word.append(char); index += 1
                    self.assertLess(index, len(value), "unterminated quoted Exec word")
                    index += 1
                    self.assertTrue(index == len(value) or value[index] in " \t", "quoted argument must end at whitespace")
                else:
                    while index < len(value) and value[index] not in " \t":
                        self.assertNotIn(value[index], reserved, "reserved Exec character must be quoted")
                        word.append(value[index]); index += 1
                raw_word = "".join(word)
                expanded = []
                field = 0
                while field < len(raw_word):
                    if raw_word[field] != "%":
                        expanded.append(raw_word[field]); field += 1; continue
                    self.assertLess(field + 1, len(raw_word), "truncated Exec field code")
                    self.assertEqual(raw_word[field + 1], "%", "unexpected Exec field code")
                    expanded.append("%"); field += 2
                words.append("".join(expanded))
            return words

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # All requested characters in one literal component; never shell data.
            special = 'áç space " percent% dollar$ backtick` backslash' + chr(92)
            home = root / special
            data_home = home / "configured data"
            state_home = home / "configured state"
            data_home.mkdir(parents=True)
            state_home.mkdir(parents=True)
            userdata = home / ".config/orla/userdata.json"
            userdata.parent.mkdir(parents=True)
            userdata.write_bytes(b'{"saved":"own fixture"}\n')
            userdata_before = (userdata.read_bytes(), stat.S_IMODE(userdata.stat().st_mode))
            fixture = root / "archive fixture"
            fixture.mkdir()
            archive, digest = package_fixtures.PackageTests().build_archive(fixture)
            frozen_archive = archive.read_bytes()
            bundle = root / "owned bootstrap"
            bundle.mkdir()
            for name in ("install.py", "package.py"):
                shutil.copyfile(LAUNCHER / name, bundle / name)
            manager, module_name, old_module = load_bootstrap(bundle)
            if old_module is None:
                self.addCleanup(sys.modules.pop, module_name, None)
            else:
                self.addCleanup(sys.modules.__setitem__, module_name, old_module)
            paths = manager.InstallPaths(home=home, data_home=data_home, state_home=state_home)
            with mock.patch("subprocess.Popen", side_effect=AssertionError("install/status must not execute payload")):
                installed = manager.install_archive(archive, expected_sha256=digest,
                                                    expected_commit="a" * 40, paths=paths)
                direct_status = manager.status(paths)
            version = data_home / "orla-desktop/launcher/versions" / digest
            tools = data_home / "orla-desktop/launcher/tools"
            controller = home / ".local/bin/orla-launcherctl"
            launcher = home / ".local/bin/orla-launcher"
            menu = data_home / "applications/org.orla.Launcher.desktop"
            for report in (installed, direct_status):
                self.assertEqual(report["status"], "installed")
                self.assertEqual(report["runtime"], "unverified")
                self.assertEqual(report["archiveSha256"], digest)
                self.assertEqual(report["versionPath"], str(version))
            for path in (controller, launcher, menu, tools / "install.py", tools / "package.py",
                         state_home / "orla/launcher-install/current.json"):
                self.assertTrue(path.is_file(), str(path))
            for relative, mode in package_fixtures.package.PAYLOAD:
                self.assertTrue((version / relative).is_file())
                self.assertEqual(stat.S_IMODE((version / relative).stat().st_mode), mode)

            bundle.rename(root / "bootstrap hidden")
            self.assertFalse(bundle.exists())
            outside = root / "unrelated cwd"
            outside.mkdir()
            decoy_home = root / "wrong environment home"
            decoy_data = root / "wrong environment data"
            decoy_state = root / "wrong environment state"
            for path in (decoy_home, decoy_data, decoy_state):
                path.mkdir()
                (path / "untouched").write_bytes(b"synthetic decoy\n")
            environment = {"HOME": str(decoy_home), "XDG_DATA_HOME": str(decoy_data),
                           "XDG_STATE_HOME": str(decoy_state), "PATH": "/usr/bin:/bin"}
            # Both subprocesses request owned Python status. No payload executes.
            standalone = subprocess.run([str(controller), "status"], cwd=outside,
                                        env=environment, capture_output=True, text=True,
                                        timeout=10, check=False)
            self.assertEqual(standalone.returncode, 0, standalone.stderr)
            standalone_status = json.loads(standalone.stdout)
            self.assertEqual(standalone_status, direct_status)

            exec_values = [line[5:] for line in menu.read_text(encoding="utf-8").splitlines()
                           if line.startswith("Exec=")]
            self.assertEqual(len(exec_values), 1)
            desktop_argv = desktop_exec_argv(exec_values[0])
            self.assertEqual(len(desktop_argv), 6)
            self.assertEqual(desktop_argv[:4], [sys.executable, "-I", "-B", "-c"])
            self.assertTrue(desktop_argv[4].isascii(), "pinned loader must embed Unicode through ASCII JSON escapes")
            self.assertEqual(desktop_argv[-1], "launch")
            status_argv = [*desktop_argv[:-1], "status"]
            from_desktop = subprocess.run(status_argv, cwd=outside, env=environment,
                                          capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(from_desktop.returncode, 0, from_desktop.stderr)
            self.assertEqual(json.loads(from_desktop.stdout), standalone_status)
            for path in (decoy_home, decoy_data, decoy_state):
                self.assertEqual([entry.name for entry in path.iterdir()], ["untouched"])
                self.assertEqual((path / "untouched").read_bytes(), b"synthetic decoy\n")
            self.assertEqual((userdata.read_bytes(), stat.S_IMODE(userdata.stat().st_mode)), userdata_before)
            self.assertEqual(archive.read_bytes(), frozen_archive)
            with mock.patch("subprocess.Popen", side_effect=AssertionError("uninstall must not execute payload")):
                self.assertEqual(manager.uninstall(paths)["status"], "uninstalled")
            self.assertFalse(controller.exists())
            self.assertFalse(launcher.exists())
            self.assertFalse(menu.exists())
            self.assertEqual((userdata.read_bytes(), stat.S_IMODE(userdata.stat().st_mode)), userdata_before)


if __name__ == "__main__":
    unittest.main()
