import QtQuick
import org.kde.plasma.workspace.dbus as DBus
import "../code/ThemeFile.js" as ThemeFile

// The portable state owns selection and callbacks; Plasma supplies only transport.
IntegrationState {
    transport: QtObject {
        function asyncCall(message, resolve, reject) {
            DBus.SessionBus.asyncCall(message, reply => resolve({value: ThemeFile.replyText(reply)}), reject);
        }
    }
}
