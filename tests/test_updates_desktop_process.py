"""Real asynchronous QProcess tests; children are synthetic, never network."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtTest import QTest
from scripts.updates_desktop import UpdatesController
from scripts.updates_contract import SOURCE
ROOT = Path(__file__).resolve().parents[1]
REF = dict(role='source', component='dock', origin='source-metadata', version='1.2.3', commit=None, digest='a' * 64)

def payload(status='update_available', channel='stable'):
    return dict(status=status, reason='network_error' if status == 'unavailable' else 'rate_limit' if status == 'rate_limited' else None, source=SOURCE, installed_version='1.2.3', available_version='2.0.0' if status in ('update_available', 'up_to_date') else None, available_url='https://github.com/caiolombello/orla-desktop/releases/tag/v2.0.0' if status in ('update_available', 'up_to_date') else None, channel=channel, checked_at='2026-10-20T12:00:00Z')

class ProcessFixture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from PySide6.QtGui import QGuiApplication
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.hosts = []

    def tearDown(self):
        for host in self.hosts:
            host.requestClose()
            self.wait(host)
        self.tmp.cleanup()

    def host(self, code, **options):
        helper = self.path / f'helper{len(self.hosts)}.py'
        helper.write_text(code)
        self.argv = []

        def runner(root, ref, channel):
            self.argv.append((root, ref.copy(), channel))
            return (sys.executable, ['-I', '-B', str(helper)])
        host = UpdatesController(ROOT, REF, runner=runner, storage_root=self.path, opener=lambda url: True, **options)
        self.hosts.append(host)
        return host

    def wait(self, host):
        for _ in range(400):
            if not host.busy:
                return
            QTest.qWait(10)
        self.fail('child not reaped')

class ProcessTests(ProcessFixture):

    def test_explicit_check_and_single_dispatch_with_literal_binding(self):
        host = self.host('import json,time\ntime.sleep(.06)\nprint(' + repr(json.dumps(payload())) + ')')
        self.assertEqual(self.argv, [])
        host.check()
        host.check()
        host.selectChannel('beta')
        self.assertTrue(host.busy)
        self.wait(host)
        self.assertEqual(len(self.argv), 1)
        self.assertEqual(self.argv[0][2], 'stable')
        self.assertEqual(host.state['record']['result']['status'], 'update_available')
        self.assertFalse(host.busy)

    def test_terminal_failures_cannot_enable_release(self):
        for code in ('print("not json")', 'print("x"*20000)', 'import sys;sys.stderr.write("x"*20000)', 'import os;os.abort()', 'print(' + repr(json.dumps(payload())) + ');raise SystemExit(2)', 'print(' + repr(json.dumps(payload()).replace('github.com/caiolombello', 'evil.test/caiolombello')) + ')'):
            with self.subTest(code=code[:30]):
                host = self.host(code)
                host.check()
                self.wait(host)
                self.assertEqual(host.state['record']['result']['status'], 'unavailable')
                self.assertFalse(host.state['releaseUrl'])

    def test_latched_close_owns_group_watchdog_and_keeps_event_loop_alive(self):
        marker = self.path / 'child.pid'
        code = "import os,signal,time\npid=os.fork()\nif pid==0:\n    while True: time.sleep(.01)\nopen(%r,'w').write(str(pid))\ndef stop(*args):\n    try: os.kill(pid,signal.SIGKILL)\n    except ProcessLookupError: pass\n    os.waitpid(pid,0)\n    raise SystemExit(0)\nsignal.signal(signal.SIGTERM,stop)\nwhile True: time.sleep(.01)\n" % str(marker)
        host = self.host(code, watchdog_ms=180)
        ready = []
        ticks = []
        host.closeReady.connect(lambda: ready.append(True))
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(True))
        timer.start(10)
        host.check()
        while not marker.exists():
            QTest.qWait(5)
        self.assertFalse(host.requestClose())
        host.check()
        host.selectChannel('beta')
        self.wait(host)
        timer.stop()
        self.assertEqual(ready, [True])
        self.assertEqual(host.channel, 'stable')
        self.assertGreater(len(ticks), 3)
        self.assertFalse(Path('/proc', marker.read_text()).exists(), 'descendant leaked')
        self.assertEqual(host.state['record']['result']['reason'], 'timeout')

    def test_production_cli_transport_worker_reaped_on_outer_deadline(self):
        marker = self.path / 'worker.pid'
        code = 'import sys,os,time\nsys.path.insert(0,' + repr(str(ROOT)) + ')\nfrom scripts import updates\n' + 'def blocked(*args):\n    open(' + repr(str(marker)) + ",'w').write(str(os.getpid()))\n    time.sleep(30)\n" + "updates.fetch_page=blocked\nraise SystemExit(updates.main(['check','--installed-version','1.2.3']))\n"
        host = self.host(code, watchdog_ms=250)
        host.check()
        while not marker.exists():
            QTest.qWait(5)
        self.wait(host)
        worker = Path('/proc', marker.read_text())
        self.assertFalse(worker.exists(), 'production CLI worker not reaped')

    def test_continuous_output_cannot_extend_cleanup_deadline(self):
        code = "import os,signal\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nwhile True: os.write(1,b'x'*4096)\n"
        host = self.host(code, watchdog_ms=1000)
        started = time.monotonic()
        host.check()
        self.wait(host)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(host.state['record']['result']['reason'], 'output_limit')

    def test_failed_spawn_closes_exactly_once(self):
        host = self.host('pass')
        host._runner = lambda *args: ('/absent-orla-fixture', [])
        host.check()
        ready = []
        host.closeReady.connect(lambda: ready.append(True))
        host.requestClose()
        self.wait(host)
        self.assertEqual(ready, [True])
        self.assertEqual(host.state['record']['result']['status'], 'unavailable')

    def test_opener_only_explicit_after_valid_result(self):
        host = self.host('print(' + repr(json.dumps(payload())) + ')')
        opened = []
        host._opener = lambda url: opened.append(url) or True
        host.openRelease()
        self.assertEqual(opened, [])
        host.check()
        self.wait(host)
        self.assertEqual(opened, [])
        host.openRelease()
        self.assertEqual(opened, [payload()['available_url']])
