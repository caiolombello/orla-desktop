import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

ColumnLayout {
    id: controls
    required property var preset
    signal focusRequested(var control, var owner)
    signal profilesRequested()
    spacing: Style.space.sm
    OrlaButton {
        id: disclosure
        objectName: "appearancePresetJSON"
        Layout.fillWidth: true
        text: checked ? qsTr("Recolher aparência portátil") : qsTr("Aparência portátil experimental")
        checkable: true
        Accessible.description: checked ? qsTr("Seção expandida") : qsTr("Seção recolhida")
        KeyNavigation.tab: checked ? exporter : null
        onActiveFocusChanged: if (activeFocus) controls.focusRequested(this, this)
    }
    Card {
        Layout.fillWidth: true
        visible: disclosure.checked
        radius: Style.radius.module
        contentItem: ColumnLayout {
            spacing: Style.space.sm
            SectionLabel { text: qsTr("Levar seu dock") }
            Controls.Label {
                Layout.fillWidth: true
                text: qsTr("Só aparência, ordem e visibilidade dos widgets. Apps, perfis, eventos e dados pessoais ficam de fora.")
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
            OrlaButton {
                id: exporter
                objectName: "appearancePresetExport"
                KeyNavigation.tab: outputScroll.visible ? output : controls.preset.managed ? input : profileLink
                KeyNavigation.backtab: disclosure
                Layout.fillWidth: true
                text: qsTr("Exportar aparência salva")
                enabled: !controls.preset.busy
                onActiveFocusChanged: if (activeFocus) controls.focusRequested(this, this)
                onClicked: { if (controls.preset.exportSaved()) output.forceActiveFocus(); }
            }
            Controls.Label {
                Layout.fillWidth: true
                visible: controls.preset.exportText.length > 0
                text: qsTr("Selecione o JSON abaixo e copie manualmente para guardar ou compartilhar.")
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
            Controls.ScrollView {
                id: outputScroll
                Layout.fillWidth: true
                Layout.preferredHeight: Style.size.target * 2
                visible: controls.preset.exportText.length > 0
                contentWidth: availableWidth
                clip: true
                Controls.TextArea {
                    id: output
                    objectName: "appearancePresetOutput"
                    Accessible.name: qsTr("JSON exportado; selecione e copie manualmente")
                    text: controls.preset.exportText
                    readOnly: true
                    selectByMouse: true
                    textFormat: TextEdit.PlainText
                    wrapMode: TextEdit.Wrap
                    KeyNavigation.priority: KeyNavigation.BeforeItem
                    KeyNavigation.tab: controls.preset.managed ? input : profileLink
                    KeyNavigation.backtab: exporter
                    onActiveFocusChanged: if (activeFocus) controls.focusRequested(outputScroll, output)
                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        radius: Style.radius.control
                        border.width: output.activeFocus ? 2 : 0
                        border.color: output.palette.highlight
                    }
                }
            }
            SectionLabel { text: qsTr("Trazer uma aparência") }
            Controls.Label {
                Layout.fillWidth: true
                text: controls.preset.managed ? qsTr("Cole o JSON exportado e use na prévia. Aplicar salva aparência e widgets juntos; Cancelar descarta.")
                    : qsTr("Para importar, crie ou escolha um perfil na aba Perfis. Você já pode exportar suas preferências anteriores.")
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
            OrlaButton {
                id: profileLink
                objectName: "appearancePresetProfiles"
                KeyNavigation.backtab: outputScroll.visible ? output : exporter
                Layout.fillWidth: true
                visible: !controls.preset.managed
                text: qsTr("Ir para Perfis")
                onActiveFocusChanged: if (activeFocus) controls.focusRequested(this, this)
                onClicked: controls.profilesRequested()
            }
            Controls.ScrollView {
                id: inputScroll
                Layout.fillWidth: true
                Layout.preferredHeight: Style.size.target * 3
                contentWidth: availableWidth
                clip: true
                Controls.TextArea {
                    id: input
                    objectName: "appearancePresetInput"
                    Accessible.name: qsTr("JSON da aparência portátil")
                    text: controls.preset.inputText
                    enabled: controls.preset.managed && controls.preset.editing && !controls.preset.busy
                    selectByMouse: true
                    textFormat: TextEdit.PlainText
                    wrapMode: TextEdit.Wrap
                    KeyNavigation.priority: KeyNavigation.BeforeItem
                    KeyNavigation.tab: preview.enabled ? preview : clear
                    KeyNavigation.backtab: outputScroll.visible ? output : exporter
                    onTextChanged: if (text !== controls.preset.inputText) controls.preset.setInputText(text)
                    onActiveFocusChanged: if (activeFocus) controls.focusRequested(inputScroll, input)
                    onCursorRectangleChanged: {
                        if (!activeFocus) return;
                        const viewport = inputScroll.contentItem;
                        if (cursorRectangle.y < viewport.contentY) viewport.contentY = cursorRectangle.y;
                        else if (cursorRectangle.y + cursorRectangle.height > viewport.contentY + viewport.height)
                            viewport.contentY = cursorRectangle.y + cursorRectangle.height - viewport.height;
                    }
                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        radius: Style.radius.control
                        border.width: input.activeFocus ? 2 : 0
                        border.color: input.palette.highlight
                    }
                }
            }
            OrlaButton {
                id: preview
                objectName: "appearancePresetPreview"
                Keys.onReturnPressed: event => { clicked(); event.accepted = true; }
                Layout.fillWidth: true
                text: qsTr("Usar na prévia")
                enabled: controls.preset.managed && controls.preset.editing && !controls.preset.busy && controls.preset.inputText.length > 0
                onActiveFocusChanged: if (activeFocus) controls.focusRequested(this, this)
                onClicked: { if (!controls.preset.previewImport()) input.forceActiveFocus(); }
            }
            OrlaButton {
                id: clear
                objectName: "appearancePresetClear"
                KeyNavigation.backtab: preview.enabled ? preview : input
                Layout.fillWidth: true
                variant: "ghost"
                text: qsTr("Limpar JSON de importação")
                enabled: controls.preset.editing && !controls.preset.busy
                onActiveFocusChanged: if (activeFocus) controls.focusRequested(this, this)
                onClicked: controls.preset.clearInput()
            }
        }
    }
}
