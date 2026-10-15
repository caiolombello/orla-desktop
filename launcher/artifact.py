"""Produce, verify and filesystem-smoke an experimental launcher CI bundle.

Metadata describes a bounded observation episode, not an atomic host snapshot.
Declared CI fields and checksums do not authenticate origin or qualify runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import zipfile

import install as installer
import package
import inventory_host

SCHEMA = "orla-launcher-artifact-0.1"
BOOTSTRAP = ("install.py", "package.py", "LICENSE", "INSTALL.txt")
MAX_JSON = 8 * 1024 * 1024
MAX_BOOTSTRAP = 4 * 1024 * 1024
DATA_PATHS = {
    "qml_controls_qmldir": package._EXACT_ASSET_PATHS["qml_controls_qmldir"],
    "qml_fusion_qmldir": "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/qmldir",
    "qml_controls_implementation": "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/Button.qml",
    "bwrap": "/usr/bin/bwrap",
}


class ArtifactError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _fail(code):
    raise ArtifactError(code)


def _fields(value, keys, code):
    if type(value) is not dict or set(value) != set(keys):
        _fail(code)
    return value


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value, limit=MAX_JSON):
    try:
        data = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                           allow_nan=False) + "\n").encode("ascii")
    except (ValueError, TypeError, RecursionError):
        _fail("evidence_json")
    if len(data) > limit:
        _fail("evidence_limit")
    return data


def _decode(data, limit=MAX_JSON):
    if len(data) > limit:
        _fail("evidence_limit")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail("evidence_json")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda _value: _fail("evidence_json"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        _fail("evidence_json")


def _read(path, limit, mode=None):
    try:
        return installer._read(path, mode=mode, limit=limit)
    except installer.InstallError as error:
        raise ArtifactError(error.code) from None


def _layout(stage):
    expected = {"": {"bin", "libexec", "LICENSE"}, "bin": {"orla-launcher"},
                "libexec": {Path(name).name for name, _mode in package.PAYLOAD if name.startswith("libexec/")}}
    pins, descriptors = {}, []
    with installer._directory(stage) as root:
        try:
            pins[""] = installer._directory_identity(os.fstat(root))
            # Both child types are admitted before any directory enumeration.
            for name in ("bin", "libexec"):
                before = os.stat(name, dir_fd=root, follow_symlinks=False)
                if not stat.S_ISDIR(before.st_mode):
                    _fail("stage_layout")
                descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root)
                descriptors.append(descriptor)
                pin = installer._directory_identity(before)
                if installer._directory_identity(os.fstat(descriptor)) != pin:
                    _fail("stage_changed")
                pins[name] = pin
            for name, descriptor in (("", root), ("bin", descriptors[0]), ("libexec", descriptors[1])):
                names = set()
                with os.scandir(descriptor) as entries:
                    for entry in entries:
                        names.add(entry.name)
                        if len(names) > len(expected[name]):
                            _fail("stage_layout")
                if names != expected[name]:
                    _fail("stage_layout")
            for name, descriptor in zip(("bin", "libexec"), descriptors):
                if installer._directory_identity(os.fstat(descriptor)) != pins[name] or installer._directory_identity(
                        os.stat(name, dir_fd=root, follow_symlinks=False)) != pins[name]:
                    _fail("stage_changed")
        finally:
            primary, cleanup = sys.exc_info()[1], None
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError as error:
                    cleanup = error
            if cleanup is not None and primary is None:
                _fail("cleanup_unknown")
    return pins


def _capture_stage(stage):
    pins = _layout(stage)
    captured = {name: _read(stage / name, package.MAX_MEMBER_BYTES, mode) for name, mode in package.PAYLOAD}
    if sum(len(data) for data, _pin in captured.values()) > package.MAX_TOTAL_BYTES:
        _fail("stage_limit")
    if _layout(stage) != pins:
        _fail("stage_changed")
    return pins, captured


def _sources():
    directory = Path(__file__).absolute().parent
    captured = {name: _read(directory / name if name != "LICENSE" else directory.parent / name,
                            2 * 1024 * 1024, 0o644) for name in BOOTSTRAP if name != "INSTALL.txt"}
    if _sha(captured["package.py"][0]) != installer.PACKAGE_SHA256:
        _fail("bootstrap_package_drift")
    return captured


def _owner(record):
    if type(record) is not dict or record.get("state") != "found":
        _fail("metadata_required")
    for key, pattern in (("owner", package._OWNER), ("nevra", package._NEVRA)):
        if type(record.get(key)) is not str or pattern.fullmatch(record[key]) is None:
            _fail("metadata_required")
    return {"owner": record["owner"], "nevra": record["nevra"]}


def _projection(raw, stage, captured, controls_data):
    _fields(raw, ("catalog", "data"), "observer_schema")
    catalog = raw["catalog"]
    if type(catalog) is not dict or catalog.get("schema") != "orla-launcher-host-catalog-0.1" \
            or catalog.get("target") != package.TARGET or catalog.get("channel") != package.CHANNEL:
        _fail("catalog_schema")
    stage_files = catalog.get("stageFiles")
    if type(stage_files) is not list or len(stage_files) != len(package.PAYLOAD):
        _fail("stage_observations")
    for record, (name, mode) in zip(stage_files, package.PAYLOAD):
        data = captured[name][0]
        if type(record) is not dict or any(record.get(key) != value for key, value in {
                "path": name, "state": "found", "mode": f"{mode:04o}", "size": len(data), "sha256": _sha(data)}.items()):
            _fail("stage_observations")
    records = catalog.get("observations")
    if type(records) is not list or len(records) > 4096:
        _fail("catalog_schema")
    by_path = {}
    for record in records:
        if type(record) is not dict or type(record.get("namespace")) is not str or record["namespace"] in by_path:
            _fail("catalog_schema")
        by_path[record["namespace"]] = record
    def observed(path):
        record = by_path.get(path)
        if record is None or record.get("state") != "found" or record.get("kind") != "file" \
                or record.get("hashCoverage") != "complete_stable_read" \
                or type(record.get("sha256")) is not str or package._SHA256.fullmatch(record["sha256"]) is None \
                or type(record.get("size")) is not int or not 0 < record["size"] <= package.MAX_MEMBER_BYTES:
            _fail("direct_observation_required")
        return record
    graph = catalog.get("catalogGraph")
    if type(graph) is not dict or type(graph.get("edges")) is not list or len(graph["edges"]) > 16384:
        _fail("catalog_schema")
    def needed(source, names):
        result = []
        for name in sorted(set(names)):
            edges = [edge for edge in graph["edges"] if edge.get("source") == source and edge.get("name") == name]
            if not edges or any(edge.get("catalogState") != "object" or type(edge.get("target")) is not str for edge in edges) \
                    or len({edge["target"] for edge in edges}) != 1:
                _fail("direct_dependency_required")
            result.append({"soname": name, **_owner(observed(edges[0]["target"]).get("package"))})
        return result
    main = str(stage / "bin/orla-launcher")
    main_record = observed(main)
    main_data = captured["bin/orla-launcher"][0]
    main_tags = package._inventory_dynamic(main_data, main=True)
    if main_record["sha256"] != _sha(main_data) or main_record["size"] != len(main_data) \
            or main_record.get("dynamicTags") != main_tags:
        _fail("stage_observations")
    expected_roots = [{"id": "staged_launcher", "path": main, "required": True}] + [
        {"id": role, "path": path, "required": True} for role, path in sorted(package._EXACT_ASSET_PATHS.items())
        if role != "qml_controls_qmldir"]
    if catalog.get("roots") != expected_roots:
        _fail("catalog_roots")
    assets = []
    for root in expected_roots[1:]:
        record = observed(root["path"])
        tags = record.get("dynamicTags")
        if type(tags) is not dict or tags.get("type") != "shared_object" or type(tags.get("needed")) is not list:
            _fail("direct_tags")
        assets.append({"role": root["id"], "kind": "elf", "path": root["path"],
                       **_owner(record.get("package")), "needed": needed(root["path"], tags["needed"])})
    extra = raw["data"]
    if type(extra) is not list or len(extra) != 4:
        _fail("data_observations")
    extra_by_role, evidence_data = {}, []
    for record in extra:
        _fields(record, ("role", "path", "state", "kind", "content", "package", "sha256", "size"), "data_observations")
        role = record["role"]
        if type(role) is not str or role not in DATA_PATHS or role in extra_by_role \
                or record["path"] != DATA_PATHS[role] or record["state"] != "found" or record["kind"] != "file" \
                or type(record["content"]) is not bytes or not 0 < len(record["content"]) <= (
                    package.MAX_MEMBER_BYTES if role == "bwrap" else package.MAX_MANIFEST_BYTES) \
                or record["sha256"] != _sha(record["content"]) or type(record["size"]) is not int \
                or record["size"] != len(record["content"]):
            _fail("data_observations")
        _owner(record["package"])
        extra_by_role[role] = record
        evidence_data.append({key: value for key, value in record.items() if key != "content"})
    controls = extra_by_role["qml_controls_qmldir"]["content"]
    fusion = extra_by_role["qml_fusion_qmldir"]["content"]
    button = extra_by_role["qml_controls_implementation"]["content"]
    if str(controls_data) != DATA_PATHS["qml_controls_implementation"] \
            or b"module QtQuick.Controls" not in controls.splitlines() \
            or b"module QtQuick.Controls.Fusion" not in fusion.splitlines() \
            or not any(re.fullmatch(rb"Button\s+[0-9]+\.[0-9]+\s+Button\.qml", line) for line in fusion.splitlines()) \
            or button.startswith(b"\x7fELF") or b"import QtQuick" not in button:
        _fail("controls_data_unproven")
    for role in ("qml_controls_qmldir", "qml_controls_implementation"):
        record = extra_by_role[role]
        assets.append({"role": role, "kind": "data", "path": record["path"],
                       **_owner(record["package"]), "needed": []})
    bwrap = extra_by_role["bwrap"]
    inventory = {"source": "caller_assertion_unverified", "elf_direct": {
        "interpreter": main_tags["interpreter"], "needed": needed(main, main_tags["needed"]),
        "rpath": main_tags["rpath"], "runpath": main_tags["runpath"]},
        "dynamic_assets": sorted(assets, key=lambda item: (item["role"], item["path"])),
        "optional_capabilities": [{"name": "bwrap", "path": bwrap["path"], **_owner(bwrap["package"])}]}
    package.validate_runtime_inventory(inventory, package.parse_elf(main_data))
    return inventory, {"catalog": catalog, "data": evidence_data}


def _bootstrap_bytes(content):
    handle = io.BytesIO()
    with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in BOOTSTRAP:
            member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            member.create_system = 3
            member.external_attr = (stat.S_IFREG | 0o644) << 16
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, content[name])
    data = handle.getvalue()
    if len(data) > MAX_BOOTSTRAP:
        _fail("bootstrap_limit")
    return data


def _bootstrap_content(data):
    if len(data) > MAX_BOOTSTRAP:
        _fail("bootstrap_limit")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.namelist() != list(BOOTSTRAP):
                _fail("bootstrap_members")
            result, total = {}, 0
            for member in archive.infolist():
                if member.create_system != 3 or member.external_attr >> 16 != (stat.S_IFREG | 0o644) \
                        or member.flag_bits & 1 or not 0 < member.file_size <= 2 * 1024 * 1024 \
                        or member.file_size > max(member.compress_size, 1) * package.MAX_EXPANSION_RATIO:
                    _fail("bootstrap_member")
                total += member.file_size
                if total > MAX_BOOTSTRAP:
                    _fail("bootstrap_limit")
                with archive.open(member) as stream:
                    content = stream.read(member.file_size + 1)
                if len(content) != member.file_size:
                    _fail("bootstrap_member")
                result[member.filename] = content
            return result
    except ArtifactError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        _fail("bootstrap_zip")


def _file_record(name, data):
    return {"name": name, "sha256": _sha(data), "size": len(data)}


def _names(version, commit):
    return (f"orla-launcher-{version}-{commit}.zip", "orla-launcher-bootstrap.zip",
            "runtime-inventory.json", "observations.json", "artifact.json", "SHA256SUMS")


_CI_IMAGE = "sha256:1b8544582f974533fb8d9a5d6bf6dc2caf0d977ea54979d5e864a6ffd345c32e"
_SOURCE_FILES = ("launcher/install.py", "launcher/package.py", "LICENSE", "package/metadata.json")
_SOURCE_LIMIT = 1024 * 1024
_BUTTON = "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/Button.qml"
_EXTRA_FILES = (
    ("qml_controls_qmldir", "/usr/lib64/qt6/qml/QtQuick/Controls/qmldir"),
    ("qml_fusion_qmldir", "/usr/lib64/qt6/qml/QtQuick/Controls/Fusion/qmldir"),
    ("qml_controls_implementation", _BUTTON),
    ("bwrap", "/usr/bin/bwrap"),
)


class _HostObservations:
    def collect(self, stage, controls_data):
        if not isinstance(controls_data, Path) or str(controls_data) != _BUTTON:
            raise ArtifactError("controls_path")
        catalog = inventory_host.collect_host_catalog(stage)
        if type(catalog) is not dict or catalog.get("truncated") or catalog.get("schema") != inventory_host.SCHEMA \
                or any(type(catalog.get(key)) is not list or len(catalog[key]) > 4096 for key in ("ancestors", "observations")):
            _fail("catalog_incomplete")
        budget = {"deadline": time.monotonic() + 20.0, "bytes": 0, "finalReserve": 3.1}
        retained, records = [], []
        replay = None
        try:
            for role, path in _EXTRA_FILES:
                parents = package._inventory_parents(path, budget)
                limit = package.MAX_MEMBER_BYTES if role == "bwrap" else package.MAX_MANIFEST_BYTES
                content, pin = package._inventory_read(path, limit, budget, parents)
                package._inventory_recheck(parents, path, pin, budget)
                package._inventory_step(budget, 3.1)
                owner = package._doctor_rpm(path)
                package._inventory_step(budget)
                package._inventory_recheck(parents, path, pin, budget)
                records.append({"role": role, "path": path, "state": "found", "kind": "file",
                                "content": content, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
                                "package": {"state": "found", "owner": owner["owner"], "nevra": owner["nevra"]}})
                retained.append((parents, path, pin))
            # Fresh replay has no RPM; bind every retained catalog identity after
            # the LAST extra metadata query without promoting catalog UNKNOWN.
            budget["finalReserve"] = 0.0
            package._inventory_step(budget)
            replay = inventory_host._Collector(inventory_host._Operations(), inventory_host._limits(None))
            replay.deadline = budget["deadline"]
            replay.finalizing = True
            replay.ancestors = {item["namespace"]: tuple(item["pin"]) for item in catalog["ancestors"]}
            # A raw alias proof may visit directories omitted by normalized paths.
            for directory in replay.ancestors:
                package._inventory_step(budget)
                with replay.parent(directory.rstrip("/") + "/.orla-artifact-replay"):
                    pass
            for record in catalog["observations"]:
                if record.get("pin") is not None or record.get("state") == "absent":
                    package._inventory_step(budget)
                    replay.replay_record(record["namespace"], record)
            for parents, path, pin in retained:
                package._inventory_recheck(parents, path, pin, budget)
            package._inventory_step(budget)
        except (package.PackageError, inventory_host.HostInventoryError, OSError) as error:
            code = error.code if hasattr(error, "code") else "observation_unknown"
            if replay is not None and type(replay.first_error) is dict:
                code = replay.first_error["code"]
            raise ArtifactError(code) from None
        return {"catalog": catalog, "data": records}


def _ci_git(root, arguments):
    command = ["/usr/bin/git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "safe.directory=" + str(root),
               "-C", str(root), *arguments]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, cwd="/", timeout=5.0, check=False,
                                env={"HOME": "/dev/null", "XDG_CONFIG_HOME": "/dev/null",
                                     "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                                     "LC_ALL": "C", "PATH": "/usr/bin:/bin"})
    except (OSError, subprocess.TimeoutExpired):
        raise ArtifactError("source_git") from None
    if result.returncode:
        raise ArtifactError("source_dirty" if arguments[:1] == ["diff"] and result.returncode == 1 else "source_git")
    if len(result.stdout) > _SOURCE_LIMIT:
        raise ArtifactError("source_limit")
    return result.stdout


def _ci_source_bytes(root, relative):
    budget = {"deadline": time.monotonic() + 5.0, "bytes": 0}
    path = str(root / relative)
    try:
        parents = package._inventory_parents(path, budget)
        content, pin = package._inventory_read(path, _SOURCE_LIMIT, budget, parents)
        package._inventory_recheck(parents, path, pin, budget)
    except (package.PackageError, OSError):
        raise ArtifactError("source_read") from None
    return content


def _ci_context(commit, ci_image_digest):
    if type(commit) is not str or package._COMMIT.fullmatch(commit) is None or ci_image_digest != _CI_IMAGE:
        raise ArtifactError("ci_context")
    values = {name: os.environ.get(name) for name in
              ("GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA")}
    if values["GITHUB_ACTIONS"] != "true" or values["GITHUB_REPOSITORY"] != "caiolombello/orla-desktop" \
            or values["GITHUB_SHA"] != commit \
            or any(type(values[name]) is not str or re.fullmatch(r"[1-9][0-9]{0,19}", values[name]) is None
                   for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")):
        raise ArtifactError("ci_context")
    return {"origin": "github_actions_declared", "repository": values["GITHUB_REPOSITORY"],
            "run_id": values["GITHUB_RUN_ID"], "run_attempt": values["GITHUB_RUN_ATTEMPT"],
            "commit": commit, "ci_image_digest": ci_image_digest}


def _ci_source_snapshot(source_root, *, version, commit, ci_image_digest):
    provenance = _ci_context(commit, ci_image_digest)
    if not isinstance(source_root, Path) or type(version) is not str or package._VERSION.fullmatch(version) is None:
        raise ArtifactError("source_identity")
    try:
        package._safe_absolute_path(str(source_root), "source_identity")
    except package.PackageError:
        raise ArtifactError("source_identity") from None
    if _ci_git(source_root, ["rev-parse", "--verify", "HEAD"]) != commit.encode("ascii") + b"\n":
        raise ArtifactError("source_head")
    clean = ["diff", "--quiet", "--no-ext-diff", "--no-textconv", "--ignore-submodules", "HEAD", "--"]
    _ci_git(source_root, clean)
    files = {}
    for relative in _SOURCE_FILES:
        captured = _ci_source_bytes(source_root, relative)
        reference = commit + ":" + relative
        size = _ci_git(source_root, ["cat-file", "-s", reference])
        if re.fullmatch(rb"[1-9][0-9]{0,6}\n", size) is None or int(size) > _SOURCE_LIMIT:
            raise ArtifactError("source_limit")
        blob = _ci_git(source_root, ["show", "--no-ext-diff", "--no-textconv", reference])
        if len(blob) != int(size) or blob != captured:
            raise ArtifactError("source_changed")
        files[relative] = captured
    try:
        metadata = package._strict_json(files["package/metadata.json"])
        if type(metadata) is not dict or type(metadata.get("KPlugin")) is not dict \
                or metadata["KPlugin"].get("Version") != version:
            raise ArtifactError("source_version")
    except package.PackageError:
        raise ArtifactError("source_version") from None
    _ci_git(source_root, clean)
    if _ci_git(source_root, ["rev-parse", "--verify", "HEAD"]) != commit.encode("ascii") + b"\n":
        raise ArtifactError("source_head")
    if _ci_context(commit, ci_image_digest) != provenance:
        raise ArtifactError("ci_context")
    return {"root": source_root, "files": files, "provenance": provenance, "version": version}


def _ci_source_recheck(snapshot):
    context = snapshot["provenance"]
    current = _ci_source_snapshot(snapshot["root"], version=snapshot["version"],
                                  commit=context["commit"], ci_image_digest=context["ci_image_digest"])
    if current["files"] != snapshot["files"] or current["provenance"] != context:
        raise ArtifactError("source_changed")
    return current["provenance"]


def _instructions(archive_name, archive_sha, commit, origin):
    return (f"Experimental {origin} bundle; runtime unverified; Native UNRUN.\n"
        "Verify the archive SHA256 through an independently trusted channel before installation.\n"
        f"python3 -I -B install.py install {archive_name} --sha256 {archive_sha} --commit {commit}\n"
        "After installation: ~/.local/bin/orla-launcherctl status\n"
        "Manual launch: ~/.local/bin/orla-launcher\n"
        "Remove managed files: ~/.local/bin/orla-launcherctl uninstall\n").encode("ascii")


def produce(stage: Path, output: Path, *, version: str, commit: str,
            ci_image_digest: str, controls_data: Path, observations_backend=None) -> dict:
    for path in (stage, output, controls_data):
        installer._absolute(path)
    package._bounded_string(version, package._VERSION, "version")
    package._bounded_string(commit, package._COMMIT, "commit")
    if type(ci_image_digest) is not str or not ci_image_digest.startswith("sha256:") \
            or package._SHA256.fullmatch(ci_image_digest[7:]) is None:
        _fail("ci_image_digest")
    try:
        output.relative_to(stage)
    except ValueError:
        pass
    else:
        _fail("output_path")
    snapshot = None
    if observations_backend is None:
        snapshot = _ci_source_snapshot(Path(__file__).absolute().parent.parent,
            version=version, commit=commit, ci_image_digest=ci_image_digest)
        observations_backend = _HostObservations()
    stage_pins, captured = _capture_stage(stage)
    sources = _sources()
    if snapshot is not None and any(data != snapshot["files"]["LICENSE" if name == "LICENSE" else "launcher/" + name]
            for name, (data, _pin) in sources.items()):
        _fail("bootstrap_source_drift")
    provenance = {**(snapshot["provenance"] if snapshot is not None else {"origin": "fixture_unverified"}),
                  "runtime": "unverified", "Native": "UNRUN"}
    raw = observations_backend.collect(stage, controls_data)
    inventory, evidence = _projection(raw, stage, captured, controls_data)
    # Freeze the observer result before any publication and without mutating it.
    inventory_data, evidence_data = _json(inventory), _json(evidence)
    names = _names(version, commit)
    created, output_pin = False, None
    try:
        with installer._directory(output.parent) as parent:
            try:
                os.mkdir(output.name, 0o700, dir_fd=parent)
            except FileExistsError:
                _fail("output_exists")
            created = True
            output_pin = installer._directory_identity(os.stat(output.name, dir_fd=parent, follow_symlinks=False))
        archive_sha = package.build(stage, output / names[0], version=version, commit=commit,
                                    ci_image_digest=ci_image_digest, runtime_inventory=inventory)
        archive_data = _read(output / names[0], package.MAX_ARCHIVE_BYTES)[0]
        if _sha(archive_data) != archive_sha:
            _fail("archive_changed")
        manifest = package._verify_archive_data(archive_data, expected_commit=commit)
        expected_files = [{"path": name, "mode": f"{mode:04o}", "size": len(captured[name][0]),
                           "sha256": _sha(captured[name][0])} for name, mode in package.PAYLOAD]
        if manifest["files"] != expected_files:
            _fail("stage_changed")
        final_pins, final_stage = _capture_stage(stage)
        if final_pins != stage_pins or final_stage != captured or _sources() != sources:
            _fail("producer_input_changed")
        instructions = _instructions(names[0], archive_sha, commit, provenance["origin"])
        bootstrap = _bootstrap_bytes({**{name: data for name, (data, _pin) in sources.items()}, "INSTALL.txt": instructions})
        contents = {names[0]: archive_data, names[1]: bootstrap, names[2]: inventory_data, names[3]: evidence_data}
        descriptor = {"schema": SCHEMA, "version": version, "commit": commit, "target": package.TARGET,
            "channel": package.CHANNEL, "archive": _file_record(names[0], archive_data),
            "bootstrap": _file_record(names[1], bootstrap), "sourceInventory": _file_record(names[2], inventory_data),
            "observations": _file_record(names[3], evidence_data),
            "provenance": provenance}
        for name in names[1:4]:
            installer._write_new(output / name, contents[name], 0o644)
        # READY files come last and only after final captured input comparisons.
        with installer._directory(output) as directory:
            if installer._directory_identity(os.fstat(directory)) != output_pin:
                _fail("output_changed")
        if snapshot is not None and _ci_source_recheck(snapshot) != snapshot["provenance"]:
            _fail("source_changed")
        contents[names[4]] = _json(descriptor, package.MAX_MANIFEST_BYTES)
        installer._write_new(output / names[4], contents[names[4]], 0o644)
        sums = "".join(f"{_sha(contents[name])}  {name}\n" for name in sorted(contents)).encode("ascii")
        installer._write_new(output / names[5], sums, 0o644)
        verified, _contents, _bootstrap = _verified_bundle(output)
        return verified
    except BaseException:
        if created and output_pin is not None:
            # Never leave READY markers after a failed private production.
            for name in (names[5], names[4]):
                try:
                    with installer._directory(output) as directory:
                        if installer._directory_identity(os.fstat(directory)) == output_pin:
                            os.unlink(name, dir_fd=directory)
                except (OSError, installer.InstallError):
                    pass
        raise


def _verified_bundle(output):
    installer._absolute(output)
    descriptor_data, descriptor_pin = _read(output / "artifact.json", package.MAX_MANIFEST_BYTES, 0o644)
    descriptor = _decode(descriptor_data, package.MAX_MANIFEST_BYTES)
    _fields(descriptor, ("schema", "version", "commit", "target", "channel", "archive", "bootstrap",
                         "sourceInventory", "observations", "provenance"), "artifact_schema")
    if descriptor["schema"] != SCHEMA or descriptor["target"] != package.TARGET or descriptor["channel"] != package.CHANNEL:
        _fail("artifact_schema")
    package._bounded_string(descriptor["version"], package._VERSION, "version")
    package._bounded_string(descriptor["commit"], package._COMMIT, "commit")
    provenance = descriptor["provenance"]
    if type(provenance) is not dict or provenance.get("runtime") != "unverified" or provenance.get("Native") != "UNRUN":
        _fail("artifact_provenance")
    if provenance.get("origin") == "fixture_unverified":
        _fields(provenance, ("origin", "runtime", "Native"), "artifact_provenance")
    elif provenance.get("origin") == "github_actions_declared":
        _fields(provenance, ("origin", "runtime", "Native", "repository", "run_id", "run_attempt", "commit", "ci_image_digest"),
                "artifact_provenance")
        if provenance["repository"] != "caiolombello/orla-desktop" or provenance["commit"] != descriptor["commit"] \
                or provenance["ci_image_digest"] != _CI_IMAGE or any(type(provenance[key]) is not str \
                    or re.fullmatch(r"[1-9][0-9]{0,19}", provenance[key]) is None for key in ("run_id", "run_attempt")):
            _fail("artifact_provenance")
    else:
        _fail("artifact_provenance")
    names = _names(descriptor["version"], descriptor["commit"])
    with installer._directory(output) as directory:
        observed = set()
        with os.scandir(directory) as entries:
            for entry in entries:
                observed.add(entry.name)
                if len(observed) > 6:
                    _fail("bundle_members")
        if observed != set(names):
            _fail("bundle_members")
    contents, pins = {"artifact.json": descriptor_data}, {"artifact.json": descriptor_pin}
    for name, limit in ((names[0], package.MAX_ARCHIVE_BYTES), (names[1], MAX_BOOTSTRAP),
                        (names[2], MAX_JSON), (names[3], MAX_JSON), (names[5], 4096)):
        contents[name], pins[name] = _read(output / name, limit, None if name == names[0] else 0o644)
    for key, name in zip(("archive", "bootstrap", "sourceInventory", "observations"), names[:4]):
        _fields(descriptor[key], ("name", "sha256", "size"), "artifact_record")
        if descriptor[key] != _file_record(name, contents[name]) or type(descriptor[key]["size"]) is not int:
            _fail("artifact_digest")
    expected_sums = "".join(f"{_sha(contents[name])}  {name}\n" for name in sorted(names[:5])).encode("ascii")
    if contents[names[5]] != expected_sums:
        _fail("bundle_checksums")
    manifest = package._verify_archive_data(contents[names[0]], expected_commit=descriptor["commit"])
    if manifest["schema"] != package.SCHEMA:
        _fail("artifact_package_schema")
    if provenance["origin"] == "github_actions_declared" and manifest["ci_image_digest"] != provenance["ci_image_digest"]:
        _fail("artifact_provenance")
    inventory = _decode(contents[names[2]])
    package.validate_runtime_inventory(inventory)
    if manifest["version"] != descriptor["version"] or manifest["runtime_inventory"] != inventory:
        _fail("artifact_inventory")
    evidence = _decode(contents[names[3]])
    _fields(evidence, ("catalog", "data"), "observer_schema")
    bootstrap = _bootstrap_content(contents[names[1]])
    if bootstrap["INSTALL.txt"] != _instructions(names[0], descriptor["archive"]["sha256"], descriptor["commit"], provenance["origin"]):
        _fail("bootstrap_instructions")
    if _sha(bootstrap["package.py"]) != installer.PACKAGE_SHA256:
        _fail("bootstrap_package_drift")
    sources = _sources()
    if any(bootstrap[name] != data for name, (data, _pin) in sources.items()):
        _fail("bootstrap_source_drift")
    # Return the same captured buffers which passed validation, never reopen for use.
    for name, pin in pins.items():
        if _read(output / name, max(len(contents[name]), 1))[1] != pin:
            _fail("bundle_changed")
    return descriptor, contents, bootstrap


def verify_bundle(output: Path) -> dict:
    return _verified_bundle(output)[0]


def smoke_install(output: Path) -> dict:
    descriptor, contents, bootstrap = _verified_bundle(output)
    with tempfile.TemporaryDirectory(prefix="orla-artifact-smoke-") as temporary:
        root = Path(temporary)
        bundle = root / "bootstrap"
        bundle.mkdir(mode=0o700)
        for name in BOOTSTRAP:
            installer._write_new(bundle / name, bootstrap[name], 0o644)
        archive = root / descriptor["archive"]["name"]
        installer._write_new(archive, contents[archive.name], 0o600)
        home, outside = root / "home", root / "outside"
        outside.mkdir(mode=0o700)
        data_home, state_home = home / ".local/share", home / ".local/state"
        userdata = {home / ".config/orla/aliases.json": b'{"fixture":"alias"}\n',
                    home / ".config/kglobalshortcutsrc": b"[fixture]\nunchanged=Meta\n",
                    data_home / "orla-desktop/user-data/favorites.json": b'{"fixture":"favorite"}\n',
                    state_home / "orla/layout/first.json": b'{"fixture":"immutable"}\n'}
        for path, data in userdata.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            installer._write_new(path, data, 0o600)
        before = {path: _read(path, 4096, 0o600) for path in userdata}
        name = "_orla_verified_artifact_smoke_install"
        specification = importlib.util.spec_from_file_location(name, bundle / "install.py")
        manager = importlib.util.module_from_spec(specification)
        old_module = sys.modules.get(name)
        sys.modules[name] = manager
        try:
            exec(compile(bootstrap["install.py"], str(bundle / "install.py"), "exec"), manager.__dict__)
            paths = manager.InstallPaths(home, data_home, state_home)
            installed = manager.install_archive(archive, expected_sha256=descriptor["archive"]["sha256"],
                                                expected_commit=descriptor["commit"], paths=paths)
            if installed["status"] != "installed" or installed["runtime"] != "unverified":
                _fail("smoke_install")
            bundle.rename(root / "bootstrap-unavailable")
            if bundle.exists():
                _fail("smoke_source_present")
            controller = home / ".local/bin/orla-launcherctl"
            environment = {"HOME": str(home), "XDG_DATA_HOME": str(data_home),
                           "XDG_STATE_HOME": str(state_home), "PATH": "/usr/bin:/bin"}
            for command, expected in (("status", "installed"), ("uninstall", "uninstalled")):
                completed = subprocess.run([str(controller), command], cwd=outside, env=environment,
                                           capture_output=True, text=True, timeout=10, check=False)
                if completed.returncode != 0:
                    _fail("smoke_controller")
                report = _decode(completed.stdout.encode("utf-8"), package.MAX_MANIFEST_BYTES)
                if report.get("status") != expected or report.get("runtime") != "unverified":
                    _fail("smoke_controller")
            if before != {path: _read(path, 4096, 0o600) for path in userdata}:
                _fail("smoke_userdata")
            if any(path.exists() for path in (home / ".local/bin/orla-launcher", controller,
                    data_home / "applications/org.orla.Launcher.desktop", data_home / "orla-desktop/launcher")):
                _fail("smoke_managed_remains")
        finally:
            if old_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old_module
    return {"status": "uninstalled", "runtime": "unverified", "userdataPreserved": True,
            "sourceAbsent": True, "Native": "UNRUN"}


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    producer = commands.add_parser("produce")
    for name in ("stage", "output", "controls-data"):
        producer.add_argument("--" + name, type=Path, required=True)
    for name in ("version", "commit", "ci-image-digest"):
        producer.add_argument("--" + name, required=True)
    for name in ("verify", "smoke"):
        commands.add_parser(name).add_argument("--bundle", type=Path, required=True)
    options = parser.parse_args(arguments)
    try:
        if options.command == "produce":
            report = produce(options.stage, options.output, version=options.version, commit=options.commit,
                ci_image_digest=options.ci_image_digest, controls_data=options.controls_data)
        elif options.command == "verify":
            report = verify_bundle(options.bundle)
        else:
            report = smoke_install(options.bundle)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except (ArtifactError, package.PackageError, installer.InstallError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "error", "code": getattr(error, "code", "artifact_unknown")}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
