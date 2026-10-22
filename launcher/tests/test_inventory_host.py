import copy
import hashlib
import importlib
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock


LAUNCHER = Path(__file__).resolve().parents[1]
_original_path = list(sys.path)
try:
    sys.path.insert(0, str(LAUNCHER))
    package = importlib.import_module("package")
    policy = importlib.import_module("inventory_policy")
    host = importlib.import_module("inventory_host")
finally:
    sys.path[:] = _original_path


def synthetic_elf(needed=(), *, main=False):
    base, interp_offset, string_offset, dynamic_offset = 0x400000, 0x200, 0x280, 0x380
    strings = bytearray(b"\0")
    offsets = []
    for name in needed:
        offsets.append(len(strings))
        strings.extend(name.encode("ascii") + b"\0")
    entries = [(5, base + string_offset), (10, len(strings))]
    entries += [(1, offset) for offset in offsets] + [(0, 0)]
    dynamic = b"".join(struct.pack("<qQ", *entry) for entry in entries)
    size = dynamic_offset + len(dynamic)
    data = bytearray(size)
    data[:64] = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + b"\0" * 9,
                            3, 62, 1, 0, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    interpreter = b"/lib64/ld-linux-x86-64.so.2\0"
    headers = [(1, 5, 0, base, base, size, size, 0x1000),
               (3 if main else 0, 4, interp_offset, base + interp_offset, base + interp_offset,
                len(interpreter), len(interpreter), 1),
               (2, 4, dynamic_offset, base + dynamic_offset, base + dynamic_offset,
                len(dynamic), len(dynamic), 8)]
    for index, header in enumerate(headers):
        data[64 + index * 56:64 + (index + 1) * 56] = struct.pack("<IIQQQQQQ", *header)
    data[interp_offset:interp_offset + len(interpreter)] = interpreter
    data[string_offset:string_offset + len(strings)] = strings
    data[dynamic_offset:dynamic_offset + len(dynamic)] = dynamic
    return bytes(data)


class OwnedOperations:
    """Actual descriptor operations confined to an owned synthetic / namespace."""
    def __init__(self, namespace, rpm_paths):
        self.namespace = namespace
        self.rpm_paths = set(rpm_paths)
        self.opened = {}
        self.calls = []
        self.rpm_calls = []
        self.closed = []

    def _operand(self, path, dir_fd):
        value = str(path)
        if value == "/" and dir_fd is None:
            return self.namespace, "/"
        if dir_fd not in self.opened or not value or "/" in value or value in (".", ".."):
            raise AssertionError("unapproved namespace operand: " + value)
        parent = self.opened[dir_fd]
        logical = parent.rstrip("/") + "/" + value
        return value, logical

    def open(self, path, flags, *, dir_fd=None):
        physical, logical = self._operand(path, dir_fd)
        descriptor = os.open(physical, flags, **({"dir_fd": dir_fd} if dir_fd is not None else {}))
        if descriptor in self.opened:
            raise AssertionError("descriptor identity reused before close")
        self.opened[descriptor] = logical
        self.calls.append(("open", logical, flags))
        return descriptor

    def stat(self, path, *, dir_fd=None, follow_symlinks=False):
        physical, logical = self._operand(path, dir_fd)
        self.calls.append(("stat", logical, follow_symlinks))
        if follow_symlinks:
            raise AssertionError("namespace stat cannot follow links")
        return os.stat(physical, dir_fd=dir_fd, follow_symlinks=False)

    def fstat(self, descriptor):
        if descriptor not in self.opened: raise AssertionError("foreign descriptor")
        self.calls.append(("fstat", self.opened[descriptor]))
        return os.fstat(descriptor)

    def scandir(self, descriptor):
        if descriptor not in self.opened: raise AssertionError("foreign directory descriptor")
        logical = self.opened[descriptor]
        if logical not in ("/synthetic-stage", "/synthetic-stage/bin", "/synthetic-stage/libexec"):
            raise AssertionError("undeclared directory enumeration: " + logical)
        self.calls.append(("scandir", logical))
        return os.scandir(descriptor)

    def read(self, descriptor, count):
        if descriptor not in self.opened: raise AssertionError("foreign content descriptor")
        self.calls.append(("read", self.opened[descriptor], count))
        return os.read(descriptor, count)

    def readlink(self, path, *, dir_fd):
        if path != "" or dir_fd not in self.opened:
            raise AssertionError("readlink must bind to owned symlink descriptor")
        self.calls.append(("readlink", self.opened[dir_fd]))
        return os.readlink("", dir_fd=dir_fd)

    def close(self, descriptor):
        if descriptor not in self.opened: raise AssertionError("double/foreign close")
        self.closed.append(self.opened[descriptor])
        os.close(descriptor)
        del self.opened[descriptor]

    def monotonic(self):
        return time.monotonic()

    def rpm(self, path):
        if path not in self.rpm_paths:
            raise AssertionError("undeclared mocked RPM query: " + path)
        self.rpm_calls.append(path)
        return {"owner": "synthetic-runtime", "version": "1.0",
                "nevra": "synthetic-runtime-0:1.0-1.fc44.x86_64"}


class HostCatalogTracerTests(unittest.TestCase):
    def test_owned_stage_alias_endpoint_and_transitive_elf_form_observed_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            namespace = Path(temporary) / "owned-namespace"
            stage = Path("/synthetic-stage")
            physical_stage = namespace / "synthetic-stage"
            (physical_stage / "bin").mkdir(parents=True)
            (physical_stage / "libexec").mkdir()
            main_data = synthetic_elf(["libSynthetic.so.1"], main=True)
            for relative, mode in package.PAYLOAD:
                path = physical_stage / relative
                path.write_bytes(main_data if relative == "bin/orla-launcher" else b"owned synthetic payload\n")
                os.chmod(path, mode)
            fixed = [(role, path) for role, path in sorted(package._EXACT_ASSET_PATHS.items())
                     if role != "qml_controls_qmldir"]
            for role, path in fixed:
                physical = namespace / path.lstrip("/")
                physical.parent.mkdir(parents=True, exist_ok=True)
                physical.write_bytes(synthetic_elf())
                os.chmod(physical, 0o644)
            alias = "/usr/lib64/libSynthetic.so.1"
            endpoint = "/usr/lib64/libSynthetic.so.1.0"
            transitive = "/usr/lib64/libTransitive.so"
            endpoint_data = synthetic_elf(["libTransitive.so"])
            transitive_data = synthetic_elf()
            (namespace / endpoint.lstrip("/")).write_bytes(endpoint_data)
            (namespace / transitive.lstrip("/")).write_bytes(transitive_data)
            (namespace / alias.lstrip("/")).symlink_to("libSynthetic.so.1.0")
            snapshot = {str(path.relative_to(namespace)): (stat.S_IMODE(path.lstat().st_mode),
                        os.readlink(path) if path.is_symlink() else path.read_bytes())
                        for path in namespace.rglob("*") if path.is_symlink() or path.is_file()}
            ops = OwnedOperations(namespace, [path for _role, path in fixed] + [alias, endpoint, transitive])
            with mock.patch.object(host, "_Operations", return_value=ops, create=True), \
                 mock.patch.object(package, "_doctor_rpm", side_effect=AssertionError("real RPM forbidden")), \
                 mock.patch("subprocess.Popen", side_effect=AssertionError("process execution forbidden")):
                result = host.collect_host_catalog(stage)

            self.assertEqual(result["schema"], "orla-launcher-host-catalog-0.1")
            self.assertEqual(result["target"], package.TARGET)
            self.assertEqual(result["channel"], "experimental")
            self.assertEqual(result["status"], "ok")
            self.assertIsNone(result["firstError"])
            self.assertEqual(result["incomplete"], [])
            self.assertEqual(result["metadataCoverage"], "complete_for_observed_paths")
            self.assertEqual(result["coverage"]["hostTraversal"], "bounded_to_observed_catalog")
            for name in ("loaderResolution", "abiSelection", "qmlImports", "pythonBuildProvenance", "runtimeHealth"):
                self.assertEqual(result["coverage"][name], "UNRUN")
            self.assertEqual(len(result["stageFiles"]), 7)
            for record, (relative, mode) in zip(result["stageFiles"], package.PAYLOAD):
                self.assertEqual(record["path"], relative)
                self.assertEqual(record["mode"], f"{mode:04o}")
                self.assertEqual(record["sha256"], hashlib.sha256((physical_stage / relative).read_bytes()).hexdigest())
                self.assertEqual(record["package"], {"state": "NOT_QUERIED"})
            graph = result["catalogGraph"]
            self.assertEqual(graph["status"], "complete_for_supplied_catalog_policy")
            self.assertEqual([node["path"] for node in graph["nodes"]],
                             [str(stage / "bin/orla-launcher"), endpoint, transitive] + [path for _role, path in fixed])
            self.assertEqual([(edge["source"], edge["occurrence"], edge["candidate"], edge["target"])
                              for edge in graph["edges"]],
                             [(str(stage / "bin/orla-launcher"), 0, alias, endpoint), (endpoint, 0, transitive, transitive)])
            self.assertEqual([root["id"] for root in result["roots"]], ["staged_launcher"] + [role for role, _path in fixed])
            observations = {record["namespace"]: record for record in result["observations"]}
            link = observations[alias]
            self.assertEqual((link["kind"], link["state"], link["rawTarget"], link["hop"]),
                             ("link", "found", "libSynthetic.so.1.0", 0))
            self.assertEqual(link["targetSha256"], hashlib.sha256(b"libSynthetic.so.1.0").hexdigest())
            self.assertEqual(tuple(link["pin"]), package._doctor_identity((namespace / alias.lstrip("/")).lstat()))
            self.assertTrue(link["parentPins"])
            for path, data in ((endpoint, endpoint_data), (transitive, transitive_data)):
                record = observations[path]
                self.assertEqual((record["kind"], record["state"], record["size"]), ("file", "found", len(data)))
                self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(tuple(record["pin"]), package._doctor_identity((namespace / path.lstrip("/")).stat()))
                self.assertEqual(record["dynamicTags"]["type"], "shared_object")
                self.assertTrue(record["parentPins"])
            self.assertEqual(set(ops.rpm_calls), ops.rpm_paths)
            self.assertEqual(len(ops.rpm_calls), len(ops.rpm_paths))
            self.assertFalse(ops.opened)
            self.assertTrue(ops.closed)
            self.assertTrue(any(call[0] == "readlink" and call[1] == alias for call in ops.calls))
            self.assertFalse(any(call[0] == "read" and call[1].startswith("/lib64/") for call in ops.calls))
            after = {str(path.relative_to(namespace)): (stat.S_IMODE(path.lstat().st_mode),
                     os.readlink(path) if path.is_symlink() else path.read_bytes())
                     for path in namespace.rglob("*") if path.is_symlink() or path.is_file()}
            self.assertEqual(after, snapshot)



class BoundsOperations(OwnedOperations):
    def __init__(self, namespace, rpm_paths):
        super().__init__(namespace, rpm_paths)
        self.peak_fds = 0

    def open(self, path, flags, *, dir_fd=None):
        descriptor = super().open(path, flags, dir_fd=dir_fd)
        self.peak_fds = max(self.peak_fds, len(self.opened))
        return descriptor


class HostCatalogBoundsTests(unittest.TestCase):
    def fixture(self, needed=("libSynthetic.so.1",)):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        namespace = Path(temporary.name) / "owned-namespace"
        stage = Path("/synthetic-stage")
        physical_stage = namespace / "synthetic-stage"
        (physical_stage / "bin").mkdir(parents=True)
        (physical_stage / "libexec").mkdir()
        for relative, mode in package.PAYLOAD:
            physical = physical_stage / relative
            physical.write_bytes(synthetic_elf(needed, main=True) if relative == "bin/orla-launcher" else b"owned synthetic payload\n")
            os.chmod(physical, mode)
        fixed = [(role, path) for role, path in sorted(package._EXACT_ASSET_PATHS.items()) if role != "qml_controls_qmldir"]
        for _role, path in fixed:
            physical = namespace / path.lstrip("/")
            physical.parent.mkdir(parents=True, exist_ok=True)
            physical.write_bytes(synthetic_elf())
            os.chmod(physical, 0o644)
        alias, endpoint, transitive = ("/usr/lib64/" + name for name in
                                       ("libSynthetic.so.1", "libSynthetic.so.1.0", "libTransitive.so"))
        (namespace / endpoint.lstrip("/")).write_bytes(synthetic_elf(["libTransitive.so"]))
        (namespace / transitive.lstrip("/")).write_bytes(synthetic_elf())
        (namespace / alias.lstrip("/")).symlink_to("libSynthetic.so.1.0")
        ops = BoundsOperations(namespace, [path for _role, path in fixed] + [alias, endpoint, transitive])
        return namespace, stage, ops, alias, endpoint, transitive

    def collect(self, stage, ops, *, limits=None):
        with mock.patch.object(host, "_Operations", return_value=ops), \
             mock.patch.object(package, "_doctor_rpm", side_effect=AssertionError("real RPM forbidden")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("process execution forbidden")):
            return host.collect_host_catalog(stage, limits=limits)

    def test_tightened_edge_limit_retains_duplicate_occurrence_frontier_as_unknown(self):
        _namespace, stage, ops, _alias, _endpoint, _transitive = self.fixture(("libSynthetic.so.1", "libSynthetic.so.1"))
        result = self.collect(stage, ops, limits={"edges": 1})
        self.assertEqual(result["status"], "unknown")
        graph = result["catalogGraph"]
        self.assertEqual(graph["status"], "unknown")
        self.assertLessEqual(len(graph["edges"]), 1)
        self.assertTrue(any(item["root"] == "staged_launcher" and item["reason"] == "edge_limit"
                            for item in graph["incomplete"]))
        self.assertNotEqual(result["firstError"]["code"], "host_tightened_protocol_unimplemented")
        self.assertFalse(ops.opened)

    def test_tiny_content_fd_operation_and_clock_limits_return_bounded_unknown(self):
        for limits, reason in (({"contentBytes": 1}, "content_budget"), ({"fds": 2}, "fd_budget"),
                               ({"fsOperations": 1}, "operation_budget"), ({"seconds": 0.001}, "deadline")):
            with self.subTest(limits=limits):
                _namespace, stage, ops, _alias, _endpoint, _transitive = self.fixture()
                result = self.collect(stage, ops, limits=limits)
                self.assertEqual(result["status"], "unknown")
                self.assertEqual(result["firstError"]["code"], reason)
                self.assertNotEqual(result["firstError"]["code"], "host_tightened_protocol_unimplemented")
                if "contentBytes" in limits: self.assertLessEqual(result["limitsConsumed"]["contentBytes"], 1)
                if "fds" in limits: self.assertLessEqual(ops.peak_fds, 2)
                if "fsOperations" in limits: self.assertLessEqual(len(ops.calls), 1)
                self.assertFalse(ops.rpm_calls)
                self.assertFalse(ops.opened)

    def test_relative_interior_parent_is_opened_before_dotdot_is_elided(self):
        namespace, stage, ops, alias, endpoint, _transitive = self.fixture()
        proof = namespace / "usr/lib64/proof-directory"
        proof.mkdir()
        physical_alias = namespace / alias.lstrip("/")
        physical_alias.unlink()
        physical_alias.symlink_to("proof-directory/../libSynthetic.so.1.0")
        result = self.collect(stage, ops)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["catalogGraph"]["status"], "complete_for_supplied_catalog_policy")
        link = next(item for item in result["observations"] if item["namespace"] == alias)
        self.assertEqual(link["rawTarget"], "proof-directory/../libSynthetic.so.1.0")
        proof_index = next(index for index, call in enumerate(ops.calls) if call[0] == "open" and call[1] == "/usr/lib64/proof-directory")
        content_index = next(index for index, call in enumerate(ops.calls) if call[0] == "read" and call[1] == endpoint)
        self.assertLess(proof_index, content_index)
        self.assertFalse(ops.opened)

    def test_symlink_interior_parent_is_not_elided_or_used_for_endpoint_reads(self):
        namespace, stage, ops, alias, endpoint, _transitive = self.fixture()
        outside = namespace / "outside-owned-directory"
        outside.mkdir()
        (namespace / "usr/lib64/proof-directory").symlink_to("../../outside-owned-directory", target_is_directory=True)
        physical_alias = namespace / alias.lstrip("/")
        physical_alias.unlink()
        physical_alias.symlink_to("proof-directory/../libSynthetic.so.1.0")
        result = self.collect(stage, ops)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(any(call[0] == "read" and call[1] == endpoint for call in ops.calls))
        self.assertNotIn(endpoint, ops.rpm_calls)
        self.assertFalse(ops.opened)

    def test_final_absence_appearance_after_metadata_invalidates_catalog_identity(self):
        namespace, stage, ops, _alias, _endpoint, _transitive = self.fixture(("libInitiallyAbsent.so",))
        absent = "/usr/lib64/libInitiallyAbsent.so"
        original_rpm = ops.rpm
        appeared = []
        def rpm(path):
            if not appeared:
                (namespace / absent.lstrip("/")).write_bytes(synthetic_elf())
                appeared.append(absent)
            return original_rpm(path)
        ops.rpm = rpm
        result = self.collect(stage, ops)
        self.assertEqual(appeared, [absent])
        self.assertEqual(result["status"], "unknown")
        record = next(item for item in result["observations"] if item["namespace"] == absent)
        self.assertEqual(record["state"], "unknown")
        self.assertEqual(record["code"], "absence_changed")
        edge = next(edge for edge in result["catalogGraph"]["edges"] if edge["candidate"] == absent)
        self.assertEqual(edge["catalogState"], "unknown")
        self.assertIsNone(edge["target"])
        self.assertNotIn(absent, ops.rpm_calls)
        self.assertFalse(ops.opened)

    def test_invalid_stage_refuses_before_any_host_read_or_metadata(self):
        for change in ("extra", "mode", "symlink-directory"):
            with self.subTest(change=change):
                namespace, stage, ops, _alias, _endpoint, _transitive = self.fixture()
                physical_stage = namespace / "synthetic-stage"
                if change == "extra": (physical_stage / "extra").write_bytes(b"owned extra\n")
                if change == "mode": os.chmod(physical_stage / "libexec/ai.py", 0o777)
                if change == "symlink-directory":
                    (physical_stage / "libexec").rename(namespace / "owned-mirror")
                    (physical_stage / "libexec").symlink_to("../owned-mirror", target_is_directory=True)
                result = self.collect(stage, ops)
                self.assertEqual(result["status"], "unknown")
                self.assertFalse(any(len(call) > 1 and str(call[1]).startswith("/usr") for call in ops.calls))
                self.assertFalse(ops.rpm_calls)
                self.assertFalse(ops.opened)


if __name__ == "__main__":
    unittest.main()
