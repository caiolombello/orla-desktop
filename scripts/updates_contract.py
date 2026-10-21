"""Pure release comparison contract. No Qt, transport or application state."""
from __future__ import annotations
import re
from urllib.parse import unquote, urlsplit
SOURCE = 'https://api.github.com/repos/caiolombello/orla-desktop/releases'
RELEASE_PAGE_PREFIX = '/caiolombello/orla-desktop/releases/tag/'
MAX_VERSION_LENGTH = 128
SEMVER = re.compile('^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(?:\\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\\+([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?$')

def parse_version(value: object, *, tag: bool=False):
    if not isinstance(value, str) or not value or len(value) > MAX_VERSION_LENGTH:
        return None
    raw = value[1:] if tag and value.startswith('v') else value
    if tag and (not value.startswith('v')):
        return None
    match = SEMVER.fullmatch(raw)
    if not match:
        return None
    major, minor, patch, prerelease, build = match.groups()
    identifiers = tuple(prerelease.split('.')) if prerelease else ()
    return (raw, (int(major), int(minor), int(patch)), identifiers, build)

def compare_versions(left, right) -> int:
    if left[1] != right[1]:
        return -1 if left[1] < right[1] else 1
    left_pre, right_pre = (left[2], right[2])
    if not left_pre or not right_pre:
        if left_pre == right_pre:
            return 0
        return -1 if left_pre else 1
    for a, b in zip(left_pre, right_pre):
        if a == b:
            continue
        a_number, b_number = (a.isdigit(), b.isdigit())
        if a_number and b_number:
            return -1 if int(a) < int(b) else 1
        if a_number != b_number:
            return -1 if a_number else 1
        return -1 if a < b else 1
    if len(left_pre) == len(right_pre):
        return 0
    return -1 if len(left_pre) < len(right_pre) else 1

def safe_release_url(value: object, tag: str) -> str | None:
    if not isinstance(value, str) or len(value) > 512 or any((ord(character) <= 32 or ord(character) == 127 for character in value)):
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    expected_path = RELEASE_PAGE_PREFIX + tag
    if parsed.scheme != 'https' or hostname != 'github.com' or port is not None or (parsed.username is not None) or (parsed.password is not None) or parsed.query or parsed.fragment or (unquote(parsed.path) != expected_path):
        return None
    return 'https://github.com' + expected_path

def result(status: str, reason: str | None, installed: str | None, channel: str, checked_at: str, available: str | None=None, available_url: str | None=None) -> dict[str, object]:
    return {'status': status, 'reason': reason, 'source': SOURCE, 'installed_version': installed, 'available_version': available, 'available_url': available_url, 'channel': channel, 'checked_at': checked_at}

def utc_time(value):
    """Only second-resolution canonical UTC used by the CLI and local records."""
    from datetime import datetime
    if not isinstance(value, str) or not re.fullmatch('\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\dZ', value):
        raise ValueError('invalid UTC')
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')

def validate_result(data, expected_channel, expected_reference, exit_code=None):
    keys = {'status', 'reason', 'source', 'installed_version', 'available_version', 'available_url', 'channel', 'checked_at'}
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError('invalid result keys')
    if data['source'] != SOURCE or data['channel'] != expected_channel or data['installed_version'] != expected_reference:
        raise ValueError('mismatched reference')
    utc_time(data['checked_at'])
    status = data['status']
    reason = data['reason']
    if not isinstance(status, str) or not (reason is None or isinstance(reason, str)):
        raise ValueError('invalid status')
    if status in ('update_available', 'up_to_date', 'no_release'):
        if reason is not None or exit_code not in (None, 0):
            raise ValueError('success exit')
        if status == 'no_release':
            if data['available_version'] is not None or data['available_url'] is not None:
                raise ValueError('empty release')
        else:
            current = parse_version(expected_reference)
            available = parse_version(data['available_version'])
            if current is None or available is None:
                raise ValueError('invalid version')
            canonical = safe_release_url(data['available_url'], 'v' + available[0])
            if not canonical or canonical != data['available_url']:
                raise ValueError('noncanonical URL')
            if (compare_versions(current, available) < 0) != (status == 'update_available'):
                raise ValueError('inconsistent comparison')
            if expected_channel == 'stable' and available[2]:
                raise ValueError('stable prerelease')
    elif status in ('unavailable', 'rate_limited'):
        reasons = ('invalid_input', 'timeout', 'unexpected_http_status', 'response_too_large', 'malformed_response', 'incomplete_results', 'network_error', 'process_error', 'output_limit', 'invalid_result', 'spawn_failed')
        if exit_code not in (None, 2) or (reason != 'rate_limit' if status == 'rate_limited' else reason not in reasons) or data['available_version'] is not None or (data['available_url'] is not None):
            raise ValueError('invalid failure')
    else:
        raise ValueError('unknown status')
    return dict(data)
