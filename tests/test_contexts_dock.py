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
    "AT_SPI_BUS_ADDRESS": "unix:path=" + str(Path(_PRIVATE.name, "absent-atspi-bus")),
    "NO_AT_BRIDGE": "1",
    "QT_ACCESSIBILITY": "0",
    "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "0",
})
assert os.environ.get("HOME") == _ORIGINAL_HOME
assert os.environ.get("CODEX_HOME") == _ORIGINAL_CODEX_HOME

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest, QSignalSpy


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

    def accessible_press(self, control):
        expression = QQmlExpression(QQmlEngine.contextForObject(control), control, "Accessible.pressAction()")
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())

    def configuration_snapshot(self):
        meta = self.config.metaObject()
        names = [meta.property(index).name() for index in range(meta.propertyOffset(), meta.propertyCount())]
        return {name: self.evaluate("JSON.stringify(configuration[" + json.dumps(name) + "])") for name in names}

    def test_automatic_policy_changes_only_its_key_and_keeps_automatic_off(self):
        self.initialize_profiles()
        self.open_contexts()
        selector = self.window.findChild(QQuickItem, "autoContextPolicy")
        self.assertIsNotNone(selector, "The explicit automatic context policy control is missing")
        before = self.configuration_snapshot()
        policy_writes = QSignalSpy(self.config.autoContextPolicyChanged)
        profile_writes = QSignalSpy(self.config.profilesJSONChanged)
        context_writes = QSignalSpy(self.config.contextsJSONChanged)
        timer_writes = [QSignalSpy(getattr(self.config, name + "Changed")) for name in (
            "focusMinutes", "breakMinutes", "timerDeadline", "timerRemaining", "timerBreak", "completedFocus")]
        self.accessible_press(selector)
        QTest.qWait(150)
        self.assertTrue(self.evaluate("popup.visible", selector))
        option = self.evaluate("popup.contentItem.itemAtIndex(1)", selector)
        self.assertIsNotNone(option)
        self.accessible_press(option)
        QTest.qWait(150)
        self.assertEqual(self.config.property("autoContextPolicy"), "desktop")
        self.assertEqual(policy_writes.count(), 1)
        self.assertEqual(profile_writes.count(), 0)
        self.assertEqual(context_writes.count(), 0)
        self.assertTrue(all(spy.isValid() and spy.count() == 0 for spy in timer_writes))
        self.assertFalse(self.config.property("autoContextEnabled"))
        self.assertFalse(self.evaluate("popup.visible", selector))
        expected = dict(before, autoContextPolicy=json.dumps("desktop"))
        self.assertEqual(self.configuration_snapshot(), expected)

    def wait_profile(self, expected):
        state = self.evaluate("profiles")
        changed = QSignalSpy(state.activeProfileIdChanged)
        if state.property("activeProfileId") != expected:
            self.assertTrue(changed.wait(1000), "No deferred profile selection was observed")
        self.assertEqual(state.property("activeProfileId"), expected)

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

    def test_automatic_profiles_require_opt_in_and_wait_for_settings_to_close(self):
        self.initialize_profiles()
        self.set_snapshot()
        automation = self.window.findChild(QObject, "dockAutoContextProfiles")
        self.assertIsNotNone(automation)
        self.assertFalse(automation.property("enabled"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "legacy")
        self.assertTrue(self.evaluate("autoContextProfiles.setDefaultProfile('work')"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "legacy")
        self.open_contexts()
        checkbox = self.window.findChild(QQuickItem, "autoContextEnabled")
        self.assertIsNotNone(checkbox)
        checkbox.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(checkbox.window(), Qt.Key_Space)
        QTest.qWait(40)
        self.assertTrue(automation.property("enabled"))
        self.assertTrue(self.popup.property("visible"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "legacy")
        self.popup.close()
        self.wait_profile("work")
        self.assertFalse(automation.property("manualOverride"))
        self.assertFalse(self.dock.property("nativeContextSourceLoaded"))
        self.assertFalse(self.dock.property("nativeDesktopSwitchBackendLoaded"))

    def test_automatic_default_selector_mouse_and_keyboard_preserve_profile(self):
        for mouse_open in (False, True):
            with self.subTest(mouse_open=mouse_open):
                if mouse_open:
                    self.dispose()
                    self.create()
                self.initialize_profiles()
                self.assertTrue(self.evaluate("autoContextProfiles.setDefaultProfile('work')"))
                self.open_contexts()
                selector = self.window.findChild(QQuickItem, "autoContextDefaultProfile")
                before = self.config.property("profilesJSON")
                selector.forceActiveFocus(Qt.TabFocusReason)
                if mouse_open:
                    point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2)).toPoint()
                    QTest.mouseClick(selector.window(), Qt.LeftButton, Qt.NoModifier, point)
                    QTest.qWait(150)
                    self.assertTrue(self.evaluate("popup.opened", selector))
                QTest.keyClick(selector.window(), Qt.Key_Down)
                QTest.keyClick(selector.window(), Qt.Key_Return)
                QTest.qWait(150)
                self.assertEqual(self.config.property("autoContextDefaultProfile"), "personal")
                self.assertFalse(self.evaluate("popup.visible", selector))
                self.assertFalse(self.config.property("autoContextEnabled"))
                self.assertEqual(self.config.property("profilesJSON"), before)
                QTest.keyClick(selector.window(), Qt.Key_Tab)
                self.assertTrue(self.window.findChild(QQuickItem, "autoContextPolicy").property("activeFocus"))
                QTest.keyClick(selector.window(), Qt.Key_Tab)
                self.assertTrue(self.window.findChild(QQuickItem, "autoContextEnabled").property("activeFocus"))

    def test_automatic_policy_keyboard_mouse_escape_and_focus_order(self):
        for mouse_open in (False, True):
            with self.subTest(mouse_open=mouse_open):
                if mouse_open:
                    self.dispose()
                    self.create()
                self.initialize_profiles()
                self.assertTrue(self.evaluate("autoContextProfiles.setDefaultProfile('work')"))
                self.open_contexts()
                selector = self.window.findChild(QQuickItem, "autoContextPolicy")
                before = self.configuration_snapshot()
                selector.forceActiveFocus(Qt.TabFocusReason)
                if mouse_open:
                    point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2)).toPoint()
                    QTest.mouseClick(selector.window(), Qt.LeftButton, Qt.NoModifier, point)
                    QTest.qWait(150)
                    self.assertTrue(self.evaluate("popup.opened", selector))
                QTest.keyClick(selector.window(), Qt.Key_Down)
                QTest.keyClick(selector.window(), Qt.Key_Return)
                QTest.qWait(150)
                self.assertEqual(self.config.property("autoContextPolicy"), "desktop")
                self.assertFalse(self.evaluate("popup.visible", selector))
                self.assertEqual(self.configuration_snapshot(), dict(before, autoContextPolicy=json.dumps("desktop")))
                QTest.keyClick(selector.window(), Qt.Key_Tab)
                self.assertTrue(self.window.findChild(QQuickItem, "autoContextEnabled").property("activeFocus"))
                QTest.keyClick(selector.window(), Qt.Key_Backtab)
                self.assertTrue(selector.property("activeFocus"))
                self.accessible_press(selector)
                QTest.qWait(150)
                QTest.keyClick(selector.window(), Qt.Key_Escape)
                QTest.qWait(150)
                self.assertFalse(self.evaluate("popup.visible", selector))
                self.assertTrue(self.popup.property("visible"))
                self.assertTrue(selector.property("activeFocus"))
                self.assertEqual(self.config.property("autoContextPolicy"), "desktop")
                point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2)).toPoint()
                QTest.mouseClick(selector.window(), Qt.LeftButton, Qt.NoModifier, point)
                QTest.qWait(150)
                option = self.evaluate("popup.contentItem.itemAtIndex(0)", selector)
                self.assertIsNotNone(option)
                visible_width = min(option.width(), self.evaluate("popup.contentItem.width", selector))
                point = option.mapToScene(QPointF(visible_width / 2, option.height() / 2)).toPoint()
                QTest.mouseClick(selector.window(), Qt.LeftButton, Qt.NoModifier, point)
                QTest.qWait(150)
                self.assertFalse(self.evaluate("popup.visible", selector))
                self.assertEqual(self.configuration_snapshot(), before)

    def test_automatic_policy_repairs_unknown_with_invalid_documents_while_off(self):
        raw = '{"formatVersion":"future","owned":true}'
        self.dispose()
        self.create(contexts_json=raw, profiles_json=raw)
        self.config.setProperty("autoContextPolicy", "future")
        self.open_contexts()
        selector = self.window.findChild(QQuickItem, "autoContextPolicy")
        self.assertTrue(selector.property("enabled"))
        self.assertEqual(selector.property("currentIndex"), -1)
        self.assertEqual(selector.property("displayText"), "Escolha uma opção")
        self.assertFalse(self.window.findChild(QQuickItem, "autoContextEnabled").property("enabled"))
        before = self.configuration_snapshot()
        self.accessible_press(selector)
        QTest.qWait(150)
        option = self.evaluate("popup.contentItem.itemAtIndex(1)", selector)
        self.assertIsNotNone(option)
        self.accessible_press(option)
        QTest.qWait(150)
        self.assertEqual(self.configuration_snapshot(), dict(before, autoContextPolicy=json.dumps("desktop")))
        self.assertTrue(self.evaluate("autoContextProfiles.policyValid"))
        self.assertFalse(self.config.property("autoContextEnabled"))

    def test_automatic_desktop_policy_explains_activity_bindings_are_preserved_and_ignored(self):
        self.initialize_profiles()
        self.open_contexts()
        explanation = self.window.findChild(QQuickItem, "contextBindingsExplanation")
        self.assertIsNotNone(explanation)
        self.assertIn("Activity tem prioridade", explanation.property("text"))
        selector = self.window.findChild(QQuickItem, "autoContextPolicy")
        self.accessible_press(selector)
        QTest.qWait(150)
        self.accessible_press(self.evaluate("popup.contentItem.itemAtIndex(1)", selector))
        QTest.qWait(150)
        text = explanation.property("text")
        self.assertIn("preservadas", text)
        self.assertIn("ignoradas", text)
        self.assertNotIn("Activity tem prioridade", text)

    def test_automatic_policy_press_ignores_closed_options_and_hidden_selector(self):
        self.initialize_profiles()
        self.open_contexts()
        selector = self.window.findChild(QQuickItem, "autoContextPolicy")
        other = self.window.findChild(QQuickItem, "autoContextDefaultProfile")
        before = self.configuration_snapshot()
        other.forceActiveFocus(Qt.TabFocusReason)
        self.accessible_press(selector)
        QTest.qWait(150)
        self.assertTrue(selector.property("activeFocus"))
        option = self.evaluate("popup.contentItem.itemAtIndex(1)", selector)
        self.assertIsNotNone(option)
        self.accessible_press(selector)
        QTest.qWait(150)
        self.accessible_press(option)
        other.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(40)
        self.assertTrue(other.property("activeFocus"))
        self.assertFalse(self.evaluate("popup.visible", selector))
        self.window.findChild(QQuickItem, "settingsTabs").setProperty("currentIndex", 0)
        self.accessible_press(selector)
        self.accessible_press(option)
        QTest.qWait(40)
        self.assertFalse(self.evaluate("popup.visible", selector))
        self.assertEqual(self.configuration_snapshot(), before)

    def test_automatic_policy_waits_for_settings_and_preserves_newer_manual_ui_choice(self):
        self.enable_automatic_bindings()
        self.open_contexts()
        selector = self.window.findChild(QQuickItem, "autoContextPolicy")
        before = json.loads(self.config.property("profilesJSON"))
        contexts_raw = self.config.property("contextsJSON")
        timer = [self.config.property(name) for name in (
            "focusMinutes", "breakMinutes", "timerDeadline", "timerRemaining", "timerBreak", "completedFocus")]
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.accessible_press(selector)
        QTest.qWait(150)
        self.accessible_press(self.evaluate("popup.contentItem.itemAtIndex(1)", selector))
        QTest.qWait(150)
        self.assertEqual(self.config.property("autoContextPolicy"), "desktop")
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        self.assertEqual(writes.count(), 0)
        self.window.findChild(QQuickItem, "settingsTabs").setProperty("currentIndex", 2)
        manual = self.window.findChild(QQuickItem, "profileSelector")
        self.accessible_press(manual)
        QTest.qWait(150)
        self.accessible_press(self.evaluate("popup.contentItem.itemAtIndex(3)", manual))
        QTest.qWait(150)
        use = self.window.findChild(QQuickItem, "profileUse")
        use.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "games")
        self.assertTrue(self.evaluate("autoContextProfiles.manualOverride"))
        self.popup.close()
        QTest.qWait(150)
        self.set_snapshot(activity_id="a2")
        QTest.qWait(40)
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "games")
        self.assertEqual(writes.count(), 1)
        expected = dict(before, activeProfileId="games")
        self.assertEqual(json.loads(self.config.property("profilesJSON")), expected)
        self.assertEqual(self.config.property("contextsJSON"), contexts_raw)
        self.assertEqual([self.config.property(name) for name in (
            "focusMinutes", "breakMinutes", "timerDeadline", "timerRemaining", "timerBreak", "completedFocus")], timer)

    def test_automatic_policy_focus_is_revealed_at_narrow_widths(self):
        self.initialize_profiles()
        controls = self.open_contexts()
        selector = self.window.findChild(QQuickItem, "autoContextPolicy")
        for width in (350, 420):
            with self.subTest(width=width):
                self.popup.setProperty("width", width)
                self.popup.setProperty("heightBudget", 420)
                self.window.findChild(QQuickItem, "autoContextHelpToggle").setProperty("checked", True)
                self.window.findChild(QQuickItem, "desktopBind").forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(40)
                selector.forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(100)
                viewport = controls.property("contentItem")
                point = selector.mapToItem(viewport, QPointF(0, 0))
                self.assertGreaterEqual(point.x(), 0)
                self.assertGreaterEqual(point.y(), 2, "The policy focus ring is clipped above the viewport")
                self.assertLessEqual(point.x() + selector.width(), viewport.width() + 1)
                self.assertLessEqual(point.y() + selector.height() + 2, viewport.height() + 1)
                self.assertTrue(selector.property("activeFocus"))

    def test_automatic_desktop_policy_uses_public_enable_with_activity_unavailable(self):
        self.initialize_profiles()
        self.assertTrue(self.evaluate("profiles.select('games',profiles.activeProfileId,profiles.revision)"))
        self.evaluate("contextSnapshot=({outputName:'Fixture',activity:{status:'unavailable',currentId:'',ids:[],names:[]},"
            "desktop:{status:'ready',currentId:'d1',ids:['d1'],names:['Área 1']}})", self.window)
        self.config.setProperty("contextsJSON", json.dumps({
            "formatVersion": "0.1-experimental", "activityBindings": [],
            "desktopBindings": [{"contextId": "d1", "lastKnownName": "Área 1", "profileId": "work"}],
        }))
        self.assertTrue(self.evaluate("autoContextProfiles.setDefaultProfile('personal')"))
        before = json.loads(self.config.property("profilesJSON"))
        contexts_raw = self.config.property("contextsJSON")
        self.open_contexts()
        selector = self.window.findChild(QQuickItem, "autoContextPolicy")
        self.accessible_press(selector)
        QTest.qWait(150)
        self.accessible_press(self.evaluate("popup.contentItem.itemAtIndex(1)", selector))
        QTest.qWait(150)
        enabled = self.window.findChild(QQuickItem, "autoContextEnabled")
        enabled.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        self.assertTrue(self.config.property("autoContextEnabled"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "games")
        self.popup.close()
        self.wait_profile("work")
        self.assertEqual(json.loads(self.config.property("profilesJSON")), dict(before, activeProfileId="work"))
        self.assertEqual(self.config.property("contextsJSON"), contexts_raw)
        self.open_contexts()
        selector.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Up)
        QTest.keyClick(self.window, Qt.Key_Return)
        QTest.qWait(150)
        self.assertEqual(self.config.property("autoContextPolicy"), "activity-desktop")
        self.popup.close()
        QTest.qWait(150)
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        self.assertIn("Activity", self.evaluate("autoContextProfiles.statusText"))

    def test_automatic_resume_retires_focus_when_new_context_hides_it(self):
        self.initialize_profiles()
        self.set_snapshot()
        self.assertTrue(self.evaluate("autoContextProfiles.setDefaultProfile('work'); autoContextProfiles.setEnabled(true)"))
        self.wait_profile("work")
        self.assertTrue(self.evaluate("profiles.select('personal',profiles.activeProfileId,profiles.revision)"))
        self.assertTrue(self.evaluate("autoContextProfiles.manualOverride"))
        self.open_contexts()
        resume = self.window.findChild(QQuickItem, "autoContextResume")
        self.assertTrue(resume.property("visible"))
        resume.forceActiveFocus(Qt.TabFocusReason)
        self.set_snapshot(activity_id="a2")
        self.assertFalse(resume.property("visible"))
        self.assertFalse(resume.property("activeFocus"))
        focused = self.window.activeFocusItem()
        self.assertIsNotNone(focused)
        self.assertTrue(focused.isVisible())
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "personal")
        self.popup.close()
        self.wait_profile("work")

    def enable_automatic_bindings(self):
        self.initialize_profiles()
        self.set_snapshot()
        self.config.setProperty("contextsJSON", json.dumps({
            "formatVersion": "0.1-experimental",
            "activityBindings": [{"contextId": "a1", "lastKnownName": "Foco", "profileId": "work"}],
            "desktopBindings": [{"contextId": "d1", "lastKnownName": "Área 1", "profileId": "personal"}],
        }))
        self.assertTrue(self.evaluate("autoContextProfiles.setDefaultProfile('games'); autoContextProfiles.setEnabled(true)"))
        self.wait_profile("work")

    def test_automatic_waits_for_draft_and_applies_only_latest_context(self):
        self.enable_automatic_bindings()
        self.open_contexts()
        self.evaluate("appearance.setToken('radius', 9); pomodoro.toggle()")
        self.assertTrue(self.evaluate("appearance.dirty"))
        before = self.config.property("profilesJSON")
        draft = self.evaluate("JSON.stringify(appearance.draft)")
        deadline = self.config.property("timerDeadline")
        writes = self.window.property("profileWriteCount")
        self.set_snapshot(activity_id="a2")
        self.set_snapshot(activity_id="a3", desktop_id="d2")
        QTest.qWait(40)
        self.assertEqual(self.config.property("profilesJSON"), before)
        self.assertEqual(self.evaluate("JSON.stringify(appearance.draft)"), draft)
        self.assertTrue(self.popup.property("visible"))
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.popup.close()
        self.wait_profile("games")
        self.assertEqual(self.window.property("profileWriteCount"), writes + 1)
        self.assertEqual(self.config.property("timerDeadline"), deadline)
        self.assertTrue(self.window.property("contextTimerIdentity"))

    def test_automatic_waits_for_audio_request_and_gesture_without_cancelling(self):
        self.enable_automatic_bindings()
        audio = self.window.findChild(QObject, "audioControlState")
        self.evaluate("active=true", audio)
        self.assertTrue(self.evaluate("requestVolume(70)", audio))
        self.set_snapshot(activity_id="a2")
        self.assertEqual(audio.property("pendingKind"), "volume")
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        backend = self.window.findChild(QObject, "dockAudioBackend")
        self.evaluate("snapshot=Object.assign({},snapshot,{outputs:snapshot.outputs.map(output => Object.assign({},output,{volumeRaw:45875}))})", backend)
        self.wait_profile("personal")
        self.assertEqual(audio.property("pendingKind"), "")
        self.assertTrue(self.evaluate("beginVolumeGesture()", audio))
        self.set_snapshot(activity_id="a3", desktop_id="d2")
        self.assertTrue(audio.property("volumeGestureActive"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "personal")
        self.evaluate("endVolumeGesture()", audio)
        self.wait_profile("games")

    def test_automatic_waits_for_fallback_menu_close_callback(self):
        self.enable_automatic_bindings()
        menu = self.window.findChild(QObject, "taskContextMenu")
        self.evaluate("popupType=0;open()", menu)
        QTest.qWait(40)
        witness = []
        menu.closed.connect(lambda: witness.append((menu.property("contextSwitchBusy"), self.evaluate("profiles.activeProfileId"))))
        self.set_snapshot(activity_id="a2")
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        self.evaluate("close()", menu)
        self.wait_profile("personal")
        self.assertEqual(witness, [(True, "work")])
        self.assertFalse(menu.property("contextSwitchBusy"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "personal")

    def test_automatic_help_reveals_group_without_reclaiming_newer_focus(self):
        self.initialize_profiles()
        controls = self.open_contexts()
        self.popup.setProperty("width", 350)
        self.popup.setProperty("heightBudget", 420)
        disclosure = self.window.findChild(QQuickItem, "autoContextHelpToggle")
        group = self.window.findChild(QQuickItem, "autoContextDetailsGroup")
        selector = self.window.findChild(QQuickItem, "autoContextDefaultProfile")
        disclosure.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(100)
        self.assertTrue(disclosure.property("checked"))
        viewport = controls.property("contentItem")
        top = group.mapToItem(viewport, QPointF(0, 0)).y()
        self.assertGreaterEqual(top, -1)
        self.assertLessEqual(top + min(group.height(), viewport.height()), viewport.height() + 1)
        self.assertGreaterEqual(disclosure.mapToItem(viewport, QPointF(0, 0)).y(), 3,
                                "The expanded help clips its disclosure focus ring")
        self.assertTrue(disclosure.property("activeFocus"))
        self.evaluate("checked=false;checked=true", disclosure)
        selector.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(100)
        self.assertTrue(selector.property("activeFocus"))

    def test_automatic_waits_for_pressed_app_drag_without_saving_it(self):
        self.enable_automatic_bindings()
        rows = self.evaluate("taskOrder()")
        if not rows:
            self.skipTest("TaskManager exposes no app tiles in this runtime")
        self.assertTrue(self.evaluate("taskDrag.begin(taskOrder()[0].identity)"))
        self.assertTrue(self.evaluate("taskDrag.pressed && !taskDrag.active"))
        self.set_snapshot(activity_id="a2")
        self.assertTrue(self.evaluate("taskDrag.pressed"))
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        self.evaluate("taskDrag.cancel()")
        self.wait_profile("personal")

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

    def test_desktop_switch_keyboard_selection_and_single_tab_request(self):
        for open_by_mouse in (False, True):
            with self.subTest(open_by_mouse=open_by_mouse):
                if open_by_mouse:
                    self.dispose()
                    self.create()
                self.initialize_profiles()
                self.evaluate("contextSnapshot = ({outputName:'Fixture',activity:{status:'unavailable',currentId:'',ids:[],names:[]},desktop:{status:'ready',currentId:'one',ids:['one','two'],names:['Uma','Outra']}})", self.window)
                self.open_contexts()
                state = self.window.findChild(QObject, "dockDesktopSwitchState")
                backend = self.window.findChild(QObject, "desktopSwitchFixtureBackend")
                selector = self.window.findChild(QQuickItem, "desktopSwitchSelector")
                button = self.window.findChild(QQuickItem, "desktopSwitchButton")
                before = self.evaluate("JSON.stringify([configuration.profilesJSON,configuration.contextsJSON,profiles.activeProfileId,configuration.timerDeadline,appearance.dirty])")
                selector.forceActiveFocus(Qt.TabFocusReason)
                if open_by_mouse:
                    point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2)).toPoint()
                    QTest.mouseClick(selector.window(), Qt.LeftButton, Qt.NoModifier, point)
                    QTest.qWait(150)
                    self.assertTrue(self.evaluate("popup.opened", selector))
                QTest.keyClick(selector.window(), Qt.Key_Down)
                QTest.keyClick(selector.window(), Qt.Key_Return)
                QTest.qWait(150)
                self.assertEqual(state.property("selectedId"), "two")
                self.assertFalse(self.evaluate("popup.visible", selector))
                self.assertEqual(backend.property("calls"), 0)
                QTest.keyClick(selector.window(), Qt.Key_Tab)
                self.assertTrue(button.property("activeFocus"))
                QTest.keyClick(selector.window(), Qt.Key_Space)
                QTest.qWait(10)
                self.assertEqual(backend.property("calls"), 1)
                self.assertEqual(self.evaluate("JSON.stringify([configuration.profilesJSON,configuration.contextsJSON,profiles.activeProfileId,configuration.timerDeadline,appearance.dirty])"), before)

    def test_desktop_switch_popup_mouse_selection_does_not_request(self):
        self.initialize_profiles()
        self.evaluate("contextSnapshot = ({outputName:'Fixture',activity:{status:'unavailable',currentId:'',ids:[],names:[]},desktop:{status:'ready',currentId:'one',ids:['one','two'],names:['Uma','Outra']}})", self.window)
        self.open_contexts()
        selector = self.window.findChild(QQuickItem, "desktopSwitchSelector")
        point = selector.mapToScene(QPointF(selector.width() / 2, selector.height() / 2)).toPoint()
        QTest.mouseClick(selector.window(), Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(150)
        self.assertTrue(self.evaluate("popup.opened", selector))
        position = json.loads(self.evaluate("var choice = popup.contentItem.itemAtIndex(1); var p = choice.mapToItem(null, Math.min(choice.width, popup.contentItem.width) / 2, choice.height / 2); JSON.stringify({x:p.x,y:p.y})", selector))
        point = QPointF(position["x"], position["y"]).toPoint()
        QTest.mouseClick(selector.window(), Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(150)
        self.assertEqual(self.window.findChild(QObject, "dockDesktopSwitchState").property("selectedId"), "two")
        self.assertFalse(self.evaluate("popup.visible", selector))
        self.assertEqual(self.window.findChild(QObject, "desktopSwitchFixtureBackend").property("calls"), 0)

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
