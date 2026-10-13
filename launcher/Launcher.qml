import QtQuick
import QtQuick.Controls
import QtQuick.Controls.impl as ControlsImpl
import QtQuick.Layouts
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
    readonly property int shadowMargin: Style.space.lg + Style.space.xxs
    readonly property var blurRequest: windowSession ? [glass.x, glass.y, glass.width, glass.height, glass.radius] : null
    onBlurRequestChanged: {
        if (blurRequest && windowSession.setBlurRegion)
            windowSession.setBlurRegion(Qt.rect(glass.x, glass.y, glass.width, glass.height), glass.radius)
    }
    property string activePanel: "search"
    property bool pendingDismiss: false
    property bool pendingQuit: false
    readonly property bool executionBlocked: pendingDismiss || aiProviders.busy || aiText.busy || steamProvider.busy
    property var selectedRow: launcher.selectedIndex >= 0 ? launcher.rows[launcher.selectedIndex] : null
    function executeTicket(ticket, selectRow) {
        if (!ticket || pendingDismiss || aiProviders.busy || aiText.busy || steamProvider.busy) return
        if (selectRow) launcher.select(ticket.row)
        launcher.execute(ticket.row, ticket.generation, ticket.id, ticket.actionId || "")
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
        if (aiReady && textReady && steamReady) finishPendingClose()
        return !pendingDismiss
    }
    onActiveChanged: if (active && activePanel === "search") search.forceActiveFocus()
    onClosing: function(close) {
        close.accepted = requestDismiss(true)
    }
    Shortcut {
        sequence: "Escape"; context: Qt.WindowShortcut
        onActivated: {
            if (window.activePanel === "ai") window.closeAiPanel()
            else if (window.activePanel === "steam") window.closeSteamPanel()
            else window.requestDismiss(false)
        }
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
            if (search.text !== launcher.query) search.text = launcher.query
            if (launcher.selectedIndex >= 0) results.positionViewAtIndex(launcher.selectedIndex, ListView.Contain)
        }
    }

    // Soft shadow in the transparent margin: stacked translucent outlines stay
    // cheap for the scene graph, unlike a blurred Canvas.
    Repeater {
        model: 6
        Rectangle {
            required property int index
            readonly property real spread: (index + 1) * (window.shadowMargin - Style.space.xs) / 6
            x: glass.x - spread
            y: glass.y - spread + Style.space.xs
            width: glass.width + spread * 2
            height: glass.height + spread * 2
            radius: glass.radius + spread
            color: Style.alpha(Style.glass.shade, 0.07 - index * 0.01)
        }
    }
    Rectangle {
        id: glass
        anchors.fill: parent
        anchors.margins: window.shadowMargin
        radius: Style.radius.popup + Style.space.xs
        color: Style.alpha(ui.canvas, 0.86)
        border.width: 1
        border.color: Style.alpha(Style.glass.highlight, 0.14)
        // Specular top edge.
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: parent.radius - 1
            gradient: Gradient {
                GradientStop { position: 0; color: Style.alpha(Style.glass.highlight, Style.glass.sheenDark) }
                GradientStop { position: 0.4; color: "transparent" }
            }
        }
    }

    ColumnLayout {
        anchors.fill: glass
        anchors.margins: Style.space.lg
        spacing: Style.space.md
        RowLayout {
            objectName: "launcherHeader"
            Layout.fillWidth: true
            spacing: Style.space.sm
            // The frameless window moves by dragging its header.
            DragHandler { target: null; onActiveChanged: if (active) window.startSystemMove() }
            Rectangle {
                width: Style.size.iconButton; height: width; radius: Math.round(width * 0.3); color: ui.accent
                Text { anchors.centerIn: parent; text: "o"; color: ui.onAccent; font.pixelSize: Style.type.headline; font.weight: Font.DemiBold; textFormat: Text.PlainText }
            }
            Text { text: "Orla"; color: ui.text; font.pixelSize: Style.type.title; font.weight: Font.DemiBold; textFormat: Text.PlainText }
            Text { Layout.fillWidth: true; Layout.minimumWidth: 0; horizontalAlignment: Text.AlignRight; wrapMode: Text.Wrap; text: windowSession && windowSession.shortcutText ? windowSession.shortcutText : qsTr("Busca local"); color: ui.textMuted; font.pixelSize: Style.type.caption; textFormat: Text.PlainText }
            Button {
                id: aiEntry
                objectName: "aiEntryButton"
                Layout.minimumWidth: 40
                Layout.minimumHeight: 40
                Layout.preferredHeight: 40
                leftPadding: 12
                rightPadding: 12
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
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: window.activePanel === "ai" ? ui.onAccent : ui.text; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: height / 2; color: window.activePanel === "ai" ? ui.accent : parent.hovered ? Style.alpha(ui.text, Style.state.pressed) : Style.alpha(ui.text, Style.state.hover); border.width: parent.activeFocus ? 2 : 0; border.color: ui.focus }
            }
            Button {
                id: steamEntry
                objectName: "steamEntryButton"
                Layout.minimumWidth: 40
                Layout.minimumHeight: 40
                Layout.preferredHeight: 40
                leftPadding: 12
                rightPadding: 12
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
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: window.activePanel === "steam" ? ui.onAccent : ui.text; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: height / 2; color: window.activePanel === "steam" ? ui.accent : parent.hovered ? Style.alpha(ui.text, Style.state.pressed) : Style.alpha(ui.text, Style.state.hover); border.width: parent.activeFocus ? 2 : 0; border.color: ui.focus }
            }
        }
        TextField {
            id: search
            objectName: "searchInput"
            Layout.fillWidth: true
            Layout.preferredHeight: Style.size.target + Style.space.lg
            color: ui.text
            placeholderText: qsTr("Buscar aplicativo, jogo ou calcular…")
            placeholderTextColor: ui.textMuted
            font.pixelSize: Style.type.headline
            leftPadding: Style.size.target + Style.space.sm
            rightPadding: Style.space.lg
            selectByMouse: true
            maximumLength: 512
            Accessible.name: qsTr("Buscar aplicativos, jogos ou calcular")
            visible: window.activePanel === "search"
            background: Rectangle {
                radius: height / 2
                color: Style.alpha(ui.text, Style.state.hover)
                border.width: 1
                border.color: search.activeFocus ? Style.alpha(ui.accent, 0.6) : Style.alpha(ui.text, Style.state.pressed)
                // Magnifier glyph, drawn so the launcher needs no icon theme.
                Canvas {
                    x: Style.space.lg
                    anchors.verticalCenter: parent.verticalCenter
                    width: Style.size.iconMd
                    height: width
                    onPaint: {
                        const context = getContext("2d")
                        context.reset()
                        context.strokeStyle = ui.textMuted
                        context.lineWidth = 2
                        context.lineCap = "round"
                        context.beginPath()
                        context.arc(width * 0.42, height * 0.42, width * 0.3, 0, 2 * Math.PI)
                        context.stroke()
                        context.beginPath()
                        context.moveTo(width * 0.65, height * 0.65)
                        context.lineTo(width * 0.92, height * 0.92)
                        context.stroke()
                    }
                }
            }
            onTextEdited: launcher.query = text
            Keys.priority: Keys.BeforeItem
            Keys.onDownPressed: function(event) { launcher.moveSelection(1); event.accepted = true }
            Keys.onUpPressed: function(event) { launcher.moveSelection(-1); event.accepted = true }
            Keys.onReturnPressed: function(event) { window.executeSelection(); event.accepted = true }
            Keys.onEnterPressed: function(event) { window.executeSelection(); event.accepted = true }
            Component.onCompleted: forceActiveFocus()
        }
        RowLayout {
            visible: window.activePanel === "search"
            Layout.fillWidth: true
            Text { text: qsTr("APLICATIVOS · CALCULADORA · STEAM"); color: ui.textMuted; font.pixelSize: Style.type.overline; font.weight: Font.Bold; font.letterSpacing: Style.letterSpacing.overline; textFormat: Text.PlainText }
            Item { Layout.fillWidth: true }
            Text { text: launcher.status === "loading" ? qsTr("Buscando…") : launcher.rows.length === 1 ? qsTr("1 resultado") : launcher.rows.length ? qsTr("%1 resultados").arg(launcher.rows.length) : ""; color: ui.accent; font.pixelSize: Style.type.caption; textFormat: Text.PlainText }
        }
        Item {
            visible: window.activePanel === "search"
            Layout.fillWidth: true
            Layout.fillHeight: true
            ListView {
                id: results
                objectName: "resultsList"
                anchors.fill: parent
                clip: true
                spacing: 6
                model: launcher.rows
                section.property: "categoryLabel"
                section.delegate: Text {
                    required property string section
                    width: results.width; height: Style.size.iconButton; text: section; color: ui.textMuted
                    verticalAlignment: Text.AlignBottom; bottomPadding: Style.space.xs; leftPadding: Style.space.sm
                    font.pixelSize: Style.type.overline; font.weight: Font.Bold; font.letterSpacing: Style.letterSpacing.overline; textFormat: Text.PlainText
                }
                ScrollBar.vertical: ScrollBar { }
                delegate: ItemDelegate {
                    id: result
                    required property int index
                    required property var modelData
                    property var rowData: modelData
                    property var executionTicket: null
                    // Leave the scrollbar its own lane.
                    width: results.width - (results.ScrollBar.vertical.visible ? results.ScrollBar.vertical.width + Style.space.xs : 0)
                    readonly property bool selected: launcher.selectedIndex === result.index
                    readonly property var tile: Style.iconTiles[rowData.kind === "calculator" ? "slate" : rowData.kind === "steam" ? "ink" : "sea"]
                    height: Style.size.target + Style.space.md
                    enabled: rowData.enabled && !window.executionBlocked
                    hoverEnabled: true
                    leftPadding: Style.space.sm
                    rightPadding: Style.space.md
                    Accessible.name: rowData.title + ", " + rowData.source
                    background: Rectangle {
                        radius: Style.radius.card
                        color: result.selected ? ui.accent : result.hovered ? Style.alpha(ui.text, Style.state.hover) : "transparent"
                        border.width: result.activeFocus ? 2 : 0
                        border.color: ui.focus
                    }
                    contentItem: RowLayout {
                        spacing: Style.space.md
                        Item {
                            Layout.preferredWidth: Style.size.iconLg + Style.space.xs
                            Layout.preferredHeight: Style.size.iconLg + Style.space.xs
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
                                Text { anchors.centerIn: parent; text: result.rowData.kind === "calculator" ? "=" : result.rowData.kind === "steam" ? "S" : "▦"; color: result.tile.ink; font.pixelSize: Style.type.title; font.weight: Font.Bold; textFormat: Text.PlainText }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text { Layout.fillWidth: true; text: result.rowData.title; color: result.selected ? ui.onAccent : ui.text; font.pixelSize: Style.type.title; font.weight: Font.DemiBold; elide: Text.ElideRight; maximumLineCount: 1; textFormat: Text.PlainText }
                            Text { Layout.fillWidth: true; text: result.rowData.description || result.rowData.source; color: result.selected ? Style.alpha(ui.onAccent, 0.8) : ui.textMuted; font.pixelSize: Style.type.label; elide: Text.ElideRight; maximumLineCount: 1; textFormat: Text.PlainText }
                        }
                        Text { text: result.selected ? "↵" : ""; color: ui.onAccent; font.pixelSize: Style.type.title; font.weight: Font.Bold; textFormat: Text.PlainText }
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
                width: Math.min(parent.width - 24, 390)
                spacing: 10
                visible: launcher.rows.length === 0
                Text {
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; color: ui.text; font.pixelSize: Style.type.headline; textFormat: Text.PlainText
                    text: launcher.status === "error" ? qsTr("Não foi possível buscar") : launcher.status === "loading" ? qsTr("Buscando no seu computador") : launcher.status === "empty" ? qsTr("Nenhum resultado") : qsTr("O que você quer abrir?")
                }
                Text {
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; color: ui.textMuted; font.pixelSize: Style.type.body; wrapMode: Text.Wrap; textFormat: Text.PlainText
                    text: launcher.status === "error" ? launcher.error : launcher.status === "empty" ? qsTr("Tente outro nome ou uma expressão como 24 * 7.") : launcher.status === "loading" ? qsTr("Você pode continuar digitando ou cancelar com Esc.") : qsTr("Digite um nome ou uma conta. Enter executa a seleção.")
                }
            }
        }
        Text {
            objectName: "executionWaiting"
            Layout.fillWidth: true
            visible: window.activePanel === "search" && (window.executionBlocked || (windowSession && windowSession.notice.length > 0))
            text: window.executionBlocked ? qsTr("Aguarde o encerramento das operações antes de abrir um resultado.") : windowSession ? windowSession.notice : ""
            color: ui.warning; font.pixelSize: Style.type.caption; wrapMode: Text.Wrap; textFormat: Text.PlainText
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Style.alpha(ui.text, Style.state.hover); visible: window.activePanel === "search" }
        RowLayout {
            visible: window.activePanel === "search"
            Layout.fillWidth: true
            spacing: 8
            Text { text: qsTr("↑ ↓ navegar · Esc fechar"); color: ui.textMuted; font.pixelSize: Style.type.caption; textFormat: Text.PlainText }
            Item { Layout.fillWidth: true }
            Repeater {
                model: window.selectedRow ? window.selectedRow.actions.slice(0, window.width < 560 ? 1 : 2) : []
                delegate: Button {
                    required property var modelData
                    property var executionTicket: null
                    text: modelData.text
                    enabled: launcher.status === "ready" && !window.executionBlocked
                    onPressed: executionTicket = { row: modelData.row, generation: modelData.generation, id: modelData.resultId, actionId: modelData.id }
                    onClicked: window.executeTicket(executionTicket, false)
                    leftPadding: Style.space.md
                    rightPadding: Style.space.md
                    Layout.preferredHeight: Style.size.iconButton + Style.space.xs
                    contentItem: Text { text: parent.text; color: parent.enabled ? ui.accent : ui.textMuted; font.pixelSize: Style.type.label; verticalAlignment: Text.AlignVCenter; textFormat: Text.PlainText; elide: Text.ElideRight }
                    background: Rectangle { radius: height / 2; color: Style.alpha(ui.text, Style.state.hover); border.color: parent.activeFocus ? ui.focus : "transparent"; border.width: 2 }
                    Layout.maximumWidth: window.width < 560 ? 118 : 150
                }
            }
            Button {
                property var executionTicket: null
                text: window.selectedRow && (window.selectedRow.kind === "app" || window.selectedRow.kind === "steam") ? qsTr("Abrir ↵") : qsTr("Usar ↵")
                enabled: launcher.status === "ready" && launcher.selectedIndex >= 0 && !window.executionBlocked
                onPressed: executionTicket = window.selectedRow ? { row: launcher.selectedIndex, generation: window.selectedRow.generation, id: window.selectedRow.id } : null
                onClicked: window.executeTicket(executionTicket, false)
                leftPadding: Style.space.md
                rightPadding: Style.space.md
                Layout.preferredHeight: Style.size.iconButton + Style.space.xs
                contentItem: Text { text: parent.text; color: parent.enabled ? ui.onAccent : ui.textMuted; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; verticalAlignment: Text.AlignVCenter; textFormat: Text.PlainText }
                background: Rectangle { radius: height / 2; color: parent.enabled ? ui.accent : Style.alpha(ui.text, Style.state.hover); border.width: parent.activeFocus ? 2 : 0; border.color: ui.text }
            }
        }
        AiSettings {
            id: aiPanel
            objectName: "aiSettings"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            visible: window.activePanel === "ai"
            controller: aiProviders
            textController: aiText
            operationStartBlocked: window.pendingDismiss
            onBackRequested: window.closeAiPanel()
        }
        SteamSettings {
            id: steamPanel
            objectName: "steamSettings"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            visible: window.activePanel === "steam"
            controller: steamProvider
            operationStartBlocked: window.pendingDismiss
            onBackRequested: window.closeSteamPanel()
        }
    }
}
