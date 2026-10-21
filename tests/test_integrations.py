import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import os
import subprocess
import shutil
import sys
from unittest.mock import patch
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'package/contents/code/integrations.py'


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('integrations', MODULE)
        self.bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bridge)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.now = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)

    def write_history(self, records):
        path = self.home / '.local/share/codexbar-linux/history.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(record) + '\n' for record in records))
        return path

    def snapshot(self, providers):
        return {'timestamp': self.now.isoformat(), 'providers': providers, 'opencode_go': None}

    def write_state(self, relative, record):
        path = self.home / '.local/state' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record))
        return path

    def test_selected_modules_read_only_their_cache_and_omit_other_payloads(self):
        paths = {'quota': '.local/share/codexbar-linux/history.jsonl',
                 'recording': '.local/state/recording-cli/recording-session.json'}
        legacy = self.bridge.collect_snapshot(self.home, self.now)
        for module, relative in paths.items():
            with self.subTest(module=module), patch.object(self.bridge, '_read_bounded', side_effect=FileNotFoundError) as read:
                result = self.bridge.collect_selected_snapshot([module], self.home, self.now)
                read.assert_called_once_with(self.home / relative, **({'history': True} if module == 'quota' else {}))
                self.assertEqual(result, {'schemaVersion': 2, 'modules': [module],
                                         module: legacy[module]})

    def test_empty_and_invalid_module_selections_do_no_cache_io(self):
        with patch.object(self.bridge, '_read_bounded', side_effect=AssertionError('unexpected cache read')) as read, \
                patch.object(self.bridge.Path, 'home', side_effect=AssertionError('unexpected home lookup')), \
                patch.object(importlib.util, 'spec_from_file_location', side_effect=AssertionError('backend lookup')):
            self.assertEqual(self.bridge.collect_selected_snapshot([]),
                             {'schemaVersion': 2, 'modules': []})
            for selection in (None, 'quota', {}, ['unknown'], ['quota', 'quota'], [False],
                              [['quota']], ['quota', 'peripherals', 'recording', 'quota']):
                with self.subTest(selection=selection), self.assertRaises(ValueError):
                    self.bridge.collect_selected_snapshot(selection)
            read.assert_not_called()

    def test_selected_modules_are_canonical_and_legacy_shape_is_unchanged(self):
        result = self.bridge.collect_selected_snapshot(['recording', 'quota'], self.home, self.now)
        self.assertEqual(result['modules'], ['quota', 'recording'])
        self.assertNotIn('peripherals', result)
        legacy = self.bridge.collect_snapshot(self.home, self.now)
        self.assertEqual(set(legacy), {'schemaVersion', 'quota', 'peripherals', 'recording'})
        self.assertEqual(legacy['schemaVersion'], 1)

    def test_cache_percentages_preserve_zero_and_discard_sensitive_fields(self):
        self.write_history([self.snapshot([{
            'provider': 'codex', 'updated_at': self.now.isoformat(), 'account_email': 'secret@example.com',
            'login_method': 'private', 'primary': {'used_percent': 0, 'window_minutes': 300},
            'secondary': {'used_percent': None},
        }])])
        result = self.bridge.collect_snapshot(self.home, self.now)
        self.assertEqual(result['quota']['status'], 'ready')
        self.assertEqual([w['usedPercent'] for w in result['quota']['windows']], [0.0, None])
        self.assertNotIn('secret@example.com', json.dumps(result))
        self.assertNotIn('private', json.dumps(result))

    def test_old_failed_future_and_api_reads_never_become_fresh_quota(self):
        self.write_history([self.snapshot([
            {'provider': 'codex', 'updated_at': '2026-10-10T19:44:59+00:00', 'primary': {'used_percent': 80}},
            {'provider': 'claude', 'updated_at': self.now.isoformat(), 'error': 'secret authentication failure', 'primary': {'used_percent': 70}},
            {'provider': 'cursor', 'updated_at': '2026-10-11T00:00:00+00:00', 'primary': {'used_percent': 60}},
            {'provider': 'openai-api', 'updated_at': self.now.isoformat(), 'primary': {'used_percent': 12}},
        ])])
        result = self.bridge.collect_snapshot(self.home, self.now)
        self.assertEqual(result['quota']['status'], 'stale')
        windows = result['quota']['windows']
        self.assertEqual([w['provider'] for w in windows], ['codex', 'claude', 'cursor'])
        self.assertTrue(windows[0]['stale'])
        self.assertEqual([w['usedPercent'] for w in windows], [80.0, None, None])
        self.assertNotIn('secret', json.dumps(result))

    def test_partial_append_uses_last_complete_snapshot_but_malformed_complete_line_is_invalid(self):
        path = self.write_history([self.snapshot([{'provider': 'codex', 'updated_at': self.now.isoformat(), 'primary': {'used_percent': 42}}])])
        with path.open('ab') as handle:
            handle.write(b'{"timestamp":')
        self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['quota']['status'], 'ready')
        with path.open('ab') as handle:
            handle.write(b'broken}\n')
        self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['quota']['status'], 'invalid')

    def test_huge_final_record_and_malformed_shapes_fail_closed(self):
        path = self.write_history([self.snapshot([])])
        with path.open('ab') as handle:
            handle.write(b'x' * (300 * 1024) + b'\n')
        self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['quota']['status'], 'invalid')
        for providers in ({}, [None], [{'provider': 'codex', 'primary': []}]):
            self.write_history([self.snapshot(providers)])
            self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['quota']['status'], 'invalid')

    def test_snapshot_cli_runs_without_qt_or_provider_collectors(self):
        env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.home / '.local/share'),
                   XDG_STATE_HOME=str(self.home / '.local/state'))
        result = subprocess.run([sys.executable, '-S', str(MODULE), '--snapshot'], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['schemaVersion'], 1)
        self.assertEqual(value['quota']['status'], 'missing')

    def install_peripheral_addon(self, enabled=True, record=None):
        from test_addons import load, manifest, export
        self.store = load('addon_store')
        self.paths = self.store.AddonPaths(home=self.home,
            data_home=self.home / '.local/share', state_home=self.home / '.local/state')
        package = self.home / 'synthetic.orla-addon.json'
        package.write_text(json.dumps(manifest()))
        package.chmod(0o600)
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        self.store.install_addon(paths=self.paths, file=package, expected_sha256=digest)
        if enabled:
            self.store.enable_addon(paths=self.paths, addon_id='org.example.battery',
                                    expected_current_sha256=digest)
        value = export() if record is None else record
        stamp = int(self.now.timestamp() * 1000)
        value.update(generatedAtMs=stamp, expiresAtMs=stamp+30000)
        for device in value['devices']:
            if device['observedAtMs'] == 100000:
                device['observedAtMs'] = stamp
        path = self.paths.state_home / 'synthetic-battery/exports/orla-peripherals-v1.json'
        path.parent.mkdir(parents=True, mode=0o700)
        path.parent.parent.chmod(0o700)
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return path, digest

    def test_both_legacy_methods_ignore_private_cache_without_installed_consent(self):
        self.write_state('perigauge/state.json', {'schema': 1, 'generated_at': self.now.timestamp(),
            'devices': [{'name': 'PRIVATE-SENTINEL', 'kind': 'mouse', 'present': True,
                         'updated_at': self.now.timestamp(), 'battery': {'percent': 87}}]})
        for frame in (self.bridge.collect_snapshot(self.home, self.now),
                      self.bridge.collect_selected_snapshot(['peripherals'], self.home, self.now)):
            self.assertEqual(frame['peripherals']['status'], 'missing')
            self.assertEqual(frame['peripherals']['devices'], [])
            self.assertEqual(frame['peripherals']['addon']['reason'], 'not_installed')
            self.assertNotIn('PRIVATE-SENTINEL', json.dumps(frame))

    def test_installed_package_and_export_do_not_enable_reading(self):
        path, _ = self.install_peripheral_addon(enabled=False)
        real_open = os.open
        def guarded_open(name, *args, **kwargs):
            self.assertNotIn('synthetic-battery', str(name), 'unconsented producer read')
            return real_open(name, *args, **kwargs)
        with patch.object(os, 'open', side_effect=guarded_open):
            result = self.bridge.collect_selected_snapshot(['peripherals'], self.home, self.now)
        self.assertEqual(result['peripherals']['addon']['reason'], 'disabled')
        self.assertEqual(result['peripherals']['devices'], [])
        self.assertTrue(path.exists())

    def test_both_legacy_envelopes_project_actual_enabled_addon_and_preserve_zero(self):
        path, digest = self.install_peripheral_addon()
        before = (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
        for frame in (self.bridge.collect_snapshot(self.home, self.now),
                      self.bridge.collect_selected_snapshot(['peripherals'], self.home, self.now)):
            result = frame['peripherals']
            self.assertEqual(result['status'], 'ready')
            self.assertEqual(result['source'], 'addon')
            self.assertEqual(result['devices'][0]['percent'], 0)
            self.assertEqual(result['devices'][0]['name'], 'mouse')
            self.assertEqual(result['generatedAtMs'], int(self.now.timestamp()*1000))
            self.assertEqual(result['generatedAt'], self.now.timestamp())
            self.assertEqual(result['leaseMs'], 30000)
            self.assertEqual(result['addon']['sha256'], digest)
            self.assertRegex(result['addon']['generation'], r'^[0-9a-f]{32}$')
        self.assertEqual((path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns), before)

    def test_unselected_peripherals_never_lookup_backend_or_producer(self):
        self.install_peripheral_addon()
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=AssertionError('backend lookup')), \
                patch.object(os, 'open', side_effect=AssertionError('producer IO')):
            self.assertEqual(self.bridge.collect_selected_snapshot([], self.home, self.now),
                             {'schemaVersion': 2, 'modules': []})
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=AssertionError('backend lookup')):
            self.assertEqual(self.bridge.collect_selected_snapshot(['recording'], self.home, self.now)
                             ['recording']['status'], 'missing')

    def test_invalid_or_unsafe_export_is_finite_and_preserves_other_readers(self):
        path, _ = self.install_peripheral_addon()
        path.write_text('{"private":"PRIVATE-SENTINEL"}')
        result = self.bridge.collect_snapshot(self.home, self.now)
        self.assertEqual(result['peripherals']['status'], 'invalid')
        self.assertEqual(result['peripherals']['devices'], [])
        self.assertEqual(result['quota']['status'], 'missing')
        self.assertNotIn('PRIVATE-SENTINEL', json.dumps(result))
        path.unlink()
        os.mkfifo(path, 0o600)
        self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['peripherals']['status'], 'invalid')

    def test_recording_phase_is_cached_and_never_claims_live_capture(self):
        session = {'version': 1, 'id': 'private-session', 'owner': 'manual', 'backend': 'audio',
                   'phase': 'recording', 'startedAt': '2026-10-10T19:00:00+00:00', 'outputPath': '/private/output.wav', 'audio': {'microphone': 'private-source'}}
        self.write_state('recording-cli/recording-session.json', session)
        result = self.bridge.collect_snapshot(self.home, self.now)['recording']
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['state'], 'recording')
        self.assertEqual(result['elapsedSeconds'], 3600)
        self.assertFalse(result['livenessVerified'])
        self.assertNotIn('private', json.dumps(result))
        session['phase'] = 'stopped'
        session['endedAt'] = '2026-10-10T19:30:00+00:00'
        self.write_state('recording-cli/recording-session.json', session)
        result = self.bridge.collect_snapshot(self.home, self.now)['recording']
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['elapsedSeconds'], 1800)

    def test_bounded_tail_reads_recent_record_and_preserves_files(self):
        path = self.write_history([self.snapshot([{'provider': 'codex', 'updated_at': self.now.isoformat(), 'primary': {'used_percent': 12}}])])
        content = b'old malformed record\n' * 20000 + path.read_bytes()
        path.write_bytes(content)
        path.chmod(0o600)
        before = path.stat()
        self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['quota']['windows'][0]['usedPercent'], 12)
        self.assertEqual(path.read_bytes(), content)
        after = path.stat()
        self.assertEqual((before.st_mode, before.st_mtime_ns, before.st_size), (after.st_mode, after.st_mtime_ns, after.st_size))

    def test_invalid_optional_caches_are_neutral_and_do_not_stop_other_readers(self):
        self.write_state('perigauge/state.json', {'schema': 2, 'devices': []})
        self.write_state('recording-cli/recording-session.json', {'version': 1, 'phase': 'recording', 'startedAt': 'invalid'})
        result = self.bridge.collect_snapshot(self.home, self.now)
        self.assertEqual(result['quota']['status'], 'missing')
        self.assertEqual(result['peripherals']['status'], 'missing')
        self.assertEqual(result['peripherals']['addon']['reason'], 'not_installed')
        self.assertEqual(result['recording']['status'], 'invalid')
        self.assertEqual(result['recording']['state'], 'unknown')

    def test_runtime_honors_absolute_xdg_roots_without_reading_legacy_config(self):
        self.install_peripheral_addon()
        data = self.home / 'alternate-data'
        state = self.home / 'alternate-state'
        (self.home / '.local/share').rename(data)
        (self.home / '.local/state').rename(state)
        legacy = self.home / '.config/recording-cli/state.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"state":"recording"}')
        with patch.dict(os.environ, {'HOME': str(self.home), 'XDG_STATE_HOME': str(state),
                                     'XDG_DATA_HOME': str(data)}):
            result = self.bridge.collect_snapshot(now=self.now)
        self.assertEqual(result['peripherals']['status'], 'ready')
        self.assertEqual(result['peripherals']['devices'][0]['percent'], 0)
        self.assertEqual(result['recording']['status'], 'missing')

    def test_symlink_and_fifo_cache_are_rejected_without_following_or_blocking(self):
        path = self.home / '.local/share/codexbar-linux/history.jsonl'
        path.parent.mkdir(parents=True)
        target = self.home / 'secret'
        target.write_text(json.dumps(self.snapshot([])) + '\n')
        path.symlink_to(target)
        self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['quota']['status'], 'invalid')
        path.unlink()
        os.mkfifo(path)
        self.assertEqual(self.bridge.collect_snapshot(self.home, self.now)['quota']['status'], 'invalid')

    def test_monetary_windows_never_appear_as_quota_percentages(self):
        self.write_history([self.snapshot([
            {'provider': 'zen', 'updated_at': self.now.isoformat(), 'primary': {'used_percent': 75, 'reset_description': '$15 / $20'}},
            {'provider': 'cursor', 'updated_at': self.now.isoformat(),
             'primary': {'used_percent': 50, 'reset_description': '$10 / $20'},
             'secondary': {'used_percent': 0, 'reset_description': 'on-demand $12 (no cap)'},
             'tertiary': {'used_percent': 25, 'reset_description': 'auto 25%'}},
            {'provider': 'glm', 'updated_at': self.now.isoformat(), 'primary': {'used_percent': 30, 'reset_description': 'Tokens'}},
            {'provider': 'grok', 'updated_at': self.now.isoformat(), 'primary': {'used_percent': 20, 'window_minutes': 10080}},
        ])])
        quota = self.bridge.collect_snapshot(self.home, self.now)['quota']
        self.assertEqual([(w['provider'], w['usedPercent']) for w in quota['windows']], [('cursor', 25.0), ('glm', 30.0), ('grok', 20.0)])
        self.assertEqual(quota['costs'], [])

    def test_missing_generic_helper_preserves_legacy_envelope_and_other_modules(self):
        copied = self.home / 'isolated-code/integrations.py'
        copied.parent.mkdir()
        copied.write_bytes(MODULE.read_bytes())
        spec = importlib.util.spec_from_file_location('isolated_legacy_bridge', copied)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        result = bridge.collect_snapshot(self.home, self.now)
        self.assertEqual(result['schemaVersion'], 1)
        self.assertEqual(result['quota']['status'], 'missing')
        self.assertEqual(result['recording']['status'], 'missing')
        self.assertEqual(result['peripherals']['status'], 'invalid')
        self.assertEqual(result['peripherals']['devices'], [])
        self.assertNotIn('isolated-code', json.dumps(result))

    def test_corrupt_registry_never_reads_export_repairs_state_or_leaks_failure_text(self):
        self.install_peripheral_addon()
        registry = self.paths.store / 'registry.json'
        registry.write_text('{"private":"PRIVATE-SENTINEL"}')
        before = registry.read_bytes()
        real_open = os.open
        def guarded_open(name, *args, **kwargs):
            self.assertNotIn('synthetic-battery', str(name), 'export read after registry refusal')
            return real_open(name, *args, **kwargs)
        with patch.object(os, 'open', side_effect=guarded_open):
            result = self.bridge.collect_snapshot(self.home, self.now)
        self.assertEqual(result['peripherals']['status'], 'invalid')
        self.assertEqual(result['peripherals']['addon']['errorCode'], 'state')
        self.assertEqual(result['peripherals']['devices'], [])
        self.assertEqual(result['recording']['status'], 'missing')
        self.assertEqual(result['quota']['status'], 'missing')
        self.assertNotIn('PRIVATE-SENTINEL', json.dumps(result))
        self.assertEqual(registry.read_bytes(), before)

    @unittest.skipUnless(shutil.which('dbus-run-session'), 'private D-Bus runner unavailable')
    def test_private_bus_selective_wire_and_source_change_exit(self):
        # A private bus and copied source keep this check away from user services.
        runner = r'''
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusArgument, QDBusMessage
app = QCoreApplication([])
with tempfile.TemporaryDirectory() as temporary:
    source = Path(temporary) / 'integrations.py'
    source.write_bytes(Path(sys.argv[1]).read_bytes())
    for sibling in ('addon_store.py', 'addon_io.py', 'addon_format.py'):
        source.with_name(sibling).write_bytes(Path(sys.argv[1]).with_name(sibling).read_bytes())
    env = dict(os.environ, HOME=temporary, XDG_STATE_HOME=temporary + '/state',
               XDG_DATA_HOME=temporary + '/data', XDG_CONFIG_HOME=temporary + '/config',
               XDG_CACHE_HOME=temporary + '/cache')
    service = subprocess.Popen([sys.executable, str(source), '--serve'], env=env)
    try:
        bus = QDBusConnection.sessionBus()
        deadline = time.monotonic() + 5
        while not bus.interface().isServiceRegistered('org.caiodock.Integrations').value():
            assert service.poll() is None
            assert time.monotonic() < deadline
            time.sleep(.02)
        iface = QDBusInterface('org.caiodock.Integrations', '/org/caiodock/Integrations', 'org.caiodock.Integrations1', bus)
        assert json.loads(iface.call('Snapshot').arguments()[0])['schemaVersion'] == 1
        for modules in ([], ['quota'], ['recording', 'peripherals'], ['unknown'], ['quota', 'quota']):
            argument = QDBusArgument()
            argument << modules
            message = QDBusMessage.createMethodCall('org.caiodock.Integrations', '/org/caiodock/Integrations',
                                                   'org.caiodock.Integrations1', 'SnapshotFor')
            message.setArguments([argument])
            reply = bus.call(message)
            assert reply.type() == QDBusMessage.ReplyMessage, reply.errorMessage()
            frame = json.loads(reply.arguments()[0])
            if modules in (['unknown'], ['quota', 'quota']):
                assert frame == {'schemaVersion': 2, 'error': 'invalid-modules'}, frame
            else:
                selected = [name for name in ('quota', 'peripherals', 'recording') if name in modules]
                assert frame['modules'] == selected and frame['schemaVersion'] == 2, frame
                assert set(frame) == {'schemaVersion', 'modules', *selected}, frame

        source.write_bytes(source.read_bytes() + b'\n# Simulated install update\n')
        deadline = time.monotonic() + 8
        while service.poll() is None and time.monotonic() < deadline:
            iface.call('Snapshot')
            time.sleep(.2)
        assert service.poll() == 0, 'old bridge survived installed source change'
    finally:
        if service.poll() is None:
            service.terminate()
        service.wait(timeout=5)
'''
        result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', runner, str(MODULE)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
