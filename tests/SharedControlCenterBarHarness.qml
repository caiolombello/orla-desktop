import QtQuick
import QtQuick.Window
import "../bar/contents/ui" as BarUI
import "../package/contents/ui" as DockUI
import "../package/contents/code/Style.js" as Style

Window {
    width: 900
    height: 820
    visible: true
    title: "Orla shared controls fixture"
    property QtObject entryClient: DockUI.ControlCenterEntry { objectName: "sharedControlCenterEntry" }
    Item {
        id: host
        objectName: "sharedControlCenterHost"
        width: parent.width
        height: 32
        property bool nativePopups: false
        property bool popAbove: false
        property var popupScheme: Style.scheme("dark")
        BarUI.BarView {
            objectName: "sharedControlCenterBar"
            anchors.right: parent.right
            width: implicitWidth
            height: parent.height
            showOrlaMenu: false
            showApplicationName: false
            showControlCenter: true
            controlCenterClient: entryClient
            controlCenterHost: host
            hostVersion: "6.7.5"
        }
    }
}
