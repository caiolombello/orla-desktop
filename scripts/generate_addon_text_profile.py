#!/usr/bin/env python3
"""Offline, pinned Unicode 16 addon text generation; --check never writes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'orla-addon-text-16.0.0-r1'
VECTOR_SHA256 = '073f8a36bcfd6b250cd5e0d07aa5641086829a58495758444ea70695c5a904ef'
ENCODING = '0x110000 bits; bit n LSB-first in byte n//8; surrogates zero'
SOURCES = [
    dict(file='UnicodeData-16.0.0.txt', url='https://www.unicode.org/Public/16.0.0/ucd/UnicodeData.txt',
         bytes=2175362, sha256='ff58e5823bd095166564a006e47d111130813dcf8bf234ef79fa51a870edb48f'),
    dict(file='ReadMe-16.0.0.txt', url='https://www.unicode.org/Public/16.0.0/ucd/ReadMe.txt',
         bytes=693, sha256='14cafa23788d3a20dd21d6b0cdcb8d6dab520781fcd9ad9392f3b88ea607e633'),
    dict(file='UNICODE-LICENSE.txt', url='https://www.unicode.org/license.txt',
         bytes=1995, sha256='e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96'),
]
DATA = Path('scripts/data/addon-text-unicode16.json')
PYTHON = Path('package/contents/code/addon_format.py')
JAVASCRIPT = Path('package/contents/code/AddonText.js')
BEGIN = '# BEGIN GENERATED ADDON TEXT PROFILE\n'
END = '# END GENERATED ADDON TEXT PROFILE\n'
CATEGORIES = frozenset('Lu Ll Lt Lm Lo Mn Mc Me Nd Nl No Pc Pd Ps Pe Pi Pf Po Sm Sc Sk So Zs Zl Zp Cc Cf Cs Co Cn'.split())


def compact(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate canonical key')
        result[key] = value
    return result


def validate(value):
    expected = {'profile', 'unicodeVersion', 'sources', 'license', 'ranges',
                'codepointCount', 'vectorEncoding', 'vectorSha256'}
    if type(value) is not dict or set(value) != expected:
        raise ValueError('canonical fields')
    if (value['profile'] != PROFILE or value['unicodeVersion'] != '16.0.0'
            or compact(value['sources']) != compact(SOURCES) or value['vectorEncoding'] != ENCODING
            or value['vectorSha256'] != VECTOR_SHA256):
        raise ValueError('canonical provenance')
    notice = value['license']
    if (type(notice) is not str or len(notice.encode('utf-8')) != SOURCES[2]['bytes']
            or hashlib.sha256(notice.encode('utf-8')).hexdigest() != SOURCES[2]['sha256']):
        raise ValueError('canonical license')
    ranges = value['ranges']
    if type(ranges) is not list or len(ranges) != 736:
        raise ValueError('canonical range count')
    previous, count = -2, 0
    vector = bytearray(0x110000 // 8)
    for interval in ranges:
        if (type(interval) is not list or len(interval) != 2
                or any(type(n) is not int for n in interval)):
            raise ValueError('canonical interval type')
        first, last = interval
        if (not 0 <= first <= last < 0x110000 or first <= previous + 1
                or (first <= 0xdfff and last >= 0xd800)):
            raise ValueError('canonical interval order/domain')
        previous = last
        count += last - first + 1
        for cp in range(first, last + 1):
            vector[cp // 8] |= 1 << (cp % 8)
    if (type(value['codepointCount']) is not int or value['codepointCount'] != count
            or count != 154810 or hashlib.sha256(vector).hexdigest() != VECTOR_SHA256):
        raise ValueError('canonical membership')
    return value


def read_canonical(path):
    with path.open('rb') as stream:
        raw = stream.read(32769)
    if len(raw) > 32768:
        raise ValueError('canonical size')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs)
    validate(value)
    if raw != compact(value):
        raise ValueError('canonical encoding')
    return value


def parse_ucd(text):
    """Validate ordered 15-column records and paired ranges; absent positions are Cn."""
    intervals, previous, pending = [[32, 32]], -1, None
    for line in text.splitlines():
        fields = line.split(';')
        if len(fields) != 15 or not re.fullmatch(r'[0-9A-F]{4,6}', fields[0]):
            raise ValueError('UCD record')
        cp = int(fields[0], 16)
        category = fields[2]
        if not previous < cp < 0x110000 or category not in CATEGORIES:
            raise ValueError('UCD ordering/category')
        previous = cp
        marker = re.fullmatch(r'<(.+), (First|Last)>', fields[1])
        if pending:
            start, name, tail = pending
            if not marker or marker[2] != 'Last' or marker[1] != name or fields[2:] != tail:
                raise ValueError('UCD range endpoint')
            pending = None
        elif marker:
            if marker[2] != 'First':
                raise ValueError('UCD range start')
            pending = cp, marker[1], fields[2:]
            continue
        else:
            start = cp
        if category[0] in 'LMNPS':
            if start <= 0xdfff and cp >= 0xd800:
                raise ValueError('UCD printable surrogate')
            intervals.append([start, cp])
    if pending:
        raise ValueError('UCD unterminated range')
    result = []
    for first, last in sorted(intervals):
        if result and first <= result[-1][1] + 1:
            result[-1][1] = max(last, result[-1][1])
        else:
            result.append([first, last])
    return result


def from_ucd(directory):
    inputs = []
    for source in SOURCES:
        with (directory / source['file']).open('rb') as stream:
            raw = stream.read(source['bytes'] + 1)
        if len(raw) != source['bytes'] or hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('unapproved UCD input')
        inputs.append(raw.decode('utf-8'))
    if 'final data files' not in inputs[1] or 'Version 16.0.0' not in inputs[1]:
        raise ValueError('UCD version')
    return validate(dict(profile=PROFILE, unicodeVersion='16.0.0', sources=SOURCES,
        license=inputs[2], ranges=parse_ucd(inputs[0]), codepointCount=154810,
        vectorEncoding=ENCODING, vectorSha256=VECTOR_SHA256))


def notice(value, prefix):
    return (prefix + 'BEGIN UNICODE LICENSE\n'
            + ''.join(prefix + line + '\n' for line in value['license'].splitlines())
            + prefix + 'END UNICODE LICENSE\n')


def python_block(value):
    intervals = ''.join('    (%d, %d),\n' % tuple(pair) for pair in value['ranges'])
    return (BEGIN + '# Generated by scripts/generate_addon_text_profile.py; do not edit.\n'
            + '# ' + PROFILE + '; vector SHA-256 ' + VECTOR_SHA256 + '\n'
            + notice(value, '# ') + '_ADDON_TEXT_RANGES = (\n' + intervals + ')\n\n'
            + '''def _addon_text_scalar(codepoint):
    low, high = 0, len(_ADDON_TEXT_RANGES)
    while low < high:
        middle = (low + high) // 2
        first, last = _ADDON_TEXT_RANGES[middle]
        if codepoint < first:
            high = middle
        elif codepoint > last:
            low = middle + 1
        else:
            return True
    return False


def _addon_text_printable(value):
    return all(_addon_text_scalar(ord(character)) for character in value)
''' + END)


def javascript(value):
    numbers = [str(n) for interval in value['ranges'] for n in interval]
    rows = ',\n'.join('    ' + ', '.join(numbers[i:i+12]) for i in range(0, len(numbers), 12))
    return ('.pragma library\n\n// Generated by scripts/generate_addon_text_profile.py; do not edit.\n'
            + '// ' + PROFILE + '; vector SHA-256 ' + VECTOR_SHA256 + '\n'
            + notice(value, '// ') + '\nvar ranges = Object.freeze([\n' + rows + '\n]);\n\n'
            + '''function scalar(codepoint) {
    let low = 0, high = ranges.length / 2;
    while (low < high) {
        const middle = Math.floor((low + high) / 2);
        if (codepoint < ranges[2 * middle]) high = middle;
        else if (codepoint > ranges[2 * middle + 1]) low = middle + 1;
        else return true;
    }
    return false;
}

function plain(value, maximum) {
    if (typeof value !== "string" || !value.length || !Number.isSafeInteger(maximum) || maximum < 1) return false;
    let count = 0;
    for (let i = 0; i < value.length; ++i) {
        let codepoint = value.charCodeAt(i);
        if (codepoint >= 0xd800 && codepoint <= 0xdbff) {
            if (++i >= value.length) return false;
            const tail = value.charCodeAt(i);
            if (tail < 0xdc00 || tail > 0xdfff) return false;
            codepoint = 0x10000 + (codepoint - 0xd800) * 0x400 + tail - 0xdc00;
        } else if (codepoint >= 0xdc00 && codepoint <= 0xdfff) return false;
        if (++count > maximum || !scalar(codepoint)) return false;
    }
    return true;
}
''')


def outputs(root, value):
    source = (root / PYTHON).read_text(encoding='utf-8')
    if source.count(BEGIN) != 1 or source.count(END) != 1:
        raise ValueError('generated block markers')
    start, end = source.index(BEGIN), source.index(END) + len(END)
    if end <= start:
        raise ValueError('generated block order')
    return {DATA: compact(value),
            PYTHON: (source[:start] + python_block(value) + source[end:]).encode('utf-8'),
            JAVASCRIPT: javascript(value).encode('utf-8')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-ucd', type=Path, metavar='DIR')
    parser.add_argument('--check', action='store_true', help='compare only; never write')
    args = parser.parse_args(argv)
    try:
        value = from_ucd(args.from_ucd) if args.from_ucd else read_canonical(ROOT / DATA)
        generated = outputs(ROOT, value)
        if args.check:
            if any(not (ROOT / p).is_file() or (ROOT / p).read_bytes() != raw for p, raw in generated.items()):
                raise ValueError('generated files differ')
        else:
            for p, raw in generated.items():
                (ROOT / p).parent.mkdir(parents=True, exist_ok=True)
                (ROOT / p).write_bytes(raw)
    except (OSError, ValueError, UnicodeError, RecursionError):
        print('addon text profile: invalid input or generated files differ', file=sys.stderr)
        return 1
    print('addon text profile: checked' if args.check else 'addon text profile: generated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
