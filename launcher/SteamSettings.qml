import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: panel
    objectName: "steamSettingsPanel"
    implicitWidth: 0
    implicitHeight: 0
    clip: true
    required property var controller
    property bool operationStartBlocked: false
    signal backRequested()
    function focusFirst() { backButton.forceActiveFocus() }
    function rootSpecs() {
        const lines = rootInput.text.split("\n")
        const result = []
        for (let line of lines) {
            if (line.endsWith("\r")) line = line.slice(0, -1)
            if (line.length > 0) result.push(line)
        }
        return result
    }
    function statusText() {
        if (panel.operationStartBlocked) return qsTr("Encerrando operações. Aguarde antes de iniciar outra.")
        switch (controller.status) {
        case "available": return qsTr("Inventário local carregado nesta sessão")
        case "absent": return qsTr("As raízes informadas não foram encontradas")
        case "partial": return qsTr("Inventário parcial; confira os avisos")
        case "unknown": return qsTr("Não foi possível confirmar o inventário")
        case "running": return qsTr("Lendo metadados locais…")
        case "error": return controller.error
        default: return qsTr("Nenhuma leitura feita nesta sessão")
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
                    objectName: "steamBackButton"
                    text: qsTr("← Busca")
                    Accessible.name: qsTr("Voltar à busca local")
                    onClicked: panel.backRequested()
                    contentItem: Text { text: parent.text; color: "#69D7C2"; font.pixelSize: 12; textFormat: Text.PlainText }
                    background: Rectangle { radius: 8; color: "#1B2733"; border.width: parent.activeFocus ? 1 : 0; border.color: "#69D7C2" }
                }
                Item { Layout.fillWidth: true }
                Text { text: qsTr("SOMENTE SESSÃO"); color: "#A7B7C4"; font.pixelSize: 10; font.letterSpacing: 1; textFormat: Text.PlainText }
            }
            Text {
                Layout.fillWidth: true; text: qsTr("Jogos Steam locais"); color: "#EAF4F1"
                font.pixelSize: 22; font.weight: Font.DemiBold; textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: "#A7B7C4"; font.pixelSize: 12; textFormat: Text.PlainText
                text: qsTr("Nada é lido ao abrir esta tela. Informe somente pastas locais de uma instalação Steam. Bibliotecas externas listadas por essas pastas também serão consultadas. O resultado mostra presença local e não confirma que sua conta pode acessar o jogo.")
            }
            TextArea {
                id: rootInput
                objectName: "steamRootInput"
                Layout.fillWidth: true; Layout.preferredHeight: 92
                placeholderText: "native=/caminho/absoluto/Steam\nflatpak=/caminho/absoluto/Steam"
                Accessible.name: qsTr("Pastas locais do Steam, uma por linha")
                color: "#EAF4F1"; placeholderTextColor: "#728391"; wrapMode: TextEdit.NoWrap
                background: Rectangle { radius: 9; color: "#1B2733"; border.width: parent.activeFocus ? 1 : 0; border.color: "#69D7C2" }
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    id: scanButton
                    objectName: "steamScanButton"
                    Layout.fillWidth: true; Layout.preferredHeight: 42
                    enabled: !panel.operationStartBlocked && !panel.controller.busy
                    text: panel.controller.apps.length > 0 ? qsTr("Atualizar jogos") : qsTr("Carregar jogos")
                    onClicked: if (!panel.operationStartBlocked) panel.controller.scan(panel.rootSpecs())
                    contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? "#111923" : "#A7B7C4"; font.pixelSize: 12; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                    background: Rectangle { radius: 9; color: parent.enabled ? "#69D7C2" : "#283542"; border.width: parent.activeFocus ? 2 : 0; border.color: "#EAF4F1" }
                }
                Button {
                    id: cancelButton
                    objectName: "steamCancelButton"
                    visible: panel.controller.busy
                    text: qsTr("Cancelar")
                    onClicked: panel.controller.cancelAll()
                }
            }
            Text {
                Layout.fillWidth: true; text: panel.statusText(); wrapMode: Text.Wrap
                color: panel.controller.status === "error" ? "#E7C58E" : "#B9CCC7"
                font.pixelSize: 11; textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true; visible: panel.controller.status === "available" || panel.controller.status === "partial"
                text: qsTr("%1 jogos · %2 avisos · %3 raízes").arg(panel.controller.apps.length).arg(panel.controller.issueCount).arg(panel.controller.rootsCount)
                color: "#91A5B4"; font.pixelSize: 10; textFormat: Text.PlainText
            }
            Button {
                id: downloadsButton
                objectName: "steamDownloadsButton"
                Layout.fillWidth: true; Layout.preferredHeight: 40
                enabled: !panel.operationStartBlocked && !panel.controller.busy
                text: qsTr("Abrir downloads no Steam")
                Accessible.description: qsTr("Encaminha a URI fixa de downloads; não confirma que o cliente abriu")
                onClicked: if (!panel.operationStartBlocked) panel.controller.openDownloads()
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: "#69D7C2"; font.pixelSize: 11; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: 8; color: "#253F42"; border.width: parent.activeFocus ? 2 : 1; border.color: "#69D7C2" }
            }
        }
    }
}
