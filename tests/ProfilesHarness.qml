import QtQuick
import "../package/contents/ui" as DockUI
import "../package/contents/code/Profiles.js" as Profiles

Item {
    id: harness
    QtObject {
        id: config
        objectName: "profilesConfiguration"
        property string profilesJSON: ""
        property var launchers: ["applications:org.kde.dolphin.desktop", "applications:org.kde.konsole.desktop"]
        property string theme: "glass"
        property string appearanceJSON: ""
        property int iconSize: 42
        property bool animations: true
        property bool showClock: true
        property bool showMusic: true
        property bool showSystemBattery: false
        property bool showPomodoro: true
        property bool showQuota: true
        property bool showPeripherals: true
        property bool showRecording: true
        property bool showAudioHud: false
        property bool calendarEvents: true
        property bool currentDesktopOnly: false
        property int focusMinutes: 25
        property int breakMinutes: 5
        property double timerDeadline: 1234567890000
        property int timerRemaining: 731
        property bool timerBreak: true
        property int completedFocus: 3
    }
    DockUI.ProfileState { id: state; objectName: "profileState"; configuration: config }
    Component { id: factory; DockUI.ProfileState { objectName: "reloadedProfiles"; configuration: config } }
    function recreateState() { factory.createObject(harness); }
    function parse(raw) { return Profiles.parse(raw); }
}
