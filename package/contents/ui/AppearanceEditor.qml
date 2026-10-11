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
        text: editor.appearance.error || (editor.appearance.saved.error ? qsTr("Aparência salva inválida; usando as preferências anteriores.") : "")
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
