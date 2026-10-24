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
        # Focus scrolls the Control Center to the control, as Tab does, so the click lands on it.
        # Let a just-shown error settle the layout first, or the scroll uses stale positions.
        QTest.qWait(20)
        item.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(20)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point.toPoint())

    def test_loading_is_read_only_and_explicit_actions_use_closed_destinations(self):
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.evaluate("open('unknown')", self.actions))
        self.assertEqual(self.calls(), [])

        for name, target in (("controlCenterSoundAction", "kcm_pulseaudio"),
                             ("controlCenterPowerAction", "kcm_powerdevilprofilesconfig"),
                             ("controlCenterNetworkAction", "kcm_networkmanagement"),
                             ("controlCenterBluetoothAction", "kcm_bluetooth"),
                             ("controlCenterAllAction", "")):
            if name == "controlCenterNetworkAction":
                # Network settings sit at the foot of the Wi-Fi page, as in macOS.
                self.activate("controlCenterWifiDetails")
                self.assertEqual(self.center.property("page"), "wifi")
            self.activate(name)
            self.assertEqual(self.calls()[-1], target)
            if name == "controlCenterNetworkAction":
                self.activate("controlCenterWifiBack")
                self.assertEqual(self.center.property("page"), "main")
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
        # macOS wording; the detail line says why nothing plays.
        self.assertEqual(self.item("controlCenterMediaTitle").property("text"), "Nada tocando")
        self.assertEqual(self.item("controlCenterMediaDetail").property("text"), "Nenhum player aberto")
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
        # The output caption left with the compact macOS layout; the selector keeps its accessible name.
        for name in ("controlCenterMediaDetail", "controlCenterPowerDetail"):
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

    def dnd_calls(self):
        calls = self.window.findChild(QObject, "controlCenterDndBackend").property("calls")
        return calls.toVariant() if hasattr(calls, "toVariant") else calls

    def test_do_not_disturb_follows_plasma_and_confirms_on_and_off(self):
        state = self.window.findChild(QObject, "controlCenterDndState")
        confirmations = QSignalSpy(state.confirmed)
        toggle = self.item("controlCenterDoNotDisturb")
        status = self.item("controlCenterDoNotDisturbStatus")
        self.assertTrue(self.item("controlCenterDoNotDisturbCard").isVisible())
        self.assertFalse(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Desativado")
        self.assertEqual(self.dnd_calls(), [])
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.dnd_calls(), [True])
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Ativando…")
        # Keyboard focus stays on the toggle while waiting; a repeat press is ignored.
        self.assertTrue(toggle.hasActiveFocus())
        self.assertTrue(toggle.property("visualFocus"))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.dnd_calls(), [True])
        self.evaluate("dndBackend.report({inhibited: true, until: Date.now() + 360 * 86400000})", self.window)
        QTest.qWait(20)
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(status.property("text"), "Ativado até você desativar")
        self.assertTrue(toggle.isEnabled())
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.dnd_calls(), [True, False])
        self.assertTrue(toggle.hasActiveFocus())
        self.evaluate("dndBackend.report({inhibited: false, until: 0})", self.window)
        QTest.qWait(20)
        self.assertEqual(confirmations.count(), 2)
        self.assertEqual(status.property("text"), "Desativado")
        self.assertFalse(toggle.property("checked"))
        self.assertEqual(self.warnings, [])

    def test_do_not_disturb_names_its_cause_and_never_fakes_success(self):
        toggle = self.item("controlCenterDoNotDisturb")
        status = self.item("controlCenterDoNotDisturbStatus")
        error = self.item("controlCenterDoNotDisturbError")
        self.evaluate('dndBackend.report({inhibited: true, byApplication: true, applications: ["Reunião sintética"]})', self.window)
        QTest.qWait(20)
        self.assertEqual(status.property("text"), "Ativado por Reunião sintética")
        self.assertTrue(toggle.property("checked"))
        self.evaluate('dndBackend.report({byApplication: false, applications: []})', self.window)
        QTest.qWait(20)
        self.assertEqual(status.property("text"), "Ativado por uma regra do KDE")
        # A KDE rule (full screen) keeps it on: the request times out honestly.
        self.assertTrue(self.evaluate("request(false)", self.window.findChild(QObject, "controlCenterDndState")))
        QTest.qWait(450)
        self.assertIn("continua ativo", error.property("text"))
        self.assertTrue(toggle.property("checked"))
        soon = "Date.now() + 2 * 3600000"
        self.evaluate(f"dndBackend.report({{until: {soon}}})", self.window)
        QTest.qWait(20)
        self.assertTrue(status.property("text").startswith("Ativado até "))
        self.assertNotIn("você desativar", status.property("text"))
        self.evaluate("dndBackend.rejectWrites = true", self.window)
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertIn("recusou", error.property("text"))
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(self.warnings, [])

    def test_do_not_disturb_unavailable_disables_only_its_card(self):
        card = self.item("controlCenterDoNotDisturbCard")
        self.evaluate('dndBackend.snapshot = {status: "unavailable"}', self.window)
        QTest.qWait(20)
        self.assertTrue(card.isVisible())
        self.assertFalse(self.item("controlCenterDoNotDisturb").isEnabled())
        self.assertEqual(self.item("controlCenterDoNotDisturbStatus").property("text"), "As notificações do KDE estão indisponíveis.")
        self.assertTrue(self.item("controlCenterAudioVolume").isEnabled())
        self.evaluate('dndBackend.snapshot = {status: "ready", inhibited: "yes", until: 0, byApplication: false, applications: []}', self.window)
        QTest.qWait(20)
        self.assertFalse(self.item("controlCenterDoNotDisturb").isEnabled())
        self.evaluate("dnd.backend = null", self.window)
        QTest.qWait(20)
        self.assertFalse(card.isVisible())
        self.assertEqual(self.dnd_calls(), [])
        self.assertEqual(self.warnings, [])

    def mic_calls(self):
        calls = self.window.findChild(QObject, "controlCenterMicBackend").property("calls")
        calls = calls.toVariant() if hasattr(calls, "toVariant") else calls
        return [(call["id"], call["muted"]) for call in calls]

    def test_microphone_mutes_the_default_input_once_the_service_confirms(self):
        state = self.window.findChild(QObject, "controlCenterMicState")
        confirmations = QSignalSpy(state.confirmed)
        toggle = self.item("controlCenterMicrophoneMute")
        status = self.item("controlCenterMicrophoneStatus")
        self.assertTrue(self.item("controlCenterMicrophoneCard").isVisible())
        self.assertFalse(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Ligado · Microfone sintético")
        # Opening the Control Center never writes.
        self.assertEqual(self.mic_calls(), [])
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.mic_calls(), [("input.synthetic", True)])
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Silenciando…")
        # Keyboard focus stays on the toggle while waiting; a repeat press is ignored.
        self.assertTrue(toggle.hasActiveFocus())
        self.assertTrue(toggle.property("visualFocus"))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(len(self.mic_calls()), 1)
        self.evaluate("micBackend.report({muted: true})", self.window)
        QTest.qWait(20)
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(status.property("text"), "Mudo · Microfone sintético")
        self.assertEqual(toggle.property("text"), "Ativar microfone")
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.mic_calls()[-1], ("input.synthetic", False))
        self.evaluate("micBackend.report({muted: false})", self.window)
        QTest.qWait(20)
        self.assertEqual(confirmations.count(), 2)
        self.assertFalse(toggle.property("checked"))
        # A change made outside Orla is shown as it is.
        self.evaluate("micBackend.report({muted: true})", self.window)
        QTest.qWait(20)
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(confirmations.count(), 2)
        self.assertEqual(self.warnings, [])

    def test_microphone_failures_never_look_like_success(self):
        toggle = self.item("controlCenterMicrophoneMute")
        error = self.item("controlCenterMicrophoneError")
        state = self.window.findChild(QObject, "controlCenterMicState")
        self.evaluate("micBackend.rejectWrites = true", self.window)
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertIn("recusou", error.property("text"))
        self.assertFalse(toggle.property("checked"))
        self.evaluate("micBackend.rejectWrites = false", self.window)
        # No confirmation: the request expires instead of claiming the mute.
        self.assertTrue(self.evaluate("request(true)", state))
        QTest.qWait(450)
        self.assertIn("não confirmou", error.property("text"))
        self.assertFalse(toggle.property("checked"))
        # The default input changing mid-request is not a confirmation either.
        self.assertTrue(self.evaluate("request(true)", state))
        self.evaluate('micBackend.snapshot = {status: "ready", input: {id: "input.other", label: "Outro", muted: true, writable: true}}', self.window)
        QTest.qWait(20)
        self.assertIn("mudou", error.property("text"))
        self.assertFalse(state.property("pending"))
        self.assertEqual(self.warnings, [])

    def test_microphone_absent_or_unavailable_disables_only_its_card(self):
        card = self.item("controlCenterMicrophoneCard")
        toggle = self.item("controlCenterMicrophoneMute")
        status = self.item("controlCenterMicrophoneStatus")
        for snapshot, text in (('{status: "absent", input: null}', "Nenhum microfone disponível"),
                               ('{status: "unavailable", input: null}', "Serviço de áudio indisponível"),
                               ('{status: "loading", input: null}', "Conectando ao áudio…")):
            with self.subTest(snapshot=snapshot):
                self.evaluate(f"micBackend.snapshot = {snapshot}", self.window)
                QTest.qWait(20)
                self.assertTrue(card.isVisible())
                self.assertFalse(toggle.isEnabled())
                self.assertEqual(status.property("text"), text)
                self.assertTrue(self.item("controlCenterAudioVolume").isEnabled())
        self.evaluate('micBackend.snapshot = {status: "ready", input: {id: "input.synthetic", label: "x", muted: "yes", writable: true}}', self.window)
        QTest.qWait(20)
        self.assertFalse(toggle.isEnabled())
        self.evaluate('micBackend.snapshot = {status: "ready", input: {id: "input.synthetic", label: "x", muted: false, writable: false}}', self.window)
        QTest.qWait(20)
        self.assertFalse(toggle.isEnabled())
        self.evaluate("mic.backend = null", self.window)
        QTest.qWait(20)
        self.assertFalse(card.isVisible())
        self.assertEqual(self.mic_calls(), [])
        self.assertEqual(self.warnings, [])


    def bluetooth_calls(self):
        calls = self.window.findChild(QObject, "controlCenterBluetoothBackend").property("calls")
        return list(calls.toVariant() if hasattr(calls, "toVariant") else calls)

    def test_bluetooth_switches_only_after_bluez_reports_it(self):
        state = self.window.findChild(QObject, "controlCenterBluetoothState")
        confirmations = QSignalSpy(state.confirmed)
        toggle = self.item("controlCenterBluetoothToggle")
        status = self.item("controlCenterBluetoothStatus")
        self.assertTrue(self.item("controlCenterBluetoothCard").isVisible())
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Conectado a Fone sintético")
        # Opening the Control Center never writes.
        self.assertEqual(self.bluetooth_calls(), [])
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.bluetooth_calls(), [False])
        self.assertFalse(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Desligando…")
        # Keyboard focus stays on the toggle while waiting; a repeat press is ignored.
        self.assertTrue(toggle.hasActiveFocus())
        self.assertTrue(toggle.property("visualFocus"))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.bluetooth_calls(), [False])
        self.evaluate("bluetoothBackend.report({enabled: false, blocked: true, connected: []})", self.window)
        QTest.qWait(20)
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(status.property("text"), "Desligado")
        self.assertEqual(toggle.property("text"), "Ligar Bluetooth")
        # A change made outside Orla is shown as it is, without a write.
        self.evaluate('bluetoothBackend.report({enabled: true, blocked: false, connected: ["Fone sintético", "Mouse sintético"]})', self.window)
        QTest.qWait(20)
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(status.property("text"), "2 dispositivos conectados")
        self.evaluate("bluetoothBackend.report({connected: []})", self.window)
        QTest.qWait(20)
        self.assertEqual(status.property("text"), "Ligado · nenhum dispositivo conectado")
        self.assertEqual(self.bluetooth_calls(), [False])
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(self.warnings, [])

    def test_bluetooth_failures_never_look_like_success(self):
        state = self.window.findChild(QObject, "controlCenterBluetoothState")
        toggle = self.item("controlCenterBluetoothToggle")
        error = self.item("controlCenterBluetoothError")
        self.evaluate("bluetoothBackend.rejectWrites = true", self.window)
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertIn("recusou", error.property("text"))
        self.assertTrue(toggle.property("checked"))
        self.evaluate("bluetoothBackend.rejectWrites = false", self.window)
        # No confirmation: the request expires instead of claiming the change.
        self.assertTrue(self.evaluate("request(false)", state))
        QTest.qWait(450)
        self.assertIn("não confirmou", error.property("text"))
        self.assertTrue(toggle.property("checked"))
        # Names stay bounded plain text, and a device list never shows while off.
        self.evaluate('bluetoothBackend.report({enabled: false, connected: ["<b>x</b>"]})', self.window)
        QTest.qWait(20)
        self.assertEqual(self.item("controlCenterBluetoothStatus").property("text"), "Desligado")
        self.assertEqual(self.evaluate("connected.length", state), 0)
        self.assertEqual(self.warnings, [])

    def test_bluetooth_absent_or_unavailable_disables_only_its_card(self):
        card = self.item("controlCenterBluetoothCard")
        toggle = self.item("controlCenterBluetoothToggle")
        status = self.item("controlCenterBluetoothStatus")
        for snapshot, text in (('{status: "absent"}', "Nenhum adaptador Bluetooth disponível"),
                               ('{status: "unavailable"}', "Serviço de Bluetooth indisponível"),
                               ('{status: "loading"}', "Lendo o Bluetooth…"),
                               ('{status: "ready", enabled: true, blocked: false, connected: "x"}', "Serviço de Bluetooth indisponível")):
            with self.subTest(snapshot=snapshot):
                self.evaluate(f"bluetoothBackend.snapshot = {snapshot}", self.window)
                QTest.qWait(20)
                self.assertTrue(card.isVisible())
                self.assertFalse(toggle.isEnabled())
                self.assertEqual(status.property("text"), text)
                self.assertTrue(self.item("controlCenterBluetoothAction").isEnabled())
                self.assertTrue(self.item("controlCenterWifiToggle").isEnabled())
        self.evaluate("bluetooth.backend = null", self.window)
        QTest.qWait(20)
        self.assertFalse(card.isVisible())
        self.assertEqual(self.bluetooth_calls(), [])
        self.assertEqual(self.warnings, [])

    def wifi_calls(self):
        calls = self.window.findChild(QObject, "controlCenterWifiBackend").property("calls")
        return list(calls.toVariant() if hasattr(calls, "toVariant") else calls)

    def test_wifi_switches_only_after_network_manager_reports_it(self):
        state = self.window.findChild(QObject, "controlCenterWifiState")
        confirmations = QSignalSpy(state.confirmed)
        toggle = self.item("controlCenterWifiToggle")
        status = self.item("controlCenterWifiStatus")
        self.assertTrue(self.item("controlCenterWifiCard").isVisible())
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Conectado a Rede sintética")
        # Opening the Control Center never writes.
        self.assertEqual(self.wifi_calls(), [])
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.wifi_calls(), [False])
        self.assertFalse(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Desligando…")
        # Keyboard focus stays on the toggle while waiting; a repeat press is ignored.
        self.assertTrue(toggle.hasActiveFocus())
        self.assertTrue(toggle.property("visualFocus"))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.wifi_calls(), [False])
        self.evaluate('wifiBackend.report({enabled: false, network: "", networks: []})', self.window)
        QTest.qWait(20)
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(status.property("text"), "Desligado")
        self.assertEqual(toggle.property("text"), "Ligar Wi-Fi")
        # A change made outside Orla is shown as it is, without a write.
        self.evaluate("wifiBackend.report({enabled: true})", self.window)
        QTest.qWait(20)
        self.assertTrue(toggle.property("checked"))
        self.assertEqual(status.property("text"), "Ligado · sem conexão")
        self.assertEqual(self.wifi_calls(), [False])
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(self.warnings, [])

    def test_wifi_failures_and_hardware_switch_never_look_like_success(self):
        state = self.window.findChild(QObject, "controlCenterWifiState")
        toggle = self.item("controlCenterWifiToggle")
        error = self.item("controlCenterWifiError")
        self.evaluate("wifiBackend.rejectWrites = true", self.window)
        toggle.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertIn("recusou", error.property("text"))
        self.assertTrue(toggle.property("checked"))
        self.evaluate("wifiBackend.rejectWrites = false", self.window)
        # No confirmation: the request expires instead of claiming the change.
        self.assertTrue(self.evaluate("request(false)", state))
        QTest.qWait(450)
        self.assertIn("não confirmou", error.property("text"))
        self.assertTrue(toggle.property("checked"))
        # A hardware switch keeps the radio off; software cannot turn it on.
        self.evaluate('wifiBackend.report({enabled: false, hardwareEnabled: false, network: ""})', self.window)
        QTest.qWait(20)
        self.assertEqual(self.item("controlCenterWifiStatus").property("text"), "Desligado por uma chave do computador")
        calls = len(self.wifi_calls())
        self.assertFalse(self.evaluate("request(true)", state))
        self.assertEqual(len(self.wifi_calls()), calls)
        self.assertIn("chave", error.property("text"))
        self.assertEqual(self.warnings, [])

    def test_wifi_absent_or_unavailable_disables_only_its_card(self):
        card = self.item("controlCenterWifiCard")
        toggle = self.item("controlCenterWifiToggle")
        status = self.item("controlCenterWifiStatus")
        for snapshot, text in (('{status: "absent"}', "Nenhum adaptador Wi-Fi disponível"),
                               ('{status: "unavailable"}', "Serviço de rede indisponível"),
                               ('{status: "loading"}', "Lendo o Wi-Fi…"),
                               ('{status: "ready", enabled: "yes", hardwareEnabled: true}', "Serviço de rede indisponível")):
            with self.subTest(snapshot=snapshot):
                self.evaluate(f"wifiBackend.snapshot = {snapshot}", self.window)
                QTest.qWait(20)
                self.assertTrue(card.isVisible())
                self.assertFalse(toggle.isEnabled())
                self.assertEqual(status.property("text"), text)
                self.assertTrue(self.item("controlCenterNetworkAction").isEnabled())
                self.assertTrue(self.item("controlCenterAudioVolume").isEnabled())
        self.evaluate("wifi.backend = null", self.window)
        QTest.qWait(20)
        self.assertFalse(card.isVisible())
        self.assertEqual(self.wifi_calls(), [])
        self.assertEqual(self.warnings, [])

    def test_wifi_page_lists_networks_in_range_and_returns_focus(self):
        backend = self.window.findChild(QObject, "controlCenterWifiBackend")
        self.activate("controlCenterWifiDetails")
        QTest.qWait(30)
        # Layout objects crash PySide's wrapper: read their visibility in QML.
        self.assertTrue(self.shown("controlCenterWifiPage"))
        self.assertFalse(self.shown("controlCenterTiles"))
        self.assertFalse(self.item("controlCenterAllAction").isVisible())
        self.assertEqual(backend.property("scans"), 1)
        self.assertTrue(self.item("controlCenterWifiBack").hasActiveFocus())
        rows = self.visual_all("controlCenterWifiNetwork")
        # Connected first, then by signal; names stay plain and bounded.
        self.assertEqual([row.property("spokenName") for row in rows],
                         ["Rede sintética, conectada", "Conectar a Café sintético",
                          "Conectar a Vizinho sintético, protegida por senha"])
        self.assertTrue(self.item("controlCenterWifiSwitch").property("checked"))
        disconnect = self.visual_all("controlCenterWifiDisconnect")
        self.assertEqual([item.isVisible() for item in disconnect], [True, False, False])
        # Opening the list never writes.
        self.assertEqual(self.wifi_calls(), [])
        self.activate("controlCenterWifiBack")
        QTest.qWait(30)
        self.assertEqual(self.center.property("page"), "main")
        self.assertTrue(self.item("controlCenterWifiDetails").hasActiveFocus())
        self.assertEqual(self.warnings, [])

    def shown(self, name):
        return self.evaluate("(function find(item) { if (item.objectName === %r) return item.visible;"
                             " for (let i = 0; i < item.children.length; ++i) { const f = find(item.children[i]);"
                             " if (f !== undefined) return f; } return undefined; })(contentItem)" % name, self.center)

    def visual_all(self, name):
        # Searched in QML: wrapping layout items in Python crashes PySide.
        found = self.evaluate("(function find(item, out) { if (item.objectName === %r) out.push(item);"
                              " for (let i = 0; i < item.children.length; ++i) find(item.children[i], out);"
                              " return out; })(contentItem, [])" % name, self.center)
        return list(found.toVariant() if hasattr(found, "toVariant") else found)

    def test_joining_a_network_waits_for_network_manager(self):
        state = self.window.findChild(QObject, "controlCenterWifiState")
        joined = QSignalSpy(state.networkJoined)
        self.activate("controlCenterWifiDetails")
        QTest.qWait(30)
        cafe = self.visual_all("controlCenterWifiNetwork")[1]
        cafe.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.wifi_calls(), [{"join": "/ap/2"}])
        self.assertEqual(state.property("joining"), "/ap/2")
        self.assertEqual(self.item("controlCenterWifiStatus").property("text"), "Conectando a Café sintético…")
        # A second choice is ignored until NetworkManager answers.
        self.assertFalse(self.evaluate('join("/ap/3")', state))
        self.assertEqual(len(self.wifi_calls()), 1)
        # Joining saves the network: it comes back with a new id, now connected.
        self.evaluate('wifiBackend.report({network: "Café sintético", networks: ['
                      '{id: "/settings/9", name: "Café sintético", strength: 55, secured: false, saved: true, state: "connected"},'
                      '{id: "/settings/1", name: "Rede sintética", strength: 82, secured: true, saved: true, state: "available"}]})',
                      self.window)
        QTest.qWait(20)
        self.assertEqual(joined.count(), 1)
        self.assertEqual(state.property("joining"), "")
        self.assertEqual(self.item("controlCenterWifiStatus").property("text"), "Conectado a Café sintético")
        self.assertEqual(state.property("networkError"), "")
        self.assertEqual(self.warnings, [])

    def test_leaving_and_join_failures_never_look_like_success(self):
        state = self.window.findChild(QObject, "controlCenterWifiState")
        left = QSignalSpy(state.networkLeft)
        error = self.item("controlCenterWifiNetworkError")
        self.activate("controlCenterWifiDetails")
        QTest.qWait(30)
        # Refused at once.
        self.evaluate("wifiBackend.rejectWrites = true", self.window)
        self.assertFalse(self.evaluate('join("/ap/2")', state))
        self.assertIn("recusou", error.property("text"))
        self.evaluate("wifiBackend.rejectWrites = false", self.window)
        # Reported failure from NetworkManager, with its message kept as plain bounded text.
        self.assertTrue(self.evaluate('join("/ap/3")', state))
        self.evaluate('wifiBackend.joinFailed("/settings/new", "<b>" + "senha incorreta ".repeat(40))', self.window)
        QTest.qWait(20)
        self.assertEqual(state.property("joining"), "")
        text = error.property("text")
        self.assertTrue(text.startswith("Não foi possível conectar a Vizinho sintético: <b>"))
        self.assertLessEqual(len(text), 220)
        self.assertEqual(self.evaluate("textFormat", error), 0)
        # No answer at all: the wait expires and says so.
        self.assertTrue(self.evaluate('join("/ap/2")', state))
        QTest.qWait(550)
        self.assertIn("ainda não confirmou", error.property("text"))
        # Leaving: only after the network stops being connected.
        disconnect = self.visual_all("controlCenterWifiDisconnect")[0]
        disconnect.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(20)
        self.assertEqual(self.wifi_calls()[-1], {"leave": "/settings/1"})
        self.assertEqual(state.property("leaving"), "/settings/1")
        self.assertEqual(left.count(), 0)
        self.evaluate('wifiBackend.report({network: "", networks: ['
                      '{id: "/settings/1", name: "Rede sintética", strength: 82, secured: true, saved: true, state: "available"}]})',
                      self.window)
        QTest.qWait(20)
        self.assertEqual(left.count(), 1)
        self.assertEqual(self.item("controlCenterWifiStatus").property("text"), "Ligado · sem conexão")
        self.assertEqual(self.warnings, [])

    def test_wifi_page_explains_a_radio_that_is_off(self):
        self.activate("controlCenterWifiDetails")
        QTest.qWait(30)
        self.evaluate('wifiBackend.report({enabled: false, network: "", networks: []})', self.window)
        QTest.qWait(20)
        self.assertEqual(self.item("controlCenterWifiListStatus").property("text"), "O Wi-Fi está desligado.")
        self.assertEqual(self.visual_all("controlCenterWifiNetwork"), [])
        # Ill-formed rows are dropped instead of shown.
        self.evaluate('wifiBackend.report({enabled: true, networks: [{id: "", name: "x", state: "available"},'
                      '{id: "/a", name: "  ", state: "available"}, {id: "/b", name: "Ok", state: "weird"},'
                      '{id: "/c", name: "Válida", strength: 400, state: "available"}]})', self.window)
        QTest.qWait(20)
        state = self.window.findChild(QObject, "controlCenterWifiState")
        networks = state.property("networks")
        networks = networks.toVariant() if hasattr(networks, "toVariant") else networks
        self.assertEqual([(item["id"], item["strength"]) for item in networks], [("/c", 100)])
        self.assertEqual(self.warnings, [])

    def power_calls(self):
        calls = self.window.findChild(QObject, "controlCenterPowerBackend").property("calls")
        return list(calls.toVariant() if hasattr(calls, "toVariant") else calls)

    def test_power_profile_changes_only_after_the_service_reports_it(self):
        state = self.window.findChild(QObject, "controlCenterPowerState")
        confirmations = QSignalSpy(state.confirmed)
        selector = self.item("controlCenterPowerProfile")
        status = self.item("controlCenterPowerProfileStatus")
        self.assertTrue(selector.isVisible())
        self.assertEqual(selector.property("displayText"), "Equilibrado")
        self.assertFalse(status.isVisible())
        # Opening the Control Center never writes.
        self.assertEqual(self.power_calls(), [])
        selector.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Down)
        QTest.qWait(20)
        self.assertEqual(self.power_calls(), ["performance"])
        self.assertEqual(selector.property("displayText"), "Desempenho")
        self.assertEqual(status.property("text"), "Aplicando Desempenho…")
        self.assertTrue(selector.hasActiveFocus())
        # A second choice while waiting is ignored and does not stay selected.
        QTest.keyClick(self.window, Qt.Key_Up)
        QTest.qWait(20)
        self.assertEqual(self.power_calls(), ["performance"])
        self.assertEqual(selector.property("displayText"), "Desempenho")
        self.assertEqual(selector.property("currentIndex"), 2)
        self.evaluate('powerBackend.report({current: "performance"})', self.window)
        QTest.qWait(20)
        self.assertEqual(confirmations.count(), 1)
        self.assertFalse(state.property("pending"))
        self.assertFalse(status.isVisible())
        # A change made outside Orla is shown as it is, without a write.
        self.evaluate('powerBackend.report({current: "power-saver"})', self.window)
        QTest.qWait(20)
        self.assertEqual(selector.property("displayText"), "Economia de energia")
        self.assertEqual(self.power_calls(), ["performance"])
        self.assertEqual(confirmations.count(), 1)
        self.assertEqual(self.warnings, [])

    def test_power_profile_failures_and_limits_never_look_like_success(self):
        state = self.window.findChild(QObject, "controlCenterPowerState")
        selector = self.item("controlCenterPowerProfile")
        status = self.item("controlCenterPowerProfileStatus")
        self.evaluate("powerBackend.rejectWrites = true", self.window)
        selector.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Up)
        QTest.qWait(20)
        self.assertIn("recusou", status.property("text"))
        self.assertEqual(selector.property("displayText"), "Equilibrado")
        self.evaluate("powerBackend.rejectWrites = false", self.window)
        # No confirmation: the request expires instead of claiming the profile.
        self.assertTrue(self.evaluate('request("power-saver")', state))
        QTest.qWait(450)
        self.assertIn("não confirmou", status.property("text"))
        self.assertEqual(selector.property("displayText"), "Equilibrado")
        # An asynchronous refusal from the service ends the wait at once.
        self.assertTrue(self.evaluate('request("power-saver")', state))
        self.evaluate('powerBackend.writeFailed("power-saver")', self.window)
        QTest.qWait(20)
        self.assertFalse(state.property("pending"))
        self.assertIn("recusou", status.property("text"))
        # Performance is not offered while the service inhibits it.
        self.evaluate('powerBackend.report({inhibitedReason: "lap-detected"})', self.window)
        QTest.qWait(20)
        calls = len(self.power_calls())
        self.assertFalse(self.evaluate('request("performance")', state))
        selector.forceActiveFocus(Qt.TabFocusReason)
        QTest.keyClick(self.window, Qt.Key_Down)
        QTest.qWait(20)
        self.assertEqual(len(self.power_calls()), calls)
        self.assertEqual(selector.property("displayText"), "Equilibrado")
        self.assertEqual(selector.property("currentIndex"), 1)
        self.assertEqual(status.property("text"), "Desempenho indisponível: o computador pode estar no colo.")
        # A profile held by an application says who holds it.
        self.evaluate('powerBackend.report({inhibitedReason: "", current: "performance", '
                      'holds: [{application: "GameMode", profile: "performance"}]})', self.window)
        QTest.qWait(20)
        self.assertEqual(status.property("text"), "Mantido por GameMode")
        self.assertEqual(self.warnings, [])

    def test_power_profile_absent_or_unavailable_keeps_the_energy_card(self):
        selector = self.item("controlCenterPowerProfile")
        status = self.item("controlCenterPowerProfileStatus")
        for snapshot, text in (('{status: "absent"}', "Este sistema não oferece perfis de energia."),
                               ('{status: "unavailable"}', "Serviço de energia indisponível"),
                               ('{status: "loading"}', "Lendo o perfil de energia…"),
                               ('{status: "ready", profiles: ["custom"], current: "custom"}', "Este sistema não oferece perfis de energia.")):
            with self.subTest(snapshot=snapshot):
                self.evaluate(f"powerBackend.snapshot = {snapshot}", self.window)
                QTest.qWait(20)
                self.assertFalse(selector.isVisible())
                self.assertEqual(status.property("text"), text)
                self.assertTrue(self.item("controlCenterPowerCard").isVisible())
                self.assertTrue(self.item("controlCenterPowerAction").isEnabled())
        # Unknown names are dropped; an unknown current profile is not shown as a known one.
        self.evaluate('powerBackend.snapshot = {status: "ready", profiles: ["balanced", "custom", "power-saver"], current: "custom"}', self.window)
        QTest.qWait(20)
        self.assertTrue(selector.isVisible())
        self.assertEqual(self.evaluate("power.profiles", self.window).toVariant()
                         if hasattr(self.evaluate("power.profiles", self.window), "toVariant")
                         else self.evaluate("power.profiles", self.window), ["power-saver", "balanced"])
        self.assertEqual(selector.property("displayText"), "Perfil desconhecido")
        self.evaluate("power.backend = null", self.window)
        QTest.qWait(20)
        self.assertFalse(selector.isVisible())
        self.assertFalse(status.isVisible())
        self.assertEqual(self.power_calls(), [])
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
