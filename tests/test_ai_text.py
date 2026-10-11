"""Offline behavioral tests for the private AI text contract."""

from __future__ import annotations

import importlib.util
import ast
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "ai_text.py"


def load_target():
    spec = importlib.util.spec_from_file_location("orla_ai_text_test_target", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("helper could not be loaded")
    target = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = target
    spec.loader.exec_module(target)
    return target


class AiTextContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = load_target()

    def request(self, **changes):
        value = {
            "schemaVersion": 1,
            "requestId": "txt-fixture.1",
            "provider": "ollama_local",
            "task": "rewrite",
            "targetLanguage": None,
            "text": "Revise this sentence.",
            "model": "gemma3:4b",
            "endpoint": "http://127.0.0.1:11434",
            "credentialBytes": 0,
        }
        value.update(changes)
        return value

    def encoded(self, **changes):
        return json.dumps(self.request(**changes), ensure_ascii=False).encode("utf-8")

    def assert_rejected(self, raw, code="invalid_request"):
        with self.assertRaises(self.target.ContractError) as caught:
            self.target.parse_request(raw)
        self.assertEqual(caught.exception.code, code)

    def test_closed_request_validation_normalizes_only_the_owned_route(self):
        request = self.target.parse_request(self.encoded(endpoint="http://[::1]:9911/"))
        self.assertEqual(request["endpoint"], "http://[::1]:9911/api/chat")

        unknown = self.request()
        unknown["extra"] = "surprise"
        invalid = [
            json.dumps(unknown).encode(),
            b'{"schemaVersion":1,"schemaVersion":1}',
            self.encoded(schemaVersion=1.0),
            self.encoded(text=""),
            self.encoded(text="x" * 16385),
            self.encoded(model="../model"),
            self.encoded(requestId="-bad"),
            self.encoded(credentialBytes=True),
            self.encoded(text="nul\x00byte"),
            json.dumps(self.request(text="\ud800")).encode(),
            b"\xff",
        ]
        for raw in invalid:
            with self.subTest(raw=raw[:80]):
                self.assert_rejected(raw)
        for raw in (
            self.encoded(endpoint="http://localhost:11434"),
            self.encoded(endpoint="http://127.0.0.1:11434/other"),
            self.encoded(endpoint="http://127.0.0.1:11434?x=1"),
        ):
            self.assert_rejected(raw, "endpoint_rejected")

    def test_cross_field_rules_keep_translation_and_credentials_explicit(self):
        valid = self.target.parse_request(self.encoded(
            provider="openai_api", task="translate", targetLanguage="Portuguese-Brazil",
            endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        self.assertIsNone(valid["endpoint"])

        for changes in (
            {"task": "translate", "targetLanguage": None},
            {"task": "rewrite", "targetLanguage": "Portuguese"},
            {"provider": "ollama_local", "credentialBytes": 20},
            {"provider": "openai_api", "endpoint": "https://api.openai.com", "credentialBytes": 32},
            {"provider": "openai_api", "endpoint": None, "credentialBytes": 19},
            {"provider": "openai_api", "endpoint": None, "credentialBytes": 513},
        ):
            with self.subTest(changes=changes):
                self.assert_rejected(self.encoded(**changes))

    def test_two_frame_input_accepts_exact_secret_length_and_rejects_trailing_bytes(self):
        marker = b"synthetic-secret-marker-123456"
        frame = self.encoded(provider="openai_api", endpoint=None,
                             credentialBytes=len(marker), model="gpt-5-mini")
        request, credential = self.target.parse_input(frame + b"\n" + marker)
        self.assertEqual(request["requestId"], "txt-fixture.1")
        self.assertEqual(credential, bytearray(marker))
        self.assertNotIn(marker.decode(), json.dumps(request))

        for wire in (frame + marker, frame + b"\n" + marker[:-1],
                     frame + b"\n" + marker + b"x", b"x" * (96 * 1024 + 1)):
            with self.subTest(length=len(wire)):
                with self.assertRaises(self.target.ContractError):
                    self.target.parse_input(wire)

    def test_builders_are_closed_bounded_and_contain_no_secret_slot(self):
        local = self.target.parse_request(self.encoded(task="summarize"))
        local_build = self.target.build_request(local)
        self.assertEqual(local_build["url"], "http://127.0.0.1:11434/api/chat")
        self.assertEqual(local_build["body"]["options"], {"num_predict": 1024})
        self.assertEqual([item["role"] for item in local_build["body"]["messages"]],
                         ["system", "user"])
        self.assertNotIn("tools", local_build["body"])

        remote = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=40, model="gpt-5-mini"))
        remote_build = self.target.build_request(remote)
        self.assertEqual(remote_build["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(remote_build["body"]["max_output_tokens"], 1024)
        self.assertEqual(remote_build["body"]["tools"], [])
        self.assertFalse(remote_build["body"]["store"])
        self.assertTrue(remote_build["body"]["stream"])
        serialized = json.dumps(remote_build)
        self.assertNotIn("credential", serialized.lower())
        self.assertNotIn("authorization", serialized.lower())

        local["text"] = "mutated after build"
        local["model"] = "mutated"
        local["endpoint"] = "http://127.0.0.1:1/api/chat"
        self.assertEqual(local_build["body"]["messages"][1]["content"],
                         "Revise this sentence.")
        self.assertEqual(local_build["body"]["model"], "gemma3:4b")
        self.assertEqual(local_build["url"], "http://127.0.0.1:11434/api/chat")

        unsafe = self.request(endpoint="http://attacker.example:11434")
        with self.assertRaises(self.target.ContractError) as caught:
            self.target.build_request(unsafe)
        self.assertEqual(caught.exception.code, "endpoint_rejected")

    def test_ollama_parser_handles_fragmented_utf8_and_reports_only_provider_usage(self):
        request = self.target.parse_request(self.encoded())
        parser = self.target.OllamaNDJSONParser(request)
        records = [
            {"message": {"role": "assistant", "content": "olá 🙂"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True,
             "done_reason": "stop", "prompt_eval_count": 7, "eval_count": 3},
        ]
        wire = b"".join(
            json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n"
            for record in records
        )
        events = parser.start()
        for byte in wire:
            events.extend(parser.feed(bytes([byte])))
        events.extend(parser.finish())
        self.assertEqual([event["type"] for event in events],
                         ["started", "delta", "completed"])
        self.assertEqual(events[1]["text"], "olá 🙂")
        self.assertEqual(events[2]["usage"], {
            "status": "reported", "inputTokens": 7, "outputTokens": 3, "totalTokens": 10,
        })
        self.assertEqual(events[2]["cost"], {
            "status": "unknown", "currency": None, "amount": None,
        })

    def test_ollama_parser_rejects_role_order_terminal_and_limits(self):
        request = self.target.parse_request(self.encoded())
        bad_streams = [
            b'{"message":{"role":"user","content":"x"},"done":false}\n',
            b'{"message":{"role":"assistant","content":"","tool_calls":[]},"done":false}\n',
            b'{"message":{"role":"assistant","content":"x"},"done":true}\n'
            b'{"message":{"role":"assistant","content":"y"},"done":false}\n',
            b'{"message":{"role":"assistant","content":"x"},"done":false}',
            b'{' + b' ' * (64 * 1024) + b'}\n',
            b'\xff\n',
            b'{"message":{"role":"assistant","content":"\\ud800"},"done":false}\n',
        ]
        for wire in bad_streams:
            with self.subTest(wire=wire[:60]):
                parser = self.target.OllamaNDJSONParser(request)
                with self.assertRaises(self.target.ContractError):
                    parser.start()
                    parser.feed(wire)
                    parser.finish()

        not_started = self.target.OllamaNDJSONParser(request)
        with self.assertRaises(self.target.ContractError):
            not_started.feed(b'{"done":false}\n')

        event_overflow = self.target.OllamaNDJSONParser(request)
        event_overflow.start()
        with self.assertRaises(self.target.ContractError) as caught:
            event_overflow.feed(b'{"done":false}\n' * 4097)
        self.assertEqual(caught.exception.code, "response_limit")

    def test_ollama_feed_is_transactional_and_preserves_prior_published_delta(self):
        request = self.target.parse_request(self.encoded())
        mixed = (
            b'{"message":{"role":"assistant","content":"kept"},"done":false}\n'
            b'{"message":{"role":"user","content":"bad"},"done":false}\n'
        )
        parser = self.target.OllamaNDJSONParser(request)
        parser.start()
        with self.assertRaises(self.target.ContractError):
            parser.feed(mixed)
        failed = parser.events.failed("protocol_invalid")
        self.assertEqual(failed["sequence"], 1)
        self.assertEqual(parser.events.output_bytes, 0)

        parser = self.target.OllamaNDJSONParser(request)
        parser.start()
        published = parser.feed(mixed.splitlines(keepends=True)[0])
        self.assertEqual([(event["sequence"], event["text"]) for event in published],
                         [(1, "kept")])
        with self.assertRaises(self.target.ContractError):
            parser.feed(mixed.splitlines(keepends=True)[1])
        failed = parser.events.failed("protocol_invalid")
        self.assertEqual(failed["sequence"], 2)
        self.assertEqual(parser.events.output_bytes, 4)

        stream_overflow = self.target.OllamaNDJSONParser(request)
        stream_overflow.start()
        with self.assertRaises(self.target.ContractError) as caught:
            stream_overflow.feed(b"x" * (512 * 1024 + 1))
        self.assertEqual(caught.exception.code, "response_limit")

    def test_ollama_terminal_reason_is_closed_and_partial_usage_is_unknown(self):
        request = self.target.parse_request(self.encoded())
        parser = self.target.OllamaNDJSONParser(request)
        wire = (b'{"message":{"role":"assistant","content":"ok"},"done":true,'
                b'"done_reason":"private provider detail","prompt_eval_count":9}\n')
        events = parser.start() + parser.feed(wire) + parser.finish()
        self.assertEqual(events[-1]["finishReason"], "completed")
        self.assertEqual(events[-1]["usage"]["status"], "unknown")
        self.assertNotIn("private provider detail", json.dumps(events))

    def test_ollama_closed_shapes_reject_non_text_and_sanitize_error_only(self):
        request = self.target.parse_request(self.encoded())
        invalid = [
            {"done": False, "message": {
                "role": "assistant", "content": "text", "images": ["synthetic"],
            }},
            {"done": False, "message": {
                "role": "assistant", "content": "text",
            }, "error": "synthetic-secret-marker"},
            {"done": False, "message": {
                "role": "assistant", "content": "text",
            }, "unknown": "synthetic"},
            {"done": False, "model": "\ud800", "message": {
                "role": "assistant", "content": "text",
            }},
            {"done": False, "eval_duration": True, "message": {
                "role": "assistant", "content": "text",
            }},
        ]
        for record in invalid:
            with self.subTest(keys=sorted(record)):
                parser = self.target.OllamaNDJSONParser(request)
                parser.start()
                with self.assertRaises(self.target.ContractError):
                    parser.feed(json.dumps(record).encode() + b"\n")
                failure = parser.events.failed("protocol_invalid")
                self.assertEqual(failure["sequence"], 1)

        parser = self.target.OllamaNDJSONParser(request)
        events = parser.start() + parser.feed(
            b'{"error":"synthetic-secret-marker"}\n') + parser.finish()
        self.assertEqual([event["type"] for event in events], ["started", "failed"])
        self.assertEqual(events[-1]["code"], "provider_failed")
        self.assertNotIn("synthetic-secret-marker", json.dumps(events))

    def test_openai_sse_orders_events_and_sanitizes_terminal_data(self):
        request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        parser = self.target.OpenAISSEParser(request)
        wire = (
            'event: response.created\ndata: {"type":"response.created","response":{"status":"in_progress"}}\n\n'
            'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"Olá 🙂"}\n\n'
            'event: response.completed\ndata: {"type":"response.completed","response":{"status":"completed",'
            '"usage":{"input_tokens":5,"output_tokens":2,"total_tokens":7}}}\n\n'
        ).encode()
        split = wire.index("🙂".encode()) + 1
        events = (parser.start() + parser.feed(wire[:split]) + parser.feed(wire[split:]) +
                  parser.finish())
        self.assertEqual([event["type"] for event in events],
                         ["started", "delta", "completed"])
        self.assertEqual(events[1]["text"], "Olá 🙂")
        self.assertEqual(events[2]["finishReason"], "completed")
        self.assertEqual(events[2]["usage"]["status"], "reported")
        self.assertFalse(any("response" in event for event in events))

    def test_openai_sse_rejects_tool_events_bad_status_and_post_terminal_bytes(self):
        request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        bad_streams = [
            b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"x"}\n\n',
            b'event: response.created\ndata: {"type":"response.created","response":{"status":"in_progress"}}\n\n'
            b'event: response.function_call_arguments.delta\ndata: {"type":"response.function_call_arguments.delta"}\n\n',
            b'event: response.created\ndata: {"type":"response.created","response":{"status":"in_progress"}}\n\n'
            b'event: response.output_item.added\ndata: {"type":"response.output_item.added","item":{"type":"function_call"}}\n\n',
            b'event: response.created\ndata: {"type":"response.created","response":{"status":"in_progress"}}\n\n'
            b'event: response.output_item.done\ndata: {"type":"response.output_item.done","item":{"type":"message","role":"assistant","content":[{"type":"refusal","refusal":"private"}]}}\n\n',
            b'event: response.created\ndata: {"type":"response.created","response":{"status":"in_progress"}}\n\n'
            b'event: response.failed\ndata: {"type":"response.failed","response":{"status":"completed"}}\n\n',
            b'event: response.created\ndata: {"type":"response.created","response":{"status":"in_progress"}}\n\n'
            b'event: response.completed\ndata: {"type":"response.completed","response":{"status":"completed"}}\n\n'
            b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"late"}\n\n',
            b'event: response.created\ndata: \xff\n\n',
            b'event: response.created\ndata: {"type":"response.created","response":{"status":"in_progress"}}\n\n'
            b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"\\ud800"}\n\n',
        ]
        for wire in bad_streams:
            with self.subTest(wire=wire[:80]):
                parser = self.target.OpenAISSEParser(request)
                with self.assertRaises(self.target.ContractError):
                    parser.start()
                    parser.feed(wire)
                    parser.finish()

    def test_openai_feed_is_transactional_for_multiple_sse_records(self):
        request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        parser = self.target.OpenAISSEParser(request)
        parser.start()
        mixed = (
            b'event: response.created\ndata: {"type":"response.created",'
            b'"response":{"status":"in_progress"}}\n\n'
            b'event: response.output_text.delta\ndata: '
            b'{"type":"response.output_text.delta","delta":"kept"}\n\n'
            b'event: response.output_text.delta\ndata: '
            b'{"type":"response.output_text.delta","delta":123}\n\n'
        )
        with self.assertRaises(self.target.ContractError):
            parser.feed(mixed)
        failed = parser.events.failed("protocol_invalid")
        self.assertEqual(failed["sequence"], 1)
        self.assertEqual(parser.events.output_bytes, 0)
        self.assertFalse(parser.created)

    def test_capability_fields_are_rejected_at_nested_and_top_levels(self):
        local = self.target.OllamaNDJSONParser(
            self.target.parse_request(self.encoded()))
        local.start()
        with self.assertRaises(self.target.ContractError) as caught:
            local.feed(
                b'{"done":false,"message":{"role":"assistant","content":"x"},'
                b'"tool_calls":[{"name":"unexpected"}]}\n')
        self.assertEqual(caught.exception.code, "unsupported_provider_event")

        remote_request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        remote = self.target.OpenAISSEParser(remote_request)
        remote.start()
        self.assertEqual(remote.feed(
            b'event: response.created\ndata: {"type":"response.created",'
            b'"response":{"status":"in_progress","tools":[],"tool_choice":"auto",'
            b'"parallel_tool_calls":true}}\n\n'), [])
        with self.assertRaises(self.target.ContractError) as caught:
            remote.feed(
                b'event: response.output_item.added\ndata: '
                b'{"type":"response.output_item.added","item":{"type":"message",'
                b'"role":"assistant","content":[],"tool_calls":[]}}\n\n')
        self.assertEqual(caught.exception.code, "unsupported_provider_event")

    def test_documented_openai_error_before_created_is_sanitized(self):
        request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        parser = self.target.OpenAISSEParser(request)
        events = parser.start() + parser.feed(
            b'event: error\ndata: {"type":"error","code":"private",'
            b'"message":"synthetic-secret-marker","param":null,"sequence_number":1}\n\n')
        self.assertEqual([event["type"] for event in events], ["started", "failed"])
        self.assertEqual(events[-1]["code"], "provider_failed")
        self.assertEqual(events[-1]["sequence"], 1)
        self.assertNotIn("synthetic-secret-marker", json.dumps(events))

        invalid_records = [
            {"type": "error", "code": "x", "message": "x", "param": None},
            {"type": "error", "code": 7, "message": "x", "param": None,
             "sequence_number": 1},
            {"type": "error", "code": None, "message": "\ud800", "param": None,
             "sequence_number": 1},
            {"type": "error", "code": None, "message": "x", "param": None,
             "sequence_number": True},
        ]
        for record in invalid_records:
            with self.subTest(record=record):
                parser = self.target.OpenAISSEParser(request)
                parser.start()
                wire = ("event: error\ndata: " + json.dumps(record) + "\n\n").encode()
                with self.assertRaises(self.target.ContractError):
                    parser.feed(wire)
                failure = parser.events.failed("protocol_invalid")
                self.assertEqual(failure["sequence"], 1)

    def test_openai_event_shapes_reject_enabled_tools_refusal_and_shell_call(self):
        request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        cases = [
            (False, "response.created", {
                "type": "response.created", "response": {
                    "status": "in_progress",
                    "tools": [{"type": "function", "name": "unexpected"}],
                    "tool_choice": {"type": "function", "name": "unexpected"},
                    "parallel_tool_calls": True,
                },
            }),
            (True, "response.completed", {
                "type": "response.completed", "response": {
                    "status": "completed", "output": [{
                        "type": "message", "role": "assistant", "content": [{
                            "type": "refusal", "refusal": "private refusal",
                        }],
                    }],
                },
            }),
            (True, "response.output_text.delta", {
                "type": "response.output_text.delta", "delta": "text",
                "shell_call": {"command": "synthetic"},
            }),
            (True, "response.output_text.delta", {
                "type": "response.output_text.delta", "delta": "text",
                "sequence_number": True,
            }),
            (True, "response.output_text.delta", {
                "type": "response.output_text.delta", "delta": "text",
                "item_id": "\ud800",
            }),
        ]
        for needs_created, kind, record in cases:
            with self.subTest(kind=kind):
                parser = self.target.OpenAISSEParser(request)
                parser.start()
                if needs_created:
                    parser.feed(
                        b'event: response.created\ndata: {"type":"response.created",'
                        b'"response":{"status":"in_progress","tools":[]}}\n\n')
                wire = (f"event: {kind}\ndata: " + json.dumps(record) + "\n\n").encode()
                with self.assertRaises(self.target.ContractError) as caught:
                    parser.feed(wire)
                self.assertIn(caught.exception.code,
                              {"protocol_invalid", "unsupported_provider_event"})

    def test_openai_terminal_errors_are_stable_and_usage_never_estimated(self):
        request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32, model="gpt-5-mini"))
        cases = [
            ("response.incomplete", {"status": "incomplete"}, "completed", "incomplete"),
            ("response.failed", {"status": "failed", "error": {"message": "private"}},
             "failed", "provider_failed"),
        ]
        for kind, response, event_type, detail in cases:
            with self.subTest(kind=kind):
                parser = self.target.OpenAISSEParser(request)
                created = ('event: response.created\ndata: {"type":"response.created",'
                           '"response":{"status":"in_progress"}}\n\n')
                terminal = f"event: {kind}\ndata: " + json.dumps(
                    {"type": kind, "response": response}) + "\n\n"
                events = (parser.start() + parser.feed((created + terminal).encode()) +
                          parser.finish())
                self.assertEqual(events[-1]["type"], event_type)
                if event_type == "completed":
                    self.assertEqual(events[-1]["finishReason"], detail)
                    self.assertEqual(events[-1]["usage"]["status"], "unknown")
                else:
                    self.assertEqual(events[-1]["code"], detail)
                self.assertNotIn("private", json.dumps(events))

        inconsistent_usage = (
            'event: response.created\ndata: {"type":"response.created",'
            '"response":{"status":"in_progress"}}\n\n'
            'event: response.completed\ndata: {"type":"response.completed",'
            '"response":{"status":"completed","usage":{"input_tokens":2,'
            '"output_tokens":3,"total_tokens":99}}}\n\n'
        )
        with self.assertRaises(self.target.ContractError):
            parser = self.target.OpenAISSEParser(request)
            parser.start()
            parser.feed(inconsistent_usage.encode())

    def test_openai_lifecycle_cross_fields_reject_before_state_mutation(self):
        request = self.target.parse_request(self.encoded(
            provider="openai_api", endpoint=None, credentialBytes=32,
            model="gpt-5-mini"))
        invalid = [
            ("response.created", "in_progress", "error"),
            ("response.created", "in_progress", "incomplete_details"),
            ("response.in_progress", "in_progress", "error"),
            ("response.in_progress", "in_progress", "incomplete_details"),
            ("response.completed", "completed", "error"),
            ("response.completed", "completed", "incomplete_details"),
            ("response.incomplete", "incomplete", "error"),
            ("response.failed", "failed", "incomplete_details"),
        ]
        for kind, status, contradictory_field in invalid:
            with self.subTest(kind=kind, field=contradictory_field):
                parser = self.target.OpenAISSEParser(request)
                parser.start()
                if kind != "response.created":
                    parser.feed(
                        b'event: response.created\ndata: {"type":"response.created",'
                        b'"response":{"status":"in_progress",'
                        b'"error":null,"incomplete_details":null}}\n\n')
                before = parser._snapshot()
                response = {"status": status}
                if contradictory_field == "error":
                    response[contradictory_field] = {
                        "code": "synthetic", "message": "private",
                    }
                else:
                    response[contradictory_field] = {
                        "reason": "max_output_tokens",
                    }
                record = {"type": kind, "response": response}
                wire = (f"event: {kind}\ndata: " + json.dumps(record) +
                        "\n\n").encode()
                with self.assertRaises(self.target.ContractError):
                    parser.feed(wire)
                self.assertEqual(parser._snapshot(), before)
                failure = parser.events.failed("protocol_invalid")
                self.assertEqual(failure["sequence"], 1)

        accepted = [
            ("response.incomplete", {
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
            }, "completed"),
            ("response.failed", {
                "status": "failed",
                "error": {"code": "private", "message": "private"},
            }, "failed"),
        ]
        for kind, response, terminal_type in accepted:
            with self.subTest(valid_kind=kind):
                parser = self.target.OpenAISSEParser(request)
                created = (
                    'event: response.created\ndata: {"type":"response.created",'
                    '"response":{"status":"in_progress","error":null,'
                    '"incomplete_details":null}}\n\n'
                )
                terminal = (f"event: {kind}\ndata: " + json.dumps({
                    "type": kind, "response": response,
                }) + "\n\n")
                events = parser.start() + parser.feed((created + terminal).encode())
                self.assertEqual(events[-1]["type"], terminal_type)
                self.assertNotIn("private", json.dumps(events))

    def test_one_terminal_slot_is_reserved_at_the_exact_event_limit(self):
        request = self.target.parse_request(self.encoded())
        for terminal_kind in ("failed", "cancelled", "completed"):
            with self.subTest(terminal_kind=terminal_kind):
                stream = self.target.EventStream(request)
                stream.started()
                for _ in range(self.target.MAX_EVENTS - 2):
                    stream.delta("x")
                before = stream._snapshot()
                with self.assertRaises(self.target.ContractError) as caught:
                    stream.delta("x")
                self.assertEqual(caught.exception.code, "response_limit")
                self.assertEqual(stream._snapshot(), before)

                if terminal_kind == "failed":
                    terminal = stream.failed("response_limit")
                elif terminal_kind == "cancelled":
                    terminal = stream.cancelled()
                else:
                    terminal = stream.completed("completed", None)
                self.assertEqual(terminal["sequence"], self.target.MAX_EVENTS - 1)
                self.assertEqual(stream.event_count, self.target.MAX_EVENTS)
                self.assertTrue(stream.terminal)
                with self.assertRaises(self.target.ContractError):
                    stream.failed("protocol_invalid")

        parser = self.target.OllamaNDJSONParser(request)
        parser.start()
        delta_record = (
            b'{"done":false,"message":{"role":"assistant",'
            b'"content":"x"}}\n'
        )
        for _ in range(self.target.MAX_EVENTS - 2):
            parser.feed(delta_record)
        before = parser._snapshot()
        with self.assertRaises(self.target.ContractError) as caught:
            parser.feed(delta_record)
        self.assertEqual(caught.exception.code, "response_limit")
        self.assertEqual(parser._snapshot(), before)
        failed = parser.events.failed("response_limit")
        self.assertEqual(failed["sequence"], self.target.MAX_EVENTS - 1)
        self.assertEqual(parser.events.event_count, self.target.MAX_EVENTS)

    def test_internal_events_have_exact_sequence_caps_and_unknown_cost(self):
        request = self.target.parse_request(self.encoded())
        stream = self.target.EventStream(request)
        started = stream.started()
        delta = stream.delta("x" * 8192)
        completed = stream.completed("stop", None)
        self.assertEqual([started["sequence"], delta["sequence"], completed["sequence"]], [0, 1, 2])
        self.assertEqual(set(started), {"schemaVersion", "requestId", "sequence", "type",
                                       "provider", "destination", "model"})
        self.assertEqual(completed["usage"]["status"], "unknown")
        self.assertEqual(completed["cost"]["status"], "unknown")
        with self.assertRaises(self.target.ContractError):
            stream.delta("late")

        oversized = self.target.EventStream(request)
        oversized.started()
        with self.assertRaises(self.target.ContractError) as caught:
            for _ in range(33):
                oversized.delta("x" * 8192)
        self.assertEqual(caught.exception.code, "response_limit")

        cancelled_stream = self.target.EventStream(request)
        cancelled_stream.started()
        cancelled = cancelled_stream.cancelled()
        self.assertEqual(cancelled["type"], "cancelled")
        self.assertEqual(cancelled["sequence"], 1)
        with self.assertRaises(self.target.ContractError):
            cancelled_stream.completed("stop", None)

        with self.assertRaises(self.target.ContractError):
            invalid_failure = self.target.EventStream(request)
            invalid_failure.started()
            invalid_failure.failed("private provider error")
        with self.assertRaises(self.target.ContractError):
            invalid_retry = self.target.EventStream(request)
            invalid_retry.started()
            invalid_retry.failed("provider_failed", retryable=1)

        with self.assertRaises(self.target.ContractError):
            stream.started()

    def test_completed_closes_usage_reason_utf8_and_line_before_state_mutation(self):
        request = self.target.parse_request(self.encoded())
        invalid = [
            ("private provider reason", None),
            ("\ud800", None),
            (["completed"], None),
            ("completed", "synthetic-secret-marker"),
            ("completed", ["synthetic-secret-marker"]),
            ("completed", {
                "status": "unknown", "inputTokens": None, "outputTokens": None,
                "totalTokens": None, "credential": "synthetic-secret-marker",
            }),
            ("completed", {
                "status": "reported", "inputTokens": True,
                "outputTokens": 0, "totalTokens": 1,
            }),
            ("completed", {
                "status": "reported", "inputTokens": -1,
                "outputTokens": 2, "totalTokens": 1,
            }),
        ]
        for reason, usage in invalid:
            with self.subTest(reason=reason, usage_type=type(usage).__name__):
                stream = self.target.EventStream(request)
                stream.started()
                with self.assertRaises(self.target.ContractError):
                    stream.completed(reason, usage)
                failure = stream.failed("protocol_invalid")
                self.assertEqual(failure["sequence"], 1)

        reported = {
            "status": "reported", "inputTokens": 2,
            "outputTokens": 3, "totalTokens": 5,
        }
        stream = self.target.EventStream(request)
        stream.started()
        completed = stream.completed("stop", reported)
        reported["inputTokens"] = 99
        self.assertEqual(completed["usage"]["inputTokens"], 2)
        encoded = self.target._encode_event_line(completed)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertLessEqual(len(encoded), 64 * 1024)

        stream = self.target.EventStream(request)
        stream.started()
        previous_limit = self.target.MAX_EVENT_LINE_BYTES
        try:
            self.target.MAX_EVENT_LINE_BYTES = 32
            with self.assertRaises(self.target.ContractError) as caught:
                stream.completed("stop", None)
            self.assertEqual(caught.exception.code, "response_limit")
        finally:
            self.target.MAX_EVENT_LINE_BYTES = previous_limit
        failure = stream.failed("protocol_invalid")
        self.assertEqual(failure["sequence"], 1)

    def test_http_status_mapping_is_closed_and_does_not_forward_provider_text(self):
        expected = {
            401: ("authentication_failed", False), 403: ("permission_denied", False),
            404: ("model_unavailable", False), 408: ("operation_timeout", True),
            429: ("rate_limited", True), 500: ("provider_unavailable", True),
            400: ("provider_failed", False),
        }
        for status, result in expected.items():
            with self.subTest(status=status):
                self.assertEqual(self.target.map_http_status(status), result)

    def test_cli_never_runs_a_transport_or_echoes_input(self):
        marker = "synthetic-secret-marker-123456789"
        output = io.StringIO()
        errors = io.StringIO()
        previous_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(marker)
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                return_code = self.target.main(["run", marker])
        finally:
            sys.stdin = previous_stdin
        self.assertEqual(return_code, 2)
        result = json.loads(output.getvalue())
        self.assertEqual(result["code"], "unsupported_transport")
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn(marker, errors.getvalue())

    def test_helper_has_no_transport_process_sdk_or_environment_boundary(self):
        tree = ast.parse(HELPER.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertTrue(imported.isdisjoint({
            "http", "urllib", "socket", "requests", "openai", "ollama",
            "subprocess", "os", "dotenv", "httpx", "aiohttp",
        }))


if __name__ == "__main__":
    unittest.main()
