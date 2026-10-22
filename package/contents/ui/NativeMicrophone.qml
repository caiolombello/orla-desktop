import QtQuick
import org.kde.plasma.private.volume as PlasmaPA

// Production-only adapter for the default audio input, through the same
// Plasma-PA module as the volume applet. Only the server's default source is
// muted: that is the input applications record from unless told otherwise.
Item {
    id: root
    visible: false
    property int revision: 0
    readonly property var snapshot: buildSnapshot(revision)

    function changed() { revision += 1; }
    function defaultInput() {
        const source = PlasmaPA.Server.defaultSource;
        const name = source ? String(source.name || "") : "";
        // A sink monitor or the null source is not a microphone.
        if (!name || name === "auto_null" || name.endsWith(".monitor")) return null;
        return source;
    }
    function buildSnapshot(witness) {
        if (PlasmaPA.Context.state !== PlasmaPA.Context.State.Ready)
            return {status: PlasmaPA.Context.autoConnecting ? "loading" : "unavailable", input: null};
        const source = defaultInput();
        if (!source) return {status: "absent", input: null};
        return {status: "ready", input: {id: String(source.name), label: String(source.description || source.name).slice(0, 128),
            muted: Boolean(source.muted), writable: Boolean(source.volumeWritable)}};
    }
    function setMuted(id, value) {
        if (PlasmaPA.Context.state !== PlasmaPA.Context.State.Ready) return false;
        const source = defaultInput();
        if (!source || String(source.name) !== String(id) || !source.volumeWritable) return false;
        source.muted = Boolean(value);
        return true;
    }

    // The model reports mute and description changes of every input, the default one included.
    PlasmaPA.SourceModel { id: sources }
    Connections {
        target: sources
        function onDataChanged() { root.changed(); }
        function onRowsInserted() { root.changed(); }
        function onRowsRemoved() { root.changed(); }
        function onModelReset() { root.changed(); }
    }
    Connections {
        target: PlasmaPA.Context
        function onStateChanged() { root.changed(); }
        function onAutoConnectingChanged() { root.changed(); }
    }
    Connections {
        target: PlasmaPA.Server
        function onDefaultSourceChanged() { root.changed(); }
    }
}
