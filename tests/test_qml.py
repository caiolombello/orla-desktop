import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "wayland" if os.environ.get("WAYLAND_DISPLAY") else "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, Qt, QPoint, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
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
        self.evaluate("integrations.acceptSnapshot(JSON.stringify({schemaVersion: 1, quota: {status: 'ready', windows: [{provider: 'codex', label: '5 h', usedPercent: 37, stale: false}]}, peripherals: {status: 'ready', devices: [{name: 'Mouse', percent: 64, stale: false}]}, recording: {status: 'idle', state: 'idle'}}))")
        self.assertEqual(self.evaluate("integrations.quotaSummary"), "codex · 37% usado")
        self.assertEqual(self.evaluate("integrations.batterySummary"), "Mouse · 64%")
        self.evaluate("integrations.acceptSnapshot(JSON.stringify({schemaVersion: 1, quota: {status: 'stale', windows: [{provider: 'codex', label: '5 h', usedPercent: 37, stale: true}]}, peripherals: {status: 'missing', devices: []}, recording: {status: 'missing', state: 'unknown'}}))")
        self.assertEqual(self.evaluate("integrations.quotaSummary"), "Dados desatualizados")
        self.assertEqual(self.evaluate("integrations.batterySummary"), "Sem leitura disponível")
        self.assertFalse(self.evaluate("integrations.acceptSnapshot('{\"schemaVersion\": 999}')"))

    def test_failed_integration_neutralizes_previously_fresh_details(self):
        self.evaluate("integrations.acceptSnapshot(JSON.stringify({schemaVersion: 1, quota: {status: 'ready', windows: [{provider: 'codex', label: '5 h', usedPercent: 37, stale: false}]}, peripherals: {status: 'missing', devices: []}, recording: {status: 'missing', state: 'unknown'}}))")
        self.evaluate("integrations.unavailable('Falha de conexão')")
        self.assertEqual(self.evaluate("integrations.quota.windows.length"), 0)
        self.assertEqual(self.evaluate("integrations.quotaSummary"), "Integração indisponível")

    def test_external_device_names_render_as_plain_text_in_tile_and_tooltip(self):
        engine = QQmlApplicationEngine()
        engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("TileHarness.qml").resolve())))
        window = engine.rootObjects()[0]
        try:
            tile = window.findChild(QObject, "fixtureTile")
            subtitle = tile.findChild(QObject, "tileSubtitle")
            tooltip_text = tile.findChild(QObject, "tileTooltipText")
            for text_item in (subtitle, tooltip_text):
                expression = QQmlExpression(engine.rootContext(), text_item, "textFormat")
                self.assertEqual(expression.evaluate()[0], 0)
                self.assertFalse(expression.hasError(), expression.error().toString())
            self.assertIn('<img src=', subtitle.property("text"))
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
        backend = self.window.findChild(QObject, "dockControlCenterBackend")
        battery = self.window.findChild(QQuickItem, "systemBattery")
        self.assertFalse(button.property("visible"))
        self.assertFalse(loader.property("active"))
        self.assertFalse(self.dock.property("nativeControlCenterBackendLoaded"))

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

        sound_action = self.window.findChild(QQuickItem, "controlCenterSoundAction")
        for _ in range(4):
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
        self.assertEqual(self.evaluate("JSON.stringify({profilesJSON:configuration.profilesJSON,theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,timerDeadline:configuration.timerDeadline,timerRemaining:configuration.timerRemaining,timerBreak:configuration.timerBreak,completedFocus:configuration.completedFocus,showControlCenter:configuration.showControlCenter})"), snapshot)
        self.assertEqual(self.warnings, [])

    def test_control_center_popup_respects_narrow_width_and_height_budget(self):
        self.config.setProperty("showControlCenter", True)
        popup = self.window.findChild(QObject, "controlCenterPopup")
        loader = self.window.findChild(QQuickItem, "controlCenterNativeLoader")
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
        for _ in range(12):
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
        self.assertEqual(self.warnings, [])

    def test_disabling_control_center_closes_popup_and_releases_optional_battery(self):
        popup = self.window.findChild(QObject, "controlCenterPopup")
        loader = self.window.findChild(QQuickItem, "controlCenterNativeLoader")
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
            self.config.setProperty("showControlCenter", False)
            QTest.qWait(30)
            self.assertFalse(popup.property("visible"))
            self.assertFalse(loader.property("active"))
            self.assertFalse(self.dock.property("nativeControlCenterBackendLoaded"))

        open_then_disable()
        self.assertFalse(battery.property("active"))

        self.config.setProperty("showSystemBattery", True)
        QTest.qWait(30)
        open_then_disable()
        self.assertTrue(battery.property("active"))

        calls = backend.property("calls")
        self.assertEqual(calls.toVariant() if hasattr(calls, "toVariant") else calls, [])
        self.assertEqual(self.evaluate("JSON.stringify({profilesJSON:configuration.profilesJSON,theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,timerDeadline:configuration.timerDeadline,timerRemaining:configuration.timerRemaining,timerBreak:configuration.timerBreak,completedFocus:configuration.completedFocus})"), protected)
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
