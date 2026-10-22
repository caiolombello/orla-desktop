#!/usr/bin/env python3
"""Lazy addon service; Qt is loaded only when constructing its runtime."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import signal
import sys
import time

BUS = 'org.orla.Addons'
OBJECT = '/org/orla/Addons'
INTERFACE = 'org.orla.Addons1'
# A periodic dock reader keeps the host alive, so idle checks must stay cheap.
# File events retire it after an update; the slow check is only a fallback.
FLIGHT_WATCH_MS = 100
IDLE_WATCH_MS = 5000


def create_service(app, bus, *, base=None, process_factory=None, clock=time.monotonic,
                   copy_message=None):
    """Construct without connecting/registering a bus. Activation owns registration.

    Explicit dependencies permit owned QCore/QProcess tests with a fake bus.
    Runtime source pins expire with this object; they are never written to disk.
    """
    from PySide6.QtCore import QFileSystemWatcher, QObject, QProcess, QTimer, Slot
    from PySide6.QtDBus import QDBusMessage

    base = Path(__file__).absolute().parent if base is None else Path(base).absolute()
    spec = importlib.util.spec_from_file_location('_orla_addon_service_worker',
                                                base / 'addon_worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    pin = worker.source_fingerprint(base)
    backend = worker.load_backend(base)
    if pin != worker.source_fingerprint(base):
        raise ValueError('source_changed')
    factory = process_factory or QProcess
    copy_message = copy_message or QDBusMessage

    class Addons(QObject):
        def __init__(self):
            super().__init__()
            self.process = None
            self.request = None
            self.action = None
            self.output = bytearray()
            self.first_failure = None
            self.obsolete = False
            self.finishing = False
            self.dispatched = False
            self.deadline = 0.0
            self.kill_deadline = self.reap_deadline = 0.0
            self.idle = QTimer(self)
            self.idle.setSingleShot(True)
            # Lambda boundaries prevent PySide from registering internal Python
            # callbacks as public dynamic slots under ExportAllSlots.
            self.idle.timeout.connect(lambda: self.close())
            self.work = QTimer(self)
            self.work.setSingleShot(True)
            self.work.timeout.connect(lambda: self.expired())
            self.kill_timer = QTimer(self)
            self.kill_timer.setSingleShot(True)
            self.kill_timer.timeout.connect(lambda: self.kill())
            self.reap_timer = QTimer(self)
            self.reap_timer.setSingleShot(True)
            self.reap_timer.timeout.connect(lambda: self.cleanup_failed())
            self.watch = QTimer(self)
            self.watch.timeout.connect(lambda: self.watch_identity())
            self.watch.start(IDLE_WATCH_MS)
            self.sources = QFileSystemWatcher(self)
            self.sources.addPaths([str(base), *(str(base / name) for name in worker.SOURCE_NAMES)])
            self.sources.fileChanged.connect(lambda path: self.watch_identity())
            self.sources.directoryChanged.connect(lambda path: self.watch_identity())
            self.idle.start(30000)

        def unchanged(self):
            try:
                return worker.source_fingerprint(base) == pin
            except (OSError, ValueError):
                return False

        def error(self, code, *, committed=False, generation=None):
            return worker.encoded(worker.failure(code, committed=committed, generation=generation))

        @Slot(QDBusMessage, result=str)
        def ListAddons(self, message):
            return self.dispatch('list', [], message)

        @Slot(str, QDBusMessage, result=str)
        def InspectAddonFile(self, uri, message):
            return self.dispatch('inspect', [uri], message)

        @Slot(str, str, QDBusMessage, result=str)
        def InstallAddon(self, uri, digest, message):
            return self.dispatch('install', [uri, digest], message)

        @Slot(str, str, QDBusMessage, result=str)
        def EnableAddon(self, addon_id, digest, message):
            return self.dispatch('enable', [addon_id, digest], message)

        @Slot(str, str, QDBusMessage, result=str)
        def DisableAddon(self, addon_id, digest, message):
            return self.dispatch('disable', [addon_id, digest], message)

        @Slot(str, str, QDBusMessage, result=str)
        def RemoveAddon(self, addon_id, digest, message):
            return self.dispatch('remove', [addon_id, digest], message)

        @Slot(str, str, QDBusMessage, result=str)
        def RollbackAddon(self, addon_id, digest, message):
            return self.dispatch('rollback', [addon_id, digest], message)

        @Slot('QStringList', QDBusMessage, result=str)
        def SnapshotFor(self, modules, message):
            if type(modules) is not list or modules not in ([], ['peripherals'], ['quota']):
                return self.error('format')
            action = 'snapshot' if modules == ['peripherals'] else 'quota' if modules == ['quota'] else 'empty'
            return self.dispatch(action, [], message)

        def dispatch(self, action, args, message):
            if self.obsolete:
                return self.error('unavailable')
            if not bus.isConnected() or not self.unchanged():
                self.close('source_changed' if bus.isConnected() else 'unavailable')
                return self.error('unavailable')
            if self.process is not None or self.finishing:
                return self.error('busy')
            try:
                worker.validate_request(action, args)
            except (ValueError, UnicodeError) as error:
                return self.error(str(error))
            if action == 'empty':
                # No AddonPaths, HOME/XDG lookup, store or producer IO.
                return worker.encoded(dict(schemaVersion=2, modules=[]))
            self.idle.stop()
            self.action, self.first_failure = action, None
            self.output = bytearray()
            self.dispatched = False
            message.setDelayedReply(True)
            self.request = copy_message(message)
            process = factory(self)
            self.process = process
            process.setStandardInputFile(QProcess.nullDevice())
            process.setStandardErrorFile(QProcess.nullDevice())
            process.setReadChannel(QProcess.StandardOutput)
            process.setProgram(sys.executable)
            process.setArguments(['-I', '-B', str(base / 'addon_worker.py'),
                                  '--source-sha', pin, action, *args])
            process.setWorkingDirectory(str(base))
            process.readyReadStandardOutput.connect(
                lambda: self.drain() if self.process is process else None)
            process.finished.connect(lambda code, status:
                self.finished(code, status) if self.process is process else None)
            process.errorOccurred.connect(lambda error:
                self.process_error(error) if self.process is process else None)
            self.deadline = clock() + 3.0
            self.work.start(3000)
            self.watch.setInterval(FLIGHT_WATCH_MS)
            self.dispatched = True
            process.start()
            return ''

        def reply(self, payload):
            # Clear before send: a fake/real transport can reenter synchronously.
            request, self.request = self.request, None
            if request is not None and bus.isConnected():
                if not bus.send(request.createReply(payload)):
                    self.close('unavailable')

        def drain(self):
            process = self.process
            if process is None:
                return
            if clock() >= self.deadline:
                self.abort('timeout')
            while process.bytesAvailable():
                chunk = bytes(process.read(min(8192, worker.LIMIT + 1 - len(self.output))))
                if not chunk:
                    break
                self.output.extend(chunk)
                if len(self.output) > worker.LIMIT:
                    self.abort('invalid_response')
                    process.closeReadChannel(QProcess.StandardOutput)
                    return

        @staticmethod
        def arm(timer, deadline):
            timer.start(max(1, int((deadline - clock()) * 1000) + 1))

        def abort(self, code):
            if self.first_failure is not None:
                return
            # This is local state, never ambient sys.exc_info() from the caller.
            self.first_failure = code
            self.work.stop()
            process = self.process
            if process is not None:
                self.kill_deadline = clock() + 0.250
                self.arm(self.kill_timer, self.kill_deadline)
                process.terminate()

        def expired(self):
            if self.process is None or self.first_failure is not None:
                return
            if clock() < self.deadline:
                self.arm(self.work, self.deadline)
            else:
                self.abort('timeout')

        def kill(self):
            if self.process is None:
                return
            if clock() < self.kill_deadline:
                self.arm(self.kill_timer, self.kill_deadline)
                return
            self.reap_deadline = clock() + 0.750
            self.arm(self.reap_timer, self.reap_deadline)
            self.process.kill()

        def cleanup_failed(self):
            if self.process is None:
                return
            if clock() < self.reap_deadline:
                self.arm(self.reap_timer, self.reap_deadline)
                return
            if self.process.state() == QProcess.NotRunning:
                self.finished(self.process.exitCode(), self.process.exitStatus())
                return
            self.obsolete = True
            self.idle.stop()
            uncertain = self.action in worker.MUTATIONS and self.dispatched
            self.reply(self.error(self.first_failure or 'cleanup_failed',
                                  committed=None if uncertain else False))
            # Never drop the process, quit, delete it or reopen the busy barrier
            # while the owned child has not actually been reaped.

        def process_error(self, error):
            if error == QProcess.FailedToStart:
                self.dispatched = False
                self.first_failure = self.first_failure or 'unavailable'
                self.finished(-1, QProcess.CrashExit)
            elif error in (QProcess.ReadError, QProcess.WriteError):
                self.abort('invalid_response')

        def finished(self, exit_code, exit_status):
            if self.process is None or self.finishing:
                return
            if self.process.state() != QProcess.NotRunning:
                self.abort('invalid_response')
                return
            self.finishing = True
            process = self.process
            self.drain()
            for timer in (self.work, self.kill_timer, self.reap_timer):
                timer.stop()
            response = None
            try:
                if exit_status == QProcess.NormalExit and exit_code in (0, 1):
                    response = worker.validate_response(bytes(self.output), exit_code,
                                                        self.action, backend)
            except (ValueError, TypeError, UnicodeError, RecursionError):
                pass
            if not self.unchanged() or not bus.isConnected():
                self.obsolete = True
                self.first_failure = self.first_failure or 'source_changed'
            if response is None:
                self.first_failure = self.first_failure or 'invalid_response'
            if self.first_failure:
                committed = None if self.action in worker.MUTATIONS and self.dispatched else False
                generation = None
                if response is not None:
                    if not response['ok']:
                        committed, generation = response['error']['committed'], response['error']['generation']
                    elif self.action in worker.MUTATIONS:
                        committed, generation = True, response['result']['generation']
                payload = self.error(self.first_failure, committed=committed, generation=generation)
            elif self.action == 'snapshot':
                payload = worker.encoded(response['result']) if response['ok'] else worker.encoded(response)
            else:
                payload = worker.encoded(response)
            try:
                self.reply(payload)
            finally:
                self.process = None
                self.finishing = False
                process.deleteLater()
            if self.obsolete:
                self.watch.stop()
                app.quit()
            else:
                self.watch.setInterval(IDLE_WATCH_MS)
                self.idle.start(30000)

        def watch_identity(self):
            if not bus.isConnected():
                self.close('unavailable')
            elif not self.unchanged():
                self.close('source_changed')

        def close(self, code='cancelled'):
            self.obsolete = True
            self.idle.stop()
            if self.process is None:
                self.watch.stop()
                app.quit()
            else:
                self.abort(code)

        def shutdown(self):
            """Bounded final cleanup if someone quits the event loop externally."""
            self.close()
            process = self.process
            if process is not None and not process.waitForFinished(250):
                process.kill()
                process.waitForFinished(750)
            return self.process is None

    return Addons()


def serve():
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusConnection

    address = os.environ.get('DBUS_SESSION_BUS_ADDRESS', '')
    if not address:
        return 1
    sys.dont_write_bytecode = True
    app = QCoreApplication(sys.argv)
    bus = QDBusConnection.connectToBus(address, 'orla-addon-service')
    obj = create_service(app, bus)
    if (not bus.isConnected() or not obj.unchanged()
            or not bus.registerObject(OBJECT, INTERFACE, obj, QDBusConnection.ExportAllSlots)
            or not bus.registerService(BUS)):
        obj.shutdown()
        QDBusConnection.disconnectFromBus('orla-addon-service')
        return 1
    signal.signal(signal.SIGTERM, lambda *_: obj.close())
    signal.signal(signal.SIGINT, lambda *_: obj.close())
    result = app.exec()
    while not obj.shutdown():
        # An uninterruptible owned child must stay owned, with admission closed.
        # No repeated kill loop and no destructor that could lose that barrier.
        app.exec()
    QDBusConnection.disconnectFromBus('orla-addon-service')
    return result


def main(argv=None):
    if (sys.argv[1:] if argv is None else argv) != ['--serve']:
        return 2
    try:
        return serve()
    except (ImportError, OSError, ValueError):
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
