import QtQuick

// Closed dispatcher contract. A backend is injected; native KDE loading is
// owned by DockView so tests and closed popups never import or retain it.
QtObject {
    id: root
    required property var backend

    function target(kind) {
        if (kind === "sound") return "kcm_pulseaudio";
        if (kind === "power") return "kcm_powerdevilprofilesconfig";
        if (kind === "network") return "kcm_networkmanagement";
        if (kind === "bluetooth") return "kcm_bluetooth";
        if (kind === "all") return "";
        return null;
    }
    function open(kind) {
        // KWin's Overview, the counterpart of Mission Control.
        if (kind === "overview") {
            if (!backend || typeof backend.showOverview !== "function") return false;
            try {
                backend.showOverview();
                return true;
            } catch (_) {
                return false;
            }
        }
        const destination = target(kind);
        if (destination === null || !backend || typeof backend.openSystemSettings !== "function") return false;
        try {
            backend.openSystemSettings(destination);
            // Dispatched only; the backend does not confirm that a window opened.
            return true;
        } catch (_) {
            return false;
        }
    }
}
