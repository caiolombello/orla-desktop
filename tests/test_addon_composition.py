"""Actual manager/data QML with delayed callbacks at the shared service boundary."""
import json
import os
from contextlib import contextmanager
from pathlib import Path
import unittest
from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest, QSignalSpy
from test_addon_peripherals import peripheral_frame


class AddonCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('AddonCompositionHarness.qml').resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.h = self.engine.rootObjects()[0]
        QTest.qWait(5)

    def tearDown(self):
        self.h.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def js(self, source):
        e = QQmlExpression(QQmlEngine.contextForObject(self.h), self.h, source)
        value, _ = e.evaluate()
        self.assertFalse(e.hasError(), e.error().toString())
        return value

    def value(self, source):
        return json.loads(self.js('JSON.stringify(' + source + ')'))

    def reply(self, index, frame):
        self.js(f'reply({index}, {json.dumps(json.dumps(frame))})')
        QTest.qWait(5)

    def test_open_settings_waits_for_unresolved_physical_data_call(self):
        self.assertEqual(self.value('calls.map(c => c.message.member)'), ['SnapshotFor'])
        self.js('surfaceOpen = true')
        QTest.qWait(5)
        self.assertEqual(self.value('calls.map(c => c.message.member)'), ['SnapshotFor'])
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertTrue(self.js('data.addonCallPending'))
        self.reply(0, peripheral_frame())
        self.assertEqual(self.value('calls.map(c => c.message.member)'), ['SnapshotFor', 'ListAddons'])
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)

    def metadata(self, enabled=True, generation='b' * 32, addons=None):
        manifest = dict(formatVersion='0.1-experimental', id='org.example.battery', name='Bateria local',
            description='Dados compartilhados localmente.', author='Projeto Exemplo', license='MIT', version='1.0.0',
            origin='https://example.org/battery', renderer='peripheral-battery',
            source=dict(namespace='synthetic-battery', formatVersion='0.1-experimental'))
        rows = [dict(manifest=manifest, sha256='a' * 64, previousSha256=None, enabled=enabled)] if addons is None else addons
        return dict(formatVersion='0.1-experimental', ok=True, result=dict(generation=generation, addons=rows))

    def open_ready(self, enabled=True):
        self.reply(0, peripheral_frame())
        self.js('surfaceOpen = true')
        QTest.qWait(5)
        self.reply(1, self.metadata(enabled))
        self.assertTrue(self.js('manager.valid'))

    def test_startup_without_settings_pins_data_without_metadata_or_consent(self):
        self.reply(0, peripheral_frame(percent=0))
        self.assertEqual(self.js('data.peripherals.devices[0].percent'), 0)
        self.assertEqual(self.value('calls.map(c => c.message.member)'), ['SnapshotFor'])
        self.assertFalse(self.js('manager.active'))
        self.assertFalse(self.js('coordinator.reloadRequired'))

    def test_cancel_while_waiting_and_duplicate_data_reply_never_open_metadata(self):
        self.js('surfaceOpen = true; scope = "profile-b"; surfaceOpen = false')
        QTest.qWait(5)
        self.assertTrue(self.js('data.addonCallPending'))
        self.assertTrue(self.js('data.addonSuspended'))
        self.reply(0, peripheral_frame())
        self.assertEqual(self.value('calls.map(c => c.message.member)'), ['SnapshotFor', 'SnapshotFor'])
        self.reply(0, peripheral_frame(percent=99))
        self.assertTrue(self.js('data.addonCallPending'))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(1, peripheral_frame(percent=0))
        self.assertEqual(self.js('data.peripherals.devices[0].percent'), 0)

    def test_metadata_browsing_pauses_exports_until_close_and_adopts_only_enabled_identity(self):
        self.open_ready(enabled=False)
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='b'*32, sha256=None))
        self.assertEqual(len(self.value('calls')), 2)
        self.js('surfaceOpen = false')
        QTest.qWait(5)
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('calls.map(c => c.message.member)'), ['SnapshotFor', 'ListAddons', 'SnapshotFor'])

    def test_closed_dispatched_mutation_settles_and_recovers_readonly_before_resume(self):
        self.open_ready()
        self.assertTrue(self.js("manager.disableAddon('org.example.battery', '" + 'a'*64 + "')"))
        self.js('surfaceOpen = false')
        self.reply(2, self.metadata(False, 'c'*32))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.value('calls[3].message.member'), 'ListAddons')
        self.reply(3, self.metadata(False, 'c'*32))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))
        self.assertEqual(self.value('calls[4].message.member'), 'SnapshotFor')
        self.reply(2, self.metadata(True, 'd'*32))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))

    def test_destroyed_owner_during_remove_cannot_lose_physical_cleanup(self):
        self.open_ready()
        self.js('surfaceOwner = Qt.createQmlObject("import QtQuick; QtObject {}", harness)')
        QTest.qWait(5)
        self.reply(2, self.metadata())
        self.assertTrue(self.js("manager.removeAddon('org.example.battery', '" + 'a'*64 + "')"))
        self.js('surfaceOwner.destroy()')
        QTest.qWait(5)
        self.reply(3, self.metadata(False, 'c'*32, []))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.value('calls[4].message.member'), 'ListAddons')
        self.reply(4, self.metadata(False, 'c'*32, []))
        self.assertFalse(self.js('data.addonSuspended'))

    def test_unknown_mutation_deadline_does_not_fabricate_physical_settlement(self):
        self.open_ready(enabled=False)
        self.js('manager.deadline.interval = 12')
        self.assertTrue(self.js("manager.enableAddon('org.example.battery', '" + 'a'*64 + "')"))
        QTest.qWait(25)
        self.assertTrue(self.js('coordinator.physical !== null'))
        self.assertTrue(self.js('coordinator.busy'))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(len(self.value('calls')), 3)
        self.js('manager.deadline.interval = 7000')
        self.reply(2, self.metadata(True, 'c'*32))
        self.assertFalse(self.js('manager.valid'))
        self.assertEqual(self.value('calls[3].message.member'), 'ListAddons')
        self.reply(3, self.metadata(True, 'c'*32))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256='a'*64))
        self.assertEqual(self.value('calls.map(c => c.message.member)').count('EnableAddon'), 1)

    def test_external_identity_change_requires_explicit_readonly_reload(self):
        self.reply(0, peripheral_frame())
        self.js('data.refresh()')
        changed = peripheral_frame()
        changed['peripherals']['addon']['generation'] = 'c'*32
        self.reply(1, changed)
        self.assertTrue(self.js('coordinator.reloadRequired'))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(len(self.value('calls')), 2)
        self.assertTrue(self.js('coordinator.reload()'))
        QTest.qWait(5)
        self.assertEqual(self.value('calls[2].message.member'), 'ListAddons')
        self.reply(2, self.metadata(True, 'c'*32))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256='a'*64))

    def test_stale_picker_scope_and_metadata_aba_are_rejected(self):
        self.open_ready(enabled=False)
        self.assertTrue(self.js('token = manager.beginFileSelection(harness); token !== null'))
        self.js('scope = "profile-b"; scope = "profile-a"')
        self.assertFalse(self.js('manager.acceptFileSelection(harness, token, "file:///synthetic/package")'))
        QTest.qWait(5)
        self.reply(2, self.metadata(False, 'c'*32))
        self.reply(1, self.metadata(True, 'd'*32))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))
        self.assertIsNone(self.value('manager.preview'))

    def test_reentrant_close_during_metadata_publication_cannot_resume_partial_identity(self):
        self.reply(0, peripheral_frame())
        self.js('surfaceOpen = true; reenter = "close-publish"')
        QTest.qWait(5)
        self.reply(1, self.metadata())
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.value('calls[2].message.member'), 'ListAddons')
        self.js('reenter = ""')
        self.reply(2, self.metadata(False, 'c'*32))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))

    def test_cancelled_opening_preserves_previously_validated_data_identity(self):
        self.reply(0, peripheral_frame())
        self.js('data.refresh(); surfaceOpen = true; surfaceOpen = false')
        self.reply(1, peripheral_frame())
        changed = peripheral_frame()
        changed['peripherals']['addon']['generation'] = 'c'*32
        self.reply(2, changed)
        self.assertTrue(self.js('coordinator.reloadRequired'))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)

    def test_reentrant_reopening_during_identity_resume_cannot_unsuspend_new_surface(self):
        self.reply(0, peripheral_frame())
        self.js('data.refresh(); surfaceOpen=true; surfaceOpen=false; reenter="resume-open"')
        self.reply(1, peripheral_frame())
        self.assertEqual(self.js('resumeLeaks'), 0)
        self.assertTrue(self.js('surfaceOpen'))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor','SnapshotFor','ListAddons'])

    def test_origin_requires_current_valid_metadata_explicit_request_and_safe_https(self):
        self.open_ready()
        self.assertFalse(self.js('coordinator.openOrigin("https://example.org/other")'))
        self.assertFalse(self.js('coordinator.openOrigin("https://user@example.org/battery")'))
        self.assertFalse(self.js('coordinator.openOrigin("http://example.org/battery")'))
        self.assertTrue(self.js('coordinator.openOrigin("https://example.org/battery")'))
        self.js('surfaceOpen = false')
        self.assertFalse(self.js('coordinator.openOrigin("https://example.org/battery")'))
        self.assertEqual(len(self.value('calls')), 2)


    def test_cancel_at_admission_before_list_resumes_only_fresh_pinned_reading(self):
        self.reply(0, peripheral_frame())
        observer = """import QtQuick; Connections {
            target: coordinator
            function onAdmittedChanged() { if (coordinator.admitted) harness.surfaceOpen=false; }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(30)
        self.assertFalse(self.js('surfaceOpen'))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertFalse(self.js('coordinator.reloadRequired'))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'SnapshotFor'])
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='b'*32, sha256='a'*64))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(0, peripheral_frame(percent=99))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(1, peripheral_frame(percent=0))
        self.assertEqual(self.js('data.peripherals.devices[0].percent'), 0)

    def test_queued_close_after_data_settlement_before_list_resumes_pinned_reader(self):
        self.reply(0, peripheral_frame())
        self.js('data.refresh(); surfaceOpen=true')
        QTest.qWait(10)
        observer = """import QtQuick; Connections {
            target: data
            function onAddonCallPendingChanged() {
                if (!data.addonCallPending && harness.surfaceOpen)
                    Qt.callLater(function() { harness.surfaceOpen=false; });
            }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness)')
        self.reply(1, peripheral_frame())
        QTest.qWait(30)
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertFalse(self.js('coordinator.reloadRequired'))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor']*3)
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='b'*32, sha256='a'*64))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(2, peripheral_frame(percent=0))
        self.assertEqual(self.js('data.peripherals.devices[0].percent'), 0)


    def test_close_after_list_dispatch_keeps_physical_barrier_and_requires_current_list(self):
        self.reply(0, peripheral_frame())
        self.js('surfaceOpen=true')
        QTest.qWait(10)
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'ListAddons'])
        self.js('surfaceOpen=false')
        QTest.qWait(10)
        self.assertTrue(self.js('coordinator.busy'))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(1, self.metadata(True, 'c'*32))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'ListAddons', 'ListAddons'])
        self.reply(2, self.metadata(False, 'd'*32))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='d'*32, sha256=None))
        self.assertEqual(self.value('calls[3].message.member'), 'SnapshotFor')

    def test_source_changed_latch_survives_pristine_admission_cancel_until_explicit_reload(self):
        self.reply(0, peripheral_frame())
        self.js('data.refresh()')
        changed = peripheral_frame()
        changed['peripherals']['addon']['generation'] = 'c'*32
        self.reply(1, changed)
        self.assertTrue(self.js('coordinator.reloadRequired'))
        observer = """import QtQuick; Connections {
            target: coordinator
            function onAdmittedChanged() { if (coordinator.admitted) harness.surfaceOpen=false; }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(30)
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertTrue(self.js('coordinator.reloadRequired'))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'SnapshotFor'])
        self.assertTrue(self.js('coordinator.reload()'))
        QTest.qWait(10)
        self.reply(2, self.metadata(True, 'c'*32))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256='a'*64))

    def test_invalid_listing_latch_survives_cancelled_reopening(self):
        self.open_ready()
        self.assertTrue(self.js('coordinator.reload()'))
        self.reply(2, dict(formatVersion='0.1-experimental', ok=True, result=dict(addons=[])))
        self.js('surfaceOpen=false')
        QTest.qWait(10)
        observer = """import QtQuick; Connections {
            target: coordinator
            function onAdmittedChanged() { if (coordinator.admitted) harness.surfaceOpen=false; }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(30)
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertTrue(self.js('coordinator.reloadRequired'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='b'*32, sha256='a'*64))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'ListAddons', 'ListAddons'])
        self.assertTrue(self.js('coordinator.reload()'))
        QTest.qWait(10)
        self.reply(3, self.metadata(False, 'c'*32))
        self.assertFalse(self.js('data.addonSuspended'))

    def test_owner_and_scope_aba_during_admission_require_current_listing_without_unpausing(self):
        self.reply(0, peripheral_frame())
        observer = """import QtQuick; Connections {
            target: coordinator
            property bool changed: false
            function onAdmittedChanged() {
                if (!coordinator.admitted || changed) return;
                changed=true;
                const original=harness.surfaceOwner;
                harness.scope="profile-b";
                harness.scope="profile-a";
                harness.surfaceOwner=Qt.createQmlObject("import QtQuick; QtObject {}", harness);
                harness.surfaceOwner=original;
            }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(30)
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'ListAddons'])
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.js('resumeLeaks'), 0)
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(1, self.metadata(False, 'c'*32))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))
        self.js('surfaceOpen=false')
        QTest.qWait(10)
        self.assertFalse(self.js('data.addonSuspended'))

    def test_queued_close_then_reopen_cannot_resume_old_data_before_current_metadata(self):
        self.reply(0, peripheral_frame())
        self.js('data.refresh(); surfaceOpen=true')
        QTest.qWait(10)
        observer = """import QtQuick; Connections {
            target: data
            property bool changed: false
            function onAddonCallPendingChanged() {
                if (data.addonCallPending || changed || !harness.surfaceOpen) return;
                changed=true;
                Qt.callLater(function() { harness.surfaceOpen=false; harness.surfaceOpen=true; });
            }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness)')
        self.reply(1, peripheral_frame())
        QTest.qWait(20)
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'SnapshotFor', 'ListAddons'])
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.js('resumeLeaks'), 0)
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(2, self.metadata(False, 'c'*32))
        self.js('surfaceOpen=false')
        QTest.qWait(10)
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))
        self.reply(1, peripheral_frame(percent=99))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)


    def test_close_during_list_reservation_resumes_without_orphan_metadata_latch(self):
        self.reply(0, peripheral_frame())
        observer = """import QtQuick; Connections {
            target: coordinator
            property bool closed: false
            function onPhysicalChanged() {
                if (coordinator.physical !== null && !closed) {
                    closed=true;
                    harness.surfaceOpen=false;
                }
            }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(40)
        self.assertFalse(self.js('surfaceOpen'))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertFalse(self.js('coordinator.reloadRequired'))
        self.assertFalse(self.js('coordinator.busy'))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'SnapshotFor'])
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='b'*32, sha256='a'*64))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(0, peripheral_frame(percent=99))
        self.assertTrue(self.js('data.addonCallPending'))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(1, peripheral_frame(percent=0))
        self.assertEqual(self.js('data.peripherals.devices[0].percent'), 0)


    def test_reservation_owner_scope_aba_preserves_newer_exact_pending_list(self):
        self.reply(0, peripheral_frame())
        observer = """import QtQuick; Connections {
            target: coordinator
            property bool changed: false
            function onPhysicalChanged() {
                if (coordinator.physical === null || changed) return;
                changed=true;
                const original=harness.surfaceOwner;
                harness.scope="profile-b";
                harness.scope="profile-a";
                harness.surfaceOwner=Qt.createQmlObject("import QtQuick; QtObject {}", harness);
                harness.surfaceOwner=original;
            }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(40)
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'ListAddons'])
        self.js('token=coordinator.physical')
        self.assertTrue(self.js('token !== null && coordinator.busy'))
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertEqual(self.js('resumeLeaks'), 0)
        self.reply(0, peripheral_frame(percent=99))
        self.assertTrue(self.js('coordinator.physical === token'))
        self.assertTrue(self.js('coordinator.busy'))
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(1, self.metadata(False, 'c'*32))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))
        self.js('surfaceOpen=false')
        QTest.qWait(10)
        self.assertFalse(self.js('data.addonSuspended'))

    def test_source_changed_before_reservation_cancel_requires_current_readonly_recovery(self):
        self.reply(0, peripheral_frame())
        self.js('data.refresh()')
        changed = peripheral_frame()
        changed['peripherals']['addon']['generation'] = 'c'*32
        self.reply(1, changed)
        self.assertTrue(self.js('coordinator.reloadRequired'))
        observer = """import QtQuick; Connections {
            target: coordinator
            property bool closed: false
            function onPhysicalChanged() {
                if (coordinator.physical !== null && !closed) {
                    closed=true;
                    harness.surfaceOpen=false;
                }
            }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(40)
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertTrue(self.js('coordinator.reloadRequired'))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'SnapshotFor', 'ListAddons'])
        self.assertEqual(self.js('data.peripherals.devices.length'), 0)
        self.reply(2, self.metadata(False, 'c'*32))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))

    def test_invalid_listing_before_reservation_cancel_keeps_uncertainty_until_valid_list(self):
        self.open_ready()
        self.assertTrue(self.js('coordinator.reload()'))
        self.reply(2, dict(formatVersion='0.1-experimental', ok=True, result=dict(addons=[])))
        self.js('surfaceOpen=false')
        QTest.qWait(10)
        observer = """import QtQuick; Connections {
            target: coordinator
            property bool closed: false
            function onPhysicalChanged() {
                if (coordinator.physical !== null && !closed) {
                    closed=true;
                    harness.surfaceOpen=false;
                }
            }
        }"""
        self.js('Qt.createQmlObject(' + json.dumps(observer) + ', harness); surfaceOpen=true')
        QTest.qWait(40)
        self.assertTrue(self.js('data.addonSuspended'))
        self.assertTrue(self.js('coordinator.reloadRequired'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='b'*32, sha256='a'*64))
        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['SnapshotFor', 'ListAddons', 'ListAddons', 'ListAddons'])
        self.reply(3, self.metadata(False, 'c'*32))
        self.assertFalse(self.js('data.addonSuspended'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='c'*32, sha256=None))


class DockCompositionTests(unittest.TestCase):
    app = None
    metadata = AddonCompositionTests.metadata
    js = AddonCompositionTests.js
    value = AddonCompositionTests.value

    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        from PySide6.QtCore import QObject
        from PySide6.QtQuick import QQuickItem
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('QmlHarness.qml').resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.h = self.engine.rootObjects()[0]
        self.dock = self.h.findChild(QQuickItem, 'dock')
        self.popup = self.h.findChild(QObject, 'settingsPopup')
        self.h.resize(900, 900)
        code = '''import QtQuick; QtObject { property var host; function asyncCall(message, resolve, reject) {
            host.addonCalls = host.addonCalls.concat([{message:message,resolve:resolve,reject:reject}]);
        }}'''
        self.js('addonTransport = Qt.createQmlObject(' + json.dumps(code) + ', this); addonTransport.host = this')
        self.dock_js('anchors.centerIn=undefined; x=40; y=24; settings.popupType=0')
        QTest.qWait(15)

    def tearDown(self):
        self.app.processEvents()
        self.h.close()
        self.h.deleteLater()
        QCoreApplication.sendPostedEvents(self.h, QEvent.DeferredDelete)
        QTest.qWait(10)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def dock_js(self, source):
        from PySide6.QtQuick import QQuickItem
        e = QQmlExpression(QQmlEngine.contextForObject(self.h.findChild(QQuickItem, 'dockSurface')), self.dock, source)
        value, _ = e.evaluate()
        self.assertFalse(e.hasError(), e.error().toString())
        return value

    def control(self, name):
        item = self.dock_js("(function find(item) { if (item.objectName === " + json.dumps(name)
            + ") return item; for (const child of item.children) { const found = find(child); if (found) return found; } return null; })(settingsContents)")
        self.assertIsNotNone(item, name)
        return item

    def open_widgets(self, width=350, height=360):
        self.popup.setProperty('width', width)
        self.popup.setProperty('heightBudget', height)
        self.dock_js('settings.open()')
        self.control('settingsTabs').setProperty('currentIndex', 1)
        for _ in range(100):
            if self.dock_js('integrations.addonCallPending || addonsSession.manager.busy || addonsSession.manager.feedback.length > 0'):
                break
            QTest.qWait(10)
        QTest.qWait(30)
        self.assertTrue(self.dock_js('integrations.addonCallPending || addonsSession.manager.active'), self.dock_js('JSON.stringify({visible:settings.visible, context:contextCommandsVisible, tab:settingsContents.widgetsTabActive, editing:appearance.editing, admitted:addonsSession.admitted, paused:addonsSession.paused, surface:addonsSession.surfaceActive, pending:integrations.addonCallPending})'))

    def reply(self, index, frame):
        raw = json.dumps(json.dumps(frame))
        self.js(f'addonCalls[{index}].resolve({{values:[{{}}], value:{{value:{raw}}}}})')
        QTest.qWait(15)

    def test_real_widgets_tab_is_passive_and_owns_only_one_scroll(self):
        self.assertEqual(self.value('addonCalls'), [])
        self.open_widgets()
        self.assertEqual(self.value('addonCalls.map(c => c.message.member)'), ['ListAddons'])
        self.assertFalse(self.dock_js('configuration.showPeripherals'))
        self.reply(0, self.metadata(False))
        manager = self.control('addonManager')
        self.assertTrue(manager.isVisible())
        self.assertFalse(manager.property('profilePeripheralVisible'))
        self.assertIn('Desativado', self.control('addonStatus-org.example.battery').property('text'))
        self.assertTrue(self.dock_js('addonPicker.parentWindow === settings.nativeDialog'))
        self.assertFalse(self.dock_js('addonPicker.visible'))
        self.control('settingsTabs').setProperty('currentIndex', 0)
        QTest.qWait(15)
        self.assertFalse(self.dock_js('addonsSession.manager.active'))
        self.assertEqual(len(self.value('addonCalls')), 1)

    def test_real_settings_controls_reveal_focus_rings_at_350_420_and_short_heights(self):
        from PySide6.QtCore import QPointF, Qt
        for width, height in ((350, 300), (350, 360), (420, 360), (420, 480)):
            with self.subTest(width=width, height=height):
                if self.popup.property('visible'):
                    closed = QSignalSpy(self.popup.closed)
                    self.popup.close()
                    if not closed.count():
                        self.assertTrue(closed.wait(1000))
                start = len(self.value('addonCalls'))
                self.open_widgets(width, height)
                self.reply(start, self.metadata(False))
                viewport = self.control('widgetScroll').property('contentItem')
                for name in ('addonChooseFile', 'addonEnable-org.example.battery', 'addonReload'):
                    item = self.control(name)
                    item.forceActiveFocus(Qt.TabFocusReason)
                    QTest.qWait(25)
                    self.assertEqual(self.h.activeFocusItem(), item)
                    top = item.mapToItem(viewport, QPointF(0, 0)).y()
                    self.assertGreaterEqual(top - 2, -0.5, name)
                    self.assertLessEqual(top + item.height() + 2, viewport.height() + 0.5, name)
                primary = json.loads(self.dock_js("JSON.stringify((function collect(item) { let result = item.visible && item.variant === 'primary' ? [item.objectName] : []; for (const child of item.children) result = result.concat(collect(child)); return result; })(settingsContents))"))
                self.assertEqual(primary, ['addonChooseFile'])
                self.assertFalse(self.dock_js('configuration.showPeripherals'))

    def test_real_install_uses_picker_approval_and_keeps_new_package_off(self):
        from PySide6.QtCore import Qt
        self.open_widgets()
        self.reply(0, self.metadata(False, None, []))
        self.dock_js('addonPicker.selectionToken = addonsSession.manager.beginFileSelection(addonPicker); addonPicker.selectionState=addonsSession.manager')
        self.assertTrue(self.dock_js('addonsSession.manager.acceptFileSelection(addonPicker, addonPicker.selectionToken, "file:///synthetic/package")'))
        manifest = self.metadata()['result']['addons'][0]['manifest']
        self.reply(1, dict(formatVersion='0.1-experimental', ok=True, result=dict(manifest=manifest, sha256='a'*64)))
        install = self.control('addonPreviewInstall')
        install.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.h, Qt.Key_Return)
        QTest.qWait(10)
        self.assertEqual(self.value('addonCalls[2].message.arguments'), ['file:///synthetic/package', 'a'*64])
        self.reply(2, self.metadata(False, 'c'*32))
        self.assertFalse(self.dock_js('addonsSession.manager.addons[0].enabled'))
        self.assertEqual(self.value('addonCalls.map(c => c.message.member)'), ['ListAddons','InspectAddonFile','InstallAddon'])
        self.assertEqual(self.h.activeFocusItem(), self.control('addonChooseFile'))
        self.assertFalse(self.dock_js('addonPicker.visible'))

    def test_real_cancel_path_closes_while_data_is_physically_pending(self):
        from PySide6.QtCore import Qt
        self.dock_js('integrations.active=true; integrations.enabledModules=["peripherals"]')
        QTest.qWait(10)
        self.open_widgets()
        self.assertEqual(self.value('addonCalls.map(c => c.message.member)'), ['SnapshotFor'])
        cancel = self.control('addonCancelWait')
        self.assertTrue(cancel.isVisible() and cancel.isEnabled())
        cancel.forceActiveFocus(Qt.TabFocusReason)
        closed = QSignalSpy(self.popup.closed)
        QTest.keyClick(self.h, Qt.Key_Space)
        if not closed.count():
            self.assertTrue(closed.wait(1000))
        self.assertFalse(self.popup.property('visible'))
        self.assertTrue(self.dock_js('integrations.addonCallPending'))
        self.assertEqual(len(self.value('addonCalls')), 1)

    def test_actual_32_row_list_uses_parent_scroll_and_hidden_surface_rejects_requests(self):
        from PySide6.QtCore import QPointF, Qt
        frame = self.metadata(False)
        original = frame['result']['addons'][0]
        rows = []
        for index in range(32):
            row = json.loads(json.dumps(original))
            row['manifest']['id'] = f'org.example.battery{index:02d}'
            rows.append(row)
        self.open_widgets(350, 360)
        self.reply(0, self.metadata(False, 'b'*32, rows))
        last = self.control('addonEnable-org.example.battery31')
        last.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(35)
        viewport = self.control('widgetScroll').property('contentItem')
        top = last.mapToItem(viewport, QPointF(0,0)).y()
        self.assertGreaterEqual(top-2, -0.5)
        self.assertLessEqual(top+last.height()+2, viewport.height()+0.5)
        self.assertGreater(self.control('addonManager').height(), viewport.height()*10)
        self.control('settingsTabs').setProperty('currentIndex', 0)
        QTest.qWait(10)
        # A retained hidden presentation cannot dispatch into recovery/current scope.
        manager = self.control('addonManager')
        e = QQmlExpression(QQmlEngine.contextForObject(manager), manager,
            "enableRequested('org.example.battery31', '" + 'a'*64 + "')")
        e.evaluate()
        self.assertFalse(e.hasError(), e.error().toString())
        self.assertEqual(self.value('addonCalls.map(c => c.message.member)'), ['ListAddons'])


    def test_actual_settings_queued_close_before_list_resumes_only_fresh_reading(self):
        self.dock_js('integrations.active=true; integrations.enabledModules=["peripherals"]; integrations.nowMsOverride=100000')
        QTest.qWait(10)
        self.js('addonCalls[0].resolve({value:' + json.dumps(json.dumps(peripheral_frame())) + '})')
        self.dock_js('integrations.refresh()')
        QTest.qWait(10)
        self.open_widgets()
        observer = """import QtQuick; Connections {
            target: integrations
            function onAddonCallPendingChanged() {
                if (!integrations.addonCallPending && settings.visible)
                    Qt.callLater(function() { settings.close(); });
            }
        }"""
        self.dock_js('Qt.createQmlObject(' + json.dumps(observer) + ', settingsContents)')
        closed = QSignalSpy(self.popup.closed)
        resumed = QSignalSpy(self.h.addonCallsChanged)
        self.js('addonCalls[1].resolve({value:' + json.dumps(json.dumps(peripheral_frame())) + '})')
        if not closed.count():
            self.assertTrue(closed.wait(1000))
        QTest.qWait(10)
        self.assertFalse(self.popup.property('visible'))
        self.assertFalse(self.dock_js('addonsSession.surfaceActive'))
        self.assertFalse(self.dock_js('integrations.addonSuspended'))
        self.assertFalse(self.dock_js('addonsSession.reloadRequired'))
        if len(self.value('addonCalls')) < 3:
            self.assertTrue(resumed.wait(1000))
        self.assertEqual(self.value('addonCalls.map(c=>c.message.member)'), ['SnapshotFor']*3)
        identity = self.dock_js('JSON.stringify(integrations.addonIdentity)')
        self.assertEqual(json.loads(identity), dict(generation='b'*32, sha256='a'*64))
        self.assertEqual(self.dock_js('integrations.peripherals.devices.length'), 0)
        self.js('addonCalls[1].resolve({value:' + json.dumps(json.dumps(peripheral_frame(percent=99))) + '})')
        self.assertEqual(self.dock_js('integrations.peripherals.devices.length'), 0)
        self.js('addonCalls[2].resolve({value:' + json.dumps(json.dumps(peripheral_frame(percent=0))) + '})')
        self.assertEqual(self.dock_js('integrations.peripherals.devices[0].percent'), 0)


    def test_actual_settings_close_during_reservation_resumes_without_list_or_stale_bytes(self):
        self.dock_js('integrations.active=true; integrations.enabledModules=["peripherals"]; integrations.nowMsOverride=100000')
        QTest.qWait(10)
        self.js('addonCalls[0].resolve({value:' + json.dumps(json.dumps(peripheral_frame())) + '})')
        observer = """import QtQuick; Connections {
            target: addonsSession
            property bool closed: false
            function onPhysicalChanged() {
                if (addonsSession.physical !== null && !closed) {
                    closed=true;
                    settings.close();
                }
            }
        }"""
        self.dock_js('Qt.createQmlObject(' + json.dumps(observer) + ', settingsContents)')
        closed = QSignalSpy(self.popup.closed)
        resumed = QSignalSpy(self.h.addonCallsChanged)
        self.dock_js('settings.open()')
        self.control('settingsTabs').setProperty('currentIndex', 1)
        if not closed.count():
            self.assertTrue(closed.wait(1000))
        if len(self.value('addonCalls')) < 2:
            resumed.wait(1000)
        self.assertFalse(self.popup.property('visible'))
        self.assertFalse(self.dock_js('integrations.addonSuspended'))
        self.assertFalse(self.dock_js('addonsSession.reloadRequired'))
        self.assertFalse(self.dock_js('addonsSession.busy'))
        self.assertEqual(self.value('addonCalls.map(c=>c.message.member)'), ['SnapshotFor', 'SnapshotFor'])
        self.assertEqual(json.loads(self.dock_js('JSON.stringify(integrations.addonIdentity)')),
            dict(generation='b'*32, sha256='a'*64))
        self.assertEqual(self.dock_js('integrations.peripherals.devices.length'), 0)
        self.js('addonCalls[0].resolve({value:' + json.dumps(json.dumps(peripheral_frame(percent=99))) + '})')
        self.assertEqual(self.dock_js('integrations.peripherals.devices.length'), 0)
        self.js('addonCalls[1].resolve({value:' + json.dumps(json.dumps(peripheral_frame(percent=0))) + '})')
        self.assertEqual(self.dock_js('integrations.peripherals.devices[0].percent'), 0)


    def assert_complete_parent_action_ring(self, name):
        from PySide6.QtCore import QPointF, Qt
        item = self.control(name)
        item.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(100)
        viewport = self.control('widgetScroll').property('contentItem')
        expression = QQmlExpression(QQmlEngine.contextForObject(item), item,
            "JSON.stringify(background.children.filter(c=>c.border && c.border.width===2).map(c=>({x:c.x,y:c.y,width:c.width,height:c.height,visible:c.visible})))")
        raw, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        rings = json.loads(raw)
        self.assertEqual(len(rings), 1)
        ring = rings[0]
        origin = item.mapToItem(viewport, QPointF(ring['x'], ring['y']))
        scheme = self.dock_js('Style.schemeFor(systemColors.Kirigami.Theme.backgroundColor)')
        expected = os.environ.get('ORLA_COMPOSITION_TEST_SCHEME')
        if expected:
            self.assertEqual(scheme, expected)
        metrics = dict(control=name, scheme=scheme, left=origin.x(), top=origin.y(),
            right=origin.x()+ring['width'], bottom=origin.y()+ring['height'],
            viewportWidth=viewport.width(), viewportHeight=viewport.height(), ring=ring)
        print('COMPOSITION_ACTUAL_RING', json.dumps(metrics))
        self.assertTrue(item.isVisible() and item.isEnabled() and item.hasActiveFocus())
        self.assertTrue(item.property('visualFocus') and ring['visible'])
        self.assertGreaterEqual(metrics['left'], -0.5, metrics)
        self.assertLessEqual(metrics['right'], viewport.width()+0.5, metrics)
        self.assertGreaterEqual(metrics['top'], -0.5, metrics)
        self.assertLessEqual(metrics['bottom'], viewport.height()+0.5, metrics)
        return metrics

    def test_cancel_actual_visible_ring_fits_all_four_parent_bounds(self):
        self.dock_js('integrations.active=true; integrations.enabledModules=["peripherals"]')
        QTest.qWait(10)
        for width, height in ((350, 300), (420, 360)):
            with self.subTest(width=width, height=height):
                self.open_widgets(width, height)
                self.assertEqual(self.value('addonCalls.map(c=>c.message.member)'), ['SnapshotFor'])
                self.assert_complete_parent_action_ring('addonCancelWait')

    def test_reload_actual_visible_ring_fits_all_four_parent_bounds(self):
        self.open_widgets(350, 300)
        self.reply(0, self.metadata(False))
        for width, height in ((350, 300), (420, 360)):
            with self.subTest(width=width, height=height):
                self.popup.setProperty('width', width)
                self.popup.setProperty('heightBudget', height)
                QTest.qWait(30)
                self.assert_complete_parent_action_ring('addonReload')
                self.assertEqual(self.value('addonCalls.map(c=>c.message.member)'), ['ListAddons'])


class AddonSessionInitializationTests(unittest.TestCase):
    setUpClass = classmethod(AddonCompositionTests.setUpClass.__func__)
    js = AddonCompositionTests.js
    value = AddonCompositionTests.value

    @contextmanager
    def constructed(self, container='Item', properties=False, scope='"initial-profile"',
                    running='root.startRunning', production_order=False, surface=False):
        ui = (Path(__file__).resolve().parents[1] / 'package/contents/ui').as_uri()
        fields = ['dataState: data', 'running: '+running, 'owner: owner', 'scopeKey: '+scope,
                  'surfaceActive: root.surfaceWanted', 'transport: fake']
        if production_order:
            fields = [fields[1], fields[0], fields[5], fields[4], fields[2], fields[3]]
        data_prefix = 'property QtObject dataObject:' if properties else ''
        session_prefix = 'property QtObject sessionObject:' if properties else ''
        qml = f"""import QtQuick
import "{ui}" as UI
{container} {{
    id: root
    property bool startRunning: false
    property bool surfaceWanted: {str(surface).lower()}
    property string initialScope: "initial-profile"
    property var calls: []
    property QtObject ownerObject: QtObject {{ id: owner }}
    property QtObject fakeTransport: QtObject {{
        id: fake
        function asyncCall(message, resolve, reject) {{
            root.calls=root.calls.concat([{{message:message, resolve:resolve, reject:reject}}]);
        }}
    }}
    {data_prefix} UI.IntegrationState {{ id: data; active: false; enabledModules: ["peripherals"]; transport: fake }}
    {session_prefix} UI.AddonsSession {{ id: session; {'; '.join(fields)} }}
    property var sessionRef: session
    property var dataRef: data
}}"""
        self.engine = QQmlEngine()
        warnings = []
        self.engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
        component = QQmlComponent(self.engine)
        component.setData(qml.encode(), QUrl('file:///synthetic/AddonSessionConstructor.qml'))
        self.assertFalse(component.isError(), [v.toString() for v in component.errors()])
        self.h = component.create()
        self.assertIsNotNone(self.h, [v.toString() for v in component.errors()])
        try:
            QTest.qWait(30)
            yield
        finally:
            self.h.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            QTest.qWait(10)
            self.engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.app.processEvents()
            self.assertEqual(warnings, [])

    def test_literal_scope_constructors_are_quiet_and_inert_with_final_running_false(self):
        cases = [dict(container='QtObject', properties=True), dict(),
                 dict(production_order=True), dict(running='false'),
                 dict(scope='root.initialScope', production_order=True), dict(scope='""')]
        for case in cases:
            with self.subTest(constructor=case), self.constructed(**case):
                self.assertTrue(self.js('sessionRef.dataState === dataRef'))
                self.assertEqual(self.js('sessionRef.scopeKey'), '' if case.get('scope') == '""' else 'initial-profile')
                self.assertFalse(self.js('sessionRef.running || sessionRef.busy || sessionRef.paused'))
                self.assertEqual(self.value('calls'), [])
                self.assertEqual(self.js('dataRef.peripherals.status'), 'disabled')

    def test_initial_running_true_without_surface_remains_passive(self):
        with self.constructed(running='true'):
            self.assertTrue(self.js('sessionRef.running'))
            self.assertFalse(self.js('sessionRef.manager.active || sessionRef.busy || sessionRef.paused'))
            self.assertEqual(self.value('calls'), [])

    def test_initial_active_surface_running_true_lists_only_final_scope_and_owner(self):
        with self.constructed(running='true', surface=True, production_order=True):
            self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons'])
            self.assertTrue(self.js('sessionRef.manager.owner === ownerObject'))
            self.assertTrue(self.js('sessionRef.manager.scopeKey.startsWith("initial-profile:")'))
            self.assertTrue(self.js('dataRef.addonSuspended && sessionRef.busy'))
            self.assertFalse(self.js('sessionRef.manager.enableAddon("org.example.battery", "' + 'a'*64 + '")'))

    def test_final_false_running_then_start_and_scope_aba_revoke_old_reply(self):
        with self.constructed(running='false', surface=True):
            self.assertEqual(self.value('calls'), [])
            self.js('sessionRef.running=true')
            QTest.qWait(30)
            self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons'])
            self.js('sessionRef.scopeKey="other-profile"; sessionRef.scopeKey="initial-profile"')
            current = dict(formatVersion='0.1-experimental', ok=True,
                result=dict(generation='b'*32, addons=[]))
            self.js('calls[0].resolve({values:[{}], value:{value:' + json.dumps(json.dumps(current)) + '}})')
            QTest.qWait(30)
            self.assertTrue(self.js('dataRef.addonSuspended'))
            self.assertFalse(self.js('sessionRef.manager.valid'))
            self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons', 'ListAddons'])
            self.js('calls[1].resolve({values:[{}], value:{value:' + json.dumps(json.dumps(current)) + '}})')
            QTest.qWait(30)
            self.assertTrue(self.js('sessionRef.manager.valid'))
            self.js('surfaceWanted=false')
            QTest.qWait(30)
            self.assertFalse(self.js('dataRef.addonSuspended || sessionRef.busy'))
            self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons', 'ListAddons'])


class AddonSessionLifetimeTests(unittest.TestCase):
    """Retire one coordinator; keep its engine, data, transport and caller alive."""
    setUpClass = classmethod(AddonCompositionTests.setUpClass.__func__)
    js = AddonCompositionTests.js
    value = AddonCompositionTests.value
    metadata = AddonCompositionTests.metadata

    @contextmanager
    def retained_caller(self, loader=True):
        ui = (Path(__file__).resolve().parents[1] / 'package/contents/ui').as_uri()
        qml = '''import QtQuick
import "UI_PATH" as UI
Window {
    id: root
    width: 350; height: 360; visible: true
    property bool held: true
    property bool wanted: true
    property string scope: "profile-a"
    property bool useLoader: USE_LOADER
    property var standaloneSession: null
    property var reservation: null
    property var session: useLoader ? holder.item : standaloneSession
    property var dataRef: dataState
    property var view: managerView
    property var calls: []
    QtObject { id: lifetimeOwner }
    QtObject {
        id: fake
        function asyncCall(message, resolve, reject) {
            root.calls=root.calls.concat([{message:message, resolve:resolve, reject:reject}]);
        }
    }
    UI.IntegrationState {
        id: dataState
        active: false
        enabledModules: ["peripherals"]
        nowMsOverride: 100000
        transport: fake
    }
    Loader {
        id: holder
        active: root.useLoader && root.held
        sourceComponent: sessionFactory
    }
    Component {
        id: sessionFactory
        UI.AddonsSession {
            dataState: root.dataRef
            transport: fake
            owner: lifetimeOwner
            scopeKey: root.scope
            surfaceActive: root.wanted
        }
    }
    UI.AddonManager {
        id: managerView
        width: parent.width
        addons: root.session ? root.session.manager.addons : []
        busy: root.session ? root.session.busy : false
        loading: root.session ? root.session.manager.loading : false
        onEnableRequested: (id, sha) => { if (root.session) root.session.manager.enableAddon(id, sha); }
    }
    Component.onCompleted: if (!useLoader) standaloneSession=sessionFactory.createObject(root)
    TextInput { id: newerFocus; objectName: "newerFocus"; y: 320; width: 100; height: 30 }
}'''.replace('UI_PATH', ui).replace('USE_LOADER', str(loader).lower())
        self.engine = QQmlEngine()
        warnings = []
        self.engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
        component = QQmlComponent(self.engine)
        component.setData(qml.encode(), QUrl('file:///synthetic/AddonSessionLifetime.qml'))
        self.assertFalse(component.isError(), [v.toString() for v in component.errors()])
        self.h = component.create()
        self.assertIsNotNone(self.h, [v.toString() for v in component.errors()])
        try:
            QTest.qWait(30)
            self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons'])
            yield
        finally:
            self.h.close()
            self.h.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            QTest.qWait(20)
            self.engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            self.app.processEvents()
            self.assertEqual(warnings, [])

    def late_result(self, index, frame=None, failed=False):
        call = 'calls[' + str(index) + ']'
        statement = call + '.reject({})' if failed else call + '.resolve({values:[{}], value:{value:' + json.dumps(json.dumps(frame)) + '}})'
        self.js('Qt.callLater(function() { ' + statement + '; })')
        QTest.qWait(30)

    def test_loader_retirement_pending_list_success_reject_and_duplicates_are_inert(self):
        from shiboken6 import isValid
        for failed in (False, True):
            with self.subTest(firstReject=failed), self.retained_caller():
                old = self.js('session')
                self.js('held=false')
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                QTest.qWait(20)
                self.assertFalse(isValid(old))
                self.assertTrue(isValid(self.h) and isValid(self.engine))
                self.assertTrue(self.js('dataRef !== null'))
                self.assertIsNone(self.js('session'))
                self.late_result(0, self.metadata(True, 'c'*32), failed)
                self.late_result(0, self.metadata(True, 'd'*32), not failed)
                self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons'])
                self.assertIsNone(self.value('dataRef.addonIdentity'))

    def test_synchronous_retirement_during_identity_publication_keeps_retained_caller_quiet(self):
        for target, signal in (('session', 'Identity'), ('dataRef', 'AddonIdentity')):
            with self.subTest(publication=signal), self.retained_caller():
                observer = '''import QtQuick; Connections {
                    target: root.TARGET
                    function onSIGNALChanged() { root.held=false; }
                }'''.replace('TARGET', target).replace('SIGNAL', signal)
                self.js('Qt.createQmlObject(' + json.dumps(observer) + ', root)')
                self.late_result(0, self.metadata(False, 'c'*32))
                self.assertIsNone(self.js('session'))
                self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons'])
                # Retirement on session identity must stop before publishing into data.
                self.assertEqual(self.value('dataRef.addonIdentity'),
                    None if target == 'session' else dict(generation='c'*32, sha256=None))

    def test_forced_destroy_pending_list_and_mutation_preserves_retained_data(self):
        from shiboken6 import isValid
        for mutation in (False, True):
            for failed in (False, True):
                with self.subTest(mutation=mutation, firstReject=failed), self.retained_caller(loader=False):
                    index = 0
                    if mutation:
                        self.late_result(0, self.metadata(False))
                        self.js('view.enableRequested("org.example.battery", "' + 'a'*64 + '")')
                        index = 1
                        self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons', 'EnableAddon'])
                    old = self.js('session')
                    old.deleteLater()
                    QCoreApplication.sendPostedEvents(old, QEvent.DeferredDelete)
                    QTest.qWait(20)
                    self.assertFalse(isValid(old))
                    self.assertTrue(isValid(self.engine) and isValid(self.h))
                    self.assertIsNone(self.js('session'))
                    self.late_result(index, self.metadata(True, 'c'*32), failed)
                    self.late_result(index, self.metadata(False, 'd'*32), not failed)
                    self.assertEqual(self.js('calls.length'), index + 1)
                    self.assertEqual(self.value('dataRef.addonIdentity'),
                        dict(generation='b'*32, sha256=None) if mutation else None)

    def test_retirement_during_reservation_or_settlement_publication_stops_old_continuation(self):
        cases = [('Physical', 'session.physical !== null', False),
                 ('NeedsMetadata', 'session.needsMetadata', False),
                 ('Physical', 'session.physical === null', True)]
        for signal, condition, dispatched in cases:
            with self.subTest(signal=signal, dispatched=dispatched), self.retained_caller():
                if not dispatched:
                    # Arm the observer on a live idle instance, before the next List.
                    self.late_result(0, self.metadata(False))
                observer = '''import QtQuick; Connections {
                    target: root.session
                    function onSIGNALChanged() { if (root.session && CONDITION) root.held=false; }
                }'''.replace('SIGNAL', signal).replace('CONDITION', condition)
                self.js('Qt.createQmlObject(' + json.dumps(observer) + ', root)')
                if dispatched:
                    self.late_result(0, self.metadata(False, 'c'*32))
                else:
                    self.js('session.reload()')
                    QTest.qWait(30)
                self.assertIsNone(self.js('session'))
                self.assertEqual(self.js('calls.length'), 1)

    def test_immediate_replacement_with_old_list_or_mutation_callbacks_preserves_current_work_and_focus(self):
        from shiboken6 import isValid
        for mutation in (False, True):
            for failed in (False, True):
                with self.subTest(oldMutation=mutation, firstReject=failed), self.retained_caller():
                    old_index = 0
                    if mutation:
                        self.late_result(0, self.metadata(False))
                        self.js('view.enableRequested("org.example.battery", "' + 'a'*64 + '")')
                        old_index = 1
                    old = self.js('session')
                    self.js('held=false; scope="profile-b"; held=true; newerFocus.forceActiveFocus(Qt.TabFocusReason)')
                    QTest.qWait(30)
                    self.assertFalse(isValid(old))
                    current_index = old_index + 1
                    self.assertTrue(self.js('session.manager.scopeKey.startsWith("profile-b:")'))
                    self.assertEqual(self.js('calls.length'), current_index + 1)
                    before = self.value('dataRef.addonIdentity')
                    self.js('reservation=session.physical')
                    self.late_result(old_index, self.metadata(True, 'e'*32), failed)
                    self.assertEqual(self.value('dataRef.addonIdentity'), before)
                    self.assertTrue(self.js('reservation !== null && session.physical === reservation'))
                    self.assertTrue(self.js('session.busy && !session.manager.valid'))
                    self.late_result(current_index, self.metadata(False, 'c'*32))
                    self.assertTrue(self.js('session.manager.valid && !session.busy'))
                    self.assertEqual(self.js('view.addons.length'), 1)
                    self.assertEqual(self.value('dataRef.addonIdentity'), dict(generation='c'*32, sha256=None))
                    self.js('view.enableRequested("org.example.battery", "' + 'a'*64 + '")')
                    self.assertEqual(self.value('calls[calls.length-1].message.member'), 'EnableAddon')
                    self.js('reservation=session.physical')
                    self.late_result(old_index, self.metadata(False, 'f'*32), not failed)
                    self.assertTrue(self.js('reservation !== null && session.physical === reservation'))
                    self.assertTrue(self.js('session.busy && !session.manager.valid'))
                    self.late_result(current_index + 1, self.metadata(True, 'd'*32))
                    self.assertTrue(self.js('session.manager.valid && !session.busy'))
                    self.assertTrue(self.js('view.addons[0].enabled'))
                    self.assertEqual(self.value('dataRef.addonIdentity'), dict(generation='d'*32, sha256='a'*64))
                    self.assertTrue(self.js('root.activeFocusItem === newerFocus'))
                    self.assertEqual(self.value('calls.map(c=>c.message.member)'),
                        (['ListAddons', 'EnableAddon'] if mutation else ['ListAddons']) + ['ListAddons', 'EnableAddon'])
                    self.js('wanted=false; dataRef.active=true')
                    QTest.qWait(30)
                    self.assertFalse(self.js('dataRef.addonSuspended'))
                    frame = peripheral_frame(percent=0)
                    frame['peripherals']['addon']['generation'] = 'd'*32
                    self.js('calls[calls.length-1].resolve({value:' + json.dumps(json.dumps(frame)) + '})')
                    QTest.qWait(20)
                    self.assertEqual(self.js('dataRef.peripherals.devices[0].percent'), 0)

    def test_replacement_inside_identity_publication_cannot_publish_old_identity_or_reclaim_new_focus(self):
        with self.retained_caller():
            observer = '''import QtQuick; Connections {
                target: root.session
                property bool replaced: false
                function onIdentityChanged() {
                    if (replaced) return;
                    replaced=true;
                    root.held=false; root.scope="profile-b"; root.held=true;
                    newerFocus.forceActiveFocus(Qt.TabFocusReason);
                }
            }'''
            self.js('Qt.createQmlObject(' + json.dumps(observer) + ', root)')
            self.late_result(0, self.metadata(True, 'e'*32))
            self.assertEqual(self.value('calls.map(c=>c.message.member)'), ['ListAddons', 'ListAddons'])
            self.assertIsNone(self.value('dataRef.addonIdentity'))
            self.late_result(0, self.metadata(True, 'f'*32))
            self.assertTrue(self.js('session.busy && !session.manager.valid'))
            self.late_result(1, self.metadata(False, 'c'*32))
            self.assertTrue(self.js('session.manager.valid && !session.busy'))
            self.assertEqual(self.value('dataRef.addonIdentity'), dict(generation='c'*32, sha256=None))
            self.assertTrue(self.js('root.activeFocusItem === newerFocus'))
            self.js('view.enableRequested("org.example.battery", "' + 'a'*64 + '")')
            self.late_result(2, self.metadata(True, 'd'*32))
            self.assertTrue(self.js('view.addons[0].enabled && !session.busy'))
            self.assertEqual(self.value('dataRef.addonIdentity'), dict(generation='d'*32, sha256='a'*64))
