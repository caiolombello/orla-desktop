import QtQuick
import org.kde.plasma.networkmanagement as PlasmaNM

// Production-only adapter for Wi-Fi, through the same library as Plasma's
// network applet. EnabledConnections and NetworkModel follow NetworkManager's
// own notifications, so they confirm a change instead of echoing the request.
Item {
    id: root
    visible: false
    property int revision: 0
    // id -> {connection, device, specific}: object paths stay inside the adapter.
    property var routes: ({})
    readonly property var snapshot: buildSnapshot(revision)
    // NetworkManager's connection types (NetworkManager::ConnectionSettings): Wired 13, Wireless 14.
    readonly property int wiredType: 13
    readonly property int wirelessType: 14
    signal joinFailed(string id, string message)

    function changed() { revision += 1; }
    function role(name) { return PlasmaNM.NetworkModel[name]; }
    function readNetworks() {
        const found = [];
        const paths = {};
        const rows = Math.min(networks.rowCount(), 128);
        for (let row = 0; row < rows; ++row) {
            const index = networks.index(row, 0);
            const value = name => networks.data(index, role(name));
            // Only Wi-Fi in range: saved and available (1) or a new access point (2).
            const kind = Number(value("ItemTypeRole"));
            if (Number(value("TypeRole")) !== wirelessType || (kind !== 1 && kind !== 2) || value("DuplicateRole") === true)
                continue;
            const connection = String(value("ConnectionPathRole") || "");
            const specific = String(value("SpecificPathRole") || "");
            const id = connection || specific;
            if (!id) continue;
            const state = Number(value("ConnectionStateRole"));
            paths[id] = {connection: connection, device: String(value("DevicePathRole") || ""), specific: specific};
            found.push({id: id, name: String(value("SsidRole") || "").slice(0, 64),
                strength: Number(value("SignalRole")) || 0, secured: Number(value("SecurityTypeRole")) > 0,
                saved: connection.length > 0,
                // NetworkManager::ActiveConnection: Activating = 1, Activated = 2.
                state: state === 2 ? "connected" : state === 1 ? "connecting" : "available"});
        }
        routes = paths;
        return found;
    }
    // An active cable connection, so the Control Center can say the computer is online.
    function readWired() {
        const rows = Math.min(networks.rowCount(), 128);
        for (let row = 0; row < rows; ++row) {
            const index = networks.index(row, 0);
            if (Number(networks.data(index, role("TypeRole"))) === wiredType
                    && Number(networks.data(index, role("ConnectionStateRole"))) === 2)
                return {connected: true, name: String(networks.data(index, role("NameRole")) || "").slice(0, 64)};
        }
        return {connected: false, name: ""};
    }
    function buildSnapshot(witness) {
        const wired = readWired();
        // Without a Wi-Fi device (or without NetworkManager) there is nothing to switch.
        if (!devices.wirelessDeviceAvailable) return {status: "absent", wired: wired};
        return {status: "ready", enabled: Boolean(radio.wirelessEnabled), hardwareEnabled: Boolean(radio.wirelessHwEnabled),
            network: String(wireless.wifiSSID || "").slice(0, 64), networks: radio.wirelessEnabled ? readNetworks() : [],
            wired: wired};
    }
    function setEnabled(on) {
        if (!devices.wirelessDeviceAvailable) return false;
        handler.enableWireless(Boolean(on));
        return true;
    }
    function joinNetwork(id) {
        const route = routes[id];
        if (!route || !route.device) return false;
        // A saved network reconnects; a new one is added, and KDE's secret agent asks for its password.
        if (route.connection) handler.activateConnection(route.connection, route.device, route.specific);
        else handler.addAndActivateConnection(route.device, route.specific);
        return true;
    }
    function leaveNetwork(id) {
        const route = routes[id];
        if (!route || !route.connection) return false;
        handler.deactivateConnection(route.connection, route.device);
        return true;
    }
    function scan() { handler.requestScan(""); }

    PlasmaNM.AvailableDevices {
        id: devices
        onWirelessDeviceAvailableChanged: root.changed()
    }
    PlasmaNM.EnabledConnections {
        id: radio
        onWirelessEnabledChanged: root.changed()
        onWirelessHwEnabledChanged: root.changed()
    }
    PlasmaNM.WirelessStatus {
        id: wireless
        onWifiSSIDChanged: root.changed()
    }
    PlasmaNM.NetworkModel { id: networks }
    Connections {
        target: networks
        // Signal strength updates often: rebuild once per event loop turn.
        function onDataChanged() { Qt.callLater(root.changed); }
        function onRowsInserted() { Qt.callLater(root.changed); }
        function onRowsRemoved() { Qt.callLater(root.changed); }
        function onModelReset() { Qt.callLater(root.changed); }
    }
    PlasmaNM.Handler {
        id: handler
        onConnectionActivationFailed: (connectionPath, message) => root.joinFailed(connectionPath, message)
    }
}
