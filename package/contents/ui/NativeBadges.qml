import QtQuick
import org.kde.plasma.workspace.dbus as DBus
import "../code/ThemeFile.js" as ThemeFile

BadgeState {
    transport: QtObject {
        function asyncCall(message, resolve, reject) {
            DBus.SessionBus.asyncCall(message, reply => resolve({value: ThemeFile.replyText(reply)}), reject);
        }
    }
}
