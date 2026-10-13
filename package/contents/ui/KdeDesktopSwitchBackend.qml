import QtQuick
import org.kde.plasma.workspace.dbus as DBus

// KDE 6.7.5 asyncCall + typed variant; writer qualification is separate from portable tests.
Item {
    id: root
    property bool active: false
    property var contexts: null
    property var transport: null
    property int requestTimeoutMs: 5000
    readonly property string status: internal.status
    readonly property bool available: status === "ready"
    readonly property string owner: internal.owner
    signal setReplied(int requestId, string owner)
    signal readback(int requestId, string currentId, string owner)
    signal failed(int requestId)
    QtObject {
        id: internal
        property bool completed: false
        property int generation: 0
        property string status: "inactive"
        property string owner: ""
        property var operation: null
        property string fingerprint: ""
    }
    function sourceReady() { return contexts && contexts.snapshot.desktop.status === "ready" && !/^\d+$/.test(contexts.snapshot.desktop.id); }
    function currentId() { return sourceReady() ? contexts.snapshot.desktop.id : ""; }
    // Plasma's decoder wraps QString in DBus.string (dbusdecoder.cpp 6.7.5).
    function stringValue(value) {
        if (typeof value === "string") return value;
        return value && typeof value.value === "string" ? value.value : "";
    }
    function validOwner(value) { return typeof value === "string" && value.length <= 255 && /^:[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+$/.test(value); }
    function live(generation) { return active && generation === internal.generation && internal.operation !== null; }
    function invalidate(nextStatus) {
        const previous = internal.operation;
        internal.operation = null;
        internal.generation++;
        timeout.stop();
        internal.status = nextStatus;
        if (previous && previous.requestId >= 0) failed(previous.requestId);
    }
    function failure(generation) { if (live(generation)) invalidate("unavailable"); }
    function call(generation, message, accept) {
        if (!live(generation)) return;
        const resolve = reply => { if (live(generation)) accept(reply); };
        const reject = () => failure(generation);
        try {
            if (transport !== null) transport.asyncCall(message, resolve, reject);
            else DBus.SessionBus.asyncCall(message, resolve, reject);
        } catch (_) { reject(); }
    }
    function getOwner(generation, accept) {
        call(generation, {service:"org.freedesktop.DBus", path:"/org/freedesktop/DBus",
            iface:"org.freedesktop.DBus", member:"GetNameOwner", signature:"(s)",
            arguments:["org.kde.KWin"]}, reply => {
                const value = reply ? stringValue(reply.value) : "";
                if (!validOwner(value)) { failure(generation); return; }
                accept(value);
            });
    }
    function getCurrent(generation, destination, accept) {
        call(generation, {service:destination, path:"/VirtualDesktopManager",
            iface:"org.freedesktop.DBus.Properties", member:"Get", signature:"(ss)",
            arguments:["org.kde.KWin.VirtualDesktopManager", "current"]}, reply => {
                const value = reply ? stringValue(reply.value) : "";
                if (!value.length || value.length > 256) {
                    failure(generation); return;
                }
                accept(value);
            });
    }
    function probe() {
        if (!internal.completed || !active || !sourceReady() || internal.operation !== null) return false;
        const generation = ++internal.generation;
        const expected = currentId();
        internal.status = "loading";
        internal.operation = {requestId:-1};
        timeout.restart();
        getOwner(generation, destination => getCurrent(generation, destination, observed => {
            if (!sourceReady() || observed !== expected || currentId() !== expected) { failure(generation); return; }
            getOwner(generation, finalOwner => {
                if (destination !== finalOwner) { failure(generation); return; }
                internal.owner = destination;
                internal.operation = null;
                timeout.stop();
                internal.status = "ready";
            });
        }));
        return true;
    }
    function guarded(validate, phase) {
        try { return typeof validate === "function" && validate(phase) === true; }
        catch (_) { return false; }
    }
    function requestDesktopSwitch(targetId, requestId, validate) {
        const admissionGeneration = internal.generation;
        if (!available || !active || internal.operation !== null || !sourceReady()
                || typeof targetId !== "string" || !targetId.length || targetId.length > 256 || /^\d+$/.test(targetId)
                || !Number.isInteger(requestId) || requestId < 0 || !guarded(validate, "dispatch")) return false;
        if (!active || !available || !sourceReady() || internal.operation !== null || internal.generation !== admissionGeneration) return false;
        const generation = ++internal.generation;
        const expected = currentId();
        const expectedOwner = internal.owner;
        internal.operation = {requestId:requestId};
        timeout.restart();
        getOwner(generation, destination => {
            if (destination !== expectedOwner) { failure(generation); return; }
            getCurrent(generation, destination, observed => {
                if (observed !== expected || currentId() !== expected || !guarded(validate, "dispatch")) { failure(generation); return; }
                call(generation, {service:destination, path:"/VirtualDesktopManager",
                    iface:"org.freedesktop.DBus.Properties", member:"Set", signature:"(ssv)",
                    arguments:["org.kde.KWin.VirtualDesktopManager", "current", new DBus.variant(targetId)]}, () => {
                        setReplied(requestId, destination);
                        if (!live(generation)) return;
                        getCurrent(generation, destination, observedCurrent => getOwner(generation, finalOwner => {
                            if (destination !== finalOwner || !guarded(validate, "observe") || !live(generation)) { failure(generation); return; }
                            internal.operation = null;
                            timeout.stop();
                            readback(requestId, observedCurrent, destination);
                        }));
                    });
            });
        });
        return true;
    }
    function cancel(requestId) {
        if (!internal.operation || internal.operation.requestId !== requestId) return;
        internal.operation = null;
        internal.generation++;
        timeout.stop();
    }
    function sourceChanged() {
        const fingerprint = contexts ? JSON.stringify({desktop:contexts.snapshot.desktop, desktops:contexts.snapshot.desktops}) : "";
        if (fingerprint === internal.fingerprint) return;
        internal.fingerprint = fingerprint;
        if (!sourceReady()) invalidate(active ? "unavailable" : "inactive");
        // Compatible model updates do not revoke the qualified capability. Every
        // explicit request still checks fresh owner/current before its one Set.
        else if (active && internal.status === "ready") return;
        else if (active && (!internal.operation || internal.operation.requestId < 0)) {
            invalidate("loading");
            probe();
        }
    }
    Connections { target:root.contexts; function onSnapshotChanged() { root.sourceChanged(); } }
    Timer { id:timeout; interval:Math.max(1, root.requestTimeoutMs); onTriggered:root.invalidate("unavailable") }
    onActiveChanged: { invalidate(active ? "loading" : "inactive"); if (active) probe(); }
    onTransportChanged: { invalidate(active ? "loading" : "inactive"); if (active) probe(); }
    onContextsChanged: sourceChanged()
    Component.onCompleted: { internal.completed = true; sourceChanged(); if (active) probe(); }
    Component.onDestruction: invalidate("inactive")
}
