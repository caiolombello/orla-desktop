import QtQuick
import org.kde.plasma.networkmanagement as PlasmaNM

// Production-only adapter for the Wi-Fi radio, through the same library as
// Plasma's network applet. EnabledConnections follows NetworkManager's own
// notifications, so it confirms a change instead of echoing the request.
Item {
    id: root
    visible: false
    property int revision: 0
    readonly property var snapshot: buildSnapshot(revision)

    function changed() { revision += 1; }
    function buildSnapshot(witness) {
        // Without a Wi-Fi device (or without NetworkManager) there is nothing to switch.
        if (!devices.wirelessDeviceAvailable) return {status: "absent"};
        return {status: "ready", enabled: Boolean(radio.wirelessEnabled), hardwareEnabled: Boolean(radio.wirelessHwEnabled),
            network: String(wireless.wifiSSID || "").slice(0, 64)};
    }
    function setEnabled(on) {
        if (!devices.wirelessDeviceAvailable) return false;
        handler.enableWireless(Boolean(on));
        return true;
    }

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
    PlasmaNM.Handler { id: handler }
}
