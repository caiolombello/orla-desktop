import QtQuick

// Dock lifetime: logical revocation never releases an unresolved transport call.
Item {
    id: session
    required property var dataState
    property bool running: true
    property var transport: null
    property var owner: null
    property string scopeKey: ""
    property bool surfaceActive: false
    readonly property alias manager: managerState
    readonly property bool waiting: paused && dataState.addonCallPending
    readonly property bool busy: waiting || physical !== null || managerState.busy
    readonly property bool reloadRequired: needsMetadata || sourceChanged
    readonly property string feedback: waiting ? qsTr("Aguardando a leitura local terminar. Você pode fechar ou cancelar a espera.")
        : sourceChanged ? qsTr("O complemento mudou fora desta janela. Recarregue os complementos para conferir a leitura.")
        : needsMetadata && !busy ? qsTr("Recarregue os complementos para conferir o resultado antes de continuar.") : managerState.feedback
    property bool paused: false
    property bool admitted: false
    property bool needsMetadata: false
    property bool recovery: false
    property bool sourceChanged: false
    property var physical: null
    property var identity: null
    // Quota addons keep their own pin; hosts without quota routing ignore it.
    property var quotaIdentity: null
    property int lifetime: 0
    signal originApproved(string origin)

    // Initial property notifications precede assignment of required collaborators.
    QtObject {
        id: lifecycle
        property bool completed: false
        // Captured JS authority survives Loader retirement without reading a QObject.
        property var callbacks: ({alive: true, publishing: false, metadata: false})
        function recoverLater() {
            const authority = callbacks;
            if (!authority.recover) authority.recover = function() { if (authority.alive) session.finishRecovery(); };
            Qt.callLater(authority.recover);
        }
    }
    function pause() {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive || paused) return;
        const callbacks = lifecycle.callbacks;
        // Preserve the reader's validated startup pin if an opening is cancelled
        // before List can run. Never recover an identity from held raw readings.
        const addon = dataState.peripherals.addon;
        if (identity === null && !dataState.addonError && addon)
            identity = Object.freeze({generation: addon.generation, sha256: addon.sha256});
        if (!callbacks.alive) return;
        const quota = dataState.quotaAddonValue !== undefined && dataState.quotaAddonValue ? dataState.quotaAddonValue.addon : null;
        if (quotaIdentity === null && !dataState.quotaAddonError && quota)
            quotaIdentity = Object.freeze({generation: quota.generation, sha256: quota.sha256});
        if (!callbacks.alive) return;
        paused = true;
        if (!callbacks.alive) return;
        dataState.addonSuspended = true;
        if (!callbacks.alive) return;
        dataState.invalidateAddons();
    }
    function schedule() {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive || !running) return;
        const callbacks = lifecycle.callbacks;
        // Stable wrappers preserve callLater's existing per-instance coalescing.
        if (!callbacks.reconcile) callbacks.reconcile = function() { if (callbacks.alive) session.reconcile(); };
        Qt.callLater(callbacks.reconcile);
    }
    function revoke() {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive) return;
        const callbacks = lifecycle.callbacks;
        lifetime++;
        if (!callbacks.alive || !running) return;
        if ((!surfaceActive || !Qt.isQtObject(owner)) && physical !== null && needsMetadata) recovery = true;
        if (!callbacks.alive) return;
        admitted = false;
        if (!callbacks.alive) return;
        pause();
        if (!callbacks.alive) return;
        dataState.invalidateAddons();
        if (!callbacks.alive) return;
        schedule();
    }
    function reconcile() {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive || !running) return;
        const callbacks = lifecycle.callbacks;
        const requested = surfaceActive && Qt.isQtObject(owner);
        if (requested || recovery) {
            pause();
            if (!callbacks.alive) return;
            if (!dataState.addonCallPending && !admitted) {
                admitted = true;
            }
            return;
        }
        if (physical || managerState.busy || needsMetadata || sourceChanged || dataState.addonCallPending) return;
        if (paused) {
            const current = lifetime;
            if (identity !== null) dataState.addonIdentity = identity;
            if (quotaIdentity !== null && dataState.quotaIdentity !== undefined) dataState.quotaIdentity = quotaIdentity;
            if (!callbacks.alive || current !== lifetime || surfaceActive && Qt.isQtObject(owner) || recovery || needsMetadata) return;
            paused = false;
            if (!callbacks.alive || current !== lifetime) return;
            dataState.addonSuspended = false;
        }
    }
    function captureMetadata() {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive || !managerState.valid) return;
        const callbacks = lifecycle.callbacks;
        // Finish the manager's publication before our observers can retire its context.
        if (callbacks.publishing) { callbacks.metadata = true; return; }
        const current = lifetime;
        const enabled = managerState.addons.find(row => row.enabled === true && row.renderer !== "quota-usage");
        const enabledQuota = managerState.addons.find(row => row.enabled === true && row.renderer === "quota-usage");
        const next = Object.freeze({generation: managerState.generation, sha256: enabled ? enabled.sha256 : null});
        const nextQuota = Object.freeze({generation: managerState.generation, sha256: enabledQuota ? enabledQuota.sha256 : null});
        identity = next;
        quotaIdentity = nextQuota;
        if (!callbacks.alive || current !== lifetime || !managerState.valid) return;
        dataState.addonIdentity = next;
        if (!callbacks.alive || current !== lifetime || !managerState.valid) return;
        if (dataState.quotaIdentity !== undefined) dataState.quotaIdentity = nextQuota;
        if (!callbacks.alive || current !== lifetime || !managerState.valid) return;
        needsMetadata = false;
        if (!callbacks.alive) return;
        sourceChanged = false;
        if (!callbacks.alive) return;
        schedule();
    }
    function reload() {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive || busy) return false;
        const callbacks = lifecycle.callbacks;
        pause();
        if (!callbacks.alive) return false;
        needsMetadata = true;
        if (!callbacks.alive) return false;
        if (!admitted) { recovery = !surfaceActive; if (callbacks.alive) schedule(); return true; }
        return managerState.refresh();
    }
    function openOrigin(origin) {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive || !surfaceActive || !Qt.isQtObject(owner) || busy || !managerState.valid) return false;
        const rows = managerState.preview ? managerState.addons.concat([managerState.preview]) : managerState.addons;
        // Validation is owned by the manager. Match its current immutable row exactly.
        if (typeof origin !== "string" || !rows.some(row => row.valid === true && row.origin === origin)
                || !/^https:\/\/[A-Za-z0-9.[\]:-]+(?:\/[^\s?#\\]*)?$/.test(origin)
                || /[@\u0000-\u0020\u007f]/.test(origin.slice(8).split("/")[0])
                || /%(?:0[0-9a-f]|1[0-9a-f]|7f)/i.test(origin)) return false;
        originApproved(origin);
        return true;
    }
    onSurfaceActiveChanged: revoke()
    onRunningChanged: if (running) schedule()
    onOwnerChanged: {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive) return;
        if (surfaceActive || admitted || physical || recovery) revoke();
        else lifetime++;
    }
    onScopeKeyChanged: revoke()
    onTransportChanged: {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive) return;
        if (surfaceActive || admitted || physical || recovery) revoke();
        else lifetime++;
    }
    Connections {
        target: session.dataState
        function onAddonCallPendingChanged() { session.schedule(); }
        function onAddonErrorCodeChanged() {
            if (lifecycle && lifecycle.completed && session.running && session.dataState.addonErrorCode === "source_changed") {
                const callbacks = lifecycle.callbacks;
                session.sourceChanged = true;
                if (!callbacks.alive) return;
                session.needsMetadata = true;
                if (!callbacks.alive) return;
                session.pause();
            }
        }
    }
    Connections {
        target: session.dataState
        ignoreUnknownSignals: true
        // A quota source change needs the same metadata review as a battery one.
        function onQuotaAddonErrorCodeChanged() {
            if (lifecycle && lifecycle.completed && session.running && session.dataState.quotaAddonErrorCode === "source_changed") {
                const callbacks = lifecycle.callbacks;
                session.sourceChanged = true;
                if (!callbacks.alive) return;
                session.needsMetadata = true;
                if (!callbacks.alive) return;
                session.pause();
            }
        }
    }
    QtObject {
        id: gate
        function asyncCall(message, resolve, reject) {
            if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive) { reject({}); return; }
            const callbacks = lifecycle.callbacks;
            const current = session.lifetime;
            const requestOwner = managerState.owner;
            session.pause();
            if (!callbacks.alive) return;
            if (current !== session.lifetime || session.dataState.addonCallPending || session.physical !== null || !session.transport) {
                reject({});
                return;
            }
            const call = {transport: session.transport, settled: false};
            session.physical = call;
            function authorized() {
                return callbacks.alive && current === session.lifetime && session.physical === call && managerState.active
                    && Qt.isQtObject(requestOwner) && managerState.owner === requestOwner;
            }
            function finish(reply, failed) {
                if (!callbacks.alive || call.settled) return;
                call.settled = true;
                // Retain the physical barrier throughout potentially reentrant publication.
                callbacks.publishing = true;
                try { if (failed) reject({}); else resolve(reply); }
                finally {
                    callbacks.publishing = false;
                    if (!callbacks.alive) return;
                    if (callbacks.metadata) { callbacks.metadata = false; session.captureMetadata(); }
                    if (!callbacks.alive) return;
                    if (session.physical === call) session.physical = null;
                    if (!callbacks.alive) return;
                    if (message.member !== "ListAddons" && message.member !== "InspectAddonFile"
                            && session.needsMetadata) {
                        if (!callbacks.refresh) callbacks.refresh = function() { if (callbacks.alive) managerState.refresh(); };
                        Qt.callLater(callbacks.refresh);
                    }
                    session.schedule();
                }
            }
            // Reservation publication can revoke this opening before List is sent.
            if (!authorized()) { finish(null, true); return; }
            if (message.member === "ListAddons") session.needsMetadata = true;
            // The metadata setter also notifies observers; retain genuine recovery.
            if (!authorized()) {
                finish(null, true);
                return;
            }
            try { call.transport.asyncCall(message,
                reply => { if (callbacks.alive) finish(reply, false); },
                () => { if (callbacks.alive) finish(null, true); }); }
            catch (_) { if (callbacks.alive) finish(null, true); }
        }
    }
    AddonManagerState {
        id: managerState
        active: !!lifecycle && lifecycle.completed && session.running && session.admitted && (session.surfaceActive && Qt.isQtObject(session.owner) || session.recovery)
        owner: session.surfaceActive && Qt.isQtObject(session.owner) ? session.owner : session
        scopeKey: session.scopeKey + ":" + session.lifetime
        transport: gate
        onValidChanged: if (valid) session.captureMetadata()
        onBusyChanged: session.schedule()
        onMutationStarted: {
            const callbacks = lifecycle.callbacks;
            session.pause();
            if (!callbacks.alive) return;
            session.needsMetadata = true;
            if (!callbacks.alive) return;
            session.recovery = true;
        }
        onMutationSettled: session.schedule()
    }
    onPhysicalChanged: schedule()
    // Recovery is read-only and survives destruction of the settings owner.
    function finishRecovery() {
        if (!lifecycle || !lifecycle.completed || !lifecycle.callbacks.alive || !running || !recovery || physical || managerState.busy) return;
        const callbacks = lifecycle.callbacks;
        if (managerState.valid && !needsMetadata) {
            recovery = false;
            if (!callbacks.alive) return;
            if (!surfaceActive || !Qt.isQtObject(owner)) admitted = false;
        }
    }
    Connections {
        target: managerState
        function onBusyChanged() { lifecycle.recoverLater(); }
        function onValidChanged() { lifecycle.recoverLater(); }
    }
    Component.onCompleted: { lifecycle.completed = true; schedule(); }
    Component.onDestruction: { lifecycle.callbacks.alive = false; running = false; }
}
