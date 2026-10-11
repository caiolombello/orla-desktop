#!/usr/bin/env python3
"""Experimental read-only Steam metadata discovery; explicit Linux roots only.

Run in an owned CLI process, not inside a Qt GUI: bounded discovery uses fork.
No account files, networking, Steam process or game execution is involved.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import json
import math
import multiprocessing
import os
import re
import stat
import sys
import time
import unicodedata


SCHEMA_VERSION = "0.1-experimental"
APPID = re.compile(r"[1-9][0-9]{0,9}\Z", re.ASCII)
MANIFEST = re.compile(r"appmanifest_([1-9][0-9]{0,9})\.acf\Z", re.ASCII)
TITLE_PATH_PREFIX = re.compile(
    r"^(?:[/\\]|[A-Za-z]:[/\\]|~[^/\\\s]*[/\\]|"
    r"\$(?:HOME|\{HOME\})[/\\]|%(?:USERPROFILE|HOMEPATH)%[/\\]|file:[/\\])",
    re.IGNORECASE | re.ASCII,
)
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True)
class SteamRoot:
    path: str
    kind: str = "native"


@dataclass(frozen=True)
class Limits:
    roots: int = 8
    libraries: int = 32
    manifests: int = 512
    directory_entries: int = 4096
    file_bytes: int = 128 * 1024
    total_bytes: int = 4 * 1024 * 1024
    tokens: int = 16384
    nesting: int = 16
    result_bytes: int = 512 * 1024
    deadline_seconds: float = 5.0


class _Issue(Exception):
    pass


def _empty(reason=None):
    return {"schema_version": SCHEMA_VERSION, "status": "unknown", "connection": "unknown",
            "ownership": "unknown", "roots": [], "libraries": [], "apps": [],
            "errors": [{"code": reason}] if reason else []}


def _appid(value):
    return (isinstance(value, str) and APPID.fullmatch(value) is not None
            and int(value) <= 4294967295)


def steam_uri(action: str, appid: str | None = None) -> str:
    """Generate only allowlisted URI strings; never open a client or a game."""
    if action == "downloads" and appid is None:
        return "steam://open/downloads"
    if action == "game" and _appid(appid):
        return "steam://rungameid/" + appid
    raise ValueError("invalid_input")


def _path_parts(path):
    if (not isinstance(path, str) or not path.startswith("/") or len(path) > 4096
            or "\\" in path or any(unicodedata.category(c).startswith("C") for c in path)):
        raise _Issue("unsafe_path")
    parts = path.split("/")[1:]
    if not parts or any(not part or part in (".", "..") or len(part.encode("utf-8")) > 255
                        for part in parts):
        raise _Issue("unsafe_path")
    return parts


def _open_directory(path):
    parts = _path_parts(path)
    descriptor = os.open("/", DIRECTORY_FLAGS)
    try:
        for part in parts:
            child = os.open(part, DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _io_code(exc):
    if isinstance(exc, _Issue):
        return str(exc)
    if exc.errno == errno.ENOENT:
        return "missing"
    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return "unsafe_target"
    if exc.errno in (errno.EACCES, errno.EPERM):
        return "permission_denied"
    return "read_error"


def _parse_vdf(body, limits):
    """Strict bounded KV1 subset; never evaluates directives/conditions/includes."""
    try:
        source = body.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        raise _Issue("invalid_encoding") from None
    tokens = []
    index = 0
    while index < len(source):
        c = source[index]
        if c in " \r\n\t":
            index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = len(source) if end < 0 else end + 1
            continue
        if c in "{}":
            tokens.append((c, False))
            index += 1
        elif c == '"':
            index += 1
            value = []
            while index < len(source) and source[index] != '"':
                c = source[index]
                if c == "\\":
                    index += 1
                    if index >= len(source) or source[index] not in ('"', "\\", "n", "t", "r"):
                        raise _Issue("unsupported_escape")
                    c = {"n": "\n", "t": "\t", "r": "\r"}.get(source[index], source[index])
                if c == "\x00":
                    raise _Issue("malformed_vdf")
                value.append(c)
                index += 1
            if index >= len(source):
                raise _Issue("truncated_vdf")
            index += 1
            tokens.append(("".join(value), True))
        else:
            start = index
            while index < len(source) and source[index] not in ' \r\n\t{}"':
                index += 1
            value = source[start:index]
            if not value or value.startswith(("#", "[")) or "\x00" in value or "\\" in value:
                raise _Issue("unsupported_vdf")
            tokens.append((value, True))
        if len(tokens) > limits.tokens:
            raise _Issue("token_limit")

    position = 0

    def block(depth):
        nonlocal position
        if depth > limits.nesting:
            raise _Issue("nesting_limit")
        result = {}
        while position < len(tokens) and tokens[position] != ("}", False):
            key, scalar = tokens[position]
            position += 1
            if not scalar or position >= len(tokens):
                raise _Issue("truncated_vdf")
            key = key.casefold()
            if key in result:
                raise _Issue("duplicate_key")
            value, scalar = tokens[position]
            position += 1
            if value == "{" and not scalar:
                value = block(depth + 1)
                if position >= len(tokens) or tokens[position] != ("}", False):
                    raise _Issue("truncated_vdf")
                position += 1
            elif not scalar:
                raise _Issue("malformed_vdf")
            result[key] = value
        return result

    result = block(0)
    if position != len(tokens) or not result:
        raise _Issue("malformed_vdf")
    return result


class _Scanner:
    def __init__(self, limits):
        self.limits = limits
        self.bytes = 0
        self.manifests = 0
        self.result = _empty()
        self.libraries = {}

    def error(self, code, library=None, appid=None, root=None):
        item = {"code": code}
        for key, value in (("library", library), ("appid", appid), ("root", root)):
            if value is not None:
                item[key] = value
        self.result["errors"].append(item)

    def read(self, descriptor, name):
        file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                       dir_fd=descriptor)
        try:
            info = os.fstat(file)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise _Issue("unsafe_target")
            if info.st_size > self.limits.file_bytes:
                raise _Issue("file_byte_limit")
            available = min(self.limits.file_bytes, self.limits.total_bytes - self.bytes)
            if available <= 0:
                raise _Issue("total_byte_limit")
            chunks = []
            size = 0
            while size <= available:
                chunk = os.read(file, min(65536, available + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            self.bytes += size
            if size > available:
                raise _Issue("total_byte_limit" if available < self.limits.file_bytes else "file_byte_limit")
            if os.fstat(file).st_size != info.st_size or size != info.st_size:
                raise _Issue("changed_during_read")
            return _parse_vdf(b"".join(chunks), self.limits)
        finally:
            os.close(file)

    def scan_library(self, path, kind, root_id):
        if path in self.libraries:
            return self.libraries[path]
        if len(self.libraries) >= self.limits.libraries:
            self.error("library_limit", root=root_id)
            return {"status": "unknown"}
        library_id = f"library-{len(self.result['libraries'])}"
        record = {"id": library_id, "root": root_id, "kind": kind, "status": "unknown"}
        self.result["libraries"].append(record)
        self.libraries[path] = record
        try:
            root = _open_directory(path)
            try:
                directory = os.open("steamapps", DIRECTORY_FLAGS, dir_fd=root)
            finally:
                os.close(root)
        except (OSError, _Issue) as exc:
            code = _io_code(exc)
            record["status"] = "missing" if code == "missing" else "unknown"
            self.error(code, library=library_id)
            return record
        try:
            matches = []
            invalid_names = False
            error_count = len(self.result["errors"])
            with os.scandir(directory) as entries:
                for count, entry in enumerate(entries, start=1):
                    if count > self.limits.directory_entries:
                        raise _Issue("directory_entry_limit")
                    match = MANIFEST.fullmatch(entry.name)
                    if match and _appid(match[1]):
                        matches.append((match[1], entry.name))
                    elif entry.name.startswith("appmanifest_") and entry.name.endswith(".acf"):
                        invalid_names = True
            record["status"] = "available"
            if invalid_names:
                self.error("unsupported_manifest_name", library=library_id)
            for appid, name in sorted(matches, key=lambda item: int(item[0])):
                if self.manifests >= self.limits.manifests:
                    raise _Issue("manifest_limit")
                self.manifests += 1
                try:
                    document = self.read(directory, name)
                    state = document.get("appstate")
                    if len(document) != 1 or not isinstance(state, dict) or state.get("appid") != appid:
                        raise _Issue("unsupported_manifest")
                    title = state.get("name")
                    if not isinstance(title, str) or not title.strip():
                        raise _Issue("unsupported_manifest")
                    title = "".join(c for c in title if not unicodedata.category(c).startswith("C"))
                    redacted = TITLE_PATH_PREFIX.match(title.lstrip()) is not None
                    title = f"Jogo {appid}" if redacted else title[:160]
                    if not title.strip():
                        raise _Issue("unsupported_manifest")
                    app = {"appid": appid, "name": title, "library": library_id,
                           "status": "unknown", "ownership": "unknown", "source": "local_manifest"}
                    if redacted:
                        app["name_redacted"] = True
                        self.error("pathlike_name_redacted", library_id, appid)
                    install = state.get("installdir")
                    if (not isinstance(install, str) or not install or install in (".", "..")
                            or "/" in install or "\\" in install or len(install.encode("utf-8")) > 255
                            or any(unicodedata.category(c).startswith("C") for c in install)):
                        raise _Issue("unsafe_installdir")
                    flags = state.get("stateflags")
                    if flags == "4":
                        try:
                            common = os.open("common", DIRECTORY_FLAGS, dir_fd=directory)
                            try:
                                installed = os.open(install, DIRECTORY_FLAGS, dir_fd=common)
                                os.close(installed)
                            finally:
                                os.close(common)
                            app["status"] = "installed_candidate"
                        except OSError as exc:
                            app["status"] = "partial" if exc.errno == errno.ENOENT else "unknown"
                            self.error(_io_code(exc), library_id, appid)
                    elif isinstance(flags, str) and re.fullmatch(r"[0-9]{1,10}", flags, re.ASCII):
                        self.error("unqualified_state_flags", library_id, appid)
                    else:
                        self.error("unknown_state_flags", library_id, appid)
                    self.result["apps"].append(app)
                except (OSError, _Issue) as exc:
                    self.error(_io_code(exc), library_id, appid)
            if len(self.result["errors"]) > error_count:
                record["status"] = "partial"
        except (OSError, _Issue) as exc:
            self.error(_io_code(exc), library_id)
            if record["status"] == "available":
                record["status"] = "partial"
        finally:
            os.close(directory)
        return record

    def library_paths(self, descriptor):
        document = self.read(descriptor, "libraryfolders.vdf")
        folders = document.get("libraryfolders")
        if len(document) != 1 or not isinstance(folders, dict):
            raise _Issue("unsupported_library_index")
        paths = []
        for key, value in folders.items():
            if key in ("timenextstatsreport", "contentstatsid") and isinstance(value, str):
                continue
            if re.fullmatch(r"[0-9]{1,5}", key, re.ASCII) is None:
                raise _Issue("unsupported_library_index")
            path = value.get("path") if isinstance(value, dict) else value
            _path_parts(path)
            paths.append((int(key), path))
        return [path for _, path in sorted(paths)]

    def scan(self, roots):
        for index, root in enumerate(roots):
            root_id = f"root-{index}"
            record = {"id": root_id, "kind": root.kind, "status": "unknown"}
            self.result["roots"].append(record)
            try:
                descriptor = _open_directory(root.path)
            except (OSError, _Issue) as exc:
                code = _io_code(exc)
                record["status"] = "absent" if code == "missing" else "unknown"
                if code != "missing":
                    self.error(code, root=root_id)
                continue
            try:
                try:
                    directory = os.open("steamapps", DIRECTORY_FLAGS, dir_fd=descriptor)
                    try:
                        paths = self.library_paths(directory)
                    finally:
                        os.close(directory)
                except (OSError, _Issue) as exc:
                    self.error(_io_code(exc), root=root_id)
                    paths = []
            finally:
                os.close(descriptor)
            record["status"] = self.scan_library(root.path, root.kind, root_id)["status"]
            for path in paths:
                if path not in self.libraries and len(self.libraries) >= self.limits.libraries:
                    self.error("library_limit", root=root_id)
                    break
                self.scan_library(path, root.kind, root_id)
        if self.result["errors"]:
            self.result["status"] = "partial" if any(r["status"] in ("available", "partial") for r in self.result["libraries"]) else "unknown"
        else:
            self.result["status"] = "absent" if all(r["status"] == "absent" for r in self.result["roots"]) else "available"
        return self.result


def _worker(connection, roots, limits):
    try:
        result = _Scanner(limits).scan(roots)
        body = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
        if len(body) > limits.result_bytes:
            body = json.dumps(_empty("result_byte_limit")).encode("ascii")
        connection.send_bytes(body)
    except BaseException:
        connection.send_bytes(json.dumps(_empty("worker_error")).encode("ascii"))
    finally:
        connection.close()


def discover(roots: list[SteamRoot], limits: Limits | None = None) -> dict:
    """Return bounded metadata without scan paths; names remain untrusted data."""
    limits = Limits() if limits is None else limits
    defaults = Limits()
    if not isinstance(limits, Limits):
        return _empty("invalid_input")
    for field, maximum in vars(defaults).items():
        value = getattr(limits, field)
        if field == "deadline_seconds":
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= maximum:
                return _empty("invalid_input")
        elif type(value) is not int or not 1 <= value <= maximum:
            return _empty("invalid_input")
    if limits.result_bytes < 1024:
        return _empty("invalid_input")
    if (not isinstance(roots, (list, tuple)) or not roots or len(roots) > limits.roots
            or any(not isinstance(root, SteamRoot) or root.kind not in ("native", "flatpak") for root in roots)):
        return _empty("invalid_input")
    try:
        for root in roots:
            _path_parts(root.path)
    except _Issue:
        return _empty("invalid_input")
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(send, roots, limits), daemon=True)
    started = False
    deadline = time.monotonic() + limits.deadline_seconds
    try:
        process.start()
        started = True
        send.close()
        if not receive.poll(max(0, deadline - time.monotonic())):
            return _empty("deadline")
        body = receive.recv_bytes(limits.result_bytes)
        return json.loads(body)
    except (OSError, EOFError, ValueError):
        return _empty("worker_error")
    finally:
        receive.close()
        if started:
            if process.is_alive():
                process.kill()
            process.join(0.5)
        else:
            send.close()


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_input")


def parser():
    result = _Parser(prog="steam", description="Read explicit Steam metadata roots without opening Steam")
    commands = result.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="read bounded metadata from explicit roots")
    scan.add_argument("--root", action="append", required=True, metavar="KIND=/ABS/PATH",
                      help="repeat native=/absolute/path or flatpak=/absolute/path; declared libraries are included")
    uri = commands.add_parser("uri", help="generate a URI string without executing it")
    uri.add_argument("--action", choices=("game", "downloads"), required=True)
    uri.add_argument("--appid")
    return result


def main(argv: list[str] | None = None, *, stdout=None) -> int:
    output = stdout or sys.stdout
    try:
        args = parser().parse_args(argv)
        if args.command == "scan":
            roots = []
            for value in args.root:
                kind, separator, path = value.partition("=")
                if not separator:
                    raise ValueError("invalid_input")
                roots.append(SteamRoot(path, kind))
            result = discover(roots)
        else:
            result = {"schema_version": SCHEMA_VERSION, "uri": steam_uri(args.action, args.appid)}
    except ValueError:
        result = _empty("invalid_input")
    json.dump(result, output, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    output.write("\n")
    return 2 if result.get("status") in ("unknown", "partial") else 0


if __name__ == "__main__":
    raise SystemExit(main())
