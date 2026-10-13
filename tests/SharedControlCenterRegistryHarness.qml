import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI
import "../package/contents/controlcenter" as Shared

Window {
    id: fixture
    width: 240
    height: 80
    visible: true
    readonly property QtObject registry: Shared.Registry
    property QtObject ownerA: null
    property QtObject ownerB: null
    readonly property QtObject clientA: firstEntry
    readonly property QtObject clientB: secondEntry
    property alias host: geometryHost
    property alias anchor: entryAnchor
    property alias newAnchor: alternateAnchor
    property alias otherWindow: other
    property alias otherAnchor: foreignAnchor
    readonly property int hardwareFactories: 0
    property bool reentrantAccepted: true
    property int requestsDuringReentry: -1

    Item {
        id: geometryHost
        anchors.fill: parent
        Item { id: entryAnchor; width: 32; height: 32 }
        Item { id: alternateAnchor; width: 32; height: 32; x: 40 }
    }
    Window {
        id: other
        width: 80; height: 80
        visible: true
        Item { id: foreignAnchor; width: 32; height: 32 }
    }
    DockUI.ControlCenterEntry { id: firstEntry; objectName: "clientA" }
    DockUI.ControlCenterEntry { id: secondEntry; objectName: "clientB" }

    Component {
        id: ownerFactory
        QtObject {
            id: owner
            property int requestCount: 0
            property int releaseCount: 0
            property int requestGeneration: 0
            property QtObject pendingClient: null
            property QtObject currentClient: null
            property QtObject lastReleasedClient: null
            property QtObject lastAcceptedClient: null
            property string transactionError: ""
            property Item lastHost: null
            property Item lastAnchor: null
            property var acceptedValue: true
            property var requestHook: null
            property var releaseHook: null
            onReleaseCountChanged: if (releaseHook) releaseHook()
            function requestControlCenter(client, host, anchor) {
                requestCount += 1;
                requestGeneration += 1;
                const generation = requestGeneration;
                pendingClient = client;
                currentClient = null;
                lastHost = host;
                lastAnchor = anchor;
                const requestedOwner = owner;
                Qt.callLater(() => {
                    if (!Qt.isQtObject(requestedOwner) || generation !== requestedOwner.requestGeneration
                            || !requestedOwner.pendingClient || Shared.Registry.owner !== requestedOwner
                            || !requestedOwner.lastHost || !requestedOwner.lastAnchor) return;
                    requestedOwner.currentClient = requestedOwner.pendingClient;
                    requestedOwner.pendingClient = null;
                });
                if (requestHook) requestHook();
                if (acceptedValue === true) lastAcceptedClient = client;
                return acceptedValue;
            }
            function releaseControlCenter(client) {
                releaseCount += 1;
                lastReleasedClient = client;
                if (pendingClient !== client && currentClient !== client) return;
                requestGeneration += 1;
                pendingClient = null;
                currentClient = null;
            }
            function controlCenterVisibleFor(client) {
                return currentClient !== null && currentClient === client;
            }
            function controlCenterErrorFor(client) {
                return client === lastAcceptedClient ? transactionError : "";
            }
        }
    }
    function makeOwner(slot) {
        const value = ownerFactory.createObject(fixture);
        if (slot === "a") ownerA = value;
        else ownerB = value;
        return registry.registerOwner(value, 1);
    }
}
