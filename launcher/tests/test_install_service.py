"""One public owned service tracer. No real systemd, D-Bus or executable runs."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import unittest
from unittest import mock

import test_install_guards as fixtures


UNIT = "orla-launcher-managed.service"


class FakeServiceBackend:
    def __init__(self, paths, digest):
        self.install_paths = paths
        self.unit = paths.data_home / "systemd/user" / UNIT
        self.link = self.unit.parent / "graphical-session.target.wants" / UNIT
        self.controller = paths.home / ".local/bin/orla-launcherctl"
        self.binary = paths.data_home / "orla-desktop/launcher/versions" / digest / "bin/orla-launcher"
        self.loaded = False
        self.running = False
        self.events = []

    def paths(self):
        return [str(self.unit.parent)]

    def owner_pid(self):
        return 1234 if self.running else None

    def snapshot(self):
        pid = 1234 if self.running else 0
        loaded = self.loaded
        environment = ["HOME=" + str(self.install_paths.home),
                       "XDG_DATA_HOME=" + str(self.install_paths.data_home),
                       "XDG_STATE_HOME=" + str(self.install_paths.state_home)]
        process = {"pid": pid, "uid": os.getuid(), "exe": str(self.binary),
                   "sha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(), "tick": 1,
                   "busPid": pid} if self.running else None
        return {"id": UNIT, "names": [UNIT] if loaded else [], "load": "loaded" if loaded else "not-found",
                "active": "active" if self.running else "inactive", "sub": "running" if self.running else "dead",
                "fragment": str(self.unit) if loaded else "", "dropins": [], "transient": False,
                "invocation": "1" * 32 if self.running else "", "pid": pid,
                "type": "dbus" if loaded else "", "bus": "org.orla.Launcher" if loaded else "",
                "restart": "no" if loaded else "", "exec": [["/bin/sh", ["/bin/sh", str(self.controller), "session"], False]] if loaded else [],
                "aux": False, "environment": environment if loaded else [], "environmentFiles": [],
                "links": [str(self.link)] if self.link.is_symlink() else [], "process": process}

    def reload(self):
        self.events.append("reload")
        self.loaded = self.unit.is_file()

    def start(self):
        if not self.loaded or not self.unit.is_file() or not self.link.is_symlink():
            raise AssertionError("fake service start requires published unit/link and reload")
        self.events.append("start")
        self.running = True

    def stop(self):
        self.events.append("stop")
        self.running = False


class ManagedServiceTracerTests(unittest.TestCase):
    def test_public_enable_status_disable_preserves_managed_payload_and_userdata(self):
        fixture = fixtures.InstallGuardTests.fixture(self)
        manager, paths, digest = fixture[5], fixture[1], fixture[3]
        with mock.patch("subprocess.Popen", side_effect=AssertionError("install cannot run programs")):
            fixtures.InstallGuardTests.install(self, fixture)
        backend = FakeServiceBackend(paths, digest)
        state = paths.state_home / "orla/launcher-install"
        service_record = paths.data_home / "orla-desktop/launcher/service.json"
        protected_paths = [path for path, _mode in manager._files(paths, digest).values()] + [
            state / "current.json", state / "receipts" / (digest + ".json"),
            state / "transactions" / (digest + "-install.json"),
            state / "transactions" / (digest + "-installed.json")]
        def frozen():
            return {str(path): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode), manager._identity(path.stat()))
                    for path in protected_paths}
        original = frozen()

        def public(action):
            output, errors = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                try:
                    code = manager.main(["--home", str(paths.home), "--data-home", str(paths.data_home),
                                         "--state-home", str(paths.state_home), "service", action])
                except SystemExit as error:
                    code = error.code
            self.assertEqual(code, 0, "public service absent or failed: " + errors.getvalue() + output.getvalue())
            self.assertEqual(errors.getvalue(), "")
            return json.loads(output.getvalue())

        with contextlib.ExitStack() as guards:
            guards.enter_context(mock.patch.object(manager, "NativeServiceBackend", return_value=backend, create=True))
            for name in ("subprocess.Popen", "subprocess.run", "os.execv", "os.execve", "os.system"):
                guards.enter_context(mock.patch(name, side_effect=AssertionError("real native/process operation forbidden: " + name)))
            # Baseline causal RED is the missing public service parser/entrypoint.
            enabled = public("enable")
            for report in (enabled, public("status")):
                self.assertEqual(report["status"], "active")
                self.assertIs(report["enabled"], True)
                self.assertEqual(report["unit"], UNIT)
                self.assertEqual(report["runtime"], "unverified")
            self.assertTrue(backend.unit.is_file())
            self.assertEqual(stat.S_IMODE(backend.unit.stat().st_mode), 0o644)
            self.assertTrue(backend.link.is_symlink())
            self.assertEqual(os.readlink(backend.link), str(backend.unit))
            unit_text = backend.unit.read_text(encoding="utf-8")
            self.assertIn("orla-launcherctl", unit_text)
            self.assertIn("session", unit_text)
            self.assertNotIn("/versions/", unit_text)
            self.assertIn("PartOf=graphical-session.target", unit_text)
            self.assertIn("After=graphical-session-pre.target", unit_text)
            self.assertIn("WantedBy=graphical-session.target", unit_text)
            self.assertNotIn("After=graphical-session.target\n", unit_text)
            self.assertTrue(service_record.is_file())
            self.assertEqual(frozen(), original)
            fixtures.InstallGuardTests.assert_userdata(self, fixture)

            disabled = public("disable")
            self.assertEqual(disabled["status"], "disabled")
            self.assertIs(disabled["enabled"], False)
            self.assertEqual(disabled["unit"], UNIT)
            self.assertEqual(disabled["runtime"], "unverified")
            self.assertFalse(backend.running)
            self.assertFalse(backend.unit.exists())
            self.assertFalse(backend.link.is_symlink())
            self.assertFalse(service_record.exists())
            self.assertEqual(backend.events.count("start"), 1)
            self.assertEqual(backend.events.count("stop"), 1)
            self.assertIn("reload", backend.events)
            self.assertEqual(frozen(), original)
            fixtures.InstallGuardTests.assert_userdata(self, fixture)
            settled = fixtures.InstallGuardTests.snapshot(self, paths.home)
            status = public("status")
            self.assertEqual(status["status"], "disabled")
            self.assertIs(status["enabled"], False)
            self.assertEqual(status["unit"], UNIT)
            self.assertEqual(status["runtime"], "unverified")
            self.assertEqual(fixtures.InstallGuardTests.snapshot(self, paths.home), settled)
            self.assertEqual(frozen(), original)


if __name__ == "__main__":
    unittest.main()
