"""Private synthetic distribution tests; never launch a desktop or contact a bus."""
import hashlib
from contextlib import contextmanager
import fcntl
import io
import zipfile
import json
import os
import re
import signal
import stat
import time
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from workspace import package
from workspace import install

SOURCE = Path(__file__).resolve().parents[1]
COMMIT = '5b0ab82b023ad1d2ef4b12c2bc63f288454c29ea'


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='orla-install-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'casa ç % $ ` " com espaços ; $(touch PWN) & \' \\'
        self.home.mkdir()
        self.paths = install.InstallPaths(self.home, self.home / 'data', self.home / 'state', self.home / 'config')
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.paths.data_home),
                        XDG_STATE_HOME=str(self.paths.state_home), XDG_CONFIG_HOME=str(self.paths.config_home),
                        PYTHONDONTWRITEBYTECODE='1', DBUS_SESSION_BUS_ADDRESS='unix:path=/absent-orla-test',
                        DBUS_SYSTEM_BUS_ADDRESS='unix:path=/absent-orla-test', TMPDIR=str(self.base))
        self.env.pop('PYTHONPATH', None)
        environment = patch.dict(os.environ, self.env, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.source = self.base / 'source'
        for name in package.PAYLOAD:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((SOURCE / name).read_bytes())
            path.chmod(0o644)
        (self.source / 'package/metadata.json').write_text('{"KPlugin":{"Version":"0.2.9"}}')
        self.archive = package.build(self.source, self.base / 'artifacts', commit=COMMIT)
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def put(self, **kwargs):
        return install.install_archive(self.archive, paths=self.paths, expected_sha256=self.sha,
                                       expected_commit=COMMIT, service='test-plasma.service', **kwargs)

    def test_install_extracts_verified_generation_and_status_without_qt(self):
        result = self.put()
        self.assertEqual(result['integrity'], 'verified')
        self.assertFalse(result['nativeValidated'])
        self.assertEqual(result['runtime'], 'unverified')
        root = self.paths.data_home / 'orla-desktop/workspace/versions' / self.sha
        self.assertEqual(package.verify_directory(root)['commit'], COMMIT)
        self.assertEqual(install.status(self.paths)['current'], self.sha)
        self.assertTrue((self.home / '.local/bin/orla-workspace').is_file())
        self.assertTrue((self.paths.data_home / 'applications/org.orla.Workspace.desktop').is_file())

    def test_interrupted_install_recovers_without_rewriting_history(self):
        def fail(name):
            if name == 'after_publish_1':
                raise RuntimeError('primary-failure')
        with self.assertRaisesRegex(RuntimeError, 'primary-failure'):
            self.put(failpoint=fail)
        history = {p: p.read_bytes() for folder in ('receipts', 'transactions')
                   for p in (self.paths.state / folder).glob('*.json')}
        self.assertEqual(install.status(self.paths)['integrity'], 'pending')
        self.assertEqual(install.recover(self.paths)['current'], self.sha)
        for path, data in history.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(install.recover(self.paths)['integrity'], 'verified')

    def test_update_retains_one_generation_and_rollback_toggles_payload_only(self):
        self.put()
        tools = {p.name: p.read_bytes() for p in (self.paths.base / 'tools').iterdir()}
        (self.source / 'LICENSE').write_text('synthetic second generation\n')
        archive = package.build(self.source, self.base / 'second', commit='a' * 40)
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        result = install.update_archive(archive, paths=self.paths, expected_sha256=sha, expected_commit='a' * 40)
        self.assertEqual((result['current'], result['previous']), (sha, self.sha))
        result = install.rollback(self.paths)
        self.assertEqual((result['current'], result['previous']), (self.sha, sha))
        self.assertEqual(install.rollback(self.paths)['current'], sha)
        with self.assertRaisesRegex(install.InstallError, 'retained_predecessor'):
            install.update_archive(archive, paths=self.paths, expected_sha256=sha, expected_commit='a' * 40)
        self.assertEqual(tools, {p.name: p.read_bytes() for p in (self.paths.base / 'tools').iterdir()})

    def test_uninstall_preserves_config_banks_audit_and_refuses_unknown_children(self):
        sentinels = [self.paths.config_home / 'plasmashellrc',
                     self.paths.state_home / 'orla/layouts/first-bank',
                     self.paths.state_home / 'orla/layouts/current-bank']
        for path in sentinels:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'private synthetic sentinel')
        self.put()
        foreign = self.paths.base / 'foreign'
        foreign.write_bytes(b'never remove')
        with self.assertRaisesRegex(install.InstallError, 'unknown_children'):
            install.uninstall(self.paths)
        self.assertTrue(foreign.exists())
        foreign.unlink()
        history = {p: p.read_bytes() for p in (self.paths.state / 'receipts').iterdir()}
        self.assertFalse(install.uninstall(self.paths)['installed'])
        self.assertFalse(self.paths.base.exists())
        self.assertFalse((self.home / '.local/bin/orla-workspace').exists())
        for path in sentinels:
            self.assertEqual(path.read_bytes(), b'private synthetic sentinel')
        for path, data in history.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(install.status(self.paths)['integrity'], 'absent')

    def test_installed_cli_works_after_source_and_archive_removed_from_unrelated_cwd(self):
        moved = self.base / 'received elsewhere.zip'
        self.archive.rename(moved)
        self.archive = moved
        self.put()
        shutil.rmtree(self.source)
        moved.unlink()
        result = subprocess.run([str(self.home / '.local/bin/orla-workspacectl'), 'status'],
                                cwd='/', env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['current'], self.sha)

    def test_wrong_external_pins_are_refused_before_any_install_output(self):
        for sha, commit in [('0' * 64, COMMIT), (self.sha, 'f' * 40), ('bad', COMMIT), (self.sha, 'bad')]:
            with self.subTest(sha=sha, commit=commit):
                with self.assertRaises(install.InstallError):
                    install.install_archive(self.archive, paths=self.paths, expected_sha256=sha,
                                            expected_commit=commit, service='test.service')
                self.assertFalse(self.paths.state.exists())
                self.assertFalse(self.paths.base.exists())

    def wait_file(self, path, process=None):
        deadline = time.monotonic() + 8
        while not path.exists() and time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                self.fail('synthetic session exited early: ' + str(process.returncode))
            time.sleep(.01)
        self.assertTrue(path.exists(), 'synthetic session did not reach barrier')

    def test_installed_supervisor_holds_shared_lease_through_signal_and_child_barrier(self):
        # This signed test generation uses a synthetic entry, never Qt/Plasma.
        entry = """import os,signal,time,json,sys
from pathlib import Path
root=Path(os.environ['XDG_CONFIG_HOME']);root.mkdir(parents=True,exist_ok=True)
def close(number,frame):
 (root/'closing').write_text(str(number))
signal.signal(signal.SIGINT,close);signal.signal(signal.SIGTERM,close)
(root/'ready').write_text(json.dumps(sys.argv[1:]))
while not (root/'barrier').exists(): time.sleep(.01)
(root/'joined').write_text('worker joined')
"""
        (self.source / 'workspace/main.py').write_text(entry)
        self.archive = package.build(self.source, self.base / 'synthetic-session', commit=COMMIT)
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.put()
        shutil.rmtree(self.source)
        self.archive.unlink()
        env = {k: v for k, v in self.env.items() if k != 'PYTHONPATH'}
        for number in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=number):
                for name in ('ready', 'closing', 'barrier', 'joined'):
                    (self.paths.config_home / name).unlink(missing_ok=True)
                arguments = [] if number == signal.SIGINT else ['--service', 'override.service']
                expected_service = 'test-plasma.service' if not arguments else 'override.service'
                process = subprocess.Popen([str(self.home / '.local/bin/orla-workspace'), *arguments],
                                           cwd='/', env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    self.wait_file(self.paths.config_home / 'ready', process)
                    self.assertEqual(json.loads((self.paths.config_home / 'ready').read_text()), ['--service', expected_service])
                    with self.assertRaisesRegex(install.InstallError, 'busy_close_workspace'):
                        install.uninstall(self.paths)
                    process.send_signal(number)
                    self.wait_file(self.paths.config_home / 'closing', process)
                    self.assertIsNone(process.poll())
                    for action in (install.recover, install.rollback, install.uninstall):
                        with self.assertRaisesRegex(install.InstallError, 'busy_close_workspace'):
                            action(self.paths)
                    self.assertEqual(install.status(self.paths)['integrity'], 'verified')
                    (self.paths.config_home / 'barrier').write_text('release worker')
                    stdout, stderr = process.communicate(timeout=8)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
                    self.assertEqual((self.paths.config_home / 'joined').read_text(), 'worker joined')
                finally:
                    (self.paths.config_home / 'barrier').touch()
                    process.communicate(timeout=8)
        self.assertFalse(install.uninstall(self.paths)['installed'])

    def test_caller_xdg_fallbacks_and_explicit_invalid_roots(self):
        for value in (None, '', 'relative/path'):
            env = {'HOME': str(self.home)}
            if value is not None:
                env.update({key: value for key in ('XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CONFIG_HOME')})
            paths = install.InstallPaths.from_environment(env)
            self.assertEqual(paths.data_home, self.home / '.local/share')
            self.assertEqual(paths.state_home, self.home / '.local/state')
            self.assertEqual(paths.config_home, self.home / '.config')
        for value in (Path('relative'), Path('/'), Path('/tmp/../elsewhere')):
            with self.assertRaises(install.InstallError):
                install.InstallPaths(self.home, value, self.paths.state_home, self.paths.config_home)
        self.put()
        altered = install.InstallPaths(self.home, self.paths.data_home, self.paths.state_home, self.home / 'other config')
        with self.assertRaisesRegex(install.InstallError, 'root_drift'):
            install.status(altered)

    def test_manager_status_runs_with_qt_imports_prohibited(self):
        self.put()
        code = """import sys,runpy
class NoQt:
 def find_spec(self,fullname,*args):
  if fullname.startswith(('PySide','PyQt')): raise RuntimeError('Qt import forbidden')
sys.meta_path.insert(0,NoQt())
sys.argv=[sys.argv[1],'status']
runpy.run_path(sys.argv[0],run_name='__main__')
"""
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(SOURCE / 'workspace/install.py')],
                                env=self.env, cwd='/', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['integrity'], 'verified')

    def test_doctor_uses_actual_passive_bundle_diagnosis(self):
        self.put()
        with patch.dict(os.environ, self.env, clear=True):
            result = install.doctor(self.paths)
        self.assertEqual(result['integrity'], 'verified')
        self.assertIn(result['runtime']['status'], ('ready', 'qt_runtime_missing', 'unsupported_runtime',
                                                  'qml_load_failed', 'qt_probe_failed', 'qt_probe_timeout'))
        self.assertFalse(result['nativeValidated'])
        self.assertFalse(result['serviceContacted'])

    def test_every_declared_install_boundary_recovers_or_aborts_without_history_rewrite(self):
        for name in ('before_stage', 'after_stage_root', 'after_stage_directory', 'after_stage_file_create',
                     'after_stage_write', 'after_stage', 'after_intent', 'after_publish_0', 'after_publish_1',
                     'after_publish_2', 'after_publish_3', 'after_publish', 'before_selector', 'after_selector'):
            with self.subTest(boundary=name):
                home = self.home / name
                home.mkdir()
                paths = install.InstallPaths(home, home / 'data', home / 'state', home / 'config')
                def fail(point):
                    if point == name:
                        raise RuntimeError('preserve original failure')
                with self.assertRaisesRegex(RuntimeError, 'preserve original failure'):
                    install.install_archive(self.archive, paths=paths, expected_sha256=self.sha,
                                            expected_commit=COMMIT, service='literal.service', failpoint=fail)
                history = {p: p.read_bytes() for folder in ('receipts', 'transactions')
                           for p in (paths.state / folder).glob('*.json')}
                result = install.recover(paths)
                self.assertEqual(result['installed'], name not in ('before_stage', 'after_stage_root', 'after_stage_directory',
                                                                   'after_stage_file_create', 'after_stage_write', 'after_stage'))
                for path, data in history.items():
                    self.assertEqual(path.read_bytes(), data)
                install.recover(paths)

    def test_collisions_and_symlink_parents_are_never_adopted(self):
        foreign = self.home / '.local/bin/orla-workspace'
        foreign.parent.mkdir(parents=True)
        foreign.write_bytes(b'foreign wrapper')
        with self.assertRaisesRegex(install.InstallError, 'collision'):
            self.put()
        self.assertEqual(foreign.read_bytes(), b'foreign wrapper')
        foreign.unlink()
        foreign.symlink_to(self.archive)
        with self.assertRaisesRegex(install.InstallError, 'collision'):
            self.put()
        self.assertTrue(foreign.is_symlink())
        foreign.unlink()
        self.paths.base.parent.rmdir()
        self.paths.base.parent.symlink_to(self.base)
        with self.assertRaises(install.InstallError):
            self.put()

    def test_file_mode_hash_and_owned_directory_identity_drift_are_refused(self):
        self.put()
        path = self.paths.base / 'versions' / self.sha / 'LICENSE'
        original = path.read_bytes()
        path.write_bytes(b'drift')
        with self.assertRaisesRegex(install.InstallError, 'file_drift'):
            install.status(self.paths)
        path.write_bytes(original)
        path.chmod(0o600)
        with self.assertRaisesRegex(install.InstallError, 'file_drift'):
            install.uninstall(self.paths)
        path.chmod(0o644)
        old = self.paths.base.with_name('moved-owned-tree')
        self.paths.base.rename(old)
        shutil.copytree(old, self.paths.base)
        with self.assertRaisesRegex(install.InstallError, 'directory_drift'):
            install.status(self.paths)
        self.assertTrue((old / 'versions' / self.sha / 'LICENSE').exists())

    def test_recovery_refuses_foreign_publish_target_before_any_overwrite(self):
        def fail(name):
            if name == 'after_intent':
                raise RuntimeError('interrupted')
        with self.assertRaises(RuntimeError):
            self.put(failpoint=fail)
        self.paths.base.mkdir()
        sentinel = self.paths.base / 'foreign'
        sentinel.write_bytes(b'preserve')
        with self.assertRaisesRegex(install.InstallError, 'collision'):
            install.recover(self.paths)
        self.assertEqual(sentinel.read_bytes(), b'preserve')
        self.assertTrue(list(self.paths.base.parent.glob('.workspace-incoming-*')))

    def test_lock_is_taken_before_selector_read_and_cli_busy_says_close(self):
        self.put()
        with (self.paths.state / 'use.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = self.paths.state / 'current.json'
            saved = current.read_bytes()
            current.write_bytes(b'invalid selector proves it was not read')
            try:
                with self.assertRaisesRegex(install.InstallError, 'busy_close_workspace'):
                    install.launch(self.paths, command_factory=lambda *_: self.fail('must not spawn'))
                result = subprocess.run([str(self.home / '.local/bin/orla-workspacectl'), 'uninstall'],
                                        env=self.env, cwd='/', capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)['message'], 'Close Workspace and retry.')
            finally:
                current.write_bytes(saved)

    def test_malformed_and_future_archives_are_rejected_before_staging(self):
        data = self.archive.read_bytes()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            rows = [(info, archive.read(info)) for info in archive.infolist()]
        for schema in ('future-workspace-9000', None):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                for info, content in rows:
                    if info.filename == 'manifest.json':
                        manifest = json.loads(content)
                        manifest['schema'] = schema
                        content = json.dumps(manifest).encode()
                    archive.writestr(info, content)
            bad = self.base / 'bad.zip'
            bad.write_bytes(buffer.getvalue())
            with self.assertRaises(install.InstallError):
                install.install_archive(bad, paths=self.paths, expected_sha256=hashlib.sha256(bad.read_bytes()).hexdigest(),
                                        expected_commit=COMMIT, service='literal.service')
            self.assertFalse(self.paths.state.exists())
        bad.write_bytes(b'not an archive')
        with self.assertRaises(install.InstallError):
            install.install_archive(bad, paths=self.paths, expected_sha256=hashlib.sha256(bad.read_bytes()).hexdigest(),
                                    expected_commit=COMMIT, service='literal.service')

    def test_accepted_manifest_bytes_are_preserved_in_generation(self):
        output = io.BytesIO()
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(output, 'w') as target:
            for info in source.infolist():
                data = source.read(info)
                if info.filename == 'manifest.json':
                    data = json.dumps(json.loads(data), indent=2).encode() + b'\n'
                    expected = data
                target.writestr(info, data)
        self.archive.write_bytes(output.getvalue())
        self.sha = hashlib.sha256(output.getvalue()).hexdigest()
        self.put()
        self.assertEqual((self.paths.base / 'versions' / self.sha / 'manifest.json').read_bytes(), expected)

    def test_partial_stage_io_failure_preserves_primary_and_can_be_recovered(self):
        fsync = os.fsync
        triggered = False
        def injected(fd):
            nonlocal triggered
            fsync(fd)
            name = os.readlink('/proc/self/fd/' + str(fd))
            if not triggered and '.workspace-incoming-' in name and name.endswith('/LICENSE') and os.fstat(fd).st_size:
                triggered = True
                raise OSError('first durable-stage failure')
        with patch('os.fsync', injected):
            with self.assertRaisesRegex(OSError, 'first durable-stage failure'):
                self.put()
        self.assertTrue(triggered)
        self.assertFalse(install.recover(self.paths)['installed'])
        self.assertFalse(list(self.paths.base.parent.glob('.workspace-incoming-*')))

    @contextmanager
    def partial_record_writer(self, record):
        fdopen = os.fdopen
        failure = OSError(28, 'synthetic partial immutable record')
        observed = {}
        class PartialWriter:
            def __init__(self, stream, path):
                self.stream, self.path = stream, path
            def __enter__(self):
                self.stream.__enter__()
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def write(self, data):
                value = json.loads(bytes(data))
                kind = ('done' if 'outcome' in value else
                        'intent' if value.get('phase') == 'ready' else 'receipt')
                if kind == record and not observed:
                    observed['path'] = self.path
                    self.stream.write(data[:max(1, len(data) // 2)])
                    self.stream.flush()
                    os.fsync(self.stream.fileno())
                    raise failure
                return self.stream.write(data)
        def injected(fd, *args, **kwargs):
            stream = fdopen(fd, *args, **kwargs)
            path = Path(os.readlink('/proc/self/fd/' + str(fd)))
            if args and args[0] == 'wb' and path.parent.name in ('transactions', 'receipts'):
                return PartialWriter(stream, path)
            return stream
        with patch('os.fdopen', injected):
            yield observed, failure

    def immutable_history(self):
        return {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_ino)
                for folder in ('receipts', 'transactions')
                for p in (self.paths.state / folder).iterdir()}

    def assert_partial_record_aborts_and_retries(self, record):
        with patch('subprocess.Popen', side_effect=AssertionError('process forbidden')):
            with self.partial_record_writer(record) as (observed, failure):
                with self.assertRaises(OSError) as raised:
                    self.put()
            self.assertIs(raised.exception, failure)
            self.assertTrue(observed)
            before = self.immutable_history()
            self.assertFalse((self.paths.state / 'current.json').exists())
            self.assertFalse(install.recover(self.paths)['installed'])
            self.assertFalse(list(self.paths.base.parent.glob('.workspace-incoming-*')))
            self.assertFalse(observed['path'].exists(), 'caught partial output must be cleaned')
            self.assertEqual(install.recover(self.paths)['integrity'], 'absent')
            self.assertEqual(self.put()['current'], self.sha)
            self.assertEqual(install.status(self.paths)['integrity'], 'verified')
            after = self.immutable_history()
            for path, snapshot in before.items():
                self.assertEqual(after[path], snapshot)
            for path in after:
                self.assertTrue(path.name.endswith('.json'))
                json.loads(path.read_bytes())

    def test_partial_intent_write_aborts_and_retries_without_rewriting_history(self):
        self.assert_partial_record_aborts_and_retries('intent')

    def test_partial_receipt_write_aborts_and_retries_without_rewriting_history(self):
        self.assert_partial_record_aborts_and_retries('receipt')

    def test_partial_done_write_replays_without_rewriting_history(self):
        with patch('subprocess.Popen', side_effect=AssertionError('process forbidden')):
            with self.partial_record_writer('done') as (observed, failure):
                with self.assertRaises(OSError) as raised:
                    self.put()
            self.assertIs(raised.exception, failure)
            self.assertTrue(observed)
            before = self.immutable_history()
            self.assertTrue((self.paths.state / 'current.json').exists())
            self.assertEqual(install.status(self.paths)['integrity'], 'pending')
            self.assertEqual(install.recover(self.paths)['current'], self.sha)
            self.assertFalse(observed['path'].exists(), 'caught partial output must be cleaned')
            after = self.immutable_history()
            for path, snapshot in before.items():
                self.assertEqual(after[path], snapshot)
            self.assertEqual(install.recover(self.paths)['integrity'], 'verified')
            self.assertEqual(self.immutable_history(), after)
            for path in after:
                self.assertTrue(path.name.endswith('.json'))
                json.loads(path.read_bytes())

    def test_corrupt_final_records_remain_refused_and_unchanged(self):
        with patch('subprocess.Popen', side_effect=AssertionError('process forbidden')):
            for record in ('intent', 'receipt', 'done'):
                with self.subTest(record=record):
                    home = self.home / record
                    home.mkdir()
                    paths = install.InstallPaths(home, home / 'data', home / 'state', home / 'config')
                    def fail(name):
                        if name == 'after_intent':
                            raise RuntimeError('before publication')
                    with self.assertRaisesRegex(RuntimeError, 'before publication'):
                        install.install_archive(self.archive, paths=paths, expected_sha256=self.sha,
                                                expected_commit=COMMIT, service='literal.service', failpoint=fail)
                    transaction = json.loads((paths.state / 'pending.json').read_bytes())
                    folder = 'receipts' if record == 'receipt' else 'transactions'
                    suffix = '-done.json' if record == 'done' else '.json'
                    final = paths.state / folder / (transaction['id'] + suffix)
                    final.write_bytes(b'{"foreign":')
                    final.chmod(0o600)
                    before = (final.read_bytes(), final.stat().st_mode, final.stat().st_ino)
                    for _ in range(2):
                        with self.assertRaisesRegex(install.InstallError, 'invalid_record'):
                            install.recover(paths)
                        self.assertEqual((final.read_bytes(), final.stat().st_mode, final.stat().st_ino), before)
                    with self.assertRaisesRegex(install.InstallError, 'recovery_required'):
                        install.launch(paths, command_factory=lambda *_: self.fail('must not launch'))

    def test_update_boundaries_recover_old_or_new_with_frozen_tools(self):
        (self.source / 'LICENSE').write_text('new generation for interrupted update\n')
        archive = package.build(self.source, self.base / 'update-boundaries', commit='a' * 40)
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        for boundary in ('after_stage_root', 'after_stage_file_create', 'after_stage_write', 'after_stage',
                         'after_intent', 'after_publish_0', 'before_selector', 'after_selector'):
            with self.subTest(boundary=boundary):
                home = self.home / boundary
                home.mkdir()
                paths = install.InstallPaths(home, home / 'data', home / 'state', home / 'config')
                install.install_archive(self.archive, paths=paths, expected_sha256=self.sha,
                                        expected_commit=COMMIT, service='literal.service')
                frozen = (paths.base / 'tools/install.py').read_bytes()
                def fail(name):
                    if name == boundary:
                        raise RuntimeError('update interrupted')
                with self.assertRaisesRegex(RuntimeError, 'update interrupted'):
                    install.update_archive(archive, paths=paths, expected_sha256=sha,
                                           expected_commit='a' * 40, failpoint=fail)
                result = install.recover(paths)
                self.assertEqual(result['current'], self.sha if boundary in ('after_stage_root', 'after_stage_file_create',
                                                                             'after_stage_write', 'after_stage') else sha)
                self.assertEqual((paths.base / 'tools/install.py').read_bytes(), frozen)
                self.assertEqual(json.loads((paths.state / 'receipts' /
                                 (json.loads((paths.state / 'current.json').read_bytes())['receipt'] + '.json')).read_bytes())['service'],
                                 'literal.service')

    def test_partial_uninstall_recovery_preserves_immutable_receipts(self):
        self.put()
        receipts = {p: p.read_bytes() for p in (self.paths.state / 'receipts').iterdir()}
        def fail(name):
            if name == 'after_remove_0':
                raise RuntimeError('uninstall interrupted')
        with self.assertRaisesRegex(RuntimeError, 'uninstall interrupted'):
            install.uninstall(self.paths, failpoint=fail)
        self.assertFalse(install.recover(self.paths)['installed'])
        for path, data in receipts.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertFalse((self.home / '.local/bin/orla-workspacectl').exists())

    def test_recovery_verifies_entire_uninstall_closure_before_removing_any_file(self):
        self.put()
        def fail(name):
            if name == 'after_intent':
                raise RuntimeError('uninstall interrupted')
        with self.assertRaises(RuntimeError):
            install.uninstall(self.paths, failpoint=fail)
        foreign = self.paths.base / 'versions' / self.sha / 'LICENSE'
        foreign.write_bytes(b'foreign bytes after intent')
        before = {p: p.read_bytes() for p in self.paths.base.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(install.InstallError, 'file_drift'):
            install.recover(self.paths)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertTrue((self.home / '.local/bin/orla-workspacectl').exists())

    def test_install_lifecycle_preserves_all_other_installs_and_layout_config(self):
        sentinels = [self.paths.config_home / 'kdeglobals', self.paths.config_home / 'plasma-org.kde.plasma.desktop-appletsrc',
                     self.paths.data_home / 'plasma/plasmoids/org.caiodock.dock/private',
                     self.paths.data_home / 'plasma/plasmoids/org.orla.bar/private',
                     self.paths.data_home / 'orla-desktop/launcher/private',
                     self.paths.state_home / 'orla/layouts/first-bank/receipt.json',
                     self.paths.state_home / 'orla/layouts/current-bank/config']
        for path in sentinels:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic preserved data')
        before = {path: (path.read_bytes(), path.stat().st_mode, path.stat().st_ino) for path in sentinels}
        self.put()
        (self.source / 'LICENSE').write_text('replacement generation\n')
        archive = package.build(self.source, self.base / 'replacement', commit='a' * 40)
        install.update_archive(archive, paths=self.paths, expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                               expected_commit='a' * 40)
        install.rollback(self.paths)
        install.uninstall(self.paths)
        for path, (data, mode, inode) in before.items():
            self.assertEqual((path.read_bytes(), path.stat().st_mode, path.stat().st_ino), (data, mode, inode))
        allowed = set(sentinels)
        for path in self.home.rglob('*'):
            if path.is_file():
                self.assertTrue(path in allowed or self.paths.state in path.parents, str(path.relative_to(self.home)))

    def test_pinned_tools_drift_is_refused_before_installed_manager_execution(self):
        self.put()
        marker = self.home / 'manager-executed'
        manager = self.paths.base / 'tools/install.py'
        manager.write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n')
        result = subprocess.run([str(self.home / '.local/bin/orla-workspacectl'), 'status'],
                                env=self.env, cwd='/', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(marker.exists())
        self.assertEqual(json.loads(result.stdout)['error'], 'pinned_tools_unavailable')

    def test_desktop_exec_decodes_to_one_literal_launcher_path(self):
        self.put()
        desktop = self.paths.data_home / 'applications/org.orla.Workspace.desktop'
        entry = next(line[5:] for line in desktop.read_text().splitlines() if line.startswith('Exec='))
        general = {'n': '\n', 'r': '\r', 't': '\t', 's': ' ', '\\': '\\'}
        decoded = re.sub(r'\\([nrts\\])', lambda m: general[m[1]], entry).replace('%%', '%')
        # The single quoted Exec token has the same special-character escaping
        # here; evaluate only argv construction, never execute its target.
        result = subprocess.run(['/bin/sh', '-c', 'set -- ' + decoded + '; printf "%s\\0" "$@"'],
                                env=self.env, cwd=self.base, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(b'\0'), [os.fsencode(self.home / '.local/bin/orla-workspace'), b''])
        self.assertFalse((self.base / 'PWN').exists())

    def test_old_tree_drift_prevents_destructive_staging_recovery(self):
        self.put()
        (self.source / 'LICENSE').write_text('another payload\n')
        archive = package.build(self.source, self.base / 'pending-update', commit='a' * 40)
        def fail(name):
            if name == 'after_stage':
                raise RuntimeError('interrupted staging')
        with self.assertRaises(RuntimeError):
            install.update_archive(archive, paths=self.paths, expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                                   expected_commit='a' * 40, failpoint=fail)
        staged = list((self.paths.base / 'versions').glob('.workspace-incoming-*'))
        self.assertEqual(len(staged), 1)
        (self.paths.base / 'foreign').write_text('unknown file')
        with self.assertRaisesRegex(install.InstallError, 'unknown_children'):
            install.recover(self.paths)
        self.assertTrue(staged[0].exists(), 'recovery must check old closure before deleting stage')

    def test_process_death_after_partial_publish_is_recoverable(self):
        code = """import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from workspace import install
install.install_archive(Path(sys.argv[2]),paths=install.InstallPaths.from_environment(),
 expected_sha256=sys.argv[3],expected_commit=sys.argv[4],service='literal.service',
 failpoint=lambda point: os._exit(91) if point=='after_publish_1' else None)
"""
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SOURCE), str(self.archive), self.sha, COMMIT],
                                env=self.env, cwd='/', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 91, result.stderr)
        shutil.rmtree(self.source)
        self.archive.unlink()
        recovered = subprocess.run([str(self.home / '.local/bin/orla-workspacectl'), 'recover'],
                                   env=self.env, cwd='/', capture_output=True, timeout=10)
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertEqual(json.loads(recovered.stdout)['current'], self.sha)

    def test_uncheckpointed_private_stage_after_process_death_is_refused(self):
        # Explicit boundary: inode creation and its identity checkpoint are
        # separate syscalls; an unrecorded artifact must remain unadopted.
        code = """import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from workspace import install
mkdir=os.mkdir
def crash(path,*args,**kwargs):
 mkdir(path,*args,**kwargs)
 if str(path).startswith('.workspace-incoming-'): os._exit(92)
os.mkdir=crash
install.install_archive(Path(sys.argv[2]),paths=install.InstallPaths.from_environment(),
 expected_sha256=sys.argv[3],expected_commit=sys.argv[4],service='literal.service')
"""
        result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(SOURCE), str(self.archive), self.sha, COMMIT],
                                env=self.env, cwd='/', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 92, result.stderr)
        stages = list(self.paths.base.parent.glob('.workspace-incoming-*'))
        self.assertEqual(len(stages), 1)
        with self.assertRaisesRegex(install.InstallError, 'unreceipted_stage'):
            install.recover(self.paths)
        self.assertTrue(stages[0].exists())
        self.assertFalse(self.paths.base.exists())

    def test_intent_and_done_publication_windows_preserve_immutable_history(self):
        replace = os.replace
        for boundary in ('intent-before-pending', 'done-before-pending-clear'):
            with self.subTest(boundary=boundary):
                home = self.home / boundary
                home.mkdir()
                paths = install.InstallPaths(home, home / 'data', home / 'state', home / 'config')
                failed = False
                def injected(src, dst, **kwargs):
                    nonlocal failed
                    if dst == 'pending.json' and not failed:
                        fd = os.open(src, os.O_RDONLY, dir_fd=kwargs['src_dir_fd'])
                        with os.fdopen(fd, 'rb') as stream:
                            value = json.load(stream)
                        trigger = (value is None if boundary == 'done-before-pending-clear' else
                                   type(value) is dict and value.get('phase') == 'ready')
                        if trigger:
                            failed = True
                            raise OSError('publication interruption')
                    return replace(src, dst, **kwargs)
                with patch('os.replace', injected):
                    with self.assertRaisesRegex(OSError, 'publication interruption'):
                        install.install_archive(self.archive, paths=paths, expected_sha256=self.sha,
                                                expected_commit=COMMIT, service='literal.service')
                self.assertTrue(failed)
                before = {p: p.read_bytes() for folder in ('transactions', 'receipts') for p in (paths.state / folder).iterdir()}
                self.assertEqual(install.recover(paths)['current'], self.sha)
                for path, data in before.items():
                    self.assertEqual(path.read_bytes(), data)

    def test_child_keeps_lease_if_synthetic_supervisor_dies(self):
        entry = """import os,time
from pathlib import Path
root=Path(os.environ['XDG_CONFIG_HOME']);root.mkdir(parents=True,exist_ok=True)
(root/'ready').touch()
while not (root/'barrier').exists(): time.sleep(.01)
(root/'joined').touch()
"""
        (self.source / 'workspace/main.py').write_text(entry)
        self.archive = package.build(self.source, self.base / 'orphan-session', commit=COMMIT)
        self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.put()
        supervisor = subprocess.Popen([str(self.home / '.local/bin/orla-workspace')], cwd='/', env=self.env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.wait_file(self.paths.config_home / 'ready', supervisor)
            os.kill(supervisor.pid, signal.SIGKILL)  # Synthetic supervisor only; never the session child.
            supervisor.wait(timeout=8)
            with self.assertRaisesRegex(install.InstallError, 'busy_close_workspace'):
                install.recover(self.paths)
        finally:
            (self.paths.config_home / 'barrier').touch()
            supervisor.wait(timeout=8)
            self.wait_file(self.paths.config_home / 'joined')
        deadline = time.monotonic() + 8
        while True:
            try:
                self.assertEqual(install.recover(self.paths)['integrity'], 'verified')
                break
            except install.InstallError as exc:
                if exc.code != 'busy_close_workspace' or time.monotonic() > deadline:
                    raise
                time.sleep(.01)

    def test_management_lifecycle_never_spawns_a_process(self):
        (self.source / 'LICENSE').write_text('second archive\n')
        archive = package.build(self.source, self.base / 'no-process-update', commit='a' * 40)
        with patch('subprocess.Popen', side_effect=AssertionError('management must be inert')):
            self.put()
            install.status(self.paths)
            install.update_archive(archive, paths=self.paths, expected_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                                   expected_commit='a' * 40)
            install.rollback(self.paths)
            install.recover(self.paths)
            install.uninstall(self.paths)

    def test_cli_install_requires_both_pins_and_explicit_service(self):
        command = [sys.executable, '-I', '-B', str(SOURCE / 'workspace/install.py'), 'install', str(self.archive)]
        for arguments in ([], ['--sha256', self.sha, '--commit', COMMIT], ['--service', 'literal.service']):
            result = subprocess.run([*command, *arguments], env=self.env, cwd='/', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(self.paths.state.exists())
        result = subprocess.run([*command, '--sha256', self.sha, '--commit', COMMIT, '--service', 'literal.service'],
                                env=self.env, cwd='/', capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        controller = str(self.home / '.local/bin/orla-workspacectl')
        for action in ('status', 'recover', 'uninstall'):
            result = subprocess.run([controller, action], env=self.env, cwd='/', capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class RecordWriteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='orla-record-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'record.json'

    def test_final_name_appears_only_after_complete_file_fsync_and_never_replaces(self):
        fsync = os.fsync
        observed = []
        data = b'{"complete":"immutable record"}\n'
        def injected(fd):
            info = os.fstat(fd)
            if stat.S_ISREG(info.st_mode):
                self.assertFalse(self.path.exists())
                temporary = Path(os.readlink('/proc/self/fd/' + str(fd)))
                self.assertEqual(temporary.read_bytes(), data)
                self.assertEqual((stat.S_IMODE(info.st_mode), info.st_nlink, info.st_uid), (0o600, 1, os.getuid()))
                observed.append('complete-file')
            else:
                self.assertTrue(self.path.exists())
                self.assertEqual(observed[0], 'complete-file')
                observed.append('parent')
            fsync(fd)
        with patch('os.fsync', injected):
            install._write(self.path, data)
        self.assertIn('parent', observed)
        before = (self.path.read_bytes(), self.path.stat().st_ino)
        with self.assertRaisesRegex(install.InstallError, 'collision'):
            install._write(self.path, b'foreign replacement forbidden')
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_ino), before)
        self.assertEqual(list(self.directory.iterdir()), [self.path])

    def test_file_fsync_failure_and_secondary_cleanup_error_preserve_primary(self):
        fsync = os.fsync
        failure = OSError(28, 'first record fsync failure')
        def injected(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise failure
            fsync(fd)
            raise OSError('secondary cleanup fsync failure')
        with patch('os.fsync', injected):
            with self.assertRaises(OSError) as raised:
                install._write(self.path, b'complete but not durable')
        self.assertIs(raised.exception, failure)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_caught_failure_never_cleans_a_replaced_temporary(self):
        failure = OSError('first write failure')
        replaced = []
        def injected(fd):
            temporary = Path(os.readlink('/proc/self/fd/' + str(fd)))
            temporary.unlink()
            temporary.write_bytes(b'foreign inode must remain')
            replaced.append((temporary, temporary.stat().st_ino))
            raise failure
        with patch('os.fsync', injected):
            with self.assertRaises(OSError) as raised:
                install._write(self.path, b'owned bytes')
        self.assertIs(raised.exception, failure)
        self.assertFalse(self.path.exists())
        temporary, inode = replaced[0]
        self.assertEqual((temporary.read_bytes(), temporary.stat().st_ino), (b'foreign inode must remain', inode))

    def test_short_writes_are_completed_before_publication(self):
        fdopen = os.fdopen
        class ShortWriter:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                self.stream.__enter__()
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def write(self, data):
                return self.stream.write(data[:3])
        def injected(fd, *args, **kwargs):
            return ShortWriter(fdopen(fd, *args, **kwargs))
        with patch('os.fdopen', injected):
            install._write(self.path, b'complete after multiple short writes')
        self.assertEqual(self.path.read_bytes(), b'complete after multiple short writes')
        self.assertEqual(list(self.directory.iterdir()), [self.path])

    def test_atomic_selector_replacement_keeps_mutable_semantics(self):
        install._atomic(self.path, {'selector': 'old'})
        install._atomic(self.path, {'selector': 'new'})
        self.assertEqual(json.loads(self.path.read_bytes()), {'selector': 'new'})
        self.assertEqual(list(self.directory.iterdir()), [self.path])


if __name__ == '__main__':
    unittest.main()
