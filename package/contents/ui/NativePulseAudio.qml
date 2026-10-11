import QtQuick
import org.kde.plasma.private.volume as PlasmaPA

Item {
    id: root
    visible: false
    property int revision: 0
    readonly property var snapshot: buildSnapshot(revision)

    function changed() { revision += 1; }

    function pulseObjectAt(index) {
        if (index < 0 || index >= sinks.count) return null;
        return sinks.data(sinks.index(index, 0), sinks.role("PulseObject"));
    }

    function eligible(object) {
        if (!object || String(object.name || "") === "auto_null" || Boolean(object.virtualDevice)) return false;
        const ports = object.ports || [];
        if (ports.length === 1 && ports[0].availability === PlasmaPA.Port.Unavailable) return false;
        return true;
    }

    function objectById(id) {
        const requested = String(id || "");
        for (let index = 0; index < sinks.count; ++index) {
            const object = pulseObjectAt(index);
            if (eligible(object) && String(object.name || "") === requested) return object;
        }
        return null;
    }

    function buildSnapshot(witness) {
        const ready = PlasmaPA.Context.state === PlasmaPA.Context.State.Ready;
        let state = "unavailable";
        if (ready) state = "ready";
        else if (PlasmaPA.Context.autoConnecting) state = "loading";
        const outputs = [];
        for (let index = 0; index < sinks.count; ++index) {
            const object = pulseObjectAt(index);
            if (!eligible(object)) continue;
            outputs.push({
                id: String(object.name || ""),
                label: String(object.description || object.name || "").slice(0, 128),
                volumeRaw: Number(object.volume),
                muted: Boolean(object.muted),
                writable: Boolean(object.volumeWritable),
                isDefault: Boolean(object.default)
            });
        }
        const defaultSink = PlasmaPA.Server.defaultSink;
        const defaultId = defaultSink ? String(defaultSink.name || "") : "";
        return {
            status: ready && outputs.length === 0 ? "absent" : state,
            normalVolume: PlasmaPA.PulseAudio.NormalVolume,
            defaultOutputId: defaultId,
            outputs: outputs
        };
    }

    function setVolume(id, raw) {
        if (PlasmaPA.Context.state !== PlasmaPA.Context.State.Ready || !Number.isFinite(Number(raw))) return false;
        const object = objectById(id);
        if (!object || !object.volumeWritable) return false;
        object.volume = Math.max(0, Math.min(PlasmaPA.PulseAudio.NormalVolume, Math.round(Number(raw))));
        return true;
    }

    function setMuted(id, value) {
        if (PlasmaPA.Context.state !== PlasmaPA.Context.State.Ready) return false;
        const object = objectById(id);
        if (!object || !object.volumeWritable) return false;
        object.muted = Boolean(value);
        return true;
    }

    function setDefaultOutput(id) {
        if (PlasmaPA.Context.state !== PlasmaPA.Context.State.Ready) return false;
        const object = objectById(id);
        if (!object) return false;
        object.default = true;
        return true;
    }

    function retry() {
        if (PlasmaPA.Context.autoConnecting) return false;
        PlasmaPA.Context.reconnectDaemon();
        return true;
    }

    PlasmaPA.SinkModel { id: sinks }
    Connections {
        target: sinks
        function onCountChanged() { root.changed(); }
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
        function onDefaultSinkChanged() { root.changed(); }
    }
}
