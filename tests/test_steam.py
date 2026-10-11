"""Synthetic filesystem tests; never inspect an existing Steam installation."""

from __future__ import annotations

import json
import io
import os
from pathlib import Path
import sys
import tempfile
import time
import multiprocessing
import unittest
from dataclasses import replace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import steam  # noqa: E402


def blocked_worker(connection, roots, limits):
    time.sleep(60)


class SteamDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "native"
        (self.root / "steamapps" / "common" / "Synthetic Game").mkdir(parents=True)
        (self.root / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders" { "0" { "path" "' + str(self.root) + '" } }', encoding="utf-8")

    def manifest(self, appid="42", *, flags="4", installdir="Synthetic Game", name="Synthetic Game"):
        path = self.root / "steamapps" / f"appmanifest_{appid}.acf"
        path.write_text('"AppState" { "appid" "' + appid + '" "name" "' + name
                        + '" "StateFlags" "' + flags + '" "installdir" "'
                        + installdir + '" }', encoding="utf-8")
        return path

    def scan(self, **kwargs):
        return steam.discover([steam.SteamRoot(str(self.root), "native")], **kwargs)

    def test_explicit_root_reports_local_install_without_claiming_ownership_or_online(self):
        self.manifest()
        result = self.scan()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["connection"], "unknown")
        self.assertEqual(len(result["apps"]), 1)
        app = result["apps"][0]
        self.assertEqual((app["appid"], app["name"], app["status"], app["ownership"]),
                         ("42", "Synthetic Game", "installed_candidate", "unknown"))
        self.assertNotIn(str(self.base), json.dumps(result))

    def test_flatpak_external_and_missing_libraries_are_distinct_without_recursive_discovery(self):
        self.manifest()
        external = self.base / "other-disk"
        (external / "steamapps").mkdir(parents=True)
        (external / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders" { "0" { "path" "/must-not-follow" } }', encoding="utf-8")
        missing = self.base / "unmounted"
        (self.root / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders" { "0" { "path" "' + str(self.root)
            + '" } "1" { "path" "' + str(external) + '" } "2" "'
            + str(missing) + '" }', encoding="utf-8")
        result = steam.discover([steam.SteamRoot(str(self.root), "flatpak")])
        self.assertEqual(result["status"], "partial")
        self.assertEqual([item["status"] for item in result["libraries"]],
                         ["available", "available", "missing"])
        self.assertEqual(result["roots"][0]["kind"], "flatpak")
        self.assertEqual(len(result["apps"]), 1)
        self.assertNotIn("must-not-follow", json.dumps(result))

    def test_absent_root_does_not_claim_offline_or_a_successful_empty_library(self):
        result = steam.discover([steam.SteamRoot(str(self.base / "absent"))])
        self.assertEqual(result["status"], "absent")
        self.assertEqual(result["roots"][0]["status"], "absent")
        self.assertEqual(result["connection"], "unknown")

    def test_corrupt_library_index_keeps_local_games_but_marks_inventory_incomplete(self):
        self.manifest()
        (self.root / "steamapps" / "libraryfolders.vdf").write_text(
            '"libraryfolders" { "0" { "path"', encoding="utf-8")
        result = self.scan()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["apps"]), 1)
        self.assertEqual(result["errors"][0]["code"], "truncated_vdf")

    def test_duplicate_truncated_unsupported_and_invalid_utf8_never_become_empty_success(self):
        path = self.manifest()
        bad = [
            (b'"AppState" { "appid" "42" "APPID" "43" }', "duplicate_key"),
            (b'"AppState" { "appid" "42"', "truncated_vdf"),
            (b'"AppState" { "appid" "42" "name" "a\\q" }', "unsupported_escape"),
            (b'#include "elsewhere"', "unsupported_vdf"),
            (b'"AppState" { "name" "\xff" }', "invalid_encoding"),
        ]
        for body, code in bad:
            with self.subTest(code=code):
                path.write_bytes(body)
                result = self.scan()
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["apps"], [])
                self.assertIn(code, [item["code"] for item in result["errors"]])

    def test_quoted_braces_comments_and_supported_escapes_are_plain_names(self):
        path = self.manifest()
        path.write_text(' // comment\n "AppState" { "appid" "42" "name" "A {game} \\"Q\\"\\n" '
                        '"StateFlags" "4" "installdir" "Synthetic Game" }', encoding="utf-8")
        result = self.scan()
        self.assertEqual(result["apps"][0]["name"], 'A {game} "Q"')
        self.assertEqual(result["status"], "available")

    def test_symlinked_manifest_is_rejected_without_reading_target(self):
        outside = self.base / "private"
        outside.write_text("private contents", encoding="utf-8")
        (self.root / "steamapps" / "appmanifest_42.acf").symlink_to(outside)
        result = self.scan()
        self.assertEqual(result["apps"], [])
        self.assertEqual(result["status"], "partial")
        self.assertIn("unsafe_target", [item["code"] for item in result["errors"]])
        self.assertNotIn("private", json.dumps(result))

    def test_manifest_traversal_and_symlinked_common_never_count_as_installed(self):
        for install in ("../outside", "/outside", "a/b", "..", "a\\\\b"):
            with self.subTest(install=install):
                self.manifest(installdir=install)
                result = self.scan()
                self.assertEqual(result["apps"], [])
                self.assertEqual(result["errors"][0]["code"], "unsafe_installdir")
        self.manifest()
        common = self.root / "steamapps" / "common"
        common.rename(self.root / "outside-common")
        common.symlink_to(self.root / "outside-common", target_is_directory=True)
        result = self.scan()
        self.assertEqual(result["apps"][0]["status"], "unknown")

    def test_missing_game_directory_is_partial_and_unknown_flags_stay_unknown(self):
        self.manifest(installdir="Not Present")
        self.assertEqual(self.scan()["apps"][0]["status"], "partial")
        for flags in ("2", "1024", "not-a-number", ""):
            with self.subTest(flags=flags):
                self.manifest(flags=flags)
                result = self.scan()
                self.assertEqual(result["apps"][0]["status"], "unknown")
                self.assertEqual(result["status"], "partial")

    def test_fifo_and_account_files_are_not_read_and_hardlinks_are_rejected(self):
        apps = self.root / "steamapps"
        for name in ("loginusers.vdf", "config.vdf", "ssfn123", "appmanifest_42.acf"):
            os.mkfifo(apps / name)
        result = self.scan()
        self.assertEqual(result["apps"], [])
        self.assertEqual(result["errors"][0]["code"], "unsafe_target")
        (apps / "appmanifest_42.acf").unlink()
        manifest = self.manifest()
        os.link(manifest, self.base / "hardlink")
        self.assertEqual(self.scan()["errors"][0]["code"], "unsafe_target")

    def test_unsafe_root_and_library_component_are_rejected(self):
        for path in (str(self.root) + "/../native", "relative", "/", str(self.root) + "/"):
            with self.subTest(path=path):
                self.assertEqual(steam.discover([steam.SteamRoot(path)])["errors"][0]["code"], "invalid_input")
        link = self.base / "linked-root"
        link.symlink_to(self.root, target_is_directory=True)
        result = steam.discover([steam.SteamRoot(str(link))])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["errors"][0]["code"], "unsafe_target")

    def test_public_limits_fail_closed_and_do_not_allow_unbounded_or_invalid_values(self):
        self.manifest()
        for limits in (replace(steam.Limits(), tokens=-1), replace(steam.Limits(), nesting=100000),
                       replace(steam.Limits(), deadline_seconds=float("nan")), False, ""):
            with self.subTest(limits=limits):
                self.assertEqual(self.scan(limits=limits)["errors"][0]["code"], "invalid_input")

    def test_uri_generation_accepts_only_fixed_actions_and_valid_32_bit_appids(self):
        self.assertEqual(steam.steam_uri("game", "42"), "steam://rungameid/42")
        self.assertEqual(steam.steam_uri("downloads"), "steam://open/downloads")
        for action, appid in (("execute", "42"), ("game", "42/quit"), ("game", "0"),
                              ("game", "042"), ("game", "4294967296"), ("game", 42),
                              ("downloads", "42"), ("game", "４２")):
            with self.subTest(action=action, appid=appid):
                self.assertRaises(ValueError, steam.steam_uri, action, appid)

    def test_cli_requires_explicit_roots_and_emits_structured_errors_without_paths(self):
        self.manifest()
        output = io.StringIO()
        self.assertEqual(steam.main(["scan", "--root", "native=" + str(self.root)], stdout=output), 0)
        self.assertEqual(json.loads(output.getvalue())["apps"][0]["appid"], "42")
        for args in (["scan"], ["scan", "--root", "garbage=" + str(self.root)], ["bogus"]):
            with self.subTest(args=args):
                output = io.StringIO()
                self.assertEqual(steam.main(args, stdout=output), 2)
                self.assertEqual(json.loads(output.getvalue())["errors"][0]["code"], "invalid_input")
                self.assertNotIn(str(self.base), output.getvalue())

    def test_invalid_manifest_filenames_are_not_read_or_silently_treated_as_empty_success(self):
        (self.root / "steamapps" / "appmanifest_00042.acf").write_text("private", encoding="utf-8")
        result = self.scan()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["apps"], [])
        self.assertEqual(result["errors"][0]["code"], "unsupported_manifest_name")

    def test_byte_token_nesting_entry_and_manifest_limits_leave_inventory_incomplete(self):
        self.manifest()
        cases = [(replace(steam.Limits(), file_bytes=16), "file_byte_limit"),
                 (replace(steam.Limits(), total_bytes=16), "total_byte_limit"),
                 (replace(steam.Limits(), tokens=2), "token_limit"),
                 (replace(steam.Limits(), nesting=1), "nesting_limit"),
                 (replace(steam.Limits(), directory_entries=1), "directory_entry_limit")]
        for limits, code in cases:
            with self.subTest(code=code):
                result = self.scan(limits=limits)
                self.assertNotEqual(result["status"], "available")
                self.assertIn(code, [item["code"] for item in result["errors"]])
        self.manifest("43")
        result = self.scan(limits=replace(steam.Limits(), manifests=1))
        self.assertEqual([item["appid"] for item in result["apps"]], ["42"])
        self.assertEqual(result["status"], "partial")
        self.assertIn("manifest_limit", [item["code"] for item in result["errors"]])

    def test_library_and_result_limits_are_explicit_failures(self):
        index = self.root / "steamapps" / "libraryfolders.vdf"
        index.write_text('"libraryfolders" { "1" "' + str(self.base / "external") + '" }', encoding="utf-8")
        result = self.scan(limits=replace(steam.Limits(), libraries=1))
        self.assertIn("library_limit", [item["code"] for item in result["errors"]])
        self.assertEqual(result["status"], "partial")
        index.write_text('"libraryfolders" {}', encoding="utf-8")
        for appid in range(42, 52):
            self.manifest(str(appid), name="X" * 160)
        result = self.scan(limits=replace(steam.Limits(), result_bytes=1024))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["errors"][0]["code"], "result_byte_limit")
        self.assertEqual(result["apps"], [])

    def test_deadline_kills_and_reaps_owned_worker_without_claiming_an_empty_inventory(self):
        before = {process.pid for process in multiprocessing.active_children()}
        started = time.monotonic()
        with patch.object(steam, "_worker", blocked_worker):
            result = self.scan(limits=replace(steam.Limits(), deadline_seconds=0.05))
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["errors"][0]["code"], "deadline")
        self.assertEqual({process.pid for process in multiprocessing.active_children()}, before)

    def test_inventory_is_deterministic_and_manifest_appid_must_match_filename(self):
        self.manifest("100")
        self.manifest("42")
        first = self.scan()
        self.assertEqual([item["appid"] for item in first["apps"]], ["42", "100"])
        self.assertEqual(self.scan(), first)
        (self.root / "steamapps" / "appmanifest_42.acf").write_text(
            '"AppState" { "appid" "999" "name" "Mismatch" }', encoding="utf-8")
        result = self.scan()
        self.assertEqual([item["appid"] for item in result["apps"]], ["100"])
        self.assertIn("unsupported_manifest", [item["code"] for item in result["errors"]])

    def test_pathlike_titles_are_redacted_in_discover_and_cli_but_unicode_game_titles_remain(self):
        path = self.manifest()
        private_names = ("/home/private-user/secret", "  /home/private-user/secret  ",
                         "C:\\Users\\private-user\\secret", "D:/private-user/secret",
                         "\\\\server\\private-user\\secret", "~/private-user/secret",
                         "~private-user/secret", "$HOME/private-user/secret",
                         "${HOME}/private-user/secret", "%USERPROFILE%/private-user/secret",
                         "%HOMEPATH%\\private-user\\secret",
                         "file:///home/private-user/secret")
        for title in private_names:
            with self.subTest(title=title):
                path.write_text('"AppState" { "appid" "42" "name" ' + json.dumps(title)
                                + ' "StateFlags" "4" "installdir" "Synthetic Game" }', encoding="utf-8")
                result = self.scan()
                self.assertEqual(result["apps"][0]["name"], "Jogo 42")
                self.assertTrue(result["apps"][0]["name_redacted"])
                self.assertEqual(result["apps"][0]["status"], "installed_candidate")
                self.assertEqual(result["status"], "partial")
                self.assertEqual(result["errors"][0]["code"], "pathlike_name_redacted")
                output = io.StringIO()
                self.assertEqual(steam.main(["scan", "--root", "native=" + str(self.root)], stdout=output), 2)
                self.assertNotIn("private-user", output.getvalue())
                self.assertEqual(json.loads(output.getvalue())["apps"][0]["name"], "Jogo 42")
        for safe_name in ("Órbita / Aventura: 星のゲーム", "File: Legend", "C: Orbital"):
            with self.subTest(safe_name=safe_name):
                self.manifest(name=safe_name)
                result = self.scan()
                self.assertEqual(result["apps"][0]["name"], safe_name)
                self.assertNotIn("name_redacted", result["apps"][0])
                self.assertEqual(result["status"], "available")


if __name__ == "__main__":
    unittest.main()
