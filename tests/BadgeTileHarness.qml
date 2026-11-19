import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    width: 240
    height: 120
    visible: true
    DockUI.Tile { objectName: "plain"; x: 10; y: 10; title: "Correio"; iconSource: "mail-message" }
    DockUI.Tile { objectName: "badged"; x: 110; y: 10; title: "Correio"; iconSource: "mail-message"; badgeCount: 3 }
}
