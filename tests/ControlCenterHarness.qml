import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    id: window
    width: 280
    height: 420
    visible: true
    color: "#111923"

    property alias backend: fixtureBackend
    property alias battery: fixtureBattery
    property alias player: fixturePlayer

    QtObject {
        id: fixtureBackend
        objectName: "controlCenterBackend"
        property var calls: []
        property string failingTarget: "none"
        function openSystemSettings(target) {
            if (target === failingTarget) throw new Error("private fixture failure");
            calls = calls.concat([target]);
        }
    }
    QtObject {
        id: fixtureBattery
        objectName: "controlCenterBattery"
        property string status: "ready"
        property string summary: "0%"
        property string subtitle: "Na bateria"
    }
    QtObject {
        id: fixturePlayer
        objectName: "controlCenterPlayer"
        property string track: "Faixa sintética"
        property string artist: "Artista sintético"
        property string identity: "Player sintético"
    }
    DockUI.KdeControlActions {
        id: actions
        objectName: "controlCenterActions"
        backend: fixtureBackend
    }
    DockUI.ControlCenter {
        id: controlCenter
        objectName: "controlCenterUnderTest"
        width: window.width
        height: window.height
        actions: actions
        player: fixturePlayer
        battery: fixtureBattery
    }
}
