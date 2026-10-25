"""Filesystem lifecycle tests with private synthetic HOME/XDG only."""
import hashlib
import json
import os
import stat
import fcntl
from unittest import mock
from pathlib import Path
import tempfile
import subprocess
import sys
import threading
import unittest

from test_addons import ROOT, load, manifest, export


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='addon-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir(mode=0o700)
        self.data = self.root / 'data'
        self.state = self.root / 'state'
        self.s = load('addon_store')
        self.paths = self.s.AddonPaths(home=self.home, data_home=self.data, state_home=self.state)

    def package(self, version='1.0.0', addon_id='org.example.battery'):
        m = manifest()
        m.update(version=version, id=addon_id)
        raw = json.dumps(m, indent=2).encode()  # Raw bytes, deliberately noncanonical.
        p = self.root / ('package-' + addon_id + '-' + version + '.json')
        p.write_bytes(raw)
        p.chmod(0o600)
        return p, hashlib.sha256(raw).hexdigest()

    def install(self, version='1.0.0', addon_id='org.example.battery'):
        p, digest = self.package(version, addon_id)
        return self.s.install_addon(paths=self.paths, file=p, expected_sha256=digest), digest

    def test_inspect_install_and_list_preserve_raw_hash_without_activation(self):
        p, digest = self.package()
        preview = self.s.inspect_addon(file=p)
        self.assertEqual(preview['sha256'], digest)
        self.assertEqual(preview['manifest']['id'], 'org.example.battery')
        before = self.s.list_addons(paths=self.paths)
        self.assertEqual(before, dict(generation=None, addons=[]))
        self.assertFalse(self.data.exists())
        installed = self.s.install_addon(paths=self.paths, file=p, expected_sha256=digest)
        listed = self.s.list_addons(paths=self.paths)
        self.assertEqual(installed, listed)
        self.assertFalse(listed['addons'][0]['enabled'])
        self.assertEqual(listed['addons'][0]['sha256'], digest)
        self.assertIsNone(listed['addons'][0]['previousSha256'])
        self.assertEqual((self.data / 'orla-desktop/addons/objects' / (digest + '.json')).read_bytes(),
                         p.read_bytes())
        self.assertEqual(self.s.list_addons(paths=self.paths)['generation'], installed['generation'])

    def operation(self, name, digest, addon_id='org.example.battery'):
        return getattr(self.s, name + '_addon')(paths=self.paths, addon_id=addon_id,
                                               expected_current_sha256=digest)

    def test_existing_shared_orla_data_folder_hosts_the_private_store(self):
        # Installed Orla features create this folder first, with the usual 0755 mode.
        shared = self.data / 'orla-desktop'
        shared.mkdir(parents=True)
        shared.chmod(0o755)
        installed, digest = self.install()
        self.assertEqual(self.s.list_addons(paths=self.paths), installed)
        self.operation('enable', digest)
        self.assertTrue(self.s.list_addons(paths=self.paths)['addons'][0]['enabled'])
        self.assertEqual(stat.S_IMODE((shared / 'addons').stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(shared.stat().st_mode), 0o755)
        # A parent that other accounts can write could swap the store, so it stays refused.
        for mode in (0o775, 0o757):
            shared.chmod(mode)
            with self.subTest(mode=oct(mode)), self.assertRaises(self.s.AddonError) as error:
                self.s.list_addons(paths=self.paths)
            self.assertEqual(error.exception.code, 'unsafe')
        shared.chmod(0o755)

    def test_update_and_rollback_require_fresh_hash_bound_activation(self):
        _, first = self.install()
        active = self.operation('enable', first)
        self.assertTrue(active['addons'][0]['enabled'])
        _, second = self.install('2.0.0')
        current = self.s.list_addons(paths=self.paths)
        self.assertFalse(current['addons'][0]['enabled'])
        self.assertEqual(current['addons'][0]['previousSha256'], first)
        with self.assertRaises(self.s.AddonError) as error:
            self.operation('enable', first)
        self.assertEqual(error.exception.code, 'hash')
        self.operation('enable', second)
        rolled = self.operation('rollback', second)
        self.assertEqual(rolled['addons'][0]['sha256'], first)
        self.assertFalse(rolled['addons'][0]['enabled'])
        self.assertEqual(rolled['addons'][0]['previousSha256'], second)
        # An external expected digest may explicitly reuse an already-known artifact.
        p, _ = self.package()
        reused = self.s.install_addon(paths=self.paths, file=p, expected_sha256=first)
        self.assertFalse(reused['addons'][0]['enabled'])

    def test_only_one_renderer_is_enabled_and_remove_preserves_preferences(self):
        preferences = self.home / 'profile-preferences.json'
        preferences.write_bytes(b'{"peripheralVisible":true,"unrelated":"keep"}\n')
        _, first = self.install()
        self.operation('enable', first)
        _, second = self.install(addon_id='org.example.second')
        result = self.operation('enable', second, 'org.example.second')
        self.assertEqual([a['manifest']['id'] for a in result['addons'] if a['enabled']],
                         ['org.example.second'])
        removed = self.operation('remove', second, 'org.example.second')
        self.assertEqual(len(removed['addons']), 1)
        self.assertEqual(preferences.read_bytes(),
                         b'{"peripheralVisible":true,"unrelated":"keep"}\n')
        self.assertTrue((self.data / 'orla-desktop/addons/objects' / (second + '.json')).is_file())
        with self.assertRaises(self.s.AddonError):
            self.operation('enable', second, 'org.example.second')
        self.operation('disable', first)
        self.assertFalse(self.s.list_addons(paths=self.paths)['addons'][0]['enabled'])

    def test_preview_hash_drift_never_installs_changed_input(self):
        p, first = self.package()
        m = manifest()
        m['name'] = 'changed after approval'
        p.write_bytes(json.dumps(m).encode())
        with self.assertRaises(self.s.AddonError) as error:
            self.s.install_addon(paths=self.paths, file=p, expected_sha256=first)
        self.assertEqual(error.exception.code, 'hash')
        self.assertFalse(self.data.exists())

    def test_unsafe_inputs_and_parent_links_are_rejected_without_installing(self):
        p, digest = self.package()
        link = self.root / 'link'
        link.symlink_to(p)
        fifo = self.root / 'pipe'
        os.mkfifo(fifo, 0o600)
        hard = self.root / 'hard'
        os.link(p, hard)
        for candidate in (link, fifo, hard, p, self.root):
            with self.subTest(kind=candidate.name), self.assertRaises(self.s.AddonError):
                self.s.inspect_addon(file=candidate)
        hard.unlink()
        parent = self.root / 'parent-link'
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(self.s.AddonError):
            self.s.inspect_addon(file=parent / p.name)
        p.chmod(0o666)
        with self.assertRaises(self.s.AddonError):
            self.s.inspect_addon(file=p)
        self.assertFalse(self.data.exists())

    def test_parent_renamed_during_read_does_not_publish_detached_input(self):
        folder = self.root / 'input'
        folder.mkdir(mode=0o700)
        p, digest = self.package()
        chosen = folder / 'package.json'
        p.rename(chosen)
        real_read = os.read
        changed = False
        def read_then_move(fd, count):
            nonlocal changed
            data = real_read(fd, count)
            if not changed:
                changed = True
                folder.rename(self.root / 'detached')
                folder.mkdir(mode=0o700)
            return data
        with mock.patch.object(os, 'read', side_effect=read_then_move):
            with self.assertRaises(self.s.AddonError) as error:
                self.s.inspect_addon(file=chosen)
        self.assertEqual(error.exception.code, 'drift')

    def test_corrupt_or_unknown_store_is_not_adopted_even_with_external_hash(self):
        _, digest = self.install()
        store = self.data / 'orla-desktop/addons'
        blob = store / 'objects' / (digest + '.json')
        approved = blob.read_bytes()
        blob.write_bytes(approved.replace(b'Synthetic batteries', b'Altered batteries!!'))
        p, _ = self.package()
        for action in (lambda: self.s.list_addons(paths=self.paths),
                       lambda: self.s.install_addon(paths=self.paths, file=p,
                                                   expected_sha256=digest),
                       lambda: self.operation('enable', digest)):
            with self.assertRaises(self.s.AddonError):
                action()
        blob.write_bytes(approved)
        unknown = store / 'objects' / ('0' * 64 + '.json')
        unknown.write_bytes(approved)
        unknown.chmod(0o600)
        with self.assertRaises(self.s.AddonError):
            self.s.install_addon(paths=self.paths, file=p, expected_sha256=digest)
        unknown.unlink()
        registry = store / 'registry.json'
        good = registry.read_bytes()
        registry.write_bytes(b'{"enabled":true}')
        with self.assertRaises(self.s.AddonError):
            self.s.list_addons(paths=self.paths)
        self.assertEqual(registry.read_bytes(), b'{"enabled":true}')
        registry.write_bytes(good)
        blob.unlink()
        blob.symlink_to(p)
        with self.assertRaises(self.s.AddonError):
            self.s.list_addons(paths=self.paths)

    def test_lock_is_bounded_and_shared_readers_do_not_exclude_each_other(self):
        _, digest = self.install()
        lock = self.data / 'orla-desktop/addons/.lock'
        with lock.open('rb') as held:
            fcntl.flock(held.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            self.assertEqual(len(self.s.list_addons(paths=self.paths)['addons']), 1)
            with self.assertRaises(self.s.AddonError) as error:
                self.operation('enable', digest)
            self.assertEqual(error.exception.code, 'busy')
            fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(self.s.AddonError) as error:
                self.s.list_addons(paths=self.paths)
            self.assertEqual(error.exception.code, 'busy')

    def test_registry_publication_failure_reports_committed_state(self):
        _, digest = self.install()
        real_fsync = os.fsync
        replaced = False
        real_replace = os.replace
        def replace(*args, **kwargs):
            nonlocal replaced
            real_replace(*args, **kwargs)
            replaced = True
        def fsync(fd):
            if replaced:
                raise OSError('private OS path must never leak')
            real_fsync(fd)
        with mock.patch.object(os, 'replace', side_effect=replace), mock.patch.object(
                os, 'fsync', side_effect=fsync):
            with self.assertRaises(self.s.AddonError) as error:
                self.operation('enable', digest)
        self.assertTrue(error.exception.committed)
        self.assertRegex(error.exception.generation, r'^[0-9a-f]{32}$')
        self.assertNotIn('private', str(error.exception))
        self.assertTrue(self.s.list_addons(paths=self.paths)['addons'][0]['enabled'])

    def publish(self, value=None):
        value = export() if value is None else value
        folder = self.state / 'synthetic-battery/exports'
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        folder.parent.chmod(0o700)
        path = folder / 'orla-peripherals-v1.json'
        path.write_bytes(json.dumps(value).encode())
        path.chmod(0o600)
        return path

    def snapshot(self, now=100000, visible=True):
        return self.s.snapshot_peripherals(paths=self.paths, now_ms=now, profile_enabled=visible)

    def test_off_and_list_never_open_producer_directories_or_exports(self):
        real_open = os.open
        def guard(path, *args, **kwargs):
            value = os.fspath(path)
            if 'synthetic-battery' in value or 'orla-peripherals-v1.json' in value:
                self.fail('producer IO while disabled/listing')
            return real_open(path, *args, **kwargs)
        with mock.patch.object(os, 'open', side_effect=guard):
            self.assertEqual(self.snapshot()['addon']['reason'], 'not_installed')
            _, digest = self.install()
            self.assertEqual(self.snapshot()['addon']['reason'], 'disabled')
            self.s.list_addons(paths=self.paths)
            self.operation('enable', digest)
            self.s.list_addons(paths=self.paths)
            self.assertEqual(self.snapshot(visible=False)['addon']['reason'], 'profile_hidden')
            self.operation('disable', digest)
            self.assertEqual(self.snapshot()['devices'], [])

    def test_projection_preserves_zero_and_coarse_without_identity_leaks(self):
        _, digest = self.install()
        self.operation('enable', digest)
        e = export()
        coarse = json.loads(json.dumps(e['devices'][0]))
        coarse['battery'].update(percent=None, level='low', estimated=True, charging='charging')
        e['devices'].append(coarse)
        case_only = json.loads(json.dumps(coarse))
        case_only.update(kind='earbuds', components=[dict(label='case', percent=42, charging='full')])
        case_only['battery'].update(level=None, charging='unknown', estimated=False)
        e['devices'].append(case_only)
        self.publish(e)
        result = self.snapshot(now=101000)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['generatedAt'], 100.0)
        self.assertEqual(result['generatedAtMs'], 100000)
        self.assertEqual(result['expiresAtMs'], 130000)
        self.assertEqual(result['leaseMs'], 30000)
        self.assertEqual(result['devices'][0]['percent'], 0)
        self.assertEqual(result['devices'][0]['observedAt'], 100.0)
        self.assertEqual(result['devices'][0]['observedAtMs'], 100000)
        self.assertEqual(result['devices'][0]['name'], 'mouse 1')
        self.assertEqual(result['devices'][1]['name'], 'mouse 2')
        self.assertIsNone(result['devices'][1]['percent'])
        self.assertEqual(result['devices'][1]['level'], 'low')
        self.assertTrue(result['devices'][1]['estimated'])
        self.assertIsNone(result['devices'][2]['percent'])
        self.assertEqual(result['devices'][2]['components'][0]['percent'], 42)
        self.assertNotIn('PeriGauge', json.dumps(result))
        e['devices'][0]['hardwareId'] = 'private-sentinel'
        self.publish(e)
        bad = self.snapshot()
        self.assertEqual(bad['status'], 'invalid')
        self.assertNotIn('private-sentinel', json.dumps(bad))
        self.assertEqual(bad['devices'], [])

    def test_shared_names_are_bounded_and_ordinals_count_connected_devices_only(self):
        _, digest = self.install()
        self.operation('enable', digest)
        e = export()
        away = json.loads(json.dumps(e['devices'][0]))
        away['present'] = False
        e['devices'].insert(0, away)
        named = json.loads(json.dumps(e['devices'][1]))
        named['name'] = 'Mouse de teste'
        e['devices'].append(named)
        self.publish(e)
        result = self.snapshot()
        self.assertEqual([d['name'] for d in result['devices']], ['mouse 1', 'mouse 2'])
        self.assertNotIn('displayName', result['devices'][0])
        self.assertEqual(result['devices'][1]['displayName'], 'Mouse de teste')
        for bad in ('', ' Mouse', 'Mouse ', 'Mouse\n', 'M' * 65, 7, None):
            with self.subTest(name=bad):
                e = export()
                e['devices'][0]['name'] = bad
                self.publish(e)
                result = self.snapshot()
                self.assertEqual(result['status'], 'invalid')
                self.assertEqual(result['devices'], [])

    def test_expiry_rollback_clock_and_absent_observations_are_unavailable(self):
        _, digest = self.install()
        self.operation('enable', digest)
        self.publish()
        self.assertEqual(self.snapshot(129999)['devices'][0]['percent'], 0)
        expired = self.snapshot(130000)
        self.assertEqual(expired['status'], 'stale')
        self.assertEqual(expired['addon']['reason'], 'expired')
        self.assertEqual(expired['devices'], [])
        self.assertEqual(self.snapshot(99999)['addon']['reason'], 'future')
        # Disconnected devices are left out of the projection (user request, as in PeriGauge's widget).
        e = export()
        e['devices'][0].update(present=False)
        self.publish(e)
        self.assertEqual(self.snapshot()['devices'], [])
        self.assertEqual(self.snapshot()['status'], 'unknown')
        for change in (dict(stale=True), dict(observedAtMs=None),
                       dict(observedAtMs=100001), dict(observedAtMs=70000)):
            e = export()
            e['devices'][0].update(change)
            self.publish(e)
            result = self.snapshot()
            self.assertIsNone(result['devices'][0]['percent'])
            self.assertEqual(result['devices'][0]['charging'], 'unknown')
            self.assertTrue(result['devices'][0]['stale'])
        path = self.publish()
        path.unlink()
        self.assertEqual(self.snapshot()['addon']['reason'], 'export_missing')

    def test_concurrent_revoke_or_registry_drift_never_publishes_stale_generation(self):
        _, digest = self.install()
        self.operation('enable', digest)
        self.publish()
        real_read = os.read
        triggered = False
        registry = self.data / 'orla-desktop/addons/registry.json'
        def read_then_revoke(fd, count):
            nonlocal triggered
            data = real_read(fd, count)
            if b'generatedAtMs' in data and not triggered:
                triggered = True
                # Cooperative revocation cannot overtake an active shared reader.
                with self.assertRaises(self.s.AddonError) as busy:
                    self.operation('disable', digest)
                self.assertEqual(busy.exception.code, 'busy')
                # An external uncooperative registry rewrite invalidates this result.
                r = json.loads(registry.read_bytes())
                r['generation'] = 'f' * 32
                r['entries'][0]['enabled'] = False
                registry.write_bytes(json.dumps(r).encode())
            return data
        with mock.patch.object(os, 'read', side_effect=read_then_revoke):
            with self.assertRaises(self.s.AddonError) as error:
                self.snapshot()
        self.assertEqual(error.exception.code, 'drift')
        self.assertEqual(self.snapshot()['addon']['reason'], 'disabled')

    def cli(self, *args):
        env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.data),
                   XDG_STATE_HOME=str(self.state), DBUS_SESSION_BUS_ADDRESS='',
                   DBUS_SYSTEM_BUS_ADDRESS='', PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/addons.py'), *args],
                              env=env, capture_output=True, timeout=10)

    def test_cli_previews_file_uri_and_installs_only_the_approved_raw_bytes(self):
        p, digest = self.package()
        inspected = self.cli('inspect', p.as_uri())
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)['result']['sha256'], digest)
        packed = self.cli('pack', str(p), '--output', str(self.root / 'packed'))
        self.assertEqual(packed.returncode, 0, packed.stderr)
        artifact = json.loads(packed.stdout)['result']
        self.assertNotEqual(artifact['sha256'], digest)
        self.assertTrue(Path(artifact['file']).read_bytes().endswith(b'\n'))
        installed = self.cli('install', str(p), '--expected-sha256', digest)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertFalse(json.loads(installed.stdout)['result']['addons'][0]['enabled'])
        activated = self.cli('enable', 'org.example.battery', '--expected-current-sha256', digest)
        self.assertEqual(activated.returncode, 0, activated.stderr)
        snap = self.cli('snapshot', '--now-ms', '100000')
        self.assertEqual(json.loads(snap.stdout)['result']['addon']['reason'], 'export_missing')
        for chosen in ('https://example.invalid/p', 'file://remote/private-sentinel',
                       'file:///private-sentinel?query', str(self.root / 'private-sentinel')):
            failure = self.cli('inspect', chosen)
            self.assertEqual(failure.returncode, 1)
            error = json.loads(failure.stdout)
            self.assertFalse(error['ok'])
            self.assertNotIn('private-sentinel', failure.stdout.decode())
            self.assertEqual(failure.stderr, b'')

    def test_capacity_refuses_before_artifact_publication(self):
        _, digest = self.install()
        store = self.data / 'orla-desktop/addons'
        registry = store / 'registry.json'
        r = json.loads(registry.read_bytes())
        for n in range(1, 128):
            m = manifest()
            m['version'] = str(n + 1) + '.0.0'
            raw = json.dumps(m).encode()
            d = hashlib.sha256(raw).hexdigest()
            p = store / 'objects' / (d + '.json')
            p.write_bytes(raw)
            p.chmod(0o600)
            r['artifacts'].append(d)
        registry.write_bytes(json.dumps(r).encode())
        before = registry.read_bytes()
        p, new = self.package('500.0.0')
        with self.assertRaises(self.s.AddonError) as error:
            self.s.install_addon(paths=self.paths, file=p, expected_sha256=new)
        self.assertEqual(error.exception.code, 'limit')
        self.assertFalse((store / 'objects' / (new + '.json')).exists())
        self.assertEqual(registry.read_bytes(), before)
        self.assertEqual(len(list((store / 'objects').iterdir())), 128)

    def test_post_commit_revalidation_failure_is_reported_as_committed(self):
        _, digest = self.install()
        real_replace = os.replace
        registry = self.data / 'orla-desktop/addons/registry.json'
        def replace_then_drift(*args, **kwargs):
            real_replace(*args, **kwargs)
            registry.chmod(0o644)
        with mock.patch.object(os, 'replace', side_effect=replace_then_drift):
            with self.assertRaises(self.s.AddonError) as error:
                self.operation('enable', digest)
        self.assertTrue(error.exception.committed)

    def test_failure_reopening_committed_registry_reports_its_generation(self):
        _, digest = self.install()
        real_replace, real_open = os.replace, os.open
        replaced = False
        def replace(*args, **kwargs):
            nonlocal replaced
            real_replace(*args, **kwargs)
            replaced = True
        def opening(path, *args, **kwargs):
            if replaced and path == 'registry.json':
                raise OSError('injected private detail')
            return real_open(path, *args, **kwargs)
        with mock.patch.object(os, 'replace', side_effect=replace), mock.patch.object(
                os, 'open', side_effect=opening):
            with self.assertRaises(self.s.AddonError) as error:
                self.operation('enable', digest)
        self.assertTrue(error.exception.committed)
        self.assertRegex(error.exception.generation, r'^[0-9a-f]{32}$')

    def test_all_mutations_reject_stale_expected_current_hash(self):
        _, first = self.install()
        _, second = self.install('2.0.0')
        before = self.s.list_addons(paths=self.paths)
        for action in ('enable', 'disable', 'remove', 'rollback'):
            with self.subTest(action=action), self.assertRaises(self.s.AddonError) as error:
                self.operation(action, first)
            self.assertEqual(error.exception.code, 'hash')
            self.assertEqual(self.s.list_addons(paths=self.paths), before)
        self.operation('enable', second)
        p, _ = self.package('2.0.0')
        result = self.s.install_addon(paths=self.paths, file=p, expected_sha256=second)
        self.assertFalse(result['addons'][0]['enabled'])

    def test_real_reader_writer_overlap_and_already_sent_generation_gate(self):
        _, digest = self.install()
        enabled = self.operation('enable', digest)
        self.publish()
        reading, release = threading.Event(), threading.Event()
        outcomes = []
        real_read = os.read
        def reading_export(fd, count):
            data = real_read(fd, count)
            if b'generatedAtMs' in data:
                reading.set()
                if not release.wait(3):
                    raise AssertionError('writer did not release reader')
            return data
        def reader():
            try:
                outcomes.append(self.snapshot())
            except BaseException as error:
                outcomes.append(error)
        with mock.patch.object(os, 'read', side_effect=reading_export):
            worker = threading.Thread(target=reader)
            worker.start()
            try:
                self.assertTrue(reading.wait(3))
                with self.assertRaises(self.s.AddonError) as busy:
                    self.operation('disable', digest)
                self.assertEqual(busy.exception.code, 'busy')
            finally:
                release.set()
                worker.join(3)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], dict)
        disabled = self.operation('disable', digest)
        # A UI receiving the earlier response after disable must compare generations.
        self.assertEqual(outcomes[0]['addon']['generation'], enabled['generation'])
        self.assertNotEqual(outcomes[0]['addon']['generation'], disabled['generation'])
        self.assertEqual(self.snapshot()['devices'], [])

    def test_removed_export_or_renamed_store_during_read_never_leaks_readings(self):
        _, digest = self.install()
        self.operation('enable', digest)
        exported = self.publish()
        real_read = os.read
        changed = False
        def read_then_unlink(fd, count):
            nonlocal changed
            data = real_read(fd, count)
            if b'generatedAtMs' in data and not changed:
                changed = True
                exported.unlink()
            return data
        with mock.patch.object(os, 'read', side_effect=read_then_unlink):
            result = self.snapshot()
        self.assertEqual(result['devices'], [])
        self.assertEqual(result['status'], 'invalid')
        self.publish()
        changed = False
        store = self.data / 'orla-desktop/addons'
        def read_then_rename(fd, count):
            nonlocal changed
            data = real_read(fd, count)
            if b'generatedAtMs' in data and not changed:
                changed = True
                store.rename(store.with_name('detached'))
                store.mkdir(mode=0o700)
            return data
        with mock.patch.object(os, 'read', side_effect=read_then_rename):
            with self.assertRaises(self.s.AddonError) as error:
                self.snapshot()
        self.assertEqual(error.exception.code, 'drift')

    def test_package_count_limit_and_no_previous_are_causal_refusals(self):
        _, digest = self.install()
        with self.assertRaises(self.s.AddonError) as error:
            self.operation('rollback', digest)
        self.assertEqual(error.exception.code, 'no_previous')
        store = self.data / 'orla-desktop/addons'
        registry = store / 'registry.json'
        r = json.loads(registry.read_bytes())
        for n in range(31):
            m = manifest()
            m['id'] = 'org.example.id' + str(n)
            raw = json.dumps(m).encode()
            d = hashlib.sha256(raw).hexdigest()
            p = store / 'objects' / (d + '.json')
            p.write_bytes(raw)
            p.chmod(0o600)
            r['artifacts'].append(d)
            r['entries'].append(dict(id=m['id'], sha256=d, previousSha256=None, enabled=False))
        registry.write_bytes(json.dumps(r).encode())
        before = registry.read_bytes()
        p, new = self.package(addon_id='org.example.limit')
        with self.assertRaises(self.s.AddonError) as error:
            self.s.install_addon(paths=self.paths, file=p, expected_sha256=new)
        self.assertEqual(error.exception.code, 'limit')
        self.assertEqual(registry.read_bytes(), before)
        self.assertFalse((store / 'objects' / (new + '.json')).exists())

    def test_sibling_imports_ignore_cwd_and_package_namespace_poisoning(self):
        poison = self.root / 'poison'
        poison.mkdir(mode=0o700)
        for name in ('addon_format', 'addon_io', 'addon_store', 'package'):
            (poison / (name + '.py')).write_text('raise RuntimeError("poisoned import")\n')
        p, _ = self.package()
        env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.data),
                   XDG_STATE_HOME=str(self.state), PYTHONPATH=str(poison),
                   DBUS_SESSION_BUS_ADDRESS='', DBUS_SYSTEM_BUS_ADDRESS='')
        process = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/addons.py'),
                                  'inspect', str(p)], cwd=poison, env=env,
                                 capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_public_paths_and_file_uri_reject_nonlocal_ambiguous_forms(self):
        p, _ = self.package()
        for home in (True, b'private-sentinel', object()):
            with self.subTest(type=type(home).__name__), self.assertRaises(self.s.AddonError):
                self.s.AddonPaths(home=home)
        for chosen in ('file:' + str(p), 'file://' + str(p),
                       p.as_uri() + '#fragment', p.as_uri() + '?query',
                       p.as_uri().replace('package-', '%xxpackage-')):
            # file:// + absolute path is the supported three-slash spelling.
            if chosen == p.as_uri():
                continue
            with self.subTest(uri=chosen), self.assertRaises(self.s.AddonError):
                self.s.inspect_addon(file=chosen)
        fallbacks = self.s.AddonPaths(home=self.home, data_home='relative', state_home='relative')
        self.assertEqual(fallbacks.data_home, self.home / '.local/share')
        self.assertEqual(fallbacks.state_home, self.home / '.local/state')

    def test_nonempty_lock_is_unknown_state_and_not_adopted(self):
        _, digest = self.install()
        lock = self.data / 'orla-desktop/addons/.lock'
        lock.write_bytes(b'unknown-lock-contents')
        with self.assertRaises(self.s.AddonError):
            self.s.list_addons(paths=self.paths)

    def test_registry_replace_failure_leaves_no_new_consent_and_orphan_is_not_adopted(self):
        _, first = self.install()
        self.operation('enable', first)
        store = self.data / 'orla-desktop/addons'
        registry = store / 'registry.json'
        before = registry.read_bytes()
        p, second = self.package('2.0.0')
        with mock.patch.object(os, 'replace', side_effect=OSError('private failure detail')):
            with self.assertRaises(self.s.AddonError) as error:
                self.s.install_addon(paths=self.paths, file=p, expected_sha256=second)
        self.assertFalse(error.exception.committed)
        self.assertEqual(registry.read_bytes(), before)
        self.assertTrue((store / 'objects' / (second + '.json')).exists())
        with self.assertRaises(self.s.AddonError):
            self.snapshot()
        # An unreferenced, uncatalogued orphan remains unknown, even if bytes match.
        with self.assertRaises(self.s.AddonError):
            self.s.install_addon(paths=self.paths, file=p, expected_sha256=second)

    def test_pack_is_exclusive_and_cli_usage_errors_are_finite(self):
        p, _ = self.package()
        output = self.root / 'packed'
        first = self.s.pack_addon(file=p, output_dir=output)
        approved = Path(first['file']).read_bytes()
        with self.assertRaises(self.s.AddonError) as error:
            self.s.pack_addon(file=p, output_dir=output)
        self.assertEqual(error.exception.code, 'exists')
        self.assertEqual(Path(first['file']).read_bytes(), approved)
        result = self.cli('snapshot', '--now-ms', 'private-sentinel')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['error']['code'], 'format')
        self.assertNotIn(b'private-sentinel', result.stdout + result.stderr)

    def test_case_only_components_do_not_confirm_an_earbud_aggregate(self):
        _, digest = self.install()
        self.operation('enable', digest)
        e = export()
        e['devices'][0].update(kind='earbuds', components=[dict(label='case', percent=45,
                                                              charging='charging')])
        e['devices'][0]['battery'].update(percent=99, level='full', estimated=True,
                                          charging='full')
        self.publish(e)
        result = self.snapshot()
        device = result['devices'][0]
        self.assertIsNone(device['percent'])
        self.assertIsNone(device['level'])
        self.assertEqual(device['charging'], 'unknown')
        self.assertFalse(device['estimated'])
        self.assertEqual(device['components'][0]['percent'], 45)
        self.assertEqual(device['components'][0]['charging'], 'charging')
        self.assertEqual(result['status'], 'ready')
        e['devices'][0]['components'].append(dict(label='left', percent=None, charging='unknown'))
        self.publish(e)
        self.assertIsNone(self.snapshot()['devices'][0]['percent'])


if __name__ == '__main__':
    unittest.main()
