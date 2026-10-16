#!/usr/bin/env python3
"""Lazy, single-flight local-theme reader. Importing this module does not load Qt."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

BUS = 'org.orla.Themes'
OBJECT = '/org/orla/Themes'
INTERFACE = 'org.orla.Themes1'
FORMAT = '0.1-experimental'
LIMIT = 65536
READ_CODES = frozenset(('type size utf8 json depth duplicate_key nonfinite unknown_key '
                        'required format_version length format range file').split())


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def failure(code):
    return encoded({'formatVersion': FORMAT, 'valid': False, 'code': code})


def identity(path):
    with open(path, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 262144:
            raise ValueError('identity')
        data = stream.read(262145)
        after = os.fstat(stream.fileno())
    def pin(value):
        return (value.st_dev, value.st_ino, value.st_uid, value.st_gid, value.st_mode,
                value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if pin(before) != pin(after) or len(data) != after.st_size:
        raise ValueError('identity')
    return pin(after), hashlib.sha256(data).hexdigest()


def serve():
    from PySide6.QtCore import QCoreApplication, QObject, QProcess, QTimer, Slot
    from PySide6.QtDBus import QDBusConnection, QDBusMessage

    base = Path(__file__).resolve().parent
    paths = [base / name for name in ('theme_service.py', 'theme_file.py', 'theme_format.py')]
    pins = [identity(path) for path in paths]
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('_orla_theme_service_format', paths[2])
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    app = QCoreApplication(sys.argv)
    # Activation supplies a session address. Never silently connect elsewhere.
    address = os.environ.get('DBUS_SESSION_BUS_ADDRESS', '')
    if not address:
        return 1
    bus = QDBusConnection.connectToBus(address, 'orla-theme-service')

    def unchanged():
        try:
            return pins == [identity(path) for path in paths]
        except (OSError, ValueError):
            return False

    class Themes(QObject):
        def __init__(self):
            super().__init__()
            self.process = None
            self.request = None
            self.output = bytearray()
            self.error = None
            self.obsolete = False
            self.deadline = 0.0
            self.idle = QTimer(self)
            self.idle.setSingleShot(True)
            self.idle.timeout.connect(app.quit)
            self.work = QTimer(self)
            self.work.setSingleShot(True)
            self.work.timeout.connect(self.expired)
            self.kill_timer = QTimer(self)
            self.kill_timer.setSingleShot(True)
            self.kill_timer.timeout.connect(self.kill)
            self.reap_timer = QTimer(self)
            self.reap_timer.setSingleShot(True)
            self.reap_timer.timeout.connect(self.cleanup_failed)
            self.watch = QTimer(self)
            self.watch.timeout.connect(self.watch_identity)
            self.watch.start(100)
            self.idle.start(30000)

        @Slot(str, QDBusMessage, result=str)
        def LoadThemeFile(self, url, message):
            if self.obsolete or not unchanged():
                self.stop()
                return failure('unavailable')
            if self.process is not None:
                return failure('busy')
            if type(url) is not str or not url.startswith('file:///'):
                return failure('file')
            try:
                if len(url) > 16384 or len(url.encode('utf-8')) > 16384:
                    return failure('size')
            except UnicodeError:
                return failure('file')
            message.setDelayedReply(True)
            self.request = QDBusMessage(message)
            self.idle.stop()
            self.output = bytearray()
            self.error = None
            process = QProcess(self)
            self.process = process
            process.setStandardInputFile(QProcess.nullDevice())
            process.setStandardErrorFile(QProcess.nullDevice())
            process.setProgram(sys.executable)
            process.setArguments(['-I', '-B', str(paths[1]), url])
            process.readyReadStandardOutput.connect(self.drain)
            process.finished.connect(self.finished)
            process.errorOccurred.connect(self.process_error)
            self.deadline = time.monotonic() + 3
            self.work.start(3000)
            process.start()
            return ''

        def reply(self, payload):
            if not unchanged():
                self.obsolete = True
                payload = failure('unavailable')
            if self.request is not None:
                bus.send(self.request.createReply(payload))
                self.request = None

        def drain(self):
            if self.process is None:
                return
            while self.process.bytesAvailable():
                chunk = bytes(self.process.read(min(8192, LIMIT + 1 - len(self.output))))
                self.output.extend(chunk)
                if len(self.output) > LIMIT:
                    self.abort('invalid_response')
                    return
                if not chunk:
                    break

        def abort(self, code):
            if self.error is not None:
                return
            self.error = code
            self.work.stop()
            if self.process is not None:
                self.process.terminate()
                self.kill_timer.start(250)

        def expired(self):
            remaining = self.deadline - time.monotonic()
            if remaining > 0:
                self.work.start(max(1, int(remaining * 1000) + 1))
            else:
                self.abort('timeout')

        def kill(self):
            if self.process is not None:
                self.process.kill()
                self.reap_timer.start(750)

        def cleanup_failed(self):
            if self.process is not None:
                # Keep ownership and the busy barrier until finished, even after reply.
                self.reply(failure('cleanup_failed'))
                self.obsolete = True

        def process_error(self, error):
            if error == QProcess.FailedToStart:
                self.error = self.error or 'unavailable'
                self.finished(-1, QProcess.CrashExit)

        def validated(self, exit_code, exit_status):
            if exit_status != QProcess.NormalExit or exit_code not in (0, 1):
                return failure('invalid_response')
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError('duplicate')
                    result[key] = value
                return result
            response = json.loads(self.output.decode('utf-8'), object_pairs_hook=pairs,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError('number')))
            if type(response) is not dict or response.get('formatVersion') != FORMAT:
                raise ValueError('envelope')
            if response.get('valid') is True and exit_code == 0 and set(response) == {'formatVersion', 'valid', 'theme'}:
                theme = parser.validate_theme(response['theme'])
                return encoded({'formatVersion': FORMAT, 'valid': True, 'theme': theme})
            if response.get('valid') is False and exit_code == 1 and set(response) == {'formatVersion', 'valid', 'errors'}:
                errors = response['errors']
                if type(errors) is list and 1 <= len(errors) <= 128 and all(
                        type(item) is dict and set(item) == {'field', 'code', 'message'}
                        and all(type(value) is str for value in item.values())
                        and item['code'] in READ_CODES for item in errors):
                    return failure(errors[0]['code'])
            raise ValueError('envelope')

        def finished(self, exit_code, exit_status):
            if self.process is None:
                return
            self.drain()
            if time.monotonic() >= self.deadline and self.error is None:
                self.error = 'timeout'
            for timer in (self.work, self.kill_timer, self.reap_timer):
                timer.stop()
            try:
                payload = failure(self.error) if self.error else self.validated(exit_code, exit_status)
            except (ValueError, TypeError, UnicodeError, RecursionError, parser.ThemeError):
                payload = failure('invalid_response')
            if not unchanged():
                self.obsolete = True
                payload = failure('unavailable')
            process, self.process = self.process, None
            process.deleteLater()
            self.reply(payload)
            if self.obsolete:
                app.quit()
            else:
                self.idle.start(30000)

        def watch_identity(self):
            if not bus.isConnected() or not unchanged():
                self.stop()

        def stop(self):
            self.obsolete = True
            if self.process is None:
                app.quit()
            elif self.error is None:
                self.abort('unavailable')

    obj = Themes()
    if not unchanged() or not bus.isConnected() or not bus.registerObject(OBJECT, INTERFACE, obj, QDBusConnection.ExportAllSlots) or not bus.registerService(BUS):
        return 1
    signal.signal(signal.SIGTERM, lambda *_: obj.stop())
    signal.signal(signal.SIGINT, lambda *_: obj.stop())
    result = app.exec()
    QDBusConnection.disconnectFromBus('orla-theme-service')
    return result


def main(argv=None):
    if (sys.argv[1:] if argv is None else argv) != ['--serve']:
        sys.stdout.write(failure('unavailable') + '\n')
        return 2
    try:
        return serve()
    except (ImportError, OSError, ValueError):
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
