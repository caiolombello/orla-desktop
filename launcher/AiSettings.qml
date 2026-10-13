import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Style.js" as Style

Item {
    id: panel
    // The launcher is a dark overlay in every system scheme.
    readonly property var ui: Style.scheme("dark")
    objectName: "aiSettingsPanel"
    implicitWidth: 0
    implicitHeight: 0
    clip: true
    required property var controller
    required property var textController
    property bool operationStartBlocked: false
    signal backRequested()
    function focusFirst() { backButton.forceActiveFocus() }
    property int textRequestGeneration: 0
    property var taskValues: ["rewrite", "summarize", "translate"]

    function revokeTextConsent() {
        textConsent.checked = false
    }
    function normalizedDestination() {
        const host = hostChoice.currentIndex === 0 ? "127.0.0.1" : "[::1]"
        return "http://" + host + ":" + portInput.value + "/api/chat"
    }
    function taskLabel() {
        return taskChoice.currentText
    }
    function terminalStatusText() {
        if (panel.operationStartBlocked) return qsTr("Encerrando operações. Aguarde antes de iniciar outra.")
        switch (textController.status) {
        case "running": return qsTr("Geração iniciada. Aguarde ou cancele.")
        case "completed":
            if (textController.finishReason === "length")
                return qsTr("Limite de saída atingido. O resultado pode estar incompleto; revise o texto.")
            if (textController.finishReason === "incomplete")
                return qsTr("Geração incompleta. Revise o resultado parcial.")
            return qsTr("Geração concluída. Revise o resultado.")
        case "failed": return qsTr("A geração falhou: %1").arg(textController.error)
        case "cancelled_confirmed": return qsTr("Geração cancelada. O resultado parcial foi preservado.")
        case "cancelled_unconfirmed": return qsTr("Cancelamento local concluído sem confirmação remota. O resultado parcial foi preservado.")
        default: return qsTr("Pronto para gerar quando você permitir o envio.")
        }
    }

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
        id: settingsScroll
        objectName: "aiSettingsScroll"
        anchors.fill: parent
        clip: true
        rightPadding: effectiveScrollBarWidth + 6
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: settingsScroll.availableWidth
            spacing: 12
            RowLayout {
                Layout.fillWidth: true
                Button {
                    id: backButton
                    objectName: "aiBackButton"
                    Layout.minimumWidth: 40
                    Layout.minimumHeight: 40
                    Layout.preferredHeight: 40
                    text: qsTr("← Busca")
                    Accessible.name: qsTr("Voltar à busca local")
                    onClicked: panel.backRequested()
                    contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: ui.accent; font.pixelSize: Style.type.label; textFormat: Text.PlainText }
                    background: Rectangle { radius: Style.radius.control; color: ui.surface; border.width: parent.activeFocus ? 1 : 0; border.color: ui.accent }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    radius: Style.radius.card; color: ui.raised
                    Layout.preferredWidth: stateLabel.implicitWidth + 18; Layout.preferredHeight: 28
                    Text { id: stateLabel; anchors.centerIn: parent; text: qsTr("DESLIGADA"); color: ui.textMuted; font.pixelSize: Style.type.overline; font.letterSpacing: 1; textFormat: Text.PlainText }
                }
            }
            Text {
                Layout.fillWidth: true; text: qsTr("Provedores de IA"); color: ui.text
                font.pixelSize: Style.type.headline; font.weight: Font.DemiBold; textFormat: Text.PlainText
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: ui.textMuted; font.pixelSize: Style.type.label
                text: qsTr("Nada é executado ao abrir esta tela. A verificação procura apenas clientes locais em uma lista fixa; todos continuam desativados.")
                textFormat: Text.PlainText
            }
            Button {
                id: discoverButton
                objectName: "aiDiscoverButton"
                Layout.fillWidth: true; Layout.preferredHeight: 42
                enabled: !panel.operationStartBlocked && !panel.controller.busy
                text: panel.controller.busy && panel.controller.operation === "detect" ? qsTr("Verificando…") : qsTr("Verificar clientes instalados")
                Accessible.description: qsTr("Consulta presença e versões permitidas em isolamento local; não autentica nem faz inferência")
                onClicked: if (!panel.operationStartBlocked) panel.controller.discover()
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? ui.onAccent : ui.textMuted; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: Style.radius.control; color: parent.enabled ? ui.accent : ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: ui.text }
            }
            Text {
                Layout.fillWidth: true; visible: panel.controller.status === "error"
                text: panel.controller.error; wrapMode: Text.Wrap; color: ui.warning; font.pixelSize: Style.type.caption; textFormat: Text.PlainText
            }
            Repeater {
                model: panel.controller.providers
                delegate: Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: providerColumn.implicitHeight + 24
                    radius: Style.radius.card; color: ui.surface; border.width: 1; border.color: ui.border
                    ColumnLayout {
                        id: providerColumn
                        anchors.fill: parent; anchors.margins: 12; spacing: 5
                        RowLayout {
                            Layout.fillWidth: true
                            Text { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.Wrap; text: modelData.displayName; color: ui.text; font.pixelSize: Style.type.title; font.weight: Font.Medium; textFormat: Text.PlainText }
                            Item { Layout.fillWidth: true }
                            Text { Layout.maximumWidth: providerColumn.width / 2; wrapMode: Text.WrapAnywhere; text: modelData.clientVersion ? "v" + modelData.clientVersion : qsTr("sem versão"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                        }
                        Text { Layout.fillWidth: true; text: panel.installationText(modelData); color: ui.textMuted; font.pixelSize: Style.type.caption; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Text { Layout.fillWidth: true; text: panel.protocolText(modelData); color: panel.capability(modelData, "anonymous_protocol") === "supported" ? ui.accent : ui.textMuted; font.pixelSize: Style.type.caption; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Text { Layout.fillWidth: true; visible: panel.messageText(modelData).length > 0; text: panel.messageText(modelData); color: ui.textMuted; font.pixelSize: Style.type.overline; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: consentColumn.implicitHeight + 24
                radius: Style.radius.card; color: Style.alpha(ui.accent, 0.08); border.width: 1; border.color: Style.alpha(ui.accent, 0.45)
                ColumnLayout {
                    id: consentColumn
                    anchors.fill: parent; anchors.margins: 12; spacing: 7
                    Text { Layout.fillWidth: true; text: qsTr("Teste anônimo do Codex"); color: ui.text; font.pixelSize: Style.type.title; font.weight: Font.Medium; textFormat: Text.PlainText }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: ui.textMuted; font.pixelSize: Style.type.caption; textFormat: Text.PlainText
                        text: qsTr("Faz uma verificação local limitada de compatibilidade. Não envia texto pessoal, não entra em conta e não inicia modelo, turno ou geração.")
                    }
                    Text {
                        Layout.fillWidth: true; wrapMode: Text.Wrap; color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText
                        text: qsTr("Autenticação, inferência, cancelamento real, uso e cobrança continuarão não verificados.")
                    }
                    Button {
                        id: probeButton
                        objectName: "aiProbeButton"
                        enabled: !panel.operationStartBlocked || (panel.controller.busy && panel.controller.operation === "probe-codex-anonymous")
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        text: panel.controller.busy && panel.controller.operation === "probe-codex-anonymous" ? qsTr("Cancelar teste") : qsTr("Testar compatibilidade anônima")
                        Accessible.description: qsTr("Consentimento separado para iniciar o teste local limitado do Codex")
                        onClicked: {
                            if (panel.controller.busy && panel.controller.operation === "probe-codex-anonymous")
                                panel.controller.cancel(panel.controller.requestId)
                            else if (!panel.operationStartBlocked && !panel.controller.busy)
                                panel.controller.probeCodex("qml-consent")
                        }
                        contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: ui.accent; font.pixelSize: Style.type.caption; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                        background: Rectangle { radius: Style.radius.control; color: Style.alpha(ui.accent, 0.14); border.width: parent.activeFocus ? 2 : 1; border.color: ui.accent }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: textGenerationColumn.implicitHeight + 28
                radius: Style.radius.popup
                color: ui.surface
                border.width: 1
                border.color: textController.busy ? ui.accent : ui.border
                ColumnLayout {
                    id: textGenerationColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            wrapMode: Text.Wrap
                            text: qsTr("Transformar texto")
                            color: ui.text
                            font.pixelSize: Style.type.title
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                        }
                        Rectangle {
                            Layout.preferredWidth: generationState.implicitWidth + 16
                            Layout.preferredHeight: 24
                            radius: Style.radius.control
                            color: textController.busy ? Style.alpha(ui.accent, 0.18) : ui.raised
                            Text {
                                id: generationState
                                anchors.centerIn: parent
                                text: textController.busy ? qsTr("EM EXECUÇÃO") : qsTr("OPCIONAL")
                                color: textController.busy ? ui.accentHover : ui.textMuted
                                font.pixelSize: Style.type.overline
                                font.letterSpacing: 1
                                textFormat: Text.PlainText
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: qsTr("Envie somente o texto digitado abaixo a um serviço em loopback, após revisar o destino e permitir o envio nesta sessão.")
                        color: ui.textMuted
                        font.pixelSize: Style.type.caption
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: panel.width < 560 ? 1 : 2
                        columnSpacing: 10
                        rowSpacing: 8
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text { text: qsTr("Tarefa"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                            ComboBox {
                                id: taskChoice
                                objectName: "aiTextTask"
                                Layout.fillWidth: true
                                enabled: !textController.busy
                                model: [qsTr("Reescrever"), qsTr("Resumir"), qsTr("Traduzir")]
                                Accessible.name: qsTr("Tarefa de texto")
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text { text: qsTr("Modelo"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                            TextField {
                                id: modelInput
                                objectName: "aiTextModel"
                                Layout.fillWidth: true
                                enabled: !textController.busy
                                text: "gemma3:4b"
                                maximumLength: 128
                                selectByMouse: true
                                Accessible.name: qsTr("Modelo informado explicitamente")
                                onTextEdited: panel.revokeTextConsent()
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text { text: qsTr("Host numérico"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                            ComboBox {
                                id: hostChoice
                                objectName: "aiTextHost"
                                Layout.fillWidth: true
                                enabled: !textController.busy
                                model: ["127.0.0.1", "::1"]
                                Accessible.name: qsTr("Host numérico de loopback")
                                onActivated: panel.revokeTextConsent()
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Text { text: qsTr("Porta"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                            SpinBox {
                                id: portInput
                                objectName: "aiTextPort"
                                Layout.fillWidth: true
                                enabled: !textController.busy
                                from: 1
                                to: 65535
                                value: 11434
                                editable: true
                                Accessible.name: qsTr("Porta do serviço local")
                                onValueModified: panel.revokeTextConsent()
                            }
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: panel.taskValues[taskChoice.currentIndex] === "translate"
                        spacing: 4
                        Text { text: qsTr("Idioma de destino"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                        TextField {
                            id: languageInput
                            objectName: "aiTextLanguage"
                            Layout.fillWidth: true
                            enabled: !textController.busy
                            placeholderText: qsTr("Ex.: português brasileiro")
                            maximumLength: 64
                            selectByMouse: true
                            Accessible.name: qsTr("Idioma de destino")
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: qsTr("Texto a enviar"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                            Item { Layout.fillWidth: true }
                            Text { text: qsTr("%1 / 16.384").arg(textInput.length); color: textInput.length >= 16384 ? ui.warning : ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                        }
                        TextArea {
                            id: textInput
                            objectName: "aiTextInput"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 116
                            enabled: !textController.busy
                            placeholderText: qsTr("Digite ou cole conscientemente o texto para transformar…")
                            color: ui.text
                            placeholderTextColor: ui.textMuted
                            selectionColor: Style.alpha(ui.accent, 0.45)
                            selectedTextColor: ui.text
                            wrapMode: TextEdit.Wrap
                            selectByMouse: true
                            onTextChanged: if (length > 16384) remove(16384, length)
                            Accessible.name: qsTr("Texto enviado ao modelo")
                            background: Rectangle { radius: Style.radius.control; color: ui.sunken; border.width: 1; border.color: textInput.activeFocus ? ui.accent : ui.borderStrong }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: previewColumn.implicitHeight + 20
                        radius: Style.radius.card
                        color: Style.alpha(ui.accent, 0.08)
                        border.width: 1
                        border.color: Style.alpha(ui.accent, 0.45)
                        ColumnLayout {
                            id: previewColumn
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 4
                            Text { Layout.fillWidth: true; text: qsTr("Revise antes de enviar"); color: ui.text; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                            Text { Layout.fillWidth: true; text: qsTr("Destino: %1").arg(panel.normalizedDestination()); color: ui.textMuted; font.pixelSize: Style.type.overline; wrapMode: Text.WrapAnywhere; textFormat: Text.PlainText }
                            Text { Layout.fillWidth: true; text: qsTr("Modelo: %1 · Tarefa: %2").arg(modelInput.text || qsTr("não informado")).arg(panel.taskLabel()); color: ui.textMuted; font.pixelSize: Style.type.overline; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                            Text { Layout.fillWidth: true; text: qsTr("Dados: somente o texto acima%1 · Custo: não informado").arg(languageInput.visible ? qsTr(" e o idioma de destino") : ""); color: ui.textMuted; font.pixelSize: Style.type.overline; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                            Text {
                                Layout.fillWidth: true
                                text: qsTr("Esse endereço é local, mas pode ser outro programa ou encaminhar o texto para a nuvem. O Orla não confirma que é Ollama nem que o processamento é offline.")
                                color: ui.warning
                                font.pixelSize: Style.type.overline
                                wrapMode: Text.Wrap
                                textFormat: Text.PlainText
                            }
                        }
                    }
                    CheckBox {
                        id: textConsent
                        objectName: "aiTextConsent"
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.max(44, consentLabel.implicitHeight + 12)
                        enabled: !textController.busy
                        text: qsTr("Permitir envio ao programa neste endereço nesta sessão")
                        Accessible.description: qsTr("Autoriza somente este destino, porta e modelo; alterações revogam a permissão")
                        contentItem: Text {
                            id: consentLabel
                            leftPadding: textConsent.indicator.width + textConsent.spacing
                            text: textConsent.text
                            color: textConsent.enabled ? ui.text : ui.textMuted
                            font.pixelSize: Style.type.caption
                            verticalAlignment: Text.AlignVCenter
                            wrapMode: Text.Wrap
                            textFormat: Text.PlainText
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            id: generateButton
                            objectName: "aiTextGenerate"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42
                            enabled: textController.busy || (!panel.operationStartBlocked && textConsent.checked && modelInput.text.length > 0
                                     && textInput.length > 0
                                     && (panel.taskValues[taskChoice.currentIndex] !== "translate" || languageInput.text.length > 0))
                            text: textController.busy ? qsTr("Cancelar") : qsTr("Gerar")
                            Accessible.description: textController.busy ? qsTr("Interrompe a geração e preserva o resultado parcial") : qsTr("Envia o texto somente após consentimento explícito")
                            onClicked: {
                                if (textController.busy) {
                                    textController.cancel(textController.requestId)
                                    return
                                }
                                if (panel.operationStartBlocked) return
                                panel.textRequestGeneration += 1
                                textController.generate("orla-qml-" + panel.textRequestGeneration,
                                    panel.taskValues[taskChoice.currentIndex],
                                    panel.taskValues[taskChoice.currentIndex] === "translate" ? languageInput.text : null,
                                    textInput.text, modelInput.text,
                                    hostChoice.currentIndex === 0 ? "127.0.0.1" : "::1",
                                    portInput.value, textConsent.checked)
                            }
                            contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? ui.onAccent : ui.textMuted; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                            background: Rectangle { radius: Style.radius.control; color: parent.enabled ? ui.accent : ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: ui.text }
                        }
                    }
                    Text {
                        id: generationAnnouncement
                        objectName: "aiTextStatus"
                        Layout.fillWidth: true
                        text: panel.terminalStatusText()
                        color: textController.status === "failed" || textController.status === "cancelled_unconfirmed" ? ui.warning : ui.textMuted
                        font.pixelSize: Style.type.overline
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                        Accessible.role: Accessible.StaticText
                        Accessible.name: text
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: textController.output.length > 0 || textController.status !== "disabled"
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: qsTr("Resultado revisável"); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                            Item { Layout.fillWidth: true }
                            Text { text: qsTr("Uso: %1 · Custo: não informado").arg(textController.usage.status === "reported" ? qsTr("reportado") : qsTr("desconhecido")); color: ui.textMuted; font.pixelSize: Style.type.overline; textFormat: Text.PlainText }
                        }
                        TextArea {
                            id: resultOutput
                            objectName: "aiTextResult"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 132
                            readOnly: true
                            color: ui.text
                            selectionColor: Style.alpha(ui.accent, 0.45)
                            selectedTextColor: ui.text
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            text: textController.output
                            Accessible.name: qsTr("Resultado gerado, somente leitura")
                            background: Rectangle { radius: Style.radius.control; color: ui.sunken; border.width: 1; border.color: resultOutput.activeFocus ? ui.accent : ui.borderStrong }
                        }
                        Button {
                            id: copyButton
                            objectName: "aiTextCopy"
                            Layout.alignment: Qt.AlignRight
                            enabled: textController.output.length > 0
                            text: qsTr("Copiar resultado")
                            Accessible.description: qsTr("Copia somente o resultado gerado por ação explícita")
                            onClicked: {
                                resultOutput.selectAll()
                                resultOutput.copy()
                                resultOutput.deselect()
                            }
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: textController.status === "cancelled_confirmed" || textController.status === "cancelled_unconfirmed"
                        text: qsTr("Fechar a conexão não garante que o programa ou modelo deixou de processar o pedido.")
                        color: ui.warning
                        font.pixelSize: Style.type.overline
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                    }
                }
            }
            Item { Layout.preferredHeight: 4 }
        }
    }
}
