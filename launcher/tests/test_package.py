import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile
import zlib


MODULE_PATH = Path(__file__).resolve().parents[1] / "package.py"
SPEC = importlib.util.spec_from_file_location("orla_launcher_package", MODULE_PATH)
package = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(package)


def synthetic_elf(*, needed=("libQt6Core.so.6",), rpath=(), runpath=()):
    base = 0x400000
    interp_offset = 0x200
    string_offset = 0x280
    dynamic_offset = 0x380
    interpreter = b"/lib64/ld-linux-x86-64.so.2\0"
    strings = bytearray(b"\0")

    def add_string(value):
        offset = len(strings)
        strings.extend(value.encode("ascii") + b"\0")
        return offset

    needed_offsets = [add_string(item) for item in needed]
    rpath_offsets = [add_string(item) for item in rpath]
    runpath_offsets = [add_string(item) for item in runpath]
    entries = [(5, base + string_offset), (10, len(strings))]
    entries += [(1, offset) for offset in needed_offsets]
    entries += [(15, offset) for offset in rpath_offsets]
    entries += [(29, offset) for offset in runpath_offsets]
    entries.append((0, 0))
    dynamic = b"".join(struct.pack("<qQ", tag, value) for tag, value in entries)
    size = dynamic_offset + len(dynamic)
    image = bytearray(size)
    image[:64] = struct.pack(
        "<16sHHIQQQIHHHHHH",
        b"\x7fELF\x02\x01\x01" + b"\0" * 9,
        3, 62, 1, 0, 64, 0, 0, 64, 56, 3, 0, 0, 0,
    )
    headers = (
        (1, 5, 0, base, base, size, size, 0x1000),
        (3, 4, interp_offset, base + interp_offset, base + interp_offset,
         len(interpreter), len(interpreter), 1),
        (2, 4, dynamic_offset, base + dynamic_offset, base + dynamic_offset,
         len(dynamic), len(dynamic), 8),
    )
    for index, values in enumerate(headers):
        image[64 + index * 56:64 + (index + 1) * 56] = struct.pack("<IIQQQQQQ", *values)
    image[interp_offset:interp_offset + len(interpreter)] = interpreter
    image[string_offset:string_offset + len(strings)] = strings
    image[dynamic_offset:dynamic_offset + len(dynamic)] = dynamic
    return bytes(image)


def dependency(soname):
    return {
        "soname": soname,
        "owner": "synthetic-runtime",
        "nevra": "synthetic-runtime-0:1.0-1.fc44.x86_64",
    }


def runtime_inventory():
    assets = []
    entries = (
        ("qpa_wayland", "elf", "/usr/lib64/qt6/plugins/platforms/libqwayland.so"),
        ("qml_qtquick_plugin", "elf", "/usr/lib64/qt6/qml/QtQuick/libqtquick2plugin.so"),
        ("qml_controls_plugin", "elf", "/usr/lib64/qt6/qml/QtQuick/Controls/libqtquickcontrols2plugin.so"),
        ("qml_controls_qmldir", "data", "/usr/lib64/qt6/qml/QtQuick/Controls/qmldir"),
        ("qml_controls_implementation", "data", "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/Button.qml"),
        ("qml_layouts_plugin", "elf", "/usr/lib64/qt6/qml/QtQuick/Layouts/libqquicklayoutsplugin.so"),
        ("krunner_services", "elf", "/usr/lib64/qt6/plugins/kf6/krunner/krunner_services.so"),
        ("krunner_calculator", "elf", "/usr/lib64/qt6/plugins/kf6/krunner/calculator.so"),
    )
    for role, kind, path in entries:
        assets.append({
            "role": role,
            "kind": kind,
            "path": path,
            "owner": "synthetic-runtime",
            "nevra": "synthetic-runtime-0:1.0-1.fc44.x86_64",
            "needed": [] if kind == "data" else [dependency("libSynthetic.so.1")],
        })
    assets.sort(key=lambda item: (item["role"], item["path"]))
    return {
        "source": "caller_assertion_unverified",
        "elf_direct": {
            "interpreter": "/lib64/ld-linux-x86-64.so.2",
            "needed": [dependency("libQt6Core.so.6")],
            "rpath": [],
            "runpath": [],
        },
        "dynamic_assets": assets,
        "optional_capabilities": [{
            "name": "bwrap",
            "path": "/usr/bin/bwrap",
            "owner": "bubblewrap",
            "nevra": "bubblewrap-0:0.11.0-1.fc44.x86_64",
        }],
    }


class PackageTests(unittest.TestCase):
    def make_stage(self, root):
        stage = root / "stage with spaces"
        (stage / "bin").mkdir(parents=True)
        (stage / "libexec").mkdir()
        (stage / "bin/orla-launcher").write_bytes(synthetic_elf())
        (stage / "libexec/ai.py").write_bytes(b"# synthetic ai helper\n")
        (stage / "libexec/steam.py").write_bytes(b"# synthetic steam helper\n")
        # Owned placeholders preserve the sibling closure without executing providers.
        for name in ("ai_text_ollama.py", "ai_text_transport.py", "ai_text.py"):
            (stage / "libexec" / name).write_bytes(("# synthetic " + name + "\n").encode("ascii"))
        (stage / "LICENSE").write_bytes(b"synthetic license\n")
        os.chmod(stage / "bin/orla-launcher", 0o755)
        for name in ("libexec/ai.py", "libexec/steam.py", "libexec/ai_text_ollama.py",
                     "libexec/ai_text_transport.py", "libexec/ai_text.py", "LICENSE"):
            os.chmod(stage / name, 0o644)
        return stage

    def build_archive(self, root, *, stage=None, inventory=None, output_name="package.zip"):
        stage = stage or self.make_stage(root)
        output = root / output_name
        digest = package.build(
            stage,
            output,
            version="0.1.0",
            commit="a" * 40,
            ci_image_digest="sha256:" + "b" * 64,
            runtime_inventory=inventory or runtime_inventory(),
        )
        return output, digest

    def assert_code(self, code, callback):
        with self.assertRaises(package.PackageError) as raised:
            callback()
        self.assertEqual(raised.exception.code, code)

    def independent_info(self, name, mode=0o644, *, kind=stat.S_IFREG, timestamp=(1980, 1, 1, 0, 0, 0)):
        info = zipfile.ZipInfo(name, date_time=timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.create_version = 20
        info.extract_version = 20
        info.external_attr = (kind | mode) << 16
        return info

    def rewrite(self, source, destination, transform):
        with zipfile.ZipFile(source) as archive:
            entries = [(info.filename, archive.read(info), stat.S_IMODE(info.external_attr >> 16))
                       for info in archive.infolist()]
        entries = transform(entries)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for name, data, mode in entries:
                    archive.writestr(self.independent_info(name, mode), data,
                                     compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        return hashlib.sha256(destination.read_bytes()).hexdigest()

    def test_build_is_deterministic_and_verify_uses_external_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            first = root / "first.zip"
            second = root / "moved output" / "second.zip"
            second.parent.mkdir()
            arguments = {
                "version": "0.1.0",
                "commit": "a" * 40,
                "ci_image_digest": "sha256:" + "b" * 64,
                "runtime_inventory": runtime_inventory(),
            }
            first_digest = package.build(stage, first, **arguments)
            moved = root / "moved staging with spaces"
            stage.rename(moved)
            second_digest = package.build(moved, second, **arguments)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_digest, hashlib.sha256(first.read_bytes()).hexdigest())
            self.assertEqual(first_digest, second_digest)
            manifest = package.verify(first, expected_sha256=first_digest, expected_commit="a" * 40)
            self.assertEqual(manifest["schema"], "orla-launcher-package-0.3")
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), [
                    "bin/orla-launcher", "libexec/ai.py", "libexec/steam.py",
                    "libexec/ai_text_ollama.py", "libexec/ai_text_transport.py",
                    "libexec/ai_text.py", "LICENSE", "manifest.json",
                ])

    def legacy_archive(self, root, output_name="legacy.zip"):
        # Independent old-format fixture: never use the current builder/constants.
        payload = (
            ("bin/orla-launcher", synthetic_elf(), 0o755),
            ("libexec/ai.py", b"# legacy ai helper\n", 0o644),
            ("libexec/steam.py", b"# legacy steam helper\n", 0o644),
            ("LICENSE", b"legacy license\n", 0o644),
        )
        manifest = {
            "schema": "orla-launcher-package-0.2", "target": "fedora44-x86_64",
            "version": "0.1.0", "channel": "experimental", "commit": "a" * 40,
            "ci_image_digest": "sha256:" + "b" * 64,
            "files": [{"path": name, "size": len(data), "mode": f"{mode:04o}",
                       "sha256": hashlib.sha256(data).hexdigest()} for name, data, mode in payload],
            "runtime_inventory": runtime_inventory(),
        }
        data = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        output = root / output_name
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, content, mode in (*payload, ("manifest.json", data, 0o644)):
                archive.writestr(self.independent_info(name, mode), content,
                                 compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.chmod(output, 0o644)
        return output, hashlib.sha256(output.read_bytes()).hexdigest()

    def test_complete_relocated_stage_builds_without_source_and_preserves_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "owned source"
            source.mkdir()
            stage = self.make_stage(source)
            moved = root / "relocated payload"
            stage.rename(moved)
            source.rmdir()
            self.assertFalse(source.exists())
            expected = {str(p.relative_to(moved)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                        for p in moved.rglob("*") if p.is_file()}
            with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")), \
                    mock.patch.object(subprocess, "run", side_effect=AssertionError("process")):
                archive, digest = self.build_archive(root, stage=moved)
                manifest = package.verify(archive, expected_sha256=digest, expected_commit="a" * 40)
            self.assertEqual(manifest["schema"], "orla-launcher-package-0.3")
            self.assertEqual(len(manifest["files"]), 7)
            with zipfile.ZipFile(archive) as result:
                self.assertEqual(len(result.infolist()), 8)
                for record in manifest["files"]:
                    data, mode = expected[record["path"]]
                    self.assertEqual(result.read(record["path"]), data)
                    self.assertEqual(record["mode"], f"{mode:04o}")
                    self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual({str(Path(name).parent) for name in result.namelist()
                                  if name.endswith(".py")}, {"libexec"})

    def test_independent_legacy_archive_verifies_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, digest = self.legacy_archive(root)
            duplicate, second_digest = self.legacy_archive(root, "second-legacy.zip")
            self.assertEqual(archive.read_bytes(), duplicate.read_bytes())
            self.assertEqual(digest, second_digest)
            before = (archive.read_bytes(), archive.stat().st_mode)
            manifest = package.verify(archive, expected_sha256=digest, expected_commit="a" * 40)
            self.assertEqual(manifest["schema"], "orla-launcher-package-0.2")
            self.assertEqual(len(manifest["files"]), 4)
            self.assertEqual(before, (archive.read_bytes(), archive.stat().st_mode))
            self.assert_code("archive_digest", lambda: package.verify(
                archive, expected_sha256="0" * 64, expected_commit="a" * 40))
            self.assert_code("manifest_commit", lambda: package.verify(
                archive, expected_sha256=digest, expected_commit="c" * 40))
            changed = root / "changed-legacy.zip"
            changed_digest = self.rewrite(archive, changed, lambda entries: [
                (name, b"tampered\n" if name == "libexec/steam.py" else data, mode)
                for name, data, mode in entries])
            self.assert_code("payload_digest", lambda: package.verify(
                changed, expected_sha256=changed_digest, expected_commit="a" * 40))

    def test_schema_and_membership_must_match_exactly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current, _digest = self.build_archive(root)
            legacy, _digest = self.legacy_archive(root)
            for archive, schemas in ((current, ("orla-launcher-package-0.2",)),
                                     (legacy, ("orla-launcher-package-0.3",)),
                                     (current, ("orla-launcher-package-0.4", None, []))):
                for index, schema in enumerate(schemas):
                    with self.subTest(archive=archive.name, schema=schema):
                        def transform(entries):
                            output = []
                            for name, data, mode in entries:
                                if name == "manifest.json":
                                    value = json.loads(data)
                                    value["schema"] = schema
                                    data = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
                                output.append((name, data, mode))
                            return output
                        candidate = root / f"mixed-{archive.stem}-{index}.zip"
                        digest = self.rewrite(archive, candidate, transform)
                        self.assert_code("manifest_identity", lambda: package.verify(
                            candidate, expected_sha256=digest, expected_commit="a" * 40))

    def test_each_helper_missing_tampered_extra_or_wrong_mode_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            archive, _digest = self.build_archive(root, stage=stage)
            helpers = ("ai.py", "steam.py", "ai_text_ollama.py", "ai_text_transport.py", "ai_text.py")
            for helper in helpers:
                with self.subTest(helper=helper):
                    path = stage / "libexec" / helper
                    content = path.read_bytes()
                    path.unlink()
                    self.assert_code("staging_layout", lambda: self.build_archive(root, stage=stage))
                    path.write_bytes(content)
                    os.chmod(path, 0o755)
                    self.assert_code("staging_file", lambda: self.build_archive(root, stage=stage))
                    os.chmod(path, 0o644)
                    relative = "libexec/" + helper
                    cases = (
                        ("missing", "zip_members", lambda entries: [item for item in entries if item[0] != relative]),
                        ("tampered", "payload_digest", lambda entries: [
                            (name, b"tampered\n" if name == relative else data, mode)
                            for name, data, mode in entries]),
                        ("extra", "zip_members", lambda entries: entries + [(relative + ".extra", b"x", 0o644)]),
                        ("mode", "zip_mode", lambda entries: [
                            (name, data, 0o755 if name == relative else mode) for name, data, mode in entries]),
                    )
                    for suffix, code, transform in cases:
                        candidate = root / f"{helper}-{suffix}.zip"
                        digest = self.rewrite(archive, candidate, transform)
                        self.assert_code(code, lambda: package.verify(
                            candidate, expected_sha256=digest, expected_commit="a" * 40))
                    extra_path = path.with_suffix(".py.extra")
                    extra_path.write_bytes(b"x")
                    self.assert_code("staging_layout", lambda: self.build_archive(root, stage=stage))
                    extra_path.unlink()

    def test_byte_change_changes_digest_and_readonly_stage_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            before = {path.relative_to(stage): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                      for path in stage.rglob("*") if path.is_file()}
            os.chmod(stage / "bin", 0o555)
            os.chmod(stage / "libexec", 0o555)
            os.chmod(stage, 0o555)
            try:
                first, first_digest = self.build_archive(root, stage=stage, output_name="one.zip")
                verified = package.verify(first, expected_sha256=first_digest, expected_commit="a" * 40)
                self.assertEqual(verified["runtime_inventory"]["source"], "caller_assertion_unverified")
                after = {path.relative_to(stage): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                         for path in stage.rglob("*") if path.is_file()}
                self.assertEqual(before, after)
            finally:
                os.chmod(stage, 0o755)
                os.chmod(stage / "bin", 0o755)
                os.chmod(stage / "libexec", 0o755)
            (stage / "libexec/ai.py").write_bytes(b"# changed byte\n")
            os.chmod(stage / "libexec/ai.py", 0o644)
            _second, second_digest = self.build_archive(root, stage=stage, output_name="two.zip")
            self.assertNotEqual(first_digest, second_digest)

    def test_wrong_external_digest_stops_before_zip_parser_or_payload_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, _digest = self.build_archive(root)
            with mock.patch.object(package.zipfile, "ZipFile", side_effect=AssertionError("ZIP was opened")):
                self.assert_code("archive_digest", lambda: package.verify(
                    archive, expected_sha256="0" * 64, expected_commit="a" * 40))

    def test_verify_never_extracts_or_writes_and_rejects_payload_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, digest = self.build_archive(root)
            names_before = sorted(path.relative_to(root) for path in root.rglob("*"))
            with mock.patch.object(zipfile.ZipFile, "extract", side_effect=AssertionError("extract")), \
                    mock.patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("extractall")):
                package.verify(archive, expected_sha256=digest, expected_commit="a" * 40)
            self.assertEqual(names_before, sorted(path.relative_to(root) for path in root.rglob("*")))

            changed = root / "changed.zip"
            changed_digest = self.rewrite(archive, changed, lambda entries: [
                (name, b"changed\n" if name == "libexec/ai.py" else data, mode)
                for name, data, mode in entries
            ])
            self.assert_code("payload_digest", lambda: package.verify(
                changed, expected_sha256=changed_digest, expected_commit="a" * 40))

    def test_builder_rejects_extra_symlink_mode_and_search_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            (stage / "private").write_text("must not ship", encoding="utf-8")
            self.assert_code("staging_layout", lambda: self.build_archive(root, stage=stage))
            (stage / "private").unlink()

            helper = stage / "libexec/ai.py"
            helper.unlink()
            helper.symlink_to(root / "outside")
            self.assert_code("staging_file", lambda: self.build_archive(root, stage=stage))
            helper.unlink()
            helper.write_text("helper\n", encoding="utf-8")
            os.chmod(helper, 0o600)
            self.assert_code("staging_file", lambda: self.build_archive(root, stage=stage))
            os.chmod(helper, 0o644)
            helper.write_bytes(b"")
            self.assert_code("staging_file", lambda: self.build_archive(root, stage=stage))
            helper.write_text("helper\n", encoding="utf-8")

            (stage / "bin/orla-launcher").write_bytes(synthetic_elf(runpath=("/checkout/build",)))
            os.chmod(stage / "bin/orla-launcher", 0o755)
            inventory = runtime_inventory()
            inventory["elf_direct"]["runpath"] = ["/checkout/build"]
            self.assert_code("elf_search_path", lambda: self.build_archive(
                root, stage=stage, inventory=inventory))

    def test_output_cannot_mutate_staging_and_archive_symlink_is_not_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            self.assert_code("output_path", lambda: package.build(
                stage,
                stage / "package.zip",
                version="0.1.0",
                commit="a" * 40,
                ci_image_digest="sha256:" + "b" * 64,
                runtime_inventory=runtime_inventory(),
            ))
            self.assertFalse((stage / "package.zip").exists())
            archive, digest = self.build_archive(root, stage=stage)
            os.chmod(archive, 0o755)
            self.assert_code("archive_file", lambda: package.verify(
                archive, expected_sha256=digest, expected_commit="a" * 40))
            os.chmod(archive, 0o644)
            link = root / "archive-link.zip"
            link.symlink_to(archive)
            self.assert_code("archive_file", lambda: package.verify(
                link, expected_sha256=digest, expected_commit="a" * 40))

    def test_build_failure_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            output = root / "existing.zip"
            output.write_bytes(b"existing data\n")
            with mock.patch.object(package, "MAX_ARCHIVE_BYTES", 1):
                self.assert_code("archive_file", lambda: package.build(
                    stage,
                    output,
                    version="0.1.0",
                    commit="a" * 40,
                    ci_image_digest="sha256:" + "b" * 64,
                    runtime_inventory=runtime_inventory(),
                ))
            self.assertEqual(output.read_bytes(), b"existing data\n")
            self.assertEqual([item.name for item in root.iterdir() if item.name.startswith(".orla-package-")], [])

    def test_manifest_is_closed_and_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, _digest = self.build_archive(root)
            with zipfile.ZipFile(archive) as source:
                original_manifest = source.read("manifest.json")

            extra = root / "extra.zip"
            value = json.loads(original_manifest)
            value["unexpected"] = True
            extra_digest = self.rewrite(archive, extra, lambda entries: [
                (name, (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
                 if name == "manifest.json" else data, mode)
                for name, data, mode in entries
            ])
            self.assert_code("manifest_schema", lambda: package.verify(
                extra, expected_sha256=extra_digest, expected_commit="a" * 40))

            duplicate = root / "duplicate-key.zip"
            duplicate_manifest = original_manifest.replace(b'{"channel":', b'{"channel":"experimental","channel":', 1)
            duplicate_digest = self.rewrite(archive, duplicate, lambda entries: [
                (name, duplicate_manifest if name == "manifest.json" else data, mode)
                for name, data, mode in entries
            ])
            self.assert_code("manifest_duplicate_key", lambda: package.verify(
                duplicate, expected_sha256=duplicate_digest, expected_commit="a" * 40))

            wrong_type = root / "wrong-type.zip"
            value = json.loads(original_manifest)
            value["files"][0]["size"] = True
            wrong_type_digest = self.rewrite(archive, wrong_type, lambda entries: [
                (name, (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
                 if name == "manifest.json" else data, mode)
                for name, data, mode in entries
            ])
            self.assert_code("manifest_file", lambda: package.verify(
                wrong_type, expected_sha256=wrong_type_digest, expected_commit="a" * 40))
            self.assert_code("manifest_commit", lambda: package.verify(
                archive, expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                expected_commit="c" * 40))

    def test_zip_rejects_names_duplicates_types_modes_metadata_and_expansion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, _digest = self.build_archive(root)

            cases = (
                ("traversal.zip", lambda entries: [("../orla", data, mode) if index == 0 else (name, data, mode)
                                                    for index, (name, data, mode) in enumerate(entries)], "zip_name"),
                ("empty-component.zip", lambda entries: [("bin//orla", data, mode) if index == 0 else (name, data, mode)
                                                          for index, (name, data, mode) in enumerate(entries)], "zip_name"),
                ("backslash.zip", lambda entries: [("bin\\orla", data, mode) if index == 0 else (name, data, mode)
                                                   for index, (name, data, mode) in enumerate(entries)], "zip_name"),
                ("duplicate.zip", lambda entries: entries[:-1] + [(entries[0][0], entries[-1][1], 0o644)],
                 "zip_duplicate"),
                ("extra.zip", lambda entries: entries + [("extra", b"x", 0o644)], "zip_members"),
            )
            for filename, transform, code in cases:
                candidate = root / filename
                digest = self.rewrite(archive, candidate, transform)
                self.assert_code(code, lambda candidate=candidate, digest=digest: package.verify(
                    candidate, expected_sha256=digest, expected_commit="a" * 40))

            with zipfile.ZipFile(archive) as source:
                entries = [(info.filename, source.read(info), stat.S_IMODE(info.external_attr >> 16))
                           for info in source.infolist()]
            symlink = root / "symlink.zip"
            with zipfile.ZipFile(symlink, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for index, (name, data, mode) in enumerate(entries):
                    info = self.independent_info(name, mode, kind=stat.S_IFLNK if index == 0 else stat.S_IFREG)
                    output.writestr(info, data)
            digest = hashlib.sha256(symlink.read_bytes()).hexdigest()
            self.assert_code("zip_mode", lambda: package.verify(
                symlink, expected_sha256=digest, expected_commit="a" * 40))

            fifo = root / "fifo.zip"
            with zipfile.ZipFile(fifo, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for index, (name, data, mode) in enumerate(entries):
                    info = self.independent_info(name, mode, kind=stat.S_IFIFO if index == 0 else stat.S_IFREG)
                    output.writestr(info, data)
            digest = hashlib.sha256(fifo.read_bytes()).hexdigest()
            self.assert_code("zip_mode", lambda: package.verify(
                fifo, expected_sha256=digest, expected_commit="a" * 40))

            wrong_mode = root / "wrong-mode.zip"
            digest = self.rewrite(archive, wrong_mode, lambda source_entries: [
                (name, data, 0o777 if index == 0 else mode)
                for index, (name, data, mode) in enumerate(source_entries)
            ])
            self.assert_code("zip_mode", lambda: package.verify(
                wrong_mode, expected_sha256=digest, expected_commit="a" * 40))

            timestamp = root / "timestamp.zip"
            with zipfile.ZipFile(timestamp, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for index, (name, data, mode) in enumerate(entries):
                    info = self.independent_info(name, mode, timestamp=(2026, 1, 1, 0, 0, 0) if index == 0 else (1980, 1, 1, 0, 0, 0))
                    output.writestr(info, data)
            digest = hashlib.sha256(timestamp.read_bytes()).hexdigest()
            self.assert_code("zip_metadata", lambda: package.verify(
                timestamp, expected_sha256=digest, expected_commit="a" * 40))

            expansion = root / "expansion.zip"
            expansion_digest = self.rewrite(archive, expansion, lambda source_entries: [
                (name, b"0" * 500_000 if name == "LICENSE" else data, mode)
                for name, data, mode in source_entries
            ])
            self.assert_code("zip_expansion", lambda: package.verify(
                expansion, expected_sha256=expansion_digest, expected_commit="a" * 40))

            manifest_limit = root / "manifest-limit.zip"
            digest = self.rewrite(archive, manifest_limit, lambda source_entries: [
                (name, b"x" * (64 * 1024 + 1) if name == "manifest.json" else data, mode)
                for name, data, mode in source_entries
            ])
            self.assert_code("manifest_limit", lambda: package.verify(
                manifest_limit, expected_sha256=digest, expected_commit="a" * 40))

            member_limit = root / "member-limit.zip"
            digest = self.rewrite(archive, member_limit, lambda source_entries: [
                (name, b"x" * (64 * 1024 * 1024 + 1) if name == "LICENSE" else data, mode)
                for name, data, mode in source_entries
            ])
            self.assert_code("member_limit", lambda: package.verify(
                member_limit, expected_sha256=digest, expected_commit="a" * 40))

    def test_crc_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, _digest = self.build_archive(root)
            corrupted = root / "corrupted.zip"
            raw = bytearray(archive.read_bytes())
            with zipfile.ZipFile(io.BytesIO(raw)) as parsed:
                info = parsed.getinfo("libexec/ai.py")
            name_length, extra_length = struct.unpack_from("<HH", raw, info.header_offset + 26)
            data_offset = info.header_offset + 30 + name_length + extra_length
            raw[data_offset + max(0, info.compress_size // 2)] ^= 1
            corrupted.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.assert_code("zip_crc", lambda: package.verify(
                corrupted, expected_sha256=digest, expected_commit="a" * 40))

    def test_raw_nul_member_name_is_rejected_before_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, _digest = self.build_archive(root)
            changed = root / "raw-nul.zip"
            self.rewrite(archive, changed, lambda entries: [
                ("LICENSEXevil" if name == "LICENSE" else name, data, mode)
                for name, data, mode in entries
            ])
            raw = changed.read_bytes().replace(b"LICENSEXevil", b"LICENSE\0evil")
            self.assertEqual(raw.count(b"LICENSE\0evil"), 2)
            changed.write_bytes(raw)
            self.assert_code("zip_name", lambda: package.verify(
                changed, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_commit="a" * 40))

    def test_actual_deflate_output_cannot_exceed_declared_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, _digest = self.build_archive(root)
            with zipfile.ZipFile(archive) as source:
                original = source.read("libexec/ai.py")
            changed = root / "excess-output.zip"
            self.rewrite(archive, changed, lambda entries: [
                (name, data + b"SMUGGLED" if name == "libexec/ai.py" else data, mode)
                for name, data, mode in entries
            ])
            raw = bytearray(changed.read_bytes())
            position = 0
            while True:
                position = raw.find(b"PK\x01\x02", position)
                self.assertGreaterEqual(position, 0)
                name_size, extra_size, comment_size = struct.unpack_from("<HHH", raw, position + 28)
                name = raw[position + 46:position + 46 + name_size]
                if name == b"libexec/ai.py":
                    local = struct.unpack_from("<I", raw, position + 42)[0]
                    struct.pack_into("<I", raw, position + 16, zlib.crc32(original))
                    struct.pack_into("<I", raw, position + 24, len(original))
                    struct.pack_into("<I", raw, local + 14, zlib.crc32(original))
                    struct.pack_into("<I", raw, local + 22, len(original))
                    local_name_size, local_extra_size = struct.unpack_from("<HH", raw, local + 26)
                    compressed_size = struct.unpack_from("<I", raw, local + 18)[0]
                    data_offset = local + 30 + local_name_size + local_extra_size
                    self.assertEqual(zlib.decompress(raw[data_offset:data_offset + compressed_size], -15),
                                     original + b"SMUGGLED")
                    break
                position += 46 + name_size + extra_size + comment_size
            changed.write_bytes(raw)
            with self.assertRaises(package.PackageError):
                package.verify(changed, expected_sha256=hashlib.sha256(raw).hexdigest(),
                               expected_commit="a" * 40)

    def test_builder_expansion_failure_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            (stage / "LICENSE").write_bytes(b"0" * 500_000)
            output = root / "existing.zip"
            output.write_bytes(b"existing data\n")
            with self.assertRaises(package.PackageError):
                package.build(stage, output, version="0.1.0", commit="a" * 40,
                              ci_image_digest="sha256:" + "b" * 64,
                              runtime_inventory=runtime_inventory())
            self.assertEqual(output.read_bytes(), b"existing data\n")

    def test_builder_total_cap_includes_manifest_and_preserves_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            payload_size = sum((stage / name).stat().st_size for name, _mode in package.PAYLOAD)
            output = root / "existing.zip"
            output.write_bytes(b"existing data\n")
            with mock.patch.object(package, "MAX_TOTAL_BYTES", payload_size):
                with self.assertRaises(package.PackageError):
                    package.build(stage, output, version="0.1.0", commit="a" * 40,
                                  ci_image_digest="sha256:" + "b" * 64,
                                  runtime_inventory=runtime_inventory())
            self.assertEqual(output.read_bytes(), b"existing data\n")

    def test_elf_parser_is_bounded_and_inventory_must_match(self):
        parsed = package.parse_elf(synthetic_elf(needed=("libA.so.1", "libB.so.2")))
        self.assertEqual(parsed["needed"], ["libA.so.1", "libB.so.2"])
        self.assertEqual(parsed["rpath"], [])
        self.assertEqual(parsed["runpath"], [])
        self.assert_code("elf_malformed", lambda: package.parse_elf(b"\x7fELF"))
        unsupported = bytearray(synthetic_elf())
        unsupported[4] = 1
        self.assert_code("elf_unsupported", lambda: package.parse_elf(bytes(unsupported)))
        self.assertEqual(package.parse_elf(synthetic_elf(rpath=("/tmp/build",)))["rpath"], ["/tmp/build"])

        inventory = runtime_inventory()
        inventory["elf_direct"]["needed"][0]["soname"] = "libWrong.so.1"
        self.assert_code("inventory_elf_mismatch", lambda: package.validate_runtime_inventory(
            inventory, package.parse_elf(synthetic_elf())))
        inventory = runtime_inventory()
        inventory["dynamic_assets"] = inventory["dynamic_assets"][1:]
        self.assert_code("inventory_assets", lambda: package.validate_runtime_inventory(inventory))
        for role in {item["role"] for item in runtime_inventory()["dynamic_assets"]}:
            inventory = runtime_inventory()
            inventory["dynamic_assets"] = [item for item in inventory["dynamic_assets"] if item["role"] != role]
            self.assert_code("inventory_assets", lambda inventory=inventory: package.validate_runtime_inventory(inventory))
        inventory = runtime_inventory()
        inventory["elf_direct"]["needed"].append(dependency("libQt6Core.so.6"))
        self.assert_code("inventory_dependency", lambda: package.validate_runtime_inventory(inventory))
        inventory = runtime_inventory()
        del inventory["elf_direct"]["needed"][0]["owner"]
        self.assert_code("inventory_dependency", lambda: package.validate_runtime_inventory(inventory))

    def test_build_and_verify_commands_use_only_explicit_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            inventory_path = root / "inventory.json"
            inventory_path.write_text(json.dumps(runtime_inventory()), encoding="utf-8")
            archive = root / "command package.zip"
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                self.assertEqual(package.main([
                    "build", str(stage), str(archive), "--version", "0.1.0",
                    "--commit", "a" * 40, "--ci-image-digest", "sha256:" + "b" * 64,
                    "--runtime-inventory", str(inventory_path),
                ]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "ok")
            output = io.StringIO()
            with mock.patch("sys.stdout", output):
                self.assertEqual(package.main([
                    "verify", str(archive), "--sha256", result["sha256"], "--commit", "a" * 40,
                ]), 0)
            self.assertEqual(json.loads(output.getvalue()), {
                "status": "ok", "commit": "a" * 40, "schema": "orla-launcher-package-0.3",
            })


class DoctorTests(unittest.TestCase):
    required = {
        "qpa_wayland", "qml_qtquick_plugin", "qml_controls_plugin", "qml_controls_qmldir",
        "qml_layouts_plugin", "krunner_services", "krunner_calculator",
    }

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.routes = dict(package._EXACT_ASSET_PATHS)
        self.optional = {
            "style_fusion": "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/qmldir",
            "style_kde": "/usr/lib64/qt6/qml/org/kde/desktop/qmldir",
            "bwrap": "/usr/bin/bwrap",
        }
        self.logical = {}
        for role, path in {**self.routes, **self.optional}.items():
            target = self.root / role
            content = (b"module QtQuick.Controls\n" if role == "qml_controls_qmldir" else
                       b"module QtQuick.Controls.Fusion\n" if role == "style_fusion" else
                       b"module org.kde.desktop\n" if role == "style_kde" else synthetic_elf())
            target.write_bytes(content)
            self.logical[path] = target
        self.processes, self.commands = [], []
        self.rpm_output = b"synthetic-qt\t0\t6.11.2\t1.fc44\tx86_64\n"
        self.rpm_exit = 0
        self.rpm_timeout = False
        self.clock = 100.0
        self.spawn_error = False
        self.wait_timeout = False
        self.after_spawn = None
        self.require_readonly_flags = False

    def doctor(self):
        original_open, original_lstat, original_read = os.open, os.lstat, os.read
        def mapped(path):
            # Unknown host/personal paths must never be touched by this test.
            self.assertIn(os.fsdecode(path), self.logical)
            return self.logical[os.fsdecode(path)]
        def open_file(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR | os.O_TRUNC))
            return original_open(mapped(path), flags, *args, **kwargs)
        def popen(command, **kwargs):
            self.commands.append((command, kwargs))
            if self.spawn_error: raise OSError("synthetic executable unavailable")
            if self.after_spawn: self.after_spawn(command[command.index("--file") + 1])
            process = mock.Mock()
            process.stdout.fileno.return_value = 910007
            process.wait.return_value = self.rpm_exit
            if self.wait_timeout: process.wait.side_effect = subprocess.TimeoutExpired(command, 2)
            process.output = self.rpm_output
            if self.require_readonly_flags and not {"--nosignature", "--nohdrchk"}.issubset(command):
                process.output = (b"warning: unknown keyring type: , using rpmdb\n"
                                  b"error: can't create transaction lock on // (Is a directory)\n" + self.rpm_output)
            process.cursor = 0
            self.processes.append(process)
            return process
        def read(fd, count):
            if fd != 910007: return original_read(fd, count)
            process = self.processes[-1]
            data = process.output[process.cursor:process.cursor + count]
            process.cursor += len(data)
            return data
        def select(timeout):
            if self.rpm_timeout: self.clock += timeout + 0.1; return []
            return [(SimpleNamespace(fileobj=self.processes[-1].stdout), 1)]
        selector = mock.MagicMock()
        selector.__enter__.return_value = selector
        selector.select.side_effect = select
        output = io.StringIO()
        # ALL external process creation is mocked; these tests never invoke RPM.
        with mock.patch("subprocess.Popen", side_effect=popen), \
             mock.patch("subprocess.run", side_effect=AssertionError("unexpected process API")), \
             mock.patch("os.open", side_effect=open_file), \
             mock.patch("os.lstat", side_effect=lambda path: original_lstat(mapped(path))), \
             mock.patch("os.read", side_effect=read), \
             mock.patch("selectors.DefaultSelector", return_value=selector), \
             mock.patch("time.monotonic", side_effect=lambda: self.clock), \
             mock.patch("sys.stdout", output):
            code = package.main(["doctor"])
        return code, json.loads(output.getvalue())

    def test_complete_fixed_assets_reports_metadata_not_runtime_health_and_never_writes(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in self.root.iterdir()}
        code, result = self.doctor()
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["target"], "fedora44-x86_64")
        self.assertEqual(result["scope"], "fixed_assets_metadata_only")
        self.assertEqual({x["role"] for x in result["checks"]}, self.required)
        self.assertTrue(all(x["state"] == "found" for x in result["checks"]))
        self.assertIn("no_library_loading", result["limitations"])
        self.assertIn("no_transitive_closure", result["limitations"])
        self.assertIn("not_runtime_inventory", result["limitations"])
        self.assertNotIn("runtime_inventory", result)
        with self.assertRaises(package.PackageError) as invalid_inventory:
            package.validate_runtime_inventory(result)
        self.assertEqual(invalid_inventory.exception.code, "inventory_schema")
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in self.root.iterdir()})
        for command, options in self.commands:
            self.assertEqual(command[0], "/usr/bin/rpm")
            self.assertIn("--query", command); self.assertIn("--file", command)
            self.assertEqual(command[command.index("--rcfile") + 1], "/dev/null")
            self.assertEqual(command[command.index("--macros") + 1], "/dev/null")
            self.assertEqual(command[command.index("--dbpath") + 1], "/var/lib/rpm")
            self.assertIn("--noplugins", command)
            self.assertNotIn("shell", options)
            self.assertEqual(options["env"]["HOME"], "/dev/null")
            self.assertEqual(options["cwd"], "/")
        for process in self.processes:
            process.wait.assert_called(); process.stdout.close.assert_called()

    def test_readonly_query_avoids_keyring_lock_path_without_discarding_diagnostics(self):
        # Model the pinned RPM6.0.2 CLI/verification/keyring path and Root's
        # preserved R1 warning. No RPM invocation or library is executed here.
        self.require_readonly_flags = True
        code, result = self.doctor()
        self.assertEqual(code, 0)
        self.assertTrue(all(x["state"] == "found" for x in result["checks"]))
        self.assertIn("rpm_ownership_not_integrity", result["limitations"])
        for command, _options in self.commands:
            self.assertIn("--nosignature", command)
            self.assertIn("--nohdrchk", command)
            self.assertNotIn("--define", command)
            self.assertNotIn("_rpmlock_path", " ".join(command))
        # A different diagnostic despite these flags still refuses metadata.
        self.rpm_output = b"warning: synthetic RPM diagnostic\n" + self.rpm_output
        code, result = self.doctor()
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(all(x["state"] == "unknown" for x in result["checks"]))

    def test_required_missing_is_distinct_from_optional_missing(self):
        for role in self.optional: self.logical[self.optional[role]].unlink()
        code, result = self.doctor()
        self.assertEqual(code, 0)
        self.assertEqual({x["state"] for x in result["capabilities"]}, {"missing"})
        self.logical[self.routes["krunner_calculator"]].unlink()
        code, result = self.doctor()
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "missing")
        by_role = {x["role"]: x for x in result["checks"]}
        self.assertEqual(by_role["krunner_calculator"]["state"], "missing")
        self.assertEqual(by_role["krunner_services"]["state"], "found")

    def test_unsafe_malformed_oversized_or_incompatible_assets_are_unknown(self):
        role = "qml_controls_plugin"; asset = self.logical[self.routes[role]]
        original = asset.read_bytes()
        for content in [b"not ELF", bytes(original[:18] + b"\x03\x00" + original[20:]), bytes(original[:16] + b"\x02\x00" + original[18:])]:
            with self.subTest(kind=len(content)):
                asset.write_bytes(content)
                code, result = self.doctor()
                self.assertEqual(code, 2); self.assertEqual(result["status"], "unknown")
                self.assertEqual(next(x for x in result["checks"] if x["role"] == role)["state"], "unknown")
        with asset.open("wb") as oversized: oversized.truncate(64 * 1024 * 1024 + 1)
        self.assertEqual(self.doctor()[0], 2)
        asset.unlink(); referent = self.root / "referent"; referent.write_bytes(original); asset.symlink_to(referent)
        code, result = self.doctor()
        self.assertEqual(code, 2); self.assertEqual(referent.read_bytes(), original)
        asset.unlink(); asset.write_bytes(original)
        self.logical[self.routes["qml_controls_qmldir"]].write_bytes(b"module Other.Module\n")
        self.assertEqual(self.doctor()[0], 2)

    def test_rpm_unknown_ambiguous_timeout_and_overflow_do_not_claim_found(self):
        for output, exit_code, timeout in [
            (b"owner missing", 1, False), (self.rpm_output * 2, 0, False),
            (b"owner\t0\t6.11.2\t1.fc44\tother\n", 0, False),
            (b"x" * 16385, 0, False), (b"", 0, True),
        ]:
            with self.subTest(output=len(output), exit=exit_code, timeout=timeout):
                self.rpm_output, self.rpm_exit, self.rpm_timeout = output, exit_code, timeout
                self.processes, self.commands = [], []
                code, result = self.doctor()
                self.assertEqual(code, 2); self.assertEqual(result["status"], "unknown")
                self.assertTrue(all(x["state"] == "unknown" for x in result["checks"]))
                if timeout or len(output) > 16384:
                    for process in self.processes: process.kill.assert_called_once(); process.wait.assert_called()

    def test_unavailable_rpm_or_unconfirmed_owned_cleanup_remains_unknown(self):
        self.spawn_error = True
        code, result = self.doctor()
        self.assertEqual(code, 2)
        self.assertEqual({x["code"] for x in result["checks"]}, {"rpm_unavailable"})
        self.spawn_error = False; self.wait_timeout = True
        self.processes, self.commands = [], []
        code, result = self.doctor()
        self.assertEqual(code, 2)
        self.assertEqual({x["code"] for x in result["checks"]}, {"rpm_cleanup_unknown"})
        for process in self.processes:
            process.kill.assert_called_once()
            self.assertEqual(process.wait.call_count, 2)
            process.stdout.close.assert_called_once()

    def test_asset_drift_during_metadata_query_is_not_reported_found(self):
        path = self.routes["qml_controls_plugin"]
        def drift(selected):
            if selected == path:
                asset = self.logical[path]
                asset.write_bytes(asset.read_bytes() + b"changed")
        self.after_spawn = drift
        code, result = self.doctor()
        self.assertEqual(code, 2)
        record = next(x for x in result["checks"] if x["role"] == "qml_controls_plugin")
        self.assertEqual(record["state"], "unknown")
        self.assertEqual(record["code"], "asset_changed")
        self.assertTrue(all(x["state"] == "found" for x in result["checks"] if x["role"] != record["role"]))

    def test_optional_unknown_metadata_does_not_block_core_or_become_required(self):
        self.logical[self.optional["style_kde"]].write_bytes(b"not a qmldir\n")
        code, result = self.doctor()
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "ok")
        kde = next(x for x in result["capabilities"] if x["role"] == "style_kde")
        self.assertEqual(kde["state"], "unknown")
        self.assertEqual(package.validate_runtime_inventory(runtime_inventory())["source"], "caller_assertion_unverified")


if __name__ == "__main__":
    unittest.main()
