"""Presentation-only QML tests; no service, file picker or producer is used."""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QTimer, Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QSignalSpy, QTest
from shiboken6 import isValid


def package(**changes):
    row = dict(id="org.example.battery", sha256="a" * 64, name="Bateria local",
               description="Leituras de bateria compartilhadas pelo aplicativo.",
               author="Projeto Exemplo", license="MIT", version="1.2.0",
               origin="https://example.org/battery", namespace="battery-example",
               enabled=False, state="installed", previousSha256="", valid=True)
    row.update(changes)
    return row


def long_preview():
    return package(sha256="c" * 64, name=("Nome extenso de complemento local " * 3)[:80],
                   description=("Descrição longa mas válida de bateria local. " * 7)[:240])


LOADER_MINIMAL_QML = """
import QtQuick
import "../package/contents/ui" as DockUI
Item {
    Loader {
        objectName: "holder"
        sourceComponent: DockUI.AddonManager {}
    }
}
"""
LOADER_WINDOW_QML = """
import QtQuick
import QtQuick.Controls as Controls
import "../package/contents/ui" as DockUI
import "../package/contents/code/Style.js" as Style
Controls.ApplicationWindow {
 id: window
 width: 350
 height: 360
 visible: true
 property bool gate: false
 property bool pendingLoad: false
 property var previewData: null
 property string schemeName: "dark"
 Controls.ScrollView {
  id: scroll
  anchors.fill: parent
  contentWidth: availableWidth
  clip: true
  Column {
   width: scroll.availableWidth
   padding: Style.space.md
   Loader {
    id: loader
    objectName: "managerLoader"
    width: parent.width-parent.padding*2
    sourceComponent: DockUI.AddonManager {
     objectName: "manager"
     scheme: Style.scheme(window.schemeName)
     busy: window.gate
     loading: window.pendingLoad
     preview: window.previewData
     onRevealRequested: function(control) { window.reveals++ }
    }
   }
   Controls.Button {
    objectName: "newerFocus"
    text: qsTr("Outra opção")
   }
  }
 }
 property int reveals: 0
}
"""


class AddonManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("AddonManagerHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.window.setProperty("schemeName", os.environ.get("ORLA_ADDON_TEST_SCHEME", "dark"))
        self.manager = self.window.findChild(QQuickItem, "addonManager")
        QTest.qWait(40)

    def tearDown(self):
        if hasattr(self, "window"):
            self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def control(self, name):
        def find(item):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                match = find(child)
                if match is not None:
                    return match
            return None
        control = find(self.window.contentItem())
        self.assertIsNotNone(control, name)
        return control

    def press(self, control, key=Qt.Key_Space):
        control.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, key)
        QTest.qWait(30)

    def evaluate(self, target, source):
        expression = QQmlExpression(QQmlEngine.contextForObject(target), target, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def reset_lifetime_case(self):
        self.tearDown()
        self.setUp()
        self.window.setHeight(240)


    def lifetime_spies(self):
        return {n: QSignalSpy(getattr(self.manager, n)) for n in ('chooseFileRequested', 'installRequested', 'enableRequested', 'disableRequested', 'removeRequested', 'rollbackRequested', 'openOriginRequested')}

    def test_reenabled_or_reactivated_scope_needs_fresh_focus_before_reveal(self):
        for change in ('manager-disabled', 'ancestor-disabled', 'actual-window-loss'):
            with self.subTest(change=change):
                self.reset_lifetime_case()
                m, w = (self.manager, self.window)
                m.setProperty('preview', long_preview())
                QTest.qWait(60)
                self.control('outsideFocus').forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(25)
                scroll = self.control('addonScroll')
                self.evaluate(scroll, 'contentItem.contentY=0')
                QTest.qWait(20)
                a = self.control('addonPreviewInstall')
                a.forceActiveFocus(Qt.TabFocusReason)
                other = None
                if change == 'actual-window-loss':
                    m.setProperty('busy', True)
                    other = QQuickWindow()
                    other.resize(100, 100)
                    other.show()
                    other.requestActivate()
                    QTest.qWait(60)
                    self.assertFalse(w.isActive())
                    self.assertTrue(other.isActive())
                    self.assertFalse(m.property('focusOwned'))
                    w.requestActivate()
                    QTest.qWait(50)
                    self.assertTrue(w.isActive())
                    self.evaluate(scroll, 'contentItem.contentY=0')
                    QTest.qWait(20)
                else:
                    target = m if change == 'manager-disabled' else m.parentItem()
                    target.setEnabled(False)
                    self.assertFalse(m.property('focusOwned'))
                events = []
                m.revealRequested.connect(lambda v: events.append(v.objectName()))
                s = self.lifetime_spies()
                if other:
                    m.setProperty('busy', False)
                else:
                    target.setEnabled(True)
                QTest.qWait(120)
                record = dict(case='revoked-auto-rearm', change=change, owned=m.property('focusOwned'), events=events, scrollY=self.evaluate(scroll, 'contentItem.contentY'), visual=a.property('visualFocus'), requests={k: v.count() for k, v in s.items()}, warnings=list(self.warnings))
                pass
                if other:
                    other.close()
                    other.deleteLater()
                self.assertFalse(any((v.count() for v in s.values())))
                self.assertEqual(self.warnings, [])
                self.assertEqual(events, [], 'automatic re-enable has resurrected revoked ownership/reveal work')
                self.assertFalse(m.property('focusOwned'))
                self.assertEqual(record['scrollY'], 0)

    def test_queued_confirmation_cannot_rearm_after_owner_or_parent_revocation(self):
        for action in ('Remove', 'Rollback'):
            for change in ('owner', 'parent'):
                with self.subTest(action=action, change=change):
                    self.reset_lifetime_case()
                    m, w = (self.manager, self.window)
                    m.setProperty('addons', [package(previousSha256='b' * 64)])
                    QTest.qWait(40)
                    self.press(self.control('addonDetails-org.example.battery'), Qt.Key_Return)
                    button = self.control('addon' + action + '-org.example.battery')
                    button.forceActiveFocus(Qt.TabFocusReason)
                    QTest.qWait(45)
                    events = []
                    m.revealRequested.connect(lambda v: events.append(v.objectName()))
                    s = self.lifetime_spies()
                    QCoreApplication.sendEvent(w, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
                    QCoreApplication.sendEvent(w, QKeyEvent(QEvent.KeyRelease, Qt.Key_Return, Qt.NoModifier))
                    self.assertEqual(w.activeFocusItem(), button)
                    temp = None
                    original = m.parentItem()
                    if change == 'owner':
                        self.evaluate(m, 'dock=({})')
                        m.setProperty('dock', None)
                    else:
                        temp = QQuickItem(original)
                        m.setParentItem(temp)
                        m.setParentItem(original)
                    self.assertFalse(m.property('focusOwned'))
                    self.assertEqual(w.activeFocusItem(), button)
                    QTest.qWait(140)
                    record = dict(case='confirmation-revoked', action=action, change=change, owned=m.property('focusOwned'), focus=w.activeFocusItem().objectName(), events=events, requests={k: v.count() for k, v in s.items()}, warnings=list(self.warnings))
                    pass
                    if temp:
                        temp.deleteLater()
                    self.assertFalse(any((v.count() for v in s.values())))
                    self.assertEqual(self.warnings, [])
                    self.assertNotEqual(w.activeFocusItem(), self.control('addonConfirm-org.example.battery'), 'old confirmation callback has moved focus after revocation')
                    self.assertFalse(m.property('focusOwned'))
                    self.assertEqual(events, [])

    def send_return(self):
        QCoreApplication.sendEvent(self.window, QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
        QCoreApplication.sendEvent(self.window, QKeyEvent(QEvent.KeyRelease, Qt.Key_Return, Qt.NoModifier))

    def confirmation_origin(self, action="Remove"):
        self.reset_lifetime_case()
        self.manager.setProperty("addons", [package(previousSha256="b" * 64)])
        QTest.qWait(40)
        self.press(self.control("addonDetails-org.example.battery"), Qt.Key_Return)
        origin = self.control("addon" + action + "-org.example.battery")
        origin.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(40)
        return origin

    def test_confirmation_transfer_checks_reentrant_publication_and_card_parent(self):
        for observed in ("intentSerialChanged", "pendingActionChanged"):
            for change in ("owner", "parent", "card-parent", "intent-aba", "newer-outside"):
                with self.subTest(observed=observed, change=change):
                    origin = self.confirmation_origin()
                    card = self.control("addonCard-org.example.battery")
                    events = QSignalSpy(self.manager.revealRequested)
                    requests = self.lifetime_spies()
                    transitions = []
                    temporary = []
                    def revoke():
                        if transitions:
                            return
                        transitions.append(True)
                        if change == "owner":
                            self.evaluate(self.manager, "dock=({})")
                            self.manager.setProperty("dock", None)
                        elif change in ("parent", "card-parent"):
                            target = card if change == "card-parent" else self.manager
                            parent = target.parentItem()
                            holder = QQuickItem(parent)
                            temporary.append(holder)
                            target.setParentItem(holder)
                            target.setParentItem(parent)
                        elif change == "intent-aba":
                            card.setProperty("pendingAction", "")
                            card.setProperty("pendingAction", "remove")
                        else:
                            self.control("outsideFocus").forceActiveFocus(Qt.TabFocusReason)
                    signal = getattr(card, observed)
                    signal.connect(revoke)
                    self.send_return()
                    self.assertEqual(transitions, [True])
                    QTest.qWait(130)
                    signal.disconnect(revoke)
                    self.assertNotEqual(self.window.activeFocusItem(), self.control("addonConfirm-org.example.battery"))
                    if change == "newer-outside":
                        self.assertEqual(self.window.activeFocusItem(), self.control("outsideFocus"))
                    else:
                        self.assertEqual(self.window.activeFocusItem(), origin)
                    self.assertFalse(any(spy.count() for spy in requests.values()))
                    if change == "intent-aba":
                        self.assertTrue(all(events.at(i)[0].objectName() == origin.objectName() for i in range(events.count())))
                    else:
                        self.assertEqual(events.count(), 0)
                    self.assertEqual(self.warnings, [])
                    for holder in temporary:
                        holder.deleteLater()

    def test_cancel_focus_return_checks_reentrant_revocation(self):
        for change in ("owner", "newer-outside"):
            with self.subTest(change=change):
                self.confirmation_origin()
                self.send_return()
                QTest.qWait(70)
                confirm = self.control("addonConfirm-org.example.battery")
                self.assert_drawn_action_ring(confirm)
                card = self.control("addonCard-org.example.battery")
                transitions = []
                def revoke():
                    if card.property("pendingAction") or transitions:
                        return
                    transitions.append(True)
                    if change == "owner":
                        self.evaluate(self.manager, "dock=({})")
                        self.manager.setProperty("dock", None)
                    else:
                        self.control("outsideFocus").forceActiveFocus(Qt.TabFocusReason)
                card.pendingActionChanged.connect(revoke)
                requests = self.lifetime_spies()
                events = QSignalSpy(self.manager.revealRequested)
                QCoreApplication.sendEvent(self.window, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
                QTest.qWait(100)
                card.pendingActionChanged.disconnect(revoke)
                self.assertEqual(transitions, [True])
                self.assertFalse(self.control("addonRemove-org.example.battery").hasActiveFocus())
                if change == "newer-outside":
                    self.assertEqual(self.window.activeFocusItem(), self.control("outsideFocus"))
                self.assertFalse(any(spy.count() for spy in requests.values()))
                self.assertEqual(events.count(), 0)
                self.assertEqual(self.warnings, [])

    def test_disappeared_action_transfer_checks_reentrant_recovery_clear(self):
        for change in ("owner", "newer-outside"):
            with self.subTest(change=change):
                self.reset_lifetime_case()
                self.manager.setProperty("preview", package())
                QTest.qWait(40)
                self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(40)
                transitions = []
                def revoke():
                    if self.evaluate(self.manager, "pendingRecovery !== null") or transitions:
                        return
                    transitions.append(True)
                    if change == "owner":
                        self.evaluate(self.manager, "dock=({})")
                        self.manager.setProperty("dock", None)
                    else:
                        self.control("outsideFocus").forceActiveFocus(Qt.TabFocusReason)
                self.manager.pendingRecoveryChanged.connect(revoke)
                requests = self.lifetime_spies()
                self.manager.setProperty("preview", None)
                QTest.qWait(130)
                self.manager.pendingRecoveryChanged.disconnect(revoke)
                self.assertEqual(transitions, [True])
                self.assertFalse(self.control("addonChooseFile").hasActiveFocus())
                if change == "newer-outside":
                    self.assertEqual(self.window.activeFocusItem(), self.control("outsideFocus"))
                self.assertFalse(any(spy.count() for spy in requests.values()))
                self.assertEqual(self.warnings, [])

    def test_fresh_native_input_reacquires_revoked_retained_controls(self):
        for kind in ("tab", "pointer", "return", "space", "disclosure"):
            with self.subTest(kind=kind):
                self.reset_lifetime_case()
                self.window.setHeight(360)
                self.manager.setProperty("preview", package(description="Curto."))
                QTest.qWait(40)
                action = self.control("addonDetailsPreview" if kind == "disclosure" else "addonPreviewInstall")
                action.forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(40)
                self.manager.setEnabled(False)
                self.manager.setEnabled(True)
                QTest.qWait(80)
                self.assertFalse(self.manager.property("focusOwned"))
                self.assertEqual(self.window.activeFocusItem(), action)
                requests = self.lifetime_spies()
                if kind == "tab":
                    QTest.keyClick(self.window, Qt.Key_Tab)
                elif kind == "pointer":
                    point = action.mapToScene(QPointF(action.width() / 2, action.height() / 2))
                    self.assertGreaterEqual(point.y(), 0)
                    self.assertLess(point.y(), self.window.height())
                    QTest.mouseClick(self.window, Qt.LeftButton, pos=point.toPoint())
                elif kind == "space":
                    QTest.keyClick(self.window, Qt.Key_Space)
                else:
                    self.send_return()
                QTest.qWait(100)
                self.assertTrue(self.manager.property("focusOwned"))
                if kind in ("pointer", "return", "space"):
                    self.assertEqual(requests["installRequested"].count(), 1)
                    self.assertEqual(requests["installRequested"].at(0), ["a" * 64])
                    self.assertEqual(sum(spy.count() for spy in requests.values()), 1)
                else:
                    self.assertFalse(any(spy.count() for spy in requests.values()))
                    self.assertTrue(self.control("addonDetailsPreview").property("visualFocus"))
                if kind == "disclosure":
                    self.assertTrue(action.property("checked"))
                self.assertEqual(self.warnings, [])

    def test_reentrant_focus_observation_cannot_rearm_changed_owner(self):
        self.manager.setProperty("preview", long_preview())
        QTest.qWait(50)
        self.control("outsideFocus").forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(30)
        self.evaluate(self.control("addonScroll"), "contentItem.contentY=0")
        transitions = []
        def revoke():
            if transitions:
                return
            transitions.append(True)
            self.evaluate(self.manager, "dock=({})")
            self.manager.setProperty("dock", None)
        self.manager.trackedFocusChanged.connect(revoke)
        events = QSignalSpy(self.manager.revealRequested)
        requests = self.lifetime_spies()
        self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(120)
        self.manager.trackedFocusChanged.disconnect(revoke)
        self.assertEqual(transitions, [True])
        self.assertFalse(self.manager.property("focusOwned"))
        self.assertEqual(events.count(), 0)
        self.assertEqual(self.evaluate(self.control("addonScroll"), "contentItem.contentY"), 0)
        self.assertFalse(any(spy.count() for spy in requests.values()))
        self.assertEqual(self.warnings, [])

    def test_queued_confirmation_deleted_delegate_does_not_call_dead_context(self):
        for action in ("Remove", "Rollback"):
            with self.subTest(action=action):
                self.confirmation_origin(action)
                requests = self.lifetime_spies()
                self.send_return()
                self.manager.setProperty("addons", [])
                QTest.qWait(150)
                self.assertFalse(any(spy.count() for spy in requests.values()))
                self.assertEqual(self.warnings, [])
                self.assert_drawn_action_ring(self.control("addonChooseFile"))

    def loader_fixture(self, windowed=False):
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        component = QQmlComponent(engine)
        fixture = LOADER_WINDOW_QML if windowed else LOADER_MINIMAL_QML
        base = QUrl.fromLocalFile(str(Path(__file__).with_name("AddonManagerHarness.qml").resolve()))
        component.setData(fixture.encode(), base)
        self.assertFalse(component.isError(), [e.toString() for e in component.errors()])
        root = component.create()
        self.assertIsNotNone(root, [e.toString() for e in component.errors()])
        if windowed:
            root.setProperty("schemeName", os.environ.get("ORLA_ADDON_TEST_SCHEME", "dark"))
        QTest.qWait(50)
        loader = root.findChild(QQuickItem, "managerLoader" if windowed else "holder")
        self.assertIsNotNone(loader)
        self.assertEqual(self.warnings, [])
        # Retain both the root and component while the Loader retires its item.
        return engine, component, root, loader

    def dispose_loader_fixture(self, engine, root):
        if isinstance(root, QQuickWindow):
            root.close()
        root.deleteLater()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def test_public_loader_retirement_cancels_unowned_gate_callbacks(self):
        for gate in ("busy", "loading"):
            for forced in (False, True):
                with self.subTest(gate=gate, forced=forced):
                    engine, component, root, loader = self.loader_fixture()
                    try:
                        manager = loader.property("item")
                        requests = {n: QSignalSpy(getattr(manager, n)) for n in (
                            "chooseFileRequested", "installRequested", "enableRequested", "disableRequested",
                            "removeRequested", "rollbackRequested", "openOriginRequested")}
                        manager.setProperty(gate, True)
                        manager.setProperty(gate, False)
                        loader.setProperty("active", False)
                        if forced:
                            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                            self.assertFalse(isValid(manager))
                        QTest.qWait(90)
                        self.assertFalse(isValid(manager))
                        self.assertTrue(isValid(root))
                        self.assertTrue(isValid(engine))
                        self.assertFalse(any(spy.count() for spy in requests.values()))
                        self.assertEqual(self.warnings, [])
                    finally:
                        self.dispose_loader_fixture(engine, root)

    def test_public_loader_retirement_cancels_owned_gate_and_pending_reveal(self):
        for kind in ("owned-gate", "pending-reveal"):
            for forced in (False, True):
                with self.subTest(kind=kind, forced=forced):
                    engine, component, root, loader = self.loader_fixture(windowed=True)
                    try:
                        root.setProperty("previewData", package(description="Curto."))
                        QTest.qWait(40)
                        manager = loader.property("item")
                        action = root.findChild(QQuickItem, "addonPreviewInstall")
                        newer = root.findChild(QQuickItem, "newerFocus")
                        self.assertTrue(root.isActive())
                        action.forceActiveFocus(Qt.TabFocusReason)
                        QTest.qWait(40)
                        self.assertTrue(manager.property("focusOwned"))
                        requests = {n: QSignalSpy(getattr(manager, n)) for n in (
                            "chooseFileRequested", "installRequested", "enableRequested", "disableRequested",
                            "removeRequested", "rollbackRequested", "openOriginRequested")}
                        if kind == "owned-gate":
                            root.setProperty("gate", True)
                            QTest.qWait(30)
                            root.setProperty("gate", False)
                        else:
                            newer.forceActiveFocus(Qt.TabFocusReason)
                            QTest.qWait(25)
                            action.forceActiveFocus(Qt.TabFocusReason)
                        newer.forceActiveFocus(Qt.TabFocusReason)
                        reveals = root.property("reveals")
                        loader.setProperty("active", False)
                        if forced:
                            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                            self.assertFalse(isValid(manager))
                        QTest.qWait(100)
                        self.assertFalse(isValid(manager))
                        self.assertTrue(isValid(root))
                        self.assertTrue(isValid(engine))
                        self.assertEqual(root.activeFocusItem(), newer)
                        self.assertEqual(root.property("reveals"), reveals)
                        self.assertFalse(any(spy.count() for spy in requests.values()))
                        self.assertEqual(self.warnings, [])
                    finally:
                        self.dispose_loader_fixture(engine, root)

    def test_loader_removal_controls_and_new_instance_remain_live(self):
        for drained in (False, True):
            with self.subTest(drained=drained):
                engine, component, root, loader = self.loader_fixture(windowed=True)
                try:
                    if drained:
                        root.setProperty("gate", True)
                        root.setProperty("gate", False)
                        QTest.qWait(60)
                    newer = root.findChild(QQuickItem, "newerFocus")
                    newer.forceActiveFocus(Qt.TabFocusReason)
                    reveals = root.property("reveals")
                    manager = loader.property("item")
                    loader.setProperty("active", False)
                    QTest.qWait(90)
                    self.assertFalse(isValid(manager))
                    self.assertEqual(root.activeFocusItem(), newer)
                    self.assertEqual(root.property("reveals"), reveals)
                    self.assertEqual(self.warnings, [])
                    # A replacement owns a distinct lifetime; cancellation of the
                    # retired manager must not suppress its live public requests.
                    loader.setProperty("active", True)
                    QTest.qWait(50)
                    replacement = loader.property("item")
                    choose = QSignalSpy(replacement.chooseFileRequested)
                    root.setProperty("gate", True)
                    root.setProperty("gate", False)
                    QTest.qWait(60)
                    button = root.findChild(QQuickItem, "addonChooseFile")
                    button.forceActiveFocus(Qt.TabFocusReason)
                    QTest.keyClick(root, Qt.Key_Return)
                    QTest.qWait(40)
                    self.assertTrue(replacement.property("focusOwned"))
                    self.assertEqual(choose.count(), 1)
                    self.assertEqual(self.warnings, [])
                finally:
                    self.dispose_loader_fixture(engine, root)

    def test_loader_retirement_during_gate_notification_cancels_remaining_callback(self):
        engine, component, root, loader = self.loader_fixture(windowed=True)
        try:
            root.setProperty("previewData", package(description="Curto."))
            QTest.qWait(40)
            manager = loader.property("item")
            action = root.findChild(QQuickItem, "addonPreviewInstall")
            newer = root.findChild(QQuickItem, "newerFocus")
            action.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(40)
            root.setProperty("gate", True)
            QTest.qWait(30)
            transitions = []
            def retire():
                if manager.property("gatedFocus") is not None or transitions:
                    return
                transitions.append(True)
                loader.setProperty("active", False)
                newer.forceActiveFocus(Qt.TabFocusReason)
            manager.gatedFocusChanged.connect(retire)
            reveals = root.property("reveals")
            root.setProperty("gate", False)
            QTest.qWait(100)
            self.assertEqual(transitions, [True])
            self.assertFalse(isValid(manager))
            self.assertTrue(isValid(root))
            self.assertTrue(isValid(engine))
            self.assertEqual(root.activeFocusItem(), newer)
            self.assertEqual(root.property("reveals"), reveals)
            self.assertEqual(self.warnings, [])
        finally:
            self.dispose_loader_fixture(engine, root)

    def test_empty_add_is_explicit_and_keyboard_operable(self):
        choose = QSignalSpy(self.manager.chooseFileRequested)
        install = QSignalSpy(self.manager.installRequested)
        enable = QSignalSpy(self.manager.enableRequested)
        self.assertTrue(self.control("addonEmpty").isVisible())
        add = self.control("addonChooseFile")
        self.assertEqual(add.property("variant"), "primary")
        self.press(add)
        self.assertEqual(choose.count(), 1)
        self.assertEqual(install.count(), 0)
        self.assertEqual(enable.count(), 0)
        self.assertEqual(self.warnings, [])

    def test_reload_keeps_the_scroll_position_while_rows_are_cleared(self):
        # Installed dock: a reload cleared the rows until the host answered, so the
        # settings scroll snapped upward and stayed there after the rows returned.
        self.window.setHeight(240)
        rows = [package(enabled=True), package(id="org.example.other", sha256="c" * 64)]
        self.manager.setProperty("addons", rows)
        QTest.qWait(60)
        flick = self.control("addonScroll").property("contentItem")
        bottom = flick.property("contentHeight") - flick.property("height")
        self.assertGreater(bottom, 100)
        flick.setProperty("contentY", bottom)
        QTest.qWait(30)
        self.manager.setProperty("loading", True)
        self.manager.setProperty("addons", [])
        QTest.qWait(60)
        self.assertAlmostEqual(flick.property("contentY"), bottom, delta=1)
        self.manager.setProperty("addons", rows)
        self.manager.setProperty("loading", False)
        QTest.qWait(60)
        self.assertAlmostEqual(flick.property("contentY"), bottom, delta=1)
        # Without rows after the answer the list really is shorter.
        self.manager.setProperty("addons", [])
        QTest.qWait(60)
        self.assertLess(flick.property("contentHeight"), bottom)
        self.assertEqual(self.warnings, [])

    def test_loading_feedback_and_provider_profile_gates(self):
        self.manager.setProperty("loading", True)
        self.assertTrue(self.control("addonProgress").isVisible())
        self.assertFalse(self.control("addonEmpty").isVisible())
        self.assertFalse(self.control("addonChooseFile").isEnabled())
        self.manager.setProperty("loading", False)
        self.manager.setProperty("feedbackKind", "error")
        self.manager.setProperty("feedback", "Escolha um arquivo válido. <b>Texto literal</b>")
        self.assertIn("<b>", self.control("addonFeedback").property("text"))
        self.assertTrue(self.evaluate(self.control("addonFeedback"), "textFormat === Text.PlainText"))
        self.manager.setProperty("addons", [package(enabled=True), package(id="org.example.other", sha256="c" * 64)])
        self.manager.setProperty("profilePeripheralVisible", False)
        QTest.qWait(40)
        self.assertFalse(self.control("addonEnable-org.example.other").isEnabled())
        self.assertIn("outro complemento", self.control("addonGuidance-org.example.other").property("text"))
        self.assertIn("neste perfil", self.control("addonGuidance-org.example.battery").property("text"))
        self.assertTrue(self.control("addonDisable-org.example.battery").isEnabled())
        self.manager.setProperty("busy", True)
        self.assertFalse(self.control("addonDisable-org.example.battery").isEnabled())
        self.assertEqual(self.warnings, [])

    def test_removed_focused_row_recovers_without_stealing_newer_focus(self):
        self.manager.setProperty("addons", [package()])
        QTest.qWait(30)
        self.control("addonEnable-org.example.battery").forceActiveFocus(Qt.TabFocusReason)
        self.manager.setProperty("addons", [])
        QTest.qWait(40)
        self.assertEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
        self.manager.setProperty("addons", [package()])
        QTest.qWait(30)
        self.control("addonEnable-org.example.battery").forceActiveFocus(Qt.TabFocusReason)
        self.manager.setProperty("addons", [])
        outside = self.control("outsideFocus")
        outside.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(40)
        self.assertEqual(self.window.activeFocusItem(), outside)
        self.assertEqual(self.warnings, [])

    def test_toggling_reading_keeps_focus_on_the_same_card_with_the_same_input(self):
        # Installed dock: after "Desativar leitura" the ring jumped to "Adicionar arquivo…",
        # even when the button had been clicked with the pointer.
        for reason, visual in ((Qt.TabFocusReason, True), (Qt.MouseFocusReason, False)):
            with self.subTest(visual=visual):
                self.manager.setProperty("addons", [package(enabled=True)])
                QTest.qWait(30)
                self.control("addonDisable-org.example.battery").forceActiveFocus(reason)
                self.manager.setProperty("addons", [package(enabled=False)])
                QTest.qWait(40)
                enable = self.control("addonEnable-org.example.battery")
                self.assertEqual(self.window.activeFocusItem(), enable)
                self.assertEqual(enable.property("visualFocus"), visual)
                self.manager.setProperty("addons", [package(enabled=True)])
                QTest.qWait(40)
                disable = self.control("addonDisable-org.example.battery")
                self.assertEqual(self.window.activeFocusItem(), disable)
                self.assertEqual(disable.property("visualFocus"), visual)
                self.manager.setProperty("addons", [])
                QTest.qWait(40)
        self.assertEqual(self.warnings, [])

    def assert_visible_add_focus(self):
        action = self.control("addonChooseFile")
        self.assertEqual(self.window.activeFocusItem(), action)
        self.assertTrue(action.isVisible())
        self.assertTrue(action.isEnabled())
        top = action.mapToScene(QPointF(0, 0)).y()
        self.assertGreaterEqual(top - 3, 0)
        self.assertLessEqual(top + action.height() + 3, self.window.height())

    def assert_action_revealed(self, action, require_visual=True):
        self.assertEqual(self.window.activeFocusItem(), action)
        self.assertTrue(action.isVisible())
        self.assertTrue(action.isEnabled())
        if require_visual:
            self.assertTrue(action.property("visualFocus"))
        top = action.mapToScene(QPointF(0, 0)).y()
        self.assertGreaterEqual(top - 3, 0)
        self.assertLessEqual(top + action.height() + 3, self.window.height())

    def tab_to_install(self):
        self.window.contentItem().forceActiveFocus(Qt.OtherFocusReason)
        QTest.keyClick(self.window, Qt.Key_Tab)
        QTest.qWait(40)
        action = self.control("addonPreviewInstall")
        self.assert_action_revealed(action)
        return action

    def assert_drawn_action_ring(self, action):
        self.assert_action_revealed(action)
        # Inspect the real OrlaButton background, whose visible 2 px rectangle
        # is drawn by the renderer; active focus alone does not draw that ring.
        self.assertTrue(self.evaluate(action, """
            background.children.some(function(item) {
                return item.visible && item.border && item.border.width === 2
                    && item.border.color.toString() === palette.highlight.toString()
                    && item.width === width + 6 && item.height === height + 6;
            })
        """))
        image = self.window.grabWindow()
        self.assertFalse(image.isNull())
        accent = QColor(self.evaluate(action, "palette.highlight.toString()"))
        origin = action.mapToScene(QPointF(0, 0))
        scale = image.width() / self.window.width()
        # Sample all four straight ring edges in the actual synthetic render.
        for x, y in ((origin.x() + action.width() / 2, origin.y() - 2),
                     (origin.x() + action.width() / 2, origin.y() + action.height() + 1),
                     (origin.x() - 2, origin.y() + action.height() / 2),
                     (origin.x() + action.width() + 1, origin.y() + action.height() / 2)):
            pixel = image.pixelColor(round(x * scale), round(y * scale))
            self.assertLessEqual(max(abs(a - b) for a, b in zip(pixel.getRgb(), accent.getRgb())), 3)

    def test_keyboard_ring_survives_growth_and_no_growth_late_gate(self):
        for width, height in ((350, 240), (350, 360), (420, 240), (420, 360)):
            for gate in ("busy", "loading"):
                for growth in (False, True):
                    with self.subTest(gate=gate, growth=growth, width=width, height=height):
                        self.tearDown()
                        self.setUp()
                        self.window.setWidth(width)
                        self.window.setHeight(height)
                        self.manager.setProperty("preview", package(description="Curto."))
                        QTest.qWait(40)
                        action = self.tab_to_install()
                        requests = QSignalSpy(self.manager.installRequested)
                        self.manager.setProperty(gate, True)
                        if growth:
                            self.manager.setProperty("preview", long_preview())
                        QTest.qWait(60)
                        self.manager.setProperty(gate, False)
                        QTest.qWait(120)
                        self.assert_drawn_action_ring(action)
                        self.assertEqual(requests.count(), 0)
                        self.assertEqual(self.warnings, [])

    def test_pointer_gate_does_not_gain_keyboard_ring(self):
        for gate in ("busy", "loading"):
            with self.subTest(gate=gate):
                self.manager.setProperty("preview", package(description="Curto."))
                QTest.qWait(40)
                action = self.control("addonPreviewInstall")
                # Synthetic pointer input on the actual button, before spying:
                # the explicit click emits one request and never installs data.
                self.control("outsideFocus").forceActiveFocus(Qt.MouseFocusReason)
                QTest.mouseClick(self.window, Qt.LeftButton, pos=action.mapToScene(QPointF(action.width() / 2, action.height() / 2)).toPoint())
                QTest.qWait(40)
                self.assertEqual(self.window.activeFocusItem(), action)
                self.assertFalse(action.property("visualFocus"))
                requests = QSignalSpy(self.manager.installRequested)
                self.manager.setProperty(gate, True)
                self.manager.setProperty("preview", long_preview())
                QTest.qWait(60)
                self.manager.setProperty(gate, False)
                QTest.qWait(120)
                self.assert_action_revealed(action, require_visual=False)
                self.assertFalse(action.property("visualFocus"))
                self.assertEqual(requests.count(), 0)
                self.assertEqual(self.warnings, [])

    def test_gate_ring_restore_cancels_for_revoked_or_newer_focus(self):
        for gate in ("busy", "loading"):
            for change in ("owner", "hidden", "parent", "newer-add", "newer-outside", "pointer"):
                with self.subTest(gate=gate, change=change):
                    self.tearDown()
                    self.setUp()
                    self.window.setHeight(240)
                    self.manager.setProperty("preview", package(description="Curto."))
                    QTest.qWait(40)
                    action = self.tab_to_install()
                    self.manager.setProperty(gate, True)
                    if change != "pointer":
                        self.manager.setProperty("preview", long_preview())
                    QTest.qWait(60)
                    events = []
                    self.manager.revealRequested.connect(lambda item: events.append(item.objectName()))
                    self.manager.setProperty(gate, False)
                    original = self.manager.parentItem()
                    temporary = None
                    newer = None
                    if change == "owner":
                        self.evaluate(self.manager, "dock=({})")
                        self.manager.setProperty("dock", None)
                    elif change == "hidden":
                        self.manager.setVisible(False)
                        self.manager.setVisible(True)
                    elif change == "parent":
                        temporary = QQuickItem(original)
                        self.manager.setParentItem(temporary)
                        self.manager.setParentItem(original)
                    elif change.startswith("newer"):
                        newer = self.control("addonChooseFile" if change == "newer-add" else "outsideFocus")
                        newer.forceActiveFocus(Qt.TabFocusReason)
                    else:
                        # A new pointer focus request revokes the keyboard scope.
                        self.control("outsideFocus").forceActiveFocus(Qt.MouseFocusReason)
                        QTest.mouseClick(self.window, Qt.LeftButton,
                                         pos=action.mapToScene(QPointF(action.width() / 2, action.height() / 2)).toPoint())
                    requests = {name: QSignalSpy(getattr(self.manager, name)) for name in (
                        "chooseFileRequested", "installRequested", "enableRequested", "disableRequested",
                        "removeRequested", "rollbackRequested", "openOriginRequested")}
                    QTest.qWait(120)
                    if newer:
                        self.assertEqual(self.window.activeFocusItem(), newer)
                        if change == "newer-add":
                            self.assert_drawn_action_ring(newer)
                        self.assertNotIn("addonPreviewInstall", events)
                    elif change == "pointer":
                        self.assertEqual(self.window.activeFocusItem(), action)
                        self.assertFalse(action.property("visualFocus"))
                    else:
                        self.assertFalse(self.manager.property("focusOwned"))
                        self.assertEqual(events, [])
                        self.assertFalse(action.property("visualFocus"))
                    self.assertFalse(any(spy.count() for spy in requests.values()))
                    self.assertEqual(self.warnings, [])
                    if temporary:
                        temporary.deleteLater()

    def test_gate_ring_restore_cancels_for_inactive_or_rehosted_window(self):
        for gate in ("busy", "loading"):
            for rehost in (False, True):
                with self.subTest(gate=gate, rehost=rehost):
                    self.tearDown()
                    self.setUp()
                    self.window.setHeight(240)
                    self.manager.setProperty("preview", package(description="Curto."))
                    QTest.qWait(40)
                    action = self.tab_to_install()
                    self.manager.setProperty(gate, True)
                    QTest.qWait(30)
                    original = self.manager.parentItem()
                    other = QQuickWindow()
                    other.resize(420, 360)
                    try:
                        if rehost:
                            self.manager.setParentItem(other.contentItem())
                        other.show()
                        other.requestActivate()
                        newer = QQuickItem(other.contentItem())
                        newer.forceActiveFocus(Qt.TabFocusReason)
                        QTest.qWait(60)
                        self.assertFalse(self.window.isActive())
                        events = QSignalSpy(self.manager.revealRequested)
                        self.manager.setProperty(gate, False)
                        QTest.qWait(120)
                        self.assertEqual(other.activeFocusItem(), newer)
                        self.assertFalse(self.manager.property("focusOwned"))
                        self.assertEqual(events.count(), 0)
                        self.assertFalse(action.property("visualFocus"))
                    finally:
                        self.manager.setParentItem(original)
                        other.close()
                        other.deleteLater()
                    self.assertEqual(self.warnings, [])

    def test_queued_card_reveal_is_revoked_by_owner_surface_roundtrip(self):
        for change in ("owner", "hidden", "parent"):
            with self.subTest(change=change):
                self.tearDown()
                self.setUp()
                self.window.setHeight(240)
                self.manager.setProperty("preview", long_preview())
                QTest.qWait(60)
                self.control("outsideFocus").forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(40)
                scroll = self.control("addonScroll")
                self.evaluate(scroll, "contentItem.contentY=0")
                QTest.qWait(30)
                events = QSignalSpy(self.manager.revealRequested)
                requests = QSignalSpy(self.manager.installRequested)
                self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)
                original = self.manager.parentItem()
                temporary = None
                if change == "owner":
                    self.evaluate(self.manager, "dock=({})")
                    self.manager.setProperty("dock", None)
                elif change == "hidden":
                    self.manager.setVisible(False)
                    self.manager.setVisible(True)
                else:
                    temporary = QQuickItem(original)
                    self.manager.setParentItem(temporary)
                    self.manager.setParentItem(original)
                self.assertFalse(self.manager.property("focusOwned"))
                QTest.qWait(120)
                self.assertEqual(events.count(), 0)
                self.assertEqual(self.evaluate(scroll, "contentItem.contentY"), 0)
                self.assertEqual(requests.count(), 0)
                self.assertEqual(self.warnings, [])
                if temporary:
                    temporary.deleteLater()

    def test_newer_add_during_real_height_change_keeps_drawn_ring_visible(self):
        for stage in ("before", "during"):
            with self.subTest(stage=stage):
                self.focused_short_preview()
                add = self.control("addonChooseFile")
                moved = []
                events = []
                self.manager.revealRequested.connect(lambda item: events.append((item.objectName(), bool(moved))))
                requests = QSignalSpy(self.manager.chooseFileRequested)
                def move():
                    if not moved:
                        moved.append(True)
                        add.forceActiveFocus(Qt.TabFocusReason)
                if stage == "during":
                    self.manager.heightChanged.connect(move)
                self.manager.setProperty("preview", long_preview())
                if stage == "before":
                    move()
                QTest.qWait(140)
                if stage == "during":
                    self.manager.heightChanged.disconnect(move)
                self.assertTrue(moved)
                self.assert_drawn_action_ring(add)
                self.assertNotIn(("addonPreviewInstall", True), events)
                self.assertEqual(requests.count(), 0)
                self.assertEqual(self.warnings, [])

    def test_growing_valid_preview_keeps_surviving_install_focus_revealed(self):
        for width, height in ((350, 240), (350, 360), (420, 240), (420, 360)):
            with self.subTest(width=width, height=height):
                self.tearDown()
                self.setUp()
                self.window.setWidth(width)
                self.window.setHeight(height)
                self.manager.setProperty("preview", package(description="Curto."))
                QTest.qWait(30)
                action = self.control("addonPreviewInstall")
                action.forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(50)
                self.assert_action_revealed(action)
                requests = {name: QSignalSpy(getattr(self.manager, name)) for name in (
                    "chooseFileRequested", "installRequested", "enableRequested", "disableRequested",
                    "removeRequested", "rollbackRequested", "openOriginRequested")}
                self.manager.setProperty("preview", long_preview())
                QTest.qWait(120)
                self.assert_action_revealed(action)
                self.assertEqual({name: spy.count() for name, spy in requests.items()},
                                 {name: 0 for name in requests})
                self.assertEqual(self.warnings, [])

    def focused_short_preview(self, width=350, height=240):
        self.tearDown()
        self.setUp()
        self.window.setWidth(width)
        self.window.setHeight(height)
        self.manager.setProperty("preview", package(description="Curto."))
        QTest.qWait(30)
        action = self.control("addonPreviewInstall")
        action.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(50)
        self.assert_action_revealed(action)
        return action

    def test_growing_preview_reveals_newer_action_without_scrolling_to_old_install(self):
        for target_name in ("outsideFocus", "addonChooseFile", "addonDetailsPreview"):
            with self.subTest(target=target_name):
                self.focused_short_preview()
                reveals = []
                self.manager.revealRequested.connect(lambda control: reveals.append(control.objectName()))
                self.manager.setProperty("preview", long_preview())
                newer = self.control(target_name)
                newer.forceActiveFocus(Qt.TabFocusReason)
                QTest.qWait(120)
                self.assertEqual(self.window.activeFocusItem(), newer)
                self.assertNotIn("addonPreviewInstall", reveals)
                if target_name != "outsideFocus":
                    self.assert_action_revealed(newer)
                self.assertEqual(self.warnings, [])

    def test_growing_valid_preview_respects_late_busy_and_loading_completion(self):
        for gate in ("busy", "loading"):
            for width, height in ((350, 240), (350, 360), (420, 240), (420, 360)):
                with self.subTest(gate=gate, width=width, height=height):
                    action = self.focused_short_preview(width, height)
                    install = QSignalSpy(self.manager.installRequested)
                    enable = QSignalSpy(self.manager.enableRequested)
                    self.manager.setProperty(gate, True)
                    self.manager.setProperty("preview", long_preview())
                    QTest.qWait(60)
                    self.assertFalse(action.isEnabled())
                    self.manager.setProperty(gate, False)
                    QTest.qWait(120)
                    self.assert_action_revealed(action)
                    self.assertEqual(install.count(), 0)
                    self.assertEqual(enable.count(), 0)
                    self.assertEqual(self.warnings, [])

    def test_reflow_callbacks_drop_old_reveal_after_new_focus_or_owner_change(self):
        for change in ("newer", "newer-hidden", "owner"):
            with self.subTest(change=change):
                self.focused_short_preview()
                reveals = []
                transitions = []
                self.manager.revealRequested.connect(
                    lambda control: reveals.append((control.objectName(), bool(transitions))))
                outside = self.control("outsideFocus")

                def after_layout():
                    if transitions:
                        return
                    transitions.append(change)
                    if change == "owner":
                        self.evaluate(self.manager, "dock = ({})")
                        self.manager.setProperty("dock", None)
                    else:
                        outside.forceActiveFocus(Qt.TabFocusReason)
                        if change == "newer-hidden":
                            outside.setVisible(False)

                self.manager.heightChanged.connect(after_layout)
                self.manager.setProperty("preview", long_preview())
                QTest.qWait(120)
                self.manager.heightChanged.disconnect(after_layout)
                self.assertEqual(transitions, [change])
                self.assertNotIn(("addonPreviewInstall", True), reveals)
                if change == "newer":
                    self.assertEqual(self.window.activeFocusItem(), outside)
                self.assertEqual(self.warnings, [])

    def test_surviving_reveal_callback_does_not_follow_action_into_new_window(self):
        self.focused_short_preview()
        original = self.manager.parentItem()
        reveals = []
        self.manager.revealRequested.connect(lambda control: reveals.append(control.objectName()))
        other = QQuickWindow()
        other.resize(420, 360)
        try:
            self.window.setWidth(420)
            self.manager.setParentItem(other.contentItem())
            other.show()
            other.requestActivate()
            newer = QQuickItem(other.contentItem())
            newer.setWidth(40)
            newer.setHeight(40)
            newer.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(100)
            self.assertEqual(other.activeFocusItem(), newer)
            self.assertNotIn("addonPreviewInstall", reveals)
        finally:
            self.manager.setParentItem(original)
            other.close()
            other.deleteLater()
        self.assertEqual(self.warnings, [])

    def test_inactive_window_does_not_reveal_replaced_preview(self):
        self.focused_short_preview()
        other = QQuickWindow()
        other.resize(100, 100)
        try:
            other.show()
            other.requestActivate()
            QTest.qWait(50)
            self.assertFalse(self.window.isActive())
            reveals = []
            self.manager.revealRequested.connect(lambda control: reveals.append(control.objectName()))
            self.manager.setProperty("preview", long_preview())
            QTest.qWait(120)
            self.assertNotIn("addonPreviewInstall", reveals)
            self.assertTrue(other.isActive())
        finally:
            other.close()
            other.deleteLater()
        self.assertEqual(self.warnings, [])

    def test_preview_clear_recovers_visible_action_synchronously_and_deferred(self):
        for deferred in (False, True):
            for cleared in (None, {}):
                with self.subTest(deferred=deferred, cleared=cleared):
                    self.manager.setProperty("preview", package())
                    QTest.qWait(30)
                    self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)
                    if deferred:
                        QTimer.singleShot(0, lambda value=cleared: self.manager.setProperty("preview", value))
                    else:
                        self.manager.setProperty("preview", cleared)
                    QTest.qWait(70)
                    self.assert_visible_add_focus()
        self.assertEqual(self.warnings, [])

    def test_install_response_recovers_visible_focus_synchronously_and_deferred(self):
        install = QSignalSpy(self.manager.installRequested)
        enable = QSignalSpy(self.manager.enableRequested)
        for deferred in (False, True):
            with self.subTest(deferred=deferred):
                self.manager.setProperty("addons", [])
                self.manager.setProperty("preview", package())
                QTest.qWait(30)

                def complete():
                    self.manager.setProperty("preview", None)
                    self.manager.setProperty("addons", [package()])

                def installed(digest):
                    if deferred:
                        QTimer.singleShot(0, complete)
                    else:
                        complete()

                self.manager.installRequested.connect(installed)
                self.press(self.control("addonPreviewInstall"), Qt.Key_Return)
                QTest.qWait(70)
                self.manager.installRequested.disconnect(installed)
                self.assert_visible_add_focus()
                self.assertFalse(self.control("addonDisable-org.example.battery").isVisible())
        self.assertEqual(install.count(), 2)
        self.assertEqual(install.at(0), ["a" * 64])
        self.assertEqual(install.at(1), ["a" * 64])
        self.assertEqual(enable.count(), 0)
        self.assertEqual(self.warnings, [])

    def test_preview_recovery_preserves_newer_visible_focus_before_or_after_clear(self):
        outside = self.control("outsideFocus")
        for deferred in (False, True):
            for before in (False, True):
                with self.subTest(deferred=deferred, before=before):
                    self.manager.setProperty("preview", package())
                    QTest.qWait(30)
                    self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)

                    def complete():
                        if before:
                            outside.forceActiveFocus(Qt.TabFocusReason)
                        self.manager.setProperty("preview", None)
                        if not before:
                            outside.forceActiveFocus(Qt.TabFocusReason)

                    if deferred:
                        QTimer.singleShot(0, complete)
                    else:
                        complete()
                    QTest.qWait(70)
                    self.assertEqual(self.window.activeFocusItem(), outside)
                    self.assertTrue(outside.isVisible())
        self.assertEqual(self.warnings, [])

    def test_inactive_window_does_not_recover_preview_focus_or_replay_it_on_activation(self):
        other = QQuickWindow()
        other.resize(100, 100)
        try:
            for deferred in (False, True):
                with self.subTest(deferred=deferred):
                    self.window.requestActivate()
                    QTest.qWait(30)
                    self.assertTrue(self.window.isActive())
                    self.manager.setProperty("preview", package())
                    QTest.qWait(30)
                    self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)
                    other.show()
                    other.requestActivate()
                    QTest.qWait(30)
                    self.assertFalse(self.window.isActive())

                    def complete():
                        self.manager.setProperty("preview", None)
                        self.manager.setProperty("addons", [package()])

                    if deferred:
                        QTimer.singleShot(0, complete)
                    else:
                        complete()
                    QTest.qWait(70)
                    self.assertFalse(self.window.isActive())
                    self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
                    self.window.requestActivate()
                    QTest.qWait(50)
                    self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
        finally:
            other.close()
            other.deleteLater()
        self.assertEqual(self.warnings, [])

    def test_newer_visible_focus_cancels_recovery_even_if_that_control_then_hides(self):
        self.manager.setProperty("preview", package())
        QTest.qWait(30)
        self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)
        self.manager.setProperty("preview", None)
        outside = self.control("outsideFocus")
        outside.forceActiveFocus(Qt.TabFocusReason)
        outside.setVisible(False)
        QTest.qWait(70)
        self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
        self.assertEqual(self.warnings, [])

    def test_install_response_preserves_newer_action_inside_the_manager(self):
        self.manager.setProperty("preview", package())
        QTest.qWait(30)

        def installed(digest):
            self.manager.setProperty("preview", None)
            self.manager.setProperty("addons", [package()])
            self.control("addonEnable-org.example.battery").forceActiveFocus(Qt.TabFocusReason)

        self.manager.installRequested.connect(installed)
        enable = QSignalSpy(self.manager.enableRequested)
        self.press(self.control("addonPreviewInstall"), Qt.Key_Return)
        QTest.qWait(70)
        self.assertEqual(self.window.activeFocusItem(), self.control("addonEnable-org.example.battery"))
        self.assertEqual(enable.count(), 0)
        self.assertEqual(self.warnings, [])

    def install_gate_response(self, gate, cleared, deferred, late, newer=False):
        self.manager.setProperty("addons", [])
        self.manager.setProperty("preview", package())
        QTest.qWait(20)
        installs = QSignalSpy(self.manager.installRequested)
        enables = QSignalSpy(self.manager.enableRequested)

        def finish():
            self.manager.setProperty(gate, False)

        def complete():
            self.manager.setProperty("preview", cleared)
            self.manager.setProperty("addons", [package()])
            if newer:
                self.control("outsideFocus").forceActiveFocus(Qt.TabFocusReason)
            if late:
                QTimer.singleShot(30, finish)
            else:
                finish()

        def installed(digest):
            self.manager.setProperty(gate, True)
            if deferred:
                QTimer.singleShot(0, complete)
            else:
                complete()

        self.manager.installRequested.connect(installed)
        self.press(self.control("addonPreviewInstall"), Qt.Key_Return)
        QTest.qWait(90)
        self.manager.installRequested.disconnect(installed)
        self.assertEqual(installs.count(), 1)
        self.assertEqual(installs.at(0), ["a" * 64])
        self.assertEqual(enables.count(), 0)
        self.assertFalse(self.control("addonDisable-org.example.battery").isVisible())
        self.assertEqual(self.warnings, [])
        if newer:
            self.assertEqual(self.window.activeFocusItem(), self.control("outsideFocus"))
        else:
            self.assert_visible_add_focus()

    def test_late_gate_completion_restores_visible_focus(self):
        for gate in ("busy", "loading"):
            for cleared in (None, {}):
                for deferred in (False, True):
                    with self.subTest(gate=gate, cleared=cleared, deferred=deferred):
                        self.install_gate_response(gate, cleared, deferred, True)

    def test_same_turn_gate_completion_restores_visible_focus(self):
        for gate in ("busy", "loading"):
            for cleared in (None, {}):
                for deferred in (False, True):
                    with self.subTest(gate=gate, cleared=cleared, deferred=deferred):
                        self.install_gate_response(gate, cleared, deferred, False)

    def test_late_gate_completion_preserves_newer_visible_focus(self):
        for gate in ("busy", "loading"):
            for cleared in (None, {}):
                for deferred in (False, True):
                    with self.subTest(gate=gate, cleared=cleared, deferred=deferred):
                        self.install_gate_response(gate, cleared, deferred, True, newer=True)

    def begin_gated_clear(self, gate="busy"):
        self.manager.setProperty("preview", package())
        QTest.qWait(20)
        self.control("addonPreviewInstall").forceActiveFocus(Qt.TabFocusReason)
        self.manager.setProperty(gate, True)
        self.manager.setProperty("preview", None)
        self.manager.setProperty("addons", [package()])
        QTest.qWait(50)
        self.assertFalse(self.control("addonChooseFile").isEnabled())

    def test_pending_recovery_waits_until_both_gates_open(self):
        enables = QSignalSpy(self.manager.enableRequested)
        for first, second in (("busy", "loading"), ("loading", "busy")):
            with self.subTest(first=first):
                self.begin_gated_clear(first)
                self.manager.setProperty(second, True)
                self.manager.setProperty(first, False)
                QTest.qWait(40)
                self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
                self.manager.setProperty(second, False)
                QTest.qWait(60)
                self.assert_visible_add_focus()
        self.assertEqual(enables.count(), 0)
        self.assertEqual(self.warnings, [])

    def test_gate_changes_without_pending_recovery_do_not_move_focus(self):
        outside = self.control("outsideFocus")
        outside.forceActiveFocus(Qt.TabFocusReason)
        for gate in ("busy", "loading"):
            self.manager.setProperty(gate, True)
            QTest.qWait(30)
            self.manager.setProperty(gate, False)
            QTest.qWait(50)
            self.assertEqual(self.window.activeFocusItem(), outside)
        self.assertEqual(self.warnings, [])

    def test_pending_recovery_cancelled_by_newer_focus_even_if_it_then_hides(self):
        self.begin_gated_clear()
        outside = self.control("outsideFocus")
        outside.forceActiveFocus(Qt.TabFocusReason)
        outside.setVisible(False)
        self.manager.setProperty("busy", False)
        QTest.qWait(60)
        self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
        self.assertEqual(self.warnings, [])

    def test_pending_recovery_cancelled_by_surface_or_owner_changes(self):
        for change in ("visibility", "enabled", "owner", "parent"):
            with self.subTest(change=change):
                self.begin_gated_clear()
                if change == "visibility":
                    self.manager.setVisible(False)
                    self.manager.setVisible(True)
                elif change == "enabled":
                    self.manager.setEnabled(False)
                    self.manager.setEnabled(True)
                elif change == "owner":
                    self.evaluate(self.manager, "dock = ({})")
                    self.manager.setProperty("dock", None)
                else:
                    original = self.manager.parentItem()
                    host = QQuickItem(original)
                    host.setWidth(original.width())
                    self.manager.setParentItem(host)
                    self.manager.setParentItem(original)
                    host.deleteLater()
                self.manager.setProperty("busy", False)
                QTest.qWait(60)
                self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
        self.assertEqual(self.warnings, [])

    def test_pending_recovery_cancelled_by_window_inactivity_without_replay(self):
        other = QQuickWindow()
        other.resize(100, 100)
        try:
            self.begin_gated_clear()
            other.show()
            other.requestActivate()
            QTest.qWait(40)
            self.assertFalse(self.window.isActive())
            self.manager.setProperty("busy", False)
            QTest.qWait(60)
            self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
            self.window.requestActivate()
            QTest.qWait(50)
            self.assertNotEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
        finally:
            other.close()
            other.deleteLater()
        self.assertEqual(self.warnings, [])

    def test_pending_recovery_cancelled_by_rehosting_preserves_new_window_focus(self):
        other = QQuickWindow()
        other.resize(350, 360)
        original = self.manager.parentItem()
        try:
            self.begin_gated_clear()
            add = self.control("addonChooseFile")
            self.manager.setParentItem(other.contentItem())
            other.show()
            other.requestActivate()
            newer = QQuickItem(other.contentItem())
            newer.setWidth(40)
            newer.setHeight(40)
            newer.forceActiveFocus(Qt.TabFocusReason)
            self.manager.setProperty("busy", False)
            QTest.qWait(60)
            self.assertEqual(other.activeFocusItem(), newer)
            self.assertFalse(add.hasActiveFocus())
        finally:
            self.manager.setParentItem(original)
            other.close()
            other.deleteLater()
        self.assertEqual(self.warnings, [])

    def test_metadata_is_plain_bounded_wrapped_and_passive_at_both_widths(self):
        choose = QSignalSpy(self.manager.chooseFileRequested)
        enable = QSignalSpy(self.manager.enableRequested)
        origin = QSignalSpy(self.manager.openOriginRequested)
        hostile = "<b>Declaração literal</b> " * 20
        self.manager.setProperty("addons", [package(author=hostile, origin="https://example.org/" + "x" * 480)])
        for width, height in ((350, 360), (420, 640)):
            for scheme in ("dark", "light"):
                with self.subTest(width=width, scheme=scheme):
                    self.window.setWidth(width)
                    self.window.setHeight(height)
                    self.window.setProperty("schemeName", scheme)
                    details = self.control("addonDetails-org.example.battery")
                    if not details.property("checked"):
                        self.press(details, Qt.Key_Return)
                    QTest.qWait(50)
                    author = self.control("addonMetadataAuthor-org.example.battery")
                    self.assertEqual(author.property("text"), hostile[:120])
                    for name in ("addonMetadataAuthor-org.example.battery", "addonMetadataOrigin-org.example.battery", "addonGuidance-org.example.battery"):
                        label = self.control(name)
                        self.assertTrue(self.evaluate(label, "textFormat === Text.PlainText"))
                        self.assertTrue(self.evaluate(label, "Qt.colorEqual(color, palette.windowText)"))
                        self.assertFalse(label.property("truncated"))
                        self.assertGreater(label.width(), 0)
                        self.assertLessEqual(label.width(), width - 24)
                    self.assertTrue(details.hasActiveFocus())
        self.assertEqual(choose.count(), 0)
        self.assertEqual(enable.count(), 0)
        self.assertEqual(origin.count(), 0)
        self.press(self.control("addonOrigin-org.example.battery"))
        self.assertEqual(origin.at(0), ["https://example.org/" + "x" * 480])
        self.assertEqual(self.warnings, [])

    def test_tab_reveals_focused_controls_in_short_parent_viewport(self):
        self.manager.setProperty("addons", [package(previousSha256="b" * 64)])
        QTest.qWait(40)
        add = self.control("addonChooseFile")
        add.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem(), self.control("addonEnable-org.example.battery"))
        QTest.keyClick(self.window, Qt.Key_Tab)
        disclosure = self.control("addonDetails-org.example.battery")
        self.assertEqual(self.window.activeFocusItem(), disclosure)
        QTest.keyClick(self.window, Qt.Key_Return)
        QTest.qWait(60)
        self.assertTrue(disclosure.property("checked"))
        QTest.keyClick(self.window, Qt.Key_Tab)
        QTest.qWait(60)
        origin = self.control("addonOrigin-org.example.battery")
        self.assertEqual(self.window.activeFocusItem(), origin)
        top = origin.mapToScene(QPointF(0, 0)).y()
        self.assertGreaterEqual(top - 3, 0)
        self.assertLessEqual(top + origin.height() + 3, self.window.height())
        self.assertEqual(self.warnings, [])

    def test_invalid_preview_hash_is_not_truncated_into_an_installable_identity(self):
        self.manager.setProperty("preview", package(sha256="a" * 65))
        QTest.qWait(30)
        self.assertFalse(self.control("addonPreviewInstall").isEnabled())

    def test_preview_is_the_first_keyboard_action_and_install_does_not_activate_row(self):
        self.manager.setProperty("preview", package())
        QTest.qWait(30)
        install = self.control("addonPreviewInstall")
        install.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem(), self.control("addonDetailsPreview"))
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem(), self.control("addonChooseFile"))
        enable = QSignalSpy(self.manager.enableRequested)
        self.manager.setProperty("preview", None)
        self.manager.setProperty("addons", [package()])
        QTest.qWait(30)
        self.assertEqual(enable.count(), 0)
        self.assertFalse(self.control("addonDisable-org.example.battery").isVisible())

    def test_cancel_restore_and_stale_confirmation_emit_no_mutation(self):
        rollback = QSignalSpy(self.manager.rollbackRequested)
        self.manager.setProperty("addons", [package(previousSha256="b" * 64)])
        QTest.qWait(30)
        self.press(self.control("addonDetails-org.example.battery"))
        self.press(self.control("addonRollback-org.example.battery"))
        self.press(self.control("addonCancel-org.example.battery"))
        self.assertEqual(rollback.count(), 0)
        self.assertFalse(self.control("addonConfirmation-org.example.battery").isVisible())
        self.press(self.control("addonRollback-org.example.battery"))
        self.manager.setProperty("addons", [package(sha256="c" * 64, previousSha256="b" * 64)])
        QTest.qWait(30)
        self.assertFalse(self.control("addonConfirmation-org.example.battery").isVisible())
        self.assertEqual(rollback.count(), 0)
        self.assertEqual(self.warnings, [])

    def test_first_inline_confirmation_reveals_focus_after_expanding_layout(self):
        self.manager.setProperty("addons", [package()])
        QTest.qWait(30)
        self.press(self.control("addonDetails-org.example.battery"))
        self.press(self.control("addonRemove-org.example.battery"))
        QTest.qWait(60)
        confirm = self.control("addonConfirm-org.example.battery")
        self.assertTrue(confirm.hasActiveFocus())
        top = confirm.mapToScene(QPointF(0, 0)).y()
        self.assertGreaterEqual(top - 3, 0)
        self.assertLessEqual(top + confirm.height() + 3, self.window.height())
        self.assertEqual(self.warnings, [])

    def test_full_32_id_list_uses_parent_scroll_and_last_action_remains_reachable(self):
        rows = [package(id=f"org.example.battery{i}", name=f"Bateria local {i + 1}") for i in range(32)]
        self.manager.setProperty("addons", rows)
        QTest.qWait(60)
        self.assertGreater(self.manager.height(), self.window.height() * 10)
        enable = QSignalSpy(self.manager.enableRequested)
        last = self.control("addonEnable-org.example.battery31")
        self.press(last, Qt.Key_Return)
        self.assertEqual(enable.at(0), ["org.example.battery31", "a" * 64])
        top = last.mapToScene(QPointF(0, 0)).y()
        self.assertGreaterEqual(top - 3, 0)
        self.assertLessEqual(top + last.height() + 3, self.window.height())
        self.assertEqual(self.warnings, [])

    def test_statuses_never_turn_activation_into_a_freshness_claim(self):
        for state, expected in (("stale", "Dados desatualizados"), ("unavailable", "Leitura indisponível"),
                                ("invalid", "Ativação indisponível"), ("ready", "Ativado para leitura local")):
            with self.subTest(state=state):
                self.manager.setProperty("addons", [package(enabled=True, state=state)])
                QTest.qWait(20)
                self.assertIn(expected, self.control("addonStatus-org.example.battery").property("text"))
                self.assertTrue(self.control("addonDisable-org.example.battery").isEnabled())
        self.assertEqual(self.warnings, [])

    def test_escape_cancels_inline_confirmation_and_deferred_reveal_keeps_newer_focus(self):
        self.manager.setProperty("addons", [package()])
        QTest.qWait(30)
        self.press(self.control("addonDetails-org.example.battery"))
        self.press(self.control("addonRemove-org.example.battery"))
        QTest.keyClick(self.window, Qt.Key_Escape)
        QTest.qWait(30)
        self.assertFalse(self.control("addonConfirmation-org.example.battery").isVisible())
        remove = self.control("addonRemove-org.example.battery")
        self.assertEqual(self.window.activeFocusItem(), remove)
        # Dispatch the click without draining deferred layout/focus work first.
        remove.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        outside = self.control("outsideFocus")
        outside.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(60)
        self.assertEqual(self.window.activeFocusItem(), outside)
        self.assertEqual(self.warnings, [])

    def test_preview_requires_explicit_install_of_exact_hash_and_never_enables(self):
        install = QSignalSpy(self.manager.installRequested)
        enable = QSignalSpy(self.manager.enableRequested)
        self.manager.setProperty("preview", package())
        QTest.qWait(40)
        action = self.control("addonPreviewInstall")
        self.assertTrue(action.isEnabled())
        self.assertEqual(action.property("variant"), "primary")
        self.assertEqual(self.control("addonChooseFile").property("variant"), "secondary")
        permission = self.control("addonPreviewPermission")
        self.assertIn("somente leitura", permission.property("text"))
        self.assertIn("não ativa", permission.property("text"))
        self.assertEqual(install.count(), 0)
        self.press(action, Qt.Key_Return)
        self.assertEqual(install.count(), 1)
        self.assertEqual(install.at(0), ["a" * 64])
        self.assertEqual(enable.count(), 0)
        self.manager.setProperty("busy", True)
        self.assertFalse(action.isEnabled())
        self.assertFalse(self.control("addonChooseFile").isEnabled())
        self.manager.setProperty("busy", False)
        self.manager.setProperty("preview", package(valid=False))
        QTest.qWait(20)
        self.assertFalse(self.control("addonPreviewInstall").isEnabled())
        self.assertEqual(self.warnings, [])

    def test_installed_actions_are_explicit_and_bound_to_id_and_current_hash(self):
        enable = QSignalSpy(self.manager.enableRequested)
        disable = QSignalSpy(self.manager.disableRequested)
        remove = QSignalSpy(self.manager.removeRequested)
        rollback = QSignalSpy(self.manager.rollbackRequested)
        self.manager.setProperty("addons", [package(previousSha256="b" * 64)])
        QTest.qWait(40)
        self.assertEqual(enable.count(), 0)
        self.press(self.control("addonEnable-org.example.battery"))
        self.assertEqual(enable.at(0), ["org.example.battery", "a" * 64])
        self.assertIn("Desativado", self.control("addonStatus-org.example.battery").property("text"))
        self.manager.setProperty("addons", [package(enabled=True, state="missing", previousSha256="b" * 64)])
        QTest.qWait(30)
        self.press(self.control("addonDisable-org.example.battery"))
        self.assertEqual(disable.at(0), ["org.example.battery", "a" * 64])
        self.press(self.control("addonDetails-org.example.battery"))
        self.press(self.control("addonRollback-org.example.battery"))
        self.assertIn("não ativa", self.control("addonConfirmation-org.example.battery").property("text"))
        self.press(self.control("addonConfirm-org.example.battery"), Qt.Key_Return)
        self.assertEqual(rollback.at(0), ["org.example.battery", "a" * 64])
        self.press(self.control("addonRemove-org.example.battery"))
        self.assertEqual(remove.count(), 0)
        confirm = self.control("addonConfirm-org.example.battery")
        self.assertTrue(confirm.hasActiveFocus())
        top = confirm.mapToScene(QPointF(0, 0)).y()
        self.assertGreaterEqual(top - 3, 0)
        self.assertLessEqual(top + confirm.height() + 3, self.window.height())
        self.press(self.control("addonConfirm-org.example.battery"))
        self.assertEqual(remove.at(0), ["org.example.battery", "a" * 64])
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
