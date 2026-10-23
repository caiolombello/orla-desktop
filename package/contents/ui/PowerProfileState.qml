import QtQuick

// Portable power-profile state; NativePowerProfile.qml talks to PowerDevil. A
// request completes only when the service reports the requested profile as the
// current one, so Orla never shows a profile that the system did not apply.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, profiles, current, inhibitedReason, degradedReason, holds: [{application, profile}]},
    //  setProfile(id) -> bool, optional signal writeFailed(id)}
    property var backend: null
    property int confirmationTimeout: 3000

    // The three profiles defined by power-profiles-daemon, in Plasma's order.
    readonly property var knownProfiles: ["power-saver", "balanced", "performance"]
    readonly property var snapshot: active && backend ? backend.snapshot : null
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property var profiles: _validated.profiles
    readonly property string current: _validated.current
    readonly property string inhibitedReason: _validated.inhibitedReason
    readonly property string degradedReason: _validated.degradedReason
    readonly property var holds: _validated.holds
    readonly property string presentation: pending ? desired : current
    property bool pending: false
    property string desired: ""
    property string error: ""

    signal confirmed(string profile)

    readonly property var _validated: validate(snapshot)

    function text(value, maximum) {
        return String(value === undefined || value === null ? "" : value).slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function validate(value) {
        const none = {status: "unavailable", profiles: [], current: "", inhibitedReason: "", degradedReason: "", holds: []};
        if (!value || typeof value !== "object") return Object.assign({}, none, {status: "loading"});
        if (value.status === "loading" || value.status === "absent") return Object.assign({}, none, {status: value.status});
        if (value.status !== "ready" || !Array.isArray(value.profiles) || typeof value.current !== "string") return none;
        // Unknown names are ignored rather than shown with an invented label.
        const offered = value.profiles.slice(0, 8).map(String);
        const profiles = knownProfiles.filter(id => offered.indexOf(id) >= 0);
        if (profiles.length === 0) return Object.assign({}, none, {status: "absent"});
        const holds = (Array.isArray(value.holds) ? value.holds : []).slice(0, 8)
            .filter(hold => hold && typeof hold === "object" && knownProfiles.indexOf(String(hold.profile)) >= 0)
            .map(hold => ({application: text(hold.application, 64), profile: String(hold.profile)}));
        return {status: "ready", profiles: profiles,
            // A profile outside the known three reads as "unknown" instead of a wrong choice.
            current: profiles.indexOf(value.current) >= 0 ? value.current : "",
            inhibitedReason: text(value.inhibitedReason, 64), degradedReason: text(value.degradedReason, 64),
            holds: holds};
    }
    // Performance is unavailable while the service reports a reason, as in Plasma's applet.
    function selectable(id) {
        return status === "ready" && profiles.indexOf(id) >= 0 && !(id === "performance" && inhibitedReason.length > 0);
    }
    // A user action only; opening the Control Center never changes the profile.
    function request(id) {
        const want = String(id || "");
        if (status !== "ready" || pending) return false;
        // A new choice replaces an old error; an unavailable one leaves the reason visible.
        error = "";
        if (!selectable(want)) return false;
        if (want === current) return true;
        desired = want;
        pending = true;
        confirmation.restart();
        let accepted = false;
        try { accepted = Boolean(backend.setProfile(want)); } catch (_) { accepted = false; }
        if (!accepted) {
            reset();
            error = qsTr("O serviço de energia recusou a troca de perfil.");
            return false;
        }
        observe();
        return true;
    }
    function observe() {
        if (!pending || !active || !backend) return;
        // One validated reading: derived properties may still be notifying.
        const reading = _validated;
        if (reading.status !== "ready" || reading.current !== desired) return;
        const value = desired;
        reset();
        confirmed(value);
    }
    function fail(id) {
        if (!pending || String(id) !== desired) return;
        reset();
        error = qsTr("O serviço de energia recusou a troca de perfil.");
    }
    function reset() {
        pending = false;
        confirmation.stop();
        error = "";
    }
    Timer {
        id: confirmation
        interval: root.confirmationTimeout
        onTriggered: {
            if (!root.pending) return;
            root.reset();
            root.error = qsTr("O serviço de energia não confirmou a troca de perfil.");
        }
    }
    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onWriteFailed(id) { root.fail(id); }
    }
    on_ValidatedChanged: observe()
    onActiveChanged: if (!active) reset()
    onBackendChanged: reset()
}
