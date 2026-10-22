"""Experimental passive-addon backend. No producer commands or IPC.

Public operations use keyword-only arguments and return JSON-compatible values.
All store reads hold a shared lock; mutations hold an exclusive lock. Generation
is revalidated before returning, but callers still gate already-sent UI responses.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import secrets

_spec = importlib.util.spec_from_file_location('_orla_addon_io',
                                              Path(__file__).absolute().with_name('addon_io.py'))
io = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(io)
f = io.f
AddonError = f.AddonError
MAX_ADDONS = 32
MAX_ARTIFACTS = 128
MAX_STORAGE_BYTES = 8 * 1024 * 1024
EXPORT_BASENAME = 'orla-peripherals-v1.json'
QUOTA_EXPORT_BASENAME = 'orla-quota-v1.json'


class AddonPaths:
    """Injected roots; relative XDG overrides fall back to HOME per XDG rules."""
    def __init__(self, *, home=None, data_home=None, state_home=None):
        try:
            home = os.environ.get('HOME', '') if home is None else os.fspath(home)
            data_home = os.environ.get('XDG_DATA_HOME', '') if data_home is None else os.fspath(data_home)
            state_home = os.environ.get('XDG_STATE_HOME', '') if state_home is None else os.fspath(state_home)
            if any(type(p) is not str for p in (home, data_home, state_home)):
                raise AddonError('type')
            if not home or not Path(home).is_absolute():
                raise AddonError('file')
        except AddonError:
            raise
        except (TypeError, ValueError):
            raise AddonError('file') from None
        self.home = io.input_path(home)
        self.data_home = (io.input_path(data_home) if data_home and Path(data_home).is_absolute()
                          else self.home / '.local/share')
        self.state_home = (io.input_path(state_home) if state_home and Path(state_home).is_absolute()
                           else self.home / '.local/state')
        self.store = self.data_home / 'orla-desktop/addons'


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _digest(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise AddonError('hash')
    return value


def inspect_addon(*, file) -> dict:
    """Validate a chosen local package; SHA is of the original bytes."""
    data = io.read_input(file)
    return dict(sha256=_hash(data), manifest=f.parse_manifest(data))


def pack_addon(*, file, output_dir) -> dict:
    """Canonical artifact, 0600; exclusive publication, never overwrite."""
    manifest = f.parse_manifest(io.read_input(file))
    data = f.canonical_manifest_bytes(manifest)
    name = manifest['id'] + '-' + manifest['version'] + '.orla-addon.json'
    with io.Directory(output_dir, create=True) as directory:
        directory.publish(name, data)
    return dict(file=str(directory.path / name), sha256=_hash(data), manifest=manifest)


def _empty():
    return dict(formatVersion=f.FORMAT_VERSION, generation=secrets.token_hex(16),
                entries=[], artifacts=[])


def _validate_registry(value):
    r = f.object_fields(value, ('formatVersion', 'generation', 'entries', 'artifacts'))
    if r['formatVersion'] != f.FORMAT_VERSION:
        raise AddonError('state')
    f.text(r['generation'], 32, r'[0-9a-f]{32}')
    if type(r['entries']) is not list or type(r['artifacts']) is not list:
        raise AddonError('state')
    if len(r['entries']) > MAX_ADDONS or len(r['artifacts']) > MAX_ARTIFACTS:
        raise AddonError('state')
    for digest in r['artifacts']:
        _digest(digest)
    if len(set(r['artifacts'])) != len(r['artifacts']):
        raise AddonError('state')
    ids, enabled = set(), 0
    for e in r['entries']:
        f.object_fields(e, ('id', 'sha256', 'previousSha256', 'enabled'))
        f.text(e['id'], 120, f.ID_PATTERN)
        _digest(e['sha256'])
        if e['previousSha256'] is not None:
            _digest(e['previousSha256'])
            if e['previousSha256'] == e['sha256']:
                raise AddonError('state')
        if (e['id'] in ids or type(e['enabled']) is not bool or e['sha256'] not in r['artifacts']
                or (e['previousSha256'] is not None and e['previousSha256'] not in r['artifacts'])):
            raise AddonError('state')
        ids.add(e['id'])
        enabled += e['enabled']
    # One active addon per renderer; Session.verify checks renderers with manifests.
    if enabled > len(f.RENDERERS):
        raise AddonError('state')
    return r


def _listing(registry, manifests):
    return dict(generation=registry['generation'], addons=[dict(
        manifest=manifests[e['sha256']], sha256=e['sha256'],
        previousSha256=e['previousSha256'], enabled=e['enabled'])
        for e in sorted(registry['entries'], key=lambda e: e['id'])])


class _Session:
    def __init__(self, directory):
        self.directory = directory
        self.committed_generation = None
        self.registry_pin, self.objects = None, None
        self.pins, self.manifests = {}, {}
        try:
            self.registry_pin = io.PinnedFile(directory, 'registry.json')
            self.raw = self.registry_pin.data
            try:
                self.registry = _validate_registry(f.strict_json(self.raw))
            except AddonError:
                raise AddonError('state') from None
            self.objects = io.Directory(directory.path / 'objects', private=True)
            self.verify()
        except BaseException:
            self.close()
            raise

    def verify(self):
        self.registry_pin.check()
        if self.registry_pin.data != self.raw:
            raise AddonError('drift')
        if self.directory.names(3) != {'.lock', 'registry.json', 'objects'}:
            raise AddonError('state')
        if self.objects.names(MAX_ARTIFACTS) != {d + '.json' for d in self.registry['artifacts']}:
            raise AddonError('state')
        for digest in self.registry['artifacts']:
            if digest not in self.pins:
                pin = io.PinnedFile(self.objects, digest + '.json')
                self.pins[digest] = pin
                if _hash(pin.data) != digest:
                    raise AddonError('hash')
                self.manifests[digest] = f.parse_manifest(pin.data)
            self.pins[digest].check()
        if sum(len(p.data) for p in self.pins.values()) > MAX_STORAGE_BYTES:
            raise AddonError('limit')
        renderers = set()
        for entry in self.registry['entries']:
            renderer = self.manifests[entry['sha256']]['renderer']
            for digest in (entry['sha256'], entry['previousSha256']):
                if digest is not None and (self.manifests[digest]['id'] != entry['id']
                                           or self.manifests[digest]['renderer'] != renderer):
                    raise AddonError('state')
            if entry['enabled']:
                if renderer in renderers:
                    raise AddonError('state')
                renderers.add(renderer)
        self.objects.check()
        self.directory.check()

    def commit(self):
        self.verify()
        self.registry['generation'] = secrets.token_hex(16)
        _validate_registry(self.registry)
        raw = f.json_bytes(self.registry)
        try:
            self.directory.publish('registry.json', raw, replace=True)
        except AddonError as error:
            if error.published:
                self.committed_generation = self.registry['generation']
                error.committed = True
                error.generation = self.registry['generation']
            raise
        self.committed_generation = self.registry['generation']
        self.registry_pin.close()
        self.registry_pin = io.PinnedFile(self.directory, 'registry.json')
        self.raw = raw
        self.verify()

    def result(self):
        self.verify()
        return _listing(self.registry, self.manifests)

    def close(self):
        for pin in self.pins.values():
            pin.close()
        if self.registry_pin is not None:
            self.registry_pin.close()
        if self.objects is not None:
            self.objects.close()


@contextmanager
def _session(paths, *, write=False):
    if not isinstance(paths, AddonPaths):
        raise AddonError('type')
    try:
        directory = io.Directory(paths.store, create=write, private=True)
    except AddonError as error:
        if error.code == 'missing' and not write:
            yield None
            # A concurrent first install cannot publish a nonempty stale response.
            try:
                with io.Directory(paths.store, private=True):
                    raise AddonError('drift')
            except AddonError as check:
                if check.code != 'missing':
                    raise
            return
        raise
    session = None
    try:
        # The store is private; its shared Orla data parent only needs to be closed to other accounts.
        with directory, io.Directory(paths.store.parent) as parent:
            with directory.file('.lock', create=write) as lock:
                try:
                    fcntl.flock(lock, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise AddonError('busy') from None
                try:
                    if os.fstat(lock).st_size != 0:
                        raise AddonError('state')
                    names = directory.names(3)
                    if write and 'registry.json' not in names:
                        if not names <= {'.lock', 'objects'}:
                            raise AddonError('state')
                        with io.Directory(paths.store / 'objects', create=True, private=True) as objects:
                            if objects.names(0):
                                raise AddonError('state')
                        directory.publish('registry.json', f.json_bytes(_empty()))
                    session = _Session(directory)
                    try:
                        yield session
                        session.verify()
                        parent.check()
                        directory.check_file('.lock', lock)
                        if os.fstat(lock).st_size != 0:
                            raise AddonError('state')
                    finally:
                        session.close()
                except OSError:
                    raise AddonError('io') from None
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
    except AddonError as error:
        if session is not None and session.committed_generation is not None:
            error.committed = True
            error.generation = session.committed_generation
        raise


def list_addons(*, paths: AddonPaths) -> dict:
    """Bounded package metadata and consent only; never opens producer state."""
    with _session(paths) as session:
        return session.result() if session else dict(generation=None, addons=[])


def install_addon(*, paths: AddonPaths, file, expected_sha256: str) -> dict:
    """Install/update by independently approved raw hash; always disable consent."""
    _digest(expected_sha256)
    data = io.read_input(file)
    if _hash(data) != expected_sha256:
        raise AddonError('hash')
    manifest = f.parse_manifest(data)
    with _session(paths, write=True) as session:
        registry = session.registry
        entry = next((e for e in registry['entries'] if e['id'] == manifest['id']), None)
        if entry is None and len(registry['entries']) == MAX_ADDONS:
            raise AddonError('limit')
        # An update cannot move an addon to another module.
        if entry is not None and session.manifests[entry['sha256']]['renderer'] != manifest['renderer']:
            raise AddonError('format')
        if expected_sha256 not in registry['artifacts']:
            if (len(registry['artifacts']) == MAX_ARTIFACTS
                    or sum(len(p.data) for p in session.pins.values()) + len(data) > MAX_STORAGE_BYTES):
                raise AddonError('limit')
            with io.Directory(paths.store / 'objects', private=True) as objects:
                objects.publish(expected_sha256 + '.json', data)
            registry['artifacts'].append(expected_sha256)
        # Known immutable artifacts can be reused only after external hash approval
        # and complete closure/content validation by _session. Never adopt unknowns.
        if entry is None:
            registry['entries'].append(dict(id=manifest['id'], sha256=expected_sha256,
                                           previousSha256=None, enabled=False))
        else:
            if entry['sha256'] != expected_sha256:
                entry['previousSha256'] = entry['sha256']
                entry['sha256'] = expected_sha256
            entry['enabled'] = False
        session.commit()
        return session.result()


def _change(paths, addon_id, expected_current_sha256, action):
    f.text(addon_id, 120, f.ID_PATTERN)
    _digest(expected_current_sha256)
    with _session(paths, write=True) as session:
        entry = next((e for e in session.registry['entries'] if e['id'] == addon_id), None)
        if entry is None:
            raise AddonError('not_found')
        if entry['sha256'] != expected_current_sha256:
            raise AddonError('hash')
        if action == 'enable':
            # Enabling replaces only the active addon of the same module.
            renderer = session.manifests[entry['sha256']]['renderer']
            for other in session.registry['entries']:
                if other is entry:
                    other['enabled'] = True
                elif session.manifests[other['sha256']]['renderer'] == renderer:
                    other['enabled'] = False
        elif action == 'disable':
            entry['enabled'] = False
        elif action == 'remove':
            # Artifacts remain inert within the 128-object lifetime budget. No
            # config/profile is read or rewritten and no unknown file is adopted.
            session.registry['entries'].remove(entry)
        elif action == 'rollback':
            if entry['previousSha256'] is None:
                raise AddonError('no_previous')
            entry['sha256'], entry['previousSha256'] = entry['previousSha256'], entry['sha256']
            entry['enabled'] = False
        session.commit()
        return session.result()


def enable_addon(*, paths: AddonPaths, addon_id: str, expected_current_sha256: str) -> dict:
    return _change(paths, addon_id, expected_current_sha256, 'enable')


def disable_addon(*, paths: AddonPaths, addon_id: str, expected_current_sha256: str) -> dict:
    return _change(paths, addon_id, expected_current_sha256, 'disable')


def remove_addon(*, paths: AddonPaths, addon_id: str, expected_current_sha256: str) -> dict:
    return _change(paths, addon_id, expected_current_sha256, 'remove')


def rollback_addon(*, paths: AddonPaths, addon_id: str, expected_current_sha256: str) -> dict:
    return _change(paths, addon_id, expected_current_sha256, 'rollback')


def _snapshot_base(generation):
    return dict(status='missing', generatedAt=None, source=None, producerVersion=None,
        limited=False, devices=[], generatedAtMs=None, expiresAtMs=None, leaseMs=None,
        addon=dict(id=None, sha256=None, enabled=False, generation=generation,
                   producerNamespace=None, reason='not_installed', errorCode=None))


def _project_export(record, result, now_ms):
    generated, expires = record['generatedAtMs'], record['expiresAtMs']
    lease = 3000 * record['intervalSeconds']
    result.update(generatedAt=generated / 1000.0, generatedAtMs=generated,
                  expiresAtMs=expires, leaseMs=lease, source='addon',
                  producerVersion=record['producerVersion'])
    if now_ms < generated or now_ms >= expires:
        result.update(status='stale', limited=True)
        result['addon']['reason'] = 'future' if now_ms < generated else 'expired'
        return result
    counts = {kind: sum(d['kind'] == kind for d in record['devices']) for kind in f.KINDS}
    ordinals = {kind: 0 for kind in f.KINDS}
    for d in record['devices']:
        observed = d['observedAtMs']
        time_valid = observed is not None and observed <= generated and observed <= now_ms
        stale = (not d['present'] or d['stale'] or not time_valid
                 or now_ms - observed >= lease)
        confirmed = not stale
        b = d['battery']
        kind = d['kind']
        case_only = (kind == 'earbuds' and any(c['label'] == 'case' for c in d['components'])
                     and not any(c['label'] in ('left', 'right') and c['percent'] is not None
                                 for c in d['components']))
        aggregate_confirmed = confirmed and not case_only
        ordinals[kind] += 1
        # Views translate generic kinds; no producer names or persistent identity.
        name = kind + (' ' + str(ordinals[kind]) if counts[kind] > 1 else '')
        result['devices'].append(dict(name=name, kind=kind,
            percent=b['percent'] if aggregate_confirmed else None,
            level=b['level'] if aggregate_confirmed else None,
            charging=b['charging'] if aggregate_confirmed else 'unknown',
            estimated=aggregate_confirmed and b['estimated'], stale=stale, present=d['present'],
            observedAt=observed / 1000.0 if time_valid else None,
            observedAtMs=observed if time_valid else None,
            components=[dict(label=c['label'], percent=c['percent'] if confirmed else None,
                             charging=c['charging'] if confirmed else 'unknown')
                        for c in d['components']]))
        result['limited'] |= stale
    ready = any(d['percent'] is not None or d['level'] is not None
                or any(c['percent'] is not None for c in d['components'])
                for d in result['devices'])
    result['status'] = ('ready' if ready else 'stale' if any(d['stale'] for d in result['devices'])
                        else 'unknown')
    result['addon']['reason'] = result['status']
    return result


def snapshot_peripherals(*, paths: AddonPaths, now_ms: int | None = None,
                         profile_enabled: bool = True) -> dict:
    """Legacy peripheral shape + addon/generation and explicit millisecond leases.

    Registry errors raise AddonError; missing/unsafe/malformed passive exports
    yield unavailable snapshots with finite codes. No enabled addon => zero
    producer directory or export opens. Caller must also gate queued UI results.
    """
    if type(profile_enabled) is not bool:
        raise AddonError('type')
    if now_ms is None:
        import time
        now_ms = time.time_ns() // 1000000
    f.integer(now_ms, 1, f.MAX_SAFE_INTEGER)
    with _session(paths) as session:
        result = _snapshot_base(session.registry['generation'] if session else None)
        if not session or not session.registry['entries']:
            return result
        if not any(session.manifests[e['sha256']]['renderer'] == 'peripheral-battery'
                   for e in session.registry['entries']):
            return result
        result['addon']['reason'] = 'disabled'
        active = next((e for e in session.registry['entries'] if e['enabled']
                       and session.manifests[e['sha256']]['renderer'] == 'peripheral-battery'), None)
        if active is None:
            return result
        namespace = session.manifests[active['sha256']]['source']['namespace']
        result['addon'].update(id=active['id'], sha256=active['sha256'], enabled=True,
                               producerNamespace=namespace)
        if not profile_enabled:
            result['addon']['reason'] = 'profile_hidden'
            return result
        try:
            with io.Directory(paths.state_home / namespace, private=True) as producer:
                with io.Directory(producer.path / 'exports', private=True) as directory:
                    with io.PinnedFile(directory, EXPORT_BASENAME) as exported:
                        record = f.parse_export(exported.data, producer_namespace=namespace)
                        _project_export(record, result, now_ms)
                        producer.check()
                        session.verify()
        except AddonError as error:
            # Do not swallow registry/package drift as a producer parsing error.
            session.verify()
            result = _snapshot_base(session.registry['generation'])
            result['addon'].update(id=active['id'], sha256=active['sha256'], enabled=True,
                producerNamespace=namespace, errorCode=error.code,
                reason='export_missing' if error.code == 'missing' else 'export_invalid')
            if error.code != 'missing':
                result['status'] = 'invalid'
        return result


def _quota_base(generation):
    return dict(status='missing', generatedAt=None, source=None, producerVersion=None,
        limited=False, providers=[], generatedAtMs=None, expiresAtMs=None, leaseMs=None,
        addon=dict(id=None, sha256=None, enabled=False, generation=generation,
                   producerNamespace=None, reason='not_installed', errorCode=None))


def _project_quota(record, result, now_ms):
    generated, expires = record['generatedAtMs'], record['expiresAtMs']
    lease = 3000 * record['intervalSeconds']
    result.update(generatedAt=generated / 1000.0, generatedAtMs=generated,
                  expiresAtMs=expires, leaseMs=lease, source='addon',
                  producerVersion=record['producerVersion'])
    if now_ms < generated or now_ms >= expires:
        result.update(status='stale', limited=True)
        result['addon']['reason'] = 'future' if now_ms < generated else 'expired'
        return result
    for provider in record['providers']:
        observed = provider['observedAtMs']
        time_valid = observed is not None and observed <= generated and observed <= now_ms
        old = time_valid and now_ms - observed >= lease
        # Only a fresh, ready observation confirms usage; zero stays a known value.
        confirmed = provider['state'] == 'ready' and time_valid and not old
        stale = provider['state'] == 'stale' or (provider['state'] == 'ready' and not confirmed)
        result['providers'].append(dict(id=provider['id'],
            state='ready' if confirmed else 'stale' if stale else provider['state'],
            observedAt=observed / 1000.0 if time_valid else None,
            observedAtMs=observed if time_valid else None,
            windows=[dict(key=w['key'], usedPercent=w['usedPercent'] if confirmed else None,
                          windowMinutes=w['windowMinutes'], resetAtMs=w['resetAtMs'])
                     for w in provider['windows']]))
        result['limited'] |= not confirmed
    ready = any(w['usedPercent'] is not None for p in result['providers'] for w in p['windows'])
    result['status'] = ('ready' if ready else 'stale' if any(p['state'] == 'stale' for p in result['providers'])
                        else 'unknown')
    result['addon']['reason'] = result['status']
    return result


def snapshot_quota(*, paths: AddonPaths, now_ms: int | None = None, profile_enabled: bool = True) -> dict:
    """Active quota-usage addon only; same lease and failure rules as batteries.

    No enabled quota addon => zero producer directory or export opens.
    """
    if type(profile_enabled) is not bool:
        raise AddonError('type')
    if now_ms is None:
        import time
        now_ms = time.time_ns() // 1000000
    f.integer(now_ms, 1, f.MAX_SAFE_INTEGER)
    with _session(paths) as session:
        result = _quota_base(session.registry['generation'] if session else None)
        if not session or not any(session.manifests[e['sha256']]['renderer'] == 'quota-usage'
                                  for e in session.registry['entries']):
            return result
        result['addon']['reason'] = 'disabled'
        active = next((e for e in session.registry['entries'] if e['enabled']
                       and session.manifests[e['sha256']]['renderer'] == 'quota-usage'), None)
        if active is None:
            return result
        namespace = session.manifests[active['sha256']]['source']['namespace']
        result['addon'].update(id=active['id'], sha256=active['sha256'], enabled=True,
                               producerNamespace=namespace)
        if not profile_enabled:
            result['addon']['reason'] = 'profile_hidden'
            return result
        try:
            with io.Directory(paths.state_home / namespace, private=True) as producer:
                with io.Directory(producer.path / 'exports', private=True) as directory:
                    with io.PinnedFile(directory, QUOTA_EXPORT_BASENAME) as exported:
                        record = f.parse_quota_export(exported.data, producer_namespace=namespace)
                        _project_quota(record, result, now_ms)
                        producer.check()
                        session.verify()
        except AddonError as error:
            session.verify()
            result = _quota_base(session.registry['generation'])
            result['addon'].update(id=active['id'], sha256=active['sha256'], enabled=True,
                producerNamespace=namespace, errorCode=error.code,
                reason='export_missing' if error.code == 'missing' else 'export_invalid')
            if error.code != 'missing':
                result['status'] = 'invalid'
        return result
