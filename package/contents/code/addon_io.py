"""Small Linux anchored IO primitives; no persistent inode/device receipts."""
from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import re
import secrets
import stat
from urllib.parse import unquote, urlsplit

_spec = importlib.util.spec_from_file_location('_orla_addon_format',
                                              Path(__file__).absolute().with_name('addon_format.py'))
f = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(f)
AddonError = f.AddonError


def input_path(value) -> Path:
    """One local filename or file:/// URI; no host, query, fragment or commands."""
    try:
        value = os.fspath(value)
        if type(value) is not str or not 1 <= len(value) <= 4096 or '\x00' in value:
            raise AddonError('file')
        if value.startswith('file:'):
            uri = urlsplit(value)
            if (not value.startswith('file:///') or uri.scheme != 'file'
                    or uri.netloc or uri.query or uri.fragment
                    or '?' in value or '#' in value or not uri.path.startswith('/')
                    or re.search(r'%(?![0-9A-Fa-f]{2})', value)):
                raise AddonError('file')
            value = unquote(uri.path, encoding='utf-8', errors='strict')
        elif '://' in value:
            raise AddonError('file')
        path = Path(value)
        if '..' in path.parts or '\x00' in value or len(value) > 4096:
            raise AddonError('file')
        return path.absolute()
    except (ValueError, TypeError, UnicodeError):
        raise AddonError('file') from None


def identity(info):
    # Device/inode exist only during an open operation, never in the registry.
    return info.st_dev, info.st_ino


def _directory(info, private=False):
    if not stat.S_ISDIR(info.st_mode):
        raise AddonError('unsafe')
    mode = stat.S_IMODE(info.st_mode)
    if private:
        safe = info.st_uid == os.getuid() and mode == 0o700
    else:
        safe = info.st_uid in (0, os.getuid()) and (not mode & 0o022 or
            (info.st_uid == 0 and bool(mode & stat.S_ISVTX)))
    if not safe:
        raise AddonError('unsafe')


def _regular(info, private=True):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid():
        raise AddonError('unsafe')
    mode = stat.S_IMODE(info.st_mode)
    if (private and mode != 0o600) or (not private and mode not in (0o400, 0o600, 0o644)):
        raise AddonError('unsafe')
    if info.st_size > f.MAX_BYTES:
        raise AddonError('size')


class Directory:
    """Nofollow every component, pin each open directory to its current name."""
    def __init__(self, path, *, create=False, private=False):
        self.path = input_path(path)
        self.chain = []
        try:
            descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.chain.append((descriptor, None))
            _directory(os.fstat(descriptor))
            for part in self.path.parts[1:]:
                parent = self.chain[-1][0]
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=parent)
                except FileNotFoundError:
                    if not create:
                        raise AddonError('missing') from None
                    self.check()
                    try:
                        os.mkdir(part, 0o700, dir_fd=parent)
                    except FileExistsError:
                        pass
                    os.fsync(parent)
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=parent)
                self.chain.append((child, part))
                _directory(os.fstat(child))
            self.private = private
            self.check()
        except AddonError:
            self.close()
            raise
        except (OSError, ValueError):
            self.close()
            raise AddonError('unsafe') from None

    @property
    def fd(self):
        return self.chain[-1][0]

    def check(self):
        try:
            for index, (descriptor, name) in enumerate(self.chain):
                info = os.fstat(descriptor)
                _directory(info, getattr(self, 'private', False) and index == len(self.chain) - 1)
                if name is not None:
                    named = os.stat(name, dir_fd=self.chain[index - 1][0], follow_symlinks=False)
                    if identity(info) != identity(named):
                        raise AddonError('drift')
        except OSError:
            raise AddonError('drift') from None

    def names(self, maximum):
        self.check()
        result = []
        # A fresh description avoids scandir(fd)'s shared directory offset.
        scan = os.open('.', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            with os.scandir(scan) as entries:
                for entry in entries:
                    result.append(entry.name)
                    if len(result) > maximum:
                        raise AddonError('state')
        finally:
            os.close(scan)
        self.check()
        return set(result)

    @contextmanager
    def file(self, name, *, private=True, create=False):
        self.check()
        descriptor = None
        try:
            if create:
                try:
                    descriptor = os.open(name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                         0o600, dir_fd=self.fd)
                    os.fsync(descriptor)
                    os.fsync(self.fd)
                except FileExistsError:
                    pass
            if descriptor is None:
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                     dir_fd=self.fd)
            info = os.fstat(descriptor)
            _regular(info, private)
            self.check_file(name, descriptor, private=private)
            yield descriptor
            self.check_file(name, descriptor, private=private)
        except FileNotFoundError:
            raise AddonError('missing') from None
        except OSError:
            raise AddonError('unsafe') from None
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def check_file(self, name, descriptor, *, private=True):
        self.check()
        try:
            info = os.fstat(descriptor)
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            _regular(info, private)
            _regular(named, private)
            if identity(info) != identity(named):
                raise AddonError('drift')
        except OSError:
            raise AddonError('drift') from None

    def read(self, name, *, private=True):
        with PinnedFile(self, name, private=private) as pinned:
            return pinned.data

    def publish(self, name, data, *, replace=False):
        if type(data) is not bytes or len(data) > f.MAX_BYTES:
            raise AddonError('size')
        self.check()
        temporary = '.addon-' + secrets.token_hex(16) + '.tmp'
        descriptor = None
        owned = False
        published = False
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=self.fd)
            owned = True
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise AddonError('io')
                view = view[written:]
            os.fsync(descriptor)
            self.check_file(temporary, descriptor)
            if replace:
                os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
                owned = False
            else:
                # link publishes without clobbering; temporary link is then removed.
                os.link(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd,
                        follow_symlinks=False)
                os.unlink(temporary, dir_fd=self.fd)
                owned = False
            published = True
            self.check_file(name, descriptor)
            os.fsync(self.fd)
            self.check()
        except AddonError as error:
            error.published = published
            raise
        except OSError as error:
            failure = AddonError('exists' if isinstance(error, FileExistsError) else 'io')
            failure.published = published
            raise failure from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if owned:
                try:
                    os.unlink(temporary, dir_fd=self.fd)
                    os.fsync(self.fd)
                except OSError:
                    pass

    def close(self):
        for descriptor, _ in reversed(self.chain):
            os.close(descriptor)
        self.chain = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def read_input(value):
    path = input_path(value)
    with Directory(path.parent) as directory:
        return directory.read(path.name, private=False)


def _signature(info):
    return identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns


class PinnedFile:
    """Keep the validated leaf descriptor and named identity until response."""
    def __init__(self, directory, name, *, private=True):
        self.directory, self.name, self.private = directory, name, private
        self.fd = None
        try:
            directory.check()
            self.fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                              dir_fd=directory.fd)
            directory.check_file(name, self.fd, private=private)
            self.signature = _signature(os.fstat(self.fd))
            self.data = os.read(self.fd, f.MAX_BYTES + 1)
            if len(self.data) > f.MAX_BYTES:
                raise AddonError('size')
            self.check()
            if len(self.data) != self.signature[1]:
                raise AddonError('drift')
        except (OSError, AddonError) as error:
            self.close()
            if isinstance(error, AddonError):
                raise
            raise AddonError('missing' if isinstance(error, FileNotFoundError) else 'unsafe') from None

    def check(self):
        self.directory.check_file(self.name, self.fd, private=self.private)
        if _signature(os.fstat(self.fd)) != self.signature:
            raise AddonError('drift')

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        try:
            if kind is None:
                self.check()
        finally:
            self.close()
