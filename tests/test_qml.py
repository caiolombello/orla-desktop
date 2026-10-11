import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "wayland" if os.environ.get("WAYLAND_DISPLAY") else "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, Qt, QPoint
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
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source):
        expression = QQmlExpression(self.engine.rootContext(), self.dock, source)
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
        self.assertIn("applications:systemsettings.desktop", self.config.property("launchers"))
        self.assertTrue(self.evaluate("moveTask(0, 1)"))
        self.assertEqual(self.config.property("launchers")[:2], ["applications:org.kde.konsole.desktop", "applications:org.kde.dolphin.desktop"])
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
        opened = QSignalSpy(popup.opened)
        point = button.mapToScene(QPoint(int(button.width() / 2), int(button.height() / 2)))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        self.assertEqual(opened.count(), 1)
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


if __name__ == "__main__":
    unittest.main()
