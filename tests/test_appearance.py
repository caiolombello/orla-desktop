import os
from pathlib import Path
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, Qt, QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class AppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("AppearanceHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.config = self.window.findChild(QObject, "appearanceConfiguration")
        self.state = self.window.findChild(QObject, "appearanceState")
        QTest.qWait(50)
        for item in self.window.findChildren(QQuickItem):
            item.ensurePolished()

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.state, source)
        result, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return result

    def click(self, name):
        button = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(button)
        button.ensurePolished()
        point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        self.app.processEvents()

    def visual_item(self, name, item=None):
        item = item or self.window.contentItem()
        if item.objectName() == name:
            return item
        for child in item.childItems():
            found = self.visual_item(name, child)
            if found is not None:
                return found
        return None

    def focus_control(self, window, control):
        control.forceActiveFocus(Qt.TabFocusReason)
        # forceActiveFocus sets the item focus chain before a newly shown
        # Wayland window has received its pending Qt focus event. QTest sends
        # modifier and key events synchronously, so settle this precondition
        # before the single key gesture. No window activation is requested.
        deadline = time.monotonic() + 1
        while window.activeFocusItem() != control and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertEqual(window.activeFocusItem(), control, "Owned fixture must have settled item focus before synthetic keys")

    def test_draft_preview_never_persists_until_apply(self):
        self.assertEqual(self.config.property("appearanceJSON"), "")
        self.evaluate("setToken('accent', '#123456')")
        self.assertEqual(self.evaluate("effective.tokens.accent"), "#123456")
        self.assertEqual(self.config.property("appearanceJSON"), "")
        self.click("appearanceApply")
        self.assertIn('"accent":"#123456"', self.config.property("appearanceJSON"))
        self.assertEqual(self.config.property("theme"), "glass")
        self.assertEqual(self.warnings, [])

    def test_apply_survives_recreating_the_component_with_same_configuration(self):
        self.evaluate("setToken('radius', 8); setToken('reducedMotion', true)")
        self.click("appearanceApply")
        self.evaluate("recreateState()", self.window)
        reloaded = self.window.findChild(QObject, "reloadedAppearance")
        self.assertIsNotNone(reloaded)
        self.assertEqual(self.evaluate("effective.tokens.radius", reloaded), 8)
        self.assertTrue(self.evaluate("effective.tokens.reducedMotion", reloaded))

    def test_invalid_color_and_numbers_block_apply_and_keep_last_good_preview(self):
        self.evaluate("setToken('accent', '#123456')")
        field = self.visual_item("appearanceColoraccent")
        self.focus_control(self.window, field)
        QTest.keyClick(self.window, Qt.Key_A, Qt.ControlModifier)
        for key in (Qt.Key_B, Qt.Key_A, Qt.Key_D):
            QTest.keyClick(self.window, key)
        self.assertTrue(self.state.property("error"))
        self.assertFalse(self.state.property("canApply"))
        self.assertEqual(self.evaluate("effective.tokens.accent"), "#123456")
        self.click("appearanceApply")
        self.assertEqual(self.config.property("appearanceJSON"), "")
        self.evaluate("setToken('accent', '#123456'); setToken('opacity', 0.39)")
        self.assertFalse(self.state.property("canApply"))
        self.assertAlmostEqual(self.evaluate("effective.tokens.opacity"), 219 / 255)
        for source in ("setToken('opacity', Infinity)", "setToken('opacity', NaN)", "setToken('opacity', true)",
                       "setToken('radius', 33)", "setToken('spacing', -1)", "setToken('iconSize', 65)"):
            self.evaluate(source)
            self.assertFalse(self.state.property("canApply"), source)

    def test_cancel_and_undo_restore_saved_appearance_and_defaults_wait_for_apply(self):
        self.evaluate("setToken('accent', '#123456')")
        self.click("appearanceApply")
        applied = self.config.property("appearanceJSON")
        self.evaluate("setToken('accent', '#654321')")
        self.click("appearanceCancel")
        self.assertEqual(self.evaluate("effective.tokens.accent"), "#123456")
        self.assertEqual(self.config.property("appearanceJSON"), applied)
        self.evaluate("begin(); restoreDefaults()")
        self.assertEqual(self.evaluate("effective.tokens.accent"), "#69d7c2")
        self.assertEqual(self.config.property("appearanceJSON"), applied)
        self.click("appearanceApply")
        self.assertEqual(self.config.property("appearanceJSON"), "")
        self.click("appearanceUndo")
        self.assertEqual(self.config.property("appearanceJSON"), applied)
        self.assertFalse(self.state.property("canUndo"))

    def test_invalid_saved_snapshot_falls_back_without_rewriting_configuration(self):
        for raw in ('{"formatVersion":"future"}', '<img src="https://invalid.example/">',
                    '{"formatVersion":"0.1-experimental","baseTheme":"paper","tokens":{}}'):
            self.config.setProperty("appearanceJSON", raw)
            self.evaluate("cancel()")
            self.assertEqual(self.evaluate("effective.tokens.accent"), "#69d7c2")
            self.assertEqual(self.config.property("appearanceJSON"), raw)
        self.assertEqual(self.warnings, [])

    def test_unknown_fields_and_unsupported_saved_versions_cannot_override_legacy(self):
        self.evaluate("setToken('accent', '#123456'); apply()")
        saved = self.config.property("appearanceJSON")
        import json
        for change in ({"unexpected": True}, {"formatVersion": "1.0"}, {"baseTheme": "unknown"}):
            value = json.loads(saved)
            value.update(change)
            self.config.setProperty("appearanceJSON", json.dumps(value))
            self.evaluate("cancel()")
            self.assertEqual(self.evaluate("effective.tokens.accent"), "#69d7c2")
        for key, value in (("unexpected", "#123456"), ("surface", "#fff"), ("reducedMotion", "true")):
            parsed = json.loads(saved)
            parsed["tokens"][key] = value
            self.config.setProperty("appearanceJSON", json.dumps(parsed))
            self.assertEqual(self.evaluate("effective.tokens.accent"), "#69d7c2")

    def test_native_buttons_apply_and_undo_from_keyboard(self):
        self.evaluate("setToken('accent', '#123456')")
        apply = self.window.findChild(QQuickItem, "appearanceApply")
        self.focus_control(self.window, apply)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertIn('"accent":"#123456"', self.config.property("appearanceJSON"))
        undo = self.window.findChild(QQuickItem, "appearanceUndo")
        self.focus_control(self.window, undo)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(self.config.property("appearanceJSON"), "")

    def test_keyboard_focus_reveals_controls_below_scroll_viewport(self):
        self.window.setHeight(420)
        self.app.processEvents()
        apply = self.window.findChild(QQuickItem, "appearanceApply")
        self.focus_control(self.window, apply)
        QTest.keyClick(self.window, Qt.Key_Tab, Qt.ShiftModifier)
        focused = self.window.activeFocusItem()
        self.assertEqual(focused.objectName(), "appearanceDefaults")
        ancestor = focused.parentItem()
        while ancestor is not None and ancestor.property("contentY") is None:
            ancestor = ancestor.parentItem()
        self.assertIsNotNone(ancestor)
        point = focused.mapToItem(ancestor, QPointF(0, 0))
        self.assertGreaterEqual(point.y(), 0)
        self.assertLessEqual(point.y() + focused.height(), ancestor.height() + 1)
        self.assertEqual(self.warnings, [])

    def test_real_dock_popup_close_and_escape_discard_preview(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(message.toString() for message in messages))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("QmlHarness.qml").resolve())))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        config = window.findChild(QObject, "configuration")
        popup = window.findChild(QObject, "settingsPopup")
        try:
            popup.setProperty("popupType", 0)  # Synthetic events use Popup.Item; native seat grabs remain unqualified.
            dock.setY(20)
            window.setHeight(800)
            button = window.findChild(QQuickItem, "settingsButton")
            QTest.qWait(50)
            for exit_action in ("close", "escape", "cancel"):
                point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
                QTest.qWait(50)
                expression = QQmlExpression(engine.rootContext(), dock, "appearance.setToken('accent', '#123456'); appearance.setToken('radius', 8); appearance.setToken('spacing', 12); appearance.setToken('opacity', 0.6); appearance.setToken('iconSize', 56); appearance.setToken('reducedMotion', true); accent")
                self.assertEqual(expression.evaluate()[0], "#123456", expression.error().toString())
                self.assertEqual(config.property("appearanceJSON"), "")
                surface = window.findChild(QQuickItem, "dockSurface")
                content = window.findChild(QQuickItem, "dockContent")
                self.assertEqual(surface.property("radius"), 8)
                self.assertAlmostEqual(surface.property("opacity"), 0.6)
                self.assertEqual(content.property("spacing"), 12)
                self.assertEqual(dock.property("requestedIconSize"), 56)
                self.assertEqual(dock.property("motion"), 0)
                if exit_action == "escape":
                    QTest.keyClick(window, Qt.Key_Escape)
                elif exit_action == "close":
                    expression = QQmlExpression(engine.rootContext(), popup, "close()")
                    expression.evaluate()
                else:
                    cancel = window.findChild(QQuickItem, "appearanceCancel")
                    self.focus_control(window, cancel)
                    QTest.keyClick(window, Qt.Key_Space)
                QTest.qWait(100)
                expression = QQmlExpression(engine.rootContext(), dock, "appearance.effective.tokens.accent")
                self.assertEqual(expression.evaluate()[0], "#69d7c2")
                self.assertFalse(popup.property("visible"))
                self.assertEqual(surface.property("radius"), 21)
                self.assertEqual(surface.property("opacity"), 1)
                self.assertEqual(content.property("spacing"), 5)
                self.assertEqual(dock.property("requestedIconSize"), 42)
            self.assertEqual(warnings, [])
        finally:
            window.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)
            self.app.processEvents()

    def test_complete_settings_popup_keeps_actions_visible_with_420_pixel_budget(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(message.toString() for message in messages))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("QmlHarness.qml").resolve())))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        popup = window.findChild(QObject, "settingsPopup")
        try:
            window.setHeight(520)
            popup.setProperty("popupType", 0)
            self.assertTrue(popup.setProperty("heightBudget", 420))
            popup.setProperty("y", 0)
            expression = QQmlExpression(engine.rootContext(), popup, "open()")
            expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
            QTest.qWait(50)
            self.assertLessEqual(popup.property("height"), 420)
            content = popup.property("contentItem")
            for item in window.findChildren(QQuickItem):
                item.ensurePolished()
            for name in ("appearanceApply", "appearanceCancel", "appearanceUndo"):
                button = window.findChild(QQuickItem, name)
                point = button.mapToItem(content, QPointF(0, 0))
                self.assertGreaterEqual(point.y(), 0, name)
                self.assertLessEqual(point.y() + button.height(), content.height() + 1, name)
            apply = window.findChild(QQuickItem, "appearanceApply")
            self.focus_control(window, apply)
            QTest.keyClick(window, Qt.Key_Tab, Qt.ShiftModifier)
            focused = window.activeFocusItem()
            self.assertEqual(focused.objectName(), "appearanceDefaults")
            ancestor = focused.parentItem()
            while ancestor is not None and ancestor.property("contentY") is None:
                ancestor = ancestor.parentItem()
            self.assertIsNotNone(ancestor)
            point = focused.mapToItem(ancestor, QPointF(0, 0))
            self.assertGreaterEqual(point.y(), 0)
            self.assertLessEqual(point.y() + focused.height(), ancestor.height() + 1)
            self.assertEqual(warnings, [])
        finally:
            window.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
