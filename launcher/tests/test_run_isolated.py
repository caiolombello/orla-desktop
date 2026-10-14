"""Exercise selection against an owned executable, without bypassing the private bus."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).with_name("run_isolated.py")


class RunIsolatedSelectionTests(unittest.TestCase):
    def test_exclusion_enumerates_and_executes_in_one_private_environment(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
            root = Path(directory)
            receipt = root / "calls.jsonl"
            binary = root / "owned-qt-test"
            binary.write_text("#!/usr/bin/python3\nimport json,os,sys\n"
                + "with open(" + repr(str(receipt)) + ", 'a') as out: out.write(json.dumps({'args':sys.argv[1:],'bus':os.environ['DBUS_SESSION_BUS_ADDRESS'],'runtime':os.environ['XDG_RUNTIME_DIR'],'id':os.environ['ORLA_EXPECTED_PRIVATE_BUS_ID'],'display':os.environ.get('DISPLAY'),'wayland':os.environ.get('WAYLAND_DISPLAY')})+'\\n')\n"
                + "print('first()\\nactions()\\nlast()' if sys.argv[1:]==['-functions'] else 'owned tests executed')\n")
            binary.chmod(0o755)
            result = subprocess.run([sys.executable, "-B", str(RUNNER), "--private-path", "--exclude-test", "actions", str(binary)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            calls = [json.loads(line) for line in receipt.read_text().splitlines()]
            self.assertEqual([call["args"] for call in calls], [["-functions"], ["first", "last"]])
            for key in ("bus", "runtime", "id"):
                self.assertEqual(calls[0][key], calls[1][key])
            self.assertNotEqual(calls[0]["bus"], os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
            self.assertIsNone(calls[0]["display"])
            self.assertIsNone(calls[0]["wayland"])
            self.assertIn("ORLA_ISOLATION_CLEANUP owned_daemon_stopped=true", result.stdout)

    def test_invalid_selection_never_executes_the_test_body(self):
        cases = [("first()\nactions()", ["unknown"]),
                 ("first()\nactions()", ["first", "actions"]),
                 ("first()\nfirst()", ["first"]),
                 ("not a function", ["actions"]),
                 ("", ["actions"])]
        for listing, excluded in cases:
            with self.subTest(listing=listing, excluded=excluded), tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
                root = Path(directory)
                body = root / "body-ran"
                binary = root / "owned-qt-test"
                binary.write_text("#!/usr/bin/python3\nimport pathlib,sys\n"
                    + "if sys.argv[1:]==['-functions']: print(" + repr(listing) + ")\n"
                    + "else: pathlib.Path(" + repr(str(body)) + ").touch()\n")
                binary.chmod(0o755)
                arguments = [sys.executable, "-B", str(RUNNER), "--private-path"]
                for name in excluded: arguments.extend(["--exclude-test", name])
                result = subprocess.run(arguments + [str(binary)], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(body.exists())
                self.assertIn("ORLA_ISOLATION_CLEANUP owned_daemon_stopped=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
