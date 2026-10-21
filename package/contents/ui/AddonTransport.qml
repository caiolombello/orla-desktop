import QtQuick
import org.kde.plasma.workspace.dbus as DBus

// AddonManagerState builds typed messages and owns all callback lifetimes.
QtObject {
    function asyncCall(message, resolve, reject) {
        DBus.SessionBus.asyncCall(message, resolve, reject);
    }
}
