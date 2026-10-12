import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
import zipfile

from scripts import caiodock


class PackageCliTests(unittest.TestCase):
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
        with mock.patch.object(caiodock, "dependency_status", return_value={"Python 3": True, "kpackagetool6": True, "busctl": True, "PySide6.QtDBus": True, "sessão D-Bus do usuário": True}), mock.patch.object(caiodock, "_plasma_version", return_value=None):
            self.assertEqual(caiodock.install(archive, data), "--install")
            (data / "plasma/plasmoids" / caiodock.PACKAGE_ID).mkdir(parents=True)
            self.assertEqual(caiodock.install(archive, data), "--upgrade")
        self.assertEqual([call.args[0][3] for call in run.call_args_list], ["--install", "--upgrade"])
        self.assertEqual(run.call_args_list[0].args[1]["XDG_DATA_HOME"], str(data))

    def test_default_install_does_not_register_integrations_or_refresh_bus(self):
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
        with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), mock.patch.object(caiodock.subprocess, "run", side_effect=run), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(caiodock.main(["install", str(archive), "--data-home", str(data)]), 0)
        self.assertTrue((installed / "contents/ui/main.qml").is_file())
        self.assertFalse((data / "dbus-1/services" / caiodock.SERVICE_NAME).exists())
        self.assertEqual(len(commands), 1)

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
        with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), mock.patch.object(caiodock.subprocess, "run", side_effect=run), mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(settings.parent), "XDG_STATE_HOME": str(cache.parent)}), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(caiodock.main(["install", str(archive), "--data-home", str(data)]), 0)
        self.assertEqual([command[3] for command in commands], ["--install", "--upgrade"])
        self.assertEqual(service.read_text(), original_service)
        self.assertEqual(service.stat().st_mtime_ns, before_service.st_mtime_ns)
        self.assertEqual(service.stat().st_mode, before_service.st_mode)
        self.assertEqual(settings.read_text(), saved_opt_in)
        self.assertEqual(cache.read_text(), "saved project state")

    def test_default_install_skips_optional_dependency_probes(self):
        archive = caiodock.build(self.root, self.root)
        with mock.patch.object(caiodock.shutil, "which", side_effect=lambda name: "/usr/bin/kpackagetool6" if name == "kpackagetool6" else None), mock.patch.object(caiodock, "_plasma_version", return_value=None), mock.patch.object(caiodock.importlib.util, "find_spec") as find_spec, mock.patch.object(caiodock, "_session_bus_available") as bus, mock.patch.object(caiodock, "run_checked"), contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(caiodock.install(archive, self.root / "data"), "--install")
        find_spec.assert_not_called()
        bus.assert_not_called()
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
                    self.assertEqual(command[:3], ["/usr/bin/kpackagetool6", "--type", "Plasma/Applet"])
                    self.assertEqual(kwargs["env"]["XDG_DATA_HOME"], str(data))
                    actions.append(command[3])
                    with zipfile.ZipFile(command[4]) as package:
                        package.extractall(installed)
                    return mock.Mock(returncode=0)

                errors = io.StringIO()
                with mock.patch.object(caiodock, "dependency_status", return_value=statuses), mock.patch.object(caiodock, "_plasma_version", return_value=(6, 7, 5)), mock.patch.object(caiodock.shutil, "which", return_value="/usr/bin/kpackagetool6"), mock.patch.object(caiodock.subprocess, "run", side_effect=run), contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
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


if __name__ == "__main__":
    unittest.main()
