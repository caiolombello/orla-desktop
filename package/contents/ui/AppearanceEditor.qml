import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import "../code/Style.js" as Style
import "../code/Appearance.js" as Appearance

ColumnLayout {
    id: editor
    required property var appearance
    property var preset: null
    readonly property bool importing: preset !== null && preset.dirty
    signal profilesRequested()
    signal canceled()
    spacing: Style.space.sm
    property var focusReveal: null
    property bool advancedOpen: false
    property bool themeOpen: false
    readonly property string advancedColorField: {
        if (!appearance || !appearance.draft) return "";
        const result = Appearance.validateTokens(appearance.draft.tokens);
        for (const issue of result.errors || []) {
            const prefix = "$/tokens/";
            if (!issue.field.startsWith(prefix)) continue;
            const key = issue.field.substring(prefix.length);
            if (Appearance.colorKeys.indexOf(key) >= 0) return key;
        }
        return "";
    }
    readonly property bool themeIssue: !!appearance && (appearance.themePending || appearance.themeError.length > 0)
    readonly property bool themeAttention: themeIssue || (importing && appearance.themeText.length > 0)
    readonly property bool advancedIssue: advancedColorField.length > 0 || themeAttention
    onAdvancedColorFieldChanged: if (advancedColorField.length) showAdvancedIssue()
    onThemeAttentionChanged: if (themeAttention) showAdvancedIssue()
    onAppearanceChanged: resetSections()
    onImportingChanged: if (!importing) showAdvancedIssue()
    Component.onCompleted: { resetSections(); showAdvancedIssue(); }
    Connections {
        target: editor.appearance
        function onEditingChanged() { editor.resetSections(); editor.showAdvancedIssue(); }
    }
    function restoreSectionFocus(section, target) {
        const captured = focusReveal;
        if (!captured || !captured.owner || !captured.owner.activeFocus) return;
        let owner = captured.owner;
        while (owner && owner !== section) owner = owner.parent;
        if (!owner) return;
        if (visible && appearance && appearance.editing && target.enabled)
            target.forceActiveFocus(Qt.TabFocusReason);
        if (focusReveal === captured) focusReveal = null;
    }
    function setThemeOpen(requested, reset = false, fallback = themeDisclosure) {
        if (!themeDisclosure || !themeFields) return;
        const next = !!requested || (!reset && themeAttention && appearance.editing);
        // Move focus before visibility changes, including programmatic collapse.
        if (!next) restoreSectionFocus(themeFields, fallback);
        themeOpen = next;
        themeDisclosure.checked = next;
    }
    function setAdvancedOpen(requested, reset = false, fallback = advancedDisclosure) {
        if (!advancedDisclosure || !advancedFields) return;
        const next = !!requested || (!reset && advancedIssue && appearance.editing);
        if (!next) {
            restoreSectionFocus(advancedFields, fallback);
            setThemeOpen(false, true, fallback);
        }
        advancedOpen = next;
        advancedDisclosure.checked = next;
        if (next && themeAttention) setThemeOpen(true);
    }
    function resetSections(fallback = advancedDisclosure) {
        if (!advancedDisclosure || !themeDisclosure) return;
        setAdvancedOpen(false, true, fallback);
        focusReveal = null;
    }
    function showAdvancedIssue() {
        if (appearance && appearance.editing && (advancedColorField.length > 0 || themeAttention))
            setAdvancedOpen(true);
    }
    function reveal(control, owner) {
        focusReveal = {control:control, owner:owner || control};
        revealNow(control);
        Qt.callLater(() => { if (editor) editor.revealFocused(); });
    }
    function revealFocused() {
        const target = focusReveal;
        if (target && target.owner && target.control && editor.visible && target.owner.activeFocus && target.control.visible) revealNow(target.control);
    }
    function revealNow(control) {
        const viewport = fields.contentItem;
        const point = control.mapToItem(viewport, 0, 0);
        const margin = Style.space.xs;
        if (point.y < margin) viewport.contentY += point.y - margin;
        else if (point.y + control.height + margin > viewport.height)
            viewport.contentY += point.y + control.height + margin - viewport.height;
    }
    Controls.Label {
        Layout.fillWidth: true
        text: qsTr("Prévia no dock. Aplicar salva; Cancelar ou fechar descarta a prévia.")
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        font.pixelSize: Style.type.caption
        opacity: 0.72
    }
    Controls.ScrollView {
        id: fields
        onHeightChanged: Qt.callLater(() => { if (editor) editor.revealFocused(); })
        onContentHeightChanged: Qt.callLater(() => { if (editor) editor.revealFocused(); })
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.preferredHeight: 320
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            x: Style.space.xs
            width: fields.availableWidth - 2 * Style.space.xs
            spacing: Style.space.sm
            Item { Layout.preferredHeight: Style.space.xxs }
            AppearancePresetControls {
                Layout.fillWidth: true
                visible: editor.preset !== null
                preset: editor.preset || ({dirty:false, managed:false, busy:false, editing:false, inputText:"", exportText:""})
                onFocusRequested: (control, owner) => editor.reveal(control, owner)
                onProfilesRequested: editor.profilesRequested()
            }
            SectionLabel { text: qsTr("Ponto de partida") }
            RowLayout {
                Layout.fillWidth: true
                spacing: Style.space.sm
                Repeater {
                    model: [{key: "glass", label: "Vidro"}, {key: "midnight", label: "Meia-noite"}, {key: "paper", label: "Papel"}]
                    // Theme card: a miniature of the dock body with its accent.
                    Templates.Button {
                        id: themeCard
                        required property var modelData
                        readonly property var theme: Style.dockTheme(modelData.key)
                        objectName: "appearanceTheme" + modelData.key
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        implicitWidth: implicitContentWidth + leftPadding + rightPadding
                        implicitHeight: implicitContentHeight + topPadding + bottomPadding
                        padding: Style.space.sm
                        text: modelData.label
                        checkable: true
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        Accessible.name: text
                        enabled: !editor.importing
                        checked: editor.appearance.draft && editor.appearance.draft.baseTheme === modelData.key
                        onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                        onClicked: editor.appearance.selectTheme(modelData.key)
                        contentItem: ColumnLayout {
                            spacing: Style.space.xs + 2
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 26
                                radius: Style.radius.control
                                color: themeCard.theme.surface
                                border.width: 1
                                border.color: themeCard.theme.border
                                Row {
                                    anchors.centerIn: parent
                                    spacing: Style.space.xs
                                    Repeater {
                                        model: 3
                                        Rectangle {
                                            required property int index
                                            width: Style.space.sm + 2
                                            height: width
                                            radius: width / 2
                                            color: index === 1 ? themeCard.theme.accent : Style.alpha(themeCard.theme.foreground, 0.55)
                                        }
                                    }
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: themeCard.text
                                textFormat: Text.PlainText
                                font.pixelSize: Style.type.label
                                font.weight: themeCard.checked ? Style.weight.demiBold : Style.weight.medium
                                color: themeCard.palette.windowText
                                horizontalAlignment: Text.AlignHCenter
                                elide: Text.ElideRight
                            }
                        }
                        background: Rectangle {
                            radius: Style.radius.card - 2
                            color: themeCard.checked ? Style.alpha(themeCard.palette.highlight, 0.12)
                                : themeCard.hovered ? Style.alpha(themeCard.palette.windowText, Style.state.hover) : "transparent"
                            border.width: themeCard.checked || themeCard.visualFocus ? 2 : 1
                            border.color: themeCard.checked || themeCard.visualFocus ? themeCard.palette.highlight
                                : Style.alpha(themeCard.palette.windowText, 0.12)
                        }
                    }
                }
            }
            SectionLabel { text: qsTr("Forma e movimento") }
            Card {
                enabled: !editor.importing
                Layout.fillWidth: true
                padding: 0
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    Repeater {
                        model: [{key: "opacity", label: qsTr("Opacidade (%)"), minimum: 40, maximum: 100, scale: 100},
                            {key: "radius", label: qsTr("Cantos (px)"), minimum: 0, maximum: 32, scale: 1},
                            {key: "spacing", label: qsTr("Espaçamento (px)"), minimum: 0, maximum: 16, scale: 1},
                            {key: "iconSize", label: qsTr("Ícones (px)"), minimum: 24, maximum: 64, scale: 1}]
                        FormRow {
                            required property var modelData
                            Controls.Label { Layout.fillWidth: true; text: modelData.label; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
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
                    FormRow {
                        last: true
                        Controls.CheckBox {
                            objectName: "appearanceReducedMotion"
                            Layout.fillWidth: true
                            text: qsTr("Movimento reduzido")
                            checked: editor.appearance.draft ? editor.appearance.draft.tokens.reducedMotion : false
                            onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                            onToggled: editor.appearance.setToken("reducedMotion", checked)
                        }
                    }
                }
            }
            OrlaButton {
                id: advancedDisclosure
                objectName: "appearanceAdvanced"
                Layout.fillWidth: true
                text: checked ? qsTr("Recolher ajustes avançados") : qsTr("Ajustes avançados")
                checkable: true
                enabled: !editor.importing || editor.themeAttention
                Accessible.description: checked ? qsTr("Seção expandida") : qsTr("Seção recolhida")
                onCheckedChanged: editor.setAdvancedOpen(checked)
                onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                Keys.onReturnPressed: event => { toggle(); event.accepted = true; }
            }
            ColumnLayout {
                id: advancedFields
                objectName: "appearanceAdvancedSection"
                Layout.fillWidth: true
                spacing: Style.space.sm
                visible: editor.advancedOpen
                SectionLabel { text: qsTr("Cores · #RRGGBB") }
                Card {
                    enabled: !editor.importing
                    Layout.fillWidth: true
                    padding: 0
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0
                        Repeater {
                            id: colorRows
                            model: [{key: "foreground", label: qsTr("Texto")}, {key: "muted", label: qsTr("Texto secundário")},
                                {key: "accent", label: qsTr("Destaque")}, {key: "surface", label: qsTr("Superfície")}, {key: "border", label: qsTr("Borda")}]
                            FormRow {
                                required property var modelData
                                required property int index
                                last: index === colorRows.count - 1
                                Controls.Label { Layout.fillWidth: true; text: modelData.label; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
                                Rectangle {
                                    implicitWidth: Style.size.iconMd; implicitHeight: Style.size.iconMd; radius: width / 2
                                    color: editor.appearance.effective.tokens[modelData.key]
                                    border.color: Style.alpha(palette.windowText, 0.3)
                                }
                                Controls.TextField {
                                    objectName: "appearanceColor" + modelData.key
                                    Layout.preferredWidth: 96
                                    Accessible.name: modelData.label + qsTr(" · cor hexadecimal")
                                    selectByMouse: true
                                    maximumLength: 16
                                    text: editor.appearance.draft ? editor.appearance.draft.tokens[modelData.key] : ""
                                    onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                                    onTextEdited: editor.appearance.setToken(modelData.key, text)
                                }
                            }
                        }
                    }
                }
                Controls.Button {
                    id: themeDisclosure
                    enabled: !editor.importing || editor.themeAttention
                    objectName: "appearanceThemeJSON"
                    Layout.fillWidth: true
                    text: qsTr("Tema JSON experimental")
                    checkable: true
                    Accessible.name: text
                    Accessible.description: checked ? qsTr("Seção expandida") : qsTr("Seção recolhida")
                    KeyNavigation.tab: editor.themeOpen ? themeInput : null
                    onCheckedChanged: editor.setThemeOpen(checked)
                    Keys.onReturnPressed: event => { toggle(); event.accepted = true; }
                    onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                }
                ColumnLayout {
                    id: themeFields
                    Layout.fillWidth: true
                    visible: editor.themeOpen
                    Controls.Label {
                        Layout.fillWidth: true
                        text: qsTr("Cole o JSON de um tema 0.1-experimental. Usar na prévia substitui os ajustes desta prévia; Aplicar salva neste perfil.")
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        visible: editor.themeAttention && (editor.importing || editor.appearance.themePending)
                        text: editor.importing ? qsTr("Limpe este JSON de tema para continuar com a aparência portátil.")
                            : qsTr("Use na prévia ou limpe o JSON para habilitar Aplicar.")
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                        font.pixelSize: Style.type.caption
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
                            enabled: editor.appearance.editing && !editor.importing
                            KeyNavigation.priority: KeyNavigation.BeforeItem
                            KeyNavigation.tab: themePreview
                            KeyNavigation.backtab: themeDisclosure
                            onTextChanged: if (text !== editor.appearance.themeText) editor.appearance.setThemeText(text)
                            onActiveFocusChanged: if (activeFocus) editor.reveal(themeScroll, themeInput)
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
                            enabled: editor.appearance.editing && !editor.importing && !editor.appearance.stale && editor.appearance.themeText.length > 0
                            onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                            onClicked: {
                                if (!editor.appearance.previewTheme()) themeInput.forceActiveFocus();
                            }
                        }
                        Controls.Button {
                            objectName: "appearanceThemeClear"
                            text: qsTr("Limpar JSON")
                            enabled: editor.appearance.editing && (!editor.preset || !editor.preset.busy)
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
            }
            OrlaButton {
                objectName: "appearanceDefaults"
                enabled: !editor.importing
                variant: "ghost"
                text: qsTr("Restaurar aparência anterior ao editor")
                Layout.fillWidth: true
                onActiveFocusChanged: if (activeFocus) editor.reveal(this)
                onClicked: editor.appearance.restoreDefaults()
            }
            Item { Layout.preferredHeight: Style.space.xxs }
        }
    }
    Controls.Label {
        objectName: "appearanceError"
        Layout.fillWidth: true
        visible: text.length > 0
        text: editor.preset && editor.preset.error.length ? editor.preset.error
            : editor.appearance.stale ? qsTr("A aparência salva mudou. Cancele e abra novamente antes de aplicar.")
            : editor.appearance.themeError || editor.appearance.error
                || (editor.appearance.saved.error ? qsTr("Aparência salva inválida; usando as preferências anteriores.") : "")
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        Accessible.role: Accessible.AlertMessage
    }
    Controls.Label {
        Layout.fillWidth: true
        visible: text.length > 0
        text: editor.preset && editor.preset.message.length ? editor.preset.message : editor.appearance.message
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Style.space.sm
        OrlaButton { objectName: "appearanceApply"; Keys.onReturnPressed: event => { clicked(); event.accepted = true; }; variant: "primary"; text: qsTr("Aplicar"); enabled: editor.importing ? editor.preset.canApply : editor.appearance.canApply; onClicked: editor.importing ? editor.preset.apply() : editor.appearance.apply() }
        OrlaButton { objectName: "appearanceCancel"; text: qsTr("Cancelar"); onClicked: { if (editor.preset) editor.preset.cancel(); else editor.appearance.cancel(); editor.canceled(); } }
        Item { Layout.fillWidth: true }
        OrlaButton { objectName: "appearanceUndo"; Keys.onReturnPressed: event => { clicked(); event.accepted = true; }; variant: "ghost"; text: qsTr("Desfazer"); enabled: !editor.importing && (editor.preset && editor.preset.canUndo || editor.appearance.canUndo); onClicked: editor.preset && editor.preset.canUndo ? editor.preset.undo() : editor.appearance.undo() }
    }
}
