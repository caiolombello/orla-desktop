import json
import os
from pathlib import Path
import time
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "wayland" if os.environ.get("WAYLAND_DISPLAY") else "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl, Qt, QPointF, QCoreApplication, QEvent
from PySide6.QtGui import QAccessible, QAccessibleActionInterface, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest


class ProfilesDockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime = Path(__file__).resolve().parents[1] / ".runtime/profiles-dock"
        runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ProfilesDockHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.config = self.window.findChild(QObject, "configuration")
        self.dock = self.window.findChild(QQuickItem, "dock")
        self.popup = self.window.findChild(QObject, "settingsPopup")
        self.popup.setProperty("popupType", 0)
        self.popup.setProperty("y", 0)
        calendar = self.window.findChild(QQuickItem, "calendarAgenda")
        calendar.setProperty("fixtureEvents", [])
        calendar.setProperty("pimPluginMetadataAvailableOverride", True)
        self.evaluate("integrations.active = false")
        self.window.findChild(QQuickItem, "systemBattery").setProperty("transport", self.window.findChild(QObject, "batteryTransport"))
        QTest.qWait(50)

    def dispose(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
        # Popup/style items can schedule their own deferred cleanup while the
        # root is destroyed. Their incubators must finish before their engine.
        QTest.qWait(10)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()

    def tearDown(self):
        self.dispose()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.dock, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def command(self, name, *args):
        return self.evaluate(f"profiles.{name}({','.join(json.dumps(value) for value in args)},profiles.activeProfileId,profiles.revision)")

    def initialize(self):
        self.assertTrue(self.evaluate("profiles.initializeDefaults(profiles.activeProfileId,profiles.revision)"))
        self.assertTrue(self.command("select", "work"))

    def open_profiles(self, width=350):
        self.popup.setProperty("width", width)
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 2)
        QTest.qWait(30)

    def press(self, control):
        interface = QAccessible.queryAccessibleInterface(control)
        self.assertIsNotNone(interface)
        actions = interface.actionInterface()
        self.assertIsNotNone(actions)
        press = QAccessibleActionInterface.pressAction()
        self.assertIn(press, actions.actionNames())
        actions.doAction(press)

    def local_press(self, control):
        expression = QQmlExpression(QQmlEngine.contextForObject(control), control, "Accessible.pressAction()")
        expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())

    def configuration_snapshot(self):
        meta = self.config.metaObject()
        return {meta.property(index).name(): self.evaluate(
            "JSON.stringify(configuration[" + json.dumps(meta.property(index).name()) + "])")
                for index in range(meta.propertyOffset(), meta.propertyCount())}

    def test_rename_active_profile_is_explicit_and_changes_only_its_name(self):
        self.initialize()
        self.open_profiles()
        disclosure = self.owned_item("profileRenameToggle")
        self.assertIsNotNone(disclosure, "The active profile needs its public rename disclosure")
        field = self.owned_item("profileRenameName")
        self.assertFalse(field.isVisible())
        self.assertEqual(self.owned_item("profileActiveName").property("text"), "Trabalho")
        self.evaluate("pomodoro.toggle()")
        timer = {key: self.config.property(key) for key in
                 ("focusMinutes", "breakMinutes", "timerDeadline", "timerRemaining", "timerBreak", "completedFocus")}
        self.evaluate("timerWitness = contentItem.children.find(item => item.objectName === 'dock').pomodoro", self.window)
        before = json.loads(self.config.property("profilesJSON"))
        flat = self.flat()
        bindings = self.config.property("contextsJSON")
        configuration = self.configuration_snapshot()
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.focus(disclosure)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertTrue(field.isVisible())
        self.assertEqual(field.property("text"), "Trabalho")
        self.assertEqual(field.property("maximumLength"), 48)
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem(), field)
        QTest.keyClick(self.window, Qt.Key_A, Qt.ControlModifier)
        for character in "estudo":
            QTest.keyClick(self.window, Qt.Key(ord(character.upper())))
        self.assertEqual(writes.count(), 0, "Typing never saves a rename")
        QTest.keyClick(self.window, Qt.Key_Return)
        self.assertEqual(writes.count(), 0, "Rename requires its explicit action")
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem(), self.owned_item("profileRenameSave"))
        QTest.keyClick(self.window, Qt.Key_Space)
        expected = json.loads(json.dumps(before))
        next(profile for profile in expected["profiles"] if profile["id"] == "work")["name"] = "estudo"
        self.assertEqual(json.loads(self.config.property("profilesJSON")), expected)
        self.assertEqual(writes.count(), 1)
        self.assertFalse(field.isVisible())
        self.assertEqual(self.window.activeFocusItem(), disclosure)
        self.assertEqual(self.owned_item("profileActiveName").property("text"), "estudo")
        self.assertEqual(self.flat(), flat)
        self.assertEqual(self.config.property("contextsJSON"), bindings)
        self.assertTrue(self.evaluate("timerWitness === contentItem.children.find(item => item.objectName === 'dock').pomodoro", self.window))
        for key, value in timer.items():
            self.assertEqual(self.config.property(key), value, key)
        after = self.configuration_snapshot()
        self.assertEqual({key: value for key, value in after.items() if key != "profilesJSON"},
                         {key: value for key, value in configuration.items() if key != "profilesJSON"})

    def test_rename_keeps_active_target_when_selector_has_a_pending_other_profile(self):
        previous = QAccessible.isActive()
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, previous)
        self.initialize()
        self.open_profiles()
        selector = self.owned_item("profileSelector")
        self.press(selector)
        self.accessible_press_combo_option(selector, "Pessoal")
        self.assertEqual(selector.property("currentText"), "Pessoal")
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        self.assertEqual(self.owned_item("profileActiveName").property("text"), "Trabalho")
        saved = json.loads(self.config.property("profilesJSON"))
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.press(self.owned_item("profileRenameToggle"))
        field = self.owned_item("profileRenameName")
        self.assertEqual(field.property("text"), "Trabalho")
        field.setProperty("text", "Equipe")
        # Press can start from another control; the native Button takes focus before clicking.
        other = self.owned_item("profileName")
        self.focus(other)
        self.local_press(self.owned_item("profileRenameSave"))
        self.assertEqual(self.window.activeFocusItem(), self.owned_item("profileRenameToggle"))
        next(profile for profile in saved["profiles"] if profile["id"] == "work")["name"] = "Equipe"
        self.assertEqual(json.loads(self.config.property("profilesJSON")), saved)
        self.assertEqual(writes.count(), 1)
        self.assertEqual(selector.property("currentText"), "Pessoal")
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")

    def test_rename_invalid_duplicate_and_same_name_are_zero_write_actions(self):
        self.initialize()
        self.open_profiles()
        self.focus(self.owned_item("profileRenameToggle"))
        QTest.keyClick(self.window, Qt.Key_Space)
        field = self.owned_item("profileRenameName")
        save = self.owned_item("profileRenameSave")
        raw = self.config.property("profilesJSON")
        writes = QSignalSpy(self.config.profilesJSONChanged)
        for draft, message in (("   ", "48"), ("Pessoal", "Já existe")):
            with self.subTest(draft=draft):
                field.setProperty("text", draft)
                self.focus(save)
                QTest.qWait(30)
                point = save.mapToScene(QPointF(save.width() / 2, save.height() / 2)).toPoint()
                QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
                self.assertTrue(field.isVisible())
                self.assertEqual(field.property("text"), draft)
                self.assertIn(message, self.owned_item("profileRenameStatus").property("text"))
                self.assertEqual(self.config.property("profilesJSON"), raw)
                self.assertEqual(writes.count(), 0)
        field.setProperty("text", " Trabalho ")
        self.focus(save)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertFalse(field.isVisible())
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertEqual(writes.count(), 0)

    def test_rename_dirty_stale_and_protected_drafts_remain_without_writes(self):
        self.initialize()
        self.open_profiles()
        disclosure = self.owned_item("profileRenameToggle")
        self.press(disclosure)
        field = self.owned_item("profileRenameName")
        field.setProperty("text", "Rascunho")
        save = self.owned_item("profileRenameSave")
        self.evaluate("appearance.setToken('radius',8)")
        raw = self.config.property("profilesJSON")
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.assertFalse(save.isEnabled())
        self.assertIn("prévia", self.owned_item("profileRenameStatus").property("text"))
        self.press(save)
        self.assertEqual(writes.count(), 0)
        self.assertEqual(field.property("text"), "Rascunho")
        self.evaluate("appearance.cancel();appearance.begin()")
        self.assertTrue(self.command("commitPresentation", {"calendarEvents": True}))
        after_external = self.config.property("profilesJSON")
        count = writes.count()
        self.assertNotEqual(after_external, raw)
        self.assertFalse(save.isEnabled())
        self.assertIn("Cancele", self.owned_item("profileRenameStatus").property("text"))
        self.press(save)
        self.assertEqual(writes.count(), count)
        self.assertEqual(field.property("text"), "Rascunho")
        self.assertEqual(self.config.property("profilesJSON"), after_external)
        self.press(self.owned_item("profileRenameCancel"))
        self.press(disclosure)
        field.setProperty("text", "Outro rascunho")
        self.assertTrue(self.command("select", "personal"))
        after_scope = self.config.property("profilesJSON")
        count = writes.count()
        self.press(save)
        self.assertFalse(save.isEnabled())
        self.assertEqual(field.property("text"), "Outro rascunho")
        self.assertEqual(writes.count(), count)
        self.assertEqual(self.config.property("profilesJSON"), after_scope)
        self.config.setProperty("profilesJSON", '{"formatVersion":"future"}')
        count = writes.count()
        self.press(save)
        self.assertEqual(writes.count(), count)
        self.assertEqual(field.property("text"), "Outro rascunho")
        self.assertEqual(self.config.property("profilesJSON"), '{"formatVersion":"future"}')

    def test_rename_escape_and_settings_close_discard_but_tab_switch_keeps_local_draft(self):
        self.open_profiles()
        disclosure = self.owned_item("profileRenameToggle")
        self.assertFalse(disclosure.isEnabled(), "Legacy preferences have no managed name to edit")
        self.press(disclosure)
        self.assertFalse(self.owned_item("profileRenameName").isVisible())
        self.initialize()
        self.press(disclosure)
        field = self.owned_item("profileRenameName")
        field.setProperty("text", "Rascunho")
        raw = self.config.property("profilesJSON")
        writes = QSignalSpy(self.config.profilesJSONChanged)
        tabs = self.window.findChild(QObject, "settingsTabs")
        tabs.setProperty("currentIndex", 3)
        QTest.qWait(20)
        tabs.setProperty("currentIndex", 2)
        QTest.qWait(20)
        self.assertTrue(field.isVisible())
        self.assertEqual(field.property("text"), "Rascunho")
        self.focus(field)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.assertTrue(self.popup.property("visible"))
        self.assertFalse(field.isVisible())
        self.assertEqual(self.window.activeFocusItem(), disclosure)
        self.press(disclosure)
        self.assertEqual(field.property("text"), "Trabalho")
        field.setProperty("text", "Descartar ao fechar")
        self.evaluate("close()", self.popup)
        self.settle(lambda: not self.popup.property("visible"))
        self.assertEqual(field.property("text"), "")
        self.assertFalse(field.isVisible())
        self.open_profiles()
        self.assertFalse(field.isVisible())
        self.press(disclosure)
        self.assertEqual(field.property("text"), "Trabalho")
        self.assertEqual(writes.count(), 0)
        self.assertEqual(self.config.property("profilesJSON"), raw)

    def test_rename_writer_preserves_newer_input_and_newer_focus(self):
        self.initialize()
        self.open_profiles()
        self.press(self.owned_item("profileRenameToggle"))
        field = self.owned_item("profileRenameName")
        save = self.owned_item("profileRenameSave")
        other = self.owned_item("profileName")
        field.setProperty("text", "Primeiro")
        self.focus(save)
        saved = json.loads(self.config.property("profilesJSON"))
        writes = QSignalSpy(self.config.profilesJSONChanged)

        def newer_ui():
            field.setProperty("text", "Rascunho mais novo")
            other.forceActiveFocus(Qt.TabFocusReason)

        self.config.profilesJSONChanged.connect(newer_ui)
        try:
            self.press(save)
        finally:
            self.config.profilesJSONChanged.disconnect(newer_ui)
        next(profile for profile in saved["profiles"] if profile["id"] == "work")["name"] = "Primeiro"
        self.assertEqual(json.loads(self.config.property("profilesJSON")), saved)
        self.assertEqual(writes.count(), 1)
        self.assertTrue(field.isVisible())
        self.assertEqual(field.property("text"), "Rascunho mais novo")
        self.assertEqual(self.window.activeFocusItem(), other)
        self.assertIn("Cancele", self.owned_item("profileRenameStatus").property("text"))

    def test_rename_keyboard_reveals_complete_focus_rims_at_350_and_420(self):
        self.initialize()
        self.open_profiles()
        disclosure = self.owned_item("profileRenameToggle")
        field = self.owned_item("profileRenameName")
        save = self.owned_item("profileRenameSave")
        cancel = self.owned_item("profileRenameCancel")
        viewport = self.owned_item("profileControls").property("contentItem")
        raw = self.config.property("profilesJSON")
        writes = QSignalSpy(self.config.profilesJSONChanged)
        for width in (350, 420):
            with self.subTest(width=width):
                self.popup.setProperty("width", width)
                self.focus(disclosure)
                QTest.qWait(300)  # Open from a settled compact layout, as a user would.
                QTest.keyClick(self.window, Qt.Key_Space)
                self.focus(field)
                QTest.qWait(60)
                point = field.mapToItem(viewport, QPointF(0, 0))
                self.assertGreaterEqual(point.y() - 2, 0, "The first-open field's complete rim must be visible")
                self.assertLessEqual(point.y() + field.height() + 2, viewport.height(),
                                     "The first-open field must reveal before any validation changes layout")
                field.setProperty("text", "Pessoal")
                self.focus(save)
                QTest.keyClick(self.window, Qt.Key_Space)
                self.assertIn("Já existe", self.owned_item("profileRenameStatus").property("text"))
                for control, margin in ((field, 2), (save, 3), (cancel, 3), (disclosure, 3)):
                    self.focus(control)
                    QTest.qWait(30)
                    point = control.mapToItem(viewport, QPointF(0, 0))
                    self.assertGreaterEqual(point.x() - margin, 0)
                    self.assertGreaterEqual(point.y() - margin, 0)
                    self.assertLessEqual(point.x() + control.width() + margin, viewport.width())
                    self.assertLessEqual(point.y() + control.height() + margin, viewport.height())
                self.focus(field)
                QTest.keyClick(self.window, Qt.Key_Tab)
                self.assertEqual(self.window.activeFocusItem(), save)
                QTest.keyClick(self.window, Qt.Key_Tab)
                self.assertEqual(self.window.activeFocusItem(), cancel)
                QTest.keyClick(self.window, Qt.Key_Escape)
                self.assertFalse(field.isVisible())
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertEqual(writes.count(), 0)

    def owned_item(self, name):
        source = "(function find(item) { if (item.objectName === " + json.dumps(name) + ") return item; for (let child of item.children) { const result = find(child); if (result) return result; } return null; })(this)"
        return self.evaluate(source, self.window.contentItem())

    def focus(self, control):
        control.forceActiveFocus(Qt.TabFocusReason)
        deadline = time.monotonic() + 1
        while self.window.activeFocusItem() != control and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertEqual(self.window.activeFocusItem(), control)

    def settle(self, predicate):
        deadline = time.monotonic() + 1
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(predicate(), "Owned model must settle before its next gesture")

    def widget_drag_points(self):
        self.popup.setProperty("heightBudget", 420)
        if not self.popup.property("visible"):
            self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        QTest.qWait(30)  # Settle the short tab layout before revealing complete rows.
        grip = self.owned_item("widgetDragclock")
        target = self.owned_item("widgetDragpomodoro")
        self.assertIsNotNone(grip, "The row must expose its real pointer grip")
        self.assertIsNotNone(target)
        self.focus(target)
        self.focus(grip)
        QTest.qWait(30)
        start = grip.mapToScene(QPointF(grip.width() / 2, grip.height() / 2)).toPoint()
        end = target.mapToScene(QPointF(target.width() / 2, target.height() * .75)).toPoint()
        self.assertGreaterEqual(start.y(), 0)
        self.assertLess(end.y(), self.window.height())
        return start, end

    def accessible_named(self, name, within=None):
        root = within or QAccessible.queryAccessibleInterface(self.window)
        self.assertIsNotNone(root)
        pending, matches, visited = [root], [], 0
        while pending:
            item = pending.pop()
            visited += 1
            self.assertLess(visited, 2048)
            if item.text(QAccessible.Text.Name) == name:
                matches.append(item)
            pending.extend(child for index in range(item.childCount())
                           if (child := item.child(index)) is not None)
        self.assertEqual(len(matches), 1, f"Expected one accessible {name}")
        return matches[0]

    def test_settings_tabs_expose_press_and_select_once_through_accessibility(self):
        previous = QAccessible.isActive()
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, previous)
        self.evaluate("open()", self.popup)
        tabs = self.window.findChild(QObject, "settingsTabs")
        self.assertIsNotNone(tabs)
        self.assertEqual(tabs.property("currentIndex"), 0)
        profiles = self.evaluate("itemAt(2)", tabs)
        contexts = self.evaluate("itemAt(3)", tabs)
        self.assertIsNotNone(profiles)
        self.assertIsNotNone(contexts)
        profiles_clicks = QSignalSpy(profiles.clicked)
        contexts_clicks = QSignalSpy(contexts.clicked)
        self.assertTrue(profiles_clicks.isValid())
        self.assertTrue(contexts_clicks.isValid())
        QTest.qWait(30)

        accessible = self.accessible_named("Perfis")
        self.assertEqual(accessible.role(), QAccessible.Role.PageTab)
        actions = accessible.actionInterface()
        self.assertIsNotNone(actions)
        press = QAccessibleActionInterface.pressAction()
        self.assertIn(press, actions.actionNames())
        actions.doAction(press)
        self.settle(lambda: tabs.property("currentIndex") == 2)
        self.assertTrue(profiles.property("checked"))
        self.assertFalse(contexts.property("checked"))
        self.assertEqual(profiles_clicks.count(), 1)
        self.assertEqual(contexts_clicks.count(), 0)

        # An already selected tab follows one click lifecycle and stays exclusive.
        self.accessible_named("Perfis").actionInterface().doAction(press)
        self.assertEqual(tabs.property("currentIndex"), 2)
        self.assertEqual(profiles_clicks.count(), 2)
        for index in range(4):
            tab = self.evaluate(f"itemAt({index})", tabs)
            self.assertEqual(tab.property("checked"), index == 2)

        # Direct dispatch must also respect a disabled tab.
        self.assertTrue(contexts.setProperty("enabled", False))
        disabled = self.accessible_named("Contextos")
        self.assertEqual(disabled.role(), QAccessible.Role.PageTab)
        self.assertTrue(disabled.state().disabled)
        disabled_actions = disabled.actionInterface()
        self.assertIsNotNone(disabled_actions)
        disabled_actions.doAction(press)
        QTest.qWait(30)
        self.assertEqual(tabs.property("currentIndex"), 2)
        self.assertTrue(profiles.property("checked"))
        self.assertFalse(contexts.property("checked"))
        self.assertEqual(profiles_clicks.count(), 2)
        self.assertEqual(contexts_clicks.count(), 0)

    def accessible_press_combo_option(self, selector, text):
        self.assertTrue(self.evaluate("popup.visible", selector))
        # Popup visibility can precede delegate layout/accessibility publication.
        deadline = time.monotonic() + 1
        while True:
            # The ListView itself can be ignored; query only this fixture app's
            # public windows, including native-style popup windows.
            windows = [self.window] + [window for window in self.app.topLevelWindows()
                                      if window != self.window]
            pending = [interface for window in windows
                       if (interface := QAccessible.queryAccessibleInterface(window)) is not None]
            matches, visited = [], 0
            while pending:
                item = pending.pop()
                visited += 1
                self.assertLess(visited, 1024)
                if (item.role() == QAccessible.Role.ListItem
                        and item.text(QAccessible.Text.Name) == text
                        and not item.state().invisible and not item.state().offscreen
                        and not item.state().disabled):
                    matches.append(item)
                pending.extend(child for index in range(item.childCount())
                               if (child := item.child(index)) is not None)
            self.assertLessEqual(len(matches), 1, "The live popup option must be unique")
            if matches:
                break
            self.assertLess(time.monotonic(), deadline, "No live real option in the fixture popup")
            QTest.qWait(10)
        actions = matches[0].actionInterface()
        self.assertIsNotNone(actions)
        press = QAccessibleActionInterface.pressAction()
        self.assertIn(press, actions.actionNames(), "The real delegate must advertise Press")
        actions.doAction(press)
        self.settle(lambda: not self.evaluate("popup.visible", selector))

    def test_profile_selector_accessible_press_defers_selection_until_use(self):
        previous = QAccessible.isActive()
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, previous)
        self.initialize()
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 2)
        QTest.qWait(30)
        selector = self.owned_item("profileSelector")
        self.assertIsNotNone(selector)
        self.focus(selector)
        header = self.evaluate("itemAt(2)", self.window.findChild(QObject, "settingsTabs"))
        self.focus(header)
        interface = QAccessible.queryAccessibleInterface(selector)
        self.assertIsNotNone(interface)
        self.assertEqual(interface.role(), QAccessible.Role.ComboBox)
        actions = interface.actionInterface()
        self.assertIsNotNone(actions)
        press = QAccessibleActionInterface.pressAction()
        self.assertIn(press, actions.actionNames())
        activated = QSignalSpy(selector.activated)
        writes = QSignalSpy(self.config.profilesJSONChanged)
        saved = self.config.property("profilesJSON")
        self.assertFalse(self.evaluate("popup.visible", selector))
        actions.doAction(press)
        self.settle(lambda: self.evaluate("popup.visible", selector))
        self.assertEqual(activated.count(), 0)
        actions.doAction(press)
        self.settle(lambda: not self.evaluate("popup.visible", selector))
        self.assertEqual(self.window.activeFocusItem(), selector)
        self.assertEqual(activated.count(), 0)
        self.assertEqual(writes.count(), 0)
        self.assertEqual(self.config.property("profilesJSON"), saved)
        actions.doAction(press)
        self.settle(lambda: self.evaluate("popup.visible", selector))
        self.accessible_press_combo_option(selector, "Pessoal")
        self.assertEqual(activated.count(), 1)
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.assertEqual(writes.count(), 0)
        use = self.owned_item("profileUse")
        self.assertIsNotNone(use)
        self.assertTrue(use.isEnabled())
        self.focus(use)
        use_actions = QAccessible.queryAccessibleInterface(use).actionInterface()
        self.assertIsNotNone(use_actions)
        self.assertIn(press, use_actions.actionNames())
        use_actions.doAction(press)
        self.settle(lambda: self.evaluate("profiles.activeProfileId") == "personal")
        self.assertEqual(writes.count(), 1)
        self.assertEqual(activated.count(), 1)
        selector.setProperty("enabled", False)
        actions.doAction(press)
        QTest.qWait(30)
        self.assertFalse(self.evaluate("popup.visible", selector))
        selector.setProperty("enabled", True)
        selector.setProperty("visible", False)
        actions.doAction(press)
        QTest.qWait(30)
        self.assertFalse(self.evaluate("popup.visible", selector))
        self.assertEqual(writes.count(), 1)
        self.assertEqual(activated.count(), 1)

    def test_default_selector_accessible_press_changes_only_default_without_opt_in(self):
        previous = QAccessible.isActive()
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, previous)
        self.initialize()
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 3)
        QTest.qWait(30)
        selector = self.owned_item("autoContextDefaultProfile")
        self.assertIsNotNone(selector)
        self.assertTrue(selector.isEnabled())
        self.focus(selector)
        header = self.evaluate("itemAt(3)", self.window.findChild(QObject, "settingsTabs"))
        self.focus(header)
        interface = QAccessible.queryAccessibleInterface(selector)
        self.assertIsNotNone(interface)
        self.assertEqual(interface.role(), QAccessible.Role.ComboBox)
        actions = interface.actionInterface()
        self.assertIsNotNone(actions)
        press = QAccessibleActionInterface.pressAction()
        self.assertIn(press, actions.actionNames())
        activated = QSignalSpy(selector.activated)
        defaults = QSignalSpy(self.config.autoContextDefaultProfileChanged)
        writes = QSignalSpy(self.config.profilesJSONChanged)
        enabled = QSignalSpy(self.config.autoContextEnabledChanged)
        saved = self.config.property("profilesJSON")
        bindings = self.config.property("contextsJSON")
        original_default = self.config.property("autoContextDefaultProfile")
        self.assertFalse(self.config.property("autoContextEnabled"))
        actions.doAction(press)
        self.settle(lambda: self.evaluate("popup.visible", selector))
        self.assertEqual(activated.count(), 0)
        actions.doAction(press)
        self.settle(lambda: not self.evaluate("popup.visible", selector))
        self.assertEqual(self.window.activeFocusItem(), selector)
        self.assertEqual(activated.count(), 0)
        self.assertEqual(defaults.count(), 0)
        self.assertEqual(self.config.property("autoContextDefaultProfile"), original_default)
        actions.doAction(press)
        self.settle(lambda: self.evaluate("popup.visible", selector))
        self.accessible_press_combo_option(selector, "Pessoal")
        self.assertEqual(activated.count(), 1)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(self.config.property("autoContextDefaultProfile"), "personal")
        self.assertFalse(self.config.property("autoContextEnabled"))
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.assertEqual(self.config.property("contextsJSON"), bindings)
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        self.assertEqual(writes.count(), 0)
        self.assertEqual(enabled.count(), 0)
        selector.setProperty("enabled", False)
        actions.doAction(press)
        QTest.qWait(30)
        self.assertFalse(self.evaluate("popup.visible", selector))
        selector.setProperty("enabled", True)
        selector.setProperty("visible", False)
        actions.doAction(press)
        QTest.qWait(30)
        self.assertFalse(self.evaluate("popup.visible", selector))
        self.assertEqual(activated.count(), 1)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(writes.count(), 0)
        self.assertEqual(enabled.count(), 0)

    def test_widget_regions_and_rows_are_named_in_the_accessible_tree(self):
        previous = QAccessible.isActive()
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, previous)
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        QTest.qWait(30)
        raw = self.config.property("profilesJSON")
        writes = QSignalSpy(self.config.profilesJSONChanged)
        options = self.accessible_named("Opções dos widgets")
        viewport = self.accessible_named("Conteúdo das opções de widgets", options)
        self.assertEqual(options.role(), QAccessible.Role.Pane)
        self.assertEqual(viewport.role(), QAccessible.Role.Pane)
        self.assertGreater(viewport.rect().height(), 0)
        for label in ("Relógio e calendário", "Pomodoro", "Música (MPRIS)",
                      "Bateria do computador", "QuotaLantern", "PeriGauge", "FalaTrace"):
            row = self.accessible_named("Widget: " + label, viewport)
            self.assertEqual(row.role(), QAccessible.Role.Grouping)
            self.assertFalse(row.state().focusable)
            controls = [row.child(index) for index in range(row.childCount())]
            names = {item.text(QAccessible.Text.Name) for item in controls}
            self.assertTrue({label, "Arrastar " + label + " para reordenar",
                             "Mover " + label + " para antes", "Mover " + label + " para depois"} <= names)
            self.assertTrue(self.accessible_named("Arrastar " + label + " para reordenar", row).state().disabled)
            self.assertFalse(self.accessible_named(label, row).state().disabled)
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertEqual(writes.count(), 0)
        self.assertEqual(self.warnings, [])

    def test_focused_widget_controls_reveal_the_whole_row_in_a_short_viewport(self):
        previous = QAccessible.isActive()
        QAccessible.setActive(True)
        self.addCleanup(QAccessible.setActive, previous)
        self.initialize()
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        raw = self.config.property("profilesJSON")
        writes = QSignalSpy(self.config.profilesJSONChanged)
        for width in (350, 420):
            self.popup.setProperty("width", width)
            QTest.qWait(30)
            for control, label in (("widgetVisiblepomodoro", "Pomodoro"),
                                   ("widgetVisiblesystemBattery", "Bateria do computador"),
                                   ("widgetUpmusic", "Música (MPRIS)"),
                                   ("widgetDownquota", "QuotaLantern"),
                                   ("widgetDragclock", "Relógio e calendário")):
                with self.subTest(width=width, control=control):
                    self.focus(self.owned_item(control))
                    QTest.qWait(10)
                    viewport = self.accessible_named("Conteúdo das opções de widgets")
                    row = self.accessible_named("Widget: " + label, viewport)
                    self.assertTrue(viewport.rect().contains(row.rect()),
                                    f"Focused row {row.rect()} must fit viewport {viewport.rect()}")
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertEqual(writes.count(), 0)
        self.assertEqual(self.warnings, [])

    def widgets(self, visible=True, reverse=False):
        ids = ["clock", "pomodoro", "music", "systemBattery", "quota", "peripherals", "recording"]
        return [{"id": key, "visible": visible} for key in (reversed(ids) if reverse else ids)]

    def flat(self):
        return self.evaluate("JSON.stringify({launchers:Array.from(configuration.launchers),theme:configuration.theme,appearanceJSON:configuration.appearanceJSON,iconSize:configuration.iconSize,animations:configuration.animations,showClock:configuration.showClock,showMusic:configuration.showMusic,showSystemBattery:configuration.showSystemBattery,showPomodoro:configuration.showPomodoro,showQuota:configuration.showQuota,showPeripherals:configuration.showPeripherals,showRecording:configuration.showRecording,calendarEvents:configuration.calendarEvents,currentDesktopOnly:configuration.currentDesktopOnly})")

    def theme_text(self, index=0):
        examples = sorted((Path(__file__).resolve().parents[1] / "themes/examples").glob("*.json"))
        return examples[index].read_text()

    def set_theme(self, text):
        self.evaluate("appearance.setThemeText(" + json.dumps(text) + ")")

    def test_external_theme_tokens_preview_and_apply_only_current_profile(self):
        self.initialize()
        flat = self.flat()
        original_raw = self.config.property("profilesJSON")
        original = json.loads(original_raw)
        before_personal = next(p for p in original["profiles"] if p["id"] == "personal")
        self.evaluate("pomodoro.toggle()")
        timer = {key: self.config.property(key) for key in ("timerDeadline", "timerRemaining", "timerBreak", "completedFocus")}
        self.evaluate("appearance.begin()")
        for index in range(2):
            text = self.theme_text(index)
            tokens = json.loads(text)["tokens"]
            self.set_theme(text)
            self.assertTrue(self.evaluate("appearance.dirty"))
            self.assertFalse(self.command("select", "personal"))
            self.assertFalse(self.command("create", "Blocked"))
            self.assertFalse(self.evaluate("appearance.canApply"))
            self.assertTrue(self.evaluate("appearance.previewTheme()"))
            self.assertEqual(json.loads(self.evaluate("JSON.stringify(appearance.effective.tokens)")), tokens)
            for key in ("foreground", "muted", "accent", "surface"):
                self.assertEqual(self.evaluate("String(" + key + ")"), tokens[key])
            surface = self.window.findChild(QQuickItem, "dockSurface")
            self.assertEqual(surface.property("radius"), tokens["radius"])
            self.assertAlmostEqual(surface.property("opacity"), tokens["opacity"])
            self.assertEqual(self.evaluate("String(border.color)", surface), tokens["border"])
            self.assertEqual(self.window.findChild(QQuickItem, "dockContent").property("spacing"), tokens["spacing"])
            self.assertEqual(self.dock.property("requestedIconSize"), tokens["iconSize"])
            self.assertEqual(self.evaluate("appearance.effective.tokens.reducedMotion"), tokens["reducedMotion"])
            self.assertEqual(self.config.property("profilesJSON"), original_raw)
            self.assertEqual(self.flat(), flat)
        widgets = self.widgets(False, True)
        self.assertTrue(self.command("commitPresentation", {"widgets": widgets}))
        self.assertTrue(self.evaluate("appearance.apply()"))
        saved = json.loads(self.config.property("profilesJSON"))
        work = next(p for p in saved["profiles"] if p["id"] == "work")
        self.assertEqual(json.loads(work["appearance"]["appearanceJSON"])["tokens"], tokens)
        self.assertEqual(work["widgets"], widgets)
        self.assertEqual(work["launchers"], next(p for p in original["profiles"] if p["id"] == "work")["launchers"])
        self.assertEqual(next(p for p in saved["profiles"] if p["id"] == "personal"), before_personal)
        self.assertEqual(self.flat(), flat)
        for key, value in timer.items():
            self.assertEqual(self.config.property(key), value)
        self.assertTrue(self.evaluate("appearance.undo()"))
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.widgets)")), widgets)
        self.assertEqual(self.evaluate("presentation.appearance.appearanceJSON"), "")
        self.assertEqual(self.flat(), flat)

    def test_theme_input_escape_cancels_and_invalid_profile_bytes_remain_protected(self):
        self.initialize()
        saved = self.config.property("profilesJSON")
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        QTest.qWait(20)
        disclosure = self.owned_item("appearanceThemeJSON")
        self.focus(disclosure); QTest.keyClick(self.window, Qt.Key_Space)
        self.set_theme(self.theme_text())
        self.assertTrue(self.evaluate("appearance.previewTheme()"))
        field = self.owned_item("appearanceThemeInput")
        self.focus(field); QTest.keyClick(self.window, Qt.Key_Escape)
        self.settle(lambda: not self.popup.property("visible"))
        self.assertEqual(self.evaluate("appearance.themeText"), "")
        self.assertFalse(self.evaluate("appearance.editing"))
        self.assertEqual(self.config.property("profilesJSON"), saved)
        raw = '{"formatVersion":"future","preserve":"owned bytes"}'
        for when in ("before", "during"):
            self.evaluate("appearance.cancel()")
            if when == "before": self.config.setProperty("profilesJSON", raw)
            self.evaluate("appearance.begin()")
            self.set_theme(self.theme_text())
            self.assertTrue(self.evaluate("appearance.previewTheme()"))
            if when == "during": self.config.setProperty("profilesJSON", raw)
            self.assertFalse(self.evaluate("appearance.apply()"))
            self.assertEqual(self.config.property("profilesJSON"), raw)
            self.assertEqual(self.config.property("appearanceJSON"), "")
            self.config.setProperty("profilesJSON", saved)

    def test_external_theme_rejects_profile_signature_change_and_scope_clears_input(self):
        self.initialize()
        self.evaluate("appearance.begin()")
        self.set_theme(self.theme_text())
        self.assertTrue(self.command("commitPresentation", {"appearance": {"theme": "paper"}}))
        saved = self.config.property("profilesJSON")
        self.assertTrue(self.evaluate("appearance.stale"))
        self.assertFalse(self.evaluate("appearance.previewTheme()"))
        self.assertFalse(self.evaluate("appearance.apply()"))
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.evaluate("appearance.cancel(); appearance.begin()")
        self.set_theme(self.theme_text())
        self.assertTrue(self.evaluate("appearance.previewTheme()"))
        self.assertTrue(self.evaluate("appearance.apply()"))
        self.assertTrue(self.command("select", "personal"))
        self.assertEqual(self.evaluate("appearance.themeText"), "")
        self.assertFalse(self.evaluate("appearance.canUndo"))
        self.assertFalse(self.evaluate("appearance.undo()"))

    def test_scoped_apply_retains_immediate_widgets_and_dirty_preview_blocks_switch(self):
        self.initialize()
        self.evaluate("appearance.begin()")
        self.assertFalse(self.evaluate("appearance.dirty"))
        self.evaluate("appearance.setToken('accent','#123456')")
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.assertFalse(self.command("select", "personal"))
        self.assertTrue(self.command("commitPresentation", {"calendarEvents": True}))
        self.assertTrue(self.evaluate("appearance.apply()"))
        saved = json.loads(self.config.property("profilesJSON"))
        work = next(profile for profile in saved["profiles"] if profile["id"] == "work")
        self.assertTrue(work["calendarEvents"])
        self.assertTrue(self.window.findChild(QQuickItem, "calendarAgenda").property("usePimEvents"))
        self.assertIn('"accent":"#123456"', work["appearance"]["appearanceJSON"])
        self.assertEqual(self.config.property("appearanceJSON"), "")
        self.assertFalse(self.evaluate("appearance.dirty"))
        self.assertTrue(self.command("select", "personal"))
        self.assertFalse(self.evaluate("appearance.canUndo"))
        self.assertEqual(self.warnings, [])
    def test_invalid_raw_keeps_presentation_and_disables_presentation_checkboxes(self):
        self.initialize()
        before = self.evaluate("JSON.stringify(presentation)")
        raw = '{"formatVersion":"unsupported"}'
        self.config.setProperty("profilesJSON", raw)
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup); QTest.qWait(30)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        for name in ("filterDesktop", "calendarEvents", "widgetVisibleclock", "widgetVisiblemusic"):
            control = self.owned_item(name)
            self.assertFalse(control.property("enabled"), name)
        self.assertEqual(self.evaluate("JSON.stringify(presentation)"), before)
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertFalse(self.command("commitPresentation", {"calendarEvents": True}))
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertEqual(self.warnings, [])

    def test_scoped_undo_restores_only_appearance_after_immediate_widget_commit(self):
        self.initialize()
        self.evaluate("appearance.begin(); appearance.setToken('radius',8); appearance.apply()")
        widgets = self.widgets(False, True)
        self.assertTrue(self.command("commitPresentation", {"widgets": widgets}))
        self.assertTrue(self.evaluate("appearance.undo()"))
        self.assertEqual(self.evaluate("presentation.appearance.appearanceJSON"), "")
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.widgets)")), widgets)
        self.assertEqual(self.config.property("appearanceJSON"), "")

    def test_transition_closes_stale_task_widget_and_add_context_but_keeps_settings(self):
        self.initialize()
        menu = self.window.findChild(QObject, "taskContextMenu")
        menu.setProperty("popupType", 0)
        self.evaluate("open()", self.popup)
        calendar = self.window.findChild(QObject, "calendarPopup")
        add = self.window.findChild(QObject, "addPopup")
        calendar.setProperty("popupType", 0); add.setProperty("popupType", 0)
        self.assertTrue(self.evaluate("openWidget('clock')"))
        self.evaluate("open()", add)
        self.evaluate("showTaskMenu(0,{AppName:'Owned',LauncherUrlWithoutIcon:'applications:org.kde.dolphin.desktop',IsLauncher:true})")
        self.assertTrue(menu.property("visible"))
        self.assertTrue(self.command("select", "personal"))
        self.assertFalse(self.evaluate("menuRow >= 0"))
        self.assertFalse(self.evaluate("Boolean(menuIndex())"))
        self.settle(lambda: not menu.property("visible") and not calendar.property("visible") and not add.property("visible"))
        self.assertTrue(self.popup.property("visible"))
        self.assertFalse(self.evaluate("appearance.dirty"))

    def test_calendar_popup_alone_activates_the_fixture_provider_path(self):
        calendar = self.window.findChild(QQuickItem, "calendarAgenda")
        popup = self.window.findChild(QObject, "calendarPopup")
        popup.setProperty("popupType", 0)
        self.assertFalse(calendar.property("active"))
        self.assertFalse(popup.property("visible"))
        self.assertTrue(self.evaluate("openWidget('clock')"))
        self.settle(lambda: popup.property("visible") and calendar.property("active"))
        self.assertEqual(self.evaluate("enabledPlugins.length", calendar), 0)
        self.evaluate("close()", popup)
        self.settle(lambda: not popup.property("visible") and not calendar.property("active"))
        self.assertEqual(self.evaluate("enabledPlugins.length", calendar), 0)
        configure = self.window.findChild(QObject, "calendarConfigureButton")
        self.assertIsNotNone(configure)
        self.assertEqual(configure.property("text"), "Configurar no KOrganizer")
        self.assertIn("relógio", configure.property("accessibilityDescription"))
        google = self.window.findChild(QObject, "calendarGoogleButton")
        self.assertIsNotNone(google)
        self.assertEqual(google.property("text"), "Abrir Google Agenda")

    def test_external_appearance_change_rejects_old_draft_and_old_undo(self):
        self.initialize()
        self.evaluate("appearance.begin(); appearance.setToken('accent','#123456')")
        self.assertTrue(self.command("commitPresentation", {"appearance": {"theme": "paper"}}))
        saved = self.config.property("profilesJSON")
        self.assertTrue(self.evaluate("appearance.stale"))
        self.assertFalse(self.evaluate("appearance.apply()"))
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.evaluate("appearance.cancel(); appearance.begin(); appearance.setToken('radius',8)")
        self.assertTrue(self.evaluate("appearance.apply()"))
        self.assertTrue(self.evaluate("appearance.canUndo"))
        self.assertTrue(self.command("commitPresentation", {"appearance": {"iconSize": 48}}))
        self.assertFalse(self.evaluate("appearance.undo()"))
        self.assertEqual(self.evaluate("presentation.appearance.iconSize"), 48)

    def test_timer_identity_deadline_and_single_completion_survive_hidden_widgets_and_switches(self):
        self.initialize()
        self.evaluate("timerWitness = contentItem.children.find(item => item.objectName === 'dock').pomodoro", self.window)
        self.evaluate("pomodoro.toggle()")
        deadline = self.config.property("timerDeadline")
        self.assertTrue(self.command("commitPresentation", {"widgets": self.widgets(False)}))
        self.assertTrue(self.command("select", "personal"))
        self.assertTrue(self.command("select", "work"))
        self.assertTrue(self.evaluate("timerWitness === contentItem.children.find(item => item.objectName === 'dock').pomodoro", self.window))
        self.assertEqual(self.config.property("timerDeadline"), deadline)
        self.assertTrue(self.evaluate("pomodoro.running"))
        self.evaluate("pomodoro.poll(configuration.timerDeadline + 1); pomodoro.poll(Date.now())")
        self.assertEqual(self.config.property("completedFocus"), 1)
        self.assertTrue(self.command("select", "games"))
        self.evaluate("pomodoro.poll(Date.now())")
        self.assertEqual(self.config.property("completedFocus"), 1)

    def test_managed_lifecycle_preserves_flat_preferences_and_reload_restores_selector(self):
        self.config.setProperty("appearanceJSON", '{"unknown":"preserve raw"}')
        before = self.flat()
        self.initialize()
        self.assertTrue(self.command("commitPresentation", {"widgets": self.widgets(False, True), "appearance": {"theme": "paper"}, "calendarEvents": True, "currentDesktopOnly": True}))
        self.assertTrue(self.command("create", "Meu perfil"))
        custom = self.evaluate("profiles.activeProfileId")
        self.assertTrue(self.command("select", "legacy"))
        self.assertEqual(self.flat(), before)
        self.assertTrue(self.command("select", custom))
        self.assertTrue(self.command("commitPresentation", {"calendarEvents": False}))
        raw = self.config.property("profilesJSON")
        self.dispose()
        self.engine = QQmlApplicationEngine()
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.setInitialProperties({"fixtureProfilesJSON": raw})
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ProfilesDockHarness.qml").resolve())))
        self.window = self.engine.rootObjects()[0]
        self.config = self.window.findChild(QObject, "configuration")
        self.dock = self.window.findChild(QQuickItem, "dock")
        self.assertEqual(self.evaluate("profiles.activeProfileId"), custom)
        self.assertEqual(self.evaluate("presentation.appearance.theme"), "paper")
        self.assertFalse(self.evaluate("presentation.calendarEvents"))
        self.assertEqual(self.config.property("profilesJSON"), raw)

    def test_launchers_edit_active_profile_only_preserve_missing_and_reject_stale_context(self):
        self.initialize()
        missing = "applications:owned-missing-app.desktop"
        self.assertTrue(self.command("commitPresentation", {"launchers": [missing, "applications:org.kde.dolphin.desktop", "applications:org.kde.konsole.desktop"]}))
        scope = self.evaluate("profiles.activeProfileId"); revision = self.evaluate("profiles.revision")
        self.assertTrue(self.evaluate("addLauncher('systemsettings.desktop')"))
        work = json.loads(self.config.property("profilesJSON"))["profiles"][0]
        self.assertIn(missing, work["launchers"])
        self.assertIn("applications:systemsettings.desktop", work["launchers"])
        self.assertTrue(self.command("select", "personal"))
        saved = self.config.property("profilesJSON")
        self.assertFalse(self.evaluate(f"addLauncher('systemsettings.desktop',{json.dumps(scope)},{revision})"))
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.assertEqual(self.evaluate("JSON.stringify(Array.from(tasksModel.launcherList))"), json.dumps(["applications:org.kde.dolphin.desktop", "applications:org.kde.konsole.desktop"], separators=(",", ":")))

    def test_legacy_pretty_decoded_desktop_can_be_captured_and_removed_in_managed_profile(self):
        with tempfile.TemporaryDirectory(prefix="legacy-", dir=Path(__file__).resolve().parents[1] / ".runtime/profiles-dock") as directory:
            desktop = Path(directory) / "Legacy App.desktop"
            desktop.write_text("[Desktop Entry]\nType=Application\nName=Owned Legacy Fixture\nExec=/usr/bin/true\n", encoding="utf-8")
            pretty = QUrl.fromLocalFile(str(desktop)).toString()
            self.config.setProperty("launchers", [pretty])
            before = self.flat()
            self.initialize()
            self.assertEqual(self.evaluate("presentation.launchers[0]"), pretty)
            self.assertTrue(self.command("create", "Legacy clone"))
            self.assertTrue(self.evaluate("removeLauncher(" + json.dumps(pretty) + ")"))
            self.assertEqual(self.evaluate("presentation.launchers.length"), 0)
            self.assertEqual(self.flat(), before)
            self.assertTrue(self.command("select", "legacy"))
            self.assertEqual(self.evaluate("presentation.launchers[0]"), pretty)
            self.assertEqual(self.flat(), before)

    def test_widget_visibility_keyboard_keeps_focus_after_repeater_replacement(self):
        self.initialize()
        self.evaluate("open()", self.popup); QTest.qWait(30)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        checkbox = self.owned_item("widgetVisibleclock")
        self.focus(checkbox); QTest.keyClick(self.window, Qt.Key_Space); QTest.qWait(30)
        self.assertFalse(self.evaluate("presentation.widgets[0].visible"))
        self.assertEqual(self.window.activeFocusItem().objectName(), "widgetVisibleclock")
        QTest.keyClick(self.window, Qt.Key_Space); QTest.qWait(30)
        self.assertTrue(self.evaluate("presentation.widgets[0].visible"))
        self.assertEqual(self.window.activeFocusItem().objectName(), "widgetVisibleclock")

    def test_optional_module_discovery_preserves_profiles_and_uses_existing_widget_toggle(self):
        self.initialize()
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        QTest.qWait(30)
        original = self.config.property("profilesJSON")
        details = self.owned_item("moduleDetailsquota")
        self.assertIsNotNone(details)
        disclosure = details.findChild(QQuickItem, "moduleDisclosure")
        self.focus(disclosure)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        self.assertTrue(details.findChild(QQuickItem, "moduleStatus").isVisible())
        viewport = self.owned_item("widgetScroll").property("contentItem")
        for name in ("moduleDescription", "moduleStatus", "moduleRequirements"):
            label = details.findChild(QQuickItem, name)
            point = label.mapToItem(viewport, QPointF(0, 0))
            self.assertGreaterEqual(point.y(), 0)
            self.assertLessEqual(point.y() + label.height(), viewport.height())
        self.assertEqual(details.property("statusText"), "Desativado neste perfil")
        self.assertEqual(self.config.property("profilesJSON"), original)
        self.assertFalse(self.evaluate("integrations.active"))
        checkbox = self.owned_item("widgetVisiblequota")
        self.focus(checkbox)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(30)
        self.assertTrue(self.evaluate("presentation.widgets.find(w => w.id === 'quota').visible"))
        self.assertTrue(self.owned_item("quotaTile").isVisible())
        self.assertEqual(self.evaluate("JSON.stringify(integrations.enabledModules)"), '["quota"]')
        self.assertEqual(self.window.activeFocusItem().objectName(), "widgetVisiblequota")
        after = json.loads(self.config.property("profilesJSON"))
        expected = json.loads(original)
        expected["profiles"][0]["widgets"][4]["visible"] = True
        self.assertEqual(after, expected)
        self.evaluate("integrations.snapshot=({quota:{status:'stale',windows:[],costs:[]},peripherals:{status:'missing',devices:[]},recording:{status:'missing',state:'unknown'}})")
        self.assertEqual(self.owned_item("moduleDetailsquota").property("statusText"), "Dados desatualizados")
        checkbox = self.owned_item("widgetVisiblequota")
        self.focus(checkbox)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(30)
        self.assertEqual(json.loads(self.config.property("profilesJSON")), json.loads(original))
        self.assertFalse(self.owned_item("quotaTile").isVisible())
        self.assertEqual(self.evaluate("JSON.stringify(integrations.enabledModules)"), '[]')
        self.assertEqual(self.window.activeFocusItem().objectName(), "widgetVisiblequota")

    def test_expanded_optional_module_keeps_its_header_as_a_drag_destination(self):
        self.initialize()
        self.popup.setProperty("width", 420)
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        QTest.qWait(30)
        details = self.owned_item("moduleDetailsquota")
        self.focus(details.findChild(QQuickItem, "moduleDisclosure"))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        grip = self.owned_item("widgetDragclock")
        target = self.owned_item("widgetDragquota")
        self.focus(grip)
        QTest.qWait(30)
        start = grip.mapToScene(QPointF(grip.width() / 2, grip.height() / 2)).toPoint()
        end = target.mapToScene(QPointF(target.width() / 2, target.height() * .75)).toPoint()
        original = self.config.property("profilesJSON")
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start)
        try:
            QTest.mouseMove(self.window, end, 30)
            QTest.qWait(20)
            self.assertTrue(self.owned_item("widgetDropIndicatorquota").isVisible())
            self.assertEqual(self.config.property("profilesJSON"), original)
            QTest.keyClick(self.window, Qt.Key_Escape)
        finally:
            QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, end)
        self.assertEqual(self.config.property("profilesJSON"), original)

    def test_encoded_owned_desktop_urls_add_move_and_remove_without_normalizing_saved_bytes(self):
        if self.app.platformName() == "offscreen":
            self.skipTest("TaskManager needs a Wayland or X11 connection")
        self.initialize()
        with tempfile.TemporaryDirectory(prefix="desktop-", dir=Path(__file__).resolve().parents[1] / ".runtime/profiles-dock") as directory:
            desktop = Path(directory) / "My Ação %20 App.desktop"
            desktop.write_text("[Desktop Entry]\nType=Application\nName=Owned URL Fixture\nExec=/usr/bin/true\nIcon=application-x-executable\n", encoding="utf-8")
            url = QUrl.fromLocalFile(str(desktop)).toString(QUrl.FullyEncoded)
            self.assertTrue(self.evaluate("addLauncher(" + json.dumps(url) + ")"))
            self.assertEqual(self.evaluate("presentation.launchers[2]"), url)
            self.settle(lambda: self.evaluate("tasksModel.count") == 3)
            self.assertTrue(self.evaluate("moveTask(2,0)"))
            self.assertEqual(self.evaluate("presentation.launchers[0]"), url)
            self.assertTrue(self.evaluate("removeLauncher(" + json.dumps(url) + ")"))
            self.assertNotIn(url, json.loads(self.evaluate("JSON.stringify(presentation.launchers)")))
            aliases = [url, url.replace("My%20", "%4Dy%20"), "applications:org.kde.dolphin.desktop"]
            self.assertTrue(self.command("commitPresentation", {"launchers": aliases}))
            self.settle(lambda: self.evaluate("tasksModel.count") == 2)
            self.assertTrue(self.evaluate("moveTask(1,0)"))
            self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.launchers)")), [aliases[2], aliases[0], aliases[1]])
            self.assertTrue(self.evaluate("removeLauncher(" + json.dumps(url) + ")"))
            self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.launchers)")), [aliases[2]])
            self.assertEqual(self.warnings, [])

    def test_encoded_owned_desktop_urls_preserve_saved_bytes_and_remove_equivalent_aliases_portably(self):
        self.initialize()
        with tempfile.TemporaryDirectory(prefix="desktop-", dir=Path(__file__).resolve().parents[1] / ".runtime/profiles-dock") as directory:
            desktop = Path(directory) / "My Ação %20 App.desktop"
            desktop.write_text("[Desktop Entry]\nType=Application\nName=Owned URL Fixture\nExec=/usr/bin/true\nIcon=application-x-executable\n", encoding="utf-8")
            url = QUrl.fromLocalFile(str(desktop)).toString(QUrl.FullyEncoded)
            original = json.loads(self.evaluate("JSON.stringify(presentation.launchers)"))
            self.assertTrue(self.evaluate("addLauncher(" + json.dumps(url) + ")"))
            added = original + [url]
            self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.launchers)")), added)
            saved = json.loads(self.config.property("profilesJSON"))
            work = next(profile for profile in saved["profiles"] if profile["id"] == "work")
            self.assertEqual(work["launchers"], added)
            aliases = [url, url.replace("My%20", "%4Dy%20"), "applications:org.kde.dolphin.desktop"]
            self.assertTrue(self.command("commitPresentation", {"launchers": aliases}))
            self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.launchers)")), aliases)
            saved = json.loads(self.config.property("profilesJSON"))
            work = next(profile for profile in saved["profiles"] if profile["id"] == "work")
            self.assertEqual(work["launchers"], aliases)
            self.assertTrue(self.evaluate("removeLauncher(" + json.dumps(url) + ")"))
            self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.launchers)")), [aliases[2]])
            saved = json.loads(self.config.property("profilesJSON"))
            work = next(profile for profile in saved["profiles"] if profile["id"] == "work")
            self.assertEqual(work["launchers"], [aliases[2]])
            self.assertEqual(self.warnings, [])

    def test_fixed_widget_order_has_no_hidden_gaps_and_battery_only_keeps_divider(self):
        self.initialize()
        self.assertTrue(self.command("commitPresentation", {"widgets": self.widgets(True, True)}))
        strip = self.window.findChild(QQuickItem, "widgetStrip")
        self.assertEqual(self.evaluate("children.filter(item => item.visible && item.objectName.endsWith('Tile') || item.visible && item.objectName === 'pomodoroButton').map(item => item.objectName).join(',')", strip), "recordingTile,peripheralsTile,quotaTile,systemBatteryTile,musicTile,pomodoroButton,clockTile")
        self.assertTrue(self.command("commitPresentation", {"widgets": self.widgets(False)}))
        self.assertFalse(strip.property("visible"))
        self.assertFalse(self.window.findChild(QQuickItem, "widgetDivider").property("visible"))
        self.assertTrue(self.window.findChild(QQuickItem, "settingsButton").property("visible"))
        self.assertTrue(self.window.findChild(QQuickItem, "addButton").property("visible"))
        battery_only = self.widgets(False); battery_only[3]["visible"] = True
        self.assertTrue(self.command("commitPresentation", {"widgets": battery_only}))
        self.assertTrue(self.window.findChild(QQuickItem, "widgetDivider").property("visible"))
        self.assertEqual(self.evaluate("children.filter(item => item.objectName === 'systemBatteryTile')[0].x", strip), 0)
        strip.ensurePolished()
        self.assertEqual(strip.property("implicitWidth"), 50)  # one live icon slot

    def test_selector_keyboard_is_pending_until_use_and_focus_reveals_at_420_height(self):
        self.assertTrue(self.evaluate("profiles.initializeDefaults(profiles.activeProfileId,profiles.revision)"))
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        QTest.qWait(30)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 2)
        selector = self.window.findChild(QQuickItem, "profileSelector")
        self.focus(selector)
        saved = self.config.property("profilesJSON")
        QTest.keyClick(self.window, Qt.Key_Down)
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "legacy")
        self.assertEqual(self.config.property("profilesJSON"), saved)
        use = self.window.findChild(QQuickItem, "profileUse")
        self.assertTrue(use.property("enabled"))
        self.focus(use); QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(self.evaluate("profiles.activeProfileId"), "work")
        name = self.window.findChild(QQuickItem, "profileName")
        name.setProperty("text", "Novo")
        create = self.window.findChild(QQuickItem, "profileCreate")
        self.focus(create)
        ancestor = create.parentItem()
        while ancestor is not None and ancestor.property("contentY") is None:
            ancestor = ancestor.parentItem()
        self.assertIsNotNone(ancestor)
        point = create.mapToItem(ancestor, QPointF(0, 0))
        self.assertGreaterEqual(point.y(), 0)
        self.assertLessEqual(point.y() + create.height(), ancestor.height() + 1)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertNotIn(self.evaluate("profiles.activeProfileId"), ["legacy", "work", "personal", "games"])
        self.assertEqual(self.warnings, [])

    def test_widget_drag_saves_once_on_release_and_preserves_other_profile_data(self):
        self.initialize()
        start, end = self.widget_drag_points()
        self.evaluate("appearance.setToken('radius',8)")
        self.assertTrue(self.evaluate("appearance.dirty"))
        original_raw = self.config.property("profilesJSON")
        original = json.loads(original_raw)
        flat = self.flat()
        writes = QSignalSpy(self.config.profilesJSONChanged)
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start)
        try:
            QTest.mouseMove(self.window, end, 30)
            QTest.qWait(20)
            indicator = self.owned_item("widgetDropIndicatorpomodoro")
            self.assertIsNotNone(indicator)
            self.assertTrue(indicator.property("visible"), "Held drag must show its destination")
            self.assertEqual(self.config.property("profilesJSON"), original_raw)
            self.assertEqual(writes.count(), 0, "Moving must not write the profile")
        finally:
            QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, end)
        self.settle(lambda: writes.count() == 1)
        self.settle(lambda: self.window.activeFocusItem() is not None
                    and self.window.activeFocusItem().objectName() == "widgetDragclock")
        saved = json.loads(self.config.property("profilesJSON"))
        old_work = next(p for p in original["profiles"] if p["id"] == "work")
        new_work = next(p for p in saved["profiles"] if p["id"] == "work")
        expected = [old_work["widgets"][1], old_work["widgets"][0], *old_work["widgets"][2:]]
        self.assertEqual(new_work["widgets"], expected)
        self.assertEqual({k: v for k, v in old_work.items() if k != "widgets"},
                         {k: v for k, v in new_work.items() if k != "widgets"})
        self.assertEqual([p for p in saved["profiles"] if p["id"] != "work"],
                         [p for p in original["profiles"] if p["id"] != "work"])
        self.assertEqual(saved["activeProfileId"], "work")
        self.assertEqual(self.flat(), flat)
        self.assertTrue(self.evaluate("appearance.dirty"))
        self.assertLess(self.owned_item("pomodoroButton").x(), self.owned_item("clockTile").x())
        self.assertEqual(writes.count(), 1)
        self.assertEqual(self.warnings, [])

    def test_widget_drag_restores_grip_focus_after_delegate_rebuild(self):
        self.initialize()
        start, end = self.widget_drag_points()
        writes = QSignalSpy(self.config.profilesJSONChanged)
        QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start)
        try:
            QTest.mouseMove(self.window, end, 30)
        finally:
            QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, end)
        self.settle(lambda: writes.count() == 1)
        self.settle(lambda: self.window.activeFocusItem() is not None
                    and self.window.activeFocusItem().objectName() == "widgetDragclock")
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(presentation.widgets.slice(0,2).map(w=>w.id))")),
                         ["pomodoro", "clock"])
        self.assertEqual(self.warnings, [])

    def test_widget_drag_commit_preserves_newer_unrelated_focus(self):
        self.initialize()
        start, end = self.widget_drag_points()
        tabs = self.window.findChild(QObject, "settingsTabs")
        original_raw = self.config.property("profilesJSON")
        original = json.loads(original_raw)
        newer_focus = self.evaluate("itemAt(1)", tabs)
        self.assertIsNotNone(newer_focus)
        self.assertTrue(newer_focus.isVisible())
        self.assertTrue(newer_focus.isEnabled())
        writes = QSignalSpy(self.config.profilesJSONChanged)
        focus_changes = []

        def newer_focus_during_write():
            # Do not process events/reenter the writer inside this synchronous
            # signal callback. This tab survives rebuilding the widget delegates.
            newer_focus.forceActiveFocus(Qt.OtherFocusReason)
            focus_changes.append(self.window.activeFocusItem() == newer_focus)

        self.config.profilesJSONChanged.connect(newer_focus_during_write)
        try:
            QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start)
            try:
                QTest.mouseMove(self.window, end, 30)
                QTest.qWait(20)
                self.assertTrue(self.owned_item("widgetDropIndicatorpomodoro").property("visible"))
                self.assertEqual(self.config.property("profilesJSON"), original_raw)
                self.assertEqual(writes.count(), 0)
            finally:
                QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, end)
            self.settle(lambda: writes.count() == 1)
            # Drain the queued delegate rebuild/focus-restoration work only
            # AFTER the writer has returned, without focusing anything again.
            QTest.qWait(40)
            self.app.processEvents()
            self.assertEqual(focus_changes, [True])
            self.assertEqual(self.window.activeFocusItem(), newer_focus)
            self.assertEqual(self.evaluate("itemAt(1)", tabs), newer_focus)
            saved = json.loads(self.config.property("profilesJSON"))
            old_work = next(p for p in original["profiles"] if p["id"] == "work")
            new_work = next(p for p in saved["profiles"] if p["id"] == "work")
            self.assertEqual(new_work["widgets"],
                             [old_work["widgets"][1], old_work["widgets"][0], *old_work["widgets"][2:]])
            self.assertEqual({k: v for k, v in new_work.items() if k != "widgets"},
                             {k: v for k, v in old_work.items() if k != "widgets"})
            self.assertEqual([p for p in saved["profiles"] if p["id"] != "work"],
                             [p for p in original["profiles"] if p["id"] != "work"])
            self.assertEqual(saved["activeProfileId"], "work")
            self.assertEqual(writes.count(), 1)
            self.assertEqual(self.warnings, [])
        finally:
            self.config.profilesJSONChanged.disconnect(newer_focus_during_write)

    def test_widget_drag_click_self_outside_and_escape_leave_saved_order_unchanged(self):
        self.initialize()
        for mode in ("click", "self", "outside", "escape"):
            with self.subTest(mode=mode):
                start, end = self.widget_drag_points()
                raw = self.config.property("profilesJSON")
                writes = QSignalSpy(self.config.profilesJSONChanged)
                release = start
                QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start)
                try:
                    if mode != "click":
                        QTest.mouseMove(self.window, end, 30)
                        QTest.qWait(20)
                        self.assertTrue(self.owned_item("widgetDropIndicatorpomodoro").property("visible"))
                        release = end
                    if mode == "self":
                        release = start
                        QTest.mouseMove(self.window, release, 20)
                    elif mode == "outside":
                        scroll = self.owned_item("widgetScroll")
                        release = scroll.mapToScene(QPointF(scroll.width() + 8, scroll.height() / 2)).toPoint()
                        QTest.mouseMove(self.window, release, 20)
                    elif mode == "escape":
                        QTest.keyClick(self.window, Qt.Key_Escape)
                        self.assertTrue(self.popup.property("visible"), "First Escape cancels only the held gesture")
                        self.assertFalse(self.owned_item("widgetDropIndicatorpomodoro").property("visible"))
                finally:
                    QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, release)
                QTest.qWait(20)
                self.assertEqual(self.config.property("profilesJSON"), raw)
                self.assertEqual(writes.count(), 0)
                self.assertFalse(self.owned_item("widgetDropIndicatorpomodoro").property("visible"))
                if mode == "escape":
                    QTest.keyClick(self.window, Qt.Key_Escape)
                    self.settle(lambda: not self.popup.property("visible"))
        self.assertEqual(self.warnings, [])

    def test_widget_drag_invalidated_while_held_never_writes_a_stale_order(self):
        self.initialize()
        original = self.config.property("profilesJSON")
        for mode in ("scope", "revision", "import", "readonly", "tab", "close"):
            with self.subTest(mode=mode):
                if self.popup.property("visible"):
                    closed = QSignalSpy(self.popup.closed)
                    self.evaluate("close()", self.popup)
                    if not closed.count():
                        self.assertTrue(closed.wait(1000))
                self.config.setProperty("profilesJSON", original)
                self.evaluate("appearancePreset.clearInput()")
                start, end = self.widget_drag_points()
                self.assertTrue(self.evaluate("appearance.editing"))
                writes = QSignalSpy(self.config.profilesJSONChanged)
                QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, start)
                try:
                    QTest.mouseMove(self.window, end, 30)
                    QTest.qWait(20)
                    self.assertTrue(self.owned_item("widgetDropIndicatorpomodoro").property("visible"))
                    self.assertEqual(writes.count(), 0)
                    if mode == "scope":
                        self.assertTrue(self.command("select", "personal"))
                    elif mode == "revision":
                        self.assertTrue(self.evaluate("profiles.commitPresentation({calendarEvents:true},profiles.activeProfileId,profiles.revision)"))
                    elif mode == "import":
                        self.evaluate("appearancePreset.setInputText('{pending}')")
                        self.assertTrue(self.evaluate("appearancePreset.pending"))
                    elif mode == "readonly":
                        self.config.setProperty("profilesJSON", '{"formatVersion":999}')
                    elif mode == "tab":
                        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 0)
                    else:
                        self.evaluate("close()", self.popup)
                    expected_raw = self.config.property("profilesJSON")
                    expected_writes = writes.count()
                finally:
                    QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, end)
                QTest.qWait(30)
                self.assertEqual(self.config.property("profilesJSON"), expected_raw)
                self.assertEqual(writes.count(), expected_writes, "Invalidated release cannot add a profile write")
        self.assertEqual(self.warnings, [])

    def test_widget_drag_cannot_initialize_legacy_or_write_a_readonly_profile(self):
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup)
        self.window.findChild(QObject, "settingsTabs").setProperty("currentIndex", 1)
        QTest.qWait(30)
        self.focus(self.owned_item("widgetVisibleclock"))
        for mode in ("legacy", "readonly"):
            with self.subTest(mode=mode):
                if mode == "readonly":
                    self.config.setProperty("profilesJSON", '{"formatVersion":999}')
                grip = self.owned_item("widgetDragclock")
                self.assertFalse(grip.isEnabled())
                self.assertFalse(self.owned_item("widgetDownclock").isEnabled())
                raw = self.config.property("profilesJSON")
                flat = self.flat()
                writes = QSignalSpy(self.config.profilesJSONChanged)
                point = grip.mapToScene(QPointF(grip.width() / 2, grip.height() / 2)).toPoint()
                QTest.mousePress(self.window, Qt.LeftButton, Qt.NoModifier, point)
                QTest.mouseMove(self.window, point + QPointF(0, 45).toPoint(), 30)
                QTest.mouseRelease(self.window, Qt.LeftButton, Qt.NoModifier, point)
                self.assertEqual(self.config.property("profilesJSON"), raw)
                self.assertEqual(self.flat(), flat)
                self.assertEqual(writes.count(), 0)
        self.assertEqual(self.warnings, [])

    def test_widget_reorder_keyboard_and_appearance_draft_survive_tabs(self):
        self.initialize()
        self.popup.setProperty("heightBudget", 420)
        self.evaluate("open()", self.popup); QTest.qWait(30)
        self.evaluate("appearance.setToken('radius',8)")
        tabs = self.window.findChild(QObject, "settingsTabs")
        tabs.setProperty("currentIndex", 1)
        button = self.owned_item("widgetDownclock")
        self.focus(button); QTest.keyClick(self.window, Qt.Key_Space); QTest.qWait(30)
        self.assertEqual(self.evaluate("presentation.widgets[1].id"), "clock")
        self.assertEqual(self.window.activeFocusItem().objectName(), "widgetDownclock")
        self.assertTrue(self.evaluate("appearance.dirty"))
        tabs.setProperty("currentIndex", 2)
        self.assertFalse(self.window.findChild(QObject, "profileUse").property("enabled"))
        self.assertIn("Aparência", self.window.findChild(QObject, "profileStatus").property("text"))
        tabs.setProperty("currentIndex", 0)
        apply = self.window.findChild(QQuickItem, "appearanceApply")
        self.focus(apply); QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(self.evaluate("presentation.widgets[1].id"), "clock")
        self.assertFalse(self.evaluate("appearance.dirty"))
        self.assertEqual(self.warnings, [])



if __name__ == "__main__":
    unittest.main()
