"""Owned finish-install recovery causals; Root alone executes these tests."""
import errno
import io
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

import test_install_guards as fixtures


CONTROL_ORDER = ("pending-error.json", "pending-intent.json", "pending.json")


class FinishInstallRecoveryGuardTests(unittest.TestCase):
    def fixture(self):
        return fixtures.InstallGuardTests.fixture(self)

    def state(self, fixture):
        return fixture[1].state_home / "orla/launcher-install"

    def bank(self, fixture):
        return self.state(fixture) / "transactions" / (fixture[3] + "-finish-install-recovery.json")

    def controls(self, fixture):
        return {name: (self.state(fixture) / name).read_bytes()
                for name in CONTROL_ORDER if (self.state(fixture) / name).exists()}

    def protected(self, fixture):
        manager, paths = fixture[5], fixture[1]
        files = [path for path, _mode in manager._files(paths, fixture[3]).values()]
        state = self.state(fixture)
        files += [state / "current.json", state / "receipts" / (fixture[3] + ".json"),
                  state / "transactions" / (fixture[3] + "-install.json"),
                  state / "transactions" / (fixture[3] + "-installed.json")]
        return {str(path): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode), manager._identity(path.stat()))
                for path in files if path.exists()}

    def late_failure(self):
        fixture = self.fixture()
        manager = fixture[5]
        original = manager._unlink_checked
        fired = []
        def fail(path, record, mode, *args, **kwargs):
            if Path(path).name == "pending-intent.json" and not fired:
                fired.append(str(path))
                raise manager.InstallError("write_failed")
            return original(path, record, mode, *args, **kwargs)
        with mock.patch.object(manager, "_unlink_checked", side_effect=fail), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("no program execution")):
            with self.assertRaises(manager.InstallError) as raised:
                fixtures.InstallGuardTests.install(self, fixture)
        self.assertEqual(raised.exception.code, "write_failed")
        self.assertEqual(len(fired), 1)
        state = self.state(fixture)
        self.assertTrue((state / "transactions" / (fixture[3] + "-installed.json")).is_file())
        self.assertEqual(set(self.controls(fixture)), set(CONTROL_ORDER))
        self.assertEqual(json.loads((state / "pending-error.json").read_bytes())["code"], "write_failed")
        return fixture

    def recover(self, fixture):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("recovery cannot execute programs")):
            return fixture[5].recover_finish_install(fixture[1])

    def refuse_without_cleanup(self, fixture):
        manager = fixture[5]
        controls = self.controls(fixture)
        with mock.patch.object(manager, "_unlink_checked", wraps=manager._unlink_checked) as unlink, \
             mock.patch("subprocess.Popen", side_effect=AssertionError("recovery cannot execute programs")):
            with self.assertRaises(manager.InstallError) as raised:
                manager.recover_finish_install(fixture[1])
        self.assertIsInstance(raised.exception.code, str)
        unlink.assert_not_called()
        self.assertEqual(self.controls(fixture), controls)
        fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_each_legal_cleanup_prefix_retries_with_immutable_bank_and_proofs(self):
        for stop_at in CONTROL_ORDER:
            with self.subTest(stop_at=stop_at):
                fixture = self.late_failure()
                manager = fixture[5]
                original_controls, protected = self.controls(fixture), self.protected(fixture)
                original = manager._unlink_checked
                stopped, deleted = [], []
                def interrupt(path, record, mode, *args, **kwargs):
                    name = Path(path).name
                    if name in CONTROL_ORDER:
                        self.assertTrue(self.bank(fixture).is_file(), "bank must precede every unlink")
                        if name == stop_at and not stopped:
                            stopped.append(name)
                            raise manager.InstallError("write_failed")
                        deleted.append(name)
                    return original(path, record, mode, *args, **kwargs)
                with mock.patch.object(manager, "_unlink_checked", side_effect=interrupt):
                    with self.assertRaises(manager.InstallError):
                        self.recover(fixture)
                self.assertEqual(stopped, [stop_at])
                self.assertEqual(deleted, list(CONTROL_ORDER[:CONTROL_ORDER.index(stop_at)]))
                self.assertEqual(set(self.controls(fixture)), set(CONTROL_ORDER[CONTROL_ORDER.index(stop_at):]))
                bank_path = self.bank(fixture)
                bank_bytes, bank_pin = bank_path.read_bytes(), manager._identity(bank_path.stat())
                bank = json.loads(bank_bytes)
                self.assertEqual(bank["schema"], "orla-launcher-finish-install-recovery-0.1")
                self.assertEqual(bank["archiveSha256"], fixture[3])
                self.assertEqual(bank["commit"], "a" * 40)
                self.assertEqual([entry["name"] for entry in bank["pending"]], list(CONTROL_ORDER))
                self.assertEqual([entry["key"] for entry in bank["proofs"]], ["current", "receipt", "prepared", "installed"])
                self.assertEqual([entry["key"] for entry in bank["parents"]], ["state", "receipts", "transactions"])
                self.assertEqual(stat.S_IMODE(bank_path.stat().st_mode), 0o600)
                self.assertLessEqual(len(bank_bytes), 524288)
                captured_error = next(entry for entry in bank["pending"] if entry["name"] == "pending-error.json")
                self.assertEqual(bytes.fromhex(captured_error["dataHex"]), original_controls["pending-error.json"])
                result = self.recover(fixture)
                self.assertEqual(result["status"], "installed")
                self.assertEqual(result["runtime"], "unverified")
                self.assertEqual(self.controls(fixture), {})
                self.assertEqual((bank_path.read_bytes(), manager._identity(bank_path.stat())), (bank_bytes, bank_pin))
                self.assertEqual(self.protected(fixture), protected)
                fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_initial_intent_only_finishes_through_public_main(self):
        fixture = self.late_failure()
        for name in ("pending-error.json", "pending.json"):
            (self.state(fixture) / name).unlink()
        protected = self.protected(fixture)
        paths, manager = fixture[1], fixture[5]
        output = io.StringIO()
        with mock.patch("sys.stdout", output), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("recovery cannot execute programs")):
            code = manager.main(["--home", str(paths.home), "--data-home", str(paths.data_home),
                                 "--state-home", str(paths.state_home), "recover", "--finish-install"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "installed")
        self.assertEqual(self.controls(fixture), {})
        bank = json.loads(self.bank(fixture).read_bytes())
        for entry in bank["pending"]:
            if entry["name"] != "pending-intent.json":
                self.assertIsNone(entry["pin"])
                self.assertIsNone(entry["dataHex"])
        self.assertEqual(self.protected(fixture), protected)
        fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_repeated_recovery_without_pending_is_a_guarded_noop(self):
        for recovered in (False, True):
            with self.subTest(recovered=recovered):
                fixture = self.late_failure() if recovered else self.fixture()
                manager = fixture[5]
                if recovered:
                    self.recover(fixture)
                else:
                    fixtures.InstallGuardTests.install(self, fixture)
                protected = self.protected(fixture)
                bank = self.bank(fixture)
                bank_before = (bank.read_bytes(), manager._identity(bank.stat())) if bank.exists() else None
                with mock.patch.object(manager, "_write_new", side_effect=AssertionError("no-op cannot write history")), \
                     mock.patch.object(manager, "_unlink_checked", side_effect=AssertionError("no-op cannot delete")):
                    result = self.recover(fixture)
                self.assertEqual(result["status"], "installed")
                self.assertEqual(result["runtime"], "unverified")
                self.assertEqual(self.protected(fixture), protected)
                self.assertEqual(self.controls(fixture), {})
                self.assertEqual((bank.read_bytes(), manager._identity(bank.stat())) if bank.exists() else None, bank_before)

    def test_orphan_error_is_not_bankless_installed_noop(self):
        fixture = self.late_failure()
        for name in ("pending-intent.json", "pending.json"):
            (self.state(fixture) / name).unlink()
        self.refuse_without_cleanup(fixture)
        self.assertFalse(self.bank(fixture).exists())

    def test_missing_current_prepared_or_installed_marker_refuses_intact(self):
        for label in ("current", "prepared", "installed"):
            with self.subTest(label=label):
                fixture = self.late_failure()
                path = self.state(fixture) / "current.json" if label == "current" else \
                       self.state(fixture) / "transactions" / (fixture[3] + ("-install.json" if label == "prepared" else "-installed.json"))
                path.unlink()
                self.refuse_without_cleanup(fixture)
                self.assertFalse(self.bank(fixture).exists())

    def test_pending_uninstall_is_not_finished_as_install(self):
        fixture = self.late_failure()
        for name in CONTROL_ORDER:
            path = self.state(fixture) / name
            value = json.loads(path.read_bytes())
            value["operation"] = "uninstall"
            path.write_bytes(fixture[5]._json(value))
        self.refuse_without_cleanup(fixture)
        self.assertFalse(self.bank(fixture).exists())

    def test_managed_payload_drift_refuses_before_cleanup(self):
        fixture = self.late_failure()
        target = fixture[1].data_home / "orla-desktop/launcher/versions" / fixture[3] / "libexec/steam.py"
        changed = target.read_bytes() + b"# owned recovery drift\n"
        target.write_bytes(changed)
        self.refuse_without_cleanup(fixture)
        self.assertEqual(target.read_bytes(), changed)
        self.assertFalse(self.bank(fixture).exists())

    def test_preexisting_partial_or_unknown_bank_is_preserved_not_repaired(self):
        for raw in (b'{"schema":', b'{"schema":"unknown"}\n'):
            with self.subTest(raw=raw):
                fixture = self.late_failure()
                bank = self.bank(fixture)
                bank.write_bytes(raw)
                bank.chmod(0o600)
                pin = fixture[5]._identity(bank.stat())
                self.refuse_without_cleanup(fixture)
                self.assertEqual((bank.read_bytes(), fixture[5]._identity(bank.stat())), (raw, pin))

    def test_same_content_new_inode_at_unlink_seam_cannot_be_deleted(self):
        fixture = self.late_failure()
        manager = fixture[5]
        original = manager._unlink_checked
        target = self.state(fixture) / "pending-error.json"
        captured = target.read_bytes()
        old_pin = manager._identity(target.stat())
        swapped, deleted = [], []
        real_unlink = os.unlink
        def swap(path, record, mode, *args, **kwargs):
            if Path(path) == target and not swapped:
                expected_pin = kwargs.get("expected_pin", args[0] if args else None)
                self.assertIsNotNone(expected_pin, "captured pin must reach anchored helper")
                replacement = self.state(fixture) / "owned-new-inode.tmp"
                replacement.write_bytes(captured)
                replacement.chmod(0o600)
                os.replace(replacement, target)
                swapped.append(manager._identity(target.stat()))
            return original(path, record, mode, *args, **kwargs)
        def unlink(path, *args, **kwargs):
            deleted.append(str(path))
            return real_unlink(path, *args, **kwargs)
        with mock.patch.object(manager, "_unlink_checked", side_effect=swap), \
             mock.patch.object(manager.os, "unlink", side_effect=unlink):
            with self.assertRaises(manager.InstallError):
                self.recover(fixture)
        self.assertEqual(len(swapped), 1)
        self.assertNotEqual(swapped[0][:2], old_pin[:2])
        self.assertEqual(target.read_bytes(), captured)
        self.assertEqual(deleted, [])
        self.assertEqual(set(self.controls(fixture)), set(CONTROL_ORDER))

    def test_partial_exclusive_bank_publication_leaves_controls_and_retry_refuses(self):
        fixture = self.late_failure()
        manager = fixture[5]
        original = manager._write_new
        controls = self.controls(fixture)
        fired = []
        def partial(path, data, mode, *args, **kwargs):
            if Path(path) == self.bank(fixture) and not fired:
                original(path, b'{"schema":', mode, *args, **kwargs)
                fired.append(str(path))
                raise OSError(errno.EIO, "owned interrupted bank publication")
            return original(path, data, mode, *args, **kwargs)
        with mock.patch.object(manager, "_write_new", side_effect=partial), \
             mock.patch.object(manager, "_unlink_checked", wraps=manager._unlink_checked) as unlink:
            with self.assertRaises((manager.InstallError, OSError)):
                self.recover(fixture)
        self.assertEqual(len(fired), 1)
        unlink.assert_not_called()
        self.assertEqual(self.controls(fixture), controls)
        self.assertEqual(self.bank(fixture).read_bytes(), b'{"schema":')
        self.refuse_without_cleanup(fixture)
        self.assertEqual(self.bank(fixture).read_bytes(), b'{"schema":')

    def test_illegal_removed_suffix_or_reappeared_prefix_refuses_further_cleanup(self):
        for action in ("missing-middle", "reappeared-prefix"):
            with self.subTest(action=action):
                fixture = self.late_failure()
                manager = fixture[5]
                original = manager._unlink_checked
                saved_error = self.controls(fixture)["pending-error.json"]
                stop = "pending-error.json" if action == "missing-middle" else "pending-intent.json"
                def interrupt(path, record, mode, *args, **kwargs):
                    if Path(path).name == stop:
                        raise manager.InstallError("write_failed")
                    return original(path, record, mode, *args, **kwargs)
                with mock.patch.object(manager, "_unlink_checked", side_effect=interrupt):
                    with self.assertRaises(manager.InstallError):
                        self.recover(fixture)
                bank_before = self.bank(fixture).read_bytes()
                if action == "missing-middle":
                    (self.state(fixture) / "pending-intent.json").unlink()
                else:
                    path = self.state(fixture) / "pending-error.json"
                    path.write_bytes(saved_error)
                    path.chmod(0o600)
                self.refuse_without_cleanup(fixture)
                self.assertEqual(self.bank(fixture).read_bytes(), bank_before)


if __name__ == "__main__":
    unittest.main()
