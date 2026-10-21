import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QPointF, QUrl, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression, QQmlProperty
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest


class ControlCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ControlCenterHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.center = self.window.findChild(QQuickItem, "controlCenterUnderTest")
        self.actions = self.window.findChild(QObject, "controlCenterActions")
        self.backend = self.window.findChild(QObject, "controlCenterBackend")
        self.battery = self.window.findChild(QObject, "controlCenterBattery")
        self.player = self.window.findChild(QObject, "controlCenterPlayer")
        QTest.qWait(30)

    def tearDown(self):
        if self.engine.rootObjects():
            self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.center, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def item(self, name):
        item = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(item, name)
        return item

    def calls(self):
        calls = self.backend.property("calls")
        return calls.toVariant() if hasattr(calls, "toVariant") else calls

    def activate(self, name):
        item = self.item(name)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())

    def test_loading_is_read_only_and_explicit_actions_use_closed_destinations(self):
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.evaluate("open('unknown')", self.actions))
        self.assertEqual(self.calls(), [])

        for name, target in (("controlCenterSoundAction", "kcm_pulseaudio"),
                             ("controlCenterPowerAction", "kcm_powerdevilprofilesconfig"),
                             ("controlCenterAllAction", "")):
            self.activate(name)
            self.assertEqual(self.calls()[-1], target)
        self.assertEqual(self.warnings, [])

    def test_action_failure_stays_in_its_card_and_does_not_claim_success(self):
        self.backend.setProperty("failingTarget", "kcm_pulseaudio")
        self.activate("controlCenterSoundAction")
        sound_error = self.item("controlCenterSoundError")
        self.assertTrue(sound_error.property("visible"))
        self.assertIn("encaminhar", sound_error.property("text"))
        self.assertNotIn("janela", sound_error.property("text").lower())
        self.assertFalse(self.item("controlCenterPowerError").property("visible"))
        self.assertEqual(self.calls(), [])

        self.activate("controlCenterPowerAction")
        self.assertEqual(self.calls(), ["kcm_powerdevilprofilesconfig"])
        self.assertTrue(sound_error.property("visible"))
        self.assertFalse(self.item("controlCenterPowerError").property("visible"))
        self.assertEqual(self.warnings, [])

    def test_external_text_is_bounded_plain_and_battery_zero_is_preserved(self):
        self.player.setProperty("track", "<b>" + "X" * 1000)
        self.player.setProperty("artist", "<i>" + "Y" * 1000)
        QTest.qWait(20)
        for name, prefix in (("controlCenterMediaTitle", "<b>"),
                             ("controlCenterMediaDetail", "<i>")):
            label = self.item(name)
            self.assertTrue(label.property("text").startswith(prefix))
            self.assertLessEqual(len(label.property("text")), 256)
            self.assertEqual(self.evaluate("textFormat", label), 0)
        self.assertEqual(self.item("controlCenterPowerTitle").property("text"), "0%")

        self.evaluate("player = null")
        self.battery.setProperty("status", "unavailable")
        self.battery.setProperty("summary", "Bateria indisponível")
        self.battery.setProperty("subtitle", "Serviço de energia indisponível")
        QTest.qWait(20)
        self.assertEqual(self.item("controlCenterMediaTitle").property("text"), "Nenhum player aberto")
        self.assertEqual(self.item("controlCenterPowerTitle").property("text"), "Bateria indisponível")
        self.assertTrue(self.item("controlCenterSoundAction").property("enabled"))
        self.assertTrue(self.item("controlCenterPowerAction").property("enabled"))
        self.assertEqual(self.warnings, [])

    def test_free_labels_follow_custom_foreground_without_recoloring_controls(self):
        foreground = QColor("#eaf4f1")
        muted = QColor("#a7b7c4")
        button = self.item("controlCenterSoundAction")
        selector = self.item("controlCenterOutputSelector")
        display_color_before = self.evaluate("contentItem.color", selector)
        button_text_before = self.evaluate("palette.buttonText", button)
        selector_text_before = self.evaluate("palette.buttonText", selector)

        self.assertTrue(QQmlProperty.write(self.center, "foreground", foreground))
        self.assertTrue(QQmlProperty.write(self.center, "muted", muted))
        self.assertTrue(QQmlProperty.write(self.center, "soundError", "Falha sintética"))
        self.assertTrue(QQmlProperty.write(self.center, "powerError", "Falha sintética"))
        self.assertTrue(QQmlProperty.write(self.center, "allError", "Falha sintética"))
        self.assertTrue(QQmlProperty.write(self.center.property("audio"), "error", "Falha sintética"))
        QTest.qWait(20)

        for name in ("controlCenterSoundHeading", "controlCenterMediaTitle",
                     "controlCenterAudioPercent", "controlCenterAudioStatus",
                     "controlCenterPowerHeading",
                     "controlCenterPowerTitle", "controlCenterSoundError",
                     "controlCenterPowerError", "controlCenterAllError"):
            self.assertEqual(self.item(name).property("color").name(), foreground.name(), name)
        for name in ("controlCenterMediaDetail", "controlCenterOutputHeading",
                     "controlCenterPowerDetail"):
            self.assertEqual(self.item(name).property("color").name(), muted.name(), name)

        self.assertEqual(self.evaluate("palette.buttonText", button), button_text_before)
        self.assertEqual(self.evaluate("palette.buttonText", selector), selector_text_before)
        self.assertEqual(self.evaluate("contentItem.color", selector), display_color_before)
        self.assertNotEqual(button_text_before.name(), foreground.name())
        self.assertEqual(self.warnings, [])

    def test_output_label_uses_one_style_renderer_and_keeps_literal_bounded_text(self):
        selector = self.item("controlCenterOutputSelector")
        self.evaluate("audioBackend.snapshot = {status:'ready',normalVolume:65536,defaultOutputId:'owned',outputs:[{id:'owned',label:'<b>'+ 'Z'.repeat(200),volumeRaw:0,muted:false,writable:true,isDefault:true}]}; audioBackend.revision += 1", self.window)
        QTest.qWait(20)
        text = selector.property("displayText")
        self.assertTrue(text.startswith("<b>"))
        self.assertLessEqual(len(text), 128)
        self.assertEqual(self.evaluate("contentItem.text", selector), text)
        self.assertEqual(self.evaluate("contentItem.length", selector), len(text))
        if os.environ.get("QT_QUICK_CONTROLS_STYLE") == "org.kde.desktop":
            self.assertEqual(self.evaluate("background.text", selector), text)
            self.assertFalse(self.evaluate("contentItem.visible", selector), "Native style already paints the noneditable label")
        else:
            self.assertTrue(self.evaluate("contentItem.visible", selector))
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.warnings, [])

    def test_keyboard_focus_reveals_each_action_in_a_narrow_view(self):
        self.window.setWidth(250)
        self.window.setHeight(240)
        QTest.qWait(30)
        scroll = self.item("controlCenterScroll")
        viewport = scroll.property("contentItem")
        for name in ("controlCenterSoundAction", "controlCenterPowerAction", "controlCenterAllAction"):
            control = self.item(name)
            control.forceActiveFocus()
            QTest.qWait(20)
            self.assertEqual(self.window.activeFocusItem(), control)
            top = control.mapToItem(viewport, QPointF(0, 0)).y()
            self.assertGreaterEqual(top, -0.5, name)
            self.assertLessEqual(top + control.height(), viewport.height() + 0.5, name)
            self.assertGreaterEqual(control.height(), 40)
            self.assertLessEqual(control.width(), self.center.width())
        self.assertEqual(self.warnings, [])

    def visual(self, name):
        # Repeater delegates exist only in the visual tree; search it in QML.
        found = self.evaluate("(function find(item) { if (item.objectName === %r) return item;"
                              " for (let i = 0; i < item.children.length; ++i) { const f = find(item.children[i]);"
                              " if (f) return f; } return null; })(contentItem)" % name, self.center)
        return found

    def brightness_calls(self):
        calls = self.window.findChild(QObject, "controlCenterBrightnessBackend").property("calls")
        return calls.toVariant() if hasattr(calls, "toVariant") else calls

    def test_brightness_reflects_the_service_and_confirms_each_change_in_order(self):
        state = self.window.findChild(QObject, "controlCenterBrightnessState")
        confirmations = QSignalSpy(state.confirmed)
        slider = self.visual("controlCenterBrightness")
        self.assertIsNotNone(slider)
        self.assertTrue(self.item("controlCenterBrightnessCard").isVisible())
        self.assertEqual(slider.property("value"), 50)
        self.assertEqual(self.visual("controlCenterBrightnessPercent").property("text"), "50%")
        self.assertEqual(self.brightness_calls(), [])
        slider.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(20)
        self.assertTrue(slider.property("visualFocus"))
        self.assertTrue(self.visual("controlCenterBrightnessFocus").isVisible())
        QTest.keyClick(self.window, Qt.Key_Right)
        QTest.keyClick(self.window, Qt.Key_Right)
        QTest.qWait(20)
        # One change in flight; the newer value waits for the service's readback.
        self.assertEqual(self.brightness_calls(), [{"id": "display0", "raw": 5100}])
        self.assertTrue(state.property("pendingAny"))
        self.assertEqual(slider.property("value"), 52)
        self.evaluate('brightnessBackend.report("display0", 5100)', self.window)
        QTest.qWait(20)
        self.assertEqual(self.brightness_calls(), [{"id": "display0", "raw": 5100}, {"id": "display0", "raw": 5200}])
        self.evaluate('brightnessBackend.report("display0", 5200)', self.window)
        QTest.qWait(20)
        self.assertFalse(state.property("pendingAny"))
        self.assertEqual(confirmations.count(), 2)
        # Readbacks update the same slider: focus and an ongoing drag survive.
        self.assertTrue(slider.hasActiveFocus())
        self.assertEqual(self.visual("controlCenterBrightnessPercent").property("text"), "52%")
        # A change made elsewhere (keys, Plasma applet) shows up without a write.
        self.evaluate('brightnessBackend.report("display0", 3000)', self.window)
        QTest.qWait(20)
        self.assertEqual(slider.property("value"), 30)
        self.assertEqual(len(self.brightness_calls()), 2)
        self.assertFalse(self.item("controlCenterBrightnessStatus").isVisible())
        self.assertEqual(self.warnings, [])

    def test_unconfirmed_or_refused_brightness_says_so_and_shows_the_current_value(self):
        slider = self.visual("controlCenterBrightness")
        self.assertIsNotNone(slider)
        status = self.item("controlCenterBrightnessStatus")
        slider.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Left)
        QTest.qWait(20)
        self.assertEqual(slider.property("value"), 49)
        QTest.qWait(450)
        self.assertTrue(status.isVisible())
        self.assertIn("não foi confirmado", status.property("text"))
        self.assertEqual(slider.property("value"), 50)
        self.evaluate("brightnessBackend.rejectWrites = true", self.window)
        QTest.keyClick(self.window, Qt.Key_Left)
        QTest.qWait(20)
        self.assertIn("recusou", status.property("text"))
        self.assertEqual(slider.property("value"), 50)
        self.assertEqual(len(self.brightness_calls()), 2)

    def test_readback_during_the_write_confirms_and_a_signalled_failure_ends_the_wait(self):
        state = self.window.findChild(QObject, "controlCenterBrightnessState")
        confirmations = QSignalSpy(state.confirmed)
        self.evaluate("brightnessBackend.reportDuringWrite = true", self.window)
        self.assertTrue(self.evaluate('request("display0", 61)', state))
        self.assertFalse(state.property("pendingAny"))
        self.assertEqual(confirmations.count(), 1)
        self.evaluate("brightnessBackend.reportDuringWrite = false", self.window)
        self.assertTrue(self.evaluate('request("display0", 40)', state))
        self.assertTrue(state.property("pendingAny"))
        self.evaluate('brightnessBackend.writeFailed("display0")', self.window)
        self.assertFalse(state.property("pendingAny"))
        self.assertIn("recusou", self.item("controlCenterBrightnessStatus").property("text"))
        self.assertEqual(self.evaluate('presentationPercent("display0")', state), 61)
        self.assertEqual(self.warnings, [])

    def test_missing_or_invalid_brightness_disables_only_its_card(self):
        card = self.item("controlCenterBrightnessCard")
        status = self.item("controlCenterBrightnessStatus")
        for snapshot, text in (('{status: "ready", displays: []}', "Nenhuma tela com brilho ajustável."),
                               ('{status: "absent", displays: []}', "Nenhuma tela com brilho ajustável."),
                               ('{status: "unavailable", displays: []}', "O controle de brilho do KDE está indisponível."),
                               ('{status: "ready", displays: [{id: "x", label: "", value: 11, max: 10, internal: false}]}',
                                "O controle de brilho do KDE está indisponível.")):
            with self.subTest(snapshot=snapshot):
                self.evaluate(f"brightnessBackend.snapshot = {snapshot}", self.window)
                QTest.qWait(20)
                self.assertTrue(card.isVisible())
                self.assertEqual(status.property("text"), text)
                self.assertIsNone(self.visual("controlCenterBrightness"))
                self.assertTrue(self.item("controlCenterAudioVolume").isEnabled())
        self.evaluate("brightness.backend = null", self.window)
        QTest.qWait(20)
        self.assertFalse(card.isVisible())
        self.assertEqual(self.brightness_calls(), [])
        self.assertEqual(self.warnings, [])

    def test_several_screens_are_named_and_never_go_below_one_percent(self):
        self.evaluate('brightnessBackend.snapshot = {status: "ready", displays: ['
                      '{id: "a", label: "Tela A", value: 50, max: 100, internal: true},'
                      '{id: "b", label: "Tela B", value: 4000, max: 10000, internal: false}]}', self.window)
        QTest.qWait(30)
        state = self.window.findChild(QObject, "controlCenterBrightnessState")
        self.assertTrue(self.evaluate('request("b", 0)', state))
        self.assertEqual(self.brightness_calls(), [{"id": "b", "raw": 100}])
        self.assertFalse(self.evaluate('request("missing", 40)', state))
        self.assertEqual(self.evaluate('presentationPercent("a")', state), 50)
        names = self.evaluate('displays.map(display => display.label).join("|")', state)
        self.assertEqual(names, "Tela A|Tela B")
        self.assertEqual(self.warnings, [])

    def test_full_volume_keeps_a_separate_visible_keyboard_focus_ring(self):
        self.evaluate("audioBackend.snapshot.outputs[0].volumeRaw = 65536; audioBackend.revision += 1", self.window)
        volume = self.item("controlCenterAudioVolume")
        QTest.qWait(20)
        self.assertEqual(volume.property("value"), 100)
        original_size = (volume.width(), volume.height())
        volume.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(30)
        self.assertTrue(volume.property("visualFocus"))
        track = volume.property("background")
        top = track.mapToScene(QPointF(track.width() / 2, 0))
        image = self.window.grabWindow()
        accent = self.evaluate("palette.highlight", volume)
        # At full volume the filled track must still have a gap below its outline.
        self.assertEqual(image.pixelColor(int(top.x()), int(top.y()) - 3), accent)
        self.assertNotEqual(image.pixelColor(int(top.x()), int(top.y()) - 1), accent)
        ring = self.item("controlCenterAudioVolumeFocus")
        self.assertEqual(self.evaluate("border.width", ring), 2)
        for corner in (QPointF(0, 0), QPointF(ring.width(), ring.height())):
            point = ring.mapToItem(volume, corner)
            self.assertGreaterEqual(point.x(), 0)
            self.assertLessEqual(point.x(), volume.width())
            self.assertGreaterEqual(point.y(), 0)
            self.assertLessEqual(point.y(), volume.height())
        self.assertEqual((volume.width(), volume.height()), original_size)
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
