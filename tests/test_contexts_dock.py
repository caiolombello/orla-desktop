import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_HOME = os.environ.get("HOME")
_ORIGINAL_CODEX_HOME = os.environ.get("CODEX_HOME")
_PRIVATE = tempfile.TemporaryDirectory(prefix="orla-contexts-dock-")
for _name in ("config", "data", "cache", "runtime", "empty"):
    _path = Path(_PRIVATE.name, _name)
    _path.mkdir(mode=0o700)
for _name in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_STARTER_ADDRESS",
              "DBUS_STARTER_BUS_ADDRESS", "DBUS_STARTER_BUS_TYPE"):
    os.environ.pop(_name, None)
os.environ.update({
    "QT_QPA_PLATFORM": "offscreen",
    "QT_QUICK_BACKEND": "software",
    "QT_QUICK_CONTROLS_STYLE": os.environ.get("QT_QUICK_CONTROLS_STYLE", "Fusion"),
    "QT_QPA_PLATFORMTHEME": "",
    "QML_DISK_CACHE_PATH": str(Path(_PRIVATE.name, "cache", "qml")),
    "XDG_CONFIG_HOME": str(Path(_PRIVATE.name, "config")),
    "XDG_CONFIG_DIRS": str(Path(_PRIVATE.name, "empty")),
    "XDG_DATA_HOME": str(Path(_PRIVATE.name, "data")),
    "XDG_DATA_DIRS": str(Path(_PRIVATE.name, "empty")),
    "XDG_CACHE_HOME": str(Path(_PRIVATE.name, "cache")),
    "XDG_RUNTIME_DIR": str(Path(_PRIVATE.name, "runtime")),
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(Path(_PRIVATE.name, "absent-session-bus")),
    "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=" + str(Path(_PRIVATE.name, "absent-system-bus")),
})
assert os.environ.get("HOME") == _ORIGINAL_HOME
assert os.environ.get("CODEX_HOME") == _ORIGINAL_CODEX_HOME

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class ContextsDockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def create(self, contexts_json="", profiles_json=""):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(
            lambda warnings: self.warnings.extend(warning.toString() for warning in warnings)
        )
        self.engine.setInitialProperties({
            "fixtureContextsJSON": contexts_json,
            "fixtureProfilesJSON": profiles_json,
        })
        self.engine.load(QUrl.fromLocalFile(str(ROOT / "tests" / "ContextsDockHarness.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.dock = self.window.findChild(QQuickItem, "dock")
        self.config = self.window.findChild(QObject, "configuration")
        self.popup = self.window.findChild(QObject, "settingsPopup")
        self.popup.setProperty("popupType", 0)
        self.popup.setProperty("y", 0)
        QTest.qWait(40)

    def setUp(self):
        self.create()

    def dispose(self):
        if not getattr(self, "window", None):
            return
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
        QTest.qWait(10)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.window = None
        self.assertEqual(self.warnings, [])

    def tearDown(self):
        self.dispose()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.dock, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def initialize_profiles(self):
        self.assertTrue(self.evaluate(
            "profiles.initializeDefaults(profiles.activeProfileId, profiles.revision)"
        ))

    def open_contexts(self):
        self.popup.open()
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 3)
        QTest.qWait(40)
        controls = self.window.findChild(QQuickItem, "contextControls")
        self.assertIsNotNone(controls)
        self.assertTrue(controls.property("active"))
        return controls

    def set_snapshot(self, activity_id="a1", activity_name="Foco", desktop_id="d1", desktop_name="Área 1"):
        value = {
            "outputName": "DP-1",
            "activity": {"status": "ready", "currentId": activity_id,
                         "ids": [activity_id], "names": [activity_name]},
            "desktop": {"status": "ready", "currentId": desktop_id,
                        "ids": [desktop_id], "names": [desktop_name]},
        }
        self.evaluate("contextSnapshot = " + json.dumps(value), self.window)
        QTest.qWait(10)

    def test_explicit_desktop_switch_keyboard_preserves_profile_and_pomodoro(self):
        self.initialize_profiles()
        self.evaluate("contextSnapshot = ({outputName:'Fixture',activity:{status:'unavailable',currentId:'',ids:[],names:[]},desktop:{status:'ready',currentId:'one',ids:['one','two'],names:['Uma','Outra']}})", self.window)
        self.open_contexts()
        state = self.window.findChild(QObject, "dockDesktopSwitchState")
        backend = self.window.findChild(QObject, "desktopSwitchFixtureBackend")
        self.config.setProperty("timerDeadline", 9999999999000)
        before = self.evaluate("JSON.stringify([configuration.profilesJSON,configuration.contextsJSON,profiles.activeProfileId,configuration.timerDeadline,appearance.dirty])")
        self.assertTrue(self.dock.property("desktopSwitchWriterQualified"))
        self.assertFalse(self.dock.property("nativeDesktopSwitchBackendLoaded"))
        self.assertTrue(self.evaluate("desktopSwitch.selectDesktop('two')"))
        button = self.window.findChild(QQuickItem, "desktopSwitchButton")
        button.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(10)
        self.assertEqual(backend.property("calls"), 1)
        self.assertTrue(state.property("pending"))
        self.evaluate("setReplied(lastId,':1.44')", backend)
        self.assertTrue(state.property("pending"))
        self.evaluate("contextSnapshot = ({outputName:'Fixture',activity:{status:'unavailable',currentId:'',ids:[],names:[]},desktop:{status:'ready',currentId:'two',ids:['one','two'],names:['Uma','Outra']}})", self.window)
        self.evaluate("readback(lastId,'two',':1.44')", backend)
        self.assertEqual(state.property("status"), "observed")
        self.assertEqual(self.evaluate("JSON.stringify([configuration.profilesJSON,configuration.contextsJSON,profiles.activeProfileId,configuration.timerDeadline,appearance.dirty])"), before)
        self.assertTrue(self.window.property("contextTimerIdentity"))
        self.popup.close()
        QTest.qWait(10)
        self.assertFalse(state.property("active"))

    def test_desktop_switch_failure_cancel_and_close_preserve_real_dependencies(self):
        self.initialize_profiles()
        self.evaluate("contextSnapshot = ({outputName:'Fixture',activity:{status:'unavailable',currentId:'',ids:[],names:[]},desktop:{status:'ready',currentId:'one',ids:['one','two'],names:['Uma','Outra']}})", self.window)
        self.open_contexts()
        state = self.window.findChild(QObject, "dockDesktopSwitchState")
        backend = self.window.findChild(QObject, "desktopSwitchFixtureBackend")
        self.evaluate("pomodoro.toggle(); appearance.begin(); appearance.setToken('radius', 9)")
        witness = "JSON.stringify([configuration.profilesJSON,configuration.contextsJSON,configuration.launchers,configuration.theme,configuration.iconSize,configuration.animations,profiles.activeProfileId,configuration.timerDeadline,configuration.timerRemaining,configuration.timerBreak,configuration.completedFocus])"
        before = self.evaluate(witness)
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.assertTrue(self.evaluate("desktopSwitch.requestDesktopSwitch('two',desktopSwitch.desktopRevision)"))
        self.evaluate("failed(lastId)", backend)
        self.assertEqual(state.property("status"), "failed")
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.assertEqual(self.evaluate(witness), before)
        self.assertTrue(self.evaluate("desktopSwitch.requestDesktopSwitch('two',desktopSwitch.desktopRevision)"))
        self.evaluate("setReplied(lastId,':1.44');readback(lastId,'two',':1.44')", backend)
        self.assertTrue(state.property("pending"))
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 0)
        self.assertFalse(state.property("pending"))
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.assertEqual(self.evaluate(witness), before)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 3)
        self.assertTrue(self.evaluate("desktopSwitch.requestDesktopSwitch('two',desktopSwitch.desktopRevision)"))
        self.popup.close()
        self.assertFalse(state.property("pending"))
        self.assertFalse(state.property("active"))
        self.evaluate("setReplied(lastId,':1.44');readback(lastId,'two',':1.44')", backend)
        self.assertNotEqual(state.property("status"), "observed")
        self.assertEqual(self.evaluate(witness), before)
        self.assertTrue(self.window.property("contextTimerIdentity"))

    def test_kconfig_declares_separate_empty_context_document(self):
        import xml.etree.ElementTree as ET
        entries = [entry for entry in ET.parse(ROOT / "package/contents/config/main.xml").iter()
                   if entry.tag.endswith("entry") and entry.attrib.get("name") == "contextsJSON"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].attrib.get("type"), "String")
        self.assertEqual([child.text for child in entries[0] if child.tag.endswith("default")], [None])

    def test_explicit_bind_writes_once_selector_arrows_do_not_write_and_recreate_loads(self):
        self.initialize_profiles()
        self.set_snapshot()
        controls = self.open_contexts()
        selector = self.window.findChild(QQuickItem, "activityProfileSelector")
        before = self.window.property("contextWriteCount")
        selector.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Down)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.assertEqual(self.window.property("contextWriteCount"), before)
        self.evaluate("chooseProfile('activity','work')", controls)
        self.assertTrue(self.evaluate("bindIntent('activity')", controls))
        self.assertEqual(self.window.property("contextWriteCount"), before + 1)
        raw = self.config.property("contextsJSON")
        profiles_raw = self.config.property("profilesJSON")
        self.assertEqual(json.loads(raw)["activityBindings"][0]["contextId"], "a1")

        self.dispose()
        self.create(raw, profiles_raw)
        reloaded = json.loads(self.evaluate("JSON.stringify(contextBindings.bindings)"))
        self.assertEqual(reloaded["activityBindings"][0]["profileId"], "work")
        self.set_snapshot()
        controls = self.open_contexts()
        self.evaluate("captureIntent('activity')", controls)
        before_unbind = self.window.property("contextWriteCount")
        self.assertTrue(self.evaluate("unbindIntent('activity')", controls))
        self.assertEqual(self.window.property("contextWriteCount"), before_unbind + 1)
        self.assertEqual(json.loads(self.config.property("contextsJSON"))["activityBindings"], [])

    def test_stale_source_and_profile_intentions_fail_without_writes(self):
        self.initialize_profiles()
        self.set_snapshot()
        controls = self.open_contexts()
        self.evaluate("chooseProfile('activity','work')", controls)
        before = self.window.property("contextWriteCount")
        self.set_snapshot(activity_id="a2", activity_name="Outro")
        self.assertFalse(self.evaluate("bindIntent('activity')", controls))
        self.assertEqual(self.window.property("contextWriteCount"), before)

        self.evaluate("chooseProfile('activity','work')", controls)
        self.assertTrue(self.evaluate(
            "profiles.commitPresentation({calendarEvents:true},profiles.activeProfileId,profiles.revision)"
        ))
        profile_writes = self.window.property("contextWriteCount")
        self.assertFalse(self.evaluate("bindIntent('activity')", controls))
        self.assertEqual(self.window.property("contextWriteCount"), profile_writes)

    def test_dirty_appearance_binding_preserves_preview_profile_and_timer_identity(self):
        self.initialize_profiles()
        self.set_snapshot()
        controls = self.open_contexts()
        profile_raw = self.config.property("profilesJSON")
        active_profile = self.evaluate("profiles.activeProfileId")
        self.evaluate("pomodoro.toggle()")
        deadline = self.config.property("timerDeadline")
        self.evaluate("appearance.begin(); appearance.setToken('radius', 9)")
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.evaluate("chooseProfile('desktop','personal')", controls)
        self.assertTrue(self.evaluate("bindIntent('desktop')", controls))
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), active_profile)
        self.assertEqual(self.config.property("profilesJSON"), profile_raw)
        self.assertEqual(self.config.property("timerDeadline"), deadline)
        self.assertTrue(self.window.property("contextTimerIdentity"))

    def test_invalid_future_raw_is_preserved_and_only_association_controls_disable(self):
        raw = '{\n  "formatVersion": "future",\n  "owned": true\n}'
        self.dispose()
        self.create(raw)
        self.initialize_profiles()
        controls = self.open_contexts()
        before = self.window.property("contextWriteCount")
        self.assertFalse(self.window.findChild(QQuickItem, "activityBind").property("enabled"))
        self.assertFalse(self.evaluate("bindIntent('activity')", controls))
        self.assertEqual(self.config.property("contextsJSON"), raw)
        self.assertEqual(self.window.property("contextWriteCount"), before)
        self.assertTrue(self.evaluate("profiles.writable"))

    def test_mock_override_blocks_native_loader_when_hidden_and_on_every_tab(self):
        loader = self.window.findChild(QObject, "contextSourceLoader")
        self.assertFalse(loader.property("active"))
        self.assertFalse(self.dock.property("nativeContextSourceLoaded"))
        self.popup.open()
        tabs = self.window.findChild(QObject, "settingsTabs")
        for index in range(4):
            tabs.setProperty("currentIndex", index)
            QTest.qWait(10)
            self.assertFalse(loader.property("active"), index)
            self.assertFalse(self.dock.property("nativeContextSourceLoaded"), index)

    def test_unavailable_activity_keeps_desktop_enabled_and_stale_binding_bytes(self):
        self.initialize_profiles()
        stale = json.dumps({
            "formatVersion": "0.1-experimental",
            "activityBindings": [
                {"contextId": "removed-activity", "lastKnownName": "Antiga", "profileId": "work"}
            ],
            "desktopBindings": [],
        }, ensure_ascii=False, indent=2)
        self.config.setProperty("contextsJSON", stale)
        self.evaluate("contextSnapshot = ({outputName:'DP-1',"
                      "activity:{status:'unavailable',currentId:'',ids:[],names:[]},"
                      "desktop:{status:'ready',currentId:'d1',ids:['d1'],names:['Área 1']}})", self.window)
        controls = self.open_contexts()
        self.assertFalse(self.window.findChild(QQuickItem, "activityBind").property("enabled"))
        self.assertTrue(self.window.findChild(QQuickItem, "desktopBind").property("enabled"))
        self.assertTrue(self.window.findChild(QQuickItem, "staleActivityBindings").property("visible"))
        self.assertEqual(self.config.property("contextsJSON"), stale)
        desktop = self.window.findChild(QQuickItem, "desktopBind")
        desktop.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(10)
        self.assertEqual(self.window.activeFocusItem(), desktop)
        self.assertGreaterEqual(controls.property("contentItem").property("contentY"), 0)

    def test_plain_long_captions_and_narrow_default_visual_captures(self):
        self.initialize_profiles()
        self.set_snapshot(
            activity_name="<b>Activity longa externa que deve permanecer texto simples</b>",
            desktop_name="Área longa externa & literal",
        )
        self.open_contexts()
        self.assertIn("<b>", self.window.findChild(QQuickItem, "activityContextName").property("text"))
        capture_dir = ROOT / ".runtime" / "contexts-dock-impl" / "captures"
        capture_dir.mkdir(parents=True, exist_ok=True)
        for width, name in ((1000, "default.png"), (420, "narrow.png")):
            self.window.setWidth(width)
            QTest.qWait(30)
            image = self.window.grabWindow()
            self.assertFalse(image.isNull())
            self.assertTrue(image.save(str(capture_dir / name)))


if __name__ == "__main__":
    unittest.main()
