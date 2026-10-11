import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    id: window
    width: 280
    height: 760
    visible: true
    color: "#111923"

    property alias backend: fixtureBackend
    property alias battery: fixtureBattery
    property alias player: fixturePlayer
    property alias audioBackend: fixtureAudioBackend

    QtObject {
        id: fixtureBackend
        objectName: "controlCenterBackend"
        property var calls: []
        property string failingTarget: "none"
        function openSystemSettings(target) {
            if (target === failingTarget) throw new Error("private fixture failure");
            calls = calls.concat([target]);
        }
    }
    QtObject {
        id: fixtureBattery
        objectName: "controlCenterBattery"
        property string status: "ready"
        property string summary: "0%"
        property string subtitle: "Na bateria"
    }
    QtObject {
        id: fixturePlayer
        objectName: "controlCenterPlayer"
        property string track: "Faixa sintética"
        property string artist: "Artista sintético"
        property string identity: "Player sintético"
    }
    QtObject {
        id: fixtureAudioBackend
        objectName: "controlCenterAudioBackend"
        property int revision: 0
        property var calls: []
        property bool rejectWrites: false
        property var snapshot: ({status: "ready", normalVolume: 65536, defaultOutputId: "speakers", outputs: [
            {id: "speakers", label: "Alto-falantes sintéticos", volumeRaw: 32768, muted: false, writable: true, isDefault: true},
            {id: "headphones", label: "Fones sintéticos", volumeRaw: 16384, muted: false, writable: true, isDefault: false}
        ]})
        function setVolume(id, value) { calls = calls.concat([{kind: "volume", id: id, value: value}]); return !rejectWrites; }
        function setMuted(id, value) { calls = calls.concat([{kind: "mute", id: id, value: value}]); return !rejectWrites; }
        function setDefaultOutput(id) { calls = calls.concat([{kind: "default-output", id: id}]); return !rejectWrites; }
        function retry() { calls = calls.concat([{kind: "retry"}]); return !rejectWrites; }
    }
    DockUI.AudioControlState {
        id: fixtureAudio
        active: true
        backend: fixtureAudioBackend
    }
    DockUI.KdeControlActions {
        id: actions
        objectName: "controlCenterActions"
        backend: fixtureBackend
    }
    DockUI.ControlCenter {
        id: controlCenter
        objectName: "controlCenterUnderTest"
        width: window.width
        height: window.height
        actions: actions
        player: fixturePlayer
        battery: fixtureBattery
        audio: fixtureAudio
    }
}
