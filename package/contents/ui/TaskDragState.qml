import QtQuick

QtObject {
    id: state
    required property var profiles
    required property bool viewActive
    required property var readOrder
    required property var commitMove
    property var intent: null
    property int generation: 0
    property bool active: false
    property bool committing: false
    property string destination: ""
    property bool after: false
    readonly property bool pressed: intent !== null
    readonly property string saved: {
        try { return JSON.stringify(Array.from(profiles.effective.launchers)); }
        catch (_) { return ""; }
    }
    onProfilesChanged: cancel()
    onViewActiveChanged: if (!viewActive) cancel()
    onSavedChanged: if (!committing) cancel()
    property Connections profileChanges: Connections {
        target: state.profiles
        function onRevisionChanged() { if (!state.committing) state.cancel(); }
        function onActiveProfileIdChanged() { state.cancel(); }
        function onWritableChanged() { if (!state.profiles.writable) state.cancel(); }
    }
    function cancel() {
        generation++;
        intent = null;
        active = false;
        destination = "";
        after = false;
    }
    function reject(captured) {
        if (intent === captured) cancel();
        return false;
    }
    function snapshot() {
        try {
            const rows = readOrder();
            if (!Array.isArray(rows) || rows.length === 0) return null;
            const ids = new Set();
            for (let n = 0; n < rows.length; ++n) {
                const row = rows[n];
                if (!row || typeof row.identity !== "string" || !row.identity.length || ids.has(row.identity)
                        || !Number.isInteger(row.rank) || row.rank < -1 || row.order !== n) return null;
                ids.add(row.identity);
            }
            return rows.map(row => ({identity: row.identity, rank: row.rank, order: row.order}));
        } catch (_) { return null; }
    }
    function domain(captured) {
        return captured !== null && intent === captured && generation === captured.generation
            && viewActive && profiles === captured.profiles && profiles.writable
            && profiles.activeProfileId === captured.scope && profiles.revision === captured.revision
            && saved === captured.saved;
    }
    function releaseValid(captured) {
        if (!domain(captured)) return false;
        const rows = snapshot();
        return domain(captured) && rows !== null && JSON.stringify(rows) === captured.order;
    }
    function begin(identity) {
        if (committing) return false;
        cancel();
        if (!viewActive || !profiles || !profiles.writable || saved === "") return false;
        const captured = {profiles: profiles, scope: profiles.activeProfileId, revision: profiles.revision,
            saved: saved, generation: generation, identity: identity};
        const rows = snapshot();
        if (rows === null || !rows.some(row => row.identity === identity)) return false;
        if (generation !== captured.generation || intent !== null) return false;
        captured.rows = rows;
        captured.order = JSON.stringify(rows);
        intent = captured;
        return releaseValid(captured) || reject(captured);
    }
    function activate() {
        const captured = intent;
        if (!releaseValid(captured)) return reject(captured);
        active = true;
        return true;
    }
    function update(identity, insertAfter) {
        const captured = intent;
        if (!active) return false;
        if (!releaseValid(captured)) return reject(captured);
        destination = captured.rows.some(row => row.identity === identity) ? identity : "";
        after = insertAfter === true;
        return destination.length > 0;
    }
    function finish() {
        if (committing) return false;
        const captured = intent;
        if (!active || !releaseValid(captured) || !destination.length) return reject(captured);
        const from = captured.rows.findIndex(row => row.identity === captured.identity);
        const target = captured.rows.findIndex(row => row.identity === destination);
        if (from < 0 || target < 0) return reject(captured);
        const boundary = target + (after ? 1 : 0);
        const to = boundary - (from < boundary ? 1 : 0);
        if (from === to) return reject(captured);
        committing = true;
        try {
            // Only the view's release handler calls finish; the adapter checks its own post-move order.
            return domain(captured) && commitMove(from, to, () => state.domain(captured)) === true;
        } finally {
            committing = false;
            if (intent === captured) cancel();
        }
    }
}
