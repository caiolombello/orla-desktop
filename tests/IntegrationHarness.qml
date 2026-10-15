import QtQuick
import "../package/contents/ui" as DockUI

DockUI.Integrations {
    id: integrations
    objectName: "integrationsUnderTest"
    width: 480
    height: 480
    // dbus_smoke.py passes --inside; ordinary UI tests stay isolated from the session service.
    active: Qt.application.arguments.indexOf("--inside") >= 0
    enabledModules: ["quota"]

    QtObject {
        id: dockFixture
        property color muted: "#888888"
        property color foreground: "#f0f0f0"
    }
    DockUI.IntegrationDetails {
        objectName: "peripheralsDetailsUnderTest"
        width: parent.width
        dock: dockFixture
        integrations: integrations
        selected: "peripherals"
    }
}
