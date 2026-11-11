import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl as ControlsImpl
import QtQuick.Layouts
import QtQuick.Templates as Templates
import "Style.js" as Style

Window {
    id: window
    // The launcher is a dark overlay in every system scheme.
    readonly property var ui: Style.scheme("dark")
    objectName: "launcherWindow"
    visible: true
    width: 660
    height: 420
    minimumWidth: 440
    minimumHeight: 380
    title: qsTr("Orla Launcher")
    // Spotlight-like: a frameless window whose only visible part is the glass
    // panel. WindowSession asks KWin to blur behind it when available.
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint
    // A wide margin gives the panel a soft, macOS-like shadow.
    readonly property int shadowMargin: Style.space.xxl
    // Search bar on top, action bar at the bottom, as Spotlight and Raycast lay them out.
    readonly property int headerHeight: Style.size.target + Style.space.xl
    readonly property int footerHeight: Style.size.target + Style.space.xs
    readonly property var blurRequest: windowSession ? [glass.x, glass.y, glass.width, glass.height, glass.radius] : null
    onBlurRequestChanged: {
        if (blurRequest && windowSession.setBlurRegion)
            windowSession.setBlurRegion(Qt.rect(glass.x, glass.y, glass.width, glass.height), glass.radius)
    }
    property string activePanel: "search"
    // Optional: hosts without the Orla command catalog show no command rows.
    readonly property var commands: launcher.commands || null
    property bool pendingDismiss: false
    property bool pendingQuit: false
    readonly property bool executionBlocked: pendingDismiss || aiProviders.busy || aiText.busy || steamProvider.busy
    property var selectedRow: launcher.selectedIndex >= 0 ? launcher.rows[launcher.selectedIndex] : null
    function executeTicket(ticket, selectRow) {
        if (!ticket || aliasPreferences.visible || pendingDismiss || aiProviders.busy || aiText.busy || steamProvider.busy) return
        if (selectRow) launcher.select(ticket.row)
        const row = launcher.rows[ticket.row]
        const started = launcher.execute(ticket.row, ticket.generation, ticket.id, ticket.actionId || "")
        // A command read keeps the launcher open and shows the provider's answer.
        if (started && row && row.kind === "command" && commands) {
            activePanel = "command"
            commandPanel.focusFirst()
        }
    }
    readonly property bool canOpenActions: activePanel === "search" && !executionBlocked && !aliasPreferences.visible
    readonly property bool canAddAlias: canOpenActions && launcher.aliasesWritable === true
        && launcher.status === "ready" && !!selectedRow && selectedRow.enabled && selectedRow.aliasEligible === true
    readonly property string selectedAppId: selectedRow ? String(selectedRow.appId || "") : ""
    readonly property bool selectedFavorite: selectedAppId.length > 0
        && (launcher.favorites || []).some(entry => entry.appId === selectedAppId)
    readonly property bool canChangeFavorite: canOpenActions && launcher.favoritesWritable === true
        && launcher.status === "ready" && !!selectedRow && selectedRow.enabled && selectedAppId.length > 0
        && (selectedFavorite || (selectedRow.kind === "app" && selectedRow.aliasEligible === true))
    property var actionsRow: null
    property int actionsEpisode: 0
    function openResultActions() {
        if (!canOpenActions) return
        const row = selectedRow
        actionsEpisode++
        actionsRow = {title: row ? row.title : qsTr("Busca local"), source: row ? row.source : qsTr("Orla"),
            actions: row && row.enabled ? row.actions.slice() : [],
            preferences: (canChangeFavorite ? [{preference: selectedFavorite ? "unpin" : "pin",
                text: selectedFavorite ? qsTr("Remover dos favoritos") : qsTr("Fixar nos favoritos")}] : [])
                .concat(canAddAlias ? [{preference: "add", text: qsTr("Adicionar alias…")}] : [])
                .concat([{preference: "manage", text: qsTr("Apps e aliases…")}])}
        resultActions.open()
        resultActions.currentIndex = 2
        const first = 2
        resultActions.currentIndex = first
        if (resultActions.itemAt(first)) resultActions.itemAt(first).forceActiveFocus(Qt.PopupFocusReason)
    }
    onExecutionBlockedChanged: if (executionBlocked) resultActions.close()
    onActivePanelChanged: {
        if (activePanel !== "search") resultActions.close()
        if (activePanel !== "command" && commands) commands.cancelAll()
    }
    function executeSelection() {
        const row = selectedRow
        if (row) executeTicket({ row: launcher.selectedIndex, generation: row.generation, id: row.id }, false)
    }
    function closeAiPanel() {
        aiProviders.cancelAll()
        aiText.cancelAll()
        activePanel = "search"
        search.forceActiveFocus()
    }
    function closeCommandPanel() {
        if (commands) commands.cancelAll()
        activePanel = "search"
        search.forceActiveFocus()
    }
    function closeSteamPanel() {
        steamProvider.cancelAll()
        activePanel = "search"
        search.forceActiveFocus()
    }
    function finishPendingClose() {
        if (!pendingDismiss || aiProviders.busy || aiText.busy || steamProvider.busy) return
        const quitApplication = pendingQuit
        pendingDismiss = false
        pendingQuit = false
        launcher.dismiss()
        if (quitApplication) Qt.quit()
    }
    function requestDismiss(quitApplication) {
        pendingQuit = pendingQuit || quitApplication
        pendingDismiss = true
        const aiReady = aiProviders.requestClose()
        const textReady = aiText.requestClose()
        const steamReady = steamProvider.requestClose()
        const commandsReady = !commands || commands.requestClose()
        if (aiReady && textReady && steamReady && commandsReady) finishPendingClose()
        return !pendingDismiss
    }
    onActiveChanged: {
        if (!active) resultActions.close()
        else if (activePanel === "search" && !resultActions.visible && !aliasPreferences.visible) search.forceActiveFocus()
    }
    onClosing: function(close) {
        close.accepted = requestDismiss(true)
    }
    Shortcut {
        sequence: "Escape"; context: Qt.WindowShortcut; enabled: !resultActions.visible && !aliasPreferences.visible
        onActivated: {
            if (window.activePanel === "ai") window.closeAiPanel()
            else if (window.activePanel === "steam") window.closeSteamPanel()
            else if (window.activePanel === "command") window.closeCommandPanel()
            else window.requestDismiss(false)
        }
    }
    Shortcut {
        sequence: "Ctrl+K"; context: Qt.WindowShortcut
        enabled: window.canOpenActions && !resultActions.visible
        onActivated: window.openResultActions()
    }

    // A key hint drawn like a keyboard key: "Ctrl", "K", "↵".
    component Keycap: Rectangle {
        property alias text: keyLabel.text
        readonly property var scheme: Style.scheme("dark")
        implicitHeight: Style.size.iconMd
        implicitWidth: Math.max(implicitHeight, keyLabel.implicitWidth + 2 * Style.space.xs + Style.space.xxs)
        radius: Style.radius.xs
        color: Style.alpha(scheme.text, Style.state.hover)
        border.width: 1
        border.color: Style.alpha(scheme.text, Style.state.chip)
        Text {
            id: keyLabel
            anchors.centerIn: parent
            color: parent.scheme.textMuted
            font.pixelSize: Style.type.caption
            font.weight: Style.weight.medium
            textFormat: Text.PlainText
        }
    }
    // Orla's mark: the brand squircle with its lowercase o.
    component BrandMark: Rectangle {
        property int size: Style.size.iconMd
        readonly property var scheme: Style.scheme("dark")
        implicitWidth: size
        implicitHeight: size
        radius: Math.round(size * Style.dock.iconRadius)
        color: scheme.accent
        Text {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: -1
            text: "o"
            color: parent.scheme.onAccent
            font.pixelSize: parent.size >= Style.size.iconLg ? Style.type.headline : Style.type.label
            font.weight: Style.weight.bold
            textFormat: Text.PlainText
        }
    }
    // Mode switches on the search bar (IA, Steam): quiet until hovered or open.
    component HeaderChip: Button {
        id: chip
        property bool current: false
        readonly property var scheme: Style.scheme("dark")
        implicitHeight: Style.size.target
        leftPadding: Style.space.md
        rightPadding: Style.space.md
        contentItem: Text {
            text: chip.text
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: chip.current ? chip.scheme.accent : chip.hovered || chip.activeFocus ? chip.scheme.text : chip.scheme.textMuted
            font.pixelSize: Style.type.label
            font.weight: Style.weight.demiBold
            textFormat: Text.PlainText
        }
        // The full target stays 40 px; the visible capsule is smaller.
        background: Item {
            implicitWidth: Style.size.target
            implicitHeight: Style.size.target
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                height: Style.size.iconButton + Style.space.xs
                radius: height / 2
                color: chip.current ? Style.alpha(chip.scheme.accent, Style.state.selected)
                    : chip.down ? Style.alpha(chip.scheme.text, Style.state.pressed)
                    : chip.hovered ? Style.alpha(chip.scheme.text, Style.state.hover)
                    : Style.alpha(chip.scheme.text, Style.state.chip)
                border.width: chip.activeFocus ? 2 : 0
                border.color: chip.scheme.focus
            }
        }
    }

    Templates.Menu {
        id: resultActions
        objectName: "resultActionsMenu"
        // Keep the actions inside this glass window, including under KDE's style.
        popupType: Popup.Item
        parent: glass
        // Raycast-like: the action panel rises from the action bar's right end.
        x: glass.width - width - Style.space.sm
        y: glass.height - window.footerHeight - height - Style.space.xs
        width: Math.min(Style.size.popupWidth, glass.width - 2 * Style.space.sm)
        height: Math.min(contentItem.implicitHeight + topPadding + bottomPadding,
                         glass.height - window.footerHeight - 2 * Style.space.sm)
        padding: Style.space.xs + Style.space.xxs
        palette.window: ui.surface
        palette.text: ui.text
        palette.highlight: ui.accent
        palette.highlightedText: ui.onAccent
        margins: window.shadowMargin + Style.space.sm
        modal: true
        dim: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        enter: Transition { }
        exit: Transition { }
        onClosed: {
            window.actionsEpisode++
            if (window.active && window.activePanel === "search" && !window.pendingDismiss && !aliasPreferences.visible) search.forceActiveFocus()
        }
        background: Item {
            // Layered soft shadow, then the popover itself.
            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    readonly property real spread: (index + 1) * Style.space.xs
                    x: -spread
                    y: -spread + Style.space.xs
                    width: parent.width + spread * 2
                    height: parent.height + spread * 2
                    radius: Style.radius.module + spread
                    color: Style.alpha(Style.glass.shade, 0.12 - index * 0.035)
                }
            }
            Rectangle {
                anchors.fill: parent
                radius: Style.radius.module
                color: ui.surface
                border.width: 1
                border.color: Style.alpha(Style.glass.highlight, Style.state.hover)
            }
        }
        contentItem: ListView {
            implicitHeight: contentHeight
            model: resultActions.contentModel
            currentIndex: resultActions.currentIndex
            highlightMoveDuration: 0
            highlightResizeDuration: 0
            spacing: Style.space.xxs
            clip: true
            ScrollIndicator.vertical: ScrollIndicator { }
            Keys.onPressed: event => {
                if (event.key === Qt.Key_K && (event.modifiers & Qt.ControlModifier)) {
                    resultActions.close()
                    event.accepted = true
                }
            }
        }
        Templates.MenuItem {
            id: actionTitle
            text: qsTr("Ações de %1").arg(window.actionsRow ? String(window.actionsRow.title).slice(0, 512) : "")
            enabled: false
            leftPadding: Style.space.sm
            rightPadding: Style.space.sm
            topPadding: Style.space.xs
            implicitHeight: contentItem.implicitHeight + topPadding
            height: implicitHeight
            contentItem: Text {
                text: actionTitle.text
                color: ui.text; font.pixelSize: Style.type.body; font.weight: Style.weight.bold
                textFormat: Text.PlainText; elide: Text.ElideRight
            }
            background: Item { }
        }
        Templates.MenuItem {
            id: actionOrigin
            text: qsTr("Origem: %1").arg(window.actionsRow ? String(window.actionsRow.source).slice(0, 256) : "")
            enabled: false
            leftPadding: Style.space.sm
            rightPadding: Style.space.sm
            bottomPadding: Style.space.sm
            implicitHeight: contentItem.implicitHeight + bottomPadding + Style.space.xxs
            height: implicitHeight
            contentItem: Text {
                objectName: "resultActionsOrigin"
                text: actionOrigin.text
                color: ui.textMuted; font.pixelSize: Style.type.caption
                textFormat: Text.PlainText; elide: Text.ElideRight
                verticalAlignment: Text.AlignTop
            }
            // A hairline closes the header.
            background: Item {
                Rectangle {
                    anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                    height: Style.size.divider
                    color: Style.alpha(ui.text, Style.state.hover)
                }
            }
        }
        Instantiator {
            model: window.actionsRow ? window.actionsRow.actions.concat(window.actionsRow.preferences) : []
            delegate: Templates.MenuItem {
                id: actionItem
                required property var modelData
                required property int index
                objectName: modelData.preference === "pin" ? "favoritePinAction" : modelData.preference === "unpin" ? "favoriteRemoveAction"
                    : modelData.preference === "add" ? "aliasAddAction" : modelData.preference === "manage" ? "aliasManageAction" : "launcherAction" + index
                property var executionTicket: null
                property int pressedEpisode: -1
                // The first Orla preference starts a new group, below the result's own actions.
                readonly property bool opensGroup: !!modelData.preference && !!window.actionsRow
                    && index === window.actionsRow.actions.length && index > 0
                text: String(modelData.text).slice(0, 512)
                enabled: window.canOpenActions && (modelData.preference === "add" ? window.canAddAlias
                    : modelData.preference === "pin" || modelData.preference === "unpin" ? window.canChangeFavorite : true)
                focusPolicy: Qt.StrongFocus
                topInset: opensGroup ? Style.space.sm : 0
                topPadding: topInset + Style.space.xs
                bottomPadding: Style.space.xs
                implicitHeight: Math.max(Style.size.control + topInset, contentItem.implicitHeight + topPadding + bottomPadding)
                height: implicitHeight
                leftPadding: Style.space.sm + Style.space.xxs
                rightPadding: Style.space.sm
                onPressed: {
                    pressedEpisode = window.actionsEpisode
                    executionTicket = null
                    if (modelData.preference === "add" && !window.canAddAlias) return
                    if ((modelData.preference === "pin" || modelData.preference === "unpin") && !window.canChangeFavorite) return
                    executionTicket = modelData.preference === "pin" || modelData.preference === "unpin"
                        ? {row: launcher.selectedIndex, generation: launcher.generation, id: window.selectedRow.id,
                            appId: window.selectedAppId, revision: launcher.favoriteRevision, preference: modelData.preference}
                        : modelData.preference === "add"
                            ? {row: launcher.selectedIndex, generation: window.selectedRow.generation, id: window.selectedRow.id, revision: launcher.aliasRevision}
                            : {row: modelData.row, generation: modelData.generation, id: modelData.resultId, actionId: modelData.id}
                }
                // A closed or reopened menu cannot revive an earlier press.
                onTriggered: {
                    if (!resultActions.visible || !window.canOpenActions || pressedEpisode !== window.actionsEpisode) return
                    const ticket = executionTicket
                    if (modelData.preference === "pin" || modelData.preference === "unpin") {
                        if (!ticket || !window.canChangeFavorite || ticket.generation !== launcher.generation
                            || ticket.revision !== launcher.favoriteRevision || ticket.row !== launcher.selectedIndex
                            || ticket.id !== window.selectedRow.id || ticket.appId !== window.selectedAppId
                            || (ticket.preference === "unpin") !== window.selectedFavorite) return
                        const episode = window.actionsEpisode
                        if (ticket.preference === "pin") launcher.pinFavorite(ticket.row, ticket.generation, ticket.id, ticket.revision)
                        else launcher.removeFavorite(ticket.appId, ticket.generation, ticket.revision)
                        // A newer menu opened by a synchronous callback owns its own focus.
                        if (episode === window.actionsEpisode) resultActions.close()
                    } else if (modelData.preference === "add") {
                        if (!window.canAddAlias || ticket.generation !== launcher.generation || ticket.revision !== launcher.aliasRevision) return
                        resultActions.close()
                        aliasPreferences.begin("add", ticket)
                    } else if (modelData.preference === "manage") {
                        resultActions.close()
                        aliasPreferences.begin("manager", null)
                    } else window.executeTicket(ticket, false)
                }
                contentItem: Text {
                    text: actionItem.text
                    color: actionItem.enabled ? ui.text : ui.textMuted
                    font.pixelSize: Style.type.body; textFormat: Text.PlainText
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                }
                // topInset keeps the group gap outside the highlight.
                background: Rectangle {
                    radius: Style.radius.control
                    color: actionItem.highlighted ? Style.alpha(ui.accent, Style.state.selected) : "transparent"
                    border.width: resultActions.activeFocus && actionItem.highlighted ? 2 : 0
                    border.color: ui.focus
                    Rectangle {
                        visible: actionItem.opensGroup
                        x: Style.space.xs
                        width: parent.width - 2 * Style.space.xs
                        y: -Math.round(actionItem.topInset / 2) - Style.space.xxs
                        height: Style.size.divider
                        color: Style.alpha(ui.text, Style.state.hover)
                    }
                }
            }
            onObjectAdded: (index, object) => resultActions.insertItem(index + 2, object)
            onObjectRemoved: (index, object) => resultActions.removeItem(object)
        }
    }
    AliasPreferences {
        id: aliasPreferences
        parent: glass
        controller: launcher
        host: window
        onClosedByUser: if (window.active && window.activePanel === "search" && !window.executionBlocked && !resultActions.visible) search.forceActiveFocus()
    }
    Shortcut { sequence: "Ctrl+Q"; context: Qt.WindowShortcut; onActivated: window.requestDismiss(true) }
    Connections {
        target: aiProviders
        function onCloseReady() {
            window.finishPendingClose()
        }
    }
    Connections {
        target: aiText
        function onCloseReady() { window.finishPendingClose() }
    }
    Connections {
        target: steamProvider
        function onCloseReady() { window.finishPendingClose() }
    }
    Connections {
        target: launcher
        function onChanged() {
            resultActions.close()
            if (search.text !== launcher.query) search.text = launcher.query
            if (launcher.selectedIndex >= 0) results.positionViewAtIndex(launcher.selectedIndex, ListView.Contain)
        }
    }

    // Soft shadow in the transparent margin: stacked translucent outlines stay
    // cheap for the scene graph, unlike a blurred Canvas.
    Repeater {
        model: 8
        Rectangle {
            required property int index
            readonly property real spread: (index + 1) * (window.shadowMargin - Style.space.xs) / 8
            x: glass.x - spread
            y: glass.y - spread + Style.space.xs
            width: glass.width + spread * 2
            height: glass.height + spread * 2
            radius: glass.radius + spread
            color: Style.alpha(Style.glass.shade, 0.06 - index * 0.0065)
        }
    }
    Rectangle {
        id: glass
        anchors.fill: parent
        anchors.margins: window.shadowMargin
        radius: Style.radius.popup + Style.space.xs
        color: Style.alpha(ui.canvas, 0.84)
        border.width: 1
        border.color: Style.alpha(Style.glass.highlight, Style.state.pressed)
        // Specular top edge.
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: parent.radius - 1
            gradient: Gradient {
                GradientStop { position: 0; color: Style.alpha(Style.glass.highlight, Style.glass.sheenDark) }
                GradientStop { position: 0.35; color: "transparent" }
            }
        }
    }

    ColumnLayout {
        anchors.fill: glass
        spacing: 0
        // The search bar is the panel's top edge, like Spotlight: no field frame,
        // large type, and the mode chips at its end.
        Item {
            objectName: "launcherHeader"
            Layout.fillWidth: true
            Layout.preferredHeight: window.headerHeight
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Style.space.lg + Style.space.xxs
                anchors.rightMargin: Style.space.md
                spacing: Style.space.md
                // Magnifier glyph, drawn so the launcher needs no icon theme.
                Canvas {
                    id: magnifier
                    visible: window.activePanel === "search"
                    Layout.preferredWidth: Style.size.iconMd
                    Layout.preferredHeight: Style.size.iconMd
                    onPaint: {
                        const context = getContext("2d")
                        context.reset()
                        context.strokeStyle = ui.textMuted
                        context.lineWidth = 2
                        context.lineCap = "round"
                        context.beginPath()
                        context.arc(width * 0.42, height * 0.42, width * 0.32, 0, 2 * Math.PI)
                        context.stroke()
                        context.beginPath()
                        context.moveTo(width * 0.66, height * 0.66)
                        context.lineTo(width * 0.92, height * 0.92)
                        context.stroke()
                    }
                }
                // Other panels keep the brand in the bar; the panel names itself below.
                BrandMark {
                    visible: window.activePanel !== "search"
                    size: Style.size.iconLg
                }
                Text {
                    visible: window.activePanel !== "search"
                    Layout.fillWidth: true
                    text: "Orla"
                    color: ui.text
                    font.pixelSize: Style.type.title
                    font.weight: Style.weight.demiBold
                    textFormat: Text.PlainText
                    // The frameless window moves by dragging the brand.
                    DragHandler { target: null; onActiveChanged: if (active) window.startSystemMove() }
                }
                TextField {
                    id: search
                    objectName: "searchInput"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 0
                    color: ui.text
                    placeholderText: qsTr("Buscar no Orla")
                    placeholderTextColor: ui.textMuted
                    font.pixelSize: Style.type.headline
                    leftPadding: 0
                    rightPadding: 0
                    selectByMouse: true
                    selectionColor: Style.alpha(ui.accent, 0.4)
                    selectedTextColor: ui.text
                    maximumLength: 512
                    Accessible.name: qsTr("Buscar aplicativos, arquivos, ajustes, jogos ou calcular")
                    visible: window.activePanel === "search"
                    // design-exempt: the search field is the launcher's resting focus; the caret marks it, as in Spotlight.
                    background: Item { }
                    onTextEdited: launcher.query = text
                    Keys.priority: Keys.BeforeItem
                    Keys.onDownPressed: function(event) { launcher.moveSelection(1); event.accepted = true }
                    Keys.onUpPressed: function(event) { launcher.moveSelection(-1); event.accepted = true }
                    Keys.onReturnPressed: function(event) { window.executeSelection(); event.accepted = true }
                    Keys.onEnterPressed: function(event) { window.executeSelection(); event.accepted = true }
                    Component.onCompleted: forceActiveFocus()
                }
                HeaderChip {
                    id: aiEntry
                    objectName: "aiEntryButton"
                    Layout.minimumWidth: Style.size.target
                    Layout.preferredHeight: Style.size.target
                    current: window.activePanel === "ai"
                    text: window.activePanel === "ai" ? qsTr("Busca") : qsTr("IA")
                    enabled: !window.pendingDismiss || window.activePanel === "ai"
                    Accessible.name: window.activePanel === "ai" ? qsTr("Voltar à busca local") : qsTr("Abrir provedores de IA, desligados")
                    onClicked: {
                        if (window.activePanel === "ai") window.closeAiPanel()
                        else if (!window.pendingDismiss) {
                            if (window.activePanel === "steam") steamProvider.cancelAll()
                            window.activePanel = "ai"
                            aiPanel.focusFirst()
                        }
                    }
                }
                HeaderChip {
                    id: steamEntry
                    objectName: "steamEntryButton"
                    Layout.minimumWidth: Style.size.target
                    Layout.preferredHeight: Style.size.target
                    current: window.activePanel === "steam"
                    text: window.activePanel === "steam" ? qsTr("Busca") : qsTr("Steam")
                    enabled: !window.pendingDismiss || window.activePanel === "steam"
                    Accessible.name: window.activePanel === "steam" ? qsTr("Voltar à busca local") : qsTr("Abrir jogos Steam locais")
                    onClicked: {
                        if (window.activePanel === "steam") window.closeSteamPanel()
                        else if (!window.pendingDismiss) {
                            if (window.activePanel === "ai") {
                                aiProviders.cancelAll()
                                aiText.cancelAll()
                            }
                            window.activePanel = "steam"
                            steamPanel.focusFirst()
                        }
                    }
                }
            }
        }
        // Edge-to-edge hairline under the search bar.
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Style.size.divider
            color: Style.alpha(ui.text, Style.state.hover)
        }
        Item {
            visible: window.activePanel === "search"
            Layout.fillWidth: true
            Layout.fillHeight: true
            ListView {
                id: results
                objectName: "resultsList"
                anchors.fill: parent
                anchors.leftMargin: Style.space.sm
                anchors.rightMargin: Style.space.sm
                topMargin: Style.space.xs
                bottomMargin: Style.space.sm
                clip: true
                spacing: Style.space.xxs
                // Keep a few rows ready below the fold so scrolling never waits on icons.
                cacheBuffer: (Style.size.target + Style.space.xs) * 4
                boundsBehavior: Flickable.StopAtBounds
                model: launcher.rows
                section.property: "categoryLabel"
                section.delegate: Text {
                    required property string section
                    width: results.width; height: Style.size.iconButton; text: section; color: ui.textMuted
                    verticalAlignment: Text.AlignBottom; bottomPadding: Style.space.xs + Style.space.xxs; leftPadding: Style.space.sm + Style.space.xxs
                    font.pixelSize: Style.type.overline; font.weight: Style.weight.bold; font.letterSpacing: Style.letterSpacing.overline; textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                // A slim overlay bar, as on macOS; it appears while scrolling.
                ScrollBar.vertical: Templates.ScrollBar {
                    id: resultsScroll
                    parent: results
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.right: parent.right
                    anchors.topMargin: results.topMargin
                    anchors.bottomMargin: results.bottomMargin
                    padding: Style.space.xxs
                    policy: ScrollBar.AsNeeded
                    contentItem: Rectangle {
                        implicitWidth: Style.space.xs
                        radius: width / 2
                        color: Style.alpha(ui.text, resultsScroll.pressed ? 0.45 : 0.3)
                        opacity: resultsScroll.active && resultsScroll.size < 1 ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Style.motion.normal } }
                    }
                }
                delegate: ItemDelegate {
                    id: result
                    required property int index
                    required property var modelData
                    property var rowData: modelData
                    property var executionTicket: null
                    width: results.width
                    readonly property bool selected: launcher.selectedIndex === result.index
                    readonly property var tile: Style.iconTiles[rowData.kind === "calculator" || rowData.kind === "datetime" ? "slate" : rowData.kind === "steam" ? "ink"
                        : rowData.kind === "command" ? Style.widgetTiles.peripherals : "sea"]
                    height: Style.size.target + Style.space.xs
                    enabled: rowData.enabled && !window.executionBlocked && !aliasPreferences.visible
                    hoverEnabled: true
                    leftPadding: Style.space.sm + Style.space.xxs
                    rightPadding: Style.space.sm + Style.space.xxs
                    Accessible.name: rowData.title + ", " + rowData.source
                    // The accent tints the selection; text keeps full contrast.
                    background: Rectangle {
                        radius: Style.radius.tile
                        color: result.selected ? Style.alpha(ui.accent, Style.state.selected)
                            : result.hovered ? Style.alpha(ui.text, Style.state.chip) : "transparent"
                        border.width: result.activeFocus ? 2 : 0
                        border.color: ui.focus
                    }
                    contentItem: RowLayout {
                        spacing: Style.space.md
                        opacity: result.enabled ? 1 : Style.state.disabled + 0.2
                        Item {
                            Layout.preferredWidth: Style.size.iconLg
                            Layout.preferredHeight: Style.size.iconLg
                            // The app's own icon from the theme, as Spotlight shows it.
                            ControlsImpl.IconImage {
                                id: resultIcon
                                anchors.fill: parent
                                name: result.rowData.iconName || ""
                                sourceSize.width: width * 2
                                sourceSize.height: height * 2
                                visible: name.length > 0 && status === Image.Ready
                            }
                            Rectangle {
                                anchors.fill: parent
                                visible: !resultIcon.visible
                                radius: Math.round(width * Style.dock.iconRadius)
                                gradient: Gradient {
                                    GradientStop { position: 0; color: result.tile.top }
                                    GradientStop { position: 1; color: result.tile.bottom }
                                }
                                border.width: 1
                                border.color: Style.alpha(Style.glass.highlight, 0.18)
                                Text { anchors.centerIn: parent; text: result.rowData.kind === "calculator" ? "=" : result.rowData.kind === "steam" ? "S" : result.rowData.kind === "command" ? "%" : "▦"; color: result.tile.ink; font.pixelSize: Style.type.title; font.weight: Style.weight.bold; textFormat: Text.PlainText }
                            }
                        }
                        // One line, as Raycast lists: the name, then its detail in muted type.
                        Text {
                            id: resultTitle
                            Layout.maximumWidth: Math.max(0, result.availableWidth * 0.62)
                            text: result.rowData.title; color: ui.text
                            font.pixelSize: Style.type.title; font.weight: Style.weight.medium
                            elide: Text.ElideRight; maximumLineCount: 1; textFormat: Text.PlainText
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            text: result.rowData.description || result.rowData.source; color: ui.textMuted
                            font.pixelSize: Style.type.body
                            elide: Text.ElideRight; maximumLineCount: 1; textFormat: Text.PlainText
                        }
                        Keycap { visible: result.selected; text: "↵" }
                    }
                    onPressed: executionTicket = { row: index, generation: rowData.generation, id: rowData.id }
                    onClicked: {
                        const ticket = executionTicket
                        window.executeTicket(ticket, true)
                        search.forceActiveFocus()
                    }
                }
            }
            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 2 * Style.space.xl, 400)
                spacing: Style.space.sm
                visible: launcher.rows.length === 0
                Text {
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; color: ui.text
                    font.pixelSize: Style.type.title; font.weight: Style.weight.demiBold; textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                    text: launcher.status === "error" ? qsTr("Não foi possível buscar") : launcher.status === "loading" ? qsTr("Buscando no seu computador") : launcher.status === "empty" ? qsTr("Nenhum resultado") : qsTr("O que você quer abrir?")
                }
                Text {
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; color: ui.textMuted; font.pixelSize: Style.type.body; wrapMode: Text.Wrap; textFormat: Text.PlainText
                    text: launcher.status === "error" ? launcher.error : launcher.status === "empty" ? qsTr("Tente outro nome ou uma expressão como 24 * 7.") : launcher.status === "loading" ? qsTr("Você pode continuar digitando ou cancelar com Esc.")
                        : window.commands ? qsTr("Aplicativos, arquivos, ajustes, contas, jogos Steam e comandos do Orla.") : qsTr("Aplicativos, arquivos, ajustes, contas e jogos Steam.")
                }
                // Keys to know, shown only on the empty surface.
                Row {
                    visible: launcher.status === "idle"
                    anchors.horizontalCenter: parent.horizontalCenter
                    topPadding: Style.space.sm
                    spacing: Style.space.lg
                    Repeater {
                        model: [{keys: ["↑", "↓"], label: qsTr("navegar")}, {keys: ["↵"], label: qsTr("abrir")}, {keys: ["Esc"], label: qsTr("fechar")}]
                        Row {
                            required property var modelData
                            spacing: Style.space.xs
                            Repeater { model: parent.modelData.keys; Keycap { required property string modelData; text: modelData } }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                leftPadding: Style.space.xxs
                                text: parent.modelData.label; color: ui.textMuted
                                font.pixelSize: Style.type.caption; textFormat: Text.PlainText
                            }
                        }
                    }
                }
            }
        }
        Text {
            objectName: "executionWaiting"
            Layout.fillWidth: true
            Layout.leftMargin: Style.space.lg
            Layout.rightMargin: Style.space.lg
            Layout.bottomMargin: Style.space.sm
            visible: window.activePanel === "search" && (window.executionBlocked || (windowSession && windowSession.notice.length > 0) || String(launcher.favoriteError || "").length > 0)
            text: window.executionBlocked ? qsTr("Aguarde o encerramento das operações antes de abrir um resultado.")
                : windowSession && windowSession.notice.length > 0 ? windowSession.notice : String(launcher.favoriteError || "").slice(0, 256)
            color: ui.warning; font.pixelSize: Style.type.caption; wrapMode: Text.Wrap; textFormat: Text.PlainText
        }
        // Action bar: who is answering on the left, what Enter and Ctrl+K do on the right.
        Rectangle {
            objectName: "launcherFooter"
            visible: window.activePanel === "search"
            Layout.fillWidth: true
            Layout.preferredHeight: window.footerHeight
            Layout.leftMargin: 1
            Layout.rightMargin: 1
            Layout.bottomMargin: 1
            color: Style.alpha(Style.glass.shade, 0.16)
            bottomLeftRadius: glass.radius - 1
            bottomRightRadius: glass.radius - 1
            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                height: Style.size.divider
                color: Style.alpha(ui.text, Style.state.chip)
            }
            // The frameless window moves by dragging the action bar.
            DragHandler { target: null; onActiveChanged: if (active) window.startSystemMove() }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Style.space.md + Style.space.xxs
                anchors.rightMargin: Style.space.sm
                spacing: Style.space.sm
                BrandMark { }
                Text {
                    text: "Orla"; color: ui.text
                    font.pixelSize: Style.type.label; font.weight: Style.weight.demiBold; textFormat: Text.PlainText
                }
                Text {
                    objectName: "resultSummary"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    elide: Text.ElideRight
                    color: ui.textMuted; font.pixelSize: Style.type.caption; textFormat: Text.PlainText
                    font.features: {"tnum": 1}
                    text: launcher.status === "loading" ? qsTr("Buscando…")
                        : launcher.rows.length === 1 ? qsTr("1 resultado")
                        : launcher.rows.length ? qsTr("%1 resultados").arg(launcher.rows.length)
                        : windowSession && windowSession.shortcutText ? windowSession.shortcutText : qsTr("Busca local")
                }
                Button {
                    id: actionsButton
                    objectName: "actionsButton"
                    text: qsTr("Ações")
                    Accessible.name: qsTr("Ações do resultado, Ctrl+K")
                    enabled: window.canOpenActions
                    onClicked: window.openResultActions()
                    leftPadding: Style.space.sm + Style.space.xxs
                    rightPadding: Style.space.xs + Style.space.xxs
                    Layout.preferredHeight: Style.size.iconButton + Style.space.xs
                    contentItem: RowLayout {
                        spacing: Style.space.sm
                        Text {
                            text: actionsButton.text; color: actionsButton.enabled ? ui.text : ui.textMuted
                            font.pixelSize: Style.type.label; font.weight: Style.weight.medium; textFormat: Text.PlainText
                        }
                        Row { spacing: Style.space.xxs; Keycap { text: "Ctrl" } Keycap { text: "K" } }
                    }
                    background: Rectangle {
                        radius: height / 2
                        color: actionsButton.down ? Style.alpha(ui.text, Style.state.pressed)
                            : actionsButton.hovered ? Style.alpha(ui.text, Style.state.hover) : "transparent"
                        border.width: actionsButton.activeFocus ? 2 : 0
                        border.color: ui.focus
                    }
                }
                Rectangle {
                    Layout.preferredWidth: Style.size.divider
                    Layout.preferredHeight: Style.size.iconSm
                    color: Style.alpha(ui.text, Style.state.selected)
                }
                Button {
                    id: executeButton
                    objectName: "executeButton"
                    property var executionTicket: null
                    // Things that open (apps, settings, places, documents, files) say "Abrir"; answers and actions say "Usar".
                    readonly property bool opens: !window.selectedRow || ["app", "steam", "alias", "favorite", "setting", "location", "document", "file"].indexOf(window.selectedRow.kind) >= 0
                    text: opens ? qsTr("Abrir ↵") : qsTr("Usar ↵")
                    Accessible.name: opens ? qsTr("Abrir, Enter") : qsTr("Usar, Enter")
                    enabled: launcher.status === "ready" && launcher.selectedIndex >= 0
                        && !!window.selectedRow && window.selectedRow.enabled === true && !window.executionBlocked && !aliasPreferences.visible
                    onPressed: executionTicket = window.selectedRow ? { row: launcher.selectedIndex, generation: window.selectedRow.generation, id: window.selectedRow.id } : null
                    onClicked: window.executeTicket(executionTicket, false)
                    leftPadding: Style.space.md
                    rightPadding: Style.space.xs + Style.space.xxs
                    Layout.preferredHeight: Style.size.iconButton + Style.space.xs
                    contentItem: RowLayout {
                        spacing: Style.space.sm
                        Text {
                            text: executeButton.opens ? qsTr("Abrir") : qsTr("Usar")
                            color: executeButton.enabled ? ui.accent : ui.textMuted
                            font.pixelSize: Style.type.label; font.weight: Style.weight.demiBold; textFormat: Text.PlainText
                        }
                        Keycap { text: "↵" }
                    }
                    // The one primary action: a tinted capsule, matching the selected row.
                    background: Rectangle {
                        radius: height / 2
                        color: !executeButton.enabled ? "transparent"
                            : executeButton.down ? Style.alpha(ui.accent, Style.state.selected + Style.state.hover)
                            : executeButton.hovered ? Style.alpha(ui.accent, Style.state.selected + Style.state.chip)
                            : Style.alpha(ui.accent, Style.state.selected)
                        border.width: executeButton.activeFocus ? 2 : 0
                        border.color: ui.focus
                    }
                }
            }
        }
        AiSettings {
            id: aiPanel
            objectName: "aiSettings"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            Layout.margins: Style.space.lg
            visible: window.activePanel === "ai"
            controller: aiProviders
            textController: aiText
            operationStartBlocked: window.pendingDismiss
            onBackRequested: window.closeAiPanel()
        }
        OrlaCommandPanel {
            id: commandPanel
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            Layout.margins: Style.space.lg
            visible: window.activePanel === "command"
            controller: window.commands
            operationStartBlocked: window.pendingDismiss
            onBackRequested: window.closeCommandPanel()
        }
        SteamSettings {
            id: steamPanel
            objectName: "steamSettings"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            Layout.margins: Style.space.lg
            visible: window.activePanel === "steam"
            controller: steamProvider
            operationStartBlocked: window.pendingDismiss
            onBackRequested: window.closeSteamPanel()
        }
    }
}
