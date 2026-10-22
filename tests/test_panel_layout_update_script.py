"""Behavioral fixed-script tests with synthetic Plasma objects, no native session."""
import copy
import json
from pathlib import Path
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine

from scripts import panel_layout as layout
from tests.test_panel_layout import inventory, manifest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"showOrlaMenu": False, "showApplicationName": False, "showControlCenter": True}


def update_plan():
    old = inventory()
    types = ["org.orla.bar", "org.kde.plasma.appmenu", "org.kde.plasma.panelspacer",
             "org.kde.plasma.systemtray", "org.kde.plasma.digitalclock"]
    ids = [35, 30, 31, 7, 22]
    old["panels"][0]["widgets"] = [dict(id=value, type=kind, index=index)
                                      for index, (value, kind) in enumerate(zip(ids, types))]
    old["knownWidgetTypes"] = sorted(set(old["knownWidgetTypes"] + ["org.caiodock.dock"]))
    old["panels"].append({"id": 32, "type": "org.kde.panel", "screen": 7, "height": 88,
        "widgets": [{"id": 34, "type": "org.caiodock.dock", "index": 0}],
        "marker": {"token": "", "schemaVersion": 0}})
    data = manifest()
    data["reuseWidgetIds"] = dict(zip([item["key"] for item in data["modules"]], ids))
    origin = layout.build_plan(data, old)
    owned = {"panelId": 36, "token": origin["planId"], "screen": 7, "height": 32,
             "widgets": copy.deepcopy(old["panels"][0]["widgets"]), "nativeValidated": False}
    plan = {"schemaVersion": 1, "kind": "managed-panel-update", "operation": "add-control-center",
        "parent": {"transactionId": origin["planId"] + "-" + "1" * 16, "receiptSha256": "a" * 64},
        "origin": {"transactionId": origin["planId"] + "-" + "1" * 16, "applyReceiptSha256": "b" * 64},
        "originPlan": origin, "inventory": layout._managed_inventory(origin, owned), "owned": owned,
        "baseline": {name: {"exists": True, "mode": 0o640, "sha256": "c" * 64} for name in layout.CONFIG_FILES},
        "service": "plasma-plasmashell.service", "serviceIdentity": {"unit": "plasma-plasmashell.service",
            "executable": "/synthetic/plasmashell", "argv": "/synthetic/plasmashell --no-respawn",
            "target": {"configHome": "/synthetic/config"}},
        "entry": {"key": "control-center", "config": dict(CONFIG)},
        "insertionIndex": 4, "restoreCompatible": True}
    plan["planId"] = layout._hash(plan)
    return plan


class UpdateScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def engine(self, plan):
        engine = QJSEngine()
        stub = ROOT / "tests/PanelLayoutStub.js"
        source = stub.read_text().replace("__TYPES__", json.dumps(plan["inventory"]["knownWidgetTypes"]))
        result = engine.evaluate(source)
        self.assertFalse(result.isError(), result.toString())
        # Reuse the existing API stub, then instrument writes/reloads/adds independently.
        setup = """
            allPanels = []; nextId = 100;
            var configWrites = [], configReads = [], configReloads = [], additions = [], panelWrites = [];
            var fakeReadback = false, fakeNewId = null, fakeNewType = null;
            var writeFailure = false, reloadFailure = false, afterAdd = null, ignoredWriteKey = null, fakeMarkerValue = null;
            var managed = new Panel('org.kde.panel'); managed.id = 36;
            managed.values = {'OrlaManaged/token': __TOKEN__, 'OrlaManaged/schemaVersion': 1,
                'General/syntheticPanelSetting': 'preserve-panel'};
            managed.items = __WIDGETS__.map(value => {
                var widget = makeWidget(value.id, value.type, managed);
                widget.values = {'General/syntheticSetting': 'preserve-' + value.id};
                widget.currentConfigGroup = ['SyntheticOriginalGroup'];
                return widget;
            });
            var foreign = new Panel('org.kde.panel'); foreign.id = 32; foreign.height = 88;
            foreign.items = [makeWidget(34, 'org.caiodock.dock', foreign)];
            foreign.items[0].values = {'General/syntheticPins': 'preserve-dock'};
            function instrument(widget) {
                var read = widget.readConfig;
                widget.readConfig = function(key, fallback) {
                    configReads.push({id:this.id, group:this.currentConfigGroup.slice(), key:key});
                    return read.call(this,key,fallback);
                };
                var write = widget.writeConfig;
                widget.writeConfig = function(key, value) {
                    configWrites.push({id:this.id, group:this.currentConfigGroup.slice(), key:key, value:value});
                    if (writeFailure) throw new Error('synthetic write failure');
                    if (key !== ignoredWriteKey) write.call(this, key,
                        key === 'token' && fakeMarkerValue !== null ? fakeMarkerValue : value);
                };
                widget.reloadConfig = function() {
                    configReloads.push(this.id);
                    if (reloadFailure) throw new Error('synthetic reload failure');
                    if (fakeReadback) this.values['General/showControlCenter'] = false;
                };
            }
            allPanels.forEach(panel => {
                var write = panel.writeConfig;
                panel.writeConfig = function(key, value) {
                    panelWrites.push({id:this.id,key:key,value:value}); write.call(this,key,value);
                };
                panel.items.forEach(instrument);
            });
            var add = managed.addWidget;
            managed.addWidget = function(type) {
                additions.push(type);
                var widget = add.call(this,type);
                if (widget) {
                    if (fakeNewId !== null) widget.id = fakeNewId;
                    if (fakeNewType !== null) widget.type = fakeNewType;
                    instrument(widget);
                }
                if (afterAdd) afterAdd(widget);
                return widget;
            };
            var panelCreations = 0;
            Panel = function() { panelCreations++; throw new Error('unexpected panel creation'); };
        """
        setup = setup.replace("__TOKEN__", json.dumps(plan["owned"]["token"]))
        setup = setup.replace("__WIDGETS__", json.dumps(plan["owned"]["widgets"]))
        result = engine.evaluate(setup)
        self.assertFalse(result.isError(), result.toString())
        return engine

    def source(self, plan, *, connector="DP-1"):
        # The Python renderer is implemented in a separate slice; this is its exact envelope.
        request = {"operation": "update-owned", "updatePlan": plan, "connector": connector}
        return (ROOT / "scripts/panel_layout.js").read_text().replace("__ORLA_REQUEST__", json.dumps(request))

    def read(self, engine, expression):
        result = engine.evaluate("JSON.stringify(" + expression + ")")
        self.assertFalse(result.isError(), result.toString())
        return json.loads(result.toString())

    def preserved_snapshot(self, engine):
        return self.read(engine, """panels().map(panel => ({id:panel.id, screen:panel.screen,
            height:panel.height, values:panel.values,
            widgets:panel.items.filter(widget => [35,30,31,7,22,34].indexOf(widget.id) >= 0)
                .map(widget => ({id:widget.id, type:widget.type, values:widget.values,
                    group:widget.currentConfigGroup}))}))""")

    def assert_no_pre_mutation(self, engine):
        self.assertEqual(self.read(engine, "additions"), [])
        self.assertEqual(self.read(engine, "configWrites"), [])
        self.assertEqual(self.read(engine, "configReloads"), [])
        self.assertEqual(self.read(engine, "panelWrites"), [])
        self.assertEqual(self.read(engine, "removed"), [])
        self.assertEqual(self.read(engine, "panelCreations"), 0)
        self.assertEqual(self.read(engine, "messages"), [])

    def test_only_new_cc_gets_general_trio_write_reload_and_readback(self):
        plan = update_plan(); engine = self.engine(plan)
        before = self.preserved_snapshot(engine)
        result = engine.evaluate(self.source(plan))
        self.assertFalse(result.isError(), result.toString())
        self.assertEqual(self.preserved_snapshot(engine), before)
        self.assertEqual(self.read(engine, "configWrites"),
            [dict(id=102, group=["OrlaManagedUpdate"], key="token", value=plan["planId"])]
            + [dict(id=102, group=["General"], key=key, value=value) for key,value in CONFIG.items()])
        self.assertEqual(self.read(engine, "configReads"),
            [dict(id=102, group=["OrlaManagedUpdate"], key="token")]
            + [dict(id=102, group=["General"], key=key) for key in CONFIG])
        self.assertEqual(self.read(engine, "configReloads"), [102])
        self.assertEqual(self.read(engine, "panelWrites"), [])
        self.assertEqual(self.read(engine, "managed.items[5].values['OrlaManagedUpdate/token']"), plan["planId"])
        self.assertEqual(self.read(engine, "managed.items[5].currentConfigGroup"), [])
        self.assertEqual(self.read(engine, "indexWrites"), [])

    def test_exact_inventory_and_marker_refuse_before_add(self):
        changes = (
            "managed.values['OrlaManaged/token']='0'.repeat(64)",
            "managed.values['OrlaManaged/schemaVersion']=2",
            "managed.height=48", "managed.screen=2",
            "managed.items[0].type='foreign.widget'",
            "foreign.height=90", "foreign.items.push(makeWidget(99,'foreign.widget',foreign))",
            "knownWidgetTypes.push('foreign.widget')",
        )
        for change in changes:
            with self.subTest(change=change):
                plan = update_plan(); engine = self.engine(plan); engine.evaluate(change)
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assert_no_pre_mutation(engine)

    def test_typed_unique_prior_ids_roles_and_insertion_refuse_before_add(self):
        changes = [
            lambda p:p["owned"]["widgets"][0].update(id="35"),
            lambda p:p["owned"]["widgets"][0].update(id=True),
            lambda p:p["owned"]["widgets"][0].update(id=0),
            lambda p:p["owned"]["widgets"][0].update(id=3.5),
            lambda p:p["owned"]["widgets"][1].update(id=35),
            lambda p:p["owned"]["widgets"][0].update(index="0"),
            lambda p:p["owned"]["widgets"][0].update(type="foreign.widget"),
            lambda p:p["owned"].update(panelId="36"),
            lambda p:p["owned"].update(nativeValidated=True),
            lambda p:p["originPlan"]["manifest"]["modules"][0].update(key="control-center"),
            lambda p:p["originPlan"]["manifest"]["modules"][1].update(key="menu"),
        ]
        for value in ("4", True, -1, 0, 3, 4.5, 5):
            changes.append(lambda p,v=value:p.update(insertionIndex=v))
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                plan = update_plan(); engine = self.engine(plan); change(plan)
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assert_no_pre_mutation(engine)

    def test_strict_entry_and_operation_refuse_before_add(self):
        changes = (
            lambda p:p["entry"]["config"].update(showOrlaMenu=True),
            lambda p:p["entry"]["config"].update(showApplicationName=True),
            lambda p:p["entry"]["config"].update(showControlCenter="true"),
            lambda p:p["entry"]["config"].update(arbitrary=True),
            lambda p:p["entry"].update(key="menu"),
            lambda p:p.update(kind="managed-update"),
            lambda p:p.update(schemaVersion=True),
            lambda p:p.update(operation="replace-panel"),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                plan = update_plan(); engine = self.engine(plan); change(plan)
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assert_no_pre_mutation(engine)

    def test_invalid_new_id_or_type_never_writes_or_returns_owned(self):
        changes = ["fakeFailType='org.orla.bar'", "fakeNewType='foreign.widget'"]
        for value in (35, 34, "102", True, 0, -1, 4.5):
            changes.append("fakeNewId=" + json.dumps(value))
        for change in changes:
            with self.subTest(change=change):
                plan = update_plan(); engine = self.engine(plan); engine.evaluate(change)
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assertEqual(self.read(engine, "configWrites"), [])
                self.assertEqual(self.read(engine, "configReloads"), [])
                self.assertEqual(self.read(engine, "messages"), [])
                self.assertEqual(self.read(engine, "additions"), ["org.orla.bar"])

    def test_private_marker_must_persist_before_any_general_write(self):
        changes = ("ignoredWriteKey='token'", "fakeMarkerValue=''", "fakeMarkerValue='0'.repeat(64)")
        for change in changes:
            with self.subTest(change=change):
                plan = update_plan(); engine = self.engine(plan); engine.evaluate(change)
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assertIn("marker readback failed", result.toString())
                self.assertEqual(self.read(engine, "configWrites"),
                    [dict(id=102, group=["OrlaManagedUpdate"], key="token", value=plan["planId"])])
                self.assertEqual(self.read(engine, "configReloads"), [])
                self.assertEqual(self.read(engine, "messages"), [])

    def test_invalid_update_token_refuses_before_add(self):
        for value in (None, True, 42, "", "a" * 63, "a" * 65, "A" * 64, "z" * 64):
            with self.subTest(value=value):
                plan = update_plan(); engine = self.engine(plan); plan["planId"] = value
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assert_no_pre_mutation(engine)

    def test_missing_each_written_boolean_fails_opposite_default_readback(self):
        for key in CONFIG:
            with self.subTest(key=key):
                plan = update_plan(); engine = self.engine(plan)
                engine.evaluate("ignoredWriteKey=" + json.dumps(key))
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assertIn("configuration readback failed", result.toString())
                self.assertEqual(self.read(engine, "messages"), [])
                self.assertEqual(self.read(engine, "configReloads"), [102])
                self.assertEqual({item["id"] for item in self.read(engine, "configWrites")}, {102})

    def test_write_reload_readback_and_post_add_structure_failures_never_return_owned(self):
        changes = ("writeFailure=true", "reloadFailure=true", "fakeReadback=true",
            "afterAdd=function(){foreign.height=90}",
            "afterAdd=function(){managed.height=48}",
            "afterAdd=function(){managed.values['OrlaManaged/token']='0'.repeat(64)}",
            "afterAdd=function(){managed.items.push(makeWidget(99,'foreign.widget',managed))}")
        for change in changes:
            with self.subTest(change=change):
                plan = update_plan(); engine = self.engine(plan); engine.evaluate(change)
                result = engine.evaluate(self.source(plan))
                self.assertTrue(result.isError(), result.toString())
                self.assertEqual(self.read(engine, "messages"), [])
                self.assertEqual(self.read(engine, "additions"), ["org.orla.bar"])
                self.assertEqual(self.read(engine, "panelWrites"), [])
                self.assertEqual({item["id"] for item in self.read(engine, "configWrites")}, {102})
                self.assertEqual(self.read(engine, "removed"), [])

    def test_enabled_prior_cc_refuses_but_disabled_preset_cc_is_not_a_role(self):
        plan = update_plan()
        plan["originPlan"]["manifest"]["modules"].insert(4,
            {"key":"control-center","enabled":False,"config":dict(CONFIG)})
        engine = self.engine(plan)
        result = engine.evaluate(self.source(plan))
        self.assertFalse(result.isError(), result.toString())
        plan = update_plan()
        plan["originPlan"]["manifest"]["modules"].insert(4,
            {"key":"control-center","enabled":True,"config":dict(CONFIG)})
        engine = self.engine(plan)
        result = engine.evaluate(self.source(plan))
        self.assertTrue(result.isError(), result.toString())
        self.assert_no_pre_mutation(engine)

    def test_actual_append_order_is_left_for_existing_cold_reorder(self):
        plan = update_plan(); engine = self.engine(plan)
        engine.evaluate("managed.delayedIndex=true;readyOrder(managed);fakeNativeEnumeration=true")
        # Start with exact prior order, then append leaves the new item's native index pending.
        engine.evaluate("managed.layoutOrder=" + json.dumps([35,30,31,7,22]))
        result = engine.evaluate(self.source(plan))
        self.assertFalse(result.isError(), result.toString())
        owned = json.loads(engine.evaluate("messages[0]").toString())
        self.assertEqual([item["index"] for item in owned["widgets"]], list(range(6)))
        self.assertEqual(self.read(engine, "indexWrites"), [])
        engine.evaluate("readyOrder(managed)")
        self.assertNotEqual(self.read(engine, "managed.layoutOrder"), [item["id"] for item in owned["widgets"]])
        inspection = layout.render_script("inspect", connector="DP-1")
        self.assertFalse(engine.evaluate(inspection).isError())
        actual = json.loads(engine.evaluate("messages[messages.length-1]").toString())
        reorder = layout.render_script("reorder-owned", panel_id=owned["panelId"], token=owned["token"],
            connector="DP-1", expected_inventory=actual, ordered_widgets=owned["widgets"])
        result = engine.evaluate(reorder)
        self.assertFalse(result.isError(), result.toString())
        self.assertEqual(self.read(engine, "managed.layoutOrder"), [item["id"] for item in owned["widgets"]])

    def test_update_adds_cc_in_same_panel_and_returns_intended_dense_order(self):
        plan = update_plan(); engine = self.engine(plan)
        result = engine.evaluate(self.source(plan))
        self.assertFalse(result.isError(), result.toString())
        owned = json.loads(engine.evaluate("messages[0]").toString())
        self.assertEqual({key: owned[key] for key in ("panelId", "token", "screen", "height", "nativeValidated")},
                         {key: plan["owned"][key] for key in ("panelId", "token", "screen", "height", "nativeValidated")})
        self.assertEqual([widget["id"] for widget in owned["widgets"]], [35, 30, 31, 7, 102, 22])
        self.assertEqual([widget["index"] for widget in owned["widgets"]], list(range(6)))
        self.assertEqual(self.read(engine, "additions"), ["org.orla.bar"])
        self.assertEqual(self.read(engine, "panelCreations"), 0)
        self.assertEqual(self.read(engine, "removed"), [])


if __name__ == "__main__":
    unittest.main()
