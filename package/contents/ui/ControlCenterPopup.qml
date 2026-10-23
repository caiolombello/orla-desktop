import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import "../code/Style.js" as Style

DockPopup {
    id: rootPopup
    required property Item owner
    property var actions: null
    property var player: null
    property var battery: null
    property var audio: null
    property var brightness: null
    property var doNotDisturb: null
    property var microphone: null
    property var powerProfile: null
    property QtObject backendLifetime: null
    property bool playing: false
    property var validateClient: function(client) { return false; }
    readonly property alias host: session.host
    readonly property Item geometryHost: host || owner
    readonly property alias entryClient: session.client
    readonly property alias contents: center
    readonly property bool dockOrigin: session.dockOrigin
    readonly property bool contextSwitchBusy: interactionBusy || session.interactionBusy
    readonly property real screenWidth: geometryHost && geometryHost.Screen.width > 0
        ? (geometryHost.Screen.desktopAvailableWidth > 0 ? Math.min(geometryHost.Screen.width, geometryHost.Screen.desktopAvailableWidth) : geometryHost.Screen.width)
        : geometryHost ? geometryHost.Screen.desktopAvailableWidth : 0
    property real widthBudget: screenWidth > 0 ? Math.max(1, screenWidth - 40) : Style.size.popupWidth
    property real heightBudget: maximumPopupHeight
    width: Math.max(1, Math.min(Style.size.popupWidth + 2 * shadowMargin, widthBudget))
    height: Math.max(1, Math.min(implicitHeight, heightBudget))
    dock: geometryHost
    title: qsTr("Central de Controle")

    function openAt(anchor) { return openFromDock(anchor); }
    function openFromDock(anchor) { return session.openFromDock(anchor); }
    function openFromClient(client, host, anchor) { return session.openFromClient(client, host, anchor); }
    function releaseClient(client) { return session.releaseClient(client); }
    function closeDockOrigin() { return session.closeDockOrigin(); }
    function closeSession() { session.close(); }
    function shutdown() { session.shutdown(); }
    function visibleFor(client) { return session.visibleFor(client); }
    function errorFor(client) { return session.errorFor(client); }

    ControlCenterSession {
        id: session
        owner: rootPopup.owner
        popup: rootPopup
        audio: rootPopup.audio
        backendLifetime: rootPopup.backendLifetime
        validateClient: rootPopup.validateClient
        performOpen: function(host, anchor) {
            if (rootPopup.nativeBackend && !rootPopup.nativeDialog) return false;
            rootPopup.anchorControl = anchor;
            rootPopup.anchorX = anchor.mapToItem(host, anchor.width / 2, 0).x;
            rootPopup.open();
            return rootPopup.visible;
        }
    }
    ControlCenter {
        id: center
        objectName: "controlCenterContents"
        Layout.fillWidth: true
        actions: rootPopup.actions
        player: rootPopup.player
        battery: rootPopup.battery
        playing: rootPopup.playing
        audio: rootPopup.audio
        brightness: rootPopup.brightness
        doNotDisturb: rootPopup.doNotDisturb
        microphone: rootPopup.microphone
        powerProfile: rootPopup.powerProfile
        foreground: rootPopup.scheme.text
        muted: rootPopup.scheme.textMuted
    }
}
