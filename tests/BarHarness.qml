import QtQuick
import QtQuick.Window
import "../bar/contents/ui" as BarUI

Window {
    width: 400
    height: 64
    visible: true
    BarUI.BarView {
        id: bar
        objectName: "barUnderTest"
        anchors.fill: parent
        controlCenterClient: fixtureControlCenter
        controlCenterHost: bar
        sessionBackend: fixtureSession
        applicationBackend: fixtureApplication
        recentApplicationsBackend: fixtureRecent
        softwareUpdatesBackend: fixtureUpdates
        hostVersion: "6.7.5"
        onOpenRequested: kind => fixtureSession.open(kind)
    }
}
