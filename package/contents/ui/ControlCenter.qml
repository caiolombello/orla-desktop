import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

Controls.Control {
    id: root
    required property var actions
    required property var player
    required property var battery
    required property var audio
    // Optional: hosts without a brightness state show no display card.
    property var brightness: null
    // Optional: hosts without a Do Not Disturb state show no focus card.
    property var doNotDisturb: null
    // Optional: hosts without a microphone state show no microphone card.
    property var microphone: null
    property color foreground: palette.windowText
    property color muted: palette.windowText
    property bool playing: false
    property string soundError: ""
    property string powerError: ""
    property string allError: ""
    implicitWidth: 310
    // Tall enough to show every module (display and focus cards included)
    // without scrolling on common screens; the popup budget caps short ones.
    implicitHeight: Math.min(body.implicitHeight + topPadding + bottomPadding, 700)
    Layout.fillHeight: true
    Layout.minimumHeight: 1
    Accessible.role: Accessible.Pane
    Accessible.name: qsTr("Central de Controle")

    function boundedText(value, maximum) {
        return String(value || "").slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function outputIndex(id) {
        for (let index = 0; index < audio.outputs.length; ++index) {
            if (audio.outputs[index].id === id) return index;
        }
        return -1;
    }
    function request(kind) {
        const dispatched = actions && actions.open(kind);
        const message = dispatched ? "" : qsTr("Não foi possível encaminhar esta ação ao KDE. Tente novamente.");
        if (kind === "sound") soundError = message;
        else if (kind === "power") powerError = message;
        else if (kind === "all") allError = message;
        return Boolean(dispatched);
    }
    function microphoneText() {
        const mic = root.microphone;
        if (!mic) return "";
        if (mic.status === "unavailable") return qsTr("Serviço de áudio indisponível");
        if (mic.status === "loading") return qsTr("Conectando ao áudio…");
        if (mic.status === "absent") return qsTr("Nenhum microfone disponível");
        if (mic.pending) return mic.desired ? qsTr("Silenciando…") : qsTr("Ativando…");
        const name = boundedText(mic.label, 128);
        return mic.muted ? qsTr("Mudo · %1").arg(name) : qsTr("Ligado · %1").arg(name);
    }
    function doNotDisturbText() {
        const mode = root.doNotDisturb;
        if (!mode) return "";
        if (mode.status === "unavailable") return qsTr("As notificações do KDE estão indisponíveis.");
        if (mode.status === "loading") return qsTr("Lendo o estado das notificações…");
        if (mode.pending) return mode.desired ? qsTr("Ativando…") : qsTr("Desativando…");
        if (!mode.inhibited) return qsTr("Desativado");
        const now = Date.now();
        if (mode.until > now) {
            if (mode.until - now > 300 * 86400000) return qsTr("Ativado até você desativar");
            return qsTr("Ativado até %1").arg(new Date(mode.until).toLocaleString(Qt.locale(), Locale.ShortFormat));
        }
        if (mode.byApplication && mode.applications.length > 0)
            return qsTr("Ativado por %1").arg(boundedText(mode.applications.join(", "), 128));
        return qsTr("Ativado por uma regra do KDE");
    }
    function reveal(control) {
        const viewport = scroll.contentItem;
        if (!control || !control.activeFocus || !viewport || viewport.contentY === undefined) return;
        const point = control.mapToItem(viewport, 0, 0);
        let offset = viewport.contentY;
        if (point.y < 0) offset += point.y;
        else if (point.y + control.height > viewport.height)
            offset += point.y + control.height - viewport.height;
        viewport.contentY = Math.max(0, Math.min(offset, Math.max(0, viewport.contentHeight - viewport.height)));
    }
    contentItem: Controls.ScrollView {
        id: scroll
        objectName: "controlCenterScroll"
        implicitWidth: root.implicitWidth
        contentWidth: availableWidth
        contentHeight: body.implicitHeight
        clip: true
        // Keep the scrollbar off the cards' edges.
        rightPadding: Controls.ScrollBar.vertical.visible ? Controls.ScrollBar.vertical.width + Style.space.xs : 0
        Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: Style.space.sm

            Card {
                objectName: "controlCenterSoundCard"
                Layout.fillWidth: true
                radius: Style.radius.module
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Style.space.md
                    // Now playing: the same live artwork as the dock's music icon.
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Style.space.md
                        LiveIcon {
                            Layout.preferredWidth: Style.size.target + Style.space.xs
                            Layout.preferredHeight: Style.size.target + Style.space.xs
                            Layout.alignment: Qt.AlignTop
                            kind: "music"
                            live: Boolean(root.player)
                            info: ({art: root.player ? root.player.artUrl || "" : "", active: root.playing})
                            animationDuration: 0
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Controls.Label {
                                objectName: "controlCenterSoundHeading"
                                Layout.fillWidth: true
                                text: qsTr("Som e mídia")
                                font.pixelSize: Style.type.caption
                                font.weight: Style.weight.bold
                                textFormat: Text.PlainText
                                color: root.foreground
                                opacity: 0.72
                            }
                            Controls.Label {
                                objectName: "controlCenterMediaTitle"
                                Layout.fillWidth: true
                                text: root.player ? root.boundedText(root.player.track || root.player.identity, 256) || qsTr("Player sem título")
                                                  : qsTr("Nenhum player aberto")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                font.weight: Style.weight.demiBold
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterMediaDetail"
                                Layout.fillWidth: true
                                text: root.player ? root.boundedText(root.player.artist || root.player.identity, 256)
                                                  : qsTr("Mídia MPRIS indisponível")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                color: root.muted
                            }
                        }
                    }
                    // Volume: a thick capsule with the speaker inside, macOS style.
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Style.space.sm
                        Controls.Slider {
                            id: audioVolume
                            objectName: "controlCenterAudioVolume"
                            Layout.fillWidth: true
                            Layout.minimumHeight: 40
                            padding: Style.space.xs
                            from: 0
                            to: 100
                            stepSize: 1
                            enabled: root.audio.status === "ready" && root.audio.writable
                                && (root.audio.pendingKind === "" || (root.audio.pendingKind === "volume"
                                    && root.audio.volumeGestureActive))
                            opacity: enabled ? 1 : 1 - Style.state.disabled
                            Accessible.name: qsTr("Volume da saída padrão")
                            onPressedChanged: {
                                if (pressed) root.audio.beginVolumeGesture();
                                else root.audio.endVolumeGesture();
                            }
                            onMoved: {
                                const accepted = pressed ? root.audio.requestGestureVolume(value)
                                                         : root.audio.requestVolume(value);
                                if (!accepted)
                                    value = root.audio.presentationVolume;
                            }
                            onActiveFocusChanged: if (activeFocus) root.reveal(this)
                            background: Rectangle {
                                x: audioVolume.leftPadding
                                y: audioVolume.topPadding + (audioVolume.availableHeight - height) / 2
                                width: audioVolume.availableWidth
                                height: Style.size.iconButton
                                radius: height / 2
                                color: Style.alpha(audioVolume.palette.windowText, Style.state.pressed)
                                Rectangle {
                                    width: Math.max(parent.height, audioVolume.visualPosition * parent.width)
                                    height: parent.height
                                    radius: height / 2
                                    color: audioVolume.palette.highlight
                                }
                                Kirigami.Icon {
                                    x: Style.space.sm
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: Style.size.iconSm
                                    height: width
                                    source: root.audio.muted ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic"
                                    isMask: true
                                    color: audioVolume.palette.highlightedText
                                }
                                Rectangle {
                                    objectName: "controlCenterAudioVolumeFocus"
                                    // Leave a gap so focus remains distinct from a full accent track.
                                    anchors.fill: parent
                                    anchors.margins: -Style.space.xs
                                    radius: height / 2
                                    color: "transparent"
                                    visible: audioVolume.visualFocus
                                    border.width: 2
                                    border.color: audioVolume.palette.highlight
                                }
                            }
                            handle: Rectangle {
                                x: audioVolume.leftPadding + audioVolume.visualPosition * (audioVolume.availableWidth - width)
                                y: audioVolume.topPadding + (audioVolume.availableHeight - height) / 2
                                width: Style.size.iconButton - Style.space.xs
                                height: width
                                radius: width / 2
                                color: Style.glass.highlight
                                border.width: 1
                                border.color: Style.alpha(Style.glass.shade, 0.18)
                                visible: audioVolume.enabled
                            }
                        }
                        Binding {
                            target: audioVolume
                            property: "value"
                            value: root.audio.presentationVolume
                            when: !audioVolume.pressed || root.audio.volumeGestureBlocked
                            restoreMode: Binding.RestoreNone
                        }
                        Controls.Label {
                            objectName: "controlCenterAudioPercent"
                            Layout.minimumWidth: Style.size.control
                            horizontalAlignment: Text.AlignRight
                            text: qsTr("%1%").arg(Math.round(audioVolume.value))
                            textFormat: Text.PlainText
                            font.features: {"tnum": 1}
                            color: root.foreground
                        }
                    }
                    Controls.Label {
                        objectName: "controlCenterOutputHeading"
                        Layout.fillWidth: true
                        Layout.bottomMargin: -Style.space.xs
                        text: qsTr("Saída padrão")
                        font.pixelSize: Style.type.caption
                        textFormat: Text.PlainText
                        color: root.muted
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Style.space.sm
                        OrlaIconButton {
                            id: muteAction
                            objectName: "controlCenterAudioMute"
                            enabled: root.audio.status === "ready" && root.audio.writable
                                && root.audio.pendingKind === "" && !root.audio.volumeGestureActive
                            checked: root.audio.muted
                            iconName: root.audio.muted ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic"
                            text: root.audio.muted ? qsTr("Ativar som") : qsTr("Silenciar")
                            onClicked: root.audio.requestMute(!root.audio.muted)
                            onActiveFocusChanged: if (activeFocus) root.reveal(this)
                        }
                        Controls.ComboBox {
                            id: outputSelector
                            objectName: "controlCenterOutputSelector"
                            Layout.fillWidth: true
                            Layout.minimumHeight: 40
                            model: root.audio.outputs
                            textRole: "label"
                            enabled: root.audio.status === "ready" && root.audio.outputs.length > 0
                                && root.audio.pendingKind === "" && !root.audio.volumeGestureActive
                            displayText: currentIndex >= 0
                                ? root.boundedText(root.audio.outputs[currentIndex].label, 128)
                                : qsTr("Nenhuma saída")
                            delegate: Controls.ItemDelegate {
                                required property var modelData
                                width: outputSelector.width
                                text: root.boundedText(modelData.label, 128)
                                contentItem: Text {
                                    text: parent.text
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    verticalAlignment: Text.AlignVCenter
                                    color: parent.palette.buttonText
                                    font: parent.font
                                }
                            }
                            Accessible.name: qsTr("Saída de áudio padrão")
                            onActivated: index => {
                                if (index >= 0 && index < root.audio.outputs.length)
                                    root.audio.requestDefaultOutput(root.audio.outputs[index].id);
                            }
                            onActiveFocusChanged: if (activeFocus) root.reveal(this)
                        }
                        Binding {
                            target: outputSelector
                            property: "currentIndex"
                            value: root.outputIndex(root.audio.presentationOutputId)
                            when: true
                            restoreMode: Binding.RestoreNone
                        }
                    }
                    Controls.Label {
                        objectName: "controlCenterAudioStatus"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: root.audio.error ? root.audio.error
                            : root.audio.pendingKind ? qsTr("Aplicando…")
                            : root.audio.status === "loading" ? qsTr("Conectando ao áudio…")
                            : root.audio.status === "absent" ? qsTr("Nenhuma saída de áudio disponível")
                            : root.audio.status === "unavailable" ? qsTr("Serviço de áudio indisponível") : ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.audio.error ? root.foreground : root.muted
                        Accessible.role: root.audio.error ? Accessible.AlertMessage : Accessible.StaticText
                    }
                    OrlaButton {
                        id: audioRetry
                        objectName: "controlCenterAudioRetry"
                        Layout.fillWidth: true
                        Layout.minimumHeight: 40
                        visible: root.audio.status === "unavailable"
                        enabled: root.audio.pendingKind === "" && !root.audio.volumeGestureActive
                        text: qsTr("Tentar reconectar o áudio")
                        onClicked: root.audio.retry()
                        onActiveFocusChanged: if (activeFocus) root.reveal(this)
                    }
                    OrlaButton {
                        id: soundAction
                        objectName: "controlCenterSoundAction"
                        variant: "ghost"
                        Layout.fillWidth: true
                        Layout.minimumHeight: 40
                        text: qsTr("Abrir Som no KDE")
                        onClicked: root.request("sound")
                        onActiveFocusChanged: if (activeFocus) root.reveal(this)
                    }
                    Controls.Label {
                        objectName: "controlCenterSoundError"
                        Layout.fillWidth: true
                        visible: root.soundError.length > 0
                        text: root.soundError
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.foreground
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }

            Card {
                objectName: "controlCenterMicrophoneCard"
                visible: root.microphone !== null && root.microphone.status !== "inactive"
                Layout.fillWidth: true
                radius: Style.radius.module
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Style.space.sm
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Style.space.md
                        OrlaIconButton {
                            objectName: "controlCenterMicrophoneMute"
                            // Stays enabled while confirming: disabling would drop keyboard focus.
                            // The state ignores a second request until the first one settles.
                            enabled: !!root.microphone && root.microphone.status === "ready" && root.microphone.writable
                            checked: !!root.microphone && root.microphone.presentation
                            iconName: checked ? "microphone-sensitivity-muted-symbolic" : "audio-input-microphone-symbolic"
                            text: checked ? qsTr("Ativar microfone") : qsTr("Silenciar microfone")
                            onClicked: root.microphone.request(!root.microphone.muted)
                            onActiveFocusChanged: if (activeFocus) root.reveal(this)
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Controls.Label {
                                Layout.fillWidth: true
                                text: qsTr("Microfone")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                font.weight: Style.weight.demiBold
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterMicrophoneStatus"
                                Layout.fillWidth: true
                                text: root.microphoneText()
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                color: root.muted
                            }
                        }
                    }
                    Controls.Label {
                        objectName: "controlCenterMicrophoneError"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: root.microphone ? root.microphone.error : ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.foreground
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }

            Card {
                objectName: "controlCenterBrightnessCard"
                visible: root.brightness !== null && root.brightness.status !== "inactive"
                Layout.fillWidth: true
                radius: Style.radius.module
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Style.space.sm
                    Controls.Label {
                        objectName: "controlCenterBrightnessHeading"
                        Layout.fillWidth: true
                        text: qsTr("Tela")
                        font.pixelSize: Style.type.caption
                        font.weight: Style.weight.bold
                        textFormat: Text.PlainText
                        color: root.foreground
                        opacity: 0.72
                    }
                    Repeater {
                        model: root.brightness ? root.brightness.displayIds : []
                        delegate: ColumnLayout {
                            id: displayRow
                            required property string modelData
                            readonly property var display: root.brightness.displayById(modelData) || ({label: ""})
                            Layout.fillWidth: true
                            spacing: Style.space.xxs
                            Controls.Label {
                                Layout.fillWidth: true
                                // A name only helps once there is more than one screen.
                                visible: root.brightness.displayIds.length > 1
                                text: displayRow.display.label || qsTr("Tela sem nome")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                color: root.muted
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Style.space.sm
                                Controls.Slider {
                                    id: brightnessSlider
                                    objectName: "controlCenterBrightness"
                                    Layout.fillWidth: true
                                    Layout.minimumHeight: 40
                                    padding: Style.space.xs
                                    from: 1
                                    to: 100
                                    stepSize: 1
                                    enabled: root.brightness.status === "ready"
                                    opacity: enabled ? 1 : 1 - Style.state.disabled
                                    Accessible.name: root.brightness.displayIds.length > 1
                                        ? qsTr("Brilho de %1").arg(displayRow.display.label || qsTr("tela sem nome")) : qsTr("Brilho da tela")
                                    onMoved: if (!root.brightness.request(displayRow.modelData, value))
                                        value = root.brightness.presentationPercent(displayRow.modelData)
                                    onActiveFocusChanged: if (activeFocus) root.reveal(this)
                                    background: Rectangle {
                                        x: brightnessSlider.leftPadding
                                        y: brightnessSlider.topPadding + (brightnessSlider.availableHeight - height) / 2
                                        width: brightnessSlider.availableWidth
                                        height: Style.size.iconButton
                                        radius: height / 2
                                        color: Style.alpha(brightnessSlider.palette.windowText, Style.state.pressed)
                                        Rectangle {
                                            width: Math.max(parent.height, brightnessSlider.visualPosition * parent.width)
                                            height: parent.height
                                            radius: height / 2
                                            color: brightnessSlider.palette.highlight
                                        }
                                        Kirigami.Icon {
                                            x: Style.space.sm
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: Style.size.iconSm
                                            height: width
                                            source: "brightness-high-symbolic"
                                            isMask: true
                                            color: brightnessSlider.palette.highlightedText
                                        }
                                        Rectangle {
                                            objectName: "controlCenterBrightnessFocus"
                                            anchors.fill: parent
                                            anchors.margins: -Style.space.xs
                                            radius: height / 2
                                            color: "transparent"
                                            visible: brightnessSlider.visualFocus
                                            border.width: 2
                                            border.color: brightnessSlider.palette.highlight
                                        }
                                    }
                                    handle: Rectangle {
                                        x: brightnessSlider.leftPadding + brightnessSlider.visualPosition * (brightnessSlider.availableWidth - width)
                                        y: brightnessSlider.topPadding + (brightnessSlider.availableHeight - height) / 2
                                        width: Style.size.iconButton - Style.space.xs
                                        height: width
                                        radius: width / 2
                                        color: Style.glass.highlight
                                        border.width: 1
                                        border.color: Style.alpha(Style.glass.shade, 0.18)
                                        visible: brightnessSlider.enabled
                                    }
                                }
                                Binding {
                                    target: brightnessSlider
                                    property: "value"
                                    value: root.brightness.presentationPercent(displayRow.modelData)
                                    when: !brightnessSlider.pressed
                                    restoreMode: Binding.RestoreNone
                                }
                                Controls.Label {
                                    objectName: "controlCenterBrightnessPercent"
                                    Layout.minimumWidth: Style.size.control
                                    horizontalAlignment: Text.AlignRight
                                    text: qsTr("%1%").arg(Math.round(brightnessSlider.value))
                                    textFormat: Text.PlainText
                                    font.features: {"tnum": 1}
                                    color: root.foreground
                                }
                            }
                        }
                    }
                    Controls.Label {
                        objectName: "controlCenterBrightnessStatus"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: !root.brightness ? ""
                            : root.brightness.error.length > 0 ? root.brightness.error
                            : root.brightness.status === "absent" ? qsTr("Nenhuma tela com brilho ajustável.")
                            : root.brightness.status === "unavailable" ? qsTr("O controle de brilho do KDE está indisponível.")
                            : root.brightness.status === "loading" ? qsTr("Lendo o brilho das telas…") : ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.foreground
                        Accessible.role: root.brightness && root.brightness.error.length > 0 ? Accessible.AlertMessage : Accessible.StaticText
                    }
                }
            }

            Card {
                objectName: "controlCenterDoNotDisturbCard"
                visible: root.doNotDisturb !== null && root.doNotDisturb.status !== "inactive"
                Layout.fillWidth: true
                radius: Style.radius.module
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Style.space.sm
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Style.space.md
                        OrlaIconButton {
                            objectName: "controlCenterDoNotDisturb"
                            // Stays enabled while confirming: disabling would drop keyboard focus.
                            // The state ignores a second request until the first one settles.
                            enabled: !!root.doNotDisturb && root.doNotDisturb.status === "ready"
                            checked: !!root.doNotDisturb && root.doNotDisturb.presentation
                            iconName: "notifications-disabled-symbolic"
                            text: checked ? qsTr("Desativar Não perturbe") : qsTr("Ativar Não perturbe")
                            onClicked: root.doNotDisturb.request(!root.doNotDisturb.inhibited)
                            onActiveFocusChanged: if (activeFocus) root.reveal(this)
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Controls.Label {
                                Layout.fillWidth: true
                                text: qsTr("Não perturbe")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                font.weight: Style.weight.demiBold
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterDoNotDisturbStatus"
                                Layout.fillWidth: true
                                text: root.doNotDisturbText()
                                textFormat: Text.PlainText
                                wrapMode: Text.WordWrap
                                maximumLineCount: 3
                                elide: Text.ElideRight
                                color: root.muted
                            }
                        }
                    }
                    Controls.Label {
                        objectName: "controlCenterDoNotDisturbError"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: root.doNotDisturb ? root.doNotDisturb.error : ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.foreground
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }

            Card {
                objectName: "controlCenterPowerCard"
                Layout.fillWidth: true
                radius: Style.radius.module
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Style.space.sm
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Style.space.md
                        Item {
                            Layout.preferredWidth: Style.size.target + Style.space.xs
                            Layout.preferredHeight: Style.size.target + Style.space.xs
                            Layout.alignment: Qt.AlignTop
                            ProgressRing {
                                anchors.fill: parent
                                lineWidth: Style.space.xs
                                progress: root.battery && root.battery.percentKnown ? root.battery.percent / 100 : 0
                                color: root.palette.highlight
                                trackColor: Style.alpha(root.foreground, 0.12)
                                animationDuration: 0
                            }
                            Kirigami.Icon {
                                anchors.centerIn: parent
                                width: Style.size.iconMd
                                height: width
                                source: root.battery && root.battery.charging ? "battery-full-charging-symbolic" : "battery-100-symbolic"
                                isMask: true
                                color: root.foreground
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Controls.Label {
                                objectName: "controlCenterPowerHeading"
                                Layout.fillWidth: true
                                text: qsTr("Energia")
                                font.pixelSize: Style.type.caption
                                font.weight: Style.weight.bold
                                textFormat: Text.PlainText
                                color: root.foreground
                                opacity: 0.72
                            }
                            Controls.Label {
                                objectName: "controlCenterPowerTitle"
                                Layout.fillWidth: true
                                text: root.battery ? root.battery.summary : qsTr("Bateria indisponível")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                font.weight: Style.weight.demiBold
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterPowerDetail"
                                Layout.fillWidth: true
                                text: root.battery ? root.battery.subtitle : qsTr("Serviço de energia indisponível")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                color: root.muted
                            }
                        }
                    }
                    OrlaButton {
                        objectName: "controlCenterPowerAction"
                        variant: "ghost"
                        Layout.fillWidth: true
                        Layout.minimumHeight: 40
                        text: qsTr("Abrir Energia no KDE")
                        onClicked: root.request("power")
                        onActiveFocusChanged: if (activeFocus) root.reveal(this)
                    }
                    Controls.Label {
                        objectName: "controlCenterPowerError"
                        Layout.fillWidth: true
                        visible: root.powerError.length > 0
                        text: root.powerError
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.foreground
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Style.space.xs
                OrlaButton {
                    objectName: "controlCenterAllAction"
                    variant: "ghost"
                    Layout.fillWidth: true
                    Layout.minimumHeight: 40
                    text: qsTr("Todos os ajustes do sistema")
                    onClicked: root.request("all")
                    onActiveFocusChanged: if (activeFocus) root.reveal(this)
                }
                Controls.Label {
                    objectName: "controlCenterAllError"
                    Layout.fillWidth: true
                    visible: root.allError.length > 0
                    text: root.allError
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    color: root.foreground
                    Accessible.role: Accessible.AlertMessage
                }
            }
        }
    }
}
