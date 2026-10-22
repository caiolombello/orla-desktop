"""Persistent directory proofs with synthetic FD/ioctl boundaries; no native IPC."""
import contextlib
import copy
import errno
import io
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_install_guards as fixtures
import test_install_service as service_fixtures


class InstallIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        private = temporary.name
        self.environment = mock.patch.dict(os.environ, {
            "HOME": private, "XDG_DATA_HOME": private + "/data", "XDG_STATE_HOME": private + "/state",
            "XDG_RUNTIME_DIR": private, "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + private + "/absent-bus",
            "PATH": "/usr/bin:/bin"}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for target in ("subprocess.Popen", "subprocess.run", "os.execve", "os.system"):
            guard = mock.patch(target, side_effect=AssertionError("native/process operation forbidden: " + target))
            guard.start()
            self.addCleanup(guard.stop)

    def fixture(self):
        return fixtures.InstallGuardTests.fixture(self)

    def snapshot(self, fixture):
        return fixtures.InstallGuardTests.snapshot(self, fixture[1].home)

    @contextlib.contextmanager
    def filesystem(self, manager, *, btrfs=True):
        real_stat, real_fstat, real_lstat = os.stat, os.fstat, os.lstat
        state = {"dev": 51, "fsUuid": b"f" * 16, "subvolumeUuid": b"s" * 16,
                 "treeId": 256, "inodeGeneration": 7, "proofs": {}, "statChanges": {}, "strictInodes": set(), "directoryDevices": {}}
        def observed(value):
            fields = {name: getattr(value, name) for name in dir(value) if name.startswith("st_")}
            fields["st_dev"] = state["directoryDevices"].get(value.st_ino, state["dev"])
            fields.update(state["statChanges"].get(value.st_ino, {}))
            return SimpleNamespace(**fields)
        def ioctl(fd, request, buffer, mutate=True):
            self.assertTrue(stat.S_ISDIR(real_fstat(fd).st_mode))
            self.assertEqual(bytes(buffer), b"\0" * len(buffer))
            self.assertIs(mutate, True)
            proof = {**state, **state["proofs"].get(real_fstat(fd).st_ino, {})}
            if request == 0x8400941f:
                self.assertEqual(len(buffer), 1024)
                buffer[16:32] = proof["fsUuid"]
            elif request == 0x81f8943c:
                self.assertEqual(len(buffer), 504)
                struct.pack_into("=Q", buffer, 0, proof["treeId"])
                buffer[296:312] = proof["subvolumeUuid"]
            elif request == 0x80087601:
                self.assertEqual(len(buffer), 8)
                struct.pack_into("=I", buffer, 0, proof["inodeGeneration"])
            else:
                self.fail("unexpected ioctl: " + hex(request))
            return 0
        with mock.patch.object(manager.os, "stat", side_effect=lambda *a, **k: observed(real_stat(*a, **k))), \
             mock.patch.object(manager.os, "fstat", side_effect=lambda fd: observed(real_fstat(fd))), \
             mock.patch.object(manager.os, "lstat", side_effect=lambda *a, **k: observed(real_lstat(*a, **k))), \
             mock.patch.object(manager, "_filesystem_type", side_effect=lambda fd: 0x9123683e if btrfs and real_fstat(fd).st_ino not in state["strictInodes"] else 0xef53, create=True), \
             mock.patch.object(manager.fcntl, "ioctl", side_effect=ioctl):
            yield state

    def invoke(self, manager, paths, *arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = manager.main(["--home", str(paths.home), "--data-home", str(paths.data_home),
                                 "--state-home", str(paths.state_home), *arguments])
        return code, output.getvalue()

    def installed_manager(self, fixture):
        tools = fixture[5]._base(fixture[1]) / "tools"
        manager, name, previous = fixtures.fixtures.load_bootstrap(tools)
        if previous is None:
            self.addCleanup(sys.modules.pop, name, None)
        else:
            self.addCleanup(sys.modules.__setitem__, name, previous)
        return manager

    def legacy(self, manager, paths):
        # Construct an old-format fixture; this is never production adoption.
        receipt = manager._receipt(paths)
        receipt["schema"] = "orla-launcher-install-0.1"
        receipt.pop("directoryProofs")
        for path in (manager._state(paths) / "current.json",
                     manager._state(paths) / "receipts" / (receipt["archiveSha256"] + ".json")):
            path.write_bytes(manager._json(receipt))
        return receipt

    def test_retained_finish_bank_state_only_device_drift_refuses_before_missing_lock_creation(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        original = manager._unlink_checked

        def cut(path, *args, **kwargs):
            if path.name == "pending-intent.json":
                raise manager.InstallError("write_failed")
            return original(path, *args, **kwargs)

        with self.filesystem(manager) as fs:
            with mock.patch.object(manager, "_unlink_checked", side_effect=cut):
                with self.assertRaises(manager.InstallError):
                    fixtures.InstallGuardTests.install(self, fixture)
            with mock.patch.object(manager, "_unlink_checked", side_effect=manager.InstallError("write_failed")):
                with self.assertRaises(manager.InstallError):
                    manager.recover_finish_install(paths)
            state = manager._state(paths)
            bank = state / "transactions" / (fixture[3] + "-finish-install-recovery.json")
            self.assertTrue(bank.is_file())
            (state / "lock").unlink()
            # State may live on a different filesystem from the managed payload.
            fs["directoryDevices"] = {p.stat().st_ino: 53 for p in [state, *state.rglob("*")]}
            before = self.snapshot(fixture)
            with self.assertRaises(manager.InstallError) as raised:
                manager.recover_finish_install(paths)
            self.assertEqual(raised.exception.code, "recovery_parent_changed")
            self.assertFalse((state / "lock").exists())
            self.assertEqual(self.snapshot(fixture), before)

    def test_device_51_to_53_admits_status_session_and_service_without_rewriting_receipts(self):
        fixture = self.fixture()
        paths = fixture[1]
        with self.filesystem(fixture[5]):
            fixtures.InstallGuardTests.install(self, fixture)
        before = self.snapshot(fixture)
        fixtures.InstallGuardTests.hide_source(self, fixture)
        manager = self.installed_manager(fixture)
        with self.filesystem(manager) as fs:
            backend = service_fixtures.FakeServiceBackend(paths, fixture[3])
            with mock.patch.object(manager, "NativeServiceBackend", return_value=backend):
                code, output = self.invoke(manager, paths, "service", "enable")
                self.assertEqual(code, 0, output)
                self.assertEqual(json.loads(output)["status"], "active")
            installed_service = self.snapshot(fixture)
            fs["dev"] = 53
            code, output = self.invoke(manager, paths, "status")
            self.assertEqual(code, 0, output)
            self.assertEqual(json.loads(output)["status"], "installed")
            with mock.patch.object(manager.os, "execv") as execute:
                self.assertEqual(self.invoke(manager, paths, "session"), (0, ""))
            binary = str(manager._base(paths) / "versions" / fixture[3] / "bin/orla-launcher")
            execute.assert_called_once_with(binary, [binary, "--managed-shortcuts", "--start-hidden"])
            with mock.patch.object(manager, "NativeServiceBackend", return_value=backend):
                for action in ("enable", "status"):
                    code, output = self.invoke(manager, paths, "service", action)
                    self.assertEqual(code, 0, output)
                    self.assertEqual(json.loads(output)["status"], "active")
                self.assertEqual(self.snapshot(fixture), installed_service)
                self.assertEqual(backend.events.count("start"), 1)
                code, output = self.invoke(manager, paths, "service", "disable")
                self.assertEqual(code, 0, output)
                self.assertEqual(json.loads(output)["status"], "disabled")
            after = self.snapshot(fixture)
            for path, record in before.items():
                if record[0] == "file":
                    self.assertEqual(after[path], record)
            receipt = json.loads((manager._state(paths) / "current.json").read_bytes())
            self.assertEqual(receipt["schema"], "orla-launcher-install-0.2")
            self.assertTrue(all(item["pin"][0] == 51 for item in receipt["directories"]))
            self.assertTrue(all(item["policy"] == "btrfs-fd-0.1" for item in receipt["directoryProofs"].values()))
            fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_each_stable_proof_or_nondevice_stat_difference_refuses_before_exec_or_service_effects(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager) as fs:
            fixtures.InstallGuardTests.install(self, fixture)
            fs["dev"] = 53
            before = self.snapshot(fixture)
            for key, directory in manager._directories(paths, fixture[3]).items():
                ino = directory.stat().st_ino
                for field, changed in (("fsUuid", b"x" * 16), ("treeId", 257),
                                       ("subvolumeUuid", b"x" * 16), ("inodeGeneration", 8),
                                       ("st_ino", ino + 1000000), ("st_mode", stat.S_IFDIR | 0o750),
                                       ("st_mode", stat.S_IFREG | 0o755),
                                       ("st_uid", os.getuid() + 1), ("st_gid", os.getgid() + 1)):
                    with self.subTest(directory=key, field=field):
                        changes = fs["statChanges"] if field.startswith("st_") else fs["proofs"]
                        changes[ino] = {field: changed}
                        backend = service_fixtures.FakeServiceBackend(paths, fixture[3])
                        with mock.patch.object(manager.os, "execv") as execute:
                            code, output = self.invoke(manager, paths, "session")
                        self.assertEqual(code, 2, output)
                        execute.assert_not_called()
                        with self.assertRaises(manager.InstallError):
                            manager.service(paths, "enable", backend=backend)
                        self.assertEqual(backend.events, [])
                        changes.clear()
                        self.assertEqual(self.snapshot(fixture), before)

    def test_legacy_and_explicit_posix_policy_stay_strict_after_device_drift(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                fixture = self.fixture()
                manager, paths = fixture[5], fixture[1]
                with self.filesystem(manager, btrfs=legacy) as fs:
                    fixtures.InstallGuardTests.install(self, fixture)
                    if legacy:
                        self.legacy(manager, paths)
                    else:
                        self.assertTrue(all(proof == {"policy": "posix-strict-0.1"}
                                            for proof in manager._receipt(paths)["directoryProofs"].values()))
                    before = self.snapshot(fixture)
                    fs["dev"] = 53
                    for command in ("status", "session", "uninstall"):
                        code, output = self.invoke(manager, paths, command)
                        self.assertEqual(code, 2, output)
                        expected = "directory_operation_requires_original_device" if command == "uninstall" and not legacy else "managed_parent_drift"
                        self.assertEqual(json.loads(output)["code"], expected)
                    self.assertEqual(self.snapshot(fixture), before)

    def test_destructive_or_transaction_operations_refuse_device_drift_before_first_write(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager) as fs:
            fixtures.InstallGuardTests.install(self, fixture)
            fs["dev"] = 53
            (manager._state(paths) / "lock").unlink()
            before = self.snapshot(fixture)
            with mock.patch.object(manager, "_write_new", side_effect=AssertionError("write before identity admission")):
                for action in (lambda: manager.uninstall(paths), lambda: manager.recover_finish_install(paths),
                               lambda: manager.update_archive(fixture[2], expected_sha256=fixture[3],
                                                              expected_commit="a" * 40, paths=paths)):
                    with self.assertRaises(manager.InstallError) as raised:
                        action()
                    self.assertEqual(raised.exception.code, "directory_operation_requires_original_device")
            self.assertEqual(self.snapshot(fixture), before)

    def test_new_schema_rejects_missing_unknown_and_malformed_proofs(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager):
            fixtures.InstallGuardTests.install(self, fixture)
            receipt = manager._receipt(paths)
            self.assertEqual(manager._receipt_value(paths, manager._json(receipt)), receipt)
            mutations = [lambda r: r.pop("directoryProofs"),
                         lambda r: r["directoryProofs"].pop("base"),
                         lambda r: r["directoryProofs"].update(extra={"policy": "posix-strict-0.1"})]
            for field, values in {"policy": [None, "unknown", True], "fsUuid": ["0" * 32, "f" * 33, True],
                                  "subvolumeUuid": ["0" * 32, "S" * 32], "treeId": [True, 0, -1, 2 ** 64],
                                  "inodeGeneration": [True, 0, -1, 2 ** 32]}.items():
                for value in values:
                    mutations.append(lambda r, f=field, v=value: r["directoryProofs"]["base"].update({f: v}))
            for index, change in enumerate(mutations):
                with self.subTest(mutation=index):
                    malformed = copy.deepcopy(receipt)
                    change(malformed)
                    with self.assertRaises(manager.InstallError) as raised:
                        manager._receipt_value(paths, manager._json(malformed))
                    self.assertEqual(raised.exception.code, "receipt_schema")

    def test_ioctl_failure_never_downgrades_btrfs_to_posix_or_executes(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager):
            fixtures.InstallGuardTests.install(self, fixture)
            before = self.snapshot(fixture)
            for request in (0x8400941f, 0x81f8943c, 0x80087601):
                original = manager.fcntl.ioctl.side_effect
                def fail(fd, operation, buffer, mutate, expected=request):
                    if operation == expected:
                        raise OSError(errno.ENOTTY, "synthetic unavailable Btrfs ioctl")
                    return original(fd, operation, buffer, mutate)
                with self.subTest(request=request), mock.patch.object(manager.fcntl, "ioctl", side_effect=fail), \
                     mock.patch.object(manager.os, "execv") as execute:
                    code, output = self.invoke(manager, paths, "session")
                    self.assertEqual(code, 2, output)
                    self.assertEqual(json.loads(output)["code"], "directory_proof_unavailable")
                    execute.assert_not_called()
                    self.assertEqual(self.snapshot(fixture), before)


    def test_mixed_filesystem_and_subvolume_proofs_are_captured_per_directory(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        # Assign each newly created directory a distinct containing FS/subvolume.
        mkdir = manager._mkdir_new
        with self.filesystem(manager) as fs:
            def create(*args, **kwargs):
                pin = mkdir(*args, **kwargs)
                ino = pin[1]
                index = len(fs["proofs"]) + 1
                fs["proofs"][ino] = {"fsUuid": bytes([index]) * 16, "treeId": 256 + index,
                                     "subvolumeUuid": bytes([index + 32]) * 16}
                return pin
            with mock.patch.object(manager, "_mkdir_new", side_effect=create):
                fixtures.InstallGuardTests.install(self, fixture)
            before = self.snapshot(fixture)
            receipt = manager._receipt(paths)
            self.assertEqual(len({p["fsUuid"] for p in receipt["directoryProofs"].values()}), 6)
            fs["dev"] = 53
            self.assertEqual(manager.status(paths)["status"], "installed")
            self.assertEqual(self.snapshot(fixture), before)
            # A strict-policy directory in the same closure cannot borrow Btrfs authority.
            fs["strictInodes"].add(manager._base(paths).stat().st_ino)
            with self.assertRaises(manager.InstallError):
                manager.status(paths)

    def test_full_dev_and_inode_race_guards_reject_at_open_after_yield_and_during_ioctl(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager) as fs:
            fixtures.InstallGuardTests.install(self, fixture)
            directory = manager._base(paths)
            ino = directory.stat().st_ino
            real_open = manager.os.open
            for field in ("st_dev", "st_ino"):
                changed = 53 if field == "st_dev" else ino + 1
                def swap_at_open(path, *args, **kwargs):
                    descriptor = real_open(path, *args, **kwargs)
                    if path == directory.name:
                        fs["statChanges"][ino] = {field: changed}
                    return descriptor
                with self.subTest(field=field, phase="open"), \
                     mock.patch.object(manager.os, "open", side_effect=swap_at_open):
                    with self.assertRaises(manager.InstallError) as raised:
                        with manager._directory(directory):
                            self.fail("directory swap was admitted")
                    self.assertEqual(raised.exception.code, "parent_changed")
                fs["statChanges"].clear()
                with self.subTest(field=field, phase="yield"):
                    with self.assertRaises(manager.InstallError) as raised:
                        with manager._directory(directory):
                            fs["statChanges"][ino] = {field: changed}
                    self.assertEqual(raised.exception.code, "parent_changed")
                fs["statChanges"].clear()
            original = manager.fcntl.ioctl.side_effect
            def swap_during_ioctl(fd, request, buffer, mutate):
                result = original(fd, request, buffer, mutate)
                fs["dev"] = 53
                return result
            with mock.patch.object(manager.fcntl, "ioctl", side_effect=swap_during_ioctl), \
                 mock.patch.object(manager.os, "execv") as execute:
                code, output = self.invoke(manager, paths, "session")
            self.assertEqual(code, 2, output)
            self.assertEqual(json.loads(output)["code"], "parent_changed")
            execute.assert_not_called()

    def test_file_read_retains_full_device_race_guard(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager) as fs:
            fixtures.InstallGuardTests.install(self, fixture)
            original = manager.os.read
            def change(fd, size):
                data = original(fd, size)
                fs["dev"] = 53
                return data
            with mock.patch.object(manager.os, "read", side_effect=change):
                with self.assertRaises(manager.InstallError) as raised:
                    manager._read(manager._state(paths) / "current.json", mode=0o600)
            self.assertEqual(raised.exception.code, "file_changed")

    def test_primary_exception_survives_directory_close_failure(self):
        fixture = self.fixture()
        manager = fixture[5]
        primary = manager.InstallError("synthetic_primary")
        real_close = manager.os.close
        closes = []
        def close(fd):
            real_close(fd)
            closes.append(fd)
            if len(closes) == 1:
                raise OSError(errno.EIO, "synthetic close failure")
        with mock.patch.object(manager.os, "close", side_effect=close):
            with self.assertRaises(manager.InstallError) as raised:
                with manager._directory(fixture[1].home):
                    raise primary
        self.assertIs(raised.exception, primary)
        self.assertGreater(len(closes), 1)

    def test_malformed_ioctl_output_is_refused_without_receipt_changes(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager):
            fixtures.InstallGuardTests.install(self, fixture)
            before = self.snapshot(fixture)
            original = manager.fcntl.ioctl.side_effect
            for failure in ("size", "status", "zero_uuid", "zero_generation"):
                def malformed(fd, request, buffer, mutate, kind=failure):
                    result = original(fd, request, buffer, mutate)
                    if kind == "size":
                        buffer.extend(b"x")
                    if kind == "zero_uuid" and request == 0x8400941f:
                        buffer[16:32] = b"\0" * 16
                    if kind == "zero_generation" and request == 0x80087601:
                        buffer[:] = b"\0" * len(buffer)
                    return 1 if kind == "status" else result
                with self.subTest(failure=failure), mock.patch.object(manager.fcntl, "ioctl", side_effect=malformed):
                    with self.assertRaises(manager.InstallError):
                        manager.status(paths)
                self.assertEqual(self.snapshot(fixture), before)

    def test_fstatfs_uses_bounded_verified_x86_64_layout_and_refuses_errors(self):
        manager = self.fixture()[5]
        calls = []
        def fstatfs(fd, output):
            self.assertEqual(fd, 19)
            self.assertEqual(manager.ctypes.sizeof(output._obj), 120)
            self.assertEqual(list(output._obj), [0] * 15)
            calls.append(fd)
            output._obj[0] = 0x9123683e
            return 0
        library = mock.Mock()
        library.fstatfs = mock.Mock(side_effect=fstatfs)
        with mock.patch.object(manager.ctypes, "CDLL", return_value=library), \
             mock.patch.object(manager.os, "uname", return_value=SimpleNamespace(machine="x86_64")):
            self.assertEqual(manager._filesystem_type(19), 0x9123683e)
            self.assertEqual(calls, [19])
            library.fstatfs.return_value = -1
            library.fstatfs.side_effect = None
            with self.assertRaises(manager.InstallError) as raised:
                manager._filesystem_type(19)
            self.assertEqual(raised.exception.code, "directory_proof_unavailable")


    def second_archive(self, fixture):
        root = fixture[0] / "second archive"
        root.mkdir()
        package_tests = fixtures.fixtures.package_fixtures
        stage = package_tests.PackageTests().make_stage(root)
        (stage / "libexec/steam.py").write_bytes(b"# distinct inert B fixture\n")
        archive = root / "B.zip"
        digest = package_tests.package.build(stage, archive, version="0.1.1", commit="b" * 40,
                                             ci_image_digest="sha256:" + "c" * 64,
                                             runtime_inventory=package_tests.runtime_inventory())
        return archive, digest

    def test_legacy_and_new_update_banks_remain_strict_after_device_drift(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                fixture = self.fixture()
                manager, paths = fixture[5], fixture[1]
                archive, digest = self.second_archive(fixture)
                with self.filesystem(manager) as fs:
                    fixtures.InstallGuardTests.install(self, fixture)
                    if legacy:
                        self.legacy(manager, paths)
                    manager.update_archive(archive, expected_sha256=digest, expected_commit="b" * 40, paths=paths)
                    self.assertEqual(manager.status(paths)["archiveSha256"], digest)
                    bank_path = manager._state(paths) / "payload-update/bank.json"
                    bank = json.loads(bank_path.read_bytes())
                    self.assertEqual(bank["from"]["schema"], "orla-launcher-install-0.1" if legacy else "orla-launcher-install-0.2")
                    (manager._state(paths) / "lock").unlink()
                    before = self.snapshot(fixture)
                    fs["dev"] = 53
                    for action in (manager.rollback_update, manager.recover_update):
                        with self.assertRaises(manager.InstallError) as raised:
                            action(paths)
                        self.assertEqual(raised.exception.code, "update_parent")
                    self.assertEqual(self.snapshot(fixture), before)

    def test_legacy_and_new_inflight_recovery_banks_remain_strict_after_device_drift(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                fixture = self.fixture()
                manager, paths = fixture[5], fixture[1]
                original = manager._unlink_checked
                def cut(path, *args, **kwargs):
                    if path.name == "pending-intent.json":
                        raise manager.InstallError("write_failed")
                    return original(path, *args, **kwargs)
                with self.filesystem(manager) as fs:
                    with mock.patch.object(manager, "_unlink_checked", side_effect=cut):
                        with self.assertRaises(manager.InstallError):
                            fixtures.InstallGuardTests.install(self, fixture)
                    if legacy:
                        self.legacy(manager, paths)
                    # Cut after exclusive bank publication and before any cleanup.
                    with mock.patch.object(manager, "_unlink_checked", side_effect=manager.InstallError("write_failed")):
                        with self.assertRaises(manager.InstallError):
                            manager.recover_finish_install(paths)
                    bank = manager._state(paths) / "transactions" / (fixture[3] + "-finish-install-recovery.json")
                    self.assertTrue(bank.is_file())
                    before = self.snapshot(fixture)
                    fs["dev"] = 53
                    with self.assertRaises(manager.InstallError) as raised:
                        manager.recover_finish_install(paths)
                    self.assertEqual(raised.exception.code, "managed_parent_drift" if legacy else "directory_operation_requires_original_device")
                    self.assertEqual(self.snapshot(fixture), before)

    def test_ordinary_service_generation_stays_exact_after_stable_directory_admission(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager) as fs:
            fixtures.InstallGuardTests.install(self, fixture)
            changed = fixture[0] / "different-manager.py"
            changed.write_bytes(Path(manager.__file__).read_bytes() + b"# another generation\n")
            before = self.snapshot(fixture)
            fs["dev"] = 53
            backend = service_fixtures.FakeServiceBackend(paths, fixture[3])
            with mock.patch.object(manager, "__file__", str(changed)):
                with self.assertRaises(manager.InstallError) as raised:
                    manager.service(paths, "enable", backend=backend)
            self.assertEqual(raised.exception.code, "service_generation")
            self.assertEqual(backend.events, [])
            self.assertEqual(self.snapshot(fixture), before)


    def test_device_drift_admission_keeps_file_hashes_membership_and_history_exact(self):
        fixture = self.fixture()
        manager, paths = fixture[5], fixture[1]
        with self.filesystem(manager) as fs:
            fixtures.InstallGuardTests.install(self, fixture)
            fs["dev"] = 53
            before = self.snapshot(fixture)
            for key, (path, _mode) in manager._files(paths, fixture[3]).items():
                original = path.read_bytes()
                with self.subTest(file=key):
                    path.write_bytes(original + b"# changed bytes\n")
                    with self.assertRaises(manager.InstallError) as raised:
                        manager.status(paths)
                    self.assertEqual(raised.exception.code, "managed_drift")
                    path.write_bytes(original)
            extra = manager._base(paths) / "tools/extra.py"
            extra.write_bytes(b"# unowned extra\n")
            with self.assertRaises(manager.InstallError) as raised:
                manager.status(paths)
            self.assertEqual(raised.exception.code, "managed_extra_file")
            extra.unlink()
            current = manager._state(paths) / "current.json"
            original = current.read_bytes()
            value = json.loads(original)
            value["directoryProofs"]["base"]["treeId"] += 1
            current.write_bytes(manager._json(value))
            with self.assertRaises(manager.InstallError) as raised:
                manager.status(paths)
            self.assertEqual(raised.exception.code, "receipt_history_changed")
            current.write_bytes(original)
            self.assertEqual(self.snapshot(fixture), before)


if __name__ == "__main__":
    unittest.main()
