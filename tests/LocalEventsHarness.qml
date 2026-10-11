import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    id: root
    width: 240
    height: 102
    visible: true
    color: "#111923"

    DockUI.EventState {
        id: state
        enabled: true
        completionEnabled: true
        audioEnabled: true
        activeScope: "profile:work"
        activeContextGeneration: 4
    }

    Item {
        id: viewport
        objectName: "syntheticTaskViewport"
        x: 86
        y: 10
        width: 80
        height: 82
        clip: true
        DockUI.Tile {
            id: tile
            objectName: "syntheticTaskTile"
            anchors.verticalCenter: parent.verticalCenter
            width: 80
            height: 80
            iconSource: "applications-system"
            iconSize: 64
            tooltip: "Tarefa sintética longa para tooltip"
            foreground: "#edf1f9"
            muted: "#9da9bf"
            accent: "#69d7c2"
            running: true
            activeTask: true
            animationDuration: 0
        }
    }

    DockUI.EventSurface {
        id: surface
        objectName: "syntheticEventSurface"
        x: 172
        y: 10
        width: 58
        height: 82
        eventState: state
        surfaceColor: "#182231"
        borderColor: "#53647a"
        foregroundColor: "#f4f7fb"
        mutedColor: "#aeb9c8"
        accentColor: "#70d7c7"
        animationDuration: 0
    }

    function submit() {
        return state.submit({kind: "completion", key: "pomodoro:completion", scope: "global",
            title: "Foco concluído", detail: "Hora de uma pausa!"}, 1000);
    }
}
