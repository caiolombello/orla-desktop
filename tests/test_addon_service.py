"""Owned QCore/QProcess runtime with fake bus; no actual registration or sockets."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest import mock

from test_addon_worker import CODE, load, manifest


class Message:
    def __init__(self):
        self.delayed = False

    def setDelayedReply(self, value):
        self.delayed = value

    def createReply(self, payload):
        return payload


class Bus:
    def __init__(self):
        self.connected = True
        self.replies = []
        self.on_send = None

    def isConnected(self):
        return self.connected

    def send(self, message):
        self.replies.append(json.loads(message))
        if self.on_send:
            self.on_send()
        return self.connected


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class Process:
    """Only the OS process boundary is fake; owner/timers/parser are real."""
    def __init__(self, parent):
        from PySide6.QtCore import QProcess
        self.q = QProcess
        self.parent = parent
        self.readyReadStandardOutput, self.finished, self.errorOccurred = Signal(), Signal(), Signal()
        self.buffer = bytearray()
        self.terminations = self.kills = 0
        self.deleted = False
        self.running = QProcess.Starting
        self.code, self.status = 0, QProcess.NormalExit

    def setStandardInputFile(self, value):
        self.stdin = value

    def setStandardErrorFile(self, value):
        self.stderr = value

    def setReadChannel(self, value):
        pass

    def setProgram(self, value):
        self.program = value

    def setArguments(self, value):
        self.args = value

    def setWorkingDirectory(self, value):
        self.cwd = value

    def start(self):
        self.running = self.q.Running

    def bytesAvailable(self):
        return len(self.buffer)

    def read(self, size):
        data = bytes(self.buffer[:size])
        del self.buffer[:size]
        return data

    def closeReadChannel(self, channel):
        self.buffer.clear()

    def terminate(self):
        self.terminations += 1

    def kill(self):
        self.kills += 1

    def state(self):
        return self.running

    def exitCode(self):
        return self.code

    def exitStatus(self):
        return self.status

    def deleteLater(self):
        self.deleted = True

    def write(self, data):
        self.buffer.extend(data)
        self.readyReadStandardOutput.emit()

    def complete(self, code=0, status=None):
        self.code = code
        self.status = status or self.q.NormalExit
        self.running = self.q.NotRunning
        self.finished.emit(self.code, self.status)

class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='addon-service-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir(mode=0o700)
        env = dict(HOME=str(self.home), XDG_DATA_HOME=str(self.root / 'data'),
                   XDG_STATE_HOME=str(self.root / 'state'), DBUS_SESSION_BUS_ADDRESS='',
                   DBUS_SYSTEM_BUS_ADDRESS='')
        self.environment = mock.patch.dict(os.environ, env)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.s = load('addon_service')
        self.bus = Bus()

    def service(self, **kwargs):
        service = self.s.create_service(self.app, self.bus, base=kwargs.pop('base', CODE),
                                        copy_message=lambda value: value, **kwargs)
        self.addCleanup(service.close)
        return service

    def fake_service(self, **kwargs):
        self.clock = [100.0]
        self.processes = []

        def factory(parent):
            process = Process(parent)
            self.processes.append(process)
            return process
        return self.service(process_factory=factory, clock=lambda: self.clock[0], **kwargs)

    def frame(self, **kwargs):
        value = dict(formatVersion='0.1-experimental', ok=True,
                     result=dict(generation=None, addons=[]))
        value.update(kwargs)
        return (json.dumps(value, separators=(',', ':')) + '\n').encode()

    def wait_reply(self):
        deadline = time.monotonic() + 5
        while not self.bus.replies and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.002)
        self.assertTrue(self.bus.replies, 'owned worker did not finish')
        return self.bus.replies[-1]

    def test_real_owned_worker_lists_private_missing_store_and_empty_never_uses_home(self):
        service = self.service()
        empty = service.SnapshotFor([], Message())
        self.assertEqual(json.loads(empty), dict(schemaVersion=2, modules=[]))
        message = Message()
        self.assertEqual(service.ListAddons(message), '')
        self.assertTrue(message.delayed)
        reply = self.wait_reply()
        self.assertEqual(reply, dict(formatVersion='0.1-experimental', ok=True,
                                    result=dict(generation=None, addons=[])))
        self.assertFalse((self.root / 'data').exists())
        self.assertFalse((self.root / 'state').exists())

    def test_all_eight_methods_with_real_owned_workers_and_fake_bus(self):
        service = self.service()

        def invoke(method, *args):
            self.bus.replies.clear()
            self.assertEqual(getattr(service, method)(*args, Message()), '')
            return self.wait_reply()

        p = self.root / 'chosen.json'
        p.write_text(json.dumps(manifest()))
        p.chmod(0o600)
        first = invoke('InspectAddonFile', p.as_uri())['result']['sha256']
        self.assertFalse(invoke('InstallAddon', p.as_uri(), first)['result']['addons'][0]['enabled'])
        self.assertTrue(invoke('EnableAddon', 'org.example.battery', first)['result']['addons'][0]['enabled'])
        snapshot = invoke('SnapshotFor', ['peripherals'])
        self.assertEqual(set(snapshot), {'schemaVersion', 'modules', 'peripherals'})
        self.assertEqual(snapshot['schemaVersion'], 2)
        self.assertEqual(snapshot['peripherals']['addon']['reason'], 'export_missing')
        self.assertFalse(invoke('DisableAddon', 'org.example.battery', first)['result']['addons'][0]['enabled'])
        p.write_text(json.dumps(manifest('2.0.0')))
        second = invoke('InspectAddonFile', p.as_uri())['result']['sha256']
        invoke('InstallAddon', p.as_uri(), second)
        rolled = invoke('RollbackAddon', 'org.example.battery', second)
        self.assertEqual(rolled['result']['addons'][0]['sha256'], first)
        self.assertEqual(invoke('RemoveAddon', 'org.example.battery', first)['result']['addons'], [])
        self.assertEqual(invoke('ListAddons')['result']['addons'], [])

    def test_busy_and_reentrant_send_do_not_start_another_process(self):
        service = self.fake_service()
        # A caller's handled exception must never become the owner's first error.
        try:
            raise RuntimeError('ambient exception privacy sentinel')
        except RuntimeError:
            service.ListAddons(Message())
        self.assertEqual(json.loads(service.ListAddons(Message()))['error']['code'], 'busy')
        during_send = []
        self.bus.on_send = lambda: during_send.append(json.loads(service.ListAddons(Message())))
        self.processes[0].write(self.frame())
        self.assertFalse(self.bus.replies, 'must wait for EOF, not a complete-looking JSON frame')
        self.processes[0].complete()
        self.assertTrue(self.bus.replies[0]['ok'])
        self.assertEqual(during_send[0]['error']['code'], 'busy')
        self.assertEqual(len(self.processes), 1)

    def test_early_deadlines_timeout_kill_and_unreaped_barrier(self):
        service = self.fake_service()
        service.EnableAddon('org.example.battery', 'a' * 64, Message())
        process = self.processes[0]
        self.clock[0] = 102.999
        service.expired()
        self.assertEqual(process.terminations, 0)
        self.clock[0] = 103.0
        service.expired()
        self.assertEqual(process.terminations, 1)
        service.kill()  # Early QTimer fire must re-arm, not kill early.
        self.assertEqual(process.kills, 0)
        self.clock[0] = 103.25
        service.kill()
        self.assertEqual(process.kills, 1)
        self.clock[0] = 103.999
        service.cleanup_failed()
        self.assertFalse(self.bus.replies)
        self.clock[0] = 104.0
        service.cleanup_failed()
        self.assertEqual(self.bus.replies[0]['error'],
                         dict(code='timeout', committed=None, generation=None))
        self.assertFalse(process.deleted)
        self.assertFalse(json.loads(service.ListAddons(Message()))['ok'])
        self.assertEqual(len(self.processes), 1)
        process.complete(9, process.q.CrashExit)
        self.assertTrue(process.deleted)
        self.assertEqual(len(self.bus.replies), 1)
        self.assertFalse(json.loads(service.ListAddons(Message()))['ok'])

    def test_late_mutation_eof_keeps_known_commit_but_never_publishes_success(self):
        service = self.fake_service()
        service.DisableAddon('org.example.battery', 'a' * 64, Message())
        process = self.processes[0]
        process.write(self.frame(result=dict(generation='b' * 32, addons=[])))
        self.clock[0] = 103
        process.complete()
        self.assertEqual(self.bus.replies[0]['error'],
                         dict(code='timeout', committed=True, generation='b' * 32))

    def test_backend_postcommit_error_is_preserved(self):
        service = self.fake_service()
        service.RemoveAddon('org.example.battery', 'a' * 64, Message())
        self.processes[0].write(self.frame(ok=False, error=dict(code='io', committed=True,
                                                               generation='b' * 32), result=None).replace(b',"result":null', b''))
        self.processes[0].complete(1)
        self.assertEqual(self.bus.replies[0]['error'],
                         dict(code='io', committed=True, generation='b' * 32))

    def test_malformed_trailing_overflow_and_exit_disagreement_are_rejected(self):
        candidates = [self.frame() + b'{}', self.frame().replace(b'"ok":true', b'"ok":true,"ok":true'),
                      self.frame().replace(b'null', b'NaN', 1),
                      self.frame().replace(b'null', b'1e999', 1), b'x' * 262145,
                      b'[' * 18 + b']' * 18 + b'\n', b'\xff\n', self.frame()]
        for index, data in enumerate(candidates):
            with self.subTest(index=index):
                self.bus.replies.clear()
                service = self.fake_service()
                service.ListAddons(Message())
                process = self.processes[-1]
                process.write(data)
                process.complete(1 if index == len(candidates) - 1 else 0)
                self.assertEqual(self.bus.replies[0]['error']['code'], 'invalid_response')
                service.close()

    def test_missing_commit_fields_unknown_codes_and_private_result_fields_are_rejected(self):
        candidates = [dict(formatVersion='0.1-experimental', ok=False, error=dict(code='io', generation=None)),
                      dict(formatVersion='0.1-experimental', ok=False, error=dict(code='raw exception', committed=False, generation=None)),
                      dict(formatVersion='0.1-experimental', ok=False, error=dict(code='io', committed=True, generation=None)),
                      dict(formatVersion='0.1-experimental', ok=True, result=dict(generation=None, addons=[], path='private sentinel'))]
        for value in candidates:
            with self.subTest(value=value):
                self.bus.replies.clear()
                service = self.fake_service()
                service.RemoveAddon('org.example.battery', 'a' * 64, Message())
                process = self.processes[0]
                process.write((json.dumps(value) + '\n').encode())
                process.complete(0 if value['ok'] else 1)
                self.assertEqual(self.bus.replies[0]['error'],
                                 dict(code='invalid_response', committed=None, generation=None))
                self.assertNotIn('sentinel', json.dumps(self.bus.replies))
                self.assertEqual(len(self.processes), 1)
                service.close()

    def test_close_and_disconnect_never_reopen_admission(self):
        for disconnect in (False, True):
            with self.subTest(disconnect=disconnect):
                self.bus.connected = True
                service = self.fake_service()
                service.ListAddons(Message())
                process = self.processes[0]
                if disconnect:
                    self.bus.connected = False
                    service.watch_identity()
                else:
                    service.close()
                self.assertEqual(process.terminations, 1)
                self.assertFalse(json.loads(service.ListAddons(Message()))['ok'])
                process.write(self.frame())
                process.complete()
                self.bus.connected = True
                self.assertFalse(json.loads(service.ListAddons(Message()))['ok'])

    def test_empty_selection_does_not_lookup_environment_or_construct_paths(self):
        service = self.service()
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(json.loads(service.SnapshotFor([], Message())),
                             dict(schemaVersion=2, modules=[]))
        for modules in (['quota'], ['peripherals', 'peripherals'], ['peripherals', 'recording'], 'peripherals'):
            self.assertEqual(json.loads(service.SnapshotFor(modules, Message()))['error']['code'], 'format')

    def test_source_change_stops_owned_worker_and_rejects_old_success(self):
        base = self.root / 'source'
        base.mkdir(mode=0o700)
        for name in load('addon_worker').SOURCE_NAMES:
            shutil.copyfile(CODE / name, base / name)
        service = self.fake_service(base=base)
        service.ListAddons(Message())
        process = self.processes[0]
        (base / 'addon_io.py').write_bytes((base / 'addon_io.py').read_bytes() + b'\n# changed\n')
        service.watch_identity()
        self.assertEqual(process.terminations, 1)
        process.write(self.frame())
        process.complete()
        self.assertEqual(self.bus.replies[0]['error']['code'], 'source_changed')
        self.assertFalse(json.loads(service.ListAddons(Message()))['ok'])
        self.assertEqual(len(self.processes), 1)

    def test_identity_poll_is_fast_only_while_a_worker_is_in_flight(self):
        service = self.fake_service()
        self.assertTrue(service.watch.isActive())
        self.assertEqual(service.watch.interval(), self.s.IDLE_WATCH_MS)
        self.assertGreaterEqual(self.s.IDLE_WATCH_MS, 1000)
        service.ListAddons(Message())
        self.assertEqual(service.watch.interval(), self.s.FLIGHT_WATCH_MS)
        self.processes[0].write(self.frame())
        self.processes[0].complete()
        self.assertTrue(self.bus.replies[0]['ok'])
        self.assertEqual(service.watch.interval(), self.s.IDLE_WATCH_MS)
        self.assertTrue(service.watch.isActive())

    def test_source_file_event_retires_idle_host_before_the_slow_poll(self):
        base = self.root / 'source'
        base.mkdir(mode=0o700)
        for name in load('addon_worker').SOURCE_NAMES:
            shutil.copyfile(CODE / name, base / name)
        service = self.fake_service(base=base)
        (base / 'addon_io.py').write_bytes((base / 'addon_io.py').read_bytes() + b'\n# changed\n')
        deadline = time.monotonic() + 2
        while not service.obsolete and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(service.obsolete)
        self.assertFalse(service.watch.isActive())
        self.assertFalse(json.loads(service.ListAddons(Message()))['ok'])
        self.assertEqual(self.processes, [])

    def test_failed_to_start_proves_no_commit_and_preserves_first_failure(self):
        service = self.fake_service()
        service.EnableAddon('org.example.battery', 'a' * 64, Message())
        process = self.processes[0]
        process.running = process.q.NotRunning
        process.errorOccurred.emit(process.q.FailedToStart)
        self.assertEqual(self.bus.replies[0]['error'],
                         dict(code='unavailable', committed=False, generation=None))
        self.assertTrue(process.deleted)

    def test_late_old_process_signals_cannot_cancel_new_owned_request(self):
        service = self.fake_service()
        service.ListAddons(Message())
        old = self.processes[0]
        old.write(self.frame())
        old.complete()
        service.ListAddons(Message())
        current = self.processes[1]
        old.finished.emit(7, old.q.CrashExit)
        old.errorOccurred.emit(old.q.ReadError)
        self.assertEqual(current.terminations, 0)
        self.assertEqual(len(self.bus.replies), 1)
        current.write(self.frame())
        current.complete()
        self.assertEqual(len(self.bus.replies), 2)
        self.assertTrue(self.bus.replies[-1]['ok'])

    def test_actual_qt_slots_delayed_message_copy_and_one_string_reply(self):
        from PySide6.QtCore import QObject
        from PySide6.QtDBus import QDBusMessage
        class MessageBus(Bus):
            def send(self, message):
                arguments = message.arguments()
                if len(arguments) != 1 or type(arguments[0]) is not str:
                    raise AssertionError('one string reply expected')
                return super().send(arguments[0])
        self.bus = MessageBus()
        service = self.s.create_service(self.app, self.bus, base=CODE)
        self.addCleanup(service.close)
        meta = service.metaObject()
        slots = {bytes(meta.method(i).methodSignature()).decode():
                 bytes(meta.method(i).typeName()).decode() if not isinstance(meta.method(i).typeName(), str)
                 else meta.method(i).typeName()
                 for i in range(QObject.staticMetaObject.methodCount(), meta.methodCount())}
        self.assertEqual(slots, {
            'ListAddons(QDBusMessage)': 'QString',
            'InspectAddonFile(QString,QDBusMessage)': 'QString',
            'InstallAddon(QString,QString,QDBusMessage)': 'QString',
            'EnableAddon(QString,QString,QDBusMessage)': 'QString',
            'DisableAddon(QString,QString,QDBusMessage)': 'QString',
            'RemoveAddon(QString,QString,QDBusMessage)': 'QString',
            'RollbackAddon(QString,QString,QDBusMessage)': 'QString',
            'SnapshotFor(QStringList,QDBusMessage)': 'QString'})
        message = QDBusMessage.createMethodCall(self.s.BUS, self.s.OBJECT, self.s.INTERFACE, 'ListAddons')
        self.assertEqual(service.ListAddons(message), '')
        self.assertTrue(message.isDelayedReply())
        self.assertTrue(self.wait_reply()['ok'])
        after = service.metaObject()
        self.assertEqual(after.methodCount(), QObject.staticMetaObject.methodCount() + 8,
                         'process signal wiring must not export dynamic helper slots')


if __name__ == '__main__':
    unittest.main()
