import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, Qt
from PySide6.QtGui import QAccessible, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class WidgetStripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("WidgetStripHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.strip = self.window.findChild(QQuickItem, "widgetStripUnderTest")
        self.dock = self.window.findChild(QObject, "fixtureDock")
        self.integrations = self.window.findChild(QObject, "fixtureIntegrations")
        self.battery = self.window.findChild(QObject, "fixtureBattery")
        QTest.qWait(30)

    def tearDown(self):
        if self.engine.rootObjects():
            self.window.close()
            self.window.deleteLater()
            QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
            self.app.processEvents()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.window, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def tile(self, name):
        tile = self.evaluate("children.find(item => item.objectName === " + json.dumps(name) + ")", self.strip)
        self.assertIsNotNone(tile, name)
        return tile

    def publish(self, quota=None, peripherals=None, recording=None):
        snapshot = {
            "schemaVersion": 1,
            "quota": quota or {"status": "missing", "windows": [], "costs": []},
            "peripherals": peripherals or {"status": "missing", "devices": []},
            "recording": recording or {"status": "missing", "state": "unknown"},
        }
        text = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
        self.assertTrue(self.evaluate("acceptSnapshot(" + json.dumps(text) + ")", self.integrations))

    # Widgets are square live icons (slot = iconSize 42 + Style.dock.slotGap 8);
    # `live` says whether the icon shows data or its idle face.
    SLOT = 50

    def assert_idle(self, tile, title, subtitle):
        self.assertFalse(tile.property("live"))
        self.assertEqual(tile.width(), self.SLOT)
        self.assertEqual(tile.property("implicitWidth"), self.SLOT)
        self.assertEqual(tile.property("title"), title)
        self.assertEqual(tile.property("subtitle"), subtitle)
        self.assertIn(title, tile.property("tooltip"))
        self.assertIn(subtitle, tile.property("tooltip"))
        interface = QAccessible.queryAccessibleInterface(tile)
        self.assertIsNotNone(interface)
        self.assertEqual(interface.text(QAccessible.Text.Name), tile.property("tooltip"))

    def assert_live(self, tile, title, subtitle):
        self.assertTrue(tile.property("live"))
        self.assertEqual(tile.width(), self.SLOT)
        self.assertEqual(tile.property("implicitWidth"), self.SLOT)
        self.assertEqual(tile.property("title"), title)
        self.assertEqual(tile.property("subtitle"), subtitle)
        self.assertIn(title, tile.property("tooltip"))

    def test_music_keeps_one_focused_actionable_tile_while_going_idle_and_live(self):
        music = self.tile("musicTile")
        identity = music
        self.assert_idle(music, "Sua música", "Nenhum player aberto")
        music.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(openCalls)")), ["music"])

        self.evaluate("player = ({iconName:'spotify',track:'Faixa real',artist:'Artista real'})", self.dock)
        QTest.qWait(10)
        self.assertIs(self.tile("musicTile"), identity)
        self.assertTrue(music.property("activeFocus"))
        self.assert_live(music, "Faixa real", "Artista real")
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(openCalls)")), ["music", "music"])

        self.evaluate("player = null", self.dock)
        QTest.qWait(10)
        self.assertIs(self.tile("musicTile"), identity)
        self.assertTrue(music.property("activeFocus"))
        self.assert_idle(music, "Sua música", "Nenhum player aberto")

    def test_provider_state_matrix_compacts_only_states_without_meaningful_data(self):
        quota = self.tile("quotaTile")
        peripherals = self.tile("peripheralsTile")
        battery = self.tile("systemBatteryTile")
        recording = self.tile("recordingTile")
        identities = [quota, peripherals, battery, recording]

        self.assert_idle(quota, "QuotaLantern", "Sem leitura disponível")
        self.assert_idle(peripherals, "PeriGauge", "Sem cache local")
        self.assert_idle(battery, "Energia", "Bateria indisponível")
        self.assert_idle(recording, "FalaTrace", "Sem estado disponível")
        quota.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(openCalls)")), ["quota"])

        self.publish(
            quota={"status": "ready", "windows": [{"provider": "codex", "usedPercent": 37, "stale": False}], "costs": []},
            peripherals={"status": "ready", "devices": [{"name": "Mouse", "percent": 64, "stale": False, "present": True}]},
            recording={"status": "unknown", "state": "recording"},
        )
        self.evaluate("status = 'ready'; percentKnown = true; percent = 99; charging = 'not-charging'", self.battery)
        QTest.qWait(10)
        self.assert_live(quota, "QuotaLantern", "codex · 37% usado")
        self.assert_live(peripherals, "PeriGauge", "Mouse · 64%")
        self.assert_live(battery, "99%", "Na tomada")
        self.assert_live(recording, "FalaTrace", "Estado salvo · gravando")
        self.assertTrue(quota.property("activeFocus"))
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(openCalls)")), ["quota", "quota"])

        self.publish(
            quota={"status": "stale", "windows": [{"provider": "codex", "usedPercent": 37, "stale": True}], "costs": []},
            peripherals={"status": "stale", "devices": [{"name": "Mouse", "percent": 64, "stale": True, "present": True}]},
            recording={"status": "unknown", "state": "recording"},
        )
        QTest.qWait(10)
        self.assert_live(quota, "QuotaLantern", "Dados desatualizados")
        self.assert_live(peripherals, "PeriGauge", "Dados desatualizados")

        self.publish(
            quota={"status": "stale", "windows": [{"provider": "codex", "usedPercent": 37, "stale": True}], "costs": []},
            peripherals={"status": "unknown", "devices": [{"name": "Mouse", "percent": None, "stale": False, "present": False}]},
            recording={"status": "unknown", "state": "recording"},
        )
        QTest.qWait(10)
        self.assert_live(peripherals, "PeriGauge", "Mouse · fora de alcance")

        self.evaluate("unavailable('Falha de conexão')", self.integrations)
        self.evaluate("status = 'unavailable'; percentKnown = false; percent = -1", self.battery)
        QTest.qWait(10)
        self.assert_idle(quota, "QuotaLantern", "Integração indisponível")
        self.assert_idle(peripherals, "PeriGauge", "Integração indisponível")
        self.assert_idle(battery, "Energia", "Bateria indisponível")
        self.assert_idle(recording, "FalaTrace", "Sem estado disponível")
        self.assertEqual([self.tile(name) for name in ("quotaTile", "peripheralsTile", "systemBatteryTile", "recordingTile")], identities)

    def test_whitespace_only_absent_name_stays_compact_through_real_snapshot_contract(self):
        peripherals = self.tile("peripheralsTile")
        identity = peripherals
        peripherals.forceActiveFocus(Qt.TabFocusReason)
        self.publish(peripherals={
            "status": "unknown",
            "devices": [{"name": " \t ", "percent": None, "stale": False, "present": False}],
        })
        QTest.qWait(10)
        self.assertIs(self.tile("peripheralsTile"), identity)
        self.assertTrue(peripherals.property("activeFocus"))
        self.assertFalse(peripherals.property("live"))
        self.assertEqual(peripherals.width(), self.SLOT)

        self.publish(peripherals={
            "status": "unknown",
            "devices": [{"name": " Mouse ", "percent": None, "stale": False, "present": False}],
        })
        QTest.qWait(10)
        self.assertIs(self.tile("peripheralsTile"), identity)
        self.assertTrue(peripherals.property("activeFocus"))
        self.assert_live(peripherals, "PeriGauge", " Mouse  · fora de alcance")

    def test_clock_and_idle_pomodoro_stay_live_and_disabled_widget_stays_hidden(self):
        clock = self.tile("clockTile")
        self.assertTrue(clock.property("live"))
        self.assertEqual(clock.width(), self.SLOT)
        self.assertEqual(clock.property("title"), "09:29")
        self.assertTrue(clock.property("subtitle"))
        self.assert_live(self.tile("pomodoroButton"), "25:00", "Foco")
        widgets = [
            {"id": "clock", "visible": True},
            {"id": "pomodoro", "visible": True},
            {"id": "music", "visible": True},
            {"id": "systemBattery", "visible": True},
            {"id": "quota", "visible": False},
            {"id": "peripherals", "visible": True},
            {"id": "recording", "visible": True},
        ]
        self.evaluate("widgets = " + json.dumps(widgets).lower())
        QTest.qWait(10)
        self.assertFalse(self.tile("quotaTile").property("visible"))
        self.assertTrue(self.tile("musicTile").property("visible"))
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(openCalls)")), [])


if __name__ == "__main__":
    unittest.main()
