import QtQuick
import QtQuick.Controls as Controls
import "../package/contents/ui" as DockUI

Controls.ApplicationWindow {
    width: 350
    height: 420
    visible: true
    QtObject {
        id: bridge
        objectName: "moduleBridge"
        property bool loading: false
        property string error: ""
        readonly property bool legacyLoading: loading
        property bool addonLoading: false
        property string addonError: ""
        function errorFor(module) { return module === "peripherals" ? addonError : error; }
        property var quota: ({status: "ready"})
        property var peripherals: ({status: "missing"})
        property var recording: ({status: "unknown"})
        property string recordingSummary: "Estado salvo · gravando"
        property int refreshRequests: 0
        function refresh() { refreshRequests++; }
    }
    Item {
        objectName: "moduleHost"
        anchors.fill: parent
        DockUI.LocalModuleDetails {
            objectName: "moduleUnderTest"
            width: parent.width
            widgetId: "quota"
            shown: false
            integrations: bridge
        }
    }
}
