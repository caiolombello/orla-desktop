#!/usr/bin/env python3
"""Private, offline contract helpers for Orla's text transformation slice.

This module deliberately contains no transport.  It validates the private
request, builds closed provider payloads, and converts bounded fixture streams
into sanitized internal events.
"""

from __future__ import annotations

import json
import re
import sys


SCHEMA_VERSION = 1
MAX_REQUEST_BYTES = 96 * 1024
MAX_TEXT_CHARS = 16_384
MAX_TEXT_BYTES = 65_536
MAX_PROVIDER_RECORD_BYTES = 64 * 1024
MAX_PROVIDER_STREAM_BYTES = 512 * 1024
MAX_EVENT_LINE_BYTES = 64 * 1024
MAX_EVENTS = 4_096
MAX_DELTA_BYTES = 8 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
MAX_TOKENS = 1_024
MAX_I64 = (1 << 63) - 1
OPENAI_URL = "https://api.openai.com/v1/responses"

_FAILURE_CODES = frozenset({
    "invalid_request", "helper_unavailable", "credential_cancelled",
    "credential_required", "endpoint_rejected", "connection_failed", "tls_failed",
    "authentication_failed", "permission_denied", "model_unavailable", "rate_limited",
    "provider_unavailable", "provider_failed", "unsupported_provider_event",
    "protocol_invalid", "response_limit", "operation_timeout",
    "process_cleanup_failed", "unsupported_transport",
})
_OLLAMA_FINISH_REASONS = frozenset({"stop", "length", "load", "completed"})
_FINISH_REASONS = _OLLAMA_FINISH_REASONS | {"incomplete"}
_USAGE_KEYS = frozenset({"status", "inputTokens", "outputTokens", "totalTokens"})
_CAPABILITY_KEYS = frozenset({
    "tool_call", "tool_calls", "function_call", "function_calls", "thinking",
    "search_call", "web_search_call", "file_search_call", "computer_call",
    "code_interpreter_call", "mcp_call", "mcp_list_tools", "shell_call",
    "local_shell_call", "image_generation_call",
})
_NON_TEXT_TYPES = frozenset({
    "refusal", "reasoning", "input_image", "output_audio", "computer_screenshot",
})
_OLLAMA_RECORD_KEYS = frozenset({
    "model", "created_at", "message", "done", "done_reason", "total_duration",
    "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count",
    "eval_duration",
})
_OPENAI_RESPONSE_KEYS = frozenset({
    "id", "object", "access_programs", "created_at", "status", "completed_at",
    "error", "incomplete_details", "input", "instructions", "max_output_tokens",
    "max_tool_calls", "model", "output", "previous_response_id", "prompt",
    "reasoning", "reasoning_effort", "safety_identifier", "service_tier", "store",
    "temperature", "text", "tool_choice", "tools", "top_logprobs", "top_p",
    "truncation", "usage", "user", "metadata", "parallel_tool_calls",
})
_OPENAI_LIFECYCLE_EVENT_KEYS = frozenset({"type", "response", "sequence_number"})
_OPENAI_DELTA_EVENT_KEYS = frozenset({
    "type", "item_id", "output_index", "content_index", "delta", "logprobs",
    "obfuscation", "sequence_number",
})
_OPENAI_OUTPUT_TEXT_DONE_KEYS = frozenset({
    "type", "item_id", "output_index", "content_index", "text", "logprobs",
    "sequence_number",
})
_OPENAI_OUTPUT_ITEM_EVENT_KEYS = frozenset({
    "type", "output_index", "item", "sequence_number",
})
_OPENAI_CONTENT_PART_EVENT_KEYS = frozenset({
    "type", "item_id", "output_index", "content_index", "part", "sequence_number",
})
_OPENAI_MESSAGE_KEYS = frozenset({"id", "status", "type", "role", "content"})
_OPENAI_TEXT_PART_KEYS = frozenset({"type", "text", "annotations", "logprobs"})
_OPENAI_LIFECYCLE_STATUSES = {
    "response.created": frozenset({"in_progress", "queued"}),
    "response.in_progress": frozenset({"in_progress"}),
    "response.completed": frozenset({"completed"}),
    "response.incomplete": frozenset({"incomplete"}),
    "response.failed": frozenset({"failed"}),
}

_REQUEST_KEYS = frozenset({
    "schemaVersion", "requestId", "provider", "task", "targetLanguage",
    "text", "model", "endpoint", "credentialBytes",
})
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_OLLAMA_ENDPOINT = re.compile(
    r"^http://(?P<host>127\.0\.0\.1|\[::1\]):(?P<port>[0-9]{1,5})(?P<path>/|/api/chat)?$"
)

_SYSTEM_INSTRUCTIONS = {
    "rewrite": "Rewrite the user's text while preserving its meaning. Return only the rewritten text.",
    "summarize": "Summarize the user's text accurately. Return only the summary.",
}


class ContractError(ValueError):
    """A stable, non-sensitive contract failure."""

    def __init__(self, code: str = "protocol_invalid"):
        super().__init__(code)
        self.code = code


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("invalid_request")
        result[key] = value
    return result


def _plain_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bounded_count(value):
    if not _plain_int(value) or value < 0 or value > MAX_I64:
        raise ContractError()
    return value


def _unknown_usage():
    return {
        "status": "unknown", "inputTokens": None,
        "outputTokens": None, "totalTokens": None,
    }


def _reported_usage(input_tokens, output_tokens, total_tokens=None):
    input_tokens = _bounded_count(input_tokens)
    output_tokens = _bounded_count(output_tokens)
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens
        if total_tokens > MAX_I64:
            raise ContractError()
    else:
        total_tokens = _bounded_count(total_tokens)
        if total_tokens != input_tokens + output_tokens:
            raise ContractError()
    return {
        "status": "reported", "inputTokens": input_tokens,
        "outputTokens": output_tokens, "totalTokens": total_tokens,
    }


def _unknown_cost():
    return {"status": "unknown", "currency": None, "amount": None}


def _encode_event_line(event):
    """Canonical private NDJSON encoding used for the pre-publication bound."""
    try:
        encoded = (json.dumps(
            event, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ) + "\n").encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ContractError() from None
    if len(encoded) > MAX_EVENT_LINE_BYTES:
        raise ContractError("response_limit")
    return encoded


def _closed_usage(value):
    if value is None:
        return _unknown_usage()
    if not isinstance(value, dict) or set(value) != _USAGE_KEYS:
        raise ContractError()
    if value["status"] == "unknown":
        if any(value[key] is not None for key in _USAGE_KEYS - {"status"}):
            raise ContractError()
        return _unknown_usage()
    if value["status"] != "reported":
        raise ContractError()
    return _reported_usage(
        value["inputTokens"], value["outputTokens"], value["totalTokens"]
    )


def _has_capability_output(value, *, ollama=False):
    """Find executable/non-text output markers without recursing on hostile JSON."""
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if key in _CAPABILITY_KEYS or (ollama and key in {
                    "tools", "tool_choice", "parallel_tool_calls",
                }):
                    return True
                if key == "type" and isinstance(child, str):
                    lowered = child.lower()
                    if (lowered in _NON_TEXT_TYPES or "tool_call" in lowered or
                            "function_call" in lowered or
                            "search_call" in lowered or "computer_call" in lowered or
                            "interpreter_call" in lowered or "mcp_call" in lowered or
                            "shell_call" in lowered or "image_generation_call" in lowered):
                        return True
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)
    return False


def _strict_utf8_string(value):
    if not isinstance(value, str):
        raise ContractError()
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ContractError() from None
    return value


def _validate_external_scalars(value):
    """Validate every external string and reject non-finite JSON numbers."""
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            _strict_utf8_string(current)
        elif isinstance(current, dict):
            for key, child in current.items():
                _strict_utf8_string(key)
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, float):
            if current != current or current in (float("inf"), float("-inf")):
                raise ContractError()


def _closed_keys(value, allowed):
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise ContractError()
    return value


def _validate_openai_event_scalars(record):
    for field in ("sequence_number", "output_index", "content_index"):
        if field in record:
            _bounded_count(record[field])
    if "item_id" in record:
        _strict_utf8_string(record["item_id"])


def _validate_openai_text_part(part):
    _closed_keys(part, _OPENAI_TEXT_PART_KEYS)
    if part.get("type") != "output_text":
        raise ContractError("unsupported_provider_event")
    if "text" in part:
        _strict_utf8_string(part["text"])
    if "annotations" in part and not isinstance(part["annotations"], list):
        raise ContractError()
    if "logprobs" in part and not isinstance(part["logprobs"], list):
        raise ContractError()


def _validate_openai_message(item):
    _closed_keys(item, _OPENAI_MESSAGE_KEYS)
    if item.get("type") != "message" or item.get("role") != "assistant":
        raise ContractError("unsupported_provider_event")
    content = item.get("content", [])
    if not isinstance(content, list):
        raise ContractError()
    for part in content:
        _validate_openai_text_part(part)


def _validate_openai_response(response):
    _closed_keys(response, _OPENAI_RESPONSE_KEYS)
    if "tools" in response:
        if not isinstance(response["tools"], list):
            raise ContractError()
        if response["tools"]:
            raise ContractError("unsupported_provider_event")
    if "tool_choice" in response:
        choice = response["tool_choice"]
        if not isinstance(choice, str) or choice not in ("auto", "none"):
            raise ContractError("unsupported_provider_event")
    if ("parallel_tool_calls" in response and
            not isinstance(response["parallel_tool_calls"], bool)):
        raise ContractError()
    if "output" in response:
        output = response["output"]
        if not isinstance(output, list):
            raise ContractError()
        for item in output:
            _validate_openai_message(item)
    if "error" in response and response["error"] is not None:
        error = response["error"]
        _closed_keys(error, {"code", "message", "param", "type"})
        for field in ("code", "message", "param", "type"):
            if field in error and error[field] is not None:
                _strict_utf8_string(error[field])
    return response


def _validate_openai_lifecycle(kind, response):
    response = _validate_openai_response(response)
    expected_statuses = _OPENAI_LIFECYCLE_STATUSES.get(kind)
    if expected_statuses is None or response.get("status") not in expected_statuses:
        raise ContractError()
    if response.get("error") is not None and kind != "response.failed":
        raise ContractError()
    incomplete = response.get("incomplete_details")
    if incomplete is not None:
        if kind != "response.incomplete" or not isinstance(incomplete, dict):
            raise ContractError()
        if set(incomplete) != {"reason"}:
            raise ContractError()
        _strict_utf8_string(incomplete["reason"])
    return response


def _target_language_valid(value: str) -> bool:
    return (1 <= len(value) <= 64 and all(
        character.isalpha() or character in " -" for character in value
    ) and any(character.isalpha() for character in value))


def _normalize_ollama_endpoint(value):
    if not isinstance(value, str) or "\x00" in value:
        raise ContractError("endpoint_rejected")
    match = _OLLAMA_ENDPOINT.fullmatch(value)
    if match is None:
        raise ContractError("endpoint_rejected")
    port = int(match.group("port"))
    if not 1 <= port <= 65_535:
        raise ContractError("endpoint_rejected")
    return f"http://{match.group('host')}:{port}/api/chat"


def parse_request(raw: bytes) -> dict[str, object]:
    """Decode and strictly validate one JSON request frame (without newline)."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_REQUEST_BYTES or b"\x00" in raw:
        raise ContractError("invalid_request")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except (UnicodeDecodeError, ValueError, RecursionError, ContractError):
        raise ContractError("invalid_request") from None
    if not isinstance(value, dict) or set(value) != _REQUEST_KEYS:
        raise ContractError("invalid_request")
    if not _plain_int(value["schemaVersion"]) or value["schemaVersion"] != SCHEMA_VERSION:
        raise ContractError("invalid_request")
    if not isinstance(value["requestId"], str) or not _REQUEST_ID.fullmatch(value["requestId"]):
        raise ContractError("invalid_request")
    if value["provider"] not in ("ollama_local", "openai_api"):
        raise ContractError("invalid_request")
    if value["task"] not in ("rewrite", "summarize", "translate"):
        raise ContractError("invalid_request")
    for field in ("requestId", "provider", "task", "text", "model"):
        if not isinstance(value[field], str) or "\x00" in value[field]:
            raise ContractError("invalid_request")
    if not _MODEL.fullmatch(value["model"]):
        raise ContractError("invalid_request")
    if not (1 <= len(value["text"]) <= MAX_TEXT_CHARS):
        raise ContractError("invalid_request")
    try:
        text_bytes = value["text"].encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ContractError("invalid_request") from None
    if len(text_bytes) > MAX_TEXT_BYTES:
        raise ContractError("invalid_request")
    target = value["targetLanguage"]
    if value["task"] == "translate":
        if not isinstance(target, str) or "\x00" in target or not _target_language_valid(target):
            raise ContractError("invalid_request")
    elif target is not None:
        raise ContractError("invalid_request")
    if not _plain_int(value["credentialBytes"]):
        raise ContractError("invalid_request")
    result = dict(value)
    if value["provider"] == "ollama_local":
        if value["credentialBytes"] != 0:
            raise ContractError("invalid_request")
        result["endpoint"] = _normalize_ollama_endpoint(value["endpoint"])
    else:
        if value["endpoint"] is not None or not 20 <= value["credentialBytes"] <= 512:
            raise ContractError("invalid_request")
    return result


def parse_input(raw: bytes):
    """Validate the complete request-line + raw-credential framing."""
    if not isinstance(raw, bytes):
        raise ContractError("invalid_request")
    newline = raw.find(b"\n")
    if newline < 0 or newline > MAX_REQUEST_BYTES:
        raise ContractError("invalid_request")
    frame = raw[:newline]
    if frame.endswith(b"\r"):
        frame = frame[:-1]
    request = parse_request(frame)
    credential = raw[newline + 1:]
    if len(credential) != request["credentialBytes"]:
        raise ContractError("invalid_request")
    return request, bytearray(credential)


def _validated_copy(request):
    if not isinstance(request, dict):
        raise ContractError("invalid_request")
    try:
        raw = json.dumps(
            request, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ContractError("invalid_request") from None
    return parse_request(raw)


def _instruction(request):
    if request["task"] == "translate":
        return (f"Translate the user's text into {request['targetLanguage']}. "
                "Return only the translation.")
    return _SYSTEM_INSTRUCTIONS[request["task"]]


def build_request(request: dict[str, object]) -> dict[str, object]:
    """Build a closed provider URL and JSON body; credentials are never accepted."""
    request = _validated_copy(request)
    instruction = _instruction(request)
    if request["provider"] == "ollama_local":
        return {
            "url": request["endpoint"],
            "body": {
                "model": request["model"],
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": request["text"]},
                ],
                "stream": True,
                "options": {"num_predict": MAX_TOKENS},
            },
        }
    return {
        "url": OPENAI_URL,
        "body": {
            "model": request["model"],
            "instructions": instruction,
            "input": request["text"],
            "stream": True,
            "store": False,
            "tools": [],
            "max_output_tokens": MAX_TOKENS,
        },
    }


class EventStream:
    """Create exact, sequenced, bounded internal events."""

    def __init__(self, request):
        self.request = _validated_copy(request)
        self.sequence = 0
        self.event_count = 0
        self.output_bytes = 0
        self.started_emitted = False
        self.terminal = False

    def _emit(self, kind, fields=None, *, terminal=False, output_bytes=0):
        if self.terminal:
            raise ContractError()
        event_limit = MAX_EVENTS if terminal else MAX_EVENTS - 1
        if self.event_count >= event_limit:
            raise ContractError("response_limit")
        if self.output_bytes + output_bytes > MAX_OUTPUT_BYTES:
            raise ContractError("response_limit")
        event = {
            "schemaVersion": SCHEMA_VERSION,
            "requestId": self.request["requestId"],
            "sequence": self.sequence,
            "type": kind,
        }
        if fields:
            event.update(fields)
        _encode_event_line(event)
        self.sequence += 1
        self.event_count += 1
        self.output_bytes += output_bytes
        if terminal:
            self.terminal = True
        return event

    def _snapshot(self):
        return (
            self.sequence, self.event_count, self.output_bytes,
            self.started_emitted, self.terminal,
        )

    def _restore(self, snapshot):
        (self.sequence, self.event_count, self.output_bytes,
         self.started_emitted, self.terminal) = snapshot

    def started(self):
        if self.started_emitted:
            raise ContractError()
        event = self._emit("started", {
            "provider": self.request["provider"],
            "destination": (self.request["endpoint"] if self.request["provider"] == "ollama_local"
                            else OPENAI_URL),
            "model": self.request["model"],
        })
        self.started_emitted = True
        return event

    def _require_started(self):
        if not self.started_emitted:
            raise ContractError()

    def delta(self, text):
        self._require_started()
        if not isinstance(text, str) or not text:
            raise ContractError()
        try:
            encoded = text.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise ContractError() from None
        if len(encoded) > MAX_DELTA_BYTES:
            raise ContractError("response_limit")
        return self._emit("delta", {"text": text}, output_bytes=len(encoded))

    def completed(self, reason, usage):
        self._require_started()
        if not isinstance(reason, str) or reason not in _FINISH_REASONS:
            raise ContractError()
        closed_usage = _closed_usage(usage)
        return self._emit("completed", {
            "finishReason": reason,
            "usage": closed_usage,
            "cost": _unknown_cost(),
        }, terminal=True)

    def failed(self, code, retryable=False):
        self._require_started()
        if (not isinstance(code, str) or code not in _FAILURE_CODES or
                not isinstance(retryable, bool)):
            raise ContractError()
        return self._emit(
            "failed", {"code": code, "retryable": retryable}, terminal=True
        )

    def cancelled(self):
        self._require_started()
        return self._emit("cancelled", terminal=True)


class _BoundedParser:
    def __init__(self, request):
        self.events = EventStream(request)
        self.buffer = bytearray()
        self.stream_bytes = 0
        self.provider_events = 0

    def start(self):
        return [self.events.started()]

    def _require_started(self):
        if not self.events.started_emitted:
            raise ContractError()

    def _snapshot_extra(self):
        return None

    def _restore_extra(self, snapshot):
        if snapshot is not None:
            raise AssertionError("unexpected parser snapshot")

    def _snapshot(self):
        return (
            bytes(self.buffer), self.stream_bytes, self.provider_events,
            self.events._snapshot(), self._snapshot_extra(),
        )

    def _restore(self, snapshot):
        buffer, self.stream_bytes, self.provider_events, events, extra = snapshot
        self.buffer = bytearray(buffer)
        self.events._restore(events)
        self._restore_extra(extra)

    def _transactional_feed(self, chunk, drain):
        """Publish only on return; an exception restores the pre-call state."""
        self._require_started()
        snapshot = self._snapshot()
        try:
            self._add(chunk)
            return drain()
        except Exception:
            self._restore(snapshot)
            raise

    def _add(self, chunk):
        if not isinstance(chunk, bytes):
            raise ContractError()
        self.stream_bytes += len(chunk)
        if self.stream_bytes > MAX_PROVIDER_STREAM_BYTES:
            raise ContractError("response_limit")
        self.buffer.extend(chunk)

    def _count_record(self, size):
        if size > MAX_PROVIDER_RECORD_BYTES:
            raise ContractError("response_limit")
        self.provider_events += 1
        if self.provider_events > MAX_EVENTS:
            raise ContractError("response_limit")

    def _text_events(self, text):
        if not isinstance(text, str):
            raise ContractError()
        result = []
        pending = ""
        pending_bytes = 0
        for character in text:
            try:
                size = len(character.encode("utf-8", errors="strict"))
            except UnicodeEncodeError:
                raise ContractError() from None
            if pending and pending_bytes + size > MAX_DELTA_BYTES:
                result.append(self.events.delta(pending))
                pending = ""
                pending_bytes = 0
            pending += character
            pending_bytes += size
        if pending:
            result.append(self.events.delta(pending))
        return result


class OllamaNDJSONParser(_BoundedParser):
    def feed(self, chunk):
        return self._transactional_feed(chunk, self._drain)

    def _drain(self):
        output = []
        while True:
            newline = self.buffer.find(b"\n")
            if newline < 0:
                if len(self.buffer) > MAX_PROVIDER_RECORD_BYTES:
                    raise ContractError("response_limit")
                break
            raw = bytes(self.buffer[:newline])
            del self.buffer[:newline + 1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
            if not raw:
                raise ContractError()
            self._count_record(len(raw))
            try:
                record = json.loads(raw.decode("utf-8", errors="strict"),
                                    object_pairs_hook=_reject_duplicate_pairs)
            except (UnicodeDecodeError, ValueError, ContractError):
                raise ContractError() from None
            output.extend(self._consume(record))
        return output

    def _consume(self, record):
        if self.events.terminal or not isinstance(record, dict):
            raise ContractError()
        _validate_external_scalars(record)
        if _has_capability_output(record, ollama=True):
            raise ContractError("unsupported_provider_event")
        if "error" in record:
            if set(record) != {"error"}:
                raise ContractError()
            _strict_utf8_string(record["error"])
            return [self.events.failed("provider_failed")]
        _closed_keys(record, _OLLAMA_RECORD_KEYS)
        if not isinstance(record.get("done"), bool):
            raise ContractError()
        for field in (
                "total_duration", "load_duration", "prompt_eval_count",
                "prompt_eval_duration", "eval_count", "eval_duration"):
            if field in record:
                _bounded_count(record[field])
        for field in ("model", "created_at", "done_reason"):
            if field in record:
                _strict_utf8_string(record[field])
        message = record.get("message")
        output = []
        if message is not None:
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise ContractError()
            if set(message) != {"role", "content"}:
                raise ContractError("unsupported_provider_event")
            content = message.get("content")
            if not isinstance(content, str):
                raise ContractError()
            output.extend(self._text_events(content))
        if record["done"]:
            present = ("prompt_eval_count" in record, "eval_count" in record)
            if any(present) and not all(present):
                usage = None
            elif all(present):
                usage = _reported_usage(record["prompt_eval_count"], record["eval_count"])
            else:
                usage = None
            raw_reason = record.get("done_reason", "completed")
            if not isinstance(raw_reason, str):
                raise ContractError()
            reason = raw_reason if raw_reason in _OLLAMA_FINISH_REASONS else "completed"
            output.append(self.events.completed(reason, usage))
        return output

    def finish(self):
        self._require_started()
        if self.buffer or not self.events.terminal:
            raise ContractError()
        return []


_IGNORED_OPENAI_EVENTS = frozenset({
    "response.in_progress", "response.output_item.added", "response.output_item.done",
    "response.content_part.added", "response.content_part.done", "response.output_text.done",
})


class OpenAISSEParser(_BoundedParser):
    def __init__(self, request):
        super().__init__(request)
        self.created = False

    def _snapshot_extra(self):
        return self.created

    def _restore_extra(self, snapshot):
        self.created = snapshot

    def feed(self, chunk):
        return self._transactional_feed(chunk, self._drain)

    def _drain(self):
        output = []
        while True:
            lf = self.buffer.find(b"\n\n")
            crlf = self.buffer.find(b"\r\n\r\n")
            positions = [(lf, 2), (crlf, 4)]
            positions = [item for item in positions if item[0] >= 0]
            if not positions:
                if len(self.buffer) > MAX_PROVIDER_RECORD_BYTES:
                    raise ContractError("response_limit")
                break
            position, separator = min(positions)
            raw = bytes(self.buffer[:position])
            del self.buffer[:position + separator]
            self._count_record(len(raw))
            output.extend(self._consume_block(raw))
        return output

    def _consume_block(self, raw):
        try:
            block = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise ContractError() from None
        event_name = None
        data_lines = []
        for line in block.replace("\r\n", "\n").split("\n"):
            if line.startswith(":"):
                continue
            if line.startswith("event: ") and event_name is None:
                event_name = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])
            else:
                raise ContractError()
        if event_name is None or len(data_lines) != 1:
            raise ContractError()
        try:
            record = json.loads(data_lines[0], object_pairs_hook=_reject_duplicate_pairs)
        except (ValueError, ContractError):
            raise ContractError() from None
        if not isinstance(record, dict) or record.get("type") != event_name:
            raise ContractError()
        return self._consume(event_name, record)

    def _consume(self, kind, record):
        if self.events.terminal:
            raise ContractError()
        _validate_external_scalars(record)
        _validate_openai_event_scalars(record)
        if _has_capability_output(record):
            raise ContractError("unsupported_provider_event")
        if kind == "error":
            if set(record) != {"type", "code", "message", "param", "sequence_number"}:
                raise ContractError()
            if record["code"] is not None and not isinstance(record["code"], str):
                raise ContractError()
            if not isinstance(record["message"], str):
                raise ContractError()
            if record["param"] is not None and not isinstance(record["param"], str):
                raise ContractError()
            for field in ("code", "message", "param"):
                if record[field] is not None:
                    try:
                        record[field].encode("utf-8", errors="strict")
                    except UnicodeEncodeError:
                        raise ContractError() from None
            _bounded_count(record["sequence_number"])
            return [self.events.failed("provider_failed")]
        if kind == "response.created":
            _closed_keys(record, _OPENAI_LIFECYCLE_EVENT_KEYS)
            response = _validate_openai_lifecycle(kind, record.get("response"))
            if self.created:
                raise ContractError()
            self.created = True
            return []
        if not self.created:
            raise ContractError()
        if ("tool" in kind or "function_call" in kind or
                ("output" in kind and "output_text" not in kind and kind not in _IGNORED_OPENAI_EVENTS)):
            raise ContractError("unsupported_provider_event")
        if kind == "response.output_text.delta":
            _closed_keys(record, _OPENAI_DELTA_EVENT_KEYS)
            return self._text_events(record.get("delta"))
        if kind == "response.completed":
            _closed_keys(record, _OPENAI_LIFECYCLE_EVENT_KEYS)
            response = _validate_openai_lifecycle(kind, record.get("response"))
            usage_record = response.get("usage")
            usage = None
            if usage_record is not None:
                if not isinstance(usage_record, dict):
                    raise ContractError()
                usage = _reported_usage(
                    usage_record.get("input_tokens"), usage_record.get("output_tokens"),
                    usage_record.get("total_tokens"),
                )
            return [self.events.completed("completed", usage)]
        if kind == "response.incomplete":
            _closed_keys(record, _OPENAI_LIFECYCLE_EVENT_KEYS)
            _validate_openai_lifecycle(kind, record.get("response"))
            return [self.events.completed("incomplete", None)]
        if kind == "response.failed":
            _closed_keys(record, _OPENAI_LIFECYCLE_EVENT_KEYS)
            _validate_openai_lifecycle(kind, record.get("response"))
            return [self.events.failed("provider_failed")]
        if kind in _IGNORED_OPENAI_EVENTS and self._compatible_ignored(kind, record):
            return []
        raise ContractError("unsupported_provider_event")

    @staticmethod
    def _compatible_ignored(kind, record):
        if kind == "response.in_progress":
            _closed_keys(record, _OPENAI_LIFECYCLE_EVENT_KEYS)
            _validate_openai_lifecycle(kind, record.get("response"))
            return True
        if kind.startswith("response.output_item."):
            _closed_keys(record, _OPENAI_OUTPUT_ITEM_EVENT_KEYS)
            item = record.get("item")
            _validate_openai_message(item)
            return True
        if kind.startswith("response.content_part."):
            _closed_keys(record, _OPENAI_CONTENT_PART_EVENT_KEYS)
            part = record.get("part")
            _validate_openai_text_part(part)
            return True
        if kind == "response.output_text.done":
            _closed_keys(record, _OPENAI_OUTPUT_TEXT_DONE_KEYS)
            _strict_utf8_string(record.get("text"))
            return True
        return False

    def finish(self):
        self._require_started()
        if self.buffer or not self.events.terminal:
            raise ContractError()
        return []


def map_http_status(status):
    if not _plain_int(status):
        raise ContractError()
    if status == 401:
        return "authentication_failed", False
    if status == 403:
        return "permission_denied", False
    if status == 404:
        return "model_unavailable", False
    if status == 408:
        return "operation_timeout", True
    if status == 429:
        return "rate_limited", True
    if 500 <= status <= 599:
        return "provider_unavailable", True
    return "provider_failed", False


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "type": "failed",
        "code": "unsupported_transport",
        "retryable": False,
    }
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
