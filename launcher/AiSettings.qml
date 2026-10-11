import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: panel
    objectName: "aiSettingsPanel"
    implicitWidth: 0
    implicitHeight: 0
    clip: true
    required property var controller
    signal backRequested()
    function focusFirst() { backButton.forceActiveFocus() }

    function capability(provider, name) {
        return provider && provider.capabilities ? provider.capabilities[name] : "unknown"
    }
    function installationText(provider) {
        const state = capability(provider, "installation")
        if (state === "supported") return qsTr("Cliente de linha de comando detectado")
        if (state === "absent") return qsTr("Cliente de linha de comando não encontrado")
        return qsTr("Presença ou versão não confirmada")
    }
    function protocolText(provider) {
        const state = capability(provider, "anonymous_protocol")
        if (state === "supported") return qsTr("Protocolo anônimo compatível")
        if (state === "absent") return qsTr("Protocolo indisponível sem o cliente")
        return qsTr("Protocolo não verificado")
    }
    function messageText(provider) {
        switch (provider.messageCode) {
        case "isolation_unavailable": return qsTr("A versão não foi consultada porque o isolamento local não está disponível.")
        case "protocol_version_unknown": return qsTr("Esta versão do Codex ainda não tem um protocolo validado pelo Orla.")
        case "cli_present_version_not_queried": return qsTr("O cliente está no PATH; a versão não foi chamada para evitar contato com um servidor.")
        case "timeout": case "protocol_timeout": return qsTr("A verificação local atingiu o limite de tempo.")
        case "cancelled": return qsTr("Verificação cancelada.")
        case "anonymous_protocol_supported": return qsTr("A troca técnica mínima de compatibilidade foi validada em ambiente isolado.")
        case "version_unrecognized": return qsTr("O cliente foi localizado, mas a versão não foi reconhecida.")
        case "process_cleanup_failed": return qsTr("A limpeza do processo local não pôde ser confirmada.")
        default: return ""
        }
    }

    ScrollView {
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: panel.width - 14
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Button {
                    id: backButton
                    objectName: "aiBackButton"
                    text: qsTr("← Busca")
                    Accessible.name: qsTr("Voltar à busca local")
                    onClicked: panel.backRequested()
                    contentItem: Text { text: parent.text; color: "#69D7C2"; font.pixelSize: 12; textFormat: Text.PlainText }
                    background: Rectangle { radius: 8; color: "#1B2733"; border.width: parent.activeFocus ? 1 : 0; border.color: "#69D7C2" }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    radius: 10; color: "#27323D"
                    Layout.preferredWidth: stateLabel.implicitWidth + 18; Layout.preferredHeight: 28
                    Text { id: stateLabel; anchors.centerIn: parent; text: qsTr("DESLIGADA"); color: "#A7B7C4"; font.pixelSize: 10; font.letterSpacing: 1; textFormat: Text.PlainText }
                }
            }
            Text {
                Layout.fillWidth: true; text: qsTr("Provedores de IA"); color: "#EAF4F1"
                font.pixelSize: 22; font.weight: Font.DemiBold; textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#A7B7C4"; font.pixelSize: 12
                text: qsTr("Nada é executado ao abrir esta tela. A verificação procura apenas clientes locais em uma lista fixa; todos continuam desativados.")
                textFormat: Text.PlainText
            }
            Button {
                id: discoverButton
                objectName: "aiDiscoverButton"
                Layout.fillWidth: true; Layout.preferredHeight: 42
                enabled: !panel.controller.busy
                text: panel.controller.busy && panel.controller.operation === "detect" ? qsTr("Verificando…") : qsTr("Verificar clientes instalados")
                Accessible.description: qsTr("Consulta presença e versões permitidas em isolamento local; não autentica nem faz inferência")
                onClicked: panel.controller.discover()
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? "#111923" : "#A7B7C4"; font.pixelSize: 12; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: 9; color: parent.enabled ? "#69D7C2" : "#283542"; border.width: parent.activeFocus ? 2 : 0; border.color: "#EAF4F1" }
            }
            Text {
                Layout.fillWidth: true; visible: panel.controller.status === "error"
                text: panel.controller.error; wrapMode: Text.Wrap; color: "#E7C58E"; font.pixelSize: 11; textFormat: Text.PlainText
            }
            Repeater {
                model: panel.controller.providers
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: providerColumn.implicitHeight + 24
                    radius: 12; color: "#1B2733"; border.width: 1; border.color: "#314352"
                    ColumnLayout {
                        id: providerColumn
                        anchors.fill: parent; anchors.margins: 12; spacing: 5
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: modelData.displayName; color: "#EAF4F1"; font.pixelSize: 15; font.weight: Font.Medium; textFormat: Text.PlainText }
                            Item { Layout.fillWidth: true }
                            Text { text: modelData.clientVersion ? "v" + modelData.clientVersion : qsTr("sem versão"); color: "#91A5B4"; font.pixelSize: 10; textFormat: Text.PlainText }
                        }
                        Text { Layout.fillWidth: true; text: panel.installationText(modelData); color: "#B9CCC7"; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Text { Layout.fillWidth: true; text: panel.protocolText(modelData); color: panel.capability(modelData, "anonymous_protocol") === "supported" ? "#69D7C2" : "#91A5B4"; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Text { Layout.fillWidth: true; visible: panel.messageText(modelData).length > 0; text: panel.messageText(modelData); color: "#91A5B4"; font.pixelSize: 10; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: consentColumn.implicitHeight + 24
                radius: 12; color: "#172D30"; border.width: 1; border.color: "#3A756C"
                ColumnLayout {
                    id: consentColumn
                    anchors.fill: parent; anchors.margins: 12; spacing: 7
                    Text { Layout.fillWidth: true; text: qsTr("Teste anônimo do Codex"); color: "#EAF4F1"; font.pixelSize: 15; font.weight: Font.Medium; textFormat: Text.PlainText }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#B9CCC7"; font.pixelSize: 11; textFormat: Text.PlainText
                        text: qsTr("Faz uma verificação local limitada de compatibilidade. Não envia texto pessoal, não entra em conta e não inicia modelo, turno ou geração.")
                    }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#91A5B4"; font.pixelSize: 10; textFormat: Text.PlainText
                        text: qsTr("Autenticação, inferência, cancelamento real, uso e cobrança continuarão não verificados.")
                    }
                    Button {
                        id: probeButton
                        objectName: "aiProbeButton"
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        text: panel.controller.busy && panel.controller.operation === "probe-codex-anonymous" ? qsTr("Cancelar teste") : qsTr("Testar compatibilidade anônima")
                        Accessible.description: qsTr("Consentimento separado para iniciar o teste local limitado do Codex")
                        onClicked: {
                            if (panel.controller.busy && panel.controller.operation === "probe-codex-anonymous")
                                panel.controller.cancel(panel.controller.requestId)
                            else if (!panel.controller.busy)
                                panel.controller.probeCodex("qml-consent")
                        }
                        contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: "#69D7C2"; font.pixelSize: 11; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                        background: Rectangle { radius: 8; color: "#253F42"; border.width: parent.activeFocus ? 2 : 1; border.color: "#69D7C2" }
                    }
                }
            }
            Item { Layout.preferredHeight: 4 }
        }
    }
}
