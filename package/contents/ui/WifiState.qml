import QtQuick

// Portable Wi-Fi state: the radio and the networks in range. NativeWifi.qml
// uses Plasma's network applet library. A request completes only when
// NetworkManager reports the requested state, so Orla never shows Wi-Fi on or
// off, or a network joined or left, when it is not.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, enabled, hardwareEnabled, network, networks: [{id, name, strength,
    //  secured, saved, state}], wired: {connected, name}}, setEnabled(on), joinNetwork(id), leaveNetwork(id) -> bool,
    //  scan(), signal joinFailed(id, message)}
    property var backend: null
    property int confirmationTimeout: 3000
    // Joining waits for association and DHCP, and maybe a password typed in KDE's dialog.
    property int joinTimeout: 45000
    readonly property int maximumNetworks: 12

    readonly property var snapshot: active && backend ? backend.snapshot : null
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property bool enabled: _validated.enabled
    // A hardware switch or rfkill block: software cannot turn the radio on.
    readonly property bool hardwareEnabled: _validated.hardwareEnabled
    readonly property string network: _validated.network
    // In range, connected first, then saved, then by signal; empty while the radio is off.
    readonly property var networks: _validated.networks
    // An active cable connection ({connected, name}); shown even without a Wi-Fi adapter.
    readonly property var wired: _validated.wired
    property string joining: ""
    property string joiningName: ""
    property string leaving: ""
    property string leavingName: ""
    property string networkError: ""
    readonly property bool presentation: pending ? desired : enabled
    property bool pending: false
    property bool desired: false
    property string error: ""

    signal confirmed(bool on)
    signal networkJoined(string name)
    signal networkLeft(string name)

    readonly property var _validated: validate(snapshot)

    function bounded(value, maximum) {
        return String(value || "").slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function validateNetworks(list) {
        if (!Array.isArray(list)) return [];
        const seen = {};
        const out = [];
        for (let index = 0; index < Math.min(list.length, 64); ++index) {
            const item = list[index];
            if (!item || typeof item !== "object") continue;
            const id = String(item.id || "").slice(0, 256);
            const name = bounded(item.name, 64);
            // Hidden networks have no name to show; KDE's settings handle them.
            if (!id || !name || seen[id]) continue;
            if (["connected", "connecting", "available"].indexOf(item.state) < 0) continue;
            seen[id] = true;
            const strength = Math.max(0, Math.min(100, Math.round(Number(item.strength) || 0)));
            out.push({id: id, name: name, strength: strength, secured: item.secured === true,
                saved: item.saved === true, state: item.state});
        }
        const rank = item => item.state === "connected" ? 0 : item.state === "connecting" ? 1 : item.saved ? 2 : 3;
        out.sort((a, b) => rank(a) - rank(b) || b.strength - a.strength || a.name.localeCompare(b.name));
        return out.slice(0, maximumNetworks);
    }
    function validateWired(value) {
        if (!value || typeof value !== "object" || value.connected !== true) return {connected: false, name: ""};
        return {connected: true, name: bounded(value.name, 64)};
    }
    function validate(value) {
        const none = {status: "unavailable", enabled: false, hardwareEnabled: false, network: "", networks: [],
            wired: {connected: false, name: ""}};
        if (!value || typeof value !== "object") return Object.assign({}, none, {status: "loading"});
        if (value.status === "loading" || value.status === "absent")
            return Object.assign({}, none, {status: value.status, wired: validateWired(value.wired)});
        if (value.status !== "ready" || typeof value.enabled !== "boolean" || typeof value.hardwareEnabled !== "boolean")
            return none;
        const networks = value.enabled ? validateNetworks(value.networks) : [];
        const current = networks.find(item => item.state === "connected");
        // The applet's SSID can lag behind the list; either one names the network.
        const network = bounded(value.network, 64) || (current ? current.name : "");
        return {status: "ready", enabled: value.enabled, hardwareEnabled: value.hardwareEnabled,
            network: value.enabled ? network : "", networks: networks, wired: validateWired(value.wired)};
    }
    function find(id) {
        return networks.find(item => item.id === id) || null;
    }
    // A user action: ask NetworkManager to join. KDE's own agent asks for any password.
    function join(id) {
        if (status !== "ready" || !enabled || joining || leaving) return false;
        const target = find(id);
        if (!target) return false;
        networkError = "";
        if (target.state === "connected") return true;
        let accepted = false;
        try { accepted = Boolean(backend.joinNetwork(id)); } catch (_) { accepted = false; }
        if (!accepted) {
            networkError = qsTr("O NetworkManager recusou a conexão com %1.").arg(target.name);
            return false;
        }
        joining = id;
        joiningName = target.name;
        joinTimer.restart();
        observeNetworks();
        return true;
    }
    function leave(id) {
        if (status !== "ready" || joining || leaving) return false;
        const target = find(id);
        if (!target || target.state !== "connected") return false;
        networkError = "";
        let accepted = false;
        try { accepted = Boolean(backend.leaveNetwork(id)); } catch (_) { accepted = false; }
        if (!accepted) {
            networkError = qsTr("O NetworkManager recusou a desconexão de %1.").arg(target.name);
            return false;
        }
        leaving = id;
        leavingName = target.name;
        joinTimer.restart();
        observeNetworks();
        return true;
    }
    // Opening the network list may ask for a fresh scan; it changes nothing.
    function scan() {
        if (status !== "ready" || !enabled || !backend || typeof backend.scan !== "function") return false;
        try { backend.scan(); } catch (_) { return false; }
        return true;
    }
    function observeNetworks() {
        // One validated reading, as in observe(); `networks` may still be notifying.
        const current = _validated.networks;
        // Joining a new network changes its id (access point -> saved connection): match by name.
        if (joiningName && current.some(item => item.name === joiningName && item.state === "connected")) {
            const name = joiningName;
            resetNetworkRequest();
            networkJoined(name);
        } else if (leavingName && !current.some(item => item.name === leavingName && item.state === "connected")) {
            const name = leavingName;
            resetNetworkRequest();
            networkLeft(name);
        }
    }
    function failNetwork(message) {
        if (!joining && !leaving) return;
        const name = joiningName || leavingName;
        const wasJoining = Boolean(joining);
        resetNetworkRequest();
        const detail = bounded(message, 160);
        networkError = wasJoining
            ? (detail ? qsTr("Não foi possível conectar a %1: %2").arg(name).arg(detail)
                      : qsTr("Não foi possível conectar a %1.").arg(name))
            : qsTr("Não foi possível desconectar de %1.").arg(name);
    }
    function resetNetworkRequest() {
        joining = "";
        joiningName = "";
        leaving = "";
        leavingName = "";
        joinTimer.stop();
    }
    // A user action only; opening the Control Center never changes the radio.
    function request(on) {
        if (status !== "ready" || pending) return false;
        const want = Boolean(on);
        error = "";
        if (want === enabled) return true;
        if (want && !hardwareEnabled) {
            error = qsTr("O Wi-Fi está desligado por uma chave do computador.");
            return false;
        }
        desired = want;
        pending = true;
        confirmation.restart();
        let accepted = false;
        try { accepted = Boolean(backend.setEnabled(want)); } catch (_) { accepted = false; }
        if (!accepted) {
            reset();
            error = qsTr("O NetworkManager recusou a alteração do Wi-Fi.");
            return false;
        }
        observe();
        return true;
    }
    function observe() {
        if (!pending || !active || !backend) return;
        // One validated reading: derived properties may still be notifying.
        const reading = _validated;
        if (reading.status !== "ready" || reading.enabled !== desired) return;
        const value = desired;
        reset();
        confirmed(value);
    }
    function reset() {
        pending = false;
        confirmation.stop();
        error = "";
    }
    Timer {
        id: confirmation
        interval: root.confirmationTimeout
        onTriggered: {
            if (!root.pending) return;
            root.reset();
            // NetworkManager may also refuse silently, for example by policy.
            root.error = qsTr("O NetworkManager não confirmou a alteração do Wi-Fi.");
        }
    }
    Timer {
        id: joinTimer
        interval: root.joinTimeout
        onTriggered: {
            if (root.joining) {
                const name = root.joiningName;
                root.resetNetworkRequest();
                root.networkError = qsTr("%1 ainda não confirmou a conexão. Se o KDE pediu uma senha, conclua por lá.").arg(name);
            } else if (root.leaving) {
                const name = root.leavingName;
                root.resetNetworkRequest();
                root.networkError = qsTr("O NetworkManager não confirmou a desconexão de %1.").arg(name);
            }
        }
    }
    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onJoinFailed(id, message) { root.failNetwork(message); }
    }
    on_ValidatedChanged: { observe(); observeNetworks(); }
    onActiveChanged: if (!active) { reset(); resetNetworkRequest(); networkError = ""; }
    onBackendChanged: { reset(); resetNetworkRequest(); networkError = ""; }
}
