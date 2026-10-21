#!/usr/bin/env python3
"""Build and verify the fixed workspace distribution without Qt or extraction."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile
import zlib

PAYLOAD = tuple(sorted((
    "LICENSE", "workspace/Workspace.qml", "workspace/CompositionView.qml",
    "scripts/workspace_setup.py", "scripts/workspace_layout.py", "scripts/panel_layout.py",
    "scripts/panel_layout.js", "scripts/panel_layout_update.py", "layouts/mac-inspired-topbar.json",
    "package/contents/code/Style.js", "package/contents/ui/Card.qml",
    "package/contents/ui/OrlaButton.qml", "workspace/main.py", "workspace/package.py",
    "workspace/__init__.py", "scripts/__init__.py",
    "workspace/Updates.qml", "scripts/updates.py", "scripts/updates_contract.py",
    "scripts/updates_desktop_state.py", "scripts/updates_desktop.py",
)))
RUNTIME = {"pythonMinimum": "3.10", "pysideMinimum": "6.11", "qtMinimum": "6.11", "plasmaExact": "6.7.5"}
MEMBER_LIMIT, TOTAL_LIMIT, MANIFEST_LIMIT, ARCHIVE_LIMIT = 2 << 20, 4 << 20, 64 << 10, 16 << 20


class PackageError(Exception):
    """Stable public error code; never include paths or underlying exception text."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{%d}" % length, value) is not None


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", value):
        return False
    pre = value.split("+", 1)[0].split("-", 1)
    return len(pre) == 1 or all(not (part.isdigit() and len(part) > 1 and part[0] == "0") for part in pre[1].split("."))


def _root_fd(root):
    if not isinstance(root, Path) or not root.is_absolute():
        raise PackageError("invalid_root")
    try:
        return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, ValueError):
        raise PackageError("invalid_root") from None


def _read_at(directory, name, limit, *, mode=False):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or (mode and stat.S_IMODE(info.st_mode) != 0o644):
                raise PackageError("invalid_file")
            if info.st_size > limit:
                raise PackageError("size_limit")
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise PackageError("size_limit")
            return data
    except (OSError, ValueError):
        raise PackageError("invalid_file") from None


def _source(root, name, limit):
    fd = _root_fd(root)
    try:
        for part in name.split("/")[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return _read_at(fd, name.split("/")[-1], limit)
    except (OSError, ValueError):
        raise PackageError("invalid_file") from None
    finally:
        os.close(fd)


def _records(files):
    return [dict(path=name, size=len(files[name]), mode=0o644, sha256=hashlib.sha256(files[name]).hexdigest()) for name in PAYLOAD]


def build(root: Path, output_dir: Path, *, commit: str) -> Path:
    if not _hex(commit, 40):
        raise PackageError("invalid_commit")
    commit = commit.lower()
    try:
        version = json.loads(_source(root, "package/metadata.json", MANIFEST_LIMIT))["KPlugin"]["Version"]
    except (ValueError, KeyError, TypeError, RecursionError):
        raise PackageError("invalid_version") from None
    if not _version(version):
        raise PackageError("invalid_version")
    files = {}
    for name in PAYLOAD:
        files[name] = _source(root, name, MEMBER_LIMIT)
        if sum(map(len, files.values())) > TOTAL_LIMIT:
            raise PackageError("size_limit")
    manifest = dict(schema="orla-workspace-package-0.2", component="workspace", version=version, commit=commit, runtime=RUNTIME, files=_records(files))
    files["manifest.json"] = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, files[name])
    data = buffer.getvalue()
    verify_archive(data, expected_sha256=hashlib.sha256(data).hexdigest(), expected_commit=commit)
    temporary = None
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"orla-workspace-{version}.zip"
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".orla-workspace-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, output)
        return output
    except (OSError, ValueError):
        raise PackageError("output_error") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                raise PackageError("output_error") from None


def _unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate key")
    return result


def _manifest(data, files):
    try:
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_unique)
        if (not isinstance(manifest, dict)
                or set(manifest) != {"schema", "component", "version", "commit", "runtime", "files"}
                or manifest["schema"] != "orla-workspace-package-0.2"
                or manifest["component"] != "workspace" or manifest["runtime"] != RUNTIME
                or not _version(manifest["version"]) or not _hex(manifest["commit"], 40)
                or not isinstance(manifest["files"], list) or len(manifest["files"]) != len(PAYLOAD)):
            raise PackageError("invalid_manifest")
        for name, record in zip(PAYLOAD, manifest["files"]):
            if (not isinstance(record, dict) or set(record) != {"path", "size", "mode", "sha256"}
                    or record["path"] != name or type(record["size"]) is not int
                    or not 0 <= record["size"] <= MEMBER_LIMIT or type(record["mode"]) is not int
                    or record["mode"] != 0o644 or not _hex(record["sha256"], 64)):
                raise PackageError("invalid_manifest")
        if manifest["files"] != _records(files):
            raise PackageError("payload_mismatch")
        return manifest
    except (ValueError, TypeError, KeyError, RecursionError):
        raise PackageError("invalid_manifest") from None


def verify_archive(data: bytes, *, expected_sha256: str, expected_commit: str) -> dict:
    if not _hex(expected_sha256, 64):
        raise PackageError("invalid_sha256")
    if not _hex(expected_commit, 40):
        raise PackageError("invalid_commit")
    if not isinstance(data, bytes):
        raise PackageError("invalid_archive")
    if len(data) > ARCHIVE_LIMIT:
        raise PackageError("size_limit")
    if hashlib.sha256(data).hexdigest() != expected_sha256.lower():
        raise PackageError("archive_hash")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(names) != len(PAYLOAD) + 1 or set(names) != set(PAYLOAD) | {"manifest.json"}:
                raise PackageError("invalid_entries")
            if sum(entry.file_size for entry in entries) > TOTAL_LIMIT:
                raise PackageError("size_limit")
            files = {}
            for entry in entries:
                limit = MANIFEST_LIMIT if entry.filename == "manifest.json" else MEMBER_LIMIT
                if entry.file_size > limit:
                    raise PackageError("size_limit")
                if (entry.orig_filename != entry.filename or entry.create_system != 3
                        or entry.external_attr >> 16 != stat.S_IFREG | 0o644
                        or entry.external_attr & 0x10 or entry.flag_bits & 1
                        or entry.date_time != (1980, 1, 1, 0, 0, 0)
                        or entry.compress_type != zipfile.ZIP_DEFLATED):
                    raise PackageError("invalid_entries")
                if entry.file_size > max(entry.compress_size, 1) * 200:
                    raise PackageError("expansion_limit")
                with archive.open(entry) as stream:
                    content = stream.read(limit + 1)
                if len(content) != entry.file_size or len(content) > limit:
                    raise PackageError("size_limit")
                files[entry.filename] = content
            manifest = _manifest(files.pop("manifest.json"), files)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError):
        raise PackageError("invalid_archive") from None
    if manifest["commit"].lower() != expected_commit.lower():
        raise PackageError("commit_mismatch")
    return {"manifest": manifest, "files": files}


def verify_directory(root: Path) -> dict:
    """Check only the chosen root, without resolving or inspecting its ancestors."""
    fd = _root_fd(root)
    files = {}
    directories = {str(parent) for name in PAYLOAD for parent in Path(name).parents if str(parent) != "."}

    def visit(directory, prefix=""):
        with os.scandir(directory) as entries:
            for entry in entries:
                name = prefix + entry.name
                if name in directories:
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        visit(child, name + "/")
                    finally:
                        os.close(child)
                elif name in PAYLOAD or name == "manifest.json":
                    files[name] = _read_at(directory, entry.name, MANIFEST_LIMIT if name == "manifest.json" else MEMBER_LIMIT, mode=True)
                    if sum(map(len, files.values())) > TOTAL_LIMIT:
                        raise PackageError("size_limit")
                else:
                    raise PackageError("invalid_entries")
    try:
        visit(fd)
        if set(files) != set(PAYLOAD) | {"manifest.json"}:
            raise PackageError("invalid_entries")
        return _manifest(files.pop("manifest.json"), files)
    except (OSError, ValueError):
        raise PackageError("invalid_directory") from None
    finally:
        os.close(fd)


def _main(argv=None):
    import argparse

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise PackageError("invalid_arguments")

    parser = Parser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    builder = sub.add_parser("build")
    builder.add_argument("--commit", required=True)
    builder.add_argument("--output-dir", type=Path, required=True)
    verifier = sub.add_parser("verify")
    verifier.add_argument("archive", type=Path)
    verifier.add_argument("--sha256", required=True)
    verifier.add_argument("--commit", required=True)
    try:
        args = parser.parse_args(argv)
        path = build(Path(__file__).resolve().parents[1], args.output_dir, commit=args.commit) if args.action == "build" else args.archive
        data = _source(path.absolute().parent, path.name, ARCHIVE_LIMIT)
        digest = hashlib.sha256(data).hexdigest()
        manifest = verify_archive(data, expected_sha256=digest if args.action == "build" else args.sha256, expected_commit=args.commit)["manifest"]
        result = dict(component="workspace", version=manifest["version"], commit=manifest["commit"], fileCount=len(PAYLOAD), sha256=digest)
        if args.action == "build":
            result["archive"] = str(path)
        print(json.dumps(result, sort_keys=True))
        return 0
    except PackageError as exc:
        print(json.dumps({"error": exc.code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
