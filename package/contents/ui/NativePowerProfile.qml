import QtQuick
import org.kde.plasma.workspace.dbus as DBus

// Production-only adapter for PowerDevil's power profiles, the service behind
// Plasma's battery applet. Everything goes over D-Bus: Plasma's
// PowerProfilesControl marks a profile active as soon as the call returns,
// which would confirm a change before the service applied it.
Item {
    id: root
    visible: false

    readonly property string service: "org.kde.Solid.PowerManagement"
    readonly property string path: "/org/kde/Solid/PowerManagement/Actions/PowerProfile"
    readonly property string iface: "org.kde.Solid.PowerManagement.Actions.PowerProfile"

    property int revision: 0
    // "loading" until the first reading, "absent" without a profile daemon.
    property string phase: "loading"
    property var profiles: []
    property string current: ""
    property string inhibitedReason: ""
    property string degradedReason: ""
    property var holds: []
    // Replies from an older connection are ignored.
    property int generation: 0
    signal writeFailed(string id)
    readonly property var snapshot: buildSnapshot(revision)

    function changed() { revision += 1; }
    function buildSnapshot(witness) {
        if (!watcher.registered) return {status: "unavailable"};
        if (phase !== "ready") return {status: phase};
        return {status: "ready", profiles: profiles.slice(), current: current, inhibitedReason: inhibitedReason,
            degradedReason: degradedReason, holds: holds.slice()};
    }
    function call(member, args, signature, done, failed) {
        DBus.SessionBus.asyncCall({service: service, path: path, iface: iface, member: member,
            signature: signature || "", arguments: args || []}, done, failed || (() => {}));
    }
    // The D-Bus module wraps strings in objects ({value}) and returns lists as
    // array-like sequences that fail Array.isArray; read both through these.
    function text(value) {
        if (value === undefined || value === null) return "";
        return String(typeof value === "object" && value.value !== undefined ? value.value : value);
    }
    function list(value) {
        if (Array.isArray(value)) return value;
        return value && typeof value === "object" && typeof value.length === "number" ? Array.from(value) : [];
    }
    function holdList(value) {
        // A reverse-DNS application ID reads better by its last part ("GameMode").
        return list(value).slice(0, 8).map(hold => ({
            application: text(hold && hold.ApplicationId).split(".").pop(), profile: text(hold && hold.Profile)}));
    }
    function reload() {
        const ticket = ++generation;
        if (!watcher.registered) { phase = "loading"; changed(); return; }
        // Without power-profiles-daemon the action is missing, so the choices call fails.
        call("profileChoices", [], "", reply => {
            if (ticket !== generation) return;
            profiles = list(reply.value).map(text);
            call("currentProfile", [], "", current => {
                if (ticket !== generation) return;
                root.current = text(current.value);
                phase = profiles.length ? "ready" : "absent";
                changed();
            }, () => { if (ticket === generation) { phase = "absent"; changed(); } });
        }, () => { if (ticket === generation) { phase = "absent"; changed(); } });
        call("performanceInhibitedReason", [], "", reply => {
            if (ticket === generation) { inhibitedReason = text(reply.value); changed(); }
        });
        call("performanceDegradedReason", [], "", reply => {
            if (ticket === generation) { degradedReason = text(reply.value); changed(); }
        });
        call("profileHolds", [], "", reply => {
            if (ticket === generation) { holds = holdList(reply.value); changed(); }
        });
    }
    function setProfile(id) {
        const profile = String(id);
        if (phase !== "ready" || profiles.indexOf(profile) < 0) return false;
        const ticket = generation;
        // The reply only means PowerDevil accepted the call; currentProfileChanged
        // (or the readback below, if that signal was missed) confirms the change.
        // The module takes the argument list as one parenthesized signature; plain "s"
        // sends no argument and PowerDevil answers UnknownMethod.
        call("setProfile", [profile], "(s)", () => {
            if (ticket !== generation) return;
            call("currentProfile", [], "", reply => {
                if (ticket === generation) { current = text(reply.value); changed(); }
            });
        }, () => { if (ticket === generation) root.writeFailed(profile); });
        return true;
    }

    DBus.DBusServiceWatcher {
        id: watcher
        busType: DBus.BusType.Session
        watchedService: root.service
        onRegisteredChanged: root.reload()
    }
    DBus.SignalWatcher {
        busType: DBus.BusType.Session
        service: root.service
        path: root.path
        iface: root.iface
        function dbuscurrentProfileChanged(profile) { root.current = root.text(profile); root.changed(); }
        function dbusprofileChoicesChanged(choices) {
            root.profiles = root.list(choices).map(root.text);
            if (root.phase !== "loading") root.phase = root.profiles.length ? "ready" : "absent";
            root.changed();
        }
        function dbusperformanceInhibitedReasonChanged(reason) { root.inhibitedReason = root.text(reason); root.changed(); }
        function dbusperformanceDegradedReasonChanged(reason) { root.degradedReason = root.text(reason); root.changed(); }
        function dbusprofileHoldsChanged(value) { root.holds = root.holdList(value); root.changed(); }
    }
    Component.onCompleted: reload()
}
