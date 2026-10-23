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
        if (kind === "all") return "";
        return null;
    }
    function open(kind) {
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
