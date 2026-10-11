import QtQuick
import org.kde.plasma.workspace.dbus as DBus
import "../code/Battery.js" as Battery

// Read-only system aggregate. The caller opts in with active=true.
// KDE callback API verified against Plasma 6.7.5 dbusconnection.h/cpp.
Item {
    id: root
    property bool active: false
    // Test seam only: null uses the real system bus. Implement asyncCall(message,
    // resolve, reject), returning the same {value: ...} reply as Plasma DBus.
    property var transport: null
    property int refreshIntervalMs: 30000
    property int requestTimeoutMs: 5000

    readonly property bool loading: internal.loading
    // inactive/loading/ready/absent/unavailable. Only ready has a percentage.
    readonly property string status: internal.snapshot.status
    readonly property real percent: internal.snapshot.percent
    readonly property bool percentKnown: status === "ready" && percent >= 0
    // charging/not-charging/unknown; pending charge is not active charging.
    readonly property string charging: internal.snapshot.charging
    readonly property string state: internal.snapshot.state
    // battery/ac/unknown, based on UPower.OnBattery rather than charging state.
    readonly property string onBattery: internal.snapshot.onBattery
    readonly property real estimatedTimeSeconds: internal.snapshot.estimatedTimeSeconds
    readonly property string estimatedTimeKind: internal.snapshot.estimatedTimeKind
    readonly property string summary: status === "absent" ? qsTr("Sem bateria do sistema")
        : status === "loading" ? qsTr("Lendo bateria…")
        : percentKnown ? Math.round(percent) + "%"
        : qsTr("Bateria indisponível")

    QtObject {
        id: internal
        property bool completed: false
        property bool loading: false
        property int generation: 0
        property var snapshot: Battery.empty("inactive")

        function invalidate(nextStatus) {
            internal.generation++;
            timeout.stop();
            internal.loading = false;
            internal.snapshot = Battery.empty(nextStatus);
        }
        function current(generation) {
            return root.active && internal.loading && generation === internal.generation;
        }
        function finish(generation, snapshot) {
            if (!current(generation)) return;
            timeout.stop();
            internal.generation++;
            internal.snapshot = snapshot;
            internal.loading = false;
        }
        function request(generation, path, iface, member, signature, args, accept) {
            const message = {service: "org.freedesktop.UPower", path: path, iface: iface,
                member: member, signature: signature, arguments: args};
            const resolve = reply => {
                if (!current(generation)) return;
                if (!reply || reply.value === undefined) {
                    finish(generation, Battery.empty("unavailable"));
                    return;
                }
                accept(reply.value);
            };
            const reject = () => finish(generation, Battery.empty("unavailable"));
            try {
                if (root.transport !== null) root.transport.asyncCall(message, resolve, reject);
                else DBus.SystemBus.asyncCall(message, resolve, reject);
            } catch (_) {
                reject();
            }
        }
        function refresh() {
            if (!root.active || internal.loading || !internal.completed) return false;
            internal.generation++;
            const generation = internal.generation;
            internal.snapshot = Battery.empty("loading");
            internal.loading = true;
            timeout.restart();
            request(generation, "/org/freedesktop/UPower", "org.freedesktop.UPower",
                "GetDisplayDevice", "()", [], value => {
                    // Plasma decodes object paths as DBus.objectPath value types.
                    const path = typeof value === "string" ? value
                        : value && typeof value.toString === "function" ? value.toString() : "";
                    // UPower guarantees this aggregate path. Reject all other paths;
                    // no peripheral discovery or arbitrary service/path access.
                    if (path !== "/org/freedesktop/UPower/devices/DisplayDevice") {
                        finish(generation, Battery.empty("unavailable"));
                        return;
                    }
                    request(generation, path, "org.freedesktop.DBus.Properties", "GetAll",
                        "(s)", ["org.freedesktop.UPower.Device"], properties => {
                            const snapshot = Battery.display(properties);
                            if (snapshot.status !== "ready") {
                                finish(generation, snapshot);
                                return;
                            }
                            request(generation, "/org/freedesktop/UPower", "org.freedesktop.DBus.Properties",
                                "Get", "(ss)", ["org.freedesktop.UPower", "OnBattery"], onBattery => {
                                    if (typeof onBattery !== "boolean") {
                                        finish(generation, Battery.empty("unavailable"));
                                        return;
                                    }
                                    snapshot.onBattery = onBattery ? "battery" : "ac";
                                    finish(generation, snapshot);
                                });
                        });
                });
            return true;
        }
    }

    function refresh() { return internal.refresh(); }

    onActiveChanged: {
        internal.invalidate(active ? "loading" : "inactive");
        if (active) refresh();
    }
    onTransportChanged: {
        internal.invalidate(active ? "loading" : "inactive");
        if (active) refresh();
    }
    Component.onCompleted: {
        internal.completed = true;
        if (active) refresh();
    }
    Component.onDestruction: internal.invalidate("inactive")
    Timer {
        id: timeout
        interval: Math.max(100, Math.min(10000, root.requestTimeoutMs))
        repeat: false
        onTriggered: internal.invalidate("unavailable")
    }
    Timer {
        interval: Math.max(15000, Math.min(300000, root.refreshIntervalMs))
        running: root.active
        repeat: true
        onTriggered: root.refresh()
    }
}
