"""Fake-only tests for the private AI text transport lifecycle."""

from __future__ import annotations

import importlib.util
import ast
import contextlib
import hashlib
import http.client
import io
import json
from pathlib import Path
import socket
import ssl
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ai_text_transport.py"


def load_target():
    spec = importlib.util.spec_from_file_location("orla_ai_text_transport_test", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("transport helper could not be loaded")
    target = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = target
    spec.loader.exec_module(target)
    return target


class FakeClock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeReader:
    def __init__(self, chunks, on_read=None):
        self.chunks = list(chunks)
        self.calls = []
        self.on_read = on_read

    def read1(self, limit, timeout):
        self.calls.append((limit, timeout))
        if self.on_read is not None:
            self.on_read(len(self.calls))
        if not self.chunks:
            raise AssertionError("reader exhausted without EOF fixture")
        value = self.chunks.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class FakeSignals:
    def __init__(self, *, fail_at=(), cancel_hooks=(), timer=(0.0, 0.0)):
        self.calls = []
        self.counts = {}
        self.fail_at = set(fail_at)
        self.cancel_hooks = set(cancel_hooks)
        self.timer = timer
        self.handlers = {name: f"original-{name}" for name in (
            "SIGINT", "SIGTERM", "SIGALRM",
        )}

    def _step(self, name, call):
        self.calls.append(call)
        count = self.counts.get(name, 0) + 1
        self.counts[name] = count
        if (name, count) in self.fail_at:
            raise RuntimeError("synthetic boundary failure")
        return count

    def block(self, names):
        self._step("block", ("block", tuple(names)))
        return "original-mask"

    def get_handler(self, name):
        self._step("get_handler", ("get_handler", name))
        return self.handlers[name]

    def get_timer(self):
        self._step("get_timer", ("get_timer",))
        return self.timer

    def install_handler(self, name, handler):
        self._step("install_handler", ("install_handler", name))
        self.handlers[name] = handler

    def arm_timer(self, seconds):
        self._step("arm_timer", ("arm_timer", seconds))

    def cancel_timer(self):
        self._step("cancel_timer", ("cancel_timer",))

    def restore_handler(self, name, handler):
        self._step("restore_handler", ("restore_handler", name, handler))
        self.handlers[name] = handler

    def restore_mask(self, mask):
        self._step("restore_mask", ("restore_mask", mask))

    def hook(self, name, token):
        self._step("hook", ("hook", name))
        if name in self.cancel_hooks:
            token.cancel()


class RecordingSink:
    def __init__(self, fail_at=None, on_publish=None):
        self.events = []
        self.fail_at = fail_at
        self.on_publish = on_publish
        self.attempts = 0

    def publish(self, event):
        self.attempts += 1
        if self.attempts == self.fail_at:
            raise BrokenPipeError()
        self.events.append(event)
        if self.on_publish is not None:
            self.on_publish(event)


class FakeResponse:
    def __init__(self, chunks, trace, *, on_read=None, close_error=False):
        self.chunks = list(chunks)
        self.trace = trace
        self.calls = []
        self.on_read = on_read
        self.close_error = close_error

    def read1(self, limit, timeout):
        self.calls.append((limit, timeout))
        if self.on_read is not None:
            self.on_read(len(self.calls))
        if not self.chunks:
            raise AssertionError("response exhausted without EOF fixture")
        value = self.chunks.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.trace.append("response.close")
        if self.close_error:
            raise RuntimeError("synthetic close failure")


class FakeConnector:
    def __init__(self, response, trace, *, clock=None, advance_connect=0.0,
                 close_error=False):
        self.response = response
        self.trace = trace
        self.calls = []
        self.clock = clock
        self.advance_connect = advance_connect
        self.close_error = close_error

    def connect(self, timeout):
        self.calls.append(("connect", timeout))
        if self.clock is not None:
            self.clock.now += self.advance_connect

    def send(self, headers, body, timeout):
        self.calls.append(("send", headers, body, timeout))

    def receive_headers(self, timeout):
        self.calls.append(("receive_headers", timeout))
        return self.response

    def close(self):
        self.trace.append("connector.close")
        if self.close_error:
            raise RuntimeError("synthetic close failure")


class FakeSocket:
    def __init__(self):
        self.calls = []

    def settimeout(self, timeout):
        self.calls.append(("settimeout", timeout))

    def connect(self, address):
        self.calls.append(("connect", address))

    def close(self):
        self.calls.append(("close",))


class FakeHTTPResponse:
    def __init__(self, chunks=(), *, status=200, headers=(), close_error=False):
        self.status = status
        self.headers = list(headers)
        self.chunks = list(chunks)
        self.calls = []
        self.close_calls = 0
        self.close_error = close_error

    def getheaders(self):
        self.calls.append(("getheaders",))
        return list(self.headers)

    def read1(self, limit):
        self.calls.append(("read1", limit))
        if not self.chunks:
            raise AssertionError("HTTP response exhausted without EOF fixture")
        value = self.chunks.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.close_calls += 1
        if self.close_error:
            raise OSError("synthetic response close fault")


class FakeHTTPConnection:
    def __init__(self, response, *, authorization_digest=None):
        self.response = response
        self.sock = FakeSocket()
        self.timeout = None
        self.calls = []
        self.authorization_digest = authorization_digest

    def connect(self):
        self.calls.append(("connect", self.timeout))

    def putrequest(self, method, path, **kwargs):
        self.calls.append(("putrequest", method, path, kwargs))

    def putheader(self, name, value):
        if name == "Authorization" and self.authorization_digest is not None:
            digest = hashlib.sha256(value).hexdigest()
            if digest != self.authorization_digest:
                raise AssertionError("unexpected synthetic authorization value")
            self.calls.append(("putheader", name, len(value), digest))
            return
        self.calls.append(("putheader", name, value))

    def endheaders(self, body, *, encode_chunked):
        self.calls.append(("endheaders", body, encode_chunked))

    def getresponse(self):
        self.calls.append(("getresponse",))
        return self.response

    def close(self):
        self.calls.append(("close",))
        self.sock.close()


class FakeOwnedSocket(FakeSocket):
    def __init__(self, *, close_error=False, handshake_error=None):
        super().__init__()
        self.close_error = close_error
        self.handshake_error = handshake_error
        self.closed = False

    def do_handshake(self):
        self.calls.append(("do_handshake",))
        if self.handshake_error is not None:
            raise self.handshake_error

    def close(self):
        self.calls.append(("close",))
        if self.close_error:
            raise OSError("synthetic owned socket close fault")
        self.closed = True


class FakeTLSPort:
    def __init__(self, wrapped=None, *, wrap_error=None, detach_before_error=False):
        self.verify_mode = ssl.CERT_REQUIRED
        self.check_hostname = True
        self.keylog_filename = None
        self.wrapped = wrapped or FakeOwnedSocket()
        self.wrap_error = wrap_error
        self.detach_before_error = detach_before_error
        self.calls = []

    def wrap_socket(self, raw, **kwargs):
        self.calls.append(("wrap_socket", raw, kwargs))
        if self.detach_before_error:
            raw.detached = True
        if self.wrap_error is not None:
            raise self.wrap_error
        raw.detached = True
        return self.wrapped


class FakeTCPPort:
    def __init__(self, raw=None, *, clock=None, advance=0.0, error=None):
        self.raw = raw or FakeOwnedSocket()
        self.clock = clock
        self.advance = advance
        self.error = error
        self.calls = []

    def acquire(self, *, host, port, budget):
        self.calls.append((host, port, budget))
        if self.clock is not None:
            self.clock.now += self.advance
        if self.error is not None:
            raise self.error
        return self.raw


class RefCountedFile(io.BytesIO):
    def __init__(self, wire, sock, fragment):
        super().__init__(wire)
        self.sock = sock
        self.fragment = fragment

    def read1(self, limit=-1):
        return super().read(min(limit, self.fragment) if limit >= 0 else self.fragment)

    def close(self):
        if not self.closed:
            self.sock.refs -= 1
            if self.sock.closed and not self.sock.refs:
                self.sock.fd_open = False
            self.sock.calls.append(("release_file",))
        super().close()


class RefCountedSocket(FakeSocket):
    """Memory socket matching socket.makefile deferred-close ownership."""

    def __init__(self, wire=b"", *, fragment=8192, connect_fault=False,
                 settimeout_fault=False, close_fault=False):
        super().__init__()
        self.wire = wire
        self.fragment = fragment
        self.connect_fault = connect_fault
        self.settimeout_fault = settimeout_fault
        self.close_fault = close_fault
        self.refs = 0
        self.closed = False
        self.fd_open = True

    def settimeout(self, timeout):
        super().settimeout(timeout)
        if self.settimeout_fault:
            raise OSError("synthetic timeout setup fault")
        if not self.fd_open:
            raise OSError("synthetic closed descriptor")

    def connect(self, address):
        super().connect(address)
        if self.connect_fault:
            raise ConnectionRefusedError("synthetic partial connect")

    def sendall(self, data):
        self.calls.append(("sendall", bytes(data)))

    def do_handshake(self):
        self.calls.append(("do_handshake",))

    def makefile(self, mode):
        self.assert_mode = mode
        self.refs += 1
        return RefCountedFile(self.wire, self, self.fragment)

    def close(self):
        self.calls.append(("close",))
        if self.close_fault:
            raise OSError("synthetic close fault")
        self.closed = True
        if not self.refs:
            self.fd_open = False


class AiTextTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = load_target()

    def setUp(self):
        def blocked(*_args, **_kwargs):
            raise AssertionError("network access is forbidden in fake-only tests")

        for name in ("socket", "create_connection", "getaddrinfo"):
            patcher = mock.patch.object(socket, name, blocked)
            patcher.start()
            self.addCleanup(patcher.stop)
        context_patcher = mock.patch.object(
            ssl, "create_default_context", side_effect=AssertionError(
                "real SSL context creation is forbidden in fake-only tests",
            ),
        )
        context_patcher.start()
        self.addCleanup(context_patcher.stop)
        wrap_patcher = mock.patch.object(
            ssl.SSLContext, "wrap_socket", side_effect=AssertionError(
                "real SSL wrapping is forbidden in fake-only tests",
            ),
        )
        wrap_patcher.start()
        self.addCleanup(wrap_patcher.stop)

    def request_wire(self, **changes):
        request = {
            "schemaVersion": 1,
            "requestId": "txt-transport.1",
            "provider": "ollama_local",
            "task": "rewrite",
            "targetLanguage": None,
            "text": "Revise this sentence.",
            "model": "gemma3:4b",
            "endpoint": "http://127.0.0.1:11434",
            "credentialBytes": 0,
        }
        request.update(changes)
        return json.dumps(request, separators=(",", ":")).encode() + b"\n"

    def run_local(self, response_chunks, *, signals=None, clock=None,
                  response_options=None, connector_options=None, sink=None,
                  reader=None):
        trace = []
        clock = clock or FakeClock()
        signals = signals or FakeSignals()
        response = FakeResponse(response_chunks, trace, **(response_options or {}))
        connector = FakeConnector(
            response, trace, clock=clock, **(connector_options or {})
        )
        sink = sink or RecordingSink()
        reader = reader or FakeReader([self.request_wire(), b""])
        specs = []
        outcome = self.target._run_call(
            input_reader=reader,
            connector_factory=lambda spec: specs.append(spec) or connector,
            clock=clock, signal_boundary=signals, sink=sink,
        )
        return outcome, sink, connector, response, signals, trace, specs

    @staticmethod
    def ollama_body():
        return {
            "model": "gemma3:4b",
            "messages": [
                {"role": "system", "content": "Rewrite exactly."},
                {"role": "user", "content": "Revise this sentence."},
            ],
            "stream": True,
            "options": {"num_predict": 1024},
        }

    def make_numeric_connector(self, *, url="http://127.0.0.1:11434/api/chat",
                               response=None):
        connection = FakeHTTPConnection(response or FakeHTTPResponse())
        connector = self.target._OllamaNumericConnector(
            {"provider": "ollama_local", "url": url},
            connection_factory=lambda **_kwargs: connection,
        )
        return connector, connection

    @staticmethod
    def openai_body():
        return {
            "model": "gpt-5-mini",
            "instructions": "Rewrite clearly.",
            "input": "Revise this sentence.",
            "stream": True,
            "store": False,
            "tools": [],
            "max_output_tokens": 1024,
        }

    def make_openai_connector(self, *, response=None, context=None,
                              connection=None, clock=None, tcp_port=None):
        response = response or FakeHTTPResponse(headers=(
            ("Content-Type", "text/event-stream"),
        ))
        connection = connection or FakeHTTPConnection(response)
        context = context or FakeTLSPort()
        tcp_port = tcp_port or FakeTCPPort()
        clock = clock or FakeClock()
        factory_calls = []

        def connection_factory(**kwargs):
            factory_calls.append(kwargs)
            return connection

        connector = self.target._OpenAIHTTPSConnector(
            {"provider": "openai_api",
             "url": "https://api.openai.com/v1/responses"},
            tcp_port=tcp_port, clock=clock,
            context_factory=lambda: context,
            connection_factory=connection_factory,
        )
        return connector, connection, context, tcp_port, factory_calls

    def test_openai_connector_requires_acquire_member_and_valid_context(self):
        valid_spec = {
            "provider": "openai_api",
            "url": "https://api.openai.com/v1/responses",
        }
        context_calls = []
        for port in (None, object(), type("Port", (), {"acquire": 3})()):
            with self.subTest(port=type(port).__name__):
                with self.assertRaises(self.target._contract.ContractError):
                    self.target._OpenAIHTTPSConnector(
                        valid_spec, tcp_port=port, clock=FakeClock(),
                        context_factory=lambda: context_calls.append(1),
                    )
        self.assertEqual(context_calls, [])

        for changes in (
                {"verify_mode": ssl.CERT_NONE},
                {"check_hostname": False},
                {"keylog_filename": "synthetic-keylog"}):
            with self.subTest(changes=changes):
                context = FakeTLSPort()
                for name, value in changes.items():
                    setattr(context, name, value)
                port = FakeTCPPort()
                with self.assertRaises(self.target._contract.ContractError):
                    self.target._OpenAIHTTPSConnector(
                        valid_spec, tcp_port=port, clock=FakeClock(),
                        context_factory=lambda: context,
                    )
                self.assertEqual(port.calls, [])

    def test_openai_connector_rejects_every_destination_drift_before_factories(self):
        cases = (
            {},
            {"provider": "openai_api"},
            {"url": "https://api.openai.com/v1/responses"},
            {"provider": "ollama_local",
             "url": "https://api.openai.com/v1/responses"},
            {"provider": "openai_api",
             "url": "http://api.openai.com/v1/responses"},
            {"provider": "openai_api",
             "url": "https://api.openai.com:443/v1/responses"},
            {"provider": "openai_api",
             "url": "https://api.openai.com/v1/responses/"},
            {"provider": "openai_api",
             "url": "https://example.invalid/v1/responses"},
            {"provider": "openai_api",
             "url": "https://api.openai.com/v1/responses", "extra": True},
        )
        for spec in cases:
            with self.subTest(spec=spec):
                context_calls = []
                port = FakeTCPPort()
                with self.assertRaises(self.target._contract.ContractError):
                    self.target._OpenAIHTTPSConnector(
                        spec, tcp_port=port, clock=FakeClock(),
                        context_factory=lambda: context_calls.append(1),
                    )
                self.assertEqual(context_calls, [])
                self.assertEqual(port.calls, [])

    def test_openai_connection_retains_raw_wraps_without_auto_handshake_then_handshakes(self):
        clock = FakeClock()
        raw = FakeOwnedSocket()
        wrapped = FakeOwnedSocket()
        tcp_port = FakeTCPPort(raw, clock=clock, advance=1.25)
        context = FakeTLSPort(wrapped)
        connection = self.target._OpenAIHTTPSConnection(
            host="api.openai.com", port=443, context=context,
            tcp_port=tcp_port, clock=clock, timeout=None,
        )
        connection.timeout = 5.0
        connection.connect()
        self.assertEqual(tcp_port.calls, [("api.openai.com", 443, 5.0)])
        self.assertEqual(raw.calls, [("settimeout", 3.75)])
        self.assertEqual(context.calls, [(
            "wrap_socket", raw, {
                "server_hostname": "api.openai.com",
                "do_handshake_on_connect": False,
            },
        )])
        self.assertEqual(wrapped.calls, [
            ("settimeout", 3.75), ("do_handshake",),
        ])
        self.assertIs(connection.sock, wrapped)
        self.assertIsNone(connection._owned_raw_socket)
        self.assertIs(connection._owned_tls_socket, wrapped)

    def test_openai_connection_rejects_returned_overshoot_and_retains_close_fault(self):
        for close_error, cleanup_fails in ((False, False), (True, True)):
            with self.subTest(close_error=close_error):
                clock = FakeClock()
                raw = FakeOwnedSocket(close_error=close_error)
                connection = self.target._OpenAIHTTPSConnection(
                    host="api.openai.com", port=443, context=FakeTLSPort(),
                    tcp_port=FakeTCPPort(raw, clock=clock, advance=5.0),
                    clock=clock, timeout=5.0,
                )
                with self.assertRaises(TimeoutError):
                    connection.connect()
                with self.assertRaises(OSError) if cleanup_fails else contextlib.nullcontext():
                    connection.close()
                self.assertEqual(raw.calls, [("close",)])
                self.assertIs(connection._owned_raw_socket, raw if cleanup_fails else None)

    def test_openai_connection_rechecks_budget_at_each_tls_boundary(self):
        class AdvancingSocket(FakeOwnedSocket):
            def __init__(self, clock, seam):
                super().__init__()
                self.clock = clock
                self.seam = seam

            def settimeout(self, timeout):
                super().settimeout(timeout)
                if self.seam == "settimeout":
                    self.clock.now += 5.0

            def do_handshake(self):
                super().do_handshake()
                if self.seam == "handshake":
                    self.clock.now += 5.0

        cases = ("raw-timeout", "tls-timeout", "handshake")
        for seam in cases:
            with self.subTest(seam=seam):
                clock = FakeClock()
                raw = AdvancingSocket(
                    clock, "settimeout" if seam == "raw-timeout" else None,
                )
                wrapped = AdvancingSocket(
                    clock, ("settimeout" if seam == "tls-timeout"
                            else "handshake" if seam == "handshake" else None),
                )
                context = FakeTLSPort(wrapped)
                connection = self.target._OpenAIHTTPSConnection(
                    host="api.openai.com", port=443, context=context,
                    tcp_port=FakeTCPPort(raw), clock=clock, timeout=5.0,
                )
                with self.assertRaises(TimeoutError):
                    connection.connect()
                connection.close()
                if seam == "raw-timeout":
                    self.assertEqual(context.calls, [])
                    self.assertTrue(raw.closed)
                    self.assertFalse(wrapped.closed)
                else:
                    self.assertEqual(len(context.calls), 1)
                    self.assertTrue(wrapped.closed)
                    self.assertEqual(
                        sum(call[0] == "do_handshake" for call in wrapped.calls),
                        0 if seam == "tls-timeout" else 1,
                    )

    def test_openai_connection_marks_every_tcp_nonreturn_unconfirmed(self):
        for error in (TimeoutError("synthetic timeout"),
                      ConnectionRefusedError("synthetic refused"),
                      OSError("synthetic hidden close fault")):
            with self.subTest(error=type(error).__name__):
                connection = self.target._OpenAIHTTPSConnection(
                    host="api.openai.com", port=443, context=FakeTLSPort(),
                    tcp_port=FakeTCPPort(error=error), clock=FakeClock(), timeout=5.0,
                )
                with self.assertRaises(type(error)):
                    connection.connect()
                self.assertTrue(connection._tcp_acquisition_unconfirmed)
                self.assertIsNone(connection._owned_raw_socket)
                with self.assertRaises(OSError):
                    connection.close()

    def test_openai_connection_wrap_nonreturn_is_unconfirmed_without_hidden_handle(self):
        for detached in (False, True):
            with self.subTest(detached=detached):
                raw = FakeOwnedSocket()
                context = FakeTLSPort(
                    wrap_error=ssl.SSLError("synthetic wrap failure"),
                    detach_before_error=detached,
                )
                connection = self.target._OpenAIHTTPSConnection(
                    host="api.openai.com", port=443, context=context,
                    tcp_port=FakeTCPPort(raw), clock=FakeClock(), timeout=5.0,
                )
                with self.assertRaises(ssl.SSLError):
                    connection.connect()
                self.assertTrue(connection._wrap_transfer_unconfirmed)
                self.assertIsNone(connection._owned_tls_socket)
                with self.assertRaises(OSError):
                    connection.close()
                self.assertEqual(raw.calls, [("settimeout", 5.0), ("close",)])
                self.assertEqual(getattr(raw, "detached", False), detached)

    def test_openai_connector_classifies_visible_handshake_and_cleanup_faults(self):
        for close_error, expected_cleanup in ((False, False), (True, True)):
            with self.subTest(close_error=close_error):
                wrapped = FakeOwnedSocket(
                    close_error=close_error,
                    handshake_error=ssl.SSLCertVerificationError(
                        "synthetic certificate marker",
                    ),
                )
                connector = self.target._OpenAIHTTPSConnector(
                    {"provider": "openai_api",
                     "url": "https://api.openai.com/v1/responses"},
                    tcp_port=FakeTCPPort(FakeOwnedSocket()), clock=FakeClock(),
                    context_factory=lambda: FakeTLSPort(wrapped),
                )
                with self.assertRaises(self.target._TransportFailure) as caught:
                    connector.connect(5.0)
                self.assertEqual((caught.exception.code, caught.exception.retryable),
                                 ("tls_failed", False))
                with self.assertRaises(OSError) if expected_cleanup else contextlib.nullcontext():
                    connector.close()

    def test_openai_connector_sends_exact_ordered_request_and_wipes_bearer(self):
        credential = bytearray(b"synthetic-openai-key-12345")
        bearer_digest = hashlib.sha256(b"Bearer " + credential).hexdigest()
        connection = FakeHTTPConnection(
            FakeHTTPResponse(headers=(("Content-Type", "text/event-stream"),)),
            authorization_digest=bearer_digest,
        )
        connector, connection, _context, _port, factory_calls = (
            self.make_openai_connector(connection=connection)
        )
        connector.connect(4.0)
        connector.send((("Authorization", credential),), self.openai_body(), 3.0)
        encoded = json.dumps(
            self.openai_body(), ensure_ascii=False, allow_nan=False,
            separators=(",", ":"),
        ).encode()
        self.assertEqual(factory_calls[0]["host"], "api.openai.com")
        self.assertEqual(factory_calls[0]["port"], 443)
        self.assertEqual(connection.calls, [
            ("connect", 4.0),
            ("putrequest", "POST", "/v1/responses", {
                "skip_host": True, "skip_accept_encoding": True,
            }),
            ("putheader", "Host", "api.openai.com"),
            ("putheader", "Content-Type", "application/json"),
            ("putheader", "Accept", "text/event-stream"),
            ("putheader", "Accept-Encoding", "identity"),
            ("putheader", "Content-Length", str(len(encoded))),
            ("putheader", "Connection", "close"),
            ("putheader", "Authorization", len(b"Bearer ") + len(credential),
             bearer_digest),
            ("endheaders", encoded, False),
        ])
        self.assertEqual(connection.sock.calls, [("settimeout", 3.0)])
        self.assertEqual(credential, bytearray(b"synthetic-openai-key-12345"))

    def test_openai_bearer_buffer_is_wiped_when_header_send_fails(self):
        class FailingHeaderConnection(FakeHTTPConnection):
            def putheader(self, name, value):
                if name == "Authorization":
                    raise OSError("synthetic header write fault")
                super().putheader(name, value)

        connection = FailingHeaderConnection(FakeHTTPResponse())
        connector, *_rest = self.make_openai_connector(connection=connection)
        connector.connect(4.0)
        credential = bytearray(b"synthetic-openai-key-12345")
        wiped = []
        original_wipe = self.target._wipe

        def observe(buffer):
            if isinstance(buffer, bytearray) and len(buffer) > len(credential):
                wiped.append(buffer)
            original_wipe(buffer)

        with mock.patch.object(self.target, "_wipe", side_effect=observe):
            with self.assertRaises(self.target._TransportFailure):
                connector.send(
                    (("Authorization", credential),), self.openai_body(), 3.0,
                )
        self.assertEqual(len(wiped), 1)
        self.assertTrue(all(value == 0 for value in wiped[0]))
        self.assertEqual(credential, bytearray(b"synthetic-openai-key-12345"))

    def test_openai_bearer_wipe_fault_is_sticky_after_success_or_send_fault(self):
        marker = b"synthetic-openai-key-12345"
        bearer_digest = hashlib.sha256(b"Bearer " + marker).hexdigest()

        class SendConnection(FakeHTTPConnection):
            def __init__(self, response, *, fail_send):
                super().__init__(response, authorization_digest=bearer_digest)
                self.fail_send = fail_send

            def endheaders(self, body, *, encode_chunked):
                super().endheaders(body, encode_chunked=encode_chunked)
                if self.fail_send:
                    raise OSError("synthetic prior send fault")

        stream = (
            b'event: response.created\ndata: {"type":"response.created",'
            b'"response":{"status":"in_progress"}}\n\n'
            b'event: response.completed\ndata: {"type":"response.completed",'
            b'"response":{"status":"completed"}}\n\n'
        )
        for fail_send in (False, True):
            with self.subTest(fail_send=fail_send):
                response = FakeHTTPResponse(
                    [stream, b""], headers=(
                        ("Content-Type", "text/event-stream"),
                        ("Content-Length", str(len(stream))),
                    ),
                )
                connection = SendConnection(response, fail_send=fail_send)
                clock = FakeClock()
                bearer_buffers = []
                original_buffers = []
                original_wipe = self.target._wipe

                def faulted_wipe(buffer):
                    if (isinstance(buffer, bytearray) and
                            buffer.startswith(b"Bearer ")):
                        bearer_buffers.append(buffer)
                        raise RuntimeError("synthetic mutable wipe fault")
                    if isinstance(buffer, bytearray) and len(buffer) == len(marker):
                        original_buffers.append(buffer)
                    original_wipe(buffer)

                def factory(spec):
                    return self.target._OpenAIHTTPSConnector(
                        spec, tcp_port=FakeTCPPort(), clock=clock,
                        context_factory=FakeTLSPort,
                        connection_factory=lambda **_kwargs: connection,
                    )

                sink = RecordingSink()
                try:
                    with mock.patch.object(
                            self.target, "_wipe", side_effect=faulted_wipe):
                        outcome = self.target._run_call(
                            input_reader=FakeReader([
                                self.request_wire(
                                    provider="openai_api", endpoint=None,
                                    model="gpt-5-mini",
                                    credentialBytes=len(marker),
                                ) + marker,
                                b"",
                            ]),
                            connector_factory=factory, clock=clock,
                            signal_boundary=FakeSignals(), sink=sink,
                        )
                    self.assertEqual(
                        (outcome.terminal, outcome.code, outcome.retryable),
                        ("failed", "process_cleanup_failed", False),
                    )
                    self.assertEqual([event["type"] for event in sink.events],
                                     ["started", "failed"])
                    self.assertIn(("close",), connection.calls)
                    self.assertEqual(len(bearer_buffers), 1)
                    self.assertTrue(original_buffers)
                    self.assertTrue(all(not any(buffer)
                                        for buffer in original_buffers))
                finally:
                    for buffer in bearer_buffers:
                        original_wipe(buffer)

    def test_openai_response_is_owned_before_status_or_media_rejection(self):
        cases = (
            FakeHTTPResponse(status=503, headers=()),
            FakeHTTPResponse(status=200, headers=(("Content-Type", "text/plain"),)),
        )
        for raw in cases:
            with self.subTest(status=raw.status):
                connector, connection, *_rest = self.make_openai_connector(response=raw)
                with self.assertRaises((self.target._TransportFailure,
                                        self.target._contract.ContractError)):
                    connector.receive_headers(2.0)
                self.assertIs(connector._pending_response, raw)
                connector.close()
                self.assertEqual(raw.close_calls, 1)
                self.assertIn(("close",), connection.calls)

    def test_openai_response_close_failure_still_closes_connection_and_is_sticky(self):
        raw = FakeHTTPResponse(
            status=503, headers=(), close_error=True,
        )
        connector, connection, *_rest = self.make_openai_connector(response=raw)
        with self.assertRaises(self.target._TransportFailure):
            connector.receive_headers(2.0)
        with self.assertRaises(OSError):
            connector.close()
        self.assertEqual(raw.close_calls, 1)
        self.assertIn(("close",), connection.calls)
        self.assertIs(connector._pending_response, raw)

    def test_openai_full_lifecycle_uses_injected_tcp_and_memory_tls_wire(self):
        marker = b"synthetic-openai-key-12345"
        stream = (
            b'event: response.created\ndata: {"type":"response.created",'
            b'"response":{"status":"in_progress"}}\n\n'
            b'event: response.output_text.delta\ndata: '
            b'{"type":"response.output_text.delta","delta":"ok"}\n\n'
            b'event: response.completed\ndata: {"type":"response.completed",'
            b'"response":{"status":"completed"}}\n\n'
        )
        wire = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/event-stream\r\n"
            + f"Content-Length: {len(stream)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + stream
        )
        wrapped = RefCountedSocket(wire, fragment=37)
        raw = FakeOwnedSocket()
        context = FakeTLSPort(wrapped)
        tcp_port = FakeTCPPort(raw)
        clock = FakeClock()
        connectors = []

        def factory(spec):
            connector = self.target._OpenAIHTTPSConnector(
                spec, tcp_port=tcp_port, clock=clock,
                context_factory=lambda: context,
            )
            connectors.append(connector)
            return connector

        request = self.request_wire(
            provider="openai_api", endpoint=None, model="gpt-5-mini",
            credentialBytes=len(marker),
        ) + marker
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([request, b""]), connector_factory=factory,
            clock=clock, signal_boundary=FakeSignals(), sink=sink,
        )

        self.assertEqual(outcome.terminal, "completed")
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "delta", "completed"])
        self.assertEqual(tcp_port.calls, [("api.openai.com", 443, 5.0)])
        self.assertEqual(context.calls[0][2], {
            "server_hostname": "api.openai.com",
            "do_handshake_on_connect": False,
        })
        sent = b"".join(call[1] for call in wrapped.calls
                        if call[0] == "sendall")
        self.assertIn(b"POST /v1/responses HTTP/1.1\r\n", sent)
        self.assertIn(b"Authorization: Bearer " + marker + b"\r\n", sent)
        wrapped.calls[:] = [
            (("sendall", len(call[1]), hashlib.sha256(call[1]).hexdigest())
             if call[0] == "sendall" else call)
            for call in wrapped.calls
        ]
        self.assertNotIn(marker, repr(wrapped.calls).encode("utf-8"))
        self.assertTrue(wrapped.closed)
        self.assertFalse(wrapped.fd_open)
        self.assertEqual(len(connectors), 1)

    def test_openai_tcp_nonreturn_cleanup_failure_outranks_transport_error(self):
        marker = b"synthetic-openai-key-12345"
        tcp_port = FakeTCPPort(error=ConnectionRefusedError("synthetic refusal"))
        clock = FakeClock()

        def factory(spec):
            return self.target._OpenAIHTTPSConnector(
                spec, tcp_port=tcp_port, clock=clock,
                context_factory=FakeTLSPort,
            )

        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([
                self.request_wire(
                    provider="openai_api", endpoint=None, model="gpt-5-mini",
                    credentialBytes=len(marker),
                ) + marker,
                b"",
            ]),
            connector_factory=factory, clock=clock,
            signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual((outcome.terminal, outcome.code, outcome.retryable),
                         ("failed", "process_cleanup_failed", False))
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "failed"])
        self.assertEqual(tcp_port.calls, [("api.openai.com", 443, 5.0)])

    def test_numeric_connection_uses_exact_family_sockaddr_and_no_name_resolution(self):
        cases = (
            ("127.0.0.1", 11434, socket.AF_INET, ("127.0.0.1", 11434)),
            ("::1", 3210, socket.AF_INET6, ("::1", 3210, 0, 0)),
        )
        for host, port, family, address in cases:
            with self.subTest(host=host):
                created = []

                def socket_factory(actual_family, actual_type):
                    sock = FakeSocket()
                    created.append((actual_family, actual_type, sock))
                    return sock

                connection = self.target._NumericHTTPConnection(
                    host=host, port=port, family=family, sockaddr=address,
                    socket_factory=socket_factory, timeout=4.25,
                )
                connection.connect()
                self.assertEqual(created[:1], [(family, socket.SOCK_STREAM, created[0][2])])
                self.assertEqual(created[0][2].calls, [
                    ("settimeout", 4.25), ("connect", address),
                ])

    def test_numeric_connector_rejects_every_nonclosed_ollama_destination(self):
        rejected = (
            "http://localhost:11434/api/chat",
            "http://127.0.0.2:11434/api/chat",
            "http://127.0.0.1:11434/",
            "http://127.0.0.1:11434/api/chat?x=1",
            "https://127.0.0.1:11434/api/chat",
            "http://user@127.0.0.1:11434/api/chat",
        )
        for url in rejected:
            with self.subTest(url=url):
                with self.assertRaises(self.target._contract.ContractError) as caught:
                    self.target._OllamaNumericConnector(
                        {"provider": "ollama_local", "url": url},
                        connection_factory=lambda **_kwargs: self.fail("factory called"),
                    )
                self.assertEqual(caught.exception.code, "endpoint_rejected")

    def test_numeric_connector_sends_exact_ordered_request_for_ipv4_and_ipv6(self):
        expected_body = (
            b'{"model":"gemma3:4b","messages":[{"role":"system",'
            b'"content":"Rewrite exactly."},{"role":"user","content":'
            b'"Revise this sentence."}],"stream":true,"options":'
            b'{"num_predict":1024}}'
        )
        for url, host in (
            ("http://127.0.0.1:11434/api/chat", "127.0.0.1:11434"),
            ("http://[::1]:3210/api/chat", "[::1]:3210"),
        ):
            with self.subTest(url=url):
                connector, connection = self.make_numeric_connector(url=url)
                connector.connect(5.0)
                connector.send((), self.ollama_body(), 3.25)
                self.assertEqual(connection.sock.calls, [("settimeout", 3.25)])
                self.assertEqual(connection.calls, [
                    ("connect", 5.0),
                    ("putrequest", "POST", "/api/chat", {
                        "skip_host": True, "skip_accept_encoding": True,
                    }),
                    ("putheader", "Host", host),
                    ("putheader", "Content-Type", "application/json"),
                    ("putheader", "Accept", "application/x-ndjson"),
                    ("putheader", "Accept-Encoding", "identity"),
                    ("putheader", "Content-Length", str(len(expected_body))),
                    ("putheader", "Connection", "close"),
                    ("endheaders", expected_body, False),
                ])

    def test_numeric_response_applies_phase_timeouts_and_accepts_exact_content_length(self):
        terminal = b'{"message":{"role":"assistant","content":"ok"},"done":true}\n'
        raw = FakeHTTPResponse(
            [terminal, b""],
            headers=(("Content-Type", "application/x-ndjson"),
                     ("Content-Length", str(len(terminal)))),
        )
        connector, connection = self.make_numeric_connector(response=raw)
        connector.connect(5.0)
        connector.send((), self.ollama_body(), 4.0)
        response = connector.receive_headers(17.0)
        self.assertEqual(response.read1(8192, 9.0), terminal)
        self.assertEqual(response.read1(8192, 8.0), b"")
        self.assertEqual(connection.sock.calls, [
            ("settimeout", 4.0), ("settimeout", 17.0),
            ("settimeout", 9.0),
        ])
        self.assertEqual(raw.calls, [
            ("getheaders",), ("read1", 8192),
        ])

    def test_public_httpresponse_exact_cl_completes_after_socket_reference_release(self):
        terminal = b'{"message":{"role":"assistant","content":"ok"},"done":true}\n'
        wire = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/x-ndjson\r\n"
            b"Connection: close\r\nContent-Length: " +
            str(len(terminal)).encode() + b"\r\n\r\n" + terminal
        )
        sock = RefCountedSocket(wire)
        connector = self.target._OllamaNumericConnector(
            {"provider": "ollama_local",
             "url": "http://127.0.0.1:11434/api/chat"},
            socket_factory=lambda *_args: sock,
        )
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda _spec: connector,
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.terminal, "completed")
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "delta", "completed"])
        self.assertFalse(sock.fd_open)
        release_index = max(index for index, call in enumerate(sock.calls)
                            if call == ("release_file",))
        self.assertNotIn(
            "settimeout", [call[0] for call in sock.calls[release_index + 1:]],
        )

    def test_partial_numeric_setup_close_fault_has_cleanup_failure_precedence(self):
        for fault in ("connect", "settimeout"):
            with self.subTest(fault=fault):
                sock = RefCountedSocket(
                    connect_fault=(fault == "connect"),
                    settimeout_fault=(fault == "settimeout"),
                    close_fault=True,
                )
                connector = self.target._OllamaNumericConnector(
                    {"provider": "ollama_local",
                     "url": "http://127.0.0.1:11434/api/chat"},
                    socket_factory=lambda *_args: sock,
                )
                sink = RecordingSink()
                outcome = self.target._run_call(
                    input_reader=FakeReader([self.request_wire(), b""]),
                    connector_factory=lambda _spec: connector,
                    clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
                )
                self.assertEqual(outcome.code, "process_cleanup_failed")
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", "failed"])
                self.assertIsNone(connector._connection.sock)
                self.assertIs(connector._connection._owned_socket, sock)
                self.assertTrue(sock.fd_open)
                self.assertGreaterEqual(sum(call == ("close",) for call in sock.calls), 2)

    def test_content_length_decimal_is_bounded_before_integer_conversion(self):
        accepted = ("0", "0" * 5000, "0" * 5000 + "524288", "524288")
        rejected = ("524289", "9" * 5000)
        for value in accepted:
            with self.subTest(kind="accepted", digits=len(value)):
                raw = FakeHTTPResponse([], headers=(
                    ("Content-Type", "application/x-ndjson"),
                    ("Content-Length", value),
                ))
                connector, _connection = self.make_numeric_connector(response=raw)
                connector.connect(5.0)
                connector.receive_headers(30.0)
        for value in rejected:
            with self.subTest(kind="rejected", digits=len(value)):
                raw = FakeHTTPResponse([], headers=(
                    ("Content-Type", "application/x-ndjson"),
                    ("Content-Length", value),
                ))
                connector, _connection = self.make_numeric_connector(response=raw)
                connector.connect(5.0)
                with self.assertRaises(self.target._contract.ContractError) as caught:
                    connector.receive_headers(30.0)
                self.assertEqual(caught.exception.code, "response_limit")

    def test_rejected_persistent_response_is_closed_without_gc(self):
        cases = (
            ("non200", b"HTTP/1.1 503 Unavailable\r\n"
             b"Content-Type: application/x-ndjson\r\nContent-Length: 8\r\n\r\nprivate!",
             "provider_unavailable"),
            ("badmedia", b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
             b"Content-Length: 8\r\n\r\nprivate!", "protocol_invalid"),
        )
        for name, wire, code in cases:
            with self.subTest(name=name):
                sock = RefCountedSocket(wire)
                connector = self.target._OllamaNumericConnector(
                    {"provider": "ollama_local",
                     "url": "http://127.0.0.1:11434/api/chat"},
                    socket_factory=lambda *_args: sock,
                )
                sink = RecordingSink()
                outcome = self.target._run_call(
                    input_reader=FakeReader([self.request_wire(), b""]),
                    connector_factory=lambda _spec: connector,
                    clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
                )
                self.assertEqual(outcome.code, code)
                self.assertEqual(sock.refs, 0)
                self.assertFalse(sock.fd_open)
                self.assertNotIn("private!", json.dumps(sink.events))

    def test_rejected_response_close_fault_keeps_cleanup_precedence_and_closes_socket(self):
        raw = FakeHTTPResponse(status=503, close_error=True)
        connector, connection = self.make_numeric_connector(response=raw)
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda _spec: connector,
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.code, "process_cleanup_failed")
        self.assertEqual(raw.close_calls, 1)
        self.assertIn(("close",), connection.sock.calls)
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "failed"])

    def test_short_content_length_invalidates_a_withheld_terminal(self):
        terminal = b'{"message":{"role":"assistant","content":"hidden"},"done":true}\n'
        raw = FakeHTTPResponse(
            [terminal, b""],
            headers=(("Content-Type", "application/x-ndjson"),
                     ("Content-Length", str(len(terminal) + 1))),
        )
        connector, _connection = self.make_numeric_connector(response=raw)
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda _spec: connector,
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.code, "protocol_invalid")
        self.assertEqual([event["type"] for event in sink.events], ["started", "failed"])
        self.assertNotIn("hidden", json.dumps(sink.events))

    def test_truncated_chunked_public_read_error_is_protocol_invalid(self):
        terminal = b'{"message":{"role":"assistant","content":"hidden"},"done":true}\n'
        raw = FakeHTTPResponse(
            [terminal, http.client.IncompleteRead(b"", 1)],
            headers=(("Content-Type", "application/x-ndjson"),
                     ("Transfer-Encoding", "chunked")),
        )
        connector, _connection = self.make_numeric_connector(response=raw)
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda _spec: connector,
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.code, "protocol_invalid")
        self.assertEqual([event["type"] for event in sink.events], ["started", "failed"])
        self.assertNotIn("hidden", json.dumps(sink.events))

    def test_hostile_response_headers_fail_closed_before_body_read(self):
        cases = {
            "duplicate-content-type": ("protocol_invalid", [
                ("Content-Type", "application/x-ndjson"),
                ("content-type", "application/x-ndjson"),
            ]),
            "te-and-cl": ("protocol_invalid", [
                ("Content-Type", "application/x-ndjson"),
                ("Transfer-Encoding", "chunked"), ("Content-Length", "1"),
            ]),
            "bad-transfer": ("protocol_invalid", [
                ("Content-Type", "application/x-ndjson"),
                ("Transfer-Encoding", "gzip"),
            ]),
            "compressed": ("protocol_invalid", [
                ("Content-Type", "application/x-ndjson"),
                ("Content-Encoding", "gzip"),
            ]),
            "oversized-cl": ("response_limit", [
                ("Content-Type", "application/x-ndjson"),
                ("Content-Length", "524289"),
            ]),
            "wrong-media": ("protocol_invalid", [
                ("Content-Type", "application/json"),
            ]),
            "too-many": ("response_limit", [
                ("X-Test", str(index)) for index in range(65)
            ]),
            "too-large": ("response_limit", [
                ("Content-Type", "application/x-ndjson"),
                ("X-Large", "x" * (32 * 1024)),
            ]),
        }
        for name, (code, headers) in cases.items():
            with self.subTest(name=name):
                raw = FakeHTTPResponse([b"must-not-read"], headers=headers)
                connector, _connection = self.make_numeric_connector(response=raw)
                connector.connect(5.0)
                with self.assertRaises(self.target._contract.ContractError) as caught:
                    connector.receive_headers(30.0)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(("read1", 8192), raw.calls)

    def test_non_200_status_maps_without_reading_response_body(self):
        raw = FakeHTTPResponse(
            [b"secret upstream body"], status=503,
            headers=(("X-Secret", "secret upstream header"),),
        )
        connector, _connection = self.make_numeric_connector(response=raw)
        connector.connect(5.0)
        with self.assertRaises(self.target._TransportFailure) as caught:
            connector.receive_headers(30.0)
        self.assertEqual((caught.exception.code, caught.exception.retryable),
                         ("provider_unavailable", True))
        self.assertEqual(raw.calls, [])

    def test_numeric_request_rejects_drift_and_body_limit_before_putrequest(self):
        connector, connection = self.make_numeric_connector()
        connector.connect(5.0)
        cases = (
            {**self.ollama_body(), "tools": []},
            {**self.ollama_body(), "stream": False},
            {**self.ollama_body(), "options": {"num_predict": 1025}},
            {**self.ollama_body(), "messages": [
                {"role": "system", "content": "x" * (96 * 1024)},
                {"role": "user", "content": "y"},
            ]},
        )
        for body in cases:
            with self.subTest(keys=tuple(body)):
                with self.assertRaises(self.target._contract.ContractError):
                    connector.send((), body, 5.0)
        self.assertEqual([call for call in connection.calls if call[0] == "putrequest"], [])

    def test_numeric_adapter_completes_for_each_allowed_response_framing(self):
        terminal = b'{"message":{"role":"assistant","content":"ok"},"done":true}\n'
        cases = (
            (("Content-Type", "application/x-ndjson"),),
            (("Content-Type", "application/x-ndjson"),
             ("Content-Length", str(len(terminal)))),
            (("Content-Type", "application/x-ndjson; charset=utf-8"),
             ("Transfer-Encoding", "chunked")),
        )
        for headers in cases:
            with self.subTest(headers=headers):
                raw = FakeHTTPResponse([terminal, b""], headers=headers)
                connector, _connection = self.make_numeric_connector(response=raw)
                sink = RecordingSink()
                outcome = self.target._run_call(
                    input_reader=FakeReader([self.request_wire(), b""]),
                    connector_factory=lambda _spec: connector,
                    clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
                )
                self.assertEqual(outcome.terminal, "completed")
                self.assertEqual(outcome.exit_code, 0)
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", "delta", "completed"])
                self.assertEqual(sum(event["type"] in {
                    "completed", "failed", "cancelled",
                } for event in sink.events), 1)

    def test_numeric_adapter_classifies_boundary_failures_once(self):
        cases = (
            (301, "provider_failed", False),
            (404, "model_unavailable", False),
            (408, "operation_timeout", True),
            (429, "rate_limited", True),
            (503, "provider_unavailable", True),
        )
        for status, code, retryable in cases:
            with self.subTest(status=status):
                raw = FakeHTTPResponse([b"must-not-read"], status=status)
                connector, _connection = self.make_numeric_connector(response=raw)
                sink = RecordingSink()
                outcome = self.target._run_call(
                    input_reader=FakeReader([self.request_wire(), b""]),
                    connector_factory=lambda _spec: connector,
                    clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
                )
                self.assertEqual((outcome.code, outcome.retryable), (code, retryable))
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", "failed"])
                self.assertEqual(sum(event["type"] == "failed"
                                     for event in sink.events), 1)
                self.assertNotIn(("read1", 8192), raw.calls)

        connector, connection = self.make_numeric_connector()
        connection.connect = mock.Mock(side_effect=ConnectionRefusedError())
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda _spec: connector,
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual((outcome.code, outcome.retryable),
                         ("connection_failed", True))
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "failed"])

    def test_numeric_response_enforces_declared_and_absolute_body_caps(self):
        cases = (
            ([b"ab"], (("Content-Type", "application/x-ndjson"),
                       ("Content-Length", "1")), "protocol_invalid"),
            ([b"x" * 8192 for _ in range(64)] + [b"x"],
             (("Content-Type", "application/x-ndjson"),), "response_limit"),
        )
        for chunks, headers, code in cases:
            with self.subTest(code=code):
                raw = FakeHTTPResponse(chunks, headers=headers)
                connector, _connection = self.make_numeric_connector(response=raw)
                connector.connect(5.0)
                response = connector.receive_headers(30.0)
                with self.assertRaises(self.target._contract.ContractError) as caught:
                    while response.read1(8192, 30.0):
                        pass
                self.assertEqual(caught.exception.code, code)

    def test_invalid_preflight_rolls_back_setup_without_output_or_connector(self):
        clock = FakeClock()
        reader = FakeReader([b""])
        signals = FakeSignals()
        sink = RecordingSink()
        connector_calls = []

        outcome = self.target._run_call(
            input_reader=reader,
            connector_factory=lambda spec: connector_calls.append(spec),
            clock=clock,
            signal_boundary=signals,
            sink=sink,
        )

        self.assertEqual(outcome.state, "preflight_failed")
        self.assertEqual(outcome.code, "invalid_request")
        self.assertEqual(outcome.exit_code, 2)
        self.assertEqual(connector_calls, [])
        self.assertEqual(sink.events, [])
        self.assertEqual(reader.calls, [(8192, 120.0)])
        self.assertEqual(
            [call for call in signals.calls if call[0] in {
                "cancel_timer", "restore_handler", "restore_mask",
            }],
            [
                ("restore_mask", "original-mask"),
                ("cancel_timer",),
                ("restore_handler", "SIGALRM", "original-SIGALRM"),
                ("restore_handler", "SIGTERM", "original-SIGTERM"),
                ("restore_handler", "SIGINT", "original-SIGINT"),
                ("restore_mask", "original-mask"),
            ],
        )

    def test_parser_or_builder_failure_before_started_uses_preflight_rollback(self):
        cases = ("_parser_for", "build_request")
        for boundary in cases:
            with self.subTest(boundary=boundary):
                signals = FakeSignals()
                sink = RecordingSink()
                connector_calls = []
                owner = self.target if boundary == "_parser_for" else self.target._contract
                with mock.patch.object(
                    owner, boundary, side_effect=RuntimeError("private marker")
                ):
                    outcome = self.target._run_call(
                        input_reader=FakeReader([self.request_wire(), b""]),
                        connector_factory=lambda spec: connector_calls.append(spec),
                        clock=FakeClock(), signal_boundary=signals, sink=sink,
                    )

                self.assertEqual(outcome.state, "preflight_failed")
                self.assertEqual(outcome.code, "helper_unavailable")
                self.assertEqual(outcome.exit_code, 2)
                self.assertEqual(connector_calls, [])
                self.assertEqual(sink.events, [])
                self.assertEqual(signals.counts["cancel_timer"], 1)
                self.assertEqual(signals.counts["restore_handler"], 3)

    def test_fake_connector_streams_and_withholds_terminal_until_cleanup(self):
        trace = []
        wire = (
            b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
            b'{"message":{"role":"assistant","content":"tail"},"done":true,'
            b'"done_reason":"stop","prompt_eval_count":2,"eval_count":1}\n'
        )
        response = FakeResponse([wire, b""], trace)
        connector = FakeConnector(response, trace)
        signals = FakeSignals()
        sink = RecordingSink()

        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda spec: connector,
            clock=FakeClock(), signal_boundary=signals, sink=sink,
        )

        self.assertEqual(outcome.state, "terminal_emitted")
        self.assertEqual(outcome.terminal, "completed")
        self.assertEqual(outcome.exit_code, 0)
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "delta", "delta", "completed"])
        self.assertEqual(trace, ["response.close", "connector.close"])
        self.assertEqual(
            [(call[0], call[-1]) for call in connector.calls],
            [("connect", 5.0), ("send", 5.0), ("receive_headers", 30.0)],
        )
        self.assertEqual(connector.calls[1][1], ())
        self.assertEqual(connector.calls[1][2]["options"], {"num_predict": 1024})
        self.assertEqual(response.calls, [(8192, 30.0), (8192, 30.0)])
        terminal_hook = signals.calls.index(("hook", "before_terminal"))
        response_close = signals.calls.index(("hook", "after_response_close"))
        self.assertLess(response_close, terminal_hook)

    def test_cancellation_at_each_post_sink_or_factory_seam_stops_next_boundary(self):
        terminal = b'{"message":{"role":"assistant","content":"done"},"done":true}\n'

        signals = FakeSignals()
        sink = RecordingSink(on_publish=lambda event: (
            signals.handlers["SIGINT"]() if event["type"] == "started" else None
        ))
        factory_calls = []
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda spec: factory_calls.append(spec),
            clock=FakeClock(), signal_boundary=signals, sink=sink,
        )
        self.assertEqual(factory_calls, [])
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "cancelled"])
        self.assertEqual(outcome.terminal, "cancelled")

        signals = FakeSignals()
        trace = []
        response = FakeResponse([terminal, b""], trace)
        connector = FakeConnector(response, trace)

        def cancelling_factory(_spec):
            signals.handlers["SIGINT"]()
            return connector

        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=cancelling_factory,
            clock=FakeClock(), signal_boundary=signals, sink=sink,
        )
        self.assertEqual(connector.calls, [])
        self.assertEqual(connector.trace, ["connector.close"])
        self.assertEqual(outcome.terminal, "cancelled")

        signals = FakeSignals()
        sink = RecordingSink(on_publish=lambda event: (
            signals.handlers["SIGINT"]() if event["type"] == "delta" else None
        ))
        delta = b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
        outcome, sink, _connector, response, *_rest = self.run_local(
            [delta, terminal, b""], signals=signals, sink=sink,
        )
        self.assertEqual(len(response.calls), 1)
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "delta", "cancelled"])
        self.assertEqual(outcome.terminal, "cancelled")

    def test_budget_precheck_before_started_rolls_back_without_output(self):
        clock = FakeClock()
        original = self.target._contract.build_request

        def exhausted_builder(request):
            built = original(request)
            clock.now += self.target.TOTAL_TIMEOUT
            return built

        sink = RecordingSink()
        factories = []
        with mock.patch.object(
            self.target._contract, "build_request", exhausted_builder,
        ):
            outcome = self.target._run_call(
                input_reader=FakeReader([self.request_wire(), b""]),
                connector_factory=lambda spec: factories.append(spec),
                clock=clock, signal_boundary=FakeSignals(), sink=sink,
            )
        self.assertEqual(outcome.state, "preflight_failed")
        self.assertEqual(outcome.code, "operation_timeout")
        self.assertEqual(outcome.exit_code, 2)
        self.assertEqual(factories, [])
        self.assertEqual(sink.events, [])

    def test_setup_failures_restore_only_confirmed_acquisitions(self):
        cases = [
            (("block", 1), []),
            (("get_handler", 1), []),
            (("get_handler", 2), []),
            (("get_handler", 3), []),
            (("get_timer", 1), []),
            (("install_handler", 1), []),
            (("install_handler", 2), ["SIGINT"]),
            (("install_handler", 3), ["SIGTERM", "SIGINT"]),
            (("arm_timer", 1), ["SIGALRM", "SIGTERM", "SIGINT"]),
            (("restore_mask", 1), ["SIGALRM", "SIGTERM", "SIGINT"]),
        ]
        for failure, restored in cases:
            with self.subTest(failure=failure):
                signals = FakeSignals(fail_at={failure})
                sink = RecordingSink()
                connector_calls = []
                outcome = self.target._run_call(
                    input_reader=FakeReader([self.request_wire(), b""]),
                    connector_factory=lambda spec: connector_calls.append(spec),
                    clock=FakeClock(), signal_boundary=signals, sink=sink,
                )
                self.assertEqual(outcome.state, "preflight_failed")
                self.assertEqual(outcome.exit_code, 2)
                self.assertEqual(connector_calls, [])
                self.assertEqual(sink.events, [])
                actual = [call[1] for call in signals.calls
                          if call[0] == "restore_handler"]
                self.assertEqual(actual, restored)

        active_timer = FakeSignals(timer=(1.0, 0.0))
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda _spec: self.fail("connector called"),
            clock=FakeClock(), signal_boundary=active_timer,
            sink=RecordingSink(),
        )
        self.assertEqual(outcome.state, "preflight_failed")
        self.assertFalse(any(call[0] == "install_handler"
                             for call in active_timer.calls))
        self.assertEqual([call for call in active_timer.calls if call[0] == "restore_mask"],
                         [("restore_mask", "original-mask")])

    def test_preflight_rollback_attempts_every_remaining_restore_after_failure(self):
        failures = [
            ("block", 2), ("cancel_timer", 1),
            ("restore_handler", 1), ("restore_handler", 2),
            ("restore_handler", 3), ("restore_mask", 2),
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                signals = FakeSignals(fail_at={failure})
                outcome = self.target._run_call(
                    input_reader=FakeReader([b""]),
                    connector_factory=lambda _spec: self.fail("connector called"),
                    clock=FakeClock(), signal_boundary=signals,
                    sink=RecordingSink(),
                )
                self.assertEqual(outcome.state, "preflight_failed")
                self.assertEqual(outcome.exit_code, 2)
                if failure != ("block", 2):
                    restored = [call[1] for call in signals.calls
                                if call[0] == "restore_handler"]
                    self.assertEqual(restored, ["SIGALRM", "SIGTERM", "SIGINT"])

    def test_partial_input_stall_is_total_only_and_never_starts(self):
        marker = b"synthetic-secret-marker-123456"
        frame = self.request_wire(
            provider="openai_api", endpoint=None, model="gpt-5-mini",
            credentialBytes=len(marker),
        )
        clock = FakeClock()

        def advance(call):
            if call == 1:
                clock.now += 10.0

        reader = FakeReader([frame + marker[:5], TimeoutError()], on_read=advance)
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=reader,
            connector_factory=lambda _spec: self.fail("connector called"),
            clock=clock, signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.state, "preflight_failed")
        self.assertEqual(outcome.exit_code, 2)
        self.assertEqual(outcome.code, "operation_timeout")
        self.assertTrue(outcome.retryable)
        self.assertEqual(sink.events, [])
        self.assertEqual([timeout for _limit, timeout in reader.calls], [120.0, 110.0])

    def test_setup_elapsed_time_reduces_alarm_and_first_stdin_budget(self):
        clock = FakeClock()
        signals = FakeSignals()
        original_get_timer = signals.get_timer

        def delayed_get_timer():
            clock.now += 10.0
            return original_get_timer()

        signals.get_timer = delayed_get_timer
        reader = FakeReader([b""])
        outcome = self.target._run_call(
            input_reader=reader,
            connector_factory=lambda _spec: self.fail("connector called"),
            clock=clock, signal_boundary=signals, sink=RecordingSink(),
        )
        self.assertEqual(outcome.state, "preflight_failed")
        arm = next(call for call in signals.calls if call[0] == "arm_timer")
        self.assertEqual(arm[1], 110.0)
        self.assertEqual(reader.calls, [(8192, 110.0)])

    def test_send_budget_is_fixed_five_reduced_by_the_operational_total(self):
        completed = b'{"message":{"role":"assistant","content":""},"done":true}\n'
        for advance, expected in ((4.0, 5.0), (116.75, 3.25)):
            with self.subTest(advance=advance):
                clock = FakeClock()
                result = self.run_local(
                    [completed, b""], clock=clock,
                    connector_options={"advance_connect": advance},
                )
                outcome, _sink, connector = result[:3]
                self.assertEqual(outcome.terminal, "completed")
                send = next(call for call in connector.calls if call[0] == "send")
                self.assertEqual(send[-1], expected)

        result = self.run_local(
            [completed, b""], clock=FakeClock(),
            connector_options={"advance_connect": 120.0},
        )
        outcome, sink, connector = result[:3]
        self.assertEqual(outcome.code, "operation_timeout")
        self.assertFalse(any(call[0] == "send" for call in connector.calls))
        self.assertEqual([event["type"] for event in sink.events], ["started", "failed"])

    def test_feed_failure_is_transactional_and_prior_delta_remains_visible(self):
        valid = b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
        invalid = b'{"message":{"role":"user","content":"hidden"},"done":false}\n'

        outcome, sink, *_rest = self.run_local([valid + invalid])
        self.assertEqual(outcome.code, "protocol_invalid")
        self.assertEqual([event["type"] for event in sink.events], ["started", "failed"])
        self.assertEqual(sink.events[-1]["sequence"], 1)

        outcome, sink, *_rest = self.run_local([valid, invalid])
        self.assertEqual(outcome.code, "protocol_invalid")
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "delta", "failed"])
        self.assertEqual(sink.events[1]["text"], "kept")
        self.assertEqual(sink.events[-1]["sequence"], 2)

    def test_trailing_bytes_replace_the_entire_unpublished_terminal_batch(self):
        terminal = (
            b'{"message":{"role":"assistant","content":"hidden"},"done":true,'
            b'"done_reason":"stop"}\n'
        )
        outcome, sink, *_rest = self.run_local([terminal, b"trailing"])
        self.assertEqual(outcome.code, "protocol_invalid")
        self.assertEqual([event["type"] for event in sink.events], ["started", "failed"])
        self.assertEqual(sink.events[-1]["sequence"], 1)
        self.assertNotIn("hidden", json.dumps(sink.events))

    def test_response_chunk_bound_is_defensive_before_parser_state_changes(self):
        oversized = b"x" * (8 * 1024 + 1)
        outcome, sink, *_rest = self.run_local([oversized])
        self.assertEqual(outcome.code, "response_limit")
        self.assertEqual([event["type"] for event in sink.events], ["started", "failed"])
        self.assertEqual(sink.events[-1]["sequence"], 1)

        outcome = self.target._run_call(
            input_reader=FakeReader([b"x" * (8 * 1024 + 1)]),
            connector_factory=lambda _spec: self.fail("connector called"),
            clock=FakeClock(), signal_boundary=FakeSignals(),
            sink=RecordingSink(),
        )
        self.assertEqual(outcome.state, "preflight_failed")
        self.assertEqual(outcome.code, "invalid_request")

    def test_cancel_can_use_the_single_reserved_terminal_slot_at_exact_limit(self):
        record = b'{"message":{"role":"assistant","content":"x"},"done":false}\n'
        chunks = []
        for start in range(0, 4094, 100):
            chunks.append(record * min(100, 4094 - start))
        chunks.extend([
            b'{"message":{"role":"assistant","content":"hidden"},"done":true}\n',
            b"",
        ])
        outcome, sink, *_rest = self.run_local(
            chunks, signals=FakeSignals(cancel_hooks={"before_terminal"}),
        )
        self.assertEqual(outcome.terminal, "cancelled")
        self.assertEqual(len(sink.events), 4096)
        self.assertEqual(sink.events[-1]["type"], "cancelled")
        self.assertEqual(sink.events[-1]["sequence"], 4095)
        self.assertNotIn("hidden", json.dumps(sink.events[-2:]))

    def test_cancel_replaces_pending_terminal_but_preserves_prior_delta(self):
        first = b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
        terminal = b'{"message":{"role":"assistant","content":"hidden"},"done":true}\n'
        signals = FakeSignals(cancel_hooks={"before_terminal"})
        outcome, sink, *_rest = self.run_local([first, terminal, b""], signals=signals)
        self.assertEqual(outcome.terminal, "cancelled")
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "delta", "cancelled"])
        self.assertEqual(sink.events[-1]["sequence"], 2)
        self.assertNotIn("hidden", json.dumps(sink.events))

    def test_cancel_at_every_cleanup_boundary_produces_one_cancelled_terminal(self):
        terminal = b'{"message":{"role":"assistant","content":"hidden"},"done":true}\n'
        hooks = (
            "before_response_close", "after_response_close",
            "before_connector_close", "after_connector_close",
            "before_wipe", "after_wipe", "before_terminal",
        )
        for hook in hooks:
            with self.subTest(hook=hook):
                signals = FakeSignals(cancel_hooks={hook})
                outcome, sink, *_rest = self.run_local(
                    [terminal, b""], signals=signals,
                )
                self.assertEqual(outcome.terminal, "cancelled")
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", "cancelled"])
                self.assertEqual(sink.events[-1]["sequence"], 1)

    def test_installed_fake_signal_cancels_body_read_and_preserves_partial(self):
        signals = FakeSignals()

        def cancel_on_second_read(call):
            if call == 2:
                signals.handlers["SIGINT"]()

        delta = b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
        outcome, sink, *_rest = self.run_local(
            [delta, b"ignored"], signals=signals,
            response_options={"on_read": cancel_on_second_read},
        )
        self.assertEqual(outcome.terminal, "cancelled")
        self.assertEqual([event["type"] for event in sink.events],
                         ["started", "delta", "cancelled"])
        self.assertEqual(sink.events[-1]["sequence"], 2)

    def test_cleanup_failure_outranks_cancel_and_restores_pending_snapshot(self):
        terminal = b'{"message":{"role":"assistant","content":"hidden"},"done":true}\n'
        signals = FakeSignals(cancel_hooks={"before_terminal"})
        outcome, sink, *_rest = self.run_local(
            [terminal, b""], signals=signals,
            response_options={"close_error": True},
        )
        self.assertEqual(outcome.terminal, "failed")
        self.assertEqual(outcome.code, "process_cleanup_failed")
        self.assertEqual([event["type"] for event in sink.events], ["started", "failed"])
        self.assertEqual(sink.events[-1]["sequence"], 1)

    def test_each_cleanup_failure_class_becomes_process_cleanup_failed(self):
        terminal = b'{"message":{"role":"assistant","content":"hidden"},"done":true}\n'
        cases = [
            ({"response_options": {"close_error": True}}, None),
            ({"connector_options": {"close_error": True}}, None),
            ({}, ("cancel_timer", 1)),
            ({}, ("hook", 1)),
            ({}, ("hook", 7)),
        ]
        for options, signal_failure in cases:
            with self.subTest(options=options, signal_failure=signal_failure):
                signals = FakeSignals(
                    fail_at=set() if signal_failure is None else {signal_failure}
                )
                outcome, sink, *_rest = self.run_local(
                    [terminal, b""], signals=signals, **options,
                )
                self.assertEqual(outcome.code, "process_cleanup_failed")
                self.assertEqual(outcome.terminal, "failed")
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", "failed"])
                self.assertEqual(sink.events[-1]["sequence"], 1)

    def test_finalizer_guard_failure_after_started_preserves_partial_without_terminal(self):
        delta = b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
        signals = FakeSignals(fail_at={("block", 2)})
        outcome, sink, _connector, _response, _signals, trace, _specs = self.run_local(
            [delta, TimeoutError()], signals=signals,
        )
        self.assertEqual(outcome.state, "finalization_failed")
        self.assertEqual(outcome.exit_code, 3)
        self.assertEqual([event["type"] for event in sink.events], ["started", "delta"])
        self.assertTrue(outcome.partial_published)
        self.assertEqual(trace, ["response.close", "connector.close"])

    def test_restore_failure_after_one_terminal_attempt_changes_only_private_outcome(self):
        terminal = b'{"message":{"role":"assistant","content":"ok"},"done":true}\n'
        for failure in (("restore_handler", 1), ("restore_mask", 2)):
            with self.subTest(failure=failure):
                signals = FakeSignals(fail_at={failure})
                outcome, sink, *_rest = self.run_local(
                    [terminal, b""], signals=signals,
                )
                self.assertEqual(outcome.state, "finalization_failed")
                self.assertEqual(outcome.exit_code, 3)
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", "delta", "completed"])
                self.assertEqual(sum(event["type"] in {
                    "completed", "failed", "cancelled",
                } for event in sink.events), 1)

    def test_lifecycle_exception_inside_started_publish_finalizes_without_ack(self):
        cases = ((self.target._Cancelled, "cancelled", None),
                 (self.target._TimedOut, "failed", "operation_timeout"))
        for exception, terminal_type, code in cases:
            with self.subTest(exception=exception.__name__):
                signals = FakeSignals()
                factories = []
                terminal_calls = []

                def interrupt(event):
                    if event["type"] == "started":
                        raise exception()
                    terminal_calls.extend(signals.calls)

                sink = RecordingSink(on_publish=interrupt)
                outcome = self.target._run_call(
                    input_reader=FakeReader([self.request_wire(), b""]),
                    connector_factory=lambda spec: factories.append(spec),
                    clock=FakeClock(), signal_boundary=signals, sink=sink,
                )
                self.assertEqual(factories, [])
                self.assertEqual((outcome.state, outcome.exit_code),
                                 ("terminal_emitted", 0))
                self.assertEqual((outcome.terminal, outcome.code), (terminal_type, code))
                self.assertEqual(outcome.published_events, 1)
                self.assertFalse(outcome.partial_published)
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", terminal_type])
                self.assertEqual([event["sequence"] for event in sink.events], [0, 1])
                expected = {"schemaVersion": 1, "requestId": "txt-transport.1",
                            "sequence": 1, "type": terminal_type}
                if code is not None:
                    expected.update(code=code, retryable=True)
                self.assertEqual(sink.events[-1], expected)
                self.assertIn(("cancel_timer",), terminal_calls)
                self.assertIn(("hook", "after_wipe"), terminal_calls)
                self.assertFalse(any(call[0] == "restore_handler" for call in terminal_calls))
                self.assertEqual(signals.counts["cancel_timer"], 1)
                self.assertEqual(signals.counts["restore_handler"], 3)
                self.assertEqual(signals.calls[-1], ("restore_mask", "original-mask"))
                retry, retry_sink, *_rest = self.run_local([
                    b'{"message":{"role":"assistant","content":""},"done":true}\n', b"",
                ])
                self.assertEqual((retry.terminal, retry.exit_code), ("completed", 0))
                self.assertEqual(retry_sink.events[-1]["sequence"], 1)

    def test_lifecycle_exception_during_delta_publication_keeps_terminal_class(self):
        delta = b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
        terminal = (
            b'{"message":{"role":"assistant","content":""},"done":true,'
            b'"prompt_eval_count":4,"eval_count":5}\n'
        )
        cases = ((self.target._Cancelled, "cancelled", None),
                 (self.target._TimedOut, "failed", "operation_timeout"))
        for exception, terminal_type, code in cases:
            with self.subTest(exception=exception.__name__):
                def interrupt(event):
                    if event["type"] == "delta":
                        raise exception()

                sink = RecordingSink(on_publish=interrupt)
                outcome, sink, _connector, response, signals, trace, _specs = self.run_local(
                    [delta, terminal, b""], sink=sink,
                )
                self.assertEqual(trace, ["response.close", "connector.close"])
                self.assertEqual(signals.counts["cancel_timer"], 1)
                self.assertEqual(signals.counts["restore_handler"], 3)
                self.assertEqual(len(response.calls), 1)
                self.assertEqual((outcome.state, outcome.exit_code),
                                 ("terminal_emitted", 0))
                self.assertEqual((outcome.terminal, outcome.code), (terminal_type, code))
                self.assertEqual([event["type"] for event in sink.events],
                                 ["started", "delta", terminal_type])
                self.assertEqual([event["sequence"] for event in sink.events], [0, 1, 2])
                self.assertEqual(sink.events[1]["text"], "kept")
                expected = {"schemaVersion": 1, "requestId": "txt-transport.1",
                            "sequence": 2, "type": terminal_type}
                if code is not None:
                    expected.update(code=code, retryable=True)
                self.assertEqual(sink.events[-1], expected)
                retry, retry_sink, *_rest = self.run_local([delta, terminal, b""])
                self.assertEqual((retry.terminal, retry.exit_code), ("completed", 0))
                self.assertEqual(retry_sink.events[-1]["usage"]["totalTokens"], 9)

    def test_ordinary_sink_exceptions_still_fail_closed_after_started(self):
        class CustomSinkError(Exception):
            pass

        delta = b'{"message":{"role":"assistant","content":"hidden"},"done":false}\n'
        terminal = b'{"message":{"role":"assistant","content":""},"done":true}\n'
        for exception in (BrokenPipeError, OSError, CustomSinkError):
            with self.subTest(exception=exception.__name__):
                class FailingSink(RecordingSink):
                    def publish(self, event):
                        if event["type"] == "delta":
                            raise exception("synthetic sink fault")
                        super().publish(event)

                outcome, sink, _connector, _response, signals, trace, _specs = self.run_local(
                    [delta, terminal, b""], sink=FailingSink(),
                )
                self.assertEqual(trace, ["response.close", "connector.close"])
                self.assertEqual(signals.counts["cancel_timer"], 1)
                self.assertEqual(signals.counts["restore_handler"], 3)
                self.assertEqual((outcome.state, outcome.exit_code), ("sink_failed", 3))
                self.assertIsNone(outcome.terminal)
                self.assertEqual([event["type"] for event in sink.events], ["started"])
                self.assertNotIn("synthetic sink fault", json.dumps(outcome.__dict__))
                retry, retry_sink, *_rest = self.run_local([terminal, b""])
                self.assertEqual((retry.terminal, retry.exit_code), ("completed", 0))
                self.assertEqual(retry_sink.events[-1]["usage"]["status"], "unknown")

    def test_sink_failure_never_retries_or_calls_a_connector_after_failed_started(self):
        connector_calls = []
        sink = RecordingSink(fail_at=1)
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda spec: connector_calls.append(spec),
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.state, "sink_failed")
        self.assertEqual(outcome.exit_code, 3)
        self.assertEqual(connector_calls, [])
        self.assertEqual(sink.attempts, 1)
        self.assertEqual(sink.events, [])

    def test_openai_fake_stream_uses_synthetic_secret_only_for_framing(self):
        marker = b"synthetic-secret-marker-123456"
        wire = self.request_wire(
            provider="openai_api", endpoint=None, model="gpt-5-mini",
            credentialBytes=len(marker),
        ) + marker
        stream = (
            b'event: response.created\ndata: {"type":"response.created",'
            b'"response":{"status":"in_progress"}}\n\n'
            b'event: response.output_text.delta\ndata: '
            b'{"type":"response.output_text.delta","delta":"ok"}\n\n'
            b'event: response.completed\ndata: {"type":"response.completed",'
            b'"response":{"status":"completed"}}\n\n'
        )
        trace = []
        response = FakeResponse([stream, b""], trace)
        connector = FakeConnector(response, trace)
        sink = RecordingSink()
        specs = []
        outcome = self.target._run_call(
            input_reader=FakeReader([wire, b""]),
            connector_factory=lambda spec: specs.append(spec) or connector,
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.terminal, "completed")
        serialized = json.dumps({"specs": specs, "calls": connector.calls,
                                 "events": sink.events}, default=str)
        self.assertNotIn(marker.decode(), serialized)
        body = next(call[2] for call in connector.calls if call[0] == "send")
        self.assertEqual(body["max_output_tokens"], 1024)
        self.assertFalse(body["store"])
        self.assertEqual(body["tools"], [])

    def test_secret_overlap_in_recursive_body_values_or_keys_is_preflight_invalid(self):
        marker = b"synthetic-secret-marker-123456"
        safe_wire = self.request_wire(
            provider="openai_api", endpoint=None, model="gpt-5-mini",
            credentialBytes=len(marker),
        ) + marker
        overlap_wire = self.request_wire(
            provider="openai_api", endpoint=None, model="gpt-5-mini",
            text=f"contains {marker.decode()} here", credentialBytes=len(marker),
        ) + marker

        for kind in ("value", "nested-key"):
            with self.subTest(kind=kind):
                signals = FakeSignals()
                sink = RecordingSink()
                factories = []
                patcher = contextlib.nullcontext()
                wire = overlap_wire
                if kind == "nested-key":
                    wire = safe_wire
                    original = self.target._contract.build_request

                    def nested_key(request):
                        built = original(request)
                        built["body"]["metadata"] = {marker.decode(): "safe"}
                        return built

                    patcher = mock.patch.object(
                        self.target._contract, "build_request", nested_key,
                    )
                with patcher:
                    outcome = self.target._run_call(
                        input_reader=FakeReader([wire, b""]),
                        connector_factory=lambda spec: factories.append(spec),
                        clock=FakeClock(), signal_boundary=signals, sink=sink,
                    )
                self.assertEqual(outcome.state, "preflight_failed")
                self.assertEqual(outcome.code, "invalid_request")
                self.assertEqual(outcome.exit_code, 2)
                self.assertEqual(factories, [])
                self.assertEqual(sink.events, [])
                self.assertNotIn(marker.decode(), json.dumps(outcome.__dict__))

    def test_wipe_failures_never_skip_remaining_rollback_or_escape(self):
        marker = b"synthetic-secret-marker-123456"
        wire = self.request_wire(
            provider="openai_api", endpoint=None, model="gpt-5-mini",
            credentialBytes=len(marker),
        ) + marker
        stream = (
            b'event: response.created\ndata: {"type":"response.created",'
            b'"response":{"status":"in_progress"}}\n\n'
            b'event: response.completed\ndata: {"type":"response.completed",'
            b'"response":{"status":"completed"}}\n\n'
        )
        original_wipe = self.target._wipe

        def failing_wipe(buffer):
            if bytes(buffer or b"") == marker:
                raise RuntimeError("private wipe marker")
            original_wipe(buffer)

        cases = ("preflight", "guard", "normal")
        for kind in cases:
            with self.subTest(kind=kind), mock.patch.object(
                self.target, "_wipe", failing_wipe,
            ):
                signals = FakeSignals(
                    fail_at={("block", 2)} if kind == "guard" else (),
                )
                trace = []
                response = FakeResponse([stream, b""], trace)
                connector = FakeConnector(response, trace)
                sink = RecordingSink()
                factory_calls = []

                def factory(spec):
                    factory_calls.append(spec)
                    return connector

                builder = contextlib.nullcontext()
                if kind == "preflight":
                    builder = mock.patch.object(
                        self.target._contract, "build_request",
                        side_effect=RuntimeError("private builder marker"),
                    )
                with builder:
                    outcome = self.target._run_call(
                        input_reader=FakeReader([wire, b""]),
                        connector_factory=factory,
                        clock=FakeClock(), signal_boundary=signals, sink=sink,
                    )

                self.assertEqual(signals.counts["cancel_timer"], 1)
                self.assertEqual(signals.counts["restore_handler"], 3)
                if kind == "preflight":
                    self.assertEqual(outcome.state, "preflight_failed")
                    self.assertEqual(outcome.exit_code, 2)
                    self.assertEqual(factory_calls, [])
                    self.assertEqual(sink.events, [])
                elif kind == "guard":
                    self.assertEqual(outcome.state, "finalization_failed")
                    self.assertEqual(outcome.exit_code, 3)
                    self.assertEqual([event["type"] for event in sink.events],
                                     ["started"])
                else:
                    self.assertEqual(outcome.code, "process_cleanup_failed")
                    self.assertEqual(outcome.terminal, "failed")
                    self.assertEqual([event["type"] for event in sink.events],
                                     ["started", "failed"])

    def test_read_frame_retains_credential_until_raw_cleanup_succeeds(self):
        valid = b"synthetic-raw-owner-123456789"
        invalid = b"invalid credential marker 12345"
        original_parse = self.target._contract.parse_input
        original_wipe = self.target._wipe

        for kind, secret in (("valid", valid), ("invalid", invalid)):
            with self.subTest(kind=kind):
                wire = self.request_wire(
                    provider="openai_api", endpoint=None, model="gpt-5-mini",
                    credentialBytes=len(secret),
                ) + secret
                acquired = []
                attempts = []
                factories = []
                sink = RecordingSink()

                def capture_parse(raw):
                    request, credential = original_parse(raw)
                    acquired.append(credential)
                    return request, credential

                def faulted_wipe(buffer):
                    is_credential = any(buffer is item for item in acquired)
                    attempts.append("credential" if is_credential else "raw")
                    if not is_credential or kind == "invalid":
                        raise RuntimeError("private wipe marker")
                    original_wipe(buffer)

                with mock.patch.object(
                    self.target._contract, "parse_input", capture_parse,
                ), mock.patch.object(self.target, "_wipe", faulted_wipe):
                    outcome = self.target._run_call(
                        input_reader=FakeReader([wire, b""]),
                        connector_factory=lambda spec: factories.append(spec),
                        clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
                    )

                self.assertEqual(attempts, ["raw", "credential"])
                self.assertEqual(outcome.state, "preflight_failed")
                self.assertEqual(outcome.exit_code, 2)
                self.assertEqual(outcome.code, (
                    "process_cleanup_failed" if kind == "valid" else "invalid_request"
                ))
                self.assertEqual(factories, [])
                self.assertEqual(sink.events, [])
                if kind == "valid":
                    self.assertTrue(all(not any(item) for item in acquired))

    def test_unexpected_connector_failure_is_sanitized_without_exception_text(self):
        marker = "synthetic-private-exception-marker"
        sink = RecordingSink()
        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=lambda _spec: (_ for _ in ()).throw(RuntimeError(marker)),
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual(outcome.code, "helper_unavailable")
        self.assertEqual(outcome.terminal, "failed")
        self.assertNotIn(marker, json.dumps({
            "outcome": outcome.__dict__, "events": sink.events,
        }))

    def test_typed_fake_connector_failure_maps_only_a_stable_code(self):
        sink = RecordingSink()

        def unavailable(_spec):
            raise self.target._TransportFailure("connection_failed", True)

        outcome = self.target._run_call(
            input_reader=FakeReader([self.request_wire(), b""]),
            connector_factory=unavailable,
            clock=FakeClock(), signal_boundary=FakeSignals(), sink=sink,
        )
        self.assertEqual((outcome.code, outcome.retryable),
                         ("connection_failed", True))
        self.assertEqual(sink.events[-1], {
            "schemaVersion": 1,
            "requestId": "txt-transport.1",
            "sequence": 1,
            "type": "failed",
            "code": "connection_failed",
            "retryable": True,
        })

    def test_source_allows_only_closed_stdlib_transports_and_cli_remains_disabled(self):
        tree = ast.parse(HELPER.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue({"http", "socket", "ssl"}.issubset(imported))
        self.assertTrue(imported.isdisjoint({
            "urllib", "signal", "requests", "openai", "ollama",
            "subprocess", "os", "dotenv", "httpx", "aiohttp",
        }))
        forbidden_calls = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and
                    isinstance(node.func.value, ast.Name) and
                    node.func.value.id == "socket" and
                    node.func.attr in {"create_connection", "getaddrinfo"}):
                forbidden_calls.append(node.func.attr)
        self.assertEqual(forbidden_calls, [])
        main = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        self.assertFalse(any(
            isinstance(node, ast.Name) and
            node.id in {"_OllamaNumericConnector", "_OpenAIHTTPSConnector"}
            for node in ast.walk(main)
        ))
        output = io.StringIO()
        errors = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = self.target.main(["run"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["code"], "unsupported_transport")
        self.assertEqual(errors.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
