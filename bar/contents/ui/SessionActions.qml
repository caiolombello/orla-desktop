import QtQuick

// Internal alpha contract. Injecting a backend prevents loading native code.
Item {
    id: root
    property var backend: null
    property string hostVersion: Application.version
    readonly property bool supportedHost: /^6\.7\.[0-9]+(?:[-+].*)?$/.test(hostVersion)
    readonly property var provider: backend !== null ? backend : native.item
    readonly property string status: provider ? provider.status : native.status === Loader.Loading ? "loading" : "unavailable"
    readonly property bool nativeLoaded: native.item !== null
    property string error: ""

    function can(action) {
        if (!provider || provider.status !== "ready") return false;
        if (action === "lock") return provider.canLock === true;
        if (action === "suspend") return provider.canSuspend === true;
        if (action === "logout") return provider.canLogout === true;
        if (action === "reboot") return provider.canReboot === true;
        if (action === "shutdown") return provider.canShutdown === true;
        return false;
    }
    function request(action) {
        error = "";
        if (!can(action)) return false;
        try {
            if (action === "lock") provider.lock();
            else if (action === "suspend") provider.suspend();
            else if (action === "logout") provider.requestLogout();
            else if (action === "reboot") provider.requestReboot();
            else if (action === "shutdown") provider.requestShutdown();
            else return false;
            // True means dispatched, never observed success. No automatic retry.
            return true;
        } catch (_) {
            error = qsTr("Não foi possível enviar a ação ao KDE. Tente novamente.");
            return false;
        }
    }
    onProviderChanged: error = ""
    Loader {
        id: native
        active: root.backend === null && root.supportedHost
        source: active ? "NativeSession.qml" : ""
    }
}
