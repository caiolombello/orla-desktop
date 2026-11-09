import QtQml
import org.kde.taskmanager as TaskManager
import org.kde.plasma.workspace.dbus as DBus

// Plasma 6.8 backend for DockAppActions. Plasma's own task manager opens
// "Show all windows" the same way: KWin's WindowView effect over D-Bus, given
// the windows' handles. The ExposeClass shortcut would only follow the active window.
QtObject {
    readonly property var desktopIds: desktopInfo.desktopIds
    readonly property var desktopNames: desktopInfo.desktopNames
    readonly property bool windowViewAvailable: windowViewWatcher.registered
    property TaskManager.VirtualDesktopInfo desktopInfo: TaskManager.VirtualDesktopInfo {}
    property DBus.DBusServiceWatcher windowViewWatcher: DBus.DBusServiceWatcher {
        busType: DBus.BusType.Session
        watchedService: "org.kde.KWin.Effect.WindowView1"
    }
    function showWindowView(handles) {
        DBus.SessionBus.asyncCall({service: "org.kde.KWin.Effect.WindowView1",
            path: "/org/kde/KWin/Effect/WindowView1", iface: "org.kde.KWin.Effect.WindowView1",
            member: "activate", signature: "(as)", arguments: [handles.map(String)]}, () => {}, () => {});
    }
}
