"""Strict process/cache boundary and isolated direct-file CLI closure."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from scripts.updates_contract import validate_result
from scripts.updates_desktop_state import strict_json, valid_reference, Store
from scripts.updates_desktop import cli_command
from test_updates_desktop_process import payload, REF, ROOT

class ContractTests(unittest.TestCase):

    def test_literal_production_argv_and_isolated_file_cli_without_network(self):
        program, args = cli_command(ROOT, REF, 'beta')
        self.assertEqual(program, str(Path(sys.executable).resolve()))
        self.assertEqual(args, ['-I', '-B', str(ROOT / 'scripts/updates.py'), 'check', '--installed-version', '1.2.3', '--channel', 'beta'])
        with tempfile.TemporaryDirectory() as directory:
            for command in ([sys.executable, '-I', '-B', str(ROOT / 'scripts/updates.py')],):
                result = subprocess.run(command + ['check', '--installed-version', 'invalid'], cwd=directory, capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)['reason'], 'invalid_input')

    def test_result_mismatches_invalid_time_url_and_semantics_are_refused(self):
        valid = payload()
        self.assertEqual(validate_result(valid, 'stable', '1.2.3', 0), valid)
        for field, value in [('source', 'https://evil.test'), ('channel', 'beta'), ('installed_version', '0.1.0'), ('checked_at', '2026-02-30T12:00:00Z'), ('checked_at', '2026-10-20T12:00:00+00:00'), ('available_url', 'https://github.com@evil.test/path'), ('status', 'up_to_date'), ('reason', 'private server response')]:
            with self.subTest(field=field, value=value):
                self.assertRaises(ValueError, validate_result, dict(valid, **{field: value}), 'stable', '1.2.3', 0)
        self.assertRaises(ValueError, validate_result, dict(valid, extra='body'), 'stable', '1.2.3', 0)
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{} {}', 'x' * 17000):
            self.assertRaises(ValueError, strict_json, raw)

    def test_bundle_reference_injection_does_not_infer_installed_dock(self):
        from scripts.updates_desktop import UpdatesController
        reference = dict(REF, role='bundle', component='workspace', origin='verified-manifest', commit='c' * 40)
        self.assertTrue(valid_reference(reference))
        with tempfile.TemporaryDirectory() as directory:
            host = UpdatesController(ROOT, reference, storage_root=Path(directory))
            self.assertEqual(host.state['role'], 'bundle')
            self.assertEqual(host.state['version'], '1.2.3')
            reference['version'] = '9.9.9'
            self.assertEqual(host.state['version'], '1.2.3')
            # Installed fields come only from the user's own package metadata,
            # never from the injected bundle reference; nothing claims the running dock.
            self.assertEqual((host.state['installedStatus'], host.state['installedVersion']), ('absent', ''))
            self.assertEqual((host.state['otherRole'], host.state['otherVersion']), ('', ''))
            self.assertFalse(any(('running' in key for key in host.state)))
