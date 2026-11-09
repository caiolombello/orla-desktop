import QtQuick
import org.kde.plasma.private.volume as PlasmaPA
import org.kde.plasma.plasma5support as P5Support

// Production-only privacy sensors for the island, loaded only while the island
// shows live activities.
// Microphone: a recording stream that is not paused, not a level meter and not
// a mixer, close to the rule of Plasma-PA's own microphone indicator.
// Camera: the session has no camera-use API, so a process of this user holding
// a V4L2 device open counts, checked with fuser every few seconds. Apps that
// reach the camera through PipeWire show up as PipeWire holding the device.
Item {
    id: root
    visible: false
    property bool microphoneInUse: false
    property bool cameraInUse: false
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
    Component.onCompleted: refreshMicrophone()
}
