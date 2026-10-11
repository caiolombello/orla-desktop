import json
import os
from pathlib import Path
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")
os.environ.setdefault("QT_QPA_PLATFORMTHEME", "")

from PySide6.QtCore import QCoreApplication, QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "EventStateHarness.qml"
EVENT_STATE = ROOT / "package" / "contents" / "ui" / "EventState.qml"


class EventStatePortableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(
            lambda warnings: self.warnings.extend(warning.toString() for warning in warnings)
        )
        self.engine.load(QUrl.fromLocalFile(str(HARNESS)))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.root = self.engine.rootObjects()[0]
        self.state = self.root.findChild(QObject, "eventState")
        self.assertIsNotNone(self.state)

    def tearDown(self):
        self.engine.deleteLater()
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source):
        expression = QQmlExpression(self.engine.rootContext(), self.state, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def snapshot(self):
        return json.loads(self.evaluate("JSON.stringify({current:current,pending:pending,count:count})"))

    def announcements(self):
        value = self.root.property("announcements")
        return value.toVariant() if hasattr(value, "toVariant") else value

    @staticmethod
    def completion(title="Foco concluído"):
        return {"kind": "completion", "key": "pomodoro:completion", "scope": "global",
                "title": title, "detail": "Hora de uma pausa!"}

    @staticmethod
    def audio(target="speakers", value=50, action="volume", scope="profile:work", generation=4):
        if action == "mute":
            value = bool(value)
        elif action == "default-output":
            value = target
        return {"kind": "audio", "action": action, "targetId": target,
                "originScope": scope, "contextGeneration": generation, "value": value,
                "title": f"Audio {target}", "detail": f"Value {value}"}

    def submit(self, event, timestamp):
        return self.evaluate(f"submit({json.dumps(event)},{timestamp})")

    def test_standalone_fixture_uses_only_portable_qt_imports(self):
        sources = (HARNESS.read_text(encoding="utf-8"), EVENT_STATE.read_text(encoding="utf-8"))
        imports = [line.strip() for source in sources for line in source.splitlines()
                   if line.strip().startswith("import ")]
        self.assertEqual(imports.count('import "../package/contents/ui" as DockUI'), 1)
        module_imports = [line.split()[1] for line in imports if not line.startswith('import "')]
        self.assertTrue(module_imports)
        self.assertEqual(set(module_imports), {"QtQuick"})
        self.assertEqual(self.state.objectName(), "eventState")

    def test_malformed_closed_union_is_rejected_without_state_change(self):
        self.assertTrue(self.submit(self.completion(), 1000))
        before = self.snapshot()
        malformed = [
            {**self.completion(), "extra": True},
            {**self.audio(), "value": 101},
            {**self.audio(), "targetId": "bad\noutput"},
            {**self.audio(), "originScope": "profile:other"},
            {**self.audio(), "contextGeneration": 3},
            {"kind": "unknown"},
        ]
        for event in malformed:
            with self.subTest(event=event):
                self.assertFalse(self.submit(event, 1100))
                self.assertEqual(self.snapshot(), before)

    def test_coalescence_priority_and_exact_expiry_promote_live_completion(self):
        self.assertTrue(self.submit(self.completion(), 1000))
        self.assertTrue(self.submit(self.audio(value=20), 1100))
        first = self.snapshot()["current"]
        self.assertEqual((first["kind"], first["priority"]), ("audio", 20))
        self.assertTrue(self.submit(self.audio(value=70), 1200))
        current = self.snapshot()["current"]
        self.assertEqual(current["sequence"], first["sequence"])
        self.assertEqual((current["value"], current["deadline"]), (70, 3000))
        self.assertFalse(self.evaluate("advance(2999)"))
        self.assertTrue(self.evaluate("advance(3000)"))
        promoted = self.snapshot()["current"]
        self.assertEqual(promoted["kind"], "completion")
        self.assertEqual(len(self.announcements()), 1)

    def test_public_audio_identities_capacity_and_drop_return_are_bounded(self):
        identities = [
            self.audio("shared", 25, "volume"),
            self.audio("shared", True, "mute"),
            self.audio("shared", "ignored", "default-output"),
        ] + [self.audio(f"out-{index}", 40) for index in range(5)]
        for index, event in enumerate(identities):
            self.assertTrue(self.submit(event, 1000 + index))
        self.assertEqual(self.state.property("count"), 8)
        self.assertFalse(self.submit(self.completion(), 1100))
        incoming = self.audio("new-output", 60)
        self.assertTrue(self.submit(incoming, 1101))
        events = json.loads(self.evaluate("JSON.stringify(allEvents())"))
        self.assertEqual(len(events), 8)
        self.assertIn("new-output", [event["targetId"] for event in events])
        self.assertNotIn(("mute", "shared"), [(event["action"], event["targetId"])
                                               for event in events])

    def test_independent_gates_selectively_clear_and_preserve_completion_fallback(self):
        self.state.setProperty("completionEnabled", False)
        self.assertFalse(self.submit(self.completion(), 1000))
        self.assertTrue(self.submit(self.audio(), 1001))
        self.state.setProperty("completionEnabled", True)
        self.assertTrue(self.submit(self.completion(), 1002))
        self.state.setProperty("activeContextGeneration", 5)
        events = json.loads(self.evaluate("JSON.stringify(allEvents())"))
        self.assertEqual([event["kind"] for event in events], ["completion"])
        self.state.setProperty("audioEnabled", False)
        self.assertEqual(self.state.property("count"), 1)
        self.state.setProperty("completionEnabled", False)
        self.assertEqual(self.state.property("count"), 0)

    def test_audio_quiet_and_maximum_use_latest_name_once(self):
        self.assertEqual((self.state.property("audioQuietDelay"),
                          self.state.property("audioMaximumDelay")), (200, 1000))
        self.assertTrue(self.submit(self.audio(value=20), 1000))
        self.assertTrue(self.submit(self.audio(value=80), 1100))
        self.assertTrue(self.evaluate("fireAudioQuiet(1300)"))
        self.assertFalse(self.evaluate("fireAudioMaximum(2000)"))
        announced = self.announcements()
        self.assertEqual(len(announced), 1)
        self.assertIn("Value 80", announced[0]["accessibleName"])

        self.evaluate("clear()")
        self.root.setProperty("announcements", [])
        for timestamp, value in ((3000, 10), (3190, 30), (3380, 50), (3570, 70)):
            self.assertTrue(self.submit(self.audio("burst", value), timestamp))
        self.assertTrue(self.evaluate("fireAudioMaximum(4000)"))
        self.assertEqual(len(self.announcements()), 1)
        self.assertIn("Value 70", self.announcements()[0]["accessibleName"])

    def test_queued_audio_stays_silent_and_lifecycle_cancellation_promotes_completion(self):
        self.assertTrue(self.submit(self.audio("current", 20), 1000))
        self.assertTrue(self.submit(self.audio("queued", 30), 1001))
        self.assertTrue(self.submit(self.completion(), 1002))
        self.assertEqual(self.announcements(), [])
        self.state.setProperty("activeScope", "profile:personal")
        current = self.snapshot()["current"]
        self.assertEqual(current["kind"], "completion")
        self.assertEqual(len(self.announcements()), 1)
        self.assertFalse(self.evaluate("fireAudioQuiet(1200)"))
        self.assertEqual(len(self.announcements()), 1)

    def test_completion_announces_once_when_presented_and_not_again_when_coalesced(self):
        self.assertTrue(self.submit(self.audio(), 1000))
        self.assertTrue(self.submit(self.completion("Primeiro"), 1001))
        self.assertEqual(self.announcements(), [])
        self.assertTrue(self.evaluate("dismiss(1100)"))
        self.assertEqual(len(self.announcements()), 1)
        self.assertTrue(self.submit(self.completion("Atualizado"), 1200))
        self.assertEqual(len(self.announcements()), 1)
        current = self.snapshot()["current"]
        self.assertEqual((current["title"], current["announced"]), ("Atualizado", True))


if __name__ == "__main__":
    unittest.main()
