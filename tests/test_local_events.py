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

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QUrl, Qt
from PySide6.QtGui import QAccessible, QGuiApplication
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
        before = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(), focused,
                  self.viewport.x(), self.viewport.width(), self.viewport.property("contentWidth"),
                  self.viewport.property("contentX"), self.evaluate("eventSlotWidth"))
        state = self.event_state()
        accepted = self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state)
        self.assertTrue(accepted)
        self.settle()
        during = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                  self.window.activeFocusItem(), self.viewport.x(), self.viewport.width(),
                  self.viewport.property("contentWidth"), self.viewport.property("contentX"),
                  self.evaluate("eventSlotWidth"))
        self.assertEqual(during, before)
        surface = self.window.findChild(QQuickItem, "localEventSurface")
        one_line = self.window.findChild(QQuickItem, "localEventOneLine")
        self.assertEqual(surface.width(), 90)
        self.assertTrue(one_line.property("truncated"))
        self.assertEqual(surface.property("accessibleName"), "Foco concluído. Hora de uma pausa!")
        self.assertTrue(self.evaluate("textFormat === 0", one_line))
        self.assertTrue(self.evaluate("advance(9000)", state))
        self.settle()
        after = (self.dock.width(), self.dock.height(), self.dock.implicitWidth(),
                 self.window.activeFocusItem(), self.viewport.x(), self.viewport.width(),
                 self.viewport.property("contentWidth"), self.viewport.property("contentX"),
                 self.evaluate("eventSlotWidth"))
        self.assertEqual(after, before)
        self.assertFalse(surface.isVisible())

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

    def test_deliberate_focus_reveals_add_without_event_driven_scrolling(self):
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

    def test_click_outside_overlay_reaches_dock_and_close_receives_real_click(self):
        self.config.setProperty("showLocalToasts", True)
        self.configure_dock(640, 102, 64)
        settings = self.window.findChild(QQuickItem, "settingsButton")
        popup = self.window.findChild(QObject, "settingsPopup")
        popup.setProperty("popupType", 0)
        maximum = max(0, self.viewport.property("contentWidth") - self.viewport.width())
        self.viewport.setProperty("contentX", maximum)
        state = self.event_state()
        self.evaluate("submit({kind:'completion',key:'pomodoro:completion',scope:'global',title:'Foco concluído',detail:'Hora de uma pausa!'},1000)", state)
        surface = self.window.findChild(QQuickItem, "localEventSurface")
        settings_point = settings.mapToScene(QPointF(settings.width() / 2, settings.height() / 2))
        self.assertLess(settings_point.x(), surface.mapToScene(QPointF(0, 0)).x())
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, settings_point.toPoint())
        self.settle()
        self.assertTrue(popup.property("visible"))
        self.assertEqual(self.viewport.property("contentX"), maximum)
        self.evaluate("close()", popup)

        close = self.window.findChild(QQuickItem, "localEventClose")
        close_point = close.mapToScene(QPointF(close.width() / 2, close.height() / 2))
        self.assertGreaterEqual(close_point.x(), surface.mapToScene(QPointF(0, 0)).x())
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, close_point.toPoint())
        self.settle()
        self.assertIsNone(state.property("current"))
        self.assertEqual(self.viewport.property("contentX"), maximum)

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
            self.assertAlmostEqual(fixture_evaluate("contentItem.children[0].scale", tile), 1.12)
            icon_bounds = fixture_evaluate("(function(){const icon=contentItem.children[0]; const extra=(icon.width*icon.scale-icon.width)/2; return [icon.x-extra,icon.x+icon.width+extra];})()", tile)
            self.assertGreaterEqual(icon_bounds[0], 0)
            self.assertLessEqual(icon_bounds[1], tile.width())
            self.assertTrue(fixture_evaluate("contentItem.children.find(item => item.height === 3).visible", tile))
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


if __name__ == "__main__":
    unittest.main()
