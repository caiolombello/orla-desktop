import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    id: window
    width: 320
    height: 240
    visible: true

    property alias backend: fixtureBackend
    property alias audio: audioState

    QtObject {
        id: fixtureBackend
        objectName: "audioBackend"
        property int revision: 0
        property var snapshot: ({
            status: "ready",
            normalVolume: 65536,
            defaultOutputId: "speakers",
            outputs: [
                {id: "speakers", label: "Alto-falantes", volumeRaw: 32768, muted: false, writable: true, isDefault: true},
                {id: "headphones", label: "Fones", volumeRaw: 16384, muted: true, writable: true, isDefault: false}
            ]
        })
        property var calls: []
        property bool rejectWrites: false

        function publish(value) { snapshot = value; revision += 1; }
        function setVolume(id, raw) {
            calls = calls.concat([{kind: "volume", id: id, value: raw}]);
            return !rejectWrites;
        }
        function setMuted(id, value) {
            calls = calls.concat([{kind: "mute", id: id, value: value}]);
            return !rejectWrites;
        }
        function setDefaultOutput(id) {
            calls = calls.concat([{kind: "default-output", id: id}]);
            return !rejectWrites;
        }
        function retry() {
            calls = calls.concat([{kind: "retry"}]);
            return !rejectWrites;
        }
    }

    DockUI.AudioControlState {
        id: audioState
        objectName: "audioState"
        active: true
        backend: fixtureBackend
    }
}
