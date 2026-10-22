import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest


class ControlCenterSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ControlCenterSessionHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        QTest.qWait(25)
        self.session = self.window.property("session")
        self.popup = self.window.property("popup")
        self.audio = self.window.findChild(QObject, "sessionAudioState")
        self.backend = self.window.findChild(QObject, "sessionAudioBackend")

    def tearDown(self):
        if self.engine.rootObjects():
            self.window.close()
            self.evaluate("barWindow.close()")
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.window, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def values(self, object_, name):
        value = object_.property(name)
        return value.toVariant() if hasattr(value, "toVariant") else value

    def settle(self):
        QTest.qWait(35)
        self.assertEqual(self.warnings, [])

    def test_dock_and_bar_open_same_audio_without_writes_on_queued_boundary(self):
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.assertFalse(self.popup.property("visible"))
        self.settle()
        self.assertTrue(self.popup.property("visible"))
        self.assertTrue(self.session.property("dockOrigin"))
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(firstClient)"))
        self.assertFalse(self.session.property("dockOrigin"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock", "bar"])
        self.assertEqual(self.values(self.backend, "calls"), [])
        self.assertEqual(self.values(self.window, "receipts"), [])
        self.assertEqual(self.window.findChild(QObject, "sessionAudioState"), self.audio)


    def test_destroying_current_host_closes_and_dock_can_reopen_without_warnings(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.evaluate("barHost.destroy()")
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.assertTrue(self.session.property("dockOrigin"))
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_transfer_waits_until_previous_native_backend_is_destroyed(self):
        lifetime = QObject(self.window)
        self.window.setProperty("backendLifetimeFixture", lifetime)
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        # Loader.item clears before its QObject's deferred destruction completes.
        self.window.setProperty("backendLifetimeFixture", None)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        lifetime.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(firstClient)"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock", "bar"])
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_backend_destruction_does_not_revive_a_cancelled_transfer(self):
        lifetime = QObject(self.window)
        self.window.setProperty("backendLifetimeFixture", lifetime)
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.window.setProperty("backendLifetimeFixture", None)
        self.evaluate("session.releaseClient(firstClient)")
        lifetime.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_backend_destruction_does_not_reopen_after_owner_destruction(self):
        lifetime = QObject(self.window)
        self.window.setProperty("backendLifetimeFixture", lifetime)
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.window.setProperty("backendLifetimeFixture", None)
        self.evaluate("ownerItem.destroy()")
        self.settle()
        lifetime.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertIsNone(self.window.property("session"))
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_transfer_waits_for_hidden_native_window_to_deactivate(self):
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.evaluate("popup.nativeDialog.active = true")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.evaluate("popup.nativeDialog.active = false")
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(firstClient)"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock", "bar"])
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_transfer_waits_for_actual_keyboard_departure_not_transient_family_activity(self):
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.evaluate("popup.nativeDialog.activeFocusItem = ownerItem.anchor; popup.nativeDialog.active = false")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.evaluate("popup.nativeDialog.active = true; popup.nativeDialog.activeFocusItem = null")
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(firstClient)"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock", "bar"])
        self.settle()
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock", "bar"])
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_transfer_waits_for_exit_and_native_hide_and_only_latest_client_opens(self):
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.popup.setProperty("asynchronousClose", True)
        self.popup.setProperty("holdNativeVisible", True)
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.assertTrue(self.evaluate("session.openFromClient(secondClient, barHost, barAnchor)"))
        self.settle()
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.evaluate("popup.finishClose()")
        self.settle()
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertIsNone(self.popup.property("capturedAnchorAfterClosed"))
        self.evaluate("popup.finishNativeHide()")
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(secondClient)"))
        self.assertFalse(self.evaluate("session.visibleFor(firstClient)"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock", "bar"])
        self.evaluate("session.releaseClient(firstClient)")
        self.evaluate("session.closeDockOrigin()")
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(secondClient)"))

    def test_pending_release_cancels_queued_open_and_stale_old_client_release_is_local(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.evaluate("session.releaseClient(firstClient)")
        self.settle()
        self.assertEqual(self.values(self.window, "openedHosts"), [])
        self.assertTrue(self.evaluate("session.openFromClient(secondClient, barHost, barAnchor)"))
        self.settle()
        self.evaluate("session.releaseClient(firstClient)")
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(secondClient)"))
        self.evaluate("session.releaseClient(secondClient)")
        self.settle()
        self.assertFalse(self.popup.property("visible"))

    def test_transfer_cancels_actual_audio_request_and_gesture_before_close_and_late_readback(self):
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.assertTrue(self.evaluate("beginVolumeGesture()", self.audio))
        self.assertTrue(self.evaluate("requestGestureVolume(80)", self.audio))
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        self.popup.setProperty("asynchronousClose", True)
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.assertEqual(self.popup.property("pendingAtClose"), "")
        self.assertFalse(self.popup.property("gestureAtClose"))
        self.evaluate("publish(52429, false, 'speakers')", self.backend)
        self.settle()
        self.assertEqual(self.values(self.window, "receipts"), [])
        self.evaluate("popup.finishClose()")
        self.settle()
        self.assertEqual(self.audio.property("confirmedVolume"), 80)
        self.assertTrue(self.evaluate("requestVolume(60)", self.audio))
        self.evaluate("publish(39322, false, 'speakers')", self.backend)
        self.settle()
        self.assertEqual(len(self.values(self.window, "receipts")), 1)
        self.assertEqual(len(self.values(self.backend, "calls")), 2)

    def test_invalid_client_and_changed_validation_do_not_open_or_write(self):
        self.window.setProperty("clientsValid", False)
        self.assertFalse(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.assertIn("indisponível", self.evaluate("session.errorFor(firstClient)"))
        self.assertEqual(self.evaluate("session.errorFor(secondClient)"), "")
        self.window.setProperty("clientsValid", True)
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.window.setProperty("clientsValid", False)
        self.settle()
        self.assertEqual(self.values(self.window, "openedHosts"), [])
        self.assertIn("abrir", self.evaluate("session.errorFor(firstClient)"))
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_pending_anchor_destruction_reports_error_without_dispatch(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.window.property("barAnchor").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.values(self.window, "openedHosts"), [])
        self.assertIn("abrir", self.evaluate("session.errorFor(firstClient)"))

    def test_window_loss_and_current_anchor_destruction_close_without_focus_callback(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.evaluate("barHost.parent = null")
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertIsNone(self.popup.property("capturedAnchorAfterClosed"))
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.evaluate("ownerItem.anchor.destroy()")
        self.settle()
        self.assertFalse(self.popup.property("visible"))

    def test_fake_host_or_cross_window_anchor_is_refused(self):
        self.assertFalse(self.evaluate("session.openFromClient(firstClient, ({width:100, visible:true}), barAnchor)"))
        self.assertFalse(self.evaluate("session.openFromClient(firstClient, barHost, ownerItem.anchor)"))
        self.settle()
        self.assertEqual(self.values(self.window, "openedHosts"), [])
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_async_open_failure_is_bounded_and_visible_only_to_dispatch_client(self):
        self.evaluate("session.performOpen = function() { throw new Error('synthetic open failure'); }")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertIn("abrir", self.evaluate("session.errorFor(firstClient)"))
        self.assertEqual(self.evaluate("session.errorFor(secondClient)"), "")
        self.assertLessEqual(len(self.session.property("error")), 160)
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_normal_escape_restores_owned_focus_and_suppresses_inherited_capture(self):
        self.window.requestActivate()
        QTest.qWait(20)
        self.assertTrue(self.window.isActive())
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.evaluate("popup.forceActiveFocus()")
        self.assertEqual(self.window.activeFocusItem(), self.popup)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertIsNone(self.popup.property("capturedAnchorAfterClosed"))
        self.assertTrue(self.evaluate("ownerItem.anchor.activeFocus"))
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_hiding_host_window_closes_and_cancels_a_queued_open(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.evaluate("barWindow.hide()")
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertFalse(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_client_destruction_closes_current_surface_and_cancels_pending_intention(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.window.property("firstClient").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertTrue(self.evaluate("session.openFromClient(secondClient, barHost, barAnchor)"))
        self.window.property("secondClient").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["bar"])
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_destroying_owner_cancels_queued_commit_and_focus_timer_cleanly(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.window.property("ownerItem").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.values(self.window, "openedHosts"), [])
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_destroying_host_after_normal_close_before_restore_keeps_target_dead(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.evaluate("popup.dismiss()")
        self.window.property("barHost").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertIsNone(self.popup.property("capturedAnchorAfterClosed"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_explicit_shutdown_cancels_audio_before_close_and_owner_teardown(self):
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.assertTrue(self.evaluate("requestMute(true)", self.audio))
        self.evaluate("session.shutdown()")
        self.assertEqual(self.popup.property("pendingAtClose"), "")
        self.assertFalse(self.popup.property("visible"))
        self.assertFalse(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.evaluate("publish(32768, true, 'speakers')", self.backend)
        self.window.property("ownerItem").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertEqual(self.values(self.window, "receipts"), [])

    def test_owner_destruction_after_escape_does_not_run_queued_focus_callback(self):
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.evaluate("popup.dismiss()")
        self.window.property("ownerItem").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertFalse(self.popup.property("visible"))
        self.assertIsNone(self.popup.property("capturedAnchorAfterClosed"))


    def test_same_window_sibling_geometry_host_accepts_real_anchor(self):
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, siblingHost, ownerItem.anchor)"))
        self.settle()
        self.assertTrue(self.evaluate("session.visibleFor(firstClient)"))
        self.assertTrue(self.evaluate("session.host === siblingHost"))
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_host_notification_successor_cannot_mix_dock_anchor_with_bar_host(self):
        self.evaluate("session.hostChanged.connect(function() { if (session.host === barHost) session.openFromDock(ownerItem.anchor); })")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertTrue(self.session.property("dockOrigin"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertTrue(self.popup.property("visible"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_open_callback_successor_survives_predecessor_throw_without_stale_error(self):
        self.evaluate("const normalOpen = session.performOpen; session.performOpen = function() { session.performOpen = normalOpen; session.openFromDock(ownerItem.anchor); throw new Error('superseded callback'); }")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertTrue(self.popup.property("visible"))
        self.assertTrue(self.session.property("dockOrigin"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.evaluate("session.errorFor(firstClient)"), "")
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertEqual(self.values(self.backend, "calls"), [])


    def assert_notification_successor(self, signal, condition):
        self.evaluate(f"let replaced = false; session.{signal}.connect(function() {{ if (!replaced && ({condition})) {{ replaced = true; session.openFromDock(ownerItem.anchor); }} }})")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertTrue(self.popup.property("visible"))
        self.assertTrue(self.session.property("dockOrigin"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_client_notification_successor_preserves_its_host_and_anchor(self):
        self.assert_notification_successor("clientChanged", "session.client === firstClient")

    def test_anchor_notification_successor_is_not_consumed_by_old_commit(self):
        self.assert_notification_successor("_anchorChanged", "session._anchor === barAnchor")

    def test_consuming_pending_notification_does_not_erase_successor(self):
        self.assert_notification_successor("_pendingChanged", "!session._pending && session.host === barHost && session.client === firstClient")

    def test_origin_notification_successor_is_not_overwritten(self):
        self.assert_notification_successor("dockOriginChanged", "!session.dockOrigin")

    def test_async_error_notification_can_accept_successor_without_stale_close(self):
        self.evaluate("const normalOpen = session.performOpen; session.performOpen = function() { session.performOpen = normalOpen; throw new Error('synthetic open failure'); }; let replaced = false; session.errorChanged.connect(function() { if (!replaced && session.error) { replaced = true; session.openFromDock(ownerItem.anchor); } })")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.settle()
        self.assertTrue(self.popup.property("visible"))
        self.assertTrue(self.session.property("dockOrigin"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.evaluate("session.errorFor(firstClient)"), "")
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertEqual(self.values(self.backend, "calls"), [])


    def test_pending_loss_error_notification_preserves_accepted_successor(self):
        self.evaluate("let replaced = false; session.errorChanged.connect(function() { if (!replaced && session.error) { replaced = true; session.openFromDock(ownerItem.anchor); } })")
        self.assertTrue(self.evaluate("session.openFromClient(firstClient, barHost, barAnchor)"))
        self.window.property("barAnchor").deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.settle()
        self.assertTrue(self.popup.property("visible"))
        self.assertTrue(self.session.property("dockOrigin"))
        self.assertTrue(self.evaluate("session.host === ownerItem"))
        self.assertEqual(self.values(self.window, "openedHosts"), ["dock"])
        self.assertEqual(self.values(self.backend, "calls"), [])


    def assert_new_focus_wins_restore(self, signal):
        self.window.requestActivate()
        QTest.qWait(20)
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.evaluate("popup.forceActiveFocus()")
        self.assertEqual(self.window.activeFocusItem(), self.popup)
        self.evaluate(f"popup.{signal}.connect(function() {{ siblingHost.forceActiveFocus(); }})")
        self.evaluate("popup.dismiss()")
        self.assertEqual(self.window.activeFocusItem(), self.window.property("siblingHost"))
        self.settle()
        self.assertEqual(self.window.activeFocusItem(), self.window.property("siblingHost"))
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.values(self.backend, "calls"), [])

    def test_focus_selected_by_closed_observer_wins_over_deferred_restore(self):
        self.assert_new_focus_wins_restore("closed")

    def test_focus_selected_after_about_to_hide_snapshot_wins_over_deferred_restore(self):
        self.assert_new_focus_wins_restore("aboutToHide")


    def test_neutral_window_content_focus_still_restores_normal_escape_target(self):
        self.window.requestActivate()
        QTest.qWait(20)
        self.assertTrue(self.evaluate("session.openFromDock(ownerItem.anchor)"))
        self.settle()
        self.evaluate("popup.forceActiveFocus(); popup.closed.connect(function() { popup.focus = false; contentItem.forceActiveFocus(); })")
        self.evaluate("popup.dismiss()")
        self.assertEqual(self.window.activeFocusItem(), self.window.contentItem())
        self.settle()
        self.assertTrue(self.evaluate("ownerItem.anchor.activeFocus"))
        self.assertFalse(self.popup.property("visible"))
        self.assertEqual(self.values(self.backend, "calls"), [])


if __name__ == "__main__":
    unittest.main()
