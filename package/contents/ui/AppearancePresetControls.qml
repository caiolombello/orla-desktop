import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style
import "../code/AppearancePreset.js" as Preset
import "../code/AppearancePresetCatalog.js" as Catalog

ColumnLayout {
    id: controls
    required property var preset
    readonly property var choices: Catalog.entries()
    readonly property string previewId: {
        if (!preset.hasPreview) return "";
        const appearance = JSON.stringify(preset.appearance.effective);
        const widgets = JSON.stringify(preset.previewWidgets);
        const entry = choices.find(option => JSON.stringify(option.payload.appearance) === appearance
            && JSON.stringify(option.payload.widgets) === widgets);
        return entry ? entry.id : "";
    }
    signal focusRequested(var control, var owner)
    signal profilesRequested()
    spacing: Style.space.sm
    property bool catalogOpen: false
    property bool portableOpen: false
    property var focusTarget: null
    readonly property bool editing: Boolean(preset.editing)
    readonly property bool importAttention: Boolean(preset.pending || (preset.error && preset.error.length))
    onEditingChanged: resetSections()
    onPresetChanged: { resetSections(); Qt.callLater(controls.revealImportIssue); }
    // Catalog selection validates synchronously; reveal only an issue that
    // remains after that action, rather than opening JSON for every preset.
    onImportAttentionChanged: if (importAttention) Qt.callLater(controls.revealImportIssue)
    Component.onCompleted: { resetSections(); revealImportIssue(); }
    function rememberFocus(control, owner) {
        focusTarget = {control:control, owner:owner || control};
        focusRequested(control, owner || control);
    }
    function releaseSectionFocus(section, target) {
        const captured = focusTarget;
        if (!captured || !captured.owner || !captured.owner.activeFocus) return;
        let item = captured.owner;
        while (item && item !== section) item = item.parent;
        if (!item) return;
        if (visible && editing && target.enabled) target.forceActiveFocus(Qt.TabFocusReason);
        if (focusTarget === captured) focusTarget = null;
    }
    function setPortableOpen(requested, reset = false) {
        if (!disclosure || !portableFields) return;
        const next = !!requested || (!reset && editing && importAttention);
        if (!next) releaseSectionFocus(portableFields, disclosure);
        if (next && !catalogOpen) setCatalogOpen(true);
        portableOpen = next;
        disclosure.checked = next;
    }
    function setCatalogOpen(requested, reset = false) {
        if (!catalogDisclosure || !catalogFields) return;
        const next = !!requested || (!reset && editing && importAttention);
        if (!next) {
            releaseSectionFocus(catalogFields, catalogDisclosure);
            setPortableOpen(false, true);
        }
        catalogOpen = next;
        catalogDisclosure.checked = next;
    }
    function resetSections() {
        if (!catalogDisclosure || !disclosure) return;
        setCatalogOpen(false, true);
        focusTarget = null;
    }
    function revealImportIssue() {
        if (!editing || !importAttention) return;
        setCatalogOpen(true);
        setPortableOpen(true);
    }
    function nameFor(id) {
        return ({essencial:qsTr("Essencial"), mare:qsTr("Maré"), estudio:qsTr("Estúdio"), jogo:qsTr("Jogo"),
            macos:qsTr("macOS")})[id] || "";
    }
    function descriptionFor(id) {
        return ({essencial:qsTr("Claro e opaco; relógio e bateria. Movimento reduzido."),
            mare:qsTr("Vidro translúcido; relógio, música e bateria. Movimento normal."),
            estudio:qsTr("Escuro opaco; Pomodoro e mídia. Movimento reduzido."),
            jogo:qsTr("Escuro opaco; música primeiro, relógio e bateria. Movimento normal."),
            macos:qsTr("Vidro translúcido, ícones maiores e só apps, como o Dock do macOS. Movimento normal.")})[id] || "";
    }
    function choose(id) {
        if (!preset.managed || !preset.editing || preset.busy) return false;
        const target = preset, appearance = target.appearance, draft = appearance.draft;
        const scope = target.scope, revision = target.revision;
        const text = Preset.serialize(Catalog.payload(id));
        if (!text.length) return false;
        target.setInputText(text);
        // A synchronous input observer can cancel or replace this intent.
        if (preset !== target || target.appearance !== appearance || appearance.draft !== draft
                || target.scope !== scope || target.revision !== revision
                || target.inputText !== text || !target.managed || !target.editing || target.busy) return false;
        return target.previewImport();
    }
    OrlaButton {
        id: catalogDisclosure
        objectName: "appearancePresetCatalogDisclosure"
        Layout.fillWidth: true
        text: checked ? qsTr("Recolher presets e aparência portátil") : qsTr("Presets e aparência portátil")
        checkable: true
        Accessible.description: (checked ? qsTr("Seção expandida.") : qsTr("Seção recolhida."))
            + " " + qsTr("Quatro opções: Essencial, Maré, Estúdio e Jogo.")
        KeyNavigation.tab: controls.catalogOpen && controls.preset.managed ? choicesRepeater.itemAt(0)
            : controls.preset.managed ? null : catalogProfiles
        onCheckedChanged: controls.setCatalogOpen(checked)
        onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
        Keys.onReturnPressed: event => { toggle(); event.accepted = true; }
    }
    Controls.Label {
        Layout.fillWidth: true
        text: qsTr("Essencial · Maré · Estúdio · Jogo · macOS")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        font.pixelSize: Style.type.caption
    }
    Controls.Label {
        objectName: "appearancePresetCatalogStatus"
        Layout.fillWidth: true
        text: controls.previewId.length ? qsTr("Em prévia: %1").arg(controls.nameFor(controls.previewId))
            + "\n" + controls.descriptionFor(controls.previewId) : controls.preset.hasPreview ? (controls.preset.message || qsTr("Prévia de aparência e widgets. Aplicar salva neste perfil."))
            : controls.preset.managed ? qsTr("Escolher muda a prévia. Aplicar salva neste perfil.")
            : qsTr("Para usar um preset, crie ou escolha um perfil na aba Perfis.")
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        font.pixelSize: Style.type.caption
    }
    OrlaButton {
        id: catalogProfiles
        objectName: "appearancePresetCatalogProfiles"
        Layout.fillWidth: true
        visible: !controls.preset.managed
        text: qsTr("Ir para Perfis")
        onClicked: controls.profilesRequested()
        onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
    }
    ColumnLayout {
        id: catalogFields
        Layout.fillWidth: true
        spacing: Style.space.sm
        visible: controls.catalogOpen
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: Style.space.sm
            columnSpacing: Style.space.sm
            Repeater {
                id: choicesRepeater
                model: controls.choices
                OrlaButton {
                    id: choice
                    required property var modelData
                    required property int index
                    objectName: "appearancePresetCatalog-" + modelData.id
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.minimumHeight: Style.size.target
                    text: controls.nameFor(modelData.id)
                    enabled: controls.preset.managed && controls.preset.editing && !controls.preset.busy
                    Accessible.description: controls.descriptionFor(modelData.id)
                        + (controls.previewId === modelData.id ? " " + qsTr("Em prévia.") : "")
                    KeyNavigation.priority: KeyNavigation.BeforeItem
                    KeyNavigation.tab: index + 1 < choicesRepeater.count ? choicesRepeater.itemAt(index + 1) : disclosure
                    KeyNavigation.backtab: index > 0 ? choicesRepeater.itemAt(index - 1) : catalogDisclosure
                    Keys.onReturnPressed: event => { if (enabled) clicked(); event.accepted = true; }
                    onClicked: controls.choose(modelData.id)
                    onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
                    contentItem: ColumnLayout {
                        spacing: Style.space.xs
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: Style.size.iconMd
                            radius: Style.radius.control
                            color: choice.modelData.payload.appearance.tokens.surface
                            opacity: choice.modelData.payload.appearance.tokens.opacity
                            Row {
                                anchors.centerIn: parent
                                spacing: Style.space.xs
                                Repeater {
                                    model: choice.modelData.payload.widgets.filter(widget => widget.visible)
                                    Rectangle {
                                        required property var modelData
                                        width: Style.space.sm
                                        height: width
                                        radius: Style.radius.xs
                                        color: choice.modelData.payload.appearance.tokens.foreground
                                    }
                                }
                            }
                        }
                        Controls.Label {
                            objectName: "appearancePresetCatalogLabel-" + choice.modelData.id
                            Layout.fillWidth: true
                            text: choice.text + (controls.previewId === choice.modelData.id ? qsTr(" · Prévia") : "")
                            font.pixelSize: Style.type.label
                            font.weight: controls.previewId === choice.modelData.id ? Style.weight.demiBold : Style.weight.medium
                            horizontalAlignment: Text.AlignHCenter
                            textFormat: Text.PlainText
                        }
                    }
                }
            }
        }
        OrlaButton {
            id: disclosure
            objectName: "appearancePresetJSON"
            Layout.fillWidth: true
            text: checked ? qsTr("Recolher aparência portátil") : qsTr("Aparência portátil experimental")
            checkable: true
            Accessible.description: checked ? qsTr("Seção expandida") : qsTr("Seção recolhida")
            KeyNavigation.tab: controls.portableOpen ? exporter : null
            onCheckedChanged: controls.setPortableOpen(checked)
            Keys.onReturnPressed: event => { toggle(); event.accepted = true; }
            KeyNavigation.backtab: controls.preset.managed ? choicesRepeater.itemAt(choicesRepeater.count - 1) : catalogProfiles
            onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
        }
        Card {
            id: portableFields
            Layout.fillWidth: true
            visible: controls.portableOpen
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
                    onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
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
                        onActiveFocusChanged: if (activeFocus) controls.rememberFocus(outputScroll, output)
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
                    onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
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
                        onActiveFocusChanged: if (activeFocus) controls.rememberFocus(inputScroll, input)
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
                    onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
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
                    onActiveFocusChanged: if (activeFocus) controls.rememberFocus(this, this)
                    onClicked: controls.preset.clearInput()
                }
            }
        }
    }
}
