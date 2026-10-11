"""Run calendar QML tests in an owned, provider-free process."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
RECEIPT_SCHEMA = "orla.calendar-tests.receipt/1"
PROBE_TIMEOUT_SECONDS = 10
SUITE_TIMEOUT_SECONDS = 60
EXPECTED_TEST_IDS = (
    "test_calendar.CalendarTests.test_inactive_or_disabled_calendar_does_not_load_pim",
    "test_calendar.CalendarTests.test_month_navigation_and_return_to_today",
    "test_calendar.CalendarTests.test_month_view_inherits_legible_dark_and_light_theme_colors",
    "test_calendar.CalendarTests.test_observable_empty_states_do_not_claim_provider_readiness",
    "test_calendar.CalendarTests.test_synthetic_events_are_plain_text_accessible_and_observed",
)
ENVIRONMENT_KEYS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "QT_QPA_PLATFORM",
    "QT_QUICK_BACKEND",
    "QT_QUICK_CONTROLS_STYLE",
)
CHILD_RUNNER = r'''
import json
from pathlib import Path
import secrets
import sys
import unittest

schema, receipt_name, nonce, style, expected_json = sys.argv[1:]
receipt_path = Path(receipt_name)
expected_ids = json.loads(expected_json)
if not secrets.compare_digest(__import__("os").environ.get("ORLA_CALENDAR_TEST_TOKEN", ""), nonce):
    raise SystemExit("calendar test nonce mismatch")

executed_ids = []
class ReceiptResult(unittest.TextTestResult):
    def startTest(self, test):
        executed_ids.append(test.id())
        super().startTest(test)

suite = unittest.defaultTestLoader.loadTestsFromNames(expected_ids)
result = unittest.TextTestRunner(verbosity=2, resultclass=ReceiptResult).run(suite)
receipt = {
    "schema": schema,
    "nonce": nonce,
    "style": style,
    "testIds": executed_ids,
    "testsRun": result.testsRun,
    "failures": len(result.failures),
    "errors": len(result.errors),
    "skipped": [test.id() for test, _ in result.skipped],
    "successful": result.wasSuccessful(),
}
receipt_path.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if result.wasSuccessful() else 1)
'''


def isolated_environment(directory, style, token):
    environment = os.environ.copy()
    for name in ("config", "data", "cache", "runtime"):
        path = Path(directory, name)
        path.mkdir(mode=0o700)
        key = f"XDG_{name.upper()}_HOME" if name != "runtime" else "XDG_RUNTIME_DIR"
        environment[key] = str(path)
    environment.update({
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={directory}/absent-session-bus",
        "ORLA_CALENDAR_TEST_ISOLATED": "1",
        "ORLA_CALENDAR_TEST_TOKEN": token,
        "PYTHONPATH": str(TESTS),
        "QT_QPA_PLATFORM": "offscreen",
        "QT_QUICK_BACKEND": "software",
        "QT_QUICK_CONTROLS_STYLE": style,
    })
    for key in ("DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE", "DISPLAY",
                "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_SESSION_TYPE"):
        environment.pop(key, None)
    return environment


def verify_import_isolation(environment):
    probe_environment = environment.copy()
    probe_environment.pop("ORLA_CALENDAR_TEST_ISOLATED", None)
    probe_environment.pop("ORLA_CALENDAR_TEST_TOKEN", None)
    probe = """
import os
import sys
keys = %r
before = {key: os.environ.get(key) for key in keys}
import test_calendar
after = {key: os.environ.get(key) for key in keys}
if before != after:
    raise SystemExit('test_calendar changed process environment during import')
if any(name == 'PySide6' or name.startswith('PySide6.') for name in sys.modules):
    raise SystemExit('test_calendar imported Qt outside the isolated runner child')
""" % (ENVIRONMENT_KEYS,)
    return subprocess.run(
        [sys.executable, "-B", "-c", probe],
        cwd=ROOT,
        env=probe_environment,
        check=False,
        timeout=PROBE_TIMEOUT_SECONDS,
    ).returncode


def validate_receipt(receipt_path, nonce, style):
    try:
        if receipt_path.is_symlink() or receipt_path.stat().st_size > 16_384:
            return "calendar test receipt has an invalid file type or size"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError) as error:
        return f"calendar test receipt is missing or invalid: {error}"
    expected = {
        "schema": RECEIPT_SCHEMA,
        "nonce": nonce,
        "style": style,
        "testIds": list(EXPECTED_TEST_IDS),
        "testsRun": len(EXPECTED_TEST_IDS),
        "failures": 0,
        "errors": 0,
        "skipped": [],
        "successful": True,
    }
    if set(receipt) != set(expected):
        return "calendar test receipt fields differ from the versioned schema"
    for key, value in expected.items():
        if receipt.get(key) != value:
            return f"calendar test receipt rejected field {key}: {receipt.get(key)!r}"
    print(json.dumps(receipt, sort_keys=True))
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--style",
        choices=("Fusion", "org.kde.desktop"),
        default="Fusion",
        help="Qt Quick Controls style for the isolated child",
    )
    args = parser.parse_args(argv)
    token = secrets.token_hex(16)
    with tempfile.TemporaryDirectory(prefix="orla-calendar-") as directory:
        environment = isolated_environment(directory, args.style, token)
        try:
            probe_status = verify_import_isolation(environment)
        except subprocess.TimeoutExpired:
            print(f"calendar import probe timed out after {PROBE_TIMEOUT_SECONDS}s", file=sys.stderr)
            return 70
        if probe_status:
            return probe_status
        receipt_path = Path(directory, "receipt.json")
        command = [
            sys.executable, "-B", "-c", CHILD_RUNNER,
            RECEIPT_SCHEMA, str(receipt_path), token, args.style,
            json.dumps(EXPECTED_TEST_IDS),
        ]
        try:
            child = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=False,
                timeout=SUITE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            print(f"calendar Qt suite timed out after {SUITE_TIMEOUT_SECONDS}s", file=sys.stderr)
            return 71
        receipt_error = validate_receipt(receipt_path, token, args.style)
        if receipt_error:
            print(receipt_error, file=sys.stderr)
            return 72
        if child.returncode:
            print(f"calendar Qt suite exited with status {child.returncode}", file=sys.stderr)
            return child.returncode
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
