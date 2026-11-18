"""Finalizing a payload update: content admission, re-entry after cuts, no native IPC."""
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import test_install_guards as install_fixtures
import test_install_identity as identity_fixtures
import test_install_service as service_fixtures
import test_install_update_guards as update_fixtures


class FinalizeUpdateTests(unittest.TestCase):
    setUp = identity_fixtures.InstallIdentityTests.setUp
    filesystem = identity_fixtures.InstallIdentityTests.filesystem
    invoke = identity_fixtures.InstallIdentityTests.invoke

    def fixture(self):
        return install_fixtures.InstallGuardTests.fixture(self)

    def snapshot(self, fixture):
        return install_fixtures.InstallGuardTests.snapshot(self, fixture[1].home)

    def archive(self, fixture, name, marker, commit):
        root = fixture[0] / ("archive " + name)
        root.mkdir()
        package_fixtures = update_fixtures.archive_fixtures.package_fixtures
        stage = package_fixtures.PackageTests().make_stage(root)
        (stage / "libexec/steam.py").write_bytes(b"# distinct inert " + marker + b" fixture\n")
        archive = root / (name + ".zip")
        digest = package_fixtures.package.build(stage, archive, version="0.1.1", commit=commit,
                                                ci_image_digest="sha256:" + "c" * 64,
                                                runtime_inventory=package_fixtures.runtime_inventory())
        return archive, digest, commit

    def update(self, manager, paths, archive):
        return manager.update_archive(archive[0], expected_sha256=archive[1], expected_commit=archive[2], paths=paths)

    def slots(self, manager, paths):
        state_slot, data_slot = manager._update_paths(paths)
        return state_slot.exists(), data_slot.exists()

    def session(self, manager, paths, digest):
        with mock.patch.object(manager.os, "execv") as execute:
            self.assertEqual(self.invoke(manager, paths, "session"), (0, ""))
        binary = str(manager._base(paths) / "versions" / digest / "bin/orla-launcher")
        execute.assert_called_once_with(binary, [binary, "--managed-shortcuts", "--start-hidden"])

    def installed(self, fixture):
        manager, paths = fixture[5], fixture[1]
        install_fixtures.InstallGuardTests.install(self, fixture)
        return manager, paths

    def test_finalize_after_update_then_reboot_allows_a_second_update(self):
        fixture = self.fixture()
        b = self.archive(fixture, "B", b"B", "b" * 40)
        c = self.archive(fixture, "C", b"C", "d" * 40)
        with self.filesystem(fixture[5]) as fs:
            manager, paths = self.installed(fixture)
            history = (manager._state(paths) / "receipts" / (fixture[3] + ".json")).read_bytes()
            self.update(manager, paths, b)
            fs["dev"] = 53
            with self.assertRaises(manager.InstallError) as raised:
                self.update(manager, paths, c)
            self.assertEqual(raised.exception.code, "update_workspace_exists")
            code, output = self.invoke(manager, paths, "finalize")
            self.assertEqual(code, 0, output)
            self.assertEqual(json.loads(output)["archiveSha256"], b[1])
            self.assertEqual(self.slots(manager, paths), (False, False))
            self.assertEqual(sorted(p.name for p in (manager._base(paths) / "versions").iterdir()), [b[1]])
            self.assertEqual((manager._state(paths) / "receipts" / (fixture[3] + ".json")).read_bytes(), history)
            self.assertEqual(manager.status(paths)["archiveSha256"], b[1])
            self.session(manager, paths, b[1])
            # Finalizing again is a no-op.
            before = self.snapshot(fixture)
            self.assertEqual(manager.finalize_update(paths)["archiveSha256"], b[1])
            self.assertEqual(self.snapshot(fixture), before)
            self.assertEqual(self.update(manager, paths, c)["archiveSha256"], c[1])
            self.assertEqual(manager.rollback_update(paths)["archiveSha256"], b[1])
            self.assertEqual(manager.finalize_update(paths)["archiveSha256"], b[1])
            self.assertEqual(self.slots(manager, paths), (False, False))
            # Receipt history stays, so the discarded archive cannot be installed again by update.
            with self.assertRaises(manager.InstallError) as raised:
                self.update(manager, paths, c)
            self.assertEqual(raised.exception.code, "update_history_exists")
            # The restored receipt still names the first boot's device; uninstall admits it by proof.
            self.assertEqual(manager.uninstall(paths)["status"], "uninstalled")
            self.assertFalse(manager._base(paths).exists())

    def test_finalize_refuses_an_update_in_flight_and_changed_parked_content_before_removing(self):
        fixture = self.fixture()
        b = self.archive(fixture, "B", b"B", "b" * 40)
        manager, paths = self.installed(fixture)
        self.update(manager, paths, b)
        state_slot, data_slot = manager._update_paths(paths)
        parked = data_slot / "versions" / fixture[3]
        mutations = (
            ("in flight", lambda: (state_slot / "barrier.json").rename(manager._state(paths) / "pending-intent.json"),
             lambda: (manager._state(paths) / "pending-intent.json").rename(state_slot / "barrier.json"), "pending_transaction"),
            ("changed payload", lambda: (parked / "libexec/steam.py").write_bytes(b"# changed\n"),
             None, "managed_drift"),
            ("extra file", lambda: (parked / "libexec/extra.py").write_bytes(b"# extra\n"),
             lambda: (parked / "libexec/extra.py").unlink(), "update_workspace"),
            ("other selector", lambda: (state_slot / "current.json").write_bytes(b"{}"),
             None, "update_selector_changed"),
        )
        for name, change, undo, code in mutations:
            with self.subTest(case=name):
                original = {path: path.read_bytes() for path in (parked / "libexec/steam.py", state_slot / "current.json")}
                change()
                before = self.snapshot(fixture)
                with self.assertRaises(manager.InstallError) as raised:
                    manager.finalize_update(paths)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(self.snapshot(fixture), before)
                if undo is not None:
                    undo()
                for path, data in original.items():
                    if path.read_bytes() != data:
                        mode = path.stat().st_mode
                        path.write_bytes(data)
                        os.chmod(path, mode)
        self.assertEqual(manager.finalize_update(paths)["archiveSha256"], b[1])
        self.assertEqual(self.slots(manager, paths), (False, False))
        self.session(manager, paths, b[1])
        backend = service_fixtures.FakeServiceBackend(paths, b[1])
        for action, status in (("enable", "active"), ("status", "active"), ("disable", "disabled")):
            self.assertEqual(manager.service(paths, action, backend=backend)["status"], status)
        self.assertEqual(manager.uninstall(paths)["status"], "uninstalled")

    def test_every_cut_finalize_is_refused_by_update_and_rollback_then_finished_by_finalize(self):
        steps = 0
        while True:
            with self.subTest(cut=steps):
                fixture = self.fixture()
                b = self.archive(fixture, "B", b"B", "b" * 40)
                c = self.archive(fixture, "C", b"C", "d" * 40)
                manager, paths = self.installed(fixture)
                self.update(manager, paths, b)
                calls = []
                real_unlink, real_rmdir = os.unlink, os.rmdir
                def counted(real):
                    def call(*args, **kwargs):
                        calls.append(args[0])
                        if len(calls) == steps + 1:
                            raise OSError("cut")
                        return real(*args, **kwargs)
                    return call
                with mock.patch.object(manager.os, "unlink", side_effect=counted(real_unlink)), \
                     mock.patch.object(manager.os, "rmdir", side_effect=counted(real_rmdir)):
                    try:
                        manager.finalize_update(paths)
                        finished = True
                    except manager.InstallError as error:
                        self.assertEqual(error.code, "filesystem_unknown")
                        finished = False
                if finished:
                    self.assertEqual(self.slots(manager, paths), (False, False))
                    break
                if steps:
                    before = self.snapshot(fixture)
                    for action in (lambda: manager.rollback_update(paths), lambda: self.update(manager, paths, c)):
                        with self.assertRaises(manager.InstallError):
                            action()
                    self.assertEqual(self.snapshot(fixture), before)
                self.assertEqual(manager.status(paths)["archiveSha256"], b[1])
                self.assertEqual(manager.finalize_update(paths)["archiveSha256"], b[1])
                self.assertEqual(self.slots(manager, paths), (False, False))
                self.assertEqual(self.update(manager, paths, c)["archiveSha256"], c[1])
            steps += 1
        # Seven payload files, five directories, three slot files (no first error) and the slot.
        self.assertEqual(steps, 16)

    def test_empty_data_slot_left_by_a_cut_update_is_removed(self):
        fixture = self.fixture()
        b = self.archive(fixture, "B", b"B", "b" * 40)
        manager, paths = self.installed(fixture)
        _state_slot, data_slot = manager._update_paths(paths)
        data_slot.mkdir(mode=0o700)
        with self.assertRaises(manager.InstallError) as raised:
            self.update(manager, paths, b)
        self.assertEqual(raised.exception.code, "update_workspace_exists")
        self.assertEqual(manager.finalize_update(paths)["archiveSha256"], fixture[3])
        self.assertEqual(self.slots(manager, paths), (False, False))
        self.assertEqual(self.update(manager, paths, b)["archiveSha256"], b[1])

    def test_finalize_uninstall_then_a_new_archive_installs_the_running_manager(self):
        # The installed manager never changes in place; after finalize, uninstalling and
        # installing a new archive is the supported way to replace it with this one.
        fixture = self.fixture()
        b = self.archive(fixture, "B", b"B", "b" * 40)
        c = self.archive(fixture, "C", b"C", "d" * 40)
        manager, paths = self.installed(fixture)
        backend = service_fixtures.FakeServiceBackend(paths, fixture[3])
        self.assertEqual(manager.service(paths, "enable", backend=backend)["status"], "active")
        self.assertEqual(manager.service(paths, "disable", backend=backend)["status"], "disabled")
        self.update(manager, paths, b)
        # Finalize first: uninstall leaves a retained slot behind, and finalize needs a receipt.
        self.assertEqual(manager.finalize_update(paths)["archiveSha256"], b[1])
        self.assertEqual(manager.uninstall(paths)["status"], "uninstalled")
        receipts = manager._state(paths) / "receipts"
        self.assertEqual(sorted(p.stem for p in receipts.iterdir()), sorted([fixture[3], b[1]]))
        # History keeps every earlier archive out, but a new one installs beside it.
        for archive in ((fixture[2], fixture[3], "a" * 40), b):
            before = self.snapshot(fixture)
            with self.assertRaises(manager.InstallError) as raised:
                manager.install_archive(archive[0], expected_sha256=archive[1], expected_commit=archive[2], paths=paths)
            self.assertEqual(raised.exception.code, "install_history_exists")
            self.assertEqual(self.snapshot(fixture), before)
        self.assertEqual(manager.install_archive(c[0], expected_sha256=c[1], expected_commit=c[2], paths=paths)["archiveSha256"], c[1])
        installed = (manager._base(paths) / "tools/install.py").read_bytes()
        self.assertEqual(installed, (fixture[4] / "install.py").read_bytes())
        controller = (paths.home / ".local/bin/orla-launcherctl").read_text()
        self.assertIn(manager.hashlib.sha256(installed).hexdigest(), controller)
        backend = service_fixtures.FakeServiceBackend(paths, c[1])
        self.assertEqual(manager.service(paths, "enable", backend=backend)["status"], "active")
        unit = (paths.data_home / "systemd/user" / manager.SERVICE_UNIT).read_text()
        self.assertIn("After=graphical-session-pre.target plasma-kwin_wayland.service plasma-kwin_x11.service\n", unit)
        self.session(manager, paths, c[1])
        install_fixtures.InstallGuardTests.assert_userdata(self, fixture)


if __name__ == "__main__":
    unittest.main()
