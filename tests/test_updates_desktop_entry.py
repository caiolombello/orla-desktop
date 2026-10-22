"""Passive Source entry: never a composition or native entry."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from scripts import caiodock
ROOT = Path(__file__).resolve().parents[1]

class EntryTests(unittest.TestCase):

    def test_lazy_command_and_complete_kit_guard(self):
        args = caiodock.parser().parse_args(['updates', 'desktop'])
        self.assertEqual(args.updates_action, 'desktop')
        with tempfile.TemporaryDirectory() as directory:
            error = io.StringIO()
            with mock.patch.object(caiodock, '__file__', str(Path(directory) / 'scripts/caiodock.py')), contextlib.redirect_stderr(error):
                self.assertEqual(caiodock.main(['updates', 'desktop']), 1)
            self.assertIn('complete source checkout', error.getvalue())

    def test_help_is_qt_free_and_missing_runtime_refuses_cleanly(self):
        import subprocess
        command=[sys.executable,'-S','-B',str(ROOT/'scripts/orla.py'),'updates','desktop']
        help_result=subprocess.run(command+['--help'],cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(help_result.returncode,0,help_result.stderr)
        refused=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=5)
        self.assertEqual(refused.returncode,1)
        self.assertIn('requires PySide6 6.11',refused.stderr)
        self.assertNotIn('Traceback',refused.stderr)

    def test_production_launch_signal_waits_for_owned_process_cleanup(self):
        import subprocess
        from test_updates_desktop_process import payload,REF
        with tempfile.TemporaryDirectory() as directory:
            private=Path(directory);helper=private/'fixture.py';marker=private/'pid'
            helper.write_text('import os,time\nopen('+repr(str(marker))+",'w').write(str(os.getpid()))\ntime.sleep(.35)\nprint("+repr(json.dumps(payload()))+')')
            code="""import sys,os,signal,time,json
from pathlib import Path
sys.path.insert(0,ROOT)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from scripts import updates_desktop as module
original=module.UpdatesController
holders=[]
def factory(*args,**kwargs):
    host=original(*args,runner=lambda *_:(sys.executable,['-I','-B',HELPER]),storage_root=Path(PRIVATE),**kwargs)
    holders.append(host)
    return host
module.UpdatesController=factory
app=QGuiApplication([])
QTimer.singleShot(30,lambda:holders[0].check())
QTimer.singleShot(80,lambda:os.kill(os.getpid(),signal.SIGTERM))
started=time.monotonic()
status=module.launch(Path(ROOT),REFERENCE)
pid=int(Path(MARKER).read_text())
print(json.dumps(dict(status=status,elapsed=time.monotonic()-started,alive=Path('/proc',str(pid)).exists())))
"""
            code='ROOT='+repr(str(ROOT))+';HELPER='+repr(str(helper))+';PRIVATE='+repr(str(private))+';MARKER='+repr(str(marker))+';REFERENCE='+repr(REF)+'\n'+code
            done=subprocess.run([sys.executable,'-I','-B','-c',code],cwd=ROOT,capture_output=True,text=True,timeout=6)
            self.assertEqual(done.returncode,0,done.stderr)
            data=json.loads(done.stdout)
            self.assertEqual(data['status'],0);self.assertFalse(data['alive']);self.assertGreater(data['elapsed'],.3)
            self.assertNotIn('Destroyed while process',done.stderr)

    def test_source_reference_is_bounded_and_never_installed(self):
        from scripts.updates_desktop_state import source_reference
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / 'package/metadata.json'
            p.parent.mkdir()
            p.write_text(json.dumps({'KPlugin': {'Id': 'org.caiodock.dock', 'Version': '1.2.3'}}))
            ref = source_reference(root)
            self.assertEqual(ref['role'], 'source')
            self.assertEqual(ref['version'], '1.2.3')
            self.assertIsNone(ref['commit'])
            self.assertEqual(ref['origin'], 'source-metadata')
            for version in ('01.2.3', None, '9' * 200):
                p.write_text(json.dumps({'KPlugin': {'Id': 'org.caiodock.dock', 'Version': version}}))
                self.assertIsNone(source_reference(root))
            p.unlink()
            p.symlink_to(ROOT / 'package/metadata.json')
            self.assertIsNone(source_reference(root))

    def test_open_is_passive_actual_ui_and_invalid_reference_disables_check(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickItem
        from scripts.updates_desktop import UpdatesController
        app = QGuiApplication.instance() or QGuiApplication([])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            host = UpdatesController(ROOT, reference=None, runner=lambda *args: calls.append(args), storage_root=root)
            engine = QQmlApplicationEngine()
            warnings = []
            engine.warnings.connect(lambda values: warnings.extend((v.toString() for v in values)))
            engine.rootContext().setContextProperty('updatesController', host)
            engine.load(QUrl.fromLocalFile(str(ROOT / 'workspace/Updates.qml')))
            self.assertTrue(engine.rootObjects(), warnings)
            window = engine.rootObjects()[0]
            app.processEvents()
            check = window.findChild(QQuickItem, 'updatesCheck')
            self.assertIsNotNone(check)
            self.assertFalse(check.property('enabled'))
            self.assertEqual(host.channel, 'stable')
            self.assertEqual(calls, [])
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual('Referência de versão indisponível', window.findChild(QQuickItem, 'updatesReference').property('text'))
            self.assertFalse(window.findChild(QQuickItem, 'updatesReferenceOrigin').isVisible())
            window.close()
            engine.deleteLater()
            app.processEvents()
            self.assertEqual(warnings, [])
