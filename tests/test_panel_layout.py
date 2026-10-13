import copy
import unittest

from scripts import panel_layout as layout


def manifest():
    return {
        "schemaVersion": 1, "preset": "mac-inspired-topbar", "mode": "dock-plus-bar",
        "screen": {"connector": "DP-1"},
        "panel": {"height": 32, "location": "top", "lengthMode": "fill",
                  "floating": False, "opacity": "opaque", "hiding": "none"},
        "replacePanelIds": [28], "reuseWidgetIds": {"tray": 7},
        "modules": [
            {"key": "menu", "enabled": True, "config": {"showMenuLabel": False, "compactHeight": True}},
            {"key": "global-menu", "enabled": True, "config": {"compactView": False, "allScreens": True}},
            {"key": "spacer", "enabled": True, "config": {}},
            {"key": "tray", "enabled": True, "config": {"controls": ["audio", "network"], "overflow": []}},
            {"key": "clock", "enabled": True, "config": {"showDate": False}},
        ],
    }


class ManifestTests(unittest.TestCase):
    def test_arbitrary_plugin_config_and_duplicate_modules_cannot_reach_plasma(self):
        invalid = []
        bad = manifest(); bad["modules"][0]["key"] = "evil-code()"; invalid.append(bad)
        bad = manifest(); bad["modules"][0]["config"]["script"] = "quit()"; invalid.append(bad)
        bad = manifest(); bad["modules"].append(copy.deepcopy(bad["modules"][0])); invalid.append(bad)
        bad = manifest(); bad["replacePanelIds"] = [True]; invalid.append(bad)
        bad = manifest(); bad["screen"]["connector"] = "DP-1\n"; invalid.append(bad)
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(layout.LayoutError):
                layout.validate_manifest(bad)


def inventory():
    return {"version": "6.7.5", "screenIds": [2, 7],
        "selectedScreen": {"id": 7, "connector": "DP-1", "geometry": {"x": 0, "y": 0, "width": 1600, "height": 900}},
        "knownWidgetTypes": sorted(set(layout.MODULE_IDS.values()) | set(layout.CONTROL_IDS.values())),
        "panels": [{"id": 28, "type": "org.kde.panel", "screen": 7, "height": 32,
            "widgets": [{"id": 35, "type": "org.orla.bar", "index": 0},
                        {"id": 7, "type": "org.kde.plasma.systemtray", "index": 1}],
            "marker": {"token": "", "schemaVersion": 0}}]}


def control_center_manifest():
    data = manifest()
    data["modules"].insert(-1, {"key": "control-center", "enabled": True,
        "config": {"showOrlaMenu": False, "showApplicationName": False, "showControlCenter": True}})
    return data


class ControlCenterManifestTests(unittest.TestCase):
    def test_opt_in_cc_only_and_old_manifest_roundtrip(self):
        old = manifest()
        self.assertEqual(layout.validate_manifest(old), old)
        data = control_center_manifest()
        self.assertEqual(layout.validate_plan(layout.build_plan(data, inventory()))["manifest"], data)
        self.assertEqual([m["key"] for m in data["modules"]][-3:], ["tray", "control-center", "clock"])

    def test_cc_config_refuses_other_presentation_or_arbitrary_keys(self):
        for config in ({"showOrlaMenu": True, "showApplicationName": False, "showControlCenter": True},
                       {"showOrlaMenu": False, "showApplicationName": True, "showControlCenter": True},
                       {"showOrlaMenu": False, "showApplicationName": False, "showControlCenter": False},
                       {"audio": True}, {"showControlCenter": "true"}):
            data = control_center_manifest(); data["modules"][-2]["config"] = config
            with self.subTest(config=config), self.assertRaises(layout.LayoutError):
                layout.validate_manifest(data)

    def test_default_preset_leaves_cc_disabled(self):
        import json
        from pathlib import Path
        data = json.loads((Path(__file__).parents[1] / "layouts/mac-inspired-topbar.json").read_text())
        cc = next(module for module in data["modules"] if module["key"] == "control-center")
        self.assertFalse(cc["enabled"])
        data["replacePanelIds"] = [28]; data["screen"]["connector"] = "DP-1"
        self.assertEqual(layout.validate_manifest(data), data)


class PlanningTests(unittest.TestCase):
    def test_sparse_connector_selection_and_editable_module_order(self):
        data = manifest(); data["modules"].reverse()
        plan = layout.build_plan(data, inventory())
        self.assertEqual(plan["screen"]["id"], 7)
        self.assertEqual([m["key"] for m in plan["manifest"]["modules"]], ["clock", "tray", "spacer", "global-menu", "menu"])
        self.assertEqual(layout.validate_plan(plan), plan)
        changed = copy.deepcopy(plan); changed["screen"]["id"] = 2
        with self.assertRaises(layout.LayoutError): layout.validate_plan(changed)

    def test_missing_version_monitor_widget_and_retained_dock_fail_before_mutation(self):
        for change in ("version", "monitor", "widget", "dock", "reuse"):
            info = inventory(); data = manifest()
            if change == "version": info["version"] = "6.7.6"
            if change == "monitor": info["selectedScreen"] = None
            if change == "widget": info["knownWidgetTypes"].remove("org.orla.bar")
            if change == "dock": info["panels"][0]["widgets"].append({"id": 40, "type": "org.caiodock.dock", "index": 2})
            if change == "reuse": data["reuseWidgetIds"]["tray"] = 35
            with self.subTest(change=change), self.assertRaises(layout.LayoutError):
                layout.build_plan(data, info)


class ScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def engine(self):
        from pathlib import Path
        from PySide6.QtQml import QJSEngine
        engine = QJSEngine()
        stub = Path(__file__).with_name("PanelLayoutStub.js")
        import json
        source = stub.read_text().replace("__TYPES__", json.dumps(inventory()["knownWidgetTypes"]))
        self.assertFalse(engine.evaluate(source).isError())
        return engine

    def test_cc_only_uses_second_plugin_instance_unique_id_right_order_and_disable(self):
        import json
        engine = self.engine(); data = control_center_manifest()
        # The menu and CC can independently reuse the same plugin type.
        data["reuseWidgetIds"]["menu"] = 35
        plan = layout.build_plan(data, inventory())
        result = engine.evaluate(layout.render_script("apply", plan=plan))
        self.assertFalse(result.isError(), result.toString())
        owned = json.loads(engine.evaluate("messages[0]").toString())
        bars = [w for w in owned["widgets"] if w["type"] == "org.orla.bar"]
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0]["id"], 35)
        self.assertNotEqual(bars[0]["id"], bars[1]["id"])
        self.assertEqual([w["index"] for w in bars], [0, 4])
        cc = bars[1]["id"]
        self.assertEqual(json.loads(engine.evaluate("JSON.stringify(panelById(" + str(owned["panelId"]) +
            ").widgetById(" + str(cc) + ").values)").toString()),
            {"General/showOrlaMenu": False, "General/showApplicationName": False, "General/showControlCenter": True})
        self.assertEqual(engine.evaluate("Object.keys(panelById(" + str(owned["panelId"]) +
            ").widgetById(35).values).sort().join(',')").toString(), "General/compactHeight,General/showMenuLabel")
        current = layout._managed_inventory(plan, owned)
        forged = copy.deepcopy(owned); forged["widgets"][4]["id"] = 35
        with self.assertRaises(layout.LayoutError): layout._managed_inventory(plan, forged)
        result = engine.evaluate(layout.render_script("remove-owned", panel_id=owned["panelId"],
            token=owned["token"], connector="DP-1", expected_inventory=current))
        self.assertFalse(result.isError(), result.toString())
        self.assertEqual(engine.evaluate("panels().length").toInt(), 0)

    def test_disabled_cc_changes_neither_old_widget_count_nor_old_configs(self):
        import json
        data = control_center_manifest(); data["modules"][-2]["enabled"] = False
        engine = self.engine(); plan = layout.build_plan(data, inventory())
        result = engine.evaluate(layout.render_script("apply", plan=plan))
        self.assertFalse(result.isError(), result.toString())
        owned = json.loads(engine.evaluate("messages[0]").toString())
        self.assertEqual(len(owned["widgets"]), 5)
        self.assertEqual(len([w for w in owned["widgets"] if w["type"] == "org.orla.bar"]), 1)
        self.assertEqual(json.loads(engine.evaluate("JSON.stringify(panels()[0].items[0].values)").toString()),
            {"General/showMenuLabel": False, "General/compactHeight": True})

    def test_real_fixed_script_moves_only_planned_widget_and_replaces_selected_panel(self):
        import json
        engine = self.engine()
        plan = json.loads(json.dumps(layout.build_plan(manifest(), inventory()), sort_keys=True))
        result = engine.evaluate(layout.render_script("apply", plan=plan))
        self.assertFalse(result.isError(), result.toString())
        receipt = json.loads(engine.evaluate("messages[0]").toString())
        self.assertEqual(receipt["screen"], 7)
        self.assertIn({"id": 7, "type": "org.kde.plasma.systemtray", "index": 3}, receipt["widgets"])
        self.assertEqual(engine.evaluate("JSON.stringify(removed)").toString(), "[28]")
        self.assertEqual(engine.evaluate("panels()[0].items[3].values['General/extraItems'].join(',')").toString(),
                         "org.kde.plasma.volume,org.kde.plasma.networkmanagement")
        self.assertFalse(receipt["nativeValidated"])

    def test_failed_creation_and_unplanned_drift_never_delete_displaced_panel(self):
        for setup in ('fakeFailType="org.kde.plasma.digitalclock"', 'fakeForeignChange=true'):
            engine = self.engine(); engine.evaluate(setup)
            result = engine.evaluate(layout.render_script("apply", plan=layout.build_plan(manifest(), inventory())))
            self.assertTrue(result.isError(), result.toString())
            self.assertEqual(engine.evaluate("JSON.stringify(removed)").toString(), "[]")


    def test_fixed_disable_script_requires_current_owned_identity_and_inventory(self):
        import json
        for fault in ("none", "token", "drift"):
            engine = self.engine()
            plan = layout.build_plan(manifest(),inventory())
            self.assertFalse(engine.evaluate(layout.render_script("apply",plan=plan)).isError())
            receipt = json.loads(engine.evaluate("messages[0]").toString())
            self.assertFalse(engine.evaluate(layout.render_script("inspect",connector="DP-1")).isError())
            current = json.loads(engine.evaluate("messages[messages.length-1]").toString())
            token = receipt["token"]
            if fault == "token": token = "0"*64
            if fault == "drift": engine.evaluate("panels()[0].items.push(makeWidget(88,'foreign.widget',panels()[0]))")
            result = engine.evaluate(layout.render_script("remove-owned",panel_id=receipt["panelId"],token=token,
                connector="DP-1",expected_inventory=current))
            self.assertEqual(result.isError(),fault != "none",result.toString())
            removed = json.loads(engine.evaluate("JSON.stringify(removed)").toString())
            self.assertEqual(removed,[28,receipt["panelId"]] if fault == "none" else [28])


class FakeRuntime:
    unit = "plasma-plasmashell.service"
    identity = {"unit": unit, "executable": "/usr/bin/plasmashell", "argv": "/usr/bin/plasmashell --no-respawn"}
    def __init__(self, config_home, failure=""):
        self.config_home = config_home; self.failure = failure
        self.identity = {**type(self).identity, "target": {"configHome": str(config_home.resolve())}}
        self.events = []; self.is_stopped = False; self.applied = False; self.disabled = False; self.plan = None
    def preflight(self, *, allow_stopped=False):
        self.events.append("preflight")
        if self.failure == "preflight": raise layout.LayoutError("capability unavailable")
    def inspect(self, connector=""):
        info = inventory()
        if self.applied:
            info["panels"] = [{"id": 100, "type": "org.kde.panel", "screen": 7, "height": 32,
                "widgets": self.owned()["widgets"], "marker": {"token": self.plan["planId"], "schemaVersion": 1}}]
        elif self.disabled:
            info["panels"] = []
        info["panels"].extend(copy.deepcopy(getattr(self,"extra_panels",[])))
        info["panels"].sort(key=lambda panel:panel["id"])
        return info
    def owned(self):
        return {"panelId": 100, "token": self.plan["planId"], "screen": 7, "height": 32,
            "widgets": [{"id": self.plan["manifest"]["reuseWidgetIds"].get(m["key"], 200+i), "type": layout.MODULE_IDS[m["key"]], "index": i}
                        for i,m in enumerate(self.plan["manifest"]["modules"]) if m["enabled"]], "nativeValidated": False}
    def stop(self): self.events.append("stop"); self.is_stopped = True
    def start(self):
        self.events.append("start"); self.is_stopped = False
        if (self.config_home/layout.CONFIG_FILES[0]).read_bytes().startswith(b"private original"):
            self.applied = False; self.disabled = False
        elif (self.config_home/layout.CONFIG_FILES[0]).read_bytes().startswith(b"disabled:"):
            self.applied = False; self.disabled = True
        else:
            self.applied = True; self.disabled = False
    def stopped(self): return self.is_stopped
    def apply(self, plan):
        self.events.append("apply"); self.plan = plan
        for name in layout.CONFIG_FILES: (self.config_home/name).write_bytes(b"modified:"+name.encode())
        if self.failure == "apply": raise layout.LayoutError("partial creation failure")
        self.applied = True; self.disabled = False
        return self.owned()
    def remove_owned(self, panel_id, token, expected_inventory):
        self.events.append("remove-owned")
        if self.inspect("DP-1") != expected_inventory or not self.applied or panel_id != 100 or token != self.plan["planId"]:
            raise layout.LayoutError("foreign panel")
        for name in layout.CONFIG_FILES: (self.config_home/name).write_bytes(b"disabled:"+name.encode())
        if self.failure == "disable": raise layout.LayoutError("uncertain remove failure")
        self.applied = False; self.disabled = True
        return {"removed":True}


class TransactionTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.config = self.root/"config"; self.config.mkdir()
        self.original = {}
        for name in layout.CONFIG_FILES:
            self.original[name] = ("private original "+name).encode()
            (self.config/name).write_bytes(self.original[name]); (self.config/name).chmod(0o640)
        self.store = layout.FileStore(self.config, self.root/"state")
        self.plan = layout.build_plan(manifest(), inventory())

    def test_partial_native_failure_restores_original_bytes_and_modes(self):
        runtime = FakeRuntime(self.config, "apply")
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan, runtime, self.store)
        for name,data in self.original.items():
            self.assertEqual((self.config/name).read_bytes(), data)
            self.assertEqual((self.config/name).stat().st_mode & 0o777, 0o640)
        self.assertFalse(runtime.is_stopped)
        self.assertEqual(self.store.current()["phase"], "RESTORED")

    def test_capability_failure_changes_no_configuration_or_journal(self):
        runtime = FakeRuntime(self.config, "preflight")
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan, runtime, self.store)
        self.assertEqual(runtime.events, ["preflight"])
        self.assertIsNone(self.store.current())
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)

    def test_completed_apply_is_idempotent_and_changed_layout_is_not_overwritten(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan, runtime, self.store)
        self.assertEqual(receipt["phase"], "COMMITTED")
        count = runtime.events.count("apply")
        self.assertEqual(layout.apply_layout(self.plan, runtime, self.store), receipt)
        self.assertEqual(runtime.events.count("apply"), count)
        (self.config/"plasmashellrc").write_bytes(b"user later changes")
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, runtime, self.store)
        self.assertEqual((self.config/"plasmashellrc").read_bytes(), b"user later changes")
        self.assertFalse(runtime.is_stopped)
        self.assertEqual(self.store.current()["phase"], "COMMITTED")

    def test_restore_preserves_absent_file_and_exact_existing_modes(self):
        (self.config/"plasmashellrc").unlink()
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan, runtime, self.store)
        layout.restore_layout(receipt, runtime, self.store)
        self.assertFalse((self.config/"plasmashellrc").exists())
        name = layout.CONFIG_FILES[0]
        self.assertEqual((self.config/name).read_bytes(), self.original[name])
        self.assertEqual((self.config/name).stat().st_mode & 0o777, 0o640)
        self.assertEqual(self.store.current()["phase"], "RESTORED")

    def test_foreign_panel_marker_and_modified_original_backup_block_restore(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan, runtime, self.store)
        before = self.store.state_home/receipt["transactionId"]/"before"/layout.CONFIG_FILES[1]
        before.write_bytes(b"corrupt backup")
        current = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, runtime, self.store)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, current)
        self.assertEqual(self.store.current()["phase"], "COMMITTED")


def fake_process(pid):
    import os
    return {"uid": os.getuid(), "startTick": 10, "home": "/private-fixture", "xdgConfigHome": "/private-fixture/config"}


class FakeCommands:
    def __init__(self):
        self.calls = []; self.active = True; self.version = "plasmashell 6.7.5"; self.owner = 42
        self.properties = {"LoadState":"loaded", "Type":"dbus", "BusName":"org.kde.plasmashell", "Result":"success", "NRestarts":"0",
            "ExecStart":"{ path=/usr/bin/plasmashell ; argv[]=/usr/bin/plasmashell --no-respawn ; }",
            "CanStart":"yes", "CanStop":"yes", "RefuseManualStart":"no", "RefuseManualStop":"no"}
    def __call__(self, argv, **kwargs):
        from types import SimpleNamespace
        self.calls.append((argv, kwargs))
        if argv[-1] == "--version": output = self.version
        elif "show" in argv:
            values = {**self.properties, "ActiveState":"active" if self.active else "inactive", "MainPID":"42" if self.active else "0"}
            output = "\n".join(key+"="+value for key,value in values.items())
        elif "stop" in argv: self.active = False; output = ""
        elif "start" in argv: self.active = True; output = ""
        elif "org.freedesktop.DBus.GetConnectionUnixProcessID" in argv: output = f"(uint32 {self.owner},)"
        elif "org.freedesktop.DBus.Properties.Get" in argv: output = "(<'"+getattr(self,"desktop_shell","org.kde.plasma.desktop")+"'>,)"
        elif "org.freedesktop.DBus.NameHasOwner" in argv: output = "(true,)" if self.active or getattr(self, "foreign_owner", False) else "(false,)"
        else:
            import json
            output = repr((json.dumps(inventory()),))
        return SimpleNamespace(returncode=0, stdout=output, stderr="private data must not escape")


class NativeContractTests(unittest.TestCase):
    def test_literal_service_and_current_bus_owner_are_required_before_mutation(self):
        for unit in ("--user.service", "/tmp/plasma.service", "plasma.service\n", "plasma service"):
            with self.subTest(unit=unit), self.assertRaises(layout.LayoutError): layout.NativeRuntime(unit)
        for key,value in (("CanStart","no"), ("CanStop","no"), ("RefuseManualStop","yes"),
                          ("Type","simple"), ("ExecStart","{ path=/bin/sh ; }")):
            commands = FakeCommands(); commands.properties[key] = value
            runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=commands, locate=lambda tool:tool, process_reader=fake_process, process_absent=lambda pid:True)
            with self.subTest(key=key), self.assertRaises(layout.LayoutError): runtime.preflight()
            self.assertFalse(any("start" in argv or "stop" in argv for argv,_ in commands.calls))
        commands = FakeCommands(); commands.owner = 999
        runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=commands, locate=lambda tool:tool, process_reader=fake_process, process_absent=lambda pid:True)
        with self.assertRaises(layout.LayoutError): runtime.preflight()

    def test_native_transport_has_fixed_destinations_and_bounded_no_shell_commands(self):
        commands = FakeCommands()
        runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=commands, locate=lambda tool:tool, process_reader=fake_process, process_absent=lambda pid:True)
        runtime.preflight(); runtime.inspect("DP-1"); runtime.stop(); runtime.start()
        for argv,kwargs in commands.calls:
            self.assertIsInstance(argv, list)
            self.assertNotIn("shell", kwargs)
            self.assertLessEqual(kwargs["timeout"], 45)
            if argv[0] == "gdbus":
                self.assertIn("--session", argv); self.assertIn("--timeout", argv)
            if argv[0] == "systemctl":
                self.assertIn("--user", argv); self.assertIn(runtime.unit, argv)
        self.assertTrue(commands.active)


class RecoveryTests(unittest.TestCase):
    setUp = TransactionTests.setUp
    def test_corrupt_backup_is_rejected_without_stopping_a_usable_current_shell(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan, runtime, self.store)
        before = self.store.state_home/receipt["transactionId"]/"before"/layout.CONFIG_FILES[0]
        before.write_bytes(b"corrupt")
        stops = runtime.events.count("stop")
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, runtime, self.store)
        self.assertFalse(runtime.is_stopped)
        self.assertEqual(runtime.events.count("stop"), stops)

    def test_explicit_recovery_can_admit_stopped_unit_but_not_a_foreign_bus_owner(self):
        commands = FakeCommands(); commands.active = False
        runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=commands, locate=lambda tool:tool, process_reader=fake_process, process_absent=lambda pid:True)
        runtime.preflight(allow_stopped=True)
        self.assertTrue(runtime.stopped())
        commands.foreign_owner = True
        with self.assertRaises(layout.LayoutError): runtime.preflight(allow_stopped=True)


class CliTests(unittest.TestCase):
    setUp = TransactionTests.setUp
    def test_bar_only_is_rejected_and_legacy_dock_parser_remains_independent(self):
        from scripts import caiodock
        data = manifest(); data["mode"] = "bar-only"
        with self.assertRaises(layout.LayoutError): layout.validate_manifest(data)
        self.assertEqual(caiodock.parser().parse_args(["uninstall"]).command, "uninstall")
        self.assertEqual(caiodock.parser().parse_args(["layout", "status", "--service", "plasma-plasmashell.service"]).layout_action, "status")

    def test_cli_plan_apply_restore_runs_only_the_injected_runtime_and_owned_files(self):
        import contextlib, io, json, os
        from unittest import mock
        from scripts import caiodock
        source = self.root/"manifest.json"; source.write_text(json.dumps(manifest()))
        plan = self.root/"plan.json"; runtime = FakeRuntime(self.config)
        env = {"XDG_CONFIG_HOME":str(self.config), "XDG_STATE_HOME":str(self.root/"cli-state")}
        with mock.patch.dict(os.environ, env), mock.patch.object(layout, "NativeRuntime", return_value=runtime), contextlib.redirect_stdout(io.StringIO()):
            common = ["--service", runtime.unit]
            self.assertEqual(caiodock.main(["layout", "plan", *common, "--manifest", str(source), "--output", str(plan)]), 0)
            self.assertFalse(runtime.applied)
            self.assertEqual(caiodock.main(["layout", "apply", *common, "--plan", str(plan)]), 0)
            store = layout.FileStore(self.config, self.root/"cli-state/orla/layouts")
            receipt = store._directory(store.current())/"receipt.json"
            self.assertEqual(caiodock.main(["layout", "disable", *common, "--receipt", str(receipt)]), 0)
            self.assertEqual(store.current()["phase"],"DISABLED")
            self.assertEqual(caiodock.main(["layout", "restore", *common, "--receipt", str(receipt)]), 0)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)


class FailureStageTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def test_reload_stop_and_after_snapshot_failures_recover_without_replaying_apply(self):
        from unittest import mock
        for stage in ("start:1", "start:2", "start:3", "stop:2", "stop:3", "after"):
            with self.subTest(stage=stage):
                runtime = FakeRuntime(self.config)
                store = layout.FileStore(self.config, self.root/stage.replace(":","-"))
                original_start,original_stop = runtime.start,runtime.stop
                counts = {"start":0, "stop":0}
                def start():
                    counts["start"] += 1
                    if stage == f"start:{counts['start']}": raise layout.LayoutError("bounded start failure")
                    original_start()
                def stop():
                    counts["stop"] += 1
                    original_stop()
                    if stage == f"stop:{counts['stop']}": raise layout.LayoutError("bounded stop failure")
                with mock.patch.object(runtime,"start",side_effect=start), mock.patch.object(runtime,"stop",side_effect=stop):
                    if stage == "after":
                        with mock.patch.object(store,"capture_after",side_effect=layout.LayoutError("snapshot failure")):
                            with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan,runtime,store)
                    else:
                        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan,runtime,store)
                self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
                self.assertLessEqual(runtime.events.count("apply"), 1)
                self.assertFalse(runtime.is_stopped)
                self.assertEqual(store.current()["phase"], "RESTORED")

    def test_interrupted_transaction_requires_explicit_recovery_and_preserves_journal(self):
        runtime = FakeRuntime(self.config)
        with self.store.lock():
            runtime.stop(); receipt = self.store.prepare(self.plan,runtime.unit,runtime.identity)
            receipt["phase"] = "APPLYING"; self.store.save(receipt)
            runtime.start(); runtime.apply(self.plan); runtime.stop()
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan,runtime,self.store)
        self.assertEqual(self.store.current()["phase"], "APPLYING")
        layout.restore_layout(receipt,runtime,self.store,recover=True)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},self.original)
        self.assertEqual(self.store.current()["phase"], "RESTORED")
        self.assertFalse(runtime.is_stopped)

    def test_backup_symlink_and_parallel_transaction_never_reach_native_apply(self):
        runtime = FakeRuntime(self.config)
        name = layout.CONFIG_FILES[0]
        target = self.root/"foreign"; target.write_bytes(b"keep foreign")
        (self.config/name).unlink(); (self.config/name).symlink_to(target)
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan,runtime,self.store)
        self.assertNotIn("apply", runtime.events)
        self.assertEqual(target.read_bytes(), b"keep foreign")
        self.assertFalse(runtime.is_stopped)
        (self.config/name).unlink(); (self.config/name).write_bytes(self.original[name])
        runtime.events.clear()
        with self.store.lock():
            with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan,runtime,self.store)
        self.assertNotIn("stop", runtime.events)

    def test_wrong_marker_and_changed_service_do_not_claim_idempotent_enable(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan,runtime,self.store)
        original_inspect = runtime.inspect
        def foreign(connector=""):
            info = original_inspect(connector); info["panels"][0]["marker"]["token"] = "foreign"
            return info
        from unittest import mock
        with mock.patch.object(runtime,"inspect",side_effect=foreign):
            with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan,runtime,self.store)
            with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt,runtime,self.store)
        runtime.identity = {**runtime.identity,"argv":"/usr/bin/plasmashell --replace"}
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan,runtime,self.store)


class StatusTests(unittest.TestCase):
    setUp = TransactionTests.setUp
    def test_status_exposes_reviewable_ids_and_never_starts_a_stopped_shell(self):
        import contextlib,io,os,json
        from unittest import mock
        from scripts import caiodock
        runtime = FakeRuntime(self.config)
        env = {"XDG_CONFIG_HOME":str(self.config),"XDG_STATE_HOME":str(self.root/"status-state")}
        for stopped in (False,True):
            runtime.is_stopped = stopped; output = io.StringIO()
            with mock.patch.dict(os.environ,env), mock.patch.object(layout,"NativeRuntime",return_value=runtime), contextlib.redirect_stdout(output):
                self.assertEqual(caiodock.main(["layout","status","--service",runtime.unit]),0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["liveInventoryAvailable"],not stopped)
            if not stopped:
                self.assertEqual(data["panels"][0]["id"],28)
                self.assertNotIn("marker",data["panels"][0])
            self.assertNotIn("start",runtime.events)
            self.assertFalse(data["nativeValidated"])


class DisableTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def test_disable_removes_only_owned_panel_and_retains_dock_and_original_recovery(self):
        runtime = FakeRuntime(self.config)
        dock = {"id":29,"type":"org.kde.panel","screen":7,"height":56,
            "widgets":[{"id":40,"type":"org.caiodock.dock","index":0}],"marker":{"token":"","schemaVersion":0}}
        runtime.extra_panels = [dock]
        plan = layout.build_plan(manifest(),runtime.inspect("DP-1"))
        receipt = layout.apply_layout(plan,runtime,self.store)
        before = copy.deepcopy(receipt["before"])
        disabled = layout.disable_layout(receipt,runtime,self.store)
        self.assertEqual(disabled["phase"],"DISABLED")
        self.assertEqual(runtime.inspect("DP-1")["panels"],[dock])
        self.assertEqual(disabled["before"],before)
        self.assertTrue((self.store._directory(disabled)/"apply-receipt.json").is_file())
        layout.disable_layout(disabled,runtime,self.store)
        self.assertEqual(runtime.events.count("remove-owned"),1)
        layout.restore_layout(disabled,runtime,self.store)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},self.original)

    def test_failed_disable_recovers_the_active_layout_not_original_baseline(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan,runtime,self.store)
        active = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        runtime.failure = "disable"
        with self.assertRaises(layout.LayoutError): layout.disable_layout(receipt,runtime,self.store)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},active)
        self.assertTrue(runtime.applied)
        self.assertEqual(self.store.current()["phase"],"COMMITTED")

    def test_changed_post_layout_refuses_disable_and_keeps_new_bytes(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan,runtime,self.store)
        (self.config/"plasmashellrc").write_bytes(b"new user layout")
        with self.assertRaises(layout.LayoutError): layout.disable_layout(receipt,runtime,self.store)
        self.assertNotIn("remove-owned",runtime.events)
        self.assertEqual((self.config/"plasmashellrc").read_bytes(),b"new user layout")
        self.assertFalse(runtime.is_stopped)

    def test_failed_disable_commit_rolls_back_active_bank_and_preserves_apply_link(self):
        from unittest import mock
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan,runtime,self.store)
        active = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        original = (self.store._directory(receipt)/"apply-receipt.json").read_bytes()
        save = self.store.save
        def fail_commit(value):
            if value["phase"] == "DISABLED": raise OSError("bounded commit failure")
            save(value)
        with mock.patch.object(self.store,"save",side_effect=fail_commit):
            with self.assertRaises(layout.LayoutError): layout.disable_layout(receipt,runtime,self.store)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},active)
        self.assertEqual((self.store._directory(receipt)/"apply-receipt.json").read_bytes(),original)
        self.assertEqual(self.store.current()["phase"],"COMMITTED")


class TargetBindingTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def test_wrong_caller_config_root_refuses_before_stop_backup_or_native_mutation(self):
        runtime = FakeRuntime(self.config)
        runtime.identity = {**runtime.identity, "target": {"configHome": str(self.config.resolve())}}
        wrong = layout.FileStore(self.root/"other-config", self.root/"other-state")
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan, runtime, wrong)
        self.assertNotIn("stop", runtime.events)
        self.assertNotIn("apply", runtime.events)
        self.assertFalse(wrong.state_home.exists())
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)

    def test_native_binding_uses_qt_absolute_path_rules_and_keeps_only_filtered_facts(self):
        for config, expected in (("/private-fixture/config", "/private-fixture/config"),
                                 ("relative-config", "/private-fixture/.config"), ("", "/private-fixture/.config")):
            facts = {**fake_process(42), "xdgConfigHome": config}
            commands = FakeCommands()
            runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=commands,
                locate=lambda tool:tool, process_reader=lambda pid:dict(facts), process_absent=lambda pid:True)
            runtime.preflight()
            self.assertEqual(runtime.identity["target"]["configHome"], expected)
            self.assertEqual(set(runtime.identity["target"]), {"uid","home","xdgConfigHome","configHome","shell","digest"})
            old = copy.deepcopy(runtime.identity)
            runtime.stop(); self.assertEqual(runtime.identity, old)
            runtime.start(); self.assertEqual(runtime.identity, old)

    def test_foreign_uid_unstable_process_wrong_shell_and_unreviewed_args_refuse(self):
        import os
        for fault in ("uid", "startTick", "shell", "argv", "home"):
            commands = FakeCommands(); reads = []
            def reader(pid):
                reads.append(pid); facts = fake_process(pid)
                if fault == "uid": facts["uid"] = os.getuid()+1
                if fault == "startTick": facts["startTick"] = len(reads)
                if fault == "home": facts["home"] = "relative-home"
                return facts
            if fault == "shell": commands.desktop_shell = "other-shell"
            if fault == "argv": commands.properties["ExecStart"] = "{ path=/usr/bin/plasmashell ; argv[]=/usr/bin/plasmashell --config other ; }"
            runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=commands,
                locate=lambda tool:tool, process_reader=reader, process_absent=lambda pid:True)
            with self.subTest(fault=fault), self.assertRaises(layout.LayoutError): runtime.preflight()
            self.assertFalse(any("start" in argv or "stop" in argv for argv,_ in commands.calls))

    def test_restart_target_drift_refuses_before_panel_mutation_and_preserves_backup(self):
        runtime = FakeRuntime(self.config)
        start = runtime.start
        def changed_start():
            start()
            runtime.identity["target"] = {"configHome": str(self.root/"foreign-config")}
            raise layout.LayoutError("configuration target changed")
        runtime.start = changed_start
        with self.assertRaises(layout.LayoutError): layout.apply_layout(self.plan, runtime, self.store)
        self.assertFalse(runtime.applied)
        receipt = self.store.current()
        self.assertEqual(receipt["phase"], "RECOVERY_REQUIRED")
        self.store.verify_backup(receipt)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)

    def test_stopped_recovery_rebinds_before_any_replacement_and_refuses_changed_target(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan, runtime, self.store)
        runtime.is_stopped = True
        current_bytes = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        start = runtime.start
        def changed_start():
            start(); runtime.identity["target"] = {"configHome": str(self.root/"foreign-config")}
        runtime.start = changed_start
        with self.assertRaises(layout.LayoutError): layout.restore_layout(receipt, runtime, self.store, recover=True)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, current_bytes)
        self.assertEqual(self.store.current(), receipt)
        self.store.verify_backup(receipt)

    def test_native_restart_rebind_refuses_changed_root_without_silently_retargeting(self):
        commands = FakeCommands(); facts = fake_process(42)
        runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=commands,
            locate=lambda tool:tool, process_reader=lambda pid:dict(facts), process_absent=lambda pid:True)
        runtime.preflight(); old = copy.deepcopy(runtime.identity); runtime.stop()
        facts["xdgConfigHome"] = "/different-fixture/config"
        with self.assertRaises(layout.LayoutError): runtime.start()
        self.assertEqual(runtime.identity, old)


class InterruptedRecoveryReviewTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def fail_second_replacement(self, receipt, runtime):
        from unittest import mock
        atomic = self.store._atomic
        def fail(path, data, mode=0o600):
            if path == self.config/layout.CONFIG_FILES[1]: raise OSError("injected second-file replacement failure")
            return atomic(path,data,mode)
        with mock.patch.object(self.store,"_atomic",side_effect=fail), self.assertRaises(layout.LayoutError):
            layout.restore_layout(receipt,runtime,self.store,recover=True)
        return self.store.current()

    def test_partial_original_recovery_retry_preserves_first_current_bank(self):
        runtime = FakeRuntime(self.config); runtime.stop()
        receipt = self.store.prepare(self.plan,runtime.unit,runtime.identity)
        receipt["phase"]="APPLYING"; self.store.save(receipt)
        runtime.start(); runtime.apply(self.plan)
        changed = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        (self.config/layout.CONFIG_FILES[0]).chmod(0o600)
        (self.config/layout.CONFIG_FILES[1]).unlink()
        receipt = self.fail_second_replacement(receipt,runtime)
        directory = self.store._directory(receipt)
        banks = {path:path.read_bytes() for path in directory.rglob("*")
                 if path.is_file() and any(part.startswith("recovery") for part in path.relative_to(directory).parts)}
        self.assertTrue(any(data==changed[layout.CONFIG_FILES[0]] for data in banks.values()))
        import json
        metadata = [json.loads(data) for path,data in banks.items() if path.name=="metadata.json"]
        self.assertEqual(len(metadata),1)
        self.assertTrue(metadata[0]["complete"])
        self.assertEqual(metadata[0]["files"][layout.CONFIG_FILES[0]]["mode"],0o600)
        self.assertEqual(metadata[0]["files"][layout.CONFIG_FILES[1]],{"exists":False,"mode":None,"sha256":None})
        applied_count = runtime.events.count("apply")
        layout.restore_layout(receipt,runtime,self.store,recover=True)
        for path,data in banks.items(): self.assertEqual(path.read_bytes(),data)
        self.assertEqual(runtime.events.count("apply"),applied_count)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},self.original)
        self.assertEqual(self.store.current()["phase"],"RESTORED")


    def test_disabled_original_restore_retry_uses_original_bank_not_active_bar(self):
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan,runtime,self.store)
        receipt = layout.disable_layout(receipt,runtime,self.store)
        receipt = self.fail_second_replacement(receipt,runtime)
        layout.restore_layout(receipt,runtime,self.store,recover=True)
        self.assertEqual(self.store.current()["phase"],"RESTORED")
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},self.original)

    def test_interrupted_disable_recovery_still_uses_active_bank_and_retains_attempt(self):
        from unittest import mock
        runtime=FakeRuntime(self.config)
        receipt=layout.apply_layout(self.plan,runtime,self.store)
        active={name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        runtime.failure="disable";atomic=self.store._atomic
        def fail(path,data,mode=0o600):
            if path==self.config/layout.CONFIG_FILES[1]: raise OSError("injected interrupted disable rollback")
            return atomic(path,data,mode)
        with mock.patch.object(self.store,"_atomic",side_effect=fail), self.assertRaises(layout.LayoutError):
            layout.disable_layout(receipt,runtime,self.store)
        pending=self.store.current()
        self.assertEqual(pending["phase"],"RECOVERY_REQUIRED")
        directory=self.store._directory(pending)
        banks={path:path.read_bytes() for path in directory.rglob("*")
               if path.is_file() and any(part.startswith("recovery") for part in path.relative_to(directory).parts)}
        runtime.failure=""
        layout.restore_layout(pending,runtime,self.store,recover=True)
        for path,data in banks.items(): self.assertEqual(path.read_bytes(),data)
        self.assertEqual(self.store.current()["phase"],"COMMITTED")
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},active)
        self.assertTrue(runtime.applied)
        self.assertEqual(runtime.events.count("apply"),1)

    def test_power_loss_after_each_durable_commit_write_allows_fresh_original_recovery(self):
        from unittest import mock
        import json
        class PowerLoss(BaseException): pass
        for boundary in (1,2,3):
            with self.subTest(boundary=boundary):
                config = self.root/("commit-config-"+str(boundary));config.mkdir()
                for name,data in self.original.items(): (config/name).write_bytes(data)
                store = layout.FileStore(config,self.root/("commit-state-"+str(boundary)))
                runtime = FakeRuntime(config); atomic=store._atomic; writes=[]
                def crash(path,data,mode=0o600):
                    result=atomic(path,data,mode)
                    if path.suffix==".json" and json.loads(data).get("phase")=="COMMITTED":
                        writes.append(path.name)
                        if len(writes)==boundary: raise PowerLoss()
                    return result
                with mock.patch.object(store,"_atomic",side_effect=crash), self.assertRaises(PowerLoss):
                    layout.apply_layout(self.plan,runtime,store)
                fresh=layout.FileStore(config,store.state_home)
                pending=fresh.current()
                runtime=FakeRuntime(config);runtime.plan=self.plan;runtime.applied=True
                layout.restore_layout(pending,runtime,fresh,recover=True)
                self.assertEqual(fresh.current()["phase"],"RESTORED")
                self.assertEqual({name:(config/name).read_bytes() for name in layout.CONFIG_FILES},self.original)
                self.assertNotIn("apply",runtime.events)

    def test_newer_transaction_journal_is_authoritative_after_pointer_write_loss(self):
        from unittest import mock
        class PowerLoss(BaseException): pass
        runtime=FakeRuntime(self.config)
        receipt=layout.apply_layout(self.plan,runtime,self.store)
        receipt["phase"]="RESTORING";receipt["operation"]="restore";receipt["recoveryIntent"]="original"
        atomic=self.store._atomic
        def crash(path,data,mode=0o600):
            result=atomic(path,data,mode)
            if path.name=="receipt.json": raise PowerLoss()
            return result
        with mock.patch.object(self.store,"_atomic",side_effect=crash), self.assertRaises(PowerLoss): self.store.save(receipt)
        fresh=layout.FileStore(self.config,self.store.state_home)
        self.assertEqual(fresh.current(),receipt)
        layout.restore_layout(fresh.current(),runtime,fresh,recover=True)
        self.assertEqual(fresh.current()["phase"],"RESTORED")


class TraySelectionReviewTests(unittest.TestCase):
    setUpClass = ScriptTests.setUpClass
    engine = ScriptTests.engine
    # Reuse the engine helper without inheriting the older cases.
    def test_reused_tray_keeps_application_visibility_and_replaces_only_native_controls(self):
        import json
        engine=self.engine()
        engine.evaluate("original.widgetById(7).values['General/shownItems']=['app.pinned','org.kde.plasma.bluetooth','org.kde.plasma.volume'];"+
                        "original.widgetById(7).values['General/hiddenItems']=['app.hidden','org.kde.plasma.battery','org.kde.plasma.networkmanagement'];")
        data=manifest();data["modules"][3]["config"]["overflow"]=["network"]
        result=engine.evaluate(layout.render_script("apply",plan=layout.build_plan(data,inventory())))
        self.assertFalse(result.isError(),result.toString())
        shown=json.loads(engine.evaluate("JSON.stringify(panels()[0].widgetById(7).values['General/shownItems'])").toString())
        hidden=json.loads(engine.evaluate("JSON.stringify(panels()[0].widgetById(7).values['General/hiddenItems'])").toString())
        self.assertEqual(shown,["app.pinned","org.kde.plasma.volume"])
        self.assertEqual(hidden,["app.hidden","org.kde.plasma.networkmanagement"])


class NativeFailureTraceReviewTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def test_failed_zero_pid_without_bus_owner_is_a_quiescent_recovery_state(self):
        commands=FakeCommands();commands.active=False
        original=commands.__call__
        def failed(argv,**kwargs):
            result=original(argv,**kwargs)
            if "show" in argv: result.stdout=result.stdout.replace("ActiveState=inactive","ActiveState=failed")
            return result
        runtime=layout.NativeRuntime("plasma-plasmashell.service",runner=failed,locate=lambda tool:tool,process_reader=fake_process, process_absent=lambda pid:True)
        runtime.preflight(allow_stopped=True)
        self.assertTrue(runtime.stopped())
        runtime.start()
        self.assertTrue(commands.active)

    def test_command_failure_facts_keep_operation_returncode_and_never_payloads(self):
        from types import SimpleNamespace
        secret="PRIVATE_TOOL_OUTPUT_DO_NOT_RETAIN"
        def fail(argv,**kwargs):return SimpleNamespace(returncode=6,stdout=secret,stderr=secret)
        runtime=layout.NativeRuntime("plasma-plasmashell.service",runner=fail,locate=lambda tool:tool,process_reader=fake_process, process_absent=lambda pid:True)
        with self.assertRaises(layout.LayoutError) as caught:runtime._command("systemctl",["--user","stop",runtime.unit])
        self.assertEqual(caught.exception.facts,{"code":"COMMAND_EXIT","operation":"UNIT_STOP","returncode":6})
        self.assertNotIn(secret,str(caught.exception.facts))

    def test_apply_and_recovery_failures_are_distinct_safe_journal_facts(self):
        runtime=FakeRuntime(self.config,"apply")
        stop=runtime.stop
        def fail_recovery():
            if "apply" in runtime.events:raise layout.LayoutError("PRIVATE_RECOVERY_MESSAGE_DO_NOT_RETAIN")
            return stop()
        runtime.stop=fail_recovery
        with self.assertRaises(layout.LayoutError):layout.apply_layout(self.plan,runtime,self.store)
        receipt=self.store.current()
        self.assertEqual(receipt["diagnostics"]["primary"]["stage"],"APPLY_SCRIPT")
        self.assertEqual(receipt["diagnostics"]["recovery"]["stage"],"RECOVERY_STOP")
        self.assertEqual(receipt["diagnostics"]["primary"]["code"],"LAYOUT_REFUSAL")
        self.assertEqual(receipt["diagnostics"]["recovery"]["code"],"LAYOUT_REFUSAL")
        self.assertNotIn("PRIVATE_RECOVERY_MESSAGE",str(receipt))

    def test_failed_quiescence_refuses_nonzero_pid_foreign_owner_and_present_previous_process(self):
        for fault in ("nonzero", "owner", "previous", "malformed-owner"):
            commands=FakeCommands();original=commands.__call__
            def failed(argv,**kwargs):
                result=original(argv,**kwargs)
                if not commands.active and "show" in argv:
                    result.stdout=result.stdout.replace("ActiveState=inactive","ActiveState=failed")
                    if fault=="nonzero":result.stdout=result.stdout.replace("MainPID=0","MainPID=42")
                if fault=="malformed-owner" and "org.freedesktop.DBus.NameHasOwner" in argv:result.stdout="false"
                return result
            runtime=layout.NativeRuntime("plasma-plasmashell.service",runner=failed,locate=lambda tool:tool,
                process_reader=fake_process,process_absent=lambda pid:fault!="previous")
            runtime.preflight();commands.active=False
            commands.foreign_owner=fault=="owner"
            with self.subTest(fault=fault), self.assertRaises(layout.LayoutError):runtime.preflight(allow_stopped=True)
            self.assertFalse(any("start" in argv or "stop" in argv for argv,_ in commands.calls))
            self.assertTrue(all("reset-failed" not in argv for argv,_ in commands.calls))

    def test_previous_pid_absence_accepts_only_explicit_not_found(self):
        from unittest import mock
        import stat
        from pathlib import Path
        from types import SimpleNamespace
        def probe(fault):
            def fixture(path,*args,**kwargs):
                if path==Path("/proc"):return SimpleNamespace(st_mode=stat.S_IFDIR)
                if fault=="absent":raise FileNotFoundError()
                if fault=="unknown":raise PermissionError("PRIVATE_PROBE_ERROR")
                return SimpleNamespace(st_mode=stat.S_IFDIR)
            return fixture
        with mock.patch("pathlib.Path.stat",autospec=True,side_effect=probe("absent")):
            self.assertTrue(layout.NativeRuntime._process_absent(42))
        with mock.patch("pathlib.Path.stat",autospec=True,side_effect=probe("unknown")), self.assertRaises(layout.LayoutError):
            layout.NativeRuntime._process_absent(42)
        with mock.patch("pathlib.Path.stat",autospec=True,side_effect=probe("present")):
            self.assertFalse(layout.NativeRuntime._process_absent(42))
        with mock.patch("pathlib.Path.stat",side_effect=FileNotFoundError()), self.assertRaises(layout.LayoutError):
            layout.NativeRuntime._process_absent(42)

    def test_post_restart_inventory_failure_keeps_only_hashes_and_exact_stage(self):
        runtime=FakeRuntime(self.config);inspect=runtime.inspect
        def changed(connector=""):
            result=inspect(connector)
            if runtime.events.count("start") == 1: result["panels"][0]["height"]=31
            return result
        runtime.inspect=changed
        with self.assertRaises(layout.LayoutError):layout.apply_layout(self.plan,runtime,self.store)
        facts=self.store.current()["diagnostics"]["primary"]
        self.assertEqual(facts["stage"],"INSPECT_AFTER_BACKUP")
        self.assertEqual(facts["code"],"INVENTORY_MISMATCH")
        self.assertNotEqual(facts["expectedSha256"],facts["actualSha256"])
        self.assertNotIn("panels",facts)
        self.assertEqual(self.store.current()["phase"],"RESTORED")


class DiagnosticPersistenceReviewTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def case_storage(self, boundary):
        self.config = self.root/("config-" + boundary); self.config.mkdir()
        for name, data in self.original.items():
            (self.config/name).write_bytes(data); (self.config/name).chmod(0o640)
        self.store = layout.FileStore(self.config, self.root/("state-" + boundary))

    def recorder_fault(self, kind, boundary):
        import json
        atomic = self.store._atomic
        injected = []
        def fail(path, data, mode=0o600):
            if path.name == boundary and kind in json.loads(data).get("diagnostics", {}) and not injected:
                injected.append(path.name)
                raise OSError(28, "PRIVATE_STORAGE_PAYLOAD", "/PRIVATE_STORAGE_FILENAME")
            return atomic(path, data, mode)
        return fail, injected

    def primary_runtime(self):
        runtime = FakeRuntime(self.config)
        apply = runtime.apply
        primary = layout.LayoutError("PRIVATE_PRIMARY_PAYLOAD", code="COMMAND_EXIT",
                                     operation="EVALUATE_SCRIPT", returncode=6)
        def fail(plan):
            apply(plan)
            raise primary
        runtime.apply = fail
        return runtime, primary

    def assert_safe_error(self, caught, cause):
        self.assertIs(caught.exception.__cause__, cause)
        self.assertNotIn("PRIVATE_", str(caught.exception))
        self.assertNotIn("PRIVATE_", str(getattr(caught.exception, "diagnostics", {})))

    def test_primary_recorder_write_failure_still_runs_guarded_original_rollback(self):
        from unittest import mock
        for boundary in ("receipt.json", "current.json"):
            with self.subTest(boundary=boundary):
                self.case_storage(boundary)
                runtime, primary = self.primary_runtime()
                fail, injected = self.recorder_fault("primary", boundary)
                with mock.patch.object(self.store, "_atomic", side_effect=fail), self.assertRaises(layout.LayoutError) as caught:
                    layout.apply_layout(self.plan, runtime, self.store)
                self.assert_safe_error(caught, primary)
                self.assertEqual(injected, [boundary])
                receipt = self.store.current()
                self.assertEqual(receipt["phase"], "RESTORED")
                self.assertEqual(receipt["diagnostics"]["primary"], {
                    "code":"COMMAND_EXIT", "operation":"EVALUATE_SCRIPT", "returncode":6, "stage":"APPLY_SCRIPT"})
                self.assertEqual(runtime.events.count("apply"), 1)
                self.assertEqual(runtime.events.count("stop"), 2)
                self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
                for name in layout.CONFIG_FILES: self.assertEqual((self.config/name).stat().st_mode & 0o777, 0o640)
                self.assertTrue(receipt["recoveryPoints"][0]["complete"])

    def test_recovery_recorder_write_failure_still_publishes_required_with_distinct_facts(self):
        from unittest import mock
        for boundary in ("receipt.json", "current.json"):
            with self.subTest(boundary=boundary):
                self.case_storage(boundary)
                runtime, primary = self.primary_runtime()
                stop = runtime.stop
                recovery = layout.LayoutError("PRIVATE_RECOVERY_PAYLOAD", code="COMMAND_EXIT",
                                              operation="UNIT_STOP", returncode=9)
                def fail_stop():
                    if "apply" in runtime.events:
                        runtime.events.append("refused-recovery-stop")
                        raise recovery
                    stop()
                runtime.stop = fail_stop
                fail, injected = self.recorder_fault("recovery", boundary)
                with mock.patch.object(self.store, "_atomic", side_effect=fail), self.assertRaises(layout.LayoutError) as caught:
                    layout.apply_layout(self.plan, runtime, self.store)
                self.assert_safe_error(caught, primary)
                self.assertEqual(injected, [boundary])
                receipt = self.store.current()
                self.assertEqual(receipt["phase"], "RECOVERY_REQUIRED")
                self.assertEqual(receipt["diagnostics"]["primary"]["stage"], "APPLY_SCRIPT")
                self.assertEqual(receipt["diagnostics"]["primary"]["returncode"], 6)
                self.assertEqual(receipt["diagnostics"]["recovery"], {
                    "code":"COMMAND_EXIT", "operation":"UNIT_STOP", "returncode":9, "stage":"RECOVERY_STOP"})
                self.assertEqual(runtime.events.count("refused-recovery-stop"), 1)
                self.assertEqual(runtime.events.count("apply"), 1)
                self.assertNotEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
                self.store.verify_backup(receipt)

    def test_restore_recorder_write_failure_still_finalizes_once_without_replaying_start(self):
        from unittest import mock
        for boundary in ("receipt.json", "current.json"):
            with self.subTest(boundary=boundary):
                self.case_storage(boundary)
                runtime = FakeRuntime(self.config)
                receipt = layout.apply_layout(self.plan, runtime, self.store)
                cause = layout.LayoutError("PRIVATE_RESTORE_PAYLOAD", code="COMMAND_EXIT", operation="UNIT_START", returncode=8)
                def fail_start():
                    runtime.events.append("refused-restore-start")
                    raise cause
                runtime.start = fail_start
                fail, injected = self.recorder_fault("recovery", boundary)
                with mock.patch.object(self.store, "_atomic", side_effect=fail), self.assertRaises(layout.LayoutError) as caught:
                    layout.restore_layout(receipt, runtime, self.store)
                self.assert_safe_error(caught, cause)
                self.assertEqual(injected, [boundary])
                current = self.store.current()
                self.assertEqual(current["phase"], "RECOVERY_REQUIRED")
                self.assertEqual(current["diagnostics"]["recovery"]["stage"], "RECOVERY_START")
                self.assertEqual(runtime.events.count("refused-restore-start"), 1)
                self.assertEqual(runtime.events.count("apply"), 1)
                self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)

    def test_permanent_storage_failure_refuses_before_recovery_mutation_and_retains_original_cause(self):
        from unittest import mock
        runtime, primary = self.primary_runtime()
        save = self.store.save
        failed_stages = []
        memory = []
        def fail(value):
            if value.get("diagnostics"):
                memory.append(copy.deepcopy(value))
                failed_stages.append((value["phase"], value["stage"]))
                raise OSError(28, "PRIVATE_STORAGE_PAYLOAD", "/PRIVATE_STORAGE_FILENAME")
            return save(value)
        with mock.patch.object(self.store, "save", side_effect=fail), self.assertRaises(layout.LayoutError) as caught:
            layout.apply_layout(self.plan, runtime, self.store)
        self.assert_safe_error(caught, primary)
        self.assertIn("storage unavailable", str(caught.exception))
        self.assertIn("durability unconfirmed", str(caught.exception))
        self.assertEqual(caught.exception.facts["code"], "FILESYSTEM_FAILURE")
        self.assertEqual(caught.exception.diagnostics["primary"]["stage"], "APPLY_SCRIPT")
        self.assertEqual(caught.exception.diagnostics["recovery"]["code"], "FILESYSTEM_FAILURE")
        self.assertEqual(caught.exception.diagnostics["recovery"]["stage"], "RECOVERY_STOP")
        self.assertEqual(failed_stages, [("APPLYING","APPLY_SCRIPT"), ("APPLYING","RECOVERY_STOP"),
                                        ("APPLYING","RECOVERY_STOP"), ("RECOVERY_REQUIRED","RECOVERY_STOP")])
        self.assertEqual(self.store.current()["phase"], "APPLYING")
        self.assertNotIn("diagnostics", self.store.current())
        self.assertEqual(runtime.events.count("stop"), 1)
        self.assertEqual(runtime.events.count("apply"), 1)
        self.assertNotIn("recoveryPoints", memory[-1])
        self.store.verify_backup(self.store.current())

    def test_restore_storage_unavailable_keeps_committed_conflict_and_safe_cause(self):
        from unittest import mock
        runtime = FakeRuntime(self.config)
        receipt = layout.apply_layout(self.plan, runtime, self.store)
        (self.config/layout.CONFIG_FILES[1]).write_bytes(b"private later layout")
        atomic = self.store._atomic
        def fail(path, data, mode=0o600):
            if path.name in ("receipt.json", "current.json"):
                raise OSError(28, "PRIVATE_STORAGE_PAYLOAD", "/PRIVATE_STORAGE_FILENAME")
            return atomic(path, data, mode)
        with mock.patch.object(self.store, "_atomic", side_effect=fail), self.assertRaises(layout.LayoutError) as caught:
            layout.restore_layout(receipt, runtime, self.store)
        self.assertIsInstance(caught.exception.__cause__, layout.LayoutError)
        self.assertNotIn("PRIVATE_", str(caught.exception))
        self.assertIn("storage unavailable", str(caught.exception))
        self.assertEqual(self.store.current()["phase"], "COMMITTED")
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertEqual((self.config/layout.CONFIG_FILES[1]).read_bytes(), b"private later layout")
        self.assertEqual(caught.exception.diagnostics["recovery"]["code"], "LAYOUT_REFUSAL")
        self.assertFalse(runtime.is_stopped)

    def test_failed_mandatory_recovery_stage_or_bank_is_not_swallowed(self):
        import json
        from unittest import mock
        for boundary in ("stage", "bank"):
            with self.subTest(boundary=boundary):
                self.case_storage(boundary)
                runtime, primary = self.primary_runtime()
                atomic = self.store._atomic
                injected = []
                def fail(path, data, mode=0o600):
                    stage = path.name == "receipt.json" and json.loads(data).get("stage") == "RECOVERY_STOP"
                    bank = path.name == "metadata.json" and path.parent.name.startswith("recovery-")
                    if ((boundary == "stage" and stage) or (boundary == "bank" and bank)) and not injected:
                        injected.append(boundary)
                        raise OSError("PRIVATE_MANDATORY_STORAGE")
                    return atomic(path, data, mode)
                with mock.patch.object(self.store, "_atomic", side_effect=fail), self.assertRaises(layout.LayoutError) as caught:
                    layout.apply_layout(self.plan, runtime, self.store)
                self.assert_safe_error(caught, primary)
                self.assertEqual(injected, [boundary])
                current = self.store.current()
                self.assertEqual(current["phase"], "RECOVERY_REQUIRED")
                self.assertEqual(current["diagnostics"]["recovery"]["code"], "FILESYSTEM_FAILURE")
                self.assertEqual(current["diagnostics"]["recovery"]["stage"],
                                 "RECOVERY_STOP" if boundary == "stage" else "RECOVERY_CAPTURE")
                self.assertNotEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
                self.assertEqual(runtime.events.count("apply"), 1)
                self.store.verify_backup(current)

    def test_cli_storage_refusal_never_prints_raw_oserror_payload(self):
        import contextlib, io, json, os
        from unittest import mock
        from scripts import caiodock
        runtime, primary = self.primary_runtime()
        plan = self.root/"plan.json"; plan.write_text(json.dumps(self.plan))
        output = io.StringIO()
        save = self.store.save
        def fail(value):
            if value.get("diagnostics"):
                raise OSError(28, "PRIVATE_STORAGE_PAYLOAD", "/PRIVATE_STORAGE_FILENAME")
            return save(value)
        env = {"XDG_CONFIG_HOME":str(self.config), "XDG_STATE_HOME":str(self.root/"state")}
        with mock.patch.dict(os.environ, env), mock.patch.object(layout, "NativeRuntime", return_value=runtime), \
             mock.patch.object(layout, "FileStore", return_value=self.store), mock.patch.object(self.store, "save", side_effect=fail), \
             contextlib.redirect_stderr(output):
            self.assertEqual(caiodock.main(["layout", "apply", "--service", runtime.unit, "--plan", str(plan)]), 1)
        self.assertIn("storage unavailable", output.getvalue())
        self.assertNotIn("PRIVATE_", output.getvalue())
        self.assertEqual(runtime.events.count("apply"), 1)



class StartupReadinessReviewTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def startup(self, replies=None):
        runtime = FakeRuntime(self.config)
        inspect = runtime.inspect
        transient = copy.deepcopy(self.plan["inventory"])
        transient["screenIds"] = []; transient["selectedScreen"] = None
        for panel in transient["panels"]: panel["screen"] = -1
        pending = list(replies) if replies is not None else [transient, self.plan["inventory"]]
        calls = []; now = [0.0]; pauses = []
        def read(connector=""):
            if runtime.events.count("start") != 1 or runtime.applied: return inspect(connector)
            calls.append(connector)
            reply = pending.pop(0) if len(pending) > 1 else pending[0]
            if callable(reply): reply = reply(runtime, now)
            if isinstance(reply, Exception): raise reply
            return copy.deepcopy(reply)
        def pause(seconds):
            pauses.append(seconds); now[0] += seconds
        runtime.inspect = read
        return runtime, transient, calls, now, pauses, pause

    def run_apply(self, runtime, now, pause):
        import inspect
        # Keep the regression behavioral against immutable Round4, whose public
        # transaction seam has no injected readiness clock yet.
        kwargs = {"clock":lambda:now[0], "pause":pause} if "clock" in inspect.signature(layout.apply_layout).parameters else {}
        return layout.apply_layout(self.plan, runtime, self.store, **kwargs)

    def assert_restored(self, runtime):
        receipt = self.store.current()
        self.assertEqual(receipt["phase"], "RESTORED")
        self.assertNotIn("apply", runtime.events)
        self.assertTrue(receipt["recoveryPoints"][0]["complete"])
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
        for name in layout.CONFIG_FILES: self.assertEqual((self.config/name).stat().st_mode & 0o777, 0o640)
        return receipt

    def test_observed_incomplete_then_exact_stable_inventory_allows_one_apply(self):
        runtime, transient, calls, now, pauses, pause = self.startup()
        expected = copy.deepcopy(self.plan)
        receipt = self.run_apply(runtime, now, pause)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertEqual(calls, ["DP-1", "DP-1"])
        self.assertEqual(pauses, [0.5])
        self.assertEqual(runtime.events.count("apply"), 1)
        self.assertEqual(self.plan, expected)
        self.assertEqual(receipt["plan"], expected)

    def test_perpetual_observed_incomplete_inventory_has_finite_timeout_and_safe_old_restore(self):
        runtime, transient, calls, now, pauses, pause = self.startup()
        runtime, _, calls, now, pauses, pause = self.startup([transient])
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
        receipt = self.assert_restored(runtime)
        self.assertEqual(receipt["diagnostics"]["primary"], {
            "code":"READINESS_TIMEOUT", "operation":"TRANSACTION", "returncode":None, "stage":"INSPECT_AFTER_BACKUP"})
        self.assertLessEqual(len(calls), 17)
        self.assertEqual(now[0], 8.0)

    def test_changed_inventory_and_nontransient_screen_shapes_refuse_without_pause(self):
        changes = ("widget", "plugin", "panel", "order", "height", "marker", "geometry", "connector",
                   "version", "partial-screen", "panel-screen")
        for fault in changes:
            with self.subTest(fault=fault):
                # Own config/state per subcase; never borrow a prior transaction.
                self.config = self.root/fault; self.config.mkdir()
                for name,data in self.original.items(): (self.config/name).write_bytes(data); (self.config/name).chmod(0o640)
                self.store = layout.FileStore(self.config, self.root/(fault+"-state"))
                runtime, transient, _, _, _, _ = self.startup()
                changed = copy.deepcopy(transient)
                if fault == "widget": changed["panels"][0]["widgets"][0]["id"] += 1
                if fault == "plugin": changed["knownWidgetTypes"].remove("org.orla.bar")
                if fault == "panel": changed["panels"][0]["id"] = 32
                if fault == "order": changed["panels"][0]["widgets"].reverse()
                if fault == "height": changed["panels"][0]["height"] += 1
                if fault == "marker": changed["panels"][0]["marker"]["token"] = "foreign"
                if fault == "version": changed["version"] = "6.7.6"
                if fault == "partial-screen": changed["screenIds"] = [7]
                if fault == "panel-screen": changed["panels"][0]["screen"] = 2
                if fault in ("geometry", "connector"):
                    changed = copy.deepcopy(self.plan["inventory"])
                    if fault == "geometry": changed["selectedScreen"]["geometry"]["width"] += 1
                    else: changed["selectedScreen"]["connector"] = "DP-2"
                runtime, _, calls, now, pauses, pause = self.startup([changed, self.plan["inventory"]])
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                self.assertEqual(self.assert_restored(runtime)["diagnostics"]["primary"]["code"], "INVENTORY_MISMATCH")
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])

    def test_command_protocol_and_identity_errors_are_never_retried(self):
        for fault in ("COMMAND_TIMEOUT", "COMMAND_EXIT", "COMMAND_IO", "SCRIPT_REPLY_INVALID", "OWNER_REPLY_INVALID",
                      "PID_REPLY_INVALID", "TARGET_CHANGED", "SERVICE_OWNER_MISMATCH", "PROCESS_BINDING_CHANGED"):
            with self.subTest(fault=fault):
                self.config = self.root/fault; self.config.mkdir()
                for name,data in self.original.items(): (self.config/name).write_bytes(data); (self.config/name).chmod(0o640)
                self.store = layout.FileStore(self.config, self.root/(fault+"-state"))
                cause = layout.LayoutError("private command refusal", code=fault, operation="EVALUATE_SCRIPT")
                runtime, _, calls, now, pauses, pause = self.startup([cause, self.plan["inventory"]])
                with self.assertRaises(layout.LayoutError) as caught: self.run_apply(runtime, now, pause)
                self.assertIs(caught.exception.__cause__, cause)
                self.assertEqual(self.assert_restored(runtime)["diagnostics"]["primary"]["code"], fault)
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])

    def test_deadline_boundary_and_inflight_inspection_overshoot_never_apply(self):
        for elapsed in (8.0, 18.0):
            with self.subTest(elapsed=elapsed):
                self.config = self.root/str(elapsed); self.config.mkdir()
                for name,data in self.original.items(): (self.config/name).write_bytes(data); (self.config/name).chmod(0o640)
                self.store = layout.FileStore(self.config, self.root/(str(elapsed)+"-state"))
                def late(runtime, now): now[0] = elapsed; return self.plan["inventory"]
                runtime, _, calls, now, pauses, pause = self.startup([late])
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                self.assertEqual(self.assert_restored(runtime)["diagnostics"]["primary"]["code"], "READINESS_TIMEOUT")
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])

    def test_attempt_bound_survives_nonadvancing_injected_clock(self):
        runtime, transient, _, _, _, _ = self.startup()
        runtime, _, calls, now, pauses, _ = self.startup([transient])
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, lambda seconds:pauses.append(seconds))
        self.assertEqual(self.assert_restored(runtime)["diagnostics"]["primary"]["code"], "READINESS_TIMEOUT")
        self.assertEqual(len(calls), 17); self.assertEqual(len(pauses), 16)

    def test_durable_apply_stage_expiration_refuses_before_native_mutation(self):
        runtime, _, calls, now, pauses, pause = self.startup([self.plan["inventory"]])
        save = self.store.save
        def late_save(receipt):
            save(receipt)
            if receipt["stage"] == "APPLY_SCRIPT": now[0] = 8.0
        self.store.save = late_save
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
        self.assertEqual(self.assert_restored(runtime)["diagnostics"]["primary"]["code"], "READINESS_TIMEOUT")
        self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])

    def test_native_binding_expiration_never_sends_mutating_evaluate_script(self):
        import inspect
        now = [0.0]; commands = FakeCommands()
        original = commands.__call__
        def runner(argv, **kwargs):
            result = original(argv, **kwargs)
            if "org.freedesktop.DBus.GetConnectionUnixProcessID" in argv: now[0] = 8.0
            return result
        runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=runner, locate=lambda tool:tool,
                                       process_reader=fake_process, process_absent=lambda pid:True)
        kwargs = {"ready_deadline":8.0, "clock":lambda:now[0]} if "ready_deadline" in inspect.signature(runtime.apply).parameters else {}
        with self.assertRaises(layout.LayoutError) as caught: runtime.apply(self.plan, **kwargs)
        self.assertEqual(caught.exception.facts["code"], "READINESS_TIMEOUT")
        self.assertFalse(any("org.kde.PlasmaShell.evaluateScript" in argv for argv,_ in commands.calls))

    def test_target_or_service_drift_after_readiness_inspection_refuses_immediately(self):
        for fault in ("target", "service"):
            with self.subTest(fault=fault):
                self.config = self.root/fault; self.config.mkdir()
                for name,data in self.original.items(): (self.config/name).write_bytes(data); (self.config/name).chmod(0o640)
                self.store = layout.FileStore(self.config, self.root/(fault+"-state"))
                def changed(runtime, now):
                    if fault == "target": runtime.identity["target"] = {"configHome":str(self.root/"foreign")}
                    else: runtime.identity["argv"] = "/usr/bin/plasmashell --replace"
                    return self.plan["inventory"]
                runtime, _, calls, now, pauses, pause = self.startup([changed])
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                self.assertNotIn("apply", runtime.events)
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])
                self.assertEqual(self.store.current()["phase"], "RECOVERY_REQUIRED")


class FinalRestartReadinessReviewTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def final_startup(self, replies=None, initial_transient=False):
        runtime = FakeRuntime(self.config)
        # Keep a second monitor's untouched panel in every final-stage case.
        runtime.extra_panels = [{"id":301, "type":"org.kde.panel", "screen":2, "height":48,
            "widgets":[{"id":401, "type":"unrelated.widget", "index":0}],
            "marker":{"token":"unrelated", "schemaVersion":0}}]
        self.plan = layout.build_plan(manifest(), runtime.inspect("DP-1"))
        inspect = runtime.inspect
        pending = list(replies) if replies is not None else ["transient", "ready"]
        calls = []; now = [0.0]; pauses = []; initial_reads = []
        def read(connector=""):
            actual = inspect(connector)
            if runtime.applied and runtime.events.count("start") == 3:
                calls.append(connector)
                reply = pending.pop(0) if len(pending) > 1 else pending[0]
                if callable(reply): return reply(runtime, now, actual)
                if isinstance(reply, Exception): raise reply
                if reply == "transient":
                    actual["screenIds"] = []; actual["selectedScreen"] = None
                    for panel in actual["panels"]: panel["screen"] = -1
            elif initial_transient and not runtime.applied and runtime.events.count("start") == 1:
                initial_reads.append(connector)
                if len(initial_reads) == 1:
                    actual["screenIds"] = []; actual["selectedScreen"] = None
                    for panel in actual["panels"]: panel["screen"] = -1
            return actual
        def pause(seconds): pauses.append(seconds); now[0] += seconds
        runtime.inspect = read
        return runtime, calls, now, pauses, pause, initial_reads

    def run_apply(self, runtime, now, pause):
        return layout.apply_layout(self.plan, runtime, self.store, clock=lambda:now[0], pause=pause)

    def assert_original_restored(self, runtime):
        receipt = self.store.current()
        self.assertEqual(receipt["phase"], "RESTORED")
        self.assertEqual(runtime.events.count("apply"), 1)
        self.assertTrue(receipt["recoveryPoints"][0]["complete"])
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
        for name in layout.CONFIG_FILES: self.assertEqual((self.config/name).stat().st_mode & 0o777, 0o640)
        self.store.verify_backup(receipt)
        return receipt

    def test_final_restart_only_transient_then_exact_ready_commits_with_one_apply(self):
        runtime, calls, now, pauses, pause, initial_reads = self.final_startup()
        original_plan = copy.deepcopy(self.plan)
        receipt = self.run_apply(runtime, now, pause)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertEqual(calls, ["DP-1", "DP-1"])
        self.assertEqual(pauses, [0.5])
        self.assertEqual(initial_reads, [])
        self.assertEqual(runtime.events.count("apply"), 1)
        self.assertEqual(receipt["plan"], original_plan)
        self.assertEqual(self.plan, original_plan)
        self.assertEqual(runtime.inspect("DP-1")["panels"][-1], original_plan["inventory"]["panels"][-1])

    def case_storage(self, name):
        self.config = self.root/name; self.config.mkdir()
        for filename, data in self.original.items():
            (self.config/filename).write_bytes(data); (self.config/filename).chmod(0o640)
        self.store = layout.FileStore(self.config, self.root/(name+"-state"))

    def test_exact_final_ready_commits_immediately_without_pause(self):
        runtime, calls, now, pauses, pause, _ = self.final_startup(["ready"])
        receipt = self.run_apply(runtime, now, pause)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertEqual(calls, ["DP-1"]); self.assertEqual(pauses, [])
        self.assertEqual(runtime.events.count("apply"), 1)

    def test_perpetual_final_transient_times_out_and_restores_immutable_original_bank(self):
        runtime, calls, now, pauses, pause, _ = self.final_startup(["transient"])
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
        receipt = self.assert_original_restored(runtime)
        self.assertEqual(receipt["diagnostics"]["primary"], {
            "code":"READINESS_TIMEOUT", "operation":"TRANSACTION", "returncode":None, "stage":"VERIFY_OWNED"})
        self.assertLessEqual(len(calls), 17); self.assertEqual(now[0], 8.0)
        self.assertEqual(len(pauses), 16); self.assertTrue(all(seconds == 0.5 for seconds in pauses))
        self.assertEqual(receipt["operation"], "restore"); self.assertEqual(receipt["recoveryIntent"], "original")

    def test_final_attempt_bound_survives_nonadvancing_injected_clock(self):
        runtime, calls, now, pauses, _, _ = self.final_startup(["transient"])
        with self.assertRaises(layout.LayoutError):
            self.run_apply(runtime, now, lambda seconds:pauses.append(seconds))
        self.assertEqual(self.assert_original_restored(runtime)["diagnostics"]["primary"]["code"], "READINESS_TIMEOUT")
        self.assertEqual(len(calls), 17); self.assertEqual(len(pauses), 16)
        self.assertEqual(now[0], 0.0)

    def test_final_readiness_uses_its_own_finite_stage_budget(self):
        runtime, calls, now, pauses, pause, initial_reads = self.final_startup(["transient"], initial_transient=True)
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
        self.assertEqual(self.assert_original_restored(runtime)["diagnostics"]["primary"]["code"], "READINESS_TIMEOUT")
        self.assertEqual(initial_reads, ["DP-1", "DP-1"])
        self.assertEqual(now[0], 8.5); self.assertLessEqual(len(calls), 17)
        self.assertEqual(len(pauses), 17)

    def test_final_inventory_drift_cannot_be_adopted_as_the_expected_baseline(self):
        faults = ("widget-id", "widget-type", "widget-index", "widget-order", "height", "panel-type", "panel-id",
                  "token", "schema", "geometry", "connector", "selected-screen", "panel-screen", "screen-ids",
                  "known-types", "version", "unrelated-height", "unrelated-widget", "unrelated-marker",
                  "unrelated-screen", "unrelated-absent", "unexpected-panel", "panel-order", "replaced-panel-retained")
        for fault in faults:
            with self.subTest(fault=fault):
                self.case_storage(fault)
                def changed(runtime, now, actual):
                    panel = actual["panels"][0]; unrelated = actual["panels"][1]
                    if fault == "widget-id": panel["widgets"][0]["id"] += 50
                    if fault == "widget-type": panel["widgets"][0]["type"] = "unplanned.widget"
                    if fault == "widget-index": panel["widgets"][0]["index"] = 6
                    if fault == "widget-order": panel["widgets"].reverse()
                    if fault == "height": panel["height"] += 1
                    if fault == "panel-type": panel["type"] = "unplanned.panel"
                    if fault == "panel-id": panel["id"] += 1
                    if fault == "token": panel["marker"]["token"] = "foreign"
                    if fault == "schema": panel["marker"]["schemaVersion"] = 0
                    if fault == "geometry": actual["selectedScreen"]["geometry"]["width"] += 1
                    if fault == "connector": actual["selectedScreen"]["connector"] = "DP-2"
                    if fault == "selected-screen": actual["selectedScreen"]["id"] = 2
                    if fault == "panel-screen": panel["screen"] = 2
                    if fault == "screen-ids": actual["screenIds"] = [7]
                    if fault == "known-types": actual["knownWidgetTypes"].append("unexpected.widget")
                    if fault == "version": actual["version"] = "6.7.6"
                    if fault == "unrelated-height": unrelated["height"] += 1
                    if fault == "unrelated-widget": unrelated["widgets"][0]["id"] += 1
                    if fault == "unrelated-marker": unrelated["marker"]["token"] = "changed"
                    if fault == "unrelated-screen": unrelated["screen"] = 7
                    if fault == "unrelated-absent": actual["panels"].pop()
                    if fault == "unexpected-panel":
                        extra = copy.deepcopy(unrelated); extra["id"] = 302; extra["widgets"][0]["id"] = 402
                        actual["panels"].append(extra)
                    if fault == "panel-order": actual["panels"].reverse()
                    if fault == "replaced-panel-retained": actual["panels"].insert(0, copy.deepcopy(self.plan["selectedPanels"][0]))
                    return actual
                runtime, calls, now, pauses, pause, _ = self.final_startup([changed, "ready"])
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                self.assert_original_restored(runtime)
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])

    def test_final_incomplete_projection_allows_no_other_drift(self):
        for fault in ("unrelated-height", "widget-order", "marker", "partial-screen", "one-assigned-panel"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                def changed(runtime, now, actual):
                    actual["screenIds"] = []; actual["selectedScreen"] = None
                    for panel in actual["panels"]: panel["screen"] = -1
                    if fault == "unrelated-height": actual["panels"][1]["height"] += 1
                    if fault == "widget-order": actual["panels"][0]["widgets"].reverse()
                    if fault == "marker": actual["panels"][0]["marker"]["token"] = "foreign"
                    if fault == "partial-screen": actual["screenIds"] = [7]
                    if fault == "one-assigned-panel": actual["panels"][1]["screen"] = 2
                    return actual
                runtime, calls, now, pauses, pause, _ = self.final_startup([changed, "ready"])
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                self.assert_original_restored(runtime)
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])

    def test_final_command_and_protocol_errors_refuse_without_retry(self):
        for fault in ("COMMAND_TIMEOUT", "COMMAND_EXIT", "COMMAND_IO", "SCRIPT_REPLY_INVALID", "OWNER_REPLY_INVALID",
                      "PID_REPLY_INVALID", "SERVICE_OWNER_MISMATCH", "PROCESS_BINDING_CHANGED"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                cause = layout.LayoutError("PRIVATE_FINAL_PAYLOAD", code=fault, operation="EVALUATE_SCRIPT")
                runtime, calls, now, pauses, pause, _ = self.final_startup([cause, "ready"])
                with self.assertRaises(layout.LayoutError) as caught: self.run_apply(runtime, now, pause)
                self.assertIs(caught.exception.__cause__, cause)
                receipt = self.assert_original_restored(runtime)
                self.assertEqual(receipt["diagnostics"]["primary"]["code"], fault)
                self.assertEqual(receipt["diagnostics"]["primary"]["stage"], "VERIFY_OWNED")
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])
                self.assertNotIn("PRIVATE_", str(receipt))

    def test_final_target_or_service_drift_refuses_before_wait_and_recovery_replacement(self):
        for fault in ("target", "service"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                def changed(runtime, now, actual):
                    if fault == "target": runtime.identity["target"] = {"configHome":str(self.root/"foreign")}
                    else: runtime.identity["argv"] = "/usr/bin/plasmashell --replace"
                    return actual
                runtime, calls, now, pauses, pause, _ = self.final_startup([changed, "ready"])
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                receipt = self.store.current()
                self.assertEqual(receipt["phase"], "RECOVERY_REQUIRED")
                self.assertEqual(receipt["diagnostics"]["primary"]["stage"], "VERIFY_OWNED")
                self.assertEqual(receipt["diagnostics"]["recovery"]["stage"], "RECOVERY_BIND")
                self.assertEqual(runtime.events.count("apply"), 1)
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])
                self.assertNotIn("recoveryPoints", receipt); self.store.verify_backup(receipt)
                self.assertNotEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)

    def test_final_deadline_and_inflight_read_overshoot_do_not_commit(self):
        for elapsed in (8.0, 18.0):
            with self.subTest(elapsed=elapsed):
                self.case_storage(str(elapsed))
                def late(runtime, now, actual): now[0] = elapsed; return actual
                runtime, calls, now, pauses, pause, _ = self.final_startup([late, "ready"])
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                receipt = self.assert_original_restored(runtime)
                self.assertEqual(receipt["diagnostics"]["primary"]["code"], "READINESS_TIMEOUT")
                self.assertEqual(receipt["diagnostics"]["primary"]["stage"], "VERIFY_OWNED")
                self.assertEqual(len(calls), 1); self.assertEqual(pauses, [])

    def test_managed_result_cannot_authorize_unplanned_modules_or_reuse_or_monitor(self):
        faults = ("token", "panel-id", "screen", "height", "native", "field", "widget-type", "widget-order",
                  "widget-index", "widget-count", "reuse", "undeclared-old-widget", "duplicate", "bool-index")
        for fault in faults:
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime, calls, now, pauses, pause, _ = self.final_startup(["ready"])
                apply = runtime.apply
                def changed(plan):
                    owned = apply(plan)
                    if fault == "token": owned["token"] = "foreign"
                    if fault == "panel-id": owned["panelId"] = 301
                    if fault == "screen": owned["screen"] = 2
                    if fault == "height": owned["height"] += 1
                    if fault == "native": owned["nativeValidated"] = True
                    if fault == "field": owned["unplanned"] = 1
                    if fault == "widget-type": owned["widgets"][0]["type"] = "unplanned.widget"
                    if fault == "widget-order": owned["widgets"].reverse()
                    if fault == "widget-index": owned["widgets"][0]["index"] = 6
                    if fault == "widget-count": owned["widgets"].pop()
                    if fault == "reuse": owned["widgets"][3]["id"] = 999
                    if fault == "undeclared-old-widget": owned["widgets"][0]["id"] = 35
                    if fault == "duplicate": owned["widgets"][0]["id"] = owned["widgets"][1]["id"]
                    if fault == "bool-index": owned["widgets"][0]["index"] = False
                    return owned
                runtime.apply = changed
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, now, pause)
                receipt = self.assert_original_restored(runtime)
                self.assertEqual(receipt["diagnostics"]["primary"]["stage"], "APPLY_SCRIPT")
                self.assertEqual(calls, []); self.assertEqual(pauses, [])


class NativeTraySequenceReviewTests(unittest.TestCase):
    setUpClass = ScriptTests.setUpClass
    engine = ScriptTests.engine

    def setUp(self):
        # Keep each Python QObject wrapper alive throughout QJSEngine evaluation.
        self.native_objects = []

    def native_engine(self, hidden=None, shown=None, variant=False):
        from PySide6.QtCore import QObject, Slot, qVersion
        self.assertIn(qVersion(), ("6.11.2", "6.12.0"))
        values = {"hiddenItems":[] if hidden is None else hidden, "shownItems":[] if shown is None else shown}
        class NativeTrayConfig(QObject):
            @Slot(str, result="QStringList")
            def strings(self, key): return values[key]
            @Slot(str, result="QVariantList")
            def variants(self, key): return values[key]
        engine = self.engine()
        native = NativeTrayConfig(engine)
        self.native_objects.append(native)
        engine.globalObject().setProperty("nativeTray", engine.newQObject(native))
        method = "variants" if variant else "strings"
        setup = engine.evaluate("fakeNativeTrayConfig=function(key,fallback){return nativeTray."+method+"(key);};")
        self.assertFalse(setup.isError(), setup.toString())
        return engine

    def apply(self, engine, overflow=False):
        data = manifest()
        if overflow: data["modules"][3]["config"]["overflow"] = ["network"]
        return engine.evaluate(layout.render_script("apply", plan=layout.build_plan(data, inventory())))

    def json_value(self, engine, source):
        import json
        result = engine.evaluate("JSON.stringify("+source+")")
        self.assertFalse(result.isError(), result.toString())
        return json.loads(result.toString())

    def assert_native_type(self, engine, key):
        source = "(function(){const value=fakeNativeTrayConfig("+repr(key)+",[]);return {type:typeof value,array:Array.isArray(value),tag:Object.prototype.toString.call(value),lengthType:typeof value.length,length:value.length};})()"
        metadata = self.json_value(engine, source)
        self.assertEqual(metadata, {"type":"object", "array":False, "tag":"[object V4Sequence]",
                                    "lengthType":"number", "length":metadata["length"]})
        return metadata["length"]

    def test_empty_real_qstringlist_and_qvariantlist_native_returns_allow_apply(self):
        for variant in (False, True):
            with self.subTest(variant=variant):
                engine = self.native_engine(variant=variant)
                self.assertEqual(self.assert_native_type(engine, "hiddenItems"), 0)
                self.assertEqual(self.assert_native_type(engine, "shownItems"), 0)
                result = self.apply(engine)
                self.assertFalse(result.isError(), result.toString())
                self.assertEqual(self.json_value(engine, "removed"), [28])
                self.assertEqual([entry["key"] for entry in self.json_value(engine, "trayConfigWrites")],
                                 ["extraItems", "hiddenItems", "shownItems", "showAllItems"])

    def assert_no_tray_writes(self, engine, result):
        self.assertTrue(result.isError(), result.toString())
        self.assertEqual(self.json_value(engine, "trayConfigWrites"), [])
        self.assertEqual(self.json_value(engine, "removed"), [])

    def test_real_single_sentinel_native_lists_preserve_exact_values(self):
        for variant in (False, True):
            with self.subTest(variant=variant):
                engine = self.native_engine(["ORLA_CONTRACT_SENTINEL"], ["ORLA_CONTRACT_SENTINEL"], variant)
                self.assertEqual(self.assert_native_type(engine, "hiddenItems"), 1)
                result = self.apply(engine, overflow=True)
                self.assertFalse(result.isError(), result.toString())
                writes = self.json_value(engine, "trayConfigWrites")
                self.assertEqual(writes[1]["value"], ["ORLA_CONTRACT_SENTINEL", "org.kde.plasma.networkmanagement"])
                self.assertEqual(writes[2]["value"], ["ORLA_CONTRACT_SENTINEL", "org.kde.plasma.volume"])

    def opaque_lists(self):
        hidden = ["org.thirdparty.tray", "statusnotifieritem-1-2", "literal,comma", "literal\\backslash",
                  "  spaces  ", "日本語😀", "", "duplicate", "duplicate", "in-both",
                  "org.kde.plasma.volume", "org.kde.plasma.battery"]
        shown = ["in-both", "org.thirdparty.pinned", "", "literal,comma", "literal\\backslash", "  spaces  ",
                 "日本語😀", "duplicate", "duplicate", "org.kde.plasma.bluetooth", "org.kde.plasma.networkmanagement"]
        expected_hidden = hidden[:-2] + ["org.kde.plasma.networkmanagement"]
        expected_shown = shown[:-2] + ["org.kde.plasma.volume"]
        return hidden, shown, expected_hidden, expected_shown

    def assert_opaque_preserved(self, engine):
        _, _, expected_hidden, expected_shown = self.opaque_lists()
        result = self.apply(engine, overflow=True)
        self.assertFalse(result.isError(), result.toString())
        writes = self.json_value(engine, "trayConfigWrites")
        self.assertEqual(writes, [
            {"key":"extraItems", "value":["org.kde.plasma.volume", "org.kde.plasma.networkmanagement"]},
            {"key":"hiddenItems", "value":expected_hidden},
            {"key":"shownItems", "value":expected_shown},
            {"key":"showAllItems", "value":False}])
        self.assertTrue(engine.evaluate("Array.isArray(trayConfigWrites[1].value)&&Array.isArray(trayConfigWrites[2].value)").toBool())
        self.assertEqual(self.json_value(engine, "removed"), [28])

    def test_populated_real_native_lists_preserve_opaque_ids_order_duplicates_and_overlap(self):
        hidden, shown, _, _ = self.opaque_lists()
        for variant in (False, True):
            with self.subTest(variant=variant):
                engine = self.native_engine(hidden, shown, variant)
                self.assertEqual(self.assert_native_type(engine, "hiddenItems"), len(hidden))
                self.assertEqual(self.assert_native_type(engine, "shownItems"), len(shown))
                self.assert_opaque_preserved(engine)
                # Copying/filtering must leave both actual native containers untouched.
                self.assertEqual(self.json_value(engine, "Array.prototype.slice.call(fakeNativeTrayConfig('hiddenItems',[]))"), hidden)
                self.assertEqual(self.json_value(engine, "Array.prototype.slice.call(fakeNativeTrayConfig('shownItems',[]))"), shown)
                self.assertFalse(engine.evaluate("trayConfigWrites[1].value===fakeNativeTrayConfig('hiddenItems',[])").toBool())

    def test_genuine_js_arrays_keep_exact_previous_visibility_behavior(self):
        import json
        hidden, shown, _, _ = self.opaque_lists()
        engine = self.engine()
        setup = engine.evaluate("original.widgetById(7).values['General/hiddenItems']="+json.dumps(hidden)+";"+
                                "original.widgetById(7).values['General/shownItems']="+json.dumps(shown)+";")
        self.assertFalse(setup.isError(), setup.toString())
        self.assert_opaque_preserved(engine)

    def test_either_invalid_native_qvariantlist_aborts_before_any_tray_write(self):
        for invalid in ([17], [None], [{"opaque":"object"}], ["valid", False], ["valid", ["nested"]]):
            for key in ("hiddenItems", "shownItems"):
                with self.subTest(invalid=invalid, key=key):
                    values = {"hiddenItems":["app.hidden"], "shownItems":["app.shown"]}
                    values[key] = invalid
                    engine = self.native_engine(values["hiddenItems"], values["shownItems"], variant=True)
                    self.assertEqual(self.assert_native_type(engine, key), len(invalid))
                    self.assert_no_tray_writes(engine, self.apply(engine))

    def invalid_js_engine(self, expression, key="shownItems"):
        engine = self.engine()
        source = "var reads=[];fakeNativeTrayConfig=function(key,fallback){reads.push(key);return key==="+repr(key)+"?"+expression+":['opaque.other'];};"
        result = engine.evaluate(source)
        self.assertFalse(result.isError(), result.toString())
        return engine

    def test_unsupported_container_values_refuse_without_default_clearing(self):
        cases = ["'one,two'", "''", "null", "undefined", "true", "42", "function(){}", "new String('boxed')",
                 "{}", "{0:'opaque',length:1}", "{length:0}"]
        for expression in cases:
            for key in ("hiddenItems", "shownItems"):
                with self.subTest(expression=expression, key=key):
                    engine = self.invalid_js_engine(expression, key)
                    self.assert_no_tray_writes(engine, self.apply(engine))
                    self.assertEqual(self.json_value(engine, "reads"),
                                     ["hiddenItems", "shownItems"] if key == "shownItems" else ["hiddenItems"])

    def test_sparse_or_nonstring_js_arrays_abort_before_any_tray_write(self):
        cases = ["new Array(1)", "['opaque',,]", "['opaque',17]", "['opaque',null]", "['opaque',undefined]",
                 "[new String('boxed')]", "[{}]", "[['nested']]",
                 "(function(){const value=new Array(1);Object.setPrototypeOf(value,{0:'prototype-only'});return value;})()"]
        for expression in cases:
            with self.subTest(expression=expression):
                engine = self.invalid_js_engine(expression)
                self.assert_no_tray_writes(engine, self.apply(engine))

    def test_invalid_or_changing_native_shape_lengths_and_throwing_access_refuse(self):
        # Synthetic hostile tag fixtures only test refusal after the versioned gate;
        # successful native acceptance is covered exclusively by real QObject slots.
        cases = ["({[Symbol.toStringTag]:'V4Sequence',length:"+length+",0:'opaque'})"
                 for length in ("-1", "0.5", "NaN", "Infinity", "'1'", "4097")]
        cases += ["({[Symbol.toStringTag]:'V4Sequence',length:1})",
                  "({[Symbol.toStringTag]:'V4Sequence',get length(){throw new Error('length');}})",
                  "({[Symbol.toStringTag]:'V4Sequence',length:1,get 0(){throw new Error('index');}})",
                  "(function(){let reads=0;return {[Symbol.toStringTag]:'V4Sequence',get length(){return ++reads===1?1:2;},0:'opaque'};})()",
                  "({get [Symbol.toStringTag](){throw new Error('tag');},length:0})"]
        for expression in cases:
            with self.subTest(expression=expression):
                engine = self.invalid_js_engine(expression)
                self.assert_no_tray_writes(engine, self.apply(engine))

    def test_real_native_length_bound_accepts_4096_and_refuses_4097_without_truncation(self):
        for variant in (False, True):
            for length in (4096, 4097):
                with self.subTest(variant=variant, length=length):
                    values = ["same.opaque"] * length
                    engine = self.native_engine(values, ["app.shown"], variant)
                    self.assertEqual(self.assert_native_type(engine, "hiddenItems"), length)
                    result = self.apply(engine)
                    if length == 4097:
                        self.assert_no_tray_writes(engine, result)
                    else:
                        self.assertFalse(result.isError(), result.toString())
                        self.assertEqual(self.json_value(engine, "trayConfigWrites[1].value"), values)


class AsyncOrderScriptTests(unittest.TestCase):
    setUpClass = ScriptTests.setUpClass
    engine = ScriptTests.engine

    def test_cc_duplicate_plugin_instances_reorder_by_applet_id(self):
        import json
        engine = self.engine(); engine.evaluate("fakeDelayedOrder=true;fakeNativeEnumeration=true")
        data = control_center_manifest(); data["reuseWidgetIds"]["menu"] = 35
        plan = layout.build_plan(data, inventory())
        result = engine.evaluate(layout.render_script("apply", plan=plan))
        self.assertFalse(result.isError(), result.toString())
        owned = json.loads(engine.evaluate("messages[messages.length-1]").toString())
        engine.evaluate("readyOrder(panels()[0])")
        current = self.read(engine)
        self.assertNotEqual(current["panels"][0]["widgets"], owned["widgets"])
        result = engine.evaluate(self.reorder_source(owned, current))
        self.assertFalse(result.isError(), result.toString())
        self.assertEqual(self.read(engine)["panels"][0]["widgets"], owned["widgets"])
        self.assertEqual([widget["id"] for widget in owned["widgets"] if widget["type"] == "org.orla.bar"][0], 35)

    def test_initial_apply_succeeds_with_uninitialized_id_sorted_widgets_without_index_setters(self):
        import json
        engine = self.engine()
        engine.evaluate("fakeDelayedOrder=true;fakeNativeEnumeration=true")
        plan = layout.build_plan(manifest(), inventory())
        result = engine.evaluate(layout.render_script("apply", plan=plan))
        self.assertFalse(result.isError(), result.toString())
        owned = json.loads(engine.evaluate("messages[messages.length-1]").toString())
        self.assertEqual([widget["index"] for widget in owned["widgets"]], list(range(5)))
        self.assertFalse(owned["nativeValidated"])
        self.assertEqual(engine.evaluate("JSON.stringify(indexWrites)").toString(), "[]")
        self.assertEqual(engine.evaluate("JSON.stringify(removed)").toString(), "[28]")
        engine.evaluate(layout.render_script("inspect", connector="DP-1"))
        current = json.loads(engine.evaluate("messages[messages.length-1]").toString())
        self.assertEqual([widget["index"] for widget in current["panels"][0]["widgets"]], [-1]*5)
        self.assertEqual([widget["id"] for widget in current["panels"][0]["widgets"]],
                         sorted(widget["id"] for widget in owned["widgets"]))


    def ready_fixture(self):
        import json
        engine = self.engine(); engine.evaluate("fakeDelayedOrder=true;fakeNativeEnumeration=true")
        result = engine.evaluate(layout.render_script("apply", plan=layout.build_plan(manifest(), inventory())))
        self.assertFalse(result.isError(), result.toString())
        owned = json.loads(engine.evaluate("messages[messages.length-1]").toString())
        engine.evaluate("readyOrder(panels()[0])")
        return engine, owned

    def read(self, engine):
        import json
        self.assertFalse(engine.evaluate(layout.render_script("inspect", connector="DP-1")).isError())
        return json.loads(engine.evaluate("messages[messages.length-1]").toString())

    def reorder_source(self, owned, current, **overrides):
        arguments = dict(panel_id=owned["panelId"], token=owned["token"], connector="DP-1",
                         expected_inventory=current, ordered_widgets=owned["widgets"])
        arguments.update(overrides)
        return layout.render_script("reorder-owned", **arguments)

    def test_supported_prefix_setters_fix_every_dense_permutation_without_config_writes(self):
        import itertools, json
        engine, owned = self.ready_fixture()
        config = engine.evaluate("JSON.stringify({panel:panels()[0].values,tray:trayConfigWrites})").toString()
        ids = [widget["id"] for widget in owned["widgets"]]
        for permutation in itertools.permutations(ids):
            engine.evaluate("panels()[0].layoutOrder="+json.dumps(permutation)+";indexWrites=[]")
            result = engine.evaluate(self.reorder_source(owned, self.read(engine)))
            self.assertFalse(result.isError(), result.toString())
            self.assertEqual(self.read(engine)["panels"][0]["widgets"], owned["widgets"])
            writes = json.loads(engine.evaluate("JSON.stringify(indexWrites)").toString())
            self.assertEqual(writes, [{"id":widget_id,"index":index,"ready":True} for index,widget_id in enumerate(ids[:-1])])
            self.assertEqual(engine.evaluate("JSON.stringify({panel:panels()[0].values,tray:trayConfigWrites})").toString(), config)

    def test_exact_full_inventory_gate_and_owned_lookup_refuse_without_any_setter(self):
        for fault in ("foreign-panel", "member", "marker", "order"):
            with self.subTest(fault=fault):
                engine, owned = self.ready_fixture()
                current = self.read(engine)
                script = self.reorder_source(owned, current)
                if fault == "foreign-panel": engine.evaluate("var foreign=new Panel('org.kde.panel');foreign.id=301")
                if fault == "member": engine.evaluate("panels()[0].items[0].type='foreign.widget'")
                if fault == "marker": engine.evaluate("panels()[0].values['OrlaManaged/token']='foreign'")
                if fault == "order": engine.evaluate("panels()[0].layoutOrder.reverse()")
                result = engine.evaluate(script)
                self.assertTrue(result.isError(), result.toString())
                self.assertEqual(engine.evaluate("JSON.stringify(indexWrites)").toString(), "[]")

    def test_render_reorder_refuses_malformed_pending_membership_or_identity(self):
        engine, owned = self.ready_fixture()
        current = self.read(engine)
        for fault in ("panel-id", "token", "connector", "pending", "dense", "target-id", "target-type", "target-index", "target-count"):
            with self.subTest(fault=fault):
                arguments = {}; altered = copy.deepcopy(current); target = copy.deepcopy(owned["widgets"])
                if fault == "panel-id": arguments["panel_id"] = True
                if fault == "token": arguments["token"] = "0"*64
                if fault == "connector": arguments["connector"] = "DP-2"
                if fault == "pending":
                    for widget in altered["panels"][0]["widgets"]: widget["index"] = -1
                if fault == "dense": altered["panels"][0]["widgets"][0]["index"] = 6
                if fault == "target-id": target[0]["id"] += 999
                if fault == "target-type": target[0]["type"] = "foreign.widget"
                if fault == "target-index": target[0]["index"] = False
                if fault == "target-count": target.pop()
                arguments["ordered_widgets"] = target
                with self.assertRaises(layout.LayoutError): self.reorder_source(owned, altered, **arguments)


class SyntheticDelayedOrderRuntime(FakeRuntime):
    """Offline boundary model; never evidence of real Plasma/visual readiness."""
    def __init__(self, config_home, *, pending_reads=1, reorder_effect=True, ack=None):
        super().__init__(config_home)
        self.pending_reads = pending_reads; self.order_reads = []; self.order_requests = []
        self.reorder_effect = reorder_effect; self.ack = {"reordered":True} if ack is None else ack
        self.current_widgets = None; self.after_read = None

    def inspect(self, connector=""):
        actual = super().inspect(connector)
        if self.applied and self.current_widgets is not None:
            panel = next(panel for panel in actual["panels"] if panel["id"] == 100)
            if self.events.count("start") == 2:
                self.order_reads.append(connector)
                if len(self.order_reads) > self.pending_reads and not self.order_requests:
                    ordered = sorted(self.owned()["widgets"], key=lambda widget:widget["id"])
                    self.current_widgets = [{**widget,"index":index} for index,widget in enumerate(ordered)]
            panel["widgets"] = copy.deepcopy(self.current_widgets)
            if self.after_read and self.events.count("start") == 2: self.after_read(actual)
        return actual

    def apply(self, plan):
        owned = super().apply(plan)
        self.current_widgets = [{**widget,"index":-1} for widget in sorted(owned["widgets"], key=lambda widget:widget["id"])]
        return owned

    def reorder_owned(self, panel_id, token, expected_inventory, ordered_widgets):
        self.events.append("reorder-owned")
        self.order_requests.append(copy.deepcopy(expected_inventory))
        self.last_order = copy.deepcopy(ordered_widgets)
        if panel_id != 100 or token != self.plan["planId"]: raise layout.LayoutError("foreign owned reorder")
        if self.reorder_effect: self.current_widgets = copy.deepcopy(ordered_widgets)
        return self.ack


class AsyncOrderTransactionTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def run_apply(self, runtime, *, clock=None, pause=None):
        return layout.apply_layout(self.plan, runtime, self.store,
                                  clock=clock or (lambda:0.0), pause=pause or (lambda seconds:None))

    def assert_restored(self, runtime, stage=None, code=None):
        receipt = self.store.current()
        self.assertEqual(receipt["phase"], "RESTORED")
        self.assertEqual(runtime.events.count("apply"), 1)
        self.assertFalse(runtime.is_stopped)
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
        for name in layout.CONFIG_FILES: self.assertEqual((self.config/name).stat().st_mode & 0o777, 0o640)
        self.store.verify_backup(receipt)
        if stage: self.assertEqual(receipt["diagnostics"]["primary"]["stage"], stage)
        if code: self.assertEqual(receipt["diagnostics"]["primary"]["code"], code)
        return receipt

    def test_delayed_id_sorted_boundary_reorders_before_save_and_commits_strict_order(self):
        runtime = SyntheticDelayedOrderRuntime(self.config)
        pauses = []
        receipt = self.run_apply(runtime, pause=pauses.append)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertFalse(receipt["owned"]["nativeValidated"])
        self.assertEqual(runtime.order_reads, ["DP-1"]*3)
        self.assertEqual(pauses, [0.5, 0.5])
        self.assertEqual(len(runtime.order_requests), 1)
        self.assertEqual(runtime.last_order, receipt["owned"]["widgets"])
        self.assertLess(runtime.events.index("reorder-owned"),
                        [index for index,event in enumerate(runtime.events) if event == "stop"][2])
        self.assertEqual(runtime.inspect("DP-1"), layout._managed_inventory(self.plan, receipt["owned"]))


    case_storage = FinalRestartReadinessReviewTests.case_storage

    def test_exact_already_ordered_inventory_skips_optional_reorder_capability(self):
        runtime = FakeRuntime(self.config)
        self.assertFalse(hasattr(runtime, "reorder_owned"))
        receipt = self.run_apply(runtime)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertNotIn("reorder-owned", runtime.events)

    def test_membership_shapes_and_unrelated_inventory_drift_refuse_before_dispatch(self):
        faults = ("missing", "id", "type", "mixed-pending", "duplicate-index", "sparse-index", "bool-index",
                  "pending-unsorted", "dense-unsorted", "token", "panel-type", "panel-id", "height", "screen",
                  "version", "plugin", "geometry", "connector", "screen-ids", "foreign-widget", "foreign-index")
        for fault in faults:
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime = SyntheticDelayedOrderRuntime(self.config, pending_reads=0)
                runtime.extra_panels = [{"id":301,"type":"org.kde.panel","screen":2,"height":48,
                    "widgets":[{"id":401,"type":"unrelated.widget","index":0}],
                    "marker":{"token":"unrelated","schemaVersion":0}}]
                self.plan = layout.build_plan(manifest(), runtime.inspect("DP-1"))
                def drift(actual):
                    panel = actual["panels"][0]; widgets = panel["widgets"]
                    if fault == "missing": widgets.pop()
                    if fault == "id": widgets[0]["id"] += 900
                    if fault == "type": widgets[0]["type"] = "foreign.widget"
                    if fault == "mixed-pending": widgets[0]["index"] = -1
                    if fault == "duplicate-index": widgets[0]["index"] = 1
                    if fault == "sparse-index": widgets[-1]["index"] = 9
                    if fault == "bool-index": widgets[0]["index"] = False
                    if fault == "pending-unsorted":
                        for widget in widgets: widget["index"] = -1
                        widgets.reverse()
                    if fault == "dense-unsorted": widgets.reverse()
                    if fault == "token": panel["marker"]["token"] = "foreign"
                    if fault == "panel-type": panel["type"] = "foreign.panel"
                    if fault == "panel-id": panel["id"] = 99
                    if fault == "height": panel["height"] += 1
                    if fault == "screen": panel["screen"] = -1
                    if fault == "version": actual["version"] = "6.7.6"
                    if fault == "plugin": actual["knownWidgetTypes"].pop()
                    if fault == "geometry": actual["selectedScreen"]["geometry"]["width"] += 1
                    if fault == "connector": actual["selectedScreen"]["connector"] = "DP-2"
                    if fault == "screen-ids": actual["screenIds"].reverse()
                    if fault == "foreign-widget": actual["panels"][1]["widgets"][0]["id"] += 1
                    if fault == "foreign-index": actual["panels"][1]["widgets"][0]["index"] = -1
                runtime.after_read = drift
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
                self.assert_restored(runtime, "WAIT_OWNED_ORDER")
                self.assertEqual(runtime.order_reads, ["DP-1"])
                self.assertEqual(runtime.order_requests, [])

    def test_pending_and_permanent_wrong_order_share_a_finite_budget_and_restore(self):
        for fault in ("pending", "wrong-order"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime = SyntheticDelayedOrderRuntime(self.config,
                    pending_reads=100 if fault == "pending" else 0, reorder_effect=False)
                pauses = []
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, pause=pauses.append)
                self.assert_restored(runtime, "WAIT_OWNED_ORDER" if fault == "pending" else "VERIFY_OWNED_ORDER",
                                     "READINESS_TIMEOUT")
                self.assertEqual(len(runtime.order_reads), 17)
                self.assertEqual(pauses, [0.5]*16)
                self.assertEqual(len(runtime.order_requests), 0 if fault == "pending" else 1)

    def test_pending_deadline_and_read_overshoot_never_dispatch(self):
        for fault in ("elapsed", "overshoot"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime = SyntheticDelayedOrderRuntime(self.config, pending_reads=100 if fault == "elapsed" else 0)
                now = [0.0]; pauses = []
                if fault == "overshoot": runtime.after_read = lambda actual:now.__setitem__(0,18.0)
                def pause(seconds): pauses.append(seconds); now[0] += seconds
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, clock=lambda:now[0], pause=pause)
                self.assert_restored(runtime, "WAIT_OWNED_ORDER", "READINESS_TIMEOUT")
                self.assertEqual(runtime.order_requests, [])
                self.assertEqual(len(pauses), 16 if fault == "elapsed" else 0)
                if fault == "elapsed": self.assertEqual(now[0], 8.0)

    def test_deadline_after_durable_reorder_stage_blocks_dispatch(self):
        runtime = SyntheticDelayedOrderRuntime(self.config, pending_reads=0)
        now = [0.0]; save = self.store.save
        def late_save(receipt):
            save(receipt)
            if receipt["stage"] == "REORDER_OWNED": now[0] = 8.0
        self.store.save = late_save
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, clock=lambda:now[0])
        self.assert_restored(runtime, "REORDER_OWNED", "READINESS_TIMEOUT")
        self.assertEqual(runtime.order_requests, [])

    def test_wrong_ack_and_missing_reorder_capability_restore_without_capture(self):
        for index,ack in enumerate(({}, {"reordered":False}, {"reordered":1}, {"reordered":True,"extra":1}, True, None)):
            with self.subTest(ack=ack):
                self.case_storage(str(index))
                runtime = SyntheticDelayedOrderRuntime(self.config, pending_reads=0)
                runtime.ack = ack
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
                receipt = self.assert_restored(runtime, "REORDER_OWNED", "SCRIPT_REPLY_INVALID")
                self.assertIsNone(receipt["after"])
                self.assertEqual(len(runtime.order_requests), 1)
        self.case_storage("missing")
        runtime = SyntheticDelayedOrderRuntime(self.config, pending_reads=0)
        runtime.reorder_owned = None
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
        self.assert_restored(runtime, "REORDER_OWNED")
        self.assertEqual(runtime.order_requests, [])

    def test_identity_drift_before_read_and_dispatch_is_not_retried_or_retargeted(self):
        for boundary in ("before-read", "after-read", "before-dispatch"):
            with self.subTest(boundary=boundary):
                self.case_storage(boundary)
                runtime = SyntheticDelayedOrderRuntime(self.config, pending_reads=0)
                def drift(): runtime.identity["target"] = {"configHome":str(self.root/"foreign")}
                if boundary == "after-read": runtime.after_read = lambda actual:drift()
                save = self.store.save
                def changed(receipt):
                    save(receipt)
                    if receipt["stage"] == ("WAIT_OWNED_ORDER" if boundary == "before-read" else "REORDER_OWNED"):
                        if boundary != "after-read": drift()
                self.store.save = changed
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
                receipt = self.store.current()
                self.assertEqual(receipt["phase"], "RECOVERY_REQUIRED")
                self.assertEqual(receipt["diagnostics"]["recovery"]["stage"], "RECOVERY_BIND")
                self.assertEqual(runtime.order_requests, [])
                self.assertEqual(len(runtime.order_reads), 0 if boundary == "before-read" else 1)
                self.store.save = save

    def test_final_order_poll_allows_only_dense_owned_permutation(self):
        runtime = SyntheticDelayedOrderRuntime(self.config, pending_reads=0, reorder_effect=False)
        def lost_membership(actual):
            if runtime.order_requests: actual["panels"][0]["widgets"][0]["id"] += 900
        runtime.after_read = lost_membership
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
        self.assert_restored(runtime, "VERIFY_OWNED_ORDER", "INVENTORY_MISMATCH")
        self.assertEqual(len(runtime.order_reads), 2)
        self.assertEqual(len(runtime.order_requests), 1)


class AsyncOrderNativeAdapterTests(unittest.TestCase):
    def test_default_inspect_is_strict_and_only_explicit_postapply_probe_can_read_pending(self):
        import json
        commands = FakeCommands()
        pending = inventory()
        for widget in pending["panels"][0]["widgets"]: widget["index"] = -1
        call = commands.__call__
        def runner(argv, **kwargs):
            result = call(argv, **kwargs)
            if "org.kde.PlasmaShell.evaluateScript" in argv: result.stdout = repr((json.dumps(pending),))
            return result
        runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=runner, locate=lambda tool:tool,
                                       process_reader=fake_process, process_absent=lambda pid:True)
        with self.assertRaises(layout.LayoutError): runtime.inspect("DP-1")
        self.assertEqual(runtime.inspect("DP-1", allow_uninitialized=True), pending)
        with self.assertRaises(layout.LayoutError): layout.build_plan(manifest(), pending)

    def test_native_reorder_binding_deadline_blocks_mutating_script_after_binding(self):
        plan = layout.build_plan(manifest(), inventory())
        from pathlib import Path
        # Only use the owned triples from the existing synthetic adapter.
        runtime_fixture = FakeRuntime(Path("/private-fixture/config")); runtime_fixture.plan = plan
        owned = runtime_fixture.owned(); current = layout._managed_inventory(plan, owned)
        now = [0.0]; commands = FakeCommands(); call = commands.__call__
        def runner(argv, **kwargs):
            result = call(argv, **kwargs)
            if "org.freedesktop.DBus.GetConnectionUnixProcessID" in argv: now[0] = 8.0
            return result
        runtime = layout.NativeRuntime("plasma-plasmashell.service", runner=runner, locate=lambda tool:tool,
                                       process_reader=fake_process, process_absent=lambda pid:True)
        with self.assertRaises(layout.LayoutError) as caught:
            runtime.reorder_owned(owned["panelId"], owned["token"], current, owned["widgets"],
                                  ready_deadline=8.0, clock=lambda:now[0])
        self.assertEqual(caught.exception.facts["code"], "READINESS_TIMEOUT")
        self.assertFalse(any("org.kde.PlasmaShell.evaluateScript" in argv for argv,_ in commands.calls))


class SyntheticPartialOrderRuntime(SyntheticDelayedOrderRuntime):
    """Offline exact five-ID analogue of Root's partial postapply observation."""
    def owned(self):
        owned = super().owned()
        ids = {"menu":35, "global-menu":30, "spacer":31, "tray":7, "clock":22}
        for module,widget in zip(self.plan["manifest"]["modules"], owned["widgets"]):
            widget["id"] = ids[module["key"]]
        return owned


class PartialInitializationTests(unittest.TestCase):
    setUp = TransactionTests.setUp
    run_apply = AsyncOrderTransactionTests.run_apply
    assert_restored = AsyncOrderTransactionTests.assert_restored
    case_storage = FinalRestartReadinessReviewTests.case_storage

    def runtime(self, snapshots):
        runtime = SyntheticPartialOrderRuntime(self.config, pending_reads=0)
        data = manifest(); data["reuseWidgetIds"]["menu"] = 35
        runtime.extra_panels = [{"id":301,"type":"org.kde.panel","screen":2,"height":48,
            "widgets":[{"id":401,"type":"unrelated.widget","index":0}],
            "marker":{"token":"unrelated","schemaVersion":0}}]
        self.plan = layout.build_plan(data, runtime.inspect("DP-1"))
        def read(actual):
            slot = min(len(runtime.order_reads)-1, len(snapshots)-1)
            snapshot = snapshots[slot]
            if snapshot is not None:
                target = next(panel for panel in actual["panels"] if panel["id"] == 100)
                target["widgets"] = copy.deepcopy(snapshot)
        runtime.after_read = read
        return runtime

    def snapshot(self, indices=None):
        indices = {35:0} if indices is None else indices
        widgets = [{"id":widget_id,"type":layout.MODULE_IDS[key],"index":indices.get(widget_id,-1)}
                   for key,widget_id in (("menu",35),("global-menu",30),("spacer",31),("tray",7),("clock",22))]
        return sorted(widgets, key=lambda widget:(widget["index"],widget["id"]))

    def test_actual_partial_five_id_shape_waits_for_full_dense_order_then_commits(self):
        partial = self.snapshot()
        self.assertEqual([(widget["id"],widget["index"]) for widget in partial],
                         [(7,-1),(22,-1),(30,-1),(31,-1),(35,0)])
        runtime = self.runtime([partial, self.snapshot({35:0,30:1,7:2}), None])
        pauses = []
        receipt = self.run_apply(runtime, pause=pauses.append)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertFalse(receipt["owned"]["nativeValidated"])
        self.assertEqual(len(runtime.order_reads), 4)
        self.assertEqual(pauses, [0.5]*3)
        self.assertEqual(len(runtime.order_requests), 1)
        gate = next(panel for panel in runtime.order_requests[0]["panels"] if panel["id"] == 100)
        self.assertEqual([widget["index"] for widget in gate["widgets"]], list(range(5)))
        self.assertEqual([widget["id"] for widget in receipt["owned"]["widgets"]], [35,30,31,7,22])
        self.assertEqual(runtime.inspect("DP-1"), layout._managed_inventory(self.plan, receipt["owned"]))

    def test_permanent_valid_partial_prefix_times_out_without_dispatch_and_restores(self):
        runtime = self.runtime([self.snapshot({35:0,30:1,31:2,7:3})])
        pauses = []
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, pause=pauses.append)
        receipt = self.assert_restored(runtime, "WAIT_OWNED_ORDER", "READINESS_TIMEOUT")
        self.assertEqual(len(runtime.order_reads), 17)
        self.assertEqual(pauses, [0.5]*16)
        self.assertEqual(runtime.order_requests, [])
        self.assertIsNone(receipt["after"])

    def test_invalid_partial_slots_membership_and_representation_refuse_without_dispatch(self):
        faults = ("gap", "duplicate", "out-of-range", "negative", "bool", "unsorted", "missing", "id", "type",
                  "full-positive-gap", "full-positive-unsorted", "full-positive-member")
        for fault in faults:
            with self.subTest(fault=fault):
                self.case_storage(fault)
                partial = self.snapshot()
                if fault == "gap": partial = self.snapshot({35:1})
                if fault == "duplicate": partial = self.snapshot({35:0,30:0})
                if fault == "out-of-range": partial = self.snapshot({35:128})
                if fault == "negative": partial = self.snapshot({35:0,7:-2})
                if fault == "bool": partial = self.snapshot({35:True})
                if fault == "unsorted": partial.reverse()
                if fault == "missing": partial.pop()
                if fault == "id": partial[0]["id"] = 999
                if fault == "type": partial[0]["type"] = "foreign.widget"
                if fault.startswith("full-positive"):
                    partial = self.snapshot({7:0,22:1,30:2,31:3,35:4})
                    if fault == "full-positive-gap": partial[-1]["index"] = 5
                    if fault == "full-positive-unsorted": partial.reverse()
                    if fault == "full-positive-member": partial[-1]["id"] = 999
                runtime = self.runtime([partial, None])
                pauses = []
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime, pause=pauses.append)
                self.assert_restored(runtime, "WAIT_OWNED_ORDER")
                self.assertEqual(runtime.order_reads, ["DP-1"])
                self.assertEqual(runtime.order_requests, [])
                self.assertEqual(pauses, [])

    def test_partial_prefix_never_relaxes_foreign_inventory_facts(self):
        for fault in ("foreign-height", "foreign-index", "marker", "screen", "plugin"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime = self.runtime([self.snapshot()])
                read = runtime.after_read
                def drift(actual):
                    read(actual)
                    foreign = next(panel for panel in actual["panels"] if panel["id"] == 301)
                    owned = next(panel for panel in actual["panels"] if panel["id"] == 100)
                    if fault == "foreign-height": foreign["height"] += 1
                    if fault == "foreign-index": foreign["widgets"][0]["index"] = -1
                    if fault == "marker": owned["marker"]["token"] = "foreign"
                    if fault == "screen": owned["screen"] = -1
                    if fault == "plugin": actual["knownWidgetTypes"].pop()
                runtime.after_read = drift
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
                self.assert_restored(runtime, "WAIT_OWNED_ORDER", "INVENTORY_MISMATCH")
                self.assertEqual(runtime.order_reads, ["DP-1"])
                self.assertEqual(runtime.order_requests, [])

    def test_full_dense_wrong_order_reorders_but_same_slots_with_wrong_members_refuse(self):
        runtime = self.runtime([None])
        receipt = self.run_apply(runtime)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertEqual(len(runtime.order_requests), 1)
        owned = next(panel for panel in runtime.order_requests[0]["panels"] if panel["id"] == 100)
        self.assertEqual([widget["id"] for widget in owned["widgets"]], [7,22,30,31,35])
        self.assertEqual([widget["index"] for widget in owned["widgets"]], list(range(5)))
        self.assertEqual([widget["id"] for widget in runtime.last_order], [35,30,31,7,22])
        self.case_storage("wrong-member")
        wrong = self.snapshot({7:0,22:1,30:2,31:3,35:4}); wrong[0]["type"] = "foreign.widget"
        runtime = self.runtime([wrong])
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
        self.assert_restored(runtime, "WAIT_OWNED_ORDER", "INVENTORY_MISMATCH")
        self.assertEqual(runtime.order_requests, [])

    def test_partial_prefix_after_reorder_dispatch_refuses_instead_of_waiting(self):
        runtime = self.runtime([None, self.snapshot()])
        pauses = []
        with self.assertRaises(layout.LayoutError): self.run_apply(runtime, pause=pauses.append)
        self.assert_restored(runtime, "VERIFY_OWNED_ORDER")
        self.assertEqual(len(runtime.order_reads), 2)
        self.assertEqual(len(runtime.order_requests), 1)
        self.assertEqual(pauses, [0.5])


class MaterializeAndLifecycleTests(unittest.TestCase):
    setUpClass = ScriptTests.setUpClass
    engine = ScriptTests.engine
    setUp = TransactionTests.setUp
    run_apply = AsyncOrderTransactionTests.run_apply
    case_storage = FinalRestartReadinessReviewTests.case_storage

    def test_moved_widgets_materialize_only_after_named_cold_reload_then_strict_order_commits(self):
        runtime = SyntheticPartialOrderRuntime(self.config, pending_reads=100)
        data = manifest(); data["reuseWidgetIds"]["menu"] = 35
        self.plan = layout.build_plan(data, runtime.inspect("DP-1"))
        start = runtime.start
        def cold_start():
            start()
            if runtime.events.count("start") == 2: runtime.pending_reads = 0
        runtime.start = cold_start
        receipt = self.run_apply(runtime)
        self.assertEqual(receipt["phase"], "COMMITTED")
        self.assertEqual(runtime.events.count("start"), 3)
        self.assertEqual(runtime.events.count("stop"), 3)
        self.assertEqual(len(runtime.order_requests), 1)
        self.assertEqual([widget["id"] for widget in receipt["owned"]["widgets"]], [35,30,31,7,22])
        self.assertEqual(runtime.inspect("DP-1"), layout._managed_inventory(self.plan, receipt["owned"]))

    snapshot = PartialInitializationTests.snapshot
    partial_runtime = PartialInitializationTests.runtime
    assert_restored = AsyncOrderTransactionTests.assert_restored

    @staticmethod
    def screen_pending(actual):
        actual = copy.deepcopy(actual)
        actual["screenIds"] = []; actual["selectedScreen"] = None
        for panel in actual["panels"]: panel["screen"] = -1
        return actual

    def test_materialize_screen_and_index_projection_waits_only_and_refuses_drift_or_deadline(self):
        for fault in ("ready", "foreign-drift", "late", "screen-timeout"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime = self.partial_runtime([self.snapshot(), None])
                read = runtime.after_read; now = [0.0]; pauses = []
                def pending(actual):
                    read(actual)
                    if fault == "screen-timeout" or len(runtime.order_reads) <= (2 if fault == "ready" else 1):
                        actual["screenIds"] = []; actual["selectedScreen"] = None
                        for panel in actual["panels"]: panel["screen"] = -1
                    if fault == "foreign-drift": actual["panels"][-1]["height"] += 1
                    if fault == "late": now[0] = 8.0
                runtime.after_read = pending
                if fault == "ready":
                    receipt = self.run_apply(runtime, clock=lambda:now[0], pause=pauses.append)
                    self.assertEqual(receipt["phase"], "COMMITTED")
                    self.assertEqual(len(runtime.order_reads), 4)
                    self.assertEqual(len(runtime.order_requests), 1)
                    self.assertEqual(runtime.order_requests[0]["selectedScreen"], self.plan["screen"])
                else:
                    with self.assertRaises(layout.LayoutError): self.run_apply(runtime, clock=lambda:now[0], pause=pauses.append)
                    self.assert_restored(runtime, "WAIT_OWNED_ORDER",
                                         "INVENTORY_MISMATCH" if fault == "foreign-drift" else "READINESS_TIMEOUT")
                    self.assertEqual(runtime.order_requests, [])
                    self.assertEqual(len(runtime.order_reads), 17 if fault == "screen-timeout" else 1)

    def test_extra_materialize_stop_start_and_preflight_failures_restore_with_distinct_stages(self):
        for fault in ("stop", "start", "preflight"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime = FakeRuntime(self.config); original = getattr(runtime,fault)
                injected = []
                def fail(*args, **kwargs):
                    due = (runtime.events.count("stop") == 1 if fault == "stop" else
                           runtime.events.count("start") == 1 if fault == "start" else
                           runtime.events.count("start") == 2)
                    if due and not injected:
                        injected.append(fault)
                        raise layout.LayoutError("PRIVATE_MATERIALIZE_FAILURE", code="COMMAND_EXIT",
                                                 operation="UNIT_STOP" if fault == "stop" else "UNIT_START" if fault == "start" else "VERSION")
                    return original(*args, **kwargs)
                setattr(runtime,fault,fail)
                with self.assertRaises(layout.LayoutError): self.run_apply(runtime)
                receipt = self.assert_restored(runtime, "STOP_FOR_ORDER" if fault == "stop" else "RESTART_FOR_ORDER", "COMMAND_EXIT")
                self.assertEqual(injected, [fault])
                self.assertIsNone(receipt["after"])
                self.assertNotIn("PRIVATE_", str(receipt))

        commands = FakeCommands(); now = [0.0]; call = commands.__call__
        def slow_binding(argv, **kwargs):
            result = call(argv, **kwargs)
            if "org.freedesktop.DBus.GetConnectionUnixProcessID" in argv: now[0] = 8.0
            return result
        native = layout.NativeRuntime("plasma-plasmashell.service", runner=slow_binding, locate=lambda tool:tool,
                                      process_reader=fake_process, process_absent=lambda pid:True)
        fixture = FakeRuntime(self.config); fixture.plan = self.plan; owned = fixture.owned()
        with self.assertRaises(layout.LayoutError) as caught:
            native.remove_owned(owned["panelId"], owned["token"], layout._managed_inventory(self.plan,owned),
                                ready_deadline=8.0, clock=lambda:now[0])
        self.assertEqual(caught.exception.facts["code"], "READINESS_TIMEOUT")
        self.assertFalse(any("org.kde.PlasmaShell.evaluateScript" in argv for argv,_ in commands.calls))

    def call_disable(self, receipt, runtime, now, pauses):
        import inspect
        # Public fixture seam bridges old Source lacking optional injected time.
        kwargs = {"clock":lambda:now[0],"pause":pauses.append} if "clock" in inspect.signature(layout.disable_layout).parameters else {}
        return layout.disable_layout(receipt,runtime,self.store,**kwargs)

    def committed_runtime(self):
        runtime = FakeRuntime(self.config)
        runtime.extra_panels = [{"id":301,"type":"org.kde.panel","screen":2,"height":48,
            "widgets":[{"id":401,"type":"unrelated.widget","index":0}],
            "marker":{"token":"unrelated","schemaVersion":0}}]
        self.plan = layout.build_plan(manifest(), runtime.inspect("DP-1"))
        return runtime, self.run_apply(runtime)

    def restart_projection(self, runtime, effects, now):
        start,inspect = runtime.start,runtime.inspect
        counts = {"start":0,"read":0}
        def restarted():
            start(); counts["start"] += 1; counts["read"] = 0
        def read(connector=""):
            actual = inspect(connector)
            if not counts["start"]: return actual
            counts["read"] += 1
            if counts["read"] != 1: return actual
            effect = effects.get(counts["start"], "transient")
            if isinstance(effect, Exception): raise effect
            if effect == "transient": return self.screen_pending(actual)
            if effect == "drift": actual["panels"][-1]["height"] += 1
            if effect == "late": now[0] += 8.0
            return actual
        runtime.start,runtime.inspect = restarted,read
        return counts

    def test_disable_initial_and_final_restart_wait_exactly_or_restore_active_bank_on_refusal(self):
        for boundary in (1,2,3):
            for fault in ("transient", "drift", "late", "command"):
                with self.subTest(boundary=boundary,fault=fault):
                    self.case_storage(str(boundary)+fault)
                    runtime,receipt = self.committed_runtime()
                    active = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
                    now = [0.0]; pauses = []
                    effects = {boundary:layout.LayoutError("PRIVATE_DISABLE_REPLY", code="COMMAND_TIMEOUT", operation="EVALUATE_SCRIPT")
                               if fault == "command" else fault}
                    self.restart_projection(runtime,effects,now)
                    if fault == "transient":
                        result = self.call_disable(receipt,runtime,now,pauses)
                        self.assertEqual(result["phase"], "DISABLED")
                        self.assertEqual(runtime.events.count("remove-owned"), 1)
                        self.assertEqual(pauses, [0.5]*3)
                    else:
                        with self.assertRaises(layout.LayoutError):
                            self.call_disable(receipt,runtime,now,pauses)
                        result = self.store.current()
                        self.assertEqual(result["phase"], "COMMITTED")
                        self.assertEqual(result["diagnostics"]["primary"]["stage"],
                                         "DISABLE_VERIFY_RESTART" if boundary == 1 else "DISABLE_VERIFY_FINAL")
                        self.assertEqual(result["diagnostics"]["primary"]["code"],
                                         "INVENTORY_MISMATCH" if fault == "drift" else "READINESS_TIMEOUT" if fault == "late" else "COMMAND_TIMEOUT")
                        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, active)
                        self.assertEqual(runtime.events.count("remove-owned"), 0 if boundary == 1 else 1)
                        self.assertNotIn("PRIVATE_", str(result))

        self.case_storage("idempotent-conflict")
        runtime,receipt = self.committed_runtime()
        receipt = layout.disable_layout(receipt,runtime,self.store,clock=lambda:0.0,pause=lambda seconds:None)
        primary = layout.LayoutError("layout configuration changed", code="INVENTORY_MISMATCH")
        start,read = runtime.start,runtime.inspect; restarted = []; postrestart_reads = []
        def restart(): start(); restarted.append(True)
        def inspect(connector=""):
            if restarted:
                postrestart_reads.append(True)
                raise layout.LayoutError("unavailable new readiness", code="COMMAND_TIMEOUT")
            return read(connector)
        runtime.start,runtime.inspect = restart,inspect
        from unittest import mock
        with mock.patch.object(self.store,"verify_current",side_effect=primary), self.assertRaises(layout.LayoutError) as caught:
            layout.disable_layout(receipt,runtime,self.store,clock=lambda:0.0,pause=lambda seconds:None)
        self.assertIs(caught.exception, primary)
        self.assertEqual(restarted,[True])
        self.assertEqual(postrestart_reads,[])

    def test_disable_rollback_and_explicit_recovery_wait_for_exact_active_inventory(self):
        for fault in ("transient", "drift"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime,receipt = self.committed_runtime()
                active = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
                original_receipt = (self.store._directory(receipt)/"apply-receipt.json").read_bytes()
                runtime.failure = "disable"; now = [0.0]; pauses = []; effects = {2:fault}
                counts = self.restart_projection(runtime,effects,now)
                with self.assertRaises(layout.LayoutError):
                    self.call_disable(receipt,runtime,now,pauses)
                result = self.store.current()
                self.assertEqual(result["diagnostics"]["primary"]["stage"], "DISABLE_REMOVE")
                if fault == "drift":
                    self.assertEqual(result["phase"], "RECOVERY_REQUIRED")
                    self.assertEqual(result["diagnostics"]["recovery"]["stage"], "DISABLE_RECOVERY_VERIFY")
                    self.assertEqual(result["diagnostics"]["recovery"]["code"], "INVENTORY_MISMATCH")
                    result = layout.restore_layout(result,runtime,self.store,recover=True,clock=lambda:now[0],pause=pauses.append)
                self.assertEqual(result["phase"], "COMMITTED")
                self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, active)
                self.assertEqual((self.store._directory(result)/"apply-receipt.json").read_bytes(), original_receipt)
                self.assertFalse(runtime.is_stopped)
                self.assertGreaterEqual(counts["start"], 2)
                layout.restore_layout(result,runtime,self.store,clock=lambda:now[0],pause=pauses.append)
                self.assertEqual(self.store.current()["phase"], "RESTORED")
                self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)

    def test_stopped_committed_restore_and_original_restart_wait_with_foreign_drift_refusal(self):
        for fault in ("transient", "drift"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime,receipt = self.committed_runtime(); runtime.is_stopped = True
                active = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
                now = [0.0]; pauses = []
                self.restart_projection(runtime,{1:fault},now)
                if fault == "transient":
                    result = layout.restore_layout(receipt,runtime,self.store,recover=True,clock=lambda:now[0],pause=pauses.append)
                    self.assertEqual(result["phase"], "RESTORED")
                    self.assertEqual(pauses, [0.5]*2)
                    self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
                else:
                    with self.assertRaises(layout.LayoutError):
                        layout.restore_layout(receipt,runtime,self.store,recover=True,clock=lambda:now[0],pause=pauses.append)
                    result = self.store.current()
                    self.assertEqual(result["phase"], "COMMITTED")
                    self.assertEqual(result["diagnostics"]["recovery"]["stage"], "RESTORE_VERIFY_CURRENT")
                    self.assertEqual(result["diagnostics"]["recovery"]["code"], "INVENTORY_MISMATCH")
                    self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, active)


    def test_clock_schema_configuration_uses_appearance_and_preserves_unrelated_general(self):
        import json
        engine = self.engine()
        setup = engine.evaluate("var originalMakeWidget=makeWidget;makeWidget=function(id,type,panel){"+
            "var widget=originalMakeWidget(id,type,panel);if(type==='org.kde.plasma.digitalclock'){"+
            "widget.values['General/opaqueClock']='keep';widget.values['Appearance/showDate']=true;"+
            "widget.values['Appearance/showLocalTimezone']=true;}return widget;};")
        self.assertFalse(setup.isError(), setup.toString())
        data = manifest(); data["modules"][-1]["config"]["showLocalTimezone"] = False
        result = engine.evaluate(layout.render_script("apply",plan=layout.build_plan(data,inventory())))
        self.assertFalse(result.isError(), result.toString())
        values = json.loads(engine.evaluate("JSON.stringify(panels()[0].items.find(widget=>widget.type==='org.kde.plasma.digitalclock').values)").toString())
        self.assertEqual(values, {"General/opaqueClock":"keep", "Appearance/showDate":False,
                                  "Appearance/showLocalTimezone":False})


class SyntheticRemovedViewCleanupRuntime(FakeRuntime):
    """Offline restart cleanup analogue; no native configuration access."""
    foreign_config = b"[PlasmaViews][Panel 301]\nopaqueForeign=preserved\n"
    owned_view = (b"[PlasmaViews][Panel 100]\nfloating=0\npanelOpacity=2\nshell=org.kde.plasma.desktop\n"
                  b"[PlasmaViews][Panel 100][Defaults]\nthickness=32\n")
    def __init__(self, config_home):
        super().__init__(config_home)
        self.cleanup_pending = False; self.cleanup_count = 0
    def apply(self, plan):
        owned = super().apply(plan)
        (self.config_home/"plasmashellrc").write_bytes(self.foreign_config+self.owned_view)
        return owned
    def remove_owned(self, panel_id, token, expected_inventory):
        result = super().remove_owned(panel_id,token,expected_inventory)
        (self.config_home/"plasmashellrc").write_bytes(self.foreign_config+self.owned_view)
        self.cleanup_pending = True
        return result
    def start(self):
        super().start()
        if self.disabled and self.cleanup_pending:
            (self.config_home/"plasmashellrc").write_bytes(self.foreign_config)
            self.cleanup_pending = False; self.cleanup_count += 1
            self.events.append("cleanup-owned-view")


class DisableFinalizationTests(unittest.TestCase):
    setUp = TransactionTests.setUp
    run_apply = AsyncOrderTransactionTests.run_apply
    case_storage = FinalRestartReadinessReviewTests.case_storage
    restart_projection = MaterializeAndLifecycleTests.restart_projection

    def runtime(self):
        runtime = SyntheticRemovedViewCleanupRuntime(self.config)
        runtime.extra_panels = [{"id":301,"type":"org.kde.panel","screen":2,"height":48,
            "widgets":[{"id":401,"type":"unrelated.widget","index":0}],
            "marker":{"token":"unrelated","schemaVersion":0}}]
        self.plan = layout.build_plan(manifest(),runtime.inspect("DP-1"))
        return runtime,self.run_apply(runtime)

    def test_removed_owned_view_cleanup_is_captured_before_disabled_restore_hash_guard(self):
        import hashlib
        runtime,receipt = self.runtime()
        apply_receipt = (self.store._directory(receipt)/"apply-receipt.json").read_bytes()
        capture = self.store._capture; final_captures = []
        def record_capture(directory):
            if directory is not None and directory.name == "disable-after-final":
                final_captures.append((runtime.cleanup_count,runtime.is_stopped))
            return capture(directory)
        self.store._capture = record_capture
        disabled = layout.disable_layout(receipt,runtime,self.store,clock=lambda:0.0,pause=lambda seconds:None)
        self.assertEqual(disabled["phase"], "DISABLED")
        self.assertEqual(final_captures, [(1,True)])
        self.assertFalse((self.store._directory(disabled)/"disable-after").exists())
        self.assertEqual(runtime.cleanup_count, 1)
        self.assertEqual((self.config/"plasmashellrc").read_bytes(), runtime.foreign_config)
        layout.restore_layout(disabled,runtime,self.store,clock=lambda:0.0,pause=lambda seconds:None)
        self.assertEqual(disabled["disableAfter"]["plasmashellrc"]["sha256"], hashlib.sha256(runtime.foreign_config).hexdigest())
        self.assertEqual(self.store.current()["phase"], "RESTORED")
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, self.original)
        for name in layout.CONFIG_FILES: self.assertEqual((self.config/name).stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.store._directory(receipt)/"apply-receipt.json").read_bytes(), apply_receipt)


    def test_final_capture_stop_storage_and_restart_failures_restore_exact_active_bank(self):
        for fault in ("stop", "capture", "save", "start", "preflight"):
            with self.subTest(fault=fault):
                self.case_storage(fault)
                runtime,receipt = self.runtime()
                active = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
                apply_receipt = (self.store._directory(receipt)/"apply-receipt.json").read_bytes()
                injected = []; stages = []; save,capture = self.store.save,self.store._capture
                start,stop,preflight = runtime.start,runtime.stop,runtime.preflight
                counts = {"start":0,"stop":0}
                def fail_stop():
                    counts["stop"] += 1
                    if fault == "stop" and counts["stop"] == 3:
                        injected.append(fault); raise layout.LayoutError("PRIVATE_STOP",code="COMMAND_EXIT",operation="UNIT_STOP")
                    stop()
                def fail_start():
                    counts["start"] += 1
                    if fault == "start" and counts["start"] == 3:
                        injected.append(fault); raise layout.LayoutError("PRIVATE_START",code="COMMAND_EXIT",operation="UNIT_START")
                    start()
                def fail_preflight(*args,**kwargs):
                    if fault == "preflight" and counts["start"] == 3 and not injected:
                        injected.append(fault); raise layout.LayoutError("PRIVATE_PREFLIGHT",code="COMMAND_EXIT",operation="VERSION")
                    preflight(*args,**kwargs)
                def fail_capture(directory):
                    if directory is not None and directory.name == "disable-after-final" and fault == "capture":
                        injected.append(fault); raise OSError("PRIVATE_CAPTURE")
                    return capture(directory)
                def fail_save(value):
                    stages.append(value["stage"])
                    if fault == "save" and value["stage"] == "DISABLE_CAPTURE_FINAL" and value.get("disableAfter") and not injected:
                        injected.append(fault); raise OSError("PRIVATE_SAVE")
                    return save(value)
                runtime.start,runtime.stop,runtime.preflight = fail_start,fail_stop,fail_preflight
                self.store._capture,self.store.save = fail_capture,fail_save
                with self.assertRaises(layout.LayoutError):
                    layout.disable_layout(receipt,runtime,self.store,clock=lambda:0.0,pause=lambda seconds:None)
                result = self.store.current()
                self.assertEqual(result["phase"], "COMMITTED")
                self.assertEqual(injected,[fault])
                self.assertEqual(result["diagnostics"]["primary"]["stage"],
                                 "DISABLE_FINAL_STOP" if fault == "stop" else "DISABLE_CAPTURE_FINAL" if fault in ("capture","save") else "DISABLE_FINAL_RESTART")
                self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}, active)
                self.assertEqual((self.store._directory(result)/"apply-receipt.json").read_bytes(),apply_receipt)
                self.assertFalse(runtime.is_stopped)
                self.assertTrue(result["recoveryPoints"][-1]["complete"])
                self.assertNotIn("PRIVATE_",str(result))

    def test_canonical_disabled_snapshot_keeps_strict_late_foreign_file_conflict_guard(self):
        runtime,receipt = self.runtime()
        disabled = layout.disable_layout(receipt,runtime,self.store,clock=lambda:0.0,pause=lambda seconds:None)
        (self.config/"plasmashellrc").write_bytes(runtime.foreign_config+b"later foreign value=retain\n")
        changed = {name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES}
        with self.assertRaises(layout.LayoutError):
            layout.restore_layout(disabled,runtime,self.store,clock=lambda:0.0,pause=lambda seconds:None)
        self.assertEqual(self.store.current()["phase"], "DISABLED")
        self.assertEqual({name:(self.config/name).read_bytes() for name in layout.CONFIG_FILES},changed)
        self.store.verify_backup(self.store.current())
        self.assertFalse(runtime.is_stopped)


class SyntheticStartLimitCommands(FakeCommands):
    """Offline systemd contract fixture; never calls a live unit or bus."""
    def __init__(self, *, baseline_result="success", baseline_restarts="0", post_result="start-limit-hit", post_restarts="0"):
        super().__init__()
        self.properties.update(Result=baseline_result,NRestarts=baseline_restarts)
        self.post_result = post_result; self.post_restarts = post_restarts
        self.start_attempts = 0; self.resets = 0; self.baseline_failed = False
        self.failure_code = 1; self.retry_failure = False; self.reset_failure = False
        self.after_failed_start = None; self.after_reset = None; self.after_retry = None

    def __call__(self, argv, **kwargs):
        from types import SimpleNamespace
        if "start" in argv:
            self.start_attempts += 1
            if self.start_attempts == 1 or self.retry_failure:
                self.calls.append((argv,kwargs)); self.active = False; self.failed = True
                self.properties.update(Result=self.post_result,NRestarts=self.post_restarts)
                if self.after_failed_start: self.after_failed_start()
                return SimpleNamespace(returncode=self.failure_code,stdout="PRIVATE_START",stderr="PRIVATE_START")
            self.failed = False
            self.properties.update(Result="success",NRestarts="0")
        if "reset-failed" in argv:
            self.calls.append((argv,kwargs)); self.resets += 1
            if self.reset_failure: return SimpleNamespace(returncode=9,stdout="PRIVATE_RESET",stderr="PRIVATE_RESET")
            self.failed = False; self.properties.update(Result="success",NRestarts="0")
            if self.after_reset: self.after_reset()
            return SimpleNamespace(returncode=0,stdout="",stderr="")
        result = super().__call__(argv,**kwargs)
        if "start" in argv and self.start_attempts > 1 and self.after_retry: self.after_retry()
        if "show" in argv and not self.active and (getattr(self,"failed",False) or self.baseline_failed):
            result.stdout = result.stdout.replace("ActiveState=inactive","ActiveState=failed")
        return result


class ControlCenterLifecycleTests(unittest.TestCase):
    setUp = TransactionTests.setUp

    def test_cc_receipt_disable_restore_preserves_original_bytes_and_independent_dock(self):
        runtime = FakeRuntime(self.config)
        dock = {"id": 29, "type": "org.kde.panel", "screen": 7, "height": 56,
            "widgets": [{"id": 40, "type": "org.caiodock.dock", "index": 0}], "marker": {"token": "", "schemaVersion": 0}}
        runtime.extra_panels = [dock]
        plan = layout.build_plan(control_center_manifest(), runtime.inspect("DP-1"))
        receipt = layout.apply_layout(plan, runtime, self.store)
        bars = [widget for widget in receipt["owned"]["widgets"] if widget["type"] == "org.orla.bar"]
        self.assertEqual(len(bars), 2)
        self.assertEqual(len(set(widget["id"] for widget in bars)), 2)
        self.assertEqual(self.store.current(), receipt)
        disabled = layout.disable_layout(receipt, runtime, self.store)
        self.assertEqual(runtime.inspect("DP-1")["panels"], [dock])
        layout.restore_layout(disabled, runtime, self.store)
        for name, data in self.original.items():
            self.assertEqual((self.config / name).read_bytes(), data)
            self.assertEqual((self.config / name).stat().st_mode & 0o777, 0o640)


class StartLimitRecoveryTests(unittest.TestCase):
    def runtime(self, commands, *, absent=None):
        runtime = layout.NativeRuntime("plasma-plasmashell.service",runner=commands,locate=lambda tool:tool,
                                       process_reader=fake_process,process_absent=absent or (lambda pid:True))
        runtime.preflight(); runtime.stop()
        return runtime

    def test_exact_manual_start_limit_uses_one_named_reset_and_retry_after_healthy_baseline(self):
        commands = SyntheticStartLimitCommands(); runtime = self.runtime(commands)
        identity = copy.deepcopy(runtime.identity)
        runtime.start()
        self.assertTrue(commands.active)
        self.assertEqual(runtime.identity,identity)
        self.assertEqual(commands.start_attempts,2)
        self.assertEqual(commands.resets,1)
        reset = [(argv,options) for argv,options in commands.calls if "reset-failed" in argv]
        self.assertEqual(reset[0][0],["systemctl","--user","reset-failed",runtime.unit])
        self.assertFalse(any("set-property" in argv or "daemon-reload" in argv for argv,_ in commands.calls))


    def assert_original_start_failure(self, caught, runtime, commands):
        self.assertEqual(caught.exception.facts, {"code":"COMMAND_EXIT","operation":"UNIT_START","returncode":1})
        self.assertNotIn("PRIVATE_", str(caught.exception))
        self.assertNotIn("PRIVATE_", str(runtime.start_limit_recovery))
        self.assertLessEqual(commands.start_attempts, 2)
        self.assertLessEqual(commands.resets, 1)

    def test_preexisting_failed_unknown_or_automatic_restart_state_never_authorizes_reset(self):
        for fault in ("failed-state", "start-limit-hit", "exit-code", "core-dump", "missing-result", "restarts", "missing-restarts", "malformed-restarts"):
            with self.subTest(fault=fault):
                commands = SyntheticStartLimitCommands(); runtime = self.runtime(commands)
                if fault == "failed-state": commands.baseline_failed = True
                if fault in ("start-limit-hit","exit-code","core-dump"): commands.properties["Result"] = fault
                if fault == "missing-result": commands.properties.pop("Result")
                if fault == "restarts": commands.properties["NRestarts"] = "1"
                if fault == "missing-restarts": commands.properties.pop("NRestarts")
                if fault == "malformed-restarts": commands.properties["NRestarts"] = "unknown"
                with self.assertRaises(layout.LayoutError) as caught: runtime.start()
                self.assert_original_start_failure(caught,runtime,commands)
                self.assertEqual(commands.resets,0); self.assertEqual(commands.start_attempts,1)
                self.assertIsNone(runtime.start_limit_recovery)
        # A normal successful first start remains possible with no recovery eligibility.
        commands = FakeCommands(); commands.properties.update(Result="exit-code",NRestarts="1")
        runtime = self.runtime(commands); runtime.start()
        self.assertTrue(commands.active)
        self.assertFalse(any("reset-failed" in argv for argv,_ in commands.calls))

    def test_nonrate_or_unverifiable_postfailure_state_refuses_without_any_reset(self):
        faults = ("exit-code", "core-dump", "timeout", "restarts", "missing-result", "missing-restarts", "owner", "prior-process", "service-drift", "target-drift")
        for fault in faults:
            with self.subTest(fault=fault):
                commands = SyntheticStartLimitCommands(); runtime = self.runtime(commands)
                def changed():
                    if fault in ("exit-code","core-dump","timeout"): commands.properties["Result"] = fault
                    if fault == "restarts": commands.properties["NRestarts"] = "1"
                    if fault == "missing-result": commands.properties.pop("Result")
                    if fault == "missing-restarts": commands.properties.pop("NRestarts")
                    if fault == "owner": commands.foreign_owner = True
                    if fault == "prior-process": runtime.process_absent = lambda pid:False
                    if fault == "service-drift": commands.properties["ExecStart"] = "{ path=/usr/bin/plasmashell ; argv[]=/usr/bin/plasmashell ; }"
                    if fault == "target-drift": runtime.identity["target"] = {"configHome":"/unrelated"}
                commands.after_failed_start = changed
                with self.assertRaises(layout.LayoutError) as caught: runtime.start()
                self.assert_original_start_failure(caught,runtime,commands)
                self.assertEqual(commands.resets,0); self.assertEqual(commands.start_attempts,1)
                self.assertFalse(runtime.start_limit_recovery["resetAttempted"])
                self.assertFalse(runtime.start_limit_recovery["retryAttempted"])
                self.assertEqual(runtime.start_limit_recovery["initialFailure"], caught.exception.facts)

    def test_reset_retry_and_full_binding_failures_are_finite_and_keep_original_error(self):
        faults = ("reset", "retry", "reset-owner", "reset-result", "reset-restarts", "reset-failed-state", "reset-service", "reset-target", "retry-binding")
        for fault in faults:
            with self.subTest(fault=fault):
                commands = SyntheticStartLimitCommands(); runtime = self.runtime(commands)
                commands.reset_failure = fault == "reset"; commands.retry_failure = fault == "retry"
                def changed():
                    if fault == "reset-owner": commands.foreign_owner = True
                    if fault == "reset-result": commands.properties["Result"] = "exit-code"
                    if fault == "reset-restarts": commands.properties["NRestarts"] = "1"
                    if fault == "reset-failed-state": commands.baseline_failed = True
                    if fault == "reset-service": commands.properties["ExecStart"] = "{ path=/usr/bin/plasmashell ; argv[]=/usr/bin/plasmashell ; }"
                    if fault == "reset-target": runtime.identity["target"] = {"configHome":"/unrelated"}
                commands.after_reset = changed
                if fault == "retry-binding": commands.after_retry = lambda:setattr(commands,"owner",999)
                with self.assertRaises(layout.LayoutError) as caught: runtime.start()
                self.assert_original_start_failure(caught,runtime,commands)
                self.assertEqual(commands.resets,1)
                self.assertEqual(commands.start_attempts,2 if fault in ("retry","retry-binding") else 1)
                self.assertFalse(runtime.start_limit_recovery["completed"])
                self.assertIsInstance(caught.exception.__cause__,layout.LayoutError)
                if fault == "reset":
                    self.assertEqual(runtime.start_limit_recovery["recoveryFailure"],
                                     {"code":"COMMAND_EXIT","operation":"UNIT_RESET_FAILED","returncode":9})

    def test_transport_or_nonstart_failures_do_not_enter_rate_recovery(self):
        import subprocess
        for fault in ("timeout", "io", "output", "wrong-operation"):
            with self.subTest(fault=fault):
                commands = SyntheticStartLimitCommands(); runtime = self.runtime(commands)
                if fault == "wrong-operation":
                    command = runtime._command
                    def wrong(tool,arguments,timeout=10):
                        if "start" in arguments: raise layout.LayoutError("wrong operation",code="COMMAND_EXIT",operation="UNIT_STOP",returncode=1)
                        return command(tool,arguments,timeout)
                    runtime._command = wrong
                else:
                    call = runtime.runner
                    def runner(argv,**kwargs):
                        result = call(argv,**kwargs)
                        if "start" in argv:
                            if fault == "timeout": raise subprocess.TimeoutExpired(argv,1)
                            if fault == "io": raise OSError("PRIVATE_IO")
                            result.returncode = 0; result.stdout = "x"*1048577
                        return result
                    runtime.runner = runner
                with self.assertRaises(layout.LayoutError) as caught: runtime.start()
                self.assertEqual(caught.exception.facts["code"],
                                 "COMMAND_TIMEOUT" if fault == "timeout" else "COMMAND_IO" if fault == "io" else "COMMAND_OUTPUT_LIMIT" if fault == "output" else "COMMAND_EXIT")
                self.assertEqual(commands.resets,0)
                self.assertIsNone(runtime.start_limit_recovery)


    def test_missing_prior_process_history_does_not_authorize_reset_but_normal_start_remains_possible(self):
        commands = SyntheticStartLimitCommands(); commands.active = False
        runtime = layout.NativeRuntime("plasma-plasmashell.service",runner=commands,locate=lambda tool:tool,
                                       process_reader=fake_process,process_absent=lambda pid:True)
        runtime.preflight(allow_stopped=True)
        self.assertIsNone(runtime.last_process)
        with self.assertRaises(layout.LayoutError) as caught: runtime.start()
        self.assert_original_start_failure(caught,runtime,commands)
        self.assertEqual(commands.start_attempts,1)
        self.assertEqual(commands.resets,0)
        self.assertIsNone(runtime.start_limit_recovery)
        commands = FakeCommands(); commands.active = False
        runtime = layout.NativeRuntime("plasma-plasmashell.service",runner=commands,locate=lambda tool:tool,
                                       process_reader=fake_process,process_absent=lambda pid:True)
        runtime.preflight(allow_stopped=True)
        self.assertIsNone(runtime.last_process)
        runtime.start()
        self.assertTrue(commands.active)
        self.assertIsNotNone(runtime.last_process)
        self.assertFalse(any("reset-failed" in argv for argv,_ in commands.calls))
