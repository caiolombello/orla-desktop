import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "wayland" if os.environ.get("WAYLAND_DISPLAY") else "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")
os.environ.setdefault("QT_QPA_PLATFORMTHEME", "")

from PySide6.QtCore import QObject, QUrl, Qt, QPoint, QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest, QSignalSpy


class DockInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("QmlHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.config = self.window.findChild(QObject, "configuration")
        self.dock = self.window.findChild(QQuickItem, "dock")
        QTest.qWait(100)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
        QTest.qWait(10)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()

    def evaluate(self, source):
        expression = QQmlExpression(self.engine.rootContext(), self.dock, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def tile_property(self, name, key):
        strip = self.window.findChild(QQuickItem, "widgetStrip")
        expression = QQmlExpression(self.engine.rootContext(), strip,
            f"children.filter(item => item.objectName === '{name}')[0].{key}")
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def test_dock_loads_with_two_launchers_and_no_qml_errors(self):
        if self.app.platformName() == "offscreen":
            self.skipTest("TaskManager needs a Wayland or X11 connection")
        self.assertEqual(self.evaluate("tasksModel.count"), 2)
        self.assertEqual(self.warnings, [])

    def test_pinning_and_reordering_persist_in_configuration(self):
        if self.app.platformName() == "offscreen":
            self.skipTest("TaskManager needs a Wayland or X11 connection")
        self.assertTrue(self.evaluate("addLauncher('systemsettings.desktop')"))
        launchers = self.config.property("launchers")
        self.assertIn("applications:systemsettings.desktop", launchers.toVariant() if hasattr(launchers, "toVariant") else launchers)
        self.assertTrue(self.evaluate("moveTask(0, 1)"))
        launchers = self.config.property("launchers")
        self.assertEqual((launchers.toVariant() if hasattr(launchers, "toVariant") else launchers)[:2], ["applications:org.kde.konsole.desktop", "applications:org.kde.dolphin.desktop"])
        self.assertFalse(self.evaluate("addLauncher('https://example.com/app.desktop')"))

    def test_timer_pause_resume_completion_and_reset(self):
        self.evaluate("pomodoro.toggle()")
        self.assertTrue(self.evaluate("pomodoro.running"))
        self.assertGreater(self.config.property("timerDeadline"), 0)
        self.evaluate("pomodoro.toggle()")
        self.assertFalse(self.evaluate("pomodoro.running"))
        self.assertLessEqual(self.config.property("timerRemaining"), 1500)
        self.evaluate("pomodoro.toggle(); pomodoro.poll(configuration.timerDeadline + 1)")
        self.assertFalse(self.evaluate("pomodoro.running"))
        self.assertEqual(self.config.property("completedFocus"), 1)
        self.assertTrue(self.config.property("timerBreak"))
        self.assertEqual(self.config.property("timerRemaining"), 300)
        self.evaluate("pomodoro.toggle(); pomodoro.poll(configuration.timerDeadline + 1)")
        self.assertEqual(self.config.property("completedFocus"), 1)
        self.assertFalse(self.config.property("timerBreak"))
        self.assertEqual(self.config.property("timerRemaining"), 1500)
        self.evaluate("pomodoro.reset()")
        self.assertFalse(self.evaluate("pomodoro.running"))

    def test_theme_and_animation_preferences_change_rendered_properties(self):
        self.config.setProperty("theme", "paper")
        self.assertTrue(self.dock.property("light"))
        self.assertEqual(self.dock.property("foreground").name(), "#252b35")
        self.assertEqual(self.dock.property("motion"), 0)
        self.config.setProperty("showMusic", False)
        self.app.processEvents()
        self.assertLess(self.dock.property("implicitWidth"), self.window.width())

    def test_frosted_slab_follows_the_measured_panel_frame(self):
        surface = self.window.findChild(QQuickItem, "dockSurface")
        viewport = self.window.findChild(QQuickItem, "appsViewport")
        content = self.window.findChild(QQuickItem, "dockContent")
        plain = (surface.x(), surface.width(), self.evaluate("implicitWidth"))
        # Without the theme, the slab keeps its legacy geometry and opaque tint.
        self.assertEqual(plain[0], 6)
        self.assertEqual(plain[2], content.property("implicitWidth") + 24)
        # The panel adds uneven margins around the dock (measured live: ~9.5 and 14).
        self.evaluate("systemGlassMargins = {left: 9.5, top: 4, right: 14, bottom: 4}; systemGlass = true")
        QTest.qWait(30)
        band_x, band_y = 10, 12
        self.assertAlmostEqual(surface.x(), -9.5 + band_x)
        self.assertAlmostEqual(surface.y(), -4 + band_y)
        self.assertAlmostEqual(surface.width(), self.dock.width() + 9.5 + 14 - 2 * band_x)
        self.assertAlmostEqual(surface.height(), self.dock.height() + 8 - 2 * band_y)
        # The dock asks for exactly the slab: content plus 4 px glass inset each side.
        self.assertAlmostEqual(self.evaluate("implicitWidth"),
                               content.property("implicitWidth") + 2 * (4 + band_x) - 9.5 - 14)
        self.assertAlmostEqual(viewport.x(), surface.x() + 4)
        # Translucent tint so KWin's blur shows; no drawn shadow under it.
        self.assertTrue(self.evaluate("frosted"))
        self.assertAlmostEqual(surface.property("color").alphaF(), 0.5, delta=0.01)
        # An opaque theme stays opaque even with the blur available.
        self.config.setProperty("theme", "midnight")
        QTest.qWait(30)
        self.assertFalse(self.evaluate("frosted"))
        self.assertEqual(surface.property("color").alphaF(), 1)
        self.config.setProperty("theme", "glass")
        self.evaluate("systemGlass = false; systemGlassMargins = null")
        QTest.qWait(30)
        self.assertEqual((surface.x(), surface.width(), self.evaluate("implicitWidth")), plain)
        self.assertEqual(self.warnings, [])

    def test_settings_popup_opens_from_button(self):
        button = self.window.findChild(QQuickItem, "settingsButton")
        popup = self.window.findChild(QObject, "settingsPopup")
        # Synthetic clicks qualify the in-window handler. Native Wayland popup
        # seat/focus behavior remains an open real-panel gate for both styles.
        self.assertTrue(popup.setProperty("popupType", 0))
        opened = QSignalSpy(popup.opened)
        point = button.mapToScene(QPoint(int(button.width() / 2), int(button.height() / 2)))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        if not opened.count():
            self.assertTrue(opened.wait(1000))
        self.assertEqual(opened.count(), 1)
        self.assertEqual(self.warnings, [])

    def test_keyboard_focus_ring_stays_visible_at_both_viewport_edges(self):
        # Force horizontal scrolling so the last slot reaches the clipped edge.
        self.dock.setWidth(180)
        viewport = self.window.findChild(QQuickItem, "appsViewport")
        for name in ("settingsButton", "musicTile"):
            with self.subTest(control=name):
                control = self.window.findChild(QQuickItem, name)
                if control is None:
                    strip = self.window.findChild(QQuickItem, "widgetStrip")
                    control = next(item for item in strip.childItems() if item.objectName() == name)
                control.forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(40)
                ring = control.findChild(QQuickItem, "tileFocusRing")
                self.assertTrue(ring.property("visible"))
                border = QQmlExpression(self.engine.rootContext(), ring, "border.width")
                self.assertEqual(border.evaluate()[0], 2)
                for corner in (QPointF(0, 0), QPointF(ring.width(), ring.height())):
                    within_slot = ring.mapToItem(control, corner)
                    within_viewport = ring.mapToItem(viewport, corner)
                    self.assertGreaterEqual(within_slot.x(), 0)
                    self.assertLessEqual(within_slot.x(), control.width())
                    self.assertGreaterEqual(within_slot.y(), 0)
                    self.assertLessEqual(within_slot.y(), control.height())
                    self.assertGreaterEqual(within_viewport.x(), 0)
                    self.assertLessEqual(within_viewport.x(), viewport.width())
                    self.assertGreaterEqual(within_viewport.y(), 0)
                    self.assertLessEqual(within_viewport.y(), viewport.height())

    def test_shared_buttons_show_pressed_feedback_without_motion(self):
        component = QQmlComponent(self.engine)
        component.setData(b'''import QtQuick
import "../package/contents/ui" as DockUI
Item {
    DockUI.OrlaButton { objectName: "action"; text: "Aplicar" }
    DockUI.OrlaIconButton { objectName: "toggle"; text: "Silenciar" }
}''', QUrl.fromLocalFile(str(Path(__file__).with_name("ButtonFeedbackFixture.qml"))))
        fixture = component.create()
        self.assertIsNotNone(fixture, [error.toString() for error in component.errors()])
        try:
            for name in ("action", "toggle"):
                with self.subTest(control=name):
                    control = fixture.findChild(QQuickItem, name)
                    control.setProperty("down", True)
                    expression = QQmlExpression(self.engine.rootContext(), control,
                        "background.children[0].opacity")
                    self.assertAlmostEqual(expression.evaluate()[0], 0.14)
                    self.assertFalse(expression.hasError(), expression.error().toString())
                    control.setProperty("down", False)
                    self.assertAlmostEqual(expression.evaluate()[0], 0)
        finally:
            fixture.deleteLater()

    def test_popups_follow_each_clicked_or_keyboard_activated_control(self):
        self.window.setHeight(720)
        self.config.setProperty("showControlCenter", True)
        # The compact icon dock is narrower than a popup; give it room to follow controls.
        self.window.setWidth(1400)
        self.dock.setWidth(1200)
        self.app.processEvents()
        cases = (("settingsButton", "settingsPopup"),
                 ("controlCenterButton", "controlCenterPopup"),
                 ("musicTile", "musicPopup"))
        observed = []
        for control_name, popup_name in cases:
            control = self.window.findChild(QQuickItem, control_name)
            if control is None:
                strip = self.window.findChild(QQuickItem, "widgetStrip")
                control = next((item for item in strip.childItems() if item.objectName() == control_name), None)
            popup = self.window.findChild(QObject, popup_name)
            self.assertIsNotNone(control)
            self.assertTrue(popup.setProperty("popupType", 0))
            center = control.mapToItem(self.dock, QPoint(int(control.width() / 2), 0)).x()
            expected = max(0, min(max(0, self.dock.width() - popup.property("width")),
                                  center - popup.property("width") / 2))
            for keyboard in (False, True):
                opened = QSignalSpy(popup.opened)
                control.forceActiveFocus(Qt.TabFocusReason)
                if keyboard:
                    QTest.keyClick(self.window, Qt.Key_Space)
                else:
                    point = control.mapToScene(QPoint(int(control.width() / 2), int(control.height() / 2)))
                    QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
                # CC opens on a queued transaction and native styles animate enter.
                if not opened.count():
                    self.assertTrue(opened.wait(1000), (control_name, keyboard, "open"))
                self.assertTrue(popup.property("visible"))
                self.assertAlmostEqual(popup.property("x"), expected, delta=1)
                observed.append(popup.property("x"))
                closed = QSignalSpy(popup.closed)
                QTest.keyClick(self.window, Qt.Key_Escape)
                if not closed.count():
                    self.assertTrue(closed.wait(1000), (control_name, keyboard, "close"))
                self.assertFalse(popup.property("visible"))
                self.assertEqual(self.window.activeFocusItem(), control)
        self.assertGreater(max(observed) - min(observed), 20)
        self.assertEqual(self.warnings, [])

    def test_popup_geometry_keeps_bottom_panel_content_above_and_clamps_narrow_docks(self):
        self.dock.setProperty("popAbove", True)
        popup = self.window.findChild(QObject, "settingsPopup")
        button = self.window.findChild(QQuickItem, "settingsButton")
        self.assertTrue(popup.setProperty("popupType", 0))
        self.dock.setWidth(240)
        button.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        self.assertTrue(popup.property("visible"))
        self.assertEqual(popup.property("x"), 0)
        # 10 px between the visible glass of the dock and of the popup; the popup
        # item also holds its shadow margin and the dock its transparent headroom.
        self.assertAlmostEqual(popup.property("y") + popup.property("height") - popup.property("shadowMargin"),
                               self.dock.property("glassTop") - 10)
        self.assertLessEqual(popup.property("height"), self.window.screen().size().height() - self.dock.height() - 30)
        self.assertEqual(popup.property("margins"), -1)
        QTest.keyClick(self.window, Qt.Key_Escape)

    def test_task_menu_uses_the_captured_control_center_and_panel_parent(self):
        self.window.setHeight(720)
        self.app.processEvents()
        menu = self.window.findChild(QObject, "taskContextMenu")
        menu.setProperty("popupType", 0)
        self.dock.setProperty("popAbove", True)
        observed = []
        for name in ("settingsButton", "musicTile"):
            button = self.window.findChild(QQuickItem, name)
            if button is None:
                strip = self.window.findChild(QQuickItem, "widgetStrip")
                button = next(item for item in strip.childItems() if item.objectName() == name)
            center = button.mapToItem(self.dock, QPoint(int(button.width() / 2), 0)).x()
            self.engine.rootContext().setContextProperty("ownedAnchorControl", button)
            expression = QQmlExpression(self.engine.rootContext(), self.dock,
                "showTaskMenuAt(0, {AppName:'Owned fixture', IsWindow:false}, ownedAnchorControl)")
            expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
            QTest.qWait(40)
            expected = max(0, min(max(0, self.dock.width() - menu.property("width")),
                                  center - menu.property("width") / 2))
            self.assertAlmostEqual(menu.property("x"), expected, delta=1)
            self.assertEqual(menu.property("parent"), self.dock)
            self.assertEqual(menu.property("margins"), -1)
            self.assertAlmostEqual(menu.property("y") + menu.property("height"), -8)
            observed.append(menu.property("x"))
            closed = QSignalSpy(menu.closed)
            menu.close()
            if not closed.count():
                self.assertTrue(closed.wait(1000))
        self.assertNotEqual(observed[0], observed[1])
        self.assertEqual(self.warnings, [])

    def place_dock_inside_available_screen(self):
        self.app.processEvents()
        bounds = self.window.screen().availableGeometry()
        bottom = self.dock.mapToGlobal(QPoint(0, int(self.dock.height()))).y()
        self.window.setHeight(int(self.window.height() + 2 * (bounds.bottom() - 20 - bottom)))
        self.app.processEvents()
        top_left = self.dock.mapToGlobal(QPoint(0, 0)).toPoint()
        bottom_right = self.dock.mapToGlobal(QPoint(int(self.dock.width()), int(self.dock.height()))).toPoint()
        self.assertTrue(bounds.contains(top_left), (bounds, top_left))
        self.assertTrue(bounds.contains(bottom_right), (bounds, bottom_right))

    def test_calendar_title_uses_the_user_locale(self):
        from PySide6.QtCore import QDate, QDateTime, QLocale, QTime
        previous = QLocale()
        self.addCleanup(QLocale.setDefault, previous)
        QLocale.setDefault(QLocale("pt_BR"))
        moment = QDateTime(QDate(2026, 10, 21), QTime(12, 0))
        self.assertTrue(self.dock.setProperty("now", moment))
        title = self.window.findChild(QObject, "calendarPopup").property("title")
        expected = QLocale("pt_BR").toString(moment.date(), "MMMM yyyy")
        self.assertEqual(title, expected[:1].upper() + expected[1:])
        self.assertNotIn("October", title)

    def test_native_label_remaps_to_each_hovered_slot(self):
        # A visible Wayland popup keeps its first anchor; the label must re-map
        # for a new slot instead of only changing its text.
        self.place_dock_inside_available_screen()
        self.config.setProperty("showControlCenter", True)
        self.assertTrue(self.dock.setProperty("nativePopups", True))
        self.app.processEvents()
        label = self.window.findChild(QObject, "dockLabelLoader").property("item")
        self.assertIsNotNone(label)
        first = self.window.findChild(QQuickItem, "settingsButton")
        second = self.window.findChild(QQuickItem, "controlCenterButton")
        visibility = QSignalSpy(label.visibleChanged)

        def shown(tile):
            target = label.property("shownTarget")
            return (label.property("visible") and target is not None
                    and target.objectName() == tile.objectName()
                    and label.property("text") == tile.property("tooltip"))

        self.dock.setProperty("labelTarget", first)
        QTest.qWait(20)
        self.assertTrue(shown(first))
        self.dock.setProperty("labelTarget", second)
        self.assertFalse(label.property("visible"))
        QTest.qWait(20)
        self.assertTrue(shown(second))
        self.assertEqual(visibility.count(), 3)
        self.dock.setProperty("labelTarget", None)
        self.assertFalse(label.property("visible"))
        QTest.qWait(20)
        self.assertFalse(label.property("visible"))
        self.assertEqual(self.warnings, [])

    def test_production_dialog_reuses_clicked_control_and_emits_one_lifecycle_per_open(self):
        self.place_dock_inside_available_screen()
        self.config.setProperty("showControlCenter", True)
        self.assertTrue(self.dock.setProperty("nativePopups", True))
        self.app.processEvents()
        for control_name, popup_name in (("settingsButton", "settingsPopup"),
                                         ("controlCenterButton", "controlCenterPopup")):
            button = self.window.findChild(QQuickItem, control_name)
            popup = self.window.findChild(QObject, popup_name)
            about = QSignalSpy(popup.aboutToShow)
            opened = QSignalSpy(popup.opened)
            closed = QSignalSpy(popup.closed)
            hidden = QSignalSpy(popup.aboutToHide)
            if popup_name == "controlCenterPopup":
                budget = QQmlExpression(self.engine.rootContext(), popup, "widthBudget = 260; heightBudget = 320")
                budget.evaluate()
                self.assertFalse(budget.hasError(), budget.error().toString())
            for cycle in (1, 2):
                # Establish actual keyboard ownership; active includes transient relatives.
                self.window.requestActivate()
                for _ in range(20):
                    if QGuiApplication.focusWindow() == self.window:
                        break
                    QTest.qWait(5)
                self.assertEqual(QGuiApplication.focusWindow(), self.window)
                self.engine.rootContext().setContextProperty("ownedPopupAnchor", button)
                expression = QQmlExpression(self.engine.rootContext(), popup, "openAt(ownedPopupAnchor)")
                expression.evaluate()
                self.assertFalse(expression.hasError(), expression.error().toString())
                QTest.qWait(40)
                dialog = popup.property("nativeDialog")
                self.assertIsNotNone(dialog)
                self.assertTrue(dialog.property("visible"))
                glass_top = self.dock.mapToGlobal(QPoint(0, int(self.dock.property("glassTop")))).y()
                self.assertLessEqual(dialog.y() + dialog.height() - popup.property("shadowMargin"), glass_top - 10 + 1)
                proxy = dialog.property("visualParent")
                self.assertNotEqual(proxy, button)
                self.assertAlmostEqual(proxy.mapToGlobal(QPoint(int(proxy.width() / 2), 0)).x(),
                                       button.mapToGlobal(QPoint(int(button.width() / 2), 0)).x(), delta=1)
                identity = QQmlExpression(self.engine.rootContext(), popup, "nativeDialog.mainItem === popupSurface")
                self.assertTrue(identity.evaluate()[0])
                self.assertFalse(identity.hasError(), identity.error().toString())
                self.assertEqual(about.count(), cycle)
                self.assertEqual(opened.count(), cycle)
                screen = self.window.screen().availableGeometry()
                global_center = button.mapToGlobal(QPoint(int(button.width() / 2), 0)).x()
                expected_x = max(screen.left(), min(screen.right() - dialog.width() + 1,
                                                    global_center - dialog.width() / 2))
                self.assertAlmostEqual(dialog.x(), expected_x, delta=1)
                if popup_name == "controlCenterPopup":
                    self.assertEqual(dialog.width(), 260)
                    self.assertLessEqual(dialog.height(), 320)
                    final_action = self.window.findChild(QQuickItem, "controlCenterAllAction")
                    # Enough presses for every Control Center control (CC1 and CC2 cards included).
                    for _ in range(20):
                        QTest.keyClick(dialog, Qt.Key_Tab)
                        QTest.qWait(10)
                        if dialog.activeFocusItem() == final_action:
                            break
                    self.assertEqual(dialog.activeFocusItem(), final_action)
                    viewport = self.window.findChild(QQuickItem, "controlCenterScroll").property("contentItem")
                    final_top = final_action.mapToItem(viewport, QPoint(0, 0)).y()
                    self.assertGreaterEqual(final_top, -0.5)
                    self.assertLessEqual(final_top + final_action.height(), viewport.height() + 0.5)
                QTest.keyClick(dialog, Qt.Key_Escape)
                QTest.qWait(40)
                self.assertFalse(popup.property("visible"))
                self.assertFalse(dialog.property("visible"))
                self.assertEqual(closed.count(), cycle)
                self.assertEqual(hidden.count(), cycle)
                identity = QQmlExpression(self.engine.rootContext(), popup, "nativeDialog.mainItem === popupSurface")
                self.assertTrue(identity.evaluate()[0])
                self.assertFalse(identity.hasError(), identity.error().toString())
        self.assertEqual(self.warnings, [])

    def test_control_center_context_busy_includes_its_queued_session(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        expression = QQmlExpression(self.engine.rootContext(), popup, "openFromDock(owner)")
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.assertFalse(popup.property("visible"))
        self.assertTrue(popup.property("contextSwitchBusy"))
        QTest.qWait(80)
        self.assertTrue(popup.property("visible"))
        self.assertTrue(popup.property("contextSwitchBusy"))
        busy_changed = QSignalSpy(popup.contextSwitchBusyChanged)
        QQmlExpression(self.engine.rootContext(), popup, "closeSession()").evaluate()
        self.assertTrue(popup.property("contextSwitchBusy"))
        self.assertTrue(busy_changed.wait(1000))
        self.assertFalse(popup.property("contextSwitchBusy"))
        self.assertEqual(self.warnings, [])

    def test_popup_busy_includes_closed_notification_and_deferred_restore(self):
        self.place_dock_inside_available_screen()
        self.dock.setProperty("nativePopups", True)
        self.app.processEvents()
        anchor = self.window.findChild(QQuickItem, "settingsButton")
        popup = self.window.findChild(QObject, "settingsPopup")
        self.engine.rootContext().setContextProperty("ownedPopupAnchor", anchor)
        expression = QQmlExpression(self.engine.rootContext(), popup, "openAt(ownedPopupAnchor)")
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        QTest.qWait(40)
        observations = []
        def closed():
            observations.append((popup.property("visible"), popup.property("interactionBusy")))
        popup.closed.connect(closed)
        try:
            popup.close()
            self.assertEqual(observations, [(False, True)])
            self.assertTrue(popup.property("interactionBusy"))
            QTest.qWait(25)
            dialog = popup.property("nativeDialog")
            self.assertFalse(dialog.isVisible())
            self.assertIsNotNone(dialog.activeFocusItem())
            self.assertTrue(popup.property("interactionBusy"))
            # Offscreen can keep a hidden window as focusWindow until another owns it.
            self.window.requestActivate()
            QTest.qWait(80)
            self.assertFalse(popup.property("interactionBusy"))
            self.assertEqual(self.warnings, [])
        finally:
            popup.closed.disconnect(closed)

    def test_popup_busy_old_restore_cannot_release_a_new_close_ticket(self):
        self.place_dock_inside_available_screen()
        self.dock.setProperty("nativePopups", True)
        self.app.processEvents()
        popup = self.window.findChild(QObject, "settingsPopup")
        anchor = self.window.findChild(QQuickItem, "settingsButton")
        self.engine.rootContext().setContextProperty("ownedPopupAnchor", anchor)
        self.engine.rootContext().setContextProperty("ownedHostWindow", self.window)
        self.engine.rootContext().setContextProperty("ownedPopup", popup)
        source = """(function() {
            let count = 0;
            ownedPopup.closed.connect(function() {
                count++;
                if (count === 1) Qt.callLater(function() {
                    ownedPopup.openAt(ownedPopupAnchor);
                    ownedPopup.close();
                });
                else {
                    ownedHostWindow.requestActivate();
                    Qt.callLater(function() {
                        ownedPopup.anchorControl.intermediateBusy = ownedPopup.interactionBusy;
                    });
                }
            });
            ownedPopup.openAt(ownedPopupAnchor);
        })()"""
        # The observer uses an owned fixture item to retain its between-callback witness.
        witness = QQmlComponent(self.engine)
        witness.setData(b'import QtQuick; QtObject { property bool intermediateBusy: false }', QUrl())
        holder = witness.create()
        self.engine.rootContext().setContextProperty("busyWitness", holder)
        source = source.replace('ownedPopup.anchorControl.intermediateBusy', 'busyWitness.intermediateBusy')
        expression = QQmlExpression(self.engine.rootContext(), popup, source)
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        QTest.qWait(40)
        popup.close()
        QTest.qWait(100)
        self.assertTrue(holder.property("intermediateBusy"))
        self.window.requestActivate()
        QTest.qWait(40)
        self.assertFalse(popup.property("interactionBusy"))
        self.assertEqual(self.warnings, [])
        holder.deleteLater()

    def test_popup_busy_rehost_and_reopen_early_returns_eventually_release(self):
        self.place_dock_inside_available_screen()
        self.dock.setProperty("nativePopups", True)
        self.app.processEvents()
        popup = self.window.findChild(QObject, "settingsPopup")
        anchor = self.window.findChild(QQuickItem, "settingsButton")
        newer = self.window.findChild(QQuickItem, "addButton")
        self.engine.rootContext().setContextProperty("ownedPopupAnchor", anchor)
        for mode in ("rehost", "reopen"):
            expression = QQmlExpression(self.engine.rootContext(), popup, "openAt(ownedPopupAnchor)")
            expression.evaluate()
            QTest.qWait(40)
            def closed():
                if mode == "rehost":
                    popup.setProperty("anchorControl", newer)
                else:
                    expression.evaluate()
            popup.closed.connect(closed)
            popup.close()
            popup.closed.disconnect(closed)
            self.assertTrue(popup.property("interactionBusy"))
            QTest.qWait(50)
            if mode == "reopen":
                self.assertTrue(popup.property("visible"))
                popup.close()
            self.window.requestActivate()
            for _ in range(20):
                if QGuiApplication.focusWindow() == self.window:
                    break
                QTest.qWait(5)
            self.assertEqual(QGuiApplication.focusWindow(), self.window)
            newer.forceActiveFocus(Qt.OtherFocusReason)
            QTest.qWait(80)
            self.assertFalse(popup.property("interactionBusy"))
            self.assertEqual(self.window.activeFocusItem(), newer)
        self.assertEqual(self.warnings, [])

    def test_native_popup_close_preserves_a_newer_host_focus_choice(self):
        self.place_dock_inside_available_screen()
        self.dock.setProperty("nativePopups", True)
        self.app.processEvents()
        anchor = self.window.findChild(QQuickItem, "settingsButton")
        newer = self.window.findChild(QQuickItem, "addButton")
        popup = self.window.findChild(QObject, "settingsPopup")
        self.assertTrue(newer.isVisible() and newer.isEnabled())
        self.window.requestActivate()
        for _ in range(40):
            if QGuiApplication.focusWindow() == self.window:
                break
            QTest.qWait(5)
        self.assertEqual(QGuiApplication.focusWindow(), self.window)
        self.engine.rootContext().setContextProperty("ownedPopupAnchor", anchor)
        expression = QQmlExpression(self.engine.rootContext(), popup, "openAt(ownedPopupAnchor)")
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        QTest.qWait(40)
        dialog = popup.property("nativeDialog")
        self.assertTrue(popup.property("visible") and dialog.isVisible())
        self.assertEqual(QGuiApplication.focusWindow(), dialog)
        choices = []

        def choose_newer_control():
            # closed is public and synchronous; the facade queues restoration afterwards.
            self.window.requestActivate()
            for _ in range(40):
                if QGuiApplication.focusWindow() == self.window:
                    break
                QTest.qWait(5)
            newer.forceActiveFocus(Qt.OtherFocusReason)
            choices.append((QGuiApplication.focusWindow() == self.window,
                            self.window.activeFocusItem() == newer))

        popup.closed.connect(choose_newer_control)
        try:
            popup.close()
            QTest.qWait(80)
            self.assertEqual(choices, [(True, True)])
            self.assertEqual(QGuiApplication.focusWindow(), self.window)
            self.assertEqual(self.window.activeFocusItem(), newer)
            self.assertFalse(popup.property("visible") or dialog.isVisible())
            self.assertEqual(self.warnings, [])
        finally:
            popup.closed.disconnect(choose_newer_control)

    def test_native_task_menu_routes_only_to_owned_dialog_and_preserves_keyboard_close(self):
        self.place_dock_inside_available_screen()
        self.dock.setProperty("nativePopups", True)
        button = self.window.findChild(QQuickItem, "settingsButton")
        self.engine.rootContext().setContextProperty("ownedTaskAnchor", button)
        self.evaluate("showTaskMenuAt(0, {AppName:'Owned task', IsWindow:true, CanLaunchNewInstance:true, IsMinimizable:true, IsClosable:true}, ownedTaskAnchor)")
        QTest.qWait(40)
        menu = self.window.findChild(QObject, "nativeTaskContextMenu")
        generic = self.window.findChild(QObject, "taskContextMenu")
        dialog = menu.property("nativeDialog")
        self.assertTrue(menu.property("visible"))
        self.assertFalse(generic.property("visible"))
        proxy = dialog.property("visualParent")
        self.assertNotEqual(proxy, button)
        self.assertAlmostEqual(proxy.mapToGlobal(QPoint(int(proxy.width() / 2), 0)).x(),
                               button.mapToGlobal(QPoint(int(button.width() / 2), 0)).x(), delta=1)
        glass_top = self.dock.mapToGlobal(QPoint(0, int(self.dock.property("glassTop")))).y()
        self.assertLessEqual(dialog.y() + dialog.height() - menu.property("shadowMargin"), glass_top - 10 + 1)
        self.assertEqual(dialog.activeFocusItem().property("text"), "Nova janela")
        QTest.keyClick(dialog, Qt.Key_Down)
        self.assertEqual(dialog.activeFocusItem().property("text"), "Minimizar / restaurar")
        QTest.keyClick(dialog, Qt.Key_Up)
        self.assertEqual(dialog.activeFocusItem().property("text"), "Nova janela")
        closed = QSignalSpy(menu.closed)
        QTest.keyClick(dialog, Qt.Key_Escape)
        QTest.qWait(40)
        self.assertFalse(menu.property("visible"))
        self.assertFalse(dialog.property("visible"))
        self.assertEqual(closed.count(), 1)
        self.assertEqual(self.warnings, [])

    def test_native_task_anchor_destruction_keeps_center_close_and_reopen_without_warnings(self):
        self.place_dock_inside_available_screen()
        self.dock.setProperty("nativePopups", True)
        self.engine.rootContext().setContextProperty("ownedAnchorParent", self.dock)
        anchor = self.evaluate("Qt.createQmlObject('import QtQuick; Item {width:40; height:40; x:20}', ownedAnchorParent)")
        self.engine.rootContext().setContextProperty("ownedDyingAnchor", anchor)
        self.evaluate("showTaskMenuAt(0, {AppName:'Owned task', CanLaunchNewInstance:true}, ownedDyingAnchor)")
        QTest.qWait(30)
        popup = self.window.findChild(QObject, "nativeTaskContextMenu")
        dialog = popup.property("nativeDialog")
        captured_center = anchor.mapToGlobal(QPoint(20, 0)).x()
        self.evaluate("ownedDyingAnchor.destroy()")
        QTest.qWait(30)
        self.assertEqual(self.warnings, [])
        self.assertIsNone(popup.property("anchorControl"))
        proxy = dialog.property("visualParent")
        self.assertAlmostEqual(proxy.mapToGlobal(QPoint(int(proxy.width() / 2), 0)).x(), captured_center, delta=1)
        QTest.keyClick(dialog, Qt.Key_Escape)
        QTest.qWait(30)
        self.assertFalse(popup.property("visible"))
        replacement = self.window.findChild(QQuickItem, "settingsButton")
        self.engine.rootContext().setContextProperty("ownedReplacementAnchor", replacement)
        self.evaluate("showTaskMenuAt(0, {AppName:'Replacement task', CanLaunchNewInstance:true}, ownedReplacementAnchor)")
        QTest.qWait(30)
        self.assertTrue(popup.property("visible"))
        self.assertEqual(popup.property("anchorControl"), replacement)
        QTest.keyClick(dialog, Qt.Key_Escape)
        QTest.qWait(30)
        self.assertFalse(popup.property("visible"))
        self.assertEqual(self.warnings, [])

    def test_task_context_menu_supports_keyboard_and_returns_focus(self):
        if self.app.platformName() == "offscreen":
            self.skipTest("TaskManager needs a Wayland or X11 connection")
        settings = self.window.findChild(QQuickItem, "settingsButton")
        menu = self.window.findChild(QObject, "taskContextMenu")
        # Exercise keyboard interaction in the in-window renderer. QtTest's
        # synthetic events cannot qualify native Wayland popup seat grabs;
        # native placement/grabs remain part of the real-panel gate.
        self.assertTrue(menu.setProperty("popupType", 0))  # Controls.Popup.Item
        for steps, key, modifiers, title in ((1, Qt.Key_Menu, Qt.NoModifier, "Dolphin"),
                                             (2, Qt.Key_F10, Qt.ShiftModifier, "Konsole")):
            settings.forceActiveFocus(Qt.TabFocusReason)
            for _ in range(steps):
                QTest.keyClick(self.window, Qt.Key_Tab)
            task_button = self.window.activeFocusItem()
            self.assertIsNotNone(task_button)
            self.assertNotEqual(task_button, settings)
            self.assertNotEqual(task_button.objectName(), "addButton")
            opened = QSignalSpy(menu.opened)
            QTest.keyClick(self.window, key, modifiers)
            if not opened.count():
                self.assertTrue(opened.wait(1000), "Keyboard context action should open the task menu")
            self.assertEqual(self.evaluate("menuData.title"), title)
            self.assertTrue(menu.property("visible"))
            closed = QSignalSpy(menu.closed)
            QTest.keyClick(self.window, Qt.Key_Escape)
            if not closed.count():
                self.assertTrue(closed.wait(1000))
            self.assertFalse(menu.property("visible"))
            self.assertEqual(self.window.activeFocusItem(), task_button)
        self.assertEqual(self.warnings, [])

    def test_integrations_render_real_percentages_and_neutral_stale_data(self):
        import json
        from test_addon_peripherals import peripheral_frame, missing_frame
        # Rendering only: quota routing through the addon host has its own tests.
        self.evaluate("integrations.addonQuotaEnabled=false")
        self.evaluate("integrations.active=true; integrations.enabledModules=['quota','peripherals','recording']; integrations.nowMsOverride=100000")
        self.evaluate("integrations.acceptSnapshot(JSON.stringify({schemaVersion:2,modules:['quota','recording'],quota:{status:'ready',windows:[{provider:'codex',label:'5 h',usedPercent:37,stale:false}]},recording:{status:'idle',state:'idle'}}), ['quota','recording'])")
        self.app.processEvents()
        def reply_addon(frame):
            self.evaluate("integrations.refresh()")
            expr = QQmlExpression(self.engine.rootContext(), self.window,
                "addonCalls.filter(c => c.message.service === 'org.orla.Addons' && c.message.member === 'SnapshotFor').slice(-1)[0].resolve({value: " + json.dumps(json.dumps(frame)) + "})")
            expr.evaluate()
            self.assertFalse(expr.hasError(), expr.error().toString())
        reply_addon(peripheral_frame(percent=64))
        self.assertEqual(self.evaluate("integrations.quotaSummary"), "codex · 37% usado")
        self.assertEqual(self.evaluate("integrations.batterySummary"), "Mouse · 64%")
        self.evaluate("integrations.acceptSnapshot(JSON.stringify({schemaVersion:2,modules:['quota','recording'],quota:{status:'stale',windows:[{provider:'codex',label:'5 h',usedPercent:37,stale:true}]},recording:{status:'missing',state:'unknown'}}), ['quota','recording']); integrations.invalidateAddons()")
        self.app.processEvents()
        reply_addon(missing_frame())
        self.assertEqual(self.evaluate("integrations.quotaSummary"), "Dados desatualizados")
        self.assertEqual(self.evaluate("integrations.batterySummary"), "Sem cache local")
        self.assertFalse(self.evaluate("integrations.acceptSnapshot('{\"schemaVersion\":999}', ['quota'])"))

    def test_failed_integration_neutralizes_previously_fresh_details(self):
        self.evaluate("integrations.acceptSnapshot(JSON.stringify({schemaVersion:2,modules:['quota','recording'],quota:{status:'ready',windows:[{provider:'codex',label:'5 h',usedPercent:37,stale:false}]},recording:{status:'missing',state:'unknown'}}), ['quota','recording'])")
        self.evaluate("integrations.unavailable('Falha de conexão')")
        self.assertEqual(self.evaluate("integrations.quota.windows.length"), 0)
        self.assertEqual(self.evaluate("integrations.quotaSummary"), "Integração indisponível")

    def test_external_device_names_render_as_plain_text_in_tile_and_tooltip(self):
        engine = QQmlApplicationEngine()
        engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("TileHarness.qml").resolve())))
        window = engine.rootObjects()[0]
        try:
            tile = window.findChild(QObject, "fixtureTile")
            # Live icons show no names; the label/tooltip is the only text surface.
            tooltip_text = tile.findChild(QObject, "tileTooltipText")
            expression = QQmlExpression(engine.rootContext(), tooltip_text, "textFormat")
            self.assertEqual(expression.evaluate()[0], 0)
            self.assertFalse(expression.hasError(), expression.error().toString())
            self.assertIn('<img src=', tile.property("tooltip"))
            self.assertIn('<img src=', tile.property("subtitle"))
        finally:
            window.close()
            engine.deleteLater()
            self.app.processEvents()

    def test_low_panel_preserves_space_for_window_indicators(self):
        self.dock.setHeight(64)
        for requested_size in (42, 64):
            self.config.setProperty("iconSize", requested_size)
            self.app.processEvents()
            self.assertLessEqual(self.dock.property("tileSize") + 16, self.dock.height() - 20)

    def test_system_battery_opt_in_renders_zero_and_neutralizes_failure(self):
        battery = self.window.findChild(QQuickItem, "systemBattery")
        transport = self.window.findChild(QObject, "batteryTransport")
        self.assertIsNotNone(battery)
        self.assertEqual(battery.property("status"), "inactive")
        battery.setProperty("transport", transport)
        self.config.setProperty("showSystemBattery", True)
        self.app.processEvents()
        self.assertEqual(battery.property("status"), "ready")
        self.assertTrue(self.tile_property("systemBatteryTile", "visible"))
        self.assertEqual(self.tile_property("systemBatteryTile", "title"), "0%")
        self.assertEqual(self.tile_property("systemBatteryTile", "subtitle"), "Na bateria")
        transport.setProperty("fail", True)
        self.evaluate("systemBattery.refresh()")
        self.assertEqual(battery.property("status"), "unavailable")
        self.assertEqual(self.tile_property("systemBatteryTile", "title"), "Energia")
        self.assertEqual(self.tile_property("systemBatteryTile", "subtitle"), "Bateria indisponível")
        self.config.setProperty("showSystemBattery", False)
        self.assertEqual(battery.property("status"), "inactive")
        self.assertFalse(self.tile_property("systemBatteryTile", "visible"))
        self.assertFalse(self.evaluate("systemBattery.refresh()"))
        self.assertEqual(self.warnings, [])

    def test_media_popup_uses_the_shared_native_model(self):
        controls = self.window.findChild(QQuickItem, "mediaControls")
        self.assertIsNotNone(controls)
        # Compare the two QObject references directly rather than executing any player action.
        self.assertIsNotNone(controls.property("media"))
        self.assertEqual(controls.property("media"), self.dock.property("mediaSource"))
        fixture = self.window.findChild(QObject, "fixtureMedia")
        self.dock.setProperty("mediaSource", fixture)
        self.app.processEvents()
        self.assertEqual(self.tile_property("musicTile", "title"), "<b>" + "A" * 509)
        self.assertEqual(self.tile_property("musicTile", "subtitle"), "<i>" + "B" * 253)
        self.assertEqual(controls.property("media"), fixture)
        self.assertEqual(self.warnings, [])

    def test_control_center_is_opt_in_read_only_on_open_and_uses_only_mock_backend(self):
        button = self.window.findChild(QQuickItem, "controlCenterButton")
        popup = self.window.findChild(QObject, "controlCenterPopup")
        loader = self.window.findChild(QQuickItem, "controlCenterNativeLoader")
        audio_loader = self.window.findChild(QQuickItem, "controlCenterAudioNativeLoader")
        backend = self.window.findChild(QObject, "dockControlCenterBackend")
        audio_backend = self.window.findChild(QObject, "dockAudioBackend")
        audio = self.window.findChild(QQuickItem, "audioControlState")
        battery = self.window.findChild(QQuickItem, "systemBattery")
        self.assertFalse(button.property("visible"))
        self.assertFalse(loader.property("active"))
        self.assertFalse(self.dock.property("nativeControlCenterBackendLoaded"))
        self.assertFalse(audio_loader.property("active"))
        self.assertFalse(self.dock.property("nativeAudioBackendLoaded"))
        self.assertEqual(audio.property("status"), "inactive")

        self.config.setProperty("showControlCenter", True)
        QTest.qWait(20)
        self.assertTrue(button.property("visible"))
        snapshot = self.evaluate("JSON.stringify({profilesJSON:configuration.profilesJSON,theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,timerDeadline:configuration.timerDeadline,timerRemaining:configuration.timerRemaining,timerBreak:configuration.timerBreak,completedFocus:configuration.completedFocus,showControlCenter:configuration.showControlCenter})")
        self.assertTrue(popup.setProperty("popupType", 0))
        point = button.mapToScene(QPoint(int(button.width() / 2), int(button.height() / 2)))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        QTest.qWait(30)
        self.assertTrue(popup.property("visible"))
        self.assertEqual(self.evaluate("JSON.stringify({profilesJSON:configuration.profilesJSON,theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,timerDeadline:configuration.timerDeadline,timerRemaining:configuration.timerRemaining,timerBreak:configuration.timerBreak,completedFocus:configuration.completedFocus,showControlCenter:configuration.showControlCenter})"), snapshot)
        calls = backend.property("calls")
        self.assertEqual(calls.toVariant() if hasattr(calls, "toVariant") else calls, [])
        self.assertTrue(battery.property("active"))
        self.assertFalse(loader.property("active"))
        self.assertFalse(self.dock.property("nativeControlCenterBackendLoaded"))
        self.assertFalse(audio_loader.property("active"))
        self.assertFalse(self.dock.property("nativeAudioBackendLoaded"))
        self.assertEqual(audio.property("status"), "ready")
        audio_calls = audio_backend.property("calls")
        self.assertEqual(audio_calls.toVariant() if hasattr(audio_calls, "toVariant") else audio_calls, [])

        sound_action = self.window.findChild(QQuickItem, "controlCenterSoundAction")
        for _ in range(8):
            if self.window.activeFocusItem() == sound_action:
                break
            QTest.keyClick(self.window, Qt.Key_Tab)
            QTest.qWait(10)
        self.assertEqual(self.window.activeFocusItem(), sound_action)
        closed = QSignalSpy(popup.closed)
        QTest.keyClick(self.window, Qt.Key_Escape)
        if not closed.count():
            self.assertTrue(closed.wait(1000))
        self.assertFalse(popup.property("visible"))
        self.assertEqual(self.window.activeFocusItem(), button)
        self.assertFalse(battery.property("active"))
        self.assertEqual(audio.property("status"), "inactive")
        self.assertEqual(self.evaluate("JSON.stringify({profilesJSON:configuration.profilesJSON,theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,timerDeadline:configuration.timerDeadline,timerRemaining:configuration.timerRemaining,timerBreak:configuration.timerBreak,completedFocus:configuration.completedFocus,showControlCenter:configuration.showControlCenter})"), snapshot)
        self.assertEqual(self.warnings, [])

    def test_control_center_popup_respects_narrow_width_and_height_budget(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        loader = self.window.findChild(QQuickItem, "controlCenterNativeLoader")
        audio_loader = self.window.findChild(QQuickItem, "controlCenterAudioNativeLoader")
        backend = self.window.findChild(QObject, "dockControlCenterBackend")
        self.assertTrue(popup.setProperty("popupType", 0))
        self.assertGreater(popup.property("heightBudget"), self.window.height() - 24)
        budget = QQmlExpression(self.engine.rootContext(), popup,
            "widthBudget = 260; heightBudget = 320")
        budget.evaluate()
        self.assertFalse(budget.hasError(), budget.error().toString())
        opened = QQmlExpression(self.engine.rootContext(), popup, "open()")
        opened.evaluate()
        self.assertFalse(opened.hasError(), opened.error().toString())
        QTest.qWait(30)
        self.assertTrue(popup.property("visible"))
        self.assertLessEqual(popup.property("width"), 260)
        self.assertLessEqual(popup.property("height"), 320)
        contents = self.window.findChild(QQuickItem, "controlCenterContents")
        scroll = self.window.findChild(QQuickItem, "controlCenterScroll")
        viewport = scroll.property("contentItem")
        for name in ("controlCenterSoundAction", "controlCenterPowerAction", "controlCenterAllAction"):
            action = self.window.findChild(QQuickItem, name)
            self.assertLessEqual(action.width(), contents.width())
            self.assertGreaterEqual(action.height(), 40)

        final_action = self.window.findChild(QQuickItem, "controlCenterAllAction")
        initial_top = final_action.mapToItem(viewport, QPoint(0, 0)).y()
        self.assertGreater(initial_top + final_action.height(), viewport.height())
        visited = []
        # Enough presses for every Control Center control (CC1 and CC2 cards included).
        for _ in range(20):
            QTest.keyClick(self.window, Qt.Key_Tab)
            QTest.qWait(10)
            focused = self.window.activeFocusItem()
            visited.append(focused.property("objectName") if focused else "")
            if focused == final_action:
                break
        self.assertEqual(self.window.activeFocusItem(), final_action, visited)
        final_top = final_action.mapToItem(viewport, QPoint(0, 0)).y()
        self.assertGreater(viewport.property("contentY"), 0)
        self.assertGreaterEqual(final_top, -0.5)
        self.assertLessEqual(final_top + final_action.height(), viewport.height() + 0.5)
        calls = backend.property("calls")
        self.assertEqual(calls.toVariant() if hasattr(calls, "toVariant") else calls, [])
        self.assertFalse(loader.property("active"))
        self.assertFalse(self.dock.property("nativeControlCenterBackendLoaded"))
        self.assertFalse(audio_loader.property("active"))
        self.assertFalse(self.dock.property("nativeAudioBackendLoaded"))
        self.assertEqual(self.warnings, [])

    def test_disabling_control_center_closes_popup_and_releases_optional_battery(self):
        popup = self.window.findChild(QObject, "controlCenterPopup")
        loader = self.window.findChild(QQuickItem, "controlCenterNativeLoader")
        audio_loader = self.window.findChild(QQuickItem, "controlCenterAudioNativeLoader")
        backend = self.window.findChild(QObject, "dockControlCenterBackend")
        battery = self.window.findChild(QQuickItem, "systemBattery")
        self.assertTrue(popup.setProperty("popupType", 0))
        protected = self.evaluate("JSON.stringify({profilesJSON:configuration.profilesJSON,theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,timerDeadline:configuration.timerDeadline,timerRemaining:configuration.timerRemaining,timerBreak:configuration.timerBreak,completedFocus:configuration.completedFocus})")

        def open_then_disable():
            self.config.setProperty("showControlCenter", True)
            expression = QQmlExpression(self.engine.rootContext(), popup, "open()")
            expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
            QTest.qWait(30)
            self.assertTrue(popup.property("visible"))
            self.assertTrue(battery.property("active"))
            closed = QSignalSpy(popup.closed)
            self.config.setProperty("showControlCenter", False)
            if not closed.count():
                self.assertTrue(closed.wait(1000))
            self.assertFalse(popup.property("visible"))
            self.assertFalse(loader.property("active"))
            self.assertFalse(self.dock.property("nativeControlCenterBackendLoaded"))
            self.assertFalse(audio_loader.property("active"))
            self.assertFalse(self.dock.property("nativeAudioBackendLoaded"))

        open_then_disable()
        self.assertFalse(battery.property("active"))

        self.config.setProperty("showSystemBattery", True)
        QTest.qWait(30)
        open_then_disable()
        self.assertTrue(battery.property("active"))

        calls = backend.property("calls")
        self.assertEqual(calls.toVariant() if hasattr(calls, "toVariant") else calls, [])
        audio_backend = self.window.findChild(QObject, "dockAudioBackend")
        audio_calls = audio_backend.property("calls")
        self.assertEqual(audio_calls.toVariant() if hasattr(audio_calls, "toVariant") else audio_calls, [])
        self.assertEqual(self.evaluate("JSON.stringify({profilesJSON:configuration.profilesJSON,theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,timerDeadline:configuration.timerDeadline,timerRemaining:configuration.timerRemaining,timerBreak:configuration.timerBreak,completedFocus:configuration.completedFocus})"), protected)
        self.assertEqual(self.warnings, [])

    def test_control_center_audio_syncs_externally_and_writes_only_explicit_gestures(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        self.assertTrue(popup.setProperty("popupType", 0))
        opened = QQmlExpression(self.engine.rootContext(), popup, "open()")
        opened.evaluate()
        self.assertFalse(opened.hasError(), opened.error().toString())
        QTest.qWait(30)
        backend = self.window.findChild(QObject, "dockAudioBackend")
        audio = self.window.findChild(QQuickItem, "audioControlState")
        slider = self.window.findChild(QQuickItem, "controlCenterAudioVolume")
        mute = self.window.findChild(QQuickItem, "controlCenterAudioMute")
        selector = self.window.findChild(QQuickItem, "controlCenterOutputSelector")

        publish = QQmlExpression(self.engine.rootContext(), backend, "snapshot = ({status:'ready',normalVolume:65536,defaultOutputId:'headphones',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:false},{id:'headphones',label:'<b>'+ 'F'.repeat(200),volumeRaw:16384,muted:true,writable:true,isDefault:true}]}); revision += 1")
        publish.evaluate()
        self.assertFalse(publish.hasError(), publish.error().toString())
        QTest.qWait(20)
        calls = backend.property("calls")
        self.assertEqual(calls.toVariant() if hasattr(calls, "toVariant") else calls, [])
        self.assertEqual(audio.property("defaultOutputId"), "headphones")
        self.assertEqual(audio.property("confirmedVolume"), 25)
        self.assertTrue(audio.property("muted"))
        self.assertLessEqual(len(selector.property("displayText")), 128)
        display = QQmlExpression(self.engine.rootContext(), selector, "contentItem.text")
        display_text = display.evaluate()[0]
        self.assertFalse(display.hasError(), display.error().toString())
        self.assertEqual(display_text, selector.property("displayText"))
        literal_length = QQmlExpression(self.engine.rootContext(), selector, "contentItem.length")
        self.assertEqual(literal_length.evaluate()[0], len(display_text))
        self.assertFalse(literal_length.hasError(), literal_length.error().toString())

        selector.setProperty("currentIndex", 0)
        QTest.qWait(10)
        calls = backend.property("calls")
        self.assertEqual(calls.toVariant() if hasattr(calls, "toVariant") else calls, [])
        activate_output = QQmlExpression(self.engine.rootContext(), selector, "activated(0)")
        activate_output.evaluate()
        self.assertFalse(activate_output.hasError(), activate_output.error().toString())
        self.assertEqual((backend.property("calls").toVariant())[-1], {"kind": "default-output", "id": "speakers"})
        self.assertFalse(slider.property("enabled"))
        self.assertFalse(mute.property("enabled"))
        confirm_output = QQmlExpression(self.engine.rootContext(), backend, "snapshot = ({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:true},{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:false}]}); revision += 1")
        confirm_output.evaluate()
        self.assertFalse(confirm_output.hasError(), confirm_output.error().toString())
        QTest.qWait(10)
        slider.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key_Right)
        QTest.qWait(10)
        self.assertEqual((backend.property("calls").toVariant())[-1]["kind"], "volume")
        self.assertEqual((backend.property("calls").toVariant())[-1]["id"], "speakers")
        self.assertFalse(any(call["kind"] == "mute" for call in backend.property("calls").toVariant()))
        self.assertFalse(selector.property("enabled"))
        self.assertFalse(mute.property("enabled"))
        raw = (backend.property("calls").toVariant())[-1]["value"]
        confirm_volume = QQmlExpression(self.engine.rootContext(), backend, f"snapshot = ({{status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{{id:'speakers',label:'Alto-falantes',volumeRaw:{raw},muted:false,writable:true,isDefault:true}},{{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:false}}]}}); revision += 1")
        confirm_volume.evaluate()
        self.assertFalse(confirm_volume.hasError(), confirm_volume.error().toString())
        QTest.qWait(10)
        point = mute.mapToScene(QPoint(int(mute.width() / 2), int(mute.height() / 2)))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        self.assertEqual((backend.property("calls").toVariant())[-1], {"kind": "mute", "id": "speakers", "value": True})
        self.assertFalse(selector.property("enabled"))
        self.assertFalse(slider.property("enabled"))
        self.assertFalse(self.dock.property("nativeAudioBackendLoaded"))
        self.assertEqual(self.warnings, [])

    def test_audio_output_keyboard_timeout_restores_confirmed_presentation(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        self.assertTrue(popup.setProperty("popupType", 0))
        opened = QQmlExpression(self.engine.rootContext(), popup, "open()")
        opened.evaluate()
        self.assertFalse(opened.hasError(), opened.error().toString())
        QTest.qWait(30)
        backend = self.window.findChild(QObject, "dockAudioBackend")
        audio = self.window.findChild(QQuickItem, "audioControlState")
        selector = self.window.findChild(QQuickItem, "controlCenterOutputSelector")

        selector.forceActiveFocus()
        QTest.qWait(20)
        QTest.keyClick(self.window, Qt.Key_Down)
        QTest.qWait(20)
        self.assertEqual((backend.property("calls").toVariant())[-1], {"kind": "default-output", "id": "headphones"})
        self.assertEqual(audio.property("pendingKind"), "default-output")
        self.assertEqual(selector.property("currentIndex"), 1)
        self.wait_for_audio_confirmation_timeout(audio)
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertEqual(audio.property("defaultOutputId"), "speakers")
        self.assertEqual(selector.property("currentIndex"), 0)
        self.assertIn("Alto-falantes", selector.property("displayText"))
        self.assertIn("confirm", audio.property("error").lower())
        self.assertEqual(self.warnings, [])

    def wait_for_audio_confirmation_timeout(self, audio):
        # Keep the public deadline during input; KDE handling can already exceed 90 ms.
        self.assertTrue(audio.property("pendingKind"))
        expired = QSignalSpy(audio.pendingKindChanged)
        self.assertTrue(expired.wait(audio.property("confirmationTimeout") + 200))

    def test_audio_output_pointer_failures_restore_confirmed_presentation(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        self.assertTrue(popup.setProperty("popupType", 0))
        opened = QQmlExpression(self.engine.rootContext(), popup, "open()")
        opened.evaluate()
        self.assertFalse(opened.hasError(), opened.error().toString())
        QTest.qWait(30)
        backend = self.window.findChild(QObject, "dockAudioBackend")
        audio = self.window.findChild(QQuickItem, "audioControlState")
        selector = self.window.findChild(QQuickItem, "controlCenterOutputSelector")
        popup_type = QQmlExpression(self.engine.rootContext(), selector, "popup.popupType = 0")
        popup_type.evaluate()
        self.assertFalse(popup_type.hasError(), popup_type.error().toString())

        def choose_headphones_with_pointer():
            selector.forceActiveFocus()
            QTest.qWait(10)
            combo_point = selector.mapToScene(QPoint(int(selector.width() / 2), int(selector.height() / 2)))
            QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, combo_point.toPoint())
            QTest.qWait(20)
            delegate_expression = QQmlExpression(self.engine.rootContext(), selector, "popup.contentItem.itemAtIndex(1)")
            delegate, _ = delegate_expression.evaluate()
            self.assertFalse(delegate_expression.hasError(), delegate_expression.error().toString())
            self.assertIsNotNone(delegate)
            point = delegate.mapToScene(QPoint(int(delegate.width() / 2), int(delegate.height() / 2)))
            QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
            QTest.qWait(20)

        backend.setProperty("rejectWrites", True)
        choose_headphones_with_pointer()
        self.assertEqual((backend.property("calls").toVariant())[-1], {"kind": "default-output", "id": "headphones"})
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertEqual(selector.property("currentIndex"), 0)
        self.assertIn("Alto-falantes", selector.property("displayText"))

        backend.setProperty("rejectWrites", False)
        choose_headphones_with_pointer()
        self.assertEqual(audio.property("pendingKind"), "default-output")
        removal = QQmlExpression(self.engine.rootContext(), backend, "snapshot = ({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes sintéticos',volumeRaw:32768,muted:false,writable:true,isDefault:true}]}); revision += 1")
        removal.evaluate()
        self.assertFalse(removal.hasError(), removal.error().toString())
        QTest.qWait(20)
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertEqual(selector.property("currentIndex"), 0)
        self.assertIn("Alto-falantes", selector.property("displayText"))
        self.assertIn("não está mais disponível", audio.property("error"))
        self.assertEqual(self.warnings, [])

    def test_audio_pointer_drag_never_redirects_after_external_default_change(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        self.assertTrue(popup.setProperty("popupType", 0))
        opened = QQmlExpression(self.engine.rootContext(), popup, "open()")
        opened.evaluate()
        self.assertFalse(opened.hasError(), opened.error().toString())
        QTest.qWait(30)
        backend = self.window.findChild(QObject, "dockAudioBackend")
        audio = self.window.findChild(QQuickItem, "audioControlState")
        slider = self.window.findChild(QQuickItem, "controlCenterAudioVolume")
        selector = self.window.findChild(QQuickItem, "controlCenterOutputSelector")
        slider.forceActiveFocus()
        QTest.qWait(20)

        def accepted_on_speakers_then_default_changes():
            backend.setProperty("calls", [])
            start = slider.mapToScene(QPoint(int(slider.width() * 0.5), int(slider.height() / 2)))
            high = slider.mapToScene(QPoint(int(slider.width() * 0.82), int(slider.height() / 2)))
            QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start.toPoint())
            self.assertTrue(audio.property("volumeGestureActive"))
            QTest.mouseMove(self.window, high.toPoint(), 10)
            QTest.qWait(10)
            accepted_raw = backend.property("calls").toVariant()[-1]["value"]
            changed = QQmlExpression(self.engine.rootContext(), backend, "snapshot = ({status:'ready',normalVolume:65536,defaultOutputId:'headphones',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:false},{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:true}]}); revision += 1")
            changed.evaluate()
            self.assertFalse(changed.hasError(), changed.error().toString())
            QTest.qWait(10)
            self.assertTrue(audio.property("volumeGestureBlocked"))
            self.assertEqual(audio.property("pendingKind"), "volume")
            self.assertEqual(audio.property("defaultOutputId"), "headphones")
            self.assertEqual(selector.property("currentIndex"), 1)
            self.assertEqual(audio.property("confirmedVolume"), 25)
            self.assertAlmostEqual(slider.property("value"), 25, delta=0.5)
            QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, high.toPoint())
            QTest.qWait(10)
            self.assertFalse(audio.property("volumeGestureActive"))
            self.assertEqual(audio.property("pendingKind"), "volume")
            self.assertAlmostEqual(slider.property("value"), 25, delta=0.5)
            self.assertFalse(any(call.get("id") == "headphones" for call in backend.property("calls").toVariant()))
            return accepted_raw

        accepted_raw = accepted_on_speakers_then_default_changes()
        readback = QQmlExpression(self.engine.rootContext(), backend,
            f"snapshot = ({{status:'ready',normalVolume:65536,defaultOutputId:'headphones',outputs:[{{id:'speakers',label:'Alto-falantes',volumeRaw:{accepted_raw},muted:false,writable:true,isDefault:false}},{{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:true}}]}}); revision += 1")
        readback.evaluate()
        self.assertFalse(readback.hasError(), readback.error().toString())
        QTest.qWait(10)
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertEqual(audio.property("defaultOutputId"), "headphones")
        self.assertAlmostEqual(slider.property("value"), 25, delta=0.5)

        reset = QQmlExpression(self.engine.rootContext(), backend, "snapshot = ({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:true},{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:false}]}); revision += 1")
        reset.evaluate()
        self.assertFalse(reset.hasError(), reset.error().toString())
        QTest.qWait(10)
        accepted_on_speakers_then_default_changes()
        self.wait_for_audio_confirmation_timeout(audio)
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertEqual(audio.property("defaultOutputId"), "headphones")
        self.assertAlmostEqual(slider.property("value"), 25, delta=0.5)
        self.assertIn("confirm", audio.property("error").lower())
        self.assertEqual(self.warnings, [])

    def test_audio_pointer_rejected_supersession_restores_pending_presentation(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        self.assertTrue(popup.setProperty("popupType", 0))
        opened = QQmlExpression(self.engine.rootContext(), popup, "open()")
        opened.evaluate()
        self.assertFalse(opened.hasError(), opened.error().toString())
        QTest.qWait(30)
        backend = self.window.findChild(QObject, "dockAudioBackend")
        audio = self.window.findChild(QQuickItem, "audioControlState")
        slider = self.window.findChild(QQuickItem, "controlCenterAudioVolume")

        def rejected_supersession():
            backend.setProperty("calls", [])
            backend.setProperty("rejectWrites", False)
            start = slider.mapToScene(QPoint(max(1, int(slider.width() * 0.50)), max(1, int(slider.height() / 2))))
            high = slider.mapToScene(QPoint(max(1, int(slider.width() * 0.82)), max(1, int(slider.height() / 2))))
            low = slider.mapToScene(QPoint(max(1, int(slider.width() * 0.35)), max(1, int(slider.height() / 2))))
            QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start.toPoint())
            QTest.mouseMove(self.window, high.toPoint(), 10)
            QTest.qWait(10)
            accepted_raw = backend.property("calls").toVariant()[-1]["value"]
            accepted_percent = round(accepted_raw * 100 / 65536)
            backend.setProperty("rejectWrites", True)
            QTest.mouseMove(self.window, low.toPoint(), 10)
            QTest.qWait(10)
            self.assertEqual(len(backend.property("calls").toVariant()), 2)
            self.assertEqual(audio.property("pendingKind"), "volume")
            self.assertEqual(audio.property("confirmedVolume"), 50)
            self.assertAlmostEqual(slider.property("value"), accepted_percent, delta=0.5)
            self.assertTrue(audio.property("error"))
            QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, low.toPoint())
            QTest.qWait(10)
            self.assertFalse(audio.property("volumeGestureActive"))
            self.assertEqual(audio.property("pendingKind"), "volume")
            self.assertAlmostEqual(slider.property("value"), accepted_percent, delta=0.5)
            self.assertTrue(audio.property("error"))
            return accepted_raw, accepted_percent

        accepted_raw, accepted_percent = rejected_supersession()
        confirm = QQmlExpression(self.engine.rootContext(), backend,
            f"snapshot = ({{status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{{id:'speakers',label:'Alto-falantes',volumeRaw:{accepted_raw},muted:false,writable:true,isDefault:true}},{{id:'headphones',label:'Fones',volumeRaw:16384,muted:false,writable:true,isDefault:false}}]}}); revision += 1")
        confirm.evaluate()
        self.assertFalse(confirm.hasError(), confirm.error().toString())
        QTest.qWait(10)
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertEqual(audio.property("confirmedVolume"), accepted_percent)
        self.assertAlmostEqual(slider.property("value"), accepted_percent, delta=0.5)

        reset = QQmlExpression(self.engine.rootContext(), backend,
            "snapshot = ({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:true},{id:'headphones',label:'Fones',volumeRaw:16384,muted:false,writable:true,isDefault:false}]}); revision += 1")
        reset.evaluate()
        self.assertFalse(reset.hasError(), reset.error().toString())
        QTest.qWait(10)
        rejected_supersession()
        self.wait_for_audio_confirmation_timeout(audio)
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertEqual(audio.property("confirmedVolume"), 50)
        self.assertAlmostEqual(slider.property("value"), 50, delta=0.5)
        self.assertIn("confirm", audio.property("error").lower())
        self.assertEqual(self.warnings, [])

    def test_control_center_preference_is_global_immediate_and_does_not_change_profile(self):
        popup = self.window.findChild(QObject, "settingsPopup")
        self.assertTrue(popup.setProperty("popupType", 0))
        expression = QQmlExpression(self.engine.rootContext(), popup, "open()")
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        QTest.qWait(30)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        QTest.qWait(20)
        toggle = self.window.findChild(QQuickItem, "showControlCenter")
        before_profile = self.config.property("profilesJSON")
        before_theme = self.config.property("theme")
        toggle.forceActiveFocus()
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertTrue(self.config.property("showControlCenter"))
        self.assertEqual(self.config.property("profilesJSON"), before_profile)
        self.assertEqual(self.config.property("theme"), before_theme)
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
