"""Production setup view and host, with a passive synthetic backend only."""

from pathlib import Path
import unittest

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from scripts.workspace_setup import WorkspaceController
from test_workspace_setup import Session

ROOT = Path(__file__).resolve().parents[1]


class FixtureSession(Session):
    phase = "UNMANAGED"
    allowed_connectors = ("DP-1",)
    read_override = None
    panels = [dict(id=28, screen=7, widgets=[dict(id=7, type="org.kde.plasma.systemtray")]),
              dict(id=32, screen=7, widgets=[dict(id=34, type="org.caiodock.dock")])]

    def read(self, connector=""):
        if connector and connector not in self.allowed_connectors:
            raise ValueError("synthetic removed connector")
        result = super().read(connector)
        if self.read_override is not None:
            return self.read_override.copy()
        result["phase"] = self.phase
        result["recordPresent"] = self.phase not in ("UNMANAGED", "RESTORED")
        result["inventory"] = dict(selectedScreen=dict(id=7) if connector else None, panels=self.panels)
        return result

    def review_apply(self, manifest):
        result = super().review_apply(manifest)
        result["connector"] = manifest["screen"]["connector"]
        result.update(height=32, modules=["menu", "global-menu", "tray", "clock"],
                      selectedPanels=[self.panels[0]])
        return result


class ViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.session = FixtureSession()
        self.host = WorkspaceController(self.session, {"screen": {}, "replacePanelIds": []}, ["DP-1"])
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.rootContext().setContextProperty("workspaceController", self.host)
        self.engine.load(QUrl.fromLocalFile(str(ROOT / "workspace/Workspace.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.window.resize(350, 620)
        self.host.refresh(""); self.wait()

    def tearDown(self):
        self.session.gate.set(); self.wait()
        self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def wait(self):
        for _ in range(200):
            QTest.qWait(10)
            if not self.host.busy:
                QTest.qWait(20)
                return
        self.fail("setup operation did not finish")

    def control(self, name):
        result = self.window.findChild(QQuickItem, name)
        if result is None:
            def named(item):
                if item.objectName() == name:
                    return item
                return next((found for child in item.childItems() if (found := named(child)) is not None), None)
            result = named(self.window.contentItem())
        self.assertIsNotNone(result, name)
        return result

    def focus(self, item):
        expression = QQmlExpression(self.engine.rootContext(), item, "forceActiveFocus(Qt.TabFocusReason)")
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        QTest.qWait(30)

    def click(self, item):
        point = item.mapToScene(QPointF(item.width()/2, item.height()/2))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        self.wait()

    def select(self):
        monitor = self.control("compositionMonitor")
        self.focus(monitor)
        QTest.keyClick(self.window, Qt.Key_Down)
        self.wait()
        self.assertEqual(monitor.property("currentText"), "DP-1")
        self.focus(self.control("compositionPanel28"))
        QTest.keyClick(self.window, Qt.Key_Space)
        self.wait()

    def test_keyboard_selection_review_back_and_single_confirmation(self):
        self.select()
        self.assertFalse(self.control("compositionPanel32").isEnabled())
        self.click(self.control("compositionPrepare"))
        self.assertTrue(self.control("compositionConfirm").isVisible())
        self.focus(self.control("compositionBack"))
        QTest.keyClick(self.window, Qt.Key_Space); self.wait()
        self.assertEqual(self.host.review, {})
        self.assertFalse(any(row[0] == "execute" for row in self.session.calls))
        self.click(self.control("compositionPrepare"))
        self.focus(self.control("compositionConfirm"))
        QTest.keyClick(self.window, Qt.Key_Space); self.wait()
        self.assertEqual(len([row for row in self.session.calls if row[0] == "execute"]), 1)

    def test_short_viewport_reveals_keyboard_control_and_keeps_footer_reachable(self):
        self.select()
        self.window.resize(350, 240)
        check = self.control("compositionPanel28")
        self.focus(check)
        viewport = self.control("compositionScroll").property("contentItem")
        point = check.mapToItem(viewport, QPointF(0, 0))
        self.assertGreaterEqual(point.y(), 0)
        self.assertLessEqual(point.y() + check.height(), viewport.height())
        primary = self.control("compositionPrepare")
        self.assertLessEqual(primary.mapToScene(QPointF(0, primary.height())).y(), self.window.height())

    def test_removed_monitor_allows_neutral_refresh_and_explicit_new_selection(self):
        self.select()
        self.session.allowed_connectors = ("DP-2",)
        self.host.set_connectors(["DP-2"])
        QTest.qWait(30)
        self.click(self.control("compositionRefresh"))
        self.assertEqual(self.host.state["phase"], "UNMANAGED")
        monitor = self.control("compositionMonitor")
        self.assertEqual(monitor.property("currentIndex"), -1)
        self.focus(monitor)
        QTest.keyClick(self.window, Qt.Key_Down); self.wait()
        self.assertEqual(monitor.property("currentText"), "DP-2")
        self.assertFalse(self.control("compositionPrepare").isEnabled())
        self.focus(self.control("compositionPanel28"))
        QTest.keyClick(self.window, Qt.Key_Space); self.wait()
        self.click(self.control("compositionPrepare"))
        self.assertEqual(self.host.review["connector"], "DP-2")
        self.assertFalse(any(row[0] == "execute" for row in self.session.calls))

    def test_monitor_insertion_keeps_display_and_target_bound_to_same_connector(self):
        self.select()
        self.host.set_connectors(["DP-0", "DP-1"])
        QTest.qWait(30)
        view = self.control("compositionView")
        self.assertEqual(self.control("compositionMonitor").property("currentText"), view.property("connector"))
        self.click(self.control("compositionRefresh"))
        self.focus(self.control("compositionPanel28"))
        QTest.keyClick(self.window, Qt.Key_Space); self.wait()
        self.click(self.control("compositionPrepare"))
        self.assertEqual(self.host.review["connector"], "DP-1")

    def test_committed_short_viewport_keeps_details_scrollable(self):
        self.session.phase = "COMMITTED"
        self.host.refresh("DP-1"); self.wait()
        self.window.resize(350, 240); QTest.qWait(40)
        viewport = self.control("compositionScroll").property("contentItem")
        self.assertGreaterEqual(viewport.height(), 40)
        self.focus(self.control("compositionRestore"))
        point = self.control("compositionRestore").mapToItem(viewport, QPointF(0, 0))
        self.assertGreaterEqual(point.y(), 0)
        self.assertLessEqual(point.y() + self.control("compositionRestore").height(), viewport.height())

    def test_recorded_commit_without_live_observation_does_not_offer_mutation(self):
        for state in (dict(phase="COMMITTED", verificationUnavailable=True),
                      dict(phase="COMMITTED", shellRunning=False, inventory=None, recordPresent=True)):
            self.session.read_override = state
            self.host.refresh(""); self.wait()
            self.assertNotIn("ativa", self.control("compositionStatus").property("text"))
            self.assertFalse(self.control("compositionDisable").isEnabled())
            self.assertFalse(self.control("compositionRestore").isEnabled())

    def test_refresh_label_fits_at_narrow_widths(self):
        for width in (320, 350, 420):
            self.window.resize(width, 620); QTest.qWait(30)
            label = self.control("compositionRefresh").property("contentItem")
            self.assertGreaterEqual(label.width(), label.implicitWidth())


if __name__ == "__main__":
    unittest.main()
