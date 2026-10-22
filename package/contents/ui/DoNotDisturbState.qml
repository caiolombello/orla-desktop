import QtQuick

// Portable Do Not Disturb state; NativeDoNotDisturb.qml uses Plasma's own
// notification settings. A request completes only when the notification server
// reports the requested state, so Orla and Plasma always show the same mode.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, inhibited, until (epoch ms or 0), byApplication, applications}, setDoNotDisturb(on) -> bool}
    property var backend: null
    property int confirmationTimeout: 3000

    readonly property var snapshot: active && backend ? backend.snapshot : null
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property bool inhibited: _validated.inhibited
    readonly property double until: _validated.until
    readonly property bool byApplication: _validated.byApplication
    readonly property var applications: _validated.applications
    readonly property bool presentation: pending ? desired : inhibited
    property bool pending: false
    property bool desired: false
    property string error: ""

    signal confirmed(bool on)

    readonly property var _validated: validate(snapshot)

    function validate(value) {
        const none = {status: "unavailable", inhibited: false, until: 0, byApplication: false, applications: []};
        if (!value || typeof value !== "object") return Object.assign({}, none, {status: "loading"});
        if (value.status !== "ready") return none;
        const until = Number(value.until);
        if (typeof value.inhibited !== "boolean" || typeof value.byApplication !== "boolean"
                || !Number.isFinite(until) || until < 0 || !Array.isArray(value.applications)) return none;
        const applications = value.applications.slice(0, 8)
            .map(name => String(name || "").slice(0, 64).replace(/\s+/g, " ").trim()).filter(name => name.length > 0);
        return {status: "ready", inhibited: value.inhibited, until: until, byApplication: value.byApplication,
            applications: applications};
    }
    // A user action only; opening the Control Center never changes the mode.
    function request(on) {
        if (status !== "ready" || pending) return false;
        const want = Boolean(on);
        error = "";
        if (want === inhibited) return true;
        desired = want;
        pending = true;
        confirmation.restart();
        let accepted = false;
        try { accepted = Boolean(backend.setDoNotDisturb(want)); } catch (_) { accepted = false; }
        if (!accepted) {
            pending = false;
            confirmation.stop();
            error = qsTr("O KDE recusou a alteração do Não perturbe.");
            return false;
        }
        observe();
        return true;
    }
    function observe() {
        if (!pending || status !== "ready" || inhibited !== desired) return;
        pending = false;
        confirmation.stop();
        confirmed(desired);
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
            root.pending = false;
            // Plasma keeps the mode on for full screen or mirrored screens by its own rules.
            root.error = root.desired ? qsTr("O KDE não confirmou o Não perturbe.")
                : qsTr("O Não perturbe continua ativo. Uma regra do KDE, como tela cheia ou espelhamento, pode mantê-lo.");
        }
    }
    onInhibitedChanged: observe()
    onStatusChanged: observe()
    onActiveChanged: if (!active) reset()
    onBackendChanged: reset()
}
