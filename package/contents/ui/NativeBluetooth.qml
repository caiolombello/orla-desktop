import QtQuick
import org.kde.bluezqt as BluezQt

// Production-only adapter for the Bluetooth radio through BluezQt, as Plasma's
// Bluetooth applet uses it. Writes only ask BlueZ and rfkill; the properties
// change when the services report it, so they confirm instead of echoing.
Item {
    id: root
    visible: false
    property int revision: 0
    // id (BlueZ object path) -> device: the objects stay inside the adapter.
    property var devicesById: ({})
    readonly property var snapshot: buildSnapshot(revision)
    signal deviceFailed(string id, string message)

    function changed() { revision += 1; }
    function buildSnapshot(witness) {
        const manager = BluezQt.Manager;
        // BlueZ itself is not running (or not answering).
        if (!manager.operational) return {status: "unavailable"};
        const blocked = Boolean(manager.bluetoothBlocked);
        if (!blocked && manager.adapters.length === 0) return {status: "absent"};
        const connected = [];
        const devices = manager.connectedDevices;
        for (let index = 0; index < Math.min(devices.length, 8); ++index)
            connected.push(String(devices[index] && devices[index].name || "").slice(0, 64));
        const enabled = Boolean(manager.bluetoothOperational);
        return {status: "ready", enabled: enabled, blocked: blocked, connected: connected,
            devices: enabled ? readDevices(manager) : []};
    }
    // Paired devices only, as the macOS list shows; discovery and pairing stay in KDE.
    function readDevices(manager) {
        const found = [];
        const byId = {};
        const all = manager.devices;
        for (let index = 0; index < Math.min(all.length, 64); ++index) {
            const device = all[index];
            if (!device || !device.paired) continue;
            const id = String(device.ubi || "");
            if (!id) continue;
            byId[id] = device;
            const battery = device.battery ? Math.round(Number(device.battery.percentage)) : -1;
            found.push({id: id, name: String(device.name || device.friendlyName || "").slice(0, 64),
                icon: String(device.icon || ""), connected: Boolean(device.connected),
                battery: Number.isInteger(battery) ? battery : -1});
        }
        devicesById = byId;
        return found;
    }
    // BlueZ answers each call asynchronously; only a failure needs reporting,
    // since success shows up as the device's `connected` change.
    function watch(id, call) {
        if (!call) return;
        call.finished.connect(() => {
            if (call.error) root.deviceFailed(id, String(call.errorText || ""));
        });
    }
    function connectDevice(id) {
        const device = devicesById[id];
        if (!device || !BluezQt.Manager.bluetoothOperational) return false;
        watch(id, device.connectToDevice());
        return true;
    }
    function disconnectDevice(id) {
        const device = devicesById[id];
        if (!device) return false;
        watch(id, device.disconnectFromDevice());
        return true;
    }
    // The same two steps as Plasma's applet: lift or set the radio block, then
    // power every adapter on or off.
    function setEnabled(on) {
        const manager = BluezQt.Manager;
        if (!manager.operational) return false;
        const enable = Boolean(on);
        manager.bluetoothBlocked = !enable;
        const adapters = manager.adapters;
        for (let index = 0; index < adapters.length; ++index) adapters[index].powered = enable;
        return true;
    }

    Connections {
        target: BluezQt.Manager
        function onOperationalChanged() { root.changed(); }
        function onBluetoothOperationalChanged() { root.changed(); }
        function onBluetoothBlockedChanged() { root.changed(); }
        function onAdapterAdded() { root.changed(); }
        function onAdapterRemoved() { root.changed(); }
        function onAdapterChanged() { root.changed(); }
        function onConnectedDevicesChanged() { root.changed(); }
        function onDeviceChanged() { root.changed(); }
        function onDeviceAdded() { root.changed(); }
        function onDeviceRemoved() { root.changed(); }
    }
}
