import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
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
        (stage / "LICENSE").write_bytes(b"synthetic license\n")
        os.chmod(stage / "bin/orla-launcher", 0o755)
        for name in ("libexec/ai.py", "libexec/steam.py", "LICENSE"):
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
            self.assertEqual(manifest["schema"], "orla-launcher-package-0.2")
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), [
                    "bin/orla-launcher", "libexec/ai.py", "libexec/steam.py", "LICENSE",
                    "manifest.json",
                ])

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

    def test_doctor_is_explicitly_unsupported_without_subprocess_support(self):
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            self.assertEqual(package.main(["doctor"]), 2)
        self.assertEqual(json.loads(output.getvalue()), {"status": "error", "code": "unsupported_doctor"})
        self.assertNotIn("subprocess", package.__dict__)

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
                "status": "ok", "commit": "a" * 40, "schema": "orla-launcher-package-0.2",
            })


if __name__ == "__main__":
    unittest.main()
