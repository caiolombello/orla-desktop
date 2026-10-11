import QtQuick
import QtQuick.Controls as Controls
import "../package/contents/ui" as DockUI

Controls.ApplicationWindow {
    width: 440
    height: 640
    visible: true
    QtObject {
        id: config
        objectName: "appearanceConfiguration"
        property string appearanceJSON: ""
        property string theme: "glass"
        property int iconSize: 42
        property bool animations: true
    }
    DockUI.AppearanceState { id: appearance; objectName: "appearanceState"; configuration: config }
    Component { id: stateFactory; DockUI.AppearanceState { objectName: "reloadedAppearance"; configuration: config } }
    function recreateState() { stateFactory.createObject(config); }
    DockUI.AppearanceEditor {
        anchors.fill: parent
        anchors.margins: 20
        appearance: appearance
    }
    Component.onCompleted: appearance.begin()
}
