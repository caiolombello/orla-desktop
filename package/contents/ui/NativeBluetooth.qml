import QtQuick
import org.kde.bluezqt as BluezQt

// Production-only adapter for the Bluetooth radio through BluezQt, as Plasma's
// Bluetooth applet uses it. Writes only ask BlueZ and rfkill; the properties
// change when the services report it, so they confirm instead of echoing.
Item {
    id: root
    visible: false
    property int revision: 0
    readonly property var snapshot: buildSnapshot(revision)

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
        return {status: "ready", enabled: Boolean(manager.bluetoothOperational), blocked: blocked, connected: connected};
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
    }
}
