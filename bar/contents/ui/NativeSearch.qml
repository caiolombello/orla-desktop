import QtQml
import org.kde.plasma.workspace.dbus as DBus

// The bar's search button. The Orla Launcher's managed service owns
// org.orla.Launcher and its "orla-search-open" shortcut; without it, KRunner
// opens instead (D-Bus activated, so it needs nothing running).
QtObject {
    function invokeLauncher() {
        DBus.SessionBus.asyncCall({service: "org.kde.kglobalaccel", path: "/component/org_orla_Launcher",
            iface: "org.kde.kglobalaccel.Component", member: "invokeShortcut", signature: "(s)",
            arguments: ["orla-search-open"]}, () => {}, () => openKRunner());
    }
    function openKRunner() {
        DBus.SessionBus.asyncCall({service: "org.kde.krunner", path: "/App", iface: "org.kde.krunner.App",
            member: "display", signature: "", arguments: []}, () => {}, () => {});
    }
    // The module wraps replies as {value}; a plain bool is accepted too.
    function owned(reply) {
        return reply === true || Boolean(reply && reply.value === true);
    }
    function open() {
        DBus.SessionBus.asyncCall({service: "org.freedesktop.DBus", path: "/org/freedesktop/DBus",
            iface: "org.freedesktop.DBus", member: "NameHasOwner", signature: "(s)",
            arguments: ["org.orla.Launcher"]},
            reply => owned(reply) ? invokeLauncher() : openKRunner(), () => openKRunner());
    }
}
