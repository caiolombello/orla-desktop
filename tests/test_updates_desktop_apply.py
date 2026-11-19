"""Updating the installed dock from the window: synthetic children, temporary XDG, no network."""
import json
from pathlib import Path
import sys
import unittest
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from scripts.updates_desktop import UpdatesController
from scripts.updates_desktop_state import dock_update_record
import test_updates_desktop_process as process


def metadata(version):
    return json.dumps({"KPlugin": {"Id": "org.caiodock.dock", "Version": version}}).encode()


class ApplyFixture(process.ProcessFixture):

    def setUp(self):
        super().setUp()
        self.installed = self.path / "data/plasma/plasmoids/org.caiodock.dock/metadata.json"
        self.installed.parent.mkdir(parents=True)
        self.installed.write_bytes(metadata("1.2.3"))
        self.folder = self.path / "state/orla/dock-update"
        self.calls = []

    def record(self, phase, *, kept=True, source="1.2.3", target="2.0.0"):
        """What `dock_update.apply` leaves behind, written by the synthetic child."""
        path = self.folder / "kept" / f"orla-dock-{source}.plasmoid"
        return (f"import json,pathlib\nf=pathlib.Path({str(self.folder)!r})\n(f/'kept').mkdir(parents=True,exist_ok=True)\n"
                + (f"pathlib.Path({str(path)!r}).write_bytes(b'PK')\n" if kept else "")
                + f"(f/'state.json').write_text(json.dumps(dict(phase={phase!r},**{{'from':{source!r},'to':{target!r}}},kept={str(path)!r},channel='stable',at=1)))\n")

    def controller(self, check_code, update_code, reference=None, **options):
        check = self.path / "check.py"
        check.write_text(check_code)
        update = self.path / "update.py"
        update.write_text(update_code)
        self.argv = []

        def runner(root, ref, channel):
            self.argv.append((root, ref.copy(), channel))
            return (sys.executable, ["-I", "-B", str(check)])

        def update_runner(root, action, channel):
            self.calls.append((action, channel))
            return (sys.executable, ["-I", "-B", str(update)])
        arguments = (process.ROOT,) if reference is None else (process.ROOT, reference)
        host = UpdatesController(*arguments, runner=runner, update_runner=update_runner, storage_root=self.path,
                                 opener=lambda url: True, **options)
        self.hosts.append(host)
        return host

    def available(self):
        return "print(" + repr(json.dumps(process.payload())) + ")"

    def checked(self, host):
        host.check()
        self.wait(host)
        self.assertEqual(host.state["record"]["result"]["status"], "update_available")


class ApplyTests(ApplyFixture):

    def test_apply_needs_the_installed_dock_and_an_available_release(self):
        installed_bump = (self.record("applied")
                          + f"pathlib.Path({str(self.installed)!r}).write_bytes({metadata('2.0.0')!r})\n"
                          + "print(json.dumps({'status':'updated','from':'1.2.3','to':'2.0.0'}))\n")
        host = self.controller(self.available(), installed_bump)
        self.assertEqual(host.state["role"], "installed")
        self.assertFalse(host.canApply)
        host.applyUpdate()
        self.assertEqual(self.calls, [])
        self.checked(host)
        self.assertTrue(host.canApply)
        host.applyUpdate()
        host.applyUpdate()
        self.assertTrue(host.busy)
        self.assertFalse(host.canCheck)
        self.assertEqual(host.state["dockUpdate"]["operation"], "apply")
        self.wait(host)
        self.assertEqual(self.calls, [("apply", "stable")])
        update = host.state["dockUpdate"]
        self.assertEqual((update["outcome"], update["fromVersion"], update["toVersion"], update["kept"]), ("updated", "1.2.3", "2.0.0", True))
        # The new installed version becomes the reference; the old check no longer applies.
        self.assertEqual(host.state["version"], "2.0.0")
        self.assertEqual(host.state["record"], {})
        self.assertFalse(host.canApply)
        self.assertTrue(host.canRollback)

    def test_source_or_bundle_copies_never_offer_apply(self):
        self.installed.unlink()
        host = self.controller(self.available(), "raise SystemExit(3)", reference=process.REF)
        self.checked(host)
        self.assertEqual(host.state["role"], "source")
        self.assertFalse(host.canApply)
        bundle = UpdatesController(self.path, process.REF, runner=lambda *a: (sys.executable, ["-c", "pass"]),
                                   storage_root=self.path)
        self.hosts.append(bundle)
        self.assertFalse(bundle.state["dockUpdate"]["supported"])
        self.assertFalse(bundle.canRollback)

    def test_failures_map_to_fixed_outcomes_from_exit_status_and_record(self):
        cases = (
            ("restored", self.record("rolled_back") + "import sys;sys.stderr.write('free text');raise SystemExit(1)\n"),
            ("recovery", self.record("recovery_required") + "raise SystemExit(1)\n"),
            ("failed", "import sys;sys.stderr.write('orla: release download failed');raise SystemExit(1)\n"),
            ("failed", "print('not json')\n"),
            ("failed", "import json;print(json.dumps({'status':'updated'}));raise SystemExit(1)\n"),
            ("current", "print('{\"status\": \"up_to_date\", \"installed\": \"1.2.3\"}')\n"),
        )
        for outcome, code in cases:
            with self.subTest(outcome=outcome, code=code[-50:]):
                (self.folder / "state.json").unlink(missing_ok=True)
                host = self.controller(self.available(), code)
                self.checked(host)
                host.applyUpdate()
                self.wait(host)
                self.assertEqual(host.state["dockUpdate"]["outcome"], outcome)
                self.assertEqual(host.state["version"], "1.2.3")

    def test_watchdog_leaves_a_recovery_offer_and_close_waits_for_the_install(self):
        code = self.record("installing") + "import time\ntime.sleep(30)\n"
        host = self.controller(self.available(), code, update_watchdog_ms=400)
        ready = []
        host.closeReady.connect(lambda: ready.append(True))
        self.checked(host)
        host.applyUpdate()
        QTest.qWait(150)
        self.assertFalse(host.requestClose())
        self.assertEqual(ready, [])
        self.wait(host)
        self.assertEqual(ready, [True])
        self.assertEqual(host.state["dockUpdate"]["outcome"], "recovery")

    def test_rollback_uses_the_kept_version_from_the_record(self):
        exec(compile(self.record("applied"), "record", "exec"))
        host = self.controller("raise SystemExit(3)", self.record("rolled_back") + "print(json.dumps({'status':'rolled_back','installed':'1.2.3'}))\n")
        self.assertTrue(host.canRollback)
        self.assertFalse(host.canApply)
        host.rollbackUpdate()
        self.wait(host)
        self.assertEqual(self.calls, [("rollback", "stable")])
        self.assertEqual(host.state["dockUpdate"]["outcome"], "rolled_back")
        self.assertFalse(host.canRollback)

    def test_record_reader_returns_fixed_fields_only(self):
        self.assertIsNone(dock_update_record(self.path / "state"))
        exec(compile(self.record("applied"), "record", "exec"))
        self.assertEqual(dock_update_record(self.path / "state"),
                         dict(phase="applied", fromVersion="1.2.3", toVersion="2.0.0", kept=True))
        state = self.folder / "state.json"
        value = json.loads(state.read_text())
        for change in ({"phase": "pwned"}, {"from": "<b>x</b>"}, {"to": 7}):
            state.write_text(json.dumps({**value, **change}))
            self.assertEqual(dock_update_record(self.path / "state")["phase"], "invalid")
        state.write_text(json.dumps({**value, "kept": "/etc/passwd"}))
        self.assertFalse(dock_update_record(self.path / "state")["kept"])
        state.write_text("{")
        self.assertEqual(dock_update_record(self.path / "state")["phase"], "invalid")


class ApplyViewTests(ApplyFixture):

    def view(self, host):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
        engine.rootContext().setContextProperty("updatesController", host)
        engine.load(QUrl.fromLocalFile(str(process.ROOT / "workspace/Updates.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.resize(350, 620)
        QTest.qWait(30)

        def cleanup():
            host.requestClose()
            self.wait(host)
            window.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.app.processEvents()
            self.assertEqual(warnings, [])
        self.addCleanup(cleanup)
        return window

    def item(self, window, name):
        found = window.findChild(QQuickItem, name)
        self.assertIsNotNone(found, name)
        return found

    def test_apply_is_the_one_primary_action_and_reports_the_restart(self):
        code = (self.record("applied") + f"pathlib.Path({str(self.installed)!r}).write_bytes({metadata('2.0.0')!r})\n"
                + "print(json.dumps({'status':'updated','from':'1.2.3','to':'2.0.0'}))\n")
        host = self.controller(self.available(), code)
        window = self.view(host)
        check, apply, rollback = (self.item(window, name) for name in ("updatesCheck", "updatesApply", "updatesRollback"))
        self.assertFalse(apply.isVisible())
        self.assertEqual(check.property("variant"), "primary")
        self.checked(host)
        QTest.qWait(30)
        self.assertTrue(apply.isVisible())
        self.assertEqual(apply.property("text"), "Atualizar a dock para 2.0.0")
        self.assertEqual((check.property("variant"), apply.property("variant")), ("secondary", "primary"))
        apply.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Return)
        self.assertIn("Atualizando a dock", self.item(window, "updatesStatus").property("text"))
        self.wait(host)
        QTest.qWait(30)
        self.assertEqual(self.item(window, "updatesApplyResult").property("text"), "Dock atualizada de 1.2.3 para 2.0.0.")
        self.assertTrue(self.item(window, "updatesRestart").isVisible())
        self.assertFalse(apply.isVisible())
        self.assertTrue(rollback.isVisible())
        self.assertEqual(rollback.property("text"), "Voltar para a dock 1.2.3")
        current = window.activeFocusItem()
        self.assertTrue(check.hasActiveFocus(), (current.objectName(), current.metaObject().className()) if current else None)
        self.assertEqual(self.calls, [("apply", "stable")])

    def test_an_unfinished_update_left_outside_offers_going_back(self):
        exec(compile(self.record("installing"), "record", "exec"))
        host = self.controller("raise SystemExit(3)", "raise SystemExit(3)")
        window = self.view(host)
        self.assertTrue(self.item(window, "updatesRollback").isVisible())
        self.assertEqual(self.item(window, "updatesApplyResult").property("text"),
                         "Uma atualização da dock não terminou. Volte à versão anterior.")


if __name__ == "__main__":
    unittest.main()
