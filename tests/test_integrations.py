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
        env = dict(os.environ, HOME=str(self.home))
        result = subprocess.run([sys.executable, '-S', str(MODULE), '--snapshot'], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['schemaVersion'], 1)
        self.assertEqual(value['quota']['status'], 'missing')

    def test_peripherals_hide_identifiers_and_neutralize_old_readings(self):
        self.write_state('perigauge/state.json', {'schema': 1, 'generated_at': self.now.timestamp(), 'devices': [
            {'id': 'private-device-id', 'name': 'Mouse', 'kind': 'mouse', 'present': True, 'updated_at': self.now.timestamp(), 'battery': {'percent': 0, 'charging': 'discharging', 'estimated': True}},
            {'name': 'Old', 'kind': 'earbuds', 'present': True, 'updated_at': self.now.timestamp() - 901, 'battery': {'percent': 80}, 'components': [{'id': 'left', 'percent': 90}]},
            {'name': 'Hidden', 'kind': 'keyboard', 'hidden': True, 'battery': {'percent': 99}},
        ]})
        result = self.bridge.collect_snapshot(self.home, self.now)['peripherals']
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(len(result['devices']), 2)
        self.assertEqual(result['devices'][0]['percent'], 0)
        self.assertTrue(result['devices'][0]['estimated'])
        self.assertIsNone(result['devices'][1]['percent'])
        self.assertIsNone(result['devices'][1]['components'][0]['percent'])
        self.assertNotIn('private-device-id', json.dumps(result))

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
        self.assertEqual(result['peripherals'], {'status': 'invalid', 'devices': []})
        self.assertEqual(result['recording']['status'], 'invalid')
        self.assertEqual(result['recording']['state'], 'unknown')

    def test_runtime_honors_absolute_xdg_state_home_without_reading_legacy_config(self):
        root = self.home / 'alternate-state'
        path = root / 'perigauge/state.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'schema': 1, 'generated_at': self.now.timestamp(), 'devices': []}))
        legacy = self.home / '.config/recording-cli/state.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"state":"recording"}')
        with patch.dict(os.environ, {'HOME': str(self.home), 'XDG_STATE_HOME': str(root)}):
            result = self.bridge.collect_snapshot(now=self.now)
        self.assertEqual(result['peripherals']['status'], 'unknown')
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

    @unittest.skipUnless(shutil.which('dbus-run-session'), 'private D-Bus runner unavailable')
    def test_service_exits_when_installed_source_changes_despite_regular_requests(self):
        # A private bus and copied source keep this check away from user services.
        runner = r'''
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtDBus import QDBusConnection, QDBusInterface
app = QCoreApplication([])
with tempfile.TemporaryDirectory() as temporary:
    source = Path(temporary) / 'integrations.py'
    source.write_bytes(Path(sys.argv[1]).read_bytes())
    env = dict(os.environ, HOME=temporary, XDG_STATE_HOME=temporary + '/state')
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
