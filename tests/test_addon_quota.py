"""Quota-usage addon host: format, per-module activation and projection. Synthetic only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_addons import ROOT, load, manifest, export

GENERATED = 100000


def quota_manifest(addon_id='org.example.quota', version='1.0.0'):
    m = manifest()
    m.update(id=addon_id, version=version, name='Synthetic quota', renderer='quota-usage',
             source=dict(namespace='synthetic-quota', formatVersion='0.1-experimental'))
    return m


def quota_export(**changes):
    value = dict(formatVersion='0.1-experimental', producer='synthetic-quota', producerVersion='0.1.0',
        generatedAtMs=GENERATED, expiresAtMs=GENERATED + 30000, intervalSeconds=10, providers=[
            dict(id='codex', state='ready', observedAtMs=GENERATED, windows=[
                dict(key='primary', usedPercent=0, windowMinutes=300, resetAtMs=GENERATED + 3600000),
                dict(key='secondary', usedPercent=42, windowMinutes=10080, resetAtMs=None)]),
            dict(id='claude', state='stale', observedAtMs=GENERATED - 1000, windows=[
                dict(key='primary', usedPercent=None, windowMinutes=300, resetAtMs=None)]),
            dict(id='gemini', state='unavailable', observedAtMs=None, windows=[]),
            dict(id='opencode-go', state='ready', observedAtMs=GENERATED - 500, windows=[
                dict(key='primary', usedPercent=88, windowMinutes=None, resetAtMs=None)])])
    value.update(changes)
    return value


class QuotaFormatTests(unittest.TestCase):
    def setUp(self):
        self.f = load('addon_format')

    def parse(self, value):
        return self.f.parse_quota_export(json.dumps(value).encode(), producer_namespace='synthetic-quota')

    def refused(self, value, code=None):
        with self.assertRaises(self.f.AddonError) as error:
            self.parse(value)
        if code:
            self.assertEqual(error.exception.code, code)

    def test_manifest_accepts_only_the_two_passive_renderers(self):
        self.assertEqual(self.f.parse_manifest(json.dumps(quota_manifest()).encode())['renderer'], 'quota-usage')
        self.assertEqual(self.f.parse_manifest(json.dumps(manifest()).encode())['renderer'], 'peripheral-battery')
        for renderer in ('quota', 'cost-usage', 'Quota-usage', ''):
            with self.subTest(renderer=renderer):
                m = quota_manifest()
                m['renderer'] = renderer
                with self.assertRaises(self.f.AddonError):
                    self.f.parse_manifest(json.dumps(m).encode())

    def test_valid_export_roundtrips_and_preserves_zero(self):
        value = self.parse(quota_export())
        self.assertEqual(value, quota_export())
        self.assertEqual(value['providers'][0]['windows'][0]['usedPercent'], 0)
        canonical = self.f.canonical_quota_export_bytes(quota_export(), producer_namespace='synthetic-quota')
        self.assertTrue(canonical.endswith(b'\n'))
        fixture = (ROOT / 'addons/fixtures/quota-0.1.json').read_bytes()
        parsed = self.f.parse_quota_export(fixture, producer_namespace='synthetic-quota')
        self.assertEqual(parsed['providers'][0]['windows'][0]['usedPercent'], 0)
        self.assertEqual([p['state'] for p in parsed['providers']], ['ready', 'stale', 'unavailable', 'ready'])

    def test_account_money_and_free_text_never_cross_the_boundary(self):
        for field, value in (('email', 'person@example.invalid'), ('balanceUsd', 1.5), ('error', 'login expired'),
                             ('accountId', 'abc'), ('url', 'https://example.invalid')):
            with self.subTest(field=field):
                e = quota_export()
                e['providers'][0][field] = value
                self.refused(e, 'fields')
        e = quota_export()
        e['providers'][0]['windows'][0]['resetDescription'] = 'Resets in $5'
        self.refused(e, 'fields')
        e = quota_export()
        e['costs'] = []
        self.refused(e, 'fields')

    def test_strict_values_order_and_bounds(self):
        cases = []
        for value in (101, -1, 1.5, True, '10'):
            e = quota_export()
            e['providers'][0]['windows'][0]['usedPercent'] = value
            cases.append(('percent %r' % (value,), e))
        for value in (0, 525601, 2.0):
            e = quota_export()
            e['providers'][0]['windows'][0]['windowMinutes'] = value
            cases.append(('minutes %r' % (value,), e))
        e = quota_export()
        e['providers'][0]['windows'].reverse()
        cases.append(('order', e))
        e = quota_export()
        e['providers'][0]['windows'][1]['key'] = 'primary'
        cases.append(('duplicate key', e))
        e = quota_export()
        e['providers'][0]['windows'] = [dict(key=k, usedPercent=1, windowMinutes=None, resetAtMs=None)
                                        for k in ('primary', 'secondary', 'tertiary', 'tertiary')]
        cases.append(('four windows', e))
        e = quota_export()
        e['providers'][1]['id'] = 'codex'
        cases.append(('duplicate provider', e))
        for bad in ('Codex', '-codex', 'codex-', 'x' * 33, 'co dex', ''):
            e = quota_export()
            e['providers'][0]['id'] = bad
            cases.append(('id %r' % bad, e))
        e = quota_export()
        e['providers'][0]['state'] = 'error'
        cases.append(('state', e))
        e = quota_export()
        e['providers'] = [dict(id='p%d' % i, state='unknown', observedAtMs=None, windows=[]) for i in range(33)]
        cases.append(('33 providers', e))
        cases.append(('lease', quota_export(expiresAtMs=GENERATED + 30001)))
        cases.append(('producer', quota_export(producer='other')))
        cases.append(('interval', quota_export(intervalSeconds=9, expiresAtMs=GENERATED + 27000)))
        for name, value in cases:
            with self.subTest(name=name):
                self.refused(value)

    def test_published_schemas_match_the_generators(self):
        for name, schema in (('manifest', self.f.manifest_schema()), ('quota', self.f.quota_schema())):
            published = json.loads((ROOT / 'addons/schema' / (name + '-0.1.schema.json')).read_bytes())
            self.assertEqual(schema, published)
        self.assertEqual(self.f.manifest_schema()['properties']['renderer'],
                         dict(enum=['peripheral-battery', 'quota-usage']))


class QuotaStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='addon-quota-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir(mode=0o700)
        self.data = self.root / 'data'
        self.state = self.root / 'state'
        self.s = load('addon_store')
        self.paths = self.s.AddonPaths(home=self.home, data_home=self.data, state_home=self.state)

    def install(self, value):
        raw = json.dumps(value, indent=2).encode()
        p = self.root / ('package-%s-%s.json' % (value['id'], value['version']))
        p.write_bytes(raw)
        p.chmod(0o600)
        digest = hashlib.sha256(raw).hexdigest()
        self.s.install_addon(paths=self.paths, file=p, expected_sha256=digest)
        return digest

    def change(self, action, addon_id, digest):
        return getattr(self.s, action + '_addon')(paths=self.paths, addon_id=addon_id, expected_current_sha256=digest)

    def write(self, value=None, namespace='synthetic-quota', name='orla-quota-v1.json'):
        folder = self.state / namespace / 'exports'
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        folder.parent.chmod(0o700)
        path = folder / name
        path.write_bytes(json.dumps(quota_export() if value is None else value).encode())
        path.chmod(0o600)

    def quota(self, now=GENERATED + 1000, visible=True):
        return self.s.snapshot_quota(paths=self.paths, now_ms=now, profile_enabled=visible)

    def enabled(self):
        return {a['manifest']['id']: a['enabled'] for a in self.s.list_addons(paths=self.paths)['addons']}

    def test_battery_and_quota_are_active_together_and_replace_only_their_module(self):
        battery = self.install(manifest())
        quota = self.install(quota_manifest())
        other = self.install(quota_manifest('org.example.quota-two'))
        self.change('enable', 'org.example.battery', battery)
        self.change('enable', 'org.example.quota', quota)
        self.assertEqual(self.enabled(), {'org.example.battery': True, 'org.example.quota': True,
                                          'org.example.quota-two': False})
        self.change('enable', 'org.example.quota-two', other)
        self.assertEqual(self.enabled(), {'org.example.battery': True, 'org.example.quota': False,
                                          'org.example.quota-two': True})
        self.change('disable', 'org.example.battery', battery)
        self.assertEqual(self.enabled()['org.example.quota-two'], True)

    def test_an_update_cannot_move_an_addon_to_another_module(self):
        self.install(manifest())
        moved = quota_manifest('org.example.battery', '2.0.0')
        raw = json.dumps(moved).encode()
        p = self.root / 'moved.json'
        p.write_bytes(raw)
        p.chmod(0o600)
        with self.assertRaises(self.s.AddonError) as error:
            self.s.install_addon(paths=self.paths, file=p, expected_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(error.exception.code, 'format')
        listed = self.s.list_addons(paths=self.paths)['addons']
        self.assertEqual([a['manifest']['renderer'] for a in listed], ['peripheral-battery'])

    def test_two_active_addons_of_one_module_in_the_registry_are_refused(self):
        first = self.install(quota_manifest())
        second = self.install(quota_manifest('org.example.quota-two'))
        registry_path = self.data / 'orla-desktop/addons/registry.json'
        registry = json.loads(registry_path.read_bytes())
        for entry in registry['entries']:
            entry['enabled'] = True
        registry_path.write_bytes(json.dumps(registry, sort_keys=True, separators=(',', ':')).encode() + b'\n')
        with self.assertRaises(self.s.AddonError) as error:
            self.s.list_addons(paths=self.paths)
        self.assertEqual(error.exception.code, 'state')
        self.assertTrue(first and second)

    def test_without_an_active_quota_addon_no_producer_state_is_opened(self):
        real_open = os.open
        def guard(path, *args, **kwargs):
            if 'synthetic-quota' in os.fspath(path) or 'orla-quota-v1.json' in os.fspath(path):
                self.fail('producer IO without an active quota addon')
            return real_open(path, *args, **kwargs)
        with mock.patch.object(os, 'open', side_effect=guard):
            self.assertEqual(self.quota()['addon']['reason'], 'not_installed')
            battery = self.install(manifest())
            self.change('enable', 'org.example.battery', battery)
            # An active battery addon is not a quota source.
            self.assertEqual(self.quota()['addon']['reason'], 'not_installed')
            quota = self.install(quota_manifest())
            self.assertEqual(self.quota()['addon']['reason'], 'disabled')
            self.change('enable', 'org.example.quota', quota)
            self.assertEqual(self.quota(visible=False)['addon']['reason'], 'profile_hidden')
        self.assertEqual(self.s.snapshot_peripherals(paths=self.paths, now_ms=GENERATED)['addon']['id'],
                         'org.example.battery')

    def test_projection_keeps_only_fresh_ready_usage_and_names_each_state(self):
        quota = self.install(quota_manifest())
        self.change('enable', 'org.example.quota', quota)
        self.assertEqual(self.quota()['addon']['reason'], 'export_missing')
        self.write()
        p = self.quota()
        self.assertEqual((p['status'], p['source'], p['leaseMs'], p['addon']['reason']), ('ready', 'addon', 30000, 'ready'))
        providers = {item['id']: item for item in p['providers']}
        self.assertEqual([w['usedPercent'] for w in providers['codex']['windows']], [0, 42])
        self.assertEqual(providers['codex']['observedAt'], GENERATED / 1000)
        self.assertEqual(providers['claude']['state'], 'stale')
        self.assertEqual(providers['claude']['windows'][0]['usedPercent'], None)
        self.assertEqual(providers['gemini']['state'], 'unavailable')
        self.assertTrue(p['limited'])
        # An observation older than the lease stops confirming usage.
        old = quota_export()
        old['providers'][0]['observedAtMs'] = 1
        self.write(old)
        p = self.quota(now=GENERATED + 29999)
        codex = next(item for item in p['providers'] if item['id'] == 'codex')
        self.assertEqual((codex['state'], [w['usedPercent'] for w in codex['windows']]), ('stale', [None, None]))
        # A future observation cannot confirm usage either.
        future = quota_export()
        future['providers'][0]['observedAtMs'] = GENERATED + 5
        self.write(future)
        codex = next(item for item in self.quota()['providers'] if item['id'] == 'codex')
        self.assertEqual((codex['state'], codex['observedAtMs']), ('stale', None))
        for now, reason in ((GENERATED - 1, 'future'), (GENERATED + 30000, 'expired')):
            with self.subTest(reason=reason):
                p = self.quota(now=now)
                self.assertEqual((p['status'], p['providers'], p['addon']['reason']), ('stale', [], reason))
        self.write(dict(formatVersion='0.1-experimental'))
        p = self.quota()
        self.assertEqual((p['status'], p['addon']['reason'], p['addon']['errorCode']), ('invalid', 'export_invalid', 'fields'))

    def test_worker_and_cli_roundtrip_the_quota_projection(self):
        quota = self.install(quota_manifest())
        self.change('enable', 'org.example.quota', quota)
        self.write()
        w = load('addon_worker')
        backend = w.load_backend(ROOT / 'package/contents/code')
        frame = dict(formatVersion='0.1-experimental', ok=True, result=dict(
            schemaVersion=2, modules=['quota'], quota=self.quota()))
        data = (json.dumps(frame) + '\n').encode()
        self.assertEqual(w.validate_response(data, 0, 'quota', backend)['result']['quota']['status'], 'ready')
        tampered = copy.deepcopy(frame)
        stale = next(p for p in tampered['result']['quota']['providers'] if p['id'] == 'claude')
        stale['windows'][0]['usedPercent'] = 10
        with self.assertRaises(ValueError):
            w.validate_response((json.dumps(tampered) + '\n').encode(), 0, 'quota', backend)
        listing = dict(formatVersion='0.1-experimental', ok=True, result=self.s.list_addons(paths=self.paths))
        self.assertTrue(w.validate_response((json.dumps(listing) + '\n').encode(), 0, 'list', backend)['ok'])
        doubled = copy.deepcopy(listing)
        doubled['result']['addons'].append(copy.deepcopy(doubled['result']['addons'][0]))
        doubled['result']['addons'][1]['manifest']['id'] = 'org.example.quota-two'
        with self.assertRaises(ValueError):
            w.validate_response((json.dumps(doubled) + '\n').encode(), 0, 'list', backend)
        self.assertEqual(w.ARITY['quota'], 0)
        result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/addons.py'),
            '--home', str(self.home), '--data-home', str(self.data), '--state-home', str(self.state),
            'snapshot', '--module', 'quota', '--now-ms', str(GENERATED + 1000)],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['result']['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
