#!/usr/bin/env python3
"""Local, pinned Workspace lifecycle manager. No Qt or desktop IPC imports."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import ctypes
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import types
import uuid
import zipfile

sys.dont_write_bytecode = True
PACKAGE_SHA256 = '1ca6b6051f37f7cf44974d555fafa1171181b23b2b9cddb8a6849a937d9a9908'
SCHEMA = 'orla-workspace-install-0.1'


class InstallError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _need(condition, code='ownership_drift'):
    if not condition:
        raise InstallError(code)


def _absolute(path):
    _need(isinstance(path, Path) and path.is_absolute(), 'invalid_paths')
    value = str(path)
    _need(value != '/' and not value.startswith('//') and '..' not in path.parts
          and len(os.fsencode(value)) < 3500 and len(path.parts) < 60
          and all(len(os.fsencode(p)) <= 220 for p in path.parts)
          and not any(ord(c) < 32 or ord(c) == 127 for c in value), 'invalid_paths')
    return path


@dataclass(frozen=True)
class InstallPaths:
    home: Path
    data_home: Path
    state_home: Path
    config_home: Path

    def __post_init__(self):
        for path in (self.home, self.data_home, self.state_home, self.config_home):
            _absolute(path)
        roots = (self.base, self.state, self.home / '.local/bin', self.data_home / 'applications')
        for a in roots:
            for b in roots:
                _need(a == b or a not in b.parents, 'overlapping_roots')
        _need(not any(self.config_home == r or r in self.config_home.parents for r in roots), 'overlapping_roots')

    @property
    def base(self):
        return self.data_home / 'orla-desktop/workspace'

    @property
    def state(self):
        return self.state_home / 'orla/workspace-install'

    @classmethod
    def from_environment(cls, environment=None):
        env = os.environ if environment is None else environment
        home = _absolute(Path(env.get('HOME', '')))
        def xdg(name, default):
            value = env.get(name, '')
            return Path(value) if value and Path(value).is_absolute() else home / default
        return cls(home, xdg('XDG_DATA_HOME', '.local/share'),
                   xdg('XDG_STATE_HOME', '.local/state'), xdg('XDG_CONFIG_HOME', '.config'))


def _roots(paths):
    return {name: str(getattr(paths, name)) for name in ('home', 'data_home', 'state_home', 'config_home')}


def _dirpin(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid]


@contextmanager
def _directory(path, *, create=False):
    """Open every component without following symlinks, and recheck relations."""
    fds, relations = [], []
    primary = None
    try:
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(fd)
        for part in path.parts[1:]:
            parent = fd
            try:
                before = os.stat(part, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o755, dir_fd=parent)
                os.fsync(parent)
                before = os.stat(part, dir_fd=parent, follow_symlinks=False)
            _need(stat.S_ISDIR(before.st_mode) and before.st_uid in (0, os.getuid())
                  and (not before.st_mode & 0o022 or before.st_uid == 0 and before.st_mode & stat.S_ISVTX), 'unsafe_parent')
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            fds.append(fd)
            pin = _dirpin(before)
            _need(_dirpin(os.fstat(fd)) == pin, 'parent_changed')
            relations.append((parent, part, fd, pin))
        yield fd
        for parent, part, fd, pin in relations:
            _need(_dirpin(os.stat(part, dir_fd=parent, follow_symlinks=False)) == pin
                  and _dirpin(os.fstat(fd)) == pin, 'parent_changed')
    except BaseException as exc:
        primary = exc
        raise
    finally:
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                if primary is None:
                    raise


def _exists(path):
    with _directory(path.parent) as fd:
        try:
            os.stat(path.name, dir_fd=fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False


def _filepin(info):
    return (*_dirpin(info), info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(path, mode=None, limit=8 << 20):
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            _need(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1
                  and before.st_size <= limit and (mode is None or stat.S_IMODE(before.st_mode) == mode), 'unsafe_file')
            data = stream.read(limit + 1)
            _need(len(data) == before.st_size and _filepin(os.fstat(stream.fileno())) == _filepin(before)
                  and _filepin(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == _filepin(before), 'file_changed')
            return data


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def _document(path):
    def unique(pairs):
        result = dict(pairs)
        _need(len(result) == len(pairs), 'invalid_record')
        return result
    try:
        return json.loads(_read(path, 0o600), object_pairs_hook=unique,
                          parse_constant=lambda _: _need(False, 'invalid_record'))
    except (ValueError, UnicodeError, RecursionError):
        raise InstallError('invalid_record') from None


def _write(path, data, mode=0o600):
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    with _directory(path.parent) as parent:
        fd = os.open(temporary.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
        primary = None
        def check_temporary():
            info = os.fstat(fd)
            _need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                  and _filepin(os.stat(temporary.name, dir_fd=parent, follow_symlinks=False)) == _filepin(info), 'file_changed')
        try:
            # Keep the exclusively created inode open through publication/cleanup.
            with os.fdopen(fd, 'wb', buffering=0, closefd=False) as stream:
                os.fchmod(stream.fileno(), mode)
                remaining = memoryview(data)
                while remaining:
                    written = stream.write(remaining)
                    _need(written is not None and 0 < written <= len(remaining), 'record_write_failed')
                    remaining = remaining[written:]
                stream.flush()
                os.fsync(stream.fileno())
            check_temporary()
            _need(os.fstat(fd).st_size == len(data), 'record_write_failed')
            _move(temporary, path)
        except BaseException as exc:
            primary = exc
            try:
                try:
                    os.stat(temporary.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    check_temporary()
                    os.unlink(temporary.name, dir_fd=parent)
                    os.fsync(parent)
            except BaseException:
                if hasattr(primary, 'add_note'):
                    primary.add_note('Record temporary cleanup failed; unproven output was not removed.')
            raise
        finally:
            try:
                os.close(fd)
            except OSError:
                if primary is None:
                    raise


def _atomic(path, value):
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    _write(temporary, _json(value))
    with _directory(path.parent) as fd:
        os.replace(temporary.name, path.name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)


def _package():
    path = Path(__file__).absolute().parent / 'package.py'
    data = _read(path, 0o644, 2 << 20)
    _need(hashlib.sha256(data).hexdigest() == PACKAGE_SHA256, 'verifier_drift')
    module = types.ModuleType('_orla_workspace_pinned_package')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def _service(value):
    _need(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}\.service', value), 'invalid_service')
    return value


def _parents(path):
    result = {}
    for parent in reversed((path, *path.parents)):
        with _directory(parent) as fd:
            result[str(parent)] = _dirpin(os.fstat(fd))
    return result


def _check_parents(records, *, missing=False):
    for text, pin in records.items():
        path = _absolute(Path(text)) if text != '/' else Path('/')
        try:
            with _directory(path) as fd:
                _need(_dirpin(os.fstat(fd)) == pin, 'parent_drift')
        except FileNotFoundError:
            _need(missing, 'parent_drift')


def _anchor(paths):
    value = _document(paths.state / 'identity.json')
    _need(type(value) is dict and set(value) == {'schema', 'roots', 'uid', 'parents', 'lock'} and value['schema'] == SCHEMA, 'unsupported_schema')
    _need(value['roots'] == _roots(paths) and value['uid'] == os.getuid(), 'root_drift')
    _check_parents(value['parents'])
    _check_file(paths.state / 'use.lock', value['lock'])
    return value


def _file(path):
    data = _read(path)
    with _directory(path.parent) as fd:
        info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
    return dict(pin=_dirpin(info), size=len(data), sha256=hashlib.sha256(data).hexdigest())


def _check_file(path, record):
    _need(_file(path) == record, 'file_drift')


def _initialize(paths):
    # Shared ancestors remain in place on uninstall; no foreign tree is adopted.
    for path in (paths.base.parent, paths.home / '.local/bin', paths.data_home / 'applications', paths.state.parent):
        with _directory(path, create=True):
            pass
    _need(not _exists(paths.state), 'unreceipted_state')
    with _directory(paths.state.parent) as parent:
        os.mkdir(paths.state.name, 0o700, dir_fd=parent)
        os.fsync(parent)
    for name in ('receipts', 'transactions'):
        with _directory(paths.state / name, create=True):
            pass
    _write(paths.state / 'use.lock', b'')
    parents = {}
    for path in (paths.base.parent, paths.home / '.local/bin', paths.data_home / 'applications',
                 paths.state / 'receipts', paths.state / 'transactions'):
        parents.update(_parents(path))
    value = dict(schema=SCHEMA, roots=_roots(paths), uid=os.getuid(), parents=parents,
                 lock=_file(paths.state / 'use.lock'))
    _write(paths.state / 'identity.json', _json(value))


@contextmanager
def _locked(paths, *, shared=False, initialize=False):
    if not paths.state.exists():
        _need(initialize, 'not_installed')
        _initialize(paths)
    _anchor(paths)
    with _directory(paths.state) as parent:
        fd = os.open('use.lock', os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        primary = None
        try:
            try:
                fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
            except BlockingIOError:
                raise InstallError('busy_close_workspace') from None
            _anchor(paths)
            yield fd
        except BaseException as exc:
            primary = exc
            raise
        finally:
            try:
                os.close(fd)
            except OSError:
                if primary is None:
                    raise


def _selection(value):
    if value is None:
        return None
    _need(type(value) is dict and set(value) == {'schema', 'current', 'previous', 'receipt'} and value['schema'] == SCHEMA, 'unsupported_schema')
    for key in ('current', 'previous'):
        _need((value[key] is None and key == 'previous') or
              (type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key])), 'invalid_selector')
    _need(type(value['receipt']) is str and re.fullmatch('[0-9a-f]{32}', value['receipt']), 'invalid_selector')
    return value


def _selector(paths):
    path = paths.state / 'current.json'
    return _selection(_document(path)) if _exists(path) else None


def _location(paths, key):
    if key == 'controller':
        return paths.home / '.local/bin/orla-workspacectl'
    if key == 'launcher':
        return paths.home / '.local/bin/orla-workspace'
    if key == 'desktop':
        return paths.data_home / 'applications/org.orla.Workspace.desktop'
    _need(isinstance(key, str) and not Path(key).is_absolute() and '..' not in Path(key).parts, 'invalid_record')
    return paths.base / key


def _receipt(paths, selection):
    value = _document(paths.state / 'receipts' / (selection['receipt'] + '.json'))
    _need(type(value) is dict and set(value) == {'schema', 'uid', 'roots', 'service', 'generations', 'files', 'directories', 'parents'}
          and value['schema'] == SCHEMA, 'unsupported_schema')
    _need(value['roots'] == _roots(paths) and value['uid'] == os.getuid(), 'root_drift')
    _service(value['service'])
    generations = value['generations']
    _need(type(generations) is dict and set(generations) == {selection['current']} | ({selection['previous']} if selection['previous'] else set()), 'invalid_record')
    expected = {'controller', 'launcher', 'desktop', 'tools/install.py', 'tools/package.py'}
    for digest, manifest in generations.items():
        _need(re.fullmatch('[0-9a-f]{64}', digest) and type(manifest) is dict and manifest.get('schema') == 'orla-workspace-package-0.2', 'unsupported_schema')
        expected.update('versions/' + digest + '/' + name for name in (*_package().PAYLOAD, 'manifest.json'))
    _need(set(value['files']) == expected, 'invalid_record')
    dirs = {'tools', 'versions'}
    for key in expected - {'controller', 'launcher', 'desktop'}:
        dirs.update(str(p) for p in Path(key).parents if str(p) != '.')
    dirs.add('.')
    _need(set(value['directories']) == dirs, 'invalid_record')
    return value


def _verify(paths, selection, *, stages=()):
    receipt = _receipt(paths, selection)
    _check_parents(receipt['parents'])
    for key, pin in receipt['directories'].items():
        path = paths.base if key == '.' else _location(paths, key)
        with _directory(path) as fd:
            _need(_dirpin(os.fstat(fd)) == pin, 'directory_drift')
            expected = {Path(k).name for k in receipt['files'] if k not in ('controller', 'launcher', 'desktop') and str(Path(k).parent) == key}
            expected.update(Path(k).name for k in receipt['directories'] if k != '.' and str(Path(k).parent) == key)
            expected.update(stage.name for stage in stages if stage.parent == path and _exists(stage))
            _need(set(os.listdir(fd)) == expected, 'unknown_children')
    for key, record in receipt['files'].items():
        _check_file(_location(paths, key), record)
    for digest, manifest in receipt['generations'].items():
        package = _package()
        try:
            _need(package.verify_directory(paths.base / 'versions' / digest) == manifest, 'manifest_drift')
        except package.PackageError as exc:
            raise InstallError(exc.code) from None
    return receipt


def _pending(paths):
    path = paths.state / 'pending.json'
    return _document(path) if _exists(path) else None


def _no_pending(paths):
    _need(_pending(paths) is None, 'recovery_required')


def _report(selection):
    return dict(installed=selection is not None, integrity='verified' if selection else 'absent', runtime='unverified',
                nativeValidated=False, current=selection['current'] if selection else None,
                previous=selection['previous'] if selection else None)


def status(paths):
    if not paths.state.exists():
        return _report(None)
    with _locked(paths, shared=True):
        if _transaction(paths):
            return dict(installed=_selector(paths) is not None, integrity='pending', runtime='unverified', nativeValidated=False)
        selection = _selector(paths)
        if selection:
            _verify(paths, selection)
        return _report(selection)


def _desktop_quote(value):
    escaped = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
    return '"' + escaped.replace('\\', '\\\\').replace('%', '%%') + '"'


# This bootstrap executes only the two explicitly pinned local tools. The manager
# revalidates caller roots and its full receipt before any operation or child.
PINNED_LOADER = '''import hashlib,json,os,stat,sys
cfg=json.loads(CONFIG)
def read(path,digest):
 fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:
  for part in path.split('/')[1:-1]:
   s=os.stat(part,dir_fd=fd,follow_symlinks=False)
   if not stat.S_ISDIR(s.st_mode) or s.st_uid not in (0,os.getuid()) or (s.st_mode&0o022 and not(s.st_uid==0 and s.st_mode&stat.S_ISVTX)): raise ValueError('unsafe_parent')
   child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
   os.close(fd);fd=child
  leaf=os.open(path.split('/')[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
  with os.fdopen(leaf,'rb') as f:
   s=os.fstat(f.fileno())
   if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=0o644 or s.st_size>2097152: raise ValueError('tool_file')
   data=f.read(2097153)
   if (lambda v:(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid,v.st_nlink,v.st_size,v.st_mtime_ns,v.st_ctime_ns))(os.fstat(f.fileno()))!=(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns) or hashlib.sha256(data).hexdigest()!=digest: raise ValueError('tool_drift')
  return data
 finally: os.close(fd)
try:
 for path,pin in cfg['parents'].items():
  s=os.lstat(path)
  if [s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid]!=pin: raise ValueError('tool_parent_drift')
 data=read(cfg['manager'],cfg['managerSha256'])
 read(cfg['package'],cfg['packageSha256'])
 globals()['__file__']=cfg['manager']
 exec(compile(data,cfg['manager'],'exec'),globals())
except (OSError,ValueError):
 print(json.dumps({'error':'pinned_tools_unavailable'}));raise SystemExit(1)
'''


def _entrypoints(paths, manager, parents):
    config = dict(manager=str(paths.base / 'tools/install.py'), managerSha256=hashlib.sha256(manager).hexdigest(),
                  package=str(paths.base / 'tools/package.py'), packageSha256=PACKAGE_SHA256, parents=parents)
    code = PINNED_LOADER.replace('CONFIG', repr(json.dumps(config, sort_keys=True)))
    command = [str(_absolute(Path(sys.executable))), '-I', '-B', '-c', code]
    ctl = ('#!/bin/sh\nexec ' + ' '.join(shlex.quote(p) for p in command) + ' "$@"\n').encode()
    wrapper = ('#!/bin/sh\nexec ' + shlex.quote(str(_location(paths, 'controller'))) + ' launch "$@"\n').encode()
    launcher = _desktop_quote(_location(paths, 'launcher'))
    desktop = ('[Desktop Entry]\nType=Application\nName=Sobre e atualizações do Orla\nExec=' +
               launcher + ' --updates\nIcon=preferences-desktop\nTerminal=false\nCategories=Utility;\n' +
               'Actions=Composition;\n\n[Desktop Action Composition]\nName=Composição Orla\nExec=' +
               launcher + '\n').encode()
    return {'controller': ctl, 'launcher': wrapper, 'desktop': desktop}


def _fail(failpoint, name):
    if failpoint is not None:
        failpoint(name)


def _move(source, target):
    """Linux no-replace publication: a concurrent collision is never overwritten."""
    with _directory(source.parent) as src, _directory(target.parent) as dst:
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(src, os.fsencode(source.name), dst, os.fsencode(target.name), 1):
            error = ctypes.get_errno()
            raise InstallError('collision' if error == errno.EEXIST else 'publish_failed')
        os.fsync(src)
        os.fsync(dst)


def _stage_check(path, item, *, missing=False):
    if not item['files'] and not item['directories']:
        _need(missing and not _exists(path), 'unreceipted_stage')
        return
    if item['directories']:
        for key, pin in item['directories'].items():
            node = path if key == '.' else path / key
            try:
                with _directory(node) as fd:
                    _need(_dirpin(os.fstat(fd)) == pin, 'directory_drift')
                    expected = {Path(k).name for k in (*item['files'], *item['directories']) if k != '.' and str(Path(k).parent) == key}
                    actual = set(os.listdir(fd))
                    _need(actual <= expected if missing else actual == expected, 'unknown_children')
            except FileNotFoundError:
                _need(missing, 'directory_drift')
        for key, record in item['files'].items():
            try:
                _check_file(path / key, record)
            except FileNotFoundError:
                _need(missing, 'file_drift')
    else:
        try:
            _check_file(path, item['files']['.'])
        except FileNotFoundError:
            _need(missing, 'file_drift')


def _remove_stage(path, item):
    _stage_check(path, item, missing=True)
    if not item['directories']:
        with _directory(path.parent) as fd:
            if _exists(path):
                os.unlink(path.name, dir_fd=fd)
                os.fsync(fd)
        return
    for key in sorted(item['files'], key=lambda x: (-len(Path(x).parts), x)):
        node = path / key
        try:
            with _directory(node.parent) as fd:
                if _exists(node):
                    _check_file(node, item['files'][key])
                    os.unlink(node.name, dir_fd=fd)
                    os.fsync(fd)
        except FileNotFoundError:
            pass
    for key in sorted(item['directories'], key=lambda x: (-len(Path(x).parts) if x != '.' else 0, x)):
        node = path if key == '.' else path / key
        try:
            with _directory(node.parent) as fd:
                if _exists(node):
                    with _directory(node) as child:
                        _need(_dirpin(os.fstat(child)) == item['directories'][key] and not os.listdir(child), 'directory_drift')
                    os.rmdir(node.name, dir_fd=fd)
                    os.fsync(fd)
        except FileNotFoundError:
            pass


def _build_stage(paths, transaction, target, contents, *, directory=True, failpoint=None):
    source = target.with_name('.workspace-incoming-' + transaction['id'] + '-' + str(len(transaction['stages'])))
    _need(not _exists(target) and not _exists(source), 'collision')
    item = dict(source=str(source), target=str(target), files={}, directories={})
    transaction['stages'].append(item)
    # Creation is journalled immediately. Unrecorded output after a hard crash is
    # refused, never matched by hash and silently adopted.
    def checkpoint():
        _atomic(paths.state / 'pending.json', transaction)
    checkpoint()
    def mkdir(node, key):
        with _directory(node.parent) as parent:
            os.mkdir(node.name, 0o700 if key == '.' else 0o755, dir_fd=parent)
            os.fsync(parent)
            item['directories'][key] = _dirpin(os.stat(node.name, dir_fd=parent, follow_symlinks=False))
        checkpoint()

    def write(node, key, data, mode):
        # Record the created inode while still empty. Caught partial I/O is
        # checkpointed too, without replacing the primary write exception.
        with _directory(node.parent) as parent:
            fd = os.open(node.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
            with os.fdopen(fd, 'wb', buffering=0) as stream:
                os.fchmod(stream.fileno(), mode)
                os.fsync(parent)
                item['files'][key] = _file(node)
                checkpoint()
                _fail(failpoint, 'after_stage_file_create')
                try:
                    remaining = memoryview(data)
                    while remaining:
                        written = stream.write(remaining)
                        _need(written is not None and written > 0, 'stage_write_failed')
                        remaining = remaining[written:]
                    stream.flush()
                    os.fsync(stream.fileno())
                    _fail(failpoint, 'after_stage_write')
                except BaseException as primary:
                    try:
                        stream.flush()
                        item['files'][key] = _file(node)
                        checkpoint()
                    except BaseException:
                        if hasattr(primary, 'add_note'):
                            primary.add_note('Partial stage checkpoint failed; recovery must refuse unproven bytes.')
                    raise
        item['files'][key] = _file(node)
        checkpoint()

    if directory:
        mkdir(source, '.')
        _fail(failpoint, 'after_stage_root')
        directories = {str(p) for name in contents for p in Path(name).parents if str(p) != '.'}
        for name in sorted(directories, key=lambda x: (len(Path(x).parts), x)):
            mkdir(source / name, name)
            _fail(failpoint, 'after_stage_directory')
        for name, (data, mode) in sorted(contents.items()):
            write(source / name, name, data, mode)
    else:
        data, mode = contents['.']
        write(source, '.', data, mode)
    return item


def _generation_contents(verified):
    result = {name: (data, 0o644) for name, data in verified['files'].items()}
    result['manifest.json'] = (verified['manifest_bytes'], 0o644)
    return result


def _new_transaction(operation, old, digest=None):
    return dict(schema=SCHEMA, id=uuid.uuid4().hex, operation=operation, phase='building',
                old=old, new=None, stages=[], digest=digest)


def _commit_intent(paths, transaction, new):
    transaction['new'] = new
    transaction['phase'] = 'ready'
    _write(paths.state / 'transactions' / (transaction['id'] + '.json'), _json(transaction))
    _atomic(paths.state / 'pending.json', transaction)


def _finish(paths, transaction, *, failpoint=None):
    _need(_selector(paths) in (transaction['old'], transaction['new']), 'selector_drift')
    if transaction['operation'] == 'uninstall':
        _remove_owned(paths, transaction, failpoint)
    for index, item in enumerate(transaction['stages']):
        source, target = Path(item['source']), Path(item['target'])
        if _exists(source):
            _stage_check(source, item)
            _need(not _exists(target), 'collision')
            _move(source, target)
        else:
            _stage_check(target, item)
        _fail(failpoint, 'after_publish_' + str(index))
    _fail(failpoint, 'after_publish')
    _need(_selector(paths) in (transaction['old'], transaction['new']), 'selector_drift')
    _fail(failpoint, 'before_selector')
    _need(_selector(paths) in (transaction['old'], transaction['new']), 'selector_drift')
    if transaction['new']:
        _verify(paths, transaction['new'])
    _atomic(paths.state / 'current.json', transaction['new'])
    _fail(failpoint, 'after_selector')
    if transaction['new']:
        _verify(paths, transaction['new'])
    _outcome(paths, transaction, 'committed')
    _atomic(paths.state / 'pending.json', None)
    return _report(transaction['new'])


def _make_receipt(paths, transaction, service, verified, digest, *, old_receipt=None):
    if old_receipt is None:
        for item in transaction['stages']:
            _stage_check(Path(item['source']), item)
        files = dict(transaction['stages'][0]['files'])
        dirs = dict(transaction['stages'][0]['directories'])
        for item, key in zip(transaction['stages'][1:], ('controller', 'launcher', 'desktop')):
            files[key] = item['files']['.']
        generations = {digest: verified['manifest']}
    else:
        files = dict(old_receipt['files'])
        dirs = dict(old_receipt['directories'])
        item = transaction['stages'][0]
        prefix = 'versions/' + digest
        for key, record in item['files'].items():
            files[prefix + '/' + key] = record
        for key, pin in item['directories'].items():
            dirs[prefix if key == '.' else prefix + '/' + key] = pin
        generations = dict(old_receipt['generations'], **{digest: verified['manifest']})
    parents = _anchor(paths)['parents']
    # Include existing config ancestors, without creating or modifying config.
    parent = paths.config_home
    while not parent.exists():
        parent = parent.parent
    parents.update(_parents(parent))
    receipt = dict(schema=SCHEMA, uid=os.getuid(), roots=_roots(paths), service=service,
                   generations=generations, files=files, directories=dirs, parents=parents)
    _write(paths.state / 'receipts' / (transaction['id'] + '.json'), _json(receipt))
    return receipt


def _verified_archive(archive, expected_sha256, expected_commit):
    _absolute(archive)
    package = _package()
    data = _read(archive, limit=package.ARCHIVE_LIMIT)
    try:
        verified = package.verify_archive(data, expected_sha256=expected_sha256, expected_commit=expected_commit)
        # Parse only after the pinned verifier has accepted every archive member.
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            verified['manifest_bytes'] = archive.read('manifest.json')
        return verified
    except package.PackageError as exc:
        raise InstallError(exc.code) from None


def install_archive(archive, *, paths, expected_sha256, expected_commit, service, failpoint=None):
    service = _service(service)
    verified = _verified_archive(archive, expected_sha256, expected_commit)
    digest = expected_sha256.lower()
    with _locked(paths, initialize=True):
        _no_pending(paths)
        _need(_selector(paths) is None, 'already_installed')
        for key in ('controller', 'launcher', 'desktop', '.'):
            _need(not _exists(paths.base if key == '.' else _location(paths, key)), 'collision')
        transaction = _new_transaction('install', None, digest)
        _fail(failpoint, 'before_stage')
        contents = {'versions/' + digest + '/' + k: v for k, v in _generation_contents(verified).items()}
        manager = _read(Path(__file__).absolute(), 0o644, 2 << 20)
        verifier = _read(Path(__file__).absolute().parent / 'package.py', 0o644, 2 << 20)
        contents.update({'tools/install.py': (manager, 0o644), 'tools/package.py': (verifier, 0o644)})
        stage = _build_stage(paths, transaction, paths.base, contents, failpoint=failpoint)
        parents = _parents(paths.base.parent)
        parents.update({str(paths.base if k == '.' else paths.base / k): v for k, v in stage['directories'].items() if k in ('.', 'tools')})
        for key, data in _entrypoints(paths, manager, parents).items():
            _build_stage(paths, transaction, _location(paths, key), {'.': (data, 0o644 if key == 'desktop' else 0o755)}, directory=False, failpoint=failpoint)
        _fail(failpoint, 'after_stage')
        _make_receipt(paths, transaction, service, verified, digest)
        selection = dict(schema=SCHEMA, current=digest, previous=None, receipt=transaction['id'])
        _commit_intent(paths, transaction, selection)
        _fail(failpoint, 'after_intent')
        return _finish(paths, transaction, failpoint=failpoint)


def _outcome(paths, transaction, outcome):
    path = paths.state / 'transactions' / (transaction['id'] + '-done.json')
    value = {'schema': SCHEMA, 'outcome': outcome}
    if _exists(path):
        _need(_document(path) == value, 'history_drift')
    else:
        _write(path, _json(value))


def _transaction(paths):
    value = _pending(paths)
    if value is None:
        return None
    _need(type(value) is dict and set(value) == {'schema', 'id', 'operation', 'phase', 'old', 'new', 'stages', 'digest'}
          and value['schema'] == SCHEMA and type(value['id']) is str and re.fullmatch('[0-9a-f]{32}', value['id']), 'invalid_intent')
    intent = paths.state / 'transactions' / (value['id'] + '.json')
    if _exists(intent):
        frozen = _document(intent)
        _need(type(frozen) is dict and set(frozen) == set(value) and frozen['schema'] == SCHEMA, 'invalid_intent')
        _need(frozen == value or value['phase'] == 'building' and frozen['id'] == value['id']
              and frozen['operation'] == value['operation'] and frozen['old'] == value['old']
              and frozen['stages'] == value['stages'] and frozen['digest'] == value['digest'] and frozen['phase'] == 'ready', 'intent_drift')
        value = frozen
    _need(value['operation'] in ('install', 'update', 'rollback', 'uninstall')
          and value['phase'] in ('building', 'ready') and type(value['stages']) is list, 'invalid_intent')
    _need(value['phase'] != 'ready' or _exists(intent), 'missing_intent')
    _selection(value['old'])
    _selection(value['new'])
    _need((value['old'] is None) == (value['operation'] == 'install'), 'invalid_intent')
    payload = value['operation'] in ('install', 'update')
    _need(type(value['digest']) is str and re.fullmatch('[0-9a-f]{64}', value['digest']) if payload else value['digest'] is None, 'invalid_intent')
    if value['phase'] == 'ready':
        _need((value['new'] is None) == (value['operation'] == 'uninstall'), 'invalid_intent')
        if payload:
            _need(value['new']['current'] == value['digest'] and value['new']['receipt'] == value['id'], 'invalid_intent')
        _need(len(value['stages']) == (4 if value['operation'] == 'install' else 1 if payload else 0), 'invalid_intent')
    _need(len(value['stages']) <= (4 if value['operation'] == 'install' else 1 if value['operation'] == 'update' else 0), 'invalid_intent')
    for index, item in enumerate(value['stages']):
        _need(type(item) is dict and set(item) == {'source', 'target', 'files', 'directories'}, 'invalid_intent')
        if value['operation'] == 'install':
            target = paths.base if index == 0 else _location(paths, ('controller', 'launcher', 'desktop')[index - 1])
        else:
            target = paths.base / 'versions' / value['digest']
        source = target.with_name('.workspace-incoming-' + value['id'] + '-' + str(index))
        _need(item['target'] == str(target) and item['source'] == str(source), 'invalid_intent')
        for key in (*item['files'], *item['directories']):
            _need(type(key) is str and not Path(key).is_absolute() and '..' not in Path(key).parts
                  and str(Path(key)) == key, 'invalid_intent')
        if value['operation'] == 'install' and index:
            _need(set(item['files']) <= {'.'} and not item['directories'], 'invalid_intent')
        else:
            allowed = set(_package().PAYLOAD) | {'manifest.json'}
            if value['operation'] == 'install':
                allowed = {'versions/' + value['digest'] + '/' + k for k in allowed} | {'tools/install.py', 'tools/package.py'}
            dirs = {'.'} | {str(p) for name in allowed for p in Path(name).parents}
            _need(set(item['files']) <= allowed and set(item['directories']) <= dirs, 'invalid_intent')
    _need(_selector(paths) in (value['old'], value['new']), 'selector_drift')
    return value


def recover(paths):
    with _locked(paths):
        transaction = _transaction(paths)
        if transaction is None:
            selection = _selector(paths)
            if selection:
                _verify(paths, selection)
            return _report(selection)
        if transaction['phase'] == 'building':
            if transaction['old']:
                _verify(paths, transaction['old'], stages=tuple(Path(s['source']) for s in transaction['stages']))
            for item in transaction['stages']:
                _need(not _exists(Path(item['target'])), 'collision')
                _stage_check(Path(item['source']), item, missing=True)
            for item in reversed(transaction['stages']):
                _remove_stage(Path(item['source']), item)
            _outcome(paths, transaction, 'aborted_before_publish')
            _atomic(paths.state / 'pending.json', None)
            if transaction['old']:
                _verify(paths, transaction['old'])
            return _report(transaction['old'])
        return _finish(paths, transaction)


def update_archive(archive, *, paths, expected_sha256, expected_commit, failpoint=None):
    verified = _verified_archive(archive, expected_sha256, expected_commit)
    digest = expected_sha256.lower()
    with _locked(paths):
        _no_pending(paths)
        old = _selector(paths)
        _need(old is not None, 'not_installed')
        receipt = _verify(paths, old)
        _need(old['previous'] is None, 'retained_predecessor')
        _need(digest != old['current'], 'already_current')
        transaction = _new_transaction('update', old, digest)
        _fail(failpoint, 'before_stage')
        _build_stage(paths, transaction, paths.base / 'versions' / digest, _generation_contents(verified), failpoint=failpoint)
        _fail(failpoint, 'after_stage')
        _make_receipt(paths, transaction, receipt['service'], verified, digest, old_receipt=receipt)
        selection = dict(schema=SCHEMA, current=digest, previous=old['current'], receipt=transaction['id'])
        _commit_intent(paths, transaction, selection)
        _fail(failpoint, 'after_intent')
        return _finish(paths, transaction, failpoint=failpoint)


def rollback(paths, *, failpoint=None):
    """Swap current and retained predecessor; repeating rollback toggles them."""
    with _locked(paths):
        _no_pending(paths)
        old = _selector(paths)
        _need(old is not None, 'not_installed')
        _verify(paths, old)
        _need(old['previous'] is not None, 'no_predecessor')
        selection = dict(old, current=old['previous'], previous=old['current'])
        transaction = _new_transaction('rollback', old)
        _commit_intent(paths, transaction, selection)
        _fail(failpoint, 'after_intent')
        return _finish(paths, transaction, failpoint=failpoint)


def _remove_owned(paths, transaction, failpoint):
    receipt = _receipt(paths, transaction['old'])
    _check_parents(receipt['parents'])
    items = [(paths.base, dict(files={k: v for k, v in receipt['files'].items() if k not in ('controller', 'launcher', 'desktop')},
                               directories=receipt['directories']))]
    items.extend((_location(paths, key), dict(files={'.': receipt['files'][key]}, directories={}))
                 for key in ('desktop', 'launcher', 'controller'))
    # Check the entire remaining closure before removing any further output.
    for path, item in items:
        _stage_check(path, item, missing=True)
    for index, (path, item) in enumerate(items):
        _remove_stage(path, item)
        _fail(failpoint, 'after_remove_' + str(index))


def uninstall(paths, *, failpoint=None):
    """Remove verified install outputs; never restore or edit desktop panels."""
    with _locked(paths):
        _no_pending(paths)
        old = _selector(paths)
        _need(old is not None, 'not_installed')
        _verify(paths, old)
        transaction = _new_transaction('uninstall', old)
        _commit_intent(paths, transaction, None)
        _fail(failpoint, 'after_intent')
        return _finish(paths, transaction, failpoint=failpoint)


def _environment(paths):
    environment = os.environ.copy()
    environment.update(HOME=str(paths.home), XDG_DATA_HOME=str(paths.data_home),
                       XDG_STATE_HOME=str(paths.state_home), XDG_CONFIG_HOME=str(paths.config_home),
                       PYTHONDONTWRITEBYTECODE='1')
    environment.pop('PYTHONPATH', None)
    return environment


def _supervise(command, *, environment, capture=False, lease=None):
    """Wait through requestClose/join; the child also inherits the shared lease."""
    child = None
    queued = []
    handlers = {}
    def forward(number, _frame):
        if child is None:
            queued.append(number)
        elif child.poll() is None:
            try:
                child.send_signal(number)
            except ProcessLookupError:
                pass
    with ExitStack() as resources:
        output = errors = None
        if capture:
            directory = Path(environment['XDG_STATE_HOME']) / 'orla/workspace-install'
            output = resources.enter_context(tempfile.TemporaryFile(dir=directory))
            errors = resources.enter_context(tempfile.TemporaryFile(dir=directory))
        try:
            for number in (signal.SIGINT, signal.SIGTERM):
                handlers[number] = signal.signal(number, forward)
            child = subprocess.Popen(command, env=environment, cwd='/', start_new_session=True,
                                     pass_fds=() if lease is None else (lease,),
                                     stdout=output if capture else None, stderr=errors if capture else None)
            for number in queued:
                forward(number, None)
            code = child.wait()
        finally:
            # No timeout/kill, including exceptions during spawn/wait/forwarding.
            # The caller's shared flock remains held while this wait completes.
            try:
                if child is not None:
                    while child.poll() is None:
                        try:
                            child.wait()
                        except InterruptedError:
                            continue
            finally:
                for number, handler in handlers.items():
                    signal.signal(number, handler)
        if capture:
            output.seek(0)
            data = output.read(16385)
            _need(len(data) <= 16384, 'diagnose_output')
            return code, data
        return code


def launch(paths, *, service=None, updates=False, command_factory=None):
    """Launch under a shared lease. command_factory(root, service) is an API seam.

    Updates selects no composition service. Its factory receives None.
    A supplied factory replaces only the child command for isolated session tests;
    it cannot bypass selection, integrity checks, the lease or signal supervision.
    No CLI/environment option enables this seam.
    """
    _need(type(updates) is bool and not (updates and service is not None), 'invalid_arguments')
    if service is not None:
        _service(service)
    with _locked(paths, shared=True) as lease:
        _no_pending(paths)
        selection = _selector(paths)
        _need(selection is not None, 'not_installed')
        receipt = _verify(paths, selection)
        service = None if updates else service if service is not None else receipt['service']
        root = paths.base / 'versions' / selection['current']
        arguments = ['--updates'] if updates else ['--service', service]
        command = ([sys.executable, '-I', '-B', str(root / 'workspace/main.py'), *arguments]
                   if command_factory is None else command_factory(root, service))
        _need(isinstance(command, (list, tuple)) and command and all(type(p) is str and '\x00' not in p for p in command), 'invalid_command')
        return _supervise(command, environment=_environment(paths), lease=lease)


def doctor(paths):
    with _locked(paths, shared=True) as lease:
        _no_pending(paths)
        selection = _selector(paths)
        _need(selection is not None, 'not_installed')
        _verify(paths, selection)
        root = paths.base / 'versions' / selection['current']
        environment = _environment(paths)
        environment['TMPDIR'] = str(paths.state)
        code, data = _supervise([sys.executable, '-I', '-B', str(root / 'workspace/main.py'), '--diagnose'],
                                environment=environment, capture=True, lease=lease)
        try:
            diagnosis = json.loads(data)
        except (ValueError, UnicodeError):
            raise InstallError('diagnose_failed') from None
        _need(type(diagnosis) is dict and diagnosis.get('bundle') == 'verified'
              and diagnosis.get('nativeValidated') is False and diagnosis.get('serviceContacted') is False
              and type(diagnosis.get('runtime')) is dict and code in (0, 1), 'diagnose_failed')
        return dict(_report(selection), runtime=diagnosis['runtime'], serviceContacted=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    actions = parser.add_subparsers(dest='action', required=True)
    for name in ('install', 'update'):
        sub = actions.add_parser(name, allow_abbrev=False)
        sub.add_argument('archive', type=Path)
        sub.add_argument('--sha256', required=True)
        sub.add_argument('--commit', required=True)
        if name == 'install':
            sub.add_argument('--service', required=True)
    for name in ('status', 'doctor', 'rollback', 'recover', 'uninstall'):
        actions.add_parser(name, allow_abbrev=False)
    launch_flags = actions.add_parser('launch', allow_abbrev=False).add_mutually_exclusive_group()
    launch_flags.add_argument('--service')
    launch_flags.add_argument('--updates', action='store_true')
    args = parser.parse_args(argv)
    try:
        paths = InstallPaths.from_environment()
        if args.action in ('install', 'update'):
            options = dict(paths=paths, expected_sha256=args.sha256, expected_commit=args.commit)
            if args.action == 'install':
                options['service'] = args.service
            result = (install_archive if args.action == 'install' else update_archive)(args.archive.absolute(), **options)
        elif args.action == 'launch':
            return launch(paths, service=args.service, updates=args.updates)
        else:
            result = {'status': status, 'doctor': doctor, 'rollback': rollback, 'recover': recover, 'uninstall': uninstall}[args.action](paths)
        print(json.dumps(result, sort_keys=True))
        return 1 if args.action == 'doctor' and result['runtime']['status'] != 'ready' else 0
    except (InstallError, OSError) as exc:
        code = exc.code if isinstance(exc, InstallError) else 'filesystem_error'
        result = {'error': code}
        if code == 'busy_close_workspace':
            result['message'] = 'Close Workspace and retry.'
        print(json.dumps(result, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
