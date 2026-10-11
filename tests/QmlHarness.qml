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
    DockUI.DockView {
        id: dockView
        anchors.centerIn: parent
        width: Math.min(implicitWidth, parent.width - 64)
        height: implicitHeight
        configuration: config
    }
}
