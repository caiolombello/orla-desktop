import QtQml
import org.kde.kcmutils as KCMUtils
import org.kde.plasma.workspace.dbus as DBus

// Plasma 6.7.5 modules; KCMLauncher API provided by KF 6.30.0 locally.
QtObject {
    function openSystemSettings(name) {
        KCMUtils.KCMLauncher.openSystemSettings(name);
    }
    // Invokes KWin's own Overview shortcut, whatever keys the user bound to it.
    function showOverview() {
        DBus.SessionBus.asyncCall({service: "org.kde.kglobalaccel", path: "/component/kwin",
            iface: "org.kde.kglobalaccel.Component", member: "invokeShortcut", signature: "(s)",
            arguments: ["Overview"]}, () => {}, () => {});
    }
}
