"""Dated history, full provenance and refusal of unsafe local persistence."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from scripts.updates_desktop_state import Store, history_key
from test_updates_desktop_process import ProcessFixture, REF, ROOT, payload
from scripts.updates_desktop import UpdatesController

class CacheFlowTests(ProcessFixture):

    def test_check_close_reopen_and_separate_channels(self):
        host = self.host('print(' + repr(json.dumps(payload())) + ')')
        host.check()
        self.wait(host)
        host.requestClose()

        def forbid(*args):
            raise AssertionError('passive open queried')
        reopened = UpdatesController(ROOT, REF, runner=forbid, storage_root=self.path)
        self.hosts.append(reopened)
        self.assertTrue(reopened.state['historical'])
        self.assertEqual(reopened.state['record']['result']['status'], 'update_available')
        self.assertTrue(reopened.state['record']['completedAt'])
        reopened.selectChannel('beta')
        self.assertEqual(reopened.state['record'], {})
        reopened.requestClose()
        again = UpdatesController(ROOT, REF, runner=forbid, storage_root=self.path)
        self.hosts.append(again)
        self.assertEqual(again.channel, 'beta')
        again.selectChannel('stable')
        self.assertEqual(again.state['record']['result']['available_version'], '2.0.0')
        changed = dict(REF, digest='b' * 64)
        different = UpdatesController(ROOT, changed, runner=forbid, storage_root=self.path)
        self.hosts.append(different)
        self.assertEqual(different.state['record'], {})

    def test_failure_remains_main_with_previous_success(self):
        host = self.host('print(' + repr(json.dumps(payload())) + ')')
        host.check()
        self.wait(host)
        helper = self.path / 'offline.py'
        helper.write_text('print(' + repr(json.dumps(payload('unavailable'))) + ');raise SystemExit(2)')
        host._runner = lambda *args: (__import__('sys').executable, ['-I', '-B', str(helper)])
        host.check()
        self.wait(host)
        self.assertEqual(host.state['record']['result']['status'], 'unavailable')
        self.assertEqual(host.state['lastCompleted']['result']['status'], 'update_available')
        reopened = UpdatesController(ROOT, REF, storage_root=self.path)
        self.hosts.append(reopened)
        self.assertEqual(reopened.state['record']['result']['status'], 'unavailable')

    def test_cache_symlink_failure_is_nonfatal_and_not_overwritten(self):
        store = Store(self.path)
        store.cache.parent.mkdir(parents=True)
        target = self.path / 'untouched'
        target.write_text('foreign')
        store.cache.symlink_to(target)
        host = self.host('print(' + repr(json.dumps(payload())) + ')')
        host.check()
        self.wait(host)
        self.assertEqual(host.state['record']['result']['status'], 'update_available')
        self.assertTrue(host.state['storageWarning'])
        self.assertEqual(target.read_text(), 'foreign')

class SafeStoreTests(unittest.TestCase):

    def test_passive_no_writes_and_atomic_bounded_strict_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory))
            self.assertEqual(store.load(), ({}, 'stable', ''))
            self.assertEqual(list(Path(directory).iterdir()), [])
            store.save_preference('beta')
            self.assertEqual(Store(Path(directory)).load()[1], 'beta')
            self.assertEqual(store.preferences.stat().st_mode & 511, 384)
            store.preferences.write_text('{"schema":"x","schema":"y"}')
            _, channel, warning = Store(Path(directory)).load()
            self.assertEqual(channel, 'stable')
            self.assertTrue(warning)

    def test_future_cache_is_historical_and_bad_time_order_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root);data=payload();data['checked_at']='2099-01-01T12:00:00Z'
            record=dict(attemptedAt=data['checked_at'],completedAt='2099-01-01T12:00:01Z',result=data)
            channels={'stable':dict(key=history_key(REF,'stable'),attempt=record,lastCompleted=record)}
            store.save_history(channels)
            host=UpdatesController(ROOT,REF,storage_root=root)
            self.assertTrue(host.state['historical']);self.assertTrue(host.state['timeUnreliable'])
            record['completedAt']='2001-01-01T00:00:00Z'
            self.assertRaises(ValueError,store.save_history,channels)

    def test_unsafe_parents_and_fifo_never_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root)
            store.cache.parent.mkdir(parents=True)
            store.cache.parent.chmod(511)
            self.assertRaises((OSError, ValueError), store.save_history, {})
            store.cache.parent.chmod(448)
            os.mkfifo(store.cache)
            self.assertTrue(store.load()[2])

    def test_provenance_key_contains_every_authority_field(self):
        base = history_key(REF, 'stable')
        for field, value in [('role', 'bundle'), ('origin', 'verified-manifest'), ('component', 'workspace'), ('version', '1.2.4'), ('commit', 'c' * 40), ('digest', 'b' * 64)]:
            self.assertNotEqual(base, history_key(dict(REF, **{field: value}), 'stable'))
        self.assertNotEqual(base, history_key(REF, 'beta'))

    def test_concurrent_writers_leave_one_complete_private_document(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda channel: Store(root).save_preference(channel), ['stable', 'beta'] * 5))
            _, channel, warning = Store(root).load()
            self.assertIn(channel, ('stable', 'beta'))
            self.assertEqual(warning, '')
            self.assertEqual(list(Store(root).preferences.parent.glob('.updates-*')), [])

    def test_relative_and_empty_xdg_fall_back_to_absolute_private_home(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'HOME': directory, 'XDG_CONFIG_HOME': 'relative', 'XDG_CACHE_HOME': ''}):
                store = Store()
                self.assertEqual(store.preferences, Path(directory) / '.config/orla/updates.json')
                self.assertEqual(store.cache, Path(directory) / '.cache/orla/updates-desktop.json')
