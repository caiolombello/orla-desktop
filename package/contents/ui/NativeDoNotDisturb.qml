import QtQuick
import org.kde.notificationmanager as NotificationManager

// Production-only adapter for Plasma's Do Not Disturb. It uses the same
// settings and rules as Plasma's notification applet, so both toggles are one
// state; the applet computes the server's `inhibited`, which confirms changes.
Item {
    id: root
    visible: false
    property int revision: 0
    readonly property var snapshot: buildSnapshot(revision)

    function changed() { revision += 1; }
    function buildSnapshot(witness) {
        if (!NotificationManager.Server.valid)
            return {status: "unavailable", inhibited: false, until: 0, byApplication: false, applications: []};
        const until = settings.notificationsInhibitedUntil;
        const time = until && !isNaN(until.getTime()) ? until.getTime() : 0;
        return {status: "ready", inhibited: Boolean(NotificationManager.Server.inhibited), until: time,
            byApplication: Boolean(settings.notificationsInhibitedByApplication),
            applications: (settings.notificationInhibitionApplications || []).slice(0, 8).map(String)};
    }
    function setDoNotDisturb(on) {
        if (on) {
            // "Until turned off", as Plasma's own toggle does it.
            const date = new Date();
            date.setFullYear(date.getFullYear() + 1);
            settings.notificationsInhibitedUntil = date;
        } else {
            settings.notificationsInhibitedUntil = undefined;
            settings.revokeApplicationInhibitions();
        }
        settings.save();
        return true;
    }

    NotificationManager.Settings {
        id: settings
        onNotificationsInhibitedUntilChanged: root.changed()
        onNotificationsInhibitedByApplicationChanged: root.changed()
        onNotificationInhibitionApplicationsChanged: root.changed()
    }
    Connections {
        target: NotificationManager.Server
        function onInhibitedChanged() { root.changed(); }
        function onValidChanged() { root.changed(); }
    }
}
