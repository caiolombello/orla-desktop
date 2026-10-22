"""One owned fixture tracer: coupled artifact, standalone filesystem smoke."""
import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

LAUNCHER = Path(__file__).resolve().parents[1]
_original_path = list(sys.path)
try:
    sys.path[:0] = [str(LAUNCHER), str(LAUNCHER / "tests")]
    import artifact
    import inventory_policy
    # Alias only: imported TestCase is never added to this discovery namespace.
    import test_package as package_fixtures
finally:
    sys.path[:] = _original_path

package = package_fixtures.package


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ControlledObservations:
    """Synthetic metadata only; no /usr reads, RPM, host or CI assertions."""
    def __init__(self, stage, controls_data):
        self.calls = []
        main = str(stage / "bin/orla-launcher")
        fixed = sorted((role, path) for role, path in package._EXACT_ASSET_PATHS.items()
                       if role != "qml_controls_qmldir")
        roots = [{"id": "staged_launcher", "path": main, "required": True}] + [
            {"id": role, "path": path, "required": True} for role, path in fixed]
        objects, paths, observations = {}, {}, []
        owner = {"state": "found", "owner": "synthetic-runtime",
                 "nevra": "synthetic-runtime-0:1.0-1.fc44.x86_64"}
        def found(path, content, tags, package_record, mode="0644"):
            objects[path] = tags
            if path.startswith("/usr/lib64/"):
                paths[path] = {"state": "object", "canonical": path}
            observations.append({"namespace": path, "state": "found", "kind": "file",
                "size": len(content), "sha256": digest(content), "mode": mode,
                "hashCoverage": "complete_stable_read", "observedBytes": len(content),
                "pin": None, "parentPins": [], "package": copy.deepcopy(package_record),
                "dynamicTags": tags})
        content = (stage / "bin/orla-launcher").read_bytes()
        found(main, content, package._inventory_dynamic(content, main=True), {"state": "NOT_QUERIED"}, mode="0755")
        for _role, path in fixed:
            content = package_fixtures.synthetic_elf(needed=("libSynthetic.so.1",))
            found(path, content, package._inventory_dynamic(content), owner)
        for soname in ("libQt6Core.so.6", "libSynthetic.so.1"):
            content = package_fixtures.synthetic_elf(needed=())
            found("/usr/lib64/" + soname, content, package._inventory_dynamic(content), owner)
        graph = inventory_policy.resolve_catalog(roots, objects, paths)
        stage_files = [{"path": relative, "state": "found", "mode": f"{mode:04o}",
                        "sha256": digest((stage / relative).read_bytes()),
                        "size": (stage / relative).stat().st_size, "package": {"state": "NOT_QUERIED"}}
                       for relative, mode in package.PAYLOAD]
        coverage = {"hostTraversal": "bounded_to_observed_catalog", **{
            name: "UNRUN" for name in ("loaderResolution", "abiSelection", "qmlImports",
                                       "pythonBuildProvenance", "runtimeHealth")}}
        catalog = {"schema": "orla-launcher-host-catalog-0.1", "target": package.TARGET,
            "channel": package.CHANNEL, "status": "unknown", "roots": roots,
            "stageFiles": stage_files, "observations": observations, "catalogGraph": graph,
            "chains": [], "ancestors": [], "knownMissingRoots": [],
            "metadataCoverage": "complete_for_observed_paths", "limitsConsumed": {},
            "firstError": {"code": "fixture_unverified"},
            "incomplete": [{"reason": "fixture_unverified"}], "coverage": coverage}
        data = []
        for role, path, content, package_record in (
            ("qml_controls_qmldir", package._EXACT_ASSET_PATHS["qml_controls_qmldir"],
             b"module QtQuick.Controls\nplugin qtquickcontrols2plugin\n", owner),
            ("qml_fusion_qmldir", "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/qmldir",
             b"module QtQuick.Controls.Fusion\nButton 2.0 Button.qml\n", owner),
            ("qml_controls_implementation", str(controls_data), b"import QtQuick\nItem {}\n", owner),
            ("bwrap", "/usr/bin/bwrap", package_fixtures.synthetic_elf(needed=()),
             {"state": "found", "owner": "bubblewrap", "nevra": "bubblewrap-0:0.12.0-1.fc44.x86_64"}),
        ):
            data.append({"role": role, "path": path, "state": "found", "kind": "file",
                         "content": content, "package": copy.deepcopy(package_record),
                         "sha256": digest(content), "size": len(content)})
        self.value = {"catalog": catalog, "data": data}

    def collect(self, stage, controls_data):
        self.calls.append((stage, controls_data))
        return copy.deepcopy(self.value)


class ArtifactTracerTests(unittest.TestCase):
    def test_controlled_artifact_bundle_verifies_and_smokes_without_source_preserving_userdata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = package_fixtures.PackageTests().make_stage(root)
            controls_data = Path("/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/Button.qml")
            observer = ControlledObservations(stage, controls_data)
            original = copy.deepcopy(observer.value)
            stage_before = {relative: ((stage / relative).read_bytes(), stat.S_IMODE((stage / relative).stat().st_mode))
                            for relative, _mode in package.PAYLOAD}
            output = root / "coupled download"
            commit, version = "a" * 40, "0.1.0"
            # Actual baseline failure must be this public feature seam, not import.
            with mock.patch.object(package, "_doctor_rpm", side_effect=AssertionError("real RPM forbidden")), \
                 mock.patch("subprocess.Popen", side_effect=AssertionError("producer cannot execute programs")):
                produced = artifact.produce(stage, output, version=version, commit=commit,
                    ci_image_digest="sha256:" + "b" * 64, controls_data=controls_data,
                    observations_backend=observer)
                verified = artifact.verify_bundle(output)
            self.assertEqual(observer.calls, [(stage, controls_data)])
            self.assertEqual(observer.value, original)
            self.assertEqual(verified, produced)
            self.assertEqual(set(produced), {"schema", "version", "commit", "target", "channel",
                "archive", "bootstrap", "sourceInventory", "observations", "provenance"})
            self.assertEqual(produced["schema"], "orla-launcher-artifact-0.1")
            self.assertEqual((produced["version"], produced["commit"], produced["target"], produced["channel"]),
                             (version, commit, package.TARGET, "experimental"))
            self.assertEqual(produced["provenance"]["origin"], "fixture_unverified")
            archive_name = f"orla-launcher-{version}-{commit}.zip"
            expected_names = {archive_name, "orla-launcher-bootstrap.zip", "runtime-inventory.json",
                              "observations.json", "artifact.json", "SHA256SUMS"}
            self.assertEqual({path.name for path in output.iterdir()}, expected_names)
            self.assertEqual(json.loads((output / "artifact.json").read_bytes()), produced)
            for key, name in (("archive", archive_name), ("bootstrap", "orla-launcher-bootstrap.zip"),
                              ("sourceInventory", "runtime-inventory.json"), ("observations", "observations.json")):
                data = (output / name).read_bytes()
                self.assertEqual(produced[key], {"name": name, "sha256": digest(data), "size": len(data)})
            checksums = {}
            for line in (output / "SHA256SUMS").read_text("ascii").splitlines():
                sha, name = line.split("  ", 1)
                self.assertNotIn(name, checksums)
                checksums[name] = sha
            self.assertEqual(set(checksums), expected_names - {"SHA256SUMS"})
            for name, sha in checksums.items(): self.assertEqual(sha, digest((output / name).read_bytes()))
            inventory = json.loads((output / "runtime-inventory.json").read_bytes())
            elf = package.parse_elf((stage / "bin/orla-launcher").read_bytes())
            self.assertEqual(package.validate_runtime_inventory(inventory, elf), inventory)
            self.assertEqual(inventory["source"], "caller_assertion_unverified")
            self.assertEqual(inventory["elf_direct"]["needed"], [package_fixtures.dependency("libQt6Core.so.6")])
            manifest = package.verify(output / archive_name, expected_sha256=produced["archive"]["sha256"], expected_commit=commit)
            self.assertEqual(manifest["runtime_inventory"], inventory)
            evidence = json.loads((output / "observations.json").read_bytes())
            self.assertEqual(evidence["catalog"], original["catalog"])
            self.assertEqual(evidence["catalog"]["status"], "unknown")
            for name in ("loaderResolution", "abiSelection", "qmlImports", "pythonBuildProvenance", "runtimeHealth"):
                self.assertEqual(evidence["catalog"]["coverage"][name], "UNRUN")
            self.assertEqual(len(evidence["data"]), 4)
            for observed, raw in zip(evidence["data"], original["data"]):
                self.assertEqual(observed, {key: value for key, value in raw.items() if key != "content"})
            with zipfile.ZipFile(output / "orla-launcher-bootstrap.zip") as bootstrap:
                self.assertEqual(bootstrap.namelist(), ["install.py", "package.py", "LICENSE", "INSTALL.txt"])
                for member in bootstrap.infolist(): self.assertEqual((member.external_attr >> 16) & 0o777, 0o644)
                self.assertEqual(bootstrap.read("install.py"), (LAUNCHER / "install.py").read_bytes())
                self.assertEqual(bootstrap.read("package.py"), (LAUNCHER / "package.py").read_bytes())
                self.assertEqual(bootstrap.read("LICENSE"), (LAUNCHER.parent / "LICENSE").read_bytes())
                self.assertIn(archive_name.encode("ascii"), bootstrap.read("INSTALL.txt"))
                self.assertIn(produced["archive"]["sha256"].encode("ascii"), bootstrap.read("INSTALL.txt"))
            real_run = subprocess.run
            commands = []
            def owned_run(argv, *args, **kwargs):
                self.assertIsInstance(argv, list)
                self.assertIn(argv[-1], ("status", "uninstall"))
                self.assertEqual(Path(argv[0]).name, "orla-launcherctl")
                self.assertNotIn(str(LAUNCHER), argv[0])
                completed = real_run(argv, *args, **kwargs)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                report = json.loads(completed.stdout)
                self.assertEqual(report["runtime"], "unverified")
                commands.append((argv[-1], report["status"]))
                return completed
            with mock.patch("subprocess.run", side_effect=owned_run):
                smoked = artifact.smoke_install(output)
            self.assertEqual(smoked, {"status": "uninstalled", "runtime": "unverified",
                "userdataPreserved": True, "sourceAbsent": True, "Native": "UNRUN"})
            self.assertEqual(commands, [("status", "installed"), ("uninstall", "uninstalled")])
            self.assertEqual(stage_before, {relative: ((stage / relative).read_bytes(), stat.S_IMODE((stage / relative).stat().st_mode))
                                           for relative, _mode in package.PAYLOAD})
            self.assertEqual(observer.value, original)
