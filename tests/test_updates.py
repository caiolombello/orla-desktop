"""Offline contract tests for the explicit Orla release check."""

from __future__ import annotations

import io
from http.client import BadStatusLine, IncompleteRead
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import updates  # noqa: E402


def blocking_network_worker(connection, marker: str, timeout: float) -> None:
    Path(marker).write_text(str(os.getpid()), encoding="ascii")
    time.sleep(60)


def release(tag: str, *, prerelease: bool = False, draft: bool = False,
            url: str | None = None) -> dict[str, object]:
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": url or f"https://github.com/caiolombello/orla-desktop/releases/tag/{tag}",
    }


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout: float):
        self.calls.append((url, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def page(items, *, status: int = 200, headers=None):
    return status, headers or {}, json.dumps(items).encode("utf-8")


class UpdateCheckTests(unittest.TestCase):
    def check(self, installed="0.2.4", channel="stable", responses=None):
        transport = FakeTransport(responses or [page([])])
        result = updates.check_updates(
            installed, channel, fetcher=transport,
            now=lambda: "2026-10-10T20:30:00Z",
            monotonic=iter((0.0, 0.1, 0.2, 0.3, 0.4)).__next__,
        )
        return result, transport

    def test_stable_sorts_semver_and_returns_only_bounded_safe_fields(self):
        items = [
            release("v0.2.9"), release("v0.10.0"), release("v0.3.0-beta.1", prerelease=True),
            release("v9.0.0", draft=True),
        ]
        result, transport = self.check(responses=[page(items)])
        self.assertEqual(result, {
            "status": "update_available",
            "reason": None,
            "source": updates.SOURCE,
            "installed_version": "0.2.4",
            "available_version": "0.10.0",
            "available_url": "https://github.com/caiolombello/orla-desktop/releases/tag/v0.10.0",
            "channel": "stable",
            "checked_at": "2026-10-10T20:30:00Z",
        })
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0][0], updates.page_url(1))
        self.assertLessEqual(transport.calls[0][1], updates.REQUEST_TIMEOUT_SECONDS)

    def test_beta_accepts_current_exact_tag_marked_prerelease(self):
        items = [release("v0.2.5", prerelease=True), release("v0.2.5-beta.2", prerelease=True)]
        result, _ = self.check(channel="beta", responses=[page(items)])
        self.assertEqual(result["status"], "update_available")
        self.assertEqual(result["available_version"], "0.2.5")

    def test_stable_excludes_prerelease_flag_even_for_exact_tag(self):
        result, _ = self.check(responses=[page([
            release("v0.2.5", prerelease=True),
            release("v0.3.0-rc.1", prerelease=False),
        ])])
        self.assertEqual(result["status"], "no_release")
        self.assertIsNone(result["available_version"])

    def test_beta_uses_canonical_semver_prerelease_precedence(self):
        items = [
            release("v1.0.0-beta.11", prerelease=True),
            release("v1.0.0-rc.1", prerelease=True),
            release("v1.0.0-beta.2", prerelease=True),
        ]
        result, _ = self.check(installed="1.0.0-beta.11", channel="beta",
                               responses=[page(items)])
        self.assertEqual(result["status"], "update_available")
        self.assertEqual(result["available_version"], "1.0.0-rc.1")

    def test_future_installed_version_never_suggests_downgrade(self):
        result, _ = self.check(installed="99.0.0", responses=[page([release("v1.0.0")])])
        self.assertEqual(result["status"], "up_to_date")
        self.assertEqual(result["available_version"], "1.0.0")

    def test_build_metadata_does_not_change_semver_precedence(self):
        result, _ = self.check(installed="0.2.4+local.7", responses=[page([release("v0.2.4+release.1")])])
        self.assertEqual(result["status"], "up_to_date")

    def test_valid_encoded_release_path_is_returned_as_safe_canonical_ascii(self):
        encoded = "https://github.com/caiolombello/orla-desktop/releases/tag/%76%31%2E%30%2E%30"
        result, _ = self.check(responses=[page([release("v1.0.0", url=encoded)])])
        self.assertEqual(result["available_url"],
                         "https://github.com/caiolombello/orla-desktop/releases/tag/v1.0.0")

    def test_fetch_is_bounded_and_incomplete_last_page_is_unavailable(self):
        full = [release(f"v0.2.{index}") for index in range(updates.RESULTS_PER_PAGE)]
        result, transport = self.check(responses=[page(full), page(full)])
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "incomplete_results")
        self.assertEqual(len(transport.calls), updates.MAX_PAGES)
        self.assertEqual(transport.calls[-1][0], updates.page_url(updates.MAX_PAGES))

    def test_oversized_response_is_unavailable(self):
        body = b"[" + b" " * updates.MAX_RESPONSE_BYTES + b"]"
        result, _ = self.check(responses=[(200, {}, body)])
        self.assertEqual((result["status"], result["reason"]),
                         ("unavailable", "response_too_large"))

    def test_total_response_and_elapsed_time_are_bounded(self):
        first = [release(f"v0.2.{index}") | {"ignored": "x" * 3000}
                 for index in range(updates.RESULTS_PER_PAGE)]
        second = [release("v1.0.0") | {"ignored": "x" * 240_000}]
        total, transport = self.check(responses=[page(first), page(second)])
        self.assertEqual((total["status"], total["reason"]),
                         ("unavailable", "response_too_large"))
        self.assertEqual(len(transport.calls), 2)

        clock = iter((0.0, 0.0, updates.TOTAL_TIMEOUT_SECONDS + 0.1)).__next__
        timed = updates.check_updates(
            "0.2.4", fetcher=FakeTransport([page([])]),
            now=lambda: "2026-10-10T20:30:00Z", monotonic=clock,
        )
        self.assertEqual((timed["status"], timed["reason"]),
                         ("unavailable", "timeout"))

    def test_malformed_or_future_incompatible_payload_is_not_up_to_date(self):
        cases = [
            b"not json",
            json.dumps({"tag_name": "v1.0.0"}).encode(),
            json.dumps([release("next")]).encode(),
            json.dumps([release("v1.0.0", url="https://example.test/release")]).encode(),
            json.dumps([release("v1.0.0", url="https://github.com:bad/release")]).encode(),
            *[
                json.dumps([release("v1.0.0", url=prefix +
                    "https://github.com/caiolombello/orla-desktop/releases/tag/v1.0.0" + suffix)]).encode()
                for prefix, suffix in ((" ", ""), ("\n", ""), ("\t", ""), ("", "\r\n"))
            ],
        ]
        for body in cases:
            with self.subTest(body=body[:20]):
                result, _ = self.check(responses=[(200, {}, body)])
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["reason"], "malformed_response")

    def test_rate_limit_and_offline_have_typed_non_success_status(self):
        limited, _ = self.check(responses=[(429, {"retry-after": "60"}, b"private detail")])
        offline, _ = self.check(responses=[OSError("contains personal network details")])
        timed, _ = self.check(responses=[TimeoutError("private timeout detail")])
        self.assertEqual((limited["status"], limited["reason"]),
                         ("rate_limited", "rate_limit"))
        self.assertEqual((offline["status"], offline["reason"]),
                         ("unavailable", "network_error"))
        self.assertEqual((timed["status"], timed["reason"]),
                         ("unavailable", "timeout"))
        self.assertNotIn("private", json.dumps(limited))
        self.assertNotIn("personal", json.dumps(offline))
        self.assertNotIn("private", json.dumps(timed))

    def test_http_protocol_failures_are_safe_unavailable(self):
        for failure in (IncompleteRead(b"partial", 99), BadStatusLine("private response")):
            with self.subTest(failure=type(failure).__name__):
                result, _ = self.check(responses=[failure])
                self.assertEqual((result["status"], result["reason"]),
                                 ("unavailable", "network_error"))
                self.assertNotIn("partial", json.dumps(result))
                self.assertNotIn("private", json.dumps(result))

    def test_production_worker_timeout_kills_and_reaps_blocked_network_work(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "pid"
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                updates._bounded_fetch(str(marker), 0.08, worker=blocking_network_worker)
            self.assertLess(time.monotonic() - started, 1.0)
            pid = int(marker.read_text(encoding="ascii"))
            with self.assertRaises(ChildProcessError):
                os.waitpid(pid, os.WNOHANG)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_redirect_and_unexpected_http_status_are_not_followed_or_successful(self):
        for status in (302, 500):
            with self.subTest(status=status):
                result, transport = self.check(responses=[(status, {"location": "https://evil.test"}, b"")])
                self.assertEqual((result["status"], result["reason"]),
                                 ("unavailable", "unexpected_http_status"))
                self.assertEqual(len(transport.calls), 1)

    def test_invalid_input_is_structured_and_makes_no_request(self):
        transport = FakeTransport([])
        result = updates.check_updates("01.2.3", "nightly", fetcher=transport)
        self.assertEqual((result["status"], result["reason"]),
                         ("unavailable", "invalid_input"))
        self.assertEqual(transport.calls, [])

    def test_cli_outputs_one_json_object_and_failure_exit_is_two(self):
        output = io.StringIO()
        code = updates.main(["check", "--installed-version", "01.2.3"], stdout=output)
        parsed = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(parsed["status"], "unavailable")
        self.assertNotIn("updated", output.getvalue())


if __name__ == "__main__":
    unittest.main()
