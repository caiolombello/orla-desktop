"""Experimental data-only addon contract. Hashes never authenticate publishers."""
from __future__ import annotations

import copy
import json
import ipaddress
import re
from urllib.parse import unquote, urlsplit

FORMAT_VERSION = '0.1-experimental'
MAX_BYTES = 65536
MAX_DEPTH = 8
MAX_SAFE_INTEGER = 9007199254740991
ID_PATTERN = r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+'
VERSION_PATTERN = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'
NAMESPACE_PATTERN = r'[a-z][a-z0-9-]{0,63}'
ERROR_CODES = frozenset(('type', 'size', 'utf8', 'json', 'depth', 'duplicate_key',
    'nonfinite', 'fields', 'format', 'range', 'lease', 'file', 'missing', 'unsafe',
    'drift', 'hash', 'state', 'busy', 'limit', 'not_found', 'no_previous', 'exists', 'io'))


class AddonError(ValueError):
    """Finite safe code only: never exposes OS messages, input values or paths."""
    def __init__(self, code: str, *, committed=False, generation=None):
        self.committed = committed
        self.generation = generation
        self.published = False
        self.code = code if code in ERROR_CODES else 'state'
        super().__init__(self.code)


def object_fields(value, fields):
    if type(value) is not dict:
        raise AddonError('type')
    if set(value) != set(fields):
        raise AddonError('fields')
    return value


def text(value, maximum, pattern=None):
    if type(value) is not str:
        raise AddonError('type')
    if not 1 <= len(value) <= maximum or not all(c.isprintable() for c in value):
        raise AddonError('format')
    if pattern and re.fullmatch(pattern, value) is None:
        raise AddonError('format')
    return value


def integer(value, minimum, maximum):
    if type(value) is not int:
        raise AddonError('type')
    if not minimum <= value <= maximum:
        raise AddonError('range')
    return value


def strict_json(data: bytes):
    """Bound before decoding/recursing; reject duplicate keys at every level."""
    if type(data) is not bytes:
        raise AddonError('type')
    if len(data) > MAX_BYTES:
        raise AddonError('size')
    try:
        decoded = data.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        raise AddonError('utf8') from None
    depth, quoted, escaped = 0, False, False
    for c in decoded:
        if quoted:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                quoted = False
        elif c == '"':
            quoted = True
        elif c in '[{':
            depth += 1
            if depth > MAX_DEPTH:
                raise AddonError('depth')
        elif c in ']}':
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AddonError('duplicate_key')
            result[key] = value
        return result

    def constant(_):
        raise AddonError('nonfinite')

    def floating(value):
        number = float(value)
        if number == float('inf') or number == -float('inf'):
            raise AddonError('nonfinite')
        return number

    try:
        return json.loads(decoded, object_pairs_hook=pairs, parse_constant=constant,
                          parse_float=floating)
    except AddonError:
        raise
    except (ValueError, RecursionError):
        raise AddonError('json') from None


def json_bytes(value):
    try:
        data = (json.dumps(value, ensure_ascii=False, sort_keys=True,
                           separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise AddonError('format') from None
    if len(data) > MAX_BYTES:
        raise AddonError('size')
    return data


def validate_manifest(value: object) -> dict:
    m = object_fields(value, ('formatVersion', 'id', 'name', 'description', 'author',
                             'license', 'version', 'origin', 'renderer', 'source'))
    if m['formatVersion'] != FORMAT_VERSION or m['renderer'] != 'peripheral-battery':
        raise AddonError('format')
    for key, limit, pattern in (('id', 120, ID_PATTERN), ('name', 80, None),
            ('description', 240, None), ('author', 120, None), ('license', 80, None),
            ('version', 32, VERSION_PATTERN), ('origin', 512, None)):
        text(m[key], limit, pattern)
    origin = m['origin']
    try:
        url = urlsplit(origin)
        valid = (origin.startswith('https://') and origin.isascii() and url.hostname
                 and url.netloc and url.username is None and url.password is None
                 and not url.query and not url.fragment and '?' not in origin and '#' not in origin
                 and not any(c.isspace() for c in origin) and '\\' not in origin)
        host = url.hostname or ''
        if ':' in host:
            ipaddress.IPv6Address(host)
            host_valid = '%' not in host
        else:
            label = r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?'
            host_valid = len(host) <= 253 and re.fullmatch(label + r'(?:\.' + label + r')*\.?', host)
        valid = (valid and host_valid and not url.netloc.endswith(':')
                 and re.search(r'%(?![0-9A-Fa-f]{2})', origin) is None
                 and unquote(origin, errors='strict').isprintable()
                 and not any(c in '<>"^`{|}' for c in origin))
        if url.port is not None and not 1 <= url.port <= 65535:
            valid = False
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise AddonError('format')
    s = object_fields(m['source'], ('namespace', 'formatVersion'))
    text(s['namespace'], 64, NAMESPACE_PATTERN)
    if s['formatVersion'] != FORMAT_VERSION:
        raise AddonError('format')
    result = copy.deepcopy(m)
    json_bytes(result)
    return result


def parse_manifest(data: bytes) -> dict:
    return validate_manifest(strict_json(data))


def canonical_manifest_bytes(value: object) -> bytes:
    return json_bytes(validate_manifest(value))


KINDS = ('mouse', 'keyboard', 'earbuds', 'headset', 'touchpad', 'gamepad', 'other')
LINKS = ('receiver', 'bluetooth', 'usb', 'unknown')
LEVELS = ('critical', 'low', 'good', 'full')
CHARGING = ('discharging', 'charging', 'full', 'unknown')
LABELS = ('left', 'right', 'case')


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        raise AddonError('format')


def _percent(value):
    if value is not None:
        integer(value, 0, 100)


def validate_export(value: object, *, producer_namespace: str) -> dict:
    text(producer_namespace, 64, NAMESPACE_PATTERN)
    e = object_fields(value, ('formatVersion', 'producer', 'producerVersion', 'generatedAtMs',
                             'expiresAtMs', 'intervalSeconds', 'devices'))
    if e['formatVersion'] != FORMAT_VERSION or e['producer'] != producer_namespace:
        raise AddonError('format')
    text(e['producerVersion'], 40, r'[A-Za-z0-9.+_-]{1,40}')
    generated = integer(e['generatedAtMs'], 1, MAX_SAFE_INTEGER)
    expires = integer(e['expiresAtMs'], 1, MAX_SAFE_INTEGER)
    interval = integer(e['intervalSeconds'], 10, 3600)
    if expires != generated + 3000 * interval:
        raise AddonError('lease')
    if type(e['devices']) is not list:
        raise AddonError('type')
    if len(e['devices']) > 128:
        raise AddonError('size')
    for d in e['devices']:
        object_fields(d, ('kind', 'link', 'present', 'stale', 'observedAtMs', 'battery', 'components'))
        _enum(d['kind'], KINDS)
        _enum(d['link'], LINKS)
        if type(d['present']) is not bool or type(d['stale']) is not bool:
            raise AddonError('type')
        if d['observedAtMs'] is not None:
            integer(d['observedAtMs'], 1, MAX_SAFE_INTEGER)
        b = object_fields(d['battery'], ('percent', 'level', 'charging', 'estimated'))
        _percent(b['percent'])
        if b['level'] is not None:
            _enum(b['level'], LEVELS)
        _enum(b['charging'], CHARGING)
        if type(b['estimated']) is not bool:
            raise AddonError('type')
        if type(d['components']) is not list:
            raise AddonError('type')
        if len(d['components']) > 3:
            raise AddonError('size')
        labels = set()
        for c in d['components']:
            object_fields(c, ('label', 'percent', 'charging'))
            _enum(c['label'], LABELS)
            _percent(c['percent'])
            _enum(c['charging'], CHARGING)
            if c['label'] in labels:
                raise AddonError('format')
            labels.add(c['label'])
    result = copy.deepcopy(e)
    json_bytes(result)
    return result


def parse_export(data: bytes, *, producer_namespace: str) -> dict:
    return validate_export(strict_json(data), producer_namespace=producer_namespace)


def canonical_export_bytes(value: object, *, producer_namespace: str) -> bytes:
    return json_bytes(validate_export(value, producer_namespace=producer_namespace))


def _schema_object(properties):
    return dict(type='object', additionalProperties=False, required=list(properties),
                properties=properties)


def _schema_text(maximum, pattern=None):
    result = dict(type='string', minLength=1, maxLength=maximum)
    if pattern:
        result['pattern'] = '^(?:' + pattern + ')$'
    return result


def manifest_schema() -> dict:
    """Portable author schema; the strict parser also enforces byte/text/URL rules."""
    schema = _schema_object(dict(
        formatVersion=dict(const=FORMAT_VERSION), id=_schema_text(120, ID_PATTERN),
        name=_schema_text(80), description=_schema_text(240), author=_schema_text(120),
        license=_schema_text(80), version=_schema_text(32, VERSION_PATTERN),
        origin=dict(type='string', maxLength=512, pattern=r'^https://[^/\s@?#\\]+(?:/[^\s?#\\]*)?$'),
        renderer=dict(const='peripheral-battery'),
        source=_schema_object(dict(namespace=_schema_text(64, NAMESPACE_PATTERN),
                                   formatVersion=dict(const=FORMAT_VERSION)))))
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$comment'] = ('Experimental. Normative stdlib parser also checks strict UTF-8, '
        '65536 bytes, depth <=8, duplicate keys, nonfinite numbers, printable text and '
        'an HTTPS URL without userinfo/query/fragment. SHA is integrity, not publisher authentication.')
    return schema


def peripherals_schema() -> dict:
    """Portable export shape; arithmetic lease/namespace equality require parser."""
    percent = dict(type=['integer', 'null'], minimum=0, maximum=100)
    stamp = dict(type='integer', minimum=1, maximum=MAX_SAFE_INTEGER)
    components = dict(type='array', maxItems=3, items=_schema_object(dict(
        label=dict(enum=list(LABELS)), percent=percent, charging=dict(enum=list(CHARGING)))))
    components['allOf'] = [dict(contains=dict(properties=dict(label=dict(const=label)),
                                            required=['label']), minContains=0, maxContains=1)
                           for label in LABELS]
    schema = _schema_object(dict(formatVersion=dict(const=FORMAT_VERSION),
        producer=_schema_text(64, NAMESPACE_PATTERN),
        producerVersion=_schema_text(40, r'[A-Za-z0-9.+_-]{1,40}'),
        generatedAtMs=stamp, expiresAtMs=stamp,
        intervalSeconds=dict(type='integer', minimum=10, maximum=3600),
        devices=dict(type='array', maxItems=128, items=_schema_object(dict(
            kind=dict(enum=list(KINDS)), link=dict(enum=list(LINKS)), present=dict(type='boolean'),
            stale=dict(type='boolean'), observedAtMs={**stamp, 'type': ['integer', 'null']},
            battery=_schema_object(dict(percent=percent, level=dict(enum=[*LEVELS, None]),
                charging=dict(enum=list(CHARGING)), estimated=dict(type='boolean'))),
            components=components)))))
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    schema['$comment'] = ('Experimental. Normative stdlib parser also checks strict UTF-8, '
        '65536 bytes, depth <=8, duplicate keys, nonfinite numbers, integer tokens, '
        'producer == selected namespace and expiresAtMs == generatedAtMs + 3000 * intervalSeconds. '
        'Host independently checks envelope/observation clocks and leases.')
    return schema
