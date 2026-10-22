import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import search_shortcut as shortcuts


class FakeBackend:
    def __init__(self):
        self.running = True
        self.actions = {
            ("org.orla.Launcher", "orla-search-open"): [[469762127, 0, 0, 0]],
            ("org.kde.krunner.desktop", "_launch"): [[16777250, 0, 0, 0], [16777362, 0, 0, 0]],
        }
        self.defaults = copy.deepcopy(self.actions)
        self.writes = []

    def preflight(self, *, require_running=False):
        if require_running and not self.running:
            raise shortcuts.ShortcutError("launcher stopped")

    def action(self, identity):
        if tuple(identity[:2]) not in self.actions:
            raise shortcuts.ShortcutError("missing action")
        return list(identity[:2]) + ["Synthetic component", "Synthetic action"]

    def keys(self, action):
        return copy.deepcopy(self.actions[tuple(action[:2])])

    def owners(self):
        return [self.action(key) for key, keys in self.actions.items() if [16777250, 0, 0, 0] in keys]

    def set_keys(self, action, keys):
        self.writes.append((action[:2], copy.deepcopy(keys)))
        self.actions[tuple(action[:2])] = copy.deepcopy(keys)


class SearchShortcutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "shortcuts"
        self.backend = FakeBackend()

    def test_enable_and_disable_restore_meta_without_changing_other_keys_or_defaults(self):
        original = copy.deepcopy(self.backend.actions)
        defaults = copy.deepcopy(self.backend.defaults)
        self.assertEqual(shortcuts.manage("enable", self.backend, self.state)["phase"], "enabled")
        self.assertEqual(self.backend.owners()[0][:2], ["org.orla.Launcher", "orla-search-open"])
        self.assertEqual(self.backend.actions[("org.kde.krunner.desktop", "_launch")], [[16777362, 0, 0, 0]])
        self.assertEqual(shortcuts.manage("disable", self.backend, self.state)["phase"], "disabled")
        self.assertEqual(self.backend.actions, original)
        self.assertEqual(self.backend.defaults, defaults)

    def test_status_never_creates_storage_or_changes_bindings(self):
        before = copy.deepcopy(self.backend.actions)
        self.assertEqual(shortcuts.manage("status", self.backend, self.state)["phase"], "unmanaged")
        self.assertFalse(self.state.exists())
        self.assertEqual(self.backend.actions, before)
        self.assertEqual(self.backend.writes, [])

    def test_multiple_prior_owners_are_refused_without_writes(self):
        self.backend.actions[("foreign.component", "foreign.action")] = [[16777250, 0, 0, 0]]
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("enable", self.backend, self.state)
        self.assertEqual(self.backend.writes, [])

    def test_disable_preserves_concurrent_unrelated_additions_and_removals(self):
        shortcuts.manage("enable", self.backend, self.state)
        self.backend.actions[("org.kde.krunner.desktop", "_launch")] = [[134217760, 0, 0, 0]]
        self.backend.actions[("org.orla.Launcher", "orla-search-open")].append([1, 2, 0, 0])
        shortcuts.manage("disable", self.backend, self.state)
        self.assertEqual(self.backend.actions[("org.kde.krunner.desktop", "_launch")],
                         [[16777250, 0, 0, 0], [134217760, 0, 0, 0]])
        self.assertEqual(self.backend.actions[("org.orla.Launcher", "orla-search-open")],
                         [[469762127, 0, 0, 0], [1, 2, 0, 0]])

    def test_unknown_write_result_is_recovered_after_a_later_retry(self):
        original = copy.deepcopy(self.backend.actions)
        setter = self.backend.set_keys

        def lost_reply(action, keys):
            setter(action, keys)
            raise shortcuts.ShortcutError("lost response")

        self.backend.set_keys = lost_reply
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("enable", self.backend, self.state)
        self.backend.set_keys = setter
        self.assertEqual(shortcuts.manage("recover", self.backend, self.state)["phase"], "disabled")
        self.assertEqual(self.backend.actions, original)

    def test_unexpected_new_meta_owner_blocks_restore_without_writing(self):
        shortcuts.manage("enable", self.backend, self.state)
        self.backend.actions[("foreign.component", "foreign.action")] = [[16777250, 0, 0, 0]]
        writes = len(self.backend.writes)
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("disable", self.backend, self.state)
        self.assertEqual(len(self.backend.writes), writes)
        self.assertEqual(shortcuts.manage("status", self.backend, self.state)["phase"], "enabled")

    def test_missing_prior_action_keeps_recovery_and_current_meta_route(self):
        shortcuts.manage("enable", self.backend, self.state)
        del self.backend.actions[("org.kde.krunner.desktop", "_launch")]
        writes = len(self.backend.writes)
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("disable", self.backend, self.state)
        self.assertEqual(len(self.backend.writes), writes)
        self.assertEqual(self.backend.owners()[0][:2], ["org.orla.Launcher", "orla-search-open"])

    def test_enable_is_idempotent_and_pending_operation_requires_recovery(self):
        shortcuts.manage("enable", self.backend, self.state)
        writes = len(self.backend.writes)
        shortcuts.manage("enable", self.backend, self.state)
        self.assertEqual(len(self.backend.writes), writes)
        store = shortcuts.Store(self.state)
        journal = store.load(); journal["phase"] = "prepared"; store.save(journal)
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("enable", self.backend, self.state)
        shortcuts.manage("recover", self.backend, self.state)
        self.assertEqual(self.backend.owners()[0][:2], ["org.kde.krunner.desktop", "_launch"])

    def test_empty_prior_owner_is_restored_to_unassigned(self):
        self.backend.actions[("org.kde.krunner.desktop", "_launch")] = [[16777362, 0, 0, 0]]
        shortcuts.manage("enable", self.backend, self.state)
        shortcuts.manage("disable", self.backend, self.state)
        self.assertEqual(self.backend.owners(), [])

    def test_symlink_journal_and_untrusted_permissions_are_refused(self):
        self.state.mkdir(mode=0o700)
        victim = Path(self.temporary.name) / "victim"
        victim.write_text("preserve")
        (self.state / "current.json").symlink_to(victim)
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("enable", self.backend, self.state)
        self.assertEqual(victim.read_text(), "preserve")
        self.assertEqual(self.backend.writes, [])

    def test_enable_requires_fallback_and_a_live_launcher_until_commit(self):
        for fault in ("fallback", "exit"):
            with self.subTest(fault=fault):
                backend = FakeBackend()
                original = copy.deepcopy(backend.actions)
                if fault == "fallback":
                    backend.actions[("org.orla.Launcher", "orla-search-open")] = []
                else:
                    setter = backend.set_keys
                    def exit_after_release(action, keys):
                        setter(action, keys)
                        backend.running = False
                    backend.set_keys = exit_after_release
                with self.assertRaises(shortcuts.ShortcutError):
                    shortcuts.manage("enable", backend, self.state / fault)
                self.assertEqual(backend.actions[("org.kde.krunner.desktop", "_launch")],
                                 original[("org.kde.krunner.desktop", "_launch")])

    def test_symlink_parent_cannot_redirect_recovery_writes(self):
        target = Path(self.temporary.name) / "outside"
        target.mkdir()
        link = Path(self.temporary.name) / "linked"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("enable", self.backend, link / "leaf")
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("status", self.backend, link / "leaf")
        self.assertFalse((target / "leaf").exists())

    def test_parallel_configuration_is_refused_without_writes(self):
        with shortcuts.Store(self.state).locked():
            with self.assertRaises(shortcuts.ShortcutError):
                shortcuts.manage("enable", self.backend, self.state)
        self.assertEqual(self.backend.writes, [])

    def test_launcher_loss_after_meta_assignment_rolls_back(self):
        original = copy.deepcopy(self.backend.actions)
        setter = self.backend.set_keys
        def exit_after_assignment(action, keys):
            setter(action, keys)
            if action[:2] == shortcuts.ORLA[:2] and shortcuts.META in keys:
                self.backend.running = False
        self.backend.set_keys = exit_after_assignment
        with self.assertRaises(shortcuts.ShortcutError):
            shortcuts.manage("enable", self.backend, self.state)
        self.assertEqual(self.backend.actions, original)

    def test_public_cli_delegates_status_without_creating_a_journal(self):
        from scripts import caiodock
        output = io.StringIO()
        with mock.patch.object(shortcuts, "NativeBackend", return_value=self.backend), \
                mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(self.state)}), contextlib.redirect_stdout(output):
            self.assertEqual(caiodock.main(["search-shortcut", "status"]), 0)
        self.assertEqual(json.loads(output.getvalue())["phase"], "unmanaged")
        self.assertFalse(self.state.exists())


class TransportTests(unittest.TestCase):
    def backend(self):
        with mock.patch.object(shortcuts.shutil, "which", return_value="/usr/bin/busctl"):
            return shortcuts.NativeBackend()

    def reply(self, signature, value):
        return subprocess.CompletedProcess([], 0, json.dumps({"type": signature, "data": [value]}), "")

    def test_foreign_assignment_uses_full_sequences_and_accepts_reordered_readback(self):
        backend = self.backend()
        backend.preflight = lambda **kwargs: None
        backend.action = lambda action: action
        keys = [[150995023, 0, 0, 0], [16777250, 0, 0, 0]]
        replies = [subprocess.CompletedProcess([], 0, "", ""), self.reply("a(ai)", [[key] for key in reversed(keys)])]
        with mock.patch.object(shortcuts.subprocess, "run", side_effect=replies) as run:
            backend.set_keys(shortcuts.ORLA, keys)
        write = run.call_args_list[0].args[0]
        self.assertEqual(write[-17:], ["asa(ai)", "4", *shortcuts.ORLA, "2", "4", "150995023", "0", "0", "0",
                                      "4", "16777250", "0", "0", "0"])
        self.assertIn("--auto-start=no", write)

    def test_bad_signature_or_shape_reports_a_recoverable_error(self):
        for reply in [self.reply("ai", [16777250]), self.reply("a(ai)", [[16777250]]),
                      self.reply("a(ai)", [[[True, 0, 0, 0]]])]:
            with self.subTest(reply=reply.stdout), mock.patch.object(shortcuts.subprocess, "run", return_value=reply):
                with self.assertRaises(shortcuts.ShortcutError):
                    self.backend().keys(shortcuts.ORLA)

    def test_nondefault_meta_context_is_refused(self):
        row = ["_launch", "Synthetic", "foreign.component", "Synthetic", "custom", "Synthetic", [16777250], []]
        with mock.patch.object(shortcuts.subprocess, "run", return_value=self.reply("a(ssssssaiai)", [row])):
            with self.assertRaises(shortcuts.ShortcutError):
                self.backend().owners()

    def test_action_in_a_component_with_custom_context_is_refused_before_keys(self):
        replies = [self.reply("o", "/component/foreign_component"), self.reply("as", ["default", "custom"])]
        with mock.patch.object(shortcuts.subprocess, "run", side_effect=replies) as run:
            with self.assertRaises(shortcuts.ShortcutError):
                self.backend().action(shortcuts.ORLA)
        self.assertEqual(run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
