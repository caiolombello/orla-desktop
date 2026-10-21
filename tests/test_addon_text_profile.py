"""Fixed contract oracle and offline generation; never consult host Unicode tables."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = '073f8a36bcfd6b250cd5e0d07aa5641086829a58495758444ea70695c5a904ef'
DATA = 'scripts/data/addon-text-unicode16.json'
GENERATOR = 'scripts/generate_addon_text_profile.py'
FORMAT = 'package/contents/code/addon_format.py'
JS = 'package/contents/code/AddonText.js'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_oracle(root=ROOT):
    value = json.loads((root / DATA).read_text(encoding='utf-8'))
    vector = bytearray(139264)
    for first, last in value['ranges']:
        for cp in range(first, last + 1):
            vector[cp // 8] |= 1 << (cp % 8)
    assert len(vector) == 139264
    assert sum(byte.bit_count() for byte in vector) == 154810
    assert hashlib.sha256(vector).hexdigest() == GOLDEN
    return value, vector


class AddonTextProfileTests(unittest.TestCase):
    def setUp(self):
        self.g = load(ROOT / GENERATOR, 'profile_generator')
        self.f = load(ROOT / FORMAT, 'profile_format')

    def test_actual_python_text_has_exact_canonical_membership(self):
        _, expected = canonical_oracle()
        actual = bytearray(139264)
        scalars = 0
        for cp in range(0x110000):
            try:
                self.f.text(chr(cp), 1)
                actual[cp // 8] |= 1 << (cp % 8)
            except self.f.AddonError as error:
                self.assertEqual(error.code, 'format')
            if not 0xd800 <= cp <= 0xdfff:
                scalars += 1
        self.assertEqual(scalars, 1112064)
        self.assertEqual(hashlib.sha256(actual).hexdigest(), GOLDEN)
        self.assertEqual(actual, expected)

    def test_types_limits_ascii_patterns_and_new_unicode16_assignments(self):
        for value in (None, 1, True, [], b'A'):
            with self.assertRaises(self.f.AddonError) as raised:
                self.f.text(value, 80)
            self.assertEqual(raised.exception.code, 'type')
        for value in ('', 'a'*81, '\ud800', '\udfff', '\u088f', '\ue000', '\ufff9'):
            with self.assertRaises(self.f.AddonError) as raised:
                self.f.text(value, 80)
            self.assertEqual(raised.exception.code, 'format')
        for value in (' ', 'e\u0301', '😀'*80, '\u1c89', '\U00010d40', '\U00011bc0', '\U0001e5d0'):
            self.assertEqual(self.f.text(value, 80), value)
        for pattern in (self.f.ID_PATTERN, self.f.NAMESPACE_PATTERN, self.f.VERSION_PATTERN):
            with self.assertRaises(self.f.AddonError):
                self.f.text('\u1c89', 120, pattern)

    def test_actual_core_javascript_matches_golden_without_client_files(self):
        program = r'''import hashlib,json,runpy,sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QUrl
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlExpression
root=Path(sys.argv[1]);oracle=runpy.run_path(str(root/'tests/test_addon_text_profile.py'))
_,expected=oracle['canonical_oracle'](root)
app=QCoreApplication([]);engine=QQmlEngine();component=QQmlComponent(engine)
url=QUrl.fromLocalFile(str(root/'package/contents/code/AddonText.js')).toString()
component.setData(('import QtQml\nimport "'+url+'" as AddonText\nQtObject { function plain(value,maximum) { return AddonText.plain(value,maximum); } }').encode(),QUrl())
obj=component.create();assert obj is not None,[e.toString() for e in component.errors()]
actual=bytearray(139264);scalars=0
for start in range(0,0x110000,4096):
    expression=QQmlExpression(engine.rootContext(),obj,r"""JSON.stringify((function(){let values=[];
        for(let cp=%d;cp<%d;++cp){const n=cp-0x10000;
        const character=cp<0x10000 ? String.fromCharCode(cp)
            : String.fromCharCode(0xd800+Math.floor(n/0x400),0xdc00+n%%0x400);
        values.push(plain(character,1));}return values;})())""" % (start,min(start+4096,0x110000)))
    text,_=expression.evaluate();assert not expression.hasError(),expression.error().toString()
    values=json.loads(text);assert len(values)==min(4096,0x110000-start)
    for offset,accepted in enumerate(values):
        assert type(accepted) is bool
        cp=start+offset
        if accepted: actual[cp//8] |= 1<<(cp%8)
        if not 0xd800<=cp<=0xdfff: scalars+=1
assert scalars==1112064
assert hashlib.sha256(actual).hexdigest()==oracle['GOLDEN']
assert actual==expected
print('CORE_JS',scalars,hashlib.sha256(actual).hexdigest())
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', program, str(ROOT)],
                                cwd=ROOT, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CORE_JS 1112064 '+GOLDEN, result.stdout)

    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name in (GENERATOR, DATA, FORMAT, JS):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        return root

    def command(self, root, *args):
        return subprocess.run([sys.executable, '-I', '-B', str(root / GENERATOR), *args],
                              cwd=root, capture_output=True, timeout=15)

    def test_generation_is_deterministic_and_check_is_nonwriting(self):
        root = self.fixture()
        def snapshot():
            return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in root.rglob('*') if p.is_file()}
        before = snapshot()
        for _ in range(2):
            checked = self.command(root, '--check')
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(snapshot(), before)
        for _ in range(2):
            generated = self.command(root)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            self.assertEqual({p: raw for p, (raw, _) in snapshot().items()},
                             {p: raw for p, (raw, _) in before.items()})
        (root / JS).write_text('corrupt generated file\n')
        before = snapshot()
        self.assertEqual(self.command(root, '--check').returncode, 1)
        self.assertEqual(snapshot(), before)

    def test_corrupt_canonical_records_and_provenance_refuse_without_writes(self):
        root = self.fixture()
        original = json.loads((root / DATA).read_text())
        cases = []
        def changed(edit):
            value = json.loads(json.dumps(original));edit(value);cases.append(self.g.compact(value))
        changed(lambda v: v.update(profile='unapproved'))
        changed(lambda v: v.update(unicodeVersion='17.0.0'))
        changed(lambda v: v['sources'][0].update(sha256='0'*64))
        changed(lambda v: v['sources'][0].update(bytes=float(v['sources'][0]['bytes'])))
        changed(lambda v: v.update(license=v['license']+'changed'))
        changed(lambda v: v.update(codepointCount=154811))
        changed(lambda v: v.update(vectorSha256='0'*64))
        changed(lambda v: v['ranges'].__setitem__(1,[31,33]))
        changed(lambda v: v['ranges'].__setitem__(1,[33,33]))
        changed(lambda v: v['ranges'].__setitem__(1,[0xd800,0xd800]))
        changed(lambda v: v['ranges'].__setitem__(1,[True,40]))
        changed(lambda v: v['ranges'].__setitem__(1,[40,39]))
        changed(lambda v: v['ranges'].__setitem__(1,[0x110000,0x110000]))
        cases.extend([b'{"profile":"x","profile":"y"}', b' '*32769, b'\xff', b'[]', b'{}'])
        for raw in cases:
            with self.subTest(raw=hashlib.sha256(raw).hexdigest()):
                (root / DATA).write_bytes(raw)
                before = {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(self.command(root, '--check').returncode, 1)
                self.assertEqual({str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)

    def test_ucd_record_parser_refuses_bad_columns_order_categories_and_ranges(self):
        def row(cp, name='A', category='Lu'):
            return ';'.join([cp,name,category,'0','L','','','','','N','','','','',''])
        for raw in (row('0041')+';extra', row('0041')+'\n'+row('0040'),
                    row('0041',category='XX'), row('0041','<X, Last>'),
                    row('0041','<X, First>'), row('0041','<X, First>')+'\n'+row('0042','<Y, Last>'),
                    row('0041','<X, First>')+'\n'+row('0042','<X, Last>','Lo'),
                    row('110000'), row('D800')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.g.parse_ucd(raw)
        self.assertEqual(self.g.parse_ucd(row('0041')+'\n'+row('0043')),[[32,32],[65,65],[67,67]])
        self.assertEqual(self.g.parse_ucd(row('0041','<X, First>')+'\n'+row('0043','<X, Last>')),
                         [[32,32],[65,67]])

    def test_ucd_import_refuses_unapproved_input_and_does_not_adopt_it(self):
        root = self.fixture()
        ucd = root / 'ucd';ucd.mkdir()
        for entry in self.g.SOURCES:
            (ucd / entry['file']).write_bytes(b'corrupt unapproved source')
        before = {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.assertEqual(self.command(root, '--from-ucd', str(ucd)).returncode, 1)
        self.assertEqual({str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)

    def test_embedded_runtime_has_complete_notice_and_no_dataset_dependency(self):
        value, _ = canonical_oracle()
        root = self.fixture()
        for name, prefix in ((FORMAT,'# '),(JS,'// ')):
            text = (root / name).read_text()
            body = text.split(prefix+'BEGIN UNICODE LICENSE\n',1)[1].split(prefix+'END UNICODE LICENSE',1)[0]
            self.assertEqual(''.join(line[len(prefix):] for line in body.splitlines(True)),value['license'])
        shutil.rmtree(root / 'scripts')
        standalone = load(root / FORMAT,'standalone_format')
        self.assertEqual(standalone.text('\U0001e5d0',1),'\U0001e5d0')
        with self.assertRaises(standalone.AddonError): standalone.text('\u088f',1)
        self.assertLess((root / FORMAT).stat().st_size,262144)

    def test_existing_out_of_profile_bytes_are_refused_without_rewriting_state(self):
        store = load(ROOT / 'package/contents/code/addon_store.py', 'profile_store')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'home';home.mkdir(mode=0o700)
            paths = store.AddonPaths(home=home, data_home=root/'data', state_home=root/'state')
            paths.store.parent.mkdir(parents=True, mode=0o700)
            paths.store.mkdir(mode=0o700)
            objects = paths.store/'objects';objects.mkdir(mode=0o700)
            m = dict(formatVersion='0.1-experimental', id='org.example.battery',
                name='synthetic\u088flabel', description='Synthetic passive data', author='Example',
                license='MIT', version='1.0.0', origin='https://example.org/project',
                renderer='peripheral-battery',source=dict(namespace='synthetic',formatVersion='0.1-experimental'))
            raw = (json.dumps(m, ensure_ascii=False)+'\n').encode()
            digest = hashlib.sha256(raw).hexdigest()
            registry = dict(formatVersion='0.1-experimental', generation='1'*32,
                entries=[dict(id=m['id'],sha256=digest,previousSha256=None,enabled=False)],artifacts=[digest])
            files = {objects/(digest+'.json'):raw,
                     paths.store/'registry.json':json.dumps(registry).encode(),
                     paths.store/'.lock':b'', home/'approval-receipt':b'synthetic unchanged consent'}
            for path, content in files.items():
                path.write_bytes(content);path.chmod(0o600)
            before = {p:(p.read_bytes(),p.stat().st_mtime_ns) for p in files}
            with self.assertRaises(store.AddonError) as raised:
                store.list_addons(paths=paths)
            self.assertEqual(raised.exception.code, 'format')
            self.assertFalse(raised.exception.committed)
            self.assertEqual({p:(p.read_bytes(),p.stat().st_mtime_ns) for p in files}, before)


if __name__ == '__main__':
    unittest.main()
