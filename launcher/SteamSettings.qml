import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Style.js" as Style

Item {
    id: panel
    // The launcher is a dark overlay in every system scheme.
    readonly property var ui: Style.scheme("dark")
    objectName: "steamSettingsPanel"
    implicitWidth: 0
    implicitHeight: 0
    clip: true
    required property var controller
    property bool operationStartBlocked: false
    property string rootDiscoveryMessage: ""
    property Item focusedControl: null
    signal backRequested()
    function focusFirst() { backButton.forceActiveFocus() }
    function reveal(control) {
        focusedControl = control;
        const viewport = panelScroll.contentItem;
        if (!viewport || viewport.height <= 0 || !control.activeFocus) return;
        const point = control.mapToItem(viewport, 0, 0);
        const margin = Style.space.xs;
        if (point.y < margin) viewport.contentY += point.y - margin;
        else if (point.y + control.height > viewport.height - margin)
            viewport.contentY += point.y + control.height - viewport.height + margin;
    }
    function locateRoots() {
        if (panel.operationStartBlocked || panel.controller.busy) return
        const specs = panel.controller.locateRoots()
        if (specs.length > 0) rootInput.text = specs.join("\n")
        rootDiscoveryMessage = specs.length > 0
            ? qsTr("Pastas encontradas nos locais conhecidos: %1. Confira as raízes e use Carregar jogos para ler os metadados.").arg(specs.length)
            : qsTr("Nenhuma pasta encontrada nos locais conhecidos. Você ainda pode informar outra raiz.")
    }
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
        id: panelScroll
        anchors.fill: parent
        contentWidth: availableWidth
        onContentHeightChanged: if (panel.focusedControl && panel.focusedControl.activeFocus) panel.reveal(panel.focusedControl)
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            x: Style.space.xs
            width: panelScroll.width - panelScroll.effectiveScrollBarWidth - Style.space.sm
            spacing: 12
            Item { Layout.preferredHeight: Style.space.xs }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    id: backButton
                    objectName: "steamBackButton"
                    text: qsTr("← Busca")
                    Accessible.name: qsTr("Voltar à busca local")
                    KeyNavigation.priority: KeyNavigation.BeforeItem
                    KeyNavigation.tab: rootInput
                    KeyNavigation.backtab: downloadsButton
                    onActiveFocusChanged: if (activeFocus) panel.reveal(this)
                    onClicked: panel.backRequested()
                    contentItem: Text { text: parent.text; color: ui.accent; font.pixelSize: Style.type.label; textFormat: Text.PlainText }
                    background: Rectangle { radius: Style.radius.control; color: ui.surface; border.width: parent.activeFocus ? 2 : 0; border.color: ui.accent }
                }
                Item { Layout.fillWidth: true }
                Text { text: qsTr("SOMENTE SESSÃO"); color: ui.textMuted; font.pixelSize: Style.type.overline; font.letterSpacing: 1; textFormat: Text.PlainText }
            }
            Text {
                Layout.fillWidth: true; text: qsTr("Jogos Steam locais"); color: ui.text
                font.pixelSize: Style.type.headline; font.weight: Font.DemiBold; textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: ui.textMuted; font.pixelSize: Style.type.label; textFormat: Text.PlainText
                text: qsTr("Nada é lido ao abrir esta tela. Localize pastas nos locais conhecidos ou informe outras raízes. Só Carregar jogos lê metadados; bibliotecas externas declaradas nessas raízes também serão consultadas. Presença local não confirma acesso pela sua conta.")
            }
            TextArea {
                id: rootInput
                objectName: "steamRootInput"
                Layout.fillWidth: true; Layout.preferredHeight: 92
                placeholderText: "native=/caminho/absoluto/Steam\nflatpak=/caminho/absoluto/Steam"
                Accessible.name: qsTr("Pastas locais do Steam, uma por linha")
                KeyNavigation.priority: KeyNavigation.BeforeItem
                KeyNavigation.tab: scanButton
                KeyNavigation.backtab: backButton
                onActiveFocusChanged: if (activeFocus) panel.reveal(this)
                color: ui.text; placeholderTextColor: ui.textMuted; wrapMode: TextEdit.NoWrap
                onTextChanged: panel.rootDiscoveryMessage = ""
                background: Rectangle { radius: Style.radius.control; color: ui.surface; border.width: parent.activeFocus ? 2 : 0; border.color: ui.accent }
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    id: scanButton
                    objectName: "steamScanButton"
                    Layout.fillWidth: true; Layout.preferredHeight: 42
                    enabled: !panel.operationStartBlocked && !panel.controller.busy
                    KeyNavigation.priority: KeyNavigation.BeforeItem
                    KeyNavigation.tab: cancelButton
                    KeyNavigation.backtab: rootInput
                    onActiveFocusChanged: if (activeFocus) panel.reveal(this)
                    text: panel.controller.apps.length > 0 ? qsTr("Atualizar jogos") : qsTr("Carregar jogos")
                    onClicked: if (!panel.operationStartBlocked) panel.controller.scan(panel.rootSpecs())
                    contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? ui.onAccent : ui.textMuted; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                    background: Rectangle { radius: Style.radius.control; color: parent.enabled ? ui.accent : ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: ui.text }
                }
                Button {
                    id: cancelButton
                    objectName: "steamCancelButton"
                    visible: panel.controller.busy
                    KeyNavigation.priority: KeyNavigation.BeforeItem
                    KeyNavigation.tab: locateButton
                    KeyNavigation.backtab: scanButton
                    onActiveFocusChanged: if (activeFocus) panel.reveal(this)
                    text: qsTr("Cancelar")
                    onClicked: panel.controller.cancelAll()
                }
            }
            Button {
                id: locateButton
                objectName: "steamLocateRootsButton"
                Layout.fillWidth: true; Layout.preferredHeight: Style.size.target
                Layout.minimumWidth: Style.size.target
                enabled: !panel.operationStartBlocked && !panel.controller.busy
                KeyNavigation.priority: KeyNavigation.BeforeItem
                KeyNavigation.tab: downloadsButton
                KeyNavigation.backtab: cancelButton
                onActiveFocusChanged: if (activeFocus) panel.reveal(this)
                text: qsTr("Localizar pastas do Steam")
                Accessible.description: qsTr("Preenche raízes existentes nos locais conhecidos sem ler metadados dos jogos")
                onClicked: panel.locateRoots()
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? ui.text : ui.textMuted; font.pixelSize: Style.type.label; textFormat: Text.PlainText }
                background: Rectangle { radius: Style.radius.control; color: ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: ui.focus }
            }
            Text {
                objectName: "steamRootDiscoveryMessage"
                Layout.fillWidth: true; visible: panel.rootDiscoveryMessage.length > 0
                text: panel.rootDiscoveryMessage; wrapMode: Text.Wrap
                color: ui.textMuted; font.pixelSize: Style.type.caption; textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true; text: panel.statusText(); wrapMode: Text.Wrap
                color: panel.controller.status === "error" ? ui.warning : ui.textMuted
                font.pixelSize: Style.type.caption; textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true; visible: panel.controller.status === "available" || panel.controller.status === "partial"
                text: qsTr("%1 jogos · %2 avisos · %3 raízes").arg(panel.controller.apps.length).arg(panel.controller.issueCount).arg(panel.controller.rootsCount)
                color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText
            }
            Button {
                id: downloadsButton
                objectName: "steamDownloadsButton"
                Layout.fillWidth: true; Layout.preferredHeight: 40
                enabled: !panel.operationStartBlocked && !panel.controller.busy
                KeyNavigation.priority: KeyNavigation.BeforeItem
                KeyNavigation.tab: backButton
                KeyNavigation.backtab: locateButton
                onActiveFocusChanged: if (activeFocus) panel.reveal(this)
                text: qsTr("Abrir downloads no Steam")
                Accessible.description: qsTr("Encaminha a URI fixa de downloads; não confirma que o cliente abriu")
                onClicked: if (!panel.operationStartBlocked) panel.controller.openDownloads()
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: ui.accent; font.pixelSize: Style.type.caption; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: Style.radius.control; color: Style.alpha(ui.accent, 0.14); border.width: parent.activeFocus ? 2 : 1; border.color: ui.accent }
            }
            Item { Layout.preferredHeight: Style.space.xs }
        }
    }
}
