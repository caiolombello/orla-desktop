"""Public bundle entry must remain inert until an explicit action is chosen."""

from pathlib import Path
import hashlib
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class EntryTests(unittest.TestCase):
    def test_unsupported_qt_never_starts_the_composition_host(self):
        import PySide6
        from workspace import main, package
        from scripts import workspace_setup
        with mock.patch.object(package, "verify_directory", return_value={}), \
                mock.patch.object(PySide6, "__version__", "6.10.0"), \
                mock.patch.object(workspace_setup, "launch", return_value=0) as launch, \
                mock.patch.object(sys, "path", sys.path.copy()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main.main(["--service", "plasma-fixture.service"]), 1)
        launch.assert_not_called()

    def test_startup_failure_omits_private_backend_exception(self):
        from workspace import main, package
        from scripts import panel_layout, workspace_setup
        error = panel_layout.LayoutError("private path /private/person/calendar")
        output = io.StringIO()
        with mock.patch.object(package, "verify_directory", return_value={}), \
                mock.patch.object(workspace_setup, "launch", side_effect=error), \
                mock.patch.object(sys, "path", sys.path.copy()), contextlib.redirect_stderr(output):
            self.assertEqual(main.main(["--service", "plasma-fixture.service"]), 1)
        self.assertIn("startup", output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_help_from_unrelated_directory_requires_neither_qt_nor_service(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "workspace/main.py"), "--help"],
                                    cwd=directory, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--service", result.stdout)
        self.assertIn("--diagnose", result.stdout)

    def test_invalid_service_is_rejected_before_runtime_or_bundle_import(self):
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "workspace/main.py"),
                                 "--service", "../foreign.service"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("literal", result.stderr)

    def bundle(self, directory):
        from workspace import package
        temporary = Path(directory)
        archive = package.build(ROOT, temporary / "archives", commit="a" * 40)
        verified = package.verify_archive(archive.read_bytes(), expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                                          expected_commit="a" * 40)
        unpacked = temporary / "original"
        for name, data in verified["files"].items():
            path = unpacked / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data); path.chmod(0o644)
        with zipfile.ZipFile(archive) as source:
            (unpacked / "manifest.json").write_bytes(source.read("manifest.json"))
        (unpacked / "manifest.json").chmod(0o644)
        moved = temporary / "Moved companion ç %"
        unpacked.rename(moved)
        return moved

    def environment(self, temporary):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        for key in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TMPDIR"):
            path = temporary / key.lower(); path.mkdir(mode=0o700)
            (path / "sentinel").write_text("owned synthetic data")
            environment[key] = str(path)
        return environment

    def test_moved_bundle_reports_version_and_loads_actual_ui_without_service(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            elsewhere = root / "unrelated"; elsewhere.mkdir()
            environment = self.environment(root)
            before = {str(path.relative_to(moved)): path.read_bytes() for path in moved.rglob("*") if path.is_file()}
            for action in ("--version", "--diagnose"):
                result = subprocess.run([sys.executable, "-I", "-B", str(moved / "workspace/main.py"), action],
                                        cwd=elsewhere, env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                report = json.loads(result.stdout)
                self.assertEqual(report["commit"], "a" * 40)
                if action == "--diagnose":
                    self.assertEqual(report["runtime"]["status"], "ready")
                    self.assertFalse(report["nativeValidated"])
                    self.assertFalse(report["serviceContacted"])
            self.assertEqual({str(path.relative_to(moved)): path.read_bytes() for path in moved.rglob("*") if path.is_file()}, before)
            for key in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
                self.assertEqual(list(Path(environment[key]).iterdir()), [Path(environment[key]) / "sentinel"])

    def test_diagnosis_loads_ui_with_repository_hidden(self):
        if shutil.which("bwrap") is None:
            self.skipTest("Bubblewrap absent; OS-level repository masking not available")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            environment = self.environment(root)
            command = ["bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
                       "--tmpfs", str(ROOT), "--bind", str(root), str(root), "--proc", "/proc", "--dev", "/dev",
                       "--", sys.executable, "-I", "-B", str(moved / "workspace/main.py"), "--diagnose"]
            result = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["runtime"]["status"], "ready")

    def test_missing_qt_still_allows_version_and_reports_dependency_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            venv.EnvBuilder(with_pip=False).create(root / "no-qt")
            python = root / "no-qt/bin/python"
            command = [str(python), "-I", "-B", str(moved / "workspace/main.py")]
            version = subprocess.run(command + ["--version"], cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(version.returncode, 0, version.stderr)
            result = subprocess.run(command + ["--diagnose"], cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["runtime"]["status"], "qt_runtime_missing")
            self.assertFalse(report["serviceContacted"])
            self.assertFalse(report["nativeValidated"])

    def test_installed_packages_cannot_replace_bundle_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            moved = self.bundle(directory)
            venv.EnvBuilder(with_pip=False, system_site_packages=True).create(root / "python")
            python = root / "python/bin/python"
            location = subprocess.run([str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                      check=True, capture_output=True, text=True, timeout=10)
            for name in ("workspace", "scripts"):
                installed = Path(location.stdout.strip()) / name
                installed.mkdir()
                (installed / "__init__.py").write_text("")
            result = subprocess.run([str(python), "-I", "-B", str(moved / "workspace/main.py"), "--diagnose"],
                                    cwd=root, env=self.environment(root), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["runtime"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
