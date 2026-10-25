import QtQuick
import "../code/AddonPeripherals.js" as Addon
import "../code/AddonQuota.js" as Quota

// One passive addon module per instance: "peripherals" (batteries) or "quota".
Item {
    id: root
    property string module: "peripherals"
    // Captured JavaScript record survives queued work without reading a destroyed QObject.
    property var callbackLifetime: ({alive: true})
    property bool active: false
    property bool suspended: false
    property var transport: null
    property var admissionAllowed: null
    // Optional host knowledge. Without settings, the first validated read pins identity.
    property var expectedIdentity: null
    property double nowMsOverride: -1
    property bool loading: false
    // Logical revocation does not settle callbacks already owned by the transport.
    readonly property bool callPending: internal.pendingCalls > 0
    // A read refused only by admission (another reader's turn); the owner retries it once.
    readonly property bool admissionWaiting: internal.admissionWaiting
    property string errorCode: ""
    readonly property string error: !errorCode ? "" : module === "quota"
        ? qsTr("Integração de quota indisponível.") : qsTr("Integração de periféricos indisponível.")
    property var value: emptyValue(active)
    QtObject {
        id: internal
        property bool completed: false
        property int generation: 0
        property var flight: null
        property bool revoking: false
        property int pendingCalls: 0
        property int publishingPending: 0
        property bool refreshDeferred: false
        property bool admissionWaiting: false
        property var accepted: null
        property var identity: null
        property double lastNow: -1
        property double freshnessFloor: -1
    }
    function admitted() {
        return admissionAllowed === null || (typeof admissionAllowed === "function" && admissionAllowed());
    }
    function canRead() {
        return !internal.revoking && internal.publishingPending === 0 && active && !suspended && admitted();
    }
    function nowMs() { return nowMsOverride >= 0 ? nowMsOverride : Date.now(); }
    function emptyValue(isActive) { return module === "quota" ? Quota.empty(isActive) : Addon.empty(isActive); }
    function decodeReply(text) { return module === "quota" ? Quota.decode(text) : Addon.decode(text); }
    function currentValue(current, now, floor) {
        return module === "quota" ? Quota.current(current, now, floor) : Addon.current(current, now, floor);
    }
    function deadlineFor(current, now) { return module === "quota" ? Quota.deadline(current, now) : Addon.deadline(current, now); }
    function queueRefresh(generation) {
        const lifetime = callbackLifetime;
        Qt.callLater(function() {
            if (!lifetime.alive) return;
            if (generation === internal.generation) root.refresh();
        });
    }
    function invalidate() { revoke(true); }
    function revoke(resetIdentity) {
        const generation = ++internal.generation;
        // Publication may call back into refresh in the same generation.
        internal.revoking = true;
        try {
            // Detach before notifying observers; a stalled old callback owns nothing new.
            internal.flight = null;
            internal.accepted = null;
            if (resetIdentity) { internal.identity = null; internal.freshnessFloor = -1; }
            internal.lastNow = -1;
            expiry.stop();
            if (resetIdentity) errorCode = "";
            if (generation !== internal.generation) return;
            value = emptyValue(active);
            if (generation !== internal.generation) return;
            loading = false;
        } finally {
            if (generation === internal.generation) internal.revoking = false;
        }
        if (generation === internal.generation) queueRefresh(generation);
    }
    function genericName(device) {
        if (typeof device.displayName === "string") return device.displayName;
        const labels = {mouse: qsTr("Mouse"), keyboard: qsTr("Teclado"), earbuds: qsTr("Fones de ouvido"),
            headset: qsTr("Headset"), touchpad: qsTr("Touchpad"), gamepad: qsTr("Controle"), other: qsTr("Periférico")};
        return labels[device.kind] + device.name.slice(device.kind.length);
    }
    function publish(generation, accepted, code) {
        if (generation !== internal.generation) return;
        internal.accepted = accepted;
        errorCode = code;
        if (generation !== internal.generation) return;
        const shown = accepted === null ? emptyValue(active) : JSON.parse(JSON.stringify(accepted));
        if (module === "peripherals") for (const device of shown.devices) device.name = genericName(device);
        value = shown;
        if (generation === internal.generation) armExpiry();
    }
    function armExpiry() {
        expiry.stop();
        const now = nowMs();
        const next = deadlineFor(internal.accepted, now);
        if (next > 0) { expiry.interval = Math.max(1, next - now); expiry.start(); }
    }
    function observeClock(now) {
        // Automatic clock revocation cannot make an already expired lease fresh again.
        if (Addon.stamp(now)) internal.freshnessFloor = Math.max(internal.freshnessFloor, now);
    }
    function checkTime() {
        const generation = internal.generation;
        const now = nowMs();
        observeClock(now);
        if (internal.lastNow >= 0 && now < internal.lastNow) {
            // Time revokes readings/callbacks, never authorization to replace the source.
            revoke(false);
            return;
        }
        internal.lastNow = now;
        if (internal.accepted !== null) {
            try {
                const current = currentValue(internal.accepted, now, internal.freshnessFloor);
                if (JSON.stringify(current) !== JSON.stringify(internal.accepted)) publish(generation, current, "");
                else armExpiry();
            } catch (_) { publish(generation, null, "invalid_response"); }
        }
    }
    function changePending(delta) {
        // Bound observers may reenter while callPending is still being evaluated.
        internal.publishingPending++;
        try { internal.pendingCalls += delta; }
        finally {
            internal.publishingPending--;
            if (internal.publishingPending === 0 && internal.refreshDeferred) {
                internal.refreshDeferred = false;
                // The counter assignment and all bound notifications have returned.
                root.refresh();
            }
        }
    }
    function settlePhysical(operation) {
        if (!operation.pending) return;
        operation.pending = false;
        changePending(-1);
    }
    function finish(operation, reply, failed) {
        if (operation.settling) return;
        // Claim the callback before notifying physical-settlement observers.
        operation.settling = true;
        settlePhysical(operation);
        if (internal.flight !== operation) return;
        if (operation.generation === internal.generation && canRead()) {
            const decoded = failed ? {error: "unavailable"} : decodeReply(reply ? reply.value : null);
            let accepted = null;
            let code = decoded.error || "";
            if (!code && (!Addon.matches(decoded.value, expectedIdentity)
                    || !Addon.matches(decoded.value, internal.identity))) code = "source_changed";
            if (!code) {
                try {
                    const now = nowMs();
                    observeClock(now);
                    if (internal.lastNow >= 0 && now < internal.lastNow) { revoke(false); return; }
                    accepted = currentValue(decoded.value, now, internal.freshnessFloor);
                    internal.lastNow = now;
                    internal.identity = Addon.identity(accepted);
                } catch (_) { code = "invalid_response"; }
            }
            publish(operation.generation, accepted, code);
        }
        if (internal.flight !== operation) return;
        internal.flight = null;
        loading = false;
    }
    function refresh() {
        if (internal.publishingPending > 0) { internal.refreshDeferred = true; return; }
        if (!internal.completed || internal.flight !== null) return;
        if (!canRead()) {
            internal.admissionWaiting = !internal.revoking && internal.publishingPending === 0 && active && !suspended
                && !admitted();
            return;
        }
        internal.admissionWaiting = false;
        checkTime();
        if (!canRead() || internal.flight !== null) return;
        const operation = {generation: internal.generation, settling: false};
        internal.flight = operation;
        loading = true;
        if (internal.flight !== operation || operation.generation !== internal.generation || !canRead()) return;
        const message = {service: "org.orla.Addons", path: "/org/orla/Addons", iface: "org.orla.Addons1",
            member: "SnapshotFor", signature: "(as)", arguments: [[module]]};
        try {
            if (transport === null) { finish(operation, null, true); return; }
            operation.pending = true;
            changePending(1);
            // A pending-call observer can revoke admission before the actual call.
            if (internal.flight !== operation || operation.generation !== internal.generation || !canRead()) {
                settlePhysical(operation);
                return;
            }
            const lifetime = callbackLifetime;
            transport.asyncCall(message,
                reply => { if (lifetime.alive) finish(operation, reply, false); },
                () => { if (lifetime.alive) finish(operation, null, true); });
        } catch (_) { finish(operation, null, true); }
    }
    onActiveChanged: invalidate()
    onSuspendedChanged: invalidate()
    onExpectedIdentityChanged: invalidate()
    onModuleChanged: invalidate()
    onNowMsOverrideChanged: if (internal.completed) checkTime()
    Component.onDestruction: callbackLifetime.alive = false
    Component.onCompleted: { internal.completed = true; invalidate(); }
    Timer { id: expiry; repeat: false; onTriggered: root.checkTime() }
    // Wall clocks can jump while a transport is stalled. Deadlines use the one-shot above.
    Timer { interval: 1000; repeat: true; running: root.active && !root.suspended; onTriggered: root.checkTime() }
    Timer { interval: 15000; repeat: true; running: root.active && !root.suspended; onTriggered: root.refresh() }
}
