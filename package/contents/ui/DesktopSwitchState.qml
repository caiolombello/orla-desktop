import QtQuick

// Transient command state. The observed ContextState remains the only current/list authority.
Item {
    id: root
    property var contexts: null
    property var backend: null
    property bool active: false
    property int confirmationTimeoutMs: 5000
    readonly property string currentId: contexts ? contexts.snapshot.desktop.id : ""
    readonly property string currentName: contexts ? contexts.snapshot.desktop.name : ""
    readonly property var desktops: contexts ? (contexts.snapshot.desktops || []) : []
    readonly property bool sourceReady: contexts && contexts.snapshot.desktop.status === "ready"
    readonly property int desktopRevision: internal.revision
    readonly property int requestGeneration: internal.generation
    readonly property bool pending: internal.intent !== null
    readonly property string status: internal.status
    readonly property string error: status === "failed" ? qsTr("Não foi possível confirmar a troca da área.") : ""
    readonly property bool available: active && sourceReady && backend && backend.available
    readonly property string selectedId: internal.selectedId
    readonly property bool canRequest: available && !pending && selectedId !== currentId && contains(selectedId)
    signal observed(int requestId, string desktopId)

    QtObject {
        id: internal
        property int revision: 0
        property int generation: 0
        property string fingerprint: ""
        property string selectedId: ""
        property string status: "idle"
        property var intent: null
        property bool settling: false
    }
    // Read one immutable ContextState snapshot per rule evaluation. Presentation
    // bindings can still contain the preceding value during snapshotChanged.
    function readSnapshot() {
        const snapshot = contexts ? contexts.snapshot : null;
        return snapshot || {desktop:{status:"unavailable", id:""}, desktops:[]};
    }
    function ready(snapshot) { return snapshot.desktop.status === "ready"; }
    function contains(id, snapshot) {
        const data = snapshot || readSnapshot();
        return typeof id === "string" && data.desktops.some(item => item.id === id);
    }
    function inventory(snapshot) {
        const data = snapshot || readSnapshot();
        return JSON.stringify(data.desktops.map(item => ({id:item.id, name:item.name})));
    }
    function selectDesktop(id) {
        const snapshot = readSnapshot();
        if (!active || internal.intent || !contains(id, snapshot)) return false;
        if (internal.selectedId !== id) internal.status = "idle";
        internal.selectedId = id;
        return true;
    }
    function finish(nextStatus) {
        const previous = internal.intent;
        // Invalidate first: state signals and cancel may synchronously reenter.
        internal.settling = true;
        internal.intent = null;
        internal.generation++;
        internal.status = nextStatus;
        timeout.stop();
        try {
            if (previous && previous.backend && typeof previous.backend.cancel === "function") previous.backend.cancel(previous.id);
        } finally { internal.settling = false; }
    }
    function valid(id, phase, snapshot) {
        const data = snapshot || readSnapshot();
        const intent = internal.intent;
        if (!intent || intent.id !== id || !active || !ready(data) || backend !== intent.backend
                || !backend.available || !contains(intent.target, data) || inventory(data) !== intent.inventory) return false;
        return phase === "dispatch" ? internal.revision === intent.revision && data.desktop.id === intent.origin
            : phase === "observe" && (data.desktop.id === intent.origin || data.desktop.id === intent.target);
    }
    function converge(snapshot) {
        const data = snapshot || readSnapshot();
        const intent = internal.intent;
        if (!intent || !intent.replied || !intent.readback || !valid(intent.id, "observe", data)
                || data.desktop.id !== intent.target || internal.revision <= intent.revision) return;
        const id = intent.id;
        const target = intent.target;
        finish("observed");
        observed(id, target);
    }
    function requestDesktopSwitch(id, expectedDesktopRevision) {
        if (internal.intent || internal.settling) return false;
        const snapshot = readSnapshot();
        refresh(snapshot);
        if (!active || !ready(snapshot) || !backend || !backend.available || typeof expectedDesktopRevision !== "number"
                || expectedDesktopRevision !== internal.revision || !contains(id, snapshot) || id === snapshot.desktop.id
                || typeof backend.requestDesktopSwitch !== "function") return false;
        const client = backend;
        const generation = ++internal.generation;
        internal.intent = {id:generation, backend:client, target:id, origin:snapshot.desktop.id,
            revision:internal.revision, inventory:inventory(snapshot), replied:false, readback:false, owner:""};
        internal.selectedId = id;
        internal.status = "requested";
        timeout.restart();
        let accepted = false;
        try { accepted = client.requestDesktopSwitch(id, generation, phase => valid(generation, phase)) === true; }
        catch (_) { accepted = false; }
        if (!accepted || !internal.intent || internal.intent.id !== generation || backend !== client || !active) {
            if (internal.intent && internal.intent.id === generation) finish("failed");
            return false;
        }
        return true;
    }
    function refresh(snapshot) {
        const data = snapshot || readSnapshot();
        const fingerprint = JSON.stringify({ready:ready(data), current:data.desktop.id, list:inventory(data)});
        if (fingerprint === internal.fingerprint) return;
        internal.fingerprint = fingerprint;
        internal.revision++;
        if (!internal.intent && internal.status === "observed" && data.desktop.id !== internal.selectedId) internal.status = "idle";
        if (!contains(internal.selectedId, data)) internal.selectedId = ready(data) ? data.desktop.id : "";
        if (internal.intent && !valid(internal.intent.id, "observe", data)) finish("failed");
        else converge(data);
    }
    Connections {
        target: root.contexts
        function onSnapshotChanged() { root.refresh(); }
    }
    Connections {
        target: root.backend
        function onAvailableChanged() { if (internal.intent && !root.backend.available) root.finish("failed"); }
        function onSetReplied(requestId, owner) {
            const snapshot = root.readSnapshot();
            root.refresh(snapshot);
            const intent = internal.intent;
            if (!intent || intent.id !== requestId) return;
            if (typeof owner !== "string" || !owner.startsWith(":")) { root.finish("failed"); return; }
            intent.owner = owner;
            intent.replied = true;
            root.converge(snapshot);
        }
        function onReadback(requestId, currentId, owner) {
            const snapshot = root.readSnapshot();
            root.refresh(snapshot);
            const intent = internal.intent;
            if (!intent || intent.id !== requestId) return;
            if (!intent.replied || owner !== intent.owner || currentId !== intent.target || !root.valid(requestId, "observe", snapshot)) {
                root.finish("failed"); return;
            }
            intent.readback = true;
            root.converge(snapshot);
        }
        function onFailed(requestId) { if (internal.intent && internal.intent.id === requestId) root.finish("failed"); }
    }
    Timer { id:timeout; interval:Math.max(1, root.confirmationTimeoutMs); onTriggered: root.finish("failed") }
    onActiveChanged: {
        if (internal.intent) finish("failed");
        internal.status = "idle";
        const snapshot = readSnapshot();
        if (active) internal.selectedId = ready(snapshot) ? snapshot.desktop.id : "";
    }
    onBackendChanged: if (internal.intent) finish("failed")
    onContextsChanged: { if (internal.intent) finish("failed"); refresh(); }
    Component.onCompleted: { const snapshot = readSnapshot(); refresh(snapshot); if (active) internal.selectedId = ready(snapshot) ? snapshot.desktop.id : ""; }
    Component.onDestruction: if (internal.intent) finish("failed")
}
