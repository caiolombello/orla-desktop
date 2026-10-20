"""Optional managed Plasma panel composition, separate from dock installation."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re

SUPPORTED_PLASMA = "6.7.5"
MODULE_IDS = {
    "menu": "org.orla.bar", "control-center": "org.orla.bar", "global-menu": "org.kde.plasma.appmenu",
    "spacer": "org.kde.plasma.panelspacer", "tray": "org.kde.plasma.systemtray",
    "clock": "org.kde.plasma.digitalclock",
}
CONTROL_IDS = {
    "network": "org.kde.plasma.networkmanagement", "bluetooth": "org.kde.plasma.bluetooth",
    "audio": "org.kde.plasma.volume", "battery": "org.kde.plasma.battery",
    "notifications": "org.kde.plasma.notifications",
}
CONFIG_TYPES = {
    "menu": {"showApplicationName": bool, "showMenuLabel": bool, "compactHeight": bool},
    "control-center": {"showOrlaMenu": bool, "showApplicationName": bool, "showControlCenter": bool, "compactHeight": bool},
    "global-menu": {"compactView": bool, "allScreens": bool},
    "spacer": {}, "tray": {"controls": list, "overflow": list},
    "clock": {"showDate": bool, "showLocalTimezone": bool},
}


FAILURE_CODES = {"LAYOUT_REFUSAL", "COMMAND_MISSING", "COMMAND_IO", "COMMAND_TIMEOUT", "COMMAND_EXIT",
                 "COMMAND_OUTPUT_LIMIT", "OWNER_REPLY_INVALID", "SERVICE_NOT_QUIESCENT", "PRIOR_PROCESS_PRESENT",
                 "TARGET_CHANGED", "INVENTORY_MISMATCH", "FILESYSTEM_FAILURE", "DATA_INVALID",
                 "SCRIPT_REPLY_INVALID", "PID_REPLY_INVALID", "SERVICE_CAPABILITY", "SERVICE_OWNER_MISMATCH",
                 "SHELL_MISMATCH", "PROCESS_BINDING_CHANGED", "TARGET_BINDING_INVALID", "READINESS_TIMEOUT"}
OPERATIONS = {"TRANSACTION", "UNIT_SHOW", "UNIT_START", "UNIT_STOP", "UNIT_RESET_FAILED", "BUS_OWNER", "BUS_PID",
              "SHELL_PROPERTY", "EVALUATE_SCRIPT", "VERSION"}
STAGES = {"BACKUP_PREPARED", "PREPARING_STOP", "RESTART_FOR_APPLY", "PREFLIGHT_AFTER_BACKUP", "INSPECT_AFTER_BACKUP",
          "APPLY_SCRIPT", "STOP_FOR_ORDER", "RESTART_FOR_ORDER", "WAIT_OWNED_ORDER", "REORDER_OWNED", "VERIFY_OWNED_ORDER",
          "STOP_AFTER_APPLY", "CAPTURE_AFTER", "RESTART_AFTER_APPLY", "VERIFY_OWNED", "COMMIT",
          "DISABLE_VERIFY_RESTART", "DISABLE_REMOVE", "DISABLE_CLEANUP_RESTART", "DISABLE_FINAL_STOP",
          "DISABLE_CAPTURE_FINAL", "DISABLE_FINAL_RESTART", "DISABLE_VERIFY_FINAL", "DISABLE_RECOVERY_VERIFY",
          "RESTORE_VERIFY_CURRENT", "RECOVERY_VERIFY", "RECOVERY_STOP", "RECOVERY_BIND", "RECOVERY_CAPTURE", "RECOVERY_REPLACE", "RECOVERY_START", "RECOVERY_COMMIT"}


class LayoutError(Exception):
    def __init__(self, message, *, code="LAYOUT_REFUSAL", operation="TRANSACTION", returncode=None, hashes=None):
        super().__init__(message)
        self.facts = {"code": code if code in FAILURE_CODES else "LAYOUT_REFUSAL",
                      "operation": operation if operation in OPERATIONS else "TRANSACTION",
                      "returncode": returncode if type(returncode) is int and -128 <= returncode <= 255 else None}
        if hashes is not None and set(hashes) == {"expectedSha256", "actualSha256"} and all(
                isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) for value in hashes.values()):
            self.facts.update(hashes)


def _stage(receipt, store, stage):
    if stage not in STAGES: raise LayoutError("invalid transaction stage")
    receipt["stage"] = stage
    store.save(receipt)


def _failure(receipt, store, kind, exc):
    if kind not in ("primary", "recovery"): raise LayoutError("invalid diagnostic kind")
    if isinstance(exc, LayoutError): facts = copy.deepcopy(exc.facts)
    else:
        facts = {"code": "FILESYSTEM_FAILURE" if isinstance(exc, OSError) else "DATA_INVALID",
                 "operation": "TRANSACTION", "returncode": None}
    facts["stage"] = receipt.get("stage") if receipt.get("stage") in STAGES else "BACKUP_PREPARED"
    receipt.setdefault("diagnostics", {})[kind] = facts
    # A recorder failure must not skip recovery. Mandatory stages/banks still
    # persist these in-memory facts and refuse before their guarded mutation.
    try: store.save(receipt)
    except (LayoutError, OSError, ValueError, KeyError, TypeError): return False
    return True


def _failure_error(receipt, store, message, *, recovery_required):
    if recovery_required: receipt["phase"] = "RECOVERY_REQUIRED"
    try:
        store.save(receipt)
    except (LayoutError, OSError, ValueError, KeyError, TypeError):
        error = LayoutError(message + "; layout storage unavailable, journal durability unconfirmed",
                            code="FILESYSTEM_FAILURE")
    else:
        error = LayoutError(message)
    error.diagnostics = copy.deepcopy(receipt.get("diagnostics", {}))
    return error


def _inventory_match(expected, actual):
    if expected != actual:
        hashes = {key: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                  for key, value in (("expectedSha256", expected), ("actualSha256", actual))}
        raise LayoutError("planned panel inventory changed", code="INVENTORY_MISMATCH", hashes=hashes)


# The native trace showed this one incomplete screen-assignment projection.
# Every other fact, including panel/widget order and ownership, stays exact.
READINESS_SECONDS = 8.0
READINESS_PAUSE = 0.5
READINESS_ATTEMPTS = 17


def _readiness_check(deadline, clock):
    if clock() >= deadline:
        raise LayoutError("panel startup readiness deadline expired", code="READINESS_TIMEOUT")


def _inspect_ready(expected, connector, runtime, store, identity, clock, pause):
    incomplete = copy.deepcopy(expected)
    incomplete["screenIds"] = []; incomplete["selectedScreen"] = None
    for panel in incomplete["panels"]: panel["screen"] = -1
    deadline = clock() + READINESS_SECONDS
    for attempt in range(READINESS_ATTEMPTS):
        _guard_target(runtime, store, identity)
        _readiness_check(deadline, clock)
        if isinstance(runtime, _NATIVE_RUNTIME_TYPE):
            actual = runtime.inspect(connector, ready_deadline=deadline, clock=clock)
        else:
            actual = runtime.inspect(connector)
        _guard_target(runtime, store, identity)
        _readiness_check(deadline, clock)
        if actual == expected: return actual, deadline
        if actual != incomplete: _inventory_match(expected, actual)
        if attempt + 1 == READINESS_ATTEMPTS:
            raise LayoutError("panel startup readiness attempts exhausted", code="READINESS_TIMEOUT")
        remaining = deadline - clock()
        if remaining <= 0: _readiness_check(deadline, clock)
        pause(min(READINESS_PAUSE, remaining))
    raise LayoutError("panel startup readiness attempts exhausted", code="READINESS_TIMEOUT")


def _object(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise LayoutError(f"invalid {name} fields")


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise LayoutError(f"invalid {name}")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def validate_manifest(data):
    _object(data, ("schemaVersion", "preset", "mode", "screen", "panel", "replacePanelIds",
                   "reuseWidgetIds", "modules"), "manifest")
    if type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
        raise LayoutError("unsupported manifest version")
    if data["preset"] != "mac-inspired-topbar" or data["mode"] not in ("dock-plus-bar", "dock-only"):
        raise LayoutError("unsupported preset or mode")
    _object(data["screen"], ("connector",), "screen")
    connector = data["screen"]["connector"]
    if not isinstance(connector, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", connector):
        raise LayoutError("select a literal monitor connector")
    panel = data["panel"]
    _object(panel, ("height", "location", "lengthMode", "floating", "opacity", "hiding"), "panel")
    _integer(panel["height"], 28, 64, "logical panel height")
    if (panel["location"] != "top" or panel["lengthMode"] != "fill"
            or type(panel["floating"]) is not bool or panel["opacity"] not in ("opaque", "translucent", "adaptive")
            or panel["hiding"] not in ("none", "autohide", "dodgewindows", "windowsgobelow")):
        raise LayoutError("unsupported panel appearance")
    ids = data["replacePanelIds"]
    if not isinstance(ids, list) or not 1 <= len(ids) <= 16 or len(ids) != len(set(map(str, ids))):
        raise LayoutError("select distinct panels to replace")
    for value in ids:
        _integer(value, 1, 2147483647, "replacement panel ID")
    modules = data["modules"]
    if not isinstance(modules, list) or not 1 <= len(modules) <= len(MODULE_IDS):
        raise LayoutError("invalid module selection")
    seen = set()
    for module in modules:
        _object(module, ("key", "enabled", "config"), "module")
        key = module["key"]
        if not isinstance(key, str) or key not in MODULE_IDS or key in seen:
            raise LayoutError("unknown or duplicate module")
        seen.add(key)
        if type(module["enabled"]) is not bool or not isinstance(module["config"], dict):
            raise LayoutError("invalid module visibility/configuration")
        for name, value in module["config"].items():
            if name not in CONFIG_TYPES[key] or type(value) is not CONFIG_TYPES[key][name]:
                raise LayoutError("unsupported module configuration")
            if key == "tray":
                if len(value) > len(CONTROL_IDS) or any(type(item) is not str or item not in CONTROL_IDS for item in value) or len(set(value)) != len(value):
                    raise LayoutError("unsupported or duplicate tray control")
        if key == "control-center" and any(module["config"].get(name) is not expected for name, expected in
                (("showOrlaMenu", False), ("showApplicationName", False), ("showControlCenter", True))):
            raise LayoutError("control-center requires a CC-only bar instance")
        if key == "tray" and not set(module["config"].get("overflow", [])).issubset(module["config"].get("controls", [])):
            raise LayoutError("overflow must refer to an enabled native control")
    enabled = {item["key"] for item in modules if item["enabled"]}
    if not enabled:
        raise LayoutError("enable a module or restore the previous layout")
    reuse = data["reuseWidgetIds"]
    if not isinstance(reuse, dict) or not set(reuse).issubset(enabled):
        raise LayoutError("reuse requires an enabled selected module")
    for value in reuse.values():
        _integer(value, 1, 2147483647, "reused widget ID")
    if len(set(reuse.values())) != len(reuse):
        raise LayoutError("a widget cannot fill two modules")
    return copy.deepcopy(data)


def validate_inventory(inventory, *, allow_uninitialized=False):
    _object(inventory, ("version", "screenIds", "selectedScreen", "knownWidgetTypes", "panels"), "inventory")
    if not isinstance(inventory["version"], str) or len(inventory["version"]) > 32:
        raise LayoutError("invalid Plasma version reply")
    ids = inventory["screenIds"]
    if not isinstance(ids, list) or len(ids) > 32:
        raise LayoutError("invalid screen inventory")
    for value in ids: _integer(value, 0, 2147483647, "screen ID")
    if len(set(ids)) != len(ids): raise LayoutError("duplicate screen IDs")
    screen = inventory["selectedScreen"]
    if screen is not None:
        _object(screen, ("id", "connector", "geometry"), "selected screen")
        _integer(screen["id"], 0, 2147483647, "selected screen ID")
        if not isinstance(screen["connector"], str) or len(screen["connector"]) > 128: raise LayoutError("invalid connector reply")
        _object(screen["geometry"], ("x", "y", "width", "height"), "screen geometry")
        for key,value in screen["geometry"].items():
            _integer(value, -1000000 if key in ("x", "y") else 1, 1000000, "screen geometry")
    types = inventory["knownWidgetTypes"]
    if not isinstance(types, list) or len(types) > 4096 or any(not isinstance(value, str) or len(value) > 256 for value in types):
        raise LayoutError("invalid installed widget inventory")
    panels = inventory["panels"]
    if not isinstance(panels, list) or len(panels) > 64: raise LayoutError("invalid panel inventory")
    panel_ids = set(); widget_ids = set()
    for panel in panels:
        _object(panel, ("id", "type", "screen", "height", "widgets", "marker"), "panel inventory")
        _integer(panel["id"], 1, 2147483647, "panel ID")
        _integer(panel["screen"], -1, 2147483647, "panel screen")
        _integer(panel["height"], 0, 1000000, "panel height")
        if panel["id"] in panel_ids: raise LayoutError("duplicate panel ID")
        panel_ids.add(panel["id"])
        if not isinstance(panel["type"], str) or len(panel["type"]) > 256: raise LayoutError("invalid panel type")
        _object(panel["marker"], ("token", "schemaVersion"), "ownership marker")
        if not isinstance(panel["marker"]["token"], str) or len(panel["marker"]["token"]) > 128: raise LayoutError("invalid ownership token")
        _integer(panel["marker"]["schemaVersion"], 0, 2147483647, "ownership schema")
        widgets = panel["widgets"]
        if not isinstance(widgets, list) or len(widgets) > 128: raise LayoutError("invalid widget inventory")
        for widget in widgets:
            _object(widget, ("id", "type", "index"), "widget inventory")
            _integer(widget["id"], 1, 2147483647, "widget ID")
            _integer(widget["index"], -1 if allow_uninitialized else 0, 127, "widget index")
            if widget["id"] in widget_ids: raise LayoutError("duplicate widget ID")
            widget_ids.add(widget["id"])
            if not isinstance(widget["type"], str) or len(widget["type"]) > 256: raise LayoutError("invalid widget type")
    return copy.deepcopy(inventory)


def build_plan(manifest, inventory):
    manifest = validate_manifest(manifest)
    inventory = validate_inventory(inventory)
    if manifest["mode"] == "dock-only":
        raise LayoutError("dock-only uses layout disable with the active receipt; dock is managed independently")
    if inventory.get("version") != SUPPORTED_PLASMA:
        raise LayoutError("panel composition requires Plasma 6.7.5")
    screen = inventory.get("selectedScreen")
    if not isinstance(screen, dict) or screen.get("id", -1) not in inventory.get("screenIds", []):
        raise LayoutError("selected connector is unavailable")
    if screen.get("connector") != manifest["screen"]["connector"] or screen.get("geometry", {}).get("height", 0) < manifest["panel"]["height"]:
        raise LayoutError("selected monitor changed or cannot fit the panel")
    required = {MODULE_IDS[m["key"]] for m in manifest["modules"] if m["enabled"]}
    for module in manifest["modules"]:
        if module["key"] == "tray" and module["enabled"]:
            required.update(CONTROL_IDS[key] for key in module["config"].get("controls", []))
    missing = required.difference(inventory.get("knownWidgetTypes", []))
    if missing:
        raise LayoutError("selected native widgets are unavailable: " + ", ".join(sorted(missing)))
    panels = {panel["id"]: panel for panel in inventory.get("panels", [])}
    selected = []
    for panel_id in manifest["replacePanelIds"]:
        panel = panels.get(panel_id)
        if panel is None or panel.get("type") != "org.kde.panel" or panel.get("screen") != screen["id"]:
            raise LayoutError("replacement panel ID/type/monitor changed")
        if any(widget["type"] == "org.caiodock.dock" for widget in panel["widgets"]):
            raise LayoutError("replacement would remove the independent dock")
        selected.append(copy.deepcopy(panel))
    for key, widget_id in manifest["reuseWidgetIds"].items():
        matches = [widget for panel in selected for widget in panel["widgets"] if widget["id"] == widget_id]
        if len(matches) != 1 or matches[0]["type"] != MODULE_IDS[key]:
            raise LayoutError("reused widget ID/type/origin changed")
    # Another tray left on this monitor would duplicate the presentation.
    if any(panel["id"] not in manifest["replacePanelIds"] and panel["screen"] == screen["id"]
           and any(widget["type"] == MODULE_IDS["tray"] for widget in panel["widgets"])
           for panel in panels.values()) and MODULE_IDS["tray"] in required:
        raise LayoutError("include the existing tray's panel in the reviewed replacement selection")
    payload = {"schemaVersion": 1, "manifest": manifest, "inventory": copy.deepcopy(inventory),
               "screen": copy.deepcopy(screen), "selectedPanels": selected}
    if len(json.dumps(payload, ensure_ascii=True)) > 120000:
        raise LayoutError("panel plan exceeds size limit")
    payload["planId"] = _hash(payload)
    return payload


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {"schemaVersion", "manifest", "inventory", "screen", "selectedPanels", "planId"}:
        raise LayoutError("invalid plan receipt")
    if build_plan(plan["manifest"], plan["inventory"]) != plan:
        raise LayoutError("plan receipt changed")
    return copy.deepcopy(plan)


def render_script(operation, *, plan=None, connector="", token="", panel_id=None, expected_inventory=None,
                  ordered_widgets=None, update_plan=None):
    if operation not in ("inspect", "apply", "remove-owned", "reorder-owned", "update-owned"):
        raise LayoutError("unsupported panel operation")
    if operation == "update-owned":
        update_plan = validate_update_plan(update_plan)
        connector = update_plan["originPlan"]["manifest"]["screen"]["connector"]
    elif operation == "apply":
        plan = validate_plan(plan)
    elif operation in ("remove-owned", "reorder-owned"):
        _integer(panel_id, 1, 2147483647, "managed panel ID")
        expected_inventory = validate_inventory(expected_inventory)
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token):
            raise LayoutError("invalid managed ownership token")
        if operation == "reorder-owned":
            matches = [panel for panel in expected_inventory["panels"] if panel["id"] == panel_id]
            if (len(matches) != 1 or matches[0]["type"] != "org.kde.panel"
                    or matches[0]["marker"] != {"token":token, "schemaVersion":1}
                    or expected_inventory["selectedScreen"] is None
                    or connector != expected_inventory["selectedScreen"]["connector"]
                    or matches[0]["screen"] != expected_inventory["selectedScreen"]["id"]):
                raise LayoutError("invalid owned reorder identity or monitor")
            current = matches[0]["widgets"]
            if not current or [widget["index"] for widget in current] != list(range(len(current))):
                raise LayoutError("owned reorder requires initialized dense indices")
            target = copy.deepcopy(expected_inventory)
            target_panel = next(panel for panel in target["panels"] if panel["id"] == panel_id)
            target_panel["widgets"] = ordered_widgets
            validate_inventory(target)
            if ([widget["index"] for widget in ordered_widgets] != list(range(len(current)))
                    or sorted((widget["id"],widget["type"]) for widget in current)
                    != sorted((widget["id"],widget["type"]) for widget in ordered_widgets)):
                raise LayoutError("owned reorder membership or intended indices changed")
            ordered_widgets = copy.deepcopy(ordered_widgets)
    elif not isinstance(connector, str) or connector and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", connector):
        raise LayoutError("invalid monitor connector")
    request = {"operation": operation, "plan": plan, "connector": connector,
               "token": token, "panelId": panel_id, "expectedInventory":expected_inventory, "orderedWidgets":ordered_widgets}
    if operation == "update-owned":
        request = {"operation": operation, "updatePlan": update_plan, "connector": connector}
    encoded = json.dumps(request, ensure_ascii=True, separators=(",", ":"))
    if len(encoded) > 131072:
        raise LayoutError("panel request exceeds size limit")
    template = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    return template.replace("__ORLA_REQUEST__", encoded)

# Native operations are explicit argv calls. Tests inject the command runner;
# constructing this adapter never queries the session or changes configuration.
class NativeRuntime:
    def __init__(self, unit, *, runner=None, locate=None, process_reader=None, process_absent=None):
        import shutil
        import subprocess
        if not isinstance(unit, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}\.service", unit):
            raise LayoutError("select a literal current-user Plasma service name")
        self.unit = unit
        self.runner = runner or subprocess.run
        self.locate = locate or shutil.which
        self.executables = {}
        self.identity = None
        self.process_reader = process_reader or self._read_process
        self.live_process = None
        self.last_process = None
        self.quiescent_state = None
        self.quiescent_result = None; self.quiescent_restarts = None
        self.start_limit_recovery = None
        self.process_absent = process_absent or self._process_absent

    def _command(self, tool, arguments, timeout=10):
        import subprocess
        executable = self.executables.get(tool) or self.locate(tool)
        operation = "VERSION"
        if tool == "systemctl":
            operation = ("UNIT_SHOW" if "show" in arguments else "UNIT_STOP" if "stop" in arguments
                         else "UNIT_RESET_FAILED" if "reset-failed" in arguments else "UNIT_START")
        elif tool == "gdbus":
            method = arguments[arguments.index("--method") + 1] if "--method" in arguments else ""
            operation = {"org.freedesktop.DBus.NameHasOwner":"BUS_OWNER", "org.freedesktop.DBus.GetConnectionUnixProcessID":"BUS_PID",
                         "org.freedesktop.DBus.Properties.Get":"SHELL_PROPERTY", "org.kde.PlasmaShell.evaluateScript":"EVALUATE_SCRIPT"}.get(method, "TRANSACTION")
        if not executable:
            raise LayoutError(f"required layout tool unavailable: {tool}", code="COMMAND_MISSING", operation=operation)
        self.executables[tool] = executable
        try:
            result = self.runner([executable, *arguments], capture_output=True, text=True,
                                 timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            code = "COMMAND_TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "COMMAND_IO"
            raise LayoutError(f"layout command failed or timed out: {tool}", code=code, operation=operation) from exc
        if result.returncode:
            raise LayoutError(f"layout command failed: {tool}", code="COMMAND_EXIT", operation=operation, returncode=result.returncode)
        if len(result.stdout) > 1048576:
            raise LayoutError(f"layout command output exceeds limit: {tool}", code="COMMAND_OUTPUT_LIMIT", operation=operation)
        return result.stdout.strip()

    def _bus_pid(self):
        output = self._command("gdbus", ["call", "--session", "--timeout", "8", "--dest", "org.freedesktop.DBus",
            "--object-path", "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.GetConnectionUnixProcessID",
            "org.kde.plasmashell"])
        match = re.fullmatch(r"\(uint32 ([1-9][0-9]{0,9}),\)", output)
        if not match:
            raise LayoutError("cannot bind Plasma service to its session bus process", code="PID_REPLY_INVALID", operation="BUS_PID")
        return int(match[1])

    def _has_bus_owner(self):
        output = self._command("gdbus", ["call", "--session", "--timeout", "8", "--dest", "org.freedesktop.DBus",
            "--object-path", "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.NameHasOwner",
            "org.kde.plasmashell"])
        if output not in ("(true,)", "(false,)"):
            raise LayoutError("invalid Plasma bus-owner reply", code="OWNER_REPLY_INVALID", operation="BUS_OWNER")
        return output == "(true,)"

    def _service(self, active, *, rate_result=None):
        properties = ("LoadState", "ActiveState", "MainPID", "Type", "BusName", "ExecStart",
                      "CanStart", "CanStop", "RefuseManualStart", "RefuseManualStop", "Result", "NRestarts")
        output = self._command("systemctl", ["--user", "show", self.unit,
            "--property=" + ",".join(properties)])
        values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
        if (values.get("LoadState") != "loaded" or values.get("Type") != "dbus"
                or values.get("BusName") != "org.kde.plasmashell"
                or values.get("CanStart") != "yes" or values.get("CanStop") != "yes"
                or values.get("RefuseManualStart") != "no" or values.get("RefuseManualStop") != "no"):
            raise LayoutError("selected service lacks the verified Plasma lifecycle capability", code="SERVICE_CAPABILITY", operation="UNIT_SHOW")
        executable = re.search(r"(?:^|[ {;])path=([^ ;}]+)", values.get("ExecStart", ""))
        if not executable or not Path(executable[1]).is_absolute() or Path(executable[1]).name != "plasmashell":
            raise LayoutError("selected service does not execute Plasma shell")
        arguments = re.search(r"argv\[\]=([^;}]+)", values.get("ExecStart", ""))
        argv = arguments[1].strip() if arguments else ""
        if argv not in (executable[1], executable[1] + " --no-respawn"):
            raise LayoutError("selected Plasma service arguments are not reviewed")
        identity = {"unit": self.unit, "executable": executable[1], "argv": argv}
        if self.identity is not None and any(self.identity.get(key) != value for key, value in identity.items()):
            raise LayoutError("selected Plasma service definition changed")
        if active:
            if values.get("ActiveState") != "active" or not values.get("MainPID", "").isdigit():
                raise LayoutError("selected service does not own the current Plasma bus process", code="SERVICE_OWNER_MISMATCH", operation="UNIT_SHOW")
            pid = int(values["MainPID"])
            if pid != self._bus_pid():
                raise LayoutError("selected service does not own the current Plasma bus process", code="SERVICE_OWNER_MISMATCH", operation="UNIT_SHOW")
            target, process = self._live_target(pid)
            if self.identity is not None and "target" in self.identity and self.identity["target"] != target:
                raise LayoutError("selected Plasma configuration target changed", code="TARGET_CHANGED", operation="SHELL_PROPERTY")
            identity["target"] = target
            self.live_process = process
            self.last_process = copy.deepcopy(process)
            self.quiescent_state = None
            self.quiescent_result = None; self.quiescent_restarts = None
        else:
            if values.get("ActiveState") not in ("inactive", "failed") or values.get("MainPID") != "0":
                raise LayoutError("selected Plasma service is not quiescent", code="SERVICE_NOT_QUIESCENT", operation="UNIT_SHOW")
            if self._has_bus_owner():
                raise LayoutError("another process owns the Plasma bus name", code="SERVICE_NOT_QUIESCENT", operation="BUS_OWNER")
            if self.last_process is not None and not self.process_absent(self.last_process["pid"]):
                raise LayoutError("previous verified Plasma process is still present", code="PRIOR_PROCESS_PRESENT", operation="UNIT_SHOW")
            if rate_result is not None and (values.get("Result") != rate_result or values.get("NRestarts") != "0"):
                raise LayoutError("selected service start-limit state is not verified", code="SERVICE_NOT_QUIESCENT", operation="UNIT_SHOW")
            self.quiescent_state = values["ActiveState"]
            self.quiescent_result = values.get("Result"); self.quiescent_restarts = values.get("NRestarts")
            if self.identity is not None and "target" in self.identity:
                identity["target"] = self.identity["target"]
            self.live_process = None
        self.identity = identity
        return executable[1]

    @staticmethod
    def _process_absent(pid):
        import stat
        root = Path("/proc")
        def root_available():
            try: return stat.S_ISDIR(root.stat().st_mode)
            except OSError: return False
        if not root_available():
            raise LayoutError("process identity filesystem is unavailable", code="SERVICE_NOT_QUIESCENT", operation="UNIT_SHOW")
        try:
            (root / str(pid)).stat()
        except FileNotFoundError:
            if not root_available():
                raise LayoutError("process identity filesystem changed", code="SERVICE_NOT_QUIESCENT", operation="UNIT_SHOW")
            return True
        except OSError as exc:
            raise LayoutError("cannot verify previous Plasma process absence", code="SERVICE_NOT_QUIESCENT", operation="UNIT_SHOW") from exc
        return False

    @staticmethod
    def _read_process(pid):
        # Never expose or persist the raw environment; only these path fields leave this reader.
        import os
        directory = Path("/proc") / str(pid)
        def identity():
            uid = directory.stat().st_uid
            with (directory / "stat").open("rb") as stream:
                data = stream.read(8193)
            if len(data) > 8192: raise LayoutError("Plasma process identity exceeds limit")
            fields = data.rsplit(b")", 1)[1].split()
            return uid, int(fields[19])  # field22, after pid and parenthesized comm
        try:
            before = identity()
            if before[0] != os.getuid(): raise LayoutError("Plasma process belongs to another user")
            with (directory / "environ").open("rb") as stream:
                data = stream.read(1048577)
            if len(data) > 1048576: raise LayoutError("Plasma environment exceeds limit")
            paths = {}
            for entry in data.split(b"\0"):
                key, separator, value = entry.partition(b"=")
                if separator and key in (b"HOME", b"XDG_CONFIG_HOME"):
                    if key in paths: raise LayoutError("ambiguous Plasma path environment")
                    paths[key] = value.decode("utf-8", errors="strict")
            if identity() != before: raise LayoutError("Plasma process identity changed during binding")
            return {"uid": before[0], "startTick": before[1], "home": paths.get(b"HOME", ""),
                    "xdgConfigHome": paths.get(b"XDG_CONFIG_HOME", "")}
        except (OSError, ValueError, IndexError, UnicodeError) as exc:
            raise LayoutError("cannot safely bind the Plasma configuration process") from exc

    def _live_target(self, pid):
        import os
        before = self.process_reader(pid)
        output = self._command("gdbus", ["call", "--session", "--timeout", "8", "--dest", "org.kde.plasmashell",
            "--object-path", "/PlasmaShell", "--method", "org.freedesktop.DBus.Properties.Get",
            "org.kde.PlasmaShell", "shell"])
        if not re.fullmatch(r"\(<\s*'org\.kde\.plasma\.desktop'\s*>,\)", output):
            raise LayoutError("managed layout requires the verified desktop shell", code="SHELL_MISMATCH", operation="SHELL_PROPERTY")
        after = self.process_reader(pid)
        service_pid = self._command("systemctl", ["--user", "show", self.unit, "--property=MainPID,ActiveState"])
        values = dict(line.split("=", 1) for line in service_pid.splitlines() if "=" in line)
        if (before != after or pid != self._bus_pid() or values.get("MainPID") != str(pid)
                or values.get("ActiveState") != "active"):
            raise LayoutError("Plasma process identity changed during target binding", code="PROCESS_BINDING_CHANGED", operation="BUS_PID")
        if (not isinstance(before, dict) or set(before) != {"uid", "startTick", "home", "xdgConfigHome"}
                or type(before["uid"]) is not int or before["uid"] != os.getuid()
                or type(before["startTick"]) is not int or before["startTick"] < 1):
            raise LayoutError("invalid same-user Plasma process binding", code="TARGET_BINDING_INVALID", operation="SHELL_PROPERTY")
        home, config = before["home"], before["xdgConfigHome"]
        if (not isinstance(home, str) or not isinstance(config, str) or len(home) > 4096 or len(config) > 4096
                or any(ord(char) < 32 for char in home + config) or not home.startswith("/")):
            raise LayoutError("invalid Plasma configuration path environment", code="TARGET_BINDING_INVALID", operation="SHELL_PROPERTY")
        # Qt6.11.2 ignores a relative/empty XDG_CONFIG_HOME, using HOME/.config.
        root = config if config.startswith("/") else str(Path(home) / ".config")
        facts = {"uid": before["uid"], "home": home, "xdgConfigHome": config,
                 "configHome": str(Path(root).resolve()), "shell": "org.kde.plasma.desktop"}
        facts["digest"] = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
        return facts, {"pid": pid, "startTick": before["startTick"]}

    def preflight(self, *, allow_stopped=False):
        for name in ("gdbus", "systemctl"):
            if not self.locate(name): raise LayoutError(f"required layout tool unavailable: {name}")
        try:
            executable = self._service(True)
        except LayoutError:
            if not allow_stopped: raise
            executable = self._service(False)
            if self._has_bus_owner(): raise LayoutError("another process owns the Plasma bus name")
        version = self._command(executable, ["--version"])
        if not re.search(r"(?:Plasma|plasmashell)\s+6\.7\.5(?:\s|$)", version):
            raise LayoutError("panel composition requires Plasma 6.7.5")

    def stop(self):
        self._service(True)
        self._command("systemctl", ["--user", "stop", self.unit], timeout=45)
        self._service(False)
        if self._has_bus_owner(): raise LayoutError("another process owns the Plasma bus name")

    def start(self):
        self._service(False)
        identity = copy.deepcopy(self.identity)
        eligible = (self.last_process is not None and self.quiescent_state == "inactive" and self.quiescent_result == "success"
                    and self.quiescent_restarts == "0")
        self.start_limit_recovery = None
        if self._has_bus_owner(): raise LayoutError("another process owns the Plasma bus name")
        try:
            self._command("systemctl", ["--user", "start", self.unit], timeout=45)
        except LayoutError as initial:
            if not eligible or initial.facts["code"] != "COMMAND_EXIT" or initial.facts["operation"] != "UNIT_START": raise
            # The initial finite error facts precede clearing transient rate state.
            self.start_limit_recovery = {"initialFailure":copy.deepcopy(initial.facts),
                                         "baselineResult":"success", "baselineNRestarts":0,
                                         "resetAttempted":False, "retryAttempted":False, "completed":False}
            try:
                self._service(False, rate_result="start-limit-hit")
                if self.identity != identity: raise LayoutError("selected service start-limit identity changed")
                self.start_limit_recovery.update(observedResult="start-limit-hit", observedNRestarts=0, resetAttempted=True)
                self._command("systemctl", ["--user", "reset-failed", self.unit])
                self._service(False, rate_result="success")
                if self.identity != identity or self.quiescent_state != "inactive":
                    raise LayoutError("selected service changed after named rate reset")
                self.start_limit_recovery["retryAttempted"] = True
                self._command("systemctl", ["--user", "start", self.unit], timeout=45)
                self._service(True)
                self.start_limit_recovery["completed"] = True
                return
            except LayoutError as recovery:
                self.start_limit_recovery["recoveryFailure"] = copy.deepcopy(recovery.facts)
                raise initial from recovery
        self._service(True)

    def stopped(self):
        try:
            self._service(False)
            return not self._has_bus_owner()
        except LayoutError:
            return False

    def _script(self, source, *, ready_deadline=None, clock=None):
        self._service(True)
        import ast
        # Admission guard after binding; existing in-flight commands keep their
        # own timeouts. This is not a hard wall-clock completion guarantee.
        if ready_deadline is not None: _readiness_check(ready_deadline, clock)
        output = self._command("gdbus", ["call", "--session", "--timeout", "8", "--dest", "org.kde.plasmashell",
            "--object-path", "/PlasmaShell", "--method", "org.kde.PlasmaShell.evaluateScript", source])
        try:
            result = ast.literal_eval(output)
            if not isinstance(result, tuple) or len(result) != 1 or not isinstance(result[0], str): raise ValueError()
            value = json.loads(result[0])
            if not isinstance(value, dict): raise ValueError()
            return value
        except (ValueError, SyntaxError, TypeError) as exc:
            raise LayoutError("invalid structured Plasma script reply", code="SCRIPT_REPLY_INVALID", operation="EVALUATE_SCRIPT") from exc

    def inspect(self, connector="", *, allow_uninitialized=False, ready_deadline=None, clock=None):
        return validate_inventory(self._script(render_script("inspect", connector=connector),
            ready_deadline=ready_deadline, clock=clock), allow_uninitialized=allow_uninitialized)

    def apply(self, plan, *, ready_deadline=None, clock=None):
        return self._script(render_script("apply", plan=plan), ready_deadline=ready_deadline, clock=clock)

    def update_owned(self, plan, *, ready_deadline=None, clock=None):
        return self._script(render_script("update-owned", update_plan=plan), ready_deadline=ready_deadline, clock=clock)

    def reorder_owned(self, panel_id, token, expected_inventory, ordered_widgets, *, ready_deadline=None, clock=None):
        return self._script(render_script("reorder-owned", panel_id=panel_id, token=token,
            connector=expected_inventory["selectedScreen"]["connector"], expected_inventory=expected_inventory,
            ordered_widgets=ordered_widgets), ready_deadline=ready_deadline, clock=clock)

    def remove_owned(self, panel_id, token, expected_inventory, *, ready_deadline=None, clock=None):
        return self._script(render_script("remove-owned", panel_id=panel_id, token=token,
            connector=expected_inventory["selectedScreen"]["connector"], expected_inventory=expected_inventory),
            ready_deadline=ready_deadline, clock=clock)

# Preserve the adapter type when callers inject the CLI constructor.
_NATIVE_RUNTIME_TYPE = NativeRuntime

CONFIG_FILES = ("plasma-org.kde.plasma.desktop-appletsrc", "plasmashellrc")


class FileStore:
    def __init__(self, config_home, state_home):
        self.config_home = Path(config_home)
        self.state_home = Path(state_home)
        if not self.config_home.is_absolute() or not self.state_home.is_absolute():
            raise LayoutError("layout configuration/state homes must be absolute")

    @staticmethod
    def _safe_path(path):
        for item in (path, *path.parents):
            if item.is_symlink(): raise LayoutError("layout storage/configuration symlinks are not supported")
        if path.exists() and not path.is_file(): raise LayoutError("layout storage requires regular files")

    @staticmethod
    def _atomic(path, data, mode=0o600):
        import os
        import tempfile
        FileStore._safe_path(path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".orla-write-", dir=path.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def _capture(self, directory):
        import stat
        result = {}
        for name in CONFIG_FILES:
            path = self.config_home / name
            self._safe_path(path)
            if not path.exists():
                result[name] = {"exists": False, "mode": None, "sha256": None}
                continue
            if path.stat().st_size > 16777216: raise LayoutError("panel configuration exceeds backup size limit")
            data = path.read_bytes()
            metadata = {"exists": True, "mode": stat.S_IMODE(path.stat().st_mode),
                        "sha256": hashlib.sha256(data).hexdigest()}
            if directory is not None: self._atomic(directory / name, data)
            result[name] = metadata
        return result

    def current(self):
        path = self.state_home / "current.json"
        self._safe_path(path)
        if not path.exists(): return None
        pointer = _read_layout_receipt(path)
        # The per-transaction journal is authoritative; current.json only selects it.
        journal = read_json(self._directory(pointer) / "receipt.json", 524288 if pointer["schemaVersion"] == 2 else 262144)
        if journal.get("transactionId") != pointer.get("transactionId"):
            raise LayoutError("current transaction journal identity changed")
        if type(journal.get("schemaVersion")) is not int or journal["schemaVersion"] != pointer["schemaVersion"]:
            raise LayoutError("current layout journal version changed")
        return journal

    def save(self, receipt):
        if receipt.get("schemaVersion") == 2:
            return save_update_receipt(self, receipt)
        data = json.dumps(receipt, sort_keys=True).encode()
        original = self._directory(receipt) / "apply-receipt.json"
        if receipt["phase"] == "COMMITTED":
            if not original.exists(): self._atomic(original, data)
            self.verify_apply_receipt(receipt)
        # Required immutable artifacts precede the authoritative phase publication.
        self._atomic(self._directory(receipt) / "receipt.json", data)
        self._atomic(self.state_home / "current.json", data)

    def _directory(self, receipt):
        transaction = receipt.get("transactionId", "")
        version = receipt.get("schemaVersion", 1)
        if type(version) is not int or version not in (1, 2): raise LayoutError("unsupported layout receipt version")
        if receipt.get("schemaVersion") == 2:
            if not isinstance(transaction, str) or not re.fullmatch(r"u2-[0-9a-f]{64}-[0-9a-f]{16}", transaction):
                raise LayoutError("invalid managed update transaction identity")
            return self.state_home / transaction
        if not re.fullmatch(r"[0-9a-f]{64}-[0-9a-f]{16}", transaction):
            raise LayoutError("invalid layout transaction identity")
        return self.state_home / transaction

    def prepare(self, plan, unit, identity):
        import secrets
        receipt = {"schemaVersion": 1, "transactionId": plan["planId"] + "-" + secrets.token_hex(8),
                   "plan": copy.deepcopy(plan), "service": unit, "serviceIdentity": copy.deepcopy(identity), "operation":"apply", "phase": "PREPARED", "stage":"BACKUP_PREPARED",
                   "before": None, "after": None, "owned": None}
        receipt["before"] = self._capture(self._directory(receipt) / "before")
        self.save(receipt)
        return receipt

    def capture_after(self, receipt):
        receipt["after"] = self._capture(self._directory(receipt) / "after")
        self.save(receipt)

    def capture_recovery(self, receipt):
        import secrets
        attempt = secrets.token_hex(16)
        directory = self._directory(receipt) / ("recovery-" + attempt)
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        point = {"attempt": attempt, "complete": False, "files": None}
        receipt.setdefault("recoveryPoints", []).append(point)
        self.save(receipt)  # Preserve incomplete-attempt provenance before capture.
        files = self._capture(directory)
        for name, metadata in files.items():
            if metadata["exists"] and hashlib.sha256((directory / name).read_bytes()).hexdigest() != metadata["sha256"]:
                raise LayoutError("new recovery bank verification failed")
        complete = {"attempt": attempt, "complete": True, "files": files}
        self._atomic(directory / "metadata.json", json.dumps(complete, sort_keys=True).encode())
        point.update(complete)
        self.save(receipt)  # Complete, verified bank is durable before replacement.

    def verify_current(self, expected):
        if self._capture(None) != expected:
            raise LayoutError("layout configuration changed; original and current layouts retained")

    def verify_apply_receipt(self, receipt):
        if receipt.get("schemaVersion") == 2:
            return verify_update_receipt(self, receipt)
        path = self._directory(receipt) / "apply-receipt.json"
        self._safe_path(path)
        original = read_json(path, 262144)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if (original.get("phase") != "COMMITTED" or original.get("plan") != receipt["plan"]
                or original.get("before") != receipt["before"] or original.get("after") != receipt["after"]
                or original.get("owned") != receipt["owned"]
                or original.get("serviceIdentity") != receipt["serviceIdentity"]
                or receipt.get("applyReceiptSha256", digest) != digest):
            raise LayoutError("original apply recovery receipt changed")
        return digest

    def verify_backup(self, receipt, *, snapshot="before"):
        folders = {"before":"before", "disableBefore":"disable-before", "updateBefore":"update-before"}
        if receipt.get("schemaVersion") != 2: folders.pop("updateBefore")
        if receipt.get("schemaVersion") == 2 and snapshot == "before":
            original = _updates()._origin(self, receipt["origin"], receipt["plan"])
            if receipt["before"] != original["before"]: raise LayoutError("update original backup changed")
            return self.verify_backup(original)
        if snapshot not in folders: raise LayoutError("invalid recovery snapshot")
        before = receipt[snapshot]
        if not isinstance(before, dict) or set(before) != set(CONFIG_FILES):
            raise LayoutError("invalid original layout backup")
        content = {}
        for name in CONFIG_FILES:
            metadata = before[name]
            _object(metadata, ("exists", "mode", "sha256"), "backup metadata")
            target = self.config_home / name; self._safe_path(target)
            if metadata["exists"] is True:
                _integer(metadata["mode"], 0, 0o777, "backup mode")
                source = self._directory(receipt) / folders[snapshot] / name; self._safe_path(source)
                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != metadata["sha256"]:
                    raise LayoutError("original layout backup changed")
                content[name] = data
            elif metadata != {"exists": False, "mode": None, "sha256": None}:
                raise LayoutError("invalid absent-file backup")
        return before, content

    def restore_before(self, receipt, *, snapshot="before"):
        import os
        before, content = self.verify_backup(receipt, snapshot=snapshot)
        # Validate all original backups before replacing either current file.
        for name in CONFIG_FILES:
            target = self.config_home / name
            if before[name]["exists"]:
                self._atomic(target, content[name], before[name]["mode"])
            elif target.exists():
                target.unlink()
                directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)

    def lock(self):
        from contextlib import contextmanager
        import fcntl
        import os
        @contextmanager
        def locked():
            path = self.state_home / ".lock"
            self._safe_path(path)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            handle = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc: raise LayoutError("another layout transaction is active") from exc
                yield
            finally:
                os.close(handle)
        return locked()


def read_json(path, limit=65536):
    path = Path(path)
    FileStore._safe_path(path)
    if path.stat().st_size > limit: raise LayoutError("layout data exceeds size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict): raise ValueError()
        return value
    except (ValueError, UnicodeError) as exc:
        raise LayoutError("invalid layout JSON data") from exc


def _read_layout_receipt(path):
    receipt = read_json(path, 524288)
    if type(receipt.get("schemaVersion")) is not int or receipt["schemaVersion"] not in (1, 2):
        raise LayoutError("unsupported layout receipt version")
    if receipt["schemaVersion"] == 1 and Path(path).stat().st_size > 262144:
        raise LayoutError("layout data exceeds size limit")
    return receipt


def _check_owned(receipt, inventory):
    if receipt.get("schemaVersion") == 2:
        _inventory_match(receipt["activeInventory"], inventory)
        return
    owned = receipt["owned"]
    if not isinstance(owned, dict) or owned.get("token") != receipt["plan"]["planId"]:
        raise LayoutError("managed panel receipt changed")
    matches = [panel for panel in inventory.get("panels", []) if panel["id"] == owned.get("panelId")]
    if len(matches) != 1:
        raise LayoutError("managed panel is unavailable")
    panel = matches[0]
    if (panel["type"] != "org.kde.panel" or panel["screen"] != receipt["plan"]["screen"]["id"]
            or panel["height"] != receipt["plan"]["manifest"]["panel"]["height"]
            or panel["marker"] != {"token": owned["token"], "schemaVersion": 1}
            or panel["widgets"] != owned.get("widgets")
            or inventory.get("selectedScreen") != receipt["plan"]["screen"]):
        raise LayoutError("managed panel ownership, modules or monitor changed")



def _managed_inventory(plan, owned):
    _object(owned, ("panelId", "token", "screen", "height", "widgets", "nativeValidated"), "managed result")
    _integer(owned["panelId"], 1, 2147483647, "managed panel ID")
    _integer(owned["screen"], 0, 2147483647, "managed screen")
    _integer(owned["height"], 28, 64, "managed height")
    if (owned["token"] != plan["planId"] or owned["screen"] != plan["screen"]["id"]
            or owned["height"] != plan["manifest"]["panel"]["height"] or owned["nativeValidated"] is not False
            or any(panel["id"] == owned["panelId"] for panel in plan["inventory"]["panels"])):
        raise LayoutError("managed result identity or monitor changed")
    modules = [module for module in plan["manifest"]["modules"] if module["enabled"]]
    widgets = owned["widgets"]
    if not isinstance(widgets, list) or len(widgets) != len(modules):
        raise LayoutError("managed result module selection changed")
    original_ids = {widget["id"] for panel in plan["inventory"]["panels"] for widget in panel["widgets"]}
    for index, (module, widget) in enumerate(zip(modules, widgets)):
        _object(widget, ("id", "type", "index"), "managed widget")
        _integer(widget["id"], 1, 2147483647, "managed widget ID")
        _integer(widget["index"], 0, 127, "managed widget index")
        reused = plan["manifest"]["reuseWidgetIds"].get(module["key"])
        if (widget["type"] != MODULE_IDS[module["key"]] or widget["index"] != index
                or (reused is not None and widget["id"] != reused)
                or (reused is None and widget["id"] in original_ids)):
            raise LayoutError("managed result widget identity or order changed")
    expected = copy.deepcopy(plan["inventory"])
    expected["panels"] = [panel for panel in expected["panels"]
                          if panel["id"] not in plan["manifest"]["replacePanelIds"]]
    expected["panels"].append({"id":owned["panelId"], "type":"org.kde.panel", "screen":owned["screen"],
        "height":owned["height"], "widgets":copy.deepcopy(widgets),
        "marker":{"token":owned["token"], "schemaVersion":1}})
    expected["panels"].sort(key=lambda panel:panel["id"])
    return validate_inventory(expected)

def _guard_target(runtime, store, expected=None):
    identity = runtime.identity
    if (not isinstance(identity, dict) or not isinstance(identity.get("target"), dict)
            or identity["target"].get("configHome") != str(store.config_home.resolve())):
        raise LayoutError("caller configuration root does not match the verified live Plasma target")
    if expected is not None and identity != expected:
        raise LayoutError("receipt Plasma configuration target changed")


def _owned_order_state(expected, actual, owned, *, allow_pending):
    # Only this freshly created panel may vary in indices/order. Validation of
    # the generic shape does not authorize pending indices on any other panel.
    validate_inventory(actual, allow_uninitialized=allow_pending)
    matches = [panel for panel in actual["panels"] if panel["id"] == owned["panelId"]]
    if len(matches) != 1: _inventory_match(expected, actual)
    widgets = matches[0]["widgets"]
    target = owned["widgets"]
    members_match = (sorted((widget["id"],widget["type"]) for widget in widgets)
                     == sorted((widget["id"],widget["type"]) for widget in target))
    initialized = [widget["index"] for widget in widgets if widget["index"] >= 0]
    # Deferred QML saves can include only the attached subset. Pending remains
    # wait-only: canonical native representation and a unique dense prefix.
    pending = (members_match and any(widget["index"] == -1 for widget in widgets)
               and len(initialized) < len(target) and sorted(initialized) == list(range(len(initialized)))
               and widgets == sorted(widgets, key=lambda widget:(widget["index"],widget["id"])))
    dense = members_match and [widget["index"] for widget in widgets] == list(range(len(target)))
    if not dense and not (allow_pending and pending): _inventory_match(expected, actual)
    comparison = copy.deepcopy(actual)
    screen_pending = (actual["screenIds"] == [] and actual["selectedScreen"] is None
                      and all(panel["screen"] == -1 for panel in actual["panels"]))
    if screen_pending:
        comparison["screenIds"] = copy.deepcopy(expected["screenIds"])
        comparison["selectedScreen"] = copy.deepcopy(expected["selectedScreen"])
        screens = {panel["id"]:panel["screen"] for panel in expected["panels"]}
        for panel in comparison["panels"]:
            if panel["id"] not in screens: _inventory_match(expected, actual)
            panel["screen"] = screens[panel["id"]]
    next(panel for panel in comparison["panels"] if panel["id"] == owned["panelId"])["widgets"] = copy.deepcopy(target)
    if comparison != expected: _inventory_match(expected, actual)
    if screen_pending: return "screen-pending"
    return "exact" if actual == expected else "dense" if dense else "pending"


def _order_owned(receipt, expected, runtime, store, clock, pause):
    # A single bounded budget covers initialization, one dispatch, and final
    # exact readback. Returning from each script lets Plasma run deferred work.
    deadline = clock() + READINESS_SECONDS
    connector = receipt["plan"]["manifest"]["screen"]["connector"]
    owned = receipt["owned"]
    dispatched = False
    for attempt in range(READINESS_ATTEMPTS):
        _guard_target(runtime, store, receipt["serviceIdentity"])
        _readiness_check(deadline, clock)
        if isinstance(runtime, _NATIVE_RUNTIME_TYPE):
            actual = runtime.inspect(connector, allow_uninitialized=not dispatched,
                                     ready_deadline=deadline, clock=clock)
        else:
            actual = runtime.inspect(connector)
        _guard_target(runtime, store, receipt["serviceIdentity"])
        _readiness_check(deadline, clock)
        state = _owned_order_state(expected, actual, owned, allow_pending=not dispatched)
        if state == "exact": return
        # Keep a read for strict final verification before dispatching.
        if attempt + 1 == READINESS_ATTEMPTS:
            raise LayoutError("owned panel order attempts exhausted", code="READINESS_TIMEOUT")
        if state == "dense" and not dispatched:
            _stage(receipt, store, "REORDER_OWNED")
            _guard_target(runtime, store, receipt["serviceIdentity"])
            _readiness_check(deadline, clock)
            reorder = getattr(runtime, "reorder_owned", None)
            if not callable(reorder): raise LayoutError("owned reorder capability unavailable")
            if isinstance(runtime, _NATIVE_RUNTIME_TYPE):
                result = reorder(owned["panelId"], owned["token"], actual, owned["widgets"],
                                 ready_deadline=deadline, clock=clock)
            else:
                result = reorder(owned["panelId"], owned["token"], actual, owned["widgets"])
            _guard_target(runtime, store, receipt["serviceIdentity"])
            _readiness_check(deadline, clock)
            if not isinstance(result, dict) or set(result) != {"reordered"} or result["reordered"] is not True:
                raise LayoutError("owned panel reorder was not acknowledged", code="SCRIPT_REPLY_INVALID",
                                  operation="EVALUATE_SCRIPT")
            dispatched = True
            _stage(receipt, store, "VERIFY_OWNED_ORDER")
        remaining = deadline - clock()
        if remaining <= 0: _readiness_check(deadline, clock)
        pause(min(READINESS_PAUSE, remaining))
    raise LayoutError("owned panel order attempts exhausted", code="READINESS_TIMEOUT")


def _rollback(receipt, runtime, store, clock, pause):
    _stage(receipt, store, "RECOVERY_STOP")
    if not runtime.stopped(): runtime.stop()
    _stage(receipt, store, "RECOVERY_BIND")
    _guard_target(runtime, store, receipt["serviceIdentity"])
    receipt["operation"] = "restore"; receipt["recoveryIntent"] = "original"
    receipt["phase"] = "RESTORING"
    _stage(receipt, store, "RECOVERY_CAPTURE")
    store.capture_recovery(receipt)
    if receipt.get("schemaVersion") == 2: _updates().guard_original_recovery(store, receipt)
    _stage(receipt, store, "RECOVERY_REPLACE")
    store.restore_before(receipt)
    _stage(receipt, store, "RECOVERY_START")
    runtime.start()
    runtime.preflight()
    _stage(receipt, store, "RECOVERY_VERIFY")
    _, deadline = _inspect_ready(receipt["plan"]["inventory"], receipt["plan"]["manifest"]["screen"]["connector"],
                                 runtime, store, receipt["serviceIdentity"], clock, pause)
    _readiness_check(deadline, clock)
    receipt["phase"] = "RESTORED"; receipt["stage"] = "RECOVERY_COMMIT"; store.save(receipt)


def apply_layout(plan, runtime, store, *, clock=None, pause=None):
    import time
    clock = time.monotonic if clock is None else clock
    pause = time.sleep if pause is None else pause
    plan = validate_plan(plan)
    runtime.preflight()
    _guard_target(runtime, store)
    with store.lock():
        previous = store.current()
        if previous and previous.get("schemaVersion") == 2 and previous.get("phase") != "RESTORED":
            raise LayoutError("active managed update must be restored or recovered before schema1 apply")
        if previous and previous["phase"] != "RESTORED":
            if previous["phase"] == "COMMITTED" and previous["plan"]["planId"] == plan["planId"]:
                if previous["service"] != runtime.unit or previous.get("serviceIdentity") != runtime.identity:
                    raise LayoutError("managed layout service identity changed")
                _check_owned(previous, runtime.inspect(plan["manifest"]["screen"]["connector"]))
                return previous
            raise LayoutError("restore the active layout or recover the interrupted transaction first")
        _inventory_match(plan["inventory"], runtime.inspect(plan["manifest"]["screen"]["connector"]))
        receipt = None
        try:
            runtime.stop()
            _guard_target(runtime, store)
            receipt = store.prepare(plan, runtime.unit, runtime.identity)
            _stage(receipt, store, "RESTART_FOR_APPLY")
            runtime.start()
            _stage(receipt, store, "PREFLIGHT_AFTER_BACKUP")
            runtime.preflight()
            _stage(receipt, store, "INSPECT_AFTER_BACKUP")
            _, deadline = _inspect_ready(plan["inventory"], plan["manifest"]["screen"]["connector"],
                                         runtime, store, receipt["serviceIdentity"], clock, pause)
            _readiness_check(deadline, clock)
            receipt["phase"] = "APPLYING"; _stage(receipt, store, "APPLY_SCRIPT")
            _readiness_check(deadline, clock)
            if isinstance(runtime, _NATIVE_RUNTIME_TYPE):
                receipt["owned"] = runtime.apply(plan, ready_deadline=deadline, clock=clock)
            else:
                receipt["owned"] = runtime.apply(plan)
            expected_managed = _managed_inventory(plan, receipt["owned"])
            store.save(receipt)
            _stage(receipt, store, "STOP_FOR_ORDER")
            runtime.stop()
            _guard_target(runtime, store, receipt["serviceIdentity"])
            _stage(receipt, store, "RESTART_FOR_ORDER")
            runtime.start()
            runtime.preflight()
            _guard_target(runtime, store, receipt["serviceIdentity"])
            _stage(receipt, store, "WAIT_OWNED_ORDER")
            _order_owned(receipt, expected_managed, runtime, store, clock, pause)
            _stage(receipt, store, "STOP_AFTER_APPLY")
            runtime.stop()
            _stage(receipt, store, "CAPTURE_AFTER")
            store.capture_after(receipt)
            _stage(receipt, store, "RESTART_AFTER_APPLY")
            runtime.start()
            runtime.preflight()
            _stage(receipt, store, "VERIFY_OWNED")
            actual, deadline = _inspect_ready(expected_managed, plan["manifest"]["screen"]["connector"],
                                              runtime, store, receipt["serviceIdentity"], clock, pause)
            _check_owned(receipt, actual)
            _readiness_check(deadline, clock)
            receipt["phase"] = "COMMITTED"; receipt["stage"] = "COMMIT"; store.save(receipt)
            return receipt
        except (LayoutError, OSError, ValueError, KeyError, TypeError) as exc:
            if receipt is not None:
                _failure(receipt, store, "primary", exc)
                try:
                    _rollback(receipt, runtime, store, clock, pause)
                except (LayoutError, OSError, ValueError, KeyError, TypeError) as recovery_exc:
                    _failure(receipt, store, "recovery", recovery_exc)
                    raise _failure_error(receipt, store, "apply failed; recovery required, backups retained",
                                         recovery_required=True) from exc
                raise LayoutError("apply failed; previous layout restored and backups retained") from exc
            if runtime.stopped():
                try: runtime.start()
                except LayoutError:
                    raise LayoutError("backup preparation failed; restart the selected Plasma service") from exc
            raise LayoutError("layout preparation failed before panel mutation") from exc


def _restore_layout_v1(receipt, runtime, store, *, recover=False, clock=None, pause=None):
    import time
    clock = time.monotonic if clock is None else clock
    pause = time.sleep if pause is None else pause
    restarted = False
    runtime.preflight(allow_stopped=recover)
    with store.lock():
        current = store.current()
        expected = receipt.get("serviceIdentity", {})
        if not isinstance(expected, dict) or not isinstance(expected.get("target"), dict):
            raise LayoutError("receipt lacks a verified Plasma configuration target")
        if (current != receipt or receipt.get("service") != runtime.unit
                or any(runtime.identity.get(key) != expected.get(key) for key in ("unit", "executable", "argv"))):
            raise LayoutError("layout receipt or selected service changed")
        validate_plan(receipt["plan"])
        if receipt["phase"] == "RESTORED": return receipt
        if expected.get("target", {}).get("configHome") != str(store.config_home.resolve()):
            raise LayoutError("receipt configuration root does not match caller storage")
        if recover and runtime.stopped():
            runtime.start(); runtime.preflight(); restarted = True
        _guard_target(runtime, store, expected)
        if receipt["phase"] in ("COMMITTED", "DISABLED") or receipt.get("operation") == "disable":
            store.verify_apply_receipt(receipt)
        if (receipt.get("operation") == "disable" and receipt.get("recoveryIntent") != "original"
                and receipt["phase"] not in ("COMMITTED", "DISABLED")):
            if not recover: raise LayoutError("interrupted disable requires explicit --recover")
            store.verify_backup(receipt, snapshot="disableBefore")
            try:
                _rollback_disable(receipt, runtime, store, clock, pause)
            except (LayoutError, OSError, ValueError, KeyError, TypeError) as exc:
                _failure(receipt, store, "recovery", exc)
                raise _failure_error(receipt, store, "disable recovery did not complete; backups retained",
                                     recovery_required=True) from exc
            return receipt
        store.verify_backup(receipt)
        if receipt["phase"] not in ("COMMITTED", "DISABLED") and not recover:
            raise LayoutError("interrupted layout requires explicit --recover")
        try:
            if receipt["phase"] in ("COMMITTED", "DISABLED"):
                connector = receipt["plan"]["manifest"]["screen"]["connector"]
                if restarted:
                    _stage(receipt, store, "RESTORE_VERIFY_CURRENT")
                    if receipt["phase"] == "COMMITTED":
                        inventory = (receipt["activeInventory"] if receipt.get("schemaVersion") == 2
                                     else _managed_inventory(receipt["plan"], receipt["owned"]))
                    else: inventory = _disabled_inventory(receipt)
                    info, deadline = _inspect_ready(inventory, connector, runtime, store,
                                                   receipt["serviceIdentity"], clock, pause)
                    _readiness_check(deadline, clock)
                else:
                    info = runtime.inspect(connector)
                if receipt["phase"] == "COMMITTED": _check_owned(receipt, info)
                else: _check_disabled(receipt, info)
                expected = receipt["after"] if receipt["phase"] == "COMMITTED" else receipt["disableAfter"]
                runtime.stop()
                try: store.verify_current(expected)
                except LayoutError:
                    runtime.start()
                    raise
                if receipt.get("schemaVersion") == 2:
                    receipt["originalRestoreFrom"] = copy.deepcopy(expected)
            _rollback(receipt, runtime, store, clock, pause)
            return receipt
        except (LayoutError, OSError, ValueError, KeyError, TypeError) as exc:
            _failure(receipt, store, "recovery", exc)
            # A committed conflict is not an interrupted restore or permission to overwrite.
            raise _failure_error(receipt, store, "restore did not complete; current layout and backups retained",
                                 recovery_required=receipt["phase"] not in ("COMMITTED", "DISABLED")) from exc



def add_parser(subparsers):
    parser = subparsers.add_parser("layout", help="enable/disable a managed top bar; dock is managed independently")
    actions = parser.add_subparsers(dest="layout_action", required=True)
    for action in ("setup", "plan", "plan-update", "status", "apply", "update", "disable", "restore"):
        child = actions.add_parser(action)
        child.add_argument("--service", required=True, help="explicit current-user Plasma dbus service unit")
        if action == "plan":
            child.add_argument("--manifest", type=Path, required=True)
            child.add_argument("--output", type=Path, required=True, help="private plan file; no panel mutation")
        elif action == "plan-update":
            child.add_argument("--receipt", type=Path, required=True)
            child.add_argument("--add", choices=("control-center",), required=True)
            child.add_argument("--output", type=Path, required=True, help="private update plan; no panel mutation")
        elif action in ("apply", "update"):
            child.add_argument("--plan", type=Path, required=True)
        elif action in ("disable", "restore"):
            child.add_argument("--receipt", type=Path, required=True)
            if action == "restore":
                child.add_argument("--recover", action="store_true", help="explicitly recover an interrupted transaction")


def cli(args):
    import os
    if args.layout_action == "setup":
        root = Path(__file__).resolve().parents[1]
        if not all((root / name).is_file() for name in (
                "workspace/Workspace.qml", "workspace/CompositionView.qml", "layouts/mac-inspired-topbar.json")):
            raise LayoutError("composition setup requires the complete source checkout (workspace/ and layouts/)")
        try:
            if __package__:
                from . import workspace_setup
            else:
                import workspace_setup
        except ImportError as exc:
            raise LayoutError("composition setup requires PySide6 6.11 or newer with Qt Quick") from exc
        return workspace_setup.launch(args.service)
    runtime = NativeRuntime(args.service)
    caller_config = os.environ.get("XDG_CONFIG_HOME", "")
    config = Path(caller_config) if caller_config.startswith("/") else Path.home()/".config"
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home()/".local/state"))) / "orla/layouts"
    store = FileStore(config, state)
    if args.layout_action == "plan":
        manifest = validate_manifest(read_json(args.manifest))
        runtime.preflight()
        plan = build_plan(manifest, runtime.inspect(manifest["screen"]["connector"]))
        FileStore._atomic(args.output, json.dumps(plan, sort_keys=True).encode())
        print("Plan saved; no panel changed. Review the selected panel IDs before apply.")
        return 0
    if args.layout_action == "status":
        runtime.preflight(allow_stopped=True)
        record = store.current()
        stopped = runtime.stopped()
        result = {"receiptPhase": record["phase"] if record else "UNMANAGED", "dockManagedIndependently": True,
                  "nativeValidated": False, "liveInventoryAvailable": not stopped}
        if not stopped:
            info = runtime.inspect()
            result["screenIds"] = info["screenIds"]
            result["panels"] = [{key:value for key,value in panel.items() if key != "marker"} for panel in info["panels"]]
        if record and record.get("owned"):
            result["panelId"] = record["owned"]["panelId"]
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.layout_action == "plan-update":
        plan = build_update_plan(read_json(args.receipt, 262144), runtime, store, add=args.add)
        FileStore._atomic(args.output, json.dumps(plan, sort_keys=True).encode())
        print("Update plan saved; no panel changed. Review before update.")
        return 0
    if args.layout_action == "apply":
        receipt = apply_layout(read_json(args.plan, 262144), runtime, store)
        print("Managed top bar enabled; dock is managed independently. Native validation pending.")
    elif args.layout_action == "update":
        receipt = update_layout(read_json(args.plan, 262144), runtime, store)
        print("Managed top bar updated; original recovery data retained. Native validation pending.")
    elif args.layout_action == "disable":
        receipt = disable_layout(_read_layout_receipt(args.receipt), runtime, store)
        print("Managed top bar disabled; other panels and dock retained. Original recovery data retained.")
    else:
        receipt = restore_layout(_read_layout_receipt(args.receipt), runtime, store, recover=args.recover)
        if receipt["phase"] == "COMMITTED":
            print("Interrupted disable recovered; active managed top bar restored.")
        else:
            print("Previous layout explicitly restored. Dock is managed independently.")
    print("Private receipt: " + str(store._directory(receipt)/"receipt.json"))
    return 0


def _check_disabled(receipt, inventory):
    before = receipt["disableInventory"]
    owned = receipt["owned"]
    panels = inventory.get("panels", [])
    if any(panel["id"] == owned["panelId"] or panel["marker"]["token"] == owned["token"] for panel in panels):
        raise LayoutError("owned managed panel is not absent")
    expected = [panel for panel in before["panels"] if panel["id"] != owned["panelId"]]
    if panels != expected or inventory["selectedScreen"] != before["selectedScreen"]:
        raise LayoutError("disabled layout has unrelated panel or monitor changes")


def _disabled_inventory(receipt):
    expected = copy.deepcopy(receipt["disableInventory"])
    expected["panels"] = [panel for panel in expected["panels"] if panel["id"] != receipt["owned"]["panelId"]]
    return expected


def _rollback_disable(receipt, runtime, store, clock, pause):
    if receipt.get("schemaVersion") == 2:
        return _updates().rollback_disable(receipt, runtime, store, clock, pause)
    if not runtime.stopped(): runtime.stop()
    _guard_target(runtime, store, receipt["serviceIdentity"])
    receipt["recoveryIntent"] = "disable"; receipt["phase"] = "RESTORING"
    store.capture_recovery(receipt)
    store.restore_before(receipt, snapshot="disableBefore")
    runtime.start()
    runtime.preflight()
    _stage(receipt, store, "DISABLE_RECOVERY_VERIFY")
    info, deadline = _inspect_ready(receipt["disableInventory"], receipt["plan"]["manifest"]["screen"]["connector"],
                                   runtime, store, receipt["serviceIdentity"], clock, pause)
    _check_owned(receipt, info)
    _readiness_check(deadline, clock)
    receipt["phase"] = "COMMITTED"; receipt["operation"] = "apply"
    receipt.pop("recoveryIntent", None); store.save(receipt)


def _disable_layout_v1(receipt, runtime, store, *, clock=None, pause=None):
    import time
    clock = time.monotonic if clock is None else clock
    pause = time.sleep if pause is None else pause
    runtime.preflight()
    _guard_target(runtime, store)
    with store.lock():
        if store.current() != receipt or receipt.get("serviceIdentity") != runtime.identity or receipt["service"] != runtime.unit:
            raise LayoutError("layout receipt or service identity changed")
        validate_plan(receipt["plan"])
        connector = receipt["plan"]["manifest"]["screen"]["connector"]
        info = runtime.inspect(connector)
        if receipt["phase"] == "DISABLED":
            store.verify_apply_receipt(receipt)
            _check_disabled(receipt, info)
            runtime.stop()
            try: store.verify_current(receipt["disableAfter"])
            finally:
                runtime.start(); runtime.preflight()
            _stage(receipt, store, "DISABLE_VERIFY_FINAL")
            actual, deadline = _inspect_ready(_disabled_inventory(receipt), connector, runtime, store,
                                             receipt["serviceIdentity"], clock, pause)
            _check_disabled(receipt, actual)
            _readiness_check(deadline, clock)
            return receipt
        if receipt["phase"] != "COMMITTED": raise LayoutError("recover the interrupted transaction before disable")
        _check_owned(receipt, info)
        original_hash = store.verify_apply_receipt(receipt)
        runtime.stop()
        try:
            store.verify_current(receipt["after"])
            metadata = store._capture(store._directory(receipt) / "disable-before")
        except (LayoutError, OSError, ValueError):
            runtime.start()
            raise
        receipt["disableBefore"] = metadata
        receipt["disableInventory"] = info
        receipt["applyReceiptSha256"] = original_hash
        receipt["operation"] = "disable"; receipt["phase"] = "DISABLING"
        try:
            store.save(receipt)
            runtime.start(); runtime.preflight()
            _stage(receipt, store, "DISABLE_VERIFY_RESTART")
            _, deadline = _inspect_ready(info, connector, runtime, store, receipt["serviceIdentity"], clock, pause)
            _stage(receipt, store, "DISABLE_REMOVE")
            _guard_target(runtime, store, receipt["serviceIdentity"])
            _readiness_check(deadline, clock)
            if isinstance(runtime, _NATIVE_RUNTIME_TYPE):
                result = runtime.remove_owned(receipt["owned"]["panelId"], receipt["owned"]["token"], info,
                                              ready_deadline=deadline, clock=clock)
            else:
                result = runtime.remove_owned(receipt["owned"]["panelId"], receipt["owned"]["token"], info)
            _guard_target(runtime, store, receipt["serviceIdentity"])
            _readiness_check(deadline, clock)
            if result != {"removed":True}: raise LayoutError("owned panel removal was not acknowledged")
            runtime.stop()
            _stage(receipt, store, "DISABLE_CLEANUP_RESTART")
            runtime.start(); runtime.preflight()
            _stage(receipt, store, "DISABLE_VERIFY_FINAL")
            actual, deadline = _inspect_ready(_disabled_inventory(receipt), connector, runtime, store,
                                             receipt["serviceIdentity"], clock, pause)
            _check_disabled(receipt, actual)
            _readiness_check(deadline, clock)
            # Startup prunes configuration for the removed panel's old view.
            # Capture the canonical state only after this verified restart.
            _stage(receipt, store, "DISABLE_FINAL_STOP")
            runtime.stop()
            _guard_target(runtime, store, receipt["serviceIdentity"])
            _stage(receipt, store, "DISABLE_CAPTURE_FINAL")
            receipt["disableAfter"] = store._capture(store._directory(receipt) / "disable-after-final")
            store.save(receipt)
            _stage(receipt, store, "DISABLE_FINAL_RESTART")
            runtime.start(); runtime.preflight()
            _stage(receipt, store, "DISABLE_VERIFY_FINAL")
            actual, deadline = _inspect_ready(_disabled_inventory(receipt), connector, runtime, store,
                                             receipt["serviceIdentity"], clock, pause)
            _check_disabled(receipt, actual)
            _readiness_check(deadline, clock)
            receipt["phase"] = "DISABLED"; store.save(receipt)
            return receipt
        except (LayoutError, OSError, ValueError, KeyError, TypeError) as exc:
            _failure(receipt, store, "primary", exc)
            try:
                _rollback_disable(receipt, runtime, store, clock, pause)
            except (LayoutError, OSError, ValueError, KeyError, TypeError) as recovery_exc:
                _failure(receipt, store, "recovery", recovery_exc)
                raise _failure_error(receipt, store, "disable failed; active-layout recovery required, backups retained",
                                     recovery_required=True) from exc
            raise LayoutError("disable failed; active managed layout restored") from exc


def _updates():
    if __package__:
        from . import panel_layout_update
    else:
        import panel_layout_update
    return panel_layout_update


def build_update_plan(parent, runtime, store, *, add="control-center"):
    return _updates().build_update_plan(parent, runtime, store, add=add)


def validate_update_plan(plan):
    return _updates().validate_update_plan(plan)


def update_layout(plan, runtime, store, *, clock=None, pause=None):
    return _updates().update_layout(plan, runtime, store, clock=clock, pause=pause)


def save_update_receipt(store, receipt):
    return _updates().save_update_receipt(store, receipt)


def verify_update_receipt(store, receipt):
    return _updates().verify_update_receipt(store, receipt)


def restore_layout(receipt, runtime, store, *, recover=False, clock=None, pause=None):
    version = receipt.get("schemaVersion")
    if type(version) is not int or version not in (1, 2): raise LayoutError("unsupported layout receipt version")
    if version == 2: return _updates().restore_update(receipt, runtime, store, recover=recover, clock=clock, pause=pause)
    return _restore_layout_v1(receipt, runtime, store, recover=recover, clock=clock, pause=pause)


def disable_layout(receipt, runtime, store, *, clock=None, pause=None):
    version = receipt.get("schemaVersion")
    if type(version) is not int or version not in (1, 2): raise LayoutError("unsupported layout receipt version")
    if version == 2:
        _updates().validate_revision(store, receipt)
        verify_update_receipt(store, receipt)
    return _disable_layout_v1(receipt, runtime, store, clock=clock, pause=pause)
