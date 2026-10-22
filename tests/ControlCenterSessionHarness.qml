import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

// Only the external popup boundary is synthetic. Audio and item lifetimes are real Qt.
Window {
    id: fixture
    width: 480
    height: 320
    visible: true
    property Item ownerItem: null
    property Item siblingHost: null
    property Item barHost: null
    property Item barAnchor: null
    property QtObject firstClient: null
    property QtObject secondClient: null
    readonly property var session: ownerItem ? ownerItem.session : null
    property var receipts: []
    property var openedHosts: []
    property bool clientsValid: true
    property QtObject backendLifetimeFixture: null
    property alias popup: boundary
    property alias audio: audioState
    property alias backend: audioBackend
    property alias barWindow: secondaryWindow

    Window { id: secondaryWindow; width: 400; height: 240; visible: true }
    Component { id: itemFactory; Item { width: 160; height: 40; focus: true } }
    Component { id: clientFactory; QtObject {} }
    Component {
        id: ownerFactory
        Item {
            id: ownerRoot
            width: 300
            height: 50
            property alias session: state
            property alias anchor: dockAnchor
            Item { id: dockAnchor; width: 40; height: 40; focus: true }
            DockUI.ControlCenterSession {
                id: state
                objectName: "controlCenterSession"
                owner: ownerRoot
                popup: boundary
                audio: audioState
                backendLifetime: fixture.backendLifetimeFixture
                validateClient: candidate => fixture.clientsValid && (candidate === fixture.firstClient || candidate === fixture.secondClient)
                performOpen: (host, anchor) => {
                    boundary.anchorControl = anchor;
                    fixture.openedHosts = fixture.openedHosts.concat([host === ownerRoot ? "dock" : "bar"]);
                    boundary.open();
                }
            }
        }
    }
    Item {
        id: boundary
        objectName: "sessionPopupBoundary"
        focus: true
        Keys.onEscapePressed: event => { dismiss(); event.accepted = true; }
        visible: false
        property Item anchorControl: null
        property Item capturedAnchorAfterClosed: null
        property bool asynchronousClose: false
        property bool holdNativeVisible: false
        property bool closing: false
        property int closeCount: 0
        property string pendingAtClose: ""
        property bool gestureAtClose: false
        property alias nativeDialog: nativeBoundary
        signal aboutToHide()
        signal closed()
        QtObject { id: nativeBoundary; property bool visible: false; property bool active: false }
        function open() { closing = false; nativeBoundary.visible = true; visible = true; }
        function close() {
            if (!visible || closing) return;
            pendingAtClose = audioState.pendingKind;
            gestureAtClose = audioState.volumeGestureActive;
            closing = true;
            closeCount++;
            aboutToHide();
            if (!asynchronousClose) finishClose();
        }
        function dismiss() { close(); }
        function finishClose() {
            visible = false;
            closing = false;
            closed();
            // Models the unchanged DockPopup ordering, never native window behavior.
            capturedAnchorAfterClosed = anchorControl;
            if (!holdNativeVisible) nativeBoundary.visible = false;
        }
        function finishNativeHide() { nativeBoundary.visible = false; }
    }
    QtObject {
        id: audioBackend
        objectName: "sessionAudioBackend"
        property int revision: 0
        property var calls: []
        property var snapshot: ({status: "ready", normalVolume: 65536, defaultOutputId: "speakers", outputs: [
            {id: "speakers", label: "Alto-falantes", volumeRaw: 32768, muted: false, writable: true, isDefault: true},
            {id: "headphones", label: "Fones", volumeRaw: 16384, muted: false, writable: true, isDefault: false}
        ]})
        function publish(raw, muted, target) {
            snapshot = {status: "ready", normalVolume: 65536, defaultOutputId: target || "speakers", outputs: [
                {id: "speakers", label: "Alto-falantes", volumeRaw: raw, muted: Boolean(muted), writable: true, isDefault: target !== "headphones"},
                {id: "headphones", label: "Fones", volumeRaw: 16384, muted: false, writable: true, isDefault: target === "headphones"}
            ]};
            revision++;
        }
        function setVolume(id, raw) { calls = calls.concat([{kind: "volume", id: id, value: raw}]); return true; }
        function setMuted(id, value) { calls = calls.concat([{kind: "mute", id: id, value: value}]); return true; }
        function setDefaultOutput(id) { calls = calls.concat([{kind: "output", id: id}]); return true; }
    }
    DockUI.AudioControlState {
        id: audioState
        objectName: "sessionAudioState"
        active: boundary.visible
        backend: audioBackend
        requestOriginScope: "profile:fixture"
        requestContextGeneration: 1
        onConfirmed: receipt => fixture.receipts = fixture.receipts.concat([receipt])
    }
    Component.onCompleted: {
        ownerItem = ownerFactory.createObject(fixture.contentItem);
        siblingHost = itemFactory.createObject(fixture.contentItem);
        barHost = itemFactory.createObject(secondaryWindow.contentItem);
        barAnchor = itemFactory.createObject(barHost);
        firstClient = clientFactory.createObject(fixture);
        secondClient = clientFactory.createObject(fixture);
    }
}
