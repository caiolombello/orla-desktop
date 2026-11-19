import QtQuick
import "../code/Badges.js" as Badges

// Polls the integration service for the unread counts of the apps in the dock.
// Plasma supplies the transport; fixtures inject their own.
Item {
    id: root
    property bool active: false
    property var transport: null
    // Returns the desktop IDs currently shown; read on every poll.
    property var idsProvider: function() { return []; }
    property int interval: 2000
    property string status: "idle"
    property var counts: ({})
    property var callbackLifetime: ({alive: true})
    property int generation: 0
    property bool pending: false

    function countFor(desktopId) {
        const value = counts[desktopId];
        return active && Number.isInteger(value) ? value : 0;
    }
    function clear() {
        generation++;
        pending = false;
        counts = ({});
        status = "idle";
    }
    function refresh() {
        if (!active || pending || transport === null) return;
        const ids = Badges.query(idsProvider());
        if (!ids.length) { counts = ({}); status = "ready"; return; }
        const operation = generation;
        const lifetime = callbackLifetime;
        const message = {service: "org.caiodock.Integrations", path: "/org/caiodock/Integrations",
            iface: "org.caiodock.Integrations1", member: "BadgeCounts", signature: "(as)", arguments: [ids]};
        pending = true;
        const done = reply => {
            if (!lifetime.alive || operation !== generation) return;
            pending = false;
            const parsed = reply ? Badges.parse(reply.value, ids) : null;
            // A service without this method (older install) or a bad reply means no badges.
            counts = parsed ? parsed.counts : ({});
            status = parsed ? parsed.status : "unavailable";
        };
        try { transport.asyncCall(message, done, () => done(null)); }
        catch (_) { done(null); }
    }
    onActiveChanged: active ? refresh() : clear()
    Component.onCompleted: if (active) refresh()
    Component.onDestruction: callbackLifetime.alive = false
    Timer {
        interval: root.interval
        running: root.active
        repeat: true
        onTriggered: root.refresh()
    }
}
