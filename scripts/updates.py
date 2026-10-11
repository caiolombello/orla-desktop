#!/usr/bin/env python3
"""Explicit, read-only Linux CLI release check for Orla Desktop.

Network deadlines exclude up to 0.5 seconds of owned-worker cleanup. Run this
standalone CLI in its own process; its fork transport is not a Qt GUI API.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.client import HTTPException
import json
import multiprocessing
import re
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SOURCE = "https://api.github.com/repos/caiolombello/orla-desktop/releases"
RELEASE_PAGE_PREFIX = "/caiolombello/orla-desktop/releases/tag/"
API_VERSION = "2022-11-28"
RESULTS_PER_PAGE = 50
MAX_PAGES = 2
MAX_RESPONSE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 384 * 1024
REQUEST_TIMEOUT_SECONDS = 5.0
TOTAL_TIMEOUT_SECONDS = 12.0
WORKER_REAP_SECONDS = 0.5
MAX_VERSION_LENGTH = 128

SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

Transport = Callable[[str, float], tuple[int, dict[str, str], bytes]]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def page_url(page: int) -> str:
    return f"{SOURCE}?per_page={RESULTS_PER_PAGE}&page={page}"


def _bounded_read(response) -> bytes:
    return response.read(MAX_RESPONSE_BYTES + 1)


def fetch_page(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """GET one fixed GitHub API page without credentials or redirects."""
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "orla-desktop-update-check/0.1",
    })
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), _bounded_read(response)
    except HTTPError as exc:
        with exc:
            return exc.code, dict(exc.headers.items()), _bounded_read(exc)


def _network_worker(connection, url: str, timeout: float) -> None:
    try:
        status, _headers, body = fetch_page(url, timeout)
        connection.send(("ok", status, body))
    except BaseException:
        connection.send(("error",))
    finally:
        connection.close()


def _bounded_fetch(url: str, timeout: float, *, worker=_network_worker):
    """Run owned network work in a killed-and-reaped Linux subprocess."""
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=worker, args=(send, url, timeout), daemon=True)
    deadline = time.monotonic() + max(0.0, timeout)
    started = False
    try:
        process.start()
        started = True
        send.close()
        if not receive.poll(max(0.0, deadline - time.monotonic())):
            raise TimeoutError("network request deadline exceeded")
        try:
            message = receive.recv()
        except EOFError as exc:
            raise OSError("network worker ended without a response") from exc
        if (not isinstance(message, tuple) or len(message) != 3 or message[0] != "ok"
                or not isinstance(message[1], int) or not isinstance(message[2], bytes)
                or len(message[2]) > MAX_RESPONSE_BYTES + 1):
            raise OSError("network worker failed")
        return message[1], {}, message[2]
    finally:
        receive.close()
        if not started:
            send.close()
        else:
            if process.is_alive():
                process.kill()
            process.join(WORKER_REAP_SECONDS)
            if process.is_alive():
                raise OSError("network worker cleanup failed")


def _parse_version(value: object, *, tag: bool = False):
    if not isinstance(value, str) or not value or len(value) > MAX_VERSION_LENGTH:
        return None
    raw = value[1:] if tag and value.startswith("v") else value
    if tag and not value.startswith("v"):
        return None
    match = SEMVER.fullmatch(raw)
    if not match:
        return None
    major, minor, patch, prerelease, build = match.groups()
    identifiers = tuple(prerelease.split(".")) if prerelease else ()
    return raw, (int(major), int(minor), int(patch)), identifiers, build


def _compare(left, right) -> int:
    if left[1] != right[1]:
        return -1 if left[1] < right[1] else 1
    left_pre, right_pre = left[2], right[2]
    if not left_pre or not right_pre:
        if left_pre == right_pre:
            return 0
        return -1 if left_pre else 1
    for a, b in zip(left_pre, right_pre):
        if a == b:
            continue
        a_number, b_number = a.isdigit(), b.isdigit()
        if a_number and b_number:
            return -1 if int(a) < int(b) else 1
        if a_number != b_number:
            return -1 if a_number else 1
        return -1 if a < b else 1
    if len(left_pre) == len(right_pre):
        return 0
    return -1 if len(left_pre) < len(right_pre) else 1


def _safe_release_url(value: object, tag: str) -> str | None:
    if (not isinstance(value, str) or len(value) > 512
            or any(ord(character) <= 32 or ord(character) == 127 for character in value)):
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    expected_path = RELEASE_PAGE_PREFIX + tag
    if (parsed.scheme != "https" or hostname != "github.com" or port is not None
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or unquote(parsed.path) != expected_path):
        return None
    return "https://github.com" + expected_path


def _result(status: str, reason: str | None, installed: str | None, channel: str,
            checked_at: str, available: str | None = None,
            available_url: str | None = None) -> dict[str, object]:
    return {
        "status": status,
        "reason": reason,
        "source": SOURCE,
        "installed_version": installed,
        "available_version": available,
        "available_url": available_url,
        "channel": channel,
        "checked_at": checked_at,
    }


def check_updates(installed_version: str, channel: str = "stable", *,
                  fetcher: Transport | None = None,
                  now: Callable[[], str] = _utc_now,
                  monotonic: Callable[[], float] = time.monotonic) -> dict[str, object]:
    """Check releases only; injected fetchers are a synchronous test seam."""
    checked_at = now()
    installed = _parse_version(installed_version)
    if installed is None or channel not in ("stable", "beta"):
        safe_installed = installed_version if isinstance(installed_version, str) and len(installed_version) <= MAX_VERSION_LENGTH else None
        safe_channel = channel if channel in ("stable", "beta") else "invalid"
        return _result("unavailable", "invalid_input", safe_installed, safe_channel, checked_at)

    started = monotonic()
    transport = _bounded_fetch if fetcher is None else fetcher
    releases: list[object] = []
    total_bytes = 0
    try:
        for page_number in range(1, MAX_PAGES + 1):
            remaining = TOTAL_TIMEOUT_SECONDS - (monotonic() - started)
            if remaining <= 0:
                return _result("unavailable", "timeout", installed[0], channel, checked_at)
            status, _headers, body = transport(page_url(page_number), min(REQUEST_TIMEOUT_SECONDS, remaining))
            if monotonic() - started > TOTAL_TIMEOUT_SECONDS:
                return _result("unavailable", "timeout", installed[0], channel, checked_at)
            if status in (403, 429):
                return _result("rate_limited", "rate_limit", installed[0], channel, checked_at)
            if status != 200:
                return _result("unavailable", "unexpected_http_status", installed[0], channel, checked_at)
            total_bytes += len(body)
            if len(body) > MAX_RESPONSE_BYTES or total_bytes > MAX_TOTAL_BYTES:
                return _result("unavailable", "response_too_large", installed[0], channel, checked_at)
            try:
                items = json.loads(body)
            except (TypeError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                return _result("unavailable", "malformed_response", installed[0], channel, checked_at)
            if not isinstance(items, list) or len(items) > RESULTS_PER_PAGE:
                return _result("unavailable", "malformed_response", installed[0], channel, checked_at)
            releases.extend(items)
            if len(items) < RESULTS_PER_PAGE:
                break
            if page_number == MAX_PAGES:
                return _result("unavailable", "incomplete_results", installed[0], channel, checked_at)
    except TimeoutError:
        return _result("unavailable", "timeout", installed[0], channel, checked_at)
    except (OSError, HTTPError, HTTPException, URLError, ValueError):
        return _result("unavailable", "network_error", installed[0], channel, checked_at)

    candidates = []
    for item in releases:
        if not isinstance(item, dict) or type(item.get("draft")) is not bool or type(item.get("prerelease")) is not bool:
            return _result("unavailable", "malformed_response", installed[0], channel, checked_at)
        if item["draft"]:
            continue
        version = _parse_version(item.get("tag_name"), tag=True)
        if version is None:
            return _result("unavailable", "malformed_response", installed[0], channel, checked_at)
        if channel == "stable" and (item["prerelease"] or version[2]):
            continue
        url = _safe_release_url(item.get("html_url"), item["tag_name"])
        if url is None:
            return _result("unavailable", "malformed_response", installed[0], channel, checked_at)
        candidates.append((version, url))

    if not candidates:
        return _result("no_release", None, installed[0], channel, checked_at)
    available, available_url = candidates[0]
    for version, url in candidates[1:]:
        if _compare(available, version) < 0:
            available, available_url = version, url
    status = "update_available" if _compare(installed, available) < 0 else "up_to_date"
    return _result(status, None, installed[0], channel, checked_at, available[0], available_url)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def parser() -> argparse.ArgumentParser:
    result = _Parser(prog=_program_name(sys.argv[0]), description="Check official Orla Desktop releases without installing")
    subparsers = result.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="perform one anonymous read-only release check")
    check.add_argument("--installed-version", required=True,
                       help="explicit version to compare; this does not inspect the running desktop session")
    check.add_argument("--channel", choices=("stable", "beta"), default="stable")
    return result


def _program_name(value: str) -> str:
    return value.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def main(argv: list[str] | None = None, *, stdout=None) -> int:
    output = stdout or sys.stdout
    try:
        args = parser().parse_args(argv)
        result = check_updates(args.installed_version, args.channel)
    except ValueError:
        result = _result("unavailable", "invalid_input", None, "invalid", _utc_now())
    json.dump(result, output, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    output.write("\n")
    return 2 if result["status"] in ("unavailable", "rate_limited") else 0


if __name__ == "__main__":
    raise SystemExit(main())
