import QtQuick
import org.kde.plasma.workspace.dbus as DBus
import "../code/ThemeFile.js" as ThemeFile

// AppearanceState owns request lifetime and validates the returned string.
QtObject {
    function loadThemeFile(encodedUrl, resolve, reject) {
        const message = {service: "org.orla.Themes", path: "/org/orla/Themes",
            iface: "org.orla.Themes1", member: "LoadThemeFile", signature: "(s)", arguments: [encodedUrl]};
        DBus.SessionBus.asyncCall(message, reply => resolve(ThemeFile.replyText(reply)), reject);
    }
}
