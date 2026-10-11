import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    property string fixtureProfilesJSON: ""
    property string fixtureContextsJSON: ""
    property int contextWriteCount: 0
    property var contextTimerWitness: dockView.pomodoro
    readonly property bool contextTimerIdentity: contextTimerWitness === dockView.pomodoro
    property var contextSnapshot: ({
        outputName: "DP-1",
        activity: {status: "ready", currentId: "activity-work", ids: ["activity-work"], names: ["Foco"]},
        desktop: {status: "ready", currentId: "desktop-1", ids: ["desktop-1"], names: ["Área 1"]}
    })
    width: Math.max(740, dockView.implicitWidth + 64)
    height: 220
    visible: true
    color: "#111827"
    title: "CaioDock interface test"
    QtObject {
        id: config
        objectName: "configuration"
        property var launchers: ["applications:org.kde.dolphin.desktop", "applications:org.kde.konsole.desktop"]
        property string theme: "glass"
        property string appearanceJSON: ""
        property string profilesJSON: fixtureProfilesJSON
        property string contextsJSON: fixtureContextsJSON
        onContextsJSONChanged: contextWriteCount++
        property int iconSize: 42
        property bool animations: false
        property bool showClock: true
        property bool showMusic: true
        property bool showSystemBattery: false
        property bool showPomodoro: true
        property bool showQuota: false
        property bool showPeripherals: false
        property bool showRecording: false
        property bool showLocalToasts: false
        property bool showAudioHud: false
        property bool showControlCenter: false
        property bool calendarEvents: false
        property bool currentDesktopOnly: false
        property int focusMinutes: 25
        property int breakMinutes: 5
        property double timerDeadline: 0
        property int timerRemaining: 1500
        property bool timerBreak: false
        property int completedFocus: 0
    }
    QtObject {
        id: ownedBatteryTransport
        objectName: "batteryTransport"
        property bool fail: false
        property var calls: []
        function asyncCall(message, resolve, reject) {
            calls = calls.concat([message]);
            if (fail) { reject({}); return; }
            if (message.member === "GetDisplayDevice")
                resolve({value: "/org/freedesktop/UPower/devices/DisplayDevice"});
            else if (message.member === "GetAll")
                resolve({value: {IsPresent: true, Type: 2, Percentage: 0, State: 2, TimeToEmpty: 900}});
            else resolve({value: true});
        }
    }
    QtObject {
        id: fixturePlayer
        property string track: "<b>" + "A".repeat(1000) + "</b>"
        property string artist: "<i>" + "B".repeat(1000) + "</i>"
        property string identity: "Owned metadata fixture"
        property string iconName: "audio-x-generic"
        property int playbackStatus: 0
        property bool canControl: false
        property bool canPlay: false
        property bool canPause: false
        property bool canGoPrevious: false
        property bool canGoNext: false
    }
    QtObject {
        id: controlCenterBackend
        objectName: "dockControlCenterBackend"
        property var calls: []
        function openSystemSettings(target) { calls = calls.concat([target]); }
    }
    QtObject {
        id: audioBackend
        objectName: "dockAudioBackend"
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
    ListModel {
        objectName: "fixtureMedia"
        property var currentPlayer: fixturePlayer
        property int currentIndex: -1
    }
    DockUI.DockView {
        id: dockView
        anchors.centerIn: parent
        width: Math.min(implicitWidth, parent.width - 64)
        height: implicitHeight
        configuration: config
        contextSnapshotOverride: contextSnapshot
        controlCenterBackendOverride: controlCenterBackend
        audioBackendOverride: audioBackend
        integrations.active: false
        systemBattery.transport: ownedBatteryTransport
    }
    function findFixtureObject(node, name, seen) {
        if (!node || seen.has(node)) return null;
        seen.add(node);
        if (node.objectName === name) return node;
        const descendants = [];
        if (node.data) descendants.push(...Array.from(node.data));
        if (node.children) descendants.push(...Array.from(node.children));
        if (node.contentItem) descendants.push(node.contentItem);
        for (const child of descendants) {
            const found = findFixtureObject(child, name, seen);
            if (found) return found;
        }
        return null;
    }
    Component.onCompleted: {
        // Initial fixture calendarEvents is false. Set synthetic events before
        // a test may enable calendarEvents; no PIM provider is then requested.
        const agenda = findFixtureObject(dockView, "calendarAgenda", new Set());
        if (agenda) agenda.fixtureEvents = [];
        else throw new Error("Owned calendar fixture was not found");
    }

}
