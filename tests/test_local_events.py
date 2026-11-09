import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_ENV = {name: (name in os.environ, os.environ.get(name))
                 for name in ("HOME", "CODEX_HOME")}
OWNED_ROOT = ROOT / ".runtime" / "tests" / "local-events"
OWNED_ROOT.mkdir(parents=True, exist_ok=True)
OWNED_ROOT.chmod(0o700)
OWNED = Path(tempfile.mkdtemp(prefix="qml-", dir=OWNED_ROOT))
for directory in ("config", "data", "cache", "runtime", "empty"):
    path = OWNED / directory
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
for variable in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_STARTER_ADDRESS",
                 "DBUS_STARTER_BUS_ADDRESS", "DBUS_STARTER_BUS_TYPE",
                 "LD_LIBRARY_PATH", "LD_PRELOAD"):
    os.environ.pop(variable, None)
os.environ.update({
    "QT_QPA_PLATFORM": "offscreen",
    "QT_QUICK_BACKEND": "software",
    "QT_QPA_PLATFORMTHEME": "",
    "QML_DISK_CACHE_PATH": str(OWNED / "cache" / "qml"),
    "XDG_CONFIG_HOME": str(OWNED / "config"),
    "XDG_CONFIG_DIRS": str(OWNED / "empty"),
    "XDG_DATA_HOME": str(OWNED / "data"),
    "XDG_DATA_DIRS": str(OWNED / "empty"),
    "XDG_CACHE_HOME": str(OWNED / "cache"),
    "XDG_RUNTIME_DIR": str(OWNED / "runtime"),
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(OWNED / "runtime" / "absent-session-bus"),
    "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=" + str(OWNED / "runtime" / "absent-system-bus"),
})
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")
assert PROTECTED_ENV == {name: (name in os.environ, os.environ.get(name))
                         for name in ("HOME", "CODEX_HOME")}

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QAccessible, QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QSignalSpy, QTest

APP = QGuiApplication.instance() or QGuiApplication([])


class LocalEventsProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP
        cls.runtime_style = QQuickStyle.name()
        print(f"RUNTIME_QT_QUICK_CONTROLS_STYLE={cls.runtime_style}")
        print(f"LOCAL_EVENTS_OWNED={OWNED}")
        if (OWNED_ROOT.stat().st_mode & 0o777) != 0o700 or (OWNED.stat().st_mode & 0o777) != 0o700:
            raise AssertionError("Local-events test directories must be private")
        if cls.runtime_style != os.environ["QT_QUICK_CONTROLS_STYLE"]:
            raise AssertionError((cls.runtime_style, os.environ["QT_QUICK_CONTROLS_STYLE"]))
        if PROTECTED_ENV != {name: (name in os.environ, os.environ.get(name))
                             for name in ("HOME", "CODEX_HOME")}:
            raise AssertionError("HOME or CODEX_HOME changed before QML startup")

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(
            lambda warnings: self.warnings.extend(warning.toString() for warning in warnings)
        )
        self.engine.load(QUrl.fromLocalFile(str(ROOT / "tests" / "QmlHarness.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.dock = self.window.findChild(QQuickItem, "dock")
        self.config = self.window.findChild(QObject, "configuration")
        self.viewport = self.window.findChild(QQuickItem, "appsViewport")
        QTest.qWait(50)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
        QTest.qWait(10)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.dock, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def settle(self, milliseconds=30):
        self.app.processEvents()
        QTest.qWait(milliseconds)

    def configure_dock(self, width, height, icon_size=64):
        self.config.setProperty("iconSize", icon_size)
        self.dock.setWidth(width)
        self.dock.setHeight(height)
        self.settle()

    def event_state(self):
        return self.window.findChild(QObject, "localEventState")

    def widget_tile(self, name):
        return self.evaluate(
            "children.find(item => item.objectName === 'appsViewport').contentItem.children"
            ".find(item => item.objectName === 'dockContent').children"
            ".find(item => item.objectName === 'widgetStrip').children"
            f".find(item => item.objectName === '{name}')"
        )

    def send_wheel(self, point):
        event = QWheelEvent(
            point, QPointF(self.window.mapToGlobal(point.toPoint())), QPoint(), QPoint(-120, 0),
            Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
        )
        QCoreApplication.sendEvent(self.window, event)
        self.settle()
        return event

    def test_local_toasts_are_default_off_and_keep_the_legacy_viewport(self):
        self.assertFalse(self.evaluate("localEventsRequested"))
        self.assertFalse(self.evaluate("localEventsActive"))
        self.assertEqual(self.viewport.x(), 10)
        self.assertEqual(self.viewport.width(), self.dock.width() - 20)
        content = self.window.findChild(QQuickItem, "dockContent")
        self.assertEqual(self.dock.implicitWidth(), content.implicitWidth() + 24)

    def test_kconfig_declares_one_typed_default_off_global_preference(self):
        import xml.etree.ElementTree as ET
        document = ET.parse(ROOT / "package/contents/config/main.xml")
        entries = [entry for entry in document.iter() if entry.tag.endswith("entry")
                   and entry.attrib.get("name") == "showLocalToasts"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].attrib.get("type"), "Bool")
        defaults = [child.text for child in entries[0] if child.tag.endswith("default")]
        self.assertEqual(defaults, ["false"])

    def test_audio_hud_kconfig_is_typed_default_off_and_scrollbar_chrome_is_hidden(self):
        import xml.etree.ElementTree as ET
        document = ET.parse(ROOT / "package/contents/config/main.xml")
        entries = [entry for entry in document.iter() if entry.tag.endswith("entry")
                   and entry.attrib.get("name") == "showAudioHud"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].attrib.get("type"), "Bool")
        self.assertEqual([child.text for child in entries[0] if child.tag.endswith("default")], ["false"])
        source = (ROOT / "package/contents/ui/DockView.qml").read_text()
        self.assertIn("Controls.ScrollBar.AlwaysOff", source)
        self.assertIn("Flickable.HorizontalFlick", source)

    def test_empty_and_rest_geometry_is_event_independent_across_widths_and_gates(self):
        settings = self.window.findChild(QQuickItem, "settingsButton")
        placeholder = self.window.findChild(QQuickItem, "settingsPlaceholder")
        content = self.window.findChild(QQuickItem, "dockContent")
        self.assertEqual(settings.parentItem(), placeholder)
        surface = self.window.findChild(QQuickItem, "localEventSurface")
        close = self.window.findChild(QQuickItem, "localEventClose")
        for width in (230, 240, 320, 640):
            self.configure_dock(width, 102, 64)
            baseline = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                        self.viewport.x(), self.viewport.width(),
                        self.viewport.property("contentWidth"), self.viewport.property("contentX"))
            self.assertEqual(self.viewport.x(), 10)
            self.assertEqual(self.viewport.width(), width - 20)
            self.assertEqual(self.dock.implicitWidth(), content.implicitWidth() + 24)
            for completion, audio in ((False, False), (True, False), (False, True), (True, True)):
                self.config.setProperty("showLocalToasts", completion)
                self.config.setProperty("showAudioHud", audio)
                self.settle()
                self.assertEqual((self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                                  self.viewport.x(), self.viewport.width(),
                                  self.viewport.property("contentWidth"), self.viewport.property("contentX")),
                                 baseline, (width, completion, audio))
                self.assertFalse(surface.isVisible(), (width, completion, audio))
                self.assertFalse(close.isVisible(), (width, completion, audio))
                self.assertFalse(close.property("activeFocusOnTab"), (width, completion, audio))

    def test_settings_control_is_explicitly_global_and_does_not_rewrite_profiles(self):
        checkbox = self.window.findChild(QQuickItem, "showLocalToasts")
        self.assertIsNotNone(checkbox)
        self.assertIn("(global)", checkbox.property("text"))
        before = self.config.property("profilesJSON")
        self.evaluate("click()", checkbox)
        self.assertTrue(self.config.property("showLocalToasts"))
        self.assertEqual(self.config.property("profilesJSON"), before)
        self.assertTrue(checkbox.property("checked"))

    def test_audio_hud_setting_is_profile_projection_and_confirmed_dock_action_is_local(self):
        checkbox = self.window.findChild(QQuickItem, "showAudioHud")
        self.assertIsNotNone(checkbox)
        before = self.config.property("profilesJSON")
        self.evaluate("click()", checkbox)
        self.settle()
        self.assertTrue(self.config.property("showAudioHud"))
        self.assertEqual(self.config.property("profilesJSON"), before)
        self.configure_dock(320, 102, 64)
        self.assertTrue(self.evaluate("localEventsRequested"))
        self.assertTrue(self.evaluate("localEventsActive"))

        popup = self.window.findChild(QObject, "controlCenterPopup")
        self.assertTrue(popup.setProperty("popupType", 0))
        self.evaluate("open()", popup)
        self.settle()
        audio = self.window.findChild(QObject, "audioControlState")
        backend = self.window.findChild(QObject, "dockAudioBackend")
        self.assertTrue(self.evaluate("requestVolume(80)", audio))
        self.evaluate("snapshot={status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes sintéticos',volumeRaw:52429,muted:false,writable:true,isDefault:true}]}; revision+=1", backend)
        self.settle()
        current = self.event_state().property("current")
        current = current.toVariant() if hasattr(current, "toVariant") else current
        self.assertEqual(current["kind"], "audio")
        self.assertEqual(current["value"], 80)
        self.assertEqual(current["originScope"], "profile:legacy")
        self.assertEqual(current["contextGeneration"], self.evaluate("profiles.revision"))

        self.dock.setProperty("notice", "")
        self.config.setProperty("completedFocus", 0)
        self.config.setProperty("timerBreak", False)
        self.config.setProperty("timerDeadline", 1000)
        self.evaluate("pomodoro.poll(1001)")
        self.assertEqual(self.dock.property("notice"), "Foco concluído. Hora de uma pausa!")
        still_current = self.event_state().property("current")
        still_current = still_current.toVariant() if hasattr(still_current, "toVariant") else still_current
        self.assertEqual(still_current["kind"], "audio")

    def test_pomodoro_routes_completion_to_exactly_one_destination(self):
        state = self.event_state()
        self.config.setProperty("showLocalToasts", False)
        self.config.setProperty("completedFocus", 0)
        self.config.setProperty("timerBreak", False)
        self.config.setProperty("timerDeadline", 1000)
        self.evaluate("pomodoro.poll(1001)")
        self.assertEqual(self.dock.property("notice"), "Foco concluído. Hora de uma pausa!")
        self.assertIsNone(state.property("current"))
        self.assertEqual(self.config.property("completedFocus"), 1)

        self.dock.setProperty("notice", "")
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(240, 102, 64)
        self.config.setProperty("completedFocus", 0)
        self.config.setProperty("timerBreak", False)
        self.config.setProperty("timerDeadline", 2000)
        self.evaluate("pomodoro.poll(2001); pomodoro.poll(2002)")
        current = state.property("current")
        current = current.toVariant() if hasattr(current, "toVariant") else current
        self.assertEqual(current["title"], "Foco concluído")
        self.assertEqual(self.dock.property("notice"), "")
        self.assertEqual(self.config.property("completedFocus"), 1)
        self.assertTrue(self.config.property("timerBreak"))

        self.config.setProperty("timerDeadline", 10000000000000)
        deadline = self.config.property("timerDeadline")
        self.config.setProperty("showLocalToasts", False)
        self.settle()
        self.assertIsNone(state.property("current"))
        self.assertEqual(self.config.property("timerDeadline"), deadline)
        self.assertTrue(self.evaluate("pomodoro.running"))

    def test_island_activities_setting_is_global_default_off_and_needs_the_island(self):
        import xml.etree.ElementTree as ET
        document = ET.parse(ROOT / "package/contents/config/main.xml")
        entries = [entry for entry in document.iter() if entry.tag.endswith("entry")
                   and entry.attrib.get("name") == "islandActivities"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].attrib.get("type"), "Bool")
        self.assertEqual([child.text for child in entries[0] if child.tag.endswith("default")], ["false"])
        checkbox = self.window.findChild(QQuickItem, "islandActivities")
        self.assertIsNotNone(checkbox)
        self.assertIn("(global)", checkbox.property("text"))
        self.assertFalse(checkbox.property("enabled"))
        self.config.setProperty("eventIsland", True)
        self.settle()
        self.assertTrue(checkbox.property("enabled"))
        before = self.config.property("profilesJSON")
        self.evaluate("click()", checkbox)
        self.assertTrue(self.config.property("islandActivities"))
        self.assertEqual(self.config.property("profilesJSON"), before)

    def test_live_activities_keep_the_island_up_without_notice_kinds(self):
        rules = self.window.findChild(QObject, "islandState")
        self.config.setProperty("eventIsland", True)
        self.settle()
        self.assertFalse(self.evaluate("eventIslandActive"))
        self.config.setProperty("islandActivities", True)
        self.settle()
        self.assertTrue(self.evaluate("islandActivitiesActive"))
        self.assertTrue(self.evaluate("eventIslandActive"))
        self.assertFalse(self.evaluate("localEventsActive"))
        # Tests have no Plasma windows and no Plasma-PA: neither loader runs.
        self.assertFalse(self.window.findChild(QObject, "eventIslandLoader").property("active"))
        self.assertFalse(self.window.findChild(QObject, "islandSensorsLoader").property("active"))
        self.assertEqual(rules.property("mode"), "idle")

        self.config.setProperty("timerBreak", False)
        self.config.setProperty("timerDeadline", self.evaluate("Date.now() + 600000"))
        self.settle(600)
        self.assertEqual(rules.property("mode"), "compact")
        self.assertEqual(self.evaluate("primary.kind", rules), "timer")
        self.assertGreater(self.evaluate("primary.secondsLeft", rules), 0)

        self.evaluate("islandSensorsOverride = {microphoneInUse: true, cameraInUse: false}")
        self.settle()
        self.assertEqual(self.evaluate("privacy", rules), {"microphone": True, "camera": False})

        state = self.event_state()
        self.assertTrue(state.property("powerEnabled"))
        self.evaluate("islandSensorsOverride = {microphoneInUse: true, cameraInUse: false, power: {percent: 30, state: 2}}")
        self.settle()
        self.evaluate("islandSensorsOverride = {microphoneInUse: true, cameraInUse: false, power: {percent: 30, state: 1}}")
        self.settle()
        current = state.property("current")
        current = current.toVariant() if hasattr(current, "toVariant") else current
        self.assertEqual((current["kind"], current["action"]), ("power", "charging"))
        self.evaluate("dismiss()", state)
        self.evaluate("islandSensorsOverride = {calendarEvents: [{title: 'Reunião sintética', startMs: Date.now() + 120000,"
                      " endMs: Date.now() + 900000, allDay: false}]}")
        self.settle(1100)
        self.assertEqual(self.evaluate("primary.kind", rules), "meeting")

        # Turning activities off leaves only notices, and none are requested.
        self.config.setProperty("islandActivities", False)
        self.settle()
        self.assertFalse(self.evaluate("eventIslandActive"))
        self.assertEqual(rules.property("mode"), "idle")
        self.assertEqual(self.evaluate("privacy", rules), {"microphone": False, "camera": False})
        self.assertFalse(state.property("powerEnabled"))
        self.config.setProperty("timerDeadline", 0)

    def test_island_kconfig_and_setting_are_global_and_default_off(self):
        import xml.etree.ElementTree as ET
        document = ET.parse(ROOT / "package/contents/config/main.xml")
        entries = [entry for entry in document.iter() if entry.tag.endswith("entry")
                   and entry.attrib.get("name") == "eventIsland"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].attrib.get("type"), "Bool")
        self.assertEqual([child.text for child in entries[0] if child.tag.endswith("default")], ["false"])
        checkbox = self.window.findChild(QQuickItem, "eventIsland")
        self.assertIsNotNone(checkbox)
        self.assertIn("(global)", checkbox.property("text"))
        before = self.config.property("profilesJSON")
        self.evaluate("click()", checkbox)
        self.assertTrue(self.config.property("eventIsland"))
        self.assertEqual(self.config.property("profilesJSON"), before)

    def test_island_takes_events_out_of_the_dock_even_when_it_is_too_narrow_for_a_slot(self):
        # 160 px leaves no room for a slot (under 48 px), which used to drop the event.
        self.config.setProperty("showLocalToasts", True)
        self.config.setProperty("eventIsland", True)
        self.configure_dock(160, 102, 64)
        self.assertLess(self.evaluate("candidateEventSlotWidth"), 48)
        self.assertTrue(self.evaluate("eventIslandActive"))
        self.assertFalse(self.evaluate("localEventsActive"))
        self.assertEqual(self.evaluate("eventSlotWidth"), 0)
        self.assertEqual(self.viewport.x(), 10)
        self.assertEqual(self.viewport.width(), self.dock.width() - 20)
        # The native window loads only in the panel; tests have no Plasma dialogs.
        loader = self.window.findChild(QObject, "eventIslandLoader")
        self.assertFalse(loader.property("active"))

        state = self.event_state()
        self.config.setProperty("completedFocus", 0)
        self.config.setProperty("timerBreak", False)
        self.config.setProperty("timerDeadline", 1000)
        self.evaluate("pomodoro.poll(1001)")
        self.settle()
        current = state.property("current")
        current = current.toVariant() if hasattr(current, "toVariant") else current
        self.assertEqual(current["title"], "Foco concluído")
        self.assertEqual(self.dock.property("notice"), "")
        self.assertFalse(self.window.findChild(QQuickItem, "localEventSurface").isVisible())
        self.assertEqual(self.viewport.width(), self.dock.width() - 20)

        # Turning the island off hands events back to the dock slot rules.
        self.config.setProperty("eventIsland", False)
        self.settle()
        self.assertFalse(self.evaluate("eventIslandActive"))
        self.assertFalse(self.evaluate("localEventsActive"))
        self.configure_dock(320, 102, 64)
        self.assertTrue(self.evaluate("localEventsActive"))
        self.assertTrue(self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                                      "title:'Pausa concluída',detail:'Pronto para focar?'},Date.now())", state))
        self.settle()
        self.assertTrue(self.window.findChild(QQuickItem, "localEventSurface").isVisible())

    def test_island_needs_a_requested_event_kind(self):
        self.config.setProperty("eventIsland", True)
        self.settle()
        self.assertFalse(self.evaluate("eventIslandActive"))
        self.assertFalse(self.evaluate("localEventsActive"))

    def test_invalid_profiles_disable_and_clear_only_local_presentation(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(240, 102, 64)
        pomodoro_identity = self.evaluate("String(pomodoro)")
        presentation = self.evaluate("JSON.stringify(presentation)")
        self.config.setProperty("timerDeadline", 10_000_000_000_000)
        deadline = self.config.property("timerDeadline")
        state = self.event_state()
        self.assertTrue(self.evaluate(
            "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
            "title:'Foco concluído',detail:'Hora de uma pausa!'},Date.now())",
            state,
        ))
        self.assertIsNotNone(state.property("current"))

        raw = '{"formatVersion":"unsupported","preserve":"owned bytes"}'
        self.config.setProperty("profilesJSON", raw)
        self.settle()

        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertFalse(self.evaluate("profiles.writable"))
        self.assertFalse(self.evaluate("localEventsActive"))
        self.assertIsNone(state.property("current"))
        self.assertEqual(self.evaluate("JSON.stringify(presentation)"), presentation)
        self.assertEqual(self.config.property("timerDeadline"), deadline)
        self.assertEqual(self.evaluate("String(pomodoro)"), pomodoro_identity)

        self.dock.setProperty("notice", "")
        self.config.setProperty("completedFocus", 0)
        self.config.setProperty("timerBreak", False)
        self.config.setProperty("timerDeadline", 1000)
        self.evaluate("pomodoro.poll(1001); pomodoro.poll(1002)")
        self.assertEqual(self.dock.property("notice"), "Foco concluído. Hora de uma pausa!")
        self.assertIsNone(state.property("current"))
        self.assertEqual(self.config.property("completedFocus"), 1)
        self.assertTrue(self.config.property("timerBreak"))
        self.assertEqual(self.evaluate("String(pomodoro)"), pomodoro_identity)

    def test_event_policy_is_known_only_bounded_coalesced_and_expires_at_eight_seconds(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(240, 102, 64)
        state = self.event_state()
        valid = "{kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'}"
        self.assertTrue(self.evaluate(f"submit({valid},1000)", state))
        current = state.property("current")
        current = current.toVariant() if hasattr(current, "toVariant") else current
        self.assertEqual(current["deadline"], 9000)
        self.assertFalse(self.evaluate("submit({kind:'unknown',key:'pomodoro:completion',scope:'global',title:'x',detail:'y'},1000)", state))
        self.assertFalse(self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'x',detail:'y',extra:true},1000)", state))
        self.assertTrue(self.evaluate("for(let i=0;i<1000;i++) submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco '+i,detail:'Fim'},2000+i); true", state))
        self.assertEqual(state.property("count"), 1)
        current = state.property("current")
        current = current.toVariant() if hasattr(current, "toVariant") else current
        self.assertEqual(current["title"], "Foco 999")
        self.assertFalse(self.evaluate(f"advance({current['deadline'] - 1})", state))
        self.assertTrue(self.evaluate(f"advance({current['deadline']})", state))
        self.assertIsNone(state.property("current"))

    def test_audio_and_completion_admission_are_independent_and_scope_clears_only_audio(self):
        state = self.event_state()
        state.setProperty("enabled", True)
        state.setProperty("activeScope", "profile:work")
        state.setProperty("activeContextGeneration", 4)
        state.setProperty("completionEnabled", False)
        state.setProperty("audioEnabled", True)
        audio = "{kind:'audio',action:'volume',targetId:'speakers',originScope:'profile:work',contextGeneration:4,value:80,title:'Volume · 80%',detail:'Alto-falantes'}"
        completion = "{kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'}"
        self.assertTrue(self.evaluate(f"submit({audio},Date.now())", state))
        self.assertFalse(self.evaluate(f"submit({completion},Date.now())", state))
        state.setProperty("completionEnabled", True)
        self.assertTrue(self.evaluate(f"submit({completion},Date.now())", state))
        self.assertEqual(state.property("count"), 2)
        state.setProperty("activeContextGeneration", 5)
        events = self.evaluate("JSON.stringify(allEvents())", state)
        events = __import__("json").loads(events)
        self.assertEqual([event["kind"] for event in events], ["completion"])
        state.setProperty("audioEnabled", False)
        self.assertIsNotNone(state.property("current"))
        state.setProperty("completionEnabled", False)
        self.assertIsNone(state.property("current"))

    def test_audio_union_origin_coalescence_public_capacity_and_private_selector(self):
        import json
        state = self.event_state()
        state.setProperty("enabled", True)
        state.setProperty("completionEnabled", True)
        state.setProperty("audioEnabled", True)
        state.setProperty("activeScope", "profile:work")
        state.setProperty("activeContextGeneration", 4)

        def audio(target, value=50):
            return {"kind": "audio", "action": "volume", "targetId": target,
                    "originScope": "profile:work", "contextGeneration": 4, "value": value,
                    "title": f"Volume · {value}%", "detail": target}

        valid = audio("speaker")
        for mutation in (
            {**valid, "originScope": "profile:other"},
            {**valid, "contextGeneration": 3},
            {**valid, "value": 101},
            {**valid, "extra": True},
            {**valid, "action": "unknown"},
            {**valid, "targetId": "bad\noutput"},
        ):
            self.assertFalse(self.evaluate(f"submit({json.dumps(mutation)},1000)", state))
        self.assertTrue(self.evaluate(f"submit({json.dumps(valid)},1000)", state))
        self.assertTrue(self.evaluate(f"submit({json.dumps({**valid, 'value': 60, 'title': 'Volume · 60%'})},1100)", state))
        self.assertEqual(state.property("count"), 1)
        self.assertEqual(self.evaluate("current.value", state), 60)

        completion = {"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                      "title": "Foco concluído", "detail": "Pausa"}
        self.evaluate("clear()", state)
        for index in range(8):
            self.assertTrue(self.evaluate(f"submit({json.dumps(audio(f'out{index}'))},{1200 + index})", state))
        self.assertFalse(self.evaluate(f"submit({json.dumps(completion)},1300)", state))
        self.assertEqual(state.property("count"), 8)

        self.evaluate("clear()", state)
        for index in range(7):
            self.assertTrue(self.evaluate(f"submit({json.dumps(audio(f'out{index}'))},{1400 + index})", state))
        self.assertTrue(self.evaluate(f"submit({json.dumps(completion)},1410)", state))
        self.assertTrue(self.evaluate(f"submit({json.dumps(audio('out7'))},1411)", state))
        kinds = json.loads(self.evaluate("JSON.stringify(allEvents().map(event=>event.kind))", state))
        self.assertEqual(kinds, ["audio"] * 8)

        self.evaluate("clear()", state)
        for index in range(8):
            self.assertTrue(self.evaluate(f"submit({json.dumps(audio(f'out{index}'))},{1500 + index})", state))
        self.assertTrue(self.evaluate(f"submit({json.dumps(audio('out8'))},1510)", state))
        targets = json.loads(self.evaluate("JSON.stringify(allEvents().map(event=>event.targetId))", state))
        self.assertIn("out8", targets)
        self.assertNotIn("out1", targets)

        selected = json.loads(self.evaluate("JSON.stringify(selectPrevalidated(["
            "{priority:10,sequence:1},{priority:10,sequence:2},{priority:10,sequence:3},"
            "{priority:10,sequence:4},{priority:10,sequence:5},{priority:10,sequence:6},"
            "{priority:10,sequence:7},{priority:10,sequence:8},{priority:20,sequence:9}]))", state))
        self.assertEqual(selected["current"]["sequence"], 9)
        self.assertEqual(len(selected["pending"]), 7)
        self.assertNotIn(1, [entry["sequence"] for entry in selected["pending"]])

    def test_completion_and_debounced_audio_announcements_are_state_owned(self):
        import json
        state = self.event_state()
        state.setProperty("enabled", True)
        state.setProperty("completionEnabled", True)
        state.setProperty("audioEnabled", True)
        state.setProperty("activeScope", "profile:work")
        state.setProperty("activeContextGeneration", 4)
        announced = QSignalSpy(state.announcementRequested)
        completion = "{kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Pausa'}"
        self.assertTrue(self.evaluate(f"submit({completion},1000)", state))
        self.assertEqual(announced.count(), 1)
        self.assertTrue(self.evaluate(f"submit({completion},1100)", state))
        self.assertEqual(announced.count(), 1)
        self.evaluate("clear()", state)

        audio = "{kind:'audio',action:'volume',targetId:'speaker',originScope:'profile:work',contextGeneration:4,value:20,title:'Volume · 20%',detail:'Speaker'}"
        self.assertTrue(self.evaluate(f"submit({audio},2000); audioQuiet.stop(); audioMaximum.stop(); true", state))
        self.assertEqual(announced.count(), 1)
        self.assertTrue(self.evaluate("fireAudioQuiet(2200)", state))
        self.assertEqual(announced.count(), 2)

        updated = audio.replace("20", "30")
        self.assertTrue(self.evaluate(f"submit({updated},2300); audioQuiet.stop(); audioMaximum.stop(); true", state))
        self.assertTrue(self.evaluate("fireAudioMaximum(3300)", state))
        self.assertEqual(announced.count(), 3)
        payload = announced.at(2)[0]
        payload = payload.toVariant() if hasattr(payload, "toVariant") else payload
        self.assertIn("30%", payload["accessibleName"])

        self.evaluate("clear()", state)
        first = audio.replace("speaker", "one").replace("Speaker", "One")
        second = audio.replace("speaker", "two").replace("Speaker", "Two")
        self.assertTrue(self.evaluate(f"submit({first},4000); submit({second},4001); audioQuiet.stop(); audioMaximum.stop(); true", state))
        self.assertEqual(announced.count(), 3)
        self.assertTrue(self.evaluate("dismiss(4100); audioQuiet.stop(); audioMaximum.stop(); true", state))
        self.assertTrue(self.evaluate("fireAudioQuiet(4300)", state))
        self.assertEqual(announced.count(), 4)
        current = json.loads(self.evaluate("JSON.stringify(current)", state))
        self.assertEqual(current["targetId"], "two")

    def test_completion_resume_unseen_drop_audio_maximum_and_cancellation_are_deterministic(self):
        import json
        state = self.event_state()
        state.setProperty("enabled", True)
        state.setProperty("completionEnabled", True)
        state.setProperty("audioEnabled", True)
        state.setProperty("activeScope", "profile:work")
        state.setProperty("activeContextGeneration", 4)
        announced = QSignalSpy(state.announcementRequested)
        completion = {"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                      "title": "Foco concluído", "detail": "Pausa"}

        def audio(target, value):
            return {"kind": "audio", "action": "volume", "targetId": target,
                    "originScope": "profile:work", "contextGeneration": 4, "value": value,
                    "title": f"Volume · {value}%", "detail": target}

        self.assertTrue(self.evaluate(f"submit({json.dumps(completion)},1000)", state))
        self.assertEqual(announced.count(), 1)
        self.assertTrue(self.evaluate(f"submit({json.dumps(audio('speaker', 20))},1001); audioQuiet.stop(); audioMaximum.stop(); true", state))
        self.assertTrue(self.evaluate("dismiss(1100)", state))
        self.assertEqual(announced.count(), 1)

        self.evaluate("clear()", state)
        for index in range(8):
            self.assertTrue(self.evaluate(f"submit({json.dumps(audio(f'out{index}', 40))},{2000 + index}); audioQuiet.stop(); audioMaximum.stop(); true", state))
        self.assertFalse(self.evaluate(f"submit({json.dumps(completion)},2010)", state))
        self.assertEqual(announced.count(), 1)

        self.evaluate("clear()", state)
        for timestamp, value in ((3000, 10), (3100, 20), (3190, 30), (3380, 40), (3570, 50), (3760, 60), (3950, 70)):
            self.assertTrue(self.evaluate(f"submit({json.dumps(audio('burst', value))},{timestamp}); audioQuiet.stop(); audioMaximum.stop(); true", state))
        self.assertTrue(self.evaluate("fireAudioMaximum(4000)", state))
        self.assertEqual(announced.count(), 2)
        payload = announced.at(1)[0]
        payload = payload.toVariant() if hasattr(payload, "toVariant") else payload
        self.assertIn("70%", payload["accessibleName"])

        for mode in ("scope", "disable", "dismiss", "expiry"):
            with self.subTest(mode=mode):
                self.evaluate("clear()", state)
                state.setProperty("audioEnabled", True)
                state.setProperty("activeScope", "profile:work")
                state.setProperty("activeContextGeneration", 4)
                self.assertTrue(self.evaluate(f"submit({json.dumps(audio(mode, 55))},5000); audioQuiet.stop(); audioMaximum.stop(); true", state))
                before = announced.count()
                if mode == "scope":
                    state.setProperty("activeContextGeneration", 5)
                elif mode == "disable":
                    state.setProperty("audioEnabled", False)
                elif mode == "dismiss":
                    self.evaluate("dismiss(5100)", state)
                else:
                    self.evaluate("advance(6800)", state)
                self.assertFalse(self.evaluate("fireAudioQuiet(7000)", state))
                self.assertEqual(announced.count(), before)

    def test_enabled_arrival_does_not_move_focus_scroll_or_resize_and_90px_keeps_full_name(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(320, 102, 64)
        add = self.window.findChild(QQuickItem, "addButton")
        maximum = max(0, self.viewport.property("contentWidth") - self.viewport.width())
        self.viewport.setProperty("contentX", maximum)
        add.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        focused = self.window.activeFocusItem()
        content = self.window.findChild(QQuickItem, "dockContent")
        idle_extent = self.viewport.property("contentWidth")
        before = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(), focused,
                  self.viewport.x(), self.viewport.width(), content.width(),
                  self.viewport.property("contentX"), self.evaluate("eventSlotWidth"))
        state = self.event_state()
        accepted = self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state)
        self.assertTrue(accepted)
        self.settle()
        during = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                  self.window.activeFocusItem(), self.viewport.x(), self.viewport.width(),
                  content.width(), self.viewport.property("contentX"),
                  self.evaluate("eventSlotWidth"))
        self.assertEqual(during, before)
        surface = self.window.findChild(QQuickItem, "localEventSurface")
        one_line = self.window.findChild(QQuickItem, "localEventOneLine")
        self.assertEqual(surface.width(), 90)
        self.assertEqual(self.viewport.property("contentWidth"), idle_extent + surface.width())
        self.assertTrue(one_line.property("truncated"))
        self.assertEqual(surface.property("accessibleName"), "Foco concluído. Hora de uma pausa!")
        self.assertTrue(self.evaluate("textFormat === 0", one_line))
        self.assertTrue(self.evaluate("advance(9000)", state))
        self.settle()
        after = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                 self.window.activeFocusItem(), self.viewport.x(), self.viewport.width(),
                 content.width(), self.viewport.property("contentX"),
                 self.evaluate("eventSlotWidth"))
        self.assertEqual(after, before)
        self.assertFalse(surface.isVisible())
        self.assertEqual(self.viewport.property("contentWidth"), idle_extent)

    def test_minimum_compact_surface_keeps_glyph_clear_of_full_close_target(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(230, 102, 64)
        self.evaluate("appearance.begin(); appearance.setToken('reducedMotion', true)")
        add = self.window.findChild(QQuickItem, "addButton")
        add.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        focused = self.window.activeFocusItem()
        state = self.event_state()
        self.assertTrue(self.evaluate(
            "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
            "title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state))
        self.settle()
        self.assertIs(self.window.activeFocusItem(), focused)

        surface = self.window.findChild(QQuickItem, "localEventSurface")
        close = self.window.findChild(QQuickItem, "localEventClose")
        self.assertEqual(surface.property("animationDuration"), 0)
        self.assertEqual((close.width(), close.height()), (24, 24))
        interface = QAccessible.queryAccessibleInterface(close)
        self.assertIsNotNone(interface)
        self.assertIn("Fechar aviso", interface.text(QAccessible.Text.Name))

        for dock_width, slot_width in ((230, 48), (231, 49), (233, 51), (237, 55)):
            self.configure_dock(dock_width, 102, 64)
            self.assertEqual(surface.width(), slot_width)
            self.assertEqual(surface.x(), dock_width - 10 - slot_width)
            self.assertEqual(surface.property("mode"), 0)
            glyph = self.evaluate(
                "(function(){const g=children.find(item => item.text === '✓');"
                "return [g.x,g.width,g.x+g.width,g.paintedWidth,g.paintedHeight];})()",
                surface,
            )
            self.assertEqual(glyph[:3], [6, 12, 18])
            self.assertLessEqual(glyph[3], glyph[1])
            self.assertLessEqual(glyph[4], surface.height())
            self.assertEqual(close.x(), slot_width - 28)
            self.assertGreaterEqual(close.x() - glyph[2], 2)

        close_point = close.mapToScene(QPointF(close.width() / 2, close.height() / 2))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, close_point.toPoint())
        self.settle()
        self.assertIsNone(state.property("current"))

        expiry_focus = self.window.activeFocusItem()
        self.assertTrue(self.evaluate(
            "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
            "title:'Foco concluído',detail:'Hora de uma pausa!'},2000)", state))
        self.assertTrue(self.evaluate("advance(10000)", state))
        self.assertIsNone(state.property("current"))
        self.assertIs(self.window.activeFocusItem(), expiry_focus)

    def test_deliberate_focus_reveals_controls_before_active_overlay_without_arrival_scrolling(self):
        for enabled in (False, True):
            with self.subTest(local_events_enabled=enabled):
                self.config.setProperty("showLocalToasts", enabled)
                self.configure_dock(240, 102, 64)
                add = self.window.findChild(QQuickItem, "addButton")
                settings = self.window.findChild(QQuickItem, "settingsButton")
                maximum = max(0, self.viewport.property("contentWidth") - self.viewport.width())
                self.assertGreater(maximum, 0)
                add.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                self.viewport.setProperty("contentX", maximum)
                settings.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                self.assertEqual(self.viewport.property("contentX"), 0)
                self.viewport.setProperty("contentX", maximum)
                add.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                revealed = self.viewport.property("contentX")
                self.assertLess(revealed, maximum)
                if enabled:
                    state = self.event_state()
                    self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state)
                    self.settle()
                    self.assertEqual(self.viewport.property("contentX"), revealed)
                    self.evaluate("clear()", state)

        self.config.setProperty("showLocalToasts", True)
        self.config.setProperty("showControlCenter", True)
        for name in ("showQuota", "showPeripherals", "showRecording"):
            self.config.setProperty(name, True)
        for dock_width, slot_width in ((230, 48), (770, 224)):
            with self.subTest(dock_width=dock_width, slot_width=slot_width):
                self.configure_dock(dock_width, 102, 64)
                self.window.setWidth(dock_width + 40)
                self.settle()
                state = self.event_state()
                last = self.widget_tile("recordingTile")
                last.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                before_arrival = self.viewport.property("contentX")
                content = self.window.findChild(QQuickItem, "dockContent")
                arrival_geometry = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                                    self.viewport.x(), self.viewport.width(), content.width(),
                                    last.x(), last.width())
                self.assertTrue(self.evaluate(
                    "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                    "title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state))
                self.settle()
                self.assertIs(self.window.activeFocusItem(), last)
                self.assertEqual(self.viewport.property("contentX"), before_arrival)
                self.assertEqual((self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                                  self.viewport.x(), self.viewport.width(), content.width(),
                                  last.x(), last.width()), arrival_geometry)

                surface = self.window.findChild(QQuickItem, "localEventSurface")
                self.assertEqual(surface.width(), slot_width)
                earlier = self.window.findChild(QQuickItem, "controlCenterButton")
                for control in (earlier, last):
                    self.window.findChild(QQuickItem, "settingsButton").forceActiveFocus(
                        Qt.TabFocusReason)
                    self.viewport.setProperty("contentX", 0)
                    control.forceActiveFocus(Qt.TabFocusReason)
                    self.settle()
                    control_left = control.mapToScene(QPointF(0, 0)).x()
                    control_right = control.mapToScene(QPointF(control.width(), 0)).x()
                    viewport_left = self.viewport.mapToScene(QPointF(0, 0)).x()
                    overlay_left = surface.mapToScene(QPointF(0, 0)).x()
                    self.assertGreaterEqual(control_left, viewport_left)
                    self.assertLessEqual(control_right, overlay_left)
                    # An ordinary resize makes Qt settle its own scroll bounds;
                    # focus stays on the same control, so focus-change-only reveal
                    # cannot protect it. Test growing and shrinking the viewport.
                    for resized_width in (dock_width + 1, dock_width + 2, dock_width):
                        self.dock.setWidth(resized_width)
                        self.window.setWidth(resized_width + 40)
                        self.settle(1000)
                        self.assertTrue(surface.isVisible())
                        self.assertIs(self.window.activeFocusItem(), control)
                        control_left = control.mapToScene(QPointF(0, 0)).x()
                        control_right = control.mapToScene(QPointF(control.width(), 0)).x()
                        viewport_left = self.viewport.mapToScene(QPointF(0, 0)).x()
                        overlay_left = surface.mapToScene(QPointF(0, 0)).x()
                        self.assertGreaterEqual(control_left, viewport_left)
                        self.assertLessEqual(control_right, overlay_left,
                                             (control.objectName(), resized_width))
                        actual_maximum = max(0, self.viewport.property("contentWidth")
                                             - self.viewport.width())
                        self.assertGreaterEqual(self.viewport.property("contentX"), 0)
                        self.assertLessEqual(self.viewport.property("contentX"), actual_maximum)
                    self.assertLessEqual(self.viewport.property("contentX"),
                                         max(0, self.viewport.property("contentWidth")
                                             - self.viewport.width()))
                self.evaluate("clear()", state)

    def test_active_overlay_consumes_body_pointer_and_wheel_while_outside_and_close_work(self):
        self.config.setProperty("showLocalToasts", True)
        self.config.setProperty("showControlCenter", True)
        for name in ("showQuota", "showPeripherals", "showRecording"):
            self.config.setProperty(name, True)
        settings = self.window.findChild(QQuickItem, "settingsButton")
        settings_popup = self.window.findChild(QObject, "settingsPopup")
        settings_popup.setProperty("popupType", 0)
        for dock_width, slot_width in ((230, 48), (770, 224)):
            with self.subTest(dock_width=dock_width, slot_width=slot_width):
                self.configure_dock(dock_width, 102, 64)
                self.window.setWidth(dock_width + 40)
                self.window.requestActivate()
                self.assertTrue(QTest.qWaitForWindowActive(self.window, 1000))
                self.settle()
                maximum = max(0, self.viewport.property("contentWidth") - self.viewport.width())
                self.viewport.setProperty("contentX", maximum)
                state = self.event_state()
                self.assertTrue(self.evaluate(
                    "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                    "title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state))
                self.settle()
                surface = self.window.findChild(QQuickItem, "localEventSurface")
                self.assertEqual(surface.width(), slot_width)
                covered = self.widget_tile("recordingTile")
                covered_left = covered.mapToScene(QPointF(0, 0)).x()
                covered_right = covered.mapToScene(QPointF(covered.width(), 0)).x()
                overlay_left = surface.mapToScene(QPointF(0, 0)).x()
                close = self.window.findChild(QQuickItem, "localEventClose")
                close_left = close.mapToScene(QPointF(0, 0)).x()
                body_left = max(covered_left, overlay_left)
                body_right = min(covered_right, close_left)
                self.assertLess(body_left, body_right)
                body_point = QPointF((body_left + body_right) / 2,
                                     surface.mapToScene(QPointF(0, surface.height() / 2)).y())
                self.dock.setProperty("selectedIntegration", "quota")
                QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier,
                                 body_point.toPoint())
                self.settle()
                self.assertEqual(self.dock.property("selectedIntegration"), "quota")

                self.viewport.setProperty("contentX", maximum / 2)
                before_wheel = self.viewport.property("contentX")
                wheel = self.send_wheel(body_point)
                self.assertTrue(wheel.isAccepted())
                self.assertEqual(self.viewport.property("contentX"), before_wheel)

                self.viewport.setProperty("contentX", 0)
                settings_point = settings.mapToScene(
                    QPointF(settings.width() / 2, settings.height() / 2))
                self.assertLess(settings_point.x(), overlay_left)
                QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier,
                                 settings_point.toPoint())
                self.settle()
                self.assertTrue(settings_popup.property("visible"))
                self.evaluate("close()", settings_popup)

                close_point = close.mapToScene(QPointF(close.width() / 2, close.height() / 2))
                QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier,
                                 close_point.toPoint())
                self.settle()
                self.assertIsNone(state.property("current"))

                self.assertTrue(self.evaluate(
                    "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                    "title:'Foco concluído',detail:'Hora de uma pausa!'},2000)", state))
                close.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                self.assertIs(self.window.activeFocusItem(), close)
                QTest.keyClick(self.window, Qt.Key_Escape)
                self.settle()
                self.assertIsNone(state.property("current"))

                self.viewport.setProperty("contentX", maximum)
                idle_point = covered.mapToScene(
                    QPointF(covered.width() / 2, covered.height() / 2))
                self.dock.setProperty("selectedIntegration", "quota")
                QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier,
                                 idle_point.toPoint())
                self.settle()
                self.assertEqual(self.dock.property("selectedIntegration"), "recording")
                self.dock.closeContext()

    def test_tab_order_reaches_center_add_then_fixed_close(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(240, 102, 64)
        settings = self.window.findChild(QQuickItem, "settingsButton")
        state = self.event_state()
        self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state)
        settings.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        visited = []
        for _ in range(20):
            QTest.keyClick(self.window, Qt.Key_Tab)
            self.settle(5)
            focus = self.window.activeFocusItem()
            visited.append(focus.objectName() if focus else "")
            if visited[-1] == "localEventClose":
                break
        self.assertIn("addButton", visited)
        self.assertEqual(visited[-1], "localEventClose")

    def test_close_owned_focus_restores_last_visible_dock_control_for_dismiss_expiry_and_keys(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(320, 102, 64)
        add = self.window.findChild(QQuickItem, "addButton")
        close = self.window.findChild(QQuickItem, "localEventClose")
        settings = self.window.findChild(QQuickItem, "settingsButton")
        state = self.event_state()
        add.forceActiveFocus(Qt.TabFocusReason)
        self.assertTrue(self.evaluate(
            "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
            "title:'Foco concluído',detail:'outside'}, 500)", state))
        settings.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        self.evaluate("dismiss(501)", state)
        self.settle()
        self.assertIs(self.window.activeFocusItem(), settings)
        cases = (("dismiss", None), ("expiry", None), ("escape", Qt.Key_Escape),
                 ("return", Qt.Key_Return), ("enter", Qt.Key_Enter))
        for index, (mode, key) in enumerate(cases):
            with self.subTest(mode=mode):
                add.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                self.assertIs(self.window.activeFocusItem(), add)
                started = 1000 + index * 10000
                self.assertTrue(self.evaluate(
                    "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                    f"title:'Foco concluído',detail:'{mode}'}}, {started})", state))
                self.settle()
                close.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                self.assertIs(self.window.activeFocusItem(), close)
                if mode == "dismiss":
                    self.evaluate(f"dismiss({started + 1})", state)
                elif mode == "expiry":
                    self.evaluate(f"advance({started + 8000})", state)
                else:
                    QTest.keyClick(self.window, key)
                self.settle()
                self.assertIsNone(state.property("current"))
                self.assertIs(self.window.activeFocusItem(), add)

    def submit_live_queue(self, include_second_audio=True):
        import json
        state = self.event_state()
        self.evaluate("nowProvider = function() { return Date.now(); }", state)
        scope = state.property("activeScope")
        generation = state.property("activeContextGeneration")
        targets = ("first", "second") if include_second_audio else ("first",)
        for target in targets:
            event = {"kind": "audio", "action": "volume", "targetId": target,
                     "originScope": scope, "contextGeneration": generation, "value": 50,
                     "title": "Volume · 50%", "detail": target}
            self.assertTrue(self.evaluate(f"submit({json.dumps(event)}, nowMs())", state))
        self.assertTrue(self.evaluate(
            "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
            "title:'Foco concluído',detail:'queued completion'}, nowMs())", state))
        self.assertEqual(state.property("count"), len(targets) + 1)
        return state

    def test_queued_close_focus_survives_dismiss_keys_mouse_and_timer_until_final_drain(self):
        self.config.setProperty("showLocalToasts", True)
        self.config.setProperty("showAudioHud", True)
        self.configure_dock(320, 102, 64)
        add = self.window.findChild(QQuickItem, "addButton")
        close = self.window.findChild(QQuickItem, "localEventClose")
        surface = self.window.findChild(QQuickItem, "localEventSurface")
        cases = (("dismiss", None), ("escape", Qt.Key_Escape),
                 ("return", Qt.Key_Return), ("enter", Qt.Key_Enter),
                 ("mouse", None), ("expiry", None))
        for mode, key in cases:
            with self.subTest(mode=mode):
                self.evaluate("clear()", self.event_state())
                self.settle()
                self.window.requestActivate()
                self.assertTrue(QTest.qWaitForWindowActive(self.window, 1000))
                add.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                state = self.submit_live_queue(include_second_audio=mode != "expiry")
                restores = QSignalSpy(surface.focusRestoreRequested)
                close.forceActiveFocus(Qt.TabFocusReason)
                self.settle()
                self.assertIs(self.window.activeFocusItem(), close)
                while state.property("count") > 1:
                    count = state.property("count")
                    if mode == "expiry":
                        # Let the real current-audio Timer expire; the queued
                        # completion has its own later, still-live deadline.
                        for _ in range(60):
                            if state.property("count") != count:
                                break
                            self.settle(50)
                    elif mode == "dismiss":
                        self.assertTrue(self.evaluate("dismiss()", state))
                    elif mode == "mouse":
                        point = close.mapToScene(QPointF(close.width() / 2, close.height() / 2))
                        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
                    else:
                        QTest.keyClick(self.window, key)
                    self.settle()
                    self.assertEqual(state.property("count"), count - 1)
                    self.assertTrue(surface.isVisible())
                    self.assertTrue(self.evaluate("current.deadline > nowMs()", state))
                    self.assertIs(self.window.activeFocusItem(), close)
                    self.assertEqual(restores.count(), 0)
                self.assertEqual(self.evaluate("current.kind", state), "completion")
                if mode == "expiry":
                    self.assertTrue(self.evaluate("advance(current.deadline)", state))
                elif mode == "mouse":
                    point = close.mapToScene(QPointF(close.width() / 2, close.height() / 2))
                    QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
                elif key is not None:
                    QTest.keyClick(self.window, key)
                else:
                    self.assertTrue(self.evaluate("dismiss()", state))
                self.settle()
                self.assertIsNone(state.property("current"))
                self.assertFalse(surface.isVisible())
                self.assertEqual(restores.count(), 1)
                self.assertIs(self.window.activeFocusItem(), add)

    def test_queue_drain_preserves_unrelated_user_focus_in_an_owned_popup(self):
        self.config.setProperty("showLocalToasts", True)
        self.config.setProperty("showAudioHud", True)
        self.configure_dock(320, 102, 64)
        add = self.window.findChild(QQuickItem, "addButton")
        close = self.window.findChild(QQuickItem, "localEventClose")
        surface = self.window.findChild(QQuickItem, "localEventSurface")
        add.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        state = self.submit_live_queue()
        close.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        self.assertIs(self.window.activeFocusItem(), close)
        popup = self.window.findChild(QObject, "addPopup")
        popup.setProperty("popupType", 0)
        self.evaluate("open()", popup)
        self.settle()
        user_focus = self.window.findChild(QQuickItem, "launcherInput")
        user_focus.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        self.assertIs(self.window.activeFocusItem(), user_focus)
        for key in (Qt.Key_O, Qt.Key_W, Qt.Key_N, Qt.Key_E, Qt.Key_D):
            QTest.keyClick(self.window, key)
        self.assertEqual(user_focus.property("text"), "owned")
        restores = QSignalSpy(surface.focusRestoreRequested)
        for remaining in (2, 1, 0):
            self.assertTrue(self.evaluate("dismiss()", state))
            self.settle()
            self.assertEqual(state.property("count"), remaining)
            self.assertIs(self.window.activeFocusItem(), user_focus)
            self.assertEqual(restores.count(), 0)
        self.evaluate("close()", popup)

    def test_queue_final_drain_does_not_restore_into_an_inactive_owned_window(self):
        self.config.setProperty("showLocalToasts", True)
        self.config.setProperty("showAudioHud", True)
        self.configure_dock(320, 102, 64)
        add = self.window.findChild(QQuickItem, "addButton")
        close = self.window.findChild(QQuickItem, "localEventClose")
        surface = self.window.findChild(QQuickItem, "localEventSurface")
        self.window.requestActivate()
        self.assertTrue(QTest.qWaitForWindowActive(self.window, 1000))
        add.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        state = self.submit_live_queue()
        close.forceActiveFocus(Qt.TabFocusReason)
        self.settle()
        self.assertIs(self.window.activeFocusItem(), close)
        restores = QSignalSpy(surface.focusRestoreRequested)
        other_engine = QQmlApplicationEngine()
        warnings = []
        other_engine.warnings.connect(
            lambda values: warnings.extend(value.toString() for value in values))
        other_engine.load(QUrl.fromLocalFile(str(ROOT / "tests" / "QmlHarness.qml")))
        self.assertTrue(other_engine.rootObjects(), warnings)
        other = other_engine.rootObjects()[0]
        try:
            other.requestActivate()
            self.assertTrue(QTest.qWaitForWindowActive(other, 1000))
            self.assertFalse(self.window.isActive())
            other_focus = other.findChild(QQuickItem, "settingsButton")
            other_focus.forceActiveFocus(Qt.TabFocusReason)
            self.settle()
            for remaining in (2, 1, 0):
                self.assertTrue(self.evaluate("dismiss()", state))
                self.settle()
                self.assertEqual(state.property("count"), remaining)
                self.assertFalse(self.window.isActive())
                self.assertTrue(other.isActive())
                self.assertIs(other.activeFocusItem(), other_focus)
                self.assertIsNot(self.window.activeFocusItem(), add)
                # Real window deactivation relinquishes close-owned focus.
                self.assertEqual(restores.count(), 0)
        finally:
            other.close()
            other.deleteLater()
            QCoreApplication.sendPostedEvents(other, QEvent.DeferredDelete)
            QTest.qWait(10)
            other_engine.deleteLater()
            QCoreApplication.sendPostedEvents(other_engine, QEvent.DeferredDelete)
            self.app.processEvents()
        self.assertEqual(warnings, [])

    def test_task_menu_anchor_uses_real_scrolled_item_coordinates_without_opening_popup(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(240, 102, 64)
        add = self.window.findChild(QQuickItem, "addButton")
        maximum = max(0, self.viewport.property("contentWidth") - self.viewport.width())
        self.assertGreater(maximum, 0)
        data = {"AppName": "Owned", "LauncherUrlWithoutIcon": "applications:owned.desktop",
                "IsLauncher": True}
        self.viewport.setProperty("contentX", 0)
        anchor_before = self.dock.captureTaskMenu(0, data, add)
        expected_before = add.mapToItem(self.dock, QPointF(add.width() / 2, 0)).x()
        self.assertAlmostEqual(anchor_before, expected_before)
        self.viewport.setProperty("contentX", maximum)
        anchor_after = self.dock.captureTaskMenu(0, data, add)
        expected_after = add.mapToItem(self.dock, QPointF(add.width() / 2, 0)).x()
        self.assertAlmostEqual(anchor_after, expected_after)
        self.assertAlmostEqual(anchor_before - anchor_after, maximum)
        self.assertFalse(self.window.findChild(QObject, "taskContextMenu").property("visible"))

    def test_real_tile_hover_indicator_tooltip_and_compact_surface_fit_the_clip(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
        engine.load(QUrl.fromLocalFile(str(ROOT / "tests/LocalEventsHarness.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        tile = window.findChild(QQuickItem, "syntheticTaskTile")
        viewport = window.findChild(QQuickItem, "syntheticTaskViewport")
        surface = window.findChild(QQuickItem, "syntheticEventSurface")
        def fixture_evaluate(source, target):
            expression = QQmlExpression(engine.rootContext(), target, source)
            value, _ = expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
            return value.toVariant() if hasattr(value, "toVariant") else value
        try:
            self.assertTrue(fixture_evaluate("submit()", window))
            QTest.qWaitForWindowExposed(window, 1000)
            QTest.mouseMove(window, QPointF(5, 5).toPoint())
            QTest.qWait(20)
            point = tile.mapToScene(QPointF(tile.width() / 2, tile.height() / 2))
            QTest.mouseMove(window, point.toPoint())
            QTest.qWait(20)
            self.assertTrue(tile.property("hovered"))
            self.assertAlmostEqual(fixture_evaluate("contentItem.children[0].scale", tile), 1.04)  # Style.motion.hoverScale
            icon_bounds = fixture_evaluate("(function(){const icon=contentItem.children[0]; const extra=(icon.width*icon.scale-icon.width)/2; return [icon.x-extra,icon.x+icon.width+extra];})()", tile)
            self.assertGreaterEqual(icon_bounds[0], 0)
            self.assertLessEqual(icon_bounds[1], tile.width())
            self.assertTrue(fixture_evaluate("contentItem.children.find(item => item.objectName === 'tileIndicator').visible", tile))
            tooltip = tile.findChild(QObject, "tileTooltipText")
            self.assertIsNotNone(tooltip)
            self.assertTrue(fixture_evaluate("textFormat === 0", tooltip))
            interface = QAccessible.queryAccessibleInterface(tile)
            self.assertIsNotNone(interface)
            self.assertEqual(interface.text(QAccessible.Text.Name), tile.property("tooltip"))
            self.assertEqual(surface.width(), 58)
            self.assertEqual(surface.property("accessibleName"), "Foco concluído. Hora de uma pausa!")
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(window, QEvent.DeferredDelete)
            QTest.qWait(10)
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)
            self.app.processEvents()
        self.assertEqual(warnings, [])

    def test_settled_product_captures_are_written_after_motion_completes(self):
        output = OWNED / "captures"
        output.mkdir(parents=True, exist_ok=True)
        output.chmod(0o700)
        self.config.setProperty("showLocalToasts", True)
        self.evaluate("appearance.begin(); appearance.setToken('reducedMotion', true)")
        self.assertEqual(self.dock.property("motion"), 0)
        state = self.event_state()
        self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state)
        for width, height, icon_size in ((240, 102, 64), (320, 102, 32), (640, 102, 64)):
            self.configure_dock(width, height, icon_size)
            self.window.setWidth(width + 40)
            self.window.setHeight(height + 40)
            QTest.qWait(500)
            screen = self.window.screen() or self.app.primaryScreen()
            image = screen.grabWindow(self.window.winId())
            self.assertFalse(image.isNull())
            QTest.qWait(100)
            stable = screen.grabWindow(self.window.winId())
            self.assertEqual(image.toImage(), stable.toImage())
            path = output / f"product-{width}x{height}-icon{icon_size}.png"
            self.assertTrue(stable.save(str(path)))
            self.assertGreater(path.stat().st_size, 0)


class EventIslandTests(unittest.TestCase):
    """The island capsule drawn alone, as the panel's top-center window shows it."""

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(
            lambda warnings: self.warnings.extend(warning.toString() for warning in warnings)
        )
        self.engine.load(QUrl.fromLocalFile(str(ROOT / "tests" / "EventIslandHarness.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.island = self.window.findChild(QQuickItem, "eventIsland")
        self.state = self.window.findChild(QObject, "islandEventState")
        self.rules = self.window.findChild(QObject, "islandState")
        self.media = self.window.findChild(QObject, "islandMediaFixture")
        self.timer = self.window.findChild(QObject, "islandTimerFixture")
        self.capsule = self.window.findChild(QQuickItem, "eventIslandCapsule")
        QTest.qWait(30)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        APP.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target):
        expression = QQmlExpression(self.engine.rootContext(), target, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def item(self, name):
        return self.window.findChild(QQuickItem, name)

    def submit(self, event):
        import json
        self.assertTrue(self.evaluate(f"submit({json.dumps(event)}, Date.now())", self.state))
        QTest.qWait(60)

    @staticmethod
    def audio(action, value, title, detail="Alto-falantes sintéticos"):
        return {"kind": "audio", "action": action, "targetId": "speakers", "originScope": "profile:work",
                "contextGeneration": 2, "value": value, "title": title, "detail": detail}

    def test_idle_island_is_hidden_and_keeps_a_fixed_size_in_the_dialog_fallback(self):
        # Outside Wayland, Plasma's Dialog keeps its first size.
        self.island.setProperty("fixedSize", True)
        QTest.qWait(30)
        self.assertFalse(self.island.property("hasEvent"))
        self.assertFalse(self.island.property("showing"))
        self.assertEqual(self.capsule.property("opacity"), 0)
        self.assertEqual(self.island.width(), 350)
        # Plasma's Dialog keeps its main item's first size: an idle island must
        # already be tall enough for a title and a detail line.
        idle_height = self.island.property("implicitHeight")
        self.submit({"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                     "title": "Pausa concluída", "detail": "Pronto para focar?"})
        self.assertEqual(self.island.property("implicitHeight"), idle_height)
        self.assertLessEqual(self.capsule.height(), idle_height)
        self.assertTrue(self.item("eventIslandDetail").isVisible())
        self.evaluate("clear()", self.state)
        self.submit(self.audio("volume", 40, "Volume · 40%"))
        self.assertEqual(self.island.property("implicitHeight"), idle_height)
        self.assertLessEqual(self.capsule.height(), idle_height)

    def test_completion_shows_icon_title_and_detail_as_plain_text(self):
        self.submit({"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                     "title": "<b>Foco concluído</b>", "detail": "Hora de uma pausa!"})
        self.assertTrue(self.island.property("showing"))
        self.assertEqual(self.capsule.property("opacity"), 1)
        self.assertEqual(self.item("eventIslandIcon").property("name"), "chronometer-symbolic")
        title = self.item("eventIslandTitle")
        self.assertEqual(title.property("text"), "<b>Foco concluído</b>")
        self.assertEqual(self.evaluate("textFormat", title), 0)  # Text.PlainText
        self.assertTrue(self.item("eventIslandDetail").isVisible())
        self.assertFalse(self.item("eventIslandLevel").isVisible())
        # In the layer-shell window the item is only as large as the capsule.
        self.assertEqual(self.island.width(), self.capsule.width())
        self.assertLessEqual(self.capsule.width(), 350)
        self.assertEqual(self.capsule.property("radius"), self.capsule.height() / 2)

    def test_volume_shows_a_level_bar_and_the_level_icon(self):
        self.submit(self.audio("volume", 40, "Volume · 40%"))
        level = self.item("eventIslandLevel")
        fill = self.item("eventIslandLevelFill")
        self.assertTrue(level.isVisible())
        self.assertAlmostEqual(fill.width(), level.width() * 0.4, places=3)
        self.assertFalse(self.item("eventIslandDetail").isVisible())
        self.assertEqual(self.item("eventIslandIcon").property("name"), "audio-volume-medium-symbolic")
        self.submit(self.audio("volume", 0, "Volume · 0%"))
        self.assertEqual(self.item("eventIslandIcon").property("name"), "audio-volume-muted-symbolic")
        self.assertEqual(fill.width(), 0)

    def test_mute_and_output_use_their_own_icons_without_a_level(self):
        self.submit(self.audio("mute", True, "Som silenciado"))
        self.assertEqual(self.item("eventIslandIcon").property("name"), "audio-volume-muted-symbolic")
        self.assertFalse(self.item("eventIslandLevel").isVisible())
        self.evaluate("clear()", self.state)
        self.submit(self.audio("default-output", "speakers", "Saída de áudio alterada"))
        self.assertEqual(self.item("eventIslandIcon").property("name"), "audio-speakers-symbolic")

    def test_long_text_stays_inside_the_island(self):
        self.submit({"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                     "title": "Foco " * 19, "detail": "Pausa " * 26})
        self.assertLessEqual(self.capsule.width(), self.island.width())
        title = self.item("eventIslandTitle")
        self.assertTrue(title.property("truncated"))

    def test_dismissal_hides_the_island_and_keeps_the_last_text_while_fading(self):
        self.submit({"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                     "title": "Pausa concluída", "detail": "Pronto para focar?"})
        self.assertTrue(self.evaluate("dismiss()", self.state))
        QTest.qWait(60)
        self.assertFalse(self.island.property("hasEvent"))
        self.assertFalse(self.island.property("showing"))
        self.assertEqual(self.item("eventIslandTitle").property("text"), "Pausa concluída")

    def live(self, **values):
        values.setdefault("activitiesEnabled", True)
        for key, value in values.items():
            self.rules.setProperty(key, value)
        QTest.qWait(60)

    def click(self, name, x=None, y=None):
        item = self.item(name)
        point = item.mapToScene(QPointF(item.width() / 2 if x is None else x,
                                        item.height() / 2 if y is None else y))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())
        QTest.qWait(60)

    def test_live_activities_stay_off_until_enabled(self):
        self.live(activitiesEnabled=False, mediaPlaying=True, mediaTitle="Faixa sintética")
        self.assertEqual(self.rules.property("mode"), "idle")
        self.assertFalse(self.island.property("showing"))
        self.live(activitiesEnabled=True)
        self.assertEqual(self.rules.property("mode"), "compact")
        self.assertTrue(self.island.property("showing"))
        self.assertTrue(self.item("islandCompact").isVisible())
        self.assertEqual(self.item("islandCompactText").property("text"), "Faixa sintética")
        self.assertTrue(self.item("islandBars").isVisible())
        self.assertFalse(self.item("islandPausedMark").isVisible())
        # Compact fits inside the menu bar and the window is just the capsule.
        self.assertEqual(self.capsule.height(), self.island.property("compactHeight"))
        self.assertEqual(self.island.height(), self.capsule.height())
        self.assertEqual(self.island.width(), self.capsule.width())
        self.assertLess(self.capsule.width(), 350)
        self.assertEqual(self.capsule.property("radius"), self.capsule.height() / 2)

    def test_timer_outranks_music_and_shows_the_time_left(self):
        self.live(mediaPlaying=True, mediaTitle="Faixa sintética", timerRunning=True, timerSecondsLeft=754)
        self.assertEqual(self.evaluate("primary.kind", self.rules), "timer")
        self.assertEqual(self.item("islandCompactText").property("text"), "Foco")
        self.assertEqual(self.item("islandClock").property("text"), "12:34")
        self.assertFalse(self.item("islandBars").isVisible())
        self.assertIn("12:34 restantes", self.evaluate("summary()", self.island))
        self.live(timerBreak=True, timerSecondsLeft=3605)
        self.assertEqual(self.item("islandCompactText").property("text"), "Pausa")
        self.assertEqual(self.item("islandClock").property("text"), "1:00:05")

    def test_privacy_takes_the_capsule_only_when_nothing_else_is_live(self):
        self.live(microphoneInUse=True)
        self.assertEqual(self.evaluate("primary.kind", self.rules), "privacy")
        self.assertEqual(self.item("islandCompactText").property("text"), "Microfone em uso")
        self.assertEqual(self.item("islandCompactIcon").property("name"), "audio-input-microphone-symbolic")
        self.assertFalse(self.item("islandPrivacyMicrophone").isVisible())
        self.live(cameraInUse=True)
        self.assertEqual(self.item("islandCompactText").property("text"), "Microfone e câmera em uso")
        self.live(mediaPlaying=True, mediaTitle="Faixa sintética")
        self.assertEqual(self.evaluate("primary.kind", self.rules), "media")
        self.assertEqual(self.item("islandCompactText").property("text"), "Faixa sintética")
        self.assertTrue(self.item("islandPrivacyMicrophone").isVisible())
        self.assertTrue(self.item("islandPrivacyCamera").isVisible())

    def test_click_expands_music_and_its_controls_reach_the_player(self):
        self.live(mediaPlaying=True, mediaTitle="Faixa sintética", mediaArtist="Artista sintético")
        compact_width = self.capsule.width()
        self.click("islandTapArea")
        self.assertEqual(self.rules.property("mode"), "expanded")
        self.assertTrue(self.item("islandExpanded").isVisible())
        self.assertFalse(self.item("islandCompact").isVisible())
        self.assertEqual(self.capsule.width(), 350)
        self.assertGreater(self.capsule.height(), self.island.property("compactHeight") * 3)
        self.assertEqual(self.island.width(), self.capsule.width())
        self.assertEqual(self.item("islandMediaTitle").property("text"), "Faixa sintética")
        self.assertEqual(self.item("islandMediaArtist").property("text"), "Artista sintético")
        self.assertTrue(self.item("islandMediaProgress").isVisible())
        self.assertGreaterEqual(self.media.property("refreshCount"), 1)
        self.assertEqual(self.item("islandPlayPause").property("text"), "Pausar")
        for name, counter in (("islandPrevious", "previousCount"), ("islandPlayPause", "playPauseCount"),
                              ("islandNext", "nextCount"), ("islandRaisePlayer", "raiseCount")):
            self.click(name)
            self.assertEqual(self.media.property(counter), 1, name)
            self.assertEqual(self.rules.property("mode"), "expanded", name)
        # The island never takes keyboard focus.
        self.assertEqual(self.evaluate("focusPolicy", self.item("islandPlayPause")), 0)
        # A click on the capsule's background folds it back; the window follows.
        self.click("islandTapArea", x=self.capsule.width() - 12, y=12)
        self.assertEqual(self.rules.property("mode"), "compact")
        QTest.qWait(60)
        self.assertEqual(self.capsule.width(), compact_width)
        self.assertEqual(self.island.width(), compact_width)

    def test_paused_music_stays_while_expanded_and_for_a_grace_period(self):
        self.live(mediaPlaying=True, mediaTitle="Faixa sintética")
        self.click("islandTapArea")
        self.live(mediaPlaying=False, mediaPaused=True)
        self.assertEqual(self.rules.property("mode"), "expanded")
        self.assertEqual(self.item("islandPlayPause").property("iconName"), "media-playback-start-symbolic")
        self.evaluate("collapse()", self.rules)
        QTest.qWait(60)
        self.assertEqual(self.rules.property("mode"), "compact")
        self.assertTrue(self.item("islandPausedMark").isVisible())
        self.assertFalse(self.item("islandBars").isVisible())
        self.evaluate("heldTimer.triggered()", self.rules)
        QTest.qWait(60)
        self.assertEqual(self.rules.property("mode"), "idle")
        # A stopped player (neither playing nor paused) leaves at once.
        self.live(mediaPaused=False, mediaPlaying=True)
        self.live(mediaPlaying=False)
        self.assertEqual(self.rules.property("mode"), "idle")

    def test_expanded_timer_pauses_and_resets_the_pomodoro(self):
        self.live(timerRunning=True, timerSecondsLeft=90)
        self.click("islandTapArea")
        self.assertEqual(self.item("islandTimerClock").property("text"), "1:30")
        self.assertEqual(self.item("islandTimerPhase").property("text"), "Foco")
        self.click("islandTimerToggle")
        self.click("islandTimerReset")
        self.assertEqual(self.timer.property("toggleCount"), 1)
        self.assertEqual(self.timer.property("resetCount"), 1)
        # Once the timer stops, nothing is live and the island folds away.
        self.live(timerRunning=False)
        self.assertEqual(self.rules.property("mode"), "idle")
        self.assertFalse(self.rules.property("expanded"))

    def test_expanded_privacy_lists_each_device_in_use(self):
        self.live(microphoneInUse=True, cameraInUse=True)
        self.click("islandTapArea")
        self.assertEqual(self.evaluate("children.filter(child => child.objectName === 'islandPrivacyRow'"
                                       " && child.visible).length", self.item("islandExpanded")), 2)

    def test_a_notice_takes_over_and_gives_the_capsule_back(self):
        self.live(mediaPlaying=True, mediaTitle="Faixa sintética")
        self.click("islandTapArea")
        self.submit({"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                     "title": "Pausa concluída", "detail": "Pronto para focar?"})
        self.assertEqual(self.rules.property("mode"), "transient")
        self.assertFalse(self.rules.property("expanded"))
        self.assertTrue(self.item("islandNotice").isVisible())
        self.assertFalse(self.item("islandCompact").isVisible())
        # A click on a notice dismisses it.
        self.click("islandTapArea")
        self.assertIsNone(self.state.property("current"))
        self.assertEqual(self.rules.property("mode"), "compact")
        self.assertTrue(self.item("islandCompact").isVisible())

    def test_battery_notices_show_a_tinted_level_and_their_icon(self):
        self.state.setProperty("powerEnabled", True)
        self.submit({"kind": "power", "action": "charging", "value": 64, "title": "Carregando",
                     "detail": "64% de bateria"})
        self.assertEqual(self.item("eventIslandIcon").property("name"), "battery-060-charging-symbolic")
        self.assertTrue(self.item("eventIslandLevel").isVisible())
        self.assertTrue(self.item("eventIslandDetail").isVisible())
        self.assertAlmostEqual(self.item("eventIslandLevelFill").width(), self.item("eventIslandLevel").width() * 0.64, places=3)
        self.assertEqual(self.item("eventIslandLevelFill").property("color").name(), "#69d7c2")
        self.evaluate("clear()", self.state)
        self.submit({"kind": "power", "action": "low", "value": 10, "title": "Bateria fraca", "detail": "10% restantes"})
        self.assertEqual(self.item("eventIslandIcon").property("name"), "battery-caution-symbolic")
        self.assertEqual(self.item("eventIslandLevelFill").property("color").name(), "#ff8a7a")
        self.evaluate("clear()", self.state)
        self.submit({"kind": "power", "action": "phone-low", "value": 20, "title": "Celular com bateria fraca",
                     "detail": "Celular sintético · 20%"})
        self.assertEqual(self.item("eventIslandIcon").property("name"), "phone-battery-symbolic")
        self.assertEqual(self.item("eventIslandLevelFill").property("color").name(), "#f2b866")

    def test_meeting_keeps_its_title_for_the_expanded_view(self):
        import time
        now = int(time.time() * 1000)
        self.live(nowMs=now, calendarEvents=[{"title": "Reunião sintética", "startMs": now + 4 * 60_000 + 500,
                                              "endMs": now + 34 * 60_000}],
                  mediaPlaying=True, mediaTitle="Faixa sintética")
        self.assertEqual(self.evaluate("primary.kind", self.rules), "meeting")
        self.assertEqual(self.item("islandCompactText").property("text"), "Em 5 min")
        self.assertEqual(self.item("islandCompactIcon").property("name"), "appointment-soon-symbolic")
        self.assertIn("Reunião sintética", self.evaluate("summary()", self.island))
        self.click("islandTapArea")
        self.assertEqual(self.item("islandMeetingTitle").property("text"), "Reunião sintética")
        self.assertIn("Em 5 min", self.item("islandMeetingTime").property("text"))
        self.assertIn(" – ", self.item("islandMeetingTime").property("text"))
        self.live(nowMs=now + 5 * 60_000)
        self.assertEqual(self.item("islandMeetingTime").property("text").split(" · ")[1], "Agora")
        # Past the tail, the music comes back and the expanded view stays on it.
        self.live(nowMs=now + 11 * 60_000)
        self.assertEqual(self.evaluate("primary.kind", self.rules), "media")

    def test_notices_compare_each_battery_reading_with_the_last(self):
        notices = self.window.findChild(QObject, "islandNotices")
        self.state.setProperty("powerEnabled", True)
        notices.setProperty("enabled", True)
        self.evaluate("power = {percent: 40, state: 2}", notices)
        self.assertIsNone(self.state.property("current"))
        self.evaluate("power = {percent: 40, state: 1}", notices)
        QTest.qWait(30)
        current = self.evaluate("current", self.state)
        self.assertEqual((current["action"], current["title"], current["detail"]), ("charging", "Carregando", "40% de bateria"))
        self.evaluate("clear()", self.state)
        self.evaluate("phones = [{id: 'phone-a', name: 'Celular sintético', charge: 21, charging: false}]", notices)
        self.evaluate("phones = [{id: 'phone-a', name: 'Celular sintético', charge: 20, charging: false}]", notices)
        current = self.evaluate("current", self.state)
        self.assertEqual((current["action"], current["detail"]), ("phone-low", "Celular sintético · 20%"))
        # Off forgets the last readings: turning on again raises nothing by itself.
        self.evaluate("clear()", self.state)
        notices.setProperty("enabled", False)
        notices.setProperty("enabled", True)
        self.assertIsNone(self.state.property("current"))

    def test_dialog_fallback_shows_activities_but_never_expands_or_takes_clicks(self):
        self.island.setProperty("fixedSize", True)
        self.island.setProperty("interactive", False)
        self.live(mediaPlaying=True, mediaTitle="Faixa sintética")
        self.assertFalse(self.item("islandTapArea").property("enabled"))
        self.assertTrue(self.evaluate("toggle()", self.rules))
        QTest.qWait(60)
        self.assertEqual(self.island.property("look"), "compact")
        self.assertFalse(self.item("islandExpanded").isVisible())
        self.assertEqual(self.island.width(), 350)
        self.assertLessEqual(self.capsule.height(), self.island.height())


class IslandLogicTests(unittest.TestCase):
    """Island.js on its own, as a plain script."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtQml import QJSEngine
        cls.js = QJSEngine()
        source = (ROOT / "package/contents/code/Island.js").read_text().replace(".pragma library", "")
        result = cls.js.evaluate(source)
        assert not result.isError(), result.toString()

    def call(self, name, *arguments):
        import json
        value = self.js.evaluate(f"JSON.stringify({name}({', '.join(json.dumps(a) for a in arguments)}))")
        self.assertFalse(value.isError(), value.toString())
        return json.loads(value.toString())

    def test_clock(self):
        self.assertEqual(self.call("clock", 0), "0:00")
        self.assertEqual(self.call("clock", 59.9), "0:59")
        self.assertEqual(self.call("clock", 754), "12:34")
        self.assertEqual(self.call("clock", 3605), "1:00:05")
        self.assertEqual(self.call("clock", -3), "0:00")

    def test_activities_are_ranked_and_bounded(self):
        activities = self.call("activities", {
            "timer": {"running": True, "secondsLeft": 61.7, "isBreak": False},
            "media": {"playing": True, "title": "  Faixa\n   sintética ", "artist": "A" * 400,
                      "artUrl": "javascript:alert(1)"},
            "privacy": {"microphone": True, "camera": False}})
        self.assertEqual([entry["kind"] for entry in activities], ["timer", "media"])
        self.assertEqual(activities[0]["secondsLeft"], 61)
        self.assertEqual(activities[1]["title"], "Faixa sintética")
        self.assertEqual(len(activities[1]["artist"]), 256)
        self.assertEqual(activities[1]["artUrl"], "")
        media = self.call("activities", {"media": {"held": True, "artUrl": "https://example.invalid/c.png"}})
        self.assertEqual(media, [{"kind": "media", "priority": 20, "playing": False, "title": "", "artist": "",
                                  "artUrl": "https://example.invalid/c.png"}])
        self.assertEqual(self.call("activities", {"media": {"artUrl": "http://example.invalid/c.png", "playing": True}})[0]["artUrl"], "")
        self.assertEqual(self.call("activities", {"timer": {"running": True, "secondsLeft": "x"}}), [])
        self.assertEqual(self.call("activities", None), [])
        self.assertEqual(self.call("activities", {"privacy": {"camera": True}})[0]["kind"], "privacy")

    def test_next_meeting_window_skips_all_day_and_picks_the_earliest(self):
        now = 1_000_000_000
        minute = 60_000
        events = [{"title": "Dia inteiro", "startMs": now - minute, "endMs": now + 60 * minute, "allDay": True},
                  {"title": "Mais tarde", "startMs": now + 9 * minute, "endMs": now + 30 * minute},
                  {"title": "Logo", "startMs": now + 4 * minute, "endMs": now + 34 * minute},
                  {"title": "Longe", "startMs": now + 11 * minute}]
        self.assertEqual(self.call("nextMeeting", events, now)["title"], "Logo")
        self.assertIsNone(self.call("nextMeeting", [events[3]], now))
        self.assertEqual(self.call("nextMeeting", [{"title": "Começou", "startMs": now - 4 * minute}], now)["title"], "Começou")
        self.assertIsNone(self.call("nextMeeting", [{"title": "Antiga", "startMs": now - 6 * minute}], now))
        self.assertIsNone(self.call("nextMeeting", None, now))
        meeting = self.call("activities", {"meeting": {"title": "Logo", "startMs": now + 4 * minute + 1, "nowMs": now},
                                           "timer": {"running": True, "secondsLeft": 60}})
        self.assertEqual([entry["kind"] for entry in meeting], ["meeting", "timer"])
        self.assertEqual(meeting[0]["minutes"], 5)

    def test_power_notices_fire_on_plug_in_and_each_low_level_once(self):
        self.assertIsNone(self.call("powerNotice", None, {"percent": 50, "state": 1}))
        self.assertIsNone(self.call("powerNotice", {"percent": 50, "state": 0}, {"percent": 50, "state": 1}))
        self.assertEqual(self.call("powerNotice", {"percent": 50, "state": 2}, {"percent": 50.4, "state": 1}),
                         {"action": "charging", "value": 50})
        self.assertEqual(self.call("powerNotice", {"percent": 50, "state": 2}, {"percent": 50, "state": 5})["action"], "charging")
        self.assertIsNone(self.call("powerNotice", {"percent": 50, "state": 1}, {"percent": 51, "state": 4}))
        self.assertEqual(self.call("powerNotice", {"percent": 21, "state": 2}, {"percent": 20, "state": 2}),
                         {"action": "low", "value": 20})
        self.assertIsNone(self.call("powerNotice", {"percent": 20, "state": 2}, {"percent": 19, "state": 2}))
        self.assertEqual(self.call("powerNotice", {"percent": 11, "state": 2}, {"percent": 10, "state": 2})["value"], 10)
        self.assertIsNone(self.call("powerNotice", {"percent": 30, "state": 2}, {"percent": 130, "state": 2}))
        self.assertEqual(self.call("phoneNotice", {"charge": 16, "charging": False}, {"charge": 15, "charging": False}),
                         None)
        self.assertEqual(self.call("phoneNotice", {"charge": 21, "charging": False}, {"charge": 20, "charging": False}),
                         {"action": "phone-low", "value": 20})
        self.assertIsNone(self.call("phoneNotice", {"charge": 21, "charging": False}, {"charge": 20, "charging": True}))
        self.assertIsNone(self.call("phoneNotice", None, {"charge": 5, "charging": False}))

    def test_mode(self):
        live = [{"kind": "media"}]
        self.assertEqual(self.call("mode", True, live, True), "transient")
        self.assertEqual(self.call("mode", False, live, True), "expanded")
        self.assertEqual(self.call("mode", False, live, False), "compact")
        self.assertEqual(self.call("mode", False, [], True), "idle")


if __name__ == "__main__":
    unittest.main()
