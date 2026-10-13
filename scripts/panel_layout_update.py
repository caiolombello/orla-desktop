"""One strict CC-only revision; original apply authority remains immutable."""
from __future__ import annotations

import copy
import hashlib
import json
import re

if __package__:
    from . import panel_layout as layout
else:
    import panel_layout as layout

ENTRY = {"key": "control-center", "config": {"showOrlaMenu": False,
         "showApplicationName": False, "showControlCenter": True}}
PLAN_FIELDS = {"schemaVersion", "kind", "operation", "planId", "parent", "origin", "originPlan",
               "inventory", "owned", "baseline", "service", "serviceIdentity", "entry",
               "insertionIndex", "restoreCompatible"}
IMMUTABLE = ("schemaVersion", "transactionId", "plan", "before", "service", "serviceIdentity",
             "origin", "parent", "updatePlan", "updateBefore", "previousInventory",
             "activeInventory", "after", "owned", "restoreCompatible")


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise layout.LayoutError("invalid update reference digest")


def _metadata(value):
    layout._object(value, layout.CONFIG_FILES, "update baseline")
    for item in value.values():
        layout._object(item, ("exists", "mode", "sha256"), "update file metadata")
        if type(item["exists"]) is not bool: raise layout.LayoutError("invalid update file existence")
        if item["exists"] is True:
            layout._integer(item["mode"], 0, 0o777, "update file mode")
            _digest(item["sha256"])
        elif item != {"exists": False, "mode": None, "sha256": None}:
            raise layout.LayoutError("invalid update absent file")


def _reference(value, digest_key):
    layout._object(value, ("transactionId", digest_key), "update reference")
    if not isinstance(value["transactionId"], str) or not re.fullmatch(r"[0-9a-f]{64}-[0-9a-f]{16}", value["transactionId"]):
        raise layout.LayoutError("initial update requires a schema1 origin")
    _digest(value[digest_key])


def _identity(value, service):
    layout._object(value, ("unit", "executable", "argv", "target"), "update service identity")
    if (not isinstance(service, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}\.service", service)
            or value["unit"] != service or not isinstance(value["executable"], str)
            or not value["executable"].startswith("/") or value["executable"].split("/")[-1] != "plasmashell"
            or value["argv"] not in (value["executable"], value["executable"] + " --no-respawn")
            or not isinstance(value["target"], dict) or not isinstance(value["target"].get("configHome"), str)
            or not value["target"]["configHome"].startswith("/")):
        raise layout.LayoutError("invalid update target or service")


def validate_update_plan(plan):
    layout._object(plan, PLAN_FIELDS, "managed update plan")
    if (type(plan["schemaVersion"]) is not int or plan["schemaVersion"] != 1
            or plan["kind"] != "managed-panel-update" or plan["operation"] != "add-control-center"):
        raise layout.LayoutError("unsupported managed update")
    _digest(plan["planId"])
    payload = {key: value for key, value in plan.items() if key != "planId"}
    if layout._hash(payload) != plan["planId"]: raise layout.LayoutError("update plan changed")
    _reference(plan["parent"], "receiptSha256")
    _reference(plan["origin"], "applyReceiptSha256")
    if plan["parent"]["transactionId"] != plan["origin"]["transactionId"]:
        raise layout.LayoutError("only the first committed revision is supported")
    original = layout.validate_plan(plan["originPlan"])
    layout._managed_inventory(original, plan["owned"])
    inventory = layout.validate_inventory(plan["inventory"])
    layout._check_owned({"plan": original, "owned": plan["owned"]}, inventory)
    modules = [m for m in original["manifest"]["modules"] if m["enabled"]]
    keys = [m["key"] for m in modules]
    if "control-center" in keys or keys.count("tray") != 1 or keys.count("clock") != 1:
        raise layout.LayoutError("CC already selected or required modules absent")
    insertion = keys.index("tray") + 1
    if insertion >= len(keys) or keys[insertion] != "clock":
        raise layout.LayoutError("control-center requires adjacent tray and clock")
    layout._integer(plan["insertionIndex"], 1, 127, "update insertion index")
    if plan["insertionIndex"] != insertion: raise layout.LayoutError("update insertion changed")
    layout._object(plan["entry"], ("key", "config"), "update entry")
    layout._object(plan["entry"]["config"], ENTRY["config"], "update entry configuration")
    if plan["entry"]["key"] != ENTRY["key"] or any(plan["entry"]["config"][key] is not value for key, value in ENTRY["config"].items()):
        raise layout.LayoutError("update requires the exact CC-only entry")
    _metadata(plan["baseline"])
    _identity(plan["serviceIdentity"], plan["service"])
    if type(plan["restoreCompatible"]) is not bool: raise layout.LayoutError("invalid restore compatibility")
    if len(json.dumps(plan, ensure_ascii=True)) > 120000: raise layout.LayoutError("update plan exceeds size limit")
    return copy.deepcopy(plan)


def kconfig_groups(data):
    """Retain all keys/values; refuse syntax whose KConfig meaning is uncertain."""
    try: text = data.decode("utf-8", errors="strict")
    except UnicodeError as exc: raise layout.LayoutError("invalid KConfig encoding") from exc
    if "\x00" in text or text.startswith("\ufeff") or any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        raise layout.LayoutError("ambiguous KConfig text")
    groups = {(): {}}
    group = ()
    # KConfig splits physical lines on LF; Unicode separators remain value data.
    for line in text.split("\n"):
        if line.endswith("\r"): line = line[:-1]
        if not line or line.startswith("#"): continue
        if line.startswith("["):
            if not re.fullmatch(r"(?:\[[A-Za-z0-9_.:/ -]+\])+", line):
                raise layout.LayoutError("unsupported KConfig group syntax")
            group = tuple(re.findall(r"\[([^\[\]]+)\]", line))
            if any(name != name.strip() for name in group) or group in groups:
                raise layout.LayoutError("ambiguous or duplicate KConfig group")
            groups[group] = {}
            continue
        key, separator, value = line.partition("=")
        if (not separator or not re.fullmatch(r"[A-Za-z0-9_.:;/ -]+", key)
                or key != key.strip() or key in groups[group]):
            raise layout.LayoutError("ambiguous KConfig entry")
        groups[group][key] = value
    return groups


def _owned_group(name, group, panel_id):
    prefix = ("Containments", str(panel_id)) if name == layout.CONFIG_FILES[0] else ("PlasmaViews", "Panel " + str(panel_id))
    return group[:len(prefix)] == prefix


def _bank_groups(store, metadata, directory=None):
    _metadata(metadata)
    result = {}
    for name, info in metadata.items():
        if not info["exists"]:
            result[name] = {}
            continue
        path = (directory or store.config_home) / name
        store._safe_path(path)
        data = path.read_bytes()
        if len(data) > 16777216 or hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise layout.LayoutError("KConfig bank changed")
        result[name] = kconfig_groups(data)
    return result


def _compatible(store, metadata, original, panel_id):
    current = _bank_groups(store, metadata)
    old = _bank_groups(store, original["after"], store._directory(original) / "after")
    for name in layout.CONFIG_FILES:
        if any(metadata[name][key] != original["after"][name][key] for key in ("exists", "mode")): return False
        outside = lambda groups: {g: values for g, values in groups.items() if not _owned_group(name, g, panel_id)}
        if outside(current[name]) != outside(old[name]): return False
    return True


def _origin(store, reference, plan=None):
    _reference(reference, "applyReceiptSha256")
    holder = {"transactionId": reference["transactionId"]}
    path = store._directory(holder) / "apply-receipt.json"
    store._safe_path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference["applyReceiptSha256"]:
        raise layout.LayoutError("immutable update origin changed")
    original = layout.read_json(path, 262144)
    if original.get("schemaVersion") != 1 or original.get("phase") != "COMMITTED":
        raise layout.LayoutError("invalid immutable update origin")
    layout.validate_plan(original["plan"])
    layout._managed_inventory(original["plan"], original["owned"])
    if original["transactionId"] != reference["transactionId"] or plan is not None and original["plan"] != plan:
        raise layout.LayoutError("update original plan changed")
    store.verify_backup(original)
    _bank_groups(store, original["after"], store._directory(original) / "after")
    return original


def _parent(store, plan):
    reference = plan["parent"]
    path = store._directory({"transactionId": reference["transactionId"]}) / "receipt.json"
    store._safe_path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference["receiptSha256"]:
        raise layout.LayoutError("update parent journal changed")
    parent = layout.read_json(path, 262144)
    original = _origin(store, plan["origin"], plan["originPlan"])
    if (parent.get("schemaVersion") != 1 or parent.get("phase") != "COMMITTED"
            or any(parent.get(key) != original.get(key) for key in ("transactionId", "plan", "before", "after", "owned", "service", "serviceIdentity"))
            or parent["owned"] != plan["owned"] or parent["serviceIdentity"] != plan["serviceIdentity"]):
        raise layout.LayoutError("committed update parent changed")
    return parent, original


def _make_plan(parent, runtime, store, add):
    if add != "control-center" or parent.get("schemaVersion") != 1 or parent.get("phase") != "COMMITTED" or store.current() != parent:
        raise layout.LayoutError("update requires the current committed schema1 receipt")
    layout._guard_target(runtime, store, parent["serviceIdentity"])
    if parent["service"] != runtime.unit: raise layout.LayoutError("update service changed")
    origin_sha = store.verify_apply_receipt(parent)
    origin_ref = {"transactionId": parent["transactionId"], "applyReceiptSha256": origin_sha}
    original = _origin(store, origin_ref, parent["plan"])
    inventory = runtime.inspect(parent["plan"]["manifest"]["screen"]["connector"])
    baseline = store._capture(None)
    keys = [m["key"] for m in parent["plan"]["manifest"]["modules"] if m["enabled"]]
    if "tray" not in keys or "clock" not in keys:
        raise layout.LayoutError("control-center requires tray and clock")
    payload = {"schemaVersion": 1, "kind": "managed-panel-update", "operation": "add-control-center",
        "parent": {"transactionId": parent["transactionId"], "receiptSha256": hashlib.sha256((store._directory(parent)/"receipt.json").read_bytes()).hexdigest()},
        "origin": origin_ref, "originPlan": copy.deepcopy(parent["plan"]), "inventory": inventory,
        "owned": copy.deepcopy(parent["owned"]), "baseline": baseline, "service": runtime.unit,
        "serviceIdentity": copy.deepcopy(runtime.identity), "entry": copy.deepcopy(ENTRY),
        "insertionIndex": keys.index("tray") + 1,
        "restoreCompatible": _compatible(store, baseline, original, parent["owned"]["panelId"])}
    payload["planId"] = layout._hash(payload)
    return validate_update_plan(payload)


def build_update_plan(parent, runtime, store, *, add="control-center"):
    runtime.preflight()
    layout._guard_target(runtime, store)
    with store.lock(): return _make_plan(parent, runtime, store, add)


def _updated_inventory(plan, owned):
    layout._object(owned, ("panelId", "token", "screen", "height", "widgets", "nativeValidated"), "updated owned result")
    layout._integer(owned["panelId"], 1, 2147483647, "updated panel ID")
    layout._integer(owned["screen"], 0, 2147483647, "updated panel screen")
    layout._integer(owned["height"], 28, 64, "updated panel height")
    previous = plan["owned"]
    if any(owned[key] != previous[key] for key in ("panelId", "token", "screen", "height")) or owned["nativeValidated"] is not False:
        raise layout.LayoutError("updated panel identity changed")
    widgets = owned["widgets"]
    at = plan["insertionIndex"]
    if not isinstance(widgets, list) or len(widgets) != len(previous["widgets"]) + 1:
        raise layout.LayoutError("updated panel membership changed")
    new = widgets[at]
    layout._object(new, ("id", "type", "index"), "new CC widget")
    layout._integer(new["id"], 1, 2147483647, "new CC ID")
    existing_ids = {w["id"] for p in plan["inventory"]["panels"] for w in p["widgets"]}
    if new["id"] in existing_ids or new["type"] != layout.MODULE_IDS["control-center"]:
        raise layout.LayoutError("new CC identity is not new")
    old = widgets[:at] + widgets[at + 1:]
    if [(w["id"], w["type"]) for w in old] != [(w["id"], w["type"]) for w in previous["widgets"]]:
        raise layout.LayoutError("existing widget identity changed")
    for index, widget in enumerate(widgets):
        layout._object(widget, ("id", "type", "index"), "updated widget")
        layout._integer(widget["index"], 0, 127, "updated widget index")
        if widget["index"] != index: raise layout.LayoutError("updated intended order changed")
    expected = copy.deepcopy(plan["inventory"])
    next(p for p in expected["panels"] if p["id"] == owned["panelId"])["widgets"] = copy.deepcopy(widgets)
    return layout.validate_inventory(expected)


def _footprint(store, receipt, current, *, committed=False):
    before = receipt["updateBefore"]
    owned = receipt.get("owned")
    previous = _bank_groups(store, before, store._directory(receipt) / "update-before")
    actual = _bank_groups(store, current)
    if owned is None:
        if current != before: raise layout.LayoutError("uncertain update identity; retain both banks")
        return
    _updated_inventory(receipt["updatePlan"], owned)
    prefix = ("Containments", str(owned["panelId"]), "Applets", str(owned["widgets"][receipt["updatePlan"]["insertionIndex"]]["id"]))
    if any(g[:len(prefix)] == prefix for g in previous[layout.CONFIG_FILES[0]]):
        raise layout.LayoutError("new CC subtree existed before the update")
    marker = actual[layout.CONFIG_FILES[0]].get(prefix + ("Configuration", "OrlaManagedUpdate"))
    if marker != {"token": receipt["updatePlan"]["planId"]}:
        raise layout.LayoutError("CC update intent marker changed or absent")
    for name in layout.CONFIG_FILES:
        if any(current[name][key] != before[name][key] for key in ("exists", "mode")):
            raise layout.LayoutError("protected KConfig file metadata changed")
        def protected(groups):
            result = copy.deepcopy(groups)
            if name == layout.CONFIG_FILES[0]:
                result = {g: values for g, values in result.items() if g[:len(prefix)] != prefix}
                order = ("Containments", str(owned["panelId"]), "General")
                if order in result: result[order].pop("AppletOrder", None)
            return result
        if protected(previous[name]) != protected(actual[name]):
            raise layout.LayoutError("protected existing or foreign KConfig groups changed")
    if committed:
        cc = actual[layout.CONFIG_FILES[0]].get(prefix + ("Configuration", "General"))
        if cc != {k: "true" if v else "false" for k, v in ENTRY["config"].items()}:
            raise layout.LayoutError("CC configuration readback changed")
        if actual[layout.CONFIG_FILES[0]].get(prefix, {}).get("plugin") != "org.orla.bar":
            raise layout.LayoutError("CC persisted plugin identity changed")
        order = actual[layout.CONFIG_FILES[0]].get(("Containments", str(owned["panelId"]), "General"), {}).get("AppletOrder")
        if order != ";".join(str(w["id"]) for w in owned["widgets"]):
            raise layout.LayoutError("CC persisted order changed")


def verify_update_receipt(store, receipt):
    validate_revision(store, receipt)
    plan = validate_update_plan(receipt["updatePlan"])
    _parent(store, plan)
    path = store._directory(receipt) / "update-receipt.json"
    store._safe_path(path)
    original = layout.read_json(path, 524288)
    if original.get("phase") != "COMMITTED" or any(original.get(k) != receipt.get(k) for k in IMMUTABLE):
        raise layout.LayoutError("immutable update receipt changed")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if receipt.get("applyReceiptSha256", digest) != digest: raise layout.LayoutError("immutable update receipt digest changed")
    if (receipt["plan"] != plan["originPlan"] or receipt["previousInventory"] != plan["inventory"]
            or receipt["updateBefore"] != plan["baseline"] or receipt["parent"] != plan["parent"]
            or receipt["origin"] != plan["origin"] or receipt["serviceIdentity"] != plan["serviceIdentity"]
            or receipt["activeInventory"] != _updated_inventory(plan, receipt["owned"])):
        raise layout.LayoutError("update recovery projection changed")
    return digest


def save_update_receipt(store, receipt):
    validate_revision(store, receipt)
    data = json.dumps(receipt, sort_keys=True).encode()
    original = store._directory(receipt) / "update-receipt.json"
    if receipt["phase"] == "COMMITTED":
        if not original.exists(): store._atomic(original, data)
        verify_update_receipt(store, receipt)
    store._atomic(store._directory(receipt) / "receipt.json", data)
    store._atomic(store.state_home / "current.json", data)


def validate_revision(store, receipt):
    if type(receipt.get("schemaVersion")) is not int or receipt["schemaVersion"] != 2:
        raise layout.LayoutError("unsupported update receipt")
    plan = validate_update_plan(receipt["updatePlan"])
    _, original = _parent(store, plan)
    store._directory(receipt)
    if not receipt["transactionId"].startswith("u2-" + plan["planId"] + "-"):
        raise layout.LayoutError("update transaction and plan differ")
    expected = {"plan": plan["originPlan"], "before": original["before"], "service": plan["service"],
        "serviceIdentity": plan["serviceIdentity"], "origin": plan["origin"], "parent": plan["parent"],
        "updateBefore": plan["baseline"], "previousInventory": plan["inventory"],
        "restoreCompatible": plan["restoreCompatible"]}
    if any(receipt.get(k) != v for k, v in expected.items()): raise layout.LayoutError("update recovery inputs changed")
    if receipt.get("phase") not in {"PREPARED", "APPLYING", "COMMITTED", "RESTORING", "RECOVERY_REQUIRED", "ROLLED_BACK", "DISABLING", "DISABLED", "RESTORED"}:
        raise layout.LayoutError("invalid update lifecycle phase")
    _metadata(receipt["updateBefore"])
    if receipt.get("owned") is None:
        if receipt.get("activeInventory") is not None or receipt.get("after") is not None:
            raise layout.LayoutError("update capture lacks owned identity")
    elif receipt.get("activeInventory") != _updated_inventory(plan, receipt["owned"]):
        raise layout.LayoutError("updated active inventory changed")
    if receipt.get("after") is not None: _metadata(receipt["after"])
    return original


def _recover_identity(receipt, store, metadata):
    if metadata == receipt["updateBefore"]: return None
    plan = receipt["updatePlan"]
    if receipt.get("owned") is not None: return receipt["owned"]
    groups = _bank_groups(store, metadata)[layout.CONFIG_FILES[0]]
    old = _bank_groups(store, receipt["updateBefore"], store._directory(receipt)/"update-before")[layout.CONFIG_FILES[0]]
    prefix = ("Containments", str(plan["owned"]["panelId"]), "Applets")
    prior_ids = {w["id"] for p in plan["inventory"]["panels"] for w in p["widgets"]}
    candidates = []
    for group, values in groups.items():
        if len(group) != 4 or group[:3] != prefix or not re.fullmatch(r"[1-9][0-9]*", group[3]): continue
        widget_id = int(group[3])
        if widget_id in prior_ids or values.get("plugin") != "org.orla.bar": continue
        if any(g[:4] == group for g in old): raise layout.LayoutError("recovery candidate existed before update")
        if groups.get(group + ("Configuration", "OrlaManagedUpdate")) == {"token": plan["planId"]}:
            candidates.append(widget_id)
    if len(candidates) != 1: raise layout.LayoutError("uncertain CC identity; current and recovery banks retained")
    owned = copy.deepcopy(plan["owned"])
    owned["widgets"].insert(plan["insertionIndex"], {"id": candidates[0], "type": "org.orla.bar", "index": plan["insertionIndex"]})
    for index, widget in enumerate(owned["widgets"]): widget["index"] = index
    _updated_inventory(plan, owned)
    return owned


def _activate_parent(receipt, runtime, store):
    parent, _ = _parent(store, receipt["updatePlan"])
    store.verify_current(receipt["updateBefore"])
    layout._guard_target(runtime, store, receipt["serviceIdentity"])
    layout._inventory_match(receipt["previousInventory"], runtime.inspect(receipt["plan"]["manifest"]["screen"]["connector"]))
    store._atomic(store.state_home / "current.json", json.dumps(parent, sort_keys=True).encode())
    return parent


def rollback_update(receipt, runtime, store, clock, pause):
    validate_revision(store, receipt)
    store.verify_backup(receipt, snapshot="updateBefore")
    receipt["phase"] = "RESTORING"; receipt["recoveryIntent"] = "update"
    layout._stage(receipt, store, "RECOVERY_STOP")
    if not runtime.stopped(): runtime.stop()
    layout._stage(receipt, store, "RECOVERY_CAPTURE")
    store.capture_recovery(receipt)
    metadata = store._capture(None)
    owned = _recover_identity(receipt, store, metadata)
    proxy = dict(receipt, owned=owned)
    _footprint(store, proxy, metadata)
    # Stopped recovery must rebind the real target before any replacement.
    runtime.start(); runtime.preflight()
    layout._guard_target(runtime, store, receipt["serviceIdentity"])
    connector = receipt["plan"]["manifest"]["screen"]["connector"]
    actual = runtime.inspect(connector)
    if owned is None:
        layout._inventory_match(receipt["previousInventory"], actual)
    else:
        expected = _updated_inventory(receipt["updatePlan"], owned)
        if layout._owned_order_state(expected, actual, owned, allow_pending=False) not in ("exact", "dense"):
            raise layout.LayoutError("uncertain recovery inventory")
    runtime.stop()
    layout._guard_target(runtime, store, receipt["serviceIdentity"])
    store.capture_recovery(receipt)
    _footprint(store, proxy, store._capture(None))
    layout._stage(receipt, store, "RECOVERY_REPLACE")
    store.restore_before(receipt, snapshot="updateBefore")
    layout._stage(receipt, store, "RECOVERY_START")
    runtime.start(); runtime.preflight()
    layout._stage(receipt, store, "RECOVERY_VERIFY")
    _, deadline = layout._inspect_ready(receipt["previousInventory"], connector, runtime, store, receipt["serviceIdentity"], clock, pause)
    layout._readiness_check(deadline, clock)
    store.verify_current(receipt["updateBefore"])
    receipt["phase"] = "ROLLED_BACK"; receipt["stage"] = "RECOVERY_COMMIT"
    store.save(receipt)
    return _activate_parent(receipt, runtime, store)


def guard_original_recovery(store, receipt):
    original = validate_revision(store, receipt)
    store.verify_apply_receipt(receipt)
    prior = receipt.get("originalRestoreFrom")
    if prior not in (receipt["after"], receipt.get("disableAfter")):
        raise layout.LayoutError("original restore checkpoint changed")
    actual = store._capture(None)
    if any(actual[name] not in (prior[name], original["before"][name]) for name in layout.CONFIG_FILES):
        raise layout.LayoutError("later user data conflicts with interrupted original restore")


def _disable_footprint(store, before, directory, actual, panel_id):
    old = _bank_groups(store, before, directory)
    current = _bank_groups(store, actual)
    for name in layout.CONFIG_FILES:
        if any(before[name][key] != actual[name][key] for key in ("exists", "mode")):
            raise layout.LayoutError("foreign file metadata changed during disable")
        outside = lambda groups: {g: values for g, values in groups.items() if not _owned_group(name, g, panel_id)}
        if outside(old[name]) != outside(current[name]): raise layout.LayoutError("foreign configuration changed during disable")
        owned = lambda groups: {g: values for g, values in groups.items() if _owned_group(name, g, panel_id)}
        remaining = owned(current[name])
        if remaining and remaining != owned(old[name]):
            raise layout.LayoutError("remaining owned configuration changed during disable")


def rollback_disable(receipt, runtime, store, clock, pause):
    validate_revision(store, receipt)
    verify_update_receipt(store, receipt)
    store.verify_backup(receipt, snapshot="disableBefore")
    if not runtime.stopped(): runtime.stop()
    receipt["recoveryIntent"] = "disable"; receipt["phase"] = "RESTORING"
    store.capture_recovery(receipt)
    _disable_footprint(store, receipt["disableBefore"], store._directory(receipt)/"disable-before",
                   store._capture(None), receipt["owned"]["panelId"])
    runtime.start(); runtime.preflight()
    layout._guard_target(runtime, store, receipt["serviceIdentity"])
    actual = runtime.inspect(receipt["plan"]["manifest"]["screen"]["connector"])
    if actual not in (receipt["disableInventory"], layout._disabled_inventory(receipt)):
        raise layout.LayoutError("uncertain interrupted disable inventory")
    runtime.stop()
    layout._guard_target(runtime, store, receipt["serviceIdentity"])
    store.capture_recovery(receipt)
    _disable_footprint(store, receipt["disableBefore"], store._directory(receipt)/"disable-before",
                   store._capture(None), receipt["owned"]["panelId"])
    store.restore_before(receipt, snapshot="disableBefore")
    runtime.start(); runtime.preflight()
    layout._stage(receipt, store, "DISABLE_RECOVERY_VERIFY")
    _, deadline = layout._inspect_ready(receipt["disableInventory"], receipt["plan"]["manifest"]["screen"]["connector"],
                                      runtime, store, receipt["serviceIdentity"], clock, pause)
    layout._readiness_check(deadline, clock)
    receipt["phase"] = "COMMITTED"; receipt["operation"] = "update"
    receipt.pop("recoveryIntent", None)
    store.save(receipt)


def restore_update(receipt, runtime, store, *, recover=False, clock=None, pause=None):
    import time
    clock = time.monotonic if clock is None else clock
    pause = time.sleep if pause is None else pause
    original = validate_revision(store, receipt)
    store.verify_backup(receipt, snapshot="updateBefore")
    if receipt["serviceIdentity"]["target"]["configHome"] != str(store.config_home.resolve()):
        raise layout.LayoutError("update recovery target changed")
    current = store.current()
    parent, _ = _parent(store, receipt["updatePlan"])
    if receipt["phase"] == "ROLLED_BACK" and current == parent:
        runtime.preflight(allow_stopped=recover)
        if runtime.unit != receipt["service"]:
            raise layout.LayoutError("update recovery service changed")
        with store.lock():
            if store.current() != parent: raise layout.LayoutError("update parent changed before recovery")
            if runtime.stopped():
                if not recover: raise layout.LayoutError("stopped recovery requires explicit --recover")
                runtime.start(); runtime.preflight()
            return _activate_parent(receipt, runtime, store)
    if current != receipt: raise layout.LayoutError("selected update is not authoritative")
    interrupted_disable = receipt.get("operation") == "disable" and receipt.get("recoveryIntent") != "original" and receipt["phase"] not in ("COMMITTED", "DISABLED")
    original_restore = receipt.get("recoveryIntent") == "original"
    if receipt["phase"] not in ("COMMITTED", "DISABLED", "RESTORED") and not original_restore:
        if not recover: raise layout.LayoutError("interrupted update requires explicit --recover")
        runtime.preflight(allow_stopped=True)
        identity = receipt["serviceIdentity"]
        if any(runtime.identity.get(k) != identity[k] for k in ("unit", "executable", "argv")):
            raise layout.LayoutError("update recovery service changed")
        with store.lock():
            if store.current() != receipt: raise layout.LayoutError("update journal changed before recovery")
            if receipt["phase"] == "ROLLED_BACK":
                if runtime.stopped(): runtime.start(); runtime.preflight()
                return _activate_parent(receipt, runtime, store)
            try:
                if interrupted_disable:
                    rollback_disable(receipt, runtime, store, clock, pause)
                    return receipt
                return rollback_update(receipt, runtime, store, clock, pause)
            except (layout.LayoutError, OSError, ValueError, KeyError, TypeError) as exc:
                layout._failure(receipt, store, "recovery", exc)
                raise layout._failure_error(receipt, store, "update recovery refused; all banks retained",
                                            recovery_required=receipt["phase"] != "ROLLED_BACK") from exc
    verify_update_receipt(store, receipt)
    if receipt["phase"] in ("COMMITTED", "DISABLED"):
        latest = receipt["after"] if receipt["phase"] == "COMMITTED" else receipt["disableAfter"]
        store.verify_current(latest)
        if not _compatible(store, latest, original, receipt["owned"]["panelId"]):
            raise layout.LayoutError("foreign drift prevents whole-file original restore")
    elif original_restore:
        if not recover: raise layout.LayoutError("interrupted original restore requires explicit --recover")
        guard_original_recovery(store, receipt)
    return layout._restore_layout_v1(receipt, runtime, store, recover=recover, clock=clock, pause=pause)


def update_layout(plan, runtime, store, *, clock=None, pause=None):
    import secrets
    import time
    clock = time.monotonic if clock is None else clock
    pause = time.sleep if pause is None else pause
    plan = validate_update_plan(plan)
    runtime.preflight()
    layout._guard_target(runtime, store, plan["serviceIdentity"])
    with store.lock():
        current = store.current()
        if current and current.get("schemaVersion") == 2 and current.get("phase") == "COMMITTED" and current.get("updatePlan") == plan:
            verify_update_receipt(store, current)
            layout._inventory_match(current["activeInventory"], runtime.inspect(plan["originPlan"]["manifest"]["screen"]["connector"]))
            return current
        parent, original = _parent(store, plan)
        if current != parent or _make_plan(parent, runtime, store, "control-center") != plan:
            raise layout.LayoutError("reviewed update baseline changed")
        receipt = None
        try:
            runtime.stop()
            layout._guard_target(runtime, store, plan["serviceIdentity"])
            store.verify_current(plan["baseline"])
            prepared = {"schemaVersion": 2, "transactionId": "u2-" + plan["planId"] + "-" + secrets.token_hex(8),
                "plan": copy.deepcopy(plan["originPlan"]), "before": copy.deepcopy(original["before"]),
                "service": runtime.unit, "serviceIdentity": copy.deepcopy(runtime.identity),
                "origin": copy.deepcopy(plan["origin"]), "parent": copy.deepcopy(plan["parent"]),
                "updatePlan": copy.deepcopy(plan), "updateBefore": None,
                "previousInventory": copy.deepcopy(plan["inventory"]), "activeInventory": None,
                "after": None, "owned": None, "restoreCompatible": plan["restoreCompatible"],
                "operation": "update", "phase": "PREPARED", "stage": "BACKUP_PREPARED"}
            prepared["updateBefore"] = store._capture(store._directory(prepared) / "update-before")
            store.verify_backup(prepared, snapshot="updateBefore")
            validate_revision(store, prepared)
            receipt = prepared
            store.save(receipt)
            layout._stage(receipt, store, "RESTART_FOR_APPLY")
            runtime.start(); runtime.preflight()
            connector = plan["originPlan"]["manifest"]["screen"]["connector"]
            _, deadline = layout._inspect_ready(plan["inventory"], connector, runtime, store, plan["serviceIdentity"], clock, pause)
            receipt["phase"] = "APPLYING"
            layout._stage(receipt, store, "APPLY_SCRIPT")
            layout._readiness_check(deadline, clock)
            if isinstance(runtime, layout._NATIVE_RUNTIME_TYPE):
                owned = runtime.update_owned(plan, ready_deadline=deadline, clock=clock)
            else: owned = runtime.update_owned(plan)
            active = _updated_inventory(plan, owned)
            receipt["owned"] = owned
            receipt["activeInventory"] = active
            store.save(receipt)
            layout._stage(receipt, store, "STOP_FOR_ORDER")
            runtime.stop()
            layout._stage(receipt, store, "RESTART_FOR_ORDER")
            runtime.start(); runtime.preflight()
            layout._stage(receipt, store, "WAIT_OWNED_ORDER")
            layout._order_owned(receipt, receipt["activeInventory"], runtime, store, clock, pause)
            layout._stage(receipt, store, "STOP_AFTER_APPLY")
            runtime.stop()
            layout._guard_target(runtime, store, plan["serviceIdentity"])
            layout._stage(receipt, store, "CAPTURE_AFTER")
            current_files = store._capture(None)
            _footprint(store, receipt, current_files, committed=True)
            store.capture_after(receipt)
            layout._stage(receipt, store, "RESTART_AFTER_APPLY")
            runtime.start(); runtime.preflight()
            layout._stage(receipt, store, "VERIFY_OWNED")
            _, deadline = layout._inspect_ready(receipt["activeInventory"], connector, runtime, store, plan["serviceIdentity"], clock, pause)
            layout._readiness_check(deadline, clock)
            receipt["phase"] = "COMMITTED"; receipt["stage"] = "COMMIT"
            store.save(receipt)
            return receipt
        except (layout.LayoutError, OSError, ValueError, KeyError, TypeError) as exc:
            if receipt is None:
                if runtime.stopped(): runtime.start()
                raise layout.LayoutError("update refused before mutation") from exc
            layout._failure(receipt, store, "primary", exc)
            try: rollback_update(receipt, runtime, store, clock, pause)
            except (layout.LayoutError, OSError, ValueError, KeyError, TypeError) as recovery:
                layout._failure(receipt, store, "recovery", recovery)
                raise layout._failure_error(receipt, store, "update failed; explicit recovery required, banks retained",
                                            recovery_required=receipt["phase"] != "ROLLED_BACK") from exc
            raise layout.LayoutError("update failed; previous managed layout restored") from exc
