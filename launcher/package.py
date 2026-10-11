#!/usr/bin/python3
"""Build and verify the experimental Orla launcher data archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import tempfile
import zipfile
import zlib


SCHEMA = "orla-launcher-package-0.2"
TARGET = "fedora44-x86_64"
CHANNEL = "experimental"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PAYLOAD = (
    ("bin/orla-launcher", 0o755),
    ("libexec/ai.py", 0o644),
    ("libexec/steam.py", 0o644),
    ("LICENSE", 0o644),
)
MEMBERS = tuple(path for path, _mode in PAYLOAD) + ("manifest.json",)
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXPANSION_RATIO = 200
MAX_ELF_PROGRAM_HEADERS = 128
MAX_ELF_DYNAMIC_BYTES = 1024 * 1024
MAX_ELF_STRING_TABLE = 1024 * 1024

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_VERSION = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}\Z", re.ASCII)
_SONAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+~-]{0,254}\Z", re.ASCII)
_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9+_.-]{0,127}\Z", re.ASCII)
_NEVRA = re.compile(r"[A-Za-z0-9][A-Za-z0-9+_.:~-]{0,253}\.x86_64\Z", re.ASCII)

_ASSET_ROLES = {
    "qpa_wayland", "qml_qtquick_plugin", "qml_controls_plugin", "qml_controls_qmldir",
    "qml_controls_implementation", "qml_layouts_plugin", "krunner_services",
    "krunner_calculator",
}
_DATA_ROLES = {"qml_controls_qmldir", "qml_controls_implementation"}
_EXACT_ASSET_PATHS = {
    "qpa_wayland": "/usr/lib64/qt6/plugins/platforms/libqwayland.so",
    "qml_qtquick_plugin": "/usr/lib64/qt6/qml/QtQuick/libqtquick2plugin.so",
    "qml_controls_plugin": "/usr/lib64/qt6/qml/QtQuick/Controls/libqtquickcontrols2plugin.so",
    "qml_controls_qmldir": "/usr/lib64/qt6/qml/QtQuick/Controls/qmldir",
    "qml_layouts_plugin": "/usr/lib64/qt6/qml/QtQuick/Layouts/libqquicklayoutsplugin.so",
    "krunner_services": "/usr/lib64/qt6/plugins/kf6/krunner/krunner_services.so",
    "krunner_calculator": "/usr/lib64/qt6/plugins/kf6/krunner/calculator.so",
}


class PackageError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _reject(code: str) -> None:
    raise PackageError(code)


def _exact_keys(value: object, keys: set[str], code: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        _reject(code)
    return value


def _bounded_string(value: object, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _reject(code)
    return value


def _safe_absolute_path(value: object, code: str) -> str:
    if type(value) is not str or not value or len(value) > 4096:
        _reject(code)
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        _reject(code)
    path = PurePosixPath(value)
    if not path.is_absolute() or value.startswith("//") or str(path) != value or ".." in path.parts:
        _reject(code)
    return value


def _dependency(value: object) -> dict:
    item = _exact_keys(value, {"soname", "owner", "nevra"}, "inventory_dependency")
    _bounded_string(item["soname"], _SONAME, "inventory_dependency")
    _bounded_string(item["owner"], _OWNER, "inventory_dependency")
    _bounded_string(item["nevra"], _NEVRA, "inventory_dependency")
    return item


def _dependencies(value: object, *, allow_empty: bool) -> list[dict]:
    if type(value) is not list or len(value) > 512 or (not allow_empty and not value):
        _reject("inventory_dependency")
    result = [_dependency(item) for item in value]
    names = [item["soname"] for item in result]
    if names != sorted(names) or len(names) != len(set(names)):
        _reject("inventory_dependency")
    return result


def validate_runtime_inventory(value: object, elf: dict | None = None) -> dict:
    inventory = _exact_keys(value, {"source", "elf_direct", "dynamic_assets", "optional_capabilities"},
                            "inventory_schema")
    if inventory["source"] != "caller_assertion_unverified":
        _reject("inventory_source")

    direct = _exact_keys(inventory["elf_direct"],
                         {"interpreter", "needed", "rpath", "runpath"}, "inventory_elf")
    _safe_absolute_path(direct["interpreter"], "inventory_elf")
    direct_needed = _dependencies(direct["needed"], allow_empty=False)
    if direct["rpath"] != [] or direct["runpath"] != []:
        _reject("inventory_search_path")

    assets = inventory["dynamic_assets"]
    if type(assets) is not list or not assets or len(assets) > 256:
        _reject("inventory_assets")
    observed_roles: dict[str, int] = {}
    observed_paths: set[str] = set()
    order: list[tuple[str, str]] = []
    for raw in assets:
        item = _exact_keys(raw, {"role", "kind", "path", "owner", "nevra", "needed"},
                           "inventory_asset")
        role = item["role"]
        if type(role) is not str or role not in _ASSET_ROLES:
            _reject("inventory_asset")
        kind = item["kind"]
        expected_kind = "data" if role in _DATA_ROLES else "elf"
        if kind != expected_kind:
            _reject("inventory_asset")
        path = _safe_absolute_path(item["path"], "inventory_asset")
        if role in _EXACT_ASSET_PATHS and path != _EXACT_ASSET_PATHS[role]:
            _reject("inventory_asset")
        if role == "qml_controls_implementation" and not path.startswith(
                "/usr/lib64/qt6/qml/QtQuick/Controls/"):
            _reject("inventory_asset")
        _bounded_string(item["owner"], _OWNER, "inventory_asset")
        _bounded_string(item["nevra"], _NEVRA, "inventory_asset")
        _dependencies(item["needed"], allow_empty=kind == "data")
        if kind == "data" and item["needed"]:
            _reject("inventory_asset")
        if path in observed_paths:
            _reject("inventory_asset")
        observed_paths.add(path)
        observed_roles[role] = observed_roles.get(role, 0) + 1
        order.append((role, path))
    if order != sorted(order):
        _reject("inventory_assets")
    for role in _ASSET_ROLES:
        count = observed_roles.get(role, 0)
        if (role == "qml_controls_implementation" and count < 1) or (role != "qml_controls_implementation" and count != 1):
            _reject("inventory_assets")

    optional = inventory["optional_capabilities"]
    if type(optional) is not list or len(optional) != 1:
        _reject("inventory_optional")
    capability = _exact_keys(optional[0], {"name", "path", "owner", "nevra"}, "inventory_optional")
    if capability["name"] != "bwrap" or capability["path"] != "/usr/bin/bwrap":
        _reject("inventory_optional")
    _bounded_string(capability["owner"], _OWNER, "inventory_optional")
    _bounded_string(capability["nevra"], _NEVRA, "inventory_optional")

    if elf is not None:
        names = [item["soname"] for item in direct_needed]
        if direct["interpreter"] != elf["interpreter"] or names != sorted(elf["needed"]):
            _reject("inventory_elf_mismatch")
        if direct["rpath"] != elf["rpath"] or direct["runpath"] != elf["runpath"]:
            _reject("inventory_elf_mismatch")
    return inventory


def _slice(data: bytes, offset: int, size: int, code: str = "elf_malformed") -> bytes:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        _reject(code)
    return data[offset:offset + size]


def parse_elf(data: bytes) -> dict:
    if type(data) is not bytes or len(data) < 64 or len(data) > MAX_MEMBER_BYTES:
        _reject("elf_malformed")
    try:
        header = struct.unpack("<16sHHIQQQIHHHHHH", data[:64])
    except struct.error:
        _reject("elf_malformed")
    ident, elf_type, machine, version, _entry, phoff, _shoff, _flags, ehsize, phentsize, phnum, _a, _b, _c = header
    if ident[:7] != b"\x7fELF\x02\x01\x01" or elf_type not in (2, 3) or machine != 62 or version != 1:
        _reject("elf_unsupported")
    if ehsize != 64 or phentsize != 56 or phnum < 1 or phnum > MAX_ELF_PROGRAM_HEADERS:
        _reject("elf_malformed")
    table = _slice(data, phoff, phnum * phentsize)
    headers = []
    try:
        for index in range(phnum):
            headers.append(struct.unpack("<IIQQQQQQ", table[index * 56:(index + 1) * 56]))
    except struct.error:
        _reject("elf_malformed")

    loads = []
    interpreters = []
    dynamics = []
    for kind, _flags, offset, virtual, _physical, file_size, memory_size, _align in headers:
        if file_size > memory_size:
            _reject("elf_malformed")
        _slice(data, offset, file_size)
        if kind == 1:
            loads.append((virtual, offset, file_size))
        elif kind == 3:
            interpreters.append(_slice(data, offset, file_size))
        elif kind == 2:
            if file_size > MAX_ELF_DYNAMIC_BYTES or file_size % 16:
                _reject("elf_malformed")
            dynamics.append(_slice(data, offset, file_size))
    if len(interpreters) != 1 or len(dynamics) != 1 or not loads:
        _reject("elf_malformed")

    def terminated_ascii(raw: bytes, code: str, *, path: bool = False) -> str:
        if not raw or raw[-1:] != b"\0" or b"\0" in raw[:-1]:
            _reject(code)
        try:
            value = raw[:-1].decode("ascii")
        except UnicodeDecodeError:
            _reject(code)
        if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
            _reject(code)
        if path:
            return _safe_absolute_path(value, code)
        return value

    interpreter = terminated_ascii(interpreters[0], "elf_interpreter", path=True)
    tags: list[tuple[int, int]] = []
    terminated = False
    for offset in range(0, len(dynamics[0]), 16):
        tag, value = struct.unpack("<qQ", dynamics[0][offset:offset + 16])
        if tag == 0:
            terminated = True
            break
        tags.append((tag, value))
    if not terminated:
        _reject("elf_malformed")
    strtab_values = [value for tag, value in tags if tag == 5]
    strsz_values = [value for tag, value in tags if tag == 10]
    if len(strtab_values) != 1 or len(strsz_values) != 1 or not 0 < strsz_values[0] <= MAX_ELF_STRING_TABLE:
        _reject("elf_malformed")

    def virtual_to_offset(address: int, size: int) -> int:
        matches = []
        for virtual, offset, file_size in loads:
            if virtual <= address and size <= file_size and address - virtual <= file_size - size:
                matches.append(offset + address - virtual)
        if len(matches) != 1:
            _reject("elf_malformed")
        return matches[0]

    strings = _slice(data, virtual_to_offset(strtab_values[0], strsz_values[0]), strsz_values[0])

    def string_at(index: int, code: str) -> str:
        if index >= len(strings):
            _reject(code)
        end = strings.find(b"\0", index)
        if end < 0 or end - index > 4096:
            _reject(code)
        return terminated_ascii(strings[index:end + 1], code)

    needed = [string_at(value, "elf_needed") for tag, value in tags if tag == 1]
    if not needed or len(needed) != len(set(needed)) or any(_SONAME.fullmatch(item) is None for item in needed):
        _reject("elf_needed")
    rpath = [string_at(value, "elf_search_path") for tag, value in tags if tag == 15]
    runpath = [string_at(value, "elf_search_path") for tag, value in tags if tag == 29]
    if len(rpath) > 1 or len(runpath) > 1:
        _reject("elf_search_path")
    return {
        "interpreter": interpreter,
        "needed": needed,
        "rpath": rpath,
        "runpath": runpath,
    }


def _canonical_stage(stage: Path) -> Path:
    if not isinstance(stage, Path) or not stage.is_absolute():
        _reject("staging_path")
    try:
        status = stage.lstat()
        canonical = stage.resolve(strict=True)
    except OSError:
        _reject("staging_path")
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode) or canonical != stage:
        _reject("staging_path")
    expected = {
        ".": {"bin", "libexec", "LICENSE"},
        "bin": {"orla-launcher"},
        "libexec": {"ai.py", "steam.py"},
    }
    for relative, names in expected.items():
        directory = stage if relative == "." else stage / relative
        try:
            directory_status = directory.lstat()
            actual = {entry.name for entry in os.scandir(directory)}
        except OSError:
            _reject("staging_layout")
        if stat.S_ISLNK(directory_status.st_mode) or not stat.S_ISDIR(directory_status.st_mode) or actual != names:
            _reject("staging_layout")
    return stage


def _read_staged_file(stage: Path, relative: str, expected_mode: int) -> bytes:
    path = stage / relative
    try:
        before = path.lstat()
    except OSError:
        _reject("staging_file")
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        _reject("staging_file")
    if stat.S_IMODE(before.st_mode) != expected_mode or not 0 < before.st_size <= MAX_MEMBER_BYTES:
        _reject("staging_file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
                _reject("staging_changed")
            chunks = []
            remaining = before.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except PackageError:
        raise
    except OSError:
        _reject("staging_file")
    if len(data) != before.st_size or (after.st_dev, after.st_ino, after.st_size) != (
            before.st_dev, before.st_ino, before.st_size):
        _reject("staging_changed")
    return data


def _manifest(version: str, commit: str, ci_image_digest: str, files: list[dict], inventory: dict) -> dict:
    return {
        "schema": SCHEMA,
        "target": TARGET,
        "version": version,
        "channel": CHANNEL,
        "commit": commit,
        "ci_image_digest": ci_image_digest,
        "files": files,
        "runtime_inventory": inventory,
    }


def _manifest_bytes(value: dict) -> bytes:
    data = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    if len(data) > MAX_MANIFEST_BYTES:
        _reject("manifest_limit")
    return data


def _zip_info(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.create_version = 20
    info.extract_version = 20
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.internal_attr = 0
    info.extra = b""
    info.comment = b""
    return info


def build(stage: Path, output: Path, *, version: str, commit: str, ci_image_digest: str,
          runtime_inventory: object) -> str:
    stage = _canonical_stage(stage)
    if not isinstance(output, Path) or not output.is_absolute() or output.name in ("", ".", ".."):
        _reject("output_path")
    _bounded_string(version, _VERSION, "version")
    _bounded_string(commit, _COMMIT, "commit")
    if type(ci_image_digest) is not str or not ci_image_digest.startswith("sha256:") \
            or _SHA256.fullmatch(ci_image_digest[7:]) is None:
        _reject("ci_image_digest")

    captured = {}
    total = 0
    for relative, mode in PAYLOAD:
        data = _read_staged_file(stage, relative, mode)
        captured[relative] = data
        total += len(data)
    if total > MAX_TOTAL_BYTES:
        _reject("total_limit")
    elf = parse_elf(captured["bin/orla-launcher"])
    if elf["rpath"] or elf["runpath"]:
        _reject("elf_search_path")
    inventory = validate_runtime_inventory(runtime_inventory, elf)
    records = [{
        "path": relative,
        "size": len(captured[relative]),
        "mode": f"{mode:04o}",
        "sha256": hashlib.sha256(captured[relative]).hexdigest(),
    } for relative, mode in PAYLOAD]
    manifest_data = _manifest_bytes(_manifest(version, commit, ci_image_digest, records, inventory))

    parent = output.parent
    try:
        output.relative_to(stage)
    except ValueError:
        pass
    else:
        _reject("output_path")
    try:
        parent_status = parent.lstat()
        if stat.S_ISLNK(parent_status.st_mode) or not stat.S_ISDIR(parent_status.st_mode) \
                or parent.resolve(strict=True) != parent:
            _reject("output_path")
        if output.is_symlink() or (output.exists() and not output.is_file()):
            _reject("output_path")
    except PackageError:
        raise
    except OSError:
        _reject("output_path")

    temporary = None
    archive_digest = None
    try:
        handle = tempfile.NamedTemporaryFile(prefix=".orla-package-", suffix=".zip", dir=parent, delete=False)
        temporary = Path(handle.name)
        handle.close()
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
                             strict_timestamps=True) as archive:
            for relative, mode in PAYLOAD:
                archive.writestr(_zip_info(relative, mode), captured[relative], compress_type=zipfile.ZIP_DEFLATED,
                                 compresslevel=9)
            archive.writestr(_zip_info("manifest.json", 0o644), manifest_data,
                             compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.chmod(temporary, 0o644)
        archive_data = _read_archive(temporary)
        archive_digest = hashlib.sha256(archive_data).hexdigest()
        _verify_archive_data(archive_data, expected_commit=commit)
        os.replace(temporary, output)
        temporary = None
    except PackageError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile):
        _reject("archive_write")
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
    if archive_digest is None:
        _reject("archive_write")
    return archive_digest


def _read_archive(path: Path) -> bytes:
    try:
        status = path.lstat()
    except OSError:
        _reject("archive_file")
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode) or status.st_size > MAX_ARCHIVE_BYTES \
            or stat.S_IMODE(status.st_mode) & (0o111 | stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
        _reject("archive_file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino, opened.st_size) != (status.st_dev, status.st_ino, status.st_size):
                _reject("archive_changed")
            chunks = []
            total = 0
            while True:
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    _reject("archive_file")
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except PackageError:
        raise
    except OSError:
        _reject("archive_file")
    if total != status.st_size or (after.st_dev, after.st_ino, after.st_size) != (
            status.st_dev, status.st_ino, status.st_size):
        _reject("archive_changed")
    return b"".join(chunks)


def _safe_member_name(name: object) -> str:
    if type(name) is not str or not name or len(name) > 4096 or "\\" in name or "\0" in name:
        _reject("zip_name")
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        _reject("zip_name")
    path = PurePosixPath(name)
    if path.is_absolute() or str(path) != name or any(part in ("", ".", "..") for part in name.split("/")):
        _reject("zip_name")
    return name


def _archive_records(data: bytes) -> list[dict]:
    if len(data) < 22:
        _reject("zip_invalid")
    eocd_offset = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if eocd_offset < 0 or eocd_offset > len(data) - 22:
        _reject("zip_invalid")
    try:
        signature, disk, central_disk, disk_entries, total_entries, central_size, central_offset, comment_size = \
            struct.unpack_from("<4s4H2IH", data, eocd_offset)
    except struct.error:
        _reject("zip_invalid")
    if signature != b"PK\x05\x06":
        _reject("zip_invalid")
    if eocd_offset + 22 + comment_size != len(data):
        _reject("zip_invalid")
    if comment_size:
        _reject("zip_metadata")
    if disk or central_disk or disk_entries != total_entries:
        _reject("zip_metadata")
    if total_entries != len(MEMBERS):
        _reject("zip_members")
    if central_offset > len(data) or central_size > len(data) - central_offset \
            or central_offset + central_size != eocd_offset:
        _reject("zip_invalid")

    records = []
    position = central_offset
    for _index in range(total_entries):
        if position > central_offset + central_size - 46:
            _reject("zip_invalid")
        try:
            fields = struct.unpack_from("<4s6H3I5H2I", data, position)
        except struct.error:
            _reject("zip_invalid")
        (central_signature, create_version, extract_version, flags, compression, modified_time,
         modified_date, crc, compressed_size, size, name_size, extra_size, member_comment_size,
         start_disk, internal_attr, external_attr, local_offset) = fields
        if central_signature != b"PK\x01\x02":
            _reject("zip_invalid")
        record_end = position + 46 + name_size + extra_size + member_comment_size
        if record_end > central_offset + central_size:
            _reject("zip_invalid")
        raw_name = data[position + 46:position + 46 + name_size]
        try:
            name = raw_name.decode("ascii", "strict")
        except UnicodeDecodeError:
            _reject("zip_name")
        _safe_member_name(name)
        mode = external_attr >> 16
        records.append({
            "name": name,
            "raw_name": raw_name,
            "create_version": create_version,
            "external_mode": mode,
            "extra_size": extra_size,
            "comment_size": member_comment_size,
            "start_disk": start_disk,
            "internal_attr": internal_attr,
            "crc": crc,
            "compressed_size": compressed_size,
            "size": size,
            "local_offset": local_offset,
            "central": (extract_version, flags, compression, modified_time, modified_date, crc,
                        compressed_size, size),
        })
        position = record_end
    if position != central_offset + central_size:
        _reject("zip_invalid")

    names = [record["name"] for record in records]
    if len(names) != len(set(names)):
        _reject("zip_duplicate")
    if names != list(MEMBERS):
        _reject("zip_members")

    expected_modes = dict(PAYLOAD)
    expected_modes["manifest.json"] = 0o644
    for record in records:
        (extract_version, flags, compression, modified_time, modified_date, _crc,
         compressed_size, size) = record["central"]
        if record["create_version"] != 0x0314 or extract_version != 20 or flags != 0 \
                or compression != zipfile.ZIP_DEFLATED or modified_time != 0 or modified_date != 0x21 \
                or record["extra_size"] or record["comment_size"] or record["start_disk"] \
                or record["internal_attr"]:
            _reject("zip_metadata")
        mode = record["external_mode"]
        if not stat.S_ISREG(mode) or stat.S_IMODE(mode) != expected_modes[record["name"]] \
                or mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
            _reject("zip_mode")
        if size > MAX_MEMBER_BYTES:
            _reject("member_limit")
        if record["name"] == "manifest.json" and size > MAX_MANIFEST_BYTES:
            _reject("manifest_limit")
        if size and (compressed_size == 0 or size > compressed_size * MAX_EXPANSION_RATIO):
            _reject("zip_expansion")

    expected_local_offset = 0
    for record in records:
        local_offset = record["local_offset"]
        if local_offset != expected_local_offset or local_offset > central_offset - 30:
            _reject("zip_invalid")
        try:
            local = struct.unpack_from("<4s5H3I2H", data, local_offset)
        except struct.error:
            _reject("zip_invalid")
        (local_signature, extract_version, flags, compression, modified_time, modified_date, crc,
         compressed_size, size, name_size, extra_size) = local
        if local_signature != b"PK\x03\x04":
            _reject("zip_invalid")
        if (extract_version, flags, compression, modified_time, modified_date, crc,
                compressed_size, size) != record["central"] or extra_size:
            _reject("zip_metadata")
        name_start = local_offset + 30
        name_end = name_start + name_size
        if name_end > central_offset:
            _reject("zip_invalid")
        local_name = data[name_start:name_end]
        try:
            decoded_local_name = local_name.decode("ascii", "strict")
        except UnicodeDecodeError:
            _reject("zip_name")
        _safe_member_name(decoded_local_name)
        if local_name != record["raw_name"] or decoded_local_name != record["name"]:
            _reject("zip_name")
        data_start = name_end
        data_end = data_start + compressed_size
        if data_end > central_offset:
            _reject("zip_invalid")
        record["compressed"] = data[data_start:data_end]
        expected_local_offset = data_end
    if expected_local_offset != central_offset:
        _reject("zip_invalid")
    return records


def _decode_member(record: dict) -> bytes:
    expected_size = record["size"]
    decoder = zlib.decompressobj(-15)
    chunks = []
    observed = 0
    compressed = record["compressed"]
    try:
        for offset in range(0, len(compressed), 64 * 1024):
            pending = compressed[offset:offset + 64 * 1024]
            while pending:
                remaining = expected_size + 1 - observed
                if remaining <= 0:
                    _reject("zip_size")
                output = decoder.decompress(pending, remaining)
                chunks.append(output)
                observed += len(output)
                if observed > expected_size:
                    _reject("zip_size")
                pending = decoder.unconsumed_tail
                if decoder.unused_data:
                    _reject("zip_size")
        tail = decoder.flush(expected_size + 1 - observed)
        chunks.append(tail)
        observed += len(tail)
    except PackageError:
        raise
    except zlib.error:
        _reject("zip_crc")
    if observed > expected_size:
        _reject("zip_size")
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        _reject("zip_crc")
    result = b"".join(chunks)
    if len(result) != expected_size:
        _reject("zip_size")
    if zlib.crc32(result) & 0xffffffff != record["crc"]:
        _reject("zip_crc")
    return result


def _strict_json(data: bytes) -> object:
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _reject("manifest_duplicate_key")
            result[key] = value
        return result

    def invalid_constant(_value):
        _reject("manifest_json")

    try:
        return json.loads(data.decode("utf-8", "strict"), object_pairs_hook=object_pairs,
                          parse_constant=invalid_constant)
    except PackageError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        _reject("manifest_json")


def _validate_manifest(value: object, expected_commit: str) -> dict:
    manifest = _exact_keys(value, {"schema", "target", "version", "channel", "commit",
                                   "ci_image_digest", "files", "runtime_inventory"}, "manifest_schema")
    if manifest["schema"] != SCHEMA or manifest["target"] != TARGET or manifest["channel"] != CHANNEL:
        _reject("manifest_identity")
    _bounded_string(manifest["version"], _VERSION, "manifest_version")
    commit = _bounded_string(manifest["commit"], _COMMIT, "manifest_commit")
    if commit != expected_commit:
        _reject("manifest_commit")
    image_digest = manifest["ci_image_digest"]
    if type(image_digest) is not str or not image_digest.startswith("sha256:") \
            or _SHA256.fullmatch(image_digest[7:]) is None:
        _reject("manifest_image")
    files = manifest["files"]
    if type(files) is not list or len(files) != len(PAYLOAD):
        _reject("manifest_files")
    for record, (expected_path, expected_mode) in zip(files, PAYLOAD, strict=True):
        item = _exact_keys(record, {"path", "size", "mode", "sha256"}, "manifest_file")
        if item["path"] != expected_path or item["mode"] != f"{expected_mode:04o}":
            _reject("manifest_file")
        if type(item["size"]) is not int or not 0 < item["size"] <= MAX_MEMBER_BYTES:
            _reject("manifest_file")
        _bounded_string(item["sha256"], _SHA256, "manifest_file")
    validate_runtime_inventory(manifest["runtime_inventory"])
    return manifest


def _verify_archive_data(archive_data: bytes, *, expected_commit: str) -> dict:
    try:
        archive_records = _archive_records(archive_data)
        if sum(record["size"] for record in archive_records) > MAX_TOTAL_BYTES:
            _reject("total_limit")
        decoded = {record["name"]: _decode_member(record) for record in archive_records}
        manifest = _validate_manifest(_strict_json(decoded["manifest.json"]), expected_commit)
        manifest_records = {item["path"]: item for item in manifest["files"]}
        payload = {}
        for relative, _mode in PAYLOAD:
            data = decoded[relative]
            record = manifest_records[relative]
            if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                _reject("payload_digest")
            payload[relative] = data
        elf = parse_elf(payload["bin/orla-launcher"])
        if elf["rpath"] or elf["runpath"]:
            _reject("elf_search_path")
        validate_runtime_inventory(manifest["runtime_inventory"], elf)
        return manifest
    except PackageError:
        raise
    except (OSError, ValueError, KeyError, struct.error):
        _reject("zip_invalid")


def verify(archive_path: Path, *, expected_sha256: str, expected_commit: str) -> dict:
    if not isinstance(archive_path, Path):
        _reject("archive_file")
    _bounded_string(expected_sha256, _SHA256, "expected_digest")
    _bounded_string(expected_commit, _COMMIT, "expected_commit")
    archive_data = _read_archive(archive_path)
    observed_digest = hashlib.sha256(archive_data).hexdigest()
    if observed_digest != expected_sha256:
        _reject("archive_digest")
    return _verify_archive_data(archive_data, expected_commit=expected_commit)


def _load_inventory(path: Path) -> object:
    try:
        status = path.lstat()
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode) or status.st_size > 1024 * 1024:
            _reject("inventory_file")
        data = path.read_bytes()
    except PackageError:
        raise
    except OSError:
        _reject("inventory_file")
    return _strict_json(data)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="package.py", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    build_command = commands.add_parser("build")
    build_command.add_argument("stage", type=Path)
    build_command.add_argument("output", type=Path)
    build_command.add_argument("--version", required=True)
    build_command.add_argument("--commit", required=True)
    build_command.add_argument("--ci-image-digest", required=True)
    build_command.add_argument("--runtime-inventory", required=True, type=Path)
    verify_command = commands.add_parser("verify")
    verify_command.add_argument("archive", type=Path)
    verify_command.add_argument("--sha256", required=True)
    verify_command.add_argument("--commit", required=True)
    commands.add_parser("doctor")
    return result


def main(arguments: list[str] | None = None) -> int:
    options = parser().parse_args(arguments)
    try:
        if options.command == "doctor":
            _reject("unsupported_doctor")
        if options.command == "build":
            digest = build(options.stage, options.output, version=options.version, commit=options.commit,
                           ci_image_digest=options.ci_image_digest,
                           runtime_inventory=_load_inventory(options.runtime_inventory))
            result = {"status": "ok", "sha256": digest}
        else:
            manifest = verify(options.archive, expected_sha256=options.sha256, expected_commit=options.commit)
            result = {"status": "ok", "commit": manifest["commit"], "schema": manifest["schema"]}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except PackageError as error:
        print(json.dumps({"status": "error", "code": error.code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
