"""CLI delegation tests: registered fake host module, no host collector calls."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "package.py"


class HostInventoryError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class HostInventoryCliTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("orla_launcher_package_host_cli", MODULE_PATH)
        self.package = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        # Old/package import must succeed when the new host module is unavailable.
        with mock.patch.dict(sys.modules, {"inventory_host": None}):
            spec.loader.exec_module(self.package)
        self.stub = ModuleType("inventory_host")
        self.stub.HostInventoryError = HostInventoryError
        self.collector = mock.Mock(name="collect_host_catalog")
        self.stub.collect_host_catalog = self.collector

    def invoke(self, arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.package.main(arguments)
        return result, stdout.getvalue(), stderr.getvalue()

    def assert_json_line(self, output, expected):
        self.assertEqual(output, json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n")
        self.assertEqual(json.loads(output), expected)

    def test_transitive_reports_preserve_payload_and_status_exits(self):
        stage = Path("/owned/stage with spaces")
        for status, exit_code in (("ok", 0), ("missing", 1), ("unknown", 2)):
            with self.subTest(status=status):
                report = {"schema": "orla-launcher-host-catalog-0.1", "status": status,
                          "coverage": {"loaderResolution": "UNRUN"}, "incomplete": ["fixture"]}
                self.collector.reset_mock()
                self.collector.return_value = report
                with mock.patch.dict(sys.modules, {"inventory_host": self.stub}):
                    result, stdout, stderr = self.invoke(["inventory-transitive", "--stage", str(stage)])
                self.assertEqual(result, exit_code)
                self.assert_json_line(stdout, report)
                self.assertEqual(stderr, "")
                self.collector.assert_called_once_with(stage)
                self.assertEqual(report["coverage"], {"loaderResolution": "UNRUN"})

    def test_host_error_uses_existing_package_error_json(self):
        self.collector.side_effect = HostInventoryError("host_limits")
        with mock.patch.dict(sys.modules, {"inventory_host": self.stub}):
            result, stdout, stderr = self.invoke(["inventory-transitive", "--stage", "/owned/stage"])
        self.assertEqual(result, 2)
        self.assert_json_line(stdout, {"status": "error", "code": "host_limits"})
        self.assertEqual(stderr, "")
        self.collector.assert_called_once_with(Path("/owned/stage"))

    def test_relative_stage_is_delegated_as_path_for_host_validation(self):
        self.collector.side_effect = HostInventoryError("host_stage_path")
        with mock.patch.dict(sys.modules, {"inventory_host": self.stub}):
            result, stdout, stderr = self.invoke(["inventory-transitive", "--stage", "relative-prefix"])
        self.collector.assert_called_once_with(Path("relative-prefix"))
        self.assertEqual(result, 2)
        self.assert_json_line(stdout, {"status": "error", "code": "host_stage_path"})
        self.assertEqual(stderr, "")

    def test_missing_stage_is_argparse_error_without_collection(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.dict(sys.modules, {"inventory_host": self.stub}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                self.package.main(["inventory-transitive"])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("--stage", stderr.getvalue())
        self.assertIn("required", stderr.getvalue())
        self.collector.assert_not_called()

    def test_parser_keeps_old_choices_and_new_stage_type(self):
        arguments = (
            (["inventory", "--stage", "/owned/stage"], "inventory"),
            (["doctor"], "doctor"),
            (["build", "/owned/stage", "/owned/archive", "--version", "0.0.1",
              "--commit", "c" * 40, "--ci-image-digest", "sha256:" + "d" * 64,
              "--runtime-inventory", "/owned/inventory.json"], "build"),
            (["verify", "/owned/archive", "--sha256", "e" * 64, "--commit", "c" * 40], "verify"),
            (["inventory-transitive", "--stage", "relative-prefix"], "inventory-transitive"),
        )
        with mock.patch.dict(sys.modules, {"inventory_host": None}):
            for argv, command in arguments:
                with self.subTest(command=command):
                    options = self.package.parser().parse_args(argv)
                    self.assertEqual(options.command, command)
                    if command in ("inventory", "inventory-transitive", "build"):
                        self.assertIsInstance(options.stage, Path)
        self.collector.assert_not_called()

    def test_old_commands_do_not_import_host_module(self):
        inventory = {"status": "ok", "schema": self.package.INVENTORY_SCHEMA}
        doctor = {"status": "ok", "scope": "fixture"}
        manifest = {"commit": "c" * 40, "schema": self.package.SCHEMA}
        digest = "e" * 64
        runtime_inventory = {"source": "caller_assertion_unverified"}
        cases = (
            (["inventory", "--stage", "/owned/stage"], inventory),
            (["doctor"], doctor),
            (["build", "/owned/stage", "/owned/archive", "--version", "0.0.1",
              "--commit", "c" * 40, "--ci-image-digest", "sha256:" + "d" * 64,
              "--runtime-inventory", "/owned/inventory.json"], {"status": "ok", "sha256": digest}),
            (["verify", "/owned/archive", "--sha256", digest, "--commit", "c" * 40],
             {"status": "ok", "commit": manifest["commit"], "schema": manifest["schema"]}),
        )
        with mock.patch.dict(sys.modules, {"inventory_host": None}), \
                mock.patch.object(self.package, "inventory", return_value=inventory) as old_inventory, \
                mock.patch.object(self.package, "doctor", return_value=doctor) as old_doctor, \
                mock.patch.object(self.package, "build", return_value=digest) as old_build, \
                mock.patch.object(self.package, "verify", return_value=manifest) as old_verify, \
                mock.patch.object(self.package, "_load_inventory", return_value=runtime_inventory) as loader:
            for argv, expected in cases:
                with self.subTest(command=argv[0]):
                    result, stdout, stderr = self.invoke(argv)
                    self.assertEqual(result, 0)
                    self.assert_json_line(stdout, expected)
                    self.assertEqual(stderr, "")
        old_inventory.assert_called_once_with(Path("/owned/stage"))
        old_doctor.assert_called_once_with()
        loader.assert_called_once_with(Path("/owned/inventory.json"))
        old_build.assert_called_once_with(Path("/owned/stage"), Path("/owned/archive"),
            version="0.0.1", commit="c" * 40, ci_image_digest="sha256:" + "d" * 64,
            runtime_inventory=runtime_inventory)
        old_verify.assert_called_once_with(Path("/owned/archive"), expected_sha256=digest, expected_commit="c" * 40)
        self.collector.assert_not_called()

    def test_old_package_error_contract_remains_compact_json(self):
        with mock.patch.dict(sys.modules, {"inventory_host": None}), \
                mock.patch.object(self.package, "inventory", side_effect=self.package.PackageError("inventory_deadline")):
            result, stdout, stderr = self.invoke(["inventory", "--stage", "/owned/stage"])
        self.assertEqual(result, 2)
        self.assert_json_line(stdout, {"status": "error", "code": "inventory_deadline"})
        self.assertEqual(stderr, "")
        self.collector.assert_not_called()

    def test_unrelated_collector_errors_are_not_silently_remapped(self):
        self.collector.side_effect = ValueError("unrelated_fixture_error")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.dict(sys.modules, {"inventory_host": self.stub}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with self.assertRaisesRegex(ValueError, "unrelated_fixture_error"):
                self.package.main(["inventory-transitive", "--stage", "/owned/stage"])
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.collector.assert_called_once_with(Path("/owned/stage"))


if __name__ == "__main__":
    unittest.main()
