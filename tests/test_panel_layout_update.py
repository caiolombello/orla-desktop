"""Managed CC revision behavior over owned synthetic KConfig banks only."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import panel_layout as layout
from test_panel_layout import FakeRuntime, inventory, manifest


class Interrupted(BaseException):
    """Process-loss cut: transaction catches must not turn this into rollback."""


class FrozenV1Store(layout.FileStore):
    # Frozen dff9dd7 reader methods: the discriminator must fail before effects.
    def _directory(self, receipt):
        import re
        transaction = receipt.get("transactionId", "")
        if not re.fullmatch(r"[0-9a-f]{64}-[0-9a-f]{16}", transaction):
            raise layout.LayoutError("invalid layout transaction identity")
        return self.state_home / transaction

    def current(self):
        path = self.state_home / "current.json"
        self._safe_path(path)
        if not path.exists(): return None
        pointer = layout.read_json(path, 262144)
        journal = layout.read_json(self._directory(pointer) / "receipt.json", 262144)
        if journal.get("transactionId") != pointer.get("transactionId"):
            raise layout.LayoutError("current transaction journal identity changed")
        return journal


class UpdateRuntime(FakeRuntime):
    def __init__(self, config_home, failure=""):
        super().__init__(config_home, failure)
        self.updated = False

    def apply(self, plan):
        self.events.append("apply")
        self.plan = plan
        self.applied = True
        widgets = self.owned()["widgets"]
        applets = "[General]\nlabel=" + getattr(self, "synthetic_label", "synthetic") + "\n[ActionPlugins][0]\nRightButton;NoModifier=synthetic.plugin\n[Containments][10][Applets][11][Configuration][General]\nshowClock=true\n"
        applets += "[Containments][100]\nplugin=org.kde.panel\n[Containments][100][General]\nAppletOrder="
        applets += ";".join(str(w["id"]) for w in widgets) + "\n"
        for w in widgets:
            applets += f"[Containments][100][Applets][{w['id']}]\nplugin={w['type']}\n"
            applets += f"[Containments][100][Applets][{w['id']}][Configuration][General]\nsetting=retained\n"
        (self.config_home/layout.CONFIG_FILES[0]).write_text(applets)
        (self.config_home/layout.CONFIG_FILES[1]).write_text("[General]\nsetting=foreign\n[PlasmaViews][Panel 100]\nthickness=32\n")
        return self.owned()

    def owned(self):
        owned = super().owned()
        if self.updated:
            owned["widgets"].insert(4, {"id": 900, "type": "org.orla.bar", "index": 4})
            for index, widget in enumerate(owned["widgets"]): widget["index"] = index
        return owned

    def start(self):
        self.events.append("start")
        self.is_stopped = False
        data = (self.config_home/layout.CONFIG_FILES[0]).read_text()
        self.applied = "\n[Containments][100]\n" in "\n" + data
        self.updated = "\n[Containments][100][Applets][900]\n" in "\n" + data
        self.disabled = not self.applied and "\n[Containments][28]\n" not in "\n" + data

    def stop(self):
        super().stop()
        if self.updated and self.failure == "stop-after-update":
            self.failure = ""
            raise layout.LayoutError("synthetic post-update stop failure")

    def update_owned(self, plan):
        self.events.append("update-owned")
        path = self.config_home/layout.CONFIG_FILES[0]
        data = path.read_text()
        old = ";".join(str(w["id"]) for w in self.owned()["widgets"])
        self.updated = True
        new = ";".join(str(w["id"]) for w in self.owned()["widgets"])
        data = data.replace("AppletOrder=" + old + "\n", "AppletOrder=" + new + "\n")
        data += "[Containments][100][Applets][900]\nplugin=org.orla.bar\n"
        if self.failure != "lost-reply-unmarked":
            data += "[Containments][100][Applets][900][Configuration][OrlaManagedUpdate]\ntoken=" + plan["planId"] + "\n"
        data += "[Containments][100][Applets][900][Configuration][General]\n"
        data += "showOrlaMenu=false\nshowApplicationName=false\nshowControlCenter=true\n"
        path.write_text(data)
        if self.failure in ("lost-reply", "lost-reply-unmarked"):
            self.failure = ""
            raise layout.LayoutError("synthetic lost owned reply")
        return self.owned()

    def remove_owned(self, panel_id, token, expected_inventory):
        self.events.append("remove-owned")
        if self.inspect("DP-1") != expected_inventory or panel_id != 100 or token != self.plan["planId"]:
            raise layout.LayoutError("synthetic foreign panel")
        from scripts.panel_layout_update import kconfig_groups
        for name in layout.CONFIG_FILES:
            groups = kconfig_groups((self.config_home/name).read_bytes())
            prefix = ("Containments", "100") if name == layout.CONFIG_FILES[0] else ("PlasmaViews", "Panel 100")
            text = ""
            for group, values in groups.items():
                if group[:len(prefix)] == prefix: continue
                if group: text += "".join("[" + part + "]" for part in group) + "\n"
                text += "".join(k + "=" + v + "\n" for k, v in values.items())
            (self.config_home/name).write_text(text)
        self.applied = False; self.disabled = True; self.updated = False
        if self.failure == "disable":
            self.failure = ""
            raise layout.LayoutError("synthetic uncertain removal")
        return {"removed": True}


class ManagedUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root/"config"
        self.config.mkdir()
        self.original = {
            layout.CONFIG_FILES[0]: b"[General]\nlabel=synthetic\n[ActionPlugins][0]\nRightButton;NoModifier=synthetic.plugin\n[Containments][28]\nplugin=org.kde.panel\n",
            layout.CONFIG_FILES[1]: b"[General]\nsetting=foreign\n[PlasmaViews][Panel 28]\nthickness=32\n",
        }
        for name, data in self.original.items():
            (self.config/name).write_bytes(data)
            (self.config/name).chmod(0o640)
        self.store = layout.FileStore(self.config, self.root/"orla/layouts")
        self.runtime = UpdateRuntime(self.config)
        self.plan = layout.build_plan(manifest(), inventory())
        self.parent = layout.apply_layout(self.plan, self.runtime, self.store)

    def origin_pins(self):
        directory = self.store._directory(self.parent)
        return {str(p.relative_to(directory)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mode & 0o777)
                for p in directory.rglob("*") if p.is_file()}

    def test_add_cc_preserves_origin_panel_and_owned_configuration_drift(self):
        path = self.config/layout.CONFIG_FILES[0]
        path.write_text(path.read_text() + "[Containments][100][Applets][200][ConfigDialog]\nDialogWidth=740\n")
        original_banks = self.origin_pins()
        plan = layout.build_update_plan(self.parent, self.runtime, self.store, add="control-center")
        self.assertEqual(plan["insertionIndex"], 4)
        self.assertTrue(plan["restoreCompatible"])
        before = path.read_text()
        receipt = layout.update_layout(plan, self.runtime, self.store)
        self.assertEqual(receipt["schemaVersion"], 2)
        self.assertTrue(receipt["transactionId"].startswith("u2-"))
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertEqual(receipt["owned"]["panelId"], self.parent["owned"]["panelId"])
        old_ids = {w["id"] for w in self.parent["owned"]["widgets"]}
        self.assertEqual({w["id"] for w in receipt["owned"]["widgets"]} - old_ids, {900})
        self.assertIn("DialogWidth=740", path.read_text())
        self.assertEqual(original_banks, self.origin_pins())
        self.assertFalse((self.store._directory(receipt)/"before").exists())
        self.assertEqual(self.runtime.events.count("update-owned"), 1)
        self.assertEqual(layout.update_layout(plan, self.runtime, self.store), receipt)
        self.assertEqual(self.runtime.events.count("update-owned"), 1)
        self.assertNotEqual(path.read_text(), before)

    def test_failure_after_reply_restores_update_before_and_keeps_origin(self):
        path = self.config/layout.CONFIG_FILES[0]
        path.write_text(path.read_text() + "[Containments][100][Applets][200][ConfigDialog]\nDialogWidth=740\n")
        before = {name: (self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        original = self.origin_pins()
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        self.runtime.failure = "stop-after-update"
        with self.assertRaises(layout.LayoutError): layout.update_layout(plan, self.runtime, self.store)
        self.assertEqual({name: (self.config/name).read_bytes() for name in layout.CONFIG_FILES}, before)
        self.assertEqual(self.store.current(), self.parent)
        self.assertEqual(original, self.origin_pins())
        self.assertFalse(self.runtime.is_stopped)
        self.assertEqual(self.runtime.events.count("update-owned"), 1)
        journals = [layout.read_json(p) for p in self.store.state_home.glob("u2-*/receipt.json")]
        self.assertEqual(journals[0]["phase"], "ROLLED_BACK")
        self.assertTrue(journals[0]["recoveryPoints"][-1]["complete"])

    def committed_update(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        return layout.update_layout(plan, self.runtime, self.store)

    def test_lost_reply_with_exact_marker_rolls_back_without_replaying(self):
        before = {name: (self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        self.runtime.failure = "lost-reply"
        with self.assertRaises(layout.LayoutError): layout.update_layout(plan, self.runtime, self.store)
        self.assertEqual({name: (self.config/name).read_bytes() for name in layout.CONFIG_FILES}, before)
        self.assertEqual(self.runtime.events.count("update-owned"), 1)
        self.assertEqual(self.store.current(), self.parent)

    def test_unknown_lost_reply_retains_banks_and_current_user_data(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        self.runtime.failure = "lost-reply-unmarked"
        with self.assertRaises(layout.LayoutError): layout.update_layout(plan, self.runtime, self.store)
        receipt = self.store.current()
        self.assertEqual(receipt["phase"], "RECOVERY_REQUIRED")
        self.assertTrue(receipt["recoveryPoints"][-1]["complete"])
        self.assertIn("[Applets][900]", (self.config/layout.CONFIG_FILES[0]).read_text())
        self.assertEqual(self.runtime.events.count("update-owned"), 1)

    def test_committed_update_restores_original_through_immutable_origin(self):
        pinned = self.origin_pins()
        receipt = self.committed_update()
        restored = layout.restore_layout(receipt, self.runtime, self.store)
        self.assertEqual(restored["phase"], "RESTORED")
        self.assertEqual({name: (self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
        self.assertEqual(self.origin_pins(), pinned)
        self.assertFalse((self.store._directory(receipt)/"before").exists())

    def test_disable_and_original_restore_use_latest_owned_then_original_bank(self):
        receipt = self.committed_update()
        disabled = layout.disable_layout(receipt, self.runtime, self.store)
        self.assertEqual(disabled["phase"], "DISABLED")
        self.assertEqual(self.runtime.events.count("remove-owned"), 1)
        self.assertEqual(len(disabled["owned"]["widgets"]), 6)
        layout.restore_layout(disabled, self.runtime, self.store)
        self.assertEqual({name: (self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)

    def test_cli_plan_update_is_read_only_and_update_uses_reviewed_plan(self):
        import contextlib
        import io
        import os
        from unittest import mock
        from scripts import caiodock
        parent_path = self.store._directory(self.parent)/"receipt.json"
        target = self.root/"update-plan.json"
        baseline = self.origin_pins()
        stops = self.runtime.events.count("stop")
        environment = {"XDG_CONFIG_HOME": str(self.config), "XDG_STATE_HOME": str(self.root)}
        with mock.patch.dict(os.environ, environment), mock.patch.object(layout, "NativeRuntime", return_value=self.runtime), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(caiodock.main(["layout", "plan-update", "--service", self.runtime.unit,
                "--receipt", str(parent_path), "--add", "control-center", "--output", str(target)]), 0)
            self.assertEqual(self.origin_pins(), baseline)
            self.assertEqual(self.runtime.events.count("stop"), stops)
            self.assertEqual(caiodock.main(["layout", "update", "--service", self.runtime.unit, "--plan", str(target)]), 0)
        self.assertEqual(self.store.current()["schemaVersion"], 2)
        self.assertEqual(self.runtime.events.count("update-owned"), 1)

    def test_native_update_adapter_emits_validated_plan_and_preserves_deadline(self):
        from unittest import mock
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        runtime = layout.NativeRuntime(self.runtime.unit)
        clock = lambda: 1.0
        with mock.patch.object(runtime, "_script", return_value={}) as dispatch:
            runtime.update_owned(plan, ready_deadline=4.0, clock=clock)
        source = dispatch.call_args.args[0]
        request = json.loads(source.split("const request = ", 1)[1].split(";", 1)[0])
        self.assertEqual(request, {"operation": "update-owned", "updatePlan": plan, "connector": "DP-1"})
        self.assertEqual(dispatch.call_args.kwargs, {"ready_deadline": 4.0, "clock": clock})

    def test_original_apply_cannot_piggyback_on_active_revision(self):
        self.committed_update()
        events = list(self.runtime.events)
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan, self.runtime, self.store)
        self.assertEqual(self.runtime.events.count("apply"), events.count("apply"))
        self.assertEqual(self.runtime.events.count("stop"), events.count("stop"))

    def test_preexisting_foreign_drift_survives_update_but_blocks_original_restore(self):
        for name in layout.CONFIG_FILES:
            path = self.config/name
            path.write_text(path.read_text() + "[UnknownNativeGroup]\nsetting=synthetic-later\n")
        pinned = self.origin_pins()
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        self.assertFalse(plan["restoreCompatible"])
        receipt = layout.update_layout(plan, self.runtime, self.store)
        current = {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES}
        stops = self.runtime.events.count("stop")
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, self.runtime, self.store)
        self.assertEqual(current, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})
        self.assertEqual(stops, self.runtime.events.count("stop"))
        self.assertEqual(pinned, self.origin_pins())

    def test_stop_flush_drift_refuses_before_script_and_recovers_service(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        stop = self.runtime.stop
        def flush():
            stop()
            path = self.config/layout.CONFIG_FILES[1]
            path.write_text(path.read_text() + "[LaterForeign]\nsetting=retained\n")
        with mock.patch.object(self.runtime, "stop", side_effect=flush), self.assertRaises(layout.LayoutError):
            layout.update_layout(plan, self.runtime, self.store)
        self.assertNotIn("update-owned", self.runtime.events)
        self.assertFalse(self.runtime.is_stopped)
        self.assertEqual(self.store.current(), self.parent)
        self.assertIn("[LaterForeign]", (self.config/layout.CONFIG_FILES[1]).read_text())

    def test_failed_backup_before_dispatch_recovers_service_without_target_mutation(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        files = {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES}
        capture = self.store._capture
        def fail_bank(directory):
            if directory is not None and directory.name == "update-before": raise OSError("synthetic bank failure")
            return capture(directory)
        with mock.patch.object(self.store, "_capture", side_effect=fail_bank), self.assertRaises(layout.LayoutError):
            layout.update_layout(plan, self.runtime, self.store)
        self.assertFalse(self.runtime.is_stopped)
        self.assertEqual(self.store.current(), self.parent)
        self.assertEqual(files, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})
        self.assertNotIn("update-owned", self.runtime.events)

    def interrupt_after_creation(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        update = self.runtime.update_owned
        def cut(plan):
            update(plan)
            raise Interrupted()
        with mock.patch.object(self.runtime, "update_owned", side_effect=cut), self.assertRaises(Interrupted):
            layout.update_layout(plan, self.runtime, self.store)
        return self.store.current()

    def test_interrupted_lost_reply_recovery_is_idempotent_without_script_replay(self):
        pinned = self.origin_pins()
        receipt = self.interrupt_after_creation()
        self.assertIsNone(receipt["owned"])
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, self.runtime, self.store)
        restored = layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        journal = layout.read_json(self.store._directory(receipt)/"receipt.json")
        starts = self.runtime.events.count("start")
        self.assertEqual(layout.restore_layout(journal, self.runtime, self.store, recover=True), restored)
        self.assertEqual(self.runtime.events.count("start"), starts)
        self.assertEqual(self.runtime.events.count("update-owned"), 1)
        self.assertEqual(pinned, self.origin_pins())

    def test_interrupted_recovery_refuses_later_existing_widget_edit_after_fresh_capture(self):
        receipt = self.interrupt_after_creation()
        path = self.config/layout.CONFIG_FILES[0]
        path.write_text(path.read_text() + "[Containments][100][Applets][200][ConfigDialog]\nDialogWidth=synthetic-later\n")
        files = {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES}
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        self.assertEqual(files, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})
        self.assertTrue(self.store.current()["recoveryPoints"][-1]["complete"])
        self.assertEqual(self.runtime.events.count("update-owned"), 1)

    def test_interrupted_recovery_refuses_foreign_later_widget(self):
        receipt = self.interrupt_after_creation()
        inspect = self.runtime.inspect
        def changed(connector=""):
            info = inspect(connector)
            info["panels"][0]["widgets"].append({"id": 777, "type": "org.orla.bar", "index": 1})
            return info
        files = {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES}
        with mock.patch.object(self.runtime, "inspect", side_effect=changed), self.assertRaises(layout.LayoutError):
            layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        self.assertEqual(files, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})
        self.assertTrue(self.store.current()["recoveryPoints"][-1]["complete"])

    def test_disable_lost_reply_rolls_back_latest_revision(self):
        receipt = self.committed_update()
        pinned = self.origin_pins()
        files = {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES}
        self.runtime.failure = "disable"
        with self.assertRaises(layout.LayoutError): layout.disable_layout(receipt, self.runtime, self.store)
        self.assertEqual(self.store.current()["phase"], "COMMITTED")
        self.assertEqual(files, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})
        self.assertEqual(pinned, self.origin_pins())
        self.assertFalse(self.runtime.is_stopped)

    def test_parent_activation_crash_resumes_without_service_restart(self):
        receipt = self.interrupt_after_creation()
        atomic = self.store._atomic
        def cut(path, data, *args):
            if path == self.store.state_home/"current.json" and json.loads(data)["schemaVersion"] == 1:
                raise Interrupted()
            return atomic(path, data, *args)
        with mock.patch.object(self.store, "_atomic", side_effect=cut), self.assertRaises(Interrupted):
            layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        current = self.store.current()
        self.assertEqual(current["phase"], "ROLLED_BACK")
        events = list(self.runtime.events)
        self.assertEqual(layout.restore_layout(current, self.runtime, self.store, recover=True), self.parent)
        self.assertEqual(self.runtime.events.count("start"), events.count("start"))
        self.assertEqual(self.runtime.events.count("stop"), events.count("stop"))

    def test_invalid_owned_reply_is_recovered_using_durable_marker(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        update = self.runtime.update_owned
        def invalid(plan):
            result = update(plan)
            result["widgets"][-1]["id"] = result["widgets"][0]["id"]
            return result
        with mock.patch.object(self.runtime, "update_owned", side_effect=invalid), self.assertRaises(layout.LayoutError):
            layout.update_layout(plan, self.runtime, self.store)
        self.assertEqual(self.store.current(), self.parent)
        self.assertFalse(self.runtime.is_stopped)
        self.assertEqual(self.runtime.events.count("update-owned"), 1)

    def test_parent_pointer_io_failure_retains_rolled_back_phase_for_retry(self):
        receipt = self.interrupt_after_creation()
        atomic = self.store._atomic
        def fail(path, data, *args):
            if path == self.store.state_home/"current.json" and json.loads(data)["schemaVersion"] == 1:
                raise OSError("synthetic parent pointer failure")
            return atomic(path, data, *args)
        with mock.patch.object(self.store, "_atomic", side_effect=fail), self.assertRaises(layout.LayoutError):
            layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        current = self.store.current()
        self.assertEqual(current["phase"], "ROLLED_BACK")
        events = list(self.runtime.events)
        layout.restore_layout(current, self.runtime, self.store, recover=True)
        self.assertEqual(self.runtime.events.count("start"), events.count("start"))
        self.assertEqual(self.runtime.events.count("stop"), events.count("stop"))

    def test_completed_rollback_recovery_still_validates_selected_service(self):
        receipt = self.interrupt_after_creation()
        layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        journal = layout.read_json(self.store._directory(receipt)/"receipt.json")
        self.runtime.unit = "foreign.service"
        self.runtime.identity["unit"] = "foreign.service"
        with self.assertRaises(layout.LayoutError): layout.restore_layout(journal, self.runtime, self.store, recover=True)

    def test_partial_marker_general_configuration_allows_rollback_but_not_commit(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        update = self.runtime.update_owned
        def partial(plan):
            result = update(plan)
            path = self.config/layout.CONFIG_FILES[0]
            path.write_text(path.read_text().replace("showControlCenter=true\n", ""))
            return result
        with mock.patch.object(self.runtime, "update_owned", side_effect=partial), self.assertRaises(layout.LayoutError):
            layout.update_layout(plan, self.runtime, self.store)
        self.assertEqual(self.store.current(), self.parent)
        self.assertEqual(self.runtime.events.count("update-owned"), 1)

    def test_later_foreign_drift_refuses_committed_restore_without_trusting_boolean(self):
        receipt = self.committed_update()
        self.assertTrue(receipt["restoreCompatible"])
        path = self.config/layout.CONFIG_FILES[1]
        path.write_text(path.read_text() + "[LaterForeign]\nsetting=synthetic-later\n")
        events = list(self.runtime.events)
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, self.runtime, self.store)
        self.assertEqual(events, self.runtime.events)
        self.assertIn("[LaterForeign]", path.read_text())

    def test_immutable_update_projection_tampering_refuses_lifecycle(self):
        receipt = self.committed_update()
        receipt["restoreCompatible"] = False
        events = list(self.runtime.events)
        with self.assertRaises(layout.LayoutError): layout.disable_layout(receipt, self.runtime, self.store)
        self.assertEqual(events, self.runtime.events)

    def test_plan_unknown_fields_and_rehashed_non_boolean_entry_refuse_before_effects(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        for change in ("unknown", "integer", "index", "origin", "version", "existence"):
            bad = copy.deepcopy(plan)
            if change == "unknown": bad["extra"] = 0
            elif change == "integer": bad["entry"]["config"]["showOrlaMenu"] = 0
            elif change == "index": bad["insertionIndex"] = 3
            elif change == "origin": bad["origin"]["transactionId"] = "u2-" + "a"*64 + "-" + "b"*16
            elif change == "version": bad["schemaVersion"] = True
            else: bad["baseline"][layout.CONFIG_FILES[0]] = {"exists": 0, "mode": None, "sha256": None}
            bad["planId"] = layout._hash({k:v for k,v in bad.items() if k != "planId"})
            events = list(self.runtime.events)
            with self.subTest(change=change), self.assertRaises(layout.LayoutError):
                layout.update_layout(bad, self.runtime, self.store)
            self.assertEqual(events, self.runtime.events)

    def test_parser_protects_native_semicolon_keys_and_refuses_ambiguous_syntax(self):
        from scripts.panel_layout_update import kconfig_groups
        self.assertEqual(kconfig_groups(b"[ActionPlugins][0]\nRightButton;NoModifier=synthetic.plugin\n")[("ActionPlugins", "0")],
                         {"RightButton;NoModifier": "synthetic.plugin"})
        for data in (b"[Group]\na=1\na=2\n", b"[Group]\n[Group]\n", b"[Group][$i]\na=1\n",
                     b"[Group\\x5d]\na=1\n", b"[Group]\na[$e]=1\n", b"[Group]\n\xff=1\n"):
            with self.subTest(data=data), self.assertRaises(layout.LayoutError): kconfig_groups(data)
        for name in layout.CONFIG_FILES:
            path = self.config/name
            baseline = path.read_bytes()
            path.write_bytes(baseline + b"[Ambiguous][$i]\nsetting=synthetic\n")
            stops = self.runtime.events.count("stop")
            with self.assertRaises(layout.LayoutError): layout.build_update_plan(self.parent, self.runtime, self.store)
            self.assertEqual(stops, self.runtime.events.count("stop"))
            path.write_bytes(baseline)

    def test_initial_update_refuses_parent_and_origin_tampering(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        for filename in ("receipt.json", "apply-receipt.json"):
            path = self.store._directory(self.parent)/filename
            data = path.read_bytes()
            path.write_bytes(data + b" ")
            events = list(self.runtime.events)
            with self.subTest(filename=filename), self.assertRaises(layout.LayoutError):
                layout.update_layout(plan, self.runtime, self.store)
            self.assertEqual(events.count("stop"), self.runtime.events.count("stop"))
            path.write_bytes(data)

    def test_frozen_v1_reader_and_restore_entry_reject_u2_before_effects(self):
        receipt = self.committed_update()
        frozen = FrozenV1Store(self.config, self.store.state_home)
        with self.assertRaises(layout.LayoutError): frozen._directory(receipt)
        with self.assertRaises(layout.LayoutError): frozen.current()
        events = list(self.runtime.events)
        with mock.patch.object(frozen, "restore_before") as replace, self.assertRaises(layout.LayoutError):
            # v1 restore entry preflights then resolves current before start/stop.
            layout._restore_layout_v1(receipt, self.runtime, frozen, recover=True)
        replace.assert_not_called()
        self.assertEqual(self.runtime.events.count("start"), events.count("start"))
        self.assertEqual(self.runtime.events.count("stop"), events.count("stop"))

    def test_unknown_receipt_versions_are_rejected_before_effects(self):
        receipt = self.committed_update()
        for version in (0, 3, True, "2"):
            bad = dict(receipt, schemaVersion=version)
            events = list(self.runtime.events)
            with self.subTest(version=version), self.assertRaises(layout.LayoutError):
                layout.restore_layout(bad, self.runtime, self.store, recover=True)
            self.assertEqual(events, self.runtime.events)
            with self.assertRaises(layout.LayoutError): self.store._directory(bad)
        pointer = self.store.state_home/"current.json"
        data = pointer.read_bytes()
        pointer.write_text(json.dumps(dict(receipt, schemaVersion=3)))
        with self.assertRaises(layout.LayoutError): self.store.current()
        pointer.write_bytes(data)

    def test_prepared_and_durable_intent_cuts_recover_without_creation(self):
        for stage_name in ("RESTART_FOR_APPLY", "APPLY_SCRIPT"):
            plan = layout.build_update_plan(self.parent, self.runtime, self.store)
            stage = layout._stage
            def cut(receipt, store, name):
                stage(receipt, store, name)
                if name == stage_name: raise Interrupted()
            with mock.patch.object(layout, "_stage", side_effect=cut), self.assertRaises(Interrupted):
                layout.update_layout(plan, self.runtime, self.store)
            receipt = self.store.current()
            self.assertEqual(layout.restore_layout(receipt, self.runtime, self.store, recover=True), self.parent)
        self.assertNotIn("update-owned", self.runtime.events)

    def test_first_update_before_replacement_cut_resumes_from_verified_bank(self):
        receipt = self.interrupt_after_creation()
        pinned = self.origin_pins()
        atomic = self.store._atomic
        fired = []
        def cut(path, data, *args):
            result = atomic(path, data, *args)
            if path == self.config/layout.CONFIG_FILES[0] and not fired:
                fired.append(True)
                raise Interrupted()
            return result
        with mock.patch.object(self.store, "_atomic", side_effect=cut), self.assertRaises(Interrupted):
            layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        current = self.store.current()
        self.assertEqual(current["stage"], "RECOVERY_REPLACE")
        self.assertEqual(layout.restore_layout(current, self.runtime, self.store, recover=True), self.parent)
        self.assertEqual(pinned, self.origin_pins())
        self.assertEqual(self.runtime.events.count("update-owned"), 1)

    def test_first_original_replacement_cut_resumes_and_preserves_origin(self):
        receipt = self.committed_update()
        pinned = self.origin_pins()
        atomic = self.store._atomic
        fired = []
        def cut(path, data, *args):
            result = atomic(path, data, *args)
            if path == self.config/layout.CONFIG_FILES[0] and not fired:
                fired.append(True)
                raise Interrupted()
            return result
        with mock.patch.object(self.store, "_atomic", side_effect=cut), self.assertRaises(Interrupted):
            layout.restore_layout(receipt, self.runtime, self.store)
        current = self.store.current()
        self.assertEqual(current["recoveryIntent"], "original")
        restored = layout.restore_layout(current, self.runtime, self.store, recover=True)
        self.assertEqual(restored["phase"], "RESTORED")
        self.assertEqual(self.original, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})
        self.assertEqual(pinned, self.origin_pins())

    def test_fresh_recovery_capture_failure_never_replaces_current_files(self):
        receipt = self.interrupt_after_creation()
        capture = self.store._capture
        def fail(directory):
            if directory is not None and directory.name.startswith("recovery-"):
                raise OSError("synthetic recovery bank failure")
            return capture(directory)
        with mock.patch.object(self.store, "_capture", side_effect=fail), mock.patch.object(self.store, "restore_before") as replace:
            with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, self.runtime, self.store, recover=True)
        replace.assert_not_called()
        self.assertFalse(self.store.current()["recoveryPoints"][-1]["complete"])
        self.assertIn("[Applets][900]", (self.config/layout.CONFIG_FILES[0]).read_text())

    def test_post_creation_restart_order_capture_and_commit_failures_rollback(self):
        for fault in ("restart", "order", "capture", "commit"):
            with self.subTest(fault=fault):
                plan = layout.build_update_plan(self.parent, self.runtime, self.store)
                files = {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES}
                pinned = self.origin_pins()
                fired = []
                start, order = self.runtime.start, layout._order_owned
                capture, save = self.store._capture, self.store.save
                def fail_restart():
                    if fault == "restart" and self.runtime.updated and not fired:
                        fired.append(True)
                        raise layout.LayoutError("synthetic restart failure")
                    return start()
                def fail_order(*args):
                    if fault == "order" and not fired:
                        fired.append(True)
                        raise layout.LayoutError("synthetic order readback failure")
                    return order(*args)
                def fail_capture(directory):
                    if fault == "capture" and directory is not None and directory.name == "after" and not fired:
                        fired.append(True)
                        raise OSError("synthetic after bank capture failure")
                    return capture(directory)
                def fail_commit(receipt):
                    if fault == "commit" and receipt["phase"] == "COMMITTED" and not fired:
                        fired.append(True)
                        raise OSError("synthetic commit publication failure")
                    return save(receipt)
                with mock.patch.object(self.runtime, "start", side_effect=fail_restart), \
                     mock.patch.object(layout, "_order_owned", side_effect=fail_order), \
                     mock.patch.object(self.store, "_capture", side_effect=fail_capture), \
                     mock.patch.object(self.store, "save", side_effect=fail_commit):
                    with self.assertRaises(layout.LayoutError): layout.update_layout(plan, self.runtime, self.store)
                self.assertTrue(fired)
                self.assertEqual(self.store.current(), self.parent)
                self.assertEqual(files, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})
                self.assertEqual(pinned, self.origin_pins())
                self.assertFalse(self.runtime.is_stopped)

    def test_modules_import_in_both_orders_without_circular_initialization(self):
        import subprocess
        for statement in ("import scripts.panel_layout_update; import scripts.panel_layout",
                          "import scripts.panel_layout; import scripts.panel_layout_update"):
            result = subprocess.run(["python3", "-B", "-c", statement], cwd=Path(__file__).parents[1],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_restore_does_not_overwrite_journal_changed_before_lock(self):
        from scripts import panel_layout_update as update
        receipt = self.committed_update()
        compatible = update._compatible
        changed = copy.deepcopy(receipt)
        changed["phase"] = "RECOVERY_REQUIRED"
        def race(*args):
            result = compatible(*args)
            self.store.save(changed)
            return result
        files = {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES}
        with mock.patch.object(update, "_compatible", side_effect=race), self.assertRaises(layout.LayoutError):
            layout.restore_layout(receipt, self.runtime, self.store)
        self.assertEqual(self.store.current(), changed)
        self.assertEqual(files, {n: (self.config/n).read_bytes() for n in layout.CONFIG_FILES})

    def test_disable_recovery_cannot_overwrite_later_existing_widget_settings(self):
        receipt = self.committed_update()
        path = self.config/layout.CONFIG_FILES[0]
        later = []
        def changed(*args, **kwargs):
            path.write_text(path.read_text() + "[Containments][100][Applets][200][ConfigDialog]\nDialogWidth=synthetic-later\n")
            later.append(path.read_bytes())
            raise layout.LayoutError("synthetic lost removal reply")
        with mock.patch.object(self.runtime, "remove_owned", side_effect=changed), self.assertRaises(layout.LayoutError):
            layout.disable_layout(receipt, self.runtime, self.store)
        self.assertEqual(path.read_bytes(), later[0])
        self.assertEqual(self.store.current()["phase"], "RECOVERY_REQUIRED")
        self.assertTrue(self.store.current()["recoveryPoints"][-1]["complete"])

    def test_wrong_and_duplicate_markers_refuse_unknown_recovery_without_replacement(self):
        receipt = self.interrupt_after_creation()
        path = self.config/layout.CONFIG_FILES[0]
        updated = path.read_text()
        token = receipt["updatePlan"]["planId"]
        for mode in ("wrong", "duplicate"):
            data = updated.replace("token=" + token, "token=" + "f"*64) if mode == "wrong" else updated + \
                "[Containments][100][Applets][901]\nplugin=org.orla.bar\n[Containments][100][Applets][901][Configuration][OrlaManagedUpdate]\ntoken=" + token + "\n"
            path.write_text(data)
            with self.subTest(mode=mode), mock.patch.object(self.store, "restore_before") as replace:
                with self.assertRaises(layout.LayoutError):
                    layout.restore_layout(self.store.current(), self.runtime, self.store, recover=True)
            replace.assert_not_called()
            self.assertEqual(path.read_text(), data)
            self.assertTrue(self.store.current()["recoveryPoints"][-1]["complete"])
        self.assertEqual(self.runtime.events.count("update-owned"), 1)

    def test_mode_drift_after_creation_retains_current_mode_and_requires_recovery(self):
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        update = self.runtime.update_owned
        path = self.config/layout.CONFIG_FILES[1]
        def mode_changed(plan):
            result = update(plan)
            path.chmod(0o600)
            return result
        with mock.patch.object(self.runtime, "update_owned", side_effect=mode_changed), self.assertRaises(layout.LayoutError):
            layout.update_layout(plan, self.runtime, self.store)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.current()["phase"], "RECOVERY_REQUIRED")
        self.assertTrue(self.store.current()["recoveryPoints"][-1]["complete"])
        self.assertIn("[Applets][900]", (self.config/layout.CONFIG_FILES[0]).read_text())

    def test_origin_absent_file_is_restored_as_absent_without_v2_copy(self):
        layout.restore_layout(self.parent, self.runtime, self.store)
        shell = self.config/layout.CONFIG_FILES[1]
        shell.unlink()
        self.parent = layout.apply_layout(self.plan, self.runtime, self.store)
        self.assertFalse(self.parent["before"][layout.CONFIG_FILES[1]]["exists"])
        pinned = self.origin_pins()
        receipt = self.committed_update()
        layout.restore_layout(receipt, self.runtime, self.store)
        self.assertFalse(shell.exists())
        self.assertEqual(pinned, self.origin_pins())
        self.assertFalse((self.store._directory(receipt)/"before").exists())

    def test_unicode_separators_in_foreign_value_cannot_hide_drift_inside_owned_projection(self):
        layout.restore_layout(self.parent, self.runtime, self.store)
        self.runtime.synthetic_label = "synthetic\u2028[Containments][100][HiddenProjection]\u2028state=old"
        path = self.config/layout.CONFIG_FILES[0]
        path.write_text(path.read_text().replace("label=synthetic\n", "label=" + self.runtime.synthetic_label + "\n"))
        self.parent = layout.apply_layout(self.plan, self.runtime, self.store)
        pinned = self.origin_pins()
        self.assertIn(b"state=old", (self.store._directory(self.parent)/"before"/layout.CONFIG_FILES[0]).read_bytes())
        path.write_text(path.read_text().replace("state=old", "state=new"))
        plan = layout.build_update_plan(self.parent, self.runtime, self.store)
        self.assertFalse(plan["restoreCompatible"])
        receipt = layout.update_layout(plan, self.runtime, self.store)
        current = path.read_bytes()
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, self.runtime, self.store)
        self.assertEqual(current, path.read_bytes())
        self.assertIn(b"state=new", current)
        self.assertEqual(pinned, self.origin_pins())

    def test_only_lf_and_crlf_form_kconfig_physical_lines(self):
        from scripts.panel_layout_update import kconfig_groups
        for separator in ("\u2028", "\u0085", "\u2029", "\r"):
            value = "synthetic" + separator + "[Containments][100][HiddenProjection]" + separator + "state=old"
            for newline in ("\n", "\r\n"):
                with self.subTest(separator=repr(separator), newline=repr(newline)):
                    groups = kconfig_groups(("[General]" + newline + "label=" + value + newline).encode())
                    self.assertEqual(groups, {(): {}, ("General",): {"label": value}})


if __name__ == "__main__": unittest.main()
