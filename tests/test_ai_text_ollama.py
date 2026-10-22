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
from unittest import mock


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


class AiTextOllamaPublishSignalTests(unittest.TestCase):
    CHILD = r'''
import importlib.util,json,os,signal,socket,sys,time
from pathlib import Path
shim_path,ready_path,result_path,interrupt_stage=sys.argv[1:]
prewrite=interrupt_stage=='started-prewrite'
finalizing=interrupt_stage.startswith('finalizer-')
def publish_ready(value):
 ready=Path(ready_path)
 temporary=ready.with_suffix('.pending')
 temporary.write_text(json.dumps(value))
 temporary.replace(ready)
spec=importlib.util.spec_from_file_location('owned_ollama_signal_shim',shim_path)
shim=importlib.util.module_from_spec(spec)
spec.loader.exec_module(shim)
transport=shim._load_transport()
def forbidden_network(*args,**kwargs):
 raise AssertionError('network forbidden in signal publication fixture')
socket.socket=forbidden_network
socket.create_connection=forbidden_network
socket.getaddrinfo=forbidden_network
trace=[]
terminal_traces=[]
terminal_lifecycle=[]
factory_calls=[]
wiped=[]
original_wipe=transport._wipe
def recording_wipe(buffer):
 original_wipe(buffer)
 wiped.append(buffer)
transport._wipe=recording_wipe
class Response:
 def __init__(self,retry=False):
  self.chunks=[json.dumps({'message':{'role':'assistant','content':'fresh' if retry else 'controlled partial'},'done':False}).encode()+b'\n',json.dumps({'message':{'role':'assistant','content':''},'done':True,'prompt_eval_count':4,'eval_count':5}).encode()+b'\n',b'']
 def read1(self,limit,timeout):
  if interrupt_stage=='finalizer-failure' and not paused and len(self.chunks)==2:
   return b'invalid json\n'
  return self.chunks.pop(0)
 def close(self): trace.append('response.close')
class Connector:
 def __init__(self,retry=False):
  factory_calls.append(retry)
  self.response=Response(retry)
 def connect(self,timeout): pass
 def send(self,headers,body,timeout): pass
 def receive_headers(self,timeout): return self.response
 def close(self): trace.append('connector.close')
original_write=os.write
paused=False
def controlled_write(fd,data):
 global paused
 event=json.loads(bytes(data)) if fd==1 else None
 if event and event['type'] in ('completed','failed','cancelled'):
  terminal_traces.append(trace.copy())
  terminal_lifecycle.append({'timer_cancelled':signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'wipe_completed':bool(wiped) and not any(wiped[-1] or b''),'handlers_installed':all(signal.getsignal(getattr(signal,name))!=handlers[name] for name in names),'signals_blocked':set(getattr(signal,name) for name in names).issubset(signal.pthread_sigmask(signal.SIG_BLOCK,set()))})
 if event and event['type']=='started' and prewrite and not paused:
  paused=True
  publish_ready({'pid':os.getpid(),'stage':'started-prewrite','written':0,'bytes':len(data)})
  os.kill(os.getpid(),int(os.environ['OWNED_PREWRITE_SIGNAL']))
 if event and finalizing and interrupt_stage=='finalizer-terminal' and event['type']=='completed' and not paused:
  paused=True
  os.kill(os.getpid(),int(os.environ['OWNED_PREWRITE_SIGNAL']))
  publish_ready({'pid':os.getpid(),'stage':interrupt_stage,'pending':int(os.environ['OWNED_PREWRITE_SIGNAL']) in signal.sigpending(),'pending_names':sorted(number.name for number in signal.sigpending())})
 written=original_write(fd,data)
 if event and event['type']==interrupt_stage and not paused:
  if written!=len(data): raise AssertionError('fixture event did not finish writing')
  paused=True
  publish_ready({'pid':os.getpid(),'stage':interrupt_stage+'-written-inside-publish','written':written,'bytes':len(data)})
  if interrupt_stage=='started':
   deadline=time.monotonic()+1.0
   while not Path(ready_path).with_suffix('.release').exists():
    if time.monotonic()>=deadline: raise AssertionError('parent handshake expired')
    time.sleep(0.005)
  else:
   signal.pause()
 return written
os.write=controlled_write
names=transport.SIGNAL_NAMES
handlers={name:signal.getsignal(getattr(signal,name)) for name in names}
mask=signal.pthread_sigmask(signal.SIG_BLOCK,set())
class FinalizerBoundary(shim.PosixSignalBoundary):
 def hook(self,name,token):
  global paused
  if interrupt_stage in ('finalizer-wipe','finalizer-failure') and name=='after_wipe' and not paused:
   paused=True
   os.kill(os.getpid(),int(os.environ['OWNED_PREWRITE_SIGNAL']))
   if os.environ.get('OWNED_MIXED'):
    os.kill(os.getpid(),signal.SIGALRM)
   publish_ready({'pid':os.getpid(),'stage':interrupt_stage,'pending':int(os.environ['OWNED_PREWRITE_SIGNAL']) in signal.sigpending(),'pending_names':sorted(number.name for number in signal.sigpending())})
boundary=FinalizerBoundary(transport)
sink=shim.NdjsonStdoutSink(transport._contract)
first=transport._run_call(input_reader=shim.FdInputReader(),connector_factory=lambda spec:Connector(),clock=time.monotonic,signal_boundary=boundary,sink=sink)
first_trace=trace.copy()
first_factory_calls=factory_calls.copy()
restored_after_first=all(signal.getsignal(getattr(signal,name))==handlers[name] for name in names)
mask_after_first=signal.pthread_sigmask(signal.SIG_BLOCK,set())==mask
timer_after_first=signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)
trace.clear()
request={'schemaVersion':1,'requestId':'ollama-operational.retry','provider':'ollama_local','task':'summarize','targetLanguage':None,'text':'offline retry marker','model':'gemma3:4b','endpoint':'http://127.0.0.1:11434','credentialBytes':0}
class Reader:
 def __init__(self): self.chunks=[json.dumps(request).encode()+b'\n',b'']
 def read1(self,limit,timeout): return self.chunks.pop(0)
retry=transport._run_call(input_reader=Reader(),connector_factory=lambda spec:Connector(True),clock=time.monotonic,signal_boundary=boundary,sink=sink)
os.write=original_write
Path(result_path).write_text(json.dumps({'first':first.__dict__,'retry':retry.__dict__,'first_close_trace':first_trace,'first_factory_calls':first_factory_calls,'terminal_lifecycle':terminal_lifecycle,'retry_close_trace':trace,'terminal_write_traces':terminal_traces,'handlers_restored':restored_after_first and all(signal.getsignal(getattr(signal,name))==handlers[name] for name in names),'mask_restored':mask_after_first and signal.pthread_sigmask(signal.SIG_BLOCK,set())==mask,'timer_cancelled':timer_after_first and signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)}))
sys.exit(first.exit_code)
'''

    def test_real_posix_signal_inside_delta_publish_keeps_lifecycle_terminal(self):
        self.assert_real_signal_publication("delta")

    def test_real_posix_signal_inside_started_publish_keeps_lifecycle_terminal(self):
        self.assert_real_signal_publication("started")

    def test_real_posix_signal_before_started_write_keeps_lifecycle_terminal(self):
        self.assert_real_signal_publication("started-prewrite")

    def test_real_pending_signal_after_finalizer_block_keeps_committed_terminal(self):
        self.assert_real_signal_publication("finalizer-wipe")
        self.assert_real_signal_publication("finalizer-terminal")
        self.assert_real_signal_publication("finalizer-failure")

    def test_ready_marker_is_hidden_until_complete_json_is_published(self):
        # Capture a partial write deterministically at the same child helper seam.
        function = self.CHILD.split("def publish_ready(value):", 1)[1].split("spec=", 1)[0]
        namespace = {"Path": Path, "json": json}
        with tempfile.TemporaryDirectory(prefix="orla-ready-atomic-") as temporary:
            ready = Path(temporary) / "ready.json"
            namespace["ready_path"] = str(ready)
            exec("def publish_ready(value):" + function, namespace)
            original_write = Path.write_text
            captures = []
            def partial_write(path, value, *args, **kwargs):
                original_write(path, value[:1], *args, **kwargs)
                captures.append((ready.exists(), path.read_text()))
                return original_write(path, value, *args, **kwargs)
            with mock.patch.object(Path, "write_text", partial_write):
                namespace["publish_ready"]({"pid": 123, "stage": "ready"})
            self.assertEqual(captures, [(False, "{")])
            self.assertEqual(json.loads(ready.read_text()), {"pid": 123, "stage": "ready"})
            self.assertFalse(ready.with_suffix(".pending").exists())

    def test_mixed_pending_lifecycle_preserves_terminal_and_first_failure(self):
        self.assert_real_signal_publication("finalizer-wipe", mixed=True)
        self.assert_real_signal_publication("finalizer-failure", mixed=True)

    def assert_real_signal_publication(self, interrupt_stage, *, mixed=False):
        for number in ((signal.SIGTERM,) if mixed else (signal.SIGTERM, signal.SIGALRM)):
            with self.subTest(signal=number.name):
                with tempfile.TemporaryDirectory(prefix="orla-publish-signal-") as temporary:
                    runtime = Path(temporary)
                    ready = runtime / "ready.json"
                    result_path = runtime / "result.json"
                    process = subprocess.Popen(
                        [str(PYTHON), "-I", "-B", "-c", self.CHILD,
                         str(HELPER), str(ready), str(result_path), interrupt_stage],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        cwd=runtime, env={"OWNED_PREWRITE_SIGNAL": str(int(number)), **({"OWNED_MIXED": "1"} if mixed else {})}, start_new_session=True,
                    )
                    try:
                        process.stdin.write(request_wire(11434, text="offline signal marker"))
                        process.stdin.close()
                        process.stdin = None
                        deadline = time.monotonic() + 2.0
                        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.005)
                        observed = ready.exists()
                        marker = json.loads(ready.read_text()) if observed else None
                        if observed and process.poll() is None and interrupt_stage not in {"started-prewrite", "finalizer-wipe", "finalizer-terminal", "finalizer-failure"}:
                            process.send_signal(number)
                            ready.with_suffix(".release").write_text("delivered")
                        elif observed:
                            pass
                        elif process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                        stdout, stderr = process.communicate(timeout=2.5)
                        result = json.loads(result_path.read_text()) if result_path.exists() else None
                        (runtime / "raw.stdout").write_bytes(stdout)
                        (runtime / "raw.stderr").write_bytes(stderr)
                    finally:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=2.0)
                        for stream in (process.stdin, process.stdout, process.stderr):
                            if stream is not None:
                                stream.close()
                    pid = process.pid
                    returncode = process.returncode
                # Reaping and private runtime removal precede every causal publication oracle.
                self.assertFalse(runtime.exists())
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
                with self.assertRaises(ProcessLookupError):
                    os.killpg(pid, 0)
                print("OWNED_PUBLISH_SIGNAL_CLEANUP " + json.dumps({
                    "signal": number.name, "stage": interrupt_stage, "pid": pid, "runtime_gone": True,
                    "pid_group_absent": True, "ready": marker, "result": result,
                    "stdout_hex": stdout.hex(), "stderr_hex": stderr.hex(),
                    "exit": returncode,
                }, sort_keys=True))
                self.assertTrue(observed)
                self.assertEqual(marker["pid"], pid)
                if interrupt_stage.startswith("finalizer-"):
                    self.assertEqual(marker["stage"], interrupt_stage)
                    self.assertTrue(marker["pending"])
                    self.assertEqual(marker["pending_names"], ["SIGALRM", "SIGTERM"] if mixed else [number.name])
                else:
                    self.assertEqual(marker["stage"], ("started-prewrite" if interrupt_stage == "started-prewrite" else interrupt_stage + "-written-inside-publish"))
                    self.assertEqual(marker["written"], 0 if interrupt_stage == "started-prewrite" else marker["bytes"])
                self.assertEqual(stderr, b"")
                self.assertEqual(returncode, 0)
                self.assertTrue(result["handlers_restored"])
                self.assertTrue(result["mask_restored"])
                self.assertTrue(result["timer_cancelled"])
                first_trace = [] if interrupt_stage.startswith("started") else ["response.close", "connector.close"]
                self.assertEqual(result["first_close_trace"], first_trace)
                self.assertEqual(result["first_factory_calls"], [] if interrupt_stage.startswith("started") else [False])
                self.assertEqual(result["terminal_lifecycle"], [
                    {"timer_cancelled": True, "wipe_completed": True,
                     "handlers_installed": True, "signals_blocked": True},
                    {"timer_cancelled": True, "wipe_completed": True,
                     "handlers_installed": True, "signals_blocked": True},
                ])
                self.assertEqual(result["retry_close_trace"], ["response.close", "connector.close"])
                self.assertEqual(result["terminal_write_traces"], [
                    first_trace, ["response.close", "connector.close"],
                ])
                events = [json.loads(line) for line in stdout.splitlines()]
                first = [event for event in events if event["requestId"] == "ollama-operational.1"]
                retry = [event for event in events if event["requestId"] == "ollama-operational.retry"]
                terminal = "failed" if interrupt_stage == "finalizer-failure" else "completed" if interrupt_stage.startswith("finalizer-") else ("cancelled" if number == signal.SIGTERM else "failed")
                first_types = ["started", terminal] if interrupt_stage.startswith("started") else ["started", "delta", terminal]
                self.assertEqual([event["type"] for event in first], first_types)
                self.assertEqual([event["sequence"] for event in first], list(range(len(first_types))))
                self.assertEqual(result["first"]["published_events"], (len(first_types) if interrupt_stage.startswith(("started", "finalizer-")) else len(first_types) - 1))
                self.assertEqual(result["first"]["partial_published"], interrupt_stage.startswith("finalizer-"))
                if interrupt_stage == "delta":
                    self.assertEqual(first[1]["text"], "controlled partial")
                expected = {"schemaVersion": 1, "requestId": "ollama-operational.1",
                            "sequence": len(first_types) - 1, "type": terminal}
                if terminal == "completed":
                    expected.update(finishReason="completed",
                                    usage={"status": "reported", "inputTokens": 4, "outputTokens": 5, "totalTokens": 9},
                                    cost={"status": "unknown", "currency": None, "amount": None})
                if terminal == "failed":
                    expected.update(code="protocol_invalid" if interrupt_stage == "finalizer-failure" else "operation_timeout",
                                    retryable=interrupt_stage != "finalizer-failure")
                self.assertEqual(first[-1], expected)
                self.assertEqual((result["first"]["terminal"], result["first"]["code"], result["first"]["exit_code"]),
                                 (terminal, expected.get("code"), 0))
                self.assertEqual([event["type"] for event in retry], ["started", "delta", "completed"])
                self.assertEqual([event["sequence"] for event in retry], [0, 1, 2])
                self.assertEqual(retry[-1]["usage"]["totalTokens"], 9)
                self.assertEqual((result["retry"]["terminal"], result["retry"]["exit_code"]),
                                 ("completed", 0))



if __name__ == "__main__":
    unittest.main()
