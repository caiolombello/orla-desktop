import QtQuick
import "../package/contents/ui" as DockUI
import "../package/contents/code/Style.js" as Style

DockUI.IntegrationState {
    id: integrations
    objectName: "integrationsUnderTest"
    width: 480
    height: 480
    property string schemeName: "dark"
    readonly property var ui: Style.scheme(schemeName)
    readonly property bool inside: Qt.application.arguments.indexOf("--inside") >= 0
    active: inside
    enabledModules: ["quota"]
    nowMsOverride: inside ? -1 : 100000
    transport: inside && nativeTransport.item ? nativeTransport.item.transport : fixtureTransport

    // Only Root's --inside smoke loads the native transport; portable tests have no KDE imports.
    Loader { id: nativeTransport; active: integrations.inside; source: active ? "../package/contents/ui/Integrations.qml" : "" }
    QtObject {
        id: fixtureTransport
        objectName: "fixtureTransport"
        property var queue: []
        property var messages: []
        function asyncCall(message, resolve, reject) {
            messages = messages.concat([message]);
            queue = queue.concat([{resolve: resolve, reject: reject}]);
        }
        function reply(text) {
            const next = queue[0];
            queue = queue.slice(1);
            next.resolve({value: text});
        }
    }
    QtObject {
        id: dockFixture
        property color muted: integrations.ui.textMuted
        property color foreground: integrations.ui.text
    }
    DockUI.IntegrationDetails {
        objectName: "peripheralsDetailsUnderTest"
        width: parent.width
        dock: dockFixture
        integrations: integrations
        selected: "peripherals"
    }
}
