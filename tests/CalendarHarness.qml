import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    width: 420
    height: 680
    visible: true
    color: "#18202e"
    QtObject {
        id: config
        property bool calendarEvents: false
    }
    QtObject {
        id: dock
        property var configuration: config
        property color foreground: "#edf1f9"
        property color muted: "#9da9bf"
    }
    DockUI.CalendarAgenda {
        objectName: "calendarUnderTest"
        anchors.fill: parent
        anchors.margins: 16
        dock: dock
        fixtureEvents: []
    }
}
