"""The optional setup host owns one operation until its thread has finished."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

import threading
import time
import unittest
from PySide6.QtCore import QThread
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QSignalSpy, QTest
from scripts.workspace_setup import WorkspaceController


class Session:
    def __init__(self):
        self.calls = []
        self.gate = threading.Event()
        self.gate.set()
        self.failure = False

    def read(self, connector=""):
        self.calls.append(("read", connector, QThread.currentThread()))
        self.gate.wait(5)
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


if __name__ == "__main__":
    unittest.main()
