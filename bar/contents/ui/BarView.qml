import QtQuick
import QtQuick.Window
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import QtQuick.Layouts

// Presentation only: providers, panel geometry and app menus have other owners.
Item {
    id: root
    property var sessionBackend: null
    property var applicationBackend: null
    property var popupHost: null
    property var menuTooltipBackend: null
    readonly property alias menuControl: menuButton
    readonly property bool menuIsOpen: menu.visible
    property string hostVersion: Application.version
    property bool showApplicationName: true
    property bool showMenuLabel: true
    property bool compactHeight: false
    property string menuLabel: "Orla"
    property string menuIcon: "orla"
    readonly property bool nativeSessionLoaded: actions.nativeLoaded
    readonly property bool nativeApplicationLoaded: nativeApplication.item !== null
    readonly property string sessionStatus: actions.status
    readonly property string actionError: actions.error
    readonly property var application: applicationBackend !== null ? applicationBackend : nativeApplication.item
    property bool preserveApplication: false
    readonly property var nextApplication: ({active: Boolean(application && application.hasActiveApplication),
        name: application ? boundedText(application.appName, 160) : ""})
    property var displayedApplication: ({active: false, name: ""})
    readonly property string applicationName: !displayedApplication.active ? qsTr("Área de trabalho")
        : displayedApplication.name || qsTr("Aplicativo")
    onNextApplicationChanged: if (!preserveApplication) displayedApplication = nextApplication
    onPreserveApplicationChanged: if (!preserveApplication) displayedApplication = nextApplication
    Component.onCompleted: displayedApplication = nextApplication
    signal openRequested(string kind)
    implicitWidth: row.implicitWidth
    implicitHeight: compactHeight ? 28 : 32

    SessionActions {
        id: actions
        backend: root.sessionBackend
        hostVersion: root.hostVersion
    }
    Loader {
        id: nativeApplication
        active: root.showApplicationName && root.applicationBackend === null && actions.supportedHost
        source: active ? "NativeApplication.qml" : ""
    }
    function boundedText(value, maximum) {
        return String(value || "").slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function requestSession(action) {
        if (!actions.can(action)) return false;
        menu.restoreFocus = false;
        menu.close();
        const dispatched = actions.request(action);
        if (!dispatched) menuButton.forceActiveFocus(Qt.PopupFocusReason);
        return dispatched;
    }
    function open(kind) {
        menu.restoreFocus = false;
        menu.close();
        if (kind === "about") { about.open(); return true; }
        if (kind !== "system" && kind !== "settings" && kind !== "configure") return false;
        openRequested(kind);
        return true;
    }
    RowLayout {
        id: row
        anchors.fill: parent
        spacing: root.compactHeight ? 8 : 10
        Templates.ToolButton {
            id: menuButton
            objectName: "orlaMenuButton"
            text: root.boundedText(root.menuLabel, 32) || "Orla"
            icon.source: root.menuIcon === "none" ? "" : Qt.resolvedUrl("../images/orla.svg")
            readonly property bool wantsLabel: root.showMenuLabel || root.menuIcon === "none"
            implicitWidth: Math.max(32, (menuGlyph.visible ? 20 : 0)
                + (wantsLabel ? Math.min(120, menuLabelText.implicitWidth) + (menuGlyph.visible ? 6 : 0) : 0)
                + leftPadding + rightPadding)
            implicitHeight: root.implicitHeight
            padding: 6
            focusPolicy: Qt.StrongFocus
            hoverEnabled: true
            Layout.minimumWidth: 32
            Layout.maximumWidth: Math.min(implicitWidth, Math.max(32, root.width))
            Layout.preferredHeight: root.implicitHeight
            Layout.maximumHeight: root.implicitHeight
            Layout.alignment: Qt.AlignVCenter
            Accessible.name: qsTr("Menu Orla")
            Accessible.role: Accessible.ButtonMenu
            onPressed: if (root.menuTooltipBackend) root.menuTooltipBackend.hideImmediately()
            onClicked: menu.visible ? menu.close() : menu.open()
            // Panel tooltips use a separate native surface. The shared Item
            // tooltip can otherwise be clamped over this short panel's button.
            Controls.ToolTip.visible: hovered && !root.menuTooltipBackend
            Controls.ToolTip.text: qsTr("Menu Orla")
            contentItem: RowLayout {
                spacing: 6
                Image {
                    id: menuGlyph
                    objectName: "orlaMenuIcon"
                    source: menuButton.icon.source
                    visible: source.toString() !== ""
                    sourceSize.width: 20; sourceSize.height: 20
                    Layout.preferredWidth: 20; Layout.preferredHeight: 20
                    Layout.minimumWidth: 20; Layout.maximumWidth: 20
                    fillMode: Image.PreserveAspectFit
                }
                Text {
                    id: menuLabelText
                    objectName: "orlaMenuLabel"
                    text: menuButton.text
                    visible: menuButton.wantsLabel && (menuButton.availableWidth >= 48 || root.menuIcon === "none")
                    textFormat: Text.PlainText
                    font: menuButton.font
                    color: menuButton.palette.buttonText
                    elide: Text.ElideRight
                    Layout.minimumWidth: 0; Layout.maximumWidth: 120
                    Layout.fillWidth: true
                }
            }
            background: Rectangle {
                radius: 6
                color: Qt.rgba(menuButton.palette.highlight.r, menuButton.palette.highlight.g,
                    menuButton.palette.highlight.b, menuButton.down ? 0.24 : menuButton.hovered ? 0.12 : 0)
                border.width: menuButton.visualFocus ? 1 : 0
                border.color: menuButton.palette.highlight
                visible: menuButton.down || menuButton.hovered || menuButton.visualFocus
            }
        }
        Controls.ToolButton {
            objectName: "sessionActionError"
            visible: root.actionError !== ""
            text: qsTr("Falha na ação")
            Accessible.description: root.actionError
            Controls.ToolTip.visible: hovered
            Controls.ToolTip.text: root.actionError
            onClicked: menu.open()
        }
        Text {
            objectName: "activeApplicationName"
            visible: root.showApplicationName
            text: root.applicationName
            textFormat: Text.PlainText
            elide: Text.ElideRight
            font.weight: Font.Bold
            color: menuButton.palette.windowText
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: 240
            Accessible.name: text
        }
    }
    // Use the controls' keyboard semantics with our own compact presentation.
    component OrlaMenuItem: Templates.MenuItem {
        id: entry
        implicitWidth: 268
        implicitHeight: 32
        height: visible ? implicitHeight : 0
        padding: 8
        leftPadding: 12
        rightPadding: 12
        font: menuButton.font
        contentItem: Text {
            text: entry.text
            textFormat: Text.PlainText
            font: entry.font
            color: entry.enabled ? (entry.highlighted ? entry.palette.highlightedText : entry.palette.windowText)
                : entry.palette.disabled.windowText
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 5
            color: entry.palette.highlight
            visible: entry.enabled && (entry.highlighted || entry.down)
        }
    }
    component OrlaMenuSeparator: Templates.MenuSeparator {
        implicitHeight: 9
        padding: 4
        contentItem: Rectangle {
            implicitHeight: 1
            color: Qt.rgba(menuButton.palette.windowText.r, menuButton.palette.windowText.g,
                menuButton.palette.windowText.b, 0.15)
        }
    }
    Controls.Menu {
        id: menu
        property bool restoreFocus: true
        onAboutToShow: {
            root.preserveApplication = true;
            restoreFocus = true;
            if (root.popupHost) root.popupHost.showPopup(menu, menuButton);
        }
        objectName: "orlaMenu"
        parent: root.popupHost ? root.popupHost.hostItem : menuButton
        // Plasma uses a full-sized appletpopup host. Standalone presentation
        // uses Popup.Window; neither places a tall menu in the panel overlay.
        popupType: root.popupHost ? Controls.Popup.Item : Controls.Popup.Window
        x: 0
        y: root.popupHost ? 0 : menuButton.height + 2
        margins: -1
        width: 268
        padding: 5
        spacing: 0
        focus: true
        closePolicy: Controls.Popup.CloseOnEscape | Controls.Popup.CloseOnPressOutside
        background: Rectangle {
            radius: 9
            color: menuButton.palette.window
            border.width: 1
            border.color: Qt.rgba(menuButton.palette.windowText.r, menuButton.palette.windowText.g,
                menuButton.palette.windowText.b, 0.18)
        }
        OrlaMenuItem { objectName: "aboutOrla"; text: qsTr("Sobre Orla Desktop"); onTriggered: root.open("about") }
        OrlaMenuItem { objectName: "aboutSystem"; text: qsTr("Sobre o sistema"); onTriggered: root.open("system") }
        OrlaMenuItem { objectName: "systemSettings"; text: qsTr("Configurações do sistema"); onTriggered: root.open("settings") }
        OrlaMenuItem { objectName: "configureBar"; text: qsTr("Configurar barra…"); onTriggered: root.open("configure") }
        OrlaMenuSeparator {}
        OrlaMenuItem {
            objectName: "sessionAvailability"
            enabled: false
            visible: actions.status !== "ready"
            text: actions.status === "loading" ? qsTr("Verificando ações da sessão…") : qsTr("Ações da sessão indisponíveis")
        }
        OrlaMenuItem { objectName: "sessionLock"; text: qsTr("Bloquear"); enabled: actions.can("lock"); onTriggered: root.requestSession("lock") }
        OrlaMenuItem { objectName: "sessionSuspend"; text: qsTr("Suspender"); enabled: actions.can("suspend"); onTriggered: root.requestSession("suspend") }
        OrlaMenuSeparator {}
        OrlaMenuItem { objectName: "sessionLogout"; text: qsTr("Sair…"); enabled: actions.can("logout"); onTriggered: root.requestSession("logout") }
        OrlaMenuItem { objectName: "sessionReboot"; text: qsTr("Reiniciar…"); enabled: actions.can("reboot"); onTriggered: root.requestSession("reboot") }
        OrlaMenuItem { objectName: "sessionShutdown"; text: qsTr("Desligar…"); enabled: actions.can("shutdown"); onTriggered: root.requestSession("shutdown") }
        OrlaMenuItem { enabled: false; visible: actions.error !== ""; text: actions.error }
        onClosed: {
            if (root.popupHost) root.popupHost.hidePopup(menu);
            root.preserveApplication = false;
            if (restoreFocus) menuButton.forceActiveFocus(Qt.PopupFocusReason);
        }
    }
    Controls.Popup {
        id: about
        objectName: "aboutOrlaPopup"
        parent: root.popupHost ? root.popupHost.hostItem : menuButton
        popupType: root.popupHost ? Controls.Popup.Item : Controls.Popup.Window
        y: root.popupHost ? 0 : menuButton.height + 2
        width: 360
        margins: -1
        padding: 16
        modal: false
        focus: true
        contentItem: ColumnLayout {
            Controls.Label { text: qsTr("Orla Desktop"); font.bold: true; textFormat: Text.PlainText }
            Controls.Label { text: qsTr("Barra experimental · 0.1\nComponentes opcionais para KDE Plasma.\nMenus globais e bandeja usam widgets nativos separados."); textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Controls.Button { text: qsTr("Fechar"); onClicked: about.close() }
        }
        onAboutToShow: if (root.popupHost) root.popupHost.showPopup(about, menuButton)
        onClosed: {
            if (root.popupHost) root.popupHost.hidePopup(about);
            menuButton.forceActiveFocus(Qt.PopupFocusReason);
        }
    }
}
