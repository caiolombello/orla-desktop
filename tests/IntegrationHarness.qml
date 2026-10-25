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
    // The palette a dock popup gives its contents, so cards match the scheme.
    palette.window: ui.surface
    palette.windowText: ui.text
    palette.base: ui.raised
    palette.mid: ui.border
    palette.highlight: ui.accent
    palette.highlightedText: ui.onAccent
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
            queue = queue.concat([{service: message.service, resolve: resolve, reject: reject}]);
        }
        function reply(text, service) {
            const index = service ? queue.findIndex(item => item.service === service) : 0;
            const next = queue[index];
            queue = queue.filter((item, i) => i !== index);
            next.resolve({value: text});
        }
    }
    QtObject {
        id: sessionFixture
        objectName: "sessionFixture"
        property bool reloadRequired: false
        property bool busy: false
        property string feedback: "O complemento mudou fora desta janela."
        property int reloads: 0
        function reload() { reloads++; return true; }
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
    DockUI.IntegrationDetails {
        objectName: "quotaDetailsUnderTest"
        width: parent.width
        dock: dockFixture
        integrations: integrations
        selected: "quota"
        addonsSession: sessionFixture
    }
}
