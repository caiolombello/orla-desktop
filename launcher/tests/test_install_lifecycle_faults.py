"""Owned filesystem failure outcomes; never launch the archive ELF."""
import errno
import hashlib
import json
import os
import unittest
from unittest import mock

import test_install_guards as guard_fixtures


class InstallLifecycleFaultTests(unittest.TestCase):
    def fixture(self):
        guard = guard_fixtures.InstallGuardTests()
        self.addCleanup(guard.doCleanups)
        return guard, guard.fixture()

    def pending(self, fixture):
        paths, manager = fixture[1], fixture[5]
        self.assertEqual(manager.status(paths)["status"], "pending")
        state = paths.state_home / "orla/launcher-install"
        return json.loads((state / "pending.json").read_bytes())

    def test_late_directory_removal_failure_keeps_standalone_management(self):
        guard, fixture = self.fixture()
        guard.install(fixture)
        guard.hide_source(fixture)
        controller = guard.controller(fixture)
        controller_bytes = controller.read_bytes()
        tools = guard.tools(fixture)
        manager_bytes = (tools / "install.py").read_bytes()
        original = os.rmdir
        failures = []

        def rmdir(name, *args, **kwargs):
            if str(name) == "bin":
                failures.append(str(name))
                raise OSError(errno.EIO, "owned directory removal failure")
            return original(name, *args, **kwargs)

        with mock.patch("os.rmdir", side_effect=rmdir):
            with self.assertRaises(fixture[5].InstallError):
                fixture[5].uninstall(fixture[1])
        self.assertEqual(failures, ["bin"])
        self.assertTrue(controller.is_file(), "late failure removed standalone management")
        self.assertEqual(controller.read_bytes(), controller_bytes)
        self.assertEqual((tools / "install.py").read_bytes(), manager_bytes)
        completed = guard.invoke_controller(fixture)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "pending")
        self.assertEqual(report["runtime"], "unverified")
        self.assertEqual(report["code"], "filesystem_unknown")
        guard.assert_userdata(fixture)

    def test_exclusive_leaf_creation_before_chmod_failure_is_recorded(self):
        guard, fixture = self.fixture()
        original_open, original_chmod = os.open, os.fchmod
        created = []

        def open_fd(name, flags, *args, **kwargs):
            fd = original_open(name, flags, *args, **kwargs)
            if str(name) == "orla-launcher" and flags & os.O_CREAT:
                created.append(fd)
            return fd

        def chmod(fd, mode):
            if fd in created:
                raise OSError(errno.EIO, "owned leaf chmod failure")
            return original_chmod(fd, mode)

        previous = os.umask(0o077)
        try:
            with mock.patch("os.open", side_effect=open_fd), mock.patch("os.fchmod", side_effect=chmod):
                with self.assertRaises(fixture[5].InstallError):
                    guard.install(fixture)
        finally:
            os.umask(previous)
        self.assertEqual(len(created), 1)
        leaf = guard.version(fixture).with_name(".incoming-" + fixture[3]) / "bin/orla-launcher"
        self.assertTrue(leaf.is_file())
        actual = leaf.stat()
        pending = self.pending(fixture)
        owned = [item for item in pending["ownedFiles"] if item["key"] == "incoming/bin/orla-launcher"]
        self.assertEqual(len(owned), 1, "exclusively created partial file has no durable identity")
        self.assertEqual(owned[0]["size"], 0)
        self.assertEqual(owned[0]["sha256"], hashlib.sha256(b"").hexdigest())
        self.assertEqual(owned[0]["pin"][:3], [actual.st_dev, actual.st_ino, actual.st_mode])
        self.assertFalse(owned[0]["complete"])
        guard.assert_userdata(fixture)

    def test_exclusive_directory_creation_before_chmod_failure_is_recorded(self):
        guard, fixture = self.fixture()
        original_open, original_chmod = os.open, os.fchmod
        opened = []

        def open_fd(name, flags, *args, **kwargs):
            fd = original_open(name, flags, *args, **kwargs)
            if str(name) == ".incoming-" + fixture[3] and flags & os.O_DIRECTORY:
                opened.append(fd)
            return fd

        def chmod(fd, mode):
            if fd in opened:
                raise OSError(errno.EIO, "owned directory chmod failure")
            return original_chmod(fd, mode)

        with mock.patch("os.open", side_effect=open_fd), mock.patch("os.fchmod", side_effect=chmod):
            with self.assertRaises(fixture[5].InstallError):
                guard.install(fixture)
        self.assertEqual(len(opened), 1)
        directory = guard.version(fixture).with_name(".incoming-" + fixture[3])
        actual = directory.stat()
        pending = self.pending(fixture)
        owned = [item for item in pending["directories"] if item["key"] == "incoming"]
        self.assertEqual(len(owned), 1, "exclusively created directory has no durable identity")
        self.assertEqual(owned[0]["pin"][:3], [actual.st_dev, actual.st_ino, actual.st_mode])
        guard.assert_userdata(fixture)

    def test_deep_receipt_returns_finite_error_without_source(self):
        guard, fixture = self.fixture()
        guard.install(fixture)
        guard.hide_source(fixture)
        current = fixture[1].state_home / "orla/launcher-install/current.json"
        current.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
        completed = guard.invoke_controller(fixture)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["code"], "receipt_schema")
        guard.assert_userdata(fixture)

    def test_final_tools_removal_failure_keeps_bounded_pending_status(self):
        guard, fixture = self.fixture()
        guard.install(fixture)
        guard.hide_source(fixture)
        controller = guard.controller(fixture)
        controller_bytes = controller.read_bytes()
        original = os.rmdir
        failures = []

        def rmdir(name, *args, **kwargs):
            if str(name) == "tools":
                failures.append(str(name))
                raise OSError(errno.EIO, "owned final tools removal failure")
            return original(name, *args, **kwargs)

        with mock.patch("os.rmdir", side_effect=rmdir):
            with self.assertRaises(fixture[5].InstallError):
                fixture[5].uninstall(fixture[1])
        self.assertEqual(failures, ["tools"])
        self.assertTrue(controller.is_file(), "final teardown lost the status capability")
        self.assertEqual(controller.read_bytes(), controller_bytes)
        self.assertFalse((guard.tools(fixture) / "install.py").exists())
        self.assertFalse((guard.tools(fixture) / "package.py").exists())
        completed = guard.invoke_controller(fixture)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "pending")
        self.assertEqual(report["runtime"], "unverified")
        self.assertEqual(report["code"], "filesystem_unknown")
        self.assertEqual(report["archiveSha256"], fixture[3])
        guard.assert_userdata(fixture)

    def test_post_publication_sync_failure_records_published_payload_ownership(self):
        guard, fixture = self.fixture()
        version = guard.version(fixture)
        incoming = version.with_name(".incoming-" + fixture[3])
        original = os.fsync
        failures = []

        def fsync(fd):
            if not failures and version.is_dir() and not incoming.exists():
                failures.append(fd)
                raise OSError(errno.EIO, "owned post-publication sync failure")
            return original(fd)

        with mock.patch("os.fsync", side_effect=fsync):
            with self.assertRaises(fixture[5].InstallError):
                guard.install(fixture)
        self.assertEqual(len(failures), 1)
        self.assertFalse(incoming.exists())
        binary = version / "bin/orla-launcher"
        self.assertTrue(binary.is_file())
        actual = binary.stat()
        pending = self.pending(fixture)
        owned = [item for item in pending["ownedFiles"] if item["key"] == "payload/bin/orla-launcher"]
        self.assertEqual(len(owned), 1, "published payload lost its durable ownership label")
        self.assertEqual(owned[0]["sha256"], hashlib.sha256(binary.read_bytes()).hexdigest())
        self.assertEqual(owned[0]["pin"][:3], [actual.st_dev, actual.st_ino, actual.st_mode])
        self.assertTrue(owned[0]["complete"])
        directory_keys = {item["key"] for item in pending["directories"]}
        self.assertIn("version", directory_keys)
        self.assertNotIn("incoming", directory_keys)
        guard.assert_userdata(fixture)
