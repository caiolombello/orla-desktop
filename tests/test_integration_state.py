"""Selection lifecycle with deferred transport; no KDE modules or session bus."""
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression


class IntegrationStateTests(unittest.TestCase):
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
        frame = {'schemaVersion': 2, 'modules': modules, **{m: values[m] for m in modules}, **changes}
        self.evaluate(f'reply({json.dumps(json.dumps(frame))}, {str(failed).lower()})', self.transport)

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
        self.select(['peripherals'])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(len(self.calls()), 2)
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertEqual(len(self.calls()), 3)
        self.assertEqual(self.calls()[-1]['arguments'], [['peripherals']])
        self.reply(['peripherals'])
        self.assertEqual(self.evaluate('peripherals.devices.length'), 1)
        self.assertEqual(self.evaluate('quota.status'), 'disabled')

    def test_aba_and_old_failure_require_a_fresh_request(self):
        self.select(['quota'])
        self.select(['peripherals'])
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
