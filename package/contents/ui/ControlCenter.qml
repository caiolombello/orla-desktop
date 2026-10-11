import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Controls.Control {
    id: root
    required property var actions
    required property var player
    required property var battery
    required property var audio
    property color foreground: palette.windowText
    property color muted: palette.windowText
    property string soundError: ""
    property string powerError: ""
    property string allError: ""
    implicitWidth: 310
    implicitHeight: Math.min(body.implicitHeight + topPadding + bottomPadding, 390)
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
        Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: 10

            Controls.Frame {
                objectName: "controlCenterSoundCard"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Kirigami.Icon { source: "preferences-desktop-sound"; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Controls.Label {
                                objectName: "controlCenterSoundHeading"
                                Layout.fillWidth: true
                                text: qsTr("Som e mídia")
                                font.bold: true
                                textFormat: Text.PlainText
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterMediaTitle"
                                Layout.fillWidth: true
                                text: root.player ? root.boundedText(root.player.track || root.player.identity, 256) || qsTr("Player sem título")
                                                  : qsTr("Nenhum player aberto")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
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
                                opacity: 0.75
                            }
                        }
                    }
                    Controls.Label {
                        objectName: "controlCenterOutputHeading"
                        Layout.fillWidth: true
                        text: qsTr("Saída padrão")
                        textFormat: Text.PlainText
                        color: root.muted
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
                        contentItem: TextInput {
                            objectName: "controlCenterOutputDisplay"
                            leftPadding: outputSelector.leftPadding
                            rightPadding: outputSelector.rightPadding
                            text: outputSelector.displayText
                            enabled: false
                            readOnly: true
                            selectByMouse: false
                            clip: true
                            verticalAlignment: Text.AlignVCenter
                            color: outputSelector.palette.buttonText
                            font: outputSelector.font
                        }
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
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Controls.Slider {
                            id: audioVolume
                            objectName: "controlCenterAudioVolume"
                            Layout.fillWidth: true
                            Layout.minimumHeight: 40
                            from: 0
                            to: 100
                            stepSize: 1
                            enabled: root.audio.status === "ready" && root.audio.writable
                                && (root.audio.pendingKind === "" || (root.audio.pendingKind === "volume"
                                    && root.audio.volumeGestureActive))
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
                            Layout.minimumWidth: 36
                            horizontalAlignment: Text.AlignRight
                            text: qsTr("%1%").arg(Math.round(audioVolume.value))
                            textFormat: Text.PlainText
                            color: root.foreground
                        }
                    }
                    Controls.Button {
                        id: muteAction
                        objectName: "controlCenterAudioMute"
                        Layout.fillWidth: true
                        Layout.minimumHeight: 40
                        enabled: root.audio.status === "ready" && root.audio.writable
                            && root.audio.pendingKind === "" && !root.audio.volumeGestureActive
                        text: root.audio.muted ? qsTr("Ativar som") : qsTr("Silenciar")
                        Accessible.name: text
                        onClicked: root.audio.requestMute(!root.audio.muted)
                        onActiveFocusChanged: if (activeFocus) root.reveal(this)
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
                    Controls.Button {
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
                    Controls.Button {
                        id: soundAction
                        objectName: "controlCenterSoundAction"
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

            Controls.Frame {
                objectName: "controlCenterPowerCard"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Kirigami.Icon { source: "preferences-system-power-management"; Layout.preferredWidth: 28; Layout.preferredHeight: 28 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Controls.Label {
                                objectName: "controlCenterPowerHeading"
                                Layout.fillWidth: true
                                text: qsTr("Energia")
                                font.bold: true
                                textFormat: Text.PlainText
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterPowerTitle"
                                Layout.fillWidth: true
                                text: root.battery ? root.battery.summary : qsTr("Bateria indisponível")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "controlCenterPowerDetail"
                                Layout.fillWidth: true
                                text: root.battery ? root.battery.subtitle : qsTr("Serviço de energia indisponível")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                color: root.muted
                                opacity: 0.75
                            }
                        }
                    }
                    Controls.Button {
                        objectName: "controlCenterPowerAction"
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

            Controls.Frame {
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    Controls.Button {
                        objectName: "controlCenterAllAction"
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
}
