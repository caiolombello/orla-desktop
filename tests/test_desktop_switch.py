import gc, json, os, tempfile, unittest
from pathlib import Path
_PRIVATE = tempfile.TemporaryDirectory(prefix='orla-switch-')
for name in ('config', 'data', 'cache', 'runtime'):
    Path(_PRIVATE.name, name).mkdir(mode=0o700)
for key, name in (('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache'), ('XDG_RUNTIME_DIR', 'runtime')):
    os.environ[key] = str(Path(_PRIVATE.name, name))
os.environ['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(Path(_PRIVATE.name, 'absent-session'))
os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = 'unix:path=' + str(Path(_PRIVATE.name, 'absent-system'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Fusion')
from PySide6.QtCore import QObject, QEvent, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression

class DesktopSwitchTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend((v.toString() for v in values)))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name('DesktopSwitchHarness.qml').resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.root = self.engine.rootObjects()[0]
        self.state = self.root.findChild(QObject, 'state')
        self.backend = self.root.findChild(QObject, 'backend')
        self.preserved = self.eval('JSON.stringify([profilesJSON,contextsJSON,activeProfileId,pomodoroDeadline,previewDirty])')

    def tearDown(self):
        if self.engine.rootObjects():
            self.assertEqual(self.eval('JSON.stringify([profilesJSON,contextsJSON,activeProfileId,pomodoroDeadline,previewDirty])'), self.preserved)
        self.root = None
        self.state = None
        self.backend = None
        self.engine.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.engine = None
        gc.collect()
        self.assertEqual(self.warnings, [])

    def eval(self, code, target=None):
        e = QQmlExpression(self.engine.rootContext(), target or self.root, code)
        value, _ = e.evaluate()
        self.assertFalse(e.hasError(), e.error().toString())
        return value

    def request(self):
        return self.eval("request('two')")

    def test_void_reply_needs_readback_and_current(self):
        self.assertTrue(self.request())
        self.eval('reply()', self.backend)
        self.assertTrue(self.state.property('pending'))
        self.eval("source('two')")
        self.assertTrue(self.state.property('pending'))
        self.eval("observed('two')", self.backend)
        self.assertFalse(self.state.property('pending'))
        self.assertEqual(self.state.property('status'), 'observed')

    def test_void_without_switch_fails(self):
        self.request()
        self.eval('reply()', self.backend)
        self.eval("observed('one')", self.backend)
        self.assertEqual(self.state.property('status'), 'failed')
        self.assertEqual(self.state.property('currentId'), 'one')

    def test_duplicate_click_and_current_noop(self):
        self.assertFalse(self.eval("request('one')"))
        self.assertEqual(self.backend.property('calls'), 0)
        self.assertTrue(self.request())
        self.assertFalse(self.request())
        self.assertEqual(self.backend.property('calls'), 1)

    def test_stale_revision_and_removed_target_refuse(self):
        rev = self.state.property('desktopRevision')
        self.eval("source('one',['one','three'],['Área','Terceira'])")
        self.assertFalse(self.eval(f"requestDesktopSwitch('two',{rev})", self.state))
        self.assertEqual(self.backend.property('calls'), 0)

    def test_drift_cancel_pending_before_dispatch(self):
        self.request()
        self.eval("source('three')")
        self.assertFalse(self.state.property('pending'))
        self.assertFalse(self.eval("guard('dispatch')", self.backend))
        self.assertEqual(self.backend.property('cancellations'), 1)

    def test_unavailable_hide_ignore_late_reply(self):
        self.backend.setProperty('available', False)
        self.assertFalse(self.request())
        self.assertEqual(self.backend.property('calls'), 0)
        self.backend.setProperty('available', True)
        self.request()
        self.state.setProperty('active', False)
        self.eval('reply()', self.backend)
        self.eval("observed('two')", self.backend)
        self.assertFalse(self.state.property('pending'))
        self.assertNotEqual(self.state.property('status'), 'observed')

    def test_external_change_updates_current(self):
        self.eval("source('three')")
        self.assertEqual(self.state.property('currentId'), 'three')
        self.assertEqual(self.backend.property('calls'), 0)

    def test_selection_duplicate_names_are_passive(self):
        self.assertTrue(self.eval("selectDesktop('two')", self.state))
        self.assertEqual(self.backend.property('calls'), 0)
        self.eval("source('one',['two','one','three'],['Renomeada','Área','Terceira'])")
        self.assertEqual(self.state.property('selectedId'), 'two')
        self.assertEqual(self.backend.property('calls'), 0)

    def test_readback_before_current_waits_old_generation_ignored(self):
        self.request()
        old = self.backend.property('lastId')
        self.eval('reply()', self.backend)
        self.eval("observed('two')", self.backend)
        self.assertTrue(self.state.property('pending'))
        self.eval("source('two')")
        self.assertEqual(self.state.property('status'), 'observed')
        self.eval("source('one')")
        self.request()
        self.eval(f"readback({old},'two',':1.44')", self.backend)
        self.assertTrue(self.state.property('pending'))

    def test_removal_unavailable_and_timeout_end_pending(self):
        self.request()
        self.eval("source('one',['one','three'],['Uma','Outra'])")
        self.assertFalse(self.state.property('pending'))
        self.eval("source('one')")
        self.request()
        self.eval('sourceSnapshot=null')
        self.assertFalse(self.state.property('pending'))

    def test_activity_changes_do_not_stale_desktop_intent(self):
        revision = self.state.property('desktopRevision')
        self.eval("sourceSnapshot={outputName:'Fixture',activity:{status:'ready',currentId:'different',ids:['different'],names:['Outra']},desktop:sourceSnapshot.desktop}")
        self.assertEqual(self.state.property('desktopRevision'), revision)
        self.assertTrue(self.request())

    def test_backend_swap_releases_exact_client(self):
        self.backend.setProperty('replaceDuringRequest', True)
        self.assertFalse(self.request())
        self.assertFalse(self.state.property('pending'))
        self.assertEqual(self.backend.property('cancellations'), 1)
        replacement = self.root.findChild(QObject, 'replacement')
        self.assertEqual(replacement.property('calls'), 0)
        self.assertEqual(replacement.property('cancellations'), 0)

    def test_cancel_reentry_refused(self):
        self.backend.setProperty('reenterDuringCancel', True)
        self.request()
        self.eval("source('three')")
        self.assertFalse(self.backend.property('reentered'))
        self.assertEqual(self.backend.property('calls'), 1)
        self.assertFalse(self.state.property('pending'))

    def test_owner_mismatch_fails_without_faking_current(self):
        self.request()
        self.eval('reply()', self.backend)
        self.eval("readback(lastId,'two',':1.45')", self.backend)
        self.assertEqual(self.state.property('status'), 'failed')
        self.assertEqual(self.state.property('currentId'), 'one')

    def test_timeout_ignores_late_reply(self):
        from PySide6.QtTest import QTest
        self.state.setProperty('confirmationTimeoutMs', 1)
        self.request()
        for _ in range(50):
            if not self.state.property('pending'): break
            QTest.qWait(10)
        self.assertFalse(self.state.property('pending'))
        self.assertEqual(self.state.property('status'), 'failed')
        self.eval('reply()', self.backend)
        self.eval("observed('two')", self.backend)
        self.assertEqual(self.state.property('status'), 'failed')
    def complete_switch(self):
        self.request()
        self.eval('reply()', self.backend)
        self.eval("source('two')")
        self.eval("observed('two')", self.backend)
        self.assertEqual(self.state.property('status'), 'observed')

    def test_new_selection_clears_previous_observation(self):
        self.complete_switch()
        self.eval("selectDesktop('three')", self.state)
        self.assertEqual(self.state.property('status'), 'idle')
        self.assertEqual(self.backend.property('calls'), 1)

    def test_external_current_clears_previous_observation(self):
        self.complete_switch()
        self.eval("source('three')")
        self.assertEqual(self.state.property('status'), 'idle')
        self.assertEqual(self.state.property('currentId'), 'three')

if __name__ == '__main__':
    unittest.main()
