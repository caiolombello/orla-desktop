import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    width: 420
    height: 120
    visible: true
    color: "#2b3440"

    DockUI.EventState {
        id: state
        objectName: "islandEventState"
        activeScope: "profile:work"
        activeContextGeneration: 2
    }

    DockUI.EventIsland {
        id: island
        x: (parent.width - width) / 2
        y: 4
        width: implicitWidth
        height: implicitHeight
        eventState: state
        reducedMotion: true
    }
}
