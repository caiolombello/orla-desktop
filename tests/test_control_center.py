import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QPointF, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class ControlCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ControlCenterHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.center = self.window.findChild(QQuickItem, "controlCenterUnderTest")
        self.actions = self.window.findChild(QObject, "controlCenterActions")
        self.backend = self.window.findChild(QObject, "controlCenterBackend")
        self.battery = self.window.findChild(QObject, "controlCenterBattery")
        self.player = self.window.findChild(QObject, "controlCenterPlayer")
        QTest.qWait(30)

    def tearDown(self):
        if self.engine.rootObjects():
            self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.center, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def item(self, name):
        item = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(item, name)
        return item

    def calls(self):
        calls = self.backend.property("calls")
        return calls.toVariant() if hasattr(calls, "toVariant") else calls

    def activate(self, name):
        item = self.item(name)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())

    def test_loading_is_read_only_and_explicit_actions_use_closed_destinations(self):
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.evaluate("open('unknown')", self.actions))
        self.assertEqual(self.calls(), [])

        for name, target in (("controlCenterSoundAction", "kcm_pulseaudio"),
                             ("controlCenterPowerAction", "kcm_powerdevilprofilesconfig"),
                             ("controlCenterAllAction", "")):
            self.activate(name)
            self.assertEqual(self.calls()[-1], target)
        self.assertEqual(self.warnings, [])

    def test_action_failure_stays_in_its_card_and_does_not_claim_success(self):
        self.backend.setProperty("failingTarget", "kcm_pulseaudio")
        self.activate("controlCenterSoundAction")
        sound_error = self.item("controlCenterSoundError")
        self.assertTrue(sound_error.property("visible"))
        self.assertIn("encaminhar", sound_error.property("text"))
        self.assertNotIn("janela", sound_error.property("text").lower())
        self.assertFalse(self.item("controlCenterPowerError").property("visible"))
        self.assertEqual(self.calls(), [])

        self.activate("controlCenterPowerAction")
        self.assertEqual(self.calls(), ["kcm_powerdevilprofilesconfig"])
        self.assertTrue(sound_error.property("visible"))
        self.assertFalse(self.item("controlCenterPowerError").property("visible"))
        self.assertEqual(self.warnings, [])

    def test_external_text_is_bounded_plain_and_battery_zero_is_preserved(self):
        self.player.setProperty("track", "<b>" + "X" * 1000)
        self.player.setProperty("artist", "<i>" + "Y" * 1000)
        QTest.qWait(20)
        for name, prefix in (("controlCenterMediaTitle", "<b>"),
                             ("controlCenterMediaDetail", "<i>")):
            label = self.item(name)
            self.assertTrue(label.property("text").startswith(prefix))
            self.assertLessEqual(len(label.property("text")), 256)
            self.assertEqual(self.evaluate("textFormat", label), 0)
        self.assertEqual(self.item("controlCenterPowerTitle").property("text"), "0%")

        self.evaluate("player = null")
        self.battery.setProperty("status", "unavailable")
        self.battery.setProperty("summary", "Bateria indisponível")
        self.battery.setProperty("subtitle", "Serviço de energia indisponível")
        QTest.qWait(20)
        self.assertEqual(self.item("controlCenterMediaTitle").property("text"), "Nenhum player aberto")
        self.assertEqual(self.item("controlCenterPowerTitle").property("text"), "Bateria indisponível")
        self.assertTrue(self.item("controlCenterSoundAction").property("enabled"))
        self.assertTrue(self.item("controlCenterPowerAction").property("enabled"))
        self.assertEqual(self.warnings, [])

    def test_keyboard_focus_reveals_each_action_in_a_narrow_view(self):
        self.window.setWidth(250)
        self.window.setHeight(240)
        QTest.qWait(30)
        scroll = self.item("controlCenterScroll")
        viewport = scroll.property("contentItem")
        for name in ("controlCenterSoundAction", "controlCenterPowerAction", "controlCenterAllAction"):
            control = self.item(name)
            control.forceActiveFocus()
            QTest.qWait(20)
            self.assertEqual(self.window.activeFocusItem(), control)
            top = control.mapToItem(viewport, QPointF(0, 0)).y()
            self.assertGreaterEqual(top, -0.5, name)
            self.assertLessEqual(top + control.height(), viewport.height() + 0.5, name)
            self.assertGreaterEqual(control.height(), 40)
            self.assertLessEqual(control.width(), self.center.width())
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
