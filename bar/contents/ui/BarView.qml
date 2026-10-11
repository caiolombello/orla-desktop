import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import QtQuick.Layouts

// Presentation only: providers, panel geometry and app menus have other owners.
Item {
    id: root
    property var sessionBackend: null
    property var applicationBackend: null
    property string hostVersion: Application.version
    property bool showApplicationName: true
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
    implicitHeight: 32

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
        spacing: 8
        Templates.ToolButton {
            id: menuButton
            objectName: "orlaMenuButton"
            text: root.boundedText(root.menuLabel, 32) || "Orla"
            icon.source: root.menuIcon === "none" ? "" : Qt.resolvedUrl("../images/orla.svg")
            implicitWidth: Math.max(32, (menuGlyph.visible ? 26 : 0)
                + Math.min(120, menuLabelText.implicitWidth) + leftPadding + rightPadding)
            implicitHeight: 32
            padding: 6
            focusPolicy: Qt.StrongFocus
            hoverEnabled: true
            Layout.minimumWidth: 32
            Layout.maximumWidth: Math.max(32, root.width)
            Layout.fillHeight: true
            Accessible.name: qsTr("Menu Orla")
            Accessible.role: Accessible.ButtonMenu
            onClicked: menu.visible ? menu.close() : menu.open()
            Controls.ToolTip.visible: hovered
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
                    visible: menuButton.availableWidth >= 48 || menuButton.icon.source.toString() === ""
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
            font.weight: Font.DemiBold
            color: menuButton.palette.windowText
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.maximumWidth: 240
            Accessible.name: text
        }
    }
    Controls.Menu {
        id: menu
        property bool restoreFocus: true
        onAboutToShow: {
            root.preserveApplication = true;
            restoreFocus = true;
        }
        objectName: "orlaMenu"
        y: root.height
        Controls.MenuItem { objectName: "aboutOrla"; text: qsTr("Sobre Orla Desktop"); onTriggered: root.open("about") }
        Controls.MenuItem { objectName: "aboutSystem"; text: qsTr("Sobre o sistema"); onTriggered: root.open("system") }
        Controls.MenuItem { objectName: "systemSettings"; text: qsTr("Configurações do sistema"); onTriggered: root.open("settings") }
        Controls.MenuItem { objectName: "configureBar"; text: qsTr("Configurar barra…"); onTriggered: root.open("configure") }
        Controls.MenuSeparator {}
        Controls.MenuItem {
            enabled: false
            visible: actions.status !== "ready"
            text: actions.status === "loading" ? qsTr("Verificando ações da sessão…") : qsTr("Ações da sessão indisponíveis")
        }
        Controls.MenuItem { objectName: "sessionLock"; text: qsTr("Bloquear"); enabled: actions.can("lock"); onTriggered: root.requestSession("lock") }
        Controls.MenuItem { objectName: "sessionSuspend"; text: qsTr("Suspender"); enabled: actions.can("suspend"); onTriggered: root.requestSession("suspend") }
        Controls.MenuSeparator {}
        Controls.MenuItem { objectName: "sessionLogout"; text: qsTr("Sair…"); enabled: actions.can("logout"); onTriggered: root.requestSession("logout") }
        Controls.MenuItem { objectName: "sessionReboot"; text: qsTr("Reiniciar…"); enabled: actions.can("reboot"); onTriggered: root.requestSession("reboot") }
        Controls.MenuItem { objectName: "sessionShutdown"; text: qsTr("Desligar…"); enabled: actions.can("shutdown"); onTriggered: root.requestSession("shutdown") }
        Controls.MenuItem { enabled: false; visible: actions.error !== ""; text: actions.error }
        onClosed: {
            root.preserveApplication = false;
            if (restoreFocus) menuButton.forceActiveFocus(Qt.PopupFocusReason);
        }
    }
    Controls.Popup {
        id: about
        y: root.height
        width: Math.min(360, root.Window.window ? root.Window.window.width : 360)
        padding: 16
        modal: false
        focus: true
        contentItem: ColumnLayout {
            Controls.Label { text: qsTr("Orla Desktop"); font.bold: true; textFormat: Text.PlainText }
            Controls.Label { text: qsTr("Barra experimental · 0.1\nComponentes opcionais para KDE Plasma.\nMenus globais e bandeja usam widgets nativos separados."); textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Controls.Button { text: qsTr("Fechar"); onClicked: about.close() }
        }
        onClosed: menuButton.forceActiveFocus(Qt.PopupFocusReason)
    }
}
