#!/usr/bin/env python3
"""Bounded AI client presence detection and isolated Codex handshake.

The helper does not authenticate or perform inference. Client processes are
started only by an explicit operation and only behind the required namespace
construction; Ollama is presence-only because its version command queries a
live server in the reviewed version.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import mmap
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time


SCHEMA_VERSION = 1
CAPABILITIES = (
    "installation", "anonymous_protocol", "authentication", "inference",
    "cancellation", "usage_reporting",
)
VERSION_TIMEOUT_SECONDS = 2.0
VERSION_STREAM_LIMIT = 8 * 1024
PROBE_TIMEOUT_SECONDS = 8.0
PROBE_STDOUT_LIMIT = 64 * 1024
SHUTDOWN_EOF_SECONDS = 2.0
SHUTDOWN_TERM_SECONDS = 1.0
SHUTDOWN_KILL_SECONDS = 1.0
KNOWN_CODEX_VERSION = "0.162.1"
ELF_INTERPRETER_LIMIT = 256
SEMVER = r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?"
SENSITIVE_ENV_NAMES = frozenset({
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENCODE_API_KEY",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS", "AZURE_OPENAI_API_KEY",
    "DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "DISPLAY",
    "XDG_RUNTIME_DIR", "SSH_AUTH_SOCK", "GPG_AGENT_INFO",
})


@dataclass(frozen=True)
class Provider:
    id: str
    display_name: str
    executable: str
    version_argv: tuple[str, ...] | None
    version_pattern: re.Pattern[str] | None
    route: str


PROVIDERS = (
    Provider("codex", "Codex", "codex", ("--version",),
             re.compile(rf"^codex-cli ({SEMVER})$"), "owned_app_server"),
    Provider("claude", "Claude Code", "claude", ("--version",),
             re.compile(rf"^({SEMVER}) \(Claude Code\)$"), "official_terminal_handoff"),
    Provider("opencode", "OpenCode", "opencode", ("--version",),
             re.compile(rf"^opencode v({SEMVER})$"), "selected_local_server"),
    Provider("ollama", "Ollama", "ollama", None, None, "selected_local_server"),
    Provider("lmstudio", "LM Studio", "lms", ("--version",),
             re.compile(rf"^(?:lms |LM Studio CLI )?v?({SEMVER})$", re.IGNORECASE),
             "selected_local_server"),
)


_cancelled = False
_runtime_root: Path | None = None
_runtime_root_identity: tuple[int, int] | None = None


def _handle_cancel(_signum, _frame):
    global _cancelled
    _cancelled = True


def _safe_env() -> dict[str, str]:
    result = {}
    for name in ("HOME", "PATH", "LANG", "CODEX_HOME"):
        value = os.environ.get(name)
        if value is not None and "\x00" not in value:
            result[name] = value
    return result


def _group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _wait_for_group(process: subprocess.Popen[bytes], process_group: int,
                    timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        process.poll()  # Reap the owned leader when it has exited.
        if not _group_exists(process_group):
            return True
        time.sleep(0.01)
    process.poll()
    return not _group_exists(process_group)


def _terminate_group(process: subprocess.Popen[bytes], process_group: int) -> bool:
    # The leader may have exited while descendants retained its process group.
    # Keep the PGID captured at spawn and prove group disappearance separately.
    if _group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            pass
    gone = _wait_for_group(process, process_group, SHUTDOWN_TERM_SECONDS)
    if not gone and _group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        gone = _wait_for_group(process, process_group, SHUTDOWN_KILL_SECONDS)
    try:
        process.wait(timeout=0)
    except subprocess.TimeoutExpired:
        pass
    return gone and process.poll() is not None


def _collect(process: subprocess.Popen[bytes], *, timeout: float,
             stdout_limit: int, stderr_limit: int) -> tuple[str, bytes, bytes]:
    selector = selectors.DefaultSelector()
    streams = {}
    output = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            if stream is not None:
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
                streams[stream.fileno()] = name
        while selector.get_map():
            if _cancelled:
                return "cancelled", bytes(output["stdout"]), bytes(output["stderr"])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout", bytes(output["stdout"]), bytes(output["stderr"])
            for key, _events in selector.select(min(remaining, 0.05)):
                try:
                    chunk = os.read(key.fd, 4096)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                name = streams[key.fd]
                output[name].extend(chunk)
                limit = stdout_limit if name == "stdout" else stderr_limit
                if len(output[name]) > limit:
                    return f"{name}_limit", bytes(output["stdout"][:limit]), bytes(output["stderr"][:limit])
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
        return "exited", bytes(output["stdout"]), bytes(output["stderr"])
    except subprocess.TimeoutExpired:
        return "timeout", bytes(output["stdout"]), bytes(output["stderr"])
    finally:
        selector.close()


def _run_version(executable_found: str, executable_name: str,
                 argv: tuple[str, ...]) -> tuple[str, str | None]:
    if _cancelled:
        return "cancelled", None
    isolation = _isolation_inputs(executable_found, executable_name)
    if isolation is None:
        return "isolation_unavailable", None
    bwrap, executable, dependencies, owned_home, home, codex_home = isolation
    process = None
    process_group = None
    status = "version_failed"
    stdout = b""
    stderr = b""
    cleanup_ok = True
    try:
        arguments = _isolated_args(
            bwrap, executable, dependencies, owned_home, home,
            target="/run/orla/client", command=argv,
        )
        if _cancelled:
            return "cancelled", None
        process = subprocess.Popen(
            arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=_isolated_env(home, codex_home),
            start_new_session=True, bufsize=0,
        )
        process_group = process.pid
        status, stdout, stderr = _collect(
            process, timeout=VERSION_TIMEOUT_SECONDS,
            stdout_limit=VERSION_STREAM_LIMIT, stderr_limit=VERSION_STREAM_LIMIT,
        )
    except (OSError, ValueError):
        status = "isolation_unavailable"
    finally:
        if process is not None:
            cleanup_ok = _terminate_group(process, process_group)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        cleanup_ok = _remove_owned_home(owned_home) and cleanup_ok
    if not cleanup_ok:
        return "process_cleanup_failed", None
    if status != "exited":
        return status, None
    if process is None or process.returncode != 0:
        return "version_failed", None
    try:
        text = stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return "version_unrecognized", None
    if stderr.strip() or "\n" in text or "\r" in text or len(text) > 256:
        return "version_unrecognized", None
    return "ok", text


def _empty_capabilities(installation: str) -> dict[str, str]:
    dependent = "absent" if installation == "absent" else "unknown"
    return {
        "installation": installation,
        "anonymous_protocol": dependent,
        "authentication": "unknown",
        "inference": dependent,
        "cancellation": dependent,
        "usage_reporting": "unknown",
    }


def _provider_result(provider: Provider) -> dict[str, object]:
    if _cancelled:
        return _cancelled_provider(provider)
    executable = shutil.which(provider.executable)
    if executable is None:
        return {
            "id": provider.id, "displayName": provider.display_name, "enabled": False,
            "clientVersion": None, "capabilities": _empty_capabilities("absent"),
            "route": provider.route, "messageCode": "cli_not_found",
        }
    if provider.version_argv is None:
        return {
            "id": provider.id, "displayName": provider.display_name, "enabled": False,
            "clientVersion": None, "capabilities": _empty_capabilities("supported"),
            "route": provider.route, "messageCode": "cli_present_version_not_queried",
        }
    status, raw_version = _run_version(executable, provider.executable, provider.version_argv)
    version = None
    if status == "ok" and raw_version is not None:
        assert provider.version_pattern is not None
        match = provider.version_pattern.fullmatch(raw_version)
        if match is not None:
            version = match.group(1)
    installation = "supported" if version is not None else "unknown"
    message = "client_version_recognized" if version is not None else (
        "version_unrecognized" if status == "ok" else status)
    return {
        "id": provider.id, "displayName": provider.display_name, "enabled": False,
        "clientVersion": version, "capabilities": _empty_capabilities(installation),
        "route": provider.route, "messageCode": message,
    }


def detect() -> dict[str, object]:
    providers = []
    for provider in PROVIDERS:
        if _cancelled:
            providers.append(_cancelled_provider(provider))
        else:
            providers.append(_provider_result(provider))
    return {"schemaVersion": SCHEMA_VERSION, "providers": providers}


def _cancelled_provider(provider: Provider) -> dict[str, object]:
    return {
        "id": provider.id, "displayName": provider.display_name, "enabled": False,
        "clientVersion": None, "capabilities": _empty_capabilities("unknown"),
        "route": provider.route, "messageCode": "cancelled",
    }


def _runtime_unavailable_provider(provider: Provider) -> dict[str, object]:
    return {
        "id": provider.id, "displayName": provider.display_name, "enabled": False,
        "clientVersion": None, "capabilities": _empty_capabilities("unknown"),
        "route": provider.route, "messageCode": "isolation_unavailable",
    }


def _inside(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath((os.path.normpath(path), os.path.normpath(parent))) == os.path.normpath(parent)
    except (ValueError, TypeError):
        return False


def _valid_home(home: object) -> bool:
    if not isinstance(home, str) or not home.startswith("/") or home == "/" or len(home) > 4096:
        return False
    if os.path.normpath(home) != home or "\x00" in home:
        return False
    return all(part not in ("", ".", "..") for part in home.split("/")[1:])


def _validated_runtime_root(value: object,
                            expected_identity: tuple[int, int] | None = None) -> Path | None:
    if not _valid_home(value):
        return None
    assert isinstance(value, str)
    candidate = Path(value)
    try:
        current = candidate
        while current != current.parent:
            if stat.S_ISLNK(current.lstat().st_mode):
                return None
            current = current.parent
        info = candidate.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            return None
        if expected_identity is not None and (info.st_dev, info.st_ino) != expected_identity:
            return None
        if candidate.resolve(strict=True) != candidate:
            return None
    except (OSError, RuntimeError):
        return None
    return candidate


def _runtime_identity(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,20}:[0-9]{1,20}", value) is None:
        return None
    device, inode = (int(part) for part in value.split(":"))
    if device <= 0 or inode <= 0 or device > 2 ** 64 - 1 or inode > 2 ** 64 - 1:
        return None
    return device, inode


def _resolved_regular_executable(path: str) -> str | None:
    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            return None
        resolved = candidate.resolve(strict=True)
        info = resolved.stat()
        if (not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK)
                or info.st_mode & (stat.S_ISUID | stat.S_ISGID)
                or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
            return None
        return str(resolved)
    except (OSError, RuntimeError, ValueError):
        return None


def _file_prefix(path: str, size: int) -> bytes | None:
    try:
        with open(path, "rb", buffering=0) as stream:
            return stream.read(size)
    except OSError:
        return None


def _allowed_home_client(path: str, executable_name: str, home: str,
                         codex_home: str | None) -> bool:
    if not _inside(path, home):
        return True
    relative = Path(os.path.relpath(path, home)).parts
    direct = relative in ((".local", "bin", executable_name), ("bin", executable_name))
    if direct:
        return True
    if executable_name == "opencode" and relative == (".opencode", "bin", "opencode"):
        return True
    if (executable_name == "claude" and len(relative) == 5
            and relative[:4] == (".local", "share", "claude", "versions")
            and re.fullmatch(r"[0-9A-Za-z._+-]{1,128}", relative[4])):
        return True
    if executable_name == "codex":
        root = codex_home or home + "/.codex"
        if _inside(path, root):
            codex_relative = Path(os.path.relpath(path, root)).parts
            return (len(codex_relative) == 6
                    and codex_relative[:3] == ("packages", "standalone", "releases")
                    and re.fullmatch(r"[0-9A-Za-z._+-]{1,160}", codex_relative[3]) is not None
                    and codex_relative[4:] == ("bin", "codex"))
    return False


def _safe_client_executable(path: str, executable_name: str, home: str,
                            codex_home: str | None) -> str | None:
    resolved = _resolved_regular_executable(path)
    if resolved is None:
        return None
    selected = os.path.normpath(path)
    home_selected = _inside(selected, home) or _inside(resolved, home)
    if home_selected:
        if (not _allowed_home_client(selected, executable_name, home, codex_home)
                or not _allowed_home_client(resolved, executable_name, home, codex_home)):
            return None
        if _file_prefix(resolved, 4) != b"\x7fELF":
            return None
    return resolved


def _safe_system_bwrap(path: str, home: str, codex_home: str | None) -> str | None:
    resolved = _resolved_regular_executable(path)
    if resolved not in ("/usr/bin/bwrap", "/bin/bwrap"):
        return None
    try:
        info = Path(resolved).stat()
        if info.st_uid != 0 or info.st_gid != 0 or _file_prefix(resolved, 4) != b"\x7fELF":
            return None
    except OSError:
        return None
    return resolved


def _runtime_dependencies(executable: str) -> list[str] | None:
    """Return a fixed, minimal runtime allowlist; reject unknown executable forms."""
    head = _file_prefix(executable, 256)
    if head is None:
        return None
    runtime_candidates = (
        "/lib64/ld-linux-x86-64.so.2", "/usr/lib64/ld-linux-x86-64.so.2",
        "/lib/ld-linux-aarch64.so.1", "/usr/lib64/ld-linux-aarch64.so.1",
        "/lib64/libc.so.6", "/usr/lib64/libc.so.6", "/lib/aarch64-linux-gnu/libc.so.6",
        "/lib64/libm.so.6", "/usr/lib64/libm.so.6", "/lib/aarch64-linux-gnu/libm.so.6",
        "/lib64/libgcc_s.so.1", "/usr/lib64/libgcc_s.so.1",
        "/lib64/libpthread.so.0", "/usr/lib64/libpthread.so.0",
        "/lib64/libdl.so.2", "/usr/lib64/libdl.so.2",
        "/lib64/librt.so.1", "/usr/lib64/librt.so.1",
    )
    available_runtime = [path for path in runtime_candidates if Path(path).is_file()]
    if head.startswith(b"#!"):
        try:
            line = head.splitlines()[0][2:].decode("ascii", errors="strict").strip()
        except (UnicodeDecodeError, IndexError):
            return None
        # Test fixtures can use the fixed system Python interpreter. Production
        # clients are expected to be ELF; arbitrary env/shebang resolution is refused.
        if line != "/usr/bin/python3":
            return None
        interpreter = Path(line)
        if not interpreter.exists():
            return None
        return [line, *available_runtime]
    if not head.startswith(b"\x7fELF"):
        return None
    requirements = _elf_requirements(executable)
    if requirements is None:
        return None
    interpreter, needed = requirements
    allowed_names = {"libc.so.6", "libm.so.6", "libgcc_s.so.1", "libpthread.so.0",
                     "libdl.so.2", "librt.so.1", "ld-linux-x86-64.so.2",
                     "ld-linux-aarch64.so.1"}
    if any(name not in allowed_names for name in needed):
        return None
    selected = []
    if interpreter is not None:
        if interpreter not in runtime_candidates or not Path(interpreter).is_file():
            return None
        selected.append(interpreter)
    for name in needed:
        matches = [path for path in available_runtime if Path(path).name == name]
        if not matches:
            return None
        selected.extend(matches)
    return list(dict.fromkeys(selected))


def _elf_requirements(executable: str) -> tuple[str | None, tuple[str, ...]] | None:
    """Parse a narrow ELF64 little-endian executable subset without executing it.

    Only x86-64 and AArch64 ET_EXEC/ET_DYN images are accepted. Program segment
    alignment must be zero, one, or a power of two with congruent file/virtual
    offsets. Dynamic and string-table bytes must each have one unambiguous,
    coherent mapping through a file-backed PT_LOAD segment.
    """
    stream = None
    body = None
    try:
        stream = open(executable, "rb", buffering=0)
        size = os.fstat(stream.fileno()).st_size
        if size < 64 or size > 512 * 1024 * 1024:
            return None
        body = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        if (len(body) < 64 or body[:4] != b"\x7fELF" or body[4:7] != b"\x02\x01\x01"):
            return None
        fields = struct.unpack_from("<HHIQQQIHHHHHH", body, 16)
        elf_type, machine, version, entry, phoff, _shoff, _flags, ehsize, phentsize, phnum, *_ = fields
        if (elf_type not in (2, 3) or machine not in (62, 183) or version != 1
                or ehsize != 64 or phentsize != 56 or not (1 <= phnum <= 128)):
            return None
        segments = []
        dynamic = None
        interpreter = None
        executable_entry = False
        for index in range(phnum):
            offset = phoff + index * phentsize
            if offset + 56 > len(body):
                return None
            kind, segment_flags, file_offset, virtual, _physical, file_size, memory_size, alignment = struct.unpack_from(
                "<IIQQQQQQ", body, offset)
            if (file_offset + file_size > len(body) or file_size > memory_size
                    or (alignment not in (0, 1)
                        and (alignment & (alignment - 1) != 0
                             or file_offset % alignment != virtual % alignment))):
                return None
            if kind == 1:
                if memory_size == 0:
                    return None
                segments.append((virtual, virtual + memory_size, file_offset,
                                 file_offset + file_size))
                if (segment_flags & 1
                        and virtual <= entry < virtual + file_size):
                    executable_entry = True
            elif kind == 2:
                if dynamic is not None:
                    return None
                dynamic = (file_offset, virtual, file_size, memory_size)
            elif kind == 3:
                if (interpreter is not None or file_size < 2
                        or file_size > ELF_INTERPRETER_LIMIT):
                    return None
                raw = body[file_offset:file_offset + file_size]
                if raw[-1] != 0 or b"\x00" in raw[:-1]:
                    return None
                interpreter = raw[:-1].decode("ascii", errors="strict")

        if not segments or not executable_entry:
            return None
        expected_interpreter = {
            62: "/lib64/ld-linux-x86-64.so.2",
            183: "/lib/ld-linux-aarch64.so.1",
        }[machine]
        if interpreter is not None and interpreter != expected_interpreter:
            return None

        if dynamic is None:
            return interpreter, ()
        dyn_offset, dyn_virtual, dyn_size, dyn_memory_size = dynamic
        if (dyn_size == 0 or dyn_size % 16 or dyn_size > 64 * 1024
                or dyn_size > dyn_memory_size):
            return None
        dynamic_mappings = [
            file_start + (dyn_virtual - virtual_start)
            for virtual_start, virtual_end, file_start, file_end in segments
            if (virtual_start <= dyn_virtual
                and dyn_virtual + dyn_size <= virtual_end
                and file_start <= file_start + (dyn_virtual - virtual_start)
                and file_start + (dyn_virtual - virtual_start) + dyn_size <= file_end)
        ]
        if len(dynamic_mappings) != 1 or dynamic_mappings[0] != dyn_offset:
            return None
        string_address = None
        string_size = None
        needed_offsets = []
        terminated = False
        for offset in range(dyn_offset, dyn_offset + dyn_size, 16):
            tag, value = struct.unpack_from("<qQ", body, offset)
            if tag == 0:
                terminated = True
                break
            if tag == 1:
                needed_offsets.append(value)
            elif tag == 5:
                if string_address is not None:
                    return None
                string_address = value
            elif tag == 10:
                if string_size is not None:
                    return None
                string_size = value
        if (not terminated or string_address is None or string_size is None
                or not (1 <= string_size <= 1024 * 1024)):
            return None
        string_mappings = [
            file_start + (string_address - virtual_start)
            for virtual_start, virtual_end, file_start, file_end in segments
            if (virtual_start <= string_address
                and string_address + string_size <= virtual_end
                and file_start <= file_start + (string_address - virtual_start)
                and file_start + (string_address - virtual_start) + string_size <= file_end)
        ]
        if len(string_mappings) != 1:
            return None
        string_offset = string_mappings[0]
        table = body[string_offset:string_offset + string_size]
        names = []
        for offset in needed_offsets:
            if offset >= len(table):
                return None
            end = table.find(b"\x00", offset)
            if end < 0:
                return None
            name = table[offset:end].decode("ascii", errors="strict")
            if not (re.fullmatch(r"lib[0-9A-Za-z_.+-]{1,128}\.so(?:\.[0-9]+)*", name)
                    or name in ("ld-linux-x86-64.so.2", "ld-linux-aarch64.so.1")):
                return None
            names.append(name)
        return interpreter, tuple(names)
    except (OSError, UnicodeDecodeError, struct.error, ValueError):
        return None
    finally:
        if body is not None:
            body.close()
        if stream is not None:
            stream.close()


def _isolated_env(home: str, codex_home: str | None) -> dict[str, str]:
    environment = {name: value for name, value in _safe_env().items()
                   if name not in SENSITIVE_ENV_NAMES}
    environment["HOME"] = home
    if codex_home is not None:
        environment["CODEX_HOME"] = codex_home
    return environment


def _isolation_inputs(executable_found: str, executable_name: str):
    home = os.environ.get("HOME")
    codex_home = os.environ.get("CODEX_HOME")
    if (not _valid_home(home)
            or (codex_home is not None and not _inside(codex_home, home))):
        return None
    bwrap_found = shutil.which("bwrap")
    if bwrap_found is None:
        return None
    executable = _safe_client_executable(executable_found, executable_name, home, codex_home)
    bwrap = _safe_system_bwrap(bwrap_found, home, codex_home)
    if executable is None or bwrap is None:
        return None
    dependencies = _runtime_dependencies(executable)
    if dependencies is None or any(
            _inside(path, home) or (codex_home and _inside(path, codex_home))
            for path in dependencies):
        return None
    owned_root = _runtime_root
    if (owned_root is None or _runtime_root_identity is None
            or _validated_runtime_root(str(owned_root), _runtime_root_identity) is None):
        return None
    created = None
    try:
        owned_home = tempfile.mkdtemp(prefix="home-", dir=owned_root)
        os.chmod(owned_home, 0o700)
        created = Path(owned_home)
        if (created.parent != owned_root or created.is_symlink()
                or stat.S_IMODE(created.lstat().st_mode) != 0o700):
            shutil.rmtree(created, ignore_errors=True)
            return None
        Path(owned_home, ".codex").mkdir(mode=0o700)
        if _validated_runtime_root(str(owned_root), _runtime_root_identity) is None:
            shutil.rmtree(created, ignore_errors=True)
            return None
    except OSError:
        if created is not None:
            shutil.rmtree(created, ignore_errors=True)
        return None
    return bwrap, executable, dependencies, owned_home, home, codex_home


def _remove_owned_home(owned_home: str) -> bool:
    if (_runtime_root is None or _runtime_root_identity is None
            or _validated_runtime_root(str(_runtime_root), _runtime_root_identity) is None):
        return False
    candidate = Path(owned_home)
    try:
        info = candidate.lstat()
        if (candidate.parent != _runtime_root or candidate.is_symlink()
                or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            return False
        shutil.rmtree(candidate, ignore_errors=False)
        return (not candidate.exists()
                and _validated_runtime_root(str(_runtime_root), _runtime_root_identity) is not None)
    except OSError:
        return False


def _provider_document(version: str | None, installation: str, protocol: str,
                       message: str) -> dict[str, object]:
    capabilities = _empty_capabilities(installation)
    capabilities["anonymous_protocol"] = protocol
    if protocol == "supported":
        # The handshake says nothing about real-turn cancellation.
        capabilities["cancellation"] = "unknown"
        capabilities["inference"] = "unknown"
    return {"schemaVersion": SCHEMA_VERSION, "provider": {
        "id": "codex", "displayName": "Codex", "enabled": False,
        "clientVersion": version, "capabilities": capabilities,
        "route": "owned_app_server", "messageCode": message,
    }}


def _isolated_args(bwrap: str, executable: str, dependencies: list[str],
                   owned_home: str, home: str, *, target: str,
                   command: tuple[str, ...]) -> list[str]:
    arguments = [
        bwrap, "--unshare-all", "--die-with-parent", "--new-session",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/run", "--dir", "/run/orla", "--dir", "/home",
        "--bind", owned_home, home,
        "--ro-bind", executable, target,
    ]
    directories = set()
    for dependency in dependencies:
        parent = Path(dependency).parent
        while str(parent) != "/":
            directories.add(str(parent))
            parent = parent.parent
    for directory in sorted(directories, key=lambda item: (item.count("/"), item)):
        arguments.extend(("--dir", directory))
    mounted = set()
    for dependency in dependencies:
        destination = os.path.normpath(dependency)
        source = str(Path(dependency).resolve())
        if destination in mounted:
            continue
        mounted.add(destination)
        arguments.extend(("--ro-bind", source, destination))
    arguments.extend(("--chdir", home, "--", target, *command))
    return arguments


def _valid_initialize_response(message: object, request_id: int,
                               expected_codex_home: str) -> bool:
    if not isinstance(message, dict) or message.get("id") != request_id:
        return False
    result = message.get("result")
    if not isinstance(result, dict):
        return False
    return (
        result.get("codexHome") == expected_codex_home
        and isinstance(result.get("platformFamily"), str)
        and isinstance(result.get("platformOs"), str)
        and isinstance(result.get("userAgent"), str)
    )


def _handshake(process: subprocess.Popen[bytes], *, home: str,
               codex_home: str) -> str:
    request_id = 17031
    request = {"id": request_id, "method": "initialize", "params": {
        "clientInfo": {"name": "orla_ai_provider_helper", "title": "Orla AI provider helper",
                       "version": "0.1.0"},
        "capabilities": {"experimentalApi": False, "requestAttestation": False,
                         "explicitGatewayOauth": True},
    }}
    assert process.stdin is not None
    try:
        process.stdin.write(json.dumps(request, separators=(",", ":")).encode("ascii") + b"\n")
        process.stdin.flush()
    except (BrokenPipeError, OSError):
        return "protocol_process_failed"

    selector = selectors.DefaultSelector()
    raw = bytearray()
    deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
    assert process.stdout is not None
    os.set_blocking(process.stdout.fileno(), False)
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while True:
            if _cancelled:
                return "cancelled"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "protocol_timeout"
            events = selector.select(min(remaining, 0.05))
            if not events and process.poll() is not None:
                return "protocol_process_failed"
            for key, _events in events:
                try:
                    chunk = os.read(key.fd, 4096)
                except BlockingIOError:
                    continue
                if not chunk:
                    return "protocol_process_failed"
                raw.extend(chunk)
                if len(raw) > PROBE_STDOUT_LIMIT:
                    return "protocol_output_limit"
                while b"\n" in raw:
                    line, _, remainder = raw.partition(b"\n")
                    raw = bytearray(remainder)
                    if not line or len(line) > PROBE_STDOUT_LIMIT:
                        return "protocol_invalid"
                    try:
                        message = json.loads(line.decode("utf-8", errors="strict"))
                    except (UnicodeDecodeError, ValueError):
                        return "protocol_invalid"
                    if not _valid_initialize_response(message, request_id, codex_home):
                        return "protocol_invalid"
                    notification = b'{"method":"initialized"}\n'
                    try:
                        process.stdin.write(notification)
                        process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        return "protocol_process_failed"
                    return "protocol_supported"
    finally:
        selector.close()


def _emit(document: dict[str, object]) -> int:
    encoded = json.dumps(document, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n"
    os.write(sys.stdout.fileno(), encoded)
    return 0


def main(argv: list[str] | None = None) -> int:
    global _runtime_root, _runtime_root_identity
    arguments = sys.argv[1:] if argv is None else argv
    if (len(arguments) == 1
            and arguments[0] in ("detect", "probe-codex-anonymous")):
        _runtime_root = None
        _runtime_root_identity = None
    elif (len(arguments) == 5
          and arguments[0] in ("detect", "probe-codex-anonymous")
          and arguments[1] == "--runtime-root"
          and arguments[3] == "--runtime-root-id"):
        identity = _runtime_identity(arguments[4])
        _runtime_root_identity = identity
        _runtime_root = _validated_runtime_root(arguments[2], identity) if identity else None
    else:
        _emit({"schemaVersion": SCHEMA_VERSION, "error": {"code": "invalid_operation"}})
        return 2
    signal.signal(signal.SIGTERM, _handle_cancel)
    signal.signal(signal.SIGINT, _handle_cancel)
    if _runtime_root is None:
        if arguments[0] == "detect":
            return _emit({"schemaVersion": SCHEMA_VERSION,
                          "providers": [_runtime_unavailable_provider(provider)
                                        for provider in PROVIDERS]})
        return _emit(_provider_document(None, "unknown", "unknown", "isolation_unavailable"))
    if arguments[0] == "detect":
        return _emit(detect())
    return _emit(probe_codex_anonymous())


def probe_codex_anonymous() -> dict[str, object]:
    provider = _provider_result(PROVIDERS[0])
    version = provider["clientVersion"]
    installation = provider["capabilities"]["installation"]
    if installation == "absent":
        return _provider_document(None, "absent", "absent", "cli_not_found")
    if provider["messageCode"] == "cancelled":
        return _provider_document(None, "unknown", "unknown", "cancelled")
    if version is None:
        return _provider_document(None, "unknown", "unknown", provider["messageCode"])
    if version != KNOWN_CODEX_VERSION:
        return _provider_document(version, "supported", "unknown", "protocol_version_unknown")

    executable_found = shutil.which("codex")
    if executable_found is None:
        return _provider_document(version, "supported", "unknown", "isolation_unavailable")
    isolation = _isolation_inputs(executable_found, "codex")
    if isolation is None:
        return _provider_document(version, "supported", "unknown", "isolation_unavailable")
    bwrap, executable, dependencies, owned_home, home, codex_home = isolation
    expected_codex_home = codex_home or home + "/.codex"
    process = None
    process_group = None
    message = "protocol_process_failed"
    cleanup_ok = True
    try:
        arguments = _isolated_args(
            bwrap, executable, dependencies, owned_home, home,
            target="/run/orla/codex",
            command=("app-server", "--listen", "stdio://",
                     "-c", "analytics.enabled=false", "-c", 'otel.exporter="none"',
                     "-c", 'otel.trace_exporter="none"'),
        )
        if _cancelled:
            return _provider_document(version, "supported", "unknown", "cancelled")
        process = subprocess.Popen(
            arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=_isolated_env(home, codex_home),
            start_new_session=True, bufsize=0,
        )
        process_group = process.pid
        message = _handshake(process, home=home, codex_home=expected_codex_home)
    except (OSError, ValueError):
        message = "isolation_unavailable"
    finally:
        if process is not None:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if message == "protocol_supported" and not _cancelled:
                try:
                    process.wait(timeout=SHUTDOWN_EOF_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
            cleanup_ok = _terminate_group(process, process_group)
            if process.stdout is not None:
                process.stdout.close()
            if not cleanup_ok:
                message = "process_cleanup_failed"
        cleanup_ok = _remove_owned_home(owned_home) and cleanup_ok

    if not cleanup_ok:
        message = "process_cleanup_failed"
    if message == "protocol_supported" and process is not None and process.returncode == 0:
        return _provider_document(version, "supported", "supported", "anonymous_protocol_supported")
    if message == "protocol_supported":
        message = "protocol_shutdown_failed"
    return _provider_document(version, "supported", "unknown", message)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # The controller receives only stable codes; paths, environment values,
        # subprocess output, and tracebacks never cross this boundary.
        raise SystemExit(_emit({
            "schemaVersion": SCHEMA_VERSION,
            "error": {"code": "helper_failure"},
        }) or 1)
