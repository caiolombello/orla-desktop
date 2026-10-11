import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

ColumnLayout {
    id: editor
    required property var appearance
    signal canceled()
    spacing: 8
    function reveal(control) {
        const viewport = fields.contentItem;
        const point = control.mapToItem(viewport, 0, 0);
        if (point.y < 0) viewport.contentY += point.y;
        else if (point.y + control.height > viewport.height)
            viewport.contentY += point.y + control.height - viewport.height;
    }
    Controls.Label {
        Layout.fillWidth: true
        text: qsTr("Prévia no dock. Aplicar salva; Cancelar ou fechar descarta a prévia.")
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
    Controls.ScrollView {
        id: fields
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.preferredHeight: 320
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            width: fields.availableWidth
            spacing: 8
            Controls.Label { text: qsTr("Ponto de partida"); font.bold: true }
            RowLayout {
                Repeater {
                    model: [{key: "glass", label: "Vidro"}, {key: "midnight", label: "Meia-noite"}, {key: "paper", label: "Papel"}]
                    Controls.Button {
                        required property var modelData
                        objectName: "appearanceTheme" + modelData.key
                        text: modelData.label
                        checkable: true
                        checked: editor.appearance.draft && editor.appearance.draft.baseTheme === modelData.key
                        onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                        onClicked: editor.appearance.selectTheme(modelData.key)
                    }
                }
            }
            Controls.Button {
                id: themeDisclosure
                objectName: "appearanceThemeJSON"
                Layout.fillWidth: true
                text: qsTr("Tema JSON experimental")
                checkable: true
                Accessible.name: text
                Accessible.description: checked ? qsTr("Seção expandida") : qsTr("Seção recolhida")
                KeyNavigation.tab: checked ? themeInput : null
                onActiveFocusChanged: if (activeFocus) editor.reveal(this)
            }
            ColumnLayout {
                Layout.fillWidth: true
                visible: themeDisclosure.checked
                Controls.Label {
                    Layout.fillWidth: true
                    text: qsTr("Cole o JSON de um tema 0.1-experimental. Usar na prévia substitui os ajustes desta prévia; Aplicar salva neste perfil.")
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                Controls.ScrollView {
                    id: themeScroll
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    Layout.minimumHeight: 120
                    Layout.maximumHeight: 120
                    contentWidth: availableWidth
                    clip: true
                    Controls.TextArea {
                        id: themeInput
                        objectName: "appearanceThemeInput"
                        Accessible.name: qsTr("JSON do tema experimental")
                        textFormat: TextEdit.PlainText
                        wrapMode: TextEdit.Wrap
                        selectByMouse: true
                        text: editor.appearance.themeText
                        enabled: editor.appearance.editing
                        KeyNavigation.priority: KeyNavigation.BeforeItem
                        KeyNavigation.tab: themePreview
                        KeyNavigation.backtab: themeDisclosure
                        onTextChanged: if (text !== editor.appearance.themeText) editor.appearance.setThemeText(text)
                        onActiveFocusChanged: if (activeFocus) editor.reveal(themeScroll)
                        onCursorRectangleChanged: {
                            if (!activeFocus) return;
                            const viewport = themeScroll.contentItem;
                            if (cursorRectangle.y < viewport.contentY) viewport.contentY = cursorRectangle.y;
                            else if (cursorRectangle.y + cursorRectangle.height > viewport.contentY + viewport.height)
                                viewport.contentY = cursorRectangle.y + cursorRectangle.height - viewport.height;
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Button {
                        id: themePreview
                        objectName: "appearanceThemePreview"
                        text: qsTr("Usar na prévia")
                        enabled: editor.appearance.editing && !editor.appearance.stale && editor.appearance.themeText.length > 0
                        onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                        onClicked: {
                            if (!editor.appearance.previewTheme()) themeInput.forceActiveFocus();
                        }
                    }
                    Controls.Button {
                        objectName: "appearanceThemeClear"
                        text: qsTr("Limpar JSON")
                        enabled: editor.appearance.editing
                        onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                        onClicked: editor.appearance.clearThemeInput()
                    }
                }
                Controls.Label {
                    objectName: "appearanceThemeMetadata"
                    Layout.fillWidth: true
                    visible: editor.appearance.themeMetadata !== null
                    text: editor.appearance.themeMetadata ?
                        (editor.appearance.themeModified ? qsTr("Base importada: ") : qsTr("Tema: "))
                        + editor.appearance.themeMetadata.name + "\n"
                        + qsTr("Autor: ") + editor.appearance.themeMetadata.author + "\n"
                        + qsTr("Versão: ") + editor.appearance.themeMetadata.version + " · "
                        + qsTr("Licença: ") + editor.appearance.themeMetadata.license + "\n"
                        + qsTr("Declarações do arquivo; direitos e identidade não verificados.") : ""
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }
            }
            Controls.Label { text: qsTr("Cores · #RRGGBB"); font.bold: true }
            Repeater {
                model: [{key: "foreground", label: qsTr("Texto")}, {key: "muted", label: qsTr("Texto secundário")},
                    {key: "accent", label: qsTr("Destaque")}, {key: "surface", label: qsTr("Superfície")}, {key: "border", label: qsTr("Borda")}]
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Controls.Label { Layout.fillWidth: true; text: modelData.label; wrapMode: Text.WordWrap }
                    Rectangle {
                        implicitWidth: 20; implicitHeight: 20; radius: 4
                        color: editor.appearance.effective.tokens[modelData.key]
                        border.color: "#808080"
                    }
                    Controls.TextField {
                        objectName: "appearanceColor" + modelData.key
                        Layout.preferredWidth: 104
                        Accessible.name: modelData.label + qsTr(" · cor hexadecimal")
                        selectByMouse: true
                        maximumLength: 16
                        text: editor.appearance.draft ? editor.appearance.draft.tokens[modelData.key] : ""
                        onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                        onTextEdited: editor.appearance.setToken(modelData.key, text)
                    }
                }
            }
            Controls.Label { text: qsTr("Forma e movimento"); font.bold: true }
            Repeater {
                model: [{key: "opacity", label: qsTr("Opacidade (%)"), minimum: 40, maximum: 100, scale: 100},
                    {key: "radius", label: qsTr("Cantos (px)"), minimum: 0, maximum: 32, scale: 1},
                    {key: "spacing", label: qsTr("Espaçamento (px)"), minimum: 0, maximum: 16, scale: 1},
                    {key: "iconSize", label: qsTr("Ícones (px)"), minimum: 24, maximum: 64, scale: 1}]
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Controls.Label { Layout.fillWidth: true; text: modelData.label; wrapMode: Text.WordWrap }
                    Controls.SpinBox {
                        objectName: "appearanceNumber" + modelData.key
                        Accessible.name: modelData.label
                        from: modelData.minimum; to: modelData.maximum
                        value: editor.appearance.draft ? Math.round(editor.appearance.draft.tokens[modelData.key] * modelData.scale) : from
                        onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                        onValueModified: editor.appearance.setToken(modelData.key, value / modelData.scale)
                    }
                }
            }
            Controls.CheckBox {
                objectName: "appearanceReducedMotion"
                text: qsTr("Movimento reduzido")
                checked: editor.appearance.draft ? editor.appearance.draft.tokens.reducedMotion : false
                onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                onToggled: editor.appearance.setToken("reducedMotion", checked)
            }
            Controls.Button {
                objectName: "appearanceDefaults"
                text: qsTr("Restaurar aparência anterior ao editor")
                Layout.fillWidth: true
                onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                onClicked: editor.appearance.restoreDefaults()
            }
        }
    }
    Controls.Label {
        objectName: "appearanceError"
        Layout.fillWidth: true
        visible: text.length > 0
        text: editor.appearance.stale ? qsTr("A aparência salva mudou. Cancele e abra novamente antes de aplicar.")
            : editor.appearance.themeError || editor.appearance.error
                || (editor.appearance.saved.error ? qsTr("Aparência salva inválida; usando as preferências anteriores.") : "")
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        Accessible.role: Accessible.AlertMessage
    }
    Controls.Label {
        Layout.fillWidth: true
        visible: text.length > 0
        text: editor.appearance.message
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
    RowLayout {
        Layout.fillWidth: true
        Controls.Button { objectName: "appearanceApply"; text: qsTr("Aplicar"); enabled: editor.appearance.canApply; onClicked: editor.appearance.apply() }
        Controls.Button { objectName: "appearanceCancel"; text: qsTr("Cancelar"); onClicked: { editor.appearance.cancel(); editor.canceled(); } }
        Controls.Button { objectName: "appearanceUndo"; text: qsTr("Desfazer"); enabled: editor.appearance.canUndo; onClicked: editor.appearance.undo() }
    }
}
