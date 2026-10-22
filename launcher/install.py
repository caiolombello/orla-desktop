"""Experimental owned launcher install/status/launch/uninstall manager.

Phase A installs inert verified files, with runtime explicitly unverified.
Service, Meta, update, rollback and interrupted-transaction recovery are separate
verticals; this first candidate requires an uncontended clean owned prefix.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys


SCHEMA = "orla-launcher-install-0.1"
PACKAGE_SHA256 = "cc5637c62ed98b4928a1de618e248fad0471b7649717b8c936be1ef630cc7011"
MAX_RECEIPT_BYTES = 64 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
PAYLOAD = (
    ("bin/orla-launcher", 0o755), ("libexec/ai.py", 0o644),
    ("libexec/steam.py", 0o644), ("libexec/ai_text_ollama.py", 0o644),
    ("libexec/ai_text_transport.py", 0o644), ("libexec/ai_text.py", 0o644),
    ("LICENSE", 0o644),
)
SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
COMMIT = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)


class InstallError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class InstallPaths:
    home: Path
    data_home: Path
    state_home: Path


def _absolute(path):
    if not isinstance(path, Path) or not path.is_absolute():
        raise InstallError("install_paths")
    text = str(path)
    if text == "/" or len(text) > 4096 or text.startswith("//") or any(part in (".", "..") for part in path.parts) \
            or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise InstallError("install_paths")
    return path


def _paths(value):
    if not isinstance(value, InstallPaths):
        raise InstallError("install_paths")
    for path in (value.home, value.data_home, value.state_home):
        _absolute(path)
    # Bound every derived pathname before either state creation or mutation.
    for path in list(_directories(value, "0" * 64).values()) + [item[0] for item in _files(value, "0" * 64).values()] + [_state(value) / "transactions" / ("0" * 64 + "-uninstalled.json")]:
        if len(os.fsencode(path)) > 4096 or len(path.parts) > 64 or any(len(os.fsencode(part)) > 255 for part in path.parts):
            raise InstallError("install_paths")
    return value


def _base(paths):
    return paths.data_home / "orla-desktop/launcher"


def _state(paths):
    return paths.state_home / "orla/launcher-install"


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _directory_identity(value):
    return value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid


@contextmanager
def _directory(path, *, create=False, mode=0o755):
    _absolute(path)
    descriptors, relations = [], []
    primary = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append(descriptor)
        for index, component in enumerate(path.parts[1:]):
            parent = descriptor
            try:
                before = os.stat(component, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, mode if index == len(path.parts) - 2 else 0o755, dir_fd=parent)
                before = os.stat(component, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or before.st_uid not in (0, os.getuid()) \
                    or (before.st_mode & 0o022 and not (before.st_uid == 0 and before.st_mode & stat.S_ISVTX)):
                raise InstallError("unsafe_parent")
            descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            descriptors.append(descriptor)
            pin = _directory_identity(before)
            if _directory_identity(os.fstat(descriptor)) != pin:
                raise InstallError("parent_changed")
            relations.append((parent, component, descriptor, pin))
        yield descriptor
        for parent, component, child, pin in relations:
            if _directory_identity(os.stat(component, dir_fd=parent, follow_symlinks=False)) != pin \
                    or _directory_identity(os.fstat(child)) != pin:
                raise InstallError("parent_changed")
    except BaseException as error:
        primary = error
        raise
    finally:
        failure = None
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError as error:
                failure = error
        if failure is not None and primary is None:
            raise InstallError("cleanup_unknown") from failure


def _regular(value, mode=None, limit=MAX_FILE_BYTES):
    if not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid() or value.st_nlink != 1 \
            or value.st_size > limit or value.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX) \
            or (mode is not None and stat.S_IMODE(value.st_mode) != mode):
        raise InstallError("unsafe_file")


def _read(path, *, mode=None, limit=MAX_FILE_BYTES):
    descriptor = None
    with _directory(path.parent) as parent:
        try:
            before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            _regular(before, mode, limit)
            pin = _identity(before)
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
            if _identity(os.fstat(descriptor)) != pin:
                raise InstallError("file_changed")
            data = bytearray()
            while True:
                chunk = os.read(descriptor, min(128 * 1024, before.st_size - len(data) + 1))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > before.st_size:
                    raise InstallError("file_changed")
            if len(data) != before.st_size or _identity(os.fstat(descriptor)) != pin \
                    or _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != pin:
                raise InstallError("file_changed")
            return bytes(data), pin
        finally:
            if descriptor is not None:
                primary = sys.exc_info()[1]
                try:
                    os.close(descriptor)
                except OSError as error:
                    if primary is None:
                        raise InstallError("cleanup_unknown") from error


def _exists(path):
    try:
        with _directory(path.parent) as parent:
            os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            return True
    except FileNotFoundError:
        return False


def _write_new(path, data, mode, *, owned=None):
    descriptor = None
    with _directory(path.parent, create=True) as parent:
        try:
            descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 mode, dir_fd=parent)
            # O_EXCL creates ownership before chmod or any later I/O can fail.
            opened = os.fstat(descriptor)
            if owned is not None:
                owned[str(path)] = [opened.st_dev, opened.st_ino]
            os.fchmod(descriptor, mode)
            if os.fstat(descriptor).st_uid != os.getuid():
                raise InstallError("file_owner")
            view = memoryview(data)
            while view:
                count = os.write(descriptor, view)
                if count <= 0:
                    raise InstallError("write_failed")
                view = view[count:]
            os.fsync(descriptor)
        except FileExistsError:
            raise InstallError("install_conflict") from None
        finally:
            if descriptor is not None:
                primary = sys.exc_info()[1]
                try:
                    os.close(descriptor)
                except OSError as error:
                    if primary is None:
                        raise InstallError("cleanup_unknown") from error
        os.fsync(parent)
    observed, _pin = _read(path, mode=mode, limit=max(len(data), 1))
    if observed != data:
        raise InstallError("write_readback")


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


def _strict_json(data):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise InstallError("receipt_schema")
            value[key] = item
        return value
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=lambda _value: (_ for _ in ()).throw(InstallError("receipt_schema")))
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        if isinstance(error, InstallError):
            raise
        raise InstallError("receipt_schema") from None


def _package():
    path = Path(__file__).with_name("package.py")
    data, _pin = _read(path, mode=0o644, limit=2 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != PACKAGE_SHA256:
        raise InstallError("package_tool_drift")
    specification = importlib.util.spec_from_file_location("_orla_installer_package", path)
    module = importlib.util.module_from_spec(specification)
    # Execute only the verified frozen module bytes, never reopen a swapped path.
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def _files(paths, digest):
    version = _base(paths) / "versions" / digest
    value = {"payload/" + relative: (version / relative, mode) for relative, mode in PAYLOAD}
    value.update({"tools/install.py": (_base(paths) / "tools/install.py", 0o644),
                  "tools/package.py": (_base(paths) / "tools/package.py", 0o644),
                  "controller": (paths.home / ".local/bin/orla-launcherctl", 0o755),
                  "launcher": (paths.home / ".local/bin/orla-launcher", 0o755),
                  "menu": (paths.data_home / "applications/org.orla.Launcher.desktop", 0o644)})
    return value


def _directories(paths, digest):
    base = _base(paths)
    version = base / "versions" / digest
    return {"base": base, "versions": base / "versions", "version": version,
            "payload-bin": version / "bin", "payload-libexec": version / "libexec", "tools": base / "tools"}


def _receipt(paths):
    data, _pin = _read(_state(paths) / "current.json", mode=0o600, limit=MAX_RECEIPT_BYTES)
    value = _strict_json(data)
    if type(value) is not dict or set(value) != {"schema", "archiveSha256", "commit", "uid", "runtime", "files", "directories"} \
            or value["schema"] != SCHEMA or type(value["archiveSha256"]) is not str or SHA256.fullmatch(value["archiveSha256"]) is None \
            or type(value["commit"]) is not str or COMMIT.fullmatch(value["commit"]) is None \
            or type(value["uid"]) is not int or value["uid"] != os.getuid() or value["runtime"] != "unverified":
        raise InstallError("receipt_schema")
    files = _files(paths, value["archiveSha256"])
    if type(value["files"]) is not list or len(value["files"]) != len(files):
        raise InstallError("receipt_schema")
    seen = set()
    for record in value["files"]:
        if type(record) is not dict or set(record) != {"key", "mode", "size", "sha256"}:
            raise InstallError("receipt_schema")
        key = record["key"]
        if type(key) is not str or key not in files or key in seen \
                or record["mode"] != f"{files[key][1]:04o}" \
                or type(record["size"]) is not int or not 0 < record["size"] <= MAX_FILE_BYTES \
                or type(record["sha256"]) is not str or SHA256.fullmatch(record["sha256"]) is None:
            raise InstallError("receipt_schema")
        seen.add(key)
    directories = _directories(paths, value["archiveSha256"])
    if type(value["directories"]) is not list or len(value["directories"]) != len(directories):
        raise InstallError("receipt_schema")
    seen = set()
    for record in value["directories"]:
        if type(record) is not dict or set(record) != {"key", "pin"} or type(record["key"]) is not str \
                or record["key"] not in directories or record["key"] in seen or type(record["pin"]) is not list \
                or len(record["pin"]) != 5 or any(type(number) is not int for number in record["pin"]):
            raise InstallError("receipt_schema")
        seen.add(record["key"])
    # Historical admission is immutable; current may never rewrite it to drift.
    old, _pin = _read(_state(paths) / "receipts" / (value["archiveSha256"] + ".json"), mode=0o600, limit=MAX_RECEIPT_BYTES)
    if old != data:
        raise InstallError("receipt_history_changed")
    return value


def _guard(paths, receipt):
    fixed = _files(paths, receipt["archiveSha256"])
    for record in receipt["files"]:
        path, mode = fixed[record["key"]]
        data, _pin = _read(path, mode=mode)
        if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise InstallError("managed_drift")
    directories = _directories(paths, receipt["archiveSha256"])
    for record in receipt["directories"]:
        with _directory(directories[record["key"]]) as descriptor:
            if list(_directory_identity(os.fstat(descriptor))) != record["pin"]:
                raise InstallError("managed_parent_drift")
    expected = {"base": {"versions", "tools"}, "versions": {receipt["archiveSha256"]},
                "version": {"bin", "libexec", "LICENSE"}, "payload-bin": {"orla-launcher"},
                "payload-libexec": {"ai.py", "steam.py", "ai_text_ollama.py", "ai_text_transport.py", "ai_text.py"},
                "tools": {"install.py", "package.py"}}
    for key, names in expected.items():
        with _directory(directories[key]) as descriptor:
            with os.scandir(descriptor) as entries:
                observed = set()
                for count, entry in enumerate(entries, 1):
                    if count > len(names):
                        raise InstallError("managed_extra_file")
                    observed.add(entry.name)
            if observed != names:
                raise InstallError("managed_extra_file")


@contextmanager
def _locked(paths):
    descriptor = None
    with _directory(_state(paths), create=True, mode=0o700) as directory:
        if os.fstat(directory).st_uid != os.getuid() or stat.S_IMODE(os.fstat(directory).st_mode) != 0o700:
            raise InstallError("unsafe_state")
        try:
            try:
                descriptor = os.open("lock", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     0o600, dir_fd=directory)
                os.fchmod(descriptor, 0o600)
            except FileExistsError:
                descriptor = os.open("lock", os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            _regular(os.fstat(descriptor), 0o600, 0)
            lock_pin = _identity(os.fstat(descriptor))
            if _identity(os.stat("lock", dir_fd=directory, follow_symlinks=False)) != lock_pin:
                raise InstallError("lock_changed")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise InstallError("install_locked") from None
            if _identity(os.fstat(descriptor)) != lock_pin or _identity(os.stat("lock", dir_fd=directory, follow_symlinks=False)) != lock_pin:
                raise InstallError("lock_changed")
            yield
            if _identity(os.fstat(descriptor)) != lock_pin or _identity(os.stat("lock", dir_fd=directory, follow_symlinks=False)) != lock_pin:
                raise InstallError("lock_changed")
        finally:
            if descriptor is not None:
                primary = sys.exc_info()[1]
                try:
                    os.close(descriptor)
                except OSError as error:
                    if primary is None:
                        raise InstallError("cleanup_unknown") from error


def _report(paths, receipt):
    return {"status": "installed", "runtime": "unverified", "archiveSha256": receipt["archiveSha256"],
            "versionPath": str(_base(paths) / "versions" / receipt["archiveSha256"])}


def status(paths: InstallPaths) -> dict:
    paths = _paths(paths)
    pending = _pending(paths)
    if pending is not None:
        return pending
    if not _exists(_state(paths) / "current.json"):
        managed = (_base(paths), paths.home / ".local/bin/orla-launcher", paths.home / ".local/bin/orla-launcherctl",
                   paths.data_home / "applications/org.orla.Launcher.desktop")
        if any(_exists(path) for path in managed):
            return {"status": "unmanaged", "runtime": "unverified", "code": "receipt_missing"}
        return {"status": "uninstalled", "runtime": "unverified"}
    receipt = _receipt(paths)
    _guard(paths, receipt)
    return _report(paths, receipt)


PINNED_LOADER = 'import hashlib,json,os,re,stat,sys\ncfg=json.loads(CONFIG_JSON)\ndef failure(code):\n print(json.dumps({"status":"error","code":code},separators=(",",":")))\n raise SystemExit(2)\ndef tool(path,expected,*,state=False):\n fds=[];relations=[];primary=None\n try:\n  parts=path.split("/")\n  if not path.startswith("/") or any(part in (".","..") for part in parts) or len(os.fsencode(path))>4096: failure("tool_path")\n  fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);fds.append(fd)\n  for part in parts[1:-1]:\n   before=os.stat(part,dir_fd=fd,follow_symlinks=False)\n   if not stat.S_ISDIR(before.st_mode) or before.st_uid not in (0,os.getuid()) or (before.st_mode&0o022 and not(before.st_uid==0 and before.st_mode&stat.S_ISVTX)): failure("tool_parent")\n   parent=fd;fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);fds.append(fd)\n   pin=(before.st_dev,before.st_ino,before.st_mode,before.st_uid,before.st_gid)\n   opened=os.fstat(fd)\n   if (opened.st_dev,opened.st_ino,opened.st_mode,opened.st_uid,opened.st_gid)!=pin: failure("tool_parent_changed")\n   relations.append((parent,part,fd,pin))\n  before=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)\n  if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=(0o600 if state else 0o644) or not 0<before.st_size<=(65536 if state else 2097152): failure("tool_file")\n  identity=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)\n  pin=identity(before);leaf=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd);fds.append(leaf)\n  if identity(os.fstat(leaf))!=pin: failure("tool_changed")\n  data=bytearray()\n  while True:\n   chunk=os.read(leaf,min(131072,before.st_size-len(data)+1))\n   if not chunk: break\n   data.extend(chunk)\n   if len(data)>before.st_size: failure("tool_changed")\n  if len(data)!=before.st_size or identity(os.fstat(leaf))!=pin or identity(os.stat(parts[-1],dir_fd=fd,follow_symlinks=False))!=pin: failure("tool_changed")\n  if not state and hashlib.sha256(data).hexdigest()!=expected: failure("tool_drift")\n  for parent,part,child,pin in relations:\n   named=os.stat(part,dir_fd=parent,follow_symlinks=False);opened=os.fstat(child)\n   if (named.st_dev,named.st_ino,named.st_mode,named.st_uid,named.st_gid)!=pin or (opened.st_dev,opened.st_ino,opened.st_mode,opened.st_uid,opened.st_gid)!=pin: failure("tool_parent_changed")\n  return bytes(data)\n except BaseException as error:\n  primary=error;raise\n finally:\n  cleanup=False\n  for fd in reversed(fds):\n   try: os.close(fd)\n   except OSError: cleanup=True\n  if cleanup and primary is None: failure("tool_cleanup")\ndef pending_status():\n if sys.argv[1:]!=["status"]: failure("tool_filesystem")\n def pairs(items):\n  result={}\n  for key,value in items:\n   if key in result: failure("pending_schema")\n   result[key]=value\n  return result\n def document(name):\n  return json.loads(tool(cfg["state_home"]+"/orla/launcher-install/"+name,None,state=True),object_pairs_hook=pairs,parse_constant=lambda value:failure("pending_schema"))\n try:\n  value=document("pending.json")\n except FileNotFoundError:\n  try: value=document("pending-intent.json")\n  except FileNotFoundError: failure("tool_filesystem")\n keys={"schema","operation","archiveSha256","commit","uid","code","files","ownedFiles","directories"}\n sha=lambda value:type(value) is str and re.fullmatch("[0-9a-f]{64}",value) is not None\n if type(value) is not dict or set(value)!=keys or value["schema"]!="orla-launcher-pending-0.1" or value["operation"] not in ("install","uninstall") or type(value["uid"]) is not int or value["uid"]!=os.getuid() or not sha(value["archiveSha256"]) or type(value["commit"]) is not str or re.fullmatch("[0-9a-f]{40}",value["commit"]) is None or value["code"]!="transaction_in_progress": failure("pending_schema")\n fixed={\'payload/bin/orla-launcher\': \'0755\', \'payload/libexec/ai.py\': \'0644\', \'payload/libexec/steam.py\': \'0644\', \'payload/libexec/ai_text_ollama.py\': \'0644\', \'payload/libexec/ai_text_transport.py\': \'0644\', \'payload/libexec/ai_text.py\': \'0644\', \'payload/LICENSE\': \'0644\', \'tools/install.py\': \'0644\', \'tools/package.py\': \'0644\', \'controller\': \'0755\', \'launcher\': \'0755\', \'menu\': \'0644\'}\n # Only computed file labels may be carried in private ownership evidence.\n if type(value["files"]) is not list or len(value["files"])!=len(fixed): failure("pending_schema")\n expected={}\n for item in value["files"]:\n  if type(item) is not dict or set(item)!={"key","mode","size","sha256"}: failure("pending_schema")\n  key=item["key"]\n  if type(key) is not str or key not in fixed or key in expected or item["mode"]!=fixed[key] or type(item["size"]) is not int or not 0<item["size"]<=67108864 or not sha(item["sha256"]): failure("pending_schema")\n  expected[key]=item\n if type(value["ownedFiles"]) is not list or len(value["ownedFiles"])>19: failure("pending_schema")\n seen=set()\n for item in value["ownedFiles"]:\n  if type(item) is not dict or set(item)!={"key","mode","expectedMode","size","sha256","expectedSha256","complete","pin"}: failure("pending_schema")\n  key=item["key"];original="payload/"+key[len("incoming/"):] if type(key) is str and key.startswith("incoming/") else key\n  if type(key) is not str or key in seen or original not in fixed or (key!=original and not original.startswith("payload/")) or type(item["mode"]) is not str or re.fullmatch("0[0-7]{3}",item["mode"]) is None or item["expectedMode"]!=fixed[original] or item["expectedSha256"]!=expected[original]["sha256"] or type(item["size"]) is not int or not 0<=item["size"]<=67108864 or not sha(item["sha256"]) or type(item["complete"]) is not bool or item["complete"]!=(item["mode"]==fixed[original] and item["size"]==expected[original]["size"] and item["sha256"]==expected[original]["sha256"]) or type(item["pin"]) is not list or len(item["pin"])!=9 or any(type(n) is not int for n in item["pin"]): failure("pending_schema")\n  seen.add(key)\n directory_keys={"base","versions","version","payload-bin","payload-libexec","tools","incoming","incoming-bin","incoming-libexec"}\n if type(value["directories"]) is not list or len(value["directories"])>len(directory_keys): failure("pending_schema")\n seen=set()\n for item in value["directories"]:\n  if type(item) is not dict or set(item)!={"key","pin"} or type(item["key"]) is not str or item["key"] not in directory_keys or item["key"] in seen or type(item["pin"]) is not list or len(item["pin"])!=5 or any(type(n) is not int for n in item["pin"]): failure("pending_schema")\n  seen.add(item["key"])\n code=value["code"]\n try: error=document("pending-error.json")\n except FileNotFoundError: error=None\n if error is not None:\n  if type(error) is not dict or set(error)!={"schema","operation","archiveSha256","uid","code"} or error["schema"]!="orla-launcher-pending-error-0.1" or error["operation"]!=value["operation"] or error["archiveSha256"]!=value["archiveSha256"] or type(error["uid"]) is not int or error["uid"]!=os.getuid() or type(error["code"]) is not str or re.fullmatch("[a-z][a-z0-9_]{0,63}",error["code"]) is None: failure("pending_schema")\n  code=error["code"]\n print(json.dumps({"status":"pending","runtime":"unverified","archiveSha256":value["archiveSha256"],"code":code},separators=(",",":")))\n raise SystemExit(0)\ntry:\n try:\n  manager=tool(cfg["manager"],cfg["managerSha256"])\n  tool(cfg["package"],cfg["packageSha256"])\n except FileNotFoundError:\n  pending_status()\n sys.argv=[cfg["manager"],"--home",cfg["home"],"--data-home",cfg["data_home"],"--state-home",cfg["state_home"]]+sys.argv[1:]\n globals()["__file__"]=cfg["manager"]\n exec(compile(manager,cfg["manager"],"exec"),globals())\nexcept (UnicodeDecodeError,ValueError,RecursionError):\n failure("pending_schema")\nexcept OSError:\n failure("tool_filesystem")\n'


def _desktop_quote(value):
    # General-value decoding precedes Exec quoting: escape each layer separately.
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    escaped = escaped.replace("\\", "\\\\").replace("%", "%%")
    return '"' + escaped + '"'


def _entrypoints(paths, manager_sha):
    manager = _base(paths) / "tools/install.py"
    python = str(_absolute(Path(sys.executable)))
    if any(ord(char) > 127 for char in python) or "=" in python:
        raise InstallError("python_wrapper")
    controller = paths.home / ".local/bin/orla-launcherctl"
    config = {"manager": str(manager), "managerSha256": manager_sha,
              "package": str(_base(paths) / "tools/package.py"), "packageSha256": PACKAGE_SHA256,
              "home": str(paths.home), "data_home": str(paths.data_home), "state_home": str(paths.state_home),
              "launcher": str(paths.home / ".local/bin/orla-launcher")}
    configured = PINNED_LOADER.replace("CONFIG_JSON", repr(json.dumps(config, sort_keys=True, ensure_ascii=True)))
    code = "exec(" + repr(configured) + ")"
    command = [python, "-I", "-B", "-c", code]
    ctl = "#!/bin/sh\nexec " + " ".join(shlex.quote(part) for part in command) + ' "$@"\n'
    launcher = "#!/bin/sh\nexec " + shlex.quote(str(controller)) + ' launch "$@"\n'
    desktop_command = command + ["launch"]
    menu = "[Desktop Entry]\nType=Application\nName=Orla Launcher\nExec=" + " ".join(_desktop_quote(part) for part in desktop_command) \
           + "\nIcon=system-search\nTerminal=false\nCategories=Utility;\n"
    return {"controller": ctl.encode("utf-8"), "launcher": launcher.encode("utf-8"), "menu": menu.encode("ascii")}


def _mkdir_new(path, mode=0o755, *, owned=None, key=None):
    with _directory(path.parent, create=True) as parent:
        try:
            os.mkdir(path.name, mode, dir_fd=parent)
        except FileExistsError:
            raise InstallError("install_conflict") from None
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode) or before.st_uid != os.getuid():
            raise InstallError("parent_changed")
        if owned is not None:
            owned[key] = list(_directory_identity(before))
        descriptor = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        try:
            opened = os.fstat(descriptor)
            if _directory_identity(opened) != _directory_identity(before):
                raise InstallError("parent_changed")
            os.fchmod(descriptor, mode)
            pin = _directory_identity(os.fstat(descriptor))
            if owned is not None:
                owned[key] = list(pin)
            if before.st_dev != pin[0] or before.st_ino != pin[1] or pin[3] != os.getuid():
                raise InstallError("parent_changed")
            os.fsync(descriptor)
        finally:
            primary = sys.exc_info()[1]
            try:
                os.close(descriptor)
            except OSError as error:
                if primary is None:
                    raise InstallError("cleanup_unknown") from error
        if _directory_identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != pin:
            raise InstallError("parent_changed")
        os.fsync(parent)
        return list(pin)


def _publish_version(parent, source_name, target_name):
    # Retain the observable absence preflight; the kernel then enforces absence.
    try:
        os.stat(target_name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise InstallError("install_conflict")
    try:
        library = ctypes.CDLL(None, use_errno=True)
        rename = library.renameat2
    except (OSError, AttributeError):
        raise InstallError("publish_api_unavailable") from None
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent, os.fsencode(source_name), parent, os.fsencode(target_name), 1) != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise InstallError("install_conflict")
        if code in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise InstallError("publish_api_unavailable")
        raise OSError(code, "owned version publication failed")


def _pending_files(paths, digest):
    fixed = dict(_files(paths, digest))
    incoming = _base(paths) / "versions" / (".incoming-" + digest)
    fixed.update({"incoming/" + relative: (incoming / relative, mode) for relative, mode in PAYLOAD})
    return fixed


def _pending_directories(paths, digest):
    fixed = dict(_directories(paths, digest))
    incoming = _base(paths) / "versions" / (".incoming-" + digest)
    fixed.update({"incoming": incoming, "incoming-bin": incoming / "bin", "incoming-libexec": incoming / "libexec"})
    return fixed


def _error_code(error):
    code = error.code if isinstance(error, InstallError) else "filesystem_unknown"
    if type(code) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code, re.ASCII) is None:
        return "filesystem_unknown"
    return code


def _pending_record(paths, operation, digest, commit, records, directory_pins, created=None):
    expected = {item["key"]: item for item in records}
    owned = []
    for key, (path, mode) in _pending_files(paths, digest).items():
        original_key = "payload/" + key[len("incoming/"):] if key.startswith("incoming/") else key
        record = expected[original_key]
        if created is not None and str(path) not in created:
            continue
        try:
            data, pin = _read(path, mode=None if created is not None else mode)
        except (InstallError, OSError):
            continue
        digest_observed = hashlib.sha256(data).hexdigest()
        if created is not None and list(pin[:2]) != created[str(path)]:
            continue
        if created is not None or (len(data) == record["size"] and digest_observed == record["sha256"]):
            owned.append({"key": key, "mode": f"{stat.S_IMODE(pin[2]):04o}", "expectedMode": record["mode"], "size": len(data),
                          "sha256": digest_observed, "expectedSha256": record["sha256"],
                          "complete": stat.S_IMODE(pin[2]) == mode and len(data) == record["size"] and digest_observed == record["sha256"], "pin": list(pin)})
    return {"schema": "orla-launcher-pending-0.1", "operation": operation,
            "archiveSha256": digest, "commit": commit, "uid": os.getuid(),
            "code": "transaction_in_progress", "files": records, "ownedFiles": owned,
            "directories": [{"key": key, "pin": pin} for key, pin in directory_pins.items()]}


def _record_failure(paths, operation, digest, commit, records, directory_pins, error, created=None):
    # The initial intent/history never changes; first-cause evidence is separate.
    pending_path = _state(paths) / "pending.json"
    if not _exists(pending_path):
        _write_new(pending_path, _json(_pending_record(paths, operation, digest, commit, records, directory_pins, created)), 0o600)
    failure = {"schema": "orla-launcher-pending-error-0.1", "operation": operation,
               "archiveSha256": digest, "uid": os.getuid(), "code": _error_code(error)}
    if not _exists(_state(paths) / "pending-error.json"):
        _write_new(_state(paths) / "pending-error.json", _json(failure), 0o600)


def _pending(paths):
    path = _state(paths) / "pending.json"
    if not _exists(path):
        path = _state(paths) / "pending-intent.json"
        if not _exists(path):
            return None
    data, _pin = _read(path, mode=0o600, limit=MAX_RECEIPT_BYTES)
    value = _strict_json(data)
    keys = {"schema", "operation", "archiveSha256", "commit", "uid", "code", "files", "ownedFiles", "directories"}
    if type(value) is not dict or set(value) != keys or value["schema"] != "orla-launcher-pending-0.1" \
            or value["operation"] not in ("install", "uninstall") or value["uid"] != os.getuid() \
            or type(value["uid"]) is not int or type(value["archiveSha256"]) is not str \
            or SHA256.fullmatch(value["archiveSha256"]) is None or type(value["commit"]) is not str \
            or COMMIT.fullmatch(value["commit"]) is None or value["code"] != "transaction_in_progress":
        raise InstallError("pending_schema")
    fixed = _files(paths, value["archiveSha256"])
    if type(value["files"]) is not list or len(value["files"]) != len(fixed):
        raise InstallError("pending_schema")
    expected = {}
    for record in value["files"]:
        if type(record) is not dict or set(record) != {"key", "mode", "size", "sha256"}:
            raise InstallError("pending_schema")
        key = record["key"]
        if type(key) is not str or key not in fixed or key in expected or record["mode"] != f"{fixed[key][1]:04o}" \
                or type(record["size"]) is not int or not 0 < record["size"] <= MAX_FILE_BYTES \
                or type(record["sha256"]) is not str or SHA256.fullmatch(record["sha256"]) is None:
            raise InstallError("pending_schema")
        expected[key] = record
    possible = _pending_files(paths, value["archiveSha256"])
    if type(value["ownedFiles"]) is not list or len(value["ownedFiles"]) > len(possible):
        raise InstallError("pending_schema")
    seen = set()
    for record in value["ownedFiles"]:
        if type(record) is not dict or set(record) != {"key", "mode", "expectedMode", "size", "sha256", "expectedSha256", "complete", "pin"}:
            raise InstallError("pending_schema")
        key = record["key"]
        original = "payload/" + key[len("incoming/"):] if type(key) is str and key.startswith("incoming/") else key
        if type(key) is not str or key not in possible or key in seen or original not in expected \
                or record["expectedMode"] != expected[original]["mode"] or type(record["mode"]) is not str or re.fullmatch(r"0[0-7]{3}", record["mode"]) is None \
                or record["expectedSha256"] != expected[original]["sha256"] \
                or type(record["size"]) is not int or not 0 <= record["size"] <= MAX_FILE_BYTES \
                or type(record["sha256"]) is not str or SHA256.fullmatch(record["sha256"]) is None \
                or type(record["complete"]) is not bool or record["complete"] != (record["mode"] == expected[original]["mode"] and record["size"] == expected[original]["size"] and record["sha256"] == expected[original]["sha256"]) \
                or type(record["pin"]) is not list or len(record["pin"]) != 9 or any(type(number) is not int for number in record["pin"]):
            raise InstallError("pending_schema")
        seen.add(key)
    possible_dirs = _pending_directories(paths, value["archiveSha256"])
    if type(value["directories"]) is not list or len(value["directories"]) > len(possible_dirs):
        raise InstallError("pending_schema")
    seen = set()
    for record in value["directories"]:
        if type(record) is not dict or set(record) != {"key", "pin"} or type(record["key"]) is not str \
                or record["key"] not in possible_dirs or record["key"] in seen or type(record["pin"]) is not list \
                or len(record["pin"]) != 5 or any(type(number) is not int for number in record["pin"]):
            raise InstallError("pending_schema")
        seen.add(record["key"])
    code = value["code"]
    error_path = _state(paths) / "pending-error.json"
    if _exists(error_path):
        error = _strict_json(_read(error_path, mode=0o600, limit=4096)[0])
        if type(error) is not dict or set(error) != {"schema", "operation", "archiveSha256", "uid", "code"} \
                or error["schema"] != "orla-launcher-pending-error-0.1" or error["operation"] != value["operation"] \
                or error["archiveSha256"] != value["archiveSha256"] or type(error["uid"]) is not int or error["uid"] != os.getuid() \
                or type(error["code"]) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error["code"], re.ASCII) is None:
            raise InstallError("pending_schema")
        code = error["code"]
    return {"status": "pending", "runtime": "unverified", "archiveSha256": value["archiveSha256"], "code": code}


def install_archive(archive: Path, *, expected_sha256: str, expected_commit: str,
                    paths: InstallPaths, backend=None) -> dict:
    paths = _paths(paths)
    if backend is not None:
        raise InstallError("backend_unimplemented")
    if type(expected_sha256) is not str or SHA256.fullmatch(expected_sha256) is None \
            or type(expected_commit) is not str or COMMIT.fullmatch(expected_commit) is None:
        raise InstallError("archive_pins")
    package = _package()
    try:
        frozen = package._read_archive(archive)
        if hashlib.sha256(frozen).hexdigest() != expected_sha256:
            raise InstallError("archive_hash")
        manifest = package._verify_archive_data(frozen, expected_commit=expected_commit)
        if manifest["schema"] != "orla-launcher-package-0.3":
            raise InstallError("archive_install_schema")
        decoded = {record["name"]: package._decode_member(record) for record in package._archive_records(frozen)}
    except package.PackageError as error:
        raise InstallError(error.code) from None
    if tuple(package.PAYLOAD) != PAYLOAD:
        raise InstallError("package_payload_contract")
    manager_data, _pin = _read(Path(__file__), mode=0o644, limit=2 * 1024 * 1024)
    package_data, _pin = _read(Path(__file__).with_name("package.py"), mode=0o644, limit=2 * 1024 * 1024)
    if hashlib.sha256(package_data).hexdigest() != PACKAGE_SHA256:
        raise InstallError("package_tool_drift")
    content = {"payload/" + relative: decoded[relative] for relative, _mode in PAYLOAD}
    content.update({"tools/install.py": manager_data, "tools/package.py": package_data})
    content.update(_entrypoints(paths, hashlib.sha256(manager_data).hexdigest()))
    files = _files(paths, expected_sha256)
    records = [{"key": key, "mode": f"{mode:04o}", "size": len(content[key]),
                "sha256": hashlib.sha256(content[key]).hexdigest()} for key, (_path, mode) in files.items()]
    directories, created = {}, {}
    with _locked(paths):
        if _pending(paths) is not None:
            raise InstallError("pending_transaction")
        if _exists(_state(paths) / "current.json") or _exists(_base(paths)) \
                or any(_exists(files[key][0]) for key in ("controller", "launcher", "menu")):
            raise InstallError("install_conflict")
        for child in ("transactions", "receipts"):
            with _directory(_state(paths) / child, create=True, mode=0o700) as descriptor:
                if os.fstat(descriptor).st_uid != os.getuid() or stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o700:
                    raise InstallError("unsafe_state")
        journal = {"schema": "orla-launcher-install-transaction-0.1", "operation": "install",
                   "archiveSha256": expected_sha256, "commit": expected_commit, "phase": "prepared", "files": records}
        try:
            _write_new(_state(paths) / "transactions" / (expected_sha256 + "-install.json"), _json(journal), 0o600)
            _write_new(_state(paths) / "pending-intent.json",
                       _json(_pending_record(paths, "install", expected_sha256, expected_commit, records, {}, {})), 0o600)
            base = _base(paths)
            directories["base"] = _mkdir_new(base, owned=directories, key="base")
            directories["versions"] = _mkdir_new(base / "versions", owned=directories, key="versions")
            version = base / "versions" / expected_sha256
            incoming = version.with_name(".incoming-" + expected_sha256)
            directories["incoming"] = _mkdir_new(incoming, owned=directories, key="incoming")
            directories["incoming-bin"] = _mkdir_new(incoming / "bin", owned=directories, key="incoming-bin")
            directories["incoming-libexec"] = _mkdir_new(incoming / "libexec", owned=directories, key="incoming-libexec")
            for relative, mode in PAYLOAD:
                _write_new(incoming / relative, decoded[relative], mode, owned=created)
            with _directory(version.parent) as parent:
                _publish_version(parent, incoming.name, version.name)
                # Publication changes ownership labels before any fallible sync.
                for old, new in (("incoming", "version"), ("incoming-bin", "payload-bin"), ("incoming-libexec", "payload-libexec")):
                    directories[new] = directories.pop(old)
                for relative, _mode in PAYLOAD:
                    key = str(incoming / relative)
                    created[str(version / relative)] = created.pop(key)
                os.fsync(parent)
            directories["tools"] = _mkdir_new(base / "tools", owned=directories, key="tools")
            for key in ("tools/install.py", "tools/package.py", "controller", "launcher", "menu"):
                path, mode = files[key]
                _write_new(path, content[key], mode, owned=created)
            receipt = {"schema": SCHEMA, "archiveSha256": expected_sha256, "commit": expected_commit,
                       "uid": os.getuid(), "runtime": "unverified", "files": records,
                       "directories": [{"key": key, "pin": pin} for key, pin in directories.items()]}
            _guard(paths, receipt)
            receipt_data = _json(receipt)
            _write_new(_state(paths) / "receipts" / (expected_sha256 + ".json"), receipt_data, 0o600)
            _write_new(_state(paths) / "current.json", receipt_data, 0o600)
            _write_new(_state(paths) / "transactions" / (expected_sha256 + "-installed.json"),
                       _json({"operation": "install", "archiveSha256": expected_sha256, "phase": "committed"}), 0o600)
            intent = _state(paths) / "pending-intent.json"
            intent_data, _pin = _read(intent, mode=0o600, limit=MAX_RECEIPT_BYTES)
            _unlink_checked(intent, {"size": len(intent_data), "sha256": hashlib.sha256(intent_data).hexdigest()}, 0o600)
            return status(paths)
        except (InstallError, OSError) as error:
            try:
                _record_failure(paths, "install", expected_sha256, expected_commit, records, directories, error, created)
            except (InstallError, OSError):
                # The initial durable intent and primary exception remain intact.
                pass
            if isinstance(error, InstallError):
                raise
            raise InstallError(_error_code(error)) from error


def _unlink_checked(path, record, mode):
    data, pin = _read(path, mode=mode)
    if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise InstallError("managed_drift")
    with _directory(path.parent) as parent:
        if _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != pin:
            raise InstallError("managed_drift")
        os.unlink(path.name, dir_fd=parent)
        os.fsync(parent)


def uninstall(paths: InstallPaths, *, backend=None) -> dict:
    paths = _paths(paths)
    if backend is not None:
        raise InstallError("backend_unimplemented")
    with _locked(paths):
        if _pending(paths) is not None:
            raise InstallError("pending_transaction")
        receipt = _receipt(paths)
        _guard(paths, receipt)
        digest = receipt["archiveSha256"]
        directories = {record["key"]: record["pin"] for record in receipt["directories"]}
        _write_new(_state(paths) / "transactions" / (digest + "-uninstall.json"),
                   _json({"operation": "uninstall", "archiveSha256": digest, "phase": "prepared", "files": receipt["files"]}), 0o600)
        # Pending exists before any deletion, so interrupted status is truthful.
        _write_new(_state(paths) / "pending.json", _json(_pending_record(paths, "uninstall", digest, receipt["commit"], receipt["files"], directories)), 0o600)
        files = _files(paths, digest)
        try:
            order = ["payload/" + relative for relative, _mode in PAYLOAD] + ["launcher", "menu"]
            records = {record["key"]: record for record in receipt["files"]}
            for key in order:
                path, mode = files[key]
                _unlink_checked(path, records[key], mode)
            fixed_dirs = _directories(paths, digest)
            for key in ("payload-bin", "payload-libexec", "version", "versions"):
                path = fixed_dirs[key]
                with _directory(path.parent) as parent:
                    if list(_directory_identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False))) != directories[key]:
                        raise InstallError("managed_parent_drift")
                    os.rmdir(path.name, dir_fd=parent)
                    os.fsync(parent)
            current = _state(paths) / "current.json"
            current_data, _pin = _read(current, mode=0o600, limit=MAX_RECEIPT_BYTES)
            _unlink_checked(current, {"size": len(current_data), "sha256": hashlib.sha256(_json(receipt)).hexdigest()}, 0o600)
            _write_new(_state(paths) / "transactions" / (digest + "-uninstalled.json"),
                       _json({"operation": "uninstall", "archiveSha256": digest, "phase": "committed"}), 0o600)
            for key in ("tools/package.py", "tools/install.py"):
                path, mode = files[key]
                _unlink_checked(path, records[key], mode)
            for key in ("tools", "base"):
                path = fixed_dirs[key]
                with _directory(path.parent) as parent:
                    if list(_directory_identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False))) != directories[key]:
                        raise InstallError("managed_parent_drift")
                    os.rmdir(path.name, dir_fd=parent)
                    os.fsync(parent)
            path, mode = files["controller"]
            _unlink_checked(path, records["controller"], mode)
            pending = _state(paths) / "pending.json"
            pending_data, _pin = _read(pending, mode=0o600, limit=MAX_RECEIPT_BYTES)
            _unlink_checked(pending, {"size": len(pending_data), "sha256": hashlib.sha256(pending_data).hexdigest()}, 0o600)
        except (InstallError, OSError) as error:
            try:
                _record_failure(paths, "uninstall", digest, receipt["commit"], receipt["files"], directories, error)
            except (InstallError, OSError):
                pass
            if isinstance(error, InstallError):
                raise
            raise InstallError(_error_code(error)) from error
    return {"status": "uninstalled", "runtime": "unverified", "archiveSha256": digest}


def _launch(paths):
    if _pending(paths) is not None:
        raise InstallError("pending_transaction")
    receipt = _receipt(paths)
    _guard(paths, receipt)
    binary = _base(paths) / "versions" / receipt["archiveSha256"] / "bin/orla-launcher"
    os.execv(str(binary), [str(binary), "--no-global-shortcut"])


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orla-launcherctl")
    parser.add_argument("--home", type=Path)
    parser.add_argument("--data-home", type=Path)
    parser.add_argument("--state-home", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    install_command = commands.add_parser("install")
    install_command.add_argument("archive", type=Path)
    install_command.add_argument("--sha256", required=True)
    install_command.add_argument("--commit", required=True)
    for command in ("status", "launch", "uninstall"):
        commands.add_parser(command)
    options = parser.parse_args(arguments)
    try:
        home = options.home or Path(os.environ.get("HOME", ""))
        data_home = options.data_home or Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share")))
        state_home = options.state_home or Path(os.environ.get("XDG_STATE_HOME", str(home / ".local/state")))
        paths = _paths(InstallPaths(home, data_home, state_home))
        if options.command == "install":
            result = install_archive(options.archive, expected_sha256=options.sha256, expected_commit=options.commit, paths=paths)
        elif options.command == "status":
            result = status(paths)
        elif options.command == "uninstall":
            result = uninstall(paths)
        else:
            _launch(paths)
            return 0
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (InstallError, OSError) as error:
        code = error.code if isinstance(error, InstallError) else "filesystem_unknown"
        print(json.dumps({"status": "error", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
