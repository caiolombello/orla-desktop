import QtQuick
import QtQuick.Window
import "../notifications/contents/ui" as Orla

Window {
    width: 420
    height: 720
    visible: true
    property var events: []
    function record(name, value) { events = events.concat([value === undefined ? name : name + ":" + value]); }
    Column {
        spacing: 24
        x: 24
        y: 24
        Orla.NotificationBanner {
            id: banner
            objectName: "bannerUnderTest"
            width: implicitWidth
            notification: ({id: "1", appName: "Aplicativo sintético", appIcon: "", summary: "Título",
                body: "Corpo", actions: [], hasDefaultAction: true, closable: true, critical: false,
                createdMs: 1000, job: null})
            nowMs: 1000
            onActivated: record("activated")
            onCloseRequested: record("close")
            onActionRequested: name => record("action", name)
            onJobControlRequested: control => record("job", control)
            onExpired: record("expired")
        }
        Orla.NotificationCenter {
            id: center
            objectName: "centerUnderTest"
            width: 360
            nowMs: 1000
            onClearAllRequested: record("clearAll")
            onClearGroupRequested: key => record("clearGroup", key)
            onCloseRequested: id => record("closeItem", id)
            onActivated: id => record("activateItem", id)
            onDoNotDisturbToggled: on => record("dnd", on)
        }
    }
}
