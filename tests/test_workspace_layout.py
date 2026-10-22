"""Portable composition consumer over synthetic runtime and real private banks."""
import copy
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from scripts import panel_layout as layout
from scripts.workspace_layout import CompositionSession
from test_panel_layout import FakeRuntime, inventory, manifest


class CompositionSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "config"
        self.config.mkdir()
        self.original = {}
        for name in layout.CONFIG_FILES:
            path = self.config / name
            data = ("private original " + name).encode()
            path.write_bytes(data)
            path.chmod(0o640)
            self.original[name] = data
        self.store = layout.FileStore(self.config, self.root / "state")
        self.runtime = FakeRuntime(self.config)
        self.session = CompositionSession(self.runtime, self.store, manifest())

    def test_real_backend_apply_disable_restore_and_new_apply_cycle(self):
        initial = self.session.read("DP-1")
        self.assertEqual(initial, {"phase": "UNMANAGED", "shellRunning": True,
                                   "inventory": inventory(), "recordPresent": False})
        review = self.session.review_apply(manifest())
        self.assertEqual(set(review), {"token", "action", "connector", "replacePanelIds",
                                      "reuseWidgetIds", "modules", "height", "selectedPanels"})
        self.assertEqual(review["selectedPanels"], inventory()["panels"])
        self.assertEqual(review["modules"], ["menu", "global-menu", "spacer", "tray", "clock"])
        for action, phase in (("apply", "COMMITTED"), ("disable", "DISABLED"), ("restore", "RESTORED")):
            if action != "apply":
                review = self.session.review_operation(action)
            self.assertEqual(self.session.execute(review["token"]),
                             {"phase": phase, "action": action, "connector": "DP-1"})
        for name, data in self.original.items():
            self.assertEqual((self.config / name).read_bytes(), data)
            self.assertEqual((self.config / name).stat().st_mode & 0o777, 0o640)
        review = self.session.review_apply(manifest())
        self.assertEqual(self.session.execute(review["token"])["phase"], "COMMITTED")
        self.assertEqual(self.runtime.events.count("apply"), 2)
        self.assertEqual(self.runtime.events.count("remove-owned"), 1)

    def test_read_rejects_invalid_inventory_without_any_mutation(self):
        invalid = inventory()
        invalid["screenIds"] = [True]
        self.runtime.inspect = lambda connector="": invalid
        with self.assertRaises(layout.LayoutError):
            self.session.read("DP-1")
        self.assertEqual(self.runtime.events, ["preflight"])
        self.assertFalse(self.store.state_home.exists())

    def tree(self):
        return {str(path.relative_to(self.root)): (path.read_bytes(), path.stat().st_mode & 0o777,
                                                   path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def apply(self):
        return self.session.execute(self.session.review_apply(manifest())["token"])

    def test_choose_review_discard_are_read_only_and_summaries_are_detached(self):
        before = self.tree()
        template = manifest()
        session = CompositionSession(self.runtime, self.store, template)
        template["panel"]["height"] = 64
        self.assertEqual(session.template["panel"]["height"], 32)
        info = session.read("DP-1")
        info["inventory"]["panels"].clear()
        data = manifest()
        review = session.review_apply(data)
        data["panel"]["height"] = 60
        review["selectedPanels"][0]["widgets"].clear()
        review["reuseWidgetIds"].clear()
        review["modules"].clear()
        review["height"] = 64
        self.assertEqual(self.tree(), before)
        self.assertFalse(self.store.state_home.exists())
        session.execute(review["token"])
        self.assertEqual(self.runtime.plan["manifest"], manifest())
        self.assertEqual(self.runtime.plan["selectedPanels"], inventory()["panels"])
        review = session.review_operation("restore")
        before = self.tree()
        session.discard()
        with self.assertRaises(layout.LayoutError): session.execute(review["token"])
        self.assertEqual(self.tree(), before)

    def test_read_discard_and_new_review_invalidate_old_tokens(self):
        for invalidate in (lambda: self.session.discard(), lambda: self.session.read("DP-1"),
                           lambda: self.session.review_apply(manifest())):
            with self.subTest(invalidate=invalidate):
                review = self.session.review_apply(manifest())
                invalidate()
                with self.assertRaises(layout.LayoutError): self.session.execute(review["token"])
        self.assertFalse(self.store.state_home.exists())
        self.assertNotIn("stop", self.runtime.events)

    def test_failed_new_review_also_invalidates_previous_intention(self):
        review = self.session.review_apply(manifest())
        invalid = manifest()
        invalid["replacePanelIds"] = []
        with self.assertRaises(layout.LayoutError): self.session.review_apply(invalid)
        with self.assertRaises(layout.LayoutError): self.session.execute(review["token"])
        self.assertNotIn("stop", self.runtime.events)

    def test_successful_token_is_single_use(self):
        review = self.session.review_apply(manifest())
        self.session.execute(review["token"])
        before = self.tree()
        events = self.runtime.events[:]
        with self.assertRaises(layout.LayoutError): self.session.execute(review["token"])
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.runtime.events, events)

    def test_config_bytes_modes_absence_inventory_identity_and_unit_drift_refuse_before_stop(self):
        changes = ("bytes", "mode", "absent", "inventory", "identity", "unit", "receipt")
        for change in changes:
            with self.subTest(change=change):
                # Each refusal gets a new review against the latest valid baseline.
                runtime = FakeRuntime(self.config)
                store = layout.FileStore(self.config, self.root / ("state-" + change))
                session = CompositionSession(runtime, store, manifest())
                review = session.review_apply(manifest())
                path = self.config / layout.CONFIG_FILES[0]
                original = path.read_bytes(), path.stat().st_mode & 0o777
                if change == "bytes": path.write_bytes(b"explicit synthetic edit")
                elif change == "mode": path.chmod(0o600)
                elif change == "absent": path.unlink()
                elif change == "inventory":
                    runtime.extra_panels = [{"id": 99, "type": "org.kde.panel", "screen": 2,
                                             "height": 30, "widgets": [],
                                             "marker": {"token": "", "schemaVersion": 0}}]
                elif change == "identity": runtime.identity["argv"] = "/usr/bin/plasmashell"
                elif change == "unit": runtime.unit = "another-plasma.service"
                else: store.prepare(layout.build_plan(manifest(), inventory()), runtime.unit, runtime.identity)
                before = self.tree()
                with self.assertRaises(layout.LayoutError): session.execute(review["token"])
                self.assertEqual(self.tree(), before)
                self.assertNotIn("stop", runtime.events)
                self.assertNotIn("start", runtime.events)
                with self.assertRaises(layout.LayoutError): session.execute(review["token"])
                path.write_bytes(original[0]); path.chmod(original[1])

    def test_receipt_numeric_boolean_lookalike_drift_is_not_equal(self):
        self.apply()
        review = self.session.review_operation("disable")
        receipt = self.store.current()
        receipt["owned"]["nativeValidated"] = 0
        self.store.save(receipt)
        self.runtime.events.clear()
        before = self.tree()
        with self.assertRaises(layout.LayoutError): self.session.execute(review["token"])
        self.assertEqual(self.tree(), before)
        self.assertNotIn("stop", self.runtime.events)

    def test_config_change_during_observation_is_refused_without_dispatch(self):
        review = self.session.review_apply(manifest())
        inspect = self.runtime.inspect
        def changing(connector=""):
            (self.config / layout.CONFIG_FILES[1]).write_bytes(b"synthetic concurrent edit")
            return inspect(connector)
        self.runtime.inspect = changing
        with self.assertRaisesRegex(layout.LayoutError, "while reading"):
            self.session.execute(review["token"])
        self.assertNotIn("stop", self.runtime.events)
        self.assertFalse(self.store.state_home.exists())

    def test_stopped_read_has_no_inventory_and_apply_requires_running(self):
        self.runtime.is_stopped = True
        self.runtime.inspect = lambda *_: self.fail("stopped shell must not be inspected")
        self.assertEqual(self.session.read(), {"phase": "UNMANAGED", "shellRunning": False,
                                              "inventory": None, "recordPresent": False})
        with self.assertRaises(layout.LayoutError): self.session.review_apply(manifest())
        self.assertNotIn("start", self.runtime.events)
        self.assertFalse(self.store.state_home.exists())

    def test_recover_dispatches_real_stopped_prepared_transaction(self):
        self.store.prepare(layout.build_plan(manifest(), inventory()), self.runtime.unit, self.runtime.identity)
        self.runtime.is_stopped = True
        before = self.tree()
        review = self.session.review_operation("recover")
        self.assertEqual(review["phase"], "PREPARED")
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.session.execute(review["token"]),
                         {"phase": "RESTORED", "action": "recover", "connector": "DP-1"})
        self.assertFalse(self.runtime.is_stopped)
        self.assertNotIn("apply", self.runtime.events)

    def test_backend_failure_preserves_primary_and_consumes_token_without_retry(self):
        from unittest import mock
        self.apply()
        review = self.session.review_operation("disable")
        self.runtime.failure = "disable"
        with mock.patch.object(self.store, "restore_before", side_effect=OSError("synthetic recovery failure")):
            with self.assertRaises(layout.LayoutError) as raised:
                self.session.execute(review["token"])
        self.assertIn("uncertain remove failure", str(raised.exception.__cause__))
        receipt = self.store.current()
        self.assertEqual(receipt["phase"], "RECOVERY_REQUIRED")
        self.assertEqual(set(receipt["diagnostics"]), {"primary", "recovery"})
        before = self.tree()
        with self.assertRaises(layout.LayoutError): self.session.execute(review["token"])
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.runtime.events.count("remove-owned"), 1)

    def test_missing_receipt_and_unsupported_actions_are_read_only(self):
        before = self.tree()
        for action in ("disable", "restore", "recover", "enable", "update"):
            with self.subTest(action=action), self.assertRaises(layout.LayoutError):
                self.session.review_operation(action)
        self.assertEqual(self.tree(), before)
        self.assertFalse(self.store.state_home.exists())

    def test_valid_schema2_receipt_can_disable_and_restore_via_real_backend(self):
        from test_panel_layout_update import UpdateRuntime
        for name, data in {
            layout.CONFIG_FILES[0]: b"[General]\nlabel=synthetic\n[Containments][28]\nplugin=org.kde.panel\n",
            layout.CONFIG_FILES[1]: b"[General]\nsetting=foreign\n[PlasmaViews][Panel 28]\nthickness=32\n",
        }.items():
            (self.config / name).write_bytes(data)
        runtime = UpdateRuntime(self.config)
        session = CompositionSession(runtime, self.store, manifest())
        session.execute(session.review_apply(manifest())["token"])
        parent = self.store.current()
        plan = layout.build_update_plan(parent, runtime, self.store)
        updated = layout.update_layout(plan, runtime, self.store)
        self.assertEqual(updated["schemaVersion"], 2)
        self.assertEqual(session.read("DP-1")["phase"], "COMMITTED")
        for action, phase in (("disable", "DISABLED"), ("restore", "RESTORED")):
            review = session.review_operation(action)
            self.assertEqual(session.execute(review["token"])["phase"], phase)

    def test_replacing_store_root_after_review_is_not_a_new_authority(self):
        review = self.session.review_apply(manifest())
        self.session.store = layout.FileStore(self.config, self.root / "different-state")
        with self.assertRaises(layout.LayoutError): self.session.execute(review["token"])
        self.assertNotIn("stop", self.runtime.events)
        self.assertFalse((self.root / "different-state").exists())

    def test_module_and_script_import_routes_are_inert_in_isolated_contexts(self):
        source = Path(__file__).resolve().parents[1]
        for pythonpath, statement in ((source, "from scripts.workspace_layout import CompositionSession"),
                                      (source / "scripts", "from workspace_layout import CompositionSession")):
            with self.subTest(statement=statement):
                env = os.environ.copy()
                env["PYTHONPATH"] = str(pythonpath)
                for key in ("DBUS_SESSION_BUS_ADDRESS", "DBUS_SYSTEM_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS"):
                    env[key] = "unix:path=" + str(self.root / ("absent-" + key))
                for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE"):
                    env.pop(key, None)
                result = subprocess.run([sys.executable, "-B", "-c", statement + "; CompositionSession(None, None, {})"],
                                        cwd=self.root, env=env, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
