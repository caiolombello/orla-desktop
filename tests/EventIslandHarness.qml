import QtQuick
import QtQuick.Window
import "../package/contents/ui" as DockUI

Window {
    width: 420
    height: 240
    visible: true
    color: "#2b3440"

    DockUI.EventState {
        id: state
        objectName: "islandEventState"
        activeScope: "profile:work"
        activeContextGeneration: 2
    }

    DockUI.IslandState {
        id: islandRules
        objectName: "islandState"
        eventState: state
    }

    DockUI.IslandNotices {
        eventState: state
    }

    // Stands in for MediaState: counts the commands it receives.
    QtObject {
        id: media
        objectName: "islandMediaFixture"
        property bool canRaise: true
        property bool canPrevious: true
        property bool canNext: true
        property bool canPlayPause: true
        property double lengthUs: 200000000
        property double positionUs: 50000000
        property int previousCount: 0
        property int nextCount: 0
        property int playPauseCount: 0
        property int raiseCount: 0
        property int refreshCount: 0
        function previous() { previousCount += 1; return true; }
        function next() { nextCount += 1; return true; }
        function playPause() { playPauseCount += 1; return true; }
        function raise() { raiseCount += 1; return true; }
        function refreshPosition() { refreshCount += 1; }
        function timeText(microseconds) {
            const total = Math.max(0, Math.floor(microseconds / 1000000));
            return Math.floor(total / 60) + ":" + (total % 60 < 10 ? "0" : "") + total % 60;
        }
    }

    QtObject {
        id: timer
        objectName: "islandTimerFixture"
        property int toggleCount: 0
        property int resetCount: 0
        function toggle() { toggleCount += 1; }
        function reset() { resetCount += 1; }
    }

    DockUI.EventIsland {
        id: island
        x: (parent.width - width) / 2
        y: 4
        width: implicitWidth
        height: implicitHeight
        islandState: islandRules
        mediaController: media
        timerController: timer
        interactive: true
        reducedMotion: true
        collapseDelay: 60000
    }
}
