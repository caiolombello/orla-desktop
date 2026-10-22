"""Bundle limits and refusal behavior through public artifact seams."""
import hashlib
import zipfile
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

original_path = list(sys.path)
try:
    sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
    import artifact
    import test_artifact as fixtures
finally:
    sys.path[:] = original_path

class ArtifactIntegrityTests(unittest.TestCase):
    def produce(self, root, *, large_bwrap=False):
        stage = fixtures.package_fixtures.PackageTests().make_stage(root)
        controls = Path(artifact.DATA_PATHS["qml_controls_implementation"])
        observer = fixtures.ControlledObservations(stage, controls)
        if large_bwrap:
            bwrap = next(item for item in observer.value["data"] if item["role"] == "bwrap")
            content = bwrap["content"] + b"B" * 90000
            bwrap.update(content=content, size=len(content), sha256=hashlib.sha256(content).hexdigest())
        output = root / "bundle"
        result = artifact.produce(stage, output, version="0.1.0", commit="a" * 40,
            ci_image_digest="sha256:" + "b" * 64, controls_data=controls,
            observations_backend=observer)
        return output, result

    def test_normal_sized_bwrap_elf_is_not_limited_as_qmldir_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            output, result = self.produce(Path(temporary), large_bwrap=True)
            self.assertEqual(artifact.verify_bundle(output), result)

    def test_changed_content_and_unexpected_member_are_refused_before_smoke(self):
        for mode in ("digest", "member", "duplicate_json"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                output, _result = self.produce(Path(temporary))
                if mode == "digest":
                    (output / "runtime-inventory.json").write_bytes(b"{}\n")
                elif mode == "member":
                    (output / "unexpected").write_bytes(b"owned")
                else:
                    data = (output / "artifact.json").read_bytes()
                    (output / "artifact.json").write_bytes(data.replace(b'{', b'{"schema":"duplicate",', 1))
                with mock.patch.object(artifact.installer, "install_archive", side_effect=AssertionError("install before verification")):
                    with self.assertRaises(artifact.ArtifactError):
                        artifact.smoke_install(output)

    def test_builder_failure_leaves_no_readiness_files_and_preserves_primary_cause(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(artifact.package, "build", side_effect=artifact.package.PackageError("owned_build_failure")):
                with self.assertRaises(artifact.package.PackageError) as raised:
                    self.produce(root)
            self.assertEqual(raised.exception.code, "owned_build_failure")
            self.assertFalse((root / "bundle/artifact.json").exists())
            self.assertFalse((root / "bundle/SHA256SUMS").exists())

    def rewrite_records(self, output, descriptor):
        for key in ("archive", "bootstrap", "sourceInventory", "observations"):
            name = descriptor[key]["name"]
            data = (output / name).read_bytes()
            descriptor[key] = {"name": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        (output / "artifact.json").write_text(json.dumps(descriptor, sort_keys=True) + "\n")
        names = sorted(path.name for path in output.iterdir() if path.name != "SHA256SUMS")
        (output / "SHA256SUMS").write_text("".join(hashlib.sha256((output / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in names))

    def test_coherent_legacy_archive_bundle_is_refused_before_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, descriptor = self.produce(root)
            legacy, _sha = fixtures.package_fixtures.PackageTests().legacy_archive(root)
            manifest = fixtures.package_fixtures.package.verify(legacy, expected_sha256=_sha, expected_commit="a" * 40)
            (output / descriptor["archive"]["name"]).write_bytes(legacy.read_bytes())
            (output / descriptor["sourceInventory"]["name"]).write_text(json.dumps(manifest["runtime_inventory"]) + "\n")
            self.rewrite_records(output, descriptor)
            with self.assertRaises(artifact.ArtifactError) as raised:
                artifact.verify_bundle(output)
            self.assertEqual(raised.exception.code, "artifact_package_schema")

    def test_coherent_bootstrap_with_wrong_installation_hash_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            output, descriptor = self.produce(Path(temporary))
            bootstrap_path = output / descriptor["bootstrap"]["name"]
            with zipfile.ZipFile(bootstrap_path) as archive:
                contents = {name: archive.read(name) for name in archive.namelist()}
            contents["INSTALL.txt"] = contents["INSTALL.txt"].replace(descriptor["archive"]["sha256"].encode(), b"0" * 64)
            with zipfile.ZipFile(bootstrap_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in contents.items():
                    archive.writestr(fixtures.package_fixtures.PackageTests().independent_info(name, 0o644), data)
            self.rewrite_records(output, descriptor)
            with self.assertRaises(artifact.ArtifactError) as raised:
                artifact.verify_bundle(output)
            self.assertEqual(raised.exception.code, "bootstrap_instructions")
