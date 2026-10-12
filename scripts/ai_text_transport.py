#!/usr/bin/env python3
"""Private lifecycle and injected HTTP adapters for bounded AI text transport.

The T2.3 stdlib adapter accepts only literal loopback IPv4/IPv6 destinations.
The T2.4 OpenAI adapter requires an injected TCP acquisition port and performs
no operational name resolution or socket creation. All factories remain
injectable for offline tests, and the command-line entry point remains
unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import http.client
import importlib.util
import json
from pathlib import Path
import re
import socket
import ssl
import sys


TOTAL_TIMEOUT = 120.0
CONNECT_TIMEOUT = 5.0
SEND_TIMEOUT = 5.0
FIRST_BYTE_TIMEOUT = 30.0
IDLE_TIMEOUT = 30.0
READ_CHUNK_BYTES = 8 * 1024
MAX_HTTP_REQUEST_BODY_BYTES = 96 * 1024
MAX_HTTP_RESPONSE_BODY_BYTES = 512 * 1024
MAX_HTTP_RESPONSE_HEADERS = 64
MAX_HTTP_RESPONSE_HEADER_BYTES = 32 * 1024
SIGNAL_NAMES = ("SIGINT", "SIGTERM", "SIGALRM")
_CREDENTIAL = re.compile(rb"[A-Za-z0-9._~+/=-]+")
_OLLAMA_URL = re.compile(
    r"^http://(?P<host>127\.0\.0\.1|\[::1\]):(?P<port>[0-9]{1,5})/api/chat$"
)
_OLLAMA_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_OPENAI_URL = "https://api.openai.com/v1/responses"
_OPENAI_HOST = "api.openai.com"
_OPENAI_PORT = 443
_OPENAI_PATH = "/v1/responses"


def _load_contract():
    path = Path(__file__).resolve().with_name("ai_text.py")
    spec = importlib.util.spec_from_file_location("_orla_ai_text_contract", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("contract unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    required = (
        "SCHEMA_VERSION", "MAX_REQUEST_BYTES", "ContractError", "build_request",
        "parse_input", "OllamaNDJSONParser", "OpenAISSEParser", "_encode_event_line",
    )
    if module.SCHEMA_VERSION != 1 or any(not hasattr(module, name) for name in required):
        raise RuntimeError("contract unavailable")
    return module


_contract = _load_contract()


class _Cancelled(Exception):
    pass


class _TimedOut(Exception):
    pass


class _SinkFailure(Exception):
    pass


class _TransportFailure(Exception):
    def __init__(self, code="helper_unavailable", retryable=False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class _NumericHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection whose connect path never resolves a host name."""

    def __init__(self, *, host, port, family, sockaddr, socket_factory=None,
                 timeout=None):
        super().__init__(host, port, timeout=timeout)
        self._numeric_family = family
        self._numeric_sockaddr = sockaddr
        self._socket_factory = socket_factory
        self._cleanup_failed = False
        self._owned_socket = None

    def connect(self):
        factory = socket.socket if self._socket_factory is None else self._socket_factory
        sock = factory(self._numeric_family, socket.SOCK_STREAM)
        self._owned_socket = sock
        self.sock = sock
        try:
            sock.settimeout(self.timeout)
            sock.connect(self._numeric_sockaddr)
        except Exception:
            try:
                sock.close()
            except Exception:
                self._cleanup_failed = True
            else:
                self.sock = None
                self._owned_socket = None
            raise

    def close(self):
        sock = self._owned_socket
        prior_failure = self._cleanup_failed
        parent_failed = False
        close_failed = False
        self.sock = None
        try:
            super().close()
        except Exception:
            self._cleanup_failed = True
            parent_failed = True
        if sock is not None:
            try:
                sock.close()
            except Exception:
                self._cleanup_failed = True
                close_failed = True
            else:
                self._owned_socket = None
        if prior_failure or parent_failed or close_failed:
            raise OSError("numeric socket cleanup failed")


class _OpenAIHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection with an explicit injected TCP acquisition boundary."""

    def __init__(self, *, host, port, context, tcp_port, clock, timeout=None):
        super().__init__(host, port, timeout=timeout, context=context)
        self._tls_context = context
        self._tcp_port = tcp_port
        self._clock = clock
        self._owned_raw_socket = None
        self._owned_tls_socket = None
        self._tcp_acquisition_unconfirmed = False
        self._wrap_transfer_unconfirmed = False
        self._cleanup_failed = False

    def _remaining_connect(self, deadline):
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise TimeoutError()
        return remaining

    def connect(self):
        deadline = self._clock() + self.timeout
        budget = self._remaining_connect(deadline)
        try:
            raw = self._tcp_port.acquire(
                host=self.host, port=self.port, budget=budget,
            )
        except Exception:
            self._tcp_acquisition_unconfirmed = True
            self._cleanup_failed = True
            raise

        self._owned_raw_socket = raw
        self.sock = raw
        raw.settimeout(self._remaining_connect(deadline))
        self._remaining_connect(deadline)
        try:
            wrapped = self._tls_context.wrap_socket(
                raw, server_hostname=_OPENAI_HOST,
                do_handshake_on_connect=False,
            )
        except Exception:
            self._wrap_transfer_unconfirmed = True
            self._cleanup_failed = True
            raise

        self._owned_tls_socket = wrapped
        self.sock = wrapped
        self._owned_raw_socket = None
        wrapped.settimeout(self._remaining_connect(deadline))
        self._remaining_connect(deadline)
        wrapped.do_handshake()
        self._remaining_connect(deadline)

    def close(self):
        raw = self._owned_raw_socket
        wrapped = self._owned_tls_socket
        prior_failure = self._cleanup_failed
        parent_failed = False
        wrapped_failed = False
        raw_failed = False
        self.sock = None
        try:
            super().close()
        except Exception:
            self._cleanup_failed = True
            parent_failed = True
        if wrapped is not None:
            try:
                wrapped.close()
            except Exception:
                self._cleanup_failed = True
                wrapped_failed = True
            else:
                self._owned_tls_socket = None
        if raw is not None:
            try:
                raw.close()
            except Exception:
                self._cleanup_failed = True
                raw_failed = True
            else:
                self._owned_raw_socket = None
        if prior_failure or parent_failed or wrapped_failed or raw_failed:
            raise OSError("HTTPS connection cleanup failed")


def _validate_ollama_body(body):
    if not isinstance(body, dict) or set(body) != {
            "model", "messages", "stream", "options"}:
        raise _contract.ContractError("invalid_request")
    if (not isinstance(body["model"], str) or
            _OLLAMA_MODEL.fullmatch(body["model"]) is None):
        raise _contract.ContractError("invalid_request")
    messages = body["messages"]
    if (not isinstance(messages, list) or len(messages) != 2 or
            any(not isinstance(message, dict) for message in messages)):
        raise _contract.ContractError("invalid_request")
    expected_roles = ("system", "user")
    for message, role in zip(messages, expected_roles):
        if (set(message) != {"role", "content"} or message["role"] != role or
                not isinstance(message["content"], str) or
                not message["content"] or "\x00" in message["content"]):
            raise _contract.ContractError("invalid_request")
    if body["stream"] is not True:
        raise _contract.ContractError("invalid_request")
    options = body["options"]
    if (not isinstance(options, dict) or set(options) != {"num_predict"} or
            type(options["num_predict"]) is not int or
            options["num_predict"] != 1024):
        raise _contract.ContractError("invalid_request")
    try:
        encoded = json.dumps(
            body, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _contract.ContractError("invalid_request") from None
    if len(encoded) > MAX_HTTP_REQUEST_BODY_BYTES:
        raise _contract.ContractError("response_limit")
    return encoded


def _validate_openai_body(body):
    if not isinstance(body, dict) or set(body) != {
            "model", "instructions", "input", "stream", "store", "tools",
            "max_output_tokens"}:
        raise _contract.ContractError("invalid_request")
    for name in ("model", "instructions", "input"):
        value = body[name]
        if (not isinstance(value, str) or not value or "\x00" in value):
            raise _contract.ContractError("invalid_request")
    if (body["stream"] is not True or body["store"] is not False or
            type(body["tools"]) is not list or body["tools"] or
            type(body["max_output_tokens"]) is not int or
            body["max_output_tokens"] != 1024):
        raise _contract.ContractError("invalid_request")
    try:
        encoded = json.dumps(
            body, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise _contract.ContractError("invalid_request") from None
    if len(encoded) > MAX_HTTP_REQUEST_BODY_BYTES:
        raise _contract.ContractError("response_limit")
    return encoded


def _validated_response_headers(response, media_types):
    try:
        headers = response.getheaders()
    except (http.client.HTTPException, OSError):
        raise _contract.ContractError("protocol_invalid") from None
    if not isinstance(headers, list):
        raise _contract.ContractError("protocol_invalid")
    if len(headers) > MAX_HTTP_RESPONSE_HEADERS:
        raise _contract.ContractError("response_limit")
    values = {}
    total = 0
    singletons = {
        "content-type", "content-length", "transfer-encoding",
        "content-encoding", "location",
    }
    for item in headers:
        if (not isinstance(item, tuple) or len(item) != 2 or
                not all(isinstance(part, str) for part in item)):
            raise _contract.ContractError("protocol_invalid")
        name, value = item
        try:
            total += len(name.encode("latin-1")) + len(value.encode("latin-1"))
        except UnicodeEncodeError:
            raise _contract.ContractError("protocol_invalid") from None
        if total > MAX_HTTP_RESPONSE_HEADER_BYTES:
            raise _contract.ContractError("response_limit")
        lower = name.lower()
        if lower in singletons and lower in values:
            raise _contract.ContractError("protocol_invalid")
        if lower in singletons:
            values[lower] = value

    media = values.get("content-type")
    if media not in media_types:
        raise _contract.ContractError("protocol_invalid")
    transfer = values.get("transfer-encoding")
    length_text = values.get("content-length")
    if transfer is not None and length_text is not None:
        raise _contract.ContractError("protocol_invalid")
    if transfer is not None and transfer != "chunked":
        raise _contract.ContractError("protocol_invalid")
    encoding = values.get("content-encoding")
    if encoding is not None and encoding != "identity":
        raise _contract.ContractError("protocol_invalid")
    length = None
    if length_text is not None:
        if not length_text or not length_text.isascii() or not length_text.isdecimal():
            raise _contract.ContractError("protocol_invalid")
        normalized = length_text.lstrip("0") or "0"
        maximum = str(MAX_HTTP_RESPONSE_BODY_BYTES)
        if (len(normalized) > len(maximum) or
                (len(normalized) == len(maximum) and normalized > maximum)):
            raise _contract.ContractError("response_limit")
        length = int(normalized)
    return length, transfer


def _validated_ollama_headers(response):
    return _validated_response_headers(response, (
        "application/x-ndjson",
        "application/x-ndjson; charset=utf-8",
    ))


def _validated_openai_headers(response):
    return _validated_response_headers(response, (
        "text/event-stream",
        "text/event-stream; charset=utf-8",
    ))


class _ValidatedHTTPResponse:
    def __init__(self, response, sock, content_length, transfer_encoding):
        self._response = response
        self._socket = sock
        self._content_length = content_length
        self._transfer_encoding = transfer_encoding
        self._body_bytes_read = 0

    def read1(self, limit, timeout):
        if (self._content_length is not None and
                self._body_bytes_read == self._content_length):
            return b""
        try:
            self._socket.settimeout(timeout)
        except TimeoutError:
            raise
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        try:
            chunk = self._response.read1(limit)
        except TimeoutError:
            raise
        except (http.client.IncompleteRead, http.client.HTTPException):
            raise _contract.ContractError("protocol_invalid") from None
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        if not isinstance(chunk, bytes):
            raise _contract.ContractError("protocol_invalid")
        if len(chunk) > limit:
            raise _contract.ContractError("response_limit")
        new_total = self._body_bytes_read + len(chunk)
        if new_total > MAX_HTTP_RESPONSE_BODY_BYTES:
            raise _contract.ContractError("response_limit")
        if self._content_length is not None and new_total > self._content_length:
            raise _contract.ContractError("protocol_invalid")
        self._body_bytes_read = new_total
        if (not chunk and self._content_length is not None and
                self._body_bytes_read != self._content_length):
            raise _contract.ContractError("protocol_invalid")
        return chunk

    def close(self):
        self._response.close()


class _OllamaNumericConnector:
    """Closed HTTP/1.1 adapter for one normalized local Ollama destination."""

    def __init__(self, spec, *, socket_factory=None, connection_factory=None):
        if (not isinstance(spec, dict) or spec.get("provider") != "ollama_local" or
                set(spec) != {"provider", "url"} or
                not isinstance(spec["url"], str)):
            raise _contract.ContractError("endpoint_rejected")
        match = _OLLAMA_URL.fullmatch(spec["url"])
        if match is None:
            raise _contract.ContractError("endpoint_rejected")
        port = int(match.group("port"))
        if not 1 <= port <= 65_535:
            raise _contract.ContractError("endpoint_rejected")
        bracketed_host = match.group("host")
        if bracketed_host == "127.0.0.1":
            host = bracketed_host
            family = socket.AF_INET
            sockaddr = (host, port)
            authority = f"{host}:{port}"
        else:
            host = "::1"
            family = socket.AF_INET6
            sockaddr = (host, port, 0, 0)
            authority = f"[{host}]:{port}"
        factory = _NumericHTTPConnection if connection_factory is None else connection_factory
        self._connection = factory(
            host=host, port=port, family=family, sockaddr=sockaddr,
            socket_factory=socket_factory, timeout=None,
        )
        self._authority = authority
        self._pending_response = None
        self._cleanup_failed = False

    def connect(self, timeout):
        self._connection.timeout = timeout
        try:
            self._connection.connect()
        except TimeoutError:
            raise
        except OSError:
            raise _TransportFailure("connection_failed", True) from None

    def _set_socket_timeout(self, timeout):
        sock = self._connection.sock
        if sock is None:
            raise _TransportFailure("connection_failed", True)
        try:
            sock.settimeout(timeout)
        except TimeoutError:
            raise
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        return sock

    def send(self, headers, body, timeout):
        if headers != ():
            raise _contract.ContractError("invalid_request")
        encoded = _validate_ollama_body(body)
        self._set_socket_timeout(timeout)
        try:
            self._connection.putrequest(
                "POST", "/api/chat", skip_host=True, skip_accept_encoding=True,
            )
            for name, value in (
                    ("Host", self._authority),
                    ("Content-Type", "application/json"),
                    ("Accept", "application/x-ndjson"),
                    ("Accept-Encoding", "identity"),
                    ("Content-Length", str(len(encoded))),
                    ("Connection", "close")):
                self._connection.putheader(name, value)
            self._connection.endheaders(encoded, encode_chunked=False)
        except TimeoutError:
            raise
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        except http.client.HTTPException:
            raise _contract.ContractError("protocol_invalid") from None

    def receive_headers(self, timeout):
        sock = self._set_socket_timeout(timeout)
        try:
            response = self._connection.getresponse()
        except TimeoutError:
            raise
        except (ConnectionError, http.client.RemoteDisconnected):
            raise _TransportFailure("connection_failed", True) from None
        except http.client.HTTPException:
            raise _contract.ContractError("protocol_invalid") from None
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        self._pending_response = response
        if response.status != 200:
            code, retryable = _contract.map_http_status(response.status)
            raise _TransportFailure(code, retryable)
        content_length, transfer_encoding = _validated_ollama_headers(response)
        validated = _ValidatedHTTPResponse(
            response, sock, content_length, transfer_encoding,
        )
        self._pending_response = None
        return validated

    def close(self):
        cleanup_failed = self._cleanup_failed
        response = self._pending_response
        if response is not None:
            try:
                response.close()
            except Exception:
                self._cleanup_failed = True
                cleanup_failed = True
            else:
                self._pending_response = None
        try:
            self._connection.close()
        except Exception:
            self._cleanup_failed = True
            cleanup_failed = True
        if cleanup_failed:
            raise OSError("numeric connector cleanup failed")


class _OpenAIHTTPSConnector:
    """Closed HTTPS adapter requiring a caller-supplied TCP acquisition port."""

    def __init__(self, spec, *, tcp_port, clock, context_factory=None,
                 connection_factory=None):
        if (not isinstance(spec, dict) or
                set(spec) != {"provider", "url"} or
                spec.get("provider") != "openai_api" or
                spec.get("url") != _OPENAI_URL):
            raise _contract.ContractError("endpoint_rejected")
        acquire = getattr(tcp_port, "acquire", None)
        if not callable(acquire) or not callable(clock):
            raise _contract.ContractError("endpoint_rejected")

        make_context = ssl.create_default_context if context_factory is None else context_factory
        context = make_context()
        if (getattr(context, "verify_mode", None) != ssl.CERT_REQUIRED or
                getattr(context, "check_hostname", None) is not True or
                getattr(context, "keylog_filename", None) is not None):
            raise _contract.ContractError("endpoint_rejected")

        factory = (_OpenAIHTTPSConnection if connection_factory is None
                   else connection_factory)
        self._connection = factory(
            host=_OPENAI_HOST, port=_OPENAI_PORT, context=context,
            tcp_port=tcp_port, clock=clock, timeout=None,
        )
        self._pending_response = None
        self._cleanup_failed = False

    def connect(self, timeout):
        self._connection.timeout = timeout
        try:
            self._connection.connect()
        except TimeoutError:
            raise
        except ssl.SSLError:
            raise _TransportFailure("tls_failed", False) from None
        except OSError:
            raise _TransportFailure("connection_failed", True) from None

    def _set_socket_timeout(self, timeout):
        sock = self._connection.sock
        if sock is None:
            raise _TransportFailure("connection_failed", True)
        try:
            sock.settimeout(timeout)
        except TimeoutError:
            raise
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        return sock

    def send(self, headers, body, timeout):
        if (not isinstance(headers, tuple) or len(headers) != 1 or
                not isinstance(headers[0], tuple) or len(headers[0]) != 2 or
                headers[0][0] != "Authorization" or
                not isinstance(headers[0][1], bytearray)):
            raise _contract.ContractError("invalid_request")
        credential = headers[0][1]
        if (not 20 <= len(credential) <= 512 or
                _CREDENTIAL.fullmatch(credential) is None):
            raise _contract.ContractError("invalid_request")
        encoded = _validate_openai_body(body)
        bearer = bytearray(b"Bearer ")
        bearer.extend(credential)
        try:
            self._set_socket_timeout(timeout)
            self._connection.putrequest(
                "POST", _OPENAI_PATH,
                skip_host=True, skip_accept_encoding=True,
            )
            for name, value in (
                    ("Host", _OPENAI_HOST),
                    ("Content-Type", "application/json"),
                    ("Accept", "text/event-stream"),
                    ("Accept-Encoding", "identity"),
                    ("Content-Length", str(len(encoded))),
                    ("Connection", "close"),
                    ("Authorization", bytes(bearer))):
                self._connection.putheader(name, value)
            self._connection.endheaders(encoded, encode_chunked=False)
        except TimeoutError:
            raise
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        except http.client.HTTPException:
            raise _contract.ContractError("protocol_invalid") from None
        finally:
            try:
                _wipe(bearer)
            except Exception:
                self._cleanup_failed = True

    def receive_headers(self, timeout):
        sock = self._set_socket_timeout(timeout)
        try:
            response = self._connection.getresponse()
        except TimeoutError:
            raise
        except (ConnectionError, http.client.RemoteDisconnected):
            raise _TransportFailure("connection_failed", True) from None
        except http.client.HTTPException:
            raise _contract.ContractError("protocol_invalid") from None
        except OSError:
            raise _TransportFailure("connection_failed", True) from None
        self._pending_response = response
        if response.status != 200:
            code, retryable = _contract.map_http_status(response.status)
            raise _TransportFailure(code, retryable)
        content_length, transfer_encoding = _validated_openai_headers(response)
        validated = _ValidatedHTTPResponse(
            response, sock, content_length, transfer_encoding,
        )
        self._pending_response = None
        return validated

    def close(self):
        cleanup_failed = self._cleanup_failed
        response = self._pending_response
        if response is not None:
            try:
                response.close()
            except Exception:
                self._cleanup_failed = True
                cleanup_failed = True
            else:
                self._pending_response = None
        try:
            self._connection.close()
        except Exception:
            self._cleanup_failed = True
            cleanup_failed = True
        if cleanup_failed:
            raise OSError("HTTPS connector cleanup failed")


@dataclass(frozen=True)
class _TransportOutcome:
    state: str
    terminal: str | None
    code: str | None
    retryable: bool
    published_events: int
    partial_published: bool
    exit_code: int


@dataclass
class _CancellationToken:
    cancelled: bool = False
    timed_out: bool = False

    def cancel(self):
        self.cancelled = True

    def timeout(self):
        self.timed_out = True

    def check(self):
        if self.timed_out:
            raise _TimedOut()
        if self.cancelled:
            raise _Cancelled()


@dataclass
class _SignalSetupLedger:
    setup_mask_acquired: bool = False
    setup_previous_mask: object | None = None
    original_handlers: dict[str, object] = field(default_factory=dict)
    original_timer_captured: bool = False
    handlers_installed: list[str] = field(default_factory=list)
    timer_armed: bool = False
    started_published: bool = False


def _remaining(clock, deadline):
    value = deadline - clock()
    return value if value > 0.0 else 0.0


def _phase_timeout(clock, deadline, limit=None):
    remaining = _remaining(clock, deadline)
    if remaining <= 0.0:
        raise _TimedOut()
    return remaining if limit is None else min(limit, remaining)


def _check_operational(clock, deadline, token):
    token.check()
    if _remaining(clock, deadline) <= 0.0:
        raise _TimedOut()


def _boundary_timeout(clock, deadline, token, limit=None):
    token.check()
    return _phase_timeout(clock, deadline, limit)


def _wipe(buffer):
    if isinstance(buffer, bytearray):
        for index in range(len(buffer)):
            buffer[index] = 0


def _signal_handler(token, *, timeout=False):
    def handler(*_unused):
        if timeout:
            token.timeout()
        else:
            token.cancel()
    return handler


def _setup_signals(boundary, token, clock, deadline, ledger):
    previous_mask = boundary.block(SIGNAL_NAMES)
    ledger.setup_previous_mask = previous_mask
    ledger.setup_mask_acquired = True

    for name in SIGNAL_NAMES:
        ledger.original_handlers[name] = boundary.get_handler(name)
    timer = boundary.get_timer()
    ledger.original_timer_captured = True
    if timer != (0.0, 0.0):
        raise RuntimeError("preflight")

    for name in SIGNAL_NAMES:
        boundary.install_handler(
            name, _signal_handler(token, timeout=(name == "SIGALRM"))
        )
        ledger.handlers_installed.append(name)

    remaining = _remaining(clock, deadline)
    if remaining <= 0.0:
        raise _TimedOut()
    boundary.arm_timer(remaining)
    ledger.timer_armed = True
    boundary.restore_mask(ledger.setup_previous_mask)
    ledger.setup_mask_acquired = False


def _rollback_operational(boundary, ledger):
    failed = False
    if ledger.timer_armed:
        try:
            boundary.cancel_timer()
        except Exception:
            failed = True
        else:
            ledger.timer_armed = False
    for name in tuple(reversed(ledger.handlers_installed)):
        try:
            boundary.restore_handler(name, ledger.original_handlers[name])
        except Exception:
            failed = True
        else:
            ledger.handlers_installed.remove(name)
    return failed


def _restore_setup_mask(boundary, ledger):
    if not ledger.setup_mask_acquired:
        return False
    try:
        boundary.restore_mask(ledger.setup_previous_mask)
    except Exception:
        return True
    ledger.setup_mask_acquired = False
    return False


def _rollback_preflight(boundary, ledger, buffers=()):
    failed = False
    for buffer in buffers:
        try:
            _wipe(buffer)
        except Exception:
            failed = True
    failed = _rollback_operational(boundary, ledger) or failed
    mask_failed = _restore_setup_mask(boundary, ledger)
    return mask_failed or failed


def _read_call_frame(input_reader, clock, deadline, token):
    maximum = _contract.MAX_REQUEST_BYTES + 1 + 512
    raw = bytearray()
    credential = None
    try:
        while True:
            token.check()
            remaining = _remaining(clock, deadline)
            if remaining <= 0.0:
                raise _TimedOut()
            limit = min(READ_CHUNK_BYTES, maximum + 1 - len(raw))
            if limit <= 0:
                raise _contract.ContractError("invalid_request")
            try:
                chunk = input_reader.read1(limit, remaining)
            except TimeoutError:
                raise _TimedOut() from None
            _check_operational(clock, deadline, token)
            if not isinstance(chunk, bytes):
                raise _contract.ContractError("invalid_request")
            if not chunk:
                break
            if len(chunk) > limit:
                raise _contract.ContractError("invalid_request")
            raw.extend(chunk)
            if len(raw) > maximum:
                raise _contract.ContractError("invalid_request")
        request, credential = _contract.parse_input(bytes(raw))
        if request["provider"] == "openai_api":
            if _CREDENTIAL.fullmatch(credential) is None:
                raise _contract.ContractError("invalid_request")
        elif credential:
            raise _contract.ContractError("invalid_request")
    except Exception:
        try:
            _wipe(raw)
        except Exception:
            pass
        if credential is not None:
            try:
                _wipe(credential)
            except Exception:
                pass
        raise

    try:
        _wipe(raw)
    except Exception:
        try:
            _wipe(credential)
        except Exception:
            pass
        raise _TransportFailure("process_cleanup_failed", False) from None
    return request, credential


def _preflight_outcome(error=None):
    terminal, code, retryable = _failure_from_exception(error)
    if terminal == "cancelled":
        code = "credential_cancelled"
    return _TransportOutcome(
        state="preflight_failed", terminal=None, code=code,
        retryable=retryable, published_events=0,
        partial_published=False, exit_code=2,
    )


def _safe_hook(boundary, name, token):
    boundary.hook(name, token)


def _safe_close(resource):
    if resource is None:
        return False
    try:
        resource.close()
    except Exception:
        return True
    return False


def _failure_from_exception(error):
    if isinstance(error, _Cancelled):
        return "cancelled", None, False
    if isinstance(error, (_TimedOut, TimeoutError)):
        return "failed", "operation_timeout", True
    if isinstance(error, _TransportFailure):
        if (error.code in _contract._FAILURE_CODES and
                isinstance(error.retryable, bool)):
            return "failed", error.code, error.retryable
        return "failed", "helper_unavailable", False
    if isinstance(error, _contract.ContractError):
        code = error.code if error.code in _contract._FAILURE_CODES else "protocol_invalid"
        return "failed", code, False
    return "failed", "helper_unavailable", False


def _parser_for(request):
    if request["provider"] == "ollama_local":
        return _contract.OllamaNDJSONParser(request)
    return _contract.OpenAISSEParser(request)


def _body_contains_secret(value, secret):
    if not secret:
        return False
    if isinstance(value, str):
        return bytes(secret) in value.encode("utf-8")
    if isinstance(value, dict):
        return any(
            _body_contains_secret(key, secret) or
            _body_contains_secret(item, secret)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_body_contains_secret(item, secret) for item in value)
    return False


def _publish(sink, events, state):
    for event in events:
        try:
            if event["type"] == "started":
                state["started_publication_begun"] = True
            sink.publish(event)
        except (_Cancelled, _TimedOut):
            raise
        except Exception:
            raise _SinkFailure() from None
        state["published_events"] += 1
        if event["type"] == "delta":
            state["partial_published"] = True


def _restore_pending(parser, pending):
    if pending is not None:
        parser._restore(pending[0])


def _finalize_started(*, boundary, ledger, token, parser, pending,
                      operational_error, sink_unavailable, response, connector, credential,
                      sink, state):
    try:
        previous_mask = boundary.block(SIGNAL_NAMES)
    except Exception:
        _restore_pending(parser, pending)
        _safe_close(response)
        _safe_close(connector)
        try:
            _wipe(credential)
        except Exception:
            pass
        _rollback_operational(boundary, ledger)
        return _TransportOutcome(
            state="finalization_failed", terminal=None,
            code="process_cleanup_failed", retryable=False,
            published_events=state["published_events"],
            partial_published=state["partial_published"], exit_code=3,
        )

    cleanup_failed = False
    sink_failed = False
    terminal_kind = None
    terminal_code = None
    terminal_retryable = False
    restore_failed = False
    try:
        try:
            _safe_hook(boundary, "before_response_close", token)
        except Exception:
            cleanup_failed = True
        cleanup_failed = _safe_close(response) or cleanup_failed
        try:
            _safe_hook(boundary, "after_response_close", token)
            _safe_hook(boundary, "before_connector_close", token)
        except Exception:
            cleanup_failed = True
        cleanup_failed = _safe_close(connector) or cleanup_failed
        try:
            _safe_hook(boundary, "after_connector_close", token)
        except Exception:
            cleanup_failed = True

        if ledger.timer_armed:
            try:
                boundary.cancel_timer()
            except Exception:
                cleanup_failed = True
            else:
                ledger.timer_armed = False

        try:
            _safe_hook(boundary, "before_wipe", token)
        except Exception:
            cleanup_failed = True
        try:
            _wipe(credential)
        except Exception:
            cleanup_failed = True
        try:
            _safe_hook(boundary, "after_wipe", token)
        except Exception:
            cleanup_failed = True

        if cleanup_failed:
            terminal_kind, terminal_code, terminal_retryable = (
                "failed", "process_cleanup_failed", False,
            )
        elif token.cancelled:
            terminal_kind, terminal_code, terminal_retryable = "cancelled", None, False
        elif token.timed_out:
            terminal_kind, terminal_code, terminal_retryable = (
                "failed", "operation_timeout", True,
            )
        elif operational_error is not None:
            terminal_kind, terminal_code, terminal_retryable = operational_error
        elif pending is None:
            terminal_kind, terminal_code, terminal_retryable = (
                "failed", "protocol_invalid", False,
            )

        try:
            boundary.hook("before_terminal", token)
        except Exception:
            cleanup_failed = True
            terminal_kind, terminal_code, terminal_retryable = (
                "failed", "process_cleanup_failed", False,
            )
        if not cleanup_failed:
            if token.cancelled:
                terminal_kind, terminal_code, terminal_retryable = "cancelled", None, False
            elif token.timed_out:
                terminal_kind, terminal_code, terminal_retryable = (
                    "failed", "operation_timeout", True,
                )

        if sink_unavailable:
            _restore_pending(parser, pending)
            sink_failed = True
        else:
            replacement = terminal_kind is not None
            if replacement:
                _restore_pending(parser, pending)
                if terminal_kind == "cancelled":
                    batch = [parser.events.cancelled()]
                else:
                    batch = [parser.events.failed(terminal_code, terminal_retryable)]
            else:
                batch = pending[1]
            terminal_kind = batch[-1]["type"]
            terminal_code = batch[-1].get("code")

            state["terminal_attempted"] = True
            try:
                _publish(sink, batch, state)
            except _SinkFailure:
                sink_failed = True
    finally:
        for name in tuple(reversed(ledger.handlers_installed)):
            try:
                boundary.restore_handler(name, ledger.original_handlers[name])
            except Exception:
                restore_failed = True
            else:
                ledger.handlers_installed.remove(name)
        try:
            boundary.restore_mask(previous_mask)
        except Exception:
            restore_failed = True

    if sink_failed:
        return _TransportOutcome(
            state="sink_failed", terminal=None, code=None, retryable=False,
            published_events=state["published_events"],
            partial_published=state["partial_published"], exit_code=3,
        )
    if restore_failed:
        return _TransportOutcome(
            state="finalization_failed", terminal=terminal_kind,
            code="process_cleanup_failed", retryable=False,
            published_events=state["published_events"],
            partial_published=state["partial_published"], exit_code=3,
        )
    return _TransportOutcome(
        state="terminal_emitted", terminal=terminal_kind, code=terminal_code,
        retryable=terminal_retryable,
        published_events=state["published_events"],
        partial_published=state["partial_published"], exit_code=0,
    )


def _run_call(*, input_reader, connector_factory, clock, signal_boundary, sink):
    """Run one fake-only call; real connectors and signal APIs are unsupported."""
    deadline = clock() + TOTAL_TIMEOUT
    token = _CancellationToken()
    ledger = _SignalSetupLedger()
    credential = None
    request = None
    try:
        _setup_signals(signal_boundary, token, clock, deadline, ledger)
        request, credential = _read_call_frame(input_reader, clock, deadline, token)
        parser = _parser_for(request)
        built = _contract.build_request(request)
        if _body_contains_secret(built["body"], credential):
            raise _contract.ContractError("invalid_request")
    except Exception as error:
        if not ledger.setup_mask_acquired and ledger.handlers_installed:
            try:
                ledger.setup_previous_mask = signal_boundary.block(SIGNAL_NAMES)
                ledger.setup_mask_acquired = True
            except Exception:
                pass
        cleanup_failed = _rollback_preflight(
            signal_boundary, ledger,
            () if credential is None else (credential,),
        )
        if cleanup_failed:
            error = _TransportFailure("process_cleanup_failed", False)
        return _preflight_outcome(error)

    connector = None
    response = None
    pending = None
    operational_error = None
    sink_unavailable = False
    state = {
        "started_publication_begun": False,
        "published_events": 0,
        "partial_published": False,
        "terminal_attempted": False,
    }
    try:
        _check_operational(clock, deadline, token)
        _publish(sink, parser.start(), state)
        ledger.started_published = True
        _check_operational(clock, deadline, token)

        connector = connector_factory({
            "provider": request["provider"],
            "url": built["url"],
        })
        _check_operational(clock, deadline, token)
        connector.connect(_boundary_timeout(
            clock, deadline, token, CONNECT_TIMEOUT,
        ))
        _check_operational(clock, deadline, token)
        request_headers = (() if request["provider"] == "ollama_local" else
                           (("Authorization", credential),))
        connector.send(request_headers, built["body"], _boundary_timeout(
            clock, deadline, token, SEND_TIMEOUT,
        ))
        _check_operational(clock, deadline, token)
        response = connector.receive_headers(
            _boundary_timeout(clock, deadline, token, FIRST_BYTE_TIMEOUT)
        )
        _check_operational(clock, deadline, token)

        while True:
            chunk = response.read1(
                READ_CHUNK_BYTES,
                _boundary_timeout(clock, deadline, token, IDLE_TIMEOUT),
            )
            _check_operational(clock, deadline, token)
            if not isinstance(chunk, bytes):
                raise _contract.ContractError("protocol_invalid")
            if len(chunk) > READ_CHUNK_BYTES:
                raise _contract.ContractError("response_limit")
            if not chunk:
                parser.finish()
                if pending is None:
                    raise _contract.ContractError("protocol_invalid")
                break
            if pending is not None:
                _restore_pending(parser, pending)
                pending = None
                raise _contract.ContractError("protocol_invalid")
            snapshot = parser._snapshot()
            try:
                events = parser.feed(chunk)
                _check_operational(clock, deadline, token)
            except Exception:
                parser._restore(snapshot)
                raise
            if events and events[-1]["type"] in {"completed", "failed", "cancelled"}:
                pending = (snapshot, events)
            else:
                _publish(sink, events, state)
                _check_operational(clock, deadline, token)
    except Exception as error:
        if not ledger.started_published and not (
                state["started_publication_begun"] and
                isinstance(error, (_Cancelled, _TimedOut))):
            if not ledger.setup_mask_acquired and ledger.handlers_installed:
                try:
                    ledger.setup_previous_mask = signal_boundary.block(SIGNAL_NAMES)
                    ledger.setup_mask_acquired = True
                except Exception:
                    pass
            cleanup_failed = _rollback_preflight(
                signal_boundary, ledger,
                () if credential is None else (credential,),
            )
            if isinstance(error, _SinkFailure):
                return _TransportOutcome(
                    state="sink_failed", terminal=None, code=None,
                    retryable=False, published_events=state["published_events"],
                    partial_published=state["partial_published"], exit_code=3,
                )
            if cleanup_failed:
                error = _TransportFailure("process_cleanup_failed", False)
            return _preflight_outcome(error)
        if isinstance(error, _SinkFailure):
            sink_unavailable = True
        else:
            operational_error = _failure_from_exception(error)

    return _finalize_started(
        boundary=signal_boundary, ledger=ledger, token=token, parser=parser,
        pending=pending, operational_error=operational_error,
        sink_unavailable=sink_unavailable, response=response,
        connector=connector, credential=credential, sink=sink, state=state,
    )


def main(argv=None):
    del argv
    result = {
        "schemaVersion": 1,
        "type": "failed",
        "code": "unsupported_transport",
        "retryable": False,
    }
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
