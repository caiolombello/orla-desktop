"""Root-executed default-observer/provenance regressions; no live host or Git."""
import copy
import contextlib
import hashlib
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

_path = list(sys.path)
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    artifact = importlib.import_module("artifact")
    package = importlib.import_module("package")
    inventory_host = importlib.import_module("inventory_host")
finally:
    sys.path[:] = _path

BUTTON = "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/Button.qml"
EXTRAS = (
    ("qml_controls_qmldir", "/usr/lib64/qt6/qml/QtQuick/Controls/qmldir"),
    ("qml_fusion_qmldir", "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/qmldir"),
    ("qml_controls_implementation", BUTTON),
    ("bwrap", "/usr/bin/bwrap"),
)


class ArtifactDefaultObserverTests(unittest.TestCase):
    def fixture(self):
        events = []
        catalog = {"schema": "orla-launcher-host-catalog-0.1", "status": "unknown",
                   "ancestors": [{"namespace": "/", "pin": [1, 2, 3, 4, 5]}],
                   "observations": [{"namespace": "/usr/lib64/libOwned.so", "pin": [1],
                                     "state": "found", "kind": "file"}],
                   "coverage": {"loaderResolution": "UNRUN"}}
        replay = mock.Mock()
        replay.parent.side_effect = lambda path: contextlib.nullcontext()
        replay.replay_record.side_effect = lambda path, record: events.append(("catalog-replay", path))
        contents = {path: ("owned " + role).encode("ascii") for role, path in EXTRAS}
        def rpm(path):
            events.append(("rpm", path))
            return {"owner": "owned-runtime", "version": "1", "nevra": "owned-runtime-0:1-1.fc44.x86_64"}
        def recheck(parents, path, pin, budget):
            events.append(("extra-replay", path))
        return events, catalog, replay, contents, rpm, recheck

    def collect(self, catalog, replay, contents, rpm, recheck):
        with mock.patch.object(inventory_host, "collect_host_catalog", return_value=catalog) as collect, \
             mock.patch.object(inventory_host, "_Collector", return_value=replay), \
             mock.patch.object(package, "_inventory_parents", return_value=[("/", (1,))]), \
             mock.patch.object(package, "_inventory_read", side_effect=lambda path, limit, budget, parents: (contents[path], (1,))), \
             mock.patch.object(package, "_inventory_recheck", side_effect=recheck), \
             mock.patch.object(package, "_doctor_rpm", side_effect=rpm), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("live process forbidden")):
            result = artifact._HostObservations().collect(Path("/owned/stage"), Path(BUTTON))
        collect.assert_called_once_with(Path("/owned/stage"))
        return result

    def test_default_collects_once_then_jointly_replays_after_last_rpm_preserving_unknown(self):
        events, catalog, replay, contents, rpm, recheck = self.fixture()
        before = copy.deepcopy(catalog)
        result = self.collect(catalog, replay, contents, rpm, recheck)
        self.assertEqual(set(result), {"catalog", "data"})
        self.assertEqual(result["catalog"], before)
        self.assertEqual(catalog, before)
        self.assertEqual(result["catalog"]["status"], "unknown")
        last_rpm = max(i for i, event in enumerate(events) if event[0] == "rpm")
        self.assertTrue(any(i > last_rpm and event[0] == "catalog-replay" for i, event in enumerate(events)))
        for role, path in EXTRAS:
            item = next(item for item in result["data"] if item["role"] == role)
            self.assertEqual(set(item), {"role", "path", "state", "kind", "content", "package", "sha256", "size"})
            self.assertEqual((item["path"], item["state"], item["kind"]), (path, "found", "file"))
            self.assertEqual(item["content"], contents[path])
            self.assertEqual(item["sha256"], hashlib.sha256(contents[path]).hexdigest())
            self.assertEqual(item["package"]["state"], "found")
            self.assertEqual(sum(event == ("rpm", path) for event in events), 1)
            self.assertTrue(any(i > last_rpm and event == ("extra-replay", path) for i, event in enumerate(events)))

    def test_catalog_drift_after_last_query_refuses_required_projection(self):
        events, catalog, replay, contents, rpm, recheck = self.fixture()
        replay.replay_record.side_effect = inventory_host.HostInventoryError("namespace_changed")
        with self.assertRaises(artifact.ArtifactError) as raised:
            self.collect(catalog, replay, contents, rpm, recheck)
        self.assertEqual(raised.exception.code, "namespace_changed")
        self.assertEqual(len([event for event in events if event[0] == "rpm"]), 4)

    def test_extra_pin_drift_at_joint_boundary_refuses(self):
        events, catalog, replay, contents, rpm, _recheck = self.fixture()
        def drift(parents, path, pin, budget):
            if len([event for event in events if event[0] == "rpm"]) == 4:
                raise package.PackageError("asset_changed")
        with self.assertRaises(artifact.ArtifactError) as raised:
            self.collect(catalog, replay, contents, rpm, drift)
        self.assertEqual(raised.exception.code, "asset_changed")

    def test_unapproved_controls_path_refuses_before_collection(self):
        with mock.patch.object(inventory_host, "collect_host_catalog", side_effect=AssertionError("collection before validation")):
            with self.assertRaises(artifact.ArtifactError):
                artifact._HostObservations().collect(Path("/owned/stage"), Path("/owned/alternate/Button.qml"))

    def test_raw_proof_only_ancestor_change_refuses_after_last_query(self):
        events, catalog, replay, contents, rpm, recheck = self.fixture()
        catalog["ancestors"].append({"namespace": "/usr/lib64/raw-proof", "pin": [1, 2, 3, 4, 5]})
        def changed(path):
            if path.startswith("/usr/lib64/raw-proof/"):
                raise inventory_host.HostInventoryError("parent_changed")
            return contextlib.nullcontext()
        replay.parent.side_effect = changed
        with self.assertRaises(artifact.ArtifactError) as raised:
            self.collect(catalog, replay, contents, rpm, recheck)
        self.assertEqual(raised.exception.code, "parent_changed")
        self.assertEqual(len([event for event in events if event[0] == "rpm"]), 4)

    def test_truncated_catalog_refuses_with_a_finite_failure(self):
        with mock.patch.object(inventory_host, "collect_host_catalog", return_value={"truncated": True}), \
             mock.patch.object(package, "_inventory_parents", side_effect=AssertionError("extras after truncated catalog")):
            with self.assertRaises(artifact.ArtifactError) as raised:
                artifact._HostObservations().collect(Path("/owned/stage"), Path(BUTTON))
        self.assertEqual(raised.exception.code, "catalog_incomplete")


class ArtifactCiSourceTests(unittest.TestCase):
    commit = "a" * 40
    image = "sha256:1b8544582f974533fb8d9a5d6bf6dc2caf0d977ea54979d5e864a6ffd345c32e"

    def env(self):
        return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "caiolombello/orla-desktop",
                "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": self.commit}

    def test_default_requires_github_context_before_git_or_source_reads(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("subprocess.run", side_effect=AssertionError("Git before context")):
            with self.assertRaises(artifact.ArtifactError) as raised:
                artifact._ci_source_snapshot(Path("/owned/source"), version="0.2.9", commit=self.commit, ci_image_digest=self.image)
        self.assertEqual(raised.exception.code, "ci_context")

    def fixture(self):
        files = {"launcher/install.py": b"owned installer\n", "launcher/package.py": b"owned package\n",
                 "LICENSE": b"owned MIT license\n", "package/metadata.json": b'{"KPlugin":{"Version":"0.2.9"}}\n'}
        calls = []
        dirty = [False]
        def git(root, arguments):
            calls.append(tuple(arguments))
            if arguments == ["rev-parse", "--verify", "HEAD"]:
                return self.commit.encode() + b"\n"
            if arguments[:1] == ["diff"]:
                if dirty[0]:
                    raise artifact.ArtifactError("source_dirty")
                return b""
            if arguments[:2] == ["cat-file", "-s"]:
                return str(len(files[arguments[-1].split(":", 1)[1]])).encode() + b"\n"
            if arguments[:1] == ["show"]:
                return files[arguments[-1].split(":", 1)[1]]
            raise AssertionError(arguments)
        return files, calls, dirty, git

    def test_clean_tracked_source_snapshot_is_bound_and_final_dirty_state_refuses(self):
        files, calls, dirty, git = self.fixture()
        with mock.patch.dict(os.environ, self.env(), clear=True), \
             mock.patch.object(artifact, "_ci_git", side_effect=git, create=True), \
             mock.patch.object(artifact, "_ci_source_bytes", side_effect=lambda root, relative: files[relative], create=True):
            snapshot = artifact._ci_source_snapshot(Path("/owned/source"), version="0.2.9", commit=self.commit, ci_image_digest=self.image)
            self.assertEqual(snapshot["files"], files)
            self.assertEqual(snapshot["provenance"]["origin"], "github_actions_declared")
            self.assertEqual(artifact._ci_source_recheck(snapshot), snapshot["provenance"])
            dirty[0] = True
            with self.assertRaises(artifact.ArtifactError) as raised:
                artifact._ci_source_recheck(snapshot)
            self.assertEqual(raised.exception.code, "source_dirty")
        self.assertTrue(any(call[:1] == ("diff",) for call in calls))

    def test_dirty_or_version_mismatched_source_never_becomes_ci_provenance(self):
        for mode in ("dirty", "version"):
            with self.subTest(mode=mode):
                files, calls, dirty, git = self.fixture()
                dirty[0] = mode == "dirty"
                version = "0.3.0" if mode == "version" else "0.2.9"
                with mock.patch.dict(os.environ, self.env(), clear=True), \
                     mock.patch.object(artifact, "_ci_git", side_effect=git, create=True), \
                     mock.patch.object(artifact, "_ci_source_bytes", side_effect=lambda root, relative: files[relative], create=True):
                    with self.assertRaises(artifact.ArtifactError) as raised:
                        artifact._ci_source_snapshot(Path("/owned/source"), version=version, commit=self.commit, ci_image_digest=self.image)
                self.assertEqual(raised.exception.code, "source_dirty" if mode == "dirty" else "source_version")
