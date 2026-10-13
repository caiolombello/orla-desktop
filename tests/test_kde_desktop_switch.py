import gc, json, unittest
from pathlib import Path
from test_desktop_switch import QGuiApplication, QQmlApplicationEngine, QQmlExpression, QUrl, QObject, QEvent

class KdeDesktopSwitchTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda v: self.warnings.extend((x.toString() for x in v)))
        fixture = 'DesktopSwitchExistingStateHarness.qml' if self._testMethodName.startswith('test_existing_') else 'KdeDesktopSwitchHarness.qml'
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name(fixture).resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.root = self.engine.rootObjects()[0]
        self.adapter = self.root.findChild(QObject, 'backend' if self._testMethodName.startswith('test_existing_') else 'adapter')
        self.transport = self.root.findChild(QObject, 'transport')

    def tearDown(self):
        self.root = None
        self.adapter = None
        self.transport = None
        self.engine.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.engine = None
        gc.collect()
        self.assertEqual(self.warnings, [])

    def evaluate(self, code, target=None):
        e = QQmlExpression(self.engine.rootContext(), target or self.root, code)
        v, _ = e.evaluate()
        self.assertFalse(e.hasError(), e.error().toString())
        return v

    def reply(self, value):
        self.evaluate('reply(' + json.dumps(value) + ')', self.transport)

    def messages(self):
        collection = 'messages' if self.transport else 'transport.messages'
        return json.loads(self.evaluate('JSON.stringify(' + collection + '.map(m=>({service:m.service,member:m.member,signature:m.signature})))', self.transport))

    def ready(self):
        self.reply(':1.40')
        self.reply('one')
        self.reply(':1.40')
        self.assertTrue(self.adapter.property('available'))

    def test_official_string_wrappers_enable_probe(self):
        self.reply({'value': ':1.40'})
        self.reply({'value': 'one'})
        self.reply({'value': ':1.40'})
        self.assertTrue(self.adapter.property('available'))

    def test_reentrant_hide_in_final_validator_never_sets(self):
        self.ready()
        self.root.setProperty('hideOnFinalDispatch', True)
        self.evaluate('request()')
        self.reply(':1.40')
        self.reply('one')
        self.assertFalse(any((m['member'] == 'Set' for m in self.messages())))

    def test_numeric_x11_namespace_stays_readonly(self):
        self.evaluate('queue=[]', self.transport)
        self.evaluate("sourceSnapshot=({outputName:'Fixture',activity:{status:'unavailable',currentId:'',ids:[],names:[]},desktop:{status:'ready',currentId:'1',ids:['1','2'],names:['Uma','Outra']}})")
        self.assertFalse(self.adapter.property('available'))
        self.assertFalse(self.evaluate('request()'))

    def test_reentrant_hide_in_observation_never_emits_readback(self):
        self.ready()
        self.root.setProperty('hideOnObserve', True)
        self.evaluate('request()')
        for value in (':1.40', 'one', None, 'two', ':1.40'):
            self.reply(value)
        self.assertEqual(self.root.property('observations'), 0)
        self.assertEqual(self.root.property('failures'), 1)

    def test_unique_owner_set_get_and_void_awaits_observation(self):
        self.ready()
        self.assertTrue(self.evaluate('request()'))
        self.reply(':1.40')
        self.reply('one')
        self.assertEqual(self.messages()[-1], {'service': ':1.40', 'member': 'Set', 'signature': '(ssv)'})
        self.reply(None)
        self.assertEqual(self.root.property('replies'), 1)
        self.assertEqual(self.root.property('observations'), 0)
        self.reply('two')
        self.reply(':1.40')
        self.assertEqual(self.root.property('observations'), 1)
        self.assertTrue(all((m['service'] == ':1.40' for m in self.messages() if m['member'] in ('Set', 'Get'))))

    def test_owner_replaced_after_set_refuses_readback(self):
        self.ready()
        self.evaluate('request()')
        self.reply(':1.40')
        self.reply('one')
        self.reply(None)
        self.reply('two')
        self.reply(':1.41')
        self.assertEqual(self.root.property('observations'), 0)
        self.assertEqual(self.root.property('failures'), 1)
        self.assertFalse(self.adapter.property('available'))

    def test_drift_guard_before_set_zero_write(self):
        self.ready()
        self.evaluate('request()')
        self.reply(':1.40')
        self.root.setProperty('guardAllowed', False)
        self.reply('one')
        self.assertFalse(any((m['member'] == 'Set' for m in self.messages())))
        self.assertEqual(self.root.property('failures'), 1)

    def test_namespace_mismatch_and_owner_loss(self):
        self.reply(':1.40')
        self.reply('uuid-not-source')
        self.assertFalse(self.adapter.property('available'))
        self.assertFalse(self.evaluate('request()'))

    def test_hide_during_preflight_never_sets(self):
        self.ready()
        self.evaluate('request()')
        self.adapter.setProperty('active', False)
        self.reply(':1.40')
        self.assertFalse(any((m['member'] == 'Set' for m in self.messages())))
        self.assertEqual(self.root.property('failures'), 1)
    def prepare_composition(self, backend_first):
        if backend_first:
            self.ready()
            self.evaluate('attachState()')
        else:
            self.evaluate('attachStateFirst()')
            self.ready()
        self.state = self.root.findChild(QObject, 'compositionState')
        self.assertTrue(self.evaluate('requestState()'))

    def complete_readback(self):
        for value in (':1.40', 'one', None, 'two', ':1.40'):
            self.reply(value)

    def assert_model_late_confirmation(self, backend_first):
        self.prepare_composition(backend_first)
        self.complete_readback()
        self.assertTrue(self.state.property('pending'))
        before = len(self.messages())
        self.evaluate("modelCurrent('two')")
        self.assertEqual(self.state.property('status'), 'observed')
        self.assertFalse(self.state.property('pending'))
        self.assertTrue(self.adapter.property('available'))
        self.assertEqual(len(self.messages()), before)
        self.assertEqual(sum(m['member'] == 'Set' for m in self.messages()), 1)

    def test_model_late_backend_listener_first_confirms(self):
        self.assert_model_late_confirmation(True)

    def test_model_late_state_listener_first_confirms(self):
        self.assert_model_late_confirmation(False)

    def test_tab_cancel_while_model_late_refuses_observation(self):
        self.prepare_composition(True)
        self.complete_readback()
        self.assertTrue(self.state.property('pending'))
        self.state.setProperty('active', False)
        self.evaluate("modelCurrent('two')")
        self.assertFalse(self.state.property('pending'))
        self.assertNotEqual(self.state.property('status'), 'observed')
        self.assertEqual(sum(m['member'] == 'Set' for m in self.messages()), 1)

    def test_source_unavailable_after_readback_still_refuses(self):
        self.prepare_composition(True)
        self.complete_readback()
        self.evaluate('sourceSnapshot=null')
        self.assertFalse(self.adapter.property('available'))
        self.assertFalse(self.state.property('pending'))
        self.assertEqual(self.state.property('status'), 'failed')

    def existing_readback_before_model(self):
        origin = '11111111-1111-4111-8111-111111111111'
        target = '22222222-2222-4222-8222-222222222222'
        for value in (':1.40', origin, ':1.40'):
            self.reply(value)
        self.evaluate('attachState()')
        self.state = self.root.findChild(QObject, 'state')
        self.assertTrue(self.evaluate('request()'))
        for value in (':1.40', origin, None, target, ':1.40'):
            self.reply(value)
        self.assertTrue(self.state.property('pending'))

    def test_existing_state_attaches_after_backend_ready_model_late_confirms(self):
        self.existing_readback_before_model()
        self.evaluate('observedSource()')
        evidence = json.loads(self.evaluate('evidence()'))
        self.assertEqual(evidence['status'], 'observed')
        self.assertFalse(evidence['pending'])
        self.assertGreater(evidence['revision'], evidence['requestRevision'])
        self.assertEqual(evidence['sets'], 1)

    def test_existing_state_simultaneous_current_inventory_drift_refuses(self):
        self.existing_readback_before_model()
        self.evaluate("sourceSnapshot={outputName:'Fixture',activity:sourceSnapshot.activity,desktop:{status:'ready',currentId:'22222222-2222-4222-8222-222222222222',ids:['22222222-2222-4222-8222-222222222222','11111111-1111-4111-8111-111111111111'],names:['Segunda','Primeira']}}")
        self.assertEqual(self.state.property('status'), 'failed')
        self.assertFalse(self.state.property('pending'))
        self.assertEqual(json.loads(self.evaluate('evidence()'))['sets'], 1)

    def test_existing_state_tab_cancel_before_model_late_refuses(self):
        self.existing_readback_before_model()
        self.state.setProperty('active', False)
        self.evaluate('observedSource()')
        self.assertNotEqual(self.state.property('status'), 'observed')
        self.assertFalse(self.state.property('pending'))
        self.assertEqual(json.loads(self.evaluate('evidence()'))['sets'], 1)

if __name__ == '__main__':
    unittest.main()
