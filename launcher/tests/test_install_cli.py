"""Bootstrap routing contract: installer is always a registered owned-path stub."""
import contextlib
import io
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

from scripts import caiodock


class LauncherInstallCliTests(unittest.TestCase):
    def invoke_stub(self, arguments, expected, *, code=0):
        module = types.ModuleType("orla_launcher_install_bootstrap")
        module.main = mock.Mock(return_value=code)
        loader = mock.Mock()
        spec = types.SimpleNamespace(name=module.__name__, loader=loader)

        def execute(loaded):
            self.assertIs(loaded, module)
            self.assertIs(sys.modules[spec.name], loaded)
            # The binding is main(list[str]), not a guessed cli(Namespace).
            self.assertFalse(hasattr(loaded, "cli"))

        loader.exec_module.side_effect = execute
        with mock.patch.dict(sys.modules), \
                mock.patch.object(caiodock.importlib.util, "spec_from_file_location", return_value=spec) as locate, \
                mock.patch.object(caiodock.importlib.util, "module_from_spec", return_value=module), \
                mock.patch.object(caiodock.subprocess, "run", side_effect=AssertionError("bootstrap must not spawn")), \
                mock.patch.object(Path, "cwd", side_effect=AssertionError("cwd is not a module source")):
            result = caiodock.main(arguments)
        locate.assert_called_once_with(spec.name, Path(caiodock.__file__).resolve().parents[1] / "launcher" / "install.py")
        loader.exec_module.assert_called_once_with(module)
        module.main.assert_called_once_with(expected)
        self.assertEqual(result, code)

    def test_install_forwards_one_explicit_argv_with_spaces_and_shell_text(self):
        archive = "/owned tree/archive $(not-a-command).zip"
        arguments = ["install", archive, "--sha256", "a" * 64, "--commit", "b" * 40]
        self.invoke_stub(["launcher", *arguments], arguments, code=7)

    def test_status_launch_uninstall_match_standalone_actions(self):
        for action in ("status", "launch", "uninstall"):
            with self.subTest(action=action):
                self.invoke_stub(["launcher", action], [action])

    def test_finish_install_recovery_forwards_the_explicit_mode(self):
        self.invoke_stub(["launcher", "recover", "--finish-install"],
                         ["recover", "--finish-install"], code=7)

    def test_parser_install_does_not_expand_archive_or_change_checksum(self):
        args = caiodock.parser().parse_args(["launcher", "install", "relative archive.zip", "--sha256", "raw-sha", "--commit", "raw-commit"])
        self.assertEqual(args.command, "launcher")
        self.assertEqual(args.launcher_action, "install")
        self.assertEqual(args.archive, Path("relative archive.zip"))
        self.assertEqual((args.sha256, args.commit), ("raw-sha", "raw-commit"))

    def test_invalid_launcher_arguments_refuse_before_loading_installer(self):
        bad = (["launcher"], ["launcher", "install", "archive.zip"],
               ["launcher", "install", "archive.zip", "--sha256", "a" * 64],
               ["launcher", "install", "archive.zip", "--commit", "b" * 40],
               ["launcher", "status", "--commit", "b" * 40], ["launcher", "update"],
               ["launcher", "recover"], ["launcher", "recover", "--rollback"])
        with mock.patch.object(caiodock.importlib.util, "spec_from_file_location") as locate:
            for arguments in bad:
                with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        caiodock.main(arguments)
                    self.assertEqual(raised.exception.code, 2)
        locate.assert_not_called()

    def test_loader_unavailable_reports_existing_cli_error_without_traceback(self):
        stderr = io.StringIO()
        with mock.patch.object(caiodock.importlib.util, "spec_from_file_location", return_value=None), contextlib.redirect_stderr(stderr):
            self.assertEqual(caiodock.main(["launcher", "status"]), 1)
        self.assertIn("orla: launcher installer could not be loaded", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_missing_installer_reports_filesystem_error_without_native_work(self):
        module = types.ModuleType("orla_launcher_install_bootstrap")
        loader = mock.Mock()
        loader.exec_module.side_effect = FileNotFoundError("owned installer missing")
        spec = types.SimpleNamespace(name=module.__name__, loader=loader)
        stderr = io.StringIO()
        with mock.patch.dict(sys.modules), \
                mock.patch.object(caiodock.importlib.util, "spec_from_file_location", return_value=spec), \
                mock.patch.object(caiodock.importlib.util, "module_from_spec", return_value=module), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(caiodock.main(["launcher", "status"]), 1)
        self.assertIn("orla: owned installer missing", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_existing_commands_never_load_installer_and_keep_their_backends(self):
        from scripts import panel_layout, search_shortcut
        with contextlib.ExitStack() as stack:
            locate = stack.enter_context(mock.patch.object(caiodock.importlib.util, "spec_from_file_location", side_effect=AssertionError("old command loaded installer")))
            project = stack.enter_context(mock.patch.object(caiodock, "project_root", return_value=Path("/owned/source")))
            build = stack.enter_context(mock.patch.object(caiodock, "build", return_value=Path("/owned/result.plasmoid")))
            install = stack.enter_context(mock.patch.object(caiodock, "install", return_value="--install"))
            uninstall = stack.enter_context(mock.patch.object(caiodock, "uninstall", return_value=True))
            doctor = stack.enter_context(mock.patch.object(caiodock, "doctor", return_value=9))
            preview = stack.enter_context(mock.patch.object(caiodock, "preview"))
            layout = stack.enter_context(mock.patch.object(panel_layout, "cli", return_value=5))
            shortcut = stack.enter_context(mock.patch.object(search_shortcut, "cli", return_value=6))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.assertEqual(caiodock.main(["build", "--project-root", "/owned/source", "--output-dir", "/owned/output"]), 0)
            build.assert_called_once_with(Path("/owned/source"), Path("/owned/output"))
            self.assertEqual(caiodock.main(["install", "/owned/widget.plasmoid", "--with-integrations"]), 0)
            install.assert_called_once_with(Path("/owned/widget.plasmoid"), None, with_integrations=True)
            self.assertEqual(caiodock.main(["uninstall"]), 0)
            uninstall.assert_called_once_with()
            self.assertEqual(caiodock.main(["doctor"]), 9)
            doctor.assert_called_once_with()
            self.assertEqual(caiodock.main(["preview", "--timeout", "2"]), 0)
            preview.assert_called_once_with(Path("/owned/source"), 2.0)
            self.assertEqual(caiodock.main(["layout", "status", "--service", "owned-plasma.service"]), 5)
            self.assertEqual(layout.call_args.args[0].layout_action, "status")
            self.assertEqual(caiodock.main(["search-shortcut", "status"]), 6)
            self.assertEqual(shortcut.call_args.args[0].action, "status")
            locate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
