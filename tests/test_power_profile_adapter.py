"""NativePowerProfile.qml against an engine-private fake of Plasma's D-Bus QML module.

The fake reproduces the module's reply shapes seen on Plasma 6.7: strings arrive
wrapped as {value} objects and lists as array-like sequences that fail
Array.isArray. No session bus, KDE module or PowerDevil is used.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtCore import QCoreApplication, QEvent, QLibraryInfo, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtTest import QSignalSpy, QTest

UI = Path(__file__).resolve().parents[1] / "package/contents/ui"
PATH = "/org/kde/Solid/PowerManagement/Actions/PowerProfile"
IFACE = "org.kde.Solid.PowerManagement.Actions.PowerProfile"

FAKE = {
    "qmldir": "module org.kde.plasma.workspace.dbus\n"
              "singleton SessionBus 1.0 SessionBus.qml\n"
              "BusType 1.0 BusType.qml\n"
              "DBusServiceWatcher 1.0 DBusServiceWatcher.qml\n"
              "SignalWatcher 1.0 SignalWatcher.qml\n",
    "BusType.qml": "import QtQml\nQtObject { enum Type { Session, System } }\n",
    "SessionBus.qml": """pragma Singleton
import QtQml
QtObject {
    readonly property string ownedFake: "orla-power-profile-test-only"
    property bool registered: true
    property var calls: []
    property var watchers: []
    function asyncCall(message, resolve, reject) {
        calls = calls.concat([{message: message, resolve: resolve, reject: reject}]);
    }
    // Plasma 6.7 shapes: a wrapped string and an array-like list.
    function text(value) { return {value: value}; }
    function sequence(items) {
        const out = {length: items.length};
        for (let index = 0; index < items.length; ++index) out[index] = items[index];
        return out;
    }
    // The newest matching call: earlier rounds may already be stale.
    function find(member, from) {
        for (let index = calls.length - 1; index >= (from || 0); --index)
            if (calls[index].message.member === member) return index;
        return -1;
    }
    function reply(index, value) { calls[index].resolve({value: value, values: [value]}); }
    function fail(index) { calls[index].reject({error: {isValid: true, name: "org.freedesktop.DBus.Error.UnknownObject", message: "synthetic"}}); }
    function emit(member, value) {
        for (const watcher of watchers) {
            if (watcher.enabled && watcher.path === "%s" && watcher.iface === "%s") watcher["dbus" + member](value);
        }
    }
}
""" % (PATH, IFACE),
    "DBusServiceWatcher.qml": """import QtQml
QtObject {
    property var busType
    property string watchedService
    readonly property bool registered: SessionBus.registered && watchedService === "org.kde.Solid.PowerManagement"
}
""",
    "SignalWatcher.qml": """import QtQml
QtObject {
    property bool enabled: true
    property var busType
    property string service
    property string path
    property string iface
    Component.onCompleted: SessionBus.watchers = SessionBus.watchers.concat([this])
}
""",
}


class PowerProfileAdapterTests(unittest.TestCase):
    def setUp(self):
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        directory = Path(private.name)
        self.app = QGuiApplication.instance() or QGuiApplication([])
        imports = directory / "imports"
        module = imports / "org/kde/plasma/workspace/dbus"
        module.mkdir(parents=True)
        qt_imports = Path(QLibraryInfo.path(QLibraryInfo.QmlImportsPath))
        for name in ("QtQml", "QtQuick"):
            (imports / name).symlink_to(qt_imports / name, target_is_directory=True)
        for name, text in FAKE.items():
            (module / name).write_text(text)
        self.engine = QQmlEngine()
        self.addCleanup(self.close_engine)
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        # Only Qt and the fake are importable: the native KDE module can never load.
        self.engine.setImportPathList([str(imports)])
        # Kept on the test: a collected component would take its objects with it.
        self.component = component = QQmlComponent(self.engine)
        component.setData(("import QtQuick\nimport " + json.dumps(UI.as_uri()) + " as Candidate\n"
                           "import org.kde.plasma.workspace.dbus as DBus\n"
                           "Item {\n"
                           "    property QtObject bus: DBus.SessionBus\n"
                           "    property QtObject adapter: adapter\n"
                           "    property QtObject profileState: profileState\n"
                           "    Candidate.NativePowerProfile { id: adapter }\n"
                           "    Candidate.PowerProfileState { id: profileState; active: true; backend: adapter; confirmationTimeout: 300 }\n"
                           "}\n").encode(), QUrl.fromLocalFile(str(directory / "Production.qml")))
        self.root = component.create()
        self.assertIsNotNone(self.root, [e.toString() for e in component.errors()])
        self.bus = self.root.property("bus")
        self.assertEqual(self.bus.property("ownedFake"), "orla-power-profile-test-only")
        self.adapter = self.root.property("adapter")
        self.state = self.root.property("profileState")
        self.assertFalse("libdbusplugin.so" in Path("/proc/self/maps").read_text())

    def close_engine(self):
        self.root.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.bus, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def snapshot(self):
        return self.evaluate("snapshot", self.adapter)

    def members(self):
        return self.evaluate("calls.map(call => call.message.member)")

    def load(self, current="balanced", choices=("power-saver", "balanced", "performance")):
        """Answer the initial reads the way Plasma 6.7's module delivers them."""
        self.evaluate("reply(find('profileChoices'), sequence(%s))" % json.dumps(list(choices)))
        self.evaluate("reply(find('currentProfile'), text(%s))" % json.dumps(current))
        self.evaluate("reply(find('performanceInhibitedReason'), text(''))")
        self.evaluate("reply(find('performanceDegradedReason'), text(''))")
        self.evaluate("reply(find('profileHolds'), sequence([]))")

    def test_wrapped_replies_read_as_profiles_and_signals_follow_the_service(self):
        self.assertEqual(self.snapshot(), {"status": "loading"})
        # The current profile is read only after the choices arrive.
        self.assertEqual(set(self.members()), {"profileChoices", "performanceInhibitedReason",
                                               "performanceDegradedReason", "profileHolds"})
        for call in self.evaluate("calls.map(call => call.message)"):
            self.assertEqual((call["service"], call["path"], call["iface"]),
                             ("org.kde.Solid.PowerManagement", PATH, IFACE))
        self.load()
        self.assertEqual(self.snapshot(), {"status": "ready", "profiles": ["power-saver", "balanced", "performance"],
                                           "current": "balanced", "inhibitedReason": "", "degradedReason": "",
                                           "holds": []})
        self.assertEqual(self.state.property("status"), "ready")
        # Signals carry the same wrapped shapes.
        self.evaluate("emit('currentProfileChanged', text('power-saver'))")
        self.evaluate("emit('performanceInhibitedReasonChanged', text('lap-detected'))")
        self.evaluate("emit('profileHoldsChanged', sequence([{ApplicationId: text('com.feralinteractive.GameMode'), "
                      "Profile: text('performance'), Reason: text('game')}]))")
        snapshot = self.snapshot()
        self.assertEqual(snapshot["current"], "power-saver")
        self.assertEqual(snapshot["inhibitedReason"], "lap-detected")
        self.assertEqual(snapshot["holds"], [{"application": "GameMode", "profile": "performance"}])
        self.evaluate("emit('profileChoicesChanged', sequence(['power-saver', 'balanced']))")
        self.assertEqual(self.snapshot()["profiles"], ["power-saver", "balanced"])
        self.evaluate("emit('profileChoicesChanged', sequence([]))")
        self.assertEqual(self.snapshot(), {"status": "absent"})

    def test_a_change_is_confirmed_by_the_service_not_by_the_reply(self):
        self.load()
        confirmed = QSignalSpy(self.state.confirmed)
        self.assertFalse(self.evaluate("setProfile('turbo')", self.adapter))
        self.assertTrue(self.evaluate("request('performance')", self.state))
        index = self.evaluate("find('setProfile')")
        call = self.evaluate("calls[%d].message" % index)
        self.assertEqual((call["signature"], call["arguments"]), ("s", ["performance"]))
        # Accepting the call is not the change: the state keeps waiting.
        self.evaluate("reply(%d, undefined)" % index)
        self.assertTrue(self.state.property("pending"))
        self.assertEqual(self.snapshot()["current"], "balanced")
        # The readback after the reply is a real reading of the service.
        readback = self.evaluate("find('currentProfile', %d)" % index)
        self.assertGreater(readback, index)
        self.evaluate("reply(%d, text('performance'))" % readback)
        self.assertFalse(self.state.property("pending"))
        self.assertEqual(confirmed.count(), 1)
        # A refusal from the service ends the wait with an error.
        self.assertTrue(self.evaluate("request('power-saver')", self.state))
        self.evaluate("fail(find('setProfile', %d))" % (index + 1))
        self.assertFalse(self.state.property("pending"))
        self.assertIn("recusou", self.state.property("error"))
        self.assertEqual(confirmed.count(), 1)

    def test_missing_daemon_service_loss_and_stale_replies(self):
        # Without power-profiles-daemon the action is missing and the choices call fails.
        self.evaluate("fail(find('profileChoices'))")
        self.assertEqual(self.snapshot(), {"status": "absent"})
        # PowerDevil leaving makes the card unavailable; returning reloads.
        self.evaluate("registered = false")
        self.assertEqual(self.snapshot(), {"status": "unavailable"})
        start = len(self.members())
        self.evaluate("registered = true")
        first = self.evaluate("find('profileChoices', %d)" % start)
        self.assertGreaterEqual(first, start)
        # A second reload makes the first round stale; its late answers are ignored.
        self.evaluate("registered = false")
        self.evaluate("registered = true")
        second = self.evaluate("find('profileChoices', %d)" % (first + 1))
        sent = len(self.members())
        self.evaluate("reply(%d, sequence(['power-saver']))" % first)
        self.assertEqual(self.snapshot(), {"status": "loading"})
        # A stale answer does not even start the follow-up read.
        self.assertEqual(len(self.members()), sent)
        self.evaluate("reply(%d, sequence(['balanced', 'performance']))" % second)
        self.evaluate("reply(find('currentProfile', %d), text('performance'))" % second)
        snapshot = self.snapshot()
        self.assertEqual((snapshot["status"], snapshot["profiles"], snapshot["current"]),
                         ("ready", ["balanced", "performance"], "performance"))


if __name__ == "__main__":
    unittest.main()
