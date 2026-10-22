"""Service-free release window. The bounded CLI runs only after explicit Check."""
from __future__ import annotations
from pathlib import Path
import os
import signal
import sys
from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl, QProcess, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from scripts.updates_desktop_state import source_reference, strict_json, LIMIT, Store, history_key, valid_reference
from scripts.updates_contract import validate_result, result, safe_release_url, utc_time, parse_version
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def cli_command(root, reference, channel):
    return (str(Path(sys.executable).resolve()), ['-I', '-B', str(root / 'scripts/updates.py'), 'check', '--installed-version', reference['version'], '--channel', channel])

class CheckProcess(QObject):
    """One request owns a new Unix session, through termination and direct reaping.

    Qt 6.11: https://doc.qt.io/qtforpython-6.11/PySide6/QtCore/QProcess.html
    CreateNewSession is implemented by Qt; no Python runs between fork and exec.
    """
    done = Signal(object)

    def __init__(self, program, args, reference, channel, watchdog_ms, attempted_at, parent):
        super().__init__(parent)
        self.reference = reference
        self.channel = channel
        self.attempted_at = attempted_at
        self.output = bytearray()
        self.errors = bytearray()
        self.failure = None
        self.pid = 0
        self.start_ticks = None
        self.terminal = False
        self.exited = False
        self.aborting = False
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.setUnixProcessParameters(QProcess.UnixProcessFlag.CreateNewSession | QProcess.UnixProcessFlag.CloseFileDescriptors | QProcess.UnixProcessFlag.DisableCoreDumps)
        self.process.setProgram(program)
        self.process.setArguments(args)
        self.process.setWorkingDirectory(str(parent.root))
        self.process.started.connect(self.started)
        self.process.readyReadStandardOutput.connect(lambda: self.drain(QProcess.StandardOutput, self.output))
        self.process.readyReadStandardError.connect(lambda: self.drain(QProcess.StandardError, self.errors))
        self.process.errorOccurred.connect(self.error)
        self.process.finished.connect(self.finished)
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(lambda: self.abort('timeout'))
        self.watchdog.start(watchdog_ms)
        self.cleanup = QTimer(self)
        self.cleanup.setInterval(20)
        self.cleanup.timeout.connect(self.settle)
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.kill_group)

    def start(self):
        self.process.start()
        self.process.closeWriteChannel()

    def started(self):
        self.pid = self.process.processId()
        try:
            self.start_ticks = self.proc_info(self.pid)[3]
        except (OSError, ValueError):
            pass
        if self.aborting:
            self.group_signal(signal.SIGTERM)
            if not self.kill_timer.isActive():
                self.kill_group()

    @staticmethod
    def proc_info(pid):
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return (fields[0], int(fields[2]), int(fields[3]), int(fields[19]))

    def members(self):
        # A live group reserves its ID. Check the session and process birth
        # before signalling after the direct child has exited.
        if not self.pid:
            return []
        members = []
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                state, group, session, birth = self.proc_info(entry.name)
                if int(entry.name) == self.pid and self.start_ticks is not None and (birth != self.start_ticks):
                    return []
                if group == self.pid and session == self.pid and (self.start_ticks is None or birth >= self.start_ticks):
                    members.append((int(entry.name), state))
            except (OSError, ValueError, IndexError):
                pass
        return members

    def group_signal(self, value):
        if self.members():
            try:
                os.killpg(self.pid, value)
            except ProcessLookupError:
                pass
            except OSError:
                self.failure = self.failure or 'process_error'

    def drain(self, channel, buffer):
        if self.terminal:
            return
        self.process.setReadChannel(channel)
        drained = 0
        while self.process.bytesAvailable() and drained < LIMIT:
            chunk = bytes(self.process.read(4096))
            drained += len(chunk)
            remaining = LIMIT - len(buffer)
            buffer.extend(chunk[:max(0, remaining)])
            if len(chunk) > remaining:
                self.abort('output_limit')
                break

    def error(self, error):
        if self.terminal:
            return
        if error == QProcess.FailedToStart:
            self.failure = self.failure or 'spawn_failed'
            self.exited = True
            self.settle()
        elif error == QProcess.Crashed:
            self.failure = self.failure or 'process_error'

    def abort(self, reason):
        # Continuous output must never postpone the original cleanup deadline.
        if self.terminal or self.aborting:
            return
        self.aborting = True
        self.failure = self.failure or reason
        self.group_signal(signal.SIGTERM)
        self.kill_timer.start(150)
        self.cleanup.start()

    def kill_group(self):
        if self.terminal:
            return
        self.group_signal(signal.SIGKILL)
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()

    def finished(self, *args):
        if self.terminal:
            return
        self.drain(QProcess.StandardOutput, self.output)
        self.drain(QProcess.StandardError, self.errors)
        self.exited = True
        if any((state != 'Z' for _, state in self.members())):
            self.failure = self.failure or 'process_error'
            self.abort(self.failure)
        self.cleanup.start()
        self.settle()

    def settle(self):
        if self.terminal or not self.exited or self.process.state() != QProcess.NotRunning:
            return
        if any((state != 'Z' for _, state in self.members())):
            return
        self.terminal = True
        self.watchdog.stop()
        self.kill_timer.stop()
        self.cleanup.stop()
        try:
            if self.failure:
                raise ValueError(self.failure)
            if self.process.exitStatus() != QProcess.NormalExit:
                raise ValueError('crash')
            data = validate_result(strict_json(bytes(self.output).decode('utf-8')), self.channel, self.reference['version'], self.process.exitCode())
        except (ValueError, TypeError, UnicodeError, RecursionError):
            data = result('unavailable', self.failure or 'invalid_result', self.reference['version'], self.channel, self.attempted_at)
        self.done.emit(data)
# Fixed, read-only Plasma script: versions of the dock widgets Plasma has loaded.
RUNNING_SCRIPT = ('var v=[];panels().forEach(function(p){p.widgets().forEach(function(w){'
                  'if(w.type==="org.caiodock.dock")v.push(String(w.version));});});'
                  'print(JSON.stringify({docks:v}));')
RUNNING_LIMIT = 16


def parse_running(text):
    """Strict reply → ('found', sorted distinct versions) or ('absent', [])."""
    if not isinstance(text, str):
        raise ValueError('reply type')
    value = strict_json(text)
    if not isinstance(value, dict) or set(value) != {'docks'} or not isinstance(value['docks'], list):
        raise ValueError('reply shape')
    docks = value['docks']
    if len(docks) > RUNNING_LIMIT or any(not isinstance(v, str) or parse_version(v) is None for v in docks):
        raise ValueError('reply versions')
    return ('found', sorted(set(docks))) if docks else ('absent', [])


def plasma_running_probe(parent, done, timeout_ms=3000):
    """Ask Plasma, asynchronously and only on request, which dock versions it loaded."""
    from PySide6.QtDBus import QDBusConnection, QDBusMessage, QDBusPendingCallWatcher
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        done('unavailable', [])
        return
    message = QDBusMessage.createMethodCall('org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell', 'evaluateScript')
    message.setArguments([RUNNING_SCRIPT])
    watcher = QDBusPendingCallWatcher(bus.asyncCall(message, timeout_ms), parent)

    def finished(call):
        reply = call.reply()
        call.deleteLater()
        arguments = reply.arguments() if reply.type() == QDBusMessage.ReplyMessage else []
        try:
            status, versions = parse_running(arguments[0] if len(arguments) == 1 else None)
        except (ValueError, TypeError, RecursionError):
            status, versions = 'unavailable', []
        done(status, versions)
    watcher.finished.connect(finished)


_UNSET = object()

class UpdatesController(QObject):
    changed = Signal()
    closeReady = Signal()

    def __init__(self, root, reference=_UNSET, *, runner=None, storage_root=None, opener=None, watchdog_ms=15000, running_probe=None, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve()
        self._source = reference is _UNSET
        self._explicit = None if self._source else dict(reference) if isinstance(reference, dict) else None
        self._fallback = None
        self._installed_status = 'absent'
        self.reference = None
        self._runner = runner or cli_command
        self._running_probe = running_probe or plasma_running_probe
        self._running = dict(status='unread', versions=[])
        self._running_token = None
        self._opener = opener
        self._watchdog_ms = watchdog_ms
        self._process = None
        self._close_emitted = False
        self._opening_failed = False
        self._channel = 'stable'
        self._busy = False
        self._closing = False
        self._status = 'idle'
        self._record = {}
        self._store = Store(storage_root)
        self.resolve_reference()
        self._records, self._channel, self._storage_warning = self._store.load()
        self._historical = True
        self._last_completed = {}
        self.restore_record()

    @Property(str, notify=changed)
    def channel(self):
        return self._channel

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def closePending(self):
        return self._closing

    @Property(bool, notify=changed)
    def readingRunning(self):
        return self._running_token is not None

    @Slot()
    def readRunning(self):
        """Explicit request only: opening the window never asks Plasma."""
        if self._running_token is not None or self._closing:
            return
        token = object()
        self._running_token = token

        def done(status, versions):
            if self._running_token is not token:
                return
            self._running_token = None
            self._running = dict(status=status, versions=list(versions))
            self.changed.emit()
        self.changed.emit()
        try:
            self._running_probe(self, done)
        except (OSError, ValueError, TypeError, RuntimeError, ImportError):
            done('unavailable', [])

    @Property(bool, notify=changed)
    def canCheck(self):
        return self.reference is not None and (not self._busy) and (not self._closing)

    def resolve_reference(self):
        """Prefer the dock installed for this user; otherwise the source or bundle copy."""
        fallback = source_reference(self.root) if self._source else self._explicit
        self._fallback = fallback if valid_reference(fallback) else None
        self._installed_status, installed = self._store.installed_dock()
        self.reference = installed if installed and valid_reference(installed) else self._fallback

    @Property('QVariantMap', notify=changed)
    def state(self):
        installed = self.reference if self.reference and self.reference['role'] == 'installed' else None
        other = self._fallback if installed else None
        return dict(status=self._status, version=self.reference['version'] if self.reference else '', role=self.reference['role'] if self.reference else '', installedStatus=self._installed_status, installedVersion=installed['version'] if installed else '', otherRole=other['role'] if other else '', otherVersion=other['version'] if other else '', runningStatus=self._running['status'], runningVersions=list(self._running['versions']), record=self._record, releaseUrl=(self._record.get('result') or {}).get('available_url') or '', openingFailed=self._opening_failed, historical=self._historical, lastCompleted=self._last_completed, storageWarning=self._storage_warning, timeUnreliable=self.time_unreliable(), old=self.old_record())

    def restore_record(self):
        entry = self._records.get(self._channel, {})
        if not self.reference or entry.get('key') != history_key(self.reference, self._channel):
            self._record = {}
            self._last_completed = {}
        else:
            self._record = entry['attempt']
            self._last_completed = entry['lastCompleted'] or {}
        self._historical = True

    def time_unreliable(self):
        return any((utc_time(value) > utc_time(now()) for record in (self._record, self._last_completed) for value in (record.get('attemptedAt'), record.get('completedAt')) if value))

    def old_record(self):
        value = self._record.get('attemptedAt')
        return bool(value and (utc_time(now()) - utc_time(value)).total_seconds() > 86400)

    def save_history(self):
        try:
            self._store.save_history(self._records)
        except (OSError, ValueError, TypeError, RecursionError):
            self._storage_warning = 'write'

    @Slot()
    def check(self):
        if not self.canCheck:
            return
        # Re-read right before the query: an update may have replaced either copy.
        self.resolve_reference()
        self.restore_record()
        if not self.reference:
            self.changed.emit()
            return
        self._busy = True
        self._status = 'checking'
        self._opening_failed = False
        captured = dict(self.reference)
        channel = self._channel
        self._historical = False
        self._record = dict(attemptedAt=now(), completedAt=None, result=None)
        self._records[channel] = dict(key=history_key(captured, channel), attempt=self._record, lastCompleted=self._last_completed or None)
        self.save_history()
        try:
            program, args = self._runner(self.root, captured, channel)
            process = CheckProcess(program, args, captured, channel, self._watchdog_ms, self._record['attemptedAt'], self)
            self._process = process
            process.done.connect(lambda data: self.completed(process, data))
            self.changed.emit()
            process.start()
        except (OSError, ValueError, TypeError):
            self.completed(None, result('unavailable', 'spawn_failed', captured['version'], channel, self._record['attemptedAt']))

    def completed(self, process, data):
        if process is not self._process:
            return
        self._process = None
        self._record = dict(attemptedAt=data['checked_at'], result=data, completedAt=now())
        if data['status'] in ('update_available', 'up_to_date', 'no_release'):
            self._last_completed = self._record
        self._records[self._channel]['attempt'] = self._record
        self._records[self._channel]['lastCompleted'] = self._last_completed or None
        self.save_history()
        self._status = data['status']
        self._busy = False
        if process:
            process.deleteLater()
        self.changed.emit()
        if self._closing and (not self._busy) and (self._process is None) and (not self._close_emitted):
            self._close_emitted = True
            self.closeReady.emit()

    @Slot()
    def openRelease(self):
        if self._busy or self._closing:
            return
        data = self._record.get('result') or {}
        version = data.get('available_version')
        url = data.get('available_url')
        if not version or safe_release_url(url, 'v' + version) != url:
            return
        if self._opener is None:
            from PySide6.QtGui import QDesktopServices
            opened = QDesktopServices.openUrl(QUrl(url))
        else:
            opened = self._opener(url)
        self._opening_failed = not opened
        self.changed.emit()

    @Slot(str)
    def selectChannel(self, channel):
        if channel not in ('stable', 'beta') or self._busy or self._closing:
            return
        if channel == self._channel:
            return
        self._channel = channel
        self.restore_record()
        try:
            self._store.save_preference(channel)
        except (OSError, ValueError):
            self._storage_warning = 'write'
        self.changed.emit()

    @Slot(result=bool)
    def requestClose(self):
        if self._closing:
            return not self._busy
        self._closing = True
        self.changed.emit()
        return not self._busy

def launch(root, reference=_UNSET):
    """Caller supplies verified bundle provenance later; Source reads only metadata."""
    import PySide6
    if tuple((int(part) for part in PySide6.__version__.split('.')[:2])) < (6, 11):
        print('orla: updates desktop requires PySide6 6.11 or newer', file=sys.stderr)
        return 1
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    controller = UpdatesController(root, reference)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('updatesController', controller)
    engine.load(QUrl.fromLocalFile(str(Path(root) / 'workspace/Updates.qml')))
    if not engine.rootObjects():
        return 1
    previous = {}

    def request_exit(*args):
        if controller.requestClose():
            engine.rootObjects()[0].close()
    for number in (signal.SIGTERM, signal.SIGINT):
        previous[number] = signal.signal(number, request_exit)
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(100)
    try:
        return app.exec()
    finally:
        tick.stop()
        for number, handler in previous.items():
            signal.signal(number, handler)
