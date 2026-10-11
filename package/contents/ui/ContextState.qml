import QtQuick
import "../code/Contexts.js" as Contexts

QtObject {
    id: state
    required property var sourceSnapshot
    readonly property int revision: internal.revision
    readonly property var snapshot: Contexts.freeze(Contexts.copy(internal.snapshot))

    property QtObject internal: QtObject {
        property int revision: 0
        property string fingerprint: ""
        property var snapshot: Contexts.normalizeSnapshot(null)
    }

    function refresh() {
        const next = Contexts.normalizeSnapshot(sourceSnapshot);
        const fingerprint = JSON.stringify(next);
        if (fingerprint === internal.fingerprint) return false;
        internal.snapshot = Contexts.freeze(next);
        internal.fingerprint = fingerprint;
        internal.revision++;
        return true;
    }

    onSourceSnapshotChanged: refresh()
    Component.onCompleted: refresh()
}
