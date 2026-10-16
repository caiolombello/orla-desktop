"""Theme service: owned private D-Bus, copied installed helpers, no real session."""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / 'package/contents/code'
EXAMPLE = ROOT / 'themes/examples/mare.json'

@contextlib.contextmanager
def service(worker=None):
    children = []
    with tempfile.TemporaryDirectory(prefix='orla-service-proof-') as temp:
        root = Path(temp)
        code = root / 'installed'
        shutil.copytree(CODE, code)
        if worker is not None:
            (code / 'theme_file.py').chmod(0o600)
            (code / 'theme_file.py').write_text(worker)
        config = root / 'bus.conf'
        config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=' + temp + '</listen><auth>EXTERNAL</auth><policy context="default"><allow own="*"/><allow send_destination="*"/><allow receive_sender="*"/></policy></busconfig>')
        env = {k:v for k,v in os.environ.items() if not k.startswith(('DBUS_', 'AT_SPI_')) and k not in ('DISPLAY','WAYLAND_DISPLAY')}
        try:
            daemon = subprocess.Popen(['dbus-daemon','--nofork','--nopidfile','--nosyslog','--config-file='+str(config),'--print-address=1'], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            children.append(daemon)
            with selectors.DefaultSelector() as ready:
                ready.register(daemon.stdout, selectors.EVENT_READ)
                assert ready.select(3)
                address = daemon.stdout.readline().decode().strip()
            env.update(DBUS_SESSION_BUS_ADDRESS=address, DBUS_SYSTEM_BUS_ADDRESS=address)
            process = subprocess.Popen([sys.executable,'-I','-B',str(code/'theme_service.py'),'--serve'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(process)
            def command(member, *arguments):
                return ['gdbus','call','--address',address,'--dest','org.orla.Themes','--object-path','/org/orla/Themes','--method',member,'--',*arguments]
            end=time.monotonic()+3
            while True:
                assert process.poll() is None, 'service_exit'
                check=subprocess.run(command('org.freedesktop.DBus.Introspectable.Introspect'), env=env, capture_output=True, timeout=1)
                if check.returncode==0:
                    break
                assert time.monotonic()<end, 'ready_deadline'
                time.sleep(.02)
            assert b'LoadThemeFile' in check.stdout
            def call(url, wait=True):
                invocation=subprocess.Popen(command('org.orla.Themes1.LoadThemeFile',url),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                children.append(invocation)
                if not wait:
                    return invocation
                output,error=invocation.communicate(timeout=6)
                assert invocation.returncode==0, 'call_failed'
                values=ast.literal_eval(output.decode())
                assert type(values) is tuple and len(values)==1 and type(values[0]) is str
                return json.loads(values[0])
            yield root,code,process,call
        finally:
            for process in reversed(children):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                for stream in (process.stdout,process.stderr):
                    if stream is not None:
                        stream.close()

class ServiceTests(unittest.TestCase):
    def test_installed_source_absent_success_and_safe_errors(self):
        with service() as (root,code,process,call):
            selected=root/'synthetic ?#.json'
            selected.write_bytes(EXAMPLE.read_bytes())
            result=call(selected.as_uri())
            self.assertIs(result['valid'],True)
            self.assertEqual(result['theme']['id'],'org.orla.example.mare')
            for url,expected in [('-secret','file'),('file://foreign/secret','file'),('file:///'+'x'*16384,'size'),((root/'absent').as_uri(),'file')]:
                response=call(url)
                self.assertEqual(response,{'formatVersion':'0.1-experimental','valid':False,'code':expected})
            selected.write_bytes(b'{secret invalid')
            self.assertEqual(call(selected.as_uri())['code'],'json')

    def test_busy_until_worker_reaped_and_timeout(self):
        worker='import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(30)\n'
        with service(worker) as (_,_,process,call):
            first=call('file:///synthetic',False)
            time.sleep(.2)
            self.assertEqual(call('file:///second')['code'],'busy')
            output,_=first.communicate(timeout=6)
            self.assertEqual(json.loads(ast.literal_eval(output.decode())[0])['code'],'timeout')
            self.assertIsNone(process.poll())
            second=call('file:///next',False)
            time.sleep(.1)
            self.assertEqual(call('file:///other')['code'],'busy')
            second.communicate(timeout=6)

    def test_invalid_worker_response_is_safe(self):
        for worker in ('print("unknown secret")\n', 'print("x"*70000)\n',
                       'print(\'{"formatVersion":"0.1-experimental","valid":true,"theme":{}}\')\n'):
            with self.subTest(worker=hashlib.sha256(worker.encode()).hexdigest()), service(worker) as (_,_,_,call):
                self.assertEqual(call('file:///synthetic')['code'],'invalid_response')

    def test_parser_replacement_during_work_refuses_publication_and_exits(self):
        worker='import time\ntime.sleep(.6)\nprint("unknown")\n'
        with service(worker) as (_,code,process,call):
            first=call('file:///synthetic',False)
            time.sleep(.2)
            parser=code/'theme_format.py'
            parser.chmod(0o600)
            parser.write_bytes(parser.read_bytes()+b'\n# replacement\n')
            output,_=first.communicate(timeout=6)
            self.assertEqual(json.loads(ast.literal_eval(output.decode())[0])['code'],'unavailable')
            self.assertEqual(process.wait(timeout=3),0)

    def test_disconnected_caller_does_not_clear_busy_barrier(self):
        worker='import time\ntime.sleep(1)\nprint("invalid")\n'
        with service(worker) as (_,_,process,call):
            first=call('file:///synthetic',False)
            time.sleep(.2)
            first.terminate()
            first.wait(timeout=2)
            self.assertEqual(call('file:///other')['code'],'busy')
            time.sleep(1.1)
            self.assertEqual(call('file:///new')['code'],'invalid_response')
            self.assertIsNone(process.poll())

    def test_shutdown_reaps_owned_worker_before_service_exit(self):
        with tempfile.TemporaryDirectory(prefix='orla-worker-pid-') as directory:
            pidfile=Path(directory)/'pid'
            worker=('import os,pathlib,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                    'target=pathlib.Path('+repr(str(pidfile))+')\n'
                    'temporary=target.with_suffix(".pending")\n'
                    'temporary.write_text(str(os.getpid()))\nos.replace(temporary,target)\ntime.sleep(30)\n')
            with service(worker) as (_,_,process,call):
                first=call('file:///synthetic',False)
                end=time.monotonic()+2
                while not pidfile.exists():
                    self.assertLess(time.monotonic(),end)
                    time.sleep(.02)
                pid=int(pidfile.read_text())
                process.terminate()
                self.assertEqual(process.wait(timeout=3),0)
                first.communicate(timeout=2)
                self.assertFalse((Path('/proc')/str(pid)).exists())

    def test_idle_exit_without_child_after_thirty_seconds(self):
        with service() as (_,_,process,call):
            start=time.monotonic()
            self.assertEqual(process.wait(timeout=34),0)
            self.assertGreaterEqual(time.monotonic()-start,28)

    def test_continuous_oversized_output_cannot_postpone_kill(self):
        worker='import os,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nend=time.monotonic()+4\nwhile time.monotonic()<end: os.write(1,b"x"*8192)\n'
        with service(worker) as (_,_,process,call):
            start=time.monotonic()
            self.assertEqual(call('file:///synthetic')['code'],'invalid_response')
            self.assertLess(time.monotonic()-start,2)

    def test_wrong_cli_has_no_qt_import_or_argument_echo(self):
        result=subprocess.run([sys.executable,'-I','-B',str(CODE/'theme_service.py'),'secret'],capture_output=True,timeout=3)
        self.assertEqual(result.returncode,2)
        self.assertNotIn(b'secret',result.stdout+result.stderr)
        probe='import runpy,sys; runpy.run_path(sys.argv[1],run_name="inert"); assert not any(x.startswith("PySide6") for x in sys.modules)'
        self.assertEqual(subprocess.run([sys.executable,'-I','-B','-c',probe,str(CODE/'theme_service.py')],capture_output=True,timeout=3).returncode,0)

if __name__=='__main__':
    unittest.main(verbosity=2)
