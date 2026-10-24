import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import org.kde.kirigami as Kirigami
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
                delegate: RowLayout {
                    id: networkRow
                    required property var modelData
                    readonly property bool joining: page.wifi.joining === modelData.id
                    readonly property bool connected: modelData.state === "connected"
                    Layout.fillWidth: true
                    spacing: 0
                    Templates.Button {
                        id: choose
                        objectName: "controlCenterWifiNetwork"
                        Layout.fillWidth: true
                        implicitHeight: Style.size.target
                        implicitWidth: implicitContentWidth + leftPadding + rightPadding
                        padding: Style.space.xs
                        leftPadding: Style.space.sm
                        rightPadding: Style.space.sm
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        readonly property string spokenName: networkRow.connected ? qsTr("%1, conectada").arg(networkRow.modelData.name)
                            : networkRow.modelData.secured ? qsTr("Conectar a %1, protegida por senha").arg(networkRow.modelData.name)
                            : qsTr("Conectar a %1").arg(networkRow.modelData.name)
                        Accessible.name: spokenName
                        onClicked: if (!networkRow.connected) page.wifi.join(networkRow.modelData.id)
                        contentItem: RowLayout {
                            spacing: Style.space.sm
                            Kirigami.Icon {
                                Layout.preferredWidth: Style.size.iconSm
                                Layout.preferredHeight: Style.size.iconSm
                                source: page.signalIcon(networkRow.modelData.strength)
                                isMask: true
                                color: networkRow.connected ? choose.palette.highlight : page.foreground
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Controls.Label {
                                    Layout.fillWidth: true
                                    text: networkRow.modelData.name
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                    font.weight: networkRow.connected ? Style.weight.demiBold : Style.weight.regular
                                    color: page.foreground
                                }
                                Controls.Label {
                                    Layout.fillWidth: true
                                    visible: text.length > 0
                                    text: networkRow.joining || networkRow.modelData.state === "connecting" ? qsTr("Conectando…")
                                        : page.wifi.leaving === networkRow.modelData.id ? qsTr("Desconectando…")
                                        : networkRow.connected ? qsTr("Conectada") : ""
                                    textFormat: Text.PlainText
                                    font.pixelSize: Style.type.caption
                                    color: page.muted
                                }
                            }
                            Kirigami.Icon {
                                Layout.preferredWidth: Style.size.iconSm
                                Layout.preferredHeight: Style.size.iconSm
                                visible: networkRow.modelData.secured
                                source: "object-locked-symbolic"
                                isMask: true
                                color: page.muted
                            }
                        }
                        background: Rectangle {
                            radius: Style.radius.control
                            color: choose.down ? Style.alpha(page.foreground, Style.state.pressed)
                                : choose.hovered ? Style.alpha(page.foreground, Style.state.hover) : "transparent"
                            Rectangle {
                                anchors.fill: parent
                                radius: parent.radius
                                color: "transparent"
                                visible: choose.visualFocus
                                border.width: 2
                                border.color: choose.palette.highlight
                            }
                        }
                    }
                    OrlaIconButton {
                        objectName: "controlCenterWifiDisconnect"
                        visible: networkRow.connected
                        flat: true
                        // Monochrome: Breeze's disconnect icon carries a red mark that reads as an error.
                        iconName: "media-eject-symbolic"
                        text: qsTr("Desconectar de %1").arg(networkRow.modelData.name)
                        onClicked: page.wifi.leave(networkRow.modelData.id)
                    }
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
