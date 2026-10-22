import QtQuick
import org.kde.plasma.workspace.dbus as DBus
import "../code/ThemeFile.js" as ThemeFile

// The portable state owns selection and callbacks; Plasma supplies only transport.
IntegrationState {
    // Quota comes from an active quota-usage addon when there is one.
    addonQuotaEnabled: true
    transport: QtObject {
        function asyncCall(message, resolve, reject) {
            DBus.SessionBus.asyncCall(message, reply => resolve({value: ThemeFile.replyText(reply)}), reject);
        }
    }
}
