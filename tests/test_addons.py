"""Synthetic addon contract tests; no producers, buses, or personal state."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).absolute().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location('_test_orla_' + name,
                                                 ROOT / 'package/contents/code' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest():
    return dict(formatVersion='0.1-experimental', id='org.example.battery',
                name='Synthetic batteries', description='Synthetic passive export',
                author='Example contributors', license='MIT', version='1.0.0',
                origin='https://example.invalid/project', renderer='peripheral-battery',
                source=dict(namespace='synthetic-battery', formatVersion='0.1-experimental'))


def export():
    return dict(formatVersion='0.1-experimental', producer='synthetic-battery',
                producerVersion='0.1.0', generatedAtMs=100000, expiresAtMs=130000,
                intervalSeconds=10, devices=[dict(kind='mouse', link='receiver', present=True,
                stale=False, observedAtMs=100000, battery=dict(percent=0, level=None,
                charging='discharging', estimated=False), components=[])])


class FormatTests(unittest.TestCase):
    def test_strict_package_roundtrip_preserves_declared_metadata_only(self):
        f = load('addon_format')
        data = json.dumps(manifest()).encode()
        self.assertEqual(f.parse_manifest(data), manifest())
        canonical = f.canonical_manifest_bytes(manifest())
        self.assertTrue(canonical.endswith(b'\n'))
        self.assertNotIn(b' ', canonical.replace(b'Synthetic batteries', b'').replace(
            b'Synthetic passive export', b'').replace(b'Example contributors', b''))
        self.assertEqual(f.parse_manifest(canonical), manifest())


    def test_parser_rejects_ambiguous_and_private_input(self):
        f = load('addon_format')
        cases = [(b' ' * 65537, 'size'), (b'"\xff"', 'utf8'),
                 (b'{"x":1,"x":2}', 'duplicate_key'), (b'NaN', 'nonfinite'),
                 (b'1e10000', 'nonfinite'), (b'[' * 1000, 'depth'),
                 (b'\xef\xbb\xbf{}', 'json')]
        for data, code in cases:
            with self.subTest(code=code), self.assertRaises(f.AddonError) as error:
                f.parse_manifest(data)
            self.assertEqual(error.exception.code, code)
        for key, value in [('command', 'do-not-echo-private-sentinel'),
                           ('name', 'bad\nname'), ('version', '01.0.0'),
                           ('origin', 'https://user@example.invalid/p'),
                           ('origin', 'https://example.invalid/?private=secret')]:
            m = manifest()
            m[key] = value
            with self.subTest(key=key), self.assertRaises(f.AddonError) as error:
                f.parse_manifest(json.dumps(m).encode())
            self.assertNotIn('sentinel', str(error.exception))
        m = manifest()
        m['source']['namespace'] = '../other'
        with self.assertRaises(f.AddonError):
            f.validate_manifest(m)

    def test_export_requires_exact_privacy_shape_and_json_safe_integers(self):
        f = load('addon_format')
        self.assertEqual(f.parse_export(json.dumps(export()).encode(),
                                       producer_namespace='synthetic-battery'), export())
        cases = []
        for key, value in [('generatedAtMs', True), ('generatedAtMs', 9007199254740992),
                           ('intervalSeconds', 9), ('expiresAtMs', 129999),
                           ('producer', 'wrong-namespace'), ('devices', [{}] * 129),
                           ('privateHardwareId', 'private-sentinel')]:
            e = export()
            e[key] = value
            cases.append(e)
        for key, value in [('present', 1), ('observedAtMs', False), ('alias', 'private-alias')]:
            e = export()
            e['devices'][0][key] = value
            cases.append(e)
        for value in (True, -1, 101, 4.5):
            e = export()
            e['devices'][0]['battery']['percent'] = value
            cases.append(e)
        e = export()
        e['devices'][0]['components'] = [dict(label='case', percent=None, charging='unknown')] * 2
        cases.append(e)
        for e in cases:
            with self.subTest(case=e), self.assertRaises(f.AddonError):
                f.parse_export(json.dumps(e).encode(), producer_namespace='synthetic-battery')
        e = export()
        e['devices'][0]['battery'].update(percent=None, level='low')
        result = f.parse_export(json.dumps(e).encode(), producer_namespace='synthetic-battery')
        self.assertIsNone(result['devices'][0]['battery']['percent'])
        self.assertEqual(result['devices'][0]['battery']['level'], 'low')

    def test_schemas_and_shared_synthetic_golden_are_offline_author_artifacts(self):
        f = load('addon_format')
        for name, schema in [('manifest', f.manifest_schema()),
                             ('peripherals', f.peripherals_schema())]:
            published = json.loads((ROOT / 'addons/schema' / (name + '-0.1.schema.json')).read_bytes())
            self.assertEqual(schema, published)
            self.assertFalse(published['additionalProperties'])
        data = (ROOT / 'addons/fixtures/peripherals-0.1.json').read_bytes()
        e = f.parse_export(data, producer_namespace='synthetic-battery')
        self.assertEqual(e['devices'][0]['battery']['percent'], 0)
        self.assertIsNone(e['devices'][1]['battery']['percent'])
        self.assertEqual(e['devices'][2]['battery']['level'], 'good')
        self.assertIsNone(e['devices'][3]['battery']['percent'])
        self.assertEqual(e['devices'][3]['components'][0]['label'], 'case')

    def test_clarified_byte_and_container_limits(self):
        f = load('addon_format')
        m = json.dumps(manifest()).encode()
        self.assertEqual(f.parse_manifest(m + b' ' * (65536 - len(m))), manifest())
        self.assertEqual(f.strict_json(b'[' * 8 + b'0' + b']' * 8), [[[[[[[[0]]]]]]]])
        with self.assertRaises(f.AddonError) as error:
            f.strict_json(b'[' * 9 + b'0' + b']' * 9)
        self.assertEqual(error.exception.code, 'depth')

    def test_origin_is_a_valid_metadata_url_without_encoded_control_or_fake_host(self):
        f = load('addon_format')
        for origin in ('https://%00.invalid/project', 'https://example.invalid:/project',
                       'https://example.invalid/%0Aprivate', 'https://bad^host/project'):
            m = manifest()
            m['origin'] = origin
            with self.subTest(origin=origin), self.assertRaises(f.AddonError):
                f.validate_manifest(m)
        m = manifest()
        m['origin'] = 'https://example.invalid/project/@branch'
        self.assertEqual(f.validate_manifest(m)['origin'], m['origin'])


if __name__ == '__main__':
    unittest.main()
