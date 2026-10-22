import QtQuick
import org.kde.plasma.private.brightnesscontrolplugin as PlasmaBrightness
import org.kde.plasma.workspace.dbus as DBus

// Production-only adapter for PowerDevil's screen brightness. Reads use the
// Plasma brightness applet's model; writes go to the service over D-Bus with
// Orla's own context, so the model only moves when PowerDevil reports the new
// value (the model updates its own writes optimistically and drops their echo).
Item {
    id: root
    visible: false
    property int revision: 0
    signal writeFailed(string id)
    readonly property var snapshot: buildSnapshot(revision)

    function changed() { revision += 1; }
    function buildSnapshot(witness) {
        const displays = [];
        for (let index = 0; index < rows.count; ++index) {
            const row = rows.objectAt(index);
            if (!row) continue;
            displays.push({id: String(row.displayName || ""), label: String(row.label || "").slice(0, 128),
                value: Number(row.brightness), max: Number(row.maxBrightness), internal: Boolean(row.isInternal)});
        }
        const status = !control.isBrightnessAvailable ? (displays.length ? "unavailable" : "absent")
            : displays.length ? "ready" : "absent";
        return {status: status, displays: displays};
    }
    // Silent (flag 1): the dock shows the result itself, without Plasma's OSD.
    function setBrightness(id, raw) {
        const display = String(id);
        if (!/^[A-Za-z0-9_]{1,64}$/.test(display)) return false;
        DBus.SessionBus.asyncCall({service: "org.kde.ScreenBrightness", path: "/org/kde/ScreenBrightness/" + display,
            iface: "org.kde.ScreenBrightness.Display", member: "SetBrightnessWithContext", signature: "(ius)",
            arguments: [Math.round(Number(raw)), 1, "orla-dock"]}, () => {}, () => root.writeFailed(display));
        return true;
    }

    PlasmaBrightness.ScreenBrightnessControl {
        id: control
        isSilent: true
        onIsBrightnessAvailableChanged: root.changed()
    }
    Instantiator {
        id: rows
        model: control.displays
        delegate: QtObject {
            required property string displayName
            required property string label
            required property int brightness
            required property int maxBrightness
            required property bool isInternal
            onBrightnessChanged: root.changed()
            onMaxBrightnessChanged: root.changed()
            onLabelChanged: root.changed()
        }
        onObjectAdded: root.changed()
        onObjectRemoved: root.changed()
    }
}
