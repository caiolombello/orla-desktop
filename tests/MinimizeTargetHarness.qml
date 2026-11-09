import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI
import "../package/contents/code/MinimizeTarget.js" as Geometry

// A dock-shaped fixture: a clipped lane with a tile whose artwork lifts,
// scales and bounces like Tile.qml, and a recorder standing in for TasksModel.
Window {
    id: harness
    width: 400
    height: 120
    visible: true
    property alias target: minimizeTarget
    property alias tile: tileItem
    property alias artwork: artworkBox
    property alias lane: laneItem
    property var calls: []
    property bool rowActive: true
    property string rowWindows: "w1"
    property bool lifted: false
    property real bounce: 0
    function geometry() { return Geometry; }

    QtObject {
        id: recorder
        objectName: "recorder"
        function makeModelIndex(row) { return {row: row}; }
        function requestPublishDelegateGeometry(index, rect, delegate) {
            harness.calls = harness.calls.concat([{row: index.row, x: rect.x, y: rect.y,
                width: rect.width, height: rect.height, delegate: delegate}]);
        }
    }
    Item {
        id: laneItem
        x: 30
        y: 10
        width: 200
        height: 100
        clip: true
        Item {
            id: tileItem
            x: 40
            width: 58
            height: 58
            y: 20
            Item {
                id: contentBox
                anchors.fill: parent
                Item {
                    id: artworkBox
                    width: 46
                    height: 46
                    x: 6
                    y: 4
                    scale: harness.lifted ? 1.1 : 1
                    transformOrigin: Item.Bottom
                    transform: [Translate { y: harness.lifted ? -6 : 0 }, Translate { y: harness.bounce }]
                }
            }
            DockUI.MinimizeTarget {
                id: minimizeTarget
                objectName: "minimizeTarget"
                publisher: recorder
                row: 3
                active: harness.rowActive
                windows: harness.rowWindows
                artwork: artworkBox
                bounds: laneItem
            }
        }
    }
}
