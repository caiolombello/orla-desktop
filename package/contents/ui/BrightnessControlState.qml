import QtQuick

// Portable screen-brightness state; the KDE backend lives in NativeBrightness.qml.
// One change per display is in flight until the service's own readback reaches
// it; during a drag only the newest value waits for its turn.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, displays: [{id, label, value, max, internal}]}, setBrightness(id, raw) -> bool}
    property var backend: null
    property int confirmationTimeout: 3000
    property var nowProvider: function() { return Date.now(); }

    readonly property var snapshot: active && backend ? backend.snapshot : null
    // Without a backend (fixtures, missing KDE module) the card stays hidden.
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property var displays: _validated.displays
    readonly property bool pendingAny: Object.keys(_pending).length > 0
    // Stable list for views: readbacks must not recreate a focused or dragged slider.
    property var displayIds: []
    property string error: ""

    signal confirmed(var receipt)

    property var _pending: ({})
    readonly property var _validated: validate(snapshot)

    function nowMs() {
        try {
            const value = Number(nowProvider());
            return Number.isFinite(value) ? value : Date.now();
        } catch (_) { return Date.now(); }
    }
    function validate(value) {
        const invalid = {status: "unavailable", displays: []};
        if (!value || typeof value !== "object") return {status: "loading", displays: []};
        if (["ready", "absent", "unavailable", "loading"].indexOf(value.status) < 0 || !Array.isArray(value.displays)) return invalid;
        const displays = [];
        const ids = {};
        for (const entry of value.displays.slice(0, 4)) {
            if (!entry || typeof entry.id !== "string" || entry.id.length === 0 || entry.id.length > 64 || ids[entry.id]) return invalid;
            const max = Number(entry.max), current = Number(entry.value);
            if (!Number.isInteger(max) || max < 1 || max > 1000000 || !Number.isInteger(current) || current < 0 || current > max) return invalid;
            ids[entry.id] = true;
            displays.push({id: entry.id, label: String(entry.label || "").slice(0, 128).replace(/\s+/g, " ").trim(),
                value: current, max: max, internal: Boolean(entry.internal),
                percent: Math.max(0, Math.min(100, Math.round(current * 100 / max)))});
        }
        if (value.status === "ready" && displays.length === 0) return {status: "absent", displays: []};
        return {status: value.status, displays: value.status === "ready" ? displays : []};
    }
    function displayById(id) {
        for (const display of displays) if (display.id === id) return display;
        return null;
    }
    // Half a percent: absorbs service rounding without swallowing a 1% step.
    function tolerance(display) { return Math.floor(display.max / 200); }
    function presentationPercent(id) {
        const display = displayById(id);
        if (!display) return 0;
        const pending = _pending[id];
        if (!pending) return display.percent;
        const raw = pending.queued >= 0 ? pending.queued : pending.raw;
        return Math.max(1, Math.min(100, Math.round(raw * 100 / display.max)));
    }
    function setPending(id, entry) {
        const next = Object.assign({}, _pending);
        if (entry) next[id] = entry; else delete next[id];
        _pending = next;
        scheduleDeadline();
    }
    function send(id, raw) {
        const display = displayById(id);
        // Pending first: a backend may report the new value before returning.
        const entry = {raw: raw, queued: -1, deadline: nowMs() + confirmationTimeout, label: display ? display.label : ""};
        setPending(id, entry);
        let accepted = false;
        try { accepted = Boolean(backend && backend.setBrightness(id, raw)); } catch (_) { accepted = false; }
        if (!accepted) {
            if (_pending[id] === entry) setPending(id, null);
            error = qsTr("O serviço de brilho recusou a alteração.");
            return false;
        }
        return true;
    }
    // A user action only; the slider never writes on its own.
    function request(id, percent) {
        if (status !== "ready") return false;
        const display = displayById(String(id));
        const value = Math.round(Number(percent));
        if (!display || !Number.isFinite(value)) return false;
        // 1% floor: some internal panels switch off at zero.
        const raw = Math.round(Math.max(1, Math.min(100, value)) * display.max / 100);
        error = "";
        const pending = _pending[display.id];
        if (pending) {
            setPending(display.id, Object.assign({}, pending, {queued: raw}));
            return true;
        }
        if (Math.abs(raw - display.value) <= 0) return true;
        return send(display.id, raw);
    }
    function observe() {
        for (const id of Object.keys(_pending)) {
            const pending = _pending[id];
            const display = displayById(id);
            if (!display) {
                setPending(id, null);
                error = qsTr("A tela deixou de estar disponível antes da confirmação.");
                continue;
            }
            if (Math.abs(display.value - pending.raw) > tolerance(display)) continue;
            confirmed({displayId: id, label: display.label, value: display.percent});
            if (pending.queued >= 0 && Math.abs(display.value - pending.queued) > tolerance(display)) send(id, pending.queued);
            else setPending(id, null);
        }
    }
    function expire() {
        const now = nowMs();
        for (const id of Object.keys(_pending)) {
            if (_pending[id].deadline > now) continue;
            setPending(id, null);
            error = qsTr("O brilho não foi confirmado pelo serviço. O valor mostrado é o atual.");
        }
    }
    function scheduleDeadline() {
        let next = 0;
        for (const id of Object.keys(_pending)) {
            const deadline = _pending[id].deadline;
            if (next === 0 || deadline < next) next = deadline;
        }
        if (next === 0) { deadlineTimer.stop(); return; }
        deadlineTimer.interval = Math.max(1, next - nowMs());
        deadlineTimer.restart();
    }
    function reset() {
        _pending = ({});
        deadlineTimer.stop();
        error = "";
    }
    Timer { id: deadlineTimer; repeat: false; onTriggered: root.expire() }
    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        // A refused write ends its wait at once instead of at the deadline.
        function onWriteFailed(id) {
            if (!root._pending[id]) return;
            root.setPending(id, null);
            root.error = qsTr("O serviço de brilho recusou a alteração.");
        }
    }
    onDisplaysChanged: {
        const ids = displays.map(display => display.id);
        if (ids.join("\n") !== displayIds.join("\n")) displayIds = ids;
        observe();
    }
    onActiveChanged: if (!active) reset()
    onBackendChanged: reset()
}
