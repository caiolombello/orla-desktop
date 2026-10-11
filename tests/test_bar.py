import os
import time
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Property, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class FixtureSession(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.values = dict(status="ready", canLock=True, canSuspend=True,
                           canLogout=True, canReboot=True, canShutdown=True)
        self.calls = []

    def update(self, **values):
        self.values.update(values)
        self.changed.emit()

    status = Property(str, lambda self: self.values["status"], notify=changed)
    canLock = Property(bool, lambda self: self.values["canLock"], notify=changed)
    canSuspend = Property(bool, lambda self: self.values["canSuspend"], notify=changed)
    canLogout = Property(bool, lambda self: self.values["canLogout"], notify=changed)
    canReboot = Property(bool, lambda self: self.values["canReboot"], notify=changed)
    canShutdown = Property(bool, lambda self: self.values["canShutdown"], notify=changed)

    @Slot()
    def lock(self):
        self.calls.append("lock")

    @Slot()
    def suspend(self):
        self.calls.append("suspend")

    @Slot()
    def requestLogout(self):
        self.calls.append("logout")

    @Slot()
    def requestReboot(self):
        self.calls.append("reboot")

    @Slot()
    def requestShutdown(self):
        self.calls.append("shutdown")

    @Slot(str)
    def open(self, kind):
        self.calls.append(kind)


class FixtureApplication(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.name = "Aplicativo sintético"
        self.active = True

    appName = Property(str, lambda self: self.name, notify=changed)
    hasActiveApplication = Property(bool, lambda self: self.active, notify=changed)


class BarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.session = FixtureSession()
        self.application = FixtureApplication()
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.rootContext().setContextProperty("fixtureSession", self.session)
        self.engine.rootContext().setContextProperty("fixtureApplication", self.application)
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("BarHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.bar = self.window.findChild(QQuickItem, "barUnderTest")
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
        expression = QQmlExpression(self.engine.rootContext(), target or self.bar, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def wait_property(self, target, name, expected):
        deadline = time.monotonic() + 1.0
        while target.property(name) != expected and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertEqual(target.property(name), expected, name)

    def test_loading_and_unavailable_never_dispatch_session_actions(self):
        for status in ("loading", "unavailable"):
            self.session.update(status=status)
            for action in ("lock", "suspend", "logout", "reboot", "shutdown"):
                self.assertFalse(self.evaluate(f"requestSession('{action}')"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


    def item(self, name):
        result = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(result, name)
        return result

    def test_menu_navigation_is_passive_and_explicit_actions_recheck_capabilities(self):
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        for key in (Qt.Key_Down, Qt.Key_Down, Qt.Key_Up):
            QTest.keyClick(self.window, key)
        self.assertEqual(self.session.calls, [])
        self.session.update(canReboot=False)
        self.assertFalse(self.item("sessionReboot").property("enabled"))
        self.assertFalse(self.evaluate("requestSession('reboot')"))
        for action in ("lock", "suspend", "logout", "shutdown"):
            self.assertTrue(self.evaluate(f"requestSession('{action}')"))
        self.assertEqual(self.session.calls, ["lock", "suspend", "logout", "shutdown"])
        self.session.update(canReboot=True)
        self.assertTrue(self.evaluate("requestSession('reboot')"))
        self.assertEqual(self.session.calls[-1], "reboot")
        self.assertFalse(self.evaluate("requestSession('arbitrary')"))
        self.assertEqual(self.warnings, [])


    def test_application_and_button_names_are_plain_bounded_and_optional(self):
        self.application.name = "<b>" + "X" * 5000 + "\nPrivate document title"
        self.application.changed.emit()
        title = self.item("activeApplicationName")
        self.assertLessEqual(len(title.property("text")), 160)
        self.assertEqual(self.evaluate("textFormat", title), 0)
        self.evaluate("menuLabel = '<b>' + 'X'.repeat(5000)")
        self.assertLessEqual(len(self.item("orlaMenuButton").property("text")), 32)
        self.evaluate("showApplicationName = false")
        self.assertFalse(title.property("visible"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


    def test_menu_items_dispatch_their_own_action_and_revoked_actions_stay_passive(self):
        for name, action, capability in (("sessionLock", "lock", "canLock"),
                ("sessionSuspend", "suspend", "canSuspend"),
                ("sessionLogout", "logout", "canLogout"),
                ("sessionReboot", "reboot", "canReboot"),
                ("sessionShutdown", "shutdown", "canShutdown")):
            self.session.calls.clear()
            self.evaluate("triggered()", self.item(name))
            self.assertEqual(self.session.calls, [action])
            self.session.update(**{capability: False})
            self.evaluate("triggered()", self.item(name))
            self.assertEqual(self.session.calls, [action])
            self.session.update(**{capability: True})
        self.assertEqual(self.warnings, [])

    def test_links_are_explicit_and_about_does_not_open_external_applications(self):
        self.evaluate("triggered()", self.item("aboutOrla"))
        self.assertEqual(self.session.calls, [])
        for name, expected in (("aboutSystem", "system"), ("systemSettings", "settings"), ("configureBar", "configure")):
            self.evaluate("triggered()", self.item(name))
            self.assertEqual(self.session.calls[-1], expected)
        self.assertFalse(self.evaluate("open('arbitrary command')"))
        self.assertEqual(self.session.calls, ["system", "settings", "configure"])
        self.assertEqual(self.warnings, [])

    def test_mock_backends_prevent_native_adapters_even_on_a_supported_host(self):
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertEqual(self.bar.property("sessionStatus"), "ready")
        self.evaluate("hostVersion = '6.8.0'; sessionBackend = null; applicationBackend = null")
        self.assertEqual(self.bar.property("sessionStatus"), "unavailable")
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertFalse(self.evaluate("requestSession('shutdown')"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])

    def test_transport_error_is_visible_without_optimistic_success(self):
        self.evaluate("sessionBackend = ({status: 'ready', canShutdown: true, requestShutdown: function() { throw new Error('private receiver details'); }})")
        self.assertFalse(self.evaluate("requestSession('shutdown')"))
        self.assertIn("Não foi possível", self.bar.property("actionError"))
        self.assertTrue(self.item("sessionActionError").property("visible"))
        self.assertNotIn("private receiver", self.bar.property("actionError"))
        self.assertEqual(self.session.calls, [])
        self.evaluate("sessionBackend = fixtureSession")
        self.assertEqual(self.bar.property("actionError"), "")
        self.assertTrue(self.evaluate("requestSession('shutdown')"))
        self.assertEqual(self.session.calls, ["shutdown"])
        self.assertEqual(self.bar.property("sessionStatus"), "ready")
        self.assertEqual(self.bar.property("actionError"), "")
        self.assertEqual(self.warnings, [])

    def test_escape_closes_the_menu_without_dispatch_and_returns_to_button(self):
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.window, Qt.Key_Space)
        menu = self.window.findChild(QObject, "orlaMenu")
        self.wait_property(menu, "opened", True)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.wait_property(menu, "visible", False)
        self.wait_property(button, "activeFocus", True)
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


    def test_application_name_is_preserved_from_menu_entry_until_closed(self):
        menu = self.window.findChild(QObject, "orlaMenu")
        self.evaluate("enter = Qt.createQmlObject('import QtQuick; Transition { PauseAnimation { duration: 120 } }', this)", menu)
        self.evaluate("exit = Qt.createQmlObject('import QtQuick; Transition { PauseAnimation { duration: 120 } }', this)", menu)
        # A focus change can occur before opened becomes true. The signal is
        # emitted by real Menu.open(); the boundary remains our synthetic source.
        def lose_active_application():
            self.application.active = False
            self.application.name = ""
            self.application.changed.emit()
        menu.aboutToShow.connect(lose_active_application)
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertFalse(menu.property("opened"))
        self.assertEqual(self.item("activeApplicationName").property("text"), "Aplicativo sintético")
        self.wait_property(menu, "opened", True)
        self.application.active = True
        self.application.name = "Segundo aplicativo"
        self.application.changed.emit()
        self.assertEqual(self.item("activeApplicationName").property("text"), "Aplicativo sintético")
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.assertEqual(self.item("activeApplicationName").property("text"), "Aplicativo sintético")
        self.wait_property(menu, "visible", False)
        self.assertEqual(self.item("activeApplicationName").property("text"), "Segundo aplicativo")
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


    def test_active_unnamed_and_whitespace_apps_are_distinct_from_no_active_app(self):
        title = self.item("activeApplicationName")
        self.application.active = True
        for name in ("", " \t\n ", " " * 500):
            self.application.name = name
            self.application.changed.emit()
            self.assertEqual(title.property("text"), "Aplicativo")
        self.application.name = "  Aplicativo real  "
        self.application.changed.emit()
        self.assertEqual(title.property("text"), "Aplicativo real")
        # An idle source must not show an obsolete name from its previous task.
        self.application.active = False
        self.application.changed.emit()
        self.assertEqual(title.property("text"), "Área de trabalho")
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
