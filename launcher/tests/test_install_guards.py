"""Owned Stage A installer guards; no real launcher/helper/host operations."""

import errno
import hashlib
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

import test_install as fixtures


LAUNCHER = Path(__file__).resolve().parents[1]


class InstallGuardTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        home = root / "owned home with spaces"
        data_home, state_home = home / ".local/share", home / ".local/state"
        data_home.mkdir(parents=True)
        state_home.mkdir(parents=True)
        userdata = {
            home / ".config/orla/aliases.json": b'{"owned":"fixture alias"}\n',
            home / ".config/kglobalshortcutsrc": b"[owned-fixture]\nunchanged=Meta\n",
            data_home / "orla-desktop/user-data/favorites.json": b'{"owned":"fixture favorite"}\n',
            state_home / "orla/layout/first.json": b'{"owned":"immutable fixture bank"}\n',
        }
        for path, data in userdata.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        preserved = {path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in userdata}
        archive_root = root / "owned archive fixture"
        archive_root.mkdir()
        archive, digest = fixtures.package_fixtures.PackageTests().build_archive(archive_root)
        bundle = root / "owned bootstrap bundle"
        bundle.mkdir()
        for name in ("install.py", "package.py"):
            shutil.copyfile(LAUNCHER / name, bundle / name)
        manager, module_name, old_module = fixtures.load_bootstrap(bundle)
        if old_module is None:
            self.addCleanup(sys.modules.pop, module_name, None)
        else:
            self.addCleanup(sys.modules.__setitem__, module_name, old_module)
        paths = manager.InstallPaths(home=home, data_home=data_home, state_home=state_home)
        return root, paths, archive, digest, bundle, manager, preserved

    def install(self, fixture):
        _root, paths, archive, digest, _bundle, manager, _preserved = fixture
        with mock.patch("subprocess.Popen", side_effect=AssertionError("file API cannot execute programs")):
            return manager.install_archive(archive, expected_sha256=digest, expected_commit="a" * 40, paths=paths)

    def assert_userdata(self, fixture):
        for path, expected in fixture[-1].items():
            self.assertEqual((path.read_bytes(), stat.S_IMODE(path.stat().st_mode)), expected)

    def snapshot(self, root):
        result = {}
        for path in root.rglob("*"):
            relative = str(path.relative_to(root))
            mode = stat.S_IMODE(path.lstat().st_mode)
            if path.is_symlink():
                result[relative] = ("symlink", mode, os.readlink(path))
            elif path.is_dir():
                result[relative] = ("directory", mode)
            else:
                result[relative] = ("file", mode, path.read_bytes())
        return result

    def controller(self, fixture):
        return fixture[1].home / ".local/bin/orla-launcherctl"

    def tools(self, fixture):
        return fixture[1].data_home / "orla-desktop/launcher/tools"

    def version(self, fixture):
        return fixture[1].data_home / "orla-desktop/launcher/versions" / fixture[3]

    def hide_source(self, fixture):
        root, _paths, _archive, _digest, bundle, _manager, _userdata = fixture
        bundle.rename(root / "owned bootstrap hidden")
        self.assertFalse(bundle.exists())

    def invoke_controller(self, fixture, *, cwd=None, extra_env=None):
        root, paths = fixture[:2]
        outside = cwd or root / "owned outside cwd"
        outside.mkdir(exist_ok=True)
        env = {"HOME": str(paths.home), "XDG_DATA_HOME": str(paths.data_home),
               "XDG_STATE_HOME": str(paths.state_home), "PATH": "/usr/bin:/bin"}
        env.update(extra_env or {})
        # Root alone runs this owned CLI status, never the ELF or helper.
        return subprocess.run([str(self.controller(fixture)), "status"], cwd=outside, env=env,
                              capture_output=True, text=True, timeout=10, check=False)

    def test_modified_installed_manager_never_executes_through_unchanged_controller(self):
        fixture = self.fixture()
        self.install(fixture)
        controller_before = self.controller(fixture).read_bytes()
        self.hide_source(fixture)
        marker = fixture[0] / "owned manager execution marker"
        malicious = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_bytes(b'owned marker')\n"
                     "print('{\"status\":\"installed\",\"runtime\":\"unverified\"}')\n").encode()
        (self.tools(fixture) / "install.py").write_bytes(malicious)
        completed = self.invoke_controller(fixture)
        self.assertFalse(marker.exists(), "modified manager executed before its pinned bytes were checked")
        self.assertEqual(self.controller(fixture).read_bytes(), controller_before)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "error")
        self.assertIsInstance(report["code"], str)
        self.assert_userdata(fixture)

    def test_source_absent_status_ignores_hostile_cwd_and_pythonpath(self):
        fixture = self.fixture()
        self.install(fixture)
        self.hide_source(fixture)
        outside = fixture[0] / "owned hostile cwd"
        pythonpath = fixture[0] / "owned hostile import path"
        outside.mkdir()
        pythonpath.mkdir()
        markers = []
        for folder in (outside, pythonpath):
            for name in ("install.py", "package.py"):
                marker = folder / (name + ".executed")
                markers.append(marker)
                (folder / name).write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_bytes(b'owned marker')\n")
        before = self.snapshot(fixture[1].home)
        completed = self.invoke_controller(fixture, cwd=outside, extra_env={"PYTHONPATH": str(pythonpath)})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "installed")
        self.assertEqual(report["runtime"], "unverified")
        self.assertEqual(report["archiveSha256"], fixture[3])
        self.assertTrue(all(not marker.exists() for marker in markers))
        self.assertEqual(self.snapshot(fixture[1].home), before)
        self.assert_userdata(fixture)

    def test_byte_identical_existing_install_without_current_receipt_is_not_adopted(self):
        fixture = self.fixture()
        self.install(fixture)
        _root, paths, archive, digest, _bundle, manager, _userdata = fixture
        # Owned fixture mutation models lost current authority; exact payload/tool
        # bytes remain present, including the otherwise valid legacy wrapper.
        (paths.state_home / "orla/launcher-install/current.json").unlink()
        before = self.snapshot(paths.home)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("conflict cannot execute programs")):
            report = manager.status(paths)
            with self.assertRaises(manager.InstallError) as raised:
                manager.install_archive(archive, expected_sha256=digest, expected_commit="a" * 40, paths=paths)
        self.assertEqual(report["status"], "unmanaged")
        self.assertEqual(raised.exception.code, "install_conflict")
        self.assertEqual(self.snapshot(paths.home), before)
        self.assert_userdata(fixture)

    def test_legacy_archive_and_invalid_sha_refuse_before_any_prefix_writes(self):
        for kind in ("legacy", "sha_shape", "sha_mismatch"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                _root, paths, archive, digest, _bundle, manager, _userdata = fixture
                if kind == "legacy":
                    archive, digest = fixtures.package_fixtures.PackageTests().legacy_archive(archive.parent)
                    manifest = fixtures.package_fixtures.package._verify_archive_data(archive.read_bytes(), expected_commit="a" * 40)
                    self.assertEqual(manifest["schema"], "orla-launcher-package-0.2")
                    expected_code = "archive_install_schema"
                elif kind == "sha_shape":
                    digest, expected_code = "not-a-sha", "archive_pins"
                else:
                    digest, expected_code = "0" * 64, "archive_hash"
                before = self.snapshot(paths.home)
                archive_before = archive.read_bytes()
                with mock.patch("subprocess.Popen", side_effect=AssertionError("invalid archive cannot execute programs")):
                    with self.assertRaises(manager.InstallError) as raised:
                        manager.install_archive(archive, expected_sha256=digest, expected_commit="a" * 40, paths=paths)
                self.assertEqual(raised.exception.code, expected_code)
                self.assertEqual(self.snapshot(paths.home), before)
                self.assertEqual(archive.read_bytes(), archive_before)
                self.assert_userdata(fixture)

    def test_managed_payload_drift_refuses_uninstall_before_any_delete(self):
        fixture = self.fixture()
        self.install(fixture)
        paths, manager = fixture[1], fixture[5]
        target = self.version(fixture) / "libexec/steam.py"
        target.write_bytes(target.read_bytes() + b"# owned drift\n")
        before = self.snapshot(paths.home)
        deletes = []
        original_unlink = os.unlink
        def unlink(path, *args, **kwargs):
            deletes.append(str(path))
            return original_unlink(path, *args, **kwargs)
        with mock.patch("os.unlink", side_effect=unlink), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("uninstall cannot execute programs")):
            with self.assertRaises(manager.InstallError) as raised:
                manager.uninstall(paths)
        self.assertEqual(raised.exception.code, "managed_drift")
        self.assertEqual(deletes, [])
        self.assertEqual(self.snapshot(paths.home), before)
        self.assert_userdata(fixture)

    def test_extra_payload_or_symlink_refuses_uninstall_before_any_delete(self):
        for kind in ("extra", "symlink"):
            with self.subTest(kind=kind):
                fixture = self.fixture()
                self.install(fixture)
                paths, manager = fixture[1], fixture[5]
                if kind == "extra":
                    (self.version(fixture) / "libexec/owned-extra.py").write_bytes(b"owned unexpected file\n")
                    expected_code = "managed_extra_file"
                else:
                    target = self.version(fixture) / "libexec/steam.py"
                    target.unlink()
                    target.symlink_to(paths.home / ".config/orla/aliases.json")
                    expected_code = "unsafe_file"
                before = self.snapshot(paths.home)
                deletes = []
                original_unlink = os.unlink
                def unlink(path, *args, **kwargs):
                    deletes.append(str(path))
                    return original_unlink(path, *args, **kwargs)
                with mock.patch("os.unlink", side_effect=unlink), \
                        mock.patch("subprocess.Popen", side_effect=AssertionError("uninstall cannot execute programs")):
                    with self.assertRaises(manager.InstallError) as raised:
                        manager.uninstall(paths)
                self.assertEqual(raised.exception.code, expected_code)
                self.assertEqual(deletes, [])
                self.assertEqual(self.snapshot(paths.home), before)
                self.assert_userdata(fixture)

    def test_partial_uninstall_io_failure_keeps_source_absent_controller_truthful_and_usable(self):
        fixture = self.fixture()
        self.install(fixture)
        self.hide_source(fixture)
        paths, manager = fixture[1], fixture[5]
        controller_before = self.controller(fixture).read_bytes()
        manager_before = (self.tools(fixture) / "install.py").read_bytes()
        failures = []
        original_unlink = os.unlink
        def unlink(path, *args, **kwargs):
            # A late tools-package removal failure must happen while the manager
            # and standalone controller still exist, after earlier payload work.
            if str(path) == "package.py":
                failures.append(str(path))
                raise OSError(errno.EIO, "owned simulated partial uninstall failure")
            return original_unlink(path, *args, **kwargs)
        with mock.patch("os.unlink", side_effect=unlink), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("file API cannot execute programs")):
            try:
                manager.uninstall(paths)
            except manager.InstallError as error:
                self.assertIsInstance(error.code, str)
            except OSError:
                pass
            else:
                self.fail("owned unlink failure was not reported")
        self.assertEqual(failures, ["package.py"])
        completed = self.invoke_controller(fixture)
        self.assertTrue(completed.stdout.strip(), completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        report = json.loads(completed.stdout)
        self.assertIn(report["status"], ("pending", "error"))
        if report["status"] == "error":
            self.assertIsInstance(report["code"], str)
        self.assertIn(completed.returncode, (0, 2))
        self.assertEqual(self.controller(fixture).read_bytes(), controller_before)
        self.assertEqual((self.tools(fixture) / "install.py").read_bytes(), manager_before)
        self.assert_userdata(fixture)

    def test_manual_launch_uses_exact_installed_binary_and_no_global_shortcut(self):
        fixture = self.fixture()
        self.install(fixture)
        self.hide_source(fixture)
        paths, manager = fixture[1], fixture[5]
        binary = self.version(fixture) / "bin/orla-launcher"
        before = self.snapshot(paths.home)
        with mock.patch("os.execv") as execute, \
                mock.patch("subprocess.Popen", side_effect=AssertionError("unexpected process API")):
            code = manager.main(["--home", str(paths.home), "--data-home", str(paths.data_home),
                                 "--state-home", str(paths.state_home), "launch"])
        self.assertEqual(code, 0)
        execute.assert_called_once_with(str(binary), [str(binary), "--no-global-shortcut"])
        self.assertEqual(self.snapshot(paths.home), before)
        self.assert_userdata(fixture)


if __name__ == "__main__":
    unittest.main()
