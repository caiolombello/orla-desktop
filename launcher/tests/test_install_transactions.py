"""Owned-only transaction causals; Root executes tests, never real installs."""

import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

import test_install as fixtures


class InstallTransactionTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        home = root / "owned home with spaces"
        data_home, state_home = home / ".local/share", home / ".local/state"
        data_home.mkdir(parents=True)
        state_home.mkdir(parents=True)
        userdata = home / ".config/orla/aliases.json"
        userdata.parent.mkdir(parents=True)
        userdata.write_bytes(b'{"owned": "untouched transaction fixture"}\n')
        archive_root = root / "archive fixture"
        archive_root.mkdir()
        archive, digest = fixtures.package_fixtures.PackageTests().build_archive(archive_root)
        bundle = root / "owned bootstrap bundle"
        bundle.mkdir()
        for name in ("install.py", "package.py"):
            shutil.copyfile(fixtures.LAUNCHER / name, bundle / name)
        manager, name, previous = fixtures.load_bootstrap(bundle)
        if previous is None: self.addCleanup(sys.modules.pop, name, None)
        else: self.addCleanup(sys.modules.__setitem__, name, previous)
        paths = manager.InstallPaths(home, data_home, state_home)
        return manager, paths, archive, digest, userdata

    def install(self, manager, paths, archive, digest):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("file transaction cannot start programs")):
            return manager.install_archive(archive, expected_sha256=digest, expected_commit="a" * 40, paths=paths)

    def test_entrypoint_publication_failure_retains_owned_pending_state_and_first_cause(self):
        manager, paths, archive, digest, userdata = self.fixture()
        original = userdata.read_bytes()
        controller = paths.home / ".local/bin/orla-launcherctl"
        launcher = paths.home / ".local/bin/orla-launcher"
        real_open = os.open
        fired = []
        def fail(path, flags, *args, **kwargs):
            if not fired and str(path) == launcher.name and flags & os.O_CREAT and controller.is_file():
                fired.append(True)
                raise manager.InstallError("write_failed")
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(manager.os, "open", side_effect=fail):
            try:
                outcome = self.install(manager, paths, archive, digest)
            except manager.InstallError as error:
                self.assertEqual(error.code, "write_failed")
            else:
                self.assertIn(outcome["status"], ("pending", "error"))
                self.assertEqual(outcome["code"], "write_failed")
        self.assertEqual(fired, [True])
        self.assertTrue(controller.is_file())
        self.assertFalse(launcher.exists())
        pending = manager.status(paths)
        self.assertEqual(pending["status"], "pending")
        self.assertEqual(pending["runtime"], "unverified")
        self.assertEqual(pending["code"], "write_failed")
        state = paths.state_home / "orla/launcher-install"
        durable = [json.loads(path.read_bytes()) for path in state.rglob("*.json")]
        rendered = json.dumps(durable, sort_keys=True)
        self.assertIn('"code": "write_failed"', rendered)
        self.assertIn(hashlib.sha256(controller.read_bytes()).hexdigest(), rendered)
        self.assertEqual(userdata.read_bytes(), original)

    def test_version_directory_appearing_after_absence_stat_is_not_clobbered(self):
        manager, paths, archive, digest, userdata = self.fixture()
        original = userdata.read_bytes()
        version = paths.data_home / "orla-desktop/launcher/versions" / digest
        real_stat = os.stat
        appeared = []
        foreign = []
        def race(path, *args, **kwargs):
            try:
                return real_stat(path, *args, **kwargs)
            except FileNotFoundError:
                if not appeared and str(path) == digest and kwargs.get("dir_fd") is not None:
                    appeared.append(True)
                    version.mkdir(mode=0o701)
                    status = real_stat(version, follow_symlinks=False)
                    foreign.append((status.st_dev, status.st_ino, stat.S_IMODE(status.st_mode)))
                raise
        outcome = None
        with mock.patch.object(manager.os, "stat", side_effect=race):
            try:
                outcome = self.install(manager, paths, archive, digest)
            except (manager.InstallError, OSError):
                pass
        self.assertEqual(appeared, [True])
        self.assertNotEqual((outcome or {}).get("status"), "installed")
        status = real_stat(version, follow_symlinks=False)
        self.assertEqual((status.st_dev, status.st_ino, stat.S_IMODE(status.st_mode)), foreign[0])
        self.assertEqual(list(version.iterdir()), [])
        self.assertEqual(userdata.read_bytes(), original)

    def test_primary_write_failure_survives_cleanup_uncertainty_after_real_close(self):
        manager, paths, archive, digest, userdata = self.fixture()
        original = userdata.read_bytes()
        real_write, real_close = os.write, os.close
        primary, cleanup = [], []
        def fail_write(descriptor, data):
            if not primary:
                primary.append(descriptor)
                raise manager.InstallError("write_failed")
            return real_write(descriptor, data)
        def fail_close(descriptor):
            real_close(descriptor)
            if primary and descriptor == primary[0] and not cleanup:
                cleanup.append(descriptor)
                # The real owned descriptor is closed before reporting ambiguity.
                raise OSError(errno.EIO, "owned simulated cleanup uncertainty")
        caught = None
        with mock.patch.object(manager.os, "write", side_effect=fail_write), \
             mock.patch.object(manager.os, "close", side_effect=fail_close):
            try:
                self.install(manager, paths, archive, digest)
            except (manager.InstallError, OSError) as error:
                caught = error
        self.assertTrue(primary and cleanup)
        self.assertIsInstance(caught, manager.InstallError)
        self.assertEqual(caught.code, "write_failed")
        self.assertEqual(userdata.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
