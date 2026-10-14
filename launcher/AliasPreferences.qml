import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl as ControlsImpl
import QtQuick.Layouts
import "Style.js" as Style

Popup {
    id: panel
    objectName: "aliasPreferences"
    required property var controller
    required property var host
    readonly property var ui: Style.scheme("dark")
    property string mode: "manager"
    property var ticket: null
    property int episode: 0
    property bool committing: false
    // Early eligibility refusals must not display an older command error.
    property bool commitNotified: false
    property string localError: ""
    property string localFavoriteError: ""
    readonly property int aliasLength: codepointLength(aliasInput.text)
    readonly property bool writable: visible && ticket !== null && !host.executionBlocked && controller.aliasesWritable === true && current()
    readonly property bool favoritesWritable: visible && mode === "manager" && ticket !== null
        && !host.executionBlocked && controller.favoritesWritable === true && favoriteCurrent()
    signal closedByUser()
    popupType: Popup.Item
    modal: true
    dim: false
    focus: true
    padding: Style.space.lg
    width: Math.min(Style.size.popupWidth + Style.size.target, parent.width - 2 * Style.space.md)
    height: Math.min(body.implicitHeight + 2 * padding, parent.height - 2 * Style.space.md)
    x: (parent.width - width) / 2
    y: (parent.height - height) / 2
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    enter: Transition { }
    exit: Transition { }
    function codepointLength(value) {
        const text = value.trim().normalize("NFC")
        let count = 0
        for (let i = 0; i < text.length; i++, count++) {
            const first = text.charCodeAt(i)
            const second = text.charCodeAt(i + 1)
            if (first >= 0xd800 && first <= 0xdbff && second >= 0xdc00 && second <= 0xdfff) i++
        }
        return count
    }
    function reveal(control) {
        const view = aliasScroll.contentItem
        const top = control.mapToItem(aliasList, 0, 0).y
        const bottom = top + control.height
        if (top < view.contentY) view.contentY = top
        else if (bottom > view.contentY + view.height)
            view.contentY = Math.max(0, Math.min(view.contentHeight - view.height, bottom - view.height))
    }
    function currentSelectedId() {
        const row = controller.selectedIndex >= 0 ? controller.rows[controller.selectedIndex] : null
        return row ? row.id : ""
    }
    function snapshot(extra) {
        return { generation: controller.generation, revision: controller.aliasRevision, favoriteRevision: controller.favoriteRevision,
            query: controller.query, selection: controller.selectedIndex,
            selectedId: currentSelectedId(),
            row: extra ? extra.row : -1, id: extra ? extra.id : "",
            alias: extra ? extra.alias || "" : "", appId: extra ? extra.appId || "" : "" }
    }
    function begin(modeValue, extra) {
        episode++
        ticket = null
        if (host.executionBlocked || host.activePanel !== "search") { close(); return }
        if (modeValue !== "manager" && extra && extra.generation !== undefined
            && (extra.generation !== controller.generation || extra.revision !== controller.aliasRevision)) { close(); return }
        if (modeValue === "manager") { controller.reloadAliases(); if (controller.reloadFavorites) controller.reloadFavorites() }
        if (host.executionBlocked || host.activePanel !== "search") { close(); return }
        mode = modeValue
        ticket = snapshot(extra)
        localError = ""
        localFavoriteError = ""
        aliasInput.text = extra ? extra.alias || "" : ""
        if (!visible) open()
        if (mode !== "manager") aliasInput.forceActiveFocus(Qt.PopupFocusReason)
        else body.forceActiveFocus(Qt.PopupFocusReason)
    }
    function invalidate() { episode++; ticket = null; close() }
    function currentContext() {
        return ticket && ticket.generation === controller.generation
            && ticket.query === controller.query && ticket.selection === controller.selectedIndex
            && ticket.selectedId === currentSelectedId()
    }
    function current() { return currentContext() && ticket.revision === controller.aliasRevision }
    function favoriteCurrent() { return currentContext() && ticket.favoriteRevision === controller.favoriteRevision }
    function removeFavorite(pair, pressedEpisode) {
        if (pressedEpisode !== episode || !pair || !favoritesWritable || !favoriteCurrent()
            || pair.generation !== ticket.generation || pair.revision !== ticket.favoriteRevision) return
        const captured = ticket
        const capturedEpisode = episode
        committing = true
        let ok = false
        try { ok = controller.removeFavorite(pair.appId, pair.generation, pair.revision) }
        finally { committing = false }
        // Do not revive a closed or newly opened manager after a synchronous callback.
        if (episode !== capturedEpisode || ticket !== captured || !visible || host.executionBlocked
            || host.activePanel !== "search" || !host.active || !host.visible) return
        if (ok) { ticket = snapshot(null); episode++; localFavoriteError = ""; body.forceActiveFocus(Qt.PopupFocusReason) }
        else localFavoriteError = String(controller.favoriteError || qsTr("Não foi possível remover o favorito. Abra a lista novamente.")).slice(0, 256)
    }
    function commit(kind, pair, pressedEpisode) {
        if (pressedEpisode !== episode || !writable || !current()) return
        const captured = ticket
        commitNotified = false
        committing = true
        let ok = false
        if (kind === "save") ok = mode === "add"
            ? controller.saveAlias(captured.row, captured.generation, captured.id, pair.alias, captured.revision)
            : controller.renameAlias(captured.alias, captured.appId, pair.alias, captured.generation, captured.revision)
        else ok = controller.removeAlias(pair.alias, pair.appId, captured.generation, captured.revision)
        committing = false
        if (ok) {
            if (kind === "remove") { ticket = snapshot(null); episode++; localError = ""; body.forceActiveFocus(Qt.PopupFocusReason) }
            else invalidate()
        } else {
            if (!current() || !commitNotified) {
                localError = qsTr("A lista ou a seleção mudou. Abra o editor novamente.")
                ticket = null
                episode++
            } else localError = String(controller.aliasError || qsTr("Não foi possível salvar a alteração. Tente novamente.")).slice(0, 256)
        }
    }
    onClosed: { episode++; ticket = null; closedByUser() }
    Connections {
        target: panel.controller
        function onChanged() {
            if (panel.committing) panel.commitNotified = true
            else if (panel.visible && !(panel.mode === "manager" ? panel.currentContext() : panel.current())) panel.invalidate()
        }
    }
    Connections {
        target: panel.host
        function onExecutionBlockedChanged() { if (panel.host.executionBlocked) panel.invalidate() }
        function onActivePanelChanged() { panel.invalidate() }
        function onActiveChanged() { if (!panel.host.active) panel.invalidate() }
        function onVisibleChanged() { if (!panel.host.visible) panel.invalidate() }
    }
    Shortcut { sequence: "Ctrl+K"; context: Qt.WindowShortcut; enabled: panel.visible; onActivated: panel.invalidate() }
    background: Rectangle {
        radius: Style.radius.module
        color: panel.ui.raised
        border.color: panel.ui.borderStrong
        border.width: 1
    }
    contentItem: ColumnLayout {
        id: body
        focus: true
        spacing: Style.space.md
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                objectName: "preferencesTitle"
                text: panel.mode === "manager" ? qsTr("Apps e aliases") : panel.mode === "add" ? qsTr("Adicionar alias") : qsTr("Editar alias")
                font.pixelSize: Style.type.title; font.weight: Style.weight.demiBold
                color: panel.ui.text; textFormat: Text.PlainText
            }
        }
        Text {
            Layout.fillWidth: true
            text: panel.mode === "manager" ? qsTr("Seus favoritos e nomes curtos para abrir aplicativos.") : qsTr("Use de 1 a 32 caracteres. Outros aliases deste aplicativo serão mantidos.")
            color: panel.ui.textMuted; font.pixelSize: Style.type.label
            wrapMode: Text.Wrap; textFormat: Text.PlainText
        }
        ScrollView {
            id: aliasScroll
            objectName: "aliasScroll"
            visible: panel.mode === "manager"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(aliasList.implicitHeight, panel.parent.height - Style.size.target * 4)
            Layout.minimumHeight: 0
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
                id: aliasList
                width: aliasScroll.availableWidth
                spacing: Style.space.sm
                Text {
                    objectName: "favoritesSectionLabel"
                    visible: (panel.controller.favorites || []).length > 0 || panel.controller.favoritesWritable === false || (panel.controller.aliases || []).length === 0
                    Layout.fillWidth: true; text: qsTr("FAVORITOS")
                    font.pixelSize: Style.type.overline; font.weight: Style.weight.bold; font.letterSpacing: Style.letterSpacing.overline
                    color: panel.ui.textMuted; textFormat: Text.PlainText
                }
                Repeater {
                    model: (panel.controller.favorites || []).slice(0, 16)
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        implicitHeight: favoriteRow.implicitHeight + 2 * Style.space.sm
                        radius: Style.radius.control; color: panel.ui.surface
                        RowLayout {
                            id: favoriteRow
                            anchors.fill: parent; anchors.margins: Style.space.sm; spacing: Style.space.sm
                            ControlsImpl.IconImage {
                                Layout.preferredWidth: Style.size.iconMd; Layout.preferredHeight: Style.size.iconMd
                                name: modelData.iconName || ""; visible: name.length > 0 && status === Image.Ready
                                sourceSize.width: width * 2; sourceSize.height: height * 2
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Style.space.xxs
                                Text {
                                    objectName: "favoriteTarget" + index
                                    Layout.fillWidth: true; text: modelData.available === false ? qsTr("Aplicativo indisponível") : String(modelData.title || modelData.appId).slice(0, 128)
                                    elide: Text.ElideRight; font.pixelSize: Style.type.body; color: panel.ui.text; textFormat: Text.PlainText
                                }
                                Text {
                                    objectName: "favoriteAppId" + index
                                    visible: modelData.available === false || (!!modelData.title
                                        && (panel.controller.favorites || []).slice(0, 16).some(other => other.appId !== modelData.appId && other.title === modelData.title))
                                    Layout.fillWidth: true; text: String(modelData.appId).slice(0, 128); elide: Text.ElideMiddle
                                    font.pixelSize: Style.type.caption; color: panel.ui.textMuted; textFormat: Text.PlainText
                                }
                            }
                            Button {
                                id: favoriteRemoveButton
                                objectName: "favoriteRemove" + index
                                property int pressedEpisode: -1
                                property var pairTicket: null
                                text: qsTr("Remover"); enabled: panel.favoritesWritable
                                Accessible.name: qsTr("Remover %1 dos favoritos").arg(String(modelData.title || modelData.appId).slice(0, 128))
                                implicitHeight: Style.size.target
                                Layout.minimumHeight: Style.size.target; Layout.minimumWidth: Style.size.target
                                onActiveFocusChanged: if (activeFocus) panel.reveal(favoriteRemoveButton)
                                onPressed: {
                                    pressedEpisode = panel.episode
                                    pairTicket = panel.ticket ? {appId: String(modelData.appId), generation: panel.ticket.generation, revision: panel.ticket.favoriteRevision} : null
                                }
                                onClicked: panel.removeFavorite(pairTicket, pressedEpisode)
                                contentItem: Text { text: parent.text; color: parent.enabled ? panel.ui.danger : panel.ui.textMuted; font.pixelSize: Style.type.label; textFormat: Text.PlainText; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle { radius: Style.radius.control; color: panel.ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: panel.ui.focus }
                            }
                        }
                    }
                }
                Text {
                    objectName: "favoriteEmptyState"
                    visible: (panel.controller.favorites || []).length === 0 && (panel.controller.favoritesWritable === false || (panel.controller.aliases || []).length === 0); Layout.fillWidth: true
                    text: panel.controller.favoritesWritable === false ? qsTr("Favoritos indisponíveis. Seus dados foram preservados.") : qsTr("Nenhum favorito salvo. Fixe um nas ações de um aplicativo.")
                    wrapMode: Text.Wrap; font.pixelSize: Style.type.body; color: panel.ui.textMuted; textFormat: Text.PlainText
                }
                Text {
                    objectName: "favoriteErrorLabel"
                    Layout.fillWidth: true; visible: panel.localFavoriteError.length > 0 || String(panel.controller.favoriteError || "").length > 0
                    text: panel.localFavoriteError || String(panel.controller.favoriteError || "").slice(0, 256)
                    color: panel.ui.warning; font.pixelSize: Style.type.caption; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText
                }
                Text {
                    objectName: "aliasesSectionLabel"
                    Layout.fillWidth: true; text: qsTr("ALIASES")
                    font.pixelSize: Style.type.overline; font.weight: Style.weight.bold; font.letterSpacing: Style.letterSpacing.overline
                    color: panel.ui.textMuted; textFormat: Text.PlainText
                }
                Repeater {
                    model: (panel.controller.aliases || []).slice(0, 16)
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        implicitHeight: aliasRow.implicitHeight + 2 * Style.space.sm
                        radius: Style.radius.control; color: panel.ui.surface
                        RowLayout {
                            id: aliasRow
                            anchors.fill: parent; anchors.margins: Style.space.sm; spacing: Style.space.sm
                            ControlsImpl.IconImage {
                                Layout.preferredWidth: Style.size.iconMd
                                Layout.preferredHeight: Style.size.iconMd
                                name: modelData.iconName || ""
                                visible: name.length > 0 && status === Image.Ready
                                sourceSize.width: width * 2; sourceSize.height: height * 2
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Style.space.xxs
                                Text { Layout.fillWidth: true; text: String(modelData.alias).slice(0, 64); elide: Text.ElideRight; font.pixelSize: Style.type.body; color: panel.ui.text; textFormat: Text.PlainText }
                                Text { objectName: "aliasTarget" + index; Layout.fillWidth: true; text: modelData.available === false ? qsTr("Aplicativo indisponível") : String(modelData.title || modelData.appId).slice(0, 128); elide: Text.ElideRight; font.pixelSize: Style.type.caption; color: panel.ui.textMuted; textFormat: Text.PlainText }
                                Text {
                                    objectName: "aliasAppId" + index
                                    visible: modelData.available === false || (!!modelData.title
                                        && (panel.controller.aliases || []).slice(0, 16).some(other => other.appId !== modelData.appId && other.title === modelData.title))
                                    Layout.fillWidth: true; text: String(modelData.appId).slice(0, 128); elide: Text.ElideMiddle
                                    font.pixelSize: Style.type.caption; color: panel.ui.textMuted; textFormat: Text.PlainText
                                }
                            }
                            Button {
                                property int pressedEpisode: -1
                                id: aliasEditButton
                                property var pairTicket: null
                                onActiveFocusChanged: if (activeFocus) panel.reveal(aliasEditButton)
                                objectName: "aliasEdit" + index
                                text: qsTr("Editar"); enabled: panel.writable
                                implicitHeight: Style.size.target
                Layout.minimumHeight: Style.size.target
                Layout.minimumWidth: Style.size.target
                                onPressed: { pressedEpisode = panel.episode; pairTicket = {alias: String(modelData.alias), appId: String(modelData.appId), generation: panel.ticket.generation, revision: panel.ticket.revision} }
                                onClicked: if (pressedEpisode === panel.episode && panel.writable && panel.current()) panel.begin("edit", pairTicket)
                                contentItem: Text { text: parent.text; color: parent.enabled ? panel.ui.accent : panel.ui.textMuted; font.pixelSize: Style.type.label; textFormat: Text.PlainText; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle { radius: Style.radius.control; color: panel.ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: panel.ui.focus }
                            }
                            Button {
                                property int pressedEpisode: -1
                                id: aliasRemoveButton
                                property var pairTicket: null
                                onActiveFocusChanged: if (activeFocus) panel.reveal(aliasRemoveButton)
                                objectName: "aliasRemove" + index
                                text: qsTr("Remover"); enabled: panel.writable
                                implicitHeight: Style.size.target
                Layout.minimumHeight: Style.size.target
                Layout.minimumWidth: Style.size.target
                                onPressed: { pressedEpisode = panel.episode; pairTicket = {alias: String(modelData.alias), appId: String(modelData.appId), generation: panel.ticket.generation, revision: panel.ticket.revision} }
                                onClicked: panel.commit("remove", pairTicket, pressedEpisode)
                                contentItem: Text { text: parent.text; color: parent.enabled ? panel.ui.danger : panel.ui.textMuted; font.pixelSize: Style.type.label; textFormat: Text.PlainText; verticalAlignment: Text.AlignVCenter }
                                background: Rectangle { radius: Style.radius.control; color: panel.ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: panel.ui.focus }
                            }
                        }
                    }
                }
                Text { objectName: "aliasEmptyState"; visible: (panel.controller.aliases || []).length === 0; Layout.fillWidth: true; text: panel.controller.aliasesWritable === false ? qsTr("Aliases indisponíveis. Seus dados foram preservados.") : qsTr("Nenhum alias salvo. Adicione um nas ações de um aplicativo."); wrapMode: Text.Wrap; font.pixelSize: Style.type.body; color: panel.ui.textMuted; textFormat: Text.PlainText }
            }
        }
        TextField {
            id: aliasInput
            objectName: "aliasInput"
            visible: panel.mode !== "manager"
            enabled: panel.writable
            Layout.fillWidth: true
            Layout.preferredHeight: Style.size.target
            Layout.minimumHeight: Style.size.target
                Layout.minimumWidth: Style.size.target
            maximumLength: 64
            placeholderText: qsTr("Nome do alias")
            placeholderTextColor: panel.ui.textMuted
            selectionColor: panel.ui.accent
            selectedTextColor: panel.ui.onAccent
            Accessible.name: qsTr("Nome do alias")
            color: panel.ui.text; font.pixelSize: Style.type.body
            selectByMouse: true
            background: Rectangle { radius: Style.radius.control; color: panel.ui.sunken; border.width: 2; border.color: aliasInput.activeFocus ? panel.ui.focus : panel.ui.border }
        }
        Text {
            objectName: "aliasErrorLabel"
            Layout.fillWidth: true
            visible: panel.localError.length > 0 || panel.controller.aliasesWritable === false
            text: panel.localError || String(panel.controller.aliasError || "").slice(0, 256)
            color: panel.ui.warning; font.pixelSize: Style.type.caption; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; textFormat: Text.PlainText
        }
        RowLayout {
            visible: panel.mode !== "manager"
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button {
                objectName: "aliasCancelButton"
                text: qsTr("Cancelar")
                implicitHeight: Style.size.target
                Layout.minimumHeight: Style.size.target
                Layout.minimumWidth: Style.size.target
                onClicked: panel.invalidate()
                contentItem: Text { text: parent.text; color: panel.ui.text; font.pixelSize: Style.type.label; textFormat: Text.PlainText; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: Style.radius.control; color: panel.ui.surface; border.width: parent.activeFocus ? 2 : 0; border.color: panel.ui.focus }
            }
            Button {
                property int pressedEpisode: -1
                property string pendingAlias: ""
                objectName: "aliasSaveButton"
                text: qsTr("Salvar")
                enabled: panel.writable && panel.aliasLength > 0 && panel.aliasLength <= 32
                implicitHeight: Style.size.target
                Layout.minimumHeight: Style.size.target
                Layout.minimumWidth: Style.size.target
                onPressed: { pressedEpisode = panel.episode; pendingAlias = aliasInput.text }
                onClicked: panel.commit("save", {alias: pendingAlias}, pressedEpisode)
                contentItem: Text { text: parent.text; color: parent.enabled ? panel.ui.onAccent : panel.ui.textMuted; font.pixelSize: Style.type.label; font.weight: Style.weight.demiBold; textFormat: Text.PlainText; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { radius: Style.radius.control; color: parent.enabled ? panel.ui.accent : panel.ui.surface; border.width: parent.activeFocus ? 2 : 0; border.color: panel.ui.focus }
            }
        }
    }
}
