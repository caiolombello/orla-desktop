import QtQuick

// Portable Wi-Fi radio state; NativeWifi.qml uses Plasma's network applet
// library. A request completes only when NetworkManager reports the radio in
// the requested state, so Orla never shows Wi-Fi on or off when it is not.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, enabled, hardwareEnabled, network}, setEnabled(on) -> bool}
    property var backend: null
    property int confirmationTimeout: 3000

    readonly property var snapshot: active && backend ? backend.snapshot : null
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property bool enabled: _validated.enabled
    // A hardware switch or rfkill block: software cannot turn the radio on.
    readonly property bool hardwareEnabled: _validated.hardwareEnabled
    readonly property string network: _validated.network
    readonly property bool presentation: pending ? desired : enabled
    property bool pending: false
    property bool desired: false
    property string error: ""

    signal confirmed(bool on)

    readonly property var _validated: validate(snapshot)

    function validate(value) {
        const none = {status: "unavailable", enabled: false, hardwareEnabled: false, network: ""};
        if (!value || typeof value !== "object") return Object.assign({}, none, {status: "loading"});
        if (value.status === "loading" || value.status === "absent") return Object.assign({}, none, {status: value.status});
        if (value.status !== "ready" || typeof value.enabled !== "boolean" || typeof value.hardwareEnabled !== "boolean")
            return none;
        const network = String(value.network || "").slice(0, 64).replace(/\s+/g, " ").trim();
        return {status: "ready", enabled: value.enabled, hardwareEnabled: value.hardwareEnabled,
            network: value.enabled ? network : ""};
    }
    // A user action only; opening the Control Center never changes the radio.
    function request(on) {
        if (status !== "ready" || pending) return false;
        const want = Boolean(on);
        error = "";
        if (want === enabled) return true;
        if (want && !hardwareEnabled) {
            error = qsTr("O Wi-Fi está desligado por uma chave do computador.");
            return false;
        }
        desired = want;
        pending = true;
        confirmation.restart();
        let accepted = false;
        try { accepted = Boolean(backend.setEnabled(want)); } catch (_) { accepted = false; }
        if (!accepted) {
            reset();
            error = qsTr("O NetworkManager recusou a alteração do Wi-Fi.");
            return false;
        }
        observe();
        return true;
    }
    function observe() {
        if (!pending || !active || !backend) return;
        // One validated reading: derived properties may still be notifying.
        const reading = _validated;
        if (reading.status !== "ready" || reading.enabled !== desired) return;
        const value = desired;
        reset();
        confirmed(value);
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
            // NetworkManager may also refuse silently, for example by policy.
            root.error = qsTr("O NetworkManager não confirmou a alteração do Wi-Fi.");
        }
    }
    on_ValidatedChanged: observe()
    onActiveChanged: if (!active) reset()
    onBackendChanged: reset()
}
