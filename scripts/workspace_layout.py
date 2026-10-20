"""Single-review consumer for the existing optional panel transactions.

Calls are serialized by the host. This module does not construct NativeRuntime,
install applets, introduce a second store, or provide transaction cancellation.
"""
from __future__ import annotations

import copy
import json
import secrets

if __package__:
    from . import panel_layout as layout
else:
    import panel_layout as layout


def _same(left, right):
    # JSON equality keeps receipt booleans distinct from numeric lookalikes.
    def encoded(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return encoded(left) == encoded(right)


class CompositionSession:
    def __init__(self, runtime, store, template):
        self.runtime = runtime
        self.store = store
        self.template = copy.deepcopy(template)
        self._review = None

    def discard(self):
        self._review = None

    def _observe(self, connector):
        runtime, store = self.runtime, self.store
        runtime.preflight(allow_stopped=True)
        layout._guard_target(runtime, store)
        unit, identity = runtime.unit, copy.deepcopy(runtime.identity)
        roots = (str(store.config_home.resolve()), str(store.state_home.resolve()))
        if identity.get("unit") != unit:
            raise layout.LayoutError("selected layout service identity changed")
        running = not runtime.stopped()
        record = copy.deepcopy(store.current())
        # Existing read-only metadata snapshot: bytes are pinned by SHA256,
        # modes/existence remain exact. Passing None creates no bank or lock.
        files = store._capture(None)
        info = layout.validate_inventory(runtime.inspect(connector)) if running else None
        runtime.preflight(allow_stopped=True)
        layout._guard_target(runtime, store, identity)
        if (roots != (str(store.config_home.resolve()), str(store.state_home.resolve()))
                or runtime.unit != unit or (not runtime.stopped()) != running
                or not _same(store.current(), record)
                or not _same(store._capture(None), files)):
            raise layout.LayoutError("layout state changed while reading")
        return copy.deepcopy({"unit": unit, "identity": identity, "storeRoots": roots,
                              "shellRunning": running,
                              "inventory": info, "record": record, "files": files})

    def read(self, connector=""):
        self.discard()
        frame = self._observe(connector)
        record = frame["record"]
        return copy.deepcopy({"phase": record["phase"] if record else "UNMANAGED",
                              "shellRunning": frame["shellRunning"],
                              "inventory": frame["inventory"], "recordPresent": record is not None})

    def review_apply(self, manifest):
        self.discard()
        data = layout.validate_manifest(copy.deepcopy(manifest))
        connector = data["screen"]["connector"]
        frame = self._observe(connector)
        if not frame["shellRunning"]:
            raise layout.LayoutError("start the selected Plasma service before applying")
        plan = layout.build_plan(data, frame["inventory"])
        token = secrets.token_hex(24)
        self._review = {"token": token, "action": "apply", "connector": connector,
                        "frame": frame, "plan": copy.deepcopy(plan)}
        return copy.deepcopy({"token": token, "action": "apply", "connector": connector,
                              "replacePanelIds": data["replacePanelIds"],
                              "reuseWidgetIds": data["reuseWidgetIds"],
                              "modules": [m["key"] for m in data["modules"] if m["enabled"]],
                              "height": data["panel"]["height"],
                              "selectedPanels": plan["selectedPanels"]})

    def review_operation(self, action):
        self.discard()
        if action not in ("disable", "restore", "recover"):
            raise layout.LayoutError("unsupported composition action")
        record = copy.deepcopy(self.store.current())
        if record is None:
            raise layout.LayoutError("there is no managed layout receipt")
        plan = layout.validate_plan(record["plan"])
        connector = plan["manifest"]["screen"]["connector"]
        frame = self._observe(connector)
        if not _same(frame["record"], record):
            raise layout.LayoutError("selected layout receipt changed")
        token = secrets.token_hex(24)
        self._review = {"token": token, "action": action, "connector": connector, "frame": frame}
        return {"token": token, "action": action, "connector": connector, "phase": record["phase"]}

    def execute(self, token):
        review, self._review = self._review, None
        if review is None or type(token) is not str or token != review["token"]:
            raise layout.LayoutError("review the composition again before executing")
        current = self._observe(review["connector"])
        if not _same(current, review["frame"]):
            raise layout.LayoutError("reviewed composition state changed")
        action = review["action"]
        if action == "apply":
            receipt = layout.apply_layout(review["plan"], self.runtime, self.store)
        elif action == "disable":
            receipt = layout.disable_layout(current["record"], self.runtime, self.store)
        else:
            receipt = layout.restore_layout(current["record"], self.runtime, self.store,
                                            recover=action == "recover")
        return {"phase": receipt["phase"], "action": action, "connector": review["connector"]}
