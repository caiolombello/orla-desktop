"""Owned causal service preflight/lock race; Root alone executes."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from unittest import mock

import test_install_guards as fixtures
import test_install_service as service_fixtures


class ManagedServiceLockRaceTests(unittest.TestCase):
    def test_service_enable_between_uninstall_preflight_and_lock_refuses_mutation(self):
        fixture = fixtures.InstallGuardTests.fixture(self)
        manager, paths = fixture[5], fixture[1]
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no install process")):
            fixtures.InstallGuardTests.install(self, fixture)
        backend = service_fixtures.FakeServiceBackend(paths, fixture[3])
        original_lock = manager._locked
        fired, post_enable = [], []

        @contextlib.contextmanager
        def enable_before_lock(selected, *args, **kwargs):
            if not fired:
                fired.append(True)
                # Enable completes under the actual original lock before the
                # uninstall caller acquires it; no thread or IPC is needed.
                with mock.patch.object(manager, "_locked", original_lock):
                    enabled = manager.service(paths, "enable", backend=backend)
                self.assertEqual(enabled["status"], "active")
                post_enable.append(fixtures.InstallGuardTests.snapshot(self, paths.home))
            with original_lock(selected, *args, **kwargs) as token:
                yield token

        with contextlib.ExitStack() as guards:
            for name in ("subprocess.Popen", "subprocess.run", "os.execv", "os.execve", "os.system"):
                guards.enter_context(mock.patch(name, side_effect=AssertionError("real native/process forbidden: " + name)))
            guards.enter_context(mock.patch.object(manager, "_locked", side_effect=enable_before_lock))
            with self.assertRaises(manager.InstallError) as raised:
                manager.uninstall(paths)
        self.assertEqual(fired, [True])
        self.assertEqual(raised.exception.code, "service_disable_first")
        self.assertEqual(len(post_enable), 1)
        self.assertEqual(fixtures.InstallGuardTests.snapshot(self, paths.home), post_enable[0])
        self.assertTrue(backend.running)
        self.assertNotIn("stop", backend.events)
        fixtures.InstallGuardTests.assert_userdata(self, fixture)


class ManagedServicePartialEnableTests(unittest.TestCase):
    def test_public_cycle_accepts_owned_data_link_omitted_by_manager_enumeration(self):
        fixture = fixtures.InstallGuardTests.fixture(self)
        manager, paths = fixture[5], fixture[1]
        fixtures.InstallGuardTests.install(self, fixture)

        class DataLinkBackend(service_fixtures.FakeServiceBackend):
            def snapshot(self):
                value = super().snapshot()
                # systemd 259 enumerates disable's config links, while the
                # loaded unit's Wants dependency also uses the data directory.
                value["links"] = []
                return value

        backend = DataLinkBackend(paths, fixture[3])
        with contextlib.ExitStack() as guards:
            guards.enter_context(mock.patch.object(manager, "NativeServiceBackend", return_value=backend))
            for name in ("subprocess.Popen", "subprocess.run", "os.execv", "os.execve", "os.system"):
                guards.enter_context(mock.patch(name, side_effect=AssertionError("no real native/process: " + name)))
            for action, status in (("enable", "active"), ("status", "active"), ("disable", "disabled")):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = manager.main(["--home", str(paths.home), "--data-home", str(paths.data_home),
                                         "--state-home", str(paths.state_home), "service", action])
                self.assertEqual(code, 0, output.getvalue())
                self.assertEqual(json.loads(output.getvalue())["status"], status)
        self.assertEqual(backend.events.count("start"), 1)
        self.assertEqual(backend.events.count("stop"), 1)
        self.assertFalse(backend.unit.exists())
        self.assertFalse(backend.link.is_symlink())
        fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_unenumerated_link_is_revalidated_after_reload_before_start(self):
        for change in ("remove", "retarget"):
            with self.subTest(change=change):
                fixture = fixtures.InstallGuardTests.fixture(self)
                manager, paths = fixture[5], fixture[1]
                fixtures.InstallGuardTests.install(self, fixture)

                class ChangedLinkBackend(service_fixtures.FakeServiceBackend):
                    def snapshot(self):
                        value = super().snapshot()
                        value["links"] = []
                        return value

                    def reload(self):
                        super().reload()
                        self.link.unlink()
                        if change == "retarget":
                            self.link.symlink_to(self.unit.parent / "foreign.service")

                backend = ChangedLinkBackend(paths, fixture[3])
                with self.assertRaises(manager.InstallError) as raised:
                    manager.service(paths, "enable", backend=backend)
                self.assertEqual(raised.exception.code, "service_drift")
                self.assertNotIn("start", backend.events)
                self.assertFalse(backend.running)
                fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_failed_start_with_no_pid_is_stopped_before_removing_its_unit(self):
        fixture = fixtures.InstallGuardTests.fixture(self)
        manager, paths = fixture[5], fixture[1]
        fixtures.InstallGuardTests.install(self, fixture)

        class FailedBackend(service_fixtures.FakeServiceBackend):
            failed = False

            def start(self):
                self.events.append("start")
                self.failed = True
                raise manager.InstallError("service_start_failed")

            def snapshot(self):
                value = super().snapshot()
                if self.failed:
                    if not self.loaded:
                        raise manager.InstallError("service_unknown")
                    value.update(active="failed", sub="failed")
                return value

            def stop(self):
                super().stop()
                self.failed = False

        backend = FailedBackend(paths, fixture[3])
        with self.assertRaises(manager.InstallError):
            manager.service(paths, "enable", backend=backend)
        result = manager.service(paths, "disable", backend=backend)
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(backend.events.count("stop"), 1)
        self.assertFalse((paths.data_home / "orla-desktop/launcher/service.json").exists())
        self.assertFalse(backend.unit.exists())
        self.assertFalse(backend.link.is_symlink())
        fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_failed_first_reload_can_disable_its_not_found_unit_and_owned_link(self):
        fixture = fixtures.InstallGuardTests.fixture(self)
        manager, paths = fixture[5], fixture[1]
        fixtures.InstallGuardTests.install(self, fixture)
        backend = service_fixtures.FakeServiceBackend(paths, fixture[3])
        reload_original = backend.reload
        fired = []

        def fail_first_reload():
            if not fired:
                fired.append(True)
                raise manager.InstallError("service_reload_failed")
            reload_original()

        with mock.patch.object(backend, "reload", side_effect=fail_first_reload):
            with self.assertRaises(manager.InstallError) as raised:
                manager.service(paths, "enable", backend=backend)
            self.assertEqual(raised.exception.code, "service_reload_failed")
            self.assertFalse(backend.loaded)
            self.assertTrue(backend.link.is_symlink())
            marker = paths.data_home / "orla-desktop/launcher/service.json"
            self.assertTrue(marker.is_file())
            status = manager.service(paths, "status", backend=backend)
            self.assertEqual(status["status"], "pending")
            self.assertIsNone(status["enabled"])
            result = manager.service(paths, "disable", backend=backend)
        self.assertEqual(result["status"], "disabled")
        self.assertFalse(marker.exists())
        self.assertFalse(backend.unit.exists())
        self.assertFalse(backend.link.is_symlink())
        self.assertNotIn("start", backend.events)
        self.assertNotIn("stop", backend.events)
        fixtures.InstallGuardTests.assert_userdata(self, fixture)


class ManagedServiceBackendTests(unittest.TestCase):
    def test_stop_resets_only_its_failed_unit_after_zero_pid_confirmation(self):
        fixture = fixtures.InstallGuardTests.fixture(self)
        manager = fixture[5]
        state = ["failed"]
        mutations = []

        def reply(argv, **kwargs):
            kind = argv[5]
            if kind == "get-property":
                name = argv[-1]
                signature, data = ("u", 0) if name == "MainPID" else ("ay", [1] * 16)
            else:
                member = argv[9]
                if member == "GetNameOwner":
                    signature, data = "s", [":1.2"]
                elif member == "ListUnitsByNames":
                    row = [service_fixtures.UNIT, "Orla", "loaded", state[0], state[0], "",
                           "/org/freedesktop/systemd1/unit/own", 0, "", "/"]
                    signature, data = "a(ssssssouso)", [[row]]
                elif member == "StopUnit":
                    mutations.append((member, argv[11:]))
                    signature, data = "o", ["/org/freedesktop/systemd1/job/1"]
                elif member == "ResetFailedUnit":
                    mutations.append((member, argv[11:]))
                    state[0] = "inactive"
                    signature, data = "", []
                else:
                    raise AssertionError("unexpected native method: " + member)
            return subprocess.CompletedProcess(argv, 0, json.dumps({"type": signature, "data": data}).encode(), b"")

        with mock.patch.object(manager.shutil, "which", return_value=sys.executable), \
                mock.patch.object(manager.subprocess, "run", side_effect=reply):
            backend = manager.NativeServiceBackend()
            backend.stop()
        self.assertEqual(state, ["inactive"])
        self.assertEqual(mutations, [("StopUnit", [service_fixtures.UNIT, "fail"]),
                                     ("ResetFailedUnit", [service_fixtures.UNIT])])


if __name__ == "__main__":
    unittest.main()
