import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: window
    objectName: "launcherWindow"
    visible: true
    width: 660
    height: 520
    minimumWidth: 440
    minimumHeight: 380
    title: qsTr("Orla Launcher")
    color: "#111923"
    flags: Qt.Window
    property string activePanel: "search"
    property bool pendingDismiss: false
    property bool pendingQuit: false
    property var selectedRow: launcher.selectedIndex >= 0 ? launcher.rows[launcher.selectedIndex] : null
    function executeSelection() {
        const row = selectedRow
        if (row) launcher.execute(launcher.selectedIndex, row.generation, row.id)
    }
    function closeAiPanel() {
        aiProviders.cancel(aiProviders.requestId)
        activePanel = "search"
        search.forceActiveFocus()
    }
    function closeSteamPanel() {
        steamProvider.cancelAll()
        activePanel = "search"
        search.forceActiveFocus()
    }
    function finishPendingClose() {
        if (!pendingDismiss || aiProviders.busy || steamProvider.busy) return
        pendingDismiss = false
        launcher.dismiss()
        if (pendingQuit) Qt.quit()
        pendingQuit = false
    }
    function requestDismiss(quitApplication) {
        const aiReady = aiProviders.requestClose()
        const steamReady = steamProvider.requestClose()
        if (!aiReady || !steamReady) {
            pendingDismiss = true
            pendingQuit = quitApplication
            return
        }
        launcher.dismiss()
        if (quitApplication) Qt.quit()
    }
    onActiveChanged: if (active && activePanel === "search") search.forceActiveFocus()
    onClosing: function(close) {
        const aiReady = aiProviders.requestClose()
        const steamReady = steamProvider.requestClose()
        if (!aiReady || !steamReady) {
            close.accepted = false
            pendingDismiss = true
            pendingQuit = true
            return
        }
        launcher.dismiss()
        Qt.quit()
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

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        RowLayout {
            objectName: "launcherHeader"
            Layout.fillWidth: true
            Rectangle {
                width: 32; height: 32; radius: 11; color: "#69D7C2"
                Text { anchors.centerIn: parent; text: "o"; color: "#111923"; font.pixelSize: 26; font.weight: Font.Medium; textFormat: Text.PlainText }
            }
            Text { text: "Orla"; color: "#EAF4F1"; font.pixelSize: 23; font.weight: Font.DemiBold; textFormat: Text.PlainText }
            Text { text: qsTr("LAUNCHER"); color: "#9FAFBC"; font.pixelSize: 10; font.letterSpacing: 2; textFormat: Text.PlainText }
            Item { Layout.fillWidth: true }
            Text { text: windowSession && windowSession.shortcutText ? windowSession.shortcutText : qsTr("Busca local"); color: "#9FAFBC"; font.pixelSize: 11; textFormat: Text.PlainText }
            Button {
                id: aiEntry
                objectName: "aiEntryButton"
                text: window.activePanel === "ai" ? qsTr("Busca") : qsTr("IA")
                Accessible.name: window.activePanel === "ai" ? qsTr("Voltar à busca local") : qsTr("Abrir provedores de IA, desligados")
                onClicked: {
                    if (window.activePanel === "ai") window.closeAiPanel()
                    else { window.activePanel = "ai"; aiPanel.focusFirst() }
                }
                contentItem: Text { text: parent.text; color: "#69D7C2"; font.pixelSize: 11; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: 8; color: "#22313D"; border.width: parent.activeFocus ? 1 : 0; border.color: "#69D7C2" }
            }
            Button {
                id: steamEntry
                objectName: "steamEntryButton"
                text: window.activePanel === "steam" ? qsTr("Busca") : qsTr("Steam")
                Accessible.name: window.activePanel === "steam" ? qsTr("Voltar à busca local") : qsTr("Abrir jogos Steam locais")
                onClicked: {
                    if (window.activePanel === "steam") window.closeSteamPanel()
                    else { window.activePanel = "steam"; steamPanel.focusFirst() }
                }
                contentItem: Text { text: parent.text; color: "#69D7C2"; font.pixelSize: 11; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: 8; color: "#22313D"; border.width: parent.activeFocus ? 1 : 0; border.color: "#69D7C2" }
            }
        }
        TextField {
            id: search
            objectName: "searchInput"
            Layout.fillWidth: true
            Layout.preferredHeight: 58
            color: "#EAF4F1"
            placeholderText: qsTr("Buscar aplicativo, jogo ou calcular…")
            placeholderTextColor: "#A7B7C4"
            font.pixelSize: 19
            leftPadding: 18
            rightPadding: 18
            selectByMouse: true
            maximumLength: 512
            Accessible.name: qsTr("Buscar aplicativos, jogos ou calcular")
            visible: window.activePanel === "search"
            background: Rectangle { radius: 14; color: "#1B2733"; border.width: 1; border.color: search.activeFocus ? "#69D7C2" : "#3B4B5A" }
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
            Text { text: qsTr("APLICATIVOS + CALCULADORA + STEAM"); color: "#9FAFBC"; font.pixelSize: 10; font.letterSpacing: 1.4; textFormat: Text.PlainText }
            Item { Layout.fillWidth: true }
            Text { text: launcher.status === "loading" ? qsTr("Buscando…") : launcher.rows.length === 1 ? qsTr("1 resultado") : launcher.rows.length ? qsTr("%1 resultados").arg(launcher.rows.length) : ""; color: "#69D7C2"; font.pixelSize: 11; textFormat: Text.PlainText }
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
                    width: results.width; height: 24; text: section; color: "#91A5B4"
                    font.pixelSize: 10; font.letterSpacing: 1.2; textFormat: Text.PlainText
                }
                ScrollBar.vertical: ScrollBar { }
                delegate: ItemDelegate {
                    id: result
                    required property int index
                    required property var modelData
                    property var rowData: modelData
                    property var executionTicket: null
                    width: results.width
                    height: 70
                    enabled: rowData.enabled
                    hoverEnabled: true
                    Accessible.name: rowData.title + ", " + rowData.source
                    background: Rectangle {
                        radius: 12
                        color: launcher.selectedIndex === result.index ? "#283F47" : result.hovered ? "#202D3A" : "transparent"
                        border.width: launcher.selectedIndex === result.index ? 1 : 0
                        border.color: "#69D7C2"
                    }
                    contentItem: RowLayout {
                        spacing: 12
                        Rectangle {
                            Layout.preferredWidth: 38; Layout.preferredHeight: 38
                            radius: 10; color: "#283542"
                            Text { anchors.centerIn: parent; text: result.rowData.kind === "calculator" ? "=" : result.rowData.kind === "steam" ? "S" : "▦"; color: "#69D7C2"; font.pixelSize: 23; textFormat: Text.PlainText }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Text { Layout.fillWidth: true; text: result.rowData.title; color: "#EAF4F1"; font.pixelSize: 16; font.weight: Font.Medium; elide: Text.ElideRight; maximumLineCount: 1; textFormat: Text.PlainText }
                            Text { Layout.fillWidth: true; text: result.rowData.description || result.rowData.source; color: "#A7B7C4"; font.pixelSize: 11; elide: Text.ElideRight; maximumLineCount: 1; textFormat: Text.PlainText }
                        }
                        Text { text: launcher.selectedIndex === result.index ? "↵" : ""; color: "#69D7C2"; font.pixelSize: 20; textFormat: Text.PlainText }
                    }
                    onPressed: executionTicket = { row: index, generation: rowData.generation, id: rowData.id }
                    onClicked: {
                        const ticket = executionTicket
                        if (ticket) {
                            launcher.select(ticket.row)
                            launcher.execute(ticket.row, ticket.generation, ticket.id)
                        }
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
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; color: "#EAF4F1"; font.pixelSize: 18; textFormat: Text.PlainText
                    text: launcher.status === "error" ? qsTr("Não foi possível buscar") : launcher.status === "loading" ? qsTr("Buscando no seu computador") : launcher.status === "empty" ? qsTr("Nenhum resultado") : qsTr("O que você quer abrir?")
                }
                Text {
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; color: "#A7B7C4"; font.pixelSize: 13; wrapMode: Text.Wrap; textFormat: Text.PlainText
                    text: launcher.status === "error" ? launcher.error : launcher.status === "empty" ? qsTr("Tente outro nome ou uma expressão como 24 * 7.") : launcher.status === "loading" ? qsTr("Você pode continuar digitando ou cancelar com Esc.") : qsTr("Digite um nome ou uma conta. Enter executa a seleção.")
                }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: window.activePanel === "search" && windowSession && windowSession.notice.length > 0
            text: windowSession ? windowSession.notice : ""
            color: "#E7C58E"; font.pixelSize: 11; wrapMode: Text.Wrap; textFormat: Text.PlainText
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: "#283542"; visible: window.activePanel === "search" }
        RowLayout {
            visible: window.activePanel === "search"
            Layout.fillWidth: true
            spacing: 8
            Text { text: qsTr("↑ ↓ navegar · Esc fechar"); color: "#A7B7C4"; font.pixelSize: 11; textFormat: Text.PlainText }
            Item { Layout.fillWidth: true }
            Repeater {
                model: window.selectedRow ? window.selectedRow.actions.slice(0, window.width < 560 ? 1 : 2) : []
                delegate: Button {
                    required property var modelData
                    property var executionTicket: null
                    text: modelData.text
                    enabled: launcher.status === "ready"
                    onPressed: executionTicket = { row: modelData.row, generation: modelData.generation, id: modelData.resultId, actionId: modelData.id }
                    onClicked: if (executionTicket) launcher.execute(executionTicket.row, executionTicket.generation, executionTicket.id, executionTicket.actionId)
                    contentItem: Text { text: parent.text; color: parent.enabled ? "#69D7C2" : "#A7B7C4"; font.pixelSize: 11; textFormat: Text.PlainText; elide: Text.ElideRight }
                    background: Rectangle { radius: 7; color: "#283542"; border.color: parent.activeFocus ? "#69D7C2" : "transparent"; border.width: 1 }
                    Layout.maximumWidth: window.width < 560 ? 118 : 150
                }
            }
            Button {
                property var executionTicket: null
                text: window.selectedRow && (window.selectedRow.kind === "app" || window.selectedRow.kind === "steam") ? qsTr("Abrir ↵") : qsTr("Usar ↵")
                enabled: launcher.status === "ready" && launcher.selectedIndex >= 0
                onPressed: executionTicket = window.selectedRow ? { row: launcher.selectedIndex, generation: window.selectedRow.generation, id: window.selectedRow.id } : null
                onClicked: if (executionTicket) launcher.execute(executionTicket.row, executionTicket.generation, executionTicket.id)
                contentItem: Text { text: parent.text; color: parent.enabled ? "#111923" : "#A7B7C4"; font.pixelSize: 11; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: 7; color: parent.enabled ? "#69D7C2" : "#283542"; border.width: parent.activeFocus ? 2 : 0; border.color: "#EAF4F1" }
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
            onBackRequested: window.closeSteamPanel()
        }
    }
}
