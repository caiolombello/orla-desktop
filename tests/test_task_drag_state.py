"""Portable TaskDragState behavior at an explicit QObject/callback boundary."""
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression


class TaskDragStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("TaskDragStateHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.harness = self.engine.rootObjects()[0]
        self.state = self.harness.findChild(QObject, "taskDragState")
        self.assertIsNotNone(self.state)

    def tearDown(self):
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.state, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def fixture(self, source):
        return self.evaluate(source, self.harness)

    def prepare_move(self):
        self.assertTrue(self.evaluate("begin('A')"))
        self.assertTrue(self.evaluate("activate()"))
        self.assertTrue(self.evaluate("update('B',true)"))

    def assert_idle_counts(self, calls=0, writes=0):
        self.assertFalse(self.state.property("pressed"))
        self.assertFalse(self.state.property("active"))
        self.assertEqual(self.harness.property("calls"), calls)
        self.assertEqual(self.harness.property("writes"), writes)
        self.assertEqual(self.warnings, [])

    def test_only_active_release_calls_adapter_and_saves_once(self):
        self.assertTrue(self.evaluate("begin('A')"))
        self.assertFalse(self.evaluate("update('B',true)"))
        self.assertFalse(self.evaluate("finish()"))
        self.assert_idle_counts()
        self.prepare_move()
        self.assertEqual(self.harness.property("calls"), 0)
        self.assertEqual(self.harness.property("writes"), 0)
        self.assertTrue(self.evaluate("finish()"))
        self.assertEqual(json.loads(self.fixture("JSON.stringify(rows.map(row=>row.identity))")), ['B', 'A', 'U'])
        self.assertEqual(json.loads(self.fixture("JSON.stringify(first.effective.launchers)")),
                         ['applications:B.desktop', 'applications:A.desktop'])
        self.assertEqual((self.harness.property("lastFrom"), self.harness.property("lastTo")), (0, 1))
        self.assertFalse(self.evaluate("finish()"))
        self.assert_idle_counts(calls=1, writes=1)

    def test_self_adjacent_outside_and_explicit_cancel_do_not_call_adapter(self):
        for mode in ('self-before', 'self-after', 'adjacent-before', 'outside', 'cancel'):
            with self.subTest(mode=mode):
                self.fixture("reset()")
                self.assertTrue(self.evaluate("begin('A')"))
                self.assertTrue(self.evaluate("activate()"))
                if mode == 'self-before':
                    self.assertTrue(self.evaluate("update('A',false)"))
                elif mode == 'self-after':
                    self.assertTrue(self.evaluate("update('A',true)"))
                elif mode == 'adjacent-before':
                    self.assertTrue(self.evaluate("update('B',false)"))
                else:
                    self.assertTrue(self.evaluate("update('B',true)"))
                    if mode == 'outside':
                        self.assertFalse(self.evaluate("update('',false)"))
                    else:
                        self.evaluate("cancel()")
                self.assertFalse(self.evaluate("finish()"))
                self.assert_idle_counts()

    def test_changed_domain_or_full_order_refuses_held_release(self):
        changes = {
            'revision': 'first.revision++',
            'scope': "first.activeProfileId='personal'",
            'instance': 'currentProfiles=second',
            'saved-launchers': "first.effective={launchers:['applications:B.desktop','applications:A.desktop']}",
            'full-order': "rows=[{identity:'B',rank:1,order:0},{identity:'A',rank:0,order:1},{identity:'U',rank:-1,order:2}]",
            'readonly': 'first.writable=false',
            'closed-view': 'viewEligible=false',
        }
        for mode, change in changes.items():
            with self.subTest(mode=mode):
                self.fixture("reset()")
                self.prepare_move()
                self.fixture(change)
                self.assertFalse(self.evaluate("finish()"))
                self.assert_idle_counts()

    def test_owned_model_move_and_accepted_setter_signals_keep_commit_live(self):
        for order in ('saved-first', 'revision-first'):
            with self.subTest(order=order):
                self.fixture("reset()")
                self.harness.setProperty("signalOrder", order)
                self.prepare_move()
                self.assertTrue(self.evaluate("finish()"))
                self.assertTrue(self.harness.property("guardBeforeMove"))
                self.assertTrue(self.harness.property("guardAfterMove"), 'Owned model movement must not compare the old order in the in-flight guard')
                self.assertTrue(self.harness.property("intentAliveAfterSignals"), 'Own accepted revision/saved signals must not cancel during the callback')
                self.assert_idle_counts(calls=1, writes=1)

    def test_legacy_and_unpinned_source_remain_eligible(self):
        self.fixture("first.activeProfileId='legacy'")
        self.assertTrue(self.evaluate("begin('U')"))
        self.assertTrue(self.evaluate("activate()"))
        self.assertTrue(self.evaluate("update('A',false)"))
        self.assertTrue(self.evaluate("finish()"))
        self.assertEqual((self.harness.property("lastFrom"), self.harness.property("lastTo")), (2, 0))
        self.assertEqual(json.loads(self.fixture("JSON.stringify(rows.map(row=>row.identity))")), ['U', 'A', 'B'])
        self.assert_idle_counts(calls=1, writes=0)


if __name__ == "__main__":
    unittest.main()
