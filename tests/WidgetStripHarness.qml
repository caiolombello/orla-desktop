import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    id: root
    width: 1200
    height: 120
    visible: true
    color: "#111827"
    property var openCalls: []
    property var widgets: [
        {id: "clock", visible: true},
        {id: "pomodoro", visible: true},
        {id: "music", visible: true},
        {id: "systemBattery", visible: true},
        {id: "quota", visible: true},
        {id: "peripherals", visible: true},
        {id: "recording", visible: true}
    ]
    QtObject {
        id: appearance
        readonly property var effective: ({tokens: {spacing: 6}})
    }
    QtObject {
        id: pomodoro
        property bool running: false
        property int secondsLeft: 1500
    }
    QtObject {
        id: configuration
        property bool timerBreak: false
    }
    QtObject {
        id: battery
        objectName: "fixtureBattery"
        property string status: "unavailable"
        property bool percentKnown: false
        property real percent: -1
        property string charging: "unknown"
    }
    DockUI.IntegrationState {
        id: integrations
        objectName: "fixtureIntegrations"
        active: true
        enabledModules: ["quota", "peripherals", "recording"]
        nowMsOverride: 100000
        transport: fixtureTransport
    }
    QtObject {
        id: fixtureTransport
        property var queue: []
        function asyncCall(message, resolve, reject) { queue = queue.concat([{message: message, resolve: resolve, reject: reject}]); }
        function replyAddons(raw, failed) {
            const waiting = queue.filter(call => call.message.service === "org.orla.Addons");
            queue = queue.filter(call => call.message.service !== "org.orla.Addons");
            for (const call of waiting) {
                if (failed) call.reject({});
                else call.resolve({value: raw});
            }
        }
    }
    QtObject {
        id: dock
        objectName: "fixtureDock"
        property var appearance: appearance
        property var presentation: ({widgets: root.widgets})
        property date now: new Date(2026, 9, 11, 9, 29)
        property var pomodoro: pomodoro
        property var configuration: configuration
        property var player: null
        property var systemBattery: battery
        property var integrations: integrations
        property int tileSize: 42
        property color foreground: "#edf1f9"
        property color muted: "#9da9bf"
        property color accent: "#8cb7ff"
        property int motion: 0
        property string powerSubtitle: battery.status === "ready" ? "Na tomada" : "Bateria indisponível"
        function mediaText(value, maximum) { return String(value || "").slice(0, maximum); }
        function openWidget(id) { root.openCalls = root.openCalls.concat([id]); return true; }
    }
    DockUI.WidgetStrip {
        id: widgetStrip
        objectName: "widgetStripUnderTest"
        anchors.centerIn: parent
        height: 80
        dock: dock
    }
}
