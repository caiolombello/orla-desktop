import QtQuick
import org.kde.plasma.private.sessions as Sessions

// Private QML bridge verified against Plasma 6.7.5 and isolated by Loader.
// https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/libkworkspace/sessionmanagement.h
Item {
    readonly property string status: session.state === Sessions.SessionManagement.Ready ? "ready"
        : session.state === Sessions.SessionManagement.Loading ? "loading" : "unavailable"
    readonly property bool canLock: status === "ready" && session.canLock
    readonly property bool canSuspend: status === "ready" && session.canSuspend
    readonly property bool canLogout: status === "ready" && session.canLogout
    readonly property bool canReboot: status === "ready" && session.canReboot
    readonly property bool canShutdown: status === "ready" && session.canShutdown
    Sessions.SessionManagement { id: session }
    function lock() { if (canLock) session.lock(); }
    function suspend() { if (canSuspend) session.suspend(); }
    function requestLogout() { if (canLogout) session.requestLogout(Sessions.SessionManagement.ForcePrompt); }
    function requestReboot() { if (canReboot) session.requestReboot(Sessions.SessionManagement.ForcePrompt); }
    function requestShutdown() { if (canShutdown) session.requestShutdown(Sessions.SessionManagement.ForcePrompt); }
}
