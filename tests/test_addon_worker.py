"""Private synthetic files only; no producer commands, bus or network."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).absolute().parents[1]
CODE = ROOT / 'package/contents/code'


def load(name, base=CODE):
    spec = importlib.util.spec_from_file_location('_test_' + name, base / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(version='1.0.0'):
    return dict(formatVersion='0.1-experimental', id='org.example.battery',
                name='Battery', description='Passive synthetic battery', author='Example',
                license='MIT', version=version, origin='https://example.org/project',
                renderer='peripheral-battery',
                source=dict(namespace='example', formatVersion='0.1-experimental'))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.w = load('addon_worker')
        self.tmp = tempfile.TemporaryDirectory(prefix='addon-service-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir(mode=0o700)
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.root / 'data'),
                        XDG_STATE_HOME=str(self.root / 'state'), DBUS_SESSION_BUS_ADDRESS='',
                        DBUS_SYSTEM_BUS_ADDRESS='', PYTHONDONTWRITEBYTECODE='1')

    def call(self, action, *args, env=None):
        run = subprocess.run([sys.executable, '-I', '-B', str(CODE / 'addon_worker.py'),
                              '--source-sha', self.w.source_fingerprint(CODE), action, *args],
                             env=env or self.env, cwd=self.root, capture_output=True, timeout=5)
        self.assertEqual(run.stderr, b'')
        self.assertEqual(run.stdout.count(b'\n'), 1)
        response = json.loads(run.stdout)
        self.assertEqual(run.returncode, 0 if response['ok'] else 1)
        self.assertEqual(response['formatVersion'], '0.1-experimental')
        self.assertNotIn(str(self.root), run.stdout.decode())
        return response

    def test_inspect_install_consent_is_explicit_and_hash_bound(self):
        raw = json.dumps(manifest(), indent=2).encode()
        p = self.root / 'chosen.json'
        p.write_bytes(raw)
        p.chmod(0o600)
        preview = self.call('inspect', p.as_uri())['result']
        self.assertEqual(preview['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.call('install', p.as_uri(), '0' * 64)['error']['code'], 'hash')
        installed = self.call('install', p.as_uri(), preview['sha256'])['result']
        self.assertFalse(installed['addons'][0]['enabled'])
        enabled = self.call('enable', 'org.example.battery', preview['sha256'])['result']
        self.assertTrue(enabled['addons'][0]['enabled'])
        self.assertNotEqual(installed['generation'], enabled['generation'])
        self.assertEqual(self.call('snapshot')['result']['peripherals']['addon']['reason'],
                         'export_missing')

    def test_unexpected_backend_failure_is_finite_and_does_not_claim_cancellation(self):
        backend = self.w.load_backend(CODE)
        with mock.patch.dict(os.environ, self.env), mock.patch.object(self.w, 'load_backend', return_value=backend), mock.patch.object(
                backend, 'enable_addon', side_effect=RuntimeError('private traceback sentinel')):
            response = self.w.execute('enable', ['org.example.battery', 'a' * 64],
                                      base=CODE, expected_source=self.w.source_fingerprint(CODE))
        self.assertEqual(response['error'], dict(code='io', committed=None, generation=None))
        self.assertNotIn('sentinel', json.dumps(response))

    def source_copy(self):
        base = self.root / 'source'
        base.mkdir(mode=0o700)
        for name in self.w.SOURCE_NAMES:
            shutil.copyfile(CODE / name, base / name)
        return base

    def test_source_changed_during_multifile_pin_is_not_reported_unchanged(self):
        base = self.source_copy()
        original_read = os.read
        changed = []

        def reading(fd, size):
            data = original_read(fd, size)
            if b'FORMAT_VERSION =' in data and not changed:
                changed.append(True)
                source = base / 'addon_service.py'
                source.write_bytes(source.read_bytes() + b'\n# replacement\n')
            return data
        with mock.patch.object(self.w.os, 'read', side_effect=reading):
            with self.assertRaises(ValueError):
                self.w.source_fingerprint(base)
        self.assertTrue(changed)

    def package(self, version='1.0.0'):
        p = self.root / ('chosen-' + version + '.json')
        p.write_text(json.dumps(manifest(version), indent=2))
        p.chmod(0o600)
        return p, hashlib.sha256(p.read_bytes()).hexdigest()

    def test_actual_cli_update_rollback_disable_remove_and_export_expiry(self):
        p, first = self.package()
        self.call('install', p.as_uri(), first)
        # Even unsafe producer state is untouched while host consent is off.
        self.root.joinpath('state').symlink_to(self.root / 'nonexistent')
        self.assertEqual(self.call('snapshot')['result']['peripherals']['addon']['reason'], 'disabled')
        self.root.joinpath('state').unlink()
        self.call('enable', 'org.example.battery', first)
        now = time.time_ns() // 1000000
        export = dict(formatVersion='0.1-experimental', producer='example', producerVersion='1.0.0',
                      generatedAtMs=now, expiresAtMs=now + 30000, intervalSeconds=10,
                      devices=[dict(kind='mouse', link='usb', present=True, stale=False,
                                    observedAtMs=now, battery=dict(percent=0, level=None,
                                    charging='charging', estimated=True), components=[])])
        directory = self.root / 'state/example/exports'
        directory.mkdir(mode=0o700, parents=True)
        self.root.joinpath('state').chmod(0o700)
        self.root.joinpath('state/example').chmod(0o700)
        exported = directory / 'orla-peripherals-v1.json'
        exported.write_text(json.dumps(export))
        exported.chmod(0o600)
        fresh = self.call('snapshot')['result']
        self.assertEqual(fresh['modules'], ['peripherals'])
        self.assertEqual(fresh['schemaVersion'], 2)
        self.assertEqual(fresh['peripherals']['devices'][0]['percent'], 0)
        self.assertTrue(fresh['peripherals']['devices'][0]['estimated'])
        export.update(generatedAtMs=now - 30001, expiresAtMs=now - 1)
        export['devices'][0]['observedAtMs'] = now - 30001
        exported.write_text(json.dumps(export))
        expired = self.call('snapshot')['result']['peripherals']
        self.assertEqual(expired['addon']['reason'], 'expired')
        self.assertEqual(expired['devices'], [])
        second_file, second = self.package('2.0.0')
        updated = self.call('install', second_file.as_uri(), second)['result']['addons'][0]
        self.assertFalse(updated['enabled'])
        self.assertEqual(updated['previousSha256'], first)
        self.assertEqual(self.call('enable', 'org.example.battery', first)['error']['code'], 'hash')
        rolled = self.call('rollback', 'org.example.battery', second)['result']['addons'][0]
        self.assertEqual(rolled['sha256'], first)
        self.assertFalse(rolled['enabled'])
        self.call('enable', 'org.example.battery', first)
        self.assertFalse(self.call('disable', 'org.example.battery', first)['result']['addons'][0]['enabled'])
        self.assertEqual(self.call('remove', 'org.example.battery', first)['result']['addons'], [])
        self.assertEqual(self.call('list')['result']['addons'], [])

    def test_empty_and_inspect_require_no_home_and_arguments_are_finite(self):
        env = dict(self.env, HOME='', XDG_DATA_HOME='relative', XDG_STATE_HOME='relative')
        self.assertEqual(self.call('empty', env=env)['result'], dict(schemaVersion=2, modules=[]))
        p, digest = self.package()
        self.assertEqual(self.call('inspect', p.as_uri(), env=env)['result']['sha256'], digest)
        for action, args, code in [('pack', [], 'format'), ('list', ['--home', '/private'], 'format'),
                                   ('inspect', ['https://example.org/remote'], 'file'),
                                   ('inspect', ['file:///tmp/%ZZ'], 'file'),
                                   ('inspect', ['file://localhost/tmp/file'], 'file'),
                                   ('inspect', ['file:///tmp/../file'], 'file'),
                                   ('inspect', ['file:///tmp/' + 'a' * 4100], 'file'),
                                   ('enable', ['org.example.battery', 'A' * 64], 'hash')]:
            with self.subTest(action=action, code=code):
                self.assertEqual(self.call(action, *args)['error'],
                                 dict(code=code, committed=False, generation=None))
        self.assertFalse((self.root / 'data').exists())
        self.assertFalse((self.root / 'state').exists())

    def test_source_policy_covers_bytes_mode_hardlinks_and_symlinked_ancestors(self):
        base = self.source_copy()
        pin = self.w.source_fingerprint(base)
        source = base / 'addon_store.py'
        source.chmod(0o600)
        self.assertNotEqual(self.w.source_fingerprint(base), pin)
        source.chmod(0o666)
        with self.assertRaises(ValueError):
            self.w.source_fingerprint(base)
        source.chmod(0o600)
        hard = self.root / 'hardlink'
        os.link(source, hard)
        with self.assertRaises(ValueError):
            self.w.source_fingerprint(base)
        hard.unlink()
        linked = self.root / 'linked'
        linked.symlink_to(base, target_is_directory=True)
        with self.assertRaises(OSError):
            self.w.source_fingerprint(linked)
        self.assertEqual(self.w.execute('list', [], base=base, expected_source=pin)['error']['code'],
                         'source_changed')

    def test_cwd_namespace_poisoning_cannot_import_or_execute_provider(self):
        p, digest = self.package()
        sentinel = self.root / 'executed'
        for name in ('addon_store.py', 'addon_io.py', 'addon_format.py', 'addon_worker.py'):
            (self.root / name).write_text('raise RuntimeError("CWD sentinel must never load")\n')
        self.assertEqual(self.call('inspect', p.as_uri())['result']['sha256'], digest)
        self.assertFalse(sentinel.exists())

    def test_maximum_catalog_metadata_fits_one_bounded_frame(self):
        backend = self.w.load_backend(CODE)
        paths = backend.AddonPaths(home=self.home, data_home=self.root / 'data', state_home=self.root / 'state')
        for index in range(32):
            record = manifest()
            record.update(id='org.example.item' + str(index), name='界' * 80,
                          description='界' * 240, author='界' * 120, license='界' * 80)
            p = self.root / ('item' + str(index) + '.json')
            raw = json.dumps(record, ensure_ascii=False).encode()
            p.write_bytes(raw)
            p.chmod(0o600)
            backend.install_addon(paths=paths, file=p, expected_sha256=hashlib.sha256(raw).hexdigest())
        response = self.call('list')
        self.assertEqual(len(response['result']['addons']), 32)
        self.assertLessEqual(len((self.w.encoded(response) + '\n').encode()), 262144)

    def test_backend_postcommit_fields_and_source_changed_after_commit_survive_worker(self):
        backend = self.w.load_backend(CODE)
        pin = self.w.source_fingerprint(CODE)
        with mock.patch.dict(os.environ, self.env), mock.patch.object(self.w, 'load_backend', return_value=backend), mock.patch.object(
                backend, 'remove_addon', side_effect=backend.AddonError('io', committed=True, generation='b' * 32)):
            response = self.w.execute('remove', ['org.example.battery', 'a' * 64], base=CODE, expected_source=pin)
        self.assertEqual(response['error'], dict(code='io', committed=True, generation='b' * 32))
        with mock.patch.dict(os.environ, self.env), mock.patch.object(self.w, 'load_backend', return_value=backend), mock.patch.object(
                backend, 'disable_addon', return_value=dict(generation='c' * 32, addons=[])), mock.patch.object(
                self.w, 'source_fingerprint', side_effect=[pin, pin, 'd' * 64]):
            response = self.w.execute('disable', ['org.example.battery', 'a' * 64], base=CODE, expected_source=pin)
        self.assertEqual(response['error'], dict(code='source_changed', committed=True, generation='c' * 32))

    def test_projection_seconds_cannot_be_boolean_even_if_numerically_equal(self):
        backend = self.w.load_backend(CODE)
        projection = dict(status='stale', generatedAt=True, source='addon', producerVersion='1',
                          limited=True, devices=[], generatedAtMs=1000, expiresAtMs=31000, leaseMs=30000,
                          addon=dict(id=None, sha256=None, enabled=False, generation=None,
                                     producerNamespace=None, reason='expired', errorCode=None))
        response = dict(formatVersion='0.1-experimental', ok=True,
                        result=dict(schemaVersion=2, modules=['peripherals'], peripherals=projection))
        with self.assertRaises(ValueError):
            self.w.validate_response((json.dumps(response) + '\n').encode(), 0, 'snapshot', backend)


if __name__ == '__main__':
    unittest.main()
