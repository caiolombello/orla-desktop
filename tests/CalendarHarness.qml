import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    width: 420
    height: 680
    visible: true
    color: dock.background
    QtObject {
        id: config
        property bool calendarEvents: false
    }
    QtObject {
        id: dock
        property var configuration: config
        property color foreground: "#edf1f9"
        property color muted: "#9da9bf"
        property color background: "#18202e"
        property color accent: "#54b8f3"
    }
    DockUI.CalendarAgenda {
        objectName: "calendarUnderTest"
        anchors.fill: parent
        anchors.margins: 16
        dock: dock
        active: true
        fixtureEvents: []
        pimPluginMetadataAvailableOverride: true
    }
}
