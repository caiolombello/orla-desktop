"""Owned-only additional host race/coverage tests; no production host/RPM IO."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_inventory_host as fixtures


host = fixtures.host
package = fixtures.package
UNRUN_FIELDS = ("loaderResolution", "abiSelection", "qmlImports", "pythonBuildProvenance", "runtimeHealth")


class HookOperations(fixtures.OwnedOperations):
    """Run real descriptor calls only in fixture namespace; mock all RPM/time."""
    def __init__(self, namespace, rpm_paths):
        super().__init__(namespace, rpm_paths)
        self.events = []
        self.hook = None
        self.provider = None
        self.clock = 0.0

    def signal(self, method, phase, logical, result=None):
        self.events.append((method, phase, logical))
        if self.hook is not None:
            self.hook(self, method, phase, logical, result)

    def around(self, method, logical, function):
        self.signal(method, "before", logical)
        result = function()
        self.signal(method, "after", logical, result)
        return result

    def open(self, path, flags, *, dir_fd=None):
        _physical, logical = self._operand(path, dir_fd)
        return self.around("open", logical, lambda: super(HookOperations, self).open(path, flags, dir_fd=dir_fd))

    def stat(self, path, *, dir_fd=None, follow_symlinks=False):
        _physical, logical = self._operand(path, dir_fd)
        return self.around("stat", logical, lambda: super(HookOperations, self).stat(
            path, dir_fd=dir_fd, follow_symlinks=follow_symlinks))

    def fstat(self, descriptor):
        return self.around("fstat", self.opened[descriptor], lambda: super(HookOperations, self).fstat(descriptor))

    def scandir(self, descriptor):
        return self.around("scandir", self.opened[descriptor], lambda: super(HookOperations, self).scandir(descriptor))

    def read(self, descriptor, count):
        return self.around("read", self.opened[descriptor], lambda: super(HookOperations, self).read(descriptor, count))

    def readlink(self, path, *, dir_fd):
        return self.around("readlink", self.opened[dir_fd], lambda: super(HookOperations, self).readlink(path, dir_fd=dir_fd))

    def close(self, descriptor):
        logical = self.opened[descriptor]
        return self.around("close", logical, lambda: super(HookOperations, self).close(descriptor))

    def monotonic(self):
        return self.clock

    def rpm(self, path):
        def call():
            value = super(HookOperations, self).rpm(path)
            return self.provider(self, path, value) if self.provider is not None else value
        return self.around("rpm", path, call)


class TrackedScandirIterator:
    """Retain the owned iterator and attest explicit close without relying on GC."""
    def __init__(self, underlying):
        self.underlying = underlying
        self.closed_explicitly = False
        self.close_calls = 0

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.underlying)

    def __enter__(self):
        return self

    def __exit__(self, _kind, _value, _traceback):
        self.close()

    def close(self):
        self.close_calls += 1
        if not self.closed_explicitly:
            self.underlying.close()
            self.closed_explicitly = True


class HostCatalogRaceTests(unittest.TestCase):
    def fixture(self, needed=("libSynthetic.so.1",)):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        namespace = Path(temporary.name) / "owned-namespace"
        stage = namespace / "synthetic-stage"
        (stage / "bin").mkdir(parents=True)
        (stage / "libexec").mkdir()
        for relative, mode in package.PAYLOAD:
            target = stage / relative
            target.write_bytes(fixtures.synthetic_elf(needed, main=True) if relative == "bin/orla-launcher"
                               else b"owned synthetic payload\n")
            target.chmod(mode)
        fixed = [(role, path) for role, path in sorted(package._EXACT_ASSET_PATHS.items())
                 if role != "qml_controls_qmldir"]
        for _role, path in fixed:
            physical = namespace / path.lstrip("/")
            physical.parent.mkdir(parents=True, exist_ok=True)
            physical.write_bytes(fixtures.synthetic_elf())
            physical.chmod(0o644)
        alias = "/usr/lib64/libSynthetic.so.1"
        endpoint = "/usr/lib64/libSynthetic.so.1.0"
        transitive = "/usr/lib64/libTransitive.so"
        endpoint_data = fixtures.synthetic_elf(["libTransitive.so"])
        (namespace / endpoint.lstrip("/")).write_bytes(endpoint_data)
        (namespace / transitive.lstrip("/")).write_bytes(fixtures.synthetic_elf())
        (namespace / alias.lstrip("/")).symlink_to("libSynthetic.so.1.0")
        ops = HookOperations(namespace, [path for _role, path in fixed] + [alias, endpoint, transitive])
        return namespace, ops, fixed, alias, endpoint, endpoint_data

    def collect(self, ops, *, limits=None):
        with mock.patch.object(host, "_Operations", return_value=ops), \
                mock.patch.object(package, "_doctor_rpm", side_effect=AssertionError("real RPM forbidden")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("process execution forbidden")):
            return host.collect_host_catalog(Path("/synthetic-stage"), limits=limits)

    def observation(self, report, path):
        return next(record for record in report["observations"] if record["namespace"] == path)

    def assert_closed(self, ops):
        self.assertFalse(ops.opened)
        opens = [event for event in ops.events if event[0:2] == ("open", "after")]
        closes = [event for event in ops.events if event[0:2] == ("close", "before")]
        self.assertEqual(len(closes), len(opens))

    def assert_unrun(self, report):
        for field in UNRUN_FIELDS:
            self.assertEqual(report["coverage"][field], "UNRUN")

    def assert_endpoint_identity(self, report, endpoint, endpoint_data):
        record = self.observation(report, endpoint)
        self.assertEqual(record["sha256"], hashlib.sha256(endpoint_data).hexdigest())
        self.assertEqual(record["size"], len(endpoint_data))
        self.assertEqual(record["dynamicTags"]["type"], "shared_object")

    def test_parent_replaced_between_stat_and_open_blocks_host_bytes(self):
        namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture()
        fired = []
        def hook(_ops, method, phase, logical, _result):
            if not fired and (method, phase, logical) == ("stat", "after", "/usr/lib64"):
                fired.append(True)
                parent = namespace / "usr/lib64"
                parent.rename(namespace / "usr/preserved-lib64")
                parent.mkdir()
        ops.hook = hook
        report = self.collect(ops)
        self.assertTrue(fired)
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["firstError"]["code"], "parent_changed")
        self.assertFalse(any(event[0] == "read" and event[2].startswith("/usr/lib64/") for event in ops.events))
        self.assertFalse(ops.rpm_calls)
        self.assert_closed(ops)
        self.assert_unrun(report)

    def test_link_named_replacement_after_anchored_reads_is_detected(self):
        namespace, ops, _fixed, alias, endpoint, _data = self.fixture()
        reads = []
        fired = []
        def hook(_ops, method, phase, logical, _result):
            if (method, phase, logical) == ("readlink", "after", alias):
                reads.append(True)
            if not fired and len(reads) >= 2 and (method, phase, logical) == ("stat", "before", alias):
                fired.append(True)
                physical = namespace / alias.lstrip("/")
                physical.unlink()
                physical.symlink_to("libSynthetic.so.1.0")
        ops.hook = hook
        report = self.collect(ops)
        self.assertTrue(fired)
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["firstError"]["code"], "namespace_changed")
        record = self.observation(report, alias)
        self.assertEqual(record["rawTarget"], "libSynthetic.so.1.0")
        self.assertEqual(record["state"], "unknown")
        self.assertFalse(any(event[0] == "read" and event[2] == endpoint for event in ops.events))
        self.assertNotIn(alias, ops.rpm_calls)
        self.assert_closed(ops)

    def test_regular_leaf_replaced_while_descriptor_open_retains_partial_identity(self):
        namespace, ops, _fixed, _alias, endpoint, endpoint_data = self.fixture()
        fired = []
        def hook(_ops, method, phase, logical, result):
            if not fired and (method, phase, logical) == ("read", "after", endpoint) and result == b"":
                fired.append(True)
                target = namespace / endpoint.lstrip("/")
                target.rename(target.with_name("preserved-endpoint"))
                target.write_bytes(endpoint_data)
        ops.hook = hook
        report = self.collect(ops)
        self.assertTrue(fired)
        self.assertEqual(report["status"], "unknown")
        record = self.observation(report, endpoint)
        self.assertEqual(record["state"], "unknown")
        self.assertIn(record["code"], ("content_changed", "namespace_changed"))
        self.assertEqual(record["sha256"], hashlib.sha256(endpoint_data).hexdigest())
        self.assertNotIn(endpoint, ops.rpm_calls)
        self.assert_closed(ops)

    def test_parent_named_relation_changed_at_leaf_exit_is_rechecked(self):
        namespace, ops, _fixed, alias, endpoint, _data = self.fixture()
        leaf_stats = []
        fired = []
        def hook(_ops, method, phase, logical, _result):
            if (method, phase, logical) == ("stat", "after", alias):
                leaf_stats.append(True)
                if not fired and len(leaf_stats) == 2:
                    fired.append(True)
                    parent = namespace / "usr/lib64"
                    parent.rename(namespace / "usr/preserved-lib64")
                    parent.mkdir()
        ops.hook = hook
        report = self.collect(ops)
        self.assertTrue(fired)
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["firstError"]["code"], "parent_changed")
        self.assertFalse(any(event[0] == "read" and event[2] == endpoint for event in ops.events))
        self.assert_closed(ops)

    def test_cleanup_uncertainty_preserves_first_error_attempts_all_close_and_stops_admissions(self):
        _namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture()
        primary = []
        cleanup = []
        def hook(_ops, method, phase, logical, _result):
            if not primary and (method, phase, logical) == ("read", "before", "/synthetic-stage/bin/orla-launcher"):
                primary.append(True)
                raise host.HostInventoryError("content_changed")
            if primary and not cleanup and method == "close" and phase == "after":
                cleanup.append(len(ops.events) - 1)
                # The owned descriptor was actually closed; report uncertainty.
                raise OSError("owned simulated close uncertainty")
        ops.hook = hook
        report = self.collect(ops)
        self.assertTrue(primary and cleanup)
        self.assertEqual(report["firstError"]["code"], "content_changed")
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(all(event[0] == "close" for event in ops.events[cleanup[0] + 1:]))
        self.assertFalse(ops.rpm_calls)
        self.assert_closed(ops)
        self.assert_unrun(report)

    def test_conclusively_absent_dependency_is_missing_when_required_roots_metadata_are_known(self):
        _namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture(["libAbsentFixture.so"])
        report = self.collect(ops)
        self.assertEqual(report["status"], "missing")
        self.assertEqual(report["catalogGraph"]["status"], "absent_in_catalog")
        self.assertEqual(report["metadataCoverage"], "complete_for_observed_paths")
        record = self.observation(report, "/usr/lib64/libAbsentFixture.so")
        self.assertEqual((record["kind"], record["state"]), ("absence", "absent"))
        self.assertNotIn(record["namespace"], ops.rpm_calls)
        self.assertEqual(report["knownMissingRoots"], [])
        self.assert_closed(ops)
        self.assert_unrun(report)

    def test_missing_or_corrupt_fixed_root_preserves_honest_pure_unknown(self):
        for action in ("missing", "corrupt"):
            with self.subTest(action=action):
                namespace, ops, fixed, _alias, _endpoint, _data = self.fixture()
                role, path = fixed[0]
                physical = namespace / path.lstrip("/")
                if action == "missing":
                    physical.unlink()
                else:
                    physical.write_bytes(b"owned not an ELF file")
                report = self.collect(ops)
                self.assertEqual(report["status"], "unknown")
                self.assertEqual(report["catalogGraph"]["status"], "unknown")
                root = next(root for root in report["catalogGraph"]["roots"] if root["id"] == role)
                self.assertEqual(root["status"], "unknown")
                self.assertNotIn(path, [node["path"] for node in report["catalogGraph"]["nodes"]])
                record = self.observation(report, path)
                if action == "missing":
                    self.assertIn(role, report["knownMissingRoots"])
                    self.assertEqual((record["kind"], record["state"]), ("absence", "absent"))
                else:
                    self.assertEqual(record["state"], "unknown")
                    self.assertEqual(record["sha256"], hashlib.sha256(b"owned not an ELF file").hexdigest())
                    self.assertIsNone(record.get("dynamicTags"))
                self.assertNotIn(path, ops.rpm_calls)
                self.assert_closed(ops)
                self.assert_unrun(report)

    def test_same_size_stage_helper_drift_blocks_all_host_reads_and_rpm(self):
        namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture()
        license_stats = []
        fired = []
        def hook(_ops, method, phase, logical, _result):
            if (method, phase, logical) == ("stat", "after", "/synthetic-stage/LICENSE"):
                license_stats.append(True)
                if not fired and len(license_stats) == 2:
                    fired.append(True)
                    helper = namespace / "synthetic-stage/libexec/ai.py"
                    data = helper.read_bytes()
                    helper.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        ops.hook = hook
        report = self.collect(ops)
        self.assertTrue(fired)
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(any(event[0] == "read" and event[2].startswith("/usr/lib64/") for event in ops.events))
        self.assertFalse(ops.rpm_calls)
        self.assert_closed(ops)

    def test_tightened_rpm_query_and_output_limits_stop_after_one_admission(self):
        for limits in ({"rpmQueries": 1}, {"rpmOutputBytes": 16384}):
            with self.subTest(limits=limits):
                _namespace, ops, _fixed, _alias, endpoint, endpoint_data = self.fixture()
                report = self.collect(ops, limits=limits)
                self.assertEqual(report["status"], "unknown")
                self.assertEqual(report["metadataCoverage"], "unknown")
                self.assertEqual(len(ops.rpm_calls), 1)
                self.assertEqual(report["limitsConsumed"]["rpmQueries"], 1)
                self.assertEqual(report["limitsConsumed"]["rpmOutputBytes"], 16384)
                self.assert_endpoint_identity(report, endpoint, endpoint_data)
                self.assert_closed(ops)

    def test_rpm_elapsed_budget_and_package_cleanup_errors_retain_content_identity(self):
        for mode in ("elapsed", "provider_error", "cleanup_error", "overrun"):
            with self.subTest(mode=mode):
                _namespace, ops, _fixed, _alias, endpoint, endpoint_data = self.fixture()
                def provider(selected, _path, value):
                    if mode == "elapsed":
                        selected.clock += 2.1
                    elif mode == "overrun":
                        selected.clock += 9.0
                    elif len(selected.rpm_calls) == 1:
                        raise package.PackageError("rpm_cleanup_unknown" if mode == "cleanup_error" else "rpm_metadata_unknown")
                    return value
                ops.provider = provider
                report = self.collect(ops)
                self.assertEqual(report["status"], "unknown")
                self.assertEqual(report["metadataCoverage"], "unknown")
                self.assert_endpoint_identity(report, endpoint, endpoint_data)
                expected = {"elapsed": "rpm_budget", "provider_error": "rpm_metadata_unknown",
                            "cleanup_error": "rpm_cleanup_unknown", "overrun": "rpm_overrun"}[mode]
                self.assertEqual(report["firstError"]["code"], expected)
                if mode == "elapsed":
                    self.assertEqual(len(ops.rpm_calls), 3)
                    self.assertAlmostEqual(report["limitsConsumed"]["rpmSeconds"], 6.3)
                elif mode in ("cleanup_error", "overrun"):
                    self.assertEqual(len(ops.rpm_calls), 1)
                else:
                    self.assertGreater(len(ops.rpm_calls), 1)
                self.assert_closed(ops)
                self.assert_unrun(report)

    def test_evidence_4096_truncation_preserves_first_error_and_all_unrun_coverage(self):
        _namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture()
        def provider(selected, _path, value):
            if len(selected.rpm_calls) == 1:
                raise package.PackageError("rpm_metadata_unknown")
            return value
        ops.provider = provider
        report = self.collect(ops, limits={"evidenceBytes": 4096})
        self.assertEqual(report["status"], "unknown")
        self.assertIs(report["truncated"], True)
        self.assertEqual(report["firstError"]["code"], "rpm_metadata_unknown")
        self.assertLessEqual(len(json.dumps(report, separators=(",", ":")).encode("utf-8")), 4096)
        for field in ("stageFiles", "roots", "catalogGraph", "observations"):
            self.assertIn(field, report["omittedFields"])
            self.assertNotIn(field, report)
        self.assertEqual(report["coverage"]["hostTraversal"], "unknown")
        self.assert_unrun(report)
        self.assert_closed(ops)

    def test_unrepresentable_roots_unicode_and_huge_numeric_limits_refuse_before_operations(self):
        cases = ((Path("/synthetic-\u2603"), None, "host_stage"),
                 (Path("/" + "a" * 4080), None, "host_stage"),
                 (Path("/synthetic-stage"), {"seconds": 1 << 4096}, "host_limits"))
        for stage, limits, code in cases:
            with self.subTest(code=code, stageLength=len(str(stage))):
                with mock.patch.object(host, "_Operations", side_effect=AssertionError("operations before validation")) as factory:
                    with self.assertRaises(host.HostInventoryError) as raised:
                        host.collect_host_catalog(stage, limits=limits)
                    self.assertEqual(raised.exception.code, code)
                    factory.assert_not_called()

    def test_oserror_primary_read_precedes_cleanup_uncertainty_without_further_admissions(self):
        _namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture()
        primary = []
        cleanup = []
        def hook(_ops, method, phase, logical, _result):
            if not primary and (method, phase, logical) == ("read", "before", "/synthetic-stage/bin/orla-launcher"):
                primary.append(True)
                raise OSError("owned simulated primary read failure")
            if primary and not cleanup and method == "close" and phase == "after":
                cleanup.append(len(ops.events) - 1)
                # Actual owned close already completed; report uncertainty only.
                raise OSError("owned simulated close uncertainty")
        ops.hook = hook
        report = self.collect(ops)
        self.assertTrue(primary and cleanup)
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["firstError"]["code"], "filesystem_unknown")
        self.assertTrue(all(event[0] == "close" for event in ops.events[cleanup[0] + 1:]))
        self.assertFalse(ops.rpm_calls)
        self.assert_closed(ops)
        self.assert_unrun(report)

    def test_returned_scandir_iterator_explicitly_closed_after_postcall_deadline(self):
        _namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture()
        retained = []
        def close_owned_descriptors():
            for descriptor in list(ops.opened):
                fixtures.OwnedOperations.close(ops, descriptor)
        # Last-in-first-out cleanup closes any extra iterator before owned FDs.
        self.addCleanup(close_owned_descriptors)
        original_scandir = ops.scandir
        def scandir_with_overrun(descriptor):
            iterator = TrackedScandirIterator(original_scandir(descriptor))
            retained.append(iterator)
            self.addCleanup(iterator.close)
            # The result exists before the collector's post-call admission check.
            ops.clock = 30.0
            return iterator
        ops.scandir = scandir_with_overrun
        report = self.collect(ops)
        self.assertEqual(len(retained), 1)
        iterator = retained[0]
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["firstError"]["code"], "deadline")
        # Assert while a strong reference is retained and before addCleanup runs.
        self.assertTrue(iterator.closed_explicitly)
        self.assertGreaterEqual(iterator.close_calls, 1)
        self.assertFalse(ops.rpm_calls)
        self.assert_closed(ops)
        self.assert_unrun(report)



class HostReturnedBytesTests(unittest.TestCase):
    fixture = HostCatalogRaceTests.fixture
    collect = HostCatalogRaceTests.collect
    observation = HostCatalogRaceTests.observation
    assert_closed = HostCatalogRaceTests.assert_closed

    def test_returned_read_after_deadline_retains_partial_evidence(self):
        namespace, ops, _fixed, _alias, _endpoint, _data = self.fixture()
        path = "/synthetic-stage/bin/orla-launcher"
        expected = (namespace / path.lstrip("/")).read_bytes()
        returned = []
        def hook(selected, method, phase, logical, result):
            if not returned and (method, phase, logical) == ("read", "after", path):
                returned.append(result)
                selected.clock = 30.0
        ops.hook = hook
        report = self.collect(ops)
        self.assertEqual(returned, [expected])
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["firstError"]["code"], "deadline")
        observed = self.observation(report, path)
        self.assertEqual(observed["observedBytes"], len(expected))
        self.assertEqual(observed["partialSha256"], hashlib.sha256(expected).hexdigest())
        self.assertEqual(observed["hashCoverage"], "partial_read")
        self.assertNotIn("sha256", observed)
        self.assertFalse(ops.rpm_calls)
        self.assert_closed(ops)


if __name__ == "__main__":
    unittest.main()
