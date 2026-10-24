import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

// The Bluetooth page of the Control Center, as in macOS: the radio switch, the
// paired devices (connected first) and a link to KDE's Bluetooth settings,
// where pairing new devices stays. BluetoothState waits for BlueZ to confirm.
ColumnLayout {
    id: page
    required property var bluetooth
    property color foreground: palette.windowText
    property color muted: palette.windowText
    property string actionError: ""
    readonly property alias backButton: back
    signal backRequested()
    signal settingsRequested()
    spacing: Style.space.sm

    function statusText() {
        if (!bluetooth) return "";
        if (bluetooth.status === "loading") return qsTr("Lendo o Bluetooth…");
        if (bluetooth.status === "absent") return qsTr("Nenhum adaptador Bluetooth disponível");
        if (bluetooth.status === "unavailable") return qsTr("Serviço de Bluetooth indisponível");
        if (bluetooth.pending) return bluetooth.desired ? qsTr("Ligando…") : qsTr("Desligando…");
        if (!bluetooth.enabled) return qsTr("O Bluetooth está desligado.");
        if (bluetooth.devices.length === 0) return qsTr("Nenhum aparelho pareado. Pareie em Ajustes de Bluetooth.");
        return "";
    }
    function detail(device) {
        if (bluetooth.busyDevice === device.id)
            return bluetooth.busyWantsConnected ? qsTr("Conectando…") : qsTr("Desconectando…");
        if (!device.connected) return "";
        return device.battery >= 0 ? qsTr("Conectado · bateria %1%").arg(device.battery) : qsTr("Conectado");
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Style.space.sm
        OrlaIconButton {
            id: back
            objectName: "controlCenterBluetoothBack"
            flat: true
            iconName: "go-previous-symbolic"
            text: qsTr("Voltar à Central de Controle")
            onClicked: page.backRequested()
        }
        Controls.Label {
            Layout.fillWidth: true
            text: qsTr("Bluetooth")
            textFormat: Text.PlainText
            font.pixelSize: Style.type.title
            font.weight: Style.weight.bold
            color: page.foreground
        }
        Controls.Switch {
            objectName: "controlCenterBluetoothSwitch"
            // Stays enabled while confirming: disabling would drop keyboard focus.
            enabled: !!page.bluetooth && page.bluetooth.status === "ready"
            checked: !!page.bluetooth && page.bluetooth.presentation
            Accessible.name: qsTr("Bluetooth")
            onToggled: {
                if (!page.bluetooth.request(checked))
                    checked = Qt.binding(() => !!page.bluetooth && page.bluetooth.presentation);
            }
        }
    }
    Controls.Label {
        objectName: "controlCenterBluetoothListStatus"
        Layout.fillWidth: true
        visible: text.length > 0
        text: page.statusText()
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.muted
    }
    Controls.Label {
        objectName: "controlCenterBluetoothPageError"
        Layout.fillWidth: true
        visible: text.length > 0
        text: page.bluetooth ? page.bluetooth.error : ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.foreground
        Accessible.role: Accessible.AlertMessage
    }
    Card {
        Layout.fillWidth: true
        visible: !!page.bluetooth && page.bluetooth.devices.length > 0
        radius: Style.radius.module
        padding: Style.space.xs
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            Repeater {
                model: page.bluetooth ? page.bluetooth.devices : []
                delegate: ControlCenterListRow {
                    required property var modelData
                    Layout.fillWidth: true
                    foreground: page.foreground
                    muted: page.muted
                    name: modelData.name
                    iconName: modelData.icon
                    connected: modelData.connected
                    detail: page.detail(modelData)
                    spokenName: connected ? qsTr("%1, conectado").arg(modelData.name) : qsTr("Conectar %1").arg(modelData.name)
                    disconnectText: qsTr("Desconectar %1").arg(modelData.name)
                    choose.objectName: "controlCenterBluetoothDevice"
                    disconnect.objectName: "controlCenterBluetoothDisconnect"
                    onChosen: page.bluetooth.setDeviceConnected(modelData.id, true)
                    onDisconnectRequested: page.bluetooth.setDeviceConnected(modelData.id, false)
                }
            }
        }
    }
    Controls.Label {
        objectName: "controlCenterBluetoothDeviceError"
        Layout.fillWidth: true
        visible: text.length > 0
        text: page.bluetooth ? page.bluetooth.deviceError : ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.foreground
        Accessible.role: Accessible.AlertMessage
    }
    OrlaButton {
        objectName: "controlCenterBluetoothAction"
        variant: "ghost"
        Layout.fillWidth: true
        Layout.minimumHeight: 40
        text: qsTr("Ajustes de Bluetooth…")
        Accessible.name: qsTr("Abrir Bluetooth no KDE")
        onClicked: page.settingsRequested()
    }
    Controls.Label {
        objectName: "controlCenterBluetoothActionError"
        Layout.fillWidth: true
        visible: page.actionError.length > 0
        text: page.actionError
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.foreground
        Accessible.role: Accessible.AlertMessage
    }
}
