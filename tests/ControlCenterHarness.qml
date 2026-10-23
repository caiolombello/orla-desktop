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
    property alias brightnessBackend: fixtureBrightnessBackend
    property alias brightness: fixtureBrightness
    property alias dndBackend: fixtureDndBackend
    property alias dnd: fixtureDnd
    property alias micBackend: fixtureMicBackend
    property alias mic: fixtureMic
    property alias powerBackend: fixturePowerBackend
    property alias power: fixturePower

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
    QtObject {
        id: fixtureBrightnessBackend
        objectName: "controlCenterBrightnessBackend"
        property var calls: []
        property bool rejectWrites: false
        property bool reportDuringWrite: false
        property var snapshot: ({status: "ready", displays: [
            {id: "display0", label: "Tela sintética", value: 5000, max: 10000, internal: true}]})
        signal writeFailed(string id)
        function setBrightness(id, raw) {
            calls = calls.concat([{id: id, raw: raw}]);
            if (reportDuringWrite) report(id, raw);
            return !rejectWrites;
        }
        // Tests confirm explicitly, like the service's readback would.
        function report(id, raw) {
            snapshot = {status: snapshot.status, displays: snapshot.displays.map(
                display => display.id === id ? Object.assign({}, display, {value: raw}) : display)};
        }
    }
    DockUI.BrightnessControlState {
        id: fixtureBrightness
        objectName: "controlCenterBrightnessState"
        active: true
        confirmationTimeout: 300
        backend: fixtureBrightnessBackend
    }
    QtObject {
        id: fixtureDndBackend
        objectName: "controlCenterDndBackend"
        property var calls: []
        property bool rejectWrites: false
        property var snapshot: ({status: "ready", inhibited: false, until: 0, byApplication: false, applications: []})
        function setDoNotDisturb(on) { calls = calls.concat([on]); return !rejectWrites; }
        // Tests report like Plasma's notification server would.
        function report(changes) { snapshot = Object.assign({}, snapshot, changes); }
    }
    DockUI.DoNotDisturbState {
        id: fixtureDnd
        objectName: "controlCenterDndState"
        active: true
        confirmationTimeout: 300
        backend: fixtureDndBackend
    }
    QtObject {
        id: fixtureMicBackend
        objectName: "controlCenterMicBackend"
        property var calls: []
        property bool rejectWrites: false
        property var snapshot: ({status: "ready", input: {id: "input.synthetic", label: "Microfone sintético", muted: false, writable: true}})
        function setMuted(id, muted) { calls = calls.concat([{id: id, muted: muted}]); return !rejectWrites; }
        // Tests report like the audio service would.
        function report(changes) { snapshot = {status: snapshot.status, input: Object.assign({}, snapshot.input, changes)}; }
    }
    DockUI.MicrophoneState {
        id: fixtureMic
        objectName: "controlCenterMicState"
        active: true
        confirmationTimeout: 300
        backend: fixtureMicBackend
    }
    QtObject {
        id: fixturePowerBackend
        objectName: "controlCenterPowerBackend"
        property var calls: []
        property bool rejectWrites: false
        property var snapshot: ({status: "ready", profiles: ["power-saver", "balanced", "performance"], current: "balanced",
            inhibitedReason: "", degradedReason: "", holds: []})
        signal writeFailed(string id)
        function setProfile(id) { calls = calls.concat([id]); return !rejectWrites; }
        // Tests report like PowerDevil would.
        function report(changes) { snapshot = Object.assign({}, snapshot, changes); }
    }
    DockUI.PowerProfileState {
        id: fixturePower
        objectName: "controlCenterPowerState"
        active: true
        confirmationTimeout: 300
        backend: fixturePowerBackend
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
        brightness: fixtureBrightness
        doNotDisturb: fixtureDnd
        microphone: fixtureMic
        powerProfile: fixturePower
    }
}
