import QtQuick

Item {
    id: root
    visible: false

    property bool active: false
    property var backend: null
    property int confirmationTimeout: 2000
    property string requestOriginScope: ""
    property int requestContextGeneration: -1
    property var nowProvider: function() { return Date.now(); }

    property string status: "inactive"
    property var outputs: []
    property string defaultOutputId: ""
    property int confirmedVolume: 0
    property bool muted: false
    property bool writable: false
    property string pendingKind: ""
    property string error: ""
    readonly property string presentationOutputId: pendingKind === "default-output"
        ? String(_desiredValue || "") : defaultOutputId
    readonly property bool pendingVolumePresentable: pendingKind === "volume"
        && status === "ready" && _pendingOutputId === defaultOutputId
        && outputById(_pendingOutputId) !== null && outputById(_pendingOutputId).writable
    readonly property int presentationVolume: pendingVolumePresentable
        ? Math.max(0, Math.min(100, Math.round(Number(_desiredValue) * 100 / _pendingNormalVolume)))
        : confirmedVolume
    property bool volumeGestureActive: false
    property bool volumeGestureBlocked: false
    property string volumeGestureOutputId: ""

    signal confirmed(var receipt)

    property int _normalVolume: 65536
    property int _confirmedRaw: 0
    property int _serial: 0
    property int _pendingSerial: 0
    property int _timerSerial: 0
    property double _pendingDeadline: 0
    property string _pendingOutputId: ""
    property string _pendingTargetLabel: ""
    property int _pendingNormalVolume: 65536
    property var _desiredValue: undefined
    property string _pendingOriginScope: ""
    property int _pendingContextGeneration: -1
    property bool _pendingAccepted: false
    property int _pendingObservationFloor: 0
    property int _observationRevision: 0
    property int _dispatchInProgressSerial: 0
    property int _matchingObservationSerial: 0
    property int _deadlineDeferredSerial: 0

    function nowMs() {
        try {
            const value = Number(nowProvider());
            return Number.isFinite(value) ? value : Date.now();
        } catch (_) { return Date.now(); }
    }
    function finite(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : NaN;
    }
    function boundedLabel(value) {
        return String(value || "").slice(0, 128).replace(/\s+/g, " ").trim();
    }
    function cancelPending() {
        confirmation.stop();
        _pendingSerial = 0; _timerSerial = 0; _pendingDeadline = 0;
        _pendingOutputId = ""; _pendingTargetLabel = ""; _pendingNormalVolume = 65536; _desiredValue = undefined;
        _pendingOriginScope = ""; _pendingContextGeneration = -1;
        _pendingAccepted = false; _pendingObservationFloor = 0;
        _dispatchInProgressSerial = 0; _matchingObservationSerial = 0; _deadlineDeferredSerial = 0;
        pendingKind = "";
    }
    function failPending(message) { cancelPending(); error = message; }
    function invalidateLifecycle() { cancelPending(); endVolumeGesture(); }
    function resetPending() { invalidateLifecycle(); }
    function outputById(id) {
        for (let index = 0; index < outputs.length; ++index)
            if (outputs[index].id === id) return outputs[index];
        return null;
    }
    function contextMatches(scope, generation) {
        return scope.length > 0 && scope === requestOriginScope
            && generation >= 0 && generation === requestContextGeneration;
    }
    function pendingMatches() {
        const target = outputById(_pendingOutputId);
        if (!target) return false;
        if (pendingKind === "volume") return target.volumeRaw === _desiredValue;
        if (pendingKind === "mute") return target.muted === _desiredValue;
        if (pendingKind === "default-output") return defaultOutputId === _desiredValue;
        return false;
    }
    function receiptValue() {
        if (pendingKind === "volume")
            return Math.max(0, Math.min(100, Math.round(Number(_desiredValue) * 100 / _pendingNormalVolume)));
        if (pendingKind === "mute") return Boolean(_desiredValue);
        return String(_desiredValue || "");
    }
    function pendingReceipt() {
        return {serial: _pendingSerial, action: pendingKind, targetId: _pendingOutputId,
            targetLabel: _pendingTargetLabel, value: receiptValue(),
            originScope: _pendingOriginScope, contextGeneration: _pendingContextGeneration};
    }
    function scheduleRemaining() {
        confirmation.stop();
        if (!_pendingSerial) return;
        confirmation.interval = Math.max(1, _pendingDeadline - nowMs());
        _timerSerial = _pendingSerial;
        confirmation.restart();
    }
    function confirmPending(preserveError) {
        const receipt = pendingReceipt();
        cancelPending();
        if (!preserveError) error = "";
        confirmed(receipt);
        return "confirmed";
    }
    function evaluatePending(preserveError) {
        if (!_pendingSerial || !_pendingAccepted || _dispatchInProgressSerial === _pendingSerial)
            return "deferred";
        if (!contextMatches(_pendingOriginScope, _pendingContextGeneration)) {
            cancelPending(); return "cancelled";
        }
        if (nowMs() >= _pendingDeadline) {
            failPending(qsTr("O serviço de áudio não confirmou a alteração.")); return "expired";
        }
        if (status !== "ready") {
            failPending(qsTr("O serviço de áudio não confirmou a alteração.")); return "service";
        }
        if (!outputById(_pendingOutputId)) {
            failPending(qsTr("A saída de áudio usada na alteração não está mais disponível.")); return "target";
        }
        if (!pendingMatches() || _observationRevision <= _pendingObservationFloor
                || _matchingObservationSerial !== _pendingSerial) {
            scheduleRemaining(); return "pending";
        }
        return confirmPending(Boolean(preserveError));
    }

    function refresh() {
        if (!active) {
            cancelPending(); status = "inactive"; outputs = []; defaultOutputId = "";
            confirmedVolume = 0; muted = false; writable = false; error = ""; endVolumeGesture(); return;
        }
        const snapshot = backend && backend.snapshot ? backend.snapshot : null;
        const incomingStatus = snapshot ? String(snapshot.status || "unavailable") : "unavailable";
        const validStatuses = ["loading", "ready", "absent", "unavailable"];
        status = validStatuses.indexOf(incomingStatus) >= 0 ? incomingStatus : "unavailable";
        const normal = snapshot ? finite(snapshot.normalVolume) : NaN;
        _normalVolume = Number.isFinite(normal) && normal > 0 ? Math.round(normal) : 65536;
        const nextOutputs = [];
        const incoming = snapshot && Array.isArray(snapshot.outputs) ? snapshot.outputs : [];
        for (let index = 0; index < incoming.length; ++index) {
            const candidate = incoming[index] || {};
            const id = String(candidate.id || "");
            const raw = finite(candidate.volumeRaw);
            if (!id || !Number.isFinite(raw)) continue;
            nextOutputs.push({id: id, label: boundedLabel(candidate.label) || qsTr("Saída sem nome"),
                volumeRaw: Math.max(0, Math.round(raw)), muted: Boolean(candidate.muted),
                writable: Boolean(candidate.writable), isDefault: Boolean(candidate.isDefault)});
        }
        outputs = nextOutputs;
        if (status === "ready" && outputs.length === 0) status = "absent";
        let nextDefault = snapshot ? String(snapshot.defaultOutputId || "") : "";
        let selected = null;
        for (let index = 0; index < outputs.length; ++index)
            if (outputs[index].id === nextDefault) selected = outputs[index];
        if (!selected) for (let index = 0; index < outputs.length; ++index)
            if (outputs[index].isDefault) { selected = outputs[index]; break; }
        nextDefault = selected ? selected.id : "";
        defaultOutputId = nextDefault;
        if (selected) {
            _confirmedRaw = selected.volumeRaw;
            confirmedVolume = Math.max(0, Math.min(100, Math.round(selected.volumeRaw * 100 / _normalVolume)));
            muted = selected.muted; writable = selected.writable;
        } else {
            _confirmedRaw = 0; confirmedVolume = 0; muted = false; writable = false;
        }
        if (volumeGestureActive && (status !== "ready" || defaultOutputId !== volumeGestureOutputId))
            volumeGestureBlocked = true;
        if (volumeGestureActive) {
            const gestureOutput = outputById(volumeGestureOutputId);
            if (!gestureOutput || !gestureOutput.writable) volumeGestureBlocked = true;
        }
        _observationRevision++;
        if (!pendingKind) return;
        _matchingObservationSerial = pendingMatches() ? _pendingSerial : 0;
        if (_dispatchInProgressSerial === _pendingSerial) return;
        evaluatePending(false);
    }

    function snapshotPending() {
        return {kind: pendingKind, serial: _pendingSerial, timerSerial: _timerSerial,
            outputId: _pendingOutputId, targetLabel: _pendingTargetLabel,
            normalVolume: _pendingNormalVolume, desired: _desiredValue,
            deadline: _pendingDeadline, originScope: _pendingOriginScope,
            contextGeneration: _pendingContextGeneration, accepted: _pendingAccepted,
            observationFloor: _pendingObservationFloor, error: error};
    }
    function restoreRejectedSupersession(previous) {
        confirmation.stop();
        pendingKind = previous.kind; _pendingSerial = previous.serial; _timerSerial = previous.timerSerial;
        _pendingOutputId = previous.outputId; _pendingTargetLabel = previous.targetLabel;
        _pendingNormalVolume = previous.normalVolume;
        _desiredValue = previous.desired; _pendingDeadline = previous.deadline;
        _pendingOriginScope = previous.originScope; _pendingContextGeneration = previous.contextGeneration;
        _pendingAccepted = previous.accepted; _pendingObservationFloor = previous.observationFloor;
        _dispatchInProgressSerial = 0; _deadlineDeferredSerial = 0;
        _matchingObservationSerial = pendingMatches() && _observationRevision > _pendingObservationFloor
            ? _pendingSerial : 0;
        if (!contextMatches(_pendingOriginScope, _pendingContextGeneration)) { cancelPending(); return; }
        if (nowMs() >= _pendingDeadline || status !== "ready") {
            failPending(qsTr("O serviço de áudio não confirmou a alteração.")); return;
        }
        if (!outputById(_pendingOutputId)) {
            failPending(qsTr("A saída de áudio usada na alteração não está mais disponível.")); return;
        }
        error = qsTr("Não foi possível enviar o novo volume; a alteração anterior ainda aguarda confirmação.");
        evaluatePending(true);
    }
    function begin(kind, outputId, desired, dispatch, allowVolumeSupersession) {
        if (!active || status !== "ready" || !backend || typeof dispatch !== "function"
                || !requestOriginScope || requestContextGeneration < 0) return false;
        const superseding = pendingKind.length > 0;
        if (superseding && !(allowVolumeSupersession && kind === "volume"
                && pendingKind === "volume" && _pendingOutputId === outputId
                && _pendingAccepted && _dispatchInProgressSerial === 0)) return false;
        const previous = superseding ? snapshotPending() : null;
        const target = outputById(outputId);
        const capturedScope = requestOriginScope;
        const capturedGeneration = requestContextGeneration;
        const serial = ++_serial;
        cancelPending(); error = "";
        pendingKind = kind; _pendingSerial = serial; _timerSerial = serial;
        _pendingOutputId = outputId; _pendingTargetLabel = target ? boundedLabel(target.label) : "";
        _pendingNormalVolume = _normalVolume;
        _desiredValue = desired; _pendingDeadline = nowMs() + confirmationTimeout;
        _pendingOriginScope = capturedScope; _pendingContextGeneration = capturedGeneration;
        _pendingAccepted = false; _pendingObservationFloor = _observationRevision;
        _dispatchInProgressSerial = serial; _matchingObservationSerial = 0;
        scheduleRemaining();
        let submitted = false;
        try { submitted = dispatch() === true; } catch (_) { submitted = false; }
        if (_pendingSerial !== serial) return submitted;
        _dispatchInProgressSerial = 0;
        if (!submitted) {
            if (previous && contextMatches(previous.originScope, previous.contextGeneration))
                restoreRejectedSupersession(previous);
            else failPending(qsTr("Não foi possível enviar a alteração ao serviço de áudio."));
            return false;
        }
        if (!contextMatches(_pendingOriginScope, _pendingContextGeneration)) {
            cancelPending(); return true;
        }
        _pendingAccepted = true;
        evaluatePending(false);
        return true;
    }

    function requestVolume(percent) {
        const requested = finite(percent);
        if (!Number.isFinite(requested) || !writable || pendingKind || volumeGestureActive) return false;
        const outputId = defaultOutputId;
        const raw = Math.round(Math.max(0, Math.min(100, requested)) * _normalVolume / 100);
        if (raw === _confirmedRaw) return false;
        return begin("volume", outputId, raw, function() { return backend.setVolume(outputId, raw); }, false);
    }
    function beginVolumeGesture() {
        if (!active || status !== "ready" || !writable || pendingKind || volumeGestureActive) return false;
        const target = outputById(defaultOutputId);
        if (!target || !target.writable) return false;
        volumeGestureOutputId = defaultOutputId; volumeGestureBlocked = false; volumeGestureActive = true; return true;
    }
    function requestGestureVolume(percent) {
        const requested = finite(percent);
        if (!volumeGestureActive || volumeGestureBlocked || !Number.isFinite(requested)) return false;
        const target = outputById(volumeGestureOutputId);
        if (status !== "ready" || defaultOutputId !== volumeGestureOutputId || !target || !target.writable) {
            volumeGestureBlocked = true; return false;
        }
        const raw = Math.round(Math.max(0, Math.min(100, requested)) * _normalVolume / 100);
        if (!pendingKind && raw === _confirmedRaw) return false;
        return begin("volume", volumeGestureOutputId, raw,
            function() { return backend.setVolume(root.volumeGestureOutputId, raw); }, true);
    }
    function endVolumeGesture() { volumeGestureActive = false; volumeGestureBlocked = false; volumeGestureOutputId = ""; }
    function requestMute(value) {
        if (!writable || volumeGestureActive) return false;
        const outputId = defaultOutputId;
        const desired = Boolean(value);
        if (!pendingKind && desired === muted) return false;
        return begin("mute", outputId, desired, function() { return backend.setMuted(outputId, desired); }, false);
    }
    function requestDefaultOutput(id) {
        const outputId = String(id || "");
        if (!outputById(outputId) || (!pendingKind && outputId === defaultOutputId)) return false;
        return begin("default-output", outputId, outputId, function() { return backend.setDefaultOutput(outputId); }, false);
    }
    function retry() {
        if (!active || pendingKind || volumeGestureActive || !backend || typeof backend.retry !== "function") return false;
        let submitted = false;
        try { submitted = backend.retry(); } catch (_) { submitted = false; }
        if (!submitted) error = qsTr("Não foi possível reconectar ao serviço de áudio.");
        else error = "";
        return Boolean(submitted);
    }

    Timer {
        id: confirmation
        interval: Math.max(1, root.confirmationTimeout)
        repeat: false
        onTriggered: {
            if (!root.pendingKind || root._timerSerial !== root._pendingSerial) return;
            if (root._dispatchInProgressSerial === root._pendingSerial) {
                root._deadlineDeferredSerial = root._pendingSerial; return;
            }
            root.failPending(qsTr("O serviço de áudio não confirmou a alteração."));
        }
    }
    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onRevisionChanged() { root.refresh(); }
        function onSnapshotChanged() { root.refresh(); }
    }
    onActiveChanged: { invalidateLifecycle(); refresh(); }
    onBackendChanged: { invalidateLifecycle(); refresh(); }
    onRequestOriginScopeChanged: invalidateLifecycle()
    onRequestContextGenerationChanged: invalidateLifecycle()
    Component.onCompleted: refresh()
}
