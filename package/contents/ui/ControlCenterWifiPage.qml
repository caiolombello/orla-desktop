import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

// The Wi-Fi page of the Control Center, as in macOS: the radio switch, the
// networks in range (connected first) and a link to KDE's network settings.
// Joining and leaving go through WifiState, which waits for NetworkManager.
ColumnLayout {
    id: page
    required property var wifi
    property color foreground: palette.windowText
    property color muted: palette.windowText
    property string actionError: ""
    readonly property alias backButton: back
    signal backRequested()
    signal settingsRequested()
    spacing: Style.space.sm

    function signalIcon(strength) {
        if (strength >= 75) return "network-wireless-signal-excellent-symbolic";
        if (strength >= 50) return "network-wireless-signal-good-symbolic";
        if (strength >= 25) return "network-wireless-signal-ok-symbolic";
        return "network-wireless-signal-none-symbolic";
    }
    function statusText() {
        if (!wifi) return "";
        if (wifi.status === "loading") return qsTr("Lendo o Wi-Fi…");
        if (wifi.status === "absent") return qsTr("Nenhum adaptador Wi-Fi disponível");
        if (wifi.status === "unavailable") return qsTr("Serviço de rede indisponível");
        if (wifi.pending) return wifi.desired ? qsTr("Ligando…") : qsTr("Desligando…");
        if (!wifi.enabled) return wifi.hardwareEnabled ? qsTr("O Wi-Fi está desligado.")
                                                       : qsTr("O Wi-Fi está desligado por uma chave do computador.");
        if (wifi.networks.length === 0) return qsTr("Procurando redes…");
        return "";
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Style.space.sm
        OrlaIconButton {
            id: back
            objectName: "controlCenterWifiBack"
            flat: true
            iconName: "go-previous-symbolic"
            text: qsTr("Voltar à Central de Controle")
            onClicked: page.backRequested()
        }
        Controls.Label {
            Layout.fillWidth: true
            text: qsTr("Wi-Fi")
            textFormat: Text.PlainText
            font.pixelSize: Style.type.title
            font.weight: Style.weight.bold
            color: page.foreground
        }
        Controls.Switch {
            id: radioSwitch
            objectName: "controlCenterWifiSwitch"
            // Stays enabled while confirming: disabling would drop keyboard focus.
            enabled: !!page.wifi && page.wifi.status === "ready"
            checked: !!page.wifi && page.wifi.presentation
            Accessible.name: qsTr("Wi-Fi")
            onToggled: {
                if (!page.wifi.request(checked)) checked = Qt.binding(() => !!page.wifi && page.wifi.presentation);
            }
        }
    }
    Controls.Label {
        objectName: "controlCenterWifiListStatus"
        Layout.fillWidth: true
        visible: text.length > 0
        text: page.statusText()
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.muted
    }
    // The cable connection, which Wi-Fi settings alone do not show.
    Controls.Label {
        objectName: "controlCenterWiredStatus"
        Layout.fillWidth: true
        visible: !!page.wifi && page.wifi.wired.connected
        text: !page.wifi || !page.wifi.wired.connected ? ""
            : page.wifi.wired.name ? qsTr("Conectado por cabo · %1").arg(page.wifi.wired.name)
            : qsTr("Conectado por cabo")
        textFormat: Text.PlainText
        elide: Text.ElideRight
        color: page.foreground
        Accessible.name: text
    }
    Controls.Label {
        objectName: "controlCenterWifiPageError"
        Layout.fillWidth: true
        visible: text.length > 0
        text: page.wifi ? page.wifi.error : ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.foreground
        Accessible.role: Accessible.AlertMessage
    }
    Card {
        Layout.fillWidth: true
        visible: !!page.wifi && page.wifi.networks.length > 0
        radius: Style.radius.module
        padding: Style.space.xs
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            Repeater {
                model: page.wifi ? page.wifi.networks : []
                delegate: ControlCenterListRow {
                    required property var modelData
                    readonly property bool busy: page.wifi.joining === modelData.id || modelData.state === "connecting"
                    Layout.fillWidth: true
                    foreground: page.foreground
                    muted: page.muted
                    name: modelData.name
                    iconName: page.signalIcon(modelData.strength)
                    badgeIcon: modelData.secured ? "object-locked-symbolic" : ""
                    connected: modelData.state === "connected"
                    detail: busy ? qsTr("Conectando…")
                        : page.wifi.leaving === modelData.id ? qsTr("Desconectando…")
                        : connected ? qsTr("Conectada") : ""
                    spokenName: connected ? qsTr("%1, conectada").arg(modelData.name)
                        : modelData.secured ? qsTr("Conectar a %1, protegida por senha").arg(modelData.name)
                        : qsTr("Conectar a %1").arg(modelData.name)
                    disconnectText: qsTr("Desconectar de %1").arg(modelData.name)
                    choose.objectName: "controlCenterWifiNetwork"
                    disconnect.objectName: "controlCenterWifiDisconnect"
                    onChosen: page.wifi.join(modelData.id)
                    onDisconnectRequested: page.wifi.leave(modelData.id)
                }
            }
        }
    }
    Controls.Label {
        objectName: "controlCenterWifiNetworkError"
        Layout.fillWidth: true
        visible: text.length > 0
        text: page.wifi ? page.wifi.networkError : ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.foreground
        Accessible.role: Accessible.AlertMessage
    }
    OrlaButton {
        objectName: "controlCenterNetworkAction"
        variant: "ghost"
        Layout.fillWidth: true
        Layout.minimumHeight: 40
        text: qsTr("Ajustes de Rede…")
        Accessible.name: qsTr("Abrir Rede no KDE")
        onClicked: page.settingsRequested()
    }
    Controls.Label {
        objectName: "controlCenterNetworkError"
        Layout.fillWidth: true
        visible: page.actionError.length > 0
        text: page.actionError
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: page.foreground
        Accessible.role: Accessible.AlertMessage
    }
}
