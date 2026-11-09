import QtQuick

// Focus modes, as on macOS: switching to a profile can turn Plasma's Do Not
// Disturb on or off. Only a profile switch acts, never startup or a reload,
// and "keep" leaves the mode alone. `waiting` keeps the Do Not Disturb backend
// loaded until Plasma has confirmed the request.
QtObject {
    id: focus
    objectName: "focusMode"
    required property var doNotDisturb
    property string profileId: ""
    // The active profile's doNotDisturb: "keep", "on" or "off".
    property string mode: "keep"
    // "on" or "off" while a switch waits for Plasma's notification server.
    property string pending: ""
    // After the request, until Plasma answers, so the state can see the answer.
    // A flag of its own: reading the state's `pending` here would loop through
    // the `active` binding this property feeds.
    property bool holding: false
    readonly property bool waiting: pending.length > 0 || holding
    property bool started: false
    // The last request: {profileId, mode, accepted}. For tests and diagnostics.
    property var last: null

    // Read the mode a turn later: the profile id and its presentation update together.
    onProfileIdChanged: if (started) Qt.callLater(focus.arm)
    function arm() {
        pending = mode === "on" || mode === "off" ? mode : "";
        if (waiting) expiry.restart();
    }
    function apply() {
        if (!waiting || !doNotDisturb || doNotDisturb.status !== "ready") return false;
        const want = pending;
        // Request first: clearing `pending` unloads the backend this request needs.
        const accepted = doNotDisturb.request(want === "on");
        holding = accepted && doNotDisturb.pending;
        pending = "";
        if (!holding) expiry.stop();
        last = {profileId: profileId, mode: want, accepted: accepted};
        return accepted;
    }
    // Tries until the backend that `waiting` loads is ready, outside the status
    // update that loading it causes.
    property Timer retry: Timer {
        interval: 50
        repeat: true
        running: focus.pending.length > 0
        onTriggered: focus.apply()
    }
    // Plasma that never answers drops the request instead of holding the backend.
    property Timer expiry: Timer {
        interval: 8000
        onTriggered: {
            if (focus.pending) focus.last = {profileId: focus.profileId, mode: focus.pending, accepted: false};
            focus.pending = "";
            focus.holding = false;
        }
    }
    // Plasma confirmed or the state gave up waiting: release the backend.
    function release() { if (holding && !doNotDisturb.pending) { holding = false; expiry.stop(); } }
    property Connections answers: Connections {
        target: focus.doNotDisturb
        function onConfirmed(on) { Qt.callLater(focus.release); }
        function onErrorChanged() { Qt.callLater(focus.release); }
    }
    Component.onCompleted: started = true
}
