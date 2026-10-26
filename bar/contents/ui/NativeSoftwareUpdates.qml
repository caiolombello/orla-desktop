import QtQuick
import org.kde.plasma.workspace.dbus as DBus
import org.kde.plasma.plasma5support as P5Support

// Reads the tray items registered with KDE's StatusNotifierWatcher, isolated
// by Loader. Verified against Plasma 6.7.5 and Discover 6.7.5: the update
// notifier registers an item only when it has something to report, and its
// icon names the state.
// https://invent.kde.org/plasma/discover/-/blob/v6.7.5/notifier/DiscoverNotifier.cpp
// https://invent.kde.org/plasma/discover/-/blob/v6.7.5/notifier/NotifierItem.cpp
Item {
    id: root
    property string systemState: "unknown"
    property bool steamRunning: false
    // "service/path" of Discover's tray item, when there is one.
    property string discoverItem: ""
    property int generation: 0
    readonly property var icons: ({"update-low": "updates", "update-high": "security",
        "system-reboot-update": "reboot", "update-busy": "busy", "offline": "offline"})

    // Plasma's decoder wraps QString in DBus.string.
    function text(value) {
        if (typeof value === "string") return value;
        return value && typeof value.value === "string" ? value.value : "";
    }
    function split(item) {
        const slash = item.indexOf("/");
        return slash > 0 ? {service: item.slice(0, slash), path: item.slice(slash)} : null;
    }
    function get(item, property, done) {
        const target = split(item);
        if (!target) { done(""); return; }
        DBus.SessionBus.asyncCall({service: target.service, path: target.path,
            iface: "org.freedesktop.DBus.Properties", member: "Get", signature: "(ss)",
            arguments: ["org.kde.StatusNotifierItem", property]},
            reply => done(text(reply ? reply.value : "")), () => done(""));
    }
    function clear() {
        systemState = "unknown";
        steamRunning = false;
        discoverItem = "";
    }
    function refresh() {
        const current = ++generation;
        DBus.SessionBus.asyncCall({service: "org.kde.StatusNotifierWatcher", path: "/StatusNotifierWatcher",
            iface: "org.freedesktop.DBus.Properties", member: "Get", signature: "(ss)",
            arguments: ["org.kde.StatusNotifierWatcher", "RegisteredStatusNotifierItems"]}, reply => {
                if (current !== generation) return;
                const list = reply ? reply.value : null;
                const items = [];
                for (let index = 0; list && typeof list.length === "number" && index < Math.min(list.length, 64); index++) {
                    const item = text(list[index]);
                    if (/^[:A-Za-z0-9._-]{1,255}\/[A-Za-z0-9_\/]{1,255}$/.test(item)) items.push(item);
                }
                let pending = items.length, discover = "", steam = false;
                const finish = () => {
                    if (current !== generation) return;
                    steamRunning = steam;
                    discoverItem = discover;
                    if (!discover) { systemState = "unknown"; return; }
                    get(discover, "IconName", icon => {
                        if (current === generation) systemState = root.icons[icon] || "unknown";
                    });
                };
                if (pending === 0) { finish(); return; }
                items.forEach(item => get(item, "Id", id => {
                    if (current !== generation) return;
                    if (id === "steam") steam = true;
                    else if (/(^|_)org\.kde\.DiscoverNotifier$/.test(id)) discover = item;
                    if (--pending === 0) finish();
                }));
            }, () => { if (current === generation) root.clear(); });
    }
    // Discover's own tray action: its update page, or the restart prompt when
    // updates wait for a reboot. Without an item, Discover opens on its updates.
    function openSystemUpdates() {
        const target = discoverItem ? split(discoverItem) : null;
        if (target) {
            DBus.SessionBus.asyncCall({service: target.service, path: target.path,
                iface: "org.kde.StatusNotifierItem", member: "Activate", signature: "(ii)", arguments: [0, 0]},
                () => {}, () => {});
            return true;
        }
        // Detached through the shell, so Discover outlives this data source.
        launcher.connectSource("plasma-discover --mode update >/dev/null 2>&1 &");
        return true;
    }
    function openSteamDownloads() {
        return Qt.openUrlExternally("steam://open/downloads");
    }
    P5Support.DataSource {
        id: launcher
        engine: "executable"
        onNewData: source => disconnectSource(source)
    }
    Component.onCompleted: refresh()
}
