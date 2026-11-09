import QtQuick
import org.kde.plasma.private.volume as PlasmaPA
import org.kde.plasma.plasma5support as P5Support
import org.kde.plasma.workspace.dbus as DBus
import org.kde.plasma.workspace.calendar as PlasmaCalendar
import org.kde.kdeconnect as KDEConnect

// Production-only sensors for the island, loaded only while the island shows
// live activities. Each one exposes plain values; IslandState and
// IslandNotices decide what to show.
// Microphone: a recording stream that is not paused, not a level meter and not
// a mixer, close to the rule of Plasma-PA's own microphone indicator.
// Camera: the session has no camera-use API, so a process of this user holding
// a V4L2 device open counts, checked with fuser every few seconds. Apps that
// reach the camera through PipeWire show up as PipeWire holding the device.
// Battery: UPower's display device, live through PropertiesChanged.
// Phones: paired, reachable KDE Connect devices with a battery.
// Calendar: today's events from the same PIM plugin as the dock's calendar,
// only when the dock's calendar events are on.
Item {
    id: root
    visible: false
    readonly property var owner: sensorsOwner
    property bool microphoneInUse: false
    property bool cameraInUse: false
    // {percent, state} with UPower's Device.State, or null without a battery.
    property var power: null
    property var phones: []
    property var calendarEvents: []
    readonly property var ignoredApplications: ["org.PulseAudio.pavucontrol", "org.gnome.VolumeControl",
        "org.kde.kmixd", "org.kde.plasma-pa"]
    readonly property string cameraCommand: "sh -c 'set -- /dev/video*; [ -e \"$1\" ] || exit 2; exec fuser -s \"$@\"'"

    function recording(stream) {
        if (!stream || stream.virtualStream || stream.corked) return false;
        const properties = stream.properties || {};
        return ignoredApplications.indexOf(String(properties["application.id"] || "")) < 0;
    }
    function refreshMicrophone() {
        let found = false;
        for (let index = 0; index < streams.count && !found; ++index) {
            const entry = streams.objectAt(index);
            found = Boolean(entry && recording(entry.stream));
        }
        microphoneInUse = found;
    }

    PlasmaPA.SourceOutputModel { id: outputs }
    Instantiator {
        id: streams
        model: outputs
        delegate: Item {
            readonly property var stream: model.PulseObject
            Connections {
                target: stream
                ignoreUnknownSignals: true
                function onCorkedChanged() { Qt.callLater(root.refreshMicrophone); }
                function onPropertiesChanged() { Qt.callLater(root.refreshMicrophone); }
            }
        }
        onObjectAdded: Qt.callLater(root.refreshMicrophone)
        onObjectRemoved: Qt.callLater(root.refreshMicrophone)
    }

    P5Support.DataSource {
        id: camera
        engine: "executable"
        onNewData: (source, data) => {
            // fuser exits 0 when some process uses a device, 1 when none does.
            root.cameraInUse = Number(data["exit code"]) === 0;
            disconnectSource(source);
        }
    }
    Timer {
        interval: 4000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: if (camera.connectedSources.indexOf(root.cameraCommand) < 0) camera.connectSource(root.cameraCommand)
    }

    // Plasma's decoder wraps some D-Bus values as {value: ...}.
    function unwrap(value) {
        return value !== null && typeof value === "object" && value.value !== undefined ? value.value : value;
    }
    function readPower() {
        const properties = upower.properties;
        // Device.Type 2 is a battery; a desktop's display device is not.
        const present = properties && Boolean(unwrap(properties.IsPresent)) && Number(unwrap(properties.Type)) === 2;
        const next = present ? {percent: Number(unwrap(properties.Percentage)), state: Number(unwrap(properties.State))} : null;
        if (JSON.stringify(next) !== JSON.stringify(power)) power = next;
    }
    DBus.Properties {
        id: upower
        busType: DBus.BusType.System
        service: "org.freedesktop.UPower"
        path: "/org/freedesktop/UPower/devices/DisplayDevice"
        iface: "org.freedesktop.UPower.Device"
        onPropertiesChanged: Qt.callLater(root.readPower)
        onRefreshed: Qt.callLater(root.readPower)
    }

    function readPhones() {
        const list = [];
        for (let index = 0; index < phoneBatteries.count; ++index) {
            const entry = phoneBatteries.objectAt(index);
            if (entry && entry.battery && entry.battery.hasBattery)
                list.push({id: entry.deviceId, name: entry.name, charge: entry.battery.charge,
                    charging: entry.battery.isCharging});
        }
        if (JSON.stringify(list) !== JSON.stringify(phones)) phones = list;
    }
    KDEConnect.DevicesModel {
        id: devices
        displayFilter: KDEConnect.DevicesModel.Paired | KDEConnect.DevicesModel.Reachable
    }
    Instantiator {
        id: phoneBatteries
        model: devices
        delegate: QtObject {
            required property string deviceId
            required property string name
            readonly property var battery: KDEConnect.DeviceBatteryDbusInterfaceFactory.create(deviceId)
            readonly property string reading: battery ? [battery.hasBattery, battery.charge, battery.isCharging].join() : ""
            onReadingChanged: Qt.callLater(root.readPhones)
        }
        onObjectAdded: Qt.callLater(root.readPhones)
        onObjectRemoved: Qt.callLater(root.readPhones)
    }

    Loader {
        id: calendarLoader
        active: Boolean(root.owner && root.owner.configuration.calendarEvents)
        onActiveChanged: if (!active) root.calendarEvents = []
        sourceComponent: QtObject {
            id: agenda
            property var plugins: PlasmaCalendar.EventPluginsManager { enabledPlugins: ["pimevents"] }
            // A month grid like MonthView's: without days and weeks the model asks plugins for nothing.
            property var calendar: PlasmaCalendar.Calendar { days: 7; weeks: 6; today: new Date(); displayedDate: new Date() }
            function read() {
                const events = calendar.daysModel.eventsForDate(new Date()) || [];
                root.calendarEvents = events.map(event => ({
                    title: String(event.title || ""),
                    startMs: new Date(event.startDateTime).getTime(),
                    endMs: new Date(event.endDateTime).getTime(),
                    allDay: Boolean(event.isAllDay)
                }));
            }
            property Connections updates: Connections {
                target: agenda.calendar.daysModel
                function onAgendaUpdated(updatedDate) { Qt.callLater(agenda.read); }
            }
            // Follows the day across midnight and catches a missed update.
            property Timer clock: Timer {
                interval: 60000
                repeat: true
                running: true
                onTriggered: {
                    agenda.calendar.today = new Date();
                    agenda.calendar.displayedDate = new Date();
                    agenda.read();
                }
            }
            Component.onCompleted: {
                calendar.daysModel.setPluginsManager(plugins);
                read();
            }
        }
    }

    Component.onCompleted: refreshMicrophone()
}
