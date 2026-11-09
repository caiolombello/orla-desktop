"""Portable routing of the dock's app-wide actions through a fake TasksModel and KWin."""
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression

EDITOR = "org.example.Editor"


class DockAppActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("DockAppActionsHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.harness = self.engine.rootObjects()[0]
        self.actions = self.harness.findChild(QObject, "dockAppActions")
        self.assertIsNotNone(self.actions)

    def tearDown(self):
        self.assertEqual(self.warnings, [])
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.actions, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def json(self, source, target=None):
        return json.loads(self.evaluate(f"JSON.stringify({source})", target))

    def calls(self):
        return self.json("calls", self.harness)

    def test_summary_counts_every_window_of_the_app_only(self):
        summary = self.json(f"summary('{EDITOR}', ['w1'])")
        # w1, w2 and w4 are Editor windows; the launcher row and Viewer are not.
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["hideable"], 1)
        self.assertEqual(summary["closable"], 2)
        self.assertEqual(summary["handles"], 3)
        self.assertEqual([d["number"] for d in summary["desktops"]], [1, 2, 3])
        self.assertEqual([d["name"] for d in summary["desktops"]], ["Um", "Dois", "Três"])
        self.assertFalse(any(d["current"] for d in summary["desktops"]))

    def test_hide_minimizes_only_visible_minimizable_windows(self):
        self.assertEqual(self.evaluate(f"hide('{EDITOR}', ['w1'])"), 1)
        self.assertEqual(self.calls(), ["minimize:w1"])

    def test_quit_requests_close_for_each_closable_window_and_never_other_apps(self):
        self.assertEqual(self.evaluate(f"quit('{EDITOR}', ['w1'])"), 2)
        self.assertEqual(self.calls(), ["close:w1", "close:w2"])

    def test_show_all_windows_passes_the_app_handles_to_window_view(self):
        self.assertTrue(self.evaluate(f"showAllWindows('{EDITOR}', ['w1'])"))
        self.assertEqual(self.calls(), ["windowview:w1,w2,w4"])

    def test_show_all_windows_is_refused_without_the_effect_or_on_failure(self):
        self.evaluate("kwin.windowViewAvailable = false", self.harness)
        self.assertFalse(self.evaluate("windowViewAvailable"))
        self.assertFalse(self.evaluate(f"showAllWindows('{EDITOR}', ['w1'])"))
        self.evaluate("kwin.windowViewAvailable = true; kwin.failing = true", self.harness)
        self.assertFalse(self.evaluate(f"showAllWindows('{EDITOR}', ['w1'])"))
        self.assertEqual(self.calls(), [])

    def test_move_to_desktop_skips_windows_already_there(self):
        self.assertEqual(self.evaluate(f"moveToDesktop('{EDITOR}', ['w1'], 'd2')"), 2)
        self.assertEqual(self.calls(), ['desktops:w1>["d2"]', 'desktops:w4>["d2"]'])

    def test_move_to_unknown_desktop_or_without_model_support_does_nothing(self):
        self.assertEqual(self.evaluate(f"moveToDesktop('{EDITOR}', ['w1'], 'nowhere')"), 0)
        # A model without requestVirtualDesktops, like an older TaskManager.
        self.evaluate("dropMoveSupport()", self.harness)
        self.assertFalse(self.evaluate("canMove"))
        self.assertEqual(self.json(f"summary('{EDITOR}', ['w1'])")["desktops"], [])
        self.assertEqual(self.calls(), [])

    def test_single_desktop_offers_no_move_choices(self):
        self.evaluate("kwin.desktopIds = ['d1']; kwin.desktopNames = ['Um']", self.harness)
        self.assertEqual(self.json(f"summary('{EDITOR}', ['w1'])")["desktops"], [])

    def test_unmovable_windows_are_left_out_of_moves(self):
        self.evaluate("tasks.rows = [row('org.example.Editor', 'w1', {desktopsChangeable: false}),"
                      " row('org.example.Editor', 'w2')]", self.harness)
        self.assertEqual(self.evaluate(f"moveToDesktop('{EDITOR}', ['w1'], 'd3')"), 1)
        self.assertEqual(self.calls(), ['desktops:w2>["d3"]'])

    def test_current_desktop_is_marked_when_every_window_is_only_there(self):
        self.evaluate("tasks.rows = [row('org.example.Editor', 'w1'), row('org.example.Editor', 'w2')]", self.harness)
        desktops = self.json(f"summary('{EDITOR}', ['w1'])")["desktops"]
        self.assertEqual([d["current"] for d in desktops], [True, False, False])

    def test_without_app_id_only_the_menu_window_counts(self):
        summary = self.json("summary('', ['w3'])")
        self.assertEqual(summary["count"], 1)
        self.assertEqual(self.evaluate("quit('', ['w3'])"), 1)
        self.assertEqual(self.calls(), ["close:w3"])

    def test_no_windows_means_no_actions(self):
        summary = self.json("summary('org.example.Missing', [])")
        self.assertEqual((summary["count"], summary["hideable"], summary["closable"], summary["handles"]), (0, 0, 0, 0))
        self.assertEqual(summary["desktops"], [])
        self.assertEqual(self.evaluate("hide('org.example.Missing', [])"), 0)
        self.assertEqual(self.evaluate("quit('org.example.Missing', [])"), 0)
        self.assertFalse(self.evaluate("showAllWindows('org.example.Missing', [])"))
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
