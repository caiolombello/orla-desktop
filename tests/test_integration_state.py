"""Selection lifecycle with deferred transport; no KDE modules or session bus."""
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent, QLibraryInfo
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine, QQmlExpression


class IntegrationStateCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('IntegrationStateHarness.qml').resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.root = self.engine.rootObjects()[0]
        self.state = self.root.findChild(QObject, 'state')
        self.transport = self.root.findChild(QObject, 'transport')

    def tearDown(self):
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.state, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.app.processEvents()
        return value

    def select(self, modules, active=True):
        self.evaluate(f'enabledModules={json.dumps(modules)}; active={str(active).lower()}')

    def calls(self):
        return json.loads(self.evaluate('JSON.stringify(messages)', self.transport))

    def reply(self, modules, failed=False, **changes):
        values = {'quota': {'status': 'ready', 'windows': [{'provider': 'fixture', 'usedPercent': 42}]},
                  'peripherals': {'status': 'ready', 'devices': [{'name': 'Fixture', 'percent': 70}]},
                  'recording': {'status': 'ready', 'state': 'stopped'}}
        if modules == ['peripherals'] and not changes:
            from test_addon_peripherals import peripheral_frame
            frame = peripheral_frame()
        else:
            frame = {'schemaVersion': 2, 'modules': modules, **{m: values[m] for m in modules}, **changes}
        self.evaluate(f'reply({json.dumps(json.dumps(frame))}, {str(failed).lower()})', self.transport)


class IntegrationStateTests(IntegrationStateCase):
    def test_off_and_empty_start_no_service_and_singleton_is_selective(self):
        self.assertEqual(self.calls(), [])
        self.select([], True)
        self.assertEqual(self.calls(), [])
        self.select(['quota'])
        self.assertEqual([(m['member'], m['signature'], m['arguments']) for m in self.calls()],
                         [('SnapshotFor', '(as)', [['quota']])])
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows[0].usedPercent'), 42)
        self.assertEqual(self.evaluate('peripherals.status'), 'disabled')
        self.assertEqual(self.evaluate('recording.state'), 'unknown')
        self.assertFalse(self.state.property('loading'))
        self.select([])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(len(self.calls()), 1)

    def test_revoked_success_clears_immediately_and_latest_selection_waits(self):
        self.select(['quota'])
        self.reply(['quota'])
        self.evaluate('refresh()')
        self.select(['recording'])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(len(self.calls()), 2)
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(len(self.calls()), 3)
        self.assertEqual(self.calls()[-1]['arguments'], [['recording']])
        self.reply(['recording'])
        self.assertEqual(self.evaluate('recording.state'), 'stopped')
        self.assertEqual(self.evaluate('quota.status'), 'disabled')

    def test_aba_and_old_failure_require_a_fresh_request(self):
        self.select(['quota'])
        self.select(['recording'])
        self.select(['quota'])
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(len(self.calls()), 2)
        self.select(['recording'])
        self.reply(['quota'], failed=True)
        self.assertEqual(self.state.property('error'), '')
        self.assertEqual(self.calls()[-1]['arguments'], [['recording']])
        self.reply(['recording'])
        self.assertEqual(self.evaluate('recording.state'), 'stopped')

    def test_disable_all_and_off_on_revoke_old_callbacks(self):
        self.select(['quota'])
        self.select(['quota'], False)
        self.assertFalse(self.state.property('loading'))
        self.reply(['quota'], failed=True)
        self.assertEqual(self.state.property('error'), '')
        self.assertEqual(len(self.calls()), 1)
        self.select(['quota'])
        self.select(['quota'], False)
        self.select(['quota'])
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(len(self.calls()), 3)
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows.length'), 1)

    def test_old_bridge_or_wrong_scope_fail_without_legacy_fallback(self):
        self.select(['quota'])
        self.reply(['quota'], schemaVersion=1)
        self.assertTrue(self.state.property('error'))
        self.assertEqual(len(self.calls()), 1)
        self.evaluate('refresh()')
        self.reply(['peripherals'])
        self.assertTrue(self.state.property('error'))
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.evaluate('refresh()')
        self.reply(['quota'], failed=True)
        self.assertIn('ponte local', self.state.property('error'))
        self.assertTrue(all(m['member'] == 'SnapshotFor' for m in self.calls()))

    def test_reentrant_loading_revokes_before_dispatch_and_commit_cannot_restore_old_data(self):
        self.root.setProperty('revokeOnLoading', True)
        self.select(['quota'])
        self.assertEqual(self.calls(), [])
        self.root.setProperty('revokeOnLoading', False)
        self.root.setProperty('changeOnCommit', True)
        self.select(['quota'])
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(self.calls()[-1]['arguments'], [['peripherals']])
        self.reply(['peripherals'])
        self.assertEqual(self.evaluate('peripherals.devices.length'), 1)

    def test_duplicate_reentrant_callback_cannot_release_a_new_request(self):
        self.select(['quota'])
        self.root.setProperty('replayOnCommit', True)
        self.root.setProperty('refreshAfterLoad', True)
        self.reply(['quota'])
        self.assertEqual(self.root.property('readyCommits'), 1)
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(self.state.property('loading'))
        self.reply(['quota'])
        self.assertEqual(self.root.property('readyCommits'), 2)
        self.assertFalse(self.state.property('loading'))

    def test_synchronous_reply_and_transport_exception_settle_once(self):
        self.transport.setProperty('immediateReply', True)
        self.select(['quota'])
        self.assertFalse(self.state.property('loading'))
        self.assertEqual(self.evaluate('quota.status'), 'ready')
        self.select([], False)
        self.transport.setProperty('immediateReply', False)
        self.transport.setProperty('throwOnCall', True)
        self.select(['quota'])
        self.assertFalse(self.state.property('loading'))
        self.assertTrue(self.state.property('error'))
        self.assertEqual(len(self.calls()), 2)

    def test_error_observer_can_change_scope_without_publishing_old_failure(self):
        self.select(['quota'])
        self.root.setProperty('changeOnError', True)
        self.reply(['quota'], failed=True)
        self.assertEqual(self.state.property('error'), '')
        self.assertEqual(self.evaluate('quota.status'), 'disabled')
        self.assertEqual(self.calls()[-1]['arguments'], [['recording']])
        self.reply(['recording'])
        self.assertEqual(self.evaluate('recording.state'), 'stopped')

    def test_addon_and_legacy_dispatch_independently(self):
        self.select(['quota', 'peripherals'])
        self.assertEqual({m['service'] for m in self.calls()},
                         {'org.caiodock.Integrations', 'org.orla.Addons'})
        addon = next(m for m in self.calls() if m['service'] == 'org.orla.Addons')
        self.assertEqual((addon['path'], addon['iface'], addon['member'], addon['signature'], addon['arguments']),
            ('/org/orla/Addons', 'org.orla.Addons1', 'SnapshotFor', '(as)', [['peripherals']]))

    def destroy_state(self):
        self.state.deleteLater()
        QCoreApplication.sendPostedEvents(self.state, QEvent.DeferredDelete)
        self.app.processEvents()

    def test_destroyed_owner_legacy_callbacks(self):
        self.select(['quota'])
        frame = dict(schemaVersion=2, modules=['quota'], quota=dict(status='ready',windows=[]))
        self.destroy_state()
        self.evaluate('let call=queue[0]; queue=[]; call.resolve({value:'+json.dumps(json.dumps(frame))+'}); call.reject(); call.resolve({value:"{}"})',self.transport)

    def test_destroyed_owner_addon_callbacks(self):
        self.select(['peripherals'])
        from test_addon_peripherals import peripheral_frame
        frame=peripheral_frame()
        self.destroy_state()
        self.evaluate('let call=queue[0]; queue=[]; call.resolve({value:'+json.dumps(json.dumps(frame))+'}); call.reject(); call.resolve({value:"{}"})',self.transport)

    def test_destroyed_owner_queued_refresh(self):
        expression=QQmlExpression(self.engine.rootContext(),self.state,'enabledModules=["quota","peripherals"]; active=true')
        expression.evaluate()
        self.assertFalse(expression.hasError(),expression.error().toString())
        self.destroy_state()
        self.assertEqual(self.evaluate('messages.length',self.transport),0)


class NativeDataTransportTests(unittest.TestCase):
    """Production wrapper, engine-private QML bus fake; never native D-Bus."""

    def setUp(self):
        private = tempfile.TemporaryDirectory()
        self.addCleanup(private.cleanup)
        directory = Path(private.name)
        env = {'HOME': str(directory), 'TMPDIR': str(directory),
               'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
               'QT_QPA_PLATFORMTHEME': '', 'QT_ACCESSIBILITY': '0',
               'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + str(directory / 'absent-session'),
               'DBUS_SYSTEM_BUS_ADDRESS': 'unix:path=' + str(directory / 'absent-system')}
        for kind in ('CONFIG_HOME', 'DATA_HOME', 'STATE_HOME', 'CACHE_HOME', 'RUNTIME_DIR'):
            path = directory / kind.lower()
            path.mkdir(mode=0o700)
            env['XDG_' + kind] = str(path)
        self.enterContext(mock.patch.dict(os.environ, env))
        for name in ('DISPLAY', 'WAYLAND_DISPLAY', 'AT_SPI_BUS_ADDRESS', 'SESSION_MANAGER'):
            os.environ.pop(name, None)
        for name in ('socket', 'create_connection', 'getaddrinfo'):
            self.enterContext(mock.patch.object(socket, name, side_effect=AssertionError('socket forbidden')))
        from PySide6 import QtDBus
        for name in ('sessionBus', 'systemBus', 'connectToBus', 'connectToPeer'):
            self.enterContext(mock.patch.object(QtDBus.QDBusConnection, name,
                                               side_effect=AssertionError('native QtDBus forbidden')))
        self.assert_no_native_bus_plugin()
        self.app = QGuiApplication.instance() or QGuiApplication([])
        imports = directory / 'imports'
        module = imports / 'org/kde/plasma/workspace/dbus'
        module.mkdir(parents=True)
        qt_imports = Path(QLibraryInfo.path(QLibraryInfo.QmlImportsPath))
        for name in ('QtQml', 'QtQuick'):
            (imports / name).symlink_to(qt_imports / name, target_is_directory=True)
        (module / 'qmldir').write_text('module org.kde.plasma.workspace.dbus\nsingleton SessionBus 1.0 SessionBus.qml\n')
        (module / 'SessionBus.qml').write_text('''pragma Singleton
import QtQml
QtObject {
    readonly property string ownedFake: "orla-data-transport-test-only"
    readonly property url moduleFile: Qt.resolvedUrl("SessionBus.qml")
    property var calls: []
    function asyncCall(message, resolve, reject) {
        calls = calls.concat([{message: message, resolve: resolve, reject: reject}]);
    }
    function stringReply(text) {
        const stringValue = {value: text};
        return {values: [stringValue], value: stringValue};
    }
    function complete(index, reply, failed) {
        if (failed) calls[index].reject(reply);
        else calls[index].resolve(reply);
    }
}
''')
        self.engine = QQmlEngine()
        self.addCleanup(self.close_engine)
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        # Expose only Qt and our fake, never a search root containing native KDE.
        self.engine.setImportPathList([str(imports)])
        self.assertEqual(self.engine.importPathList(), [str(imports)])
        # Resolve and prove ownership before loading any production KDE import.
        self.probe = QQmlComponent(self.engine)
        self.probe.setData(b'import QtQml\nimport org.kde.plasma.workspace.dbus as DBus\n'
                           b'QtObject { property QtObject bus: DBus.SessionBus }',
                           QUrl.fromLocalFile(str(directory / 'Probe.qml')))
        self.root = self.probe.create()
        self.assertIsNotNone(self.root, [e.toString() for e in self.probe.errors()])
        self.bus = self.root.property('bus')
        self.assertEqual(self.bus.property('ownedFake'), 'orla-data-transport-test-only')
        self.assertEqual(self.bus.property('moduleFile').toLocalFile(), str(module / 'SessionBus.qml'))
        ui = Path(__file__).resolve().parents[1] / 'package/contents/ui'
        self.component = QQmlComponent(self.engine)
        self.component.setData(('import QtQuick\nimport ' + json.dumps(ui.as_uri()) + ' as Candidate\n'
            'import org.kde.plasma.workspace.dbus as DBus\n'
            'Candidate.Integrations { nowMsOverride: 100000; property var forwarded: null; '
            'property var errorToken: ({error:{isValid:true,message:"synthetic"}}) }').encode(),
            QUrl.fromLocalFile(str(directory / 'Production.qml')))
        self.state = self.component.create()
        self.assertIsNotNone(self.state, [e.toString() for e in self.component.errors()])
        self.assert_no_native_bus_plugin()

    def assert_no_native_bus_plugin(self):
        self.assertFalse('libdbusplugin.so' in Path('/proc/self/maps').read_text(),
                         'native KDE D-Bus plugin loaded')

    def close_engine(self):
        for name in ('state', 'root'):
            obj = getattr(self, name, None)
            if obj is not None:
                obj.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])
        self.assert_no_native_bus_plugin()

    def evaluate(self, source, target=None):
        target = target or self.state
        expression = QQmlExpression(QQmlEngine.contextForObject(target), target, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.app.processEvents()
        return value.toVariant() if hasattr(value, 'toVariant') else value

    def test_production_adapter_forwards_exact_single_string_and_errors(self):
        raw = ' \n{"escaped":"\\u00e9", "literal":"Maré 😀", "zero":0.00, "duplicate":1,"duplicate":2}\t'
        self.evaluate('transport.asyncCall({service:"fixture",path:"/fixture",iface:"fixture",'
            'member:"SnapshotFor",signature:"(as)",arguments:[["peripherals"]]},'
            'reply=>{forwarded={type:typeof reply.value,text:reply.value,keys:Object.keys(reply)};},'
            'reply=>{forwarded=reply;})')
        self.assertEqual(self.evaluate('calls.length', self.bus), 1)
        self.assertIsNone(self.evaluate('forwarded'))
        self.assertEqual(self.evaluate('DBus.SessionBus.complete(0,DBus.SessionBus.stringReply('
                                       + json.dumps(raw) + '),false); forwarded.type'), 'string')
        self.assertEqual(self.evaluate('forwarded.text').encode('utf-8'), raw.encode('utf-8'))
        self.assertEqual(self.evaluate('forwarded.keys'), ['value'])
        self.assertTrue(self.evaluate('DBus.SessionBus.complete(0,errorToken,true); forwarded===errorToken'))

    def test_native_shaped_data_reaches_both_existing_consumers(self):
        from test_addon_peripherals import peripheral_frame
        self.evaluate('enabledModules=["quota","peripherals","recording"]; active=true')
        messages = self.evaluate('calls.map(call=>call.message)', self.bus)
        self.assertEqual(len(messages), 2)
        for index, message in enumerate(messages):
            addon = message['service'] == 'org.orla.Addons'
            self.assertEqual(message, {
                'service': 'org.orla.Addons' if addon else 'org.caiodock.Integrations',
                'path': '/org/orla/Addons' if addon else '/org/caiodock/Integrations',
                'iface': 'org.orla.Addons1' if addon else 'org.caiodock.Integrations1',
                'member': 'SnapshotFor', 'signature': '(as)',
                'arguments': [['peripherals']] if addon else [['quota', 'recording']]})
            frame = peripheral_frame(percent=0) if addon else {
                'schemaVersion': 2, 'modules': ['quota', 'recording'],
                'quota': {'status': 'ready', 'windows': [{'provider': 'fixture', 'usedPercent': 0}]},
                'recording': {'status': 'ready', 'state': 'stopped'}}
            self.evaluate('complete(' + str(index) + ',stringReply(' + json.dumps(json.dumps(frame)) + '),false)', self.bus)
        self.assertEqual(self.state.property('addonErrorCode'), '')
        self.assertEqual(self.state.property('legacyError'), '')
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)
        self.assertEqual(self.evaluate('quota.windows[0].usedPercent'), 0)
        self.assertEqual(self.evaluate('recording.state'), 'stopped')
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertFalse(self.state.property('loading'))

    def latest_reply(self, frame, failed=False):
        self.evaluate('complete(calls.length-1,stringReply(' + json.dumps(json.dumps(frame))
                      + '),' + str(failed).lower() + ')', self.bus)

    def test_native_shapes_and_invalid_json_fail_closed_without_rewriting(self):
        from test_addon_peripherals import peripheral_frame
        self.evaluate('enabledModules=["peripherals"]; active=true')
        raw = json.dumps(peripheral_frame())
        text = json.dumps(raw)
        malformed = ['null', '({})', '({values:[],value:{value:' + text + '}})',
            '({values:[{},{}],value:{value:' + text + '}})',
            '({values:"x",value:{value:' + text + '}})',
            '({values:[{}],value:' + text + '})', '({values:[{}],value:{value:12}})',
            '({values:[{}],value:{value:false}})', '({values:[{}],value:[' + text + ']})',
            '({values:[{}],value:{value:{}}})', 'stringReply(' + json.dumps(raw.replace(
                '"schemaVersion": 2', '"schemaVersion": 2,"schemaVersion": 2')) + ')']
        for reply in malformed:
            with self.subTest(reply=reply[:90]):
                self.latest_reply(peripheral_frame(percent=0))
                self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)
                self.evaluate('refresh()')
                self.evaluate('complete(calls.length-1,' + reply + ',false)', self.bus)
                self.assertEqual(self.state.property('addonErrorCode'), 'invalid_response')
                self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
                self.assertFalse(self.state.property('addonCallPending'))
                self.assertFalse(self.state.property('loading'))
                self.evaluate('refresh()')

    def test_native_peripheral_readings_keep_stale_zero_coarse_and_unavailable(self):
        from test_addon_peripherals import missing_frame, peripheral_frame
        self.evaluate('enabledModules=["peripherals"]; active=true')
        for changes, percent, level, stale in [
                ({'percent': 0, 'estimated': True, 'charging': 'charging'}, 0, None, False),
                ({'percent': None, 'level': 'low'}, None, 'low', False),
                ({'stale': True}, None, None, True),
                ({'observed': None}, None, None, True)]:
            with self.subTest(changes=changes):
                self.latest_reply(peripheral_frame(**changes))
                self.assertEqual(self.state.property('addonErrorCode'), '')
                self.assertEqual(self.evaluate('peripherals.devices[0].percent'), percent)
                self.assertEqual(self.evaluate('peripherals.devices[0].level'), level)
                self.assertEqual(self.evaluate('peripherals.devices[0].stale'), stale)
                if percent == 0:
                    self.assertTrue(self.evaluate('peripherals.devices[0].estimated'))
                    self.assertEqual(self.evaluate('peripherals.devices[0].charging'), 'charging')
                self.evaluate('refresh()')
        self.latest_reply(peripheral_frame())
        self.evaluate('nowMsOverride=130000')
        self.assertEqual(self.evaluate('peripherals.status'), 'stale')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.evaluate('refresh()')
        self.latest_reply({}, failed=True)
        self.assertEqual(self.state.property('addonErrorCode'), 'unavailable')
        self.assertFalse(self.state.property('addonCallPending'))
        self.evaluate('invalidateAddons()')
        self.latest_reply(missing_frame())
        self.assertEqual(self.state.property('addonErrorCode'), '')
        self.assertEqual(self.evaluate('peripherals.status'), 'missing')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_native_legacy_stale_and_unavailable_do_not_block_addon(self):
        from test_addon_peripherals import peripheral_frame
        self.evaluate('enabledModules=["quota","recording"]; active=true')
        frame = {'schemaVersion': 2, 'modules': ['quota', 'recording'],
                 'quota': {'status': 'stale', 'windows': []},
                 'recording': {'status': 'unknown', 'state': 'unknown'}}
        self.latest_reply(frame)
        self.assertEqual(self.state.property('legacyError'), '')
        self.assertEqual(self.evaluate('quota.status'), 'stale')
        self.assertEqual(self.evaluate('recording.state'), 'unknown')
        self.evaluate('refresh()')
        self.latest_reply({}, failed=True)
        self.assertTrue(self.state.property('legacyError'))
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.evaluate('enabledModules=["quota","peripherals","recording"]')
        index = self.evaluate('calls.findIndex(call=>call.message.service==="org.orla.Addons")', self.bus)
        self.assertGreaterEqual(index, 0)
        self.evaluate('complete(' + str(index) + ',stringReply('
                      + json.dumps(json.dumps(peripheral_frame(percent=0))) + '),false)', self.bus)
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)
        self.assertEqual(self.evaluate('errorFor("peripherals")'), '')

    def test_native_stale_and_duplicate_callbacks_cannot_publish_or_release_new_call(self):
        from test_addon_peripherals import peripheral_frame
        self.evaluate('enabledModules=["peripherals"]; active=true')
        self.assertTrue(self.state.property('addonCallPending'))
        self.evaluate('active=false; active=true')
        self.assertEqual(self.evaluate('calls.length', self.bus), 2)
        old = json.dumps(json.dumps(peripheral_frame(percent=70)))
        self.evaluate('complete(0,stringReply(' + old + '),false); complete(0,{},true)', self.bus)
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.assertTrue(self.state.property('addonCallPending'))
        self.assertTrue(self.state.property('loading'))
        self.latest_reply(peripheral_frame(percent=0))
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)
        self.assertFalse(self.state.property('addonCallPending'))
        self.evaluate('complete(0,stringReply(' + old + '),false); complete(1,{},true)', self.bus)
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)
        self.assertEqual(self.state.property('addonErrorCode'), '')

    def test_production_wrapper_late_callbacks_after_owner_destruction(self):
        from test_addon_peripherals import peripheral_frame
        self.evaluate('enabledModules=["quota","peripherals"]; active=true')
        self.assertEqual(self.evaluate('calls.length', self.bus), 2)
        self.state.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.state = None
        raw = json.dumps(json.dumps(peripheral_frame()))
        self.evaluate('for (let index=0; index<calls.length; index++) {'
                      'complete(index,stringReply(' + raw + '),false);'
                      'complete(index,{},true); complete(index,{},false); }', self.bus)
        self.assertEqual(self.evaluate('calls.length', self.bus), 2)
