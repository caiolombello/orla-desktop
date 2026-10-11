import QtQuick
import QtQuick.Window
import "../bar/contents/ui" as BarUI

Window {
    width: 400
    height: 64
    visible: true
    BarUI.BarView {
        objectName: "barUnderTest"
        anchors.fill: parent
        sessionBackend: fixtureSession
        applicationBackend: fixtureApplication
        hostVersion: "6.7.5"
        onOpenRequested: kind => fixtureSession.open(kind)
    }
}
