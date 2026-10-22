"""Experimental bounded, descriptor-confined host dependency catalog.

Filesystem observations and supplied-policy graph projection remain separate.
Cooperative budgets and namespace replay do not establish an atomic snapshot,
loader selection, ABI compatibility or runtime/session admission.
"""

from collections import deque
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time

import package
from inventory_policy import resolve_catalog


SCHEMA = "orla-launcher-host-catalog-0.1"
DEFAULT_LIMITS = {
    "roots": 16, "nodes": 256, "edges": 4096, "paths": 4096, "aliasHops": 16,
    "elfBytes": 67108864, "contentBytes": 268435456, "linkBytes": 1048576,
    "components": 56, "fds": 64, "fsOperations": 100000, "evidenceBytes": 4194304,
    "seconds": 20.0, "finalizationReserve": 3.1, "rpmQueries": 256,
    "rpmOutputBytes": 4194304, "rpmSeconds": 8.0,
}


class HostInventoryError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class _Operations:
    # Instantiate only after caller input validation; no import-time operations.
    open = staticmethod(os.open)
    stat = staticmethod(os.stat)
    fstat = staticmethod(os.fstat)
    scandir = staticmethod(os.scandir)
    read = staticmethod(os.read)
    readlink = staticmethod(os.readlink)
    close = staticmethod(os.close)
    monotonic = staticmethod(time.monotonic)
    rpm = staticmethod(package._doctor_rpm)


def _limits(value):
    selected = dict(DEFAULT_LIMITS)
    if value is not None:
        if type(value) is not dict or not set(value) <= set(selected):
            raise HostInventoryError("host_limits")
        for name, number in value.items():
            if name in ("seconds", "rpmSeconds"):
                valid = type(number) in (int, float) and 0 < number <= selected[name] and math.isfinite(number)
            else:
                valid = type(number) is int and 0 < number <= selected[name]
            if not valid:
                raise HostInventoryError("host_limits")
            selected[name] = number
    if selected["roots"] < 7 or selected["evidenceBytes"] < 4096:
        raise HostInventoryError("host_limits")
    return selected


class _Collector:
    def __init__(self, ops, limits):
        self.ops, self.limits = ops, limits
        self.start = ops.monotonic()
        self.deadline = self.start + limits["seconds"]
        self.finalizing = False
        self.iterators = 0
        self.stage_pins = {}
        self.required_paths = set()
        self.expanded = set()
        self.edge_keys = set()
        self.chains = []
        self.chain_candidates = set()
        self.catalog_endpoints = {}
        self.raw_proofs = {}
        self.traversal_complete = True
        self.stopped = False
        self.first_error = None
        self.ancestors = {}
        self.observations = {}
        self.objects, self.paths = {}, {}
        self.live = set()
        self.used = {"fsOperations": 0, "contentBytes": 0, "linkBytes": 0,
                     "rpmQueries": 0, "rpmOutputBytes": 0, "rpmSeconds": 0.0,
                     "edges": 0, "peakFds": 0, "aliasHops": 0}
        self.metadata_complete = True
        self.incomplete = []

    def error(self, code, namespace=None):
        if self.first_error is None:
            self.first_error = {"code": code, "namespace": namespace}

    def check(self, reserve=0.0):
        if self.stopped:
            raise HostInventoryError("cleanup_unknown")
        final_reserve = 0.0 if self.finalizing else self.limits["finalizationReserve"]
        if self.ops.monotonic() + reserve + final_reserve >= self.deadline:
            raise HostInventoryError("deadline")

    def call(self, name, *args, **kwargs):
        self.check()
        if self.used["fsOperations"] >= self.limits["fsOperations"]:
            raise HostInventoryError("operation_budget")
        self.used["fsOperations"] += 1
        result = getattr(self.ops, name)(*args, **kwargs)
        self.check()
        return result

    def open(self, path, flags, descriptors, *, dir_fd=None):
        if len(self.live) + self.iterators >= self.limits["fds"]:
            raise HostInventoryError("fd_budget")
        # Track successful opens before the post-operation clock check, so an
        # overrun cannot strand a newly returned descriptor.
        self.check()
        if self.used["fsOperations"] >= self.limits["fsOperations"]:
            raise HostInventoryError("operation_budget")
        self.used["fsOperations"] += 1
        descriptor = self.ops.open(path, flags, **({"dir_fd": dir_fd} if dir_fd is not None else {}))
        descriptors.append(descriptor)
        self.live.add(descriptor)
        self.used["peakFds"] = max(self.used["peakFds"], len(self.live) + self.iterators)
        self.check()
        return descriptor

    def close(self, descriptors):
        failed = False
        for descriptor in reversed(descriptors):
            try:
                self.ops.close(descriptor)
            except OSError:
                failed = True
                self.error("cleanup_unknown")
            finally:
                self.live.discard(descriptor)
        if failed:
            self.stopped = True
            raise HostInventoryError("cleanup_unknown")

    def directory_pin(self, path, status):
        pin = package._inventory_directory_identity(status)
        if not stat.S_ISDIR(status.st_mode):
            raise HostInventoryError("parent_unsafe")
        if path in self.ancestors and self.ancestors[path] != pin:
            raise HostInventoryError("parent_changed")
        if path not in self.ancestors and len(self.ancestors) >= self.limits["paths"]:
            raise HostInventoryError("path_budget")
        self.ancestors.setdefault(path, pin)
        return pin

    @contextmanager
    def parent(self, path):
        package._safe_absolute_path(path, "host_path")
        parts = Path(path).parts
        if len(parts) > self.limits["components"]:
            raise HostInventoryError("component_budget")
        descriptors, relations, parents = [], [], []
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            descriptor = self.open("/", flags, descriptors)
            current = "/"
            pin = self.directory_pin(current, self.call("fstat", descriptor))
            parents.append({"namespace": current, "pin": list(pin)})
            root_fd, root_pin = descriptor, pin
            for component in parts[1:-1]:
                parent_fd = descriptor
                expected = self.call("stat", component, dir_fd=parent_fd, follow_symlinks=False)
                current = current.rstrip("/") + "/" + component
                pin = self.directory_pin(current, expected)
                descriptor = self.open(component, flags, descriptors, dir_fd=parent_fd)
                opened = self.call("fstat", descriptor)
                if package._inventory_directory_identity(opened) != pin:
                    raise HostInventoryError("parent_changed")
                if current in self.stage_pins and package._doctor_identity(opened) != self.stage_pins[current]:
                    raise HostInventoryError("stage_changed")
                parents.append({"namespace": current, "pin": list(pin)})
                relations.append((parent_fd, component, descriptor, pin))
            yield descriptor, parts[-1], parents, descriptors
            if package._inventory_directory_identity(self.call("fstat", root_fd)) != root_pin:
                raise HostInventoryError("parent_changed")
            for parent_fd, component, child_fd, pin in relations:
                named = self.call("stat", component, dir_fd=parent_fd, follow_symlinks=False)
                opened = self.call("fstat", child_fd)
                if package._inventory_directory_identity(named) != pin or package._inventory_directory_identity(opened) != pin:
                    raise HostInventoryError("parent_changed")
        except (HostInventoryError, package.PackageError, OSError) as error:
            code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "filesystem_unknown"
            self.error(code, path)
            raise
        finally:
            self.close(descriptors)

    @contextmanager
    def entries(self, descriptor):
        self.check()
        if len(self.live) + self.iterators >= self.limits["fds"]:
            raise HostInventoryError("fd_budget")
        if self.used["fsOperations"] >= self.limits["fsOperations"]:
            raise HostInventoryError("operation_budget")
        self.used["fsOperations"] += 1
        iterator = self.ops.scandir(descriptor)
        self.iterators += 1
        self.used["peakFds"] = max(self.used["peakFds"], len(self.live) + self.iterators)
        try:
            self.check()
            yield iterator
        except (HostInventoryError, package.PackageError, OSError) as error:
            self.error(error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "filesystem_unknown")
            raise
        finally:
            try:
                iterator.close()
            except OSError:
                self.error("cleanup_unknown")
                self.stopped = True
                raise HostInventoryError("cleanup_unknown") from None
            finally:
                self.iterators -= 1

    def read_chunk(self, descriptor, count, data, record):
        self.check()
        if self.used["fsOperations"] >= self.limits["fsOperations"]:
            raise HostInventoryError("operation_budget")
        self.used["fsOperations"] += 1
        chunk = self.ops.read(descriptor, count)
        data.extend(chunk)
        record.update(observedBytes=len(data), partialSha256=hashlib.sha256(data).hexdigest(),
                      hashCoverage="partial_read")
        # Bytes returned by an overrun remain partial facts, never a full hash.
        self.check()
        return chunk

    def raw_target(self, current, target):
        if target.startswith("/"):
            package._safe_absolute_path(target, "alias_target")
            if not target.startswith("/usr/lib64/"):
                raise HostInventoryError("alias_escape")
            return target
        components = target.split("/")
        if any(not part for part in components) or len(components) + len(Path(current).parts) > self.limits["components"]:
            raise HostInventoryError("component_budget")
        with self.parent(current) as (parent_fd, _name, parents, descriptors):
            stack = [(entry["namespace"], descriptor) for entry, descriptor in zip(parents, descriptors)]
            relations = []
            for index, part in enumerate(components):
                self.check()
                if part == ".":
                    continue
                if part == "..":
                    if len(stack) <= 3:
                        raise HostInventoryError("alias_escape")
                    stack.pop()
                    continue
                path = stack[-1][0].rstrip("/") + "/" + part
                if not path.startswith("/usr/lib64/"):
                    raise HostInventoryError("alias_escape")
                if index == len(components) - 1:
                    result = path
                    break
                expected = self.call("stat", part, dir_fd=stack[-1][1], follow_symlinks=False)
                pin = self.directory_pin(path, expected)
                child_fd = self.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     descriptors, dir_fd=stack[-1][1])
                if package._inventory_directory_identity(self.call("fstat", child_fd)) != pin:
                    raise HostInventoryError("parent_changed")
                relations.append((stack[-1][1], part, child_fd, pin))
                self.raw_proofs.setdefault(current, set()).add(path)
                stack.append((path, child_fd))
            else:
                raise HostInventoryError("alias_target")
            for parent_fd, part, child_fd, pin in relations:
                if package._inventory_directory_identity(self.call("stat", part, dir_fd=parent_fd, follow_symlinks=False)) != pin \
                        or package._inventory_directory_identity(self.call("fstat", child_fd)) != pin:
                    raise HostInventoryError("parent_changed")
            return result

    def stage_gate(self, stage):
        expected = ({"bin", "libexec", "LICENSE"}, {"orla-launcher"},
                    {"ai.py", "steam.py", "ai_text_ollama.py", "ai_text_transport.py", "ai_text.py"})
        pins = []
        with self.parent(str(stage / "LICENSE")) as (stage_fd, _name, _parents, descriptors):
            directories = [(str(stage), stage_fd)]
            for child in ("bin", "libexec"):
                before = self.call("stat", child, dir_fd=stage_fd, follow_symlinks=False)
                pin = self.directory_pin(str(stage / child), before)
                descriptor = self.open(child, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                       descriptors, dir_fd=stage_fd)
                if package._inventory_directory_identity(self.call("fstat", descriptor)) != pin:
                    raise HostInventoryError("parent_changed")
                directories.append((str(stage / child), descriptor))
            # All directory types are admitted before any bounded enumeration.
            for (path, descriptor), names in zip(directories, expected):
                before = package._doctor_identity(self.call("fstat", descriptor))
                observed = set()
                with self.entries(descriptor) as entries:
                    for count, entry in enumerate(entries, 1):
                        self.check()
                        if count > len(names):
                            raise HostInventoryError("stage_layout")
                        observed.add(entry.name)
                if observed != names or package._doctor_identity(self.call("fstat", descriptor)) != before:
                    raise HostInventoryError("stage_layout")
                pins.append((path, before))
            for path, descriptor in directories[1:]:
                name = path.rsplit("/", 1)[1]
                pin = dict(pins)[path]
                if package._doctor_identity(self.call("stat", name, dir_fd=stage_fd, follow_symlinks=False)) != pin \
                        or package._doctor_identity(self.call("fstat", descriptor)) != pin:
                    raise HostInventoryError("stage_changed")
        return pins

    def observe(self, path, *, main=False, staged_mode=None, hop=None):
        if path in self.observations:
            return self.observations[path]
        if len(self.observations) >= self.limits["paths"]:
            raise HostInventoryError("path_budget")
        record = {"namespace": path, "kind": "unknown", "state": "unknown", "code": None,
                  "parentPins": [], "pin": None, "package": {"state": "NOT_QUERIED"} if staged_mode is not None else None}
        self.observations[path] = record
        phase = "parents"
        try:
            with self.parent(path) as (parent_fd, name, parents, descriptors):
                record["parentPins"] = parents
                phase = "initial_leaf"
                try:
                    before = self.call("stat", name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    self.error("endpoint_missing", path)
                    raise
                phase = "observed_leaf"
                pin = package._doctor_identity(before)
                record.update(pin=list(pin), size=before.st_size, mode=f"{stat.S_IMODE(before.st_mode):04o}")
                if stat.S_ISLNK(before.st_mode) and staged_mode is None:
                    record["kind"] = "link"
                    if not hasattr(os, "O_PATH") or not 0 < before.st_size <= 4096:
                        raise HostInventoryError("alias_api_or_size")
                    if self.used["linkBytes"] + before.st_size > self.limits["linkBytes"]:
                        raise HostInventoryError("link_budget")
                    self.used["linkBytes"] += before.st_size
                    descriptor = self.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, descriptors, dir_fd=parent_fd)
                    if package._doctor_identity(self.call("fstat", descriptor)) != pin:
                        raise HostInventoryError("namespace_changed")
                    try:
                        target = self.call("readlink", "", dir_fd=descriptor)
                    except OSError:
                        raise HostInventoryError("alias_api_unavailable") from None
                    if type(target) is not str or len(target) != before.st_size or not 0 < len(target) <= 4096 \
                            or any(not 32 <= ord(character) < 127 for character in target):
                        raise HostInventoryError("alias_target")
                    record.update(rawTarget=target, targetSha256=hashlib.sha256(target.encode("ascii")).hexdigest(),
                                  hop=hop, hopSemantics="first_recorded_chain_occurrence")
                    if self.call("readlink", "", dir_fd=descriptor) != target \
                            or package._doctor_identity(self.call("fstat", descriptor)) != pin:
                        raise HostInventoryError("namespace_changed")
                elif stat.S_ISREG(before.st_mode):
                    record["kind"] = "file"
                    if before.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX) \
                            or before.st_size > self.limits["elfBytes"] \
                            or (staged_mode is not None and (stat.S_IMODE(before.st_mode) != staged_mode or before.st_size == 0)):
                        raise HostInventoryError("leaf_unsafe")
                    if self.used["contentBytes"] + before.st_size + 1 > self.limits["contentBytes"]:
                        raise HostInventoryError("content_budget")
                    self.used["contentBytes"] += before.st_size + 1
                    descriptor = self.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                                           descriptors, dir_fd=parent_fd)
                    if package._doctor_identity(self.call("fstat", descriptor)) != pin:
                        raise HostInventoryError("namespace_changed")
                    data = bytearray()
                    while True:
                        chunk = self.read_chunk(descriptor, min(128 * 1024, before.st_size - len(data) + 1), data, record)
                        if not chunk:
                            break
                        if len(data) > before.st_size:
                            raise HostInventoryError("content_changed")
                    if len(data) != before.st_size:
                        raise HostInventoryError("content_changed")
                    record["sha256"] = hashlib.sha256(data).hexdigest()
                    record["hashCoverage"] = "complete_read"
                    if package._doctor_identity(self.call("fstat", descriptor)) != pin:
                        raise HostInventoryError("content_changed")
                    if main or staged_mode is None:
                        record["dynamicTags"] = package._inventory_dynamic(bytes(data), main=main)
                        if not main and record["dynamicTags"]["type"] != "shared_object":
                            raise HostInventoryError("elf_refused")
                else:
                    raise HostInventoryError("leaf_unsafe")
                if package._doctor_identity(self.call("stat", name, dir_fd=parent_fd, follow_symlinks=False)) != pin:
                    raise HostInventoryError("namespace_changed")
                record["state"] = "found"
                if record["kind"] == "file":
                    record["hashCoverage"] = "complete_stable_read"
        except FileNotFoundError:
            record.update(kind="absence" if phase == "initial_leaf" else record["kind"],
                          state="absent" if phase == "initial_leaf" else "unknown",
                          code="endpoint_missing" if phase == "initial_leaf" else "namespace_changed")
            self.error(record["code"], path)
        except (HostInventoryError, package.PackageError, OSError) as error:
            code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "filesystem_unknown"
            record.update(state="unknown", code=code)
            self.error(code, path)
        if record["state"] == "unknown":
            self.traversal_complete = False
        return record

    def catalog(self, candidate):
        self.check()
        if candidate in self.chain_candidates:
            return self.catalog_endpoints.get(candidate)
        if len(self.chain_candidates) >= self.limits["paths"]:
            raise HostInventoryError("path_budget")
        self.chain_candidates.add(candidate)
        chain = {"candidate": candidate, "namespaces": [], "endpoint": None, "state": "unknown"}
        self.chains.append(chain)
        current, visited = candidate, set()
        try:
            for hop in range(self.limits["aliasHops"] + 1):
                self.check()
                if current in visited:
                    raise HostInventoryError("alias_loop")
                visited.add(current)
                chain["namespaces"].append(current)
                record = self.observe(current, hop=hop)
                if record["state"] != "found":
                    self.paths[current] = {"state": "absent_in_catalog" if record["state"] == "absent" else "unknown"}
                    chain["state"] = self.paths[current]["state"]
                    return None
                if record["kind"] == "file":
                    if len(self.objects) >= self.limits["nodes"] and current not in self.objects:
                        raise HostInventoryError("node_budget")
                    self.objects[current] = record["dynamicTags"]
                    self.paths[current] = {"state": "object", "canonical": current}
                    chain.update(endpoint=current, state="object")
                    self.catalog_endpoints[candidate] = current
                    return current
                if hop >= self.limits["aliasHops"]:
                    raise HostInventoryError("alias_hop_limit")
                target = record["rawTarget"]
                next_path = self.raw_target(current, target)
                self.used["aliasHops"] += 1
                self.paths[current] = {"state": "alias", "target": target}
                current = next_path
        except (HostInventoryError, package.PackageError, OSError) as error:
            code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "filesystem_unknown"
            self.paths[current] = {"state": "unknown"}
            self.error(code, current)
            self.incomplete.append({"reason": code, "candidate": candidate, "namespace": current})
            self.traversal_complete = False
        return None

    def expand(self, path):
        pending = deque([path])
        while pending:
            self.check()
            source = pending.popleft()
            if source in self.expanded:
                continue
            self.expanded.add(source)
            tags = self.objects.get(source)
            if tags is None:
                continue
            for occurrence, name in enumerate(tags["needed"]):
                self.check()
                key = (source, occurrence)
                candidate = "/usr/lib64/" + name
                if key not in self.edge_keys:
                    if len(self.edge_keys) >= self.limits["edges"]:
                        self.error("edge_budget", source)
                        self.incomplete.append({"reason": "edge_budget", "source": source,
                                                "occurrence": occurrence, "candidate": candidate})
                        self.traversal_complete = False
                        return
                    self.edge_keys.add(key)
                    self.used["edges"] = len(self.edge_keys)
                target = self.catalog(candidate)
                if target is not None and target not in self.expanded:
                    pending.append(target)

    def metadata(self):
        for path, record in self.observations.items():
            if record["package"] == {"state": "NOT_QUERIED"}:
                continue
            if record["state"] == "absent" and path not in self.required_paths:
                record["package"] = {"state": "NOT_QUERIED", "reason": "observed_absence"}
                continue
            if record["state"] != "found":
                self.metadata_complete = False
                continue
            try:
                self.check(3.1)
                if self.used["rpmQueries"] >= self.limits["rpmQueries"] \
                        or self.used["rpmOutputBytes"] + 16384 > self.limits["rpmOutputBytes"] \
                        or self.used["rpmSeconds"] + 3.1 > self.limits["rpmSeconds"]:
                    raise HostInventoryError("rpm_budget")
                self.used["rpmQueries"] += 1
                self.used["rpmOutputBytes"] += 16384
                started = self.ops.monotonic()
                try:
                    value = self.ops.rpm(path)
                finally:
                    self.used["rpmSeconds"] += max(0.0, self.ops.monotonic() - started)
                record["package"] = {"state": "found", **value}
                self.check()
                if self.used["rpmSeconds"] > self.limits["rpmSeconds"]:
                    raise HostInventoryError("rpm_overrun")
            except (HostInventoryError, package.PackageError, OSError) as error:
                code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "rpm_unknown"
                record["package"] = {"state": "unknown", "code": code}
                self.metadata_complete = False
                self.error(code, path)
                if code in ("rpm_cleanup_unknown", "rpm_overrun", "deadline", "cleanup_unknown"):
                    self.stopped = True

    def replay_record(self, path, record):
        with self.parent(path) as (parent_fd, name, _parents, descriptors):
            if record["state"] == "absent":
                try:
                    self.call("stat", name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    return
                raise HostInventoryError("absence_changed")
            if record["pin"] is None or record["kind"] not in ("file", "link"):
                return
            pin = tuple(record["pin"])
            if package._doctor_identity(self.call("stat", name, dir_fd=parent_fd, follow_symlinks=False)) != pin:
                raise HostInventoryError("namespace_changed")
            flags = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC if record["kind"] == "link" else \
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            descriptor = self.open(name, flags, descriptors, dir_fd=parent_fd)
            if package._doctor_identity(self.call("fstat", descriptor)) != pin:
                raise HostInventoryError("namespace_changed")
            if record["kind"] == "link" and self.call("readlink", "", dir_fd=descriptor) != record["rawTarget"]:
                raise HostInventoryError("namespace_changed")
            if package._doctor_identity(self.call("stat", name, dir_fd=parent_fd, follow_symlinks=False)) != pin \
                    or package._doctor_identity(self.call("fstat", descriptor)) != pin:
                raise HostInventoryError("namespace_changed")

    def invalidate(self, path, code):
        record = self.observations.get(path)
        if record is not None:
            record.update(state="unknown", code=code)
        if path.startswith("/usr/lib64/"):
            self.paths[path] = {"state": "unknown"}
        self.objects.pop(path, None)
        self.error(code, path)
        self.traversal_complete = False

    def recheck_stage(self, stage, pins):
        for relative, _mode in package.PAYLOAD:
            path = str(stage / relative)
            try:
                self.replay_record(path, self.observations[path])
            except (HostInventoryError, package.PackageError, OSError) as error:
                code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "stage_changed"
                self.invalidate(path, code)
                raise HostInventoryError("stage_changed") from None
        if self.stage_gate(stage) != pins:
            raise HostInventoryError("stage_changed")

    def replay(self):
        self.finalizing = True
        # Replay even raw proof directories that were opened before '..' elision.
        for directory in list(self.ancestors):
            try:
                dummy = directory.rstrip("/") + "/.orla-directory-replay"
                with self.parent(dummy):
                    pass
            except (HostInventoryError, package.PackageError, OSError) as error:
                code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "parent_changed"
                for path, record in self.observations.items():
                    if any(parent["namespace"] == directory for parent in record["parentPins"]) \
                            or directory in self.raw_proofs.get(path, set()):
                        self.invalidate(path, code)
                self.error(code, directory)
                self.traversal_complete = False
        for path, record in self.observations.items():
            try:
                self.replay_record(path, record)
            except (HostInventoryError, package.PackageError, OSError) as error:
                code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "namespace_changed"
                self.invalidate(path, code)
        for chain in self.chains:
            if any(self.paths.get(path, {}).get("state") == "unknown" for path in chain["namespaces"]):
                chain["state"] = "unknown"
                chain["endpoint"] = None


def _fits_evidence(value, limit):
    # Stop encoding at the cap without constructing a giant temporary JSON blob.
    used = 0
    for chunk in json.JSONEncoder(separators=(",", ":"), ensure_ascii=True).iterencode(value):
        used += len(chunk.encode("ascii"))
        if used > limit:
            return False
    return True


def collect_host_catalog(stage, *, limits=None):
    if not isinstance(stage, Path):
        raise HostInventoryError("host_stage")
    text = str(stage)
    if any(not 32 <= ord(character) < 127 for character in text) or len(str(stage / "bin/orla-launcher")) > 4096:
        raise HostInventoryError("host_stage")
    try:
        package._safe_absolute_path(text, "host_stage")
    except package.PackageError:
        raise HostInventoryError("host_stage") from None
    selected = _limits(limits)
    fixed = [(role, path) for role, path in sorted(package._EXACT_ASSET_PATHS.items()) if role != "qml_controls_qmldir"]
    roots = [{"id": "staged_launcher", "path": str(stage / "bin/orla-launcher"), "required": True}] \
            + [{"id": role, "path": path, "required": True} for role, path in fixed]
    collector = _Collector(_Operations(), selected)
    collector.required_paths = {root["path"] for root in roots}
    stage_files = []
    stage_ready = False
    try:
        stage_pins = collector.stage_gate(stage)
        collector.stage_pins = dict(stage_pins)
        for relative, mode in package.PAYLOAD:
            record = collector.observe(str(stage / relative), main=relative == "bin/orla-launcher", staged_mode=mode)
            if record["state"] != "found":
                raise HostInventoryError("stage_refused")
            stage_files.append({"path": relative, "mode": record["mode"], "sha256": record["sha256"],
                                "size": record["size"], "package": {"state": "NOT_QUERIED"}})
        # Recheck all seven captured file pins before the first host operation.
        collector.recheck_stage(stage, stage_pins)
        stage_ready = True
        for root in roots:
            collector.check()
            record = collector.observe(root["path"], main=root["id"] == "staged_launcher")
            if record["state"] == "found" and record["kind"] != "file":
                record.update(state="unknown", code="root_leaf_unsafe")
                collector.error("root_leaf_unsafe", root["path"])
                collector.traversal_complete = False
            if record["state"] == "found":
                if root["path"] not in collector.objects and len(collector.objects) >= selected["nodes"]:
                    collector.invalidate(root["path"], "node_budget")
                    collector.incomplete.append({"reason": "node_budget", "namespace": root["path"]})
                    collector.metadata_complete = False
                    continue
                collector.objects[root["path"]] = record["dynamicTags"]
                if root["path"].startswith("/usr/lib64/"):
                    collector.paths[root["path"]] = {"state": "object", "canonical": root["path"]}
                collector.expand(root["path"])
            else:
                collector.metadata_complete = False
        collector.metadata()
        collector.replay()
        collector.recheck_stage(stage, stage_pins)
    except (HostInventoryError, package.PackageError, OSError) as error:
        code = error.code if isinstance(error, (HostInventoryError, package.PackageError)) else "filesystem_unknown"
        collector.error(code)
        collector.metadata_complete = False
        collector.traversal_complete = False
        collector.incomplete.append({"reason": code})
        # A non-stage budget failure does not erase independently pinned roots.
        if not stage_ready or code.startswith("stage"):
            collector.objects.pop(str(stage / "bin/orla-launcher"), None)
    for record in stage_files:
        record["state"] = collector.observations[str(stage / record["path"])]["state"]
    graph_limits = {name: selected[name] for name in ("roots", "nodes", "edges", "aliasHops")}
    graph = resolve_catalog(roots, collector.objects, collector.paths, limits=graph_limits)
    observations = list(collector.observations.values())
    known_missing = [root["id"] for root in roots if collector.observations.get(root["path"], {}).get("state") == "absent"]
    unknown = graph["status"] == "unknown" or not collector.metadata_complete \
              or collector.incomplete or any(record["state"] == "unknown" for record in observations)
    status = "unknown" if unknown else "missing" if graph["status"] == "absent_in_catalog" else "ok"
    report = {"schema": SCHEMA, "target": package.TARGET, "channel": package.CHANNEL, "status": status,
              "stageFiles": stage_files, "roots": roots, "catalogGraph": graph, "observations": observations,
              "chains": collector.chains,
              "ancestors": [{"namespace": path, "pin": list(pin)} for path, pin in collector.ancestors.items()],
              "knownMissingRoots": known_missing,
              "metadataCoverage": "complete_for_observed_paths" if collector.metadata_complete else "unknown",
              "limitsConsumed": collector.used, "firstError": collector.first_error, "incomplete": collector.incomplete,
              "coverage": {"hostTraversal": "bounded_to_observed_catalog" if collector.traversal_complete else "unknown",
                           "loaderResolution": "UNRUN", "abiSelection": "UNRUN", "qmlImports": "UNRUN",
                           "pythonBuildProvenance": "UNRUN", "runtimeHealth": "UNRUN"}}
    if not _fits_evidence(report, selected["evidenceBytes"]):
        report = {"schema": SCHEMA, "target": package.TARGET, "channel": package.CHANNEL, "status": "unknown",
                  "truncated": True, "omittedFields": ["stageFiles", "roots", "catalogGraph", "observations", "chains", "ancestors"],
                  "firstError": {"code": (collector.first_error or {"code": "evidence_budget"})["code"]},
                  "incomplete": [{"reason": "evidence_budget"}], "metadataCoverage": "unknown",
                  "coverage": {"hostTraversal": "unknown", "loaderResolution": "UNRUN", "abiSelection": "UNRUN",
                               "qmlImports": "UNRUN", "pythonBuildProvenance": "UNRUN", "runtimeHealth": "UNRUN"}}
        if not _fits_evidence(report, selected["evidenceBytes"]):
            raise HostInventoryError("host_evidence_fallback")
    return report
