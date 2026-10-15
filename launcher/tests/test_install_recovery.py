"""One causal public recovery tracer. Root executes; preparation is static."""

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import test_install as fixtures


class InstallRecoveryTracerTests(unittest.TestCase):
    def test_finish_published_pending_install_without_replacing_owned_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "owned home with spaces"
            data_home, state_home = home / "configured data", home / "configured state"
            data_home.mkdir(parents=True)
            state_home.mkdir(parents=True)
            roots = ["--home", str(home), "--data-home", str(data_home),
                     "--state-home", str(state_home)]
            userdata = {
                home / ".config/orla/aliases.json": b'{"fixture":"alias remains"}\n',
                home / ".config/kglobalshortcutsrc": b"[owned-fixture]\nunchanged=Meta\n",
                data_home / "orla-desktop/user-data/favorites.json": b'{"fixture":"favorite remains"}\n',
                state_home / "orla/layout/first.json": b'{"fixture":"first bank remains"}\n',
            }
            for path, content in userdata.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            def frozen(paths):
                return {path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) for path in paths}

            preserved = frozen(userdata)
            archive_root = root / "archive fixture"
            archive_root.mkdir()
            archive, digest = fixtures.package_fixtures.PackageTests().build_archive(archive_root)
            archive_before = frozen([archive])
            commit = "a" * 40

            original_bundle, new_bundle = root / "original bootstrap", root / "new bootstrap"
            for bundle in (original_bundle, new_bundle):
                bundle.mkdir()
                for name in ("install.py", "package.py"):
                    shutil.copyfile(fixtures.LAUNCHER / name, bundle / name)
                    os.chmod(bundle / name, 0o644)
            manager, module_name, previous = fixtures.load_bootstrap(original_bundle)
            if previous is None:
                self.addCleanup(sys.modules.pop, module_name, None)
            else:
                self.addCleanup(sys.modules.__setitem__, module_name, previous)

            paths = manager.InstallPaths(home, data_home, state_home)
            state = state_home / "orla/launcher-install"
            intent = state / "pending-intent.json"
            installed_marker = state / "transactions" / (digest + "-installed.json")
            real_unlink = manager._unlink_checked
            fired = []

            def fail_late(path, record, mode):
                if path == intent and not fired:
                    self.assertTrue(installed_marker.is_file())
                    self.assertTrue((state / "current.json").is_file())
                    fired.append(True)
                    raise manager.InstallError("write_failed")
                return real_unlink(path, record, mode)

            def public(module, arguments):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        code = module.main([*roots, *arguments])
                    except SystemExit as error:
                        code = error.code
                return code, stdout.getvalue(), stderr.getvalue()

            with mock.patch.object(manager, "_unlink_checked", side_effect=fail_late), \
                    mock.patch("subprocess.Popen", side_effect=AssertionError("filesystem install cannot start programs")):
                code, output, stderr = public(manager, ["install", str(archive), "--sha256", digest,
                                                        "--commit", commit])
            self.assertEqual(fired, [True])
            self.assertEqual(code, 2, stderr)
            self.assertEqual(json.loads(output), {"status": "error", "code": "write_failed"})
            self.assertEqual(manager.status(paths)["status"], "pending")
            self.assertEqual(manager.status(paths)["code"], "write_failed")
            with mock.patch.object(manager.os, "execv", side_effect=AssertionError("pending launch must not execute")), \
                    mock.patch("subprocess.Popen", side_effect=AssertionError("pending barriers cannot start programs")):
                for action in ("launch", "uninstall"):
                    code, output, stderr = public(manager, [action])
                    self.assertEqual(code, 2, stderr)
                    self.assertEqual(json.loads(output)["code"], "pending_transaction")

            version = data_home / "orla-desktop/launcher/versions" / digest
            tools = data_home / "orla-desktop/launcher/tools"
            controller = home / ".local/bin/orla-launcherctl"
            launcher = home / ".local/bin/orla-launcher"
            menu = data_home / "applications/org.orla.Launcher.desktop"
            managed = [version / relative for relative, _mode in fixtures.package_fixtures.package.PAYLOAD]
            managed += [tools / "install.py", tools / "package.py", controller, launcher, menu]
            managed_before = frozen(managed)
            immutable = [state / "current.json", state / "receipts" / (digest + ".json"),
                         state / "transactions" / (digest + "-install.json"), installed_marker]
            immutable_before = frozen(immutable)
            pending_paths = [intent, state / "pending.json", state / "pending-error.json"]
            pending_before = frozen(pending_paths)
            self.assertEqual(json.loads(pending_before[pending_paths[-1]][0])["code"], "write_failed")

            # Only a disposable copy disappears; Source and frozen preparation stay untouched.
            original_bundle.rename(root / "original bootstrap unavailable")
            self.assertFalse(original_bundle.exists())
            new_manager, new_name, new_previous = fixtures.load_bootstrap(new_bundle)
            if new_previous is None:
                self.addCleanup(sys.modules.pop, new_name, None)
            else:
                self.addCleanup(sys.modules.__setitem__, new_name, new_previous)
            with mock.patch("subprocess.Popen", side_effect=AssertionError("recovery cannot start programs")), \
                    mock.patch.object(new_manager.os, "execv", side_effect=AssertionError("recovery cannot execute launcher")):
                code, output, stderr = public(new_manager, ["recover", "--finish-install"])
            # Baseline RED is here: argparse rejects the absent recover command.
            self.assertEqual(code, 0, "public recovery unavailable or failed: " + stderr + output)
            recovered = json.loads(output)
            self.assertEqual(recovered["status"], "installed")
            self.assertEqual(recovered["runtime"], "unverified")
            self.assertEqual(recovered["archiveSha256"], digest)
            self.assertEqual(frozen(managed), managed_before)
            self.assertEqual(frozen(immutable), immutable_before)
            self.assertEqual(frozen(userdata), preserved)
            self.assertEqual(frozen([archive]), archive_before)
            self.assertFalse(intent.exists())
            self.assertFalse((state / "pending.json").exists())

            # Root's shared public audit contract stores exact evidence inside
            # one immutable finite JSON bank, rather than raw history copies.
            banks = list((state / "transactions").glob("*-finish-install-recovery.json"))
            self.assertEqual(len(banks), 1)
            bank_path = banks[0]
            bank_stat = bank_path.lstat()
            self.assertTrue(stat.S_ISREG(bank_stat.st_mode))
            self.assertEqual(stat.S_IMODE(bank_stat.st_mode), 0o600)
            self.assertLessEqual(bank_stat.st_size, 512 * 1024)
            bank_before = frozen([bank_path])

            def unique_fields(pairs):
                result = {}
                for key, value in pairs:
                    self.assertNotIn(key, result, "duplicate recovery bank JSON field")
                    result[key] = value
                return result

            def reject_constant(value):
                self.fail("nonfinite recovery bank JSON constant: " + value)

            bank = json.loads(bank_before[bank_path][0], object_pairs_hook=unique_fields,
                              parse_constant=reject_constant)
            self.assertIs(type(bank), dict)
            self.assertEqual(bank["schema"], "orla-launcher-finish-install-recovery-0.1")
            self.assertIs(type(bank["pending"]), list)
            self.assertEqual(len(bank["pending"]), 3)
            expected_pending = {path.name: original for path, original in pending_before.items()}
            observed_pending = {}
            for record in bank["pending"]:
                self.assertIs(type(record), dict)
                self.assertEqual(set(record), {"name", "pin", "dataHex"})
                name = record["name"]
                self.assertIs(type(name), str)
                self.assertIn(name, expected_pending)
                self.assertNotIn(name, observed_pending)
                # All three records exist in this causal tracer. The public bank
                # also permits pin:null/dataHex:null for an originally absent file.
                self.assertIs(type(record["pin"]), list)
                self.assertEqual(len(record["pin"]), 9)
                self.assertTrue(all(type(number) is int for number in record["pin"]))
                self.assertIs(type(record["dataHex"]), str)
                decoded = bytes.fromhex(record["dataHex"])
                self.assertEqual((decoded, stat.S_IMODE(record["pin"][2])), expected_pending[name])
                observed_pending[name] = decoded
            self.assertEqual(set(observed_pending), set(expected_pending))
            self.assertEqual(json.loads(observed_pending["pending-error.json"])["code"], "write_failed")

            # Both bootstraps unavailable: only the original installed controller
            # and its original hash-pinned tools may manage this owned install.
            new_bundle.rename(root / "new bootstrap unavailable")
            self.assertFalse(new_bundle.exists())
            outside = root / "outside working directory"
            outside.mkdir()
            environment = {"HOME": str(home), "XDG_DATA_HOME": str(data_home),
                           "XDG_STATE_HOME": str(state_home), "PATH": "/usr/bin:/bin"}
            for action, expected in (("status", "installed"), ("uninstall", "uninstalled")):
                completed = subprocess.run([str(controller), action], cwd=outside, env=environment,
                                           capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
                report = json.loads(completed.stdout)
                self.assertEqual(report["status"], expected)
                self.assertEqual(report["runtime"], "unverified")
            for path in managed:
                self.assertFalse(path.exists())
            self.assertEqual(frozen(userdata), preserved)
            self.assertEqual(frozen([archive]), archive_before)
            self.assertEqual(frozen([bank_path]), bank_before)
            for path, expected in immutable_before.items():
                if path.name != "current.json":
                    self.assertEqual(frozen([path])[path], expected)


if __name__ == "__main__":
    unittest.main()
