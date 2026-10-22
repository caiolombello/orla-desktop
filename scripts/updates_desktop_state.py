"""Local reference and history. This module never imports Qt or transport."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
import re
import secrets
from scripts.updates_contract import SOURCE, parse_version, validate_result, utc_time
LIMIT = 16 * 1024

def reject_constant(value):
    raise ValueError('nonfinite')


def strict_json(raw):

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    if len(raw) > LIMIT:
        raise ValueError('oversized document')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject_constant)

def read_regular(path):
    parent = _parent_fd(Path(path))
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError('unsafe file')
        raw = os.read(fd, LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError('oversized document')
        return raw
    finally:
        os.close(fd)

def _dock_reference(raw, role, origin):
    plugin = strict_json(raw)['KPlugin']
    if plugin['Id'] != 'org.caiodock.dock' or parse_version(plugin.get('Version')) is None:
        return None
    return dict(role=role, component='dock', origin=origin, version=plugin['Version'], commit=None, digest=hashlib.sha256(raw).hexdigest())

def source_reference(root):
    try:
        path = Path(root) / 'package/metadata.json'
        if path.parent.is_symlink():
            return None
        return _dock_reference(read_regular(path), 'source', 'source-metadata')
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return None

def installed_dock(data_home):
    """Passive read of the dock installed for this user: (status, reference).

    Only the user's own package directory is read. A system-wide package,
    the copy Plasma has loaded and the publisher remain unverified.
    """
    path = Path(data_home) / 'plasma/plasmoids/org.caiodock.dock/metadata.json'
    try:
        raw = read_regular(path)
    except FileNotFoundError:
        return ('absent', None)
    except (OSError, ValueError):
        return ('invalid', None)
    try:
        reference = _dock_reference(raw, 'installed', 'user-plasmoid-metadata')
    except (ValueError, KeyError, TypeError, RecursionError):
        reference = None
    return ('found', reference) if reference else ('invalid', None)
CACHE_SCHEMA = 'orla-updates-desktop-cache-0.1'
PREF_SCHEMA = 'orla-updates-preferences-0.1'

def valid_reference(value):
    if not isinstance(value, dict) or set(value) != {'role', 'component', 'origin', 'version', 'commit', 'digest'}:
        return False
    if parse_version(value['version']) is None:
        return False
    if not isinstance(value['digest'], str) or not re.fullmatch('[0-9a-f]{64}', value['digest']):
        return False
    commit = value['commit']
    if commit is not None and (not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit)):
        return False
    kind = (value['role'], value['component'], value['origin'])
    if kind in (('source', 'dock', 'source-metadata'), ('installed', 'dock', 'user-plasmoid-metadata')):
        return commit is None
    return kind == ('bundle', 'workspace', 'verified-manifest')

def history_key(reference, channel):
    return dict(schema=CACHE_SCHEMA, source=SOURCE, channel=channel, reference=dict(reference))

def validate_record(record, key):
    if not isinstance(record, dict) or set(record) != {'attemptedAt', 'completedAt', 'result'}:
        raise ValueError('record')
    attempted = utc_time(record['attemptedAt'])
    if record['completedAt'] is None:
        if record['result'] is not None:
            raise ValueError('unfinished result')
    else:
        completed = utc_time(record['completedAt'])
        data = validate_result(record['result'], key['channel'], key['reference']['version'])
        if data['checked_at'] != record['attemptedAt'] or completed < attempted:
            raise ValueError('time order')
    return record

def validate_history(value):
    if not isinstance(value, dict) or set(value) != {'schema', 'channels'} or value['schema'] != CACHE_SCHEMA:
        raise ValueError('cache schema')
    channels = value['channels']
    if not isinstance(channels, dict) or not set(channels) <= {'stable', 'beta'}:
        raise ValueError('channels')
    for channel, entry in channels.items():
        if not isinstance(entry, dict) or set(entry) != {'key', 'attempt', 'lastCompleted'}:
            raise ValueError('entry')
        key = entry['key']
        if not isinstance(key, dict) or set(key) != {'schema', 'source', 'channel', 'reference'}:
            raise ValueError('key')
        if key['schema'] != CACHE_SCHEMA or key['source'] != SOURCE or key['channel'] != channel or (not valid_reference(key['reference'])):
            raise ValueError('provenance')
        validate_record(entry['attempt'], key)
        if entry['lastCompleted'] is not None:
            validate_record(entry['lastCompleted'], key)
            if entry['lastCompleted']['result']['status'] not in ('update_available', 'up_to_date', 'no_release'):
                raise ValueError('completion')
            if utc_time(entry['lastCompleted']['attemptedAt']) > utc_time(entry['attempt']['attemptedAt']):
                raise ValueError('history order')
    return channels

def _parent_fd(path, create=False):
    """Walk with openat/O_NOFOLLOW, never resolve a symlink in a cache path."""
    if not path.is_absolute():
        raise ValueError('absolute path required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parent.parts[1:]:
            if part in ('.', '..'):
                raise ValueError('unsafe parent')
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            info = os.fstat(next_fd)
            # Root-owned sticky /tmp is safe above the private user directory.
            unsafe = info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and (not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)))
            if unsafe:
                os.close(next_fd)
                raise ValueError('unsafe parent')
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise

def _read_owned(path):
    parent = _parent_fd(path)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError('unsafe leaf')
            return strict_json(os.read(fd, LIMIT + 1))
        finally:
            os.close(fd)
    finally:
        os.close(parent)

def _atomic_write(path, value):
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    if len(raw) > LIMIT:
        raise ValueError('cache limit')
    parent = _parent_fd(path, True)
    temporary = '.updates-' + secrets.token_hex(12)
    try:
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise ValueError('unsafe leaf')
        except FileNotFoundError:
            pass
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass
    finally:
        os.close(parent)

class Store:

    def __init__(self, root=None):
        home = Path.home()

        def xdg(name, default):
            value = os.environ.get(name, '')
            path = Path(value)
            return path if value and path.is_absolute() else home / default
        config = Path(root) / 'config' if root is not None else xdg('XDG_CONFIG_HOME', '.config')
        cache = Path(root) / 'cache' if root is not None else xdg('XDG_CACHE_HOME', '.cache')
        self.data = Path(root) / 'data' if root is not None else xdg('XDG_DATA_HOME', '.local/share')
        self.preferences = config / 'orla/updates.json'
        self.cache = cache / 'orla/updates-desktop.json'
        self.blocked = set()

    def load(self):
        channels = {}
        channel = 'stable'
        warning = ''
        for path in (self.preferences, self.cache):
            try:
                value = _read_owned(path)
                if path == self.preferences:
                    if not isinstance(value, dict) or set(value) != {'schema', 'channel'} or value['schema'] != PREF_SCHEMA or (value['channel'] not in ('stable', 'beta')):
                        raise ValueError('preference')
                    channel = value['channel']
                else:
                    channels = validate_history(value)
            except FileNotFoundError:
                pass
            except (OSError, ValueError, KeyError, TypeError, RecursionError):
                self.blocked.add(path)
                warning = 'read'
        return (channels, channel, warning)

    def installed_dock(self):
        return installed_dock(self.data)

    def save_preference(self, channel):
        if self.preferences in self.blocked:
            raise ValueError('invalid existing preference')
        if channel not in ('stable', 'beta'):
            raise ValueError('channel')
        _atomic_write(self.preferences, dict(schema=PREF_SCHEMA, channel=channel))

    def save_history(self, channels):
        if self.cache in self.blocked:
            raise ValueError('invalid existing cache')
        value = dict(schema=CACHE_SCHEMA, channels=channels)
        validate_history(value)
        _atomic_write(self.cache, value)
