"""Package-unit fixtures use a synthetic main; Root tests the real source closure."""

import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import zipfile

from workspace import package as bundle

SOURCE = Path(__file__).resolve().parents[1]
COMMIT = "bc78722224b19cac4701055fe0ca7cef678b4b8d"
PAYLOAD = (
    "LICENSE", "workspace/Workspace.qml", "workspace/CompositionView.qml",
    "scripts/workspace_setup.py", "scripts/workspace_layout.py", "scripts/panel_layout.py",
    "scripts/panel_layout.js", "scripts/panel_layout_update.py", "layouts/mac-inspired-topbar.json",
    "package/contents/code/Style.js", "package/contents/ui/Card.qml",
    "package/contents/ui/OrlaButton.qml", "workspace/main.py", "workspace/package.py",
    "workspace/__init__.py", "scripts/__init__.py",
    "workspace/Updates.qml", "scripts/updates.py", "scripts/updates_contract.py",
    "scripts/updates_desktop_state.py", "scripts/updates_desktop.py",
)


class PackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="orla-package-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "source"
        self.expected = {}
        # Canonical inputs and this module, never a substitute for Root's main.
        for name in PAYLOAD:
            data = b'"""Synthetic entry point: package-unit fixture only."""\n' if name == "workspace/main.py" else (SOURCE / name).read_bytes()
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o644)
            self.expected[name] = data
        (self.root / "package/metadata.json").write_text('{"KPlugin":{"Version":"0.2.9"}}')

    def build(self):
        return bundle.build(self.root, self.base / "saída com espaços", commit=COMMIT)

    def test_build_is_deterministic_and_contains_only_exact_preserved_payload(self):
        first = self.build()
        data = first.read_bytes()
        (self.root / "unrelated-private.txt").write_text("excluded")
        self.assertEqual(first, self.build())
        self.assertEqual(data, first.read_bytes())
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.namelist(), sorted((*PAYLOAD, "manifest.json")))
            for entry in archive.infolist():
                self.assertEqual(entry.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(entry.create_system, 3)
                self.assertEqual(entry.external_attr >> 16, stat.S_IFREG | 0o644)
                self.assertEqual(entry.compress_type, zipfile.ZIP_DEFLATED)
            for name, content in self.expected.items():
                self.assertEqual(archive.read(name), content)
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(set(manifest), {"schema", "component", "version", "commit", "runtime", "files"})
        self.assertEqual(manifest["schema"], "orla-workspace-package-0.2")
        self.assertEqual(manifest["component"], "workspace")
        self.assertEqual(manifest["version"], "0.2.9")
        self.assertEqual(manifest["commit"], COMMIT)
        self.assertEqual(manifest["runtime"], {"pythonMinimum": "3.10", "pysideMinimum": "6.11", "qtMinimum": "6.11", "plasmaExact": "6.7.5"})
        self.assertEqual(manifest["files"], [dict(path=name, size=len(self.expected[name]), mode=0o644, sha256=hashlib.sha256(self.expected[name]).hexdigest()) for name in sorted(PAYLOAD)])

    def verify(self, data, *, sha=None, commit=COMMIT):
        return bundle.verify_archive(data, expected_sha256=sha or hashlib.sha256(data).hexdigest(), expected_commit=commit)

    def test_verified_archive_returns_only_manifest_and_original_payload_bytes(self):
        data = self.build().read_bytes()
        result = self.verify(data)
        self.assertEqual(set(result), {"manifest", "files"})
        self.assertEqual(result["files"], self.expected)
        self.assertEqual(result["manifest"]["commit"], COMMIT)
        self.assertFalse((self.base / "workspace").exists())

    def assert_rejected(self, data, code=None, **kwargs):
        with self.assertRaises(bundle.PackageError) as caught:
            self.verify(data, **kwargs)
        self.assertEqual(str(caught.exception), caught.exception.code)
        self.assertNotIn(str(self.base), str(caught.exception))
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_archive_is_authenticated_before_parsing_and_commit_is_pinned(self):
        data = self.build().read_bytes()
        self.assert_rejected(data, "archive_hash", sha="0" * 64)
        self.assert_rejected(data, "commit_mismatch", commit="a" * 40)
        self.assert_rejected(data, "invalid_sha256", sha="bad")
        self.assert_rejected(data, "invalid_commit", commit="bad")
        self.assert_rejected(b"not a zip", "invalid_archive")

    def rewrite(self, change):
        with zipfile.ZipFile(io.BytesIO(self.build().read_bytes())) as archive:
            rows = [(info, archive.read(info)) for info in archive.infolist()]
        change(rows)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for info, data in rows:
                archive.writestr(info, data)
        return output.getvalue()

    def test_archive_rejects_nonexact_names_duplicates_and_missing_members(self):
        def rename(rows, name):
            rows[0][0].filename = name
        for name in ("../LICENSE", "/LICENSE", "workspace/../LICENSE", "workspace\\main.py", "./LICENSE", "workspace/", "unexpected.py", "LICENSE\x00hidden"):
            with self.subTest(name=name):
                self.assert_rejected(self.rewrite(lambda rows: rename(rows, name)))
        self.assert_rejected(self.rewrite(lambda rows: rows.pop()))
        # A duplicate entry must fail even when both copies carry the right bytes.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.assert_rejected(self.rewrite(lambda rows: rows.append(rows[0])))
        def extra(rows):
            info = zipfile.ZipInfo("unexpected")
            rows.append((info, b"extra"))
        self.assert_rejected(self.rewrite(extra))

    def test_archive_rejects_nonregular_modes_and_noncanonical_zip_metadata(self):
        for attributes in ((stat.S_IFLNK | 0o644) << 16, (stat.S_IFREG | 0o755) << 16, (stat.S_IFDIR | 0o644) << 16):
            with self.subTest(attributes=attributes):
                self.assert_rejected(self.rewrite(lambda rows: setattr(rows[0][0], "external_attr", attributes)))
        self.assert_rejected(self.rewrite(lambda rows: setattr(rows[0][0], "compress_type", zipfile.ZIP_STORED)))
        self.assert_rejected(self.rewrite(lambda rows: setattr(rows[0][0], "create_system", 0)))

    def test_archive_rejects_modified_payload_and_corrupt_compressed_data(self):
        self.assert_rejected(self.rewrite(lambda rows: rows.__setitem__(0, (rows[0][0], b"tampered"))), "payload_mismatch")
        data = bytearray(self.build().read_bytes())
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.infolist()[0]
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        data[offset] ^= 0xff
        self.assert_rejected(bytes(data), "invalid_archive")

    def test_archive_rejects_bounded_size_and_excessive_expansion(self):
        self.assert_rejected(b"x" * ((16 << 20) + 1), "size_limit")
        def replace(rows, content):
            rows[0] = rows[0][0], content
        self.assert_rejected(self.rewrite(lambda rows: replace(rows, b"x" * ((2 << 20) + 1))), "size_limit")
        self.assert_rejected(self.rewrite(lambda rows: replace(rows, b"x" * (512 << 10))), "expansion_limit")
        def manifest_large(rows):
            index = next(i for i, row in enumerate(rows) if row[0].filename == "manifest.json")
            rows[index] = rows[index][0], b"x" * ((64 << 10) + 1)
        self.assert_rejected(self.rewrite(manifest_large), "size_limit")
        def total_large(rows):
            for i in range(5):
                import random
                rows[i] = rows[i][0], random.Random(i).randbytes(900 << 10)
        self.assert_rejected(self.rewrite(total_large), "size_limit")

    def with_manifest(self, change):
        def replace(rows):
            index = next(i for i, row in enumerate(rows) if row[0].filename == "manifest.json")
            manifest = json.loads(rows[index][1])
            change(manifest)
            rows[index] = rows[index][0], json.dumps(manifest).encode()
        return self.rewrite(replace)

    def test_manifest_requires_exact_schema_runtime_semver_and_record_types(self):
        changes = (
            lambda m: m.update(extra=True), lambda m: m.pop("schema"),
            lambda m: m.update(schema="other"), lambda m: m.update(component="dock"),
            lambda m: m.update(version="01.2.3"), lambda m: m.update(version="1.2.3-01"),
            lambda m: m.update(commit="bad"), lambda m: m["runtime"].update(qtMinimum="6.10"),
            lambda m: m["runtime"].update(extra="value"), lambda m: m.update(files={}),
            lambda m: m["files"].reverse(), lambda m: m["files"].append(m["files"][0]),
            lambda m: m["files"][0].update(extra=True),
            lambda m: m["files"][0].update(mode="0644"),
            lambda m: m["files"][0].update(size=True),
            lambda m: m["files"][0].update(size=-1),
            lambda m: m["files"][0].update(sha256="0" * 64),
            lambda m: m["files"][0].update(path="../LICENSE"),
        )
        for i, change in enumerate(changes):
            with self.subTest(mutation=i):
                self.assert_rejected(self.with_manifest(change))

    def test_manifest_rejects_duplicate_keys_invalid_utf8_and_nonobjects(self):
        def replace(rows, data):
            index = next(i for i, row in enumerate(rows) if row[0].filename == "manifest.json")
            rows[index] = rows[index][0], data
        with zipfile.ZipFile(self.build()) as archive:
            data = archive.read("manifest.json")
        duplicate = b'{"component":"other",' + data[1:]
        for content in (duplicate, data.decode().encode("utf-16"), b"\xff", b"[]", b"null", b"NaN", b"{" * 2000):
            with self.subTest(content=content[:30]):
                self.assert_rejected(self.rewrite(lambda rows: replace(rows, content)))

    def directory(self):
        root = self.base / "unpacked"
        with zipfile.ZipFile(self.build()) as archive:
            for info in archive.infolist():
                target = root / info.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
                target.chmod(0o644)
        return root

    def test_directory_verification_matches_archive_without_inspecting_ancestors(self):
        root = self.directory()
        expected = self.verify(self.build().read_bytes())["manifest"]
        self.assertEqual(bundle.verify_directory(root), expected)
        (root.parent / "unrelated-sibling").write_text("ignored")
        alias = self.base / "ancestor-alias"
        alias.symlink_to(self.base, target_is_directory=True)
        self.assertEqual(bundle.verify_directory(alias / root.name), expected)
        self.assertFalse(any(root.rglob("*.pyc")))

    def test_directory_requires_absolute_real_directory(self):
        root = self.directory()
        alias = self.base / "root-alias"
        alias.symlink_to(root, target_is_directory=True)
        for path in (Path("relative"), root / "LICENSE", alias, root / "missing"):
            with self.subTest(path=path.name), self.assertRaises(bundle.PackageError) as caught:
                bundle.verify_directory(path)
            self.assertEqual(caught.exception.code, "invalid_root")

    def test_directory_rejects_unknown_children_symlinks_nonregular_and_drift(self):
        import os
        root = self.directory()
        target = root / "workspace/main.py"
        original = target.read_bytes()
        def extra_file():
            target.write_bytes(original)
            (root / "extra").write_text("unknown")
        def extra_directory():
            (root / "extra").mkdir()
        def symlink_file():
            target.unlink()
            target.symlink_to(self.root / "workspace/main.py")
        def symlink_directory():
            shutil.rmtree(root / "workspace")
            (root / "workspace").symlink_to(self.root / "workspace", target_is_directory=True)
        def fifo():
            target.unlink()
            os.mkfifo(target)
        mutations = (extra_file, extra_directory, symlink_file, symlink_directory, fifo,
                     lambda: target.chmod(0o755), lambda: target.write_bytes(b"tampered"),
                     lambda: target.unlink(), lambda: target.write_bytes(b"x" * ((2 << 20) + 1)),
                     lambda: (root / "scripts/unexpected.py").write_text("unknown"))
        for mutate in mutations:
            with self.subTest(mutation=mutate.__name__):
                shutil.rmtree(root)
                root = self.directory()
                target = root / "workspace/main.py"
                mutate()
                with self.assertRaises(bundle.PackageError) as caught:
                    bundle.verify_directory(root)
                self.assertNotIn(str(root), str(caught.exception))

    def cli(self, *args):
        import subprocess
        import sys
        return subprocess.run([sys.executable, "-I", "-B", str(self.root / "workspace/package.py"), *map(str, args)], cwd=self.base, capture_output=True, text=True, timeout=15)

    def test_cli_build_and_verify_emit_json_summaries_without_payload_bytes(self):
        output_dir = self.base / "pacote saída com espaços"
        result = self.cli("build", "--commit", COMMIT, "--output-dir", output_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        summary = json.loads(result.stdout)
        output = Path(summary["archive"])
        self.assertEqual(output.parent, output_dir)
        self.assertEqual(summary["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        result = self.cli("verify", output, "--sha256", summary["sha256"], "--commit", COMMIT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        verified = json.loads(result.stdout)
        self.assertEqual(verified["fileCount"], 21)
        self.assertEqual(verified["commit"], COMMIT)
        self.assertEqual(verified["version"], "0.2.9")
        self.assertNotIn("files", verified)
        failure = self.cli("verify", output, "--sha256", "0" * 64, "--commit", COMMIT)
        self.assertNotEqual(failure.returncode, 0)
        self.assertEqual(json.loads(failure.stdout), {"error": "archive_hash"})
        self.assertEqual(failure.stderr, "")
        failure = self.cli("verify", self.base / "private-missing.zip", "--sha256", "0" * 64, "--commit", COMMIT)
        self.assertNotEqual(failure.returncode, 0)
        self.assertNotIn(str(self.base), failure.stdout + failure.stderr)

    def test_module_import_is_inert_and_cli_help_needs_only_stdlib(self):
        import subprocess
        import sys
        before = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*"))
        code = '''import runpy, sys

def audit(event, args):
    if event.startswith(("subprocess.", "socket.", "ctypes.dlopen")):
        raise AssertionError(event)

sys.addaudithook(audit)
runpy.run_path(sys.argv[1], run_name="package_unit_import")
assert not any(name.startswith(("PySide6", "scripts.", "workspace.main")) for name in sys.modules)
'''
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(self.root / "workspace/package.py")], cwd=self.base, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        help_result = self.cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("build", help_result.stdout)
        self.assertEqual(before, sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*")))

    def test_build_rejects_unsafe_sources_and_invalid_metadata_without_artifacts(self):
        for value in ("", "not-hex" * 6, "0" * 39):
            with self.subTest(commit=value), self.assertRaises(bundle.PackageError) as caught:
                bundle.build(self.root, self.base / "bad-output", commit=value)
            self.assertEqual(caught.exception.code, "invalid_commit")
        metadata = self.root / "package/metadata.json"
        for content in ('{}', '{"KPlugin":{"Version":"../escape"}}', '{"KPlugin":{"Version":"01.2.3"}}', '{"KPlugin":{"Version":"1.2.3-01"}}', 'null', '{'):
            with self.subTest(metadata=content):
                metadata.write_text(content)
                with self.assertRaises(bundle.PackageError) as caught:
                    self.build()
                self.assertEqual(caught.exception.code, "invalid_version")
        metadata.write_text('{"KPlugin":{"Version":"1.2.3-rc.1+local"}}')
        self.assertEqual(self.verify(self.build().read_bytes())["manifest"]["version"], "1.2.3-rc.1+local")
        target = self.root / "workspace/main.py"
        target.unlink()
        target.symlink_to(SOURCE / "LICENSE")
        with self.assertRaises(bundle.PackageError):
            self.build()
        target.unlink()
        shutil.rmtree(self.root / "workspace")
        (self.root / "workspace").symlink_to(SOURCE / "workspace", target_is_directory=True)
        with self.assertRaises(bundle.PackageError):
            self.build()
        self.assertFalse((self.base / "bad-output").exists())

    def test_build_never_returns_a_package_that_its_verifier_would_reject(self):
        target = self.root / "workspace/main.py"
        for content, code in ((b"x" * ((2 << 20) + 1), "size_limit"), (b"x" * (512 << 10), "expansion_limit")):
            with self.subTest(code=code):
                target.write_bytes(content)
                with self.assertRaises(bundle.PackageError) as caught:
                    self.build()
                self.assertEqual(caught.exception.code, code)
                self.assertFalse((self.base / "saída com espaços").exists())

    def test_build_does_not_follow_existing_output_symlink(self):
        external = self.base / "protected-file"
        external.write_bytes(b"preserve")
        output_dir = self.base / "saída com espaços"
        output_dir.mkdir()
        output = output_dir / "orla-workspace-0.2.9.zip"
        output.symlink_to(external)
        try:
            self.build()
        except bundle.PackageError:
            pass
        self.assertEqual(external.read_bytes(), b"preserve")

    def test_hash_pins_accept_hex_case_without_changing_canonical_manifest(self):
        output = bundle.build(self.root, self.base / "upper", commit=COMMIT.upper())
        data = output.read_bytes()
        result = bundle.verify_archive(data, expected_sha256=hashlib.sha256(data).hexdigest().upper(), expected_commit=COMMIT.upper())
        self.assertEqual(result["manifest"]["commit"], COMMIT)

    def test_deep_metadata_and_filesystem_errors_have_stable_private_errors(self):
        metadata = self.root / "package/metadata.json"
        metadata.write_text("[" * 1500 + "]" * 1500)
        with self.assertRaises(bundle.PackageError) as caught:
            self.build()
        self.assertEqual(caught.exception.code, "invalid_version")
        metadata.write_text('{"KPlugin":{"Version":"0.2.9"}}')
        with self.assertRaises(bundle.PackageError) as caught:
            bundle.build(self.root, self.base / "invalid\x00directory", commit=COMMIT)
        self.assertEqual(caught.exception.code, "output_error")
        for args in ((), ("build",), ("verify", "secret-file", "--unexpected", "private-value")):
            failure = self.cli(*args)
            self.assertEqual(failure.returncode, 1)
            self.assertEqual(json.loads(failure.stdout), {"error": "invalid_arguments"})
            self.assertEqual(failure.stderr, "")

    def test_build_cleans_temporary_output_on_publish_failure(self):
        output_dir = self.base / "saída com espaços"
        (output_dir / "orla-workspace-0.2.9.zip").mkdir(parents=True)
        with self.assertRaises(bundle.PackageError) as caught:
            self.build()
        self.assertEqual(caught.exception.code, "output_error")
        self.assertEqual([path.name for path in output_dir.iterdir()], ["orla-workspace-0.2.9.zip"])
