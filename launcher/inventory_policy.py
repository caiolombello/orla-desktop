"""Experimental pure finite-catalog dependency projection.

This validates supplied records and contexts, without observing the host or
claiming dynamic loader, ABI, filesystem, RPM or lifecycle qualification.
"""

from collections import deque
import posixpath
import re


SCHEMA = "orla-launcher-catalog-graph-0.1"
POLICY = "fedora44-usr-lib64-catalog-0.1"
DEFAULT_LIMITS = {"roots": 16, "nodes": 256, "edges": 4096, "aliasHops": 16}
_TAG_KEYS = {"type", "interpreter", "needed", "rpath", "runpath", "flags", "unsupportedMechanisms"}
_SONAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+~-]{0,254}\Z", re.ASCII)
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z", re.ASCII)


class PolicyError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _reject(code):
    raise PolicyError(code)


def _text(value):
    return type(value) is str and 0 < len(value) <= 4096 and all(32 <= ord(char) < 127 for char in value)


def _path(value):
    return (_text(value) and value.startswith("/") and not value.startswith("//")
            and posixpath.normpath(value) == value)


def _library_path(value):
    return _path(value) and value.startswith("/usr/lib64/")


def _validate(roots, objects, paths, limits):
    if type(roots) is not list or not 1 <= len(roots) <= 16:
        _reject("policy_roots")
    ids = set()
    for root in roots:
        if type(root) is not dict or set(root) != {"id", "path", "required"}:
            _reject("policy_roots")
        if type(root["id"]) is not str or _LABEL.fullmatch(root["id"]) is None \
                or root["id"] in ids or not _path(root["path"]) or type(root["required"]) is not bool:
            _reject("policy_roots")
        ids.add(root["id"])
    if not any(root["required"] for root in roots):
        _reject("policy_roots")
    root_paths = {root["path"] for root in roots}
    if type(objects) is not dict or len(objects) > 256:
        _reject("policy_objects")
    for path, tags in objects.items():
        if not _path(path) or (path not in root_paths and not _library_path(path)) \
                or type(tags) is not dict or set(tags) != _TAG_KEYS:
            _reject("policy_objects")
        if type(tags["type"]) is not str or tags["type"] not in ("executable", "shared_object") \
                or (tags["interpreter"] is not None and not _path(tags["interpreter"])):
            _reject("policy_objects")
        needed = tags["needed"]
        if type(needed) is not list or len(needed) > 256 \
                or any(type(name) is not str or _SONAME.fullmatch(name) is None for name in needed):
            _reject("policy_objects")
        for name in ("rpath", "runpath"):
            if type(tags[name]) is not list or len(tags[name]) > 1 or any(not _text(value) for value in tags[name]):
                _reject("policy_objects")
        for name, allowed in (("flags", {30, 0x6ffffffb}),
                              ("unsupportedMechanisms", {0x7fffffff, 0x7ffffffd, 0x6ffffefc, 0x6ffffefb})):
            values = tags[name]
            if type(values) is not list or len(values) > len(allowed):
                _reject("policy_objects")
            seen = set()
            for item in values:
                if type(item) is not dict or set(item) != {"tag", "value"} \
                        or type(item["tag"]) is not int or item["tag"] not in allowed or item["tag"] in seen \
                        or type(item["value"]) is not int or not 0 <= item["value"] < (1 << 64):
                    _reject("policy_objects")
                seen.add(item["tag"])
    if type(paths) is not dict or len(paths) > 4096:
        _reject("policy_paths")
    for path, item in paths.items():
        if not _library_path(path) or type(item) is not dict:
            _reject("policy_paths")
        state = item.get("state")
        if type(state) is not str:
            _reject("policy_paths")
        expected = {"state", "canonical"} if state == "object" else {"state", "target"} if state == "alias" else {"state"}
        if type(state) is not str or state not in ("object", "alias", "absent_in_catalog", "unknown") or set(item) != expected:
            _reject("policy_paths")
        if state == "object" and not _library_path(item["canonical"]):
            _reject("policy_paths")
        if state == "alias" and not _text(item["target"]):
            _reject("policy_paths")
    selected = dict(DEFAULT_LIMITS)
    if limits is not None:
        if type(limits) is not dict or not set(limits) <= set(DEFAULT_LIMITS):
            _reject("policy_limits")
        for name, value in limits.items():
            if type(value) is not int or not 1 <= value <= DEFAULT_LIMITS[name]:
                _reject("policy_limits")
            selected[name] = value
    return selected


def _canonical_consistent(path, paths):
    # Canonical identity cannot coexist with a contradictory explicit endpoint.
    # An omitted endpoint remains allowed: object data was supplied separately.
    item = paths.get(path)
    return item is None or (item["state"] == "object" and item["canonical"] == path)


def _candidate(candidate, objects, paths, alias_hops):
    current = candidate
    visited = set()
    hops = 0
    while True:
        if current in visited:
            return "unknown", None, ["alias_cycle"]
        visited.add(current)
        item = paths.get(current)
        if item is None:
            return "unknown", None, ["candidate_unprovided"]
        if item["state"] == "unknown":
            return "unknown", None, ["candidate_unknown"]
        if item["state"] == "absent_in_catalog":
            return "absent_in_catalog", None, ["candidate_absent_in_catalog"]
        if item["state"] == "object":
            target = item["canonical"]
            if not _canonical_consistent(target, paths):
                return "unknown", None, ["canonical_conflict"]
            if target not in objects:
                return "unknown", None, ["object_unprovided"]
            return "object", target, []
        if hops >= alias_hops:
            return "unknown", None, ["alias_hop_limit"]
        target = item["target"]
        current = posixpath.normpath(target if target.startswith("/") else
                                     posixpath.join(posixpath.dirname(current), target))
        if not _library_path(current):
            return "unknown", None, ["alias_escape"]
        hops += 1


def _blockers(tags):
    reasons = []
    if tags["rpath"]: reasons.append("own_rpath")
    if tags["runpath"]: reasons.append("own_runpath")
    if tags["unsupportedMechanisms"]: reasons.append("unsupported_mechanism")
    if any(item["value"] != 0 for item in tags["flags"]): reasons.append("nonzero_dynamic_flags")
    return reasons



def _inherited_contexts(root_path, objects, edges):
    # Each node has only two RPATH contexts: clean or inherited uncertainty.
    # Revisiting the blocked context reaches late-discovered shared descendants.
    outgoing = {}
    for edge in edges:
        outgoing.setdefault(edge["source"], []).append(edge)
    pending = deque([(root_path, False)])
    visited = set()
    inherited = set()
    while pending:
        source, blocked = pending.popleft()
        if (source, blocked) in visited:
            continue
        visited.add((source, blocked))
        if blocked:
            inherited.add(source)
        tags = objects.get(source)
        if tags is None:
            continue
        child_blocked = blocked or bool(tags["rpath"])
        for edge in outgoing.get(source, []):
            if edge["target"] is not None:
                pending.append((edge["target"], child_blocked))
    return inherited


def _frontier(root_id, reason, source, occurrence, candidate, target=None):
    return {"root": root_id, "reason": reason, "source": source,
            "occurrence": occurrence, "candidate": candidate, "target": target}


def _root_graph(root, objects, paths, limits, nodes, node_paths, edges, cache, incomplete):
    # Finish each required root before optional roots can spend remaining budgets.
    path = root["path"]
    if not _canonical_consistent(path, paths):
        incomplete.append(_frontier(root["id"], "canonical_conflict", None, None, path))
        return "unknown", [], ["canonical_conflict"]
    if path not in objects:
        return "unknown", [], ["root_unprovided"]
    if path not in node_paths:
        if len(nodes) >= limits["nodes"]:
            incomplete.append(_frontier(root["id"], "node_limit", None, None, path, path))
            return "unknown", [], ["node_limit"]
        node_paths.add(path)
        nodes.append({"path": path})
    pending = deque([path])
    visited = set()
    occurrences = []
    diagnostics = []
    state = "complete"
    while pending:
        source = pending.popleft()
        if source in visited:
            continue
        visited.add(source)
        tags = objects[source]
        own = _blockers(tags)
        if own:
            state = "unknown"
            diagnostics += [reason for reason in own if reason not in diagnostics]
        for occurrence, name in enumerate(tags["needed"]):
            key = (source, occurrence)
            candidate = "/usr/lib64/" + name
            if key not in cache:
                if len(edges) >= limits["edges"]:
                    frontier = _frontier(root["id"], "edge_limit", source, occurrence, candidate)
                    frontier["remainingOccurrences"] = len(tags["needed"]) - occurrence
                    incomplete.append(frontier)
                    state = "unknown"
                    if "edge_limit" not in diagnostics:
                        diagnostics.append("edge_limit")
                    break
                catalog_state, target, reasons = _candidate(candidate, objects, paths, limits["aliasHops"])
                edge = {"source": source, "occurrence": occurrence, "name": name,
                        "candidate": candidate, "target": target, "state": catalog_state,
                        "catalogState": catalog_state, "contexts": []}
                cache[key] = (edge, reasons)
                edges.append(edge)
            edge, reasons = cache[key]
            target = edge["target"]
            cut = []
            if target is not None and target not in node_paths:
                if len(nodes) >= limits["nodes"]:
                    incomplete.append(_frontier(root["id"], "node_limit", source, occurrence, candidate, target))
                    cut.append("node_limit")
                    state = "unknown"
                else:
                    node_paths.add(target)
                    nodes.append({"path": target})
            occurrences.append((edge, reasons, cut))
            if target is not None and not cut and target not in visited:
                pending.append(target)
    return state, occurrences, diagnostics


def _root_contexts(root, objects, state, occurrences, diagnostics):
    inherited = _inherited_contexts(root["path"], objects, [edge for edge, _reasons, _cut in occurrences])
    for edge, candidate_reasons, cut in occurrences:
        reasons = _blockers(objects[edge["source"]])
        if edge["source"] in inherited:
            reasons.append("inherited_rpath")
        reasons += candidate_reasons + cut
        diagnostics += [reason for reason in reasons if reason not in diagnostics]
        catalog_state = edge["catalogState"]
        effective = "unknown" if reasons and (catalog_state != "absent_in_catalog" or
                    any(reason != "candidate_absent_in_catalog" for reason in reasons)) else \
                    "absent_in_catalog" if catalog_state == "absent_in_catalog" else "complete"
        if effective == "unknown":
            state = "unknown"
        elif effective == "absent_in_catalog" and state != "unknown":
            state = "absent_in_catalog"
        edge["contexts"].append({"root": root["id"], "state": effective, "reasons": reasons})
    return state, diagnostics


def resolve_catalog(roots, objects, paths, *, limits=None):
    selected = _validate(roots, objects, paths, limits)
    if len(roots) > selected["roots"]:
        _reject("policy_roots")
    nodes, edges, incomplete = [], [], []
    node_paths, cache, results, diagnostics = set(), {}, {}, {}
    priority = [root for root in roots if root["required"]] + [root for root in roots if not root["required"]]
    for root in priority:
        state, occurrences, reasons = _root_graph(root, objects, paths, selected, nodes, node_paths, edges, cache, incomplete)
        state, reasons = _root_contexts(root, objects, state, occurrences, reasons)
        diagnostics[root["id"]] = {"root": root["id"], "reasons": reasons}
        results[root["id"]] = {"id": root["id"], "path": root["path"],
                              "required": root["required"], "status": state}
    required_states = {results[root["id"]]["status"] for root in roots if root["required"]}
    status = "unknown" if "unknown" in required_states else "absent_in_catalog" if "absent_in_catalog" in required_states \
             else "complete_for_supplied_catalog_policy"
    return {"schema": SCHEMA, "policy": POLICY, "status": status,
            "roots": [results[root["id"]] for root in roots],
            "nodes": nodes, "edges": edges, "incomplete": incomplete,
            "rootDiagnostics": [diagnostics[root["id"]] for root in roots],
            "coverage": {"actualHost": "UNRUN", "loader": "UNRUN", "abi": "UNRUN", "lifecycle": "UNRUN"}}
