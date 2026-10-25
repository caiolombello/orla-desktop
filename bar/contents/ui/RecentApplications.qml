import QtQuick

// Recently used applications for the Orla Menu, as in the Apple menu's
// "Recent Items". Injecting a backend prevents loading the native model.
// Items carry the app's desktop-file ID, so a launch reaches the app that was shown.
Item {
    id: root
    property var backend: null
    property string hostVersion: Application.version
    // The native model only loads while the menu is offered.
    property bool wanted: true
    readonly property int limit: 5
    readonly property bool supportedHost: /^6\.7\.[0-9]+(?:[-+].*)?$/.test(hostVersion)
    readonly property var provider: backend !== null ? backend : native.item
    readonly property bool nativeLoaded: native.item !== null
    readonly property var items: bounded(provider && provider.status === "ready" ? provider.items : [])
    property string error: ""

    function plain(value, maximum) {
        return String(value || "").replace(/\s+/g, " ").trim().slice(0, maximum);
    }
    // A JS array or a list property from C++; only the first rows are read.
    function bounded(list) {
        if (!list || typeof list.length !== "number") return [];
        const result = [];
        for (let row = 0; row < Math.min(list.length, 32) && result.length < limit; row++) {
            const item = list[row];
            if (!item || typeof item.id !== "string" || !/^[A-Za-z0-9._+-]{1,200}\.desktop$/.test(item.id)) continue;
            const name = plain(item.name, 80);
            if (!name) continue;
            const icon = typeof item.icon === "string" && /^[A-Za-z0-9._+-]{1,128}$/.test(item.icon) ? item.icon : "";
            result.push({id: item.id, name: name, icon: icon});
        }
        return result;
    }
    // True means the launch was handed to KDE, not that the app started.
    function launch(id) {
        error = "";
        if (!provider || !items.some(item => item.id === id)) return false;
        try {
            if (provider.launch(id) === true) return true;
        } catch (_) {}
        error = qsTr("Não foi possível abrir o aplicativo.");
        return false;
    }
    onProviderChanged: error = ""
    Loader {
        id: native
        active: root.wanted && root.backend === null && root.supportedHost
        source: active ? "NativeRecentApplications.qml" : ""
    }
}
