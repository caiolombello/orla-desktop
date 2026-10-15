"""Settings presentation with real Qt controls and synthetic KConfig values."""

import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class BarSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("BarSettingsHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.settings = self.item("barSettingsUnderTest")
        QTest.qWait(30)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def item(self, name):
        item = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(item, name)
        return item

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.settings, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def config(self):
        keys = ("showOrlaMenu", "showControlCenter", "showApplicationName", "menuLabel",
                "showMenuLabel", "compactHeight", "menuIcon")
        return {key: self.settings.property("cfg_" + key) for key in keys}

    def test_menu_customization_and_help_are_collapsed_and_passive(self):
        before = self.config()
        fields = self.item("barMenuCustomizationFields")
        help_text = self.item("barCompositionHelpText")
        self.assertFalse(fields.isVisible())
        self.assertFalse(help_text.isVisible())
        for name, content in (("barMenuCustomizationDisclosure", fields),
                              ("barCompositionHelpDisclosure", help_text)):
            disclosure = self.item(name)
            self.evaluate("forceActiveFocus(Qt.TabFocusReason)", disclosure)
            QTest.keyClick(self.window, Qt.Key_Space)
            QTest.qWait(20)
            self.assertTrue(content.isVisible())
            self.assertEqual(self.config(), before)
            QTest.keyClick(self.window, Qt.Key_Space)
            self.assertFalse(content.isVisible())
            self.assertTrue(disclosure.hasActiveFocus())
            self.assertEqual(self.config(), before)

    def test_hidden_and_ineffective_menu_controls_preserve_their_preferences(self):
        self.evaluate("setMenuOpen(true); cfg_menuLabel = 'Meu menu'; cfg_showMenuLabel = false")
        name = self.item("menuLabelSetting")
        label = self.item("showMenuLabelSetting")
        icon = self.item("menuIconSetting")
        self.assertFalse(name.isEnabled())
        self.assertTrue(label.isEnabled())
        self.evaluate("cfg_menuIcon = 'none'")
        self.assertTrue(name.isEnabled())
        self.assertFalse(label.isEnabled())
        self.assertFalse(self.settings.property("cfg_showMenuLabel"))
        self.evaluate("cfg_showOrlaMenu = false")
        for item in (name, label, icon):
            self.assertFalse(item.isEnabled())
        self.assertEqual(self.settings.property("cfg_menuLabel"), "Meu menu")
        self.assertEqual(self.settings.property("cfg_menuIcon"), "none")
        self.assertFalse(self.settings.property("cfg_showMenuLabel"))
        self.evaluate("cfg_showOrlaMenu = true; cfg_menuIcon = 'orla'")
        self.assertFalse(name.isEnabled())
        self.assertTrue(label.isEnabled())
        self.assertEqual(self.settings.property("cfg_menuLabel"), "Meu menu")

    def assert_in_viewport(self, control):
        viewport = self.evaluate("contentItem")
        top = control.mapToItem(viewport, QPointF(0, 0))
        self.assertGreaterEqual(top.y(), 0)
        self.assertLessEqual(top.y() + control.height(), viewport.height())
        self.assertGreaterEqual(top.x(), 0)
        self.assertLessEqual(top.x() + control.width(), viewport.width())

    def test_collapsing_moves_focus_and_delayed_reveals_respect_newer_focus(self):
        self.window.setWidth(320)
        self.window.setHeight(240)
        self.evaluate("setMenuOpen(true)")
        name = self.item("menuLabelSetting")
        self.evaluate("forceActiveFocus(Qt.TabFocusReason)", name)
        QTest.qWait(30)
        self.assert_in_viewport(name)
        self.evaluate("setMenuOpen(false)")
        QTest.qWait(30)
        disclosure = self.item("barMenuCustomizationDisclosure")
        self.assertTrue(disclosure.hasActiveFocus())
        self.assertFalse(name.isVisible())
        self.assert_in_viewport(disclosure)
        self.evaluate("setMenuOpen(true)")
        self.evaluate("forceActiveFocus(Qt.TabFocusReason)", name)
        first = self.item("showOrlaMenuSetting")
        self.evaluate("forceActiveFocus(Qt.TabFocusReason)", first)
        QTest.qWait(30)
        self.assertTrue(first.hasActiveFocus())
        self.assert_in_viewport(first)

    def test_opening_help_reveals_its_text_while_keeping_the_disclosure_visible(self):
        self.window.resize(520, 240)
        disclosure = self.item("barCompositionHelpDisclosure")
        self.evaluate("forceActiveFocus(Qt.TabFocusReason)", disclosure)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(30)
        self.assertTrue(disclosure.hasActiveFocus())
        self.assert_in_viewport(disclosure)
        self.assert_in_viewport(self.item("barCompositionHelpText"))

    def test_tab_and_backtab_skip_the_collapsed_menu_fields(self):
        self.window.resize(320, 240)
        disclosure = self.item("barMenuCustomizationDisclosure")
        help_control = self.item("barCompositionHelpDisclosure")
        self.evaluate("forceActiveFocus(Qt.TabFocusReason)", disclosure)
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertTrue(help_control.hasActiveFocus())
        self.assert_in_viewport(help_control)
        QTest.keyClick(self.window, Qt.Key_Backtab)
        self.assertTrue(disclosure.hasActiveFocus())
        self.assert_in_viewport(disclosure)
        self.assertFalse(self.item("menuLabelSetting").isVisible())

    def test_tab_navigation_reaches_and_reveals_controls_at_narrow_and_wide_sizes(self):
        before = self.config()
        expected = {"showOrlaMenuSetting", "showApplicationNameSetting", "showControlCenterSetting",
                    "compactHeightSetting", "applyMacInspiredPreset", "barMenuCustomizationDisclosure",
                    "menuIconSetting", "showMenuLabelSetting", "menuLabelSetting", "barCompositionHelpDisclosure"}
        for width, height in ((320, 240), (520, 560), (1280, 720)):
            with self.subTest(width=width, height=height):
                self.window.resize(width, height)
                self.evaluate("setMenuOpen(true); setHelpOpen(true)")
                self.evaluate("forceActiveFocus(Qt.TabFocusReason)", self.item("showOrlaMenuSetting"))
                seen = set()
                for _ in range(24):
                    QTest.qWait(10)
                    focused = self.window.activeFocusItem()
                    self.assertIsNotNone(focused)
                    if focused.objectName() in expected:
                        self.assert_in_viewport(focused)
                        seen.add(focused.objectName())
                    QTest.keyClick(self.window, Qt.Key_Tab)
                self.assertEqual(seen, expected)
                self.assertEqual(self.config(), before)


if __name__ == "__main__":
    unittest.main()
