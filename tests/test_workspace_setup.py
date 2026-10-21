"""The optional setup host owns one operation until its thread has finished."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

import threading
import time
import unittest
from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy, QTest
from scripts.workspace_setup import WorkspaceController
from scripts.panel_layout import LayoutError


class Session:
    def __init__(self):
        self.calls = []
        self.gate = threading.Event()
        self.gate.set()
        self.failure = False

    def read(self, connector=""):
        self.calls.append(("read", connector, QThread.currentThread()))
        self.gate.wait(5)
        if isinstance(self.failure, Exception):
            raise self.failure
        if self.failure:
            raise ValueError("private path /private/person/calendar")
        return dict(phase="UNMANAGED", shellRunning=True, inventory=None, recordPresent=False)

    def discard(self):
        self.calls.append(("discard",))

    def review_apply(self, manifest):
        self.calls.append(("review", manifest))
        return dict(token="review-one", action="apply", connector="DP-1", replacePanelIds=[28])

    def review_operation(self, action):
        return dict(token="review-one", action=action, connector="DP-1")

    def execute(self, token):
        self.calls.append(("execute", token))
        self.gate.wait(5)
        return dict(phase="COMMITTED", action="apply", connector="DP-1")


class HostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.session = Session()
        self.host = WorkspaceController(self.session, {"screen": {}, "replacePanelIds": []}, ["DP-1"])
        self.addCleanup(self.finish)

    def finish(self):
        self.session.gate.set()
        for _ in range(1000):
            if not self.host.busy:
                break
            QTest.qWait(10)
            # QtTest waits can retain the GIL; let the Python backend advance.
            time.sleep(0.001)
        self.assertFalse(self.host.busy)

    def wait(self):
        self.finish()

    def test_construction_is_inert_and_reads_run_off_gui_thread(self):
        self.assertEqual(self.session.calls, [])
        self.assertTrue(self.host.refresh("DP-1"))
        self.wait()
        self.assertNotEqual(self.session.calls[0][2], self.app.thread())
        self.assertEqual(self.host.state["phase"], "UNMANAGED")

    def test_close_during_operation_latches_before_publishing_and_blocks_reentry(self):
        self.session.gate.clear()
        self.assertTrue(self.host.refresh("DP-1"))
        close = QSignalSpy(self.host.closeReady)
        self.assertFalse(self.host.requestClose())
        self.assertFalse(self.host.requestClose())
        self.assertFalse(self.host.refresh("DP-1"))
        self.host.changed.connect(lambda: self.assertFalse(self.host.refresh("DP-1")))
        self.assertEqual(close.count(), 0)
        self.wait()
        self.assertEqual(close.count(), 1)
        self.assertTrue(self.host.closePending)

    def test_review_never_executes_and_confirmation_is_single_dispatch(self):
        self.assertTrue(self.host.prepareApply("DP-1", [28]))
        self.wait()
        self.assertEqual(self.host.review["token"], "review-one")
        self.assertFalse(any(row[0] == "execute" for row in self.session.calls))
        self.assertTrue(self.host.confirm())
        self.assertFalse(self.host.confirm())
        self.wait()
        self.assertEqual([row for row in self.session.calls if row[0] == "execute"], [("execute", "review-one")])
        self.assertEqual(self.host.review, {})

    def test_discard_invalidates_confirmation_without_executing(self):
        self.host.prepareApply("DP-1", [28]); self.wait()
        self.assertTrue(self.host.discard())
        self.assertFalse(self.host.confirm())
        self.assertFalse(any(row[0] == "execute" for row in self.session.calls))

    def test_worker_failure_is_visible_without_private_exception_text(self):
        self.session.failure = True
        self.host.refresh("DP-1"); self.wait()
        self.assertTrue(self.host.problem)
        self.assertNotIn("private", self.host.problem)
        self.assertEqual(self.host.state["phase"], "UNKNOWN")

    def test_initial_read_failure_facts_survive_join_and_worker_deletion(self):
        self.session.failure = LayoutError("synthetic private payload", code="COMMAND_EXIT",
                                           operation="UNIT_SHOW", returncode=6,
                                           hashes={"expectedSha256": "a" * 64, "actualSha256": "b" * 64})
        self.assertTrue(self.host.refresh(""))
        job = self.host.findChild(QThread)
        destroyed = QSignalSpy(job.destroyed)
        self.wait()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(destroyed.count(), 1)
        expected = {"code": "COMMAND_EXIT", "operation": "UNIT_SHOW", "returncode": 6,
                    "expectedSha256": "a" * 64, "actualSha256": "b" * 64}
        self.assertEqual(self.host.failureDiagnostics, expected)
        self.assertEqual(self.host.property("failureDiagnostics"), expected)
        self.assertEqual(self.host.state, {"phase": "UNKNOWN"})
        self.assertEqual(self.host.problem, "Não foi possível concluir a operação. Atualize a leitura para verificar o layout e a recuperação.")
        self.assertEqual(len(self.session.calls), 1)

    def test_failure_facts_are_copied_before_delivery_and_on_every_property_read(self):
        error = LayoutError("synthetic private payload", code="INVENTORY_MISMATCH",
                            hashes={"expectedSha256": "c" * 64, "actualSha256": "d" * 64})
        self.session.failure = error
        self.assertTrue(self.host.refresh(""))
        self.assertTrue(self.host.findChild(QThread).wait(1000))
        error.facts.clear()
        error.facts["private"] = {"account": "synthetic account"}
        self.wait()
        expected = {"code": "INVENTORY_MISMATCH", "operation": "TRANSACTION", "returncode": None,
                    "expectedSha256": "c" * 64, "actualSha256": "d" * 64}
        self.assertEqual(self.host.failureDiagnostics, expected)
        exposed = self.host.failureDiagnostics
        exposed["code"] = "private replacement"
        exposed["nested"] = {"payload": []}
        via_qt = self.host.property("failureDiagnostics")
        via_qt.clear()
        self.assertEqual(self.host.failureDiagnostics, expected)

    def test_typed_failure_facts_are_resanitized_with_canonical_bounds(self):
        class PayloadString(str):
            private_payload = "synthetic private payload"
        class PayloadInt(int):
            private_payload = "synthetic private payload"
        class PayloadDict(dict):
            def get(self, *args):
                raise AssertionError("custom mapping must not be read")
        defaults = {"code": "LAYOUT_REFUSAL", "operation": "TRANSACTION", "returncode": None}
        cases = [
            ({"code": "COMMAND_TIMEOUT", "operation": "BUS_OWNER", "returncode": -128},
             {"code": "COMMAND_TIMEOUT", "operation": "BUS_OWNER", "returncode": -128}),
            ({"code": "COMMAND_EXIT", "operation": "EVALUATE_SCRIPT", "returncode": 255},
             {"code": "COMMAND_EXIT", "operation": "EVALUATE_SCRIPT", "returncode": 255}),
            ({"code": "private" * 10000, "operation": "private account", "returncode": "private path"}, defaults),
            ({"code": [], "operation": {}, "returncode": True}, defaults),
            ({"code": PayloadString("COMMAND_EXIT"), "operation": PayloadString("UNIT_SHOW"),
              "returncode": PayloadInt(6)}, defaults),
            (None, defaults), ([], defaults), ("private payload", defaults), (PayloadDict(), defaults),
        ]
        for returncode in (-129, 256, 10**100, False, 6.0, float("nan"), object(), LayoutError):
            cases.append(({"returncode": returncode}, defaults))
        for actual in ("A" * 64, "b" * 63, "b" * 65, "b" * 64 + "\n", "é" * 64,
                       ["private payload"], PayloadString("b" * 64), None):
            cases.append(({"expectedSha256": "a" * 64, "actualSha256": actual}, defaults))
        cases.append(({"expectedSha256": "a" * 64}, defaults))
        for index, (facts, expected) in enumerate(cases):
            with self.subTest(case=index):
                error = LayoutError("synthetic private path/account/widget payload")
                error.facts = facts
                error.diagnostics = {"primary": {"raw": "private payload"}}
                self.session.failure = error
                self.assertTrue(self.host.refresh(""))
                self.wait()
                self.assertEqual(self.host.failureDiagnostics, expected)
                self.assertNotIn("private", self.host.problem)
                self.assertEqual(self.host.state, {"phase": "UNKNOWN"})

    def test_only_allowed_failure_fields_survive_even_with_valid_hashes(self):
        error = LayoutError("synthetic private payload")
        error.facts = {"code": "INVENTORY_MISMATCH", "operation": "TRANSACTION", "returncode": 0,
                       "expectedSha256": "a" * 64, "actualSha256": "b" * 64,
                       "path": "/synthetic/private", "account": "synthetic account",
                       "widgets": [{"configuration": "private"}], "exception": error,
                       "trace": object(), "stage": "private", "class": LayoutError}
        self.session.failure = error
        self.host.refresh(""); self.wait()
        self.assertEqual(self.host.failureDiagnostics, {
            "code": "INVENTORY_MISMATCH", "operation": "TRANSACTION", "returncode": 0,
            "expectedSha256": "a" * 64, "actualSha256": "b" * 64})

    def test_next_accepted_request_clears_diagnostics_and_next_failure_updates_them(self):
        changed = QSignalSpy(self.host.changed)
        self.session.failure = LayoutError("synthetic failure", code="COMMAND_EXIT", returncode=6)
        self.host.refresh(""); self.wait()
        prior_notifications = changed.count()
        self.session.failure = LayoutError("synthetic next failure", code="COMMAND_IO", operation="VERSION")
        self.session.gate.clear()
        self.assertTrue(self.host.refresh(""))
        self.assertEqual(self.host.failureDiagnostics, {})
        self.assertEqual(changed.count(), prior_notifications + 1)
        self.wait()
        self.assertEqual(self.host.failureDiagnostics,
                         {"code": "COMMAND_IO", "operation": "VERSION", "returncode": None})
        self.session.failure = False
        self.assertTrue(self.host.refresh(""))
        self.assertEqual(self.host.failureDiagnostics, {})
        self.wait()
        self.assertEqual(self.host.failureDiagnostics, {})
        self.assertEqual(self.host.state["phase"], "UNMANAGED")
        self.assertEqual(self.host.problem, "")

    def test_busy_and_closing_rejections_preserve_pending_and_completed_failure(self):
        self.session.failure = LayoutError("synthetic failure", code="COMMAND_EXIT", returncode=6)
        self.session.gate.clear()
        self.assertTrue(self.host.refresh(""))
        self.assertFalse(self.host.refresh(""))
        self.assertFalse(self.host.prepareApply("DP-1", [28]))
        self.assertFalse(self.host.prepareOperation("restore"))
        self.assertFalse(self.host.confirm())
        self.assertFalse(self.host.discard())
        self.assertEqual(self.host.failureDiagnostics, {})
        close = QSignalSpy(self.host.closeReady)
        self.assertFalse(self.host.requestClose())
        self.assertFalse(self.host.refresh(""))
        self.wait()
        expected = {"code": "COMMAND_EXIT", "operation": "TRANSACTION", "returncode": 6}
        self.assertEqual(self.host.failureDiagnostics, expected)
        self.assertEqual(close.count(), 1)
        for accepted in (self.host.refresh(""), self.host.prepareApply("DP-1", [28]),
                         self.host.prepareOperation("recover"), self.host.confirm(), self.host.discard()):
            self.assertFalse(accepted)
        self.assertTrue(self.host.requestClose())
        self.assertEqual(close.count(), 1)
        self.assertEqual(self.host.failureDiagnostics, expected)
        self.assertEqual(len(self.session.calls), 1)

    def test_rejected_actions_and_monitor_changes_do_not_erase_prior_failure(self):
        self.session.failure = LayoutError("synthetic failure", code="COMMAND_IO")
        self.host.refresh(""); self.wait()
        expected = {"code": "COMMAND_IO", "operation": "TRANSACTION", "returncode": None}
        self.assertFalse(self.host.prepareOperation("unsupported"))
        self.assertFalse(self.host.confirm())
        self.host.set_connectors(["DP-2"])
        self.assertEqual(self.host.failureDiagnostics, expected)
        self.assertTrue(self.host.discard())
        self.assertEqual(self.host.failureDiagnostics, {})

    def test_unknown_exceptions_have_fixed_diagnostics_without_retaining_the_exception(self):
        import gc
        import weakref
        class UnknownFailure(Exception):
            pass
        error = UnknownFailure("synthetic private path/account/widget payload")
        error.facts = {"code": "COMMAND_EXIT", "operation": "UNIT_SHOW", "returncode": 6}
        error_ref = weakref.ref(error)
        self.session.failure = error
        del error
        self.host.refresh(""); self.wait()
        self.session.failure = False
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        gc.collect()
        self.assertIsNone(error_ref())
        self.assertEqual(self.host.failureDiagnostics,
                         {"code": "UNEXPECTED_FAILURE", "operation": "TRANSACTION", "returncode": None})
        self.assertNotIn("private", self.host.problem)

    def test_controller_import_and_construction_keep_native_and_update_paths_lazy(self):
        from pathlib import Path
        import subprocess
        import sys
        program = """import sys
from scripts import panel_layout
def forbidden(*args, **kwargs):
    raise AssertionError('native runtime must stay unconstructed')
panel_layout.NativeRuntime = forbidden
from scripts.workspace_setup import WorkspaceController
controller = WorkspaceController(None, {}, [])
assert controller.failureDiagnostics == {}
assert not any(name.endswith('panel_layout_update') for name in sys.modules)
"""
        result = subprocess.run([sys.executable, "-B", "-c", program],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_widgets_gives_actionable_guidance_without_echoing_identifiers(self):
        def missing(connector=""):
            raise ValueError("selected native widgets are unavailable: private.widget.identifier")
        self.session.read = missing
        self.host.refresh(""); self.wait()
        self.assertIn("instal", self.host.problem.lower())
        self.assertNotIn("private", self.host.problem)

    def test_completed_transaction_with_failed_read_is_recorded_without_replay(self):
        execute = self.session.execute
        def fail_read_after_execute(token):
            result = execute(token)
            self.session.failure = True
            return result
        self.session.execute = fail_read_after_execute
        self.host.prepareApply("DP-1", [28]); self.wait()
        self.host.confirm(); self.wait()
        self.assertEqual(self.host.state, dict(phase="COMMITTED", verificationUnavailable=True))
        self.assertEqual(self.host.review, {})
        self.assertFalse(self.host.confirm())
        self.assertEqual(len([row for row in self.session.calls if row[0] == "execute"]), 1)

    def test_host_consumes_real_layout_transactions_in_its_worker(self):
        import tempfile
        from pathlib import Path
        from scripts import panel_layout as layout
        from scripts.workspace_layout import CompositionSession
        from test_panel_layout import FakeRuntime, manifest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"; config.mkdir()
            original = {}
            for name in layout.CONFIG_FILES:
                original[name] = ("private original " + name).encode()
                (config / name).write_bytes(original[name])
            runtime = FakeRuntime(config)
            store = layout.FileStore(config, root / "state")
            session = CompositionSession(runtime, store, manifest())
            self.host = WorkspaceController(session, manifest(), ["DP-1"])
            self.host.prepareApply("DP-1", [28]); self.wait()
            self.assertTrue(self.host.review)
            self.assertNotIn("stop", runtime.events)
            for action, phase in (("apply", "COMMITTED"), ("disable", "DISABLED"), ("restore", "RESTORED")):
                if action != "apply":
                    self.host.prepareOperation(action); self.wait()
                self.assertTrue(self.host.confirm()); self.wait()
                self.assertEqual(self.host.state["phase"], phase, self.host.problem)
            self.assertEqual({name: (config / name).read_bytes() for name in layout.CONFIG_FILES}, original)
            self.assertEqual(runtime.events.count("apply"), 1)
            self.assertEqual(runtime.events.count("remove-owned"), 1)

    def test_launch_uses_caller_defaults_for_relative_xdg_homes_before_gui_start(self):
        from pathlib import Path
        from unittest import mock
        from scripts import panel_layout, workspace_setup
        home = Path("/synthetic-workspace-home")
        class StartupObserved(Exception):
            pass
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "relative-config", "XDG_STATE_HOME": "relative-state"}), \
                mock.patch.object(Path, "home", return_value=home), \
                mock.patch.object(panel_layout, "NativeRuntime"), \
                mock.patch.object(panel_layout, "FileStore") as store, \
                mock.patch.object(workspace_setup, "QGuiApplication", side_effect=StartupObserved):
            with self.assertRaises(StartupObserved):
                workspace_setup.launch("plasma-fixture.service")
        store.assert_called_once_with(home / ".config", home / ".local/state/orla/layouts")


if __name__ == "__main__":
    unittest.main()
