import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

from scripts import caiodock


class PackageCliTests(unittest.TestCase):
    def test_optional_composition_help_does_not_import_qt_or_touch_layout(self):
        args = caiodock.parser().parse_args(["layout", "setup", "--service", "plasma-fixture.service"])
        self.assertEqual(args.layout_action, "setup")
        self.assertEqual(args.service, "plasma-fixture.service")

    def test_composition_entry_forwards_explicit_service_without_constructing_native_runtime(self):
        from types import SimpleNamespace
        import scripts
        from scripts import panel_layout
        launch = mock.Mock(return_value=0)
        module = SimpleNamespace(launch=launch)
        with mock.patch.object(scripts, "workspace_setup", module, create=True), \
                mock.patch.dict(sys.modules, {"scripts.workspace_setup": module}), \
                mock.patch.object(panel_layout, "NativeRuntime", side_effect=AssertionError("must remain lazy")):
            self.assertEqual(caiodock.main(["layout", "setup", "--service", "plasma-fixture.service"]), 0)
        launch.assert_called_once_with("plasma-fixture.service")

    def test_composition_incomplete_kit_refuses_before_qt_or_native_startup(self):
        from scripts import panel_layout
        error = io.StringIO()
        with mock.patch.object(panel_layout, "__file__", str(self.root / "scripts/panel_layout.py")), \
                mock.patch.object(panel_layout, "NativeRuntime", side_effect=AssertionError("must remain inert")), \
                contextlib.redirect_stderr(error):
            self.assertEqual(caiodock.main(["layout", "setup", "--service", "plasma-fixture.service"]), 1)
        self.assertIn("complete source checkout", error.getvalue())

    def test_script_and_module_entrypoints_show_layout_help(self):
        import subprocess
        import sys
        source = Path(__file__).resolve().parents[1]
        for entry in ([sys.executable, "-B", "scripts/orla.py"],
                      [sys.executable, "-B", "-m", "scripts.orla"]):
            with self.subTest(entry=entry):
                result = subprocess.run(entry + ["layout", "--help"], cwd=source,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("restore", result.stdout)

    def test_updates_source_dispatch_is_lazy_and_forwards_root(self):
        from types import SimpleNamespace
        import scripts
        launch = mock.Mock(return_value=0)
        module=SimpleNamespace(launch=launch)
        with mock.patch.object(scripts, 'updates_desktop', module, create=True), mock.patch.dict(sys.modules, {'scripts.updates_desktop':module}):
            self.assertEqual(caiodock.main(['updates','desktop']),0)
        launch.assert_called_once_with(Path(caiodock.__file__).resolve().parents[1])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        package = self.root / "package"
        (package / "contents/ui").mkdir(parents=True)
        (package / "metadata.json").write_text(json.dumps({"KPlugin": {"Id": caiodock.PACKAGE_ID, "Version": "1.2.3"}}))
        (package / "contents/ui/main.qml").write_text("Item {}")
        (package / "contents/code").mkdir(parents=True)
        (package / "contents/code/integrations.py").write_text("# bridge")
        (package / "contents/ui/theme.qml").write_text("// theme")
        (self.root / "LICENSE").write_text("MIT license")
        (self.root / "scripts/private.py").parent.mkdir()
        (self.root / "scripts/private.py").write_text("secret")
        (self.root / "package/private-root.txt").write_text("must not ship")

    def tearDown(self):
        self.temporary.cleanup()

    def test_build_has_package_root_and_only_runtime_files(self):
        archive_path = caiodock.build(self.root)
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, {"metadata.json", "LICENSE", "contents/ui/main.qml", "contents/ui/theme.qml", "contents/code/integrations.py"})
            self.assertEqual(archive.read("LICENSE"), b"MIT license")
            self.assertEqual(json.loads(archive.read("metadata.json"))["KPlugin"]["Id"], caiodock.PACKAGE_ID)

    def test_build_ignores_symlinks_and_rejects_missing_entrypoint(self):
        (self.root / "package/contents/ui/link.qml").symlink_to(self.root / "scripts/private.py")
        archive_path = caiodock.build(self.root)
        with zipfile.ZipFile(archive_path) as archive:
            self.assertNotIn("contents/ui/link.qml", archive.namelist())
            self.assertNotIn("private-root.txt", archive.namelist())
        (self.root / "package/contents/ui/main.qml").unlink()
        with self.assertRaises(caiodock.PackageError):
            caiodock.build(self.root)

    def test_build_excludes_python_bytecode(self):
        cache = self.root / "package/contents/code/__pycache__"
        cache.mkdir(parents=True)
        (cache / "integrations.cpython-314.pyc").write_bytes(b"bytecode")
        (cache.parent / "stray.pyc").write_bytes(b"bytecode")
        with zipfile.ZipFile(caiodock.build(self.root)) as archive:
            self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in archive.namelist()))

    def test_build_is_byte_for_byte_deterministic(self):
        first = caiodock.build(self.root, self.root).read_bytes()
        source = self.root / "package/contents/ui/main.qml"
        timestamp = time.time() + 3600
        os.utime(source, (timestamp, timestamp))
        second = caiodock.build(self.root, self.root).read_bytes()
        self.assertEqual(first, second)

    def test_cli_build_output_directory_preserves_readonly_source_and_user_state(self):
        source = Path(__file__).resolve().parents[1]
        for name in ("orla.py", "caiodock.py", "panel_layout.py", "search_shortcut.py"):
            shutil.copyfile(source / "scripts" / name, self.root / "scripts" / name)

        def snapshot(root):
            return {str(path.relative_to(root)): (path.stat().st_mode, path.stat().st_mtime_ns,
                    path.read_bytes() if path.is_file() else None)
                    for path in [root, *root.rglob("*")]}

        paths = [self.root, *self.root.rglob("*")]
        for path in paths:
            path.chmod(0o555 if path.is_dir() else 0o444)
        before_source = snapshot(self.root)
        try:
            with tempfile.TemporaryDirectory() as temporary:
                workspace = Path(temporary)
                env = os.environ.copy()
                for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE"):
                    env.pop(key, None)
                xdg_keys = ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR")
                for key in xdg_keys:
                    directory = workspace / key
                    directory.mkdir(mode=0o700)
                    (directory / "preserved").write_text("synthetic saved state")
                    env[key] = str(directory)
                env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(workspace / "absent-bus")
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                before_state = {key: snapshot(Path(env[key])) for key in xdg_keys}
                expected = caiodock.build(self.root, workspace / "api").read_bytes()
                for name, output in (("orla.py", Path("relative output")),
                                     ("caiodock.py", workspace / "absolute output")):
                    with self.subTest(entry=name):
                        result = subprocess.run([sys.executable, "-B", str(self.root / "scripts" / name),
                                                 "build", "--output-dir", str(output)], cwd=workspace,
                                                env=env, capture_output=True, text=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        archive = workspace / output / "orla-dock-1.2.3.plasmoid"
                        self.assertEqual(Path(result.stdout.strip()), output / archive.name)
                        self.assertEqual(archive.read_bytes(), expected)
                self.assertEqual(snapshot(self.root), before_source)
                self.assertFalse((self.root / "dist").exists())
                for key, before in before_state.items():
                    self.assertEqual(snapshot(Path(env[key])), before)
        finally:
            for path in paths:
                path.chmod(0o755 if path.is_dir() else 0o644)

    def test_cli_build_default_output_remains_source_dist(self):
        source = Path(__file__).resolve().parents[1]
        for name in ("orla.py", "caiodock.py"):
            with self.subTest(entry=name):
                result = subprocess.run([sys.executable, "-B", str(source / "scripts" / name),
                                         "build", "--project-root", str(self.root)],
                                        cwd=self.root / "scripts", capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                archive = self.root / "dist/orla-dock-1.2.3.plasmoid"
                self.assertEqual(Path(result.stdout.strip()), archive)
                self.assertTrue(archive.is_file())

    def test_cli_build_output_directory_reports_argument_and_filesystem_errors(self):
        source = Path(__file__).resolve().parents[1]
        entry = [sys.executable, "-B", str(source / "scripts/orla.py"),
                 "build", "--project-root", str(self.root), "--output-dir"]
        result = subprocess.run(entry, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--output-dir: expected one argument", result.stderr)
        output = self.root / "existing file"
        output.write_text("preserved")
        result = subprocess.run(entry + [str(output)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("orla:", result.stderr)
        self.assertIn(str(output), result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(output.read_text(), "preserved")
        self.assertFalse((self.root / "dist").exists())

    def test_integrations_activation_handles_spaces_and_preserves_foreign_service(self):
        import shlex
        data = self.root / "data with spaces"
        bridge = data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/code/integrations.py"
        bridge.parent.mkdir(parents=True)
        bridge.write_text("# bridge")
        service = caiodock.enable_integrations(data)
        text = service.read_text()
        self.assertIn("Name=org.caiodock.Integrations\n", text)
        command = next(line[5:] for line in text.splitlines() if line.startswith("Exec="))
        self.assertEqual(shlex.split(command), [caiodock.sys.executable, str(bridge), "--serve"])
        service.write_text("# Other application\n")
        with self.assertRaises(caiodock.PackageError):
            caiodock.enable_integrations(data)
        self.assertEqual(service.read_text(), "# Other application\n")

    def test_build_rejects_unsafe_version(self):
        metadata_path = self.root / "package/metadata.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["KPlugin"]["Version"] = "../../escape"
        metadata_path.write_text(json.dumps(metadata))
        with self.assertRaises(caiodock.PackageError):
            caiodock.build(self.root)

    @mock.patch.object(caiodock.shutil, "which", return_value="/usr/bin/kpackagetool6")
    @mock.patch.object(caiodock, "run_checked")
    def test_install_selects_upgrade_and_passes_data_home(self, run, _which):
        archive = self.root / "widget.plasmoid"
        caiodock.build(self.root, self.root)
        archive.write_bytes((self.root / "orla-dock-1.2.3.plasmoid").read_bytes())
        data = self.root / "data"
        with mock.patch.object(caiodock, "dependency_status", return_value={"Python 3": True, "kpackagetool6": True, "busctl": True, "PySide6.QtDBus": True, "sessão D-Bus do usuário": True}), mock.patch.object(caiodock, "_plasma_version", return_value=None), mock.patch.object(caiodock, "_session_bus_available", return_value=False):
            self.assertEqual(caiodock.install(archive, data), "--install")
            (data / "plasma/plasmoids" / caiodock.PACKAGE_ID).mkdir(parents=True)
            self.assertEqual(caiodock.install(archive, data), "--upgrade")
        self.assertEqual([call.args[0][3] for call in run.call_args_list], ["--install", "--upgrade"])
        self.assertEqual(run.call_args_list[0].args[1]["XDG_DATA_HOME"], str(data))

    def test_default_install_preserves_integrations_and_refreshes_available_bus(self):
        archive = caiodock.build(self.root, self.root)
        data = self.root / "default-data"
        installed = data / "plasma/plasmoids" / caiodock.PACKAGE_ID
        commands = []

        def run(command, **kwargs):
            commands.append(command)
            if command[0] == "/usr/bin/kpackagetool6":
                with zipfile.ZipFile(command[4]) as package:
                    package.extractall(installed)
            return mock.Mock(returncode=0)

        statuses = {"Python 3": True, "kpackagetool6": True, "busctl": True, "PySide6.QtDBus": True, "sessão D-Bus do usuário": True}
        with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock, "_session_bus_available", return_value=True), mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), mock.patch.object(caiodock.subprocess, "run", side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(caiodock.main(["install", str(archive), "--data-home", str(data)]), 0)
        self.assertTrue((installed / "contents/ui/main.qml").is_file())
        self.assertFalse((data / "dbus-1/services" / caiodock.SERVICE_NAME).exists())
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[-1][-1], "ReloadConfig")

        service = data / "dbus-1/services" / caiodock.SERVICE_NAME
        service.parent.mkdir(parents=True)
        original_service = caiodock.SERVICE_MARKER + "[D-BUS Service]\nExec=existing helper\n"
        service.write_text(original_service)
        service.chmod(0o600)
        before_service = service.stat()
        settings = self.root / "config/plasma-org.kde.plasma.desktop-appletsrc"
        settings.parent.mkdir()
        saved_opt_in = "[Containments][17][Applets][22][Configuration][General]\nshowQuota=true\nshowPeripherals=true\nshowRecording=true\n"
        settings.write_text(saved_opt_in)
        cache = self.root / "state/project-cache"
        cache.parent.mkdir()
        cache.write_text("saved project state")
        with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock, "_session_bus_available", return_value=True), mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), mock.patch.object(caiodock.subprocess, "run", side_effect=run), mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(settings.parent), "XDG_STATE_HOME": str(cache.parent)}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(caiodock.main(["install", str(archive), "--data-home", str(data)]), 0)
        self.assertEqual([command[3] for command in commands if command[0].endswith("kpackagetool6")], ["--install", "--upgrade"])
        self.assertEqual([command[-1] for command in commands if command[0].endswith("busctl")], ["ReloadConfig", "ReloadConfig"])
        self.assertEqual(service.read_text(), original_service)
        self.assertEqual(service.stat().st_mtime_ns, before_service.st_mtime_ns)
        self.assertEqual(service.stat().st_mode, before_service.st_mode)
        self.assertEqual(settings.read_text(), saved_opt_in)
        self.assertEqual(cache.read_text(), "saved project state")

    def test_default_install_skips_integration_probes_and_checks_bus_for_refresh(self):
        archive = caiodock.build(self.root, self.root)
        with mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: "/usr/bin/kpackagetool6" if name == "kpackagetool6" else None), mock.patch.object(caiodock, "_plasma_version", return_value=None), mock.patch.object(caiodock.importlib.util, "find_spec") as find_spec, mock.patch.object(caiodock, "_session_bus_available", return_value=False) as bus, mock.patch.object(caiodock, "run_checked"), mock.patch.object(caiodock.subprocess, "run") as refresh, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(caiodock.install(archive, self.root / "data"), "--install")
        find_spec.assert_not_called()
        bus.assert_called_once_with()
        refresh.assert_not_called()
        self.assertEqual(errors.getvalue(), "")

    def test_install_validates_archive_and_foreign_service_before_package_mutation(self):
        archive = self.root / "widget.plasmoid"
        archive.write_text("invalid")
        with mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaises(caiodock.PackageError):
                caiodock.install(archive, self.root / "data")
            run.assert_not_called()

        archive = caiodock.build(self.root, self.root)
        data = self.root / "data"
        service = data / "dbus-1/services" / caiodock.SERVICE_NAME
        service.parent.mkdir(parents=True)
        service.write_text("# foreign service\n")
        with mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaises(caiodock.PackageError):
                caiodock.install(archive, data)
            run.assert_not_called()

    def test_install_missing_required_dependency_does_not_mutate_package(self):
        archive = caiodock.build(self.root, self.root)
        data = self.root / "data"
        statuses = {"Python 3": True, "kpackagetool6": False, "busctl": True, "PySide6.QtDBus": True, "sessão D-Bus do usuário": True}
        with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=None), mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaisesRegex(caiodock.PackageError, "kpackagetool6"):
                caiodock.install(archive, data)
            run.assert_not_called()
            self.assertFalse((data / "plasma/plasmoids" / caiodock.PACKAGE_ID).exists())

    def test_install_and_upgrade_work_without_optional_integrations_and_preserve_user_data(self):
        archive = caiodock.build(self.root, self.root)
        for missing in ("PySide6.QtDBus", "busctl", "sessão D-Bus do usuário"):
            with self.subTest(missing=missing):
                data = self.root / missing
                installed = data / "plasma/plasmoids" / caiodock.PACKAGE_ID
                service = data / "dbus-1/services" / caiodock.SERVICE_NAME
                settings = data / "config/plasma-settings"
                cache = data / "cache/project-state"
                for path in (settings, cache):
                    path.parent.mkdir(parents=True)
                    path.write_text("preserve me")
                statuses = {"Python 3": True, "kpackagetool6": True, "busctl": True, "PySide6.QtDBus": True, "sessão D-Bus do usuário": True}
                statuses[missing] = False
                actions = []

                def run(command, **kwargs):
                    self.assertEqual(kwargs["env"]["XDG_DATA_HOME"], str(data))
                    if command[0] == "/usr/bin/busctl":
                        self.assertEqual(command[-1], "ReloadConfig")
                        return mock.Mock(returncode=0)
                    self.assertEqual(command[:3], ["/usr/bin/kpackagetool6", "--type", "Plasma/Applet"])
                    actions.append(command[3])
                    with zipfile.ZipFile(command[4]) as package:
                        package.extractall(installed)
                    return mock.Mock(returncode=0)

                errors = io.StringIO()
                with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock, "_session_bus_available", return_value=missing == "PySide6.QtDBus"), mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), mock.patch.object(caiodock.subprocess, "run", side_effect=run), contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(caiodock.main(["install", str(archive), "--with-integrations", "--data-home", str(data)]), 0)
                    self.assertTrue((installed / "contents/ui/main.qml").is_file())
                    self.assertFalse(service.exists())
                    service.parent.mkdir(parents=True)
                    original_service = caiodock.SERVICE_MARKER + "[D-BUS Service]\nExec=existing helper\n"
                    service.write_text(original_service)
                    self.assertEqual(caiodock.main(["install", str(archive), "--with-integrations", "--data-home", str(data)]), 0)
                self.assertEqual(actions, ["--install", "--upgrade"])
                self.assertIn(missing, errors.getvalue())
                self.assertEqual(service.read_text(), original_service)
                self.assertEqual(settings.read_text(), "preserve me")
                self.assertEqual(cache.read_text(), "preserve me")

                statuses[missing] = True
                commands = []

                def recovered_run(command, **kwargs):
                    commands.append(command)
                    if command[0] == "/usr/bin/kpackagetool6":
                        return run(command, **kwargs)
                    return mock.Mock(returncode=0)

                with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), mock.patch.object(caiodock.subprocess, "run", side_effect=recovered_run), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(caiodock.main(["install", str(archive), "--with-integrations", "--data-home", str(data)]), 0)
                import shlex
                service_text = service.read_text()
                command = next(line[5:] for line in service_text.splitlines() if line.startswith("Exec="))
                self.assertEqual(shlex.split(command), [caiodock.sys.executable, str(installed / "contents/code/integrations.py"), "--serve"])
                self.assertIn("Name=org.caiodock.Integrations\n", service_text)
                self.assertEqual(commands[-1], ["/usr/bin/busctl", "--user", "--timeout=8s", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ReloadConfig"])
                self.assertEqual(settings.read_text(), "preserve me")
                self.assertEqual(cache.read_text(), "preserve me")

    def test_install_preserves_dock_and_warns_when_optional_bus_refresh_fails(self):
        archive = caiodock.build(self.root, self.root)
        statuses = {"Python 3": True, "kpackagetool6": True, "busctl": True, "PySide6.QtDBus": True, "sessão D-Bus do usuário": True}
        failures = (mock.Mock(returncode=1), caiodock.subprocess.TimeoutExpired("busctl", 10), OSError("bus unavailable"))
        for index, failure in enumerate(failures):
            with self.subTest(failure=failure):
                data = self.root / f"refresh-{index}"
                installed = data / "plasma/plasmoids" / caiodock.PACKAGE_ID
                settings = data / "config/plasma-settings"
                cache = data / "cache/project-state"
                for path in (settings, cache):
                    path.parent.mkdir(parents=True)
                    path.write_text("preserve me")
                commands = []

                def run(command, **kwargs):
                    commands.append(command)
                    if command[0] == "/usr/bin/kpackagetool6":
                        with zipfile.ZipFile(command[4]) as package:
                            package.extractall(installed)
                        return mock.Mock(returncode=0)
                    self.assertEqual(command[-1], "ReloadConfig")
                    if isinstance(failure, Exception):
                        raise failure
                    return failure

                errors = io.StringIO()
                with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), mock.patch.object(caiodock.subprocess, "run", side_effect=run), contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(caiodock.main(["install", str(archive), "--with-integrations", "--data-home", str(data)]), 0)
                self.assertEqual(len(commands), 2)
                self.assertEqual((installed / "contents/ui/main.qml").read_text(), "Item {}")
                service = data / "dbus-1/services" / caiodock.SERVICE_NAME
                self.assertIn("Name=org.caiodock.Integrations\n", service.read_text())
                self.assertEqual(settings.read_text(), "preserve me")
                self.assertEqual(cache.read_text(), "preserve me")
                self.assertIn("dock instalado", errors.getvalue())
                self.assertIn("integrações locais opcionais", errors.getvalue())
                self.assertIn("doctor", errors.getvalue())
                self.assertIn("reinstale com --with-integrations", errors.getvalue())

    def test_uninstall_removes_only_owned_package_service_and_preserves_other_data(self):
        data = self.root / "data"
        installed = data / "plasma/plasmoids" / caiodock.PACKAGE_ID
        installed.mkdir(parents=True)
        settings = self.root / "config/plasma-org.kde.plasma.desktop-appletsrc"
        settings.parent.mkdir(parents=True)
        settings.write_text("user config")
        cache = self.root / "state/codexbar-linux/history.jsonl"
        cache.parent.mkdir(parents=True)
        cache.write_text("project cache")
        service = data / "dbus-1/services" / caiodock.SERVICE_NAME
        service.parent.mkdir(parents=True)
        service.write_text(caiodock.SERVICE_MARKER + "[D-BUS Service]\n")
        with mock.patch.object(caiodock, "require_tool", return_value="/usr/bin/kpackagetool6"), mock.patch.object(caiodock, "run_checked") as run:
            self.assertTrue(caiodock.uninstall(data))
        self.assertEqual(run.call_args.args[0], ["/usr/bin/kpackagetool6", "--type", "Plasma/Applet", "--remove", caiodock.PACKAGE_ID])
        self.assertFalse(service.exists())
        self.assertEqual(settings.read_text(), "user config")
        self.assertEqual(cache.read_text(), "project cache")

    def test_uninstall_refuses_foreign_or_symlink_service_before_package_mutation(self):
        data = self.root / "data"
        (data / "plasma/plasmoids" / caiodock.PACKAGE_ID).mkdir(parents=True)
        service = data / "dbus-1/services" / caiodock.SERVICE_NAME
        service.parent.mkdir(parents=True)
        service.write_text("foreign")
        with mock.patch.object(caiodock, "require_tool", return_value="/usr/bin/kpackagetool6"), mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaises(caiodock.PackageError):
                caiodock.uninstall(data)
            run.assert_not_called()
        service.unlink()
        service.symlink_to(self.root / "elsewhere")
        with mock.patch.object(caiodock, "require_tool", return_value="/usr/bin/kpackagetool6"), mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaises(caiodock.PackageError):
                caiodock.uninstall(data)
            run.assert_not_called()

    def test_doctor_fails_for_missing_dependencies(self):
        statuses = {"Python 3": True, "kpackagetool6": False, "busctl": True, "PySide6.QtDBus": True, "sessão D-Bus do usuário": True}
        with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=None):
            self.assertEqual(caiodock.doctor(), 1)

    def test_doctor_reports_missing_optional_integrations_without_failing_dock_checks(self):
        statuses = {"Python 3": True, "kpackagetool6": True, "busctl": False, "PySide6.QtDBus": False, "sessão D-Bus do usuário": False}
        output = io.StringIO()
        with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), contextlib.redirect_stdout(output):
            self.assertEqual(caiodock.main(["doctor"]), 0)
        for name in ("busctl", "PySide6.QtDBus", "sessão D-Bus do usuário"):
            self.assertIn("OPCIONAL AUSENTE  " + name, output.getvalue())
        self.assertIn("OK  Plasma 6.7.5", output.getvalue())

    @mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}")
    @mock.patch.object(caiodock.subprocess, "run")
    def test_preview_uses_temporary_xdg_dirs_preserves_session_and_cleans_them(self, subprocess_mock, _which):
        seen = []

        def run(command, **kwargs):
            env = kwargs["env"]
            seen.append((command, env.copy()))
            return mock.Mock(returncode=0)

        subprocess_mock.side_effect = run
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/123", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/bus", "WAYLAND_DISPLAY": "wayland-0", "XDG_DATA_DIRS": "/usr/share"}):
            caiodock.preview(self.root)
        self.assertEqual(len(seen), 2)
        first_env, second_env = seen[0][1], seen[1][1]
        for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            self.assertEqual(first_env[key], second_env[key])
            self.assertFalse(Path(first_env[key]).exists())
        for key, value in (("XDG_RUNTIME_DIR", "/run/user/123"), ("DBUS_SESSION_BUS_ADDRESS", "unix:path=/bus"), ("WAYLAND_DISPLAY", "wayland-0"), ("XDG_DATA_DIRS", "/usr/share")):
            self.assertEqual(second_env[key], value)
        self.assertEqual(seen[1][0], ["/usr/bin/plasmawindowed", caiodock.PACKAGE_ID])

    @mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}")
    @mock.patch.object(caiodock.subprocess, "run")
    def test_preview_timeout_is_reported_and_private_directory_is_cleaned(self, subprocess_mock, _which):
        created = []

        def run(command, **kwargs):
            if command[0].endswith("plasmawindowed"):
                created.append(Path(kwargs["env"]["XDG_DATA_HOME"]).parent)
                raise caiodock.subprocess.TimeoutExpired(command, kwargs["timeout"])
            return mock.Mock(returncode=0)

        subprocess_mock.side_effect = run
        with self.assertRaises(caiodock.PackageError):
            caiodock.preview(self.root, 2)
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].exists())


class ThemeServiceInstallTests(unittest.TestCase):
    setUp = PackageCliTests.setUp
    tearDown = PackageCliTests.tearDown
    def theme_archive(self):
        for name in ("theme_service.py", "theme_file.py", "theme_format.py"):
            (self.root / "package/contents/code" / name).write_text("# thematic runtime")
        return caiodock.build(self.root, self.root)

    def service_path(self, data):
        return data / "dbus-1/services/org.orla.Themes.service"

    def fake_install(self, command, env=None):
        installed = Path(env["XDG_DATA_HOME"]) / "plasma/plasmoids" / caiodock.PACKAGE_ID
        if command[3] == "--remove":
            shutil.rmtree(installed)
        else:
            with zipfile.ZipFile(command[4]) as package:
                package.extractall(installed)

    def runtime(self):
        return contextlib.ExitStack()

    def prepare_runtime(self, stack, dependencies=True):
        stack.enter_context(mock.patch.object(caiodock, "_require_install_runtime", return_value=False))
        stack.enter_context(mock.patch.object(caiodock.importlib.util, "find_spec", return_value=object() if dependencies else None))
        stack.enter_context(mock.patch.object(caiodock, "_session_bus_available", return_value=dependencies))
        stack.enter_context(mock.patch.object(caiodock, "require_tool", side_effect=lambda name: "/fake/" + name))
        stack.enter_context(mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: "/fake/" + name))
        stack.enter_context(mock.patch.object(caiodock.subprocess, "run", return_value=mock.Mock(returncode=0)))
        return stack.enter_context(mock.patch.object(caiodock, "run_checked", side_effect=self.fake_install))

    def test_theme_default_install_update_spaces_and_uninstall(self):
        import shlex
        archive = self.theme_archive()
        data = self.root / "data with spaces"
        with self.runtime() as stack:
            run = self.prepare_runtime(stack)
            self.assertEqual(caiodock.install(archive, data), "--install")
            service = self.service_path(data)
            text = service.read_text()
            self.assertIn("Name=org.orla.Themes\n", text)
            command = next(line[5:] for line in text.splitlines() if line.startswith("Exec="))
            self.assertEqual(shlex.split(command), [sys.executable, str(data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/code/theme_service.py"), "--serve"])
            before = (service.read_bytes(), service.stat().st_mtime_ns)
            self.assertEqual(caiodock.install(archive, data), "--upgrade")
            self.assertEqual((service.read_bytes(), service.stat().st_mtime_ns), before)
            self.assertFalse((data / "dbus-1/services" / caiodock.SERVICE_NAME).exists())
            self.assertTrue(caiodock.uninstall(data))
            self.assertFalse(service.exists())
            self.assertEqual(run.call_count, 3)

    def test_theme_foreign_edited_exec_and_symlink_refuse_before_package_mutation(self):
        archive = self.theme_archive()
        data = self.root / "data"
        with self.runtime() as stack:
            run = self.prepare_runtime(stack)
            caiodock.install(archive, data)
            service = self.service_path(data)
            owned = service.read_text()
            for foreign in ("# foreign\n", owned.replace("--serve", "--foreign"), owned.replace("Name=org.orla.Themes", "Name=org.foreign")):
                service.write_text(foreign)
                run.reset_mock()
                for operation in (lambda: caiodock.install(archive, data), lambda: caiodock.uninstall(data)):
                    with self.assertRaises(caiodock.PackageError): operation()
                run.assert_not_called()
                self.assertEqual(service.read_text(), foreign)
            service.unlink()
            target = self.root / "foreign"
            target.write_text(owned)
            service.symlink_to(target)
            run.reset_mock()
            with self.assertRaises(caiodock.PackageError): caiodock.install(archive, data)
            with self.assertRaises(caiodock.PackageError): caiodock.uninstall(data)
            run.assert_not_called()
            self.assertEqual(target.read_text(), owned)

    def test_theme_dependency_loss_disables_only_owned_mapping(self):
        archive = self.theme_archive()
        data = self.root / "data"
        with self.runtime() as stack:
            self.prepare_runtime(stack)
            caiodock.install(archive, data)
        integration = data / "dbus-1/services" / caiodock.SERVICE_NAME
        integration.write_text(caiodock.SERVICE_MARKER + "legacy")
        with self.runtime() as stack, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.prepare_runtime(stack, dependencies=False)
            self.assertEqual(caiodock.install(archive, data), "--upgrade")
        self.assertFalse(self.service_path(data).exists())
        self.assertEqual(integration.read_text(), caiodock.SERVICE_MARKER + "legacy")
        self.assertIn("temas", errors.getvalue())
        self.assertIn("PySide6.QtCore", errors.getvalue())

    def test_theme_package_failure_preserves_mapping_and_no_fake_rollback(self):
        archive = self.theme_archive()
        data = self.root / "data"
        with self.runtime() as stack:
            run = self.prepare_runtime(stack)
            caiodock.install(archive, data)
            service = self.service_path(data)
            original = service.read_bytes()
            run.side_effect = caiodock.PackageError("package failed")
            for operation in (lambda: caiodock.install(archive, data), lambda: caiodock.uninstall(data)):
                with self.assertRaisesRegex(caiodock.PackageError, "package failed"): operation()
                self.assertEqual(service.read_bytes(), original)

    def test_theme_rechecks_collision_after_package_mutation(self):
        archive = self.theme_archive()
        data = self.root / "data"
        service = self.service_path(data)
        def collision(command, env=None):
            self.fake_install(command, env)
            service.parent.mkdir(parents=True, exist_ok=True)
            service.write_text("foreign appeared during package installation")
        with self.runtime() as stack:
            run = self.prepare_runtime(stack)
            run.side_effect = collision
            with self.assertRaisesRegex(caiodock.PackageError, "dock instalado"):
                caiodock.install(archive, data)
        self.assertEqual(service.read_text(), "foreign appeared during package installation")
        self.assertTrue((data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/ui/main.qml").exists())

    def test_theme_legacy_archive_removes_obsolete_owned_mapping(self):
        archive = self.theme_archive()
        data = self.root / "data"
        with self.runtime() as stack:
            self.prepare_runtime(stack)
            caiodock.install(archive, data)
            for name in ("theme_service.py", "theme_file.py", "theme_format.py"):
                (self.root / "package/contents/code" / name).unlink()
            legacy = caiodock.build(self.root, self.root)
            caiodock.install(legacy, data)
            self.assertFalse(self.service_path(data).exists())


    def test_theme_reader_only_archive_does_not_probe_or_register(self):
        for name in ("theme_file.py", "theme_format.py"):
            (self.root / "package/contents/code" / name).write_text("# reader-only predecessor")
        archive = caiodock.build(self.root, self.root)
        with self.runtime() as stack:
            self.prepare_runtime(stack)
            probe = stack.enter_context(mock.patch.object(caiodock, "_theme_dependencies"))
            caiodock.install(archive, self.root / "data")
            probe.assert_not_called()
        self.assertFalse(self.service_path(self.root / "data").exists())

    def test_theme_incomplete_service_archive_refuses_before_mutation(self):
        (self.root / "package/contents/code/theme_service.py").write_text("# missing siblings")
        archive = caiodock.build(self.root, self.root)
        with mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaisesRegex(caiodock.PackageError, "incomplete theme runtime"):
                caiodock.install(archive, self.root / "data")
            run.assert_not_called()

    def test_theme_dependency_losses_are_independent_and_warn_without_mapping(self):
        archive = self.theme_archive()
        for absent in ("PySide6.QtCore", "PySide6.QtDBus", "sessão D-Bus do usuário"):
            data = self.root / absent
            with self.runtime() as stack, contextlib.redirect_stderr(io.StringIO()) as errors:
                self.prepare_runtime(stack)
                stack.enter_context(mock.patch.object(caiodock.importlib.util, "find_spec", side_effect=lambda name: None if name == absent else object()))
                stack.enter_context(mock.patch.object(caiodock, "_session_bus_available", return_value=absent != "sessão D-Bus do usuário"))
                caiodock.install(archive, data)
                self.assertFalse(self.service_path(data).exists())
                self.assertIn(absent, errors.getvalue())
                self.assertTrue((data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/ui/main.qml").is_file())

    def test_theme_and_integrations_share_only_one_reload_and_never_start(self):
        archive = self.theme_archive()
        with self.runtime() as stack:
            self.prepare_runtime(stack)
            stack.enter_context(mock.patch.object(caiodock, "_require_install_runtime", return_value=True))
            bus = stack.enter_context(mock.patch.object(caiodock.subprocess, "run", return_value=mock.Mock(returncode=0)))
            caiodock.install(archive, self.root / "data", with_integrations=True)
        self.assertEqual(bus.call_count, 1)
        self.assertEqual(bus.call_args.args[0][-1], "ReloadConfig")
        self.assertNotIn("StartServiceByName", bus.call_args.args[0])

    def test_theme_service_marker_only_directory_and_parent_symlink_refuse(self):
        archive = self.theme_archive()
        data = self.root / "data"
        service = self.service_path(data)
        service.parent.mkdir(parents=True)
        for content in ("# Managed by Orla Dock theme import\n", "[D-BUS Service]\nName=org.orla.Themes\nExec=foreign\n"):
            service.write_text(content)
            with mock.patch.object(caiodock, "run_checked") as run:
                with self.assertRaises(caiodock.PackageError): caiodock.install(archive, data)
                run.assert_not_called()
        service.unlink()
        service.mkdir()
        with mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaises(caiodock.PackageError): caiodock.install(archive, data)
            run.assert_not_called()
        service.rmdir()
        service.parent.rmdir()
        target = self.root / "elsewhere"
        target.mkdir()
        service.parent.symlink_to(target, target_is_directory=True)
        with mock.patch.object(caiodock, "run_checked") as run:
            with self.assertRaises(caiodock.PackageError): caiodock.install(archive, data)
            run.assert_not_called()
        self.assertEqual(list(target.iterdir()), [])

    def test_theme_foreign_mapping_after_successful_uninstall_is_preserved(self):
        archive = self.theme_archive()
        data = self.root / "data"
        service = self.service_path(data)
        with self.runtime() as stack:
            run = self.prepare_runtime(stack)
            caiodock.install(archive, data)
            def collision(command, env=None):
                self.fake_install(command, env)
                service.write_text("foreign appeared during removal")
            run.side_effect = collision
            with self.assertRaisesRegex(caiodock.PackageError, "pacote removido ou ausente"):
                caiodock.uninstall(data)
        self.assertEqual(service.read_text(), "foreign appeared during removal")
        self.assertFalse((data / "plasma/plasmoids" / caiodock.PACKAGE_ID).exists())


    def test_theme_reinstall_retries_failed_refresh_without_rewriting_mapping(self):
        archive = self.theme_archive()
        data = self.root / "data with spaces"
        with self.runtime() as stack, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.prepare_runtime(stack)
            refresh = stack.enter_context(mock.patch.object(caiodock.subprocess, "run",
                side_effect=[mock.Mock(returncode=1), mock.Mock(returncode=0)]))
            caiodock.install(archive, data)
            service = self.service_path(data)
            before = (service.read_bytes(), service.stat().st_mtime_ns, service.stat().st_mode)
            self.assertIn("reinstale", errors.getvalue())
            caiodock.install(archive, data)
            self.assertEqual(refresh.call_count, 2)
            self.assertEqual([call.args[0][-1] for call in refresh.call_args_list], ["ReloadConfig", "ReloadConfig"])
            self.assertEqual((service.read_bytes(), service.stat().st_mtime_ns, service.stat().st_mode), before)
            self.assertFalse((data / "dbus-1/services" / caiodock.SERVICE_NAME).exists())

    def assert_removed_mapping_refresh_retry(self, *, downgrade):
        archive = self.theme_archive()
        data = self.root / "data"
        with self.runtime() as stack:
            self.prepare_runtime(stack)
            caiodock.install(archive, data)
        self.assertTrue(self.service_path(data).exists())
        if downgrade:
            for name in ("theme_service.py", "theme_file.py", "theme_format.py"):
                (self.root / "package/contents/code" / name).unlink()
            archive = caiodock.build(self.root, self.root)
        with self.runtime() as stack, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.prepare_runtime(stack)
            stack.enter_context(mock.patch.object(caiodock, "_theme_dependencies",
                return_value=[] if downgrade else ["PySide6.QtDBus"]))
            refresh = stack.enter_context(mock.patch.object(caiodock.subprocess, "run",
                side_effect=[mock.Mock(returncode=1), mock.Mock(returncode=0)]))
            caiodock.install(archive, data)
            self.assertFalse(self.service_path(data).exists())
            self.assertEqual(refresh.call_count, 1)
            self.assertIn("reinstale para temas", errors.getvalue())
            caiodock.install(archive, data)
            self.assertEqual(refresh.call_count, 2)
            self.assertEqual([call.args[0][-1] for call in refresh.call_args_list],
                             ["ReloadConfig", "ReloadConfig"])
            self.assertFalse(self.service_path(data).exists())
            self.assertFalse((data / "dbus-1/services" / caiodock.SERVICE_NAME).exists())

    def test_theme_dependency_loss_reinstall_retries_removed_mapping_refresh(self):
        self.assert_removed_mapping_refresh_retry(downgrade=False)

    def test_theme_legacy_downgrade_reinstall_retries_removed_mapping_refresh(self):
        self.assert_removed_mapping_refresh_retry(downgrade=True)

    def test_legacy_without_registrations_refresh_failure_is_silent(self):
        archive = caiodock.build(self.root, self.root)
        with self.runtime() as stack, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.prepare_runtime(stack)
            refresh = stack.enter_context(mock.patch.object(caiodock.subprocess, "run",
                return_value=mock.Mock(returncode=1)))
            caiodock.install(archive, self.root / "data")
        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(refresh.call_args.args[0][-1], "ReloadConfig")
        self.assertEqual(errors.getvalue(), "")


class AddonServiceInstallTests(unittest.TestCase):
    setUp = PackageCliTests.setUp
    tearDown = PackageCliTests.tearDown
    runtime_names = ("addon_service.py", "addon_worker.py", "addon_format.py", "addon_io.py", "addon_store.py")

    def addon_archive(self):
        for name in self.runtime_names:
            (self.root / "package/contents/code" / name).write_text("# inert trusted-host fixture\n")
        return caiodock.build(self.root, self.root)

    def service_path(self, data):
        return data / "dbus-1/services/org.orla.Addons.service"

    def fake_command(self, command, **kwargs):
        if command[0] == "/fake/kpackagetool6":
            installed = Path(kwargs["env"]["XDG_DATA_HOME"]) / "plasma/plasmoids" / caiodock.PACKAGE_ID
            if command[3] == "--remove":
                shutil.rmtree(installed)
            else:
                with zipfile.ZipFile(command[4]) as archive:
                    archive.extractall(installed)
        else:
            self.assertEqual(command, ["/fake/busctl", "--user", "--timeout=8s", "call",
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ReloadConfig"])
        return mock.Mock(returncode=0)

    def prepare_runtime(self, stack):
        stack.enter_context(mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: "/fake/" + name))
        stack.enter_context(mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)))
        stack.enter_context(mock.patch.object(caiodock.importlib.util, "find_spec", return_value=object()))
        stack.enter_context(mock.patch.object(caiodock, "_session_bus_available", return_value=True))
        return stack.enter_context(mock.patch.object(caiodock.subprocess, "run", side_effect=self.fake_command))

    def test_addon_default_install_is_isolated_lazy_and_keeps_exact_mapping_on_upgrade(self):
        import shlex
        archive = self.addon_archive()
        data = self.root / "data with spaces"
        service = self.service_path(data)
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            self.assertEqual(caiodock.install(archive, data), "--install")
            bridge = data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/code/addon_service.py"
            expected = ("# Managed by Orla Dock addon host\n[D-BUS Service]\nName=org.orla.Addons\nExec="
                        + shlex.join([sys.executable, "-I", "-B", str(bridge), "--serve"]) + "\n").encode()
            self.assertEqual(service.read_bytes(), expected)
            service.chmod(0o600)
            before = service.stat()
            self.assertEqual(caiodock.install(archive, data), "--upgrade")
            self.assertEqual(service.read_bytes(), expected)
            self.assertEqual((service.stat().st_mtime_ns, service.stat().st_mode), (before.st_mtime_ns, before.st_mode))
        self.assertEqual([call.args[0][3] for call in commands.call_args_list if call.args[0][0].endswith("kpackagetool6")],
                         ["--install", "--upgrade"])
        self.assertEqual([call.args[0][-1] for call in commands.call_args_list if call.args[0][0].endswith("busctl")],
                         ["ReloadConfig", "ReloadConfig"])
        self.assertFalse((service.parent / "org.caiodock.Integrations.service").exists())
        self.assertFalse((data / "orla-desktop").exists())

    def test_addon_partial_archives_refuse_before_dependencies_or_any_mutation(self):
        archive = self.addon_archive()
        with zipfile.ZipFile(archive) as source:
            entries = {name: source.read(name) for name in source.namelist()}
        for missing in self.runtime_names:
            with self.subTest(missing=missing):
                partial = self.root / (missing + ".zip")
                with zipfile.ZipFile(partial, "w") as output:
                    for name, content in entries.items():
                        if name != "contents/code/" + missing:
                            output.writestr(name, content)
                data = self.root / missing
                with contextlib.ExitStack() as stack:
                    commands = self.prepare_runtime(stack)
                    probe = stack.enter_context(mock.patch.object(caiodock.importlib.util, "find_spec", side_effect=AssertionError("too early")))
                    with self.assertRaisesRegex(caiodock.PackageError, "incomplete addon runtime"):
                        caiodock.install(partial, data)
                    commands.assert_not_called()
                    probe.assert_not_called()
                self.assertFalse(data.exists())

    def test_addon_archive_special_runtime_entries_refuse_before_package_command(self):
        import stat
        archive = self.addon_archive()
        with zipfile.ZipFile(archive) as source:
            entries = {name: source.read(name) for name in source.namelist()}
        target = "contents/code/addon_worker.py"
        for kind in (stat.S_IFDIR, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFLNK, "duplicate"):
            with self.subTest(kind=kind):
                malformed = self.root / (str(kind) + ".zip")
                with zipfile.ZipFile(malformed, "w") as output:
                    for name, content in entries.items():
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = ((kind if isinstance(kind, int) and name == target else stat.S_IFREG) | 0o644) << 16
                        output.writestr(info, content)
                    if kind == "duplicate":
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            output.writestr(target, "# alternate runtime")
                with contextlib.ExitStack() as stack:
                    commands = self.prepare_runtime(stack)
                    with self.assertRaises(caiodock.PackageError):
                        caiodock.install(malformed, self.root / str(kind))
                    commands.assert_not_called()

    def test_addon_unsafe_mapping_refuses_even_without_runtime_or_dependencies(self):
        archive = caiodock.build(self.root, self.root)
        data = self.root / "data"
        service = self.service_path(data)
        service.parent.mkdir(parents=True)
        sentinel = self.root / "foreign"
        sentinel.write_text("foreign target")
        for kind in ("marker", "foreign", "oversize", "directory", "fifo", "symlink", "dangling", "hardlink"):
            with self.subTest(kind=kind), contextlib.ExitStack() as stack:
                if kind == "directory":
                    service.mkdir()
                    stack.callback(service.rmdir)
                elif kind == "fifo":
                    os.mkfifo(service)
                    stack.callback(service.unlink)
                elif kind in ("symlink", "dangling"):
                    service.symlink_to(sentinel if kind == "symlink" else self.root / "absent")
                    stack.callback(service.unlink)
                elif kind == "hardlink":
                    os.link(sentinel, service)
                    stack.callback(service.unlink)
                else:
                    service.write_bytes({"marker": b"# Managed by Orla Dock addon host\n",
                                         "foreign": b"[D-BUS Service]\nName=org.orla.Addons\nExec=foreign\n",
                                         "oversize": b"x" * 100000}[kind])
                    stack.callback(service.unlink)
                commands = self.prepare_runtime(stack)
                probe = stack.enter_context(mock.patch.object(caiodock.importlib.util, "find_spec", side_effect=AssertionError("dependency probe must follow ownership")))
                for operation in (lambda: caiodock.install(archive, data), lambda: caiodock.uninstall(data)):
                    with self.assertRaises(caiodock.PackageError):
                        operation()
                commands.assert_not_called()
                probe.assert_not_called()
                self.assertTrue(service.exists() or service.is_symlink())
                self.assertEqual(sentinel.read_text(), "foreign target")

    def test_addon_unsafe_service_parents_refuse_before_package_or_dependency_probes(self):
        archive = self.addon_archive()
        for component in ("data", "dbus-1", "services"):
            for kind in ("symlink", "file"):
                with self.subTest(component=component, kind=kind):
                    data = self.root / (component + kind) / "data"
                    parent = {"data": data, "dbus-1": data / "dbus-1", "services": data / "dbus-1/services"}[component]
                    parent.parent.mkdir(parents=True)
                    target = self.root / (component + kind + "-target")
                    target.mkdir()
                    if kind == "symlink":
                        parent.symlink_to(target, target_is_directory=True)
                    else:
                        parent.write_text("preserved parent")
                    with contextlib.ExitStack() as stack:
                        commands = self.prepare_runtime(stack)
                        for operation in (lambda: caiodock.install(archive, data), lambda: caiodock.uninstall(data)):
                            with self.assertRaises(caiodock.PackageError):
                                operation()
                        commands.assert_not_called()
                    self.assertEqual(list(target.iterdir()), [])

    def test_addon_missing_dependencies_remove_only_exact_owned_mapping_after_commit(self):
        archive = self.addon_archive()
        for absent in ("PySide6.QtCore", "PySide6.QtDBus", "sessão D-Bus do usuário"):
            with self.subTest(absent=absent), contextlib.ExitStack() as stack:
                commands = self.prepare_runtime(stack)
                data = self.root / absent
                caiodock.install(archive, data)
                service = self.service_path(data)
                legacy = service.parent / "org.caiodock.Integrations.service"
                legacy.write_text("# Managed by CaioDock\nlegacy opt-in preserved\n")
                preserved = [data / "orla-desktop/addons/registry.json", data / "config/preferences", data / "producer/state"]
                for path in preserved:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("untouched sentinel")
                commands.reset_mock()
                stack.enter_context(mock.patch.object(caiodock.importlib.util, "find_spec", side_effect=lambda name: None if name == absent else object()))
                stack.enter_context(mock.patch.object(caiodock, "_session_bus_available", return_value=absent != "sessão D-Bus do usuário"))
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    caiodock.install(archive, data)
                self.assertFalse(service.exists())
                self.assertIn(absent, errors.getvalue())
                self.assertIn("dock instalado", errors.getvalue())
                self.assertIn("reinstale", errors.getvalue())
                self.assertLess(len(errors.getvalue()), 1000)
                self.assertEqual(legacy.read_text(), "# Managed by CaioDock\nlegacy opt-in preserved\n")
                for path in preserved:
                    self.assertEqual(path.read_text(), "untouched sentinel")
                self.assertEqual(commands.call_args_list[0].args[0][3], "--upgrade")

    def test_addon_source_only_bundle_does_not_probe_or_register_and_drops_old_owned_mapping(self):
        archive = self.addon_archive()
        data = self.root / "data"
        with contextlib.ExitStack() as stack:
            self.prepare_runtime(stack)
            caiodock.install(archive, data)
            for name in ("addon_service.py", "addon_worker.py"):
                (self.root / "package/contents/code" / name).unlink()
            source_only = caiodock.build(self.root, self.root)
            probe = stack.enter_context(mock.patch.object(caiodock.importlib.util, "find_spec", side_effect=AssertionError("old bundle must not probe Qt")))
            caiodock.install(source_only, data)
            self.assertFalse(self.service_path(data).exists())
            caiodock.install(source_only, self.root / "old-fresh")
            self.assertFalse(self.service_path(self.root / "old-fresh").exists())
            probe.assert_not_called()

    def test_addon_failed_package_operations_preserve_all_mappings_and_user_state(self):
        ThemeServiceInstallTests.theme_archive(self)
        archive = self.addon_archive()
        data = self.root / "data"
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            caiodock.install(archive, data, with_integrations=True)
            services = list(self.service_path(data).parent.iterdir())
            self.assertEqual(len(services), 3)
            before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in services}
            commands.side_effect = lambda *args, **kwargs: mock.Mock(returncode=1)
            for operation in (lambda: caiodock.install(archive, data), lambda: caiodock.uninstall(data)):
                commands.reset_mock()
                with self.assertRaisesRegex(caiodock.PackageError, "command failed"):
                    operation()
                self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns) for path in services}, before)
                self.assertEqual(commands.call_count, 1)

    def test_addon_uninstall_preserves_registry_preferences_and_producer_data_even_when_package_absent(self):
        archive = self.addon_archive()
        data = self.root / "data"
        sentinels = [data / "orla-desktop/addons/registry.json", data / "config/profile", data / "producer/exports/data"]
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            caiodock.install(archive, data)
            owned = self.service_path(data).read_bytes()
            for path in sentinels:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("preserve")
            self.assertTrue(caiodock.uninstall(data))
            self.assertFalse(self.service_path(data).exists())
            self.service_path(data).write_bytes(owned)
            commands.reset_mock()
            self.assertFalse(caiodock.uninstall(data))
            commands.assert_not_called()
            self.assertFalse(self.service_path(data).exists())
        for path in sentinels:
            self.assertEqual(path.read_text(), "preserve")

    def test_addon_themes_and_opt_in_legacy_combine_one_reload_after_all_mappings(self):
        ThemeServiceInstallTests.theme_archive(self)
        archive = self.addon_archive()
        data = self.root / "data"
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            def run(command, **kwargs):
                if command[0] == "/fake/busctl":
                    self.assertEqual({path.name for path in self.service_path(data).parent.iterdir()},
                        {"org.orla.Addons.service", "org.orla.Themes.service", "org.caiodock.Integrations.service"})
                return self.fake_command(command, **kwargs)
            commands.side_effect = run
            caiodock.install(archive, data, with_integrations=True)
        self.assertEqual(len(commands.call_args_list), 2)
        self.assertEqual(commands.call_args_list[-1].args[0][-1], "ReloadConfig")

    def test_addon_bad_activation_paths_refuse_before_package_mutation(self):
        archive = self.addon_archive()
        for bad in ("relative-python", "/python\nExec=foreign", "/python\r", "/python\x00"):
            with self.subTest(executable=bad), contextlib.ExitStack() as stack:
                commands = self.prepare_runtime(stack)
                stack.enter_context(mock.patch.object(caiodock.sys, "executable", bad))
                with self.assertRaisesRegex(caiodock.PackageError, "addon activation"):
                    caiodock.install(archive, self.root / "data")
                commands.assert_not_called()
        for bad in ("data\nExec=foreign", "data\r", "data\x00"):
            with self.subTest(data=bad), contextlib.ExitStack() as stack:
                commands = self.prepare_runtime(stack)
                with self.assertRaisesRegex(caiodock.PackageError, "addon activation"):
                    caiodock.install(archive, self.root / bad)
                commands.assert_not_called()

    def test_addon_installed_runtime_checked_before_even_reusing_exact_mapping(self):
        archive = self.addon_archive()
        for missing in self.runtime_names:
            for kind in ("missing", "symlink", "directory"):
                with self.subTest(member=missing, kind=kind), contextlib.ExitStack() as stack:
                    commands = self.prepare_runtime(stack)
                    data = self.root / (missing + kind)
                    caiodock.install(archive, data)
                    service = self.service_path(data)
                    before = service.read_bytes()
                    def incomplete(command, **kwargs):
                        result = self.fake_command(command, **kwargs)
                        member = data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/code" / missing
                        member.unlink()
                        if kind == "symlink":
                            member.symlink_to(self.root / "package/contents/code" / missing)
                        elif kind == "directory":
                            member.mkdir()
                        return result
                    commands.side_effect = incomplete
                    commands.reset_mock()
                    with self.assertRaisesRegex(caiodock.PackageError, "dock instalado; registro de addons falhou"):
                        caiodock.install(archive, data)
                    self.assertEqual(service.read_bytes(), before)
                    self.assertEqual(commands.call_count, 1)

    def test_addon_registration_collision_after_commit_reports_installed_and_preserves_foreign(self):
        archive = self.addon_archive()
        data = self.root / "data"
        service = self.service_path(data)
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            def collision(command, **kwargs):
                result = self.fake_command(command, **kwargs)
                service.parent.mkdir(parents=True, exist_ok=True)
                service.write_text("foreign during package commit")
                return result
            commands.side_effect = collision
            with self.assertRaisesRegex(caiodock.PackageError, "dock instalado; registro de addons falhou; pacote não foi revertido"):
                caiodock.install(archive, data)
            self.assertEqual(commands.call_count, 1)
        self.assertEqual(service.read_text(), "foreign during package commit")
        self.assertTrue((data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/ui/main.qml").is_file())

    def test_addon_mapping_edited_exec_name_mode_and_marker_are_not_adopted(self):
        archive = self.addon_archive()
        data = self.root / "data"
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            caiodock.install(archive, data)
            service = self.service_path(data)
            original = service.read_text()
            for content in (original.replace("--serve", "--other"), original.replace("Name=org.orla.Addons", "Name=org.foreign"),
                            original.replace("# Managed by Orla Dock addon host", "# foreign"), original + "extra\n"):
                service.write_text(content)
                commands.reset_mock()
                for operation in (lambda: caiodock.install(archive, data), lambda: caiodock.uninstall(data)):
                    with self.assertRaises(caiodock.PackageError):
                        operation()
                commands.assert_not_called()
                self.assertEqual(service.read_text(), content)
            service.write_text(original)
            service.chmod(0o666)
            commands.reset_mock()
            with self.assertRaises(caiodock.PackageError):
                caiodock.install(archive, data)
            commands.assert_not_called()

    def test_addon_runtime_parent_symlink_after_package_commit_cannot_register(self):
        archive = self.addon_archive()
        data = self.root / "data"
        target = self.root / "elsewhere-code"
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            def linked(command, **kwargs):
                result = self.fake_command(command, **kwargs)
                code = data / "plasma/plasmoids" / caiodock.PACKAGE_ID / "contents/code"
                code.rename(target)
                code.symlink_to(target, target_is_directory=True)
                return result
            commands.side_effect = linked
            with self.assertRaisesRegex(caiodock.PackageError, "dock instalado; registro de addons falhou"):
                caiodock.install(archive, data)
            self.assertEqual(commands.call_count, 1)
        self.assertFalse(self.service_path(data).exists())
        self.assertEqual(len(list(target.glob("addon_*.py"))), 5)

    def test_addon_foreign_mapping_appearing_during_uninstall_is_preserved(self):
        archive = self.addon_archive()
        data = self.root / "data"
        service = self.service_path(data)
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            caiodock.install(archive, data)
            def collision(command, **kwargs):
                result = self.fake_command(command, **kwargs)
                service.write_text("foreign during removal")
                return result
            commands.side_effect = collision
            commands.reset_mock()
            with self.assertRaisesRegex(caiodock.PackageError, "pacote removido ou ausente; registro de addons preservado"):
                caiodock.uninstall(data)
            self.assertEqual(commands.call_count, 1)
        self.assertEqual(service.read_text(), "foreign during removal")
        self.assertFalse((data / "plasma/plasmoids" / caiodock.PACKAGE_ID).exists())

    def test_addon_mapping_publication_is_complete_exclusive_and_cleans_failed_temp(self):
        archive = self.addon_archive()
        actual_link = os.link
        for collision in (False, True):
            with self.subTest(collision=collision), contextlib.ExitStack() as stack:
                commands = self.prepare_runtime(stack)
                data = self.root / str(collision)
                service = self.service_path(data)
                def publish(source, destination, **kwargs):
                    self.assertFalse(service.exists())
                    content = Path(source).read_bytes()
                    self.assertIn(b"Name=org.orla.Addons\nExec=", content)
                    self.assertTrue(content.endswith(b"addon_service.py --serve\n") or content.endswith(b"addon_service.py' --serve\n"))
                    if collision:
                        service.write_text("foreign before publication")
                    result = actual_link(source, destination, **kwargs)
                    self.assertEqual(service.read_bytes(), content)
                    return result
                stack.enter_context(mock.patch.object(caiodock.os, "link", side_effect=publish))
                if collision:
                    with self.assertRaisesRegex(caiodock.PackageError, "dock instalado; registro de addons falhou"):
                        caiodock.install(archive, data)
                    self.assertEqual(service.read_text(), "foreign before publication")
                    self.assertEqual(commands.call_count, 1)
                else:
                    caiodock.install(archive, data)
                    self.assertEqual(service.stat().st_nlink, 1)
                self.assertEqual(list(service.parent.glob(".org.orla.Addons-*")), [])

    def test_addon_retry_refresh_failure_keeps_mapping_and_does_not_start_any_service(self):
        archive = self.addon_archive()
        data = self.root / "data"
        with contextlib.ExitStack() as stack:
            commands = self.prepare_runtime(stack)
            def failed_refresh(command, **kwargs):
                if command[0] == "/fake/busctl":
                    self.assertEqual(command[-1], "ReloadConfig")
                    raise subprocess.TimeoutExpired("busctl", 10)
                return self.fake_command(command, **kwargs)
            commands.side_effect = failed_refresh
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                caiodock.install(archive, data)
            self.assertIn("dock instalado", errors.getvalue())
            self.assertIn("addons", errors.getvalue())
            service = self.service_path(data)
            before = (service.read_bytes(), service.stat().st_mtime_ns)
            commands.side_effect = self.fake_command
            commands.reset_mock()
            caiodock.install(archive, data)
            self.assertEqual((service.read_bytes(), service.stat().st_mtime_ns), before)
            self.assertEqual(commands.call_count, 2)
            self.assertEqual(commands.call_args.args[0][-1], "ReloadConfig")

if __name__ == "__main__":
    unittest.main()
