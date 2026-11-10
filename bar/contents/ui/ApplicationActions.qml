import QtQuick

// Application menu actions, as in the macOS menu bar's app menu. The provider is
// the application backend; one without these functions offers no menu at all.
Item {
    id: root
    // {captureActions(), hide(), hideOthers(), showAll(), quit()}
    property var provider: null
    readonly property var names: ["hide", "hideOthers", "showAll", "quit"]
    readonly property bool available: Boolean(provider) && typeof provider.captureActions === "function"
        && names.every(name => typeof provider[name] === "function")
    // Windows each action would reach, as counted when the menu opened.
    property var summary: ({hide: 0, hideOthers: 0, showAll: 0, quit: 0})
    property string error: ""

    function count(value) {
        const number = Number(value);
        return Number.isFinite(number) && number > 0 ? Math.min(Math.floor(number), 999) : 0;
    }
    // Called as the menu opens, before its window takes the focus from the app.
    function capture() {
        let counted = null;
        error = "";
        if (available) {
            try { counted = provider.captureActions(); }
            catch (_) { counted = null; }
        }
        summary = {hide: count(counted && counted.hide), hideOthers: count(counted && counted.hideOthers),
            showAll: count(counted && counted.showAll), quit: count(counted && counted.quit)};
    }
    function can(action) {
        return available && names.indexOf(action) !== -1 && summary[action] > 0;
    }
    // True means handed to KDE, never an observed result. No automatic retry.
    function request(action) {
        error = "";
        if (!can(action)) return false;
        try {
            provider[action]();
            return true;
        } catch (_) {
            error = qsTr("Não foi possível enviar a ação ao KDE. Tente novamente.");
            return false;
        }
    }
    onProviderChanged: {
        error = "";
        summary = {hide: 0, hideOthers: 0, showAll: 0, quit: 0};
    }
}
