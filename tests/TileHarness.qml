import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    width: 240
    height: 120
    visible: true
    DockUI.Tile {
        objectName: "fixtureTile"
        anchors.centerIn: parent
        liveKind: "peripherals"
        live: true
        title: "PeriGauge"
        subtitle: '<img src="https://example.test/probe"> · 64%'
        tooltip: subtitle
    }
}
