import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    width: 350
    height: 360
    visible: true
    color: "#1d2535"
    DockUI.MediaControls {
        objectName: "mediaUnderTest"
        anchors.fill: parent
        anchors.margins: 20
        media: fixtureMedia
        palette.windowText: "#edf1f9"
        palette.text: "#edf1f9"
        palette.buttonText: "#edf1f9"
        palette.button: "#2c3850"
        palette.base: "#20293b"
        palette.highlight: "#91b8ff"
    }
}
