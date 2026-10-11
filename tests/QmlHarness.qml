import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
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
        property int iconSize: 42
        property bool animations: false
        property bool showClock: true
        property bool showMusic: true
        property bool showSystemBattery: false
        property bool showPomodoro: true
        property bool showQuota: false
        property bool showPeripherals: false
        property bool showRecording: false
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
    }
}
