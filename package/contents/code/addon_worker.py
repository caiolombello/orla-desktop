#!/usr/bin/env python3
"""One finite trusted-host operation, one JSON frame, then EOF. Stdlib only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import unquote, urlsplit

FORMAT = '0.1-experimental'
LIMIT = 262144
SOURCE_NAMES = ('addon_service.py', 'addon_worker.py', 'addon_store.py',
                'addon_io.py', 'addon_format.py')
MUTATIONS = frozenset(('install', 'enable', 'disable', 'remove', 'rollback'))
ARITY = dict(list=0, inspect=1, install=2, enable=2, disable=2, remove=2,
             rollback=2, snapshot=0, quota=0, empty=0)
CODES = frozenset(('type size utf8 json depth duplicate_key nonfinite fields format range '
    'lease file missing unsafe drift hash state busy limit not_found no_previous exists io '
    'unavailable timeout invalid_response cleanup_failed source_changed cancelled').split())


def encoded(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(',', ':'))


def failure(code, *, committed=False, generation=None):
    return dict(formatVersion=FORMAT, ok=False, error=dict(
        code=code if code in CODES else 'state', committed=committed, generation=generation))


def _pin(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def source_fingerprint(base):
    """Hash actual bytes and operation-local identities, anchored from /, no links.

    No persistent development receipt. Source ancestors allow root-owned sticky
    directories; ordinary ancestors must be root/user owned and not writable by
    group/other. Leaf policy also rejects hardlinks and special files.
    """
    base = Path(base).absolute()
    chain = [(os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW), None)]
    pins, leaves = [], {}
    try:
        for part in base.parts[1:]:
            parent = chain[-1][0]
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
            chain.append((child, part))
        for fd, name in chain:
            info = os.fstat(fd)
            mode = stat.S_IMODE(info.st_mode)
            if (info.st_uid not in (0, os.getuid()) or
                    (mode & 0o022 and not (info.st_uid == 0 and mode & stat.S_ISVTX))):
                raise ValueError('unsafe')
            pins.append((info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode))
        result = hashlib.sha256(encoded(pins).encode())
        for name in SOURCE_NAMES:
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                         dir_fd=chain[-1][0])
            try:
                before = os.fstat(fd)
                if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                        or before.st_uid not in (0, os.getuid())
                        or stat.S_IMODE(before.st_mode) & 0o022
                        or before.st_size > LIMIT):
                    raise ValueError('unsafe')
                chunks, size = [], 0
                while True:
                    data = os.read(fd, min(8192, LIMIT + 1 - size))
                    if not data:
                        break
                    chunks.append(data)
                    size += len(data)
                    if size > LIMIT:
                        raise ValueError('size')
                after = os.fstat(fd)
                named = os.stat(name, dir_fd=chain[-1][0], follow_symlinks=False)
                if _pin(before) != _pin(after) or _pin(after) != _pin(named) or size != after.st_size:
                    raise ValueError('drift')
                result.update(name.encode())
                result.update(encoded(_pin(after)).encode())
                result.update(b''.join(chunks))
                leaves[name] = _pin(after)
            finally:
                os.close(fd)
        for name, leaf_pin in leaves.items():
            if _pin(os.stat(name, dir_fd=chain[-1][0], follow_symlinks=False)) != leaf_pin:
                raise ValueError('drift')
        for index, (fd, name) in enumerate(chain):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode) != pins[index]:
                raise ValueError('drift')
            if name is not None:
                named = os.stat(name, dir_fd=chain[index - 1][0], follow_symlinks=False)
                if (named.st_dev, named.st_ino, named.st_uid, named.st_gid, named.st_mode) != pins[index]:
                    raise ValueError('drift')
        return result.hexdigest()
    finally:
        for fd, _ in reversed(chain):
            os.close(fd)


def load_backend(base):
    # Never resolve siblings through sys.path, a package namespace or the CWD.
    spec = importlib.util.spec_from_file_location('_orla_addon_worker_store',
                                                Path(base) / 'addon_store.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_request(action, args):
    if action not in ARITY or type(args) not in (list, tuple) or len(args) != ARITY[action]:
        raise ValueError('format')
    if any(type(v) is not str for v in args):
        raise ValueError('type')
    if action in ('inspect', 'install'):
        value = args[0]
        try:
            if not 1 <= len(value) <= 4096 or len(value.encode('utf-8')) > 16384:
                raise ValueError('file')
            uri = urlsplit(value)
            decoded = unquote(uri.path, encoding='utf-8', errors='strict')
            if (not value.startswith('file:///') or uri.scheme != 'file' or uri.netloc
                    or '?' in value or '#' in value or '\x00' in decoded
                    or re.search(r'%(?![0-9A-Fa-f]{2})', value)
                    or not decoded.startswith('/') or '..' in Path(decoded).parts):
                raise ValueError('file')
        except (ValueError, UnicodeError):
            raise ValueError('file') from None
    if action in MUTATIONS:
        if re.fullmatch(r'[0-9a-f]{64}', args[1]) is None:
            raise ValueError('hash')
        if action != 'install' and (len(args[0]) > 120 or re.fullmatch(
                r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+',
                args[0]) is None):
            raise ValueError('format')


def strict_frame(data):
    if type(data) is not bytes or len(data) > LIMIT or not data.endswith(b'\n') or data.count(b'\n') != 1:
        raise ValueError('frame')
    text = data[:-1].decode('utf-8', errors='strict')
    depth, quoted, escaped = 0, False, False
    for c in text:
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
            if depth > 16:
                raise ValueError('depth')
        elif c in ']}':
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate')
            result[key] = value
        return result

    def floating(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('nonfinite')
        return parsed

    def constant(_):
        raise ValueError('nonfinite')

    return json.loads(text, object_pairs_hook=pairs, parse_float=floating, parse_constant=constant)


def _fields(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError('fields')


def _hex(value, length, nullable=False):
    if nullable and value is None:
        return
    if type(value) is not str or re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is None:
        raise ValueError('hash')


def validate_response(data, exit_code, action, backend):
    """EOF/normal-exit is checked by the owner before this frame validator."""
    value = strict_frame(data)
    if type(value) is not dict or value.get('formatVersion') != FORMAT or type(value.get('ok')) is not bool:
        raise ValueError('envelope')
    if not value['ok']:
        _fields(value, 'formatVersion ok error')
        error = value['error']
        _fields(error, 'code committed generation')
        if (type(error['code']) is not str or error['code'] not in CODES or exit_code != 1
                or (error['committed'] is not None and type(error['committed']) is not bool)):
            raise ValueError('error')
        _hex(error['generation'], 32, nullable=error['committed'] is not True)
        if error['committed'] is False and error['generation'] is not None:
            raise ValueError('error')
        return value
    _fields(value, 'formatVersion ok result')
    if exit_code != 0:
        raise ValueError('exit')
    result = value['result']
    if action == 'inspect':
        _fields(result, 'sha256 manifest')
        _hex(result['sha256'], 64)
        backend.f.validate_manifest(result['manifest'])
    elif action in MUTATIONS or action == 'list':
        _fields(result, 'generation addons')
        _hex(result['generation'], 32, nullable=action == 'list')
        if type(result['addons']) is not list or len(result['addons']) > 32:
            raise ValueError('addons')
        ids, enabled = [], []
        for item in result['addons']:
            _fields(item, 'manifest sha256 previousSha256 enabled')
            backend.f.validate_manifest(item['manifest'])
            ids.append(item['manifest']['id'])
            _hex(item['sha256'], 64)
            _hex(item['previousSha256'], 64, nullable=True)
            if type(item['enabled']) is not bool:
                raise ValueError('enabled')
            if item['enabled']:
                enabled.append(item['manifest']['renderer'])
        # At most one active addon per renderer.
        if ids != sorted(set(ids)) or len(enabled) != len(set(enabled)) or (ids and result['generation'] is None):
            raise ValueError('addons')
    elif action == 'empty':
        if result != dict(schemaVersion=2, modules=[]):
            raise ValueError('snapshot')
    elif action == 'snapshot':
        _fields(result, 'schemaVersion modules peripherals')
        if type(result['schemaVersion']) is not int or result['schemaVersion'] != 2 or result['modules'] != ['peripherals']:
            raise ValueError('snapshot')
        _validate_projection(result['peripherals'], backend)
    elif action == 'quota':
        _fields(result, 'schemaVersion modules quota')
        if type(result['schemaVersion']) is not int or result['schemaVersion'] != 2 or result['modules'] != ['quota']:
            raise ValueError('snapshot')
        _validate_quota(result['quota'], backend)
    else:
        raise ValueError('action')
    return value


def _validate_envelope(p, backend, items):
    _fields(p, 'status generatedAt source producerVersion limited ' + items + ' generatedAtMs expiresAtMs leaseMs addon')
    if p['status'] not in ('missing', 'invalid', 'ready', 'stale', 'unknown') or type(p['limited']) is not bool:
        raise ValueError('snapshot')
    for key in ('generatedAtMs', 'expiresAtMs', 'leaseMs'):
        if p[key] is not None:
            backend.f.integer(p[key], 1, backend.f.MAX_SAFE_INTEGER)
    if ((p['generatedAt'] is not None and type(p['generatedAt']) not in (int, float))
            or p['generatedAt'] != (None if p['generatedAtMs'] is None else p['generatedAtMs'] / 1000.0)):
        raise ValueError('time')
    if p['source'] not in (None, 'addon'):
        raise ValueError('source')
    if p['producerVersion'] is not None:
        backend.f.text(p['producerVersion'], 40, r'[A-Za-z0-9.+_-]+')
    a = p['addon']
    _fields(a, 'id sha256 enabled generation producerNamespace reason errorCode')
    _hex(a['generation'], 32, nullable=True)
    _hex(a['sha256'], 64, nullable=True)
    if a['id'] is not None:
        backend.f.text(a['id'], 120, backend.f.ID_PATTERN)
    if a['producerNamespace'] is not None:
        backend.f.text(a['producerNamespace'], 64, backend.f.NAMESPACE_PATTERN)
    if (type(a['enabled']) is not bool or a['reason'] not in ('not_installed', 'disabled',
            'profile_hidden', 'export_missing', 'export_invalid', 'future', 'expired', 'ready', 'stale', 'unknown')
            or (a['errorCode'] is not None and a['errorCode'] not in backend.f.ERROR_CODES)):
        raise ValueError('addon')


def _validate_quota(p, backend):
    _validate_envelope(p, backend, 'providers')
    if type(p['providers']) is not list or len(p['providers']) > 32:
        raise ValueError('providers')
    ids = set()
    for provider in p['providers']:
        _fields(provider, 'id state observedAt observedAtMs windows')
        backend.f.text(provider['id'], 32, backend.f.PROVIDER_PATTERN)
        if provider['id'] in ids or provider['state'] not in backend.f.QUOTA_STATES:
            raise ValueError('provider')
        ids.add(provider['id'])
        if provider['observedAtMs'] is not None:
            backend.f.integer(provider['observedAtMs'], 1, backend.f.MAX_SAFE_INTEGER)
        if ((provider['observedAt'] is not None and type(provider['observedAt']) not in (int, float))
                or provider['observedAt'] != (None if provider['observedAtMs'] is None else provider['observedAtMs'] / 1000.0)):
            raise ValueError('time')
        if type(provider['windows']) is not list or len(provider['windows']) > 3:
            raise ValueError('windows')
        order = -1
        for window in provider['windows']:
            _fields(window, 'key usedPercent windowMinutes resetAtMs')
            if window['key'] not in backend.f.WINDOW_KEYS or backend.f.WINDOW_KEYS.index(window['key']) <= order:
                raise ValueError('window')
            order = backend.f.WINDOW_KEYS.index(window['key'])
            if window['usedPercent'] is not None:
                backend.f.integer(window['usedPercent'], 0, 100)
                if provider['state'] != 'ready':
                    raise ValueError('window')
            if window['windowMinutes'] is not None:
                backend.f.integer(window['windowMinutes'], 1, 525600)
            if window['resetAtMs'] is not None:
                backend.f.integer(window['resetAtMs'], 1, backend.f.MAX_SAFE_INTEGER)


def _validate_projection(p, backend):
    _fields(p, 'status generatedAt source producerVersion limited devices generatedAtMs expiresAtMs leaseMs addon')
    if p['status'] not in ('missing', 'invalid', 'ready', 'stale', 'unknown') or type(p['limited']) is not bool:
        raise ValueError('snapshot')
    for key in ('generatedAtMs', 'expiresAtMs', 'leaseMs'):
        if p[key] is not None:
            backend.f.integer(p[key], 1, backend.f.MAX_SAFE_INTEGER)
    if ((p['generatedAt'] is not None and type(p['generatedAt']) not in (int, float))
            or p['generatedAt'] != (None if p['generatedAtMs'] is None else p['generatedAtMs'] / 1000.0)):
        raise ValueError('time')
    if p['source'] not in (None, 'addon'):
        raise ValueError('source')
    if p['producerVersion'] is not None:
        backend.f.text(p['producerVersion'], 40, r'[A-Za-z0-9.+_-]+')
    a = p['addon']
    _fields(a, 'id sha256 enabled generation producerNamespace reason errorCode')
    _hex(a['generation'], 32, nullable=True)
    _hex(a['sha256'], 64, nullable=True)
    if a['id'] is not None:
        backend.f.text(a['id'], 120, backend.f.ID_PATTERN)
    if a['producerNamespace'] is not None:
        backend.f.text(a['producerNamespace'], 64, backend.f.NAMESPACE_PATTERN)
    if (type(a['enabled']) is not bool or a['reason'] not in ('not_installed', 'disabled',
            'profile_hidden', 'export_missing', 'export_invalid', 'future', 'expired', 'ready', 'stale', 'unknown')
            or (a['errorCode'] is not None and a['errorCode'] not in backend.f.ERROR_CODES)):
        raise ValueError('addon')
    if type(p['devices']) is not list or len(p['devices']) > 128:
        raise ValueError('devices')
    for d in p['devices']:
        _fields(d, 'name kind percent level charging estimated stale present observedAt observedAtMs components')
        if (d['kind'] not in backend.f.KINDS or type(d['name']) is not str
                or re.fullmatch(re.escape(d['kind']) + r'(?: [1-9][0-9]{0,2})?', d['name']) is None):
            raise ValueError('name')
        for key in ('estimated', 'stale', 'present'):
            if type(d[key]) is not bool:
                raise ValueError('boolean')
        if d['observedAtMs'] is not None:
            backend.f.integer(d['observedAtMs'], 1, backend.f.MAX_SAFE_INTEGER)
        if ((d['observedAt'] is not None and type(d['observedAt']) not in (int, float))
                or d['observedAt'] != (None if d['observedAtMs'] is None else d['observedAtMs'] / 1000.0)):
            raise ValueError('time')
        if d['percent'] is not None:
            backend.f.integer(d['percent'], 0, 100)
        if d['level'] not in (None, 'critical', 'low', 'good', 'full'):
            raise ValueError('level')
        if d['charging'] not in ('discharging', 'charging', 'full', 'unknown'):
            raise ValueError('charging')
        if type(d['components']) is not list or len(d['components']) > 3:
            raise ValueError('components')
        labels = set()
        for c in d['components']:
            _fields(c, 'label percent charging')
            if c['label'] not in ('left', 'right', 'case') or c['label'] in labels:
                raise ValueError('label')
            labels.add(c['label'])
            if c['percent'] is not None:
                backend.f.integer(c['percent'], 0, 100)
            if c['charging'] not in ('discharging', 'charging', 'full', 'unknown'):
                raise ValueError('charging')


def execute(action, args, *, base, expected_source):
    """Roots come only from the activation environment, never method arguments."""
    committed, generation = False, None
    try:
        validate_request(action, args)
        if source_fingerprint(base) != expected_source:
            return failure('source_changed')
        if action == 'empty':
            return dict(formatVersion=FORMAT, ok=True, result=dict(schemaVersion=2, modules=[]))
        backend = load_backend(base)
        if source_fingerprint(base) != expected_source:
            return failure('source_changed')
    except Exception:
        return failure('unavailable')
    try:
        if action == 'inspect':
            result = backend.inspect_addon(file=args[0])
        else:
            paths = backend.AddonPaths()
            if action == 'list':
                result = backend.list_addons(paths=paths)
            elif action == 'snapshot':
                result = dict(schemaVersion=2, modules=['peripherals'],
                              peripherals=backend.snapshot_peripherals(paths=paths))
            elif action == 'quota':
                result = dict(schemaVersion=2, modules=['quota'], quota=backend.snapshot_quota(paths=paths))
            elif action == 'install':
                committed = None  # Interrupted/unknown exceptions cannot promise cancellation.
                result = backend.install_addon(paths=paths, file=args[0], expected_sha256=args[1])
            else:
                operation = {'enable': backend.enable_addon, 'disable': backend.disable_addon,
                             'remove': backend.remove_addon, 'rollback': backend.rollback_addon}[action]
                committed = None
                result = operation(paths=paths, addon_id=args[0], expected_current_sha256=args[1])
        if action in MUTATIONS:
            committed, generation = True, result['generation']
        response = dict(formatVersion=FORMAT, ok=True, result=result)
    except backend.AddonError as error:
        committed, generation = error.committed, error.generation
        response = failure(error.code, committed=committed, generation=generation)
    except Exception:
        # Boundary only: unexpected exceptions must not print OS/input details,
        # and a mutation already entered may have committed before it failed.
        response = failure('io', committed=committed, generation=generation)
    try:
        if source_fingerprint(base) != expected_source:
            return failure('source_changed', committed=committed, generation=generation)
        data = (encoded(response) + '\n').encode('ascii')
        validate_response(data, 0 if response['ok'] else 1, action, backend)
    except Exception:
        return failure('invalid_response', committed=committed, generation=generation)
    return response


def main(argv=None):
    sys.dont_write_bytecode = True
    args = sys.argv[1:] if argv is None else argv
    response = failure('format')
    if (len(args) >= 3 and args[0] == '--source-sha'
            and re.fullmatch(r'[0-9a-f]{64}', args[1]) is not None):
        try:
            validate_request(args[2], args[3:])
        except ValueError as error:
            response = failure(str(error))
        else:
            response = execute(args[2], args[3:], base=Path(__file__).absolute().parent,
                               expected_source=args[1])
    data = (encoded(response) + '\n').encode('ascii')
    if len(data) > LIMIT:
        response = failure('size', committed=None)
        data = (encoded(response) + '\n').encode('ascii')
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    return 0 if response['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
