"""Operational subprocess tests for the private numeric-loopback Ollama shim."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = (ROOT / "scripts" / "ai_text_ollama.py").resolve()
PYTHON = Path(sys.executable).resolve()
PARENT_HOME = "/literal-parent-home-presence-value"
PARENT_CODEX_HOME = "/literal-parent-codex-presence-value"


def request_wire(port, *, host="127.0.0.1", text="private prompt marker", **changes):
    endpoint_host = host if host == "127.0.0.1" else f"[{host}]"
    request = {
        "schemaVersion": 1,
        "requestId": "ollama-operational.1",
        "provider": "ollama_local",
        "task": "summarize",
        "targetLanguage": None,
        "text": text,
        "model": "gemma3:4b",
        "endpoint": f"http://{endpoint_host}:{port}",
        "credentialBytes": 0,
    }
    request.update(changes)
    return json.dumps(request, separators=(",", ":")).encode() + b"\n"


class OwnedHttpServer:
    def __init__(self, response_parts, *, family=socket.AF_INET, stall=False):
        self.family = family
        self.response_parts = tuple(response_parts)
        self.stall = stall
        self.request = b""
        self.accepted = threading.Event()
        self.request_complete = threading.Event()
        self.release = threading.Event()
        self.error = None
        self.listener = socket.socket(family, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        address = ("127.0.0.1", 0) if family == socket.AF_INET else ("::1", 0, 0, 0)
        self.listener.bind(address)
        self.listener.listen(1)
        self.listener.settimeout(4.0)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def _serve(self):
        connection = None
        try:
            connection, _address = self.listener.accept()
            connection.settimeout(4.0)
            self.accepted.set()
            data = bytearray()
            expected = None
            while expected is None or len(data) < expected:
                chunk = connection.recv(8192)
                if not chunk:
                    break
                data.extend(chunk)
                if expected is None and b"\r\n\r\n" in data:
                    head, body = bytes(data).split(b"\r\n\r\n", 1)
                    content_length = None
                    for line in head.split(b"\r\n")[1:]:
                        name, value = line.split(b":", 1)
                        if name.lower() == b"content-length":
                            content_length = int(value.strip())
                    if content_length is None:
                        raise AssertionError("request omitted Content-Length")
                    expected = len(head) + 4 + content_length
            self.request = bytes(data)
            self.request_complete.set()
            for part in self.response_parts:
                connection.sendall(part)
            if self.stall:
                self.release.wait(4.0)
        except BaseException as error:
            if not (isinstance(error, OSError) and self.release.is_set()):
                self.error = error
            self.request_complete.set()
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass
            try:
                self.listener.close()
            except OSError:
                pass

    def __exit__(self, *_unused):
        self.release.set()
        try:
            self.listener.close()
        except OSError:
            pass
        self.thread.join(5.0)
        if self.thread.is_alive():
            raise AssertionError("owned HTTP server did not stop")
        if self.error is not None:
            raise self.error


class AiTextOllamaOperationalTests(unittest.TestCase):
    def test_cli_rejects_wrong_command_and_missing_isolation_silently(self):
        cases = (
            [str(PYTHON), "-I", "-B", str(HELPER), "run"],
            [str(PYTHON), "-B", str(HELPER), "run-ollama"],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                result = subprocess.run(
                    argv, input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=ROOT, env={}, timeout=2.0, check=False,
                )
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (2, b"", b""))

    def run_helper(self, wire, *, wait=True, close_stdin=True):
        self.assertTrue(PYTHON.is_absolute())
        runtime = tempfile.TemporaryDirectory(prefix="orla-ollama-test-")
        self.addCleanup(runtime.cleanup)
        os.chmod(runtime.name, 0o700)
        previous_home = os.environ.get("HOME")
        previous_codex = os.environ.get("CODEX_HOME")
        os.environ["HOME"] = PARENT_HOME
        os.environ["CODEX_HOME"] = PARENT_CODEX_HOME
        self.addCleanup(self._restore_env, "HOME", previous_home)
        self.addCleanup(self._restore_env, "CODEX_HOME", previous_codex)
        self.assertEqual(os.environ["HOME"], PARENT_HOME)
        self.assertEqual(os.environ["CODEX_HOME"], PARENT_CODEX_HOME)
        process = subprocess.Popen(
            [str(PYTHON), "-I", "-B", str(HELPER), "run-ollama"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=runtime.name, env={}, start_new_session=True,
        )
        self.addCleanup(self._stop_process, process)
        expected_argv = [
            str(PYTHON).encode(), b"-I", b"-B", str(HELPER).encode(), b"run-ollama",
        ]
        deadline = time.monotonic() + 1.0
        observed_argv = []
        while time.monotonic() < deadline and observed_argv != expected_argv:
            observed_argv = Path(f"/proc/{process.pid}/cmdline").read_bytes().split(b"\0")[:-1]
            if observed_argv != expected_argv:
                time.sleep(0.005)
        self.assertEqual(observed_argv, expected_argv)
        self.assertEqual(Path(f"/proc/{process.pid}/environ").read_bytes(), b"")
        assert process.stdin is not None
        process.stdin.write(wire)
        process.stdin.flush()
        if close_stdin:
            process.stdin.close()
            process.stdin = None
        if not wait:
            return process, runtime
        stdout, stderr = process.communicate(timeout=4.0)
        return process, stdout, stderr, runtime

    @staticmethod
    def _restore_env(name, previous):
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous

    @staticmethod
    def _stop_process(process):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2.0)

    def record_then_parse(self, runtime, stdout, stderr):
        stdout_path = Path(runtime.name) / "raw.stdout"
        stderr_path = Path(runtime.name) / "raw.stderr"
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        self.assertEqual(stdout_path.read_bytes(), stdout)
        self.assertEqual(stderr_path.read_bytes(), stderr)
        return [json.loads(line) for line in stdout.splitlines()]

    def test_real_loopback_request_requires_stdin_eof_and_emits_canonical_events(self):
        provider = (
            b'{"message":{"role":"assistant","content":"response marker"},"done":false}\n'
            b'{"message":{"role":"assistant","content":""},"done":true,'
            b'"done_reason":"stop","prompt_eval_count":7,"eval_count":2}\n'
        )
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\n"
            + f"Content-Length: {len(provider)}\r\nConnection: close\r\n\r\n".encode()
            + provider
        )
        with OwnedHttpServer([response]) as server:
            process, stdout, stderr, runtime = self.run_helper(request_wire(server.port))
            self.assertTrue(server.request_complete.wait(1.0))
        events = self.record_then_parse(runtime, stdout, stderr)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(stderr, b"")
        self.assertEqual([event["type"] for event in events],
                         ["started", "delta", "completed"])
        self.assertEqual(events[1]["text"], "response marker")
        self.assertEqual(events[2]["usage"]["totalTokens"], 9)
        head, body = server.request.split(b"\r\n\r\n", 1)
        self.assertIn(b"POST /api/chat HTTP/1.1", head)
        sent = json.loads(body)
        self.assertEqual(sent["messages"][1]["content"], "private prompt marker")
        self.assertNotIn(b"private prompt marker", stdout + stderr)
        self.assertNotIn(PARENT_HOME.encode(), stdout + stderr + server.request)
        self.assertNotIn(PARENT_CODEX_HOME.encode(), stdout + stderr + server.request)

    def test_request_does_not_start_until_actual_stdin_eof(self):
        provider = b'{"message":{"role":"assistant","content":""},"done":true}\n'
        response = (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\n"
            + f"Content-Length: {len(provider)}\r\nConnection: close\r\n\r\n".encode()
            + provider
        )
        with OwnedHttpServer([response]) as server:
            process, runtime = self.run_helper(
                request_wire(server.port), wait=False, close_stdin=False,
            )
            self.assertFalse(server.accepted.wait(0.15))
            assert process.stdin is not None
            process.stdin.close()
            process.stdin = None
            self.assertTrue(server.request_complete.wait(2.0))
            stdout, stderr = process.communicate(timeout=2.0)
        events = self.record_then_parse(runtime, stdout, stderr)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(stderr, b"")
        self.assertEqual([event["type"] for event in events], ["started", "completed"])

    def test_terminal_provider_record_is_withheld_until_http_eof(self):
        provider = b'{"message":{"role":"assistant","content":"final"},"done":true}\n'
        headers = b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\nConnection: close\r\n\r\n"
        with OwnedHttpServer([headers, provider], stall=True) as server:
            process, runtime = self.run_helper(request_wire(server.port), wait=False)
            self.assertTrue(server.request_complete.wait(2.0))
            time.sleep(0.15)
            self.assertIsNone(process.poll())
            server.release.set()
            stdout, stderr = process.communicate(timeout=2.0)
        events = self.record_then_parse(runtime, stdout, stderr)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(stderr, b"")
        self.assertEqual([event["type"] for event in events],
                         ["started", "delta", "completed"])

    def test_bad_frame_fails_preflight_without_output_or_network(self):
        process, stdout, stderr, runtime = self.run_helper(b'{"bad":true}\n')
        self.record_then_parse(runtime, stdout, stderr)
        self.assertEqual((process.returncode, stdout, stderr), (2, b"", b""))

    def test_sigterm_interrupts_real_stalled_socket_before_controller_grace(self):
        delta = b'{"message":{"role":"assistant","content":"kept partial"},"done":false}\n'
        headers = b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\nConnection: close\r\n\r\n"
        with OwnedHttpServer([headers, delta], stall=True) as server:
            process, runtime = self.run_helper(request_wire(server.port), wait=False)
            self.assertTrue(server.request_complete.wait(2.0))
            time.sleep(0.1)
            started = time.monotonic()
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=2.5)
            elapsed = time.monotonic() - started
        events = self.record_then_parse(runtime, stdout, stderr)
        self.assertLess(elapsed, 3.0)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(stderr, b"")
        self.assertEqual([event["type"] for event in events],
                         ["started", "delta", "cancelled"])
        self.assertEqual(events[1]["text"], "kept partial")


if __name__ == "__main__":
    unittest.main()
