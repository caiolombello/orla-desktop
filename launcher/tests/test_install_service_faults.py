"""Owned service fault guards; no real systemd, D-Bus or executable runs."""
import contextlib
import io
import json
import os
import stat
import unittest
from unittest import mock

import test_install_guards as fixtures
import test_install_service as service_fixtures


class ManagedServiceFaultTests(unittest.TestCase):
    def setUp(self):
        guards = contextlib.ExitStack()
        self.addCleanup(guards.close)
        for name in ("subprocess.Popen", "subprocess.run", "os.execv", "os.execve", "os.system"):
            guards.enter_context(mock.patch(name, side_effect=AssertionError("real native/process forbidden: " + name)))

    def installed(self):
        fixture = fixtures.InstallGuardTests.fixture(self)
        fixtures.InstallGuardTests.install(self, fixture)
        return fixture, service_fixtures.FakeServiceBackend(fixture[1], fixture[3])

    def protected(self, fixture):
        _root, paths, _archive, digest, _bundle, manager, _userdata = fixture
        state = paths.state_home / "orla/launcher-install"
        selected = [path for path, _mode in manager._files(paths, digest).values()] + [
            state / "current.json", state / "receipts" / (digest + ".json"),
            state / "transactions" / (digest + "-install.json"),
            state / "transactions" / (digest + "-installed.json")]
        selected.extend(fixture[-1])
        return {str(path): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode),
                            manager._identity(path.stat())) for path in selected}

    def marker(self, fixture):
        return fixture[1].data_home / "orla-desktop/launcher/service.json"

    def failure(self, fixture):
        record = json.loads(self.marker(fixture).read_bytes())
        return fixture[1].state_home / "orla/launcher-install/transactions" / (
            "service-" + record["token"] + "-error.json")

    def test_different_caller_generation_refuses_before_service_publication(self):
        fixture, backend = self.installed()
        manager, paths = fixture[5], fixture[1]
        # The installed immutable tools retain A; the owned caller now has B bytes.
        caller = fixture[4] / "install.py"
        caller.write_bytes(caller.read_bytes() + b"\n# owned newer caller generation\n")
        before = fixtures.InstallGuardTests.snapshot(self, paths.home)
        with self.assertRaises(manager.InstallError) as raised:
            manager.service(paths, "enable", backend=backend)
        self.assertEqual(raised.exception.code, "service_generation")
        self.assertEqual(fixtures.InstallGuardTests.snapshot(self, paths.home), before)
        self.assertFalse(self.marker(fixture).exists())
        self.assertEqual(backend.events, [])

    def test_foreign_preflight_state_is_preserved_without_start_or_barrier(self):
        for case in ("unit", "link", "owner", "load_path", "loaded"):
            with self.subTest(case=case):
                fixture, backend = self.installed()
                manager, paths = fixture[5], fixture[1]
                if case == "unit":
                    backend.unit.parent.mkdir(parents=True, exist_ok=True)
                    backend.unit.write_bytes(b"owned foreign unit\n")
                elif case == "link":
                    backend.link.parent.mkdir(parents=True, exist_ok=True)
                    backend.link.symlink_to(backend.unit.parent / "foreign.service")
                elif case == "owner":
                    backend.owner_pid = lambda: 4321
                elif case == "load_path":
                    backend.paths = lambda: [str(fixture[0] / "other service path")]
                else:
                    backend.loaded = True
                before = fixtures.InstallGuardTests.snapshot(self, paths.home)
                with self.assertRaises(manager.InstallError):
                    manager.service(paths, "enable", backend=backend)
                self.assertFalse(self.marker(fixture).exists())
                self.assertEqual(backend.events, [])
                self.assertEqual(fixtures.InstallGuardTests.snapshot(self, paths.home), before)
                fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_start_error_retains_first_cause_and_unknown_process_requires_explicit_retry(self):
        for unknown in (False, True):
            with self.subTest(unknown_process=unknown):
                fixture, backend = self.installed()
                manager, paths = fixture[5], fixture[1]
                protected = self.protected(fixture)
                original_start, original_snapshot = backend.start, backend.snapshot
                def start_then_fail():
                    original_start()
                    raise manager.InstallError("write_failed")
                backend.start = start_then_fail
                with self.assertRaises(manager.InstallError) as raised:
                    manager.service(paths, "enable", backend=backend)
                self.assertEqual(raised.exception.code, "write_failed")
                first = self.failure(fixture).read_bytes()
                self.assertEqual(json.loads(first)["code"], "write_failed")
                self.assertTrue(backend.running)
                self.assertNotIn("stop", backend.events)
                self.assertTrue(self.marker(fixture).is_file())
                if unknown:
                    def unknown_snapshot():
                        value = original_snapshot()
                        value["process"]["busPid"] = 4321
                        return value
                    backend.snapshot = unknown_snapshot
                    with self.assertRaises(manager.InstallError):
                        manager.service(paths, "disable", backend=backend)
                    self.assertNotIn("stop", backend.events)
                    self.assertTrue(self.marker(fixture).is_file())
                    self.assertTrue(backend.unit.is_file())
                    self.assertTrue(backend.link.is_symlink())
                    backend.snapshot = original_snapshot
                self.assertEqual(self.failure(fixture).read_bytes(), first)
                report = manager.service(paths, "disable", backend=backend)
                self.assertEqual(report["status"], "disabled")
                self.assertFalse(self.marker(fixture).exists())
                self.assertFalse(backend.running)
                self.assertEqual(self.protected(fixture), protected)
                # Audit remains immutable even after successful explicit cleanup.
                audits = list((paths.state_home / "orla/launcher-install/transactions").glob("service-*-error.json"))
                self.assertEqual([path.read_bytes() for path in audits], [first])

    def test_stop_error_or_delayed_stop_keeps_barrier_until_retry(self):
        for case in ("error", "still_running"):
            with self.subTest(case=case):
                fixture, backend = self.installed()
                manager, paths = fixture[5], fixture[1]
                protected = self.protected(fixture)
                manager.service(paths, "enable", backend=backend)
                original_stop = backend.stop
                def refuse_stop():
                    backend.events.append("stop-refused")
                    if case == "error":
                        raise manager.InstallError("write_failed")
                backend.stop = refuse_stop
                with self.assertRaises(manager.InstallError) as raised:
                    manager.service(paths, "disable", backend=backend)
                self.assertEqual(raised.exception.code, "write_failed" if case == "error" else "service_stop_unknown")
                first_path = self.failure(fixture)
                first = first_path.read_bytes()
                self.assertEqual(json.loads(first)["code"], raised.exception.code)
                self.assertTrue(self.marker(fixture).is_file())
                self.assertTrue(backend.unit.is_file())
                self.assertTrue(backend.link.is_symlink())
                self.assertTrue(backend.running)
                backend.stop = original_stop
                self.assertEqual(manager.service(paths, "disable", backend=backend)["status"], "disabled")
                self.assertFalse(self.marker(fixture).exists())
                self.assertEqual(first_path.read_bytes(), first)
                self.assertEqual(self.protected(fixture), protected)

    def test_live_service_blocks_all_managed_payload_mutations(self):
        fixture, backend = self.installed()
        manager, paths, archive, digest = fixture[5], fixture[1], fixture[2], fixture[3]
        manager.service(paths, "enable", backend=backend)
        operations = {
            "install": lambda: manager.install_archive(archive, expected_sha256=digest, expected_commit="a" * 40, paths=paths),
            "update": lambda: manager.update_archive(archive, expected_sha256=digest, expected_commit="a" * 40, paths=paths),
            "rollback": lambda: manager.rollback_update(paths),
            "recover_update": lambda: manager.recover_update(paths),
            "recover_install": lambda: manager.recover_finish_install(paths),
            "uninstall": lambda: manager.uninstall(paths),
        }
        before = fixtures.InstallGuardTests.snapshot(self, paths.home)
        for name, operation in operations.items():
            with self.subTest(operation=name):
                with self.assertRaises(manager.InstallError) as raised:
                    operation()
                self.assertEqual(raised.exception.code, "service_disable_first")
                self.assertEqual(fixtures.InstallGuardTests.snapshot(self, paths.home), before)
                self.assertTrue(backend.running)
                self.assertNotIn("stop", backend.events)

    def test_marker_or_unit_or_link_drift_refuses_stop_and_delete(self):
        for case in ("marker", "unit", "link"):
            with self.subTest(case=case):
                fixture, backend = self.installed()
                manager, paths = fixture[5], fixture[1]
                protected = self.protected(fixture)
                manager.service(paths, "enable", backend=backend)
                if case == "marker":
                    record = json.loads(self.marker(fixture).read_bytes())
                    record["token"] = "f" * 32
                    self.marker(fixture).write_text(json.dumps(record))
                elif case == "unit":
                    backend.unit.write_bytes(backend.unit.read_bytes() + b"# drift\n")
                else:
                    backend.link.unlink()
                    backend.link.symlink_to(backend.unit.parent / "foreign.service")
                observed = (self.marker(fixture).read_bytes(), backend.unit.read_bytes(), os.readlink(backend.link))
                with mock.patch("os.unlink", side_effect=AssertionError("drift cannot delete files")):
                    with self.assertRaises(manager.InstallError):
                        manager.service(paths, "disable", backend=backend)
                self.assertEqual((self.marker(fixture).read_bytes(), backend.unit.read_bytes(), os.readlink(backend.link)), observed)
                self.assertTrue(backend.running)
                self.assertNotIn("stop", backend.events)
                self.assertEqual(self.protected(fixture), protected)

    def test_disabled_reads_and_invalid_service_arguments_have_no_effects(self):
        fixture, backend = self.installed()
        manager, paths = fixture[5], fixture[1]
        before = fixtures.InstallGuardTests.snapshot(self, paths.home)
        for action in ("status", "disable", "status"):
            report = manager.service(paths, action, backend=backend)
            self.assertEqual(report["status"], "disabled")
            self.assertIs(report["enabled"], False)
            self.assertEqual(fixtures.InstallGuardTests.snapshot(self, paths.home), before)
            self.assertEqual(backend.events, [])
        with mock.patch.object(manager, "NativeServiceBackend", side_effect=AssertionError("invalid CLI cannot construct backend"), create=True):
            for arguments in (["service"], ["service", "start"], ["service", "enable", "--force"], ["service", "status", "extra"]):
                with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        manager.main(arguments)
                    self.assertEqual(raised.exception.code, 2)
                    self.assertEqual(fixtures.InstallGuardTests.snapshot(self, paths.home), before)


if __name__ == "__main__":
    unittest.main()
