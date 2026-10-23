import QtQuick

// Portable Bluetooth radio state; NativeBluetooth.qml uses BluezQt, as Plasma's
// Bluetooth applet does. A request completes only when BlueZ reports the radio
// in the requested state, so Orla never shows Bluetooth on or off when it is not.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, enabled, blocked, connected: [names]}, setEnabled(on) -> bool}
    property var backend: null
    property int confirmationTimeout: 5000

    readonly property var snapshot: active && backend ? backend.snapshot : null
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property bool enabled: _validated.enabled
    // Turned off by a radio block (rfkill), which Orla lifts the way Plasma does.
    readonly property bool blocked: _validated.blocked
    readonly property var connected: _validated.connected
    readonly property bool presentation: pending ? desired : enabled
    property bool pending: false
    property bool desired: false
    property string error: ""

    signal confirmed(bool on)

    readonly property var _validated: validate(snapshot)

    function validate(value) {
        const none = {status: "unavailable", enabled: false, blocked: false, connected: []};
        if (!value || typeof value !== "object") return Object.assign({}, none, {status: "loading"});
        if (value.status === "loading" || value.status === "absent") return Object.assign({}, none, {status: value.status});
        if (value.status !== "ready" || typeof value.enabled !== "boolean" || typeof value.blocked !== "boolean"
                || !Array.isArray(value.connected)) return none;
        const connected = value.connected.slice(0, 8)
            .map(name => String(name || "").slice(0, 64).replace(/\s+/g, " ").trim()).filter(name => name.length > 0);
        return {status: "ready", enabled: value.enabled, blocked: value.blocked, connected: value.enabled ? connected : []};
    }
    // A user action only; opening the Control Center never changes the radio.
    function request(on) {
        if (status !== "ready" || pending) return false;
        const want = Boolean(on);
        error = "";
        if (want === enabled) return true;
        desired = want;
        pending = true;
        confirmation.restart();
        let accepted = false;
        try { accepted = Boolean(backend.setEnabled(want)); } catch (_) { accepted = false; }
        if (!accepted) {
            reset();
            error = qsTr("O serviço de Bluetooth recusou a alteração.");
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
        // Lifting a radio block brings the adapter back before it powers on, so allow longer.
        interval: root.confirmationTimeout
        onTriggered: {
            if (!root.pending) return;
            root.reset();
            root.error = qsTr("O serviço de Bluetooth não confirmou a alteração.");
        }
    }
    on_ValidatedChanged: observe()
    onActiveChanged: if (!active) reset()
    onBackendChanged: reset()
}
