import QtQuick

// Portable microphone mute state; NativeMicrophone.qml reads Plasma's default
// input. A request completes only when the audio service reports the requested
// state for the same input, so Orla never shows a mute that did not happen.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, input: {id, label, muted, writable} or null}, setMuted(id, muted) -> bool}
    property var backend: null
    property int confirmationTimeout: 3000

    readonly property var snapshot: active && backend ? backend.snapshot : null
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property string inputId: _validated.id
    readonly property string label: _validated.label
    readonly property bool muted: _validated.muted
    readonly property bool writable: _validated.writable
    readonly property bool presentation: pending ? desired : muted
    property bool pending: false
    property bool desired: false
    property string error: ""
    property string _targetId: ""

    signal confirmed(bool muted, string label)

    readonly property var _validated: validate(snapshot)

    function validate(value) {
        const none = {status: "unavailable", id: "", label: "", muted: false, writable: false};
        if (!value || typeof value !== "object") return Object.assign({}, none, {status: "loading"});
        if (value.status === "loading" || value.status === "absent") return Object.assign({}, none, {status: value.status});
        if (value.status !== "ready") return none;
        const input = value.input;
        if (!input || typeof input !== "object") return Object.assign({}, none, {status: "absent"});
        const id = String(input.id || "");
        if (!id || id.length > 256 || typeof input.muted !== "boolean" || typeof input.writable !== "boolean") return none;
        const label = String(input.label || "").slice(0, 128).replace(/\s+/g, " ").trim();
        return {status: "ready", id: id, label: label || qsTr("Microfone sem nome"), muted: input.muted,
            writable: input.writable};
    }
    // A user action only; opening the Control Center never changes the microphone.
    function request(mute) {
        if (status !== "ready" || pending || !writable) return false;
        const want = Boolean(mute);
        error = "";
        if (want === muted) return true;
        desired = want;
        _targetId = inputId;
        pending = true;
        confirmation.restart();
        let accepted = false;
        try { accepted = Boolean(backend.setMuted(_targetId, want)); } catch (_) { accepted = false; }
        if (!accepted) {
            reset();
            error = qsTr("O serviço de áudio recusou a alteração do microfone.");
            return false;
        }
        observe();
        return true;
    }
    function observe() {
        if (!pending || !active || !backend) return;
        // One validated reading: derived properties may still be notifying.
        const current = _validated;
        if (current.status === "ready" && current.id !== _targetId) {
            reset();
            error = qsTr("O microfone padrão mudou antes da confirmação.");
            return;
        }
        if (current.status !== "ready" || current.muted !== desired) return;
        const value = desired;
        reset();
        confirmed(value, current.label);
    }
    function reset() {
        pending = false;
        _targetId = "";
        confirmation.stop();
        error = "";
    }
    Timer {
        id: confirmation
        interval: root.confirmationTimeout
        onTriggered: {
            if (!root.pending) return;
            root.reset();
            root.error = qsTr("O serviço de áudio não confirmou a alteração do microfone.");
        }
    }
    on_ValidatedChanged: observe()
    onActiveChanged: if (!active) reset()
    onBackendChanged: reset()
}
