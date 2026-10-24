import QtQuick

// Portable Bluetooth state: the radio and the paired devices. NativeBluetooth.qml
// uses BluezQt, as Plasma's Bluetooth applet does. A request completes only
// when BlueZ reports the requested state, so Orla never shows Bluetooth on or
// off, or a device connected or not, when it is not.
Item {
    id: root
    visible: false

    property bool active: false
    // {snapshot: {status, enabled, blocked, connected: [names], devices: [{id, name, icon,
    //  connected, battery}]}, setEnabled(on), connectDevice(id), disconnectDevice(id) -> bool,
    //  signal deviceFailed(id, message)}
    property var backend: null
    property int confirmationTimeout: 5000
    // Headsets may take a while to answer, and some ask to confirm on the device.
    property int deviceTimeout: 20000
    readonly property int maximumDevices: 12

    readonly property var snapshot: active && backend ? backend.snapshot : null
    readonly property string status: !active || !backend ? "inactive" : _validated.status
    readonly property bool enabled: _validated.enabled
    // Turned off by a radio block (rfkill), which Orla lifts the way Plasma does.
    readonly property bool blocked: _validated.blocked
    readonly property var connected: _validated.connected
    // Paired devices, connected first; empty while the radio is off.
    readonly property var devices: _validated.devices
    property string busyDevice: ""
    property bool busyWantsConnected: false
    property string busyName: ""
    property string deviceError: ""
    readonly property bool presentation: pending ? desired : enabled
    property bool pending: false
    property bool desired: false
    property string error: ""

    signal confirmed(bool on)
    signal deviceConfirmed(string name, bool connected)

    readonly property var _validated: validate(snapshot)

    function bounded(value, maximum) {
        return String(value || "").slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function validateDevices(list) {
        if (!Array.isArray(list)) return [];
        const seen = {};
        const out = [];
        for (let index = 0; index < Math.min(list.length, 64); ++index) {
            const item = list[index];
            if (!item || typeof item !== "object") continue;
            const id = String(item.id || "").slice(0, 256);
            const name = bounded(item.name, 64);
            if (!id || !name || seen[id] || typeof item.connected !== "boolean") continue;
            seen[id] = true;
            // Only freedesktop-style icon names reach Kirigami.Icon.
            const icon = /^[a-z0-9-]{1,64}$/.test(String(item.icon || "")) ? String(item.icon) : "preferences-system-bluetooth";
            const battery = Number.isInteger(item.battery) && item.battery >= 0 && item.battery <= 100 ? item.battery : -1;
            out.push({id: id, name: name, icon: icon, connected: item.connected, battery: battery});
        }
        out.sort((a, b) => Number(b.connected) - Number(a.connected) || a.name.localeCompare(b.name));
        return out.slice(0, maximumDevices);
    }
    function validate(value) {
        const none = {status: "unavailable", enabled: false, blocked: false, connected: [], devices: []};
        if (!value || typeof value !== "object") return Object.assign({}, none, {status: "loading"});
        if (value.status === "loading" || value.status === "absent") return Object.assign({}, none, {status: value.status});
        if (value.status !== "ready" || typeof value.enabled !== "boolean" || typeof value.blocked !== "boolean"
                || !Array.isArray(value.connected)) return none;
        const connected = value.connected.slice(0, 8)
            .map(name => String(name || "").slice(0, 64).replace(/\s+/g, " ").trim()).filter(name => name.length > 0);
        return {status: "ready", enabled: value.enabled, blocked: value.blocked, connected: value.enabled ? connected : [],
            devices: value.enabled ? validateDevices(value.devices) : []};
    }
    function findDevice(id) {
        return devices.find(item => item.id === id) || null;
    }
    // A user action: ask BlueZ to connect or disconnect a paired device.
    function setDeviceConnected(id, on) {
        if (status !== "ready" || !enabled || busyDevice) return false;
        const target = findDevice(id);
        if (!target) return false;
        const want = Boolean(on);
        deviceError = "";
        if (target.connected === want) return true;
        let accepted = false;
        try { accepted = Boolean(want ? backend.connectDevice(id) : backend.disconnectDevice(id)); } catch (_) { accepted = false; }
        if (!accepted) {
            deviceError = want ? qsTr("O serviço de Bluetooth recusou conectar %1.").arg(target.name)
                               : qsTr("O serviço de Bluetooth recusou desconectar %1.").arg(target.name);
            return false;
        }
        busyDevice = id;
        busyWantsConnected = want;
        busyName = target.name;
        deviceTimer.restart();
        observeDevices();
        return true;
    }
    function observeDevices() {
        if (!busyDevice) return;
        // One validated reading, as in observe().
        const target = _validated.devices.find(item => item.id === busyDevice);
        if (!target || target.connected !== busyWantsConnected) return;
        const name = busyName;
        const value = busyWantsConnected;
        resetDeviceRequest();
        deviceConfirmed(name, value);
    }
    function failDevice(id, message) {
        if (!busyDevice || (id && id !== busyDevice)) return;
        const name = busyName;
        const wanted = busyWantsConnected;
        resetDeviceRequest();
        const detail = bounded(message, 160);
        const base = wanted ? qsTr("Não foi possível conectar %1").arg(name) : qsTr("Não foi possível desconectar %1").arg(name);
        deviceError = detail ? qsTr("%1: %2").arg(base).arg(detail) : base + ".";
    }
    function resetDeviceRequest() {
        busyDevice = "";
        busyName = "";
        busyWantsConnected = false;
        deviceTimer.stop();
    }
    // A user action only; opening the Control Center never changes the radio.
    function request(on) {
        if (status !== "ready" || pending) return false;
        const want = Boolean(on);
        error = "";
        if (want === enabled) return true;
        desired = want;
        pending = true;
        confirmation.restart();
        let accepted = false;
        try { accepted = Boolean(backend.setEnabled(want)); } catch (_) { accepted = false; }
        if (!accepted) {
            reset();
            error = qsTr("O serviço de Bluetooth recusou a alteração.");
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
        // Lifting a radio block brings the adapter back before it powers on, so allow longer.
        interval: root.confirmationTimeout
        onTriggered: {
            if (!root.pending) return;
            root.reset();
            root.error = qsTr("O serviço de Bluetooth não confirmou a alteração.");
        }
    }
    Timer {
        id: deviceTimer
        interval: root.deviceTimeout
        onTriggered: {
            if (!root.busyDevice) return;
            const name = root.busyName;
            const wanted = root.busyWantsConnected;
            root.resetDeviceRequest();
            root.deviceError = wanted ? qsTr("%1 não confirmou a conexão.").arg(name)
                                      : qsTr("%1 não confirmou a desconexão.").arg(name);
        }
    }
    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onDeviceFailed(id, message) { root.failDevice(id, message); }
    }
    on_ValidatedChanged: { observe(); observeDevices(); }
    onActiveChanged: if (!active) { reset(); resetDeviceRequest(); deviceError = ""; }
    onBackendChanged: { reset(); resetDeviceRequest(); deviceError = ""; }
}
