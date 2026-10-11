import QtQuick

Item {
    id: root
    visible: false

    property bool active: false
    property var backend: null
    property int confirmationTimeout: 2000

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
        ? Math.max(0, Math.min(100, Math.round(Number(_desiredValue) * 100 / _normalVolume)))
        : confirmedVolume
    property bool volumeGestureActive: false
    property bool volumeGestureBlocked: false
    property string volumeGestureOutputId: ""

    property int _normalVolume: 65536
    property int _confirmedRaw: 0
    property int _serial: 0
    property int _pendingSerial: 0
    property int _timerSerial: 0
    property double _pendingDeadline: 0
    property string _pendingOutputId: ""
    property var _desiredValue: undefined

    function finite(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : NaN;
    }

    function boundedLabel(value) {
        return String(value || "").slice(0, 128).replace(/\s+/g, " ").trim();
    }

    function cancelPending() {
        confirmation.stop();
        _pendingSerial = 0;
        _timerSerial = 0;
        _pendingDeadline = 0;
        _pendingOutputId = "";
        _desiredValue = undefined;
        pendingKind = "";
    }

    function failPending(message) {
        cancelPending();
        error = message;
    }

    function outputById(id) {
        for (let index = 0; index < outputs.length; ++index) {
            if (outputs[index].id === id) return outputs[index];
        }
        return null;
    }

    function refresh() {
        if (!active) {
            cancelPending();
            status = "inactive";
            outputs = [];
            defaultOutputId = "";
            confirmedVolume = 0;
            muted = false;
            writable = false;
            error = "";
            endVolumeGesture();
            return;
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
            nextOutputs.push({
                id: id,
                label: boundedLabel(candidate.label) || qsTr("Saída sem nome"),
                volumeRaw: Math.max(0, Math.round(raw)),
                muted: Boolean(candidate.muted),
                writable: Boolean(candidate.writable),
                isDefault: Boolean(candidate.isDefault)
            });
        }
        outputs = nextOutputs;
        if (status === "ready" && outputs.length === 0) status = "absent";

        let nextDefault = snapshot ? String(snapshot.defaultOutputId || "") : "";
        let selected = null;
        for (let index = 0; index < outputs.length; ++index) {
            if (outputs[index].id === nextDefault) selected = outputs[index];
        }
        if (!selected) {
            for (let index = 0; index < outputs.length; ++index) {
                if (outputs[index].isDefault) { selected = outputs[index]; break; }
            }
        }
        if (selected) nextDefault = selected.id;
        else nextDefault = "";
        defaultOutputId = nextDefault;
        if (selected) {
            _confirmedRaw = selected.volumeRaw;
            confirmedVolume = Math.max(0, Math.min(100, Math.round(selected.volumeRaw * 100 / _normalVolume)));
            muted = selected.muted;
            writable = selected.writable;
        } else {
            _confirmedRaw = 0;
            confirmedVolume = 0;
            muted = false;
            writable = false;
        }

        if (volumeGestureActive && (status !== "ready" || defaultOutputId !== volumeGestureOutputId))
            volumeGestureBlocked = true;
        if (volumeGestureActive) {
            const gestureOutput = outputById(volumeGestureOutputId);
            if (!gestureOutput || !gestureOutput.writable) volumeGestureBlocked = true;
        }

        if (!pendingKind) return;
        if (status !== "ready") {
            failPending(qsTr("O serviço de áudio não confirmou a alteração."));
            return;
        }
        const pendingOutput = outputById(_pendingOutputId);
        if (!pendingOutput) {
            failPending(qsTr("A saída de áudio usada na alteração não está mais disponível."));
            return;
        }
        let observed = false;
        if (pendingKind === "volume") observed = pendingOutput.volumeRaw === _desiredValue;
        else if (pendingKind === "mute") observed = pendingOutput.muted === _desiredValue;
        else if (pendingKind === "default-output") observed = defaultOutputId === _desiredValue;
        if (observed) {
            cancelPending();
            error = "";
        }
    }

    function begin(kind, outputId, desired, dispatch, allowVolumeSupersession) {
        if (!active || status !== "ready" || !backend || typeof dispatch !== "function") return false;
        const superseding = pendingKind.length > 0;
        if (superseding && !(allowVolumeSupersession && kind === "volume"
                && pendingKind === "volume" && _pendingOutputId === outputId)) return false;
        const previous = superseding ? {
            kind: pendingKind, serial: _pendingSerial, timerSerial: _timerSerial,
            outputId: _pendingOutputId, desired: _desiredValue,
            deadline: _pendingDeadline, error: error
        } : null;
        _serial += 1;
        cancelPending();
        error = "";
        pendingKind = kind;
        _pendingSerial = _serial;
        _timerSerial = _serial;
        _pendingOutputId = outputId;
        _desiredValue = desired;
        _pendingDeadline = Date.now() + confirmationTimeout;
        confirmation.interval = Math.max(1, confirmationTimeout);
        confirmation.restart();
        let submitted = false;
        try { submitted = dispatch(); }
        catch (exception) { submitted = false; }
        if (!submitted) {
            if (previous) {
                confirmation.stop();
                pendingKind = previous.kind;
                _pendingSerial = previous.serial;
                _timerSerial = previous.timerSerial;
                _pendingOutputId = previous.outputId;
                _desiredValue = previous.desired;
                _pendingDeadline = previous.deadline;
                error = qsTr("Não foi possível enviar o novo volume; a alteração anterior ainda aguarda confirmação.");
                confirmation.interval = Math.max(1, previous.deadline - Date.now());
                confirmation.restart();
                return false;
            }
            failPending(qsTr("Não foi possível enviar a alteração ao serviço de áudio."));
            return false;
        }
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
        volumeGestureOutputId = defaultOutputId;
        volumeGestureBlocked = false;
        volumeGestureActive = true;
        return true;
    }

    function requestGestureVolume(percent) {
        const requested = finite(percent);
        if (!volumeGestureActive || volumeGestureBlocked || !Number.isFinite(requested)) return false;
        const target = outputById(volumeGestureOutputId);
        if (status !== "ready" || defaultOutputId !== volumeGestureOutputId || !target || !target.writable) {
            volumeGestureBlocked = true;
            return false;
        }
        const raw = Math.round(Math.max(0, Math.min(100, requested)) * _normalVolume / 100);
        if (!pendingKind && raw === _confirmedRaw) return false;
        return begin("volume", volumeGestureOutputId, raw,
            function() { return backend.setVolume(root.volumeGestureOutputId, raw); }, true);
    }

    function endVolumeGesture() {
        volumeGestureActive = false;
        volumeGestureBlocked = false;
        volumeGestureOutputId = "";
    }

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
        try { submitted = backend.retry(); }
        catch (exception) { submitted = false; }
        if (!submitted) error = qsTr("Não foi possível reconectar ao serviço de áudio.");
        else error = "";
        return Boolean(submitted);
    }

    Timer {
        id: confirmation
        interval: Math.max(1, root.confirmationTimeout)
        repeat: false
        onTriggered: {
            if (root.pendingKind && root._timerSerial === root._pendingSerial)
                root.failPending(qsTr("O serviço de áudio não confirmou a alteração."));
        }
    }

    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onRevisionChanged() { root.refresh(); }
        function onSnapshotChanged() { root.refresh(); }
    }
    onActiveChanged: refresh()
    onBackendChanged: refresh()
    Component.onCompleted: refresh()
}
