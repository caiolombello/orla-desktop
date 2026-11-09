import QtQuick
import "../code/Island.js" as Island

// Rules for the top island: which live activity it shows and whether it is
// expanded. EventState keeps owning the transient notices, which take the
// capsule over while they last; EventIsland.qml only draws the result.
QtObject {
    id: state
    objectName: "islandState"

    property var eventState: null
    property bool activitiesEnabled: false
    property bool timerRunning: false
    property int timerSecondsLeft: 0
    property bool timerBreak: false
    property bool mediaPlaying: false
    property bool mediaPaused: false
    property string mediaTitle: ""
    property string mediaArtist: ""
    property string mediaArtUrl: ""
    property bool microphoneInUse: false
    property bool cameraInUse: false
    property bool expanded: false
    // Paused music stays in the island a moment, so the play button that
    // paused it is still there to resume it.
    readonly property int pausedGrace: 15000
    property bool mediaHeld: false

    readonly property bool hasEvent: Boolean(eventState && eventState.current)
    readonly property var privacy: Island.privacyState(activitiesEnabled
        ? {microphone: microphoneInUse, camera: cameraInUse} : null)
    readonly property var activities: activitiesEnabled ? Island.activities({
        timer: {running: timerRunning, secondsLeft: timerSecondsLeft, isBreak: timerBreak},
        media: {playing: mediaPlaying, held: mediaPaused && (mediaHeld || expanded),
            title: mediaTitle, artist: mediaArtist, artUrl: mediaArtUrl},
        privacy: privacy
    }) : []
    readonly property var primary: activities.length ? activities[0] : null
    readonly property string mode: Island.mode(hasEvent, activities, expanded)

    function toggle() {
        if (!primary || hasEvent) return false;
        expanded = !expanded;
        return true;
    }
    function collapse() { expanded = false; }

    // Checked a turn later: a player going from playing to paused updates
    // both flags, in either order, and must not fold the island in between.
    onPrimaryChanged: Qt.callLater(state.collapseWhenIdle)
    function collapseWhenIdle() { if (!primary) expanded = false; }
    // A notice replaces the expanded view; it comes back compact.
    onHasEventChanged: if (hasEvent) expanded = false
    onMediaPlayingChanged: if (mediaPlaying) { heldTimer.stop(); mediaHeld = false; }
    onMediaPausedChanged: {
        heldTimer.stop();
        mediaHeld = mediaPaused;
        if (mediaPaused) heldTimer.restart();
    }
    onActivitiesEnabledChanged: if (!activitiesEnabled) { heldTimer.stop(); mediaHeld = false; expanded = false; }

    property Timer heldTimer: Timer {
        interval: state.pausedGrace
        onTriggered: state.mediaHeld = false
    }
}
