import QtQuick
import QtQuick.Window
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import QtQuick.Controls.impl as ControlsImpl
import QtQuick.Layouts
import "../code/Style.js" as Style

// Presentation only: providers, panel geometry and app menus have other owners.
Item {
    id: root
    property var sessionBackend: null
    property var applicationBackend: null
    property var recentApplicationsBackend: null
    property var popupHost: null
    property var menuTooltipBackend: null
    property var controlCenterTooltipBackend: null
    readonly property alias controlCenterControl: controlCenterButton
    readonly property alias menuControl: menuButton
    readonly property bool menuIsOpen: menu.visible
    property string hostVersion: Application.version
    property bool showOrlaMenu: true
    property bool showControlCenter: false
    property QtObject controlCenterClient: null
    property Item controlCenterHost: null
    property string controlCenterLoadError: ""
    property bool reducedMotion: false
    property QtObject leasedControlCenterClient: null
    property int controlCenterGeneration: 0
    property bool controlCenterDispatchActive: false
    readonly property bool controlCenterCompatible: Boolean(controlCenterClient && controlCenterClient.apiVersion === 1
        && typeof controlCenterClient.open === "function" && typeof controlCenterClient.release === "function")
    readonly property string controlCenterStatus: controlCenterCompatible ? boundedText(controlCenterClient.status, 32) : "unavailable"
    readonly property bool controlCenterAvailable: controlCenterCompatible && controlCenterClient.available === true
        && controlCenterStatus === "ready" && controlCenterHost !== null
        && controlCenterHost.Window.window === root.Window.window && root.Window.window !== null
    readonly property bool controlCenterIsOpen: controlCenterCompatible && controlCenterClient.isOpen === true
    readonly property string controlCenterError: controlCenterCompatible ? boundedText(controlCenterClient.error, 240)
        : controlCenterClient ? qsTr("A Central de Controle instalada é incompatível.")
        : boundedText(controlCenterLoadError, 240) || qsTr("Central de Controle indisponível. Ative uma única Orla Dock.")
    readonly property string controlCenterDescription: controlCenterError || (controlCenterAvailable
        ? qsTr("Central de Controle") : qsTr("Central de Controle indisponível. Ative uma única Orla Dock."))
    onShowOrlaMenuChanged: if (!showOrlaMenu) {
        menu.restoreFocus = false;
        menu.close();
        about.close();
    }
    onShowControlCenterChanged: releaseControlCenter()
    onControlCenterClientChanged: releaseControlCenter()
    onControlCenterAvailableChanged: if (!controlCenterAvailable) releaseControlCenter()
    onControlCenterHostChanged: releaseControlCenter()
    Component.onDestruction: releaseControlCenter()
    property bool showApplicationName: true
    property bool showMenuLabel: true
    property bool compactHeight: false
    property string menuLabel: "Orla"
    property string menuIcon: "orla"
    readonly property bool nativeSessionLoaded: actions.nativeLoaded
    readonly property bool nativeApplicationLoaded: nativeApplication.item !== null
    readonly property string sessionStatus: actions.status
    readonly property string actionError: actions.error || recent.error
    readonly property bool nativeRecentApplicationsLoaded: recent.nativeLoaded
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
    implicitHeight: compactHeight ? Style.size.iconButton : Style.space.xxxl
    readonly property real minimumControlHeight: Style.space.xxl
    // Panel margins can allocate less than our preferred height.
    readonly property real controlHeight: Math.min(root.implicitHeight, Math.max(0, root.height))

    SessionActions {
        id: actions
        backend: root.sessionBackend
        hostVersion: root.showOrlaMenu || root.showApplicationName ? root.hostVersion : ""
    }
    RecentApplications {
        id: recent
        backend: root.recentApplicationsBackend
        hostVersion: root.hostVersion
        wanted: root.showOrlaMenu
    }
    Loader {
        id: nativeApplication
        active: root.showApplicationName && root.applicationBackend === null && actions.supportedHost
        source: active ? "NativeApplication.qml" : ""
    }
    function boundedText(value, maximum) {
        return String(value || "").slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function releaseControlCenter() {
        controlCenterGeneration += 1;
        // A client callback may invalidate an opening before it returns acceptance.
        // Keep the exact typed lease until the outer dispatch can cancel it.
        if (controlCenterDispatchActive) return false;
        const client = leasedControlCenterClient;
        leasedControlCenterClient = null;
        if (!client) return true;
        controlCenterDispatchActive = true;
        try {
            client.release();
            return true;
        } catch (_) {
            return false;
        } finally {
            controlCenterDispatchActive = false;
        }
    }
    function toggleControlCenter() {
        if (controlCenterDispatchActive || !showControlCenter || !controlCenterAvailable) return false;
        const client = controlCenterClient;
        const host = controlCenterHost;
        const window = root.Window.window;
        leasedControlCenterClient = client;
        if (controlCenterIsOpen) return releaseControlCenter();
        const generation = ++controlCenterGeneration;
        controlCenterDispatchActive = true;
        try {
            let accepted = false;
            try { accepted = client.open(host, controlCenterButton) === true; }
            catch (_) { accepted = false; }
            const current = accepted && leasedControlCenterClient === client
                && generation === controlCenterGeneration && showControlCenter && controlCenterAvailable
                && controlCenterClient === client && controlCenterHost === host && root.Window.window === window;
            if (!current) {
                const pending = leasedControlCenterClient;
                leasedControlCenterClient = null;
                if (pending) {
                    try { pending.release(); }
                    catch (_) { /* The rejected dispatch must never adopt another client's lease. */ }
                }
            }
            return current;
        } finally {
            controlCenterDispatchActive = false;
        }
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
        if (["system", "settings", "configure", "forceQuit"].indexOf(kind) < 0) return false;
        openRequested(kind);
        return true;
    }
    // By ID, never by row: the list reorders as soon as another app starts.
    function launchRecent(slot) {
        const item = recent.items[slot];
        if (!item) return false;
        menu.restoreFocus = false;
        menu.close();
        const launched = recent.launch(item.id);
        if (!launched) menuButton.forceActiveFocus(Qt.PopupFocusReason);
        return launched;
    }
    RowLayout {
        id: row
        anchors.fill: parent
        spacing: root.compactHeight ? Style.space.sm : Style.space.md
        Templates.ToolButton {
            id: menuButton
            objectName: "orlaMenuButton"
            visible: root.showOrlaMenu
            text: root.boundedText(root.menuLabel, 32) || "Orla"
            icon.source: root.menuIcon === "none" ? "" : Qt.resolvedUrl("../images/orla.svg")
            readonly property bool wantsLabel: root.showMenuLabel || root.menuIcon === "none"
            implicitWidth: Math.max(32, (menuGlyph.visible ? 20 : 0)
                + (wantsLabel ? Math.ceil(Math.min(120, menuLabelText.implicitWidth)) + (menuGlyph.visible ? 6 : 0) : 0)
                + leftPadding + rightPadding)
            implicitHeight: root.implicitHeight
            padding: Style.space.xs + Style.space.xxs
            topPadding: Math.min(padding, Math.max(0, (root.controlHeight - Style.size.iconMd) / 2))
            bottomPadding: topPadding
            focusPolicy: Qt.StrongFocus
            hoverEnabled: true
            Layout.minimumWidth: 32
            Layout.maximumWidth: Math.min(implicitWidth, Math.max(32, root.width))
            Layout.preferredHeight: root.controlHeight
            Layout.maximumHeight: root.controlHeight
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
                // Monochrome Orla mark in the text color, like a menu bar glyph:
                // the sun arc over the horizon line.
                Canvas {
                    id: menuGlyph
                    objectName: "orlaMenuIcon"
                    readonly property color ink: menuButton.palette.buttonText
                    visible: menuButton.icon.source.toString() !== ""
                    Layout.preferredWidth: Style.size.iconMd; Layout.preferredHeight: Style.size.iconMd
                    Layout.minimumWidth: Style.size.iconMd; Layout.maximumWidth: Style.size.iconMd
                    Layout.minimumHeight: Style.size.iconMd; Layout.maximumHeight: Style.size.iconMd
                    onInkChanged: requestPaint()
                    onPaint: {
                        const context = getContext("2d");
                        context.reset();
                        const unit = width / 20;
                        context.strokeStyle = ink;
                        context.fillStyle = ink;
                        context.lineCap = "round";
                        context.lineWidth = 1.8 * unit;
                        context.beginPath();
                        context.arc(10 * unit, 13 * unit, 6 * unit, Math.PI, 2 * Math.PI);
                        context.stroke();
                        context.beginPath();
                        context.moveTo(2.5 * unit, 15.5 * unit);
                        context.lineTo(17.5 * unit, 15.5 * unit);
                        context.stroke();
                        context.beginPath();
                        context.arc(10 * unit, 9.5 * unit, 1.3 * unit, 0, 2 * Math.PI);
                        context.fill();
                    }
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
                radius: Style.radius.control
                color: Style.alpha(menuButton.palette.windowText, menuButton.down || root.menuIsOpen
                    ? Style.state.pressed : menuButton.hovered ? Style.state.hover : 0)
                border.width: menuButton.visualFocus ? 2 : 0
                border.color: menuButton.palette.highlight
                visible: menuButton.down || menuButton.hovered || menuButton.visualFocus || root.menuIsOpen
                Behavior on color { ColorAnimation { duration: Style.motion.fast } }
            }
        }
        Templates.ToolButton {
            id: controlCenterButton
            objectName: "barControlCenterButton"
            visible: root.showControlCenter
            enabled: root.controlCenterAvailable
            text: qsTr("Central de Controle")
            palette: menuButton.palette
            implicitWidth: Style.size.iconButton + Style.space.xs
            implicitHeight: root.implicitHeight
            padding: Style.space.xs
            topPadding: Math.min(padding, Math.max(0, (root.controlHeight - Style.size.iconMd) / 2))
            bottomPadding: topPadding
            focusPolicy: Qt.StrongFocus
            hoverEnabled: true
            Layout.preferredWidth: implicitWidth
            Layout.preferredHeight: root.controlHeight
            Layout.maximumHeight: root.controlHeight
            Layout.alignment: Qt.AlignVCenter
            Accessible.name: text
            Accessible.description: root.controlCenterDescription
            Accessible.role: Accessible.Button
            onPressed: if (root.controlCenterTooltipBackend) root.controlCenterTooltipBackend.hideImmediately()
            onClicked: root.toggleControlCenter()
            Controls.ToolTip {
                id: controlCenterTooltip
                objectName: "barControlCenterTooltip"
                visible: controlCenterButton.hovered && !root.controlCenterTooltipBackend
                text: root.controlCenterDescription
                width: Math.min(Style.size.popupWidth, implicitWidth)
                contentItem: Text {
                    objectName: "barControlCenterTooltipText"
                    text: controlCenterTooltip.text
                    textFormat: Text.PlainText
                    font: controlCenterTooltip.font
                    color: controlCenterTooltip.palette.windowText
                    wrapMode: Text.WordWrap
                }
            }
            contentItem: Canvas {
                objectName: "barControlCenterIcon"
                readonly property color ink: controlCenterButton.palette.windowText
                readonly property bool available: root.controlCenterAvailable
                onInkChanged: requestPaint()
                onAvailableChanged: requestPaint()
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                onPaint: {
                    const context = getContext("2d");
                    context.reset();
                    const size = Math.min(width, height);
                    const unit = size / Style.space.xxl;
                    const left = (width - size) / 2;
                    const top = (height - size) / 2;
                    context.strokeStyle = ink;
                    context.fillStyle = ink;
                    context.lineCap = "round";
                    context.lineWidth = Style.space.xxs * unit;
                    // Two opposing sliders, kept monochrome like the menu mark.
                    [Style.space.sm, Style.space.lg].forEach((rowY, index) => {
                        context.beginPath();
                        const half = (Style.space.xs + Style.space.xxs) / 2;
                        const start = left + (Style.space.xs + half) * unit;
                        const end = left + (Style.space.xl - half) * unit;
                        const center = top + rowY * unit;
                        context.moveTo(start, center - half * unit);
                        context.lineTo(end, center - half * unit);
                        context.arc(end, center, half * unit, -Math.PI / 2, Math.PI / 2);
                        context.lineTo(start, center + half * unit);
                        context.arc(start, center, half * unit, Math.PI / 2, 3 * Math.PI / 2);
                        context.closePath();
                        context.stroke();
                        context.beginPath();
                        context.arc(left + (index ? Style.space.lg : Style.space.sm) * unit,
                            top + rowY * unit, Style.space.xxs * unit, 0, 2 * Math.PI);
                        context.fill();
                    });
                    if (!available) {
                        context.beginPath();
                        context.moveTo(left + Style.space.xs * unit, top + Style.space.xl * unit);
                        context.lineTo(left + Style.space.xl * unit, top + Style.space.xs * unit);
                        context.stroke();
                    }
                }
            }
            background: Rectangle {
                radius: Style.radius.control
                color: Style.alpha(controlCenterButton.palette.windowText,
                    controlCenterButton.down || root.controlCenterIsOpen ? Style.state.pressed
                    : controlCenterButton.hovered ? Style.state.hover : 0)
                border.width: controlCenterButton.visualFocus ? Style.space.xxs : 0
                border.color: controlCenterButton.palette.highlight
                visible: controlCenterButton.down || controlCenterButton.hovered
                    || controlCenterButton.visualFocus || root.controlCenterIsOpen
                Behavior on color { ColorAnimation { objectName: "barControlCenterHoverAnimation"; duration: Style.duration(Style.motion.fast, root.reducedMotion) } }
            }
        }
        Controls.ToolButton {
            objectName: "sessionActionError"
            visible: root.showOrlaMenu && root.actionError !== ""
            text: qsTr("Falha na ação")
            Accessible.description: root.actionError
            topPadding: Math.min(padding, Math.max(0, (root.controlHeight - implicitContentHeight) / 2))
            bottomPadding: topPadding
            Layout.preferredHeight: root.controlHeight
            Layout.maximumHeight: root.controlHeight
            Layout.alignment: Qt.AlignVCenter
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
        // App icons keep their own colors; only a theme name is accepted.
        property string iconName: ""
        implicitWidth: 248
        implicitHeight: Style.size.control - Style.space.sm - Style.space.xxs
        height: visible ? implicitHeight : 0
        padding: Style.space.xs
        leftPadding: Style.space.md - Style.space.xxs
        rightPadding: Style.space.md - Style.space.xxs
        font: menuButton.font
        contentItem: RowLayout {
            spacing: Style.space.sm
            ControlsImpl.IconImage {
                visible: entry.iconName !== ""
                name: entry.iconName
                sourceSize.width: Style.size.iconSm
                sourceSize.height: Style.size.iconSm
                Layout.preferredWidth: Style.size.iconSm
                Layout.preferredHeight: Style.size.iconSm
            }
            Text {
                text: entry.text
                textFormat: Text.PlainText
                font: entry.font
                color: entry.enabled ? (entry.highlighted ? entry.palette.highlightedText : entry.palette.windowText)
                    : entry.palette.disabled.windowText
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
                Layout.fillWidth: true
            }
        }
        background: Rectangle {
            radius: Style.radius.sm
            color: entry.palette.highlight
            visible: entry.enabled && (entry.highlighted || entry.down)
        }
    }
    component OrlaMenuSeparator: Templates.MenuSeparator {
        implicitHeight: 9
        height: visible ? implicitHeight : 0
        padding: 4
        contentItem: Rectangle {
            implicitHeight: 1
            color: Style.alpha(menuButton.palette.windowText, 0.12)
        }
    }
    component RecentMenuItem: OrlaMenuItem {
        required property int slot
        readonly property var app: recent.items[slot] || null
        objectName: "recentApplication" + slot
        visible: app !== null
        text: app ? app.name : ""
        iconName: app ? app.icon : ""
        Accessible.name: app ? qsTr("Abrir %1").arg(app.name) : ""
        onTriggered: root.launchRecent(slot)
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
        width: 248
        padding: Style.space.xs + 1
        spacing: 0
        focus: true
        closePolicy: Controls.Popup.CloseOnEscape | Controls.Popup.CloseOnPressOutside
        background: Rectangle {
            radius: Style.radius.card
            color: menuButton.palette.window
            border.width: 1
            border.color: Style.alpha(menuButton.palette.windowText, 0.14)
        }
        OrlaMenuItem { objectName: "aboutOrla"; text: qsTr("Sobre Orla Desktop"); onTriggered: root.open("about") }
        OrlaMenuItem { objectName: "aboutSystem"; text: qsTr("Sobre o sistema"); onTriggered: root.open("system") }
        OrlaMenuItem { objectName: "systemSettings"; text: qsTr("Configurações do sistema"); onTriggered: root.open("settings") }
        OrlaMenuItem { objectName: "configureBar"; text: qsTr("Configurar barra…"); onTriggered: root.open("configure") }
        OrlaMenuSeparator { visible: recent.items.length > 0 }
        OrlaMenuItem { objectName: "recentHeader"; enabled: false; visible: recent.items.length > 0; text: qsTr("Recentes") }
        RecentMenuItem { slot: 0 }
        RecentMenuItem { slot: 1 }
        RecentMenuItem { slot: 2 }
        RecentMenuItem { slot: 3 }
        RecentMenuItem { slot: 4 }
        OrlaMenuSeparator {}
        OrlaMenuItem { objectName: "forceQuit"; text: qsTr("Forçar encerramento…"); onTriggered: root.open("forceQuit") }
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
        padding: Style.space.xl
        modal: false
        focus: true
        background: Rectangle {
            radius: Style.radius.popup
            color: about.palette.window
            border.width: 1
            border.color: Style.alpha(about.palette.windowText, 0.14)
        }
        contentItem: ColumnLayout {
            spacing: Style.space.md
            RowLayout {
                spacing: Style.space.md
                Image {
                    source: Qt.resolvedUrl("../images/orla.svg")
                    sourceSize.width: Style.size.target + Style.space.sm
                    sourceSize.height: Style.size.target + Style.space.sm
                    Layout.preferredWidth: Style.size.target + Style.space.sm
                    Layout.preferredHeight: Style.size.target + Style.space.sm
                }
                ColumnLayout {
                    spacing: Style.space.xxs
                    Controls.Label { text: qsTr("Orla Desktop"); font.pixelSize: Style.type.title; font.weight: Style.weight.demiBold; textFormat: Text.PlainText }
                    Controls.Label { text: qsTr("Barra experimental · 0.1"); font.pixelSize: Style.type.caption; opacity: 0.72; textFormat: Text.PlainText }
                }
            }
            Controls.Label { text: qsTr("Componentes opcionais para KDE Plasma.\nMenus globais e bandeja usam widgets nativos separados."); textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Controls.Button { text: qsTr("Fechar"); Layout.alignment: Qt.AlignRight; onClicked: about.close() }
        }
        onAboutToShow: if (root.popupHost) root.popupHost.showPopup(about, menuButton)
        onClosed: {
            if (root.popupHost) root.popupHost.hidePopup(about);
            menuButton.forceActiveFocus(Qt.PopupFocusReason);
        }
    }
}
