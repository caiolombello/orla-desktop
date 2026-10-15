"""One public owned payload update/rollback tracer; Root alone executes."""

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


class PayloadUpdateTracerTests(unittest.TestCase):
    def test_update_distinct_payload_then_rollback_keeps_original_management(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "owned home with spaces"
            data_home, state_home = home / "configured data", home / "configured state"
            data_home.mkdir(parents=True)
            state_home.mkdir(parents=True)
            roots = ["--home", str(home), "--data-home", str(data_home),
                     "--state-home", str(state_home)]
            userdata = {
                home / ".config/orla/aliases.json": b'{"fixture":"alias preserved"}\n',
                home / ".config/kglobalshortcutsrc": b"[owned-fixture]\nunchanged=Meta\n",
                data_home / "orla-desktop/user-data/favorites.json": b'{"fixture":"favorite preserved"}\n',
                state_home / "orla/layout/first.json": b'{"fixture":"first bank preserved"}\n',
            }
            for path, content in userdata.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            def frozen(paths):
                result = {}
                for path in paths:
                    observed = path.lstat()
                    self.assertTrue(stat.S_ISREG(observed.st_mode))
                    result[path] = (path.read_bytes(), stat.S_IMODE(observed.st_mode),
                                    observed.st_dev, observed.st_ino)
                return result

            preserved = frozen(userdata)
            package_fixtures = fixtures.package_fixtures
            package = package_fixtures.package
            fixture_a, fixture_b = root / "archive A", root / "archive B"
            fixture_a.mkdir()
            fixture_b.mkdir()
            archive_a, digest_a = package_fixtures.PackageTests().build_archive(fixture_a)
            stage_b = package_fixtures.PackageTests().make_stage(fixture_b)
            binary_b = stage_b / "bin/orla-launcher"
            binary_b.write_bytes(binary_b.read_bytes() + b"\nowned synthetic B ELF footer\n")
            (stage_b / "libexec/ai.py").write_bytes(b"# owned synthetic B helper; never executed\n")
            archive_b = fixture_b / "package B.zip"
            digest_b = package.build(stage_b, archive_b, version="0.1.1", commit="b" * 40,
                                     ci_image_digest="sha256:" + "b" * 64,
                                     runtime_inventory=package_fixtures.runtime_inventory())
            self.assertNotEqual(digest_a, digest_b)
            verified_b = package.verify(archive_b, expected_sha256=digest_b, expected_commit="b" * 40)
            self.assertEqual(verified_b["version"], "0.1.1")
            expected_b = {relative: ((stage_b / relative).read_bytes(), mode)
                          for relative, mode in package.PAYLOAD}
            archives_before = frozen([archive_a, archive_b])

            original_bundle, new_bundle = root / "original bootstrap", root / "new bootstrap"
            for bundle in (original_bundle, new_bundle):
                bundle.mkdir()
                for name in ("install.py", "package.py"):
                    shutil.copyfile(fixtures.LAUNCHER / name, bundle / name)
                    os.chmod(bundle / name, 0o644)

            def load(bundle):
                module, name, previous = fixtures.load_bootstrap(bundle)
                if previous is None:
                    self.addCleanup(sys.modules.pop, name, None)
                else:
                    self.addCleanup(sys.modules.__setitem__, name, previous)
                return module

            def public(module, arguments):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        code = module.main([*roots, *arguments])
                    except SystemExit as error:
                        code = error.code
                return code, stdout.getvalue(), stderr.getvalue()

            original = load(original_bundle)
            with mock.patch("subprocess.Popen", side_effect=AssertionError("install must not execute programs")):
                code, output, stderr = public(original, ["install", str(archive_a), "--sha256", digest_a,
                                                         "--commit", "a" * 40])
            self.assertEqual(code, 0, stderr + output)
            self.assertEqual(json.loads(output)["status"], "installed")
            base = data_home / "orla-desktop/launcher"
            version_a, version_b = base / "versions" / digest_a, base / "versions" / digest_b
            state = state_home / "orla/launcher-install"
            current = state / "current.json"
            current_a_bytes = current.read_bytes()
            controller = home / ".local/bin/orla-launcherctl"
            launcher = home / ".local/bin/orla-launcher"
            menu = data_home / "applications/org.orla.Launcher.desktop"
            shared = [base / "tools/install.py", base / "tools/package.py", controller, launcher, menu]
            shared_before = frozen(shared)
            managed_a = [version_a / relative for relative, _mode in package.PAYLOAD] + shared
            managed_a_before = frozen(managed_a)
            self.assertNotEqual((version_a / "bin/orla-launcher").read_bytes(), expected_b["bin/orla-launcher"][0])
            self.assertNotEqual((version_a / "libexec/ai.py").read_bytes(), expected_b["libexec/ai.py"][0])
            histories_a = [state / "receipts" / (digest_a + ".json"),
                           state / "transactions" / (digest_a + "-install.json"),
                           state / "transactions" / (digest_a + "-installed.json")]
            history_a_before = frozen(histories_a)
            original_bundle.rename(root / "original bootstrap unavailable")
            self.assertFalse(original_bundle.exists())
            new_manager = load(new_bundle)

            with mock.patch("subprocess.Popen", side_effect=AssertionError("payload update cannot execute programs")), \
                    mock.patch.object(new_manager.os, "execv", side_effect=AssertionError("payload update cannot launch")):
                code, output, stderr = public(new_manager, ["update", str(archive_b), "--sha256", digest_b,
                                                            "--commit", "b" * 40])
            # Baseline RED must be here: the update public command is absent.
            self.assertEqual(code, 0, "public update unavailable or failed: " + stderr + output)
            updated = json.loads(output)
            self.assertEqual(updated["status"], "installed")
            self.assertEqual(updated["runtime"], "unverified")
            self.assertEqual(updated["archiveSha256"], digest_b)
            self.assertEqual(frozen(shared), shared_before)
            self.assertEqual(frozen(histories_a), history_a_before)
            self.assertEqual(frozen(userdata), preserved)
            self.assertEqual({path.name for path in (base / "versions").iterdir()}, {digest_b})
            for relative, (content, mode) in expected_b.items():
                path = version_b / relative
                self.assertEqual((path.read_bytes(), stat.S_IMODE(path.stat().st_mode)), (content, mode))
            retained = data_home / "orla-desktop/launcher-update"
            for relative, _mode in package.PAYLOAD:
                source_record = managed_a_before[version_a / relative]
                retained_path = retained / "versions" / digest_a / relative
                self.assertEqual(frozen([retained_path])[retained_path], source_record)

            outside = root / "outside working directory"
            outside.mkdir()
            environment = {"HOME": str(home), "XDG_DATA_HOME": str(data_home),
                           "XDG_STATE_HOME": str(state_home), "PATH": "/usr/bin:/bin"}

            def standalone(action, expected_status, expected_digest):
                completed = subprocess.run([str(controller), action], cwd=outside, env=environment,
                                           capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
                report = json.loads(completed.stdout)
                self.assertEqual(report["status"], expected_status)
                self.assertEqual(report["runtime"], "unverified")
                self.assertEqual(report["archiveSha256"], expected_digest)

            standalone("status", "installed", digest_b)
            bank_path = state / "payload-update/bank.json"
            bank_stat = bank_path.lstat()
            self.assertTrue(stat.S_ISREG(bank_stat.st_mode))
            self.assertEqual(stat.S_IMODE(bank_stat.st_mode), 0o600)
            self.assertLessEqual(bank_stat.st_size, 512 * 1024)
            bank_before = frozen([bank_path])
            bank = json.loads(bank_before[bank_path][0])
            self.assertEqual(bank["schema"], "orla-launcher-payload-update-0.1")
            self.assertEqual(bank["from"]["archiveSha256"], digest_a)
            self.assertEqual(bank["to"]["archiveSha256"], digest_b)
            history_b = state / "receipts" / (digest_b + ".json")
            history_b_before = frozen([history_b])

            with mock.patch("subprocess.Popen", side_effect=AssertionError("rollback cannot execute programs")), \
                    mock.patch.object(new_manager.os, "execv", side_effect=AssertionError("rollback cannot launch")):
                code, output, stderr = public(new_manager, ["rollback"])
            self.assertEqual(code, 0, stderr + output)
            rolled_back = json.loads(output)
            self.assertEqual(rolled_back["status"], "installed")
            self.assertEqual(rolled_back["runtime"], "unverified")
            self.assertEqual(rolled_back["archiveSha256"], digest_a)
            self.assertEqual(current.read_bytes(), current_a_bytes)
            self.assertEqual(frozen(managed_a), managed_a_before)
            self.assertEqual(frozen(histories_a), history_a_before)
            self.assertEqual(frozen([history_b]), history_b_before)
            self.assertEqual(frozen([bank_path]), bank_before)
            self.assertEqual(frozen(userdata), preserved)
            self.assertEqual({path.name for path in (base / "versions").iterdir()}, {digest_a})
            retained_b_paths = [retained / "versions" / digest_b / relative for relative, _mode in package.PAYLOAD]
            retained_b_before = frozen(retained_b_paths)
            for relative, (content, mode) in expected_b.items():
                path = retained / "versions" / digest_b / relative
                self.assertEqual((path.read_bytes(), stat.S_IMODE(path.stat().st_mode)), (content, mode))

            new_bundle.rename(root / "new bootstrap unavailable")
            self.assertFalse(new_bundle.exists())
            standalone("status", "installed", digest_a)
            standalone("uninstall", "uninstalled", digest_a)
            for path in managed_a:
                self.assertFalse(path.exists())
            self.assertFalse(current.exists())
            self.assertEqual(frozen(userdata), preserved)
            self.assertEqual(frozen([archive_a, archive_b]), archives_before)
            self.assertEqual(frozen(histories_a), history_a_before)
            self.assertEqual(frozen([history_b]), history_b_before)
            self.assertEqual(frozen([bank_path]), bank_before)
            # Old uninstall removes the active install, not the retained other
            # payload or its finite update workspace/history.
            self.assertEqual(frozen(retained_b_paths), retained_b_before)
            self.assertTrue((state / "payload-update").is_dir())


if __name__ == "__main__":
    unittest.main()
