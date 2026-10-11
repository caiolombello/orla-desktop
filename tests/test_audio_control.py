import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtTest import QTest


class AudioControlStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("AudioControlHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.backend = self.window.findChild(QObject, "audioBackend")
        self.audio = self.window.findChild(QObject, "audioState")
        QTest.qWait(20)

    def tearDown(self):
        self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.audio, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def calls(self):
        calls = self.backend.property("calls")
        return calls.toVariant() if hasattr(calls, "toVariant") else calls

    def publish(self, expression):
        self.evaluate(f"publish({expression})", self.backend)
        QTest.qWait(10)

    def test_initial_snapshot_and_external_changes_are_read_only(self):
        self.assertEqual(self.audio.property("status"), "ready")
        self.assertEqual(self.audio.property("defaultOutputId"), "speakers")
        self.assertEqual(self.audio.property("confirmedVolume"), 50)
        self.assertFalse(self.audio.property("muted"))
        self.assertEqual(self.calls(), [])
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'<b>'+ 'X'.repeat(300),volumeRaw:0,muted:true,writable:true,isDefault:true}]})")
        self.assertEqual(self.audio.property("confirmedVolume"), 0)
        self.assertTrue(self.audio.property("muted"))
        outputs = self.audio.property("outputs")
        outputs = outputs.toVariant() if hasattr(outputs, "toVariant") else outputs
        self.assertLessEqual(len(outputs[0]["label"]), 128)
        self.assertTrue(outputs[0]["label"].startswith("<b>"))
        self.assertEqual(self.calls(), [])

    def test_volume_is_finite_clamped_and_does_not_change_mute(self):
        self.assertFalse(self.evaluate("requestVolume(50)"))
        self.assertEqual(self.calls(), [])
        cases = [(-8, 0), (1, 655), (50, 32768), (100, 65536)]
        for requested, raw in cases:
            self.assertTrue(self.evaluate(f"requestVolume({requested})"))
            self.assertEqual(self.calls()[-1], {"kind": "volume", "id": "speakers", "value": raw})
            self.publish(f"({{status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{{id:'speakers',label:'Alto-falantes',volumeRaw:{raw},muted:false,writable:true,isDefault:true}}]}})")
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:true}]})")
        self.assertTrue(self.evaluate("requestVolume(180)"))
        self.assertEqual(self.calls()[-1], {"kind": "volume", "id": "speakers", "value": 65536})
        before = len(self.calls())
        self.assertFalse(self.evaluate("requestVolume(NaN)"))
        self.assertFalse(self.evaluate("requestVolume(Infinity)"))
        self.assertEqual(len(self.calls()), before)
        self.assertFalse(any(call["kind"] == "mute" for call in self.calls()))

    def test_readback_confirms_observed_state_without_claiming_origin(self):
        self.assertTrue(self.evaluate("requestVolume(80)"))
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        self.assertEqual(self.audio.property("confirmedVolume"), 50)
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:52429,muted:false,writable:true,isDefault:true}]})")
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertEqual(self.audio.property("confirmedVolume"), 80)
        self.assertEqual(self.audio.property("error"), "")

    def test_latest_request_restarts_timeout_and_timeout_restores_confirmed_state(self):
        self.audio.setProperty("confirmationTimeout", 100)
        self.assertTrue(self.evaluate("beginVolumeGesture()"))
        self.assertTrue(self.evaluate("requestGestureVolume(20)"))
        QTest.qWait(60)
        self.assertTrue(self.evaluate("requestGestureVolume(30)"))
        QTest.qWait(60)
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        QTest.qWait(70)
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertEqual(self.audio.property("confirmedVolume"), 50)
        self.assertIn("confirm", self.audio.property("error").lower())
        self.evaluate("endVolumeGesture()")

    def test_different_pending_kinds_are_serialized_without_losing_supervision(self):
        self.audio.setProperty("confirmationTimeout", 90)
        self.assertTrue(self.evaluate("requestVolume(80)"))
        self.assertFalse(self.evaluate("requestMute(true)"))
        self.assertFalse(self.evaluate("requestDefaultOutput('headphones')"))
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        self.assertEqual(len(self.calls()), 1)
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:true,writable:true,isDefault:true},{id:'headphones',label:'Fones',volumeRaw:16384,muted:false,writable:true,isDefault:false}]})")
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        QTest.qWait(110)
        self.assertIn("confirm", self.audio.property("error").lower())

        self.assertTrue(self.evaluate("requestMute(false)"))
        self.assertFalse(self.evaluate("requestVolume(50)"))
        self.assertFalse(self.evaluate("requestDefaultOutput('speakers')"))
        self.assertEqual(self.audio.property("pendingKind"), "mute")
        self.assertEqual(self.calls()[-1]["kind"], "mute")
        self.assertNotEqual(self.audio.property("presentationOutputId"), "headphones")

    def test_same_volume_drag_can_counter_an_earlier_pending_request(self):
        self.assertTrue(self.evaluate("beginVolumeGesture()"))
        self.assertTrue(self.evaluate("requestGestureVolume(80)"))
        self.assertTrue(self.evaluate("requestGestureVolume(50)"))
        self.assertEqual([call["value"] for call in self.calls()], [52429, 32768])
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:true}]})")
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.evaluate("endVolumeGesture()")

    def test_volume_drag_blocks_when_target_or_service_changes(self):
        self.assertTrue(self.evaluate("beginVolumeGesture()"))
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'headphones',outputs:[{id:'headphones',label:'Fones',volumeRaw:16384,muted:false,writable:true,isDefault:true}]})")
        self.assertTrue(self.audio.property("volumeGestureBlocked"))
        before = len(self.calls())
        self.assertFalse(self.evaluate("requestGestureVolume(70)"))
        self.assertEqual(len(self.calls()), before)
        self.evaluate("endVolumeGesture()")

        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:true}]})")
        self.assertTrue(self.evaluate("beginVolumeGesture()"))
        self.publish("({status:'loading',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:true,isDefault:true}]})")
        self.assertTrue(self.audio.property("volumeGestureBlocked"))
        self.assertFalse(self.evaluate("requestGestureVolume(70)"))
        self.assertEqual(len(self.calls()), before)
        self.evaluate("endVolumeGesture()")

    def test_pending_volume_is_presented_only_for_the_current_writable_output(self):
        self.assertTrue(self.evaluate("beginVolumeGesture()"))
        self.assertTrue(self.evaluate("requestGestureVolume(80)"))
        self.assertEqual(self.audio.property("presentationVolume"), 80)

        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:false,writable:false,isDefault:true}]})")
        self.assertEqual(self.audio.property("pendingKind"), "volume")
        self.assertEqual(self.audio.property("confirmedVolume"), 50)
        self.assertEqual(self.audio.property("presentationVolume"), 50)
        self.assertTrue(self.audio.property("volumeGestureBlocked"))

        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'headphones',outputs:[{id:'headphones',label:'Fones',volumeRaw:16384,muted:false,writable:true,isDefault:true}]})")
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertEqual(self.audio.property("confirmedVolume"), 25)
        self.assertEqual(self.audio.property("presentationVolume"), 25)
        self.assertIn("não está mais disponível", self.audio.property("error"))
        self.evaluate("endVolumeGesture()")

    def test_mute_and_default_output_require_matching_readback(self):
        self.assertFalse(self.evaluate("requestMute(false)"))
        self.assertEqual(self.calls(), [])
        self.assertTrue(self.evaluate("requestMute(true)"))
        self.assertEqual(self.calls()[-1], {"kind": "mute", "id": "speakers", "value": True})
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'speakers',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:true,writable:true,isDefault:true},{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:false}]})")
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertTrue(self.audio.property("muted"))

        before = len(self.calls())
        self.assertFalse(self.evaluate("requestDefaultOutput('speakers')"))
        self.assertEqual(len(self.calls()), before)
        self.assertTrue(self.evaluate("requestDefaultOutput('headphones')"))
        self.assertEqual(self.calls()[-1], {"kind": "default-output", "id": "headphones"})
        self.assertEqual(self.audio.property("pendingKind"), "default-output")
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'headphones',outputs:[{id:'speakers',label:'Alto-falantes',volumeRaw:32768,muted:true,writable:true,isDefault:false},{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:true}]})")
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertEqual(self.audio.property("defaultOutputId"), "headphones")
        self.assertEqual(self.audio.property("confirmedVolume"), 25)

        self.assertTrue(self.evaluate("requestDefaultOutput('speakers')"))
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'headphones',outputs:[{id:'headphones',label:'Fones',volumeRaw:16384,muted:true,writable:true,isDefault:true}]})")
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertIn("não está mais disponível", self.audio.property("error"))

    def test_failure_removal_inactive_and_retry_are_local(self):
        self.backend.setProperty("rejectWrites", True)
        self.assertFalse(self.evaluate("requestMute(true)"))
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertTrue(self.audio.property("error"))
        self.assertFalse(self.evaluate("retry()"))
        self.assertEqual(self.calls()[-1], {"kind": "retry"})

        self.backend.setProperty("rejectWrites", False)
        self.assertTrue(self.evaluate("requestVolume(70)"))
        self.publish("({status:'ready',normalVolume:65536,defaultOutputId:'',outputs:[]})")
        self.assertEqual(self.audio.property("status"), "absent")
        self.assertEqual(self.audio.property("pendingKind"), "")
        self.assertTrue(self.audio.property("error"))
        before = len(self.calls())
        self.audio.setProperty("active", False)
        QTest.qWait(10)
        self.assertEqual(self.audio.property("status"), "inactive")
        self.assertFalse(self.evaluate("requestVolume(10)"))
        self.assertEqual(len(self.calls()), before)
        self.assertEqual(self.warnings, [])


class NativeAdapterSourceTests(unittest.TestCase):
    def test_private_module_is_isolated_and_uses_pinned_api(self):
        root = Path(__file__).parents[1]
        native = (root / "package/contents/ui/NativePulseAudio.qml").read_text()
        self.assertIn("import org.kde.plasma.private.volume as PlasmaPA", native)
        self.assertEqual(native.count("PlasmaPA.SinkModel"), 1)
        self.assertIn("PlasmaPA.Context.State.Ready", native)
        self.assertIn('sinks.role("PulseObject")', native)
        self.assertIn("PlasmaPA.Server.defaultSink", native)
        self.assertNotIn("SinkInputModel", native)
        self.assertNotIn("GlobalService", native)
        self.assertNotIn("switchStreams", native)

        importers = []
        for path in (root / "package/contents/ui").glob("*.qml"):
            if "org.kde.plasma.private.volume" in path.read_text():
                importers.append(path.name)
        self.assertEqual(importers, ["NativePulseAudio.qml"])


if __name__ == "__main__":
    unittest.main()
