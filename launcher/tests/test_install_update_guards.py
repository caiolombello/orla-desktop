"""Owned payload-update causals. Root alone executes these inert file tests."""
import ctypes
import errno
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

import test_install as archive_fixtures
import test_install_guards as install_fixtures


class ManagedUpdateGuardTests(unittest.TestCase):
    def fixture(self, *, finished_bank=False):
        fixture = install_fixtures.InstallGuardTests.fixture(self)
        manager, paths = fixture[5], fixture[1]
        if finished_bank:
            original = manager._unlink_checked
            fired = []
            def late(path, record, mode, *args, **kwargs):
                if Path(path).name == "pending-intent.json" and not fired:
                    fired.append(True)
                    raise manager.InstallError("write_failed")
                return original(path, record, mode, *args, **kwargs)
            with mock.patch.object(manager, "_unlink_checked", side_effect=late):
                with self.assertRaises(manager.InstallError):
                    install_fixtures.InstallGuardTests.install(self, fixture)
            self.assertEqual(fired, [True])
            manager.recover_finish_install(paths)
        else:
            install_fixtures.InstallGuardTests.install(self, fixture)
        root = fixture[0] / "owned B archive"
        root.mkdir()
        suite = archive_fixtures.package_fixtures.PackageTests()
        stage = suite.make_stage(root)
        (stage / "libexec/steam.py").write_bytes(b"# distinct inert B fixture\n")
        archive = root / "B.zip"
        package = archive_fixtures.package_fixtures.package
        digest = package.build(stage, archive, version="0.1.1", commit="b" * 40,
                               ci_image_digest="sha256:" + "c" * 64,
                               runtime_inventory=archive_fixtures.package_fixtures.runtime_inventory())
        self.assertNotEqual(digest, fixture[3])
        return fixture, archive, digest

    def state(self, fixture):
        return fixture[1].state_home / "orla/launcher-install"

    def base(self, fixture):
        return fixture[1].data_home / "orla-desktop/launcher"

    def state_slot(self, fixture):
        return self.state(fixture) / "payload-update"

    def data_slot(self, fixture):
        return fixture[1].data_home / "orla-desktop/launcher-update"

    def bank(self, fixture):
        return self.state_slot(fixture) / "bank.json"

    def pair(self, fixture):
        active = (self.state(fixture) / "pending-intent.json").exists()
        parked = (self.state_slot(fixture) / "barrier.json").exists()
        barrier = "active" if active and not parked else "slot" if parked and not active else "invalid"
        versions = self.base(fixture) / "versions"
        names = sorted(path.name for path in versions.iterdir()) if versions.is_dir() else []
        current = self.state(fixture) / "current.json"
        selected = json.loads(current.read_bytes())["archiveSha256"] if current.is_file() else None
        return barrier, names[0] if len(names) == 1 else None, selected

    def protected(self, fixture):
        manager, paths = fixture[5], fixture[1]
        selected = {key: value for key, value in manager._files(paths, fixture[3]).items()
                    if not key.startswith("payload/")}
        state = self.state(fixture)
        proof_paths = [path for path, _mode in selected.values()] + [
            state / "receipts" / (fixture[3] + ".json"),
            state / "transactions" / (fixture[3] + "-install.json"),
            state / "transactions" / (fixture[3] + "-installed.json")]
        old_bank = state / "transactions" / (fixture[3] + "-finish-install-recovery.json")
        if old_bank.exists():
            proof_paths.append(old_bank)
        return {str(path): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode), manager._identity(path.stat()))
                for path in proof_paths if path.exists()}

    def snapshot(self, fixture):
        # Evidence-only first-error publication is permitted on a refusal.
        result = install_fixtures.InstallGuardTests.snapshot(self, fixture[1].home)
        return {key: value for key, value in result.items() if not key.endswith("payload-update/first-error.json")}

    def update(self, fixture, archive, digest, *, commit="b" * 40):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no ELF/helper/process execution")):
            return fixture[5].update_archive(archive, expected_sha256=digest, expected_commit=commit, paths=fixture[1])

    def recover(self, fixture):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no ELF/helper/process execution")):
            return fixture[5].recover_update(fixture[1])

    def assert_a(self, fixture):
        report = fixture[5].status(fixture[1])
        self.assertEqual(report["status"], "installed")
        self.assertEqual(report["archiveSha256"], fixture[3])
        self.assertEqual(report["runtime"], "unverified")
        self.assertEqual(self.pair(fixture), ("slot", fixture[3], fixture[3]))
        install_fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def interrupt_after_sync(self, fixture, expected, action):
        manager = fixture[5]
        real_sync = os.fsync
        fired = []
        def sync(descriptor):
            result = real_sync(descriptor)
            if not fired and self.bank(fixture).is_file() and self.pair(fixture) == expected:
                fired.append(expected)
                if expected[0] == "active":
                    # The original legacy-compatible pending/status API must
                    # parse the barrier even when the payload/current pair mixes.
                    pending = manager.status(fixture[1])
                    self.assertEqual(pending["status"], "pending")
                    self.assertEqual(pending["code"], "transaction_in_progress")
                raise manager.InstallError("write_failed")
            return result
        with mock.patch.object(manager.os, "fsync", side_effect=sync):
            with self.assertRaises(manager.InstallError):
                action()
        self.assertEqual(fired, [expected])
        self.assertEqual(self.pair(fixture), expected)

    def test_update_interruption_after_each_observed_transition_recovers_to_a(self):
        for label in ("active-AA", "active-BA", "active-BB", "parked-BB"):
            with self.subTest(label=label):
                fixture, archive, digest = self.fixture()
                protected = self.protected(fixture)
                expected = {"active-AA": ("active", fixture[3], fixture[3]),
                            "active-BA": ("active", digest, fixture[3]),
                            "active-BB": ("active", digest, digest), "parked-BB": ("slot", digest, digest)}[label]
                self.interrupt_after_sync(fixture, expected, lambda: self.update(fixture, archive, digest))
                first = self.state_slot(fixture) / "first-error.json"
                first_bytes = first.read_bytes()
                self.assertEqual(json.loads(first_bytes)["code"], "write_failed")
                bank_bytes = self.bank(fixture).read_bytes()
                result = self.recover(fixture)
                self.assertEqual(result["archiveSha256"], fixture[3])
                self.assert_a(fixture)
                self.assertEqual(self.protected(fixture), protected)
                self.assertEqual(self.bank(fixture).read_bytes(), bank_bytes)
                self.assertEqual(first.read_bytes(), first_bytes)
                self.assertEqual(self.recover(fixture)["archiveSha256"], fixture[3])
                self.assertEqual(first.read_bytes(), first_bytes)

    def test_rollback_interrupted_in_active_ab_recovers_to_a(self):
        fixture, archive, digest = self.fixture()
        protected = self.protected(fixture)
        self.update(fixture, archive, digest)
        self.interrupt_after_sync(fixture, ("active", fixture[3], digest),
                                  lambda: fixture[5].rollback_update(fixture[1]))
        self.recover(fixture)
        self.assert_a(fixture)
        self.assertEqual(self.protected(fixture), protected)

    def test_invalid_external_pins_and_legacy_schema_refuse_before_workspaces(self):
        for kind in ("sha", "commit", "schema"):
            with self.subTest(kind=kind):
                fixture, archive, digest = self.fixture()
                commit = "b" * 40
                if kind == "sha": digest = "0" * 64
                if kind == "commit": commit = "c" * 40
                if kind == "schema":
                    archive, digest = archive_fixtures.package_fixtures.PackageTests().legacy_archive(archive.parent)
                    commit = "a" * 40
                before = self.snapshot(fixture)
                with self.assertRaises(fixture[5].InstallError):
                    self.update(fixture, archive, digest, commit=commit)
                self.assertEqual(self.snapshot(fixture), before)
                self.assertFalse(self.state_slot(fixture).exists())
                self.assertFalse(self.data_slot(fixture).exists())

    def test_partial_bank_publication_keeps_a_usable_and_refuses_repair(self):
        fixture, archive, digest = self.fixture()
        manager = fixture[5]
        protected = self.protected(fixture)
        original = manager._write_new
        fired = []
        def partial(path, data, mode, *args, **kwargs):
            if Path(path) == self.bank(fixture) and not fired:
                original(path, b'{"schema":', mode, *args, **kwargs)
                fired.append(True)
                raise manager.InstallError("write_failed")
            return original(path, data, mode, *args, **kwargs)
        with mock.patch.object(manager, "_write_new", side_effect=partial):
            with self.assertRaises(manager.InstallError): self.update(fixture, archive, digest)
        self.assertEqual(fired, [True])
        self.assert_a(fixture)
        self.assertEqual(self.protected(fixture), protected)
        before = self.snapshot(fixture)
        for action in (lambda: self.update(fixture, archive, digest), lambda: manager.rollback_update(fixture[1]),
                       lambda: self.recover(fixture)):
            with self.assertRaises(manager.InstallError): action()
            self.assertEqual(self.snapshot(fixture), before)
        self.assertEqual(self.bank(fixture).read_bytes(), b'{"schema":')

    def test_bank_complement_new_inode_or_unknown_workspace_entries_refuse(self):
        for kind in ("bank", "payload", "selector-inode", "barrier-inode", "extra", "symlink"):
            with self.subTest(kind=kind):
                fixture, archive, digest = self.fixture()
                self.update(fixture, archive, digest)
                if kind == "bank": self.bank(fixture).write_bytes(b'{"schema":"unknown"}\n')
                if kind == "payload":
                    path = self.data_slot(fixture) / "versions" / fixture[3] / "libexec/steam.py"
                    path.write_bytes(path.read_bytes() + b"# retained complement drift\n")
                if kind in ("selector-inode", "barrier-inode"):
                    path = self.state_slot(fixture) / ("current.json" if kind == "selector-inode" else "barrier.json")
                    temporary = self.state_slot(fixture) / "owned-replacement.tmp"
                    temporary.write_bytes(path.read_bytes()); temporary.chmod(0o600)
                    old = path.stat()
                    os.replace(temporary, path)
                    self.assertNotEqual((old.st_dev, old.st_ino), (path.stat().st_dev, path.stat().st_ino))
                if kind == "extra": (self.state_slot(fixture) / "owned-extra").write_bytes(b"do not delete\n")
                if kind == "symlink": (self.data_slot(fixture) / "owned-link").symlink_to(fixture[0] / "missing-owned-target")
                before = self.snapshot(fixture)
                for action in (lambda: fixture[5].rollback_update(fixture[1]), lambda: self.recover(fixture)):
                    with self.assertRaises(fixture[5].InstallError): action()
                    self.assertEqual(self.snapshot(fixture), before)

    def test_inactive_mixed_pair_is_refused_without_normalizing(self):
        fixture, archive, digest = self.fixture()
        self.interrupt_after_sync(fixture, ("active", digest, fixture[3]),
                                  lambda: self.update(fixture, archive, digest))
        # Owned deliberate contradiction: move the known active barrier to its
        # empty slot without completing the mixed selector pair.
        os.rename(self.state(fixture) / "pending-intent.json", self.state_slot(fixture) / "barrier.json")
        self.assertEqual(self.pair(fixture), ("slot", digest, fixture[3]))
        before = self.snapshot(fixture)
        with self.assertRaises(fixture[5].InstallError): self.recover(fixture)
        self.assertEqual(self.snapshot(fixture), before)

    def test_existing_lock_refuses_update_before_preparation(self):
        fixture, archive, digest = self.fixture()
        before = self.snapshot(fixture)
        with fixture[5]._locked(fixture[1]):
            with self.assertRaises(fixture[5].InstallError): self.update(fixture, archive, digest)
        self.assertEqual(self.snapshot(fixture), before)
        self.assertFalse(self.state_slot(fixture).exists())
        self.assertFalse(self.data_slot(fixture).exists())

    def test_finish_install_history_and_userdata_survive_update_rollback_and_repeat_refusal(self):
        fixture, archive, digest = self.fixture(finished_bank=True)
        protected = self.protected(fixture)
        self.update(fixture, archive, digest)
        self.assertEqual(fixture[5].status(fixture[1])["archiveSha256"], digest)
        fixture[5].rollback_update(fixture[1])
        self.assert_a(fixture)
        self.assertEqual(self.protected(fixture), protected)
        before = self.snapshot(fixture)
        with self.assertRaises(fixture[5].InstallError): self.update(fixture, archive, digest)
        self.assertEqual(self.snapshot(fixture), before)
        self.assertEqual(self.protected(fixture), protected)

    def test_ordinary_uninstall_does_not_allow_update_recovery_to_resurrect(self):
        fixture, archive, digest = self.fixture()
        self.update(fixture, archive, digest)
        result = fixture[5].uninstall(fixture[1])
        self.assertEqual(result["status"], "uninstalled")
        self.assertFalse(self.base(fixture).exists())
        self.assertTrue((self.data_slot(fixture) / "versions" / fixture[3]).is_dir())
        before = self.snapshot(fixture)
        with self.assertRaises(fixture[5].InstallError): self.recover(fixture)
        self.assertEqual(self.snapshot(fixture), before)
        self.assertFalse(self.base(fixture).exists())
        install_fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_renameat2_exdev_or_unavailable_refuses_without_copy_delete_fallback(self):
        for number in (errno.EXDEV, errno.ENOSYS):
            with self.subTest(errno=number):
                fixture, archive, digest = self.fixture()
                protected = self.protected(fixture)
                calls = []
                class Rename:
                    def __call__(self, *args):
                        calls.append(args)
                        ctypes.set_errno(number)
                        return -1
                library = mock.Mock()
                library.renameat2 = Rename()
                # Keep FD filesystem classification real; only renameat2 fails.
                library.fstatfs = ctypes.CDLL(None, use_errno=True).fstatfs
                with mock.patch.object(ctypes, "CDLL", return_value=library):
                    with self.assertRaises(fixture[5].InstallError): self.update(fixture, archive, digest)
                self.assertTrue(calls, "documented renameat2 seam must be exercised")
                self.assertEqual(self.protected(fixture), protected)
                self.assertEqual(fixture[5].status(fixture[1])["archiveSha256"], fixture[3])
                self.assertFalse((self.state(fixture) / "pending-intent.json").exists())
                install_fixtures.InstallGuardTests.assert_userdata(self, fixture)


if __name__ == "__main__":
    unittest.main()
