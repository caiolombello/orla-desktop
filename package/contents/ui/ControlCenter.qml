import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Controls.Control {
    id: root
    required property var actions
    required property var player
    required property var battery
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
                            Controls.Label { Layout.fillWidth: true; text: qsTr("Som e mídia"); font.bold: true; textFormat: Text.PlainText }
                            Controls.Label {
                                objectName: "controlCenterMediaTitle"
                                Layout.fillWidth: true
                                text: root.player ? root.boundedText(root.player.track || root.player.identity, 256) || qsTr("Player sem título")
                                                  : qsTr("Nenhum player aberto")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
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
                            Controls.Label { Layout.fillWidth: true; text: qsTr("Energia"); font.bold: true; textFormat: Text.PlainText }
                            Controls.Label {
                                objectName: "controlCenterPowerTitle"
                                Layout.fillWidth: true
                                text: root.battery ? root.battery.summary : qsTr("Bateria indisponível")
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
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
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }
        }
    }
}
