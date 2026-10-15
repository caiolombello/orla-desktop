import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, Qt, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class LocalModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("LocalModuleHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.details = self.window.findChild(QQuickItem, "moduleUnderTest")
        self.bridge = self.window.findChild(QObject, "moduleBridge")
        QTest.qWait(30)

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()

    def control(self, name):
        item = self.details.findChild(QQuickItem, name)
        self.assertIsNotNone(item, name)
        return item

    def test_keyboard_discovery_is_passive_and_disabled_state_ignores_cached_data(self):
        disclosure = self.control("moduleDisclosure")
        state = self.control("moduleStatus")
        self.assertFalse(state.isVisible())
        disclosure.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.app.processEvents()
        self.assertTrue(state.isVisible())
        self.assertEqual(state.property("text"), "Desativado neste perfil")
        self.assertIn("QuotaLantern", self.control("moduleDescription").property("text"))
        self.assertIn("três módulos", self.control("moduleRequirements").property("text"))
        self.assertFalse(self.details.property("shown"))
        self.assertEqual(self.bridge.property("refreshRequests"), 0)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.app.processEvents()
        self.assertFalse(state.isVisible())
        self.assertEqual(self.bridge.property("refreshRequests"), 0)
        self.assertEqual(self.warnings, [])

    def test_enabled_states_distinguish_cache_transport_and_saved_recording(self):
        self.details.setProperty("shown", True)
        self.assertEqual(self.details.property("statusText"), "Leitura disponível")
        for status, expected in (("missing", "Sem cache local"), ("invalid", "Cache local inválido"),
                                 ("stale", "Dados desatualizados"), ("unknown", "Sem leitura confirmada")):
            with self.subTest(status=status):
                self.bridge.setProperty("quota", {"status": status})
                self.assertEqual(self.details.property("statusText"), expected)
        self.bridge.setProperty("loading", True)
        self.assertEqual(self.details.property("statusText"), "Relendo cache local…")
        self.bridge.setProperty("error", "<b>raw transport detail</b>")
        self.assertEqual(self.details.property("statusText"), "Integração indisponível")
        self.details.setProperty("shown", False)
        self.assertEqual(self.details.property("statusText"), "Desativado neste perfil")
        self.bridge.setProperty("error", "")
        self.bridge.setProperty("loading", False)
        self.details.setProperty("shown", True)
        self.details.setProperty("widgetId", "recording")
        self.assertEqual(self.details.property("statusText"), "Estado salvo · gravando")
        self.control("moduleDisclosure").setProperty("checked", True)
        self.bridge.setProperty("recordingSummary", "<b>Estado salvo</b>")
        status = self.control("moduleStatus")
        expression = QQmlExpression(QQmlEngine.contextForObject(status), status, "textFormat === Text.PlainText")
        self.assertEqual(expression.evaluate()[0], True)
        self.assertFalse(expression.hasError())
        self.assertEqual(self.control("moduleStatus").property("text"), "<b>Estado salvo</b>")
        self.details.setProperty("integrations", None)
        self.assertEqual(self.details.property("statusText"), "Integração indisponível")
        self.assertEqual(self.bridge.property("refreshRequests"), 0)
        self.assertEqual(self.warnings, [])

    def test_closed_or_unknown_module_clears_disclosure_and_short_layout_fits(self):
        for width in (350, 420):
            self.window.setWidth(width)
            for widget, project in (("quota", "QuotaLantern"), ("peripherals", "PeriGauge"),
                                    ("recording", "FalaTrace")):
                with self.subTest(width=width, widget=widget):
                    self.details.setProperty("widgetId", widget)
                    disclosure = self.control("moduleDisclosure")
                    self.assertFalse(disclosure.property("checked"))
                    self.assertIn(project, disclosure.property("text"))
                    disclosure.setProperty("checked", True)
                    QTest.qWait(40)  # Let the two nested layouts polish after expanding.
                    self.assertLessEqual(self.details.property("implicitHeight"), 297)
                    for name in ("moduleDescription", "moduleStatus", "moduleRequirements"):
                        label = self.control(name)
                        self.assertGreater(label.width(), 0)
                        self.assertLessEqual(label.x() + label.width(), width)
                        self.assertFalse(label.property("truncated"))
                    host = self.window.findChild(QQuickItem, "moduleHost")
                    host.setVisible(False)
                    self.assertFalse(disclosure.property("checked"))
                    host.setVisible(True)
        self.details.setProperty("widgetId", "unknown")
        self.assertFalse(self.details.property("known"))
        self.assertEqual(self.details.property("statusText"), "")
        self.assertFalse(self.details.property("visible"))
        self.assertEqual(self.warnings, [])
