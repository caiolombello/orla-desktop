"""Public installed-session routing; exec is captured, never ELF/IPC/native IO."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest import mock

import test_install_guards as fixtures
import test_install_update_guards as update_fixtures


class InstalledSessionTests(unittest.TestCase):
    def setUp(self):
        for target in ("subprocess.Popen", "subprocess.run", "os.execve", "os.system"):
            guard = mock.patch(target, side_effect=AssertionError("unexpected process/IPC path: " + target))
            guard.start()
            self.addCleanup(guard.stop)

    def fixture(self):
        return fixtures.InstallGuardTests.fixture(self)

    def install(self, fixture):
        return fixtures.InstallGuardTests.install(self, fixture)

    def snapshot(self, fixture):
        return fixtures.InstallGuardTests.snapshot(self, fixture[1].home)

    def state(self, fixture):
        return update_fixtures.ManagedUpdateGuardTests.state(self, fixture)

    def invoke(self, fixture, action, *arguments):
        manager, paths = fixture[5], fixture[1]
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), \
             mock.patch.object(manager.os, "execv") as execute:
            try:
                code = manager.main(["--home", str(paths.home), "--data-home", str(paths.data_home),
                                     "--state-home", str(paths.state_home), action, *arguments])
            except SystemExit as error:
                code = error.code
        return code, output.getvalue(), errors.getvalue(), execute

    def binary(self, fixture, digest):
        return str(fixture[1].data_home / "orla-desktop/launcher/versions" / digest / "bin/orla-launcher")

    def test_source_absent_session_executes_selected_binary_with_fixed_managed_arguments(self):
        fixture = self.fixture()
        self.install(fixture)
        fixtures.InstallGuardTests.hide_source(self, fixture)
        before = self.snapshot(fixture)
        code, output, errors, execute = self.invoke(fixture, "session")
        # Baseline causal RED: public session is absent, argparse exits2.
        self.assertEqual(code, 0, errors + output)
        binary = self.binary(fixture, fixture[3])
        execute.assert_called_once_with(binary, [binary, "--managed-shortcuts", "--start-hidden"])
        self.assertEqual(output, "")
        self.assertEqual(errors, "")
        self.assertEqual(self.snapshot(fixture), before)
        fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_pending_or_managed_drift_refuses_session_before_exec(self):
        for condition in ("pending", "drift"):
            with self.subTest(condition=condition):
                fixture = self.fixture()
                manager = fixture[5]
                if condition == "pending":
                    original = manager._unlink_checked
                    fired = []
                    def fail(path, record, mode, *args, **kwargs):
                        if Path(path).name == "pending-intent.json" and not fired:
                            fired.append(True)
                            raise manager.InstallError("write_failed")
                        return original(path, record, mode, *args, **kwargs)
                    with mock.patch.object(manager, "_unlink_checked", side_effect=fail):
                        with self.assertRaises(manager.InstallError): self.install(fixture)
                    self.assertEqual(fired, [True])
                    self.assertEqual(manager.status(fixture[1])["status"], "pending")
                    expected = "pending_transaction"
                else:
                    self.install(fixture)
                    target = Path(self.binary(fixture, fixture[3]))
                    target.write_bytes(target.read_bytes() + b"owned managed drift\n")
                    expected = "managed_drift"
                before = self.snapshot(fixture)
                code, output, errors, execute = self.invoke(fixture, "session")
                self.assertEqual(code, 2, errors + output)
                self.assertEqual(json.loads(output), {"status": "error", "code": expected})
                self.assertEqual(errors, "")
                execute.assert_not_called()
                self.assertEqual(self.snapshot(fixture), before)
                fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_launch_retains_its_existing_one_shot_argument(self):
        fixture = self.fixture()
        self.install(fixture)
        fixtures.InstallGuardTests.hide_source(self, fixture)
        before = self.snapshot(fixture)
        code, output, errors, execute = self.invoke(fixture, "launch")
        self.assertEqual(code, 0, errors + output)
        binary = self.binary(fixture, fixture[3])
        execute.assert_called_once_with(binary, [binary, "--no-global-shortcut"])
        self.assertEqual((output, errors), ("", ""))
        self.assertEqual(self.snapshot(fixture), before)

    def test_session_uses_b_after_update_and_a_after_rollback_without_replacing_tools(self):
        fixture, archive, digest = update_fixtures.ManagedUpdateGuardTests.fixture(self)
        manager = fixture[5]
        protected = update_fixtures.ManagedUpdateGuardTests.protected(self, fixture)
        manager.update_archive(archive, expected_sha256=digest, expected_commit="b" * 40, paths=fixture[1])
        for selected in (digest, fixture[3]):
            with self.subTest(selected=selected):
                if selected == fixture[3]: manager.rollback_update(fixture[1])
                self.assertEqual(manager.status(fixture[1])["archiveSha256"], selected)
                before = self.snapshot(fixture)
                code, output, errors, execute = self.invoke(fixture, "session")
                self.assertEqual(code, 0, errors + output)
                binary = self.binary(fixture, selected)
                execute.assert_called_once_with(binary, [binary, "--managed-shortcuts", "--start-hidden"])
                self.assertEqual((output, errors), ("", ""))
                self.assertEqual(self.snapshot(fixture), before)
                self.assertEqual(update_fixtures.ManagedUpdateGuardTests.protected(self, fixture), protected)
        fixtures.InstallGuardTests.assert_userdata(self, fixture)

    def test_session_accepts_no_free_arguments_or_caller_shortcut_flags(self):
        fixture = self.fixture()
        self.install(fixture)
        before = self.snapshot(fixture)
        for arguments in (("extra",), ("--managed-shortcuts",), ("--start-hidden",), ("--no-global-shortcut",)):
            with self.subTest(arguments=arguments):
                code, output, errors, execute = self.invoke(fixture, "session", *arguments)
                self.assertEqual(code, 2)
                self.assertEqual(output, "")
                self.assertTrue(errors)
                execute.assert_not_called()
                self.assertEqual(self.snapshot(fixture), before)


if __name__ == "__main__":
    unittest.main()
