#!/usr/bin/env python3
"""Operational POSIX shim for one explicit numeric-loopback Ollama call."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import selectors
import signal
import sys
import time


def _load_transport():
    path = Path(__file__).resolve().with_name("ai_text_transport.py")
    spec = importlib.util.spec_from_file_location("_orla_ai_text_transport", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("transport unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FdInputReader:
    """Bounded readiness wait and read from the inherited stdin descriptor."""

    def read1(self, limit, timeout):
        if type(limit) is not int or limit <= 0 or not isinstance(timeout, (int, float)):
            raise ValueError("invalid read boundary")
        selector = selectors.DefaultSelector()
        try:
            selector.register(0, selectors.EVENT_READ)
            if not selector.select(timeout):
                raise TimeoutError()
            return os.read(0, limit)
        finally:
            selector.close()


class NdjsonStdoutSink:
    """Write canonical event records completely to the inherited stdout fd."""

    def __init__(self, contract):
        self._contract = contract

    def publish(self, event):
        remaining = memoryview(self._contract._encode_event_line(event))
        while remaining:
            written = os.write(1, remaining)
            if written <= 0:
                raise BrokenPipeError()
            remaining = remaining[written:]


class PosixSignalBoundary:
    """Minimal real signal/timer boundary required by the transport lifecycle."""

    def __init__(self, transport):
        self._transport = transport
        self._numbers = {
            "SIGINT": signal.SIGINT,
            "SIGTERM": signal.SIGTERM,
            "SIGALRM": signal.SIGALRM,
        }

    def _number(self, name):
        try:
            return self._numbers[name]
        except KeyError:
            raise ValueError("unsupported signal") from None

    def block(self, names):
        return signal.pthread_sigmask(
            signal.SIG_BLOCK, {self._number(name) for name in names},
        )

    def get_handler(self, name):
        return signal.getsignal(self._number(name))

    def get_timer(self):
        return signal.getitimer(signal.ITIMER_REAL)

    def install_handler(self, name, callback):
        number = self._number(name)
        timeout = name == "SIGALRM"

        def interrupt(_signum, _frame):
            callback()
            if timeout:
                raise self._transport._TimedOut()
            raise self._transport._Cancelled()

        signal.signal(number, interrupt)

    def arm_timer(self, seconds):
        signal.setitimer(signal.ITIMER_REAL, seconds, 0.0)

    def cancel_timer(self):
        signal.setitimer(signal.ITIMER_REAL, 0.0, 0.0)

    def restore_handler(self, name, handler):
        signal.signal(self._number(name), handler)

    def restore_mask(self, mask):
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)

    def hook(self, name, token):
        del name, token


def _connector_factory(transport):
    def create(spec):
        if not isinstance(spec, dict) or spec.get("provider") != "ollama_local":
            raise transport._contract.ContractError("endpoint_rejected")
        return transport._OllamaNumericConnector(spec)

    return create


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["run-ollama"]:
        return 2
    if not (sys.flags.isolated and sys.flags.ignore_environment and
            sys.flags.dont_write_bytecode):
        return 2
    if os.isatty(0) or os.isatty(1):
        return 2

    transport = _load_transport()
    outcome = transport._run_call(
        input_reader=FdInputReader(),
        connector_factory=_connector_factory(transport),
        clock=time.monotonic,
        signal_boundary=PosixSignalBoundary(transport),
        sink=NdjsonStdoutSink(transport._contract),
    )
    return outcome.exit_code


if __name__ == "__main__":
    try:
        _exit_code = main()
    except BaseException:
        _exit_code = 3
    raise SystemExit(_exit_code)
