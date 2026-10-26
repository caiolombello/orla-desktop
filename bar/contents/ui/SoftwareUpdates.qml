import QtQuick

// Software updates for the Orla Menu, as the Apple menu flags them beside
// System Settings. The system state is the one KDE's Discover notifier reports;
// Orla never counts, downloads or installs packages. Game downloads stay in
// Steam. Injecting a backend prevents loading the native reader.
Item {
    id: root
    property var backend: null
    property string hostVersion: Application.version
    // The native reader only loads while the menu is offered.
    property bool wanted: true
    readonly property bool supportedHost: /^6\.7\.[0-9]+(?:[-+].*)?$/.test(hostVersion)
    readonly property var provider: backend !== null ? backend : native.item
    readonly property bool nativeLoaded: native.item !== null
    // "unknown" also covers "nothing reported": Discover shows no tray item when
    // the system is up to date, and Orla cannot tell that apart from no notifier.
    readonly property var states: ["unknown", "updates", "security", "reboot", "busy", "offline"]
    readonly property string systemState: provider && states.indexOf(provider.systemState) >= 0
        ? provider.systemState : "unknown"
    readonly property bool steamRunning: Boolean(provider && provider.steamRunning === true)
    readonly property string badge: systemState === "updates" ? qsTr("Disponíveis")
        : systemState === "security" ? qsTr("Segurança")
        : systemState === "reboot" ? qsTr("Reiniciar")
        : systemState === "busy" ? qsTr("Instalando…")
        : systemState === "offline" ? qsTr("Sem rede") : ""
    readonly property string description: systemState === "updates" ? qsTr("Atualizações disponíveis")
        : systemState === "security" ? qsTr("Atualizações de segurança disponíveis")
        : systemState === "reboot" ? qsTr("Reinicie para instalar as atualizações")
        : systemState === "busy" ? qsTr("Instalando atualizações automáticas")
        : systemState === "offline" ? qsTr("Sem rede para procurar atualizações") : ""
    property string error: ""

    function refresh() {
        if (!provider || typeof provider.refresh !== "function") return;
        try { provider.refresh(); } catch (_) {}
    }
    function call(name, message) {
        error = "";
        if (provider && typeof provider[name] === "function") {
            try {
                if (provider[name]() === true) return true;
            } catch (_) {}
        }
        error = message;
        return false;
    }
    // True means the request was handed to KDE or Steam, not that a window opened.
    function openSystemUpdates() {
        return call("openSystemUpdates", qsTr("Não foi possível abrir as atualizações do sistema."));
    }
    function openSteamDownloads() {
        return steamRunning && call("openSteamDownloads", qsTr("Não foi possível abrir os downloads do Steam."));
    }
    onProviderChanged: error = ""
    Loader {
        id: native
        active: root.wanted && root.backend === null && root.supportedHost
        source: active ? "NativeSoftwareUpdates.qml" : ""
    }
}
