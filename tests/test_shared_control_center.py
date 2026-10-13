"""Composition checks require local KDE QML; portable rules have separate suites."""
import os
import time
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OWNED = Path(tempfile.mkdtemp(prefix="orla-shared-controls-"))
for name in ("config", "data", "cache", "runtime", "empty"):
    (OWNED / name).mkdir(mode=0o700)
for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "QML_IMPORT_PATH", "QML2_IMPORT_PATH"):
    os.environ.pop(name, None)
os.environ.update({"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
    "QT_QPA_PLATFORMTHEME": "", "XDG_CONFIG_HOME": str(OWNED / "config"),
    "XDG_CONFIG_DIRS": str(OWNED / "empty"), "XDG_DATA_HOME": str(OWNED / "data"),
    "XDG_DATA_DIRS": str(OWNED / "empty"), "XDG_CACHE_HOME": str(OWNED / "cache"),
    "XDG_RUNTIME_DIR": str(OWNED / "runtime"),
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(OWNED / "runtime/absent-session"),
    "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=" + str(OWNED / "runtime/absent-system")})
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest, QSignalSpy


class SharedControlCenterCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(ROOT / "tests/QmlHarness.qml")))
        if not self.engine.rootObjects():
            missing = ("org.kde.kirigami", "org.kde.taskmanager", "org.kde.plasma.private.mpris")
            if any("module \"" + name + "\" is not installed" in message
                   for message in self.warnings for name in missing):
                self.engine.deleteLater()
                self.app.processEvents()
                self.skipTest("Composition needs KDE QML; portable registry/session suites cover CI rules")
            self.fail(str(self.warnings))
        self.dock_window = self.engine.rootObjects()[0]
        self.dock_window.setProperty("width", 900)
        self.dock_window.setProperty("height", 900)
        self.dock = self.dock_window.findChild(QQuickItem, "dock")
        self.config = self.dock_window.findChild(QObject, "configuration")
        self.config.setProperty("showControlCenter", True)
        self.popup = self.dock_window.findChild(QQuickItem, "controlCenterPopup")
        self.popup.setProperty("popupType", 0)
        self.audio = self.dock_window.findChild(QObject, "audioControlState")
        self.center = self.dock_window.findChild(QQuickItem, "controlCenterContents")
        self.audio_backend = self.dock.property("audioBackendOverride")
        self.action_backend = self.dock.property("controlCenterBackendOverride")
        self.dock_button = self.dock_window.findChild(QQuickItem, "controlCenterButton")
        self.engine.load(QUrl.fromLocalFile(str(ROOT / "tests/SharedControlCenterBarHarness.qml")))
        self.assertEqual(len(self.engine.rootObjects()), 2, self.warnings)
        self.bar_window = self.engine.rootObjects()[1]
        self.entry = self.bar_window.findChild(QObject, "sharedControlCenterEntry")
        self.bar = self.bar_window.findChild(QQuickItem, "sharedControlCenterBar")
        self.button = self.bar_window.findChild(QQuickItem, "barControlCenterButton")
        QTest.qWait(50)

    def tearDown(self):
        for window in reversed(self.engine.rootObjects()):
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(window, QEvent.DeferredDelete)
        self.app.processEvents()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def wait_until(self, predicate):
        deadline = time.monotonic() + 1.5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "Composed popup did not reach its requested state")

    def evaluate(self, source, target=None):
        target = target or self.dock
        expression = QQmlExpression(QQmlEngine.contextForObject(target), target, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def test_bar_and_dock_open_the_same_view_and_audio_owner_without_writing(self):
        self.assertTrue(self.entry.property("available"))
        self.bar_window.requestActivate()
        QTest.qWait(30)
        point = self.button.mapToScene(self.button.boundingRect().center()).toPoint()
        QTest.mouseClick(self.bar_window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(80)
        self.assertTrue(self.popup.property("visible"))
        self.assertTrue(self.entry.property("isOpen"))
        self.assertEqual(self.center.property("audio"), self.audio)
        self.assertEqual(self.audio.property("confirmedVolume"), 50)
        self.assertIsNone(self.dock_window.findChild(QObject, "controlCenterAudioNativeLoader").property("item"))
        self.assertEqual(self.evaluate("Array.from(calls).length", self.audio_backend), 0)
        self.assertEqual(self.evaluate("Array.from(calls).length", self.action_backend), 0)
        self.evaluate("release()", self.entry)
        self.wait_until(lambda: not self.popup.property("visible"))
        self.dock_window.requestActivate()
        QTest.qWait(30)
        point = self.dock_button.mapToScene(self.dock_button.boundingRect().center()).toPoint()
        QTest.mouseClick(self.dock_window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(80)
        self.assertTrue(self.popup.property("visible"))
        self.assertFalse(self.entry.property("isOpen"))
        self.assertEqual(self.center.property("audio"), self.audio)
        self.assertEqual(self.evaluate("Array.from(calls).length", self.audio_backend), 0)

    def open_bar(self):
        self.bar_window.requestActivate()
        QTest.qWait(30)
        point = self.button.mapToScene(self.button.boundingRect().center()).toPoint()
        QTest.mouseClick(self.bar_window, Qt.LeftButton, Qt.NoModifier, point)
        self.wait_until(lambda: self.entry.property("isOpen"))

    def open_dock(self):
        self.dock_window.requestActivate()
        QTest.qWait(30)
        point = self.dock_button.mapToScene(self.dock_button.boundingRect().center()).toPoint()
        QTest.mouseClick(self.dock_window, Qt.LeftButton, Qt.NoModifier, point)
        self.wait_until(lambda: self.popup.property("visible") and self.popup.property("dockOrigin"))

    def publish_volume(self, raw):
        self.evaluate("snapshot = {status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:["
            "{id:'speakers',label:'Alto-falantes sintéticos',volumeRaw:%d,muted:false,writable:true,isDefault:true},"
            "{id:'headphones',label:'Fones sintéticos',volumeRaw:16384,muted:false,writable:true,isDefault:false}]}; revision++" % raw,
            self.audio_backend)
        QTest.qWait(30)

    def test_transfer_cancels_pending_gesture_and_only_new_readback_emits_one_hud(self):
        self.config.setProperty("showAudioHud", True)
        self.open_dock()
        signal = self.audio.metaObject().method(self.audio.metaObject().indexOfSignal("confirmed(QVariant)"))
        receipts = QSignalSpy(self.audio, signal)
        self.assertTrue(receipts.isValid())
        self.assertTrue(self.evaluate("beginVolumeGesture()", self.audio))
        self.assertTrue(self.evaluate("requestGestureVolume(80)", self.audio))
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        self.open_bar()
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertFalse(self.audio.property("volumeGestureActive"))
        self.publish_volume(52429)
        events = self.dock_window.findChild(QObject, "localEventState")
        self.assertEqual(receipts.count(), 0)
        self.assertEqual(events.property("count"), 0)
        self.assertEqual(self.audio.property("confirmedVolume"), 80)
        self.assertTrue(self.evaluate("requestVolume(60)", self.audio))
        self.publish_volume(39322)
        self.publish_volume(39322)
        self.assertEqual(receipts.count(), 1)
        self.assertEqual(events.property("count"), 1)
        self.assertEqual(self.evaluate("Array.from(calls).length", self.audio_backend), 2)
        current = events.property("current").toVariant()
        self.assertEqual((current["kind"], current["value"]), ("audio", 60))

    def test_hide_dock_entry_preserves_bar_then_removing_bar_preserves_dock_config(self):
        saved = self.evaluate("JSON.stringify({launchers:launchers,profiles:profilesJSON,contexts:contextsJSON})", self.config)
        self.open_bar()
        self.config.setProperty("showControlCenter", False)
        QTest.qWait(30)
        self.assertTrue(self.entry.property("isOpen"))
        self.bar.setProperty("showControlCenter", False)
        self.wait_until(lambda: not self.popup.property("visible"))
        self.assertEqual(self.evaluate("JSON.stringify({launchers:launchers,profiles:profilesJSON,contexts:contextsJSON})", self.config), saved)
        self.config.setProperty("showControlCenter", True)
        self.open_dock()
        self.bar_window.close()
        QTest.qWait(30)
        self.assertTrue(self.popup.property("visible"))
        self.assertEqual(self.evaluate("Array.from(calls).length", self.audio_backend), 0)

    def test_external_failure_and_explicit_settings_are_shared_and_single(self):
        self.open_bar()
        self.audio_backend.setProperty("rejectWrites", True)
        self.assertFalse(self.evaluate("requestVolume(70)", self.audio))
        self.assertTrue(self.audio.property("error"))
        self.assertEqual(self.center.property("audio"), self.audio)
        action = self.dock_window.findChild(QQuickItem, "controlCenterSoundAction")
        self.evaluate("click()", action)
        self.assertEqual(self.evaluate("Array.from(calls).length", self.action_backend), 1)
        self.open_dock()
        self.assertEqual(self.center.property("audio"), self.audio)
        self.assertEqual(self.evaluate("Array.from(calls).length", self.action_backend), 1)

    def test_pending_bar_request_is_cancelled_when_its_window_closes(self):
        self.assertTrue(self.evaluate("toggleControlCenter()", self.bar))
        self.bar_window.close()
        QTest.qWait(60)
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.evaluate("Array.from(calls).length", self.audio_backend), 0)
        self.open_dock()

    def test_destroying_bar_host_closes_actual_surface_and_dock_reopens(self):
        self.open_bar()
        self.bar_window.deleteLater()
        QCoreApplication.sendPostedEvents(self.bar_window, QEvent.DeferredDelete)
        QTest.qWait(60)
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.evaluate("Array.from(calls).length", self.audio_backend), 0)
        self.open_dock()

    def test_destroying_dock_owner_removes_registry_lease_and_bar_is_unavailable(self):
        self.open_bar()
        self.assertEqual(self.evaluate("Array.from(calls).length", self.audio_backend), 0)
        self.dock_window.deleteLater()
        QCoreApplication.sendPostedEvents(self.dock_window, QEvent.DeferredDelete)
        QTest.qWait(60)
        self.assertFalse(self.entry.property("available"))
        self.assertFalse(self.entry.property("isOpen"))
