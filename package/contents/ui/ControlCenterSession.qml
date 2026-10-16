import QtQuick
import QtQuick.Window

// The dock owns state; hosts only lend an item/window for this opening.
Item {
    id: root
    visible: false
    required property Item owner
    property var popup: null
    property var audio: null
    property QtObject backendLifetime: null
    property var performOpen: null
    property var validateClient: function(candidate) { return false; }
    property Item host: owner
    property QtObject client: null
    readonly property bool dockOrigin: !_external
    readonly property bool interactionBusy: Boolean(popup && (popup.interactionBusy !== undefined
            ? popup.interactionBusy : popup.visible)) || _pending || _closing || !_closed
        || _retiringBackend !== null || _commitPending || commitQueue.running || focusQueue.running
        || _restoreGeneration >= 0 || _requestDepth > 0
        || Boolean(_nativeDialog && (_nativeDialog.visible || _nativeFocusHeld))
    property string error: ""
    property QtObject lastErrorClient: null

    readonly property QtObject _nativeDialog: popup && popup.nativeDialog ? popup.nativeDialog : null
    // Window.active also includes its transient family, not only keyboard ownership.
    readonly property bool _nativeFocusHeld: _nativeDialog
        ? (_nativeDialog.activeFocusItem !== undefined
            ? _nativeDialog.activeFocusItem !== null : _nativeDialog.active === true) : false
    readonly property QtObject _hostWindow: host ? host.Window.window : null
    readonly property QtObject _pendingWindow: _pendingHost ? _pendingHost.Window.window : null
    property int _requestDepth: 0
    property bool _commitPending: false
    property int _commitGeneration: 0
    property bool _external: false
    property Item _anchor: null
    property bool _pending: false
    property bool _pendingExternal: false
    property QtObject _pendingClient: null
    property Item _pendingHost: null
    property Item _pendingAnchor: null
    property int _generation: 0
    property int _pendingGeneration: -1
    property bool _closed: true
    property bool _closing: false
    property bool _stopped: false
    property QtObject _retiringBackend: null
    property Item _restoreTarget: null
    property Item _closingFocus: null
    property int _restoreGeneration: -1

    function queueCommit() {
        _commitGeneration++;
        _commitPending = true;
        commitQueue.restart();
    }
    function validHost(candidateHost, candidateAnchor) {
        const h = candidateHost as Item;
        const a = candidateAnchor as Item;
        if (!h || !a || !h.Window.window || !h.Window.window.visible || h.Window.window !== a.Window.window
                || !h.visible || !h.enabled || !a.visible || !a.enabled) return false;
        return true;
    }
    function validClient(candidate) {
        if (!(candidate as QtObject) || typeof validateClient !== "function") return false;
        try { return Boolean(validateClient(candidate)); } catch (_) { return false; }
    }
    function visibleFor(candidate) {
        return Boolean(candidate && _external && client === candidate && popup && popup.visible);
    }
    function errorFor(candidate) { return candidate && candidate === lastErrorClient ? error : ""; }
    function setError(candidate, message, generation = _generation) {
        if (_generation !== generation) return false;
        lastErrorClient = candidate as QtObject;
        if (_generation !== generation) return false;
        error = String(message || "").slice(0, 160);
        return _generation === generation;
    }
    function invalidateAudio() {
        if (audio && typeof audio.invalidateLifecycle === "function") audio.invalidateLifecycle();
    }
    function clearRestore(generation = _generation) {
        focusQueue.stop();
        if (_generation !== generation) return false;
        _restoreTarget = null;
        if (_generation !== generation) return false;
        _closingFocus = null;
        if (_generation !== generation) return false;
        _restoreGeneration = -1;
        return _generation === generation;
    }
    function clearPending(generation = _generation) {
        if (_generation !== generation) return false;
        _pending = false;
        if (_generation !== generation) return false;
        _pendingClient = null;
        if (_generation !== generation) return false;
        _pendingHost = null;
        if (_generation !== generation) return false;
        _pendingAnchor = null;
        if (_generation !== generation) return false;
        _pendingGeneration = -1;
        return _generation === generation;
    }
    function captureBackendLifetime(generation = _generation) {
        if (_generation !== generation) return false;
        // Loader.item clears before deleteLater destroys the backend QObject.
        if (popup && popup.visible && !_retiringBackend && backendLifetime)
            _retiringBackend = backendLifetime;
        return _generation === generation;
    }
    function beginClose(generation = _generation) {
        if (_generation !== generation || !clearRestore(generation)) return;
        if (!captureBackendLifetime(generation)) return;
        invalidateAudio();
        if (_generation !== generation) return;
        if (popup && popup.visible) {
            const alreadyClosing = _closing;
            _closed = false;
            if (_generation !== generation) return;
            _closing = true;
            if (_generation !== generation) return;
            if (!alreadyClosing) popup.close();
            if (_generation !== generation) return;
        }
        queueCommit();
    }
    function request(candidate, candidateHost, candidateAnchor, external) {
        const beforeValidation = _generation;
        _requestDepth++;
        try {
            const valid = !_stopped && owner && popup && typeof performOpen === "function"
                && validHost(candidateHost, candidateAnchor) && (!external || validClient(candidate));
            if (_generation !== beforeValidation) return false;
            if (!valid) {
                setError(candidate, qsTr("A Central de Controle está indisponível."), beforeValidation);
                return false;
            }
            const generation = _generation + 1;
            _generation = generation;
            if (!clearPending(generation)) return true;
            _pendingExternal = external;
            if (_generation !== generation) return true;
            _pendingClient = candidate;
            if (_generation !== generation) return true;
            _pendingHost = candidateHost;
            if (_generation !== generation) return true;
            _pendingAnchor = candidateAnchor;
            if (_generation !== generation) return true;
            _pendingGeneration = generation;
            if (_generation !== generation) return true;
            _pending = true;
            if (_generation !== generation || !setError(candidate, "", generation)) return true;
            beginClose(generation);
            return true;
        } finally {
            _requestDepth--;
        }
    }
    function openFromDock(anchor) { return request(null, owner, anchor, false); }
    function openFromClient(candidate, candidateHost, anchor) { return request(candidate, candidateHost, anchor, true); }
    function releaseClient(candidate) {
        if (!candidate) return;
        if (_pending && _pendingExternal && _pendingClient === candidate) {
            const generation = _generation + 1;
            _generation = generation;
            if (!clearPending(generation) || !clearRestore(generation)) return;
        }
        if (_external && client === candidate) beginClose();
    }
    function closeDockOrigin() {
        if (_pending && !_pendingExternal) {
            const generation = _generation + 1;
            _generation = generation;
            if (!clearPending(generation)) return;
        }
        if (!_external) beginClose();
    }
    function close() {
        const generation = _generation + 1;
        _generation = generation;
        if (clearPending(generation)) beginClose(generation);
    }
    function shutdown() {
        if (_stopped) return;
        _stopped = true;
        close();
        commitQueue.stop();
        _commitGeneration++;
        _commitPending = false;
        focusQueue.stop();
    }
    function pendingLost() {
        if (!_pending) return;
        const generation = _generation;
        if (!setError(_pendingClient, qsTr("Não foi possível abrir a Central de Controle."), generation)) return;
        const cancellation = generation + 1;
        _generation = cancellation;
        if (!clearPending(cancellation) || !clearRestore(cancellation)) return;
        queueCommit();
    }
    function checkPending() {
        if (_pending && (!validHost(_pendingHost, _pendingAnchor)
                || (_pendingExternal && !validClient(_pendingClient)))) pendingLost();
    }
    function checkCurrent() {
        if (!_stopped && popup && popup.visible && !_closing
                && (!validHost(host, _anchor) || (_external && !client))) close();
    }
    onHostChanged: checkCurrent()
    on_AnchorChanged: checkCurrent()
    onClientChanged: checkCurrent()
    on_PendingHostChanged: checkPending()
    on_PendingAnchorChanged: checkPending()
    on_PendingClientChanged: checkPending()
    onOwnerChanged: if (!owner) shutdown()
    on_NativeDialogChanged: queueCommit()
    on_NativeFocusHeldChanged: if (!_nativeFocusHeld) queueCommit()
    on_RetiringBackendChanged: if (!_retiringBackend && !_stopped) queueCommit()

    function pendingMatches(request) {
        return !_stopped && owner && popup && _pending && _generation === request.generation
            && _pendingGeneration === request.generation && _pendingClient === request.client
            && _pendingHost === request.host && _pendingAnchor === request.anchor
            && _pendingExternal === request.external;
    }
    function drain() {
        if (_stopped || !owner || !popup || !_closed || popup.visible || _retiringBackend
                || (_nativeDialog && (_nativeDialog.visible || _nativeFocusHeld))) return;
        // Signals can accept another request at every assignment below.
        const request = {generation: _generation, client: _pendingClient, host: _pendingHost,
            anchor: _pendingAnchor, external: _pendingExternal};
        const hadPending = _pending;
        _closing = false;
        if (_generation !== request.generation) return;
        if (!hadPending) {
            host = owner;
            if (_generation === request.generation) focusQueue.restart();
            return;
        }
        const valid = pendingMatches(request) && validHost(request.host, request.anchor)
            && (!request.external || validClient(request.client));
        if (!pendingMatches(request)) return;
        if (!valid) {
            if (!setError(request.client, qsTr("Não foi possível abrir a Central de Controle."), request.generation)) return;
            if (clearPending(request.generation)) host = owner;
            return;
        }
        host = request.host;
        if (!pendingMatches(request)) return;
        client = request.client;
        if (!pendingMatches(request)) return;
        _external = request.external;
        if (!pendingMatches(request)) return;
        _anchor = request.anchor;
        if (!pendingMatches(request)) return;
        if (!clearPending(request.generation)) return;
        if (_stopped || !owner || !popup || _generation !== request.generation) return;
        try {
            performOpen(request.host, request.anchor);
            if (_generation !== request.generation || _stopped || !owner || !popup) return;
            if (!popup.visible) throw new Error("popup did not open");
        } catch (_) {
            if (_generation !== request.generation || _stopped || !owner || !popup) return;
            if (setError(request.client, qsTr("Não foi possível abrir a Central de Controle."), request.generation)) close();
        }
    }
    Timer {
        id: commitQueue
        interval: 0
        onTriggered: {
            const generation = root._commitGeneration;
            try { root.drain(); }
            finally { if (generation === root._commitGeneration) root._commitPending = false; }
        }
    }
    Timer {
        id: focusQueue
        interval: 0
        onTriggered: {
            const generation = root._generation;
            if (!root._stopped && root.owner && !root._pending && root.popup && !root.popup.visible
                    && root._restoreGeneration === root._generation && root._restoreTarget) {
                const window = root._restoreTarget.Window.window;
                const focused = window ? window.activeFocusItem : null;
                // A different live control owns the user's newer focus choice.
                const restoreAllowed = !focused || focused === window.contentItem
                    || focused === root._restoreTarget || focused === root._closingFocus
                    || !focused.visible || !focused.enabled;
                if (window && window.active && restoreAllowed
                        && root._restoreTarget.visible && root._restoreTarget.enabled)
                    root._restoreTarget.forceActiveFocus(Qt.PopupFocusReason);
            }
            if (root._generation === generation) root.clearRestore(generation);
        }
    }
    Connections {
        target: root.popup
        function onAboutToHide() {
            if (root._closing) return;
            const target = root._anchor;
            const window = target ? target.Window.window : null;
            const closingFocus = window ? window.activeFocusItem : null;
            const generation = root._generation + 1;
            root._generation = generation;
            if (!root.clearPending(generation)) return;
            if (!root.captureBackendLifetime(generation)) return;
            root.invalidateAudio();
            if (root._generation !== generation) return;
            root._restoreTarget = target;
            if (root._generation !== generation) return;
            root._closingFocus = closingFocus;
            if (root._generation !== generation) return;
            root._restoreGeneration = generation;
            if (root._generation !== generation) return;
            root._closing = true;
            if (root._generation === generation) root._closed = false;
        }
        function onClosed() {
            root.popup.anchorControl = null;
            root._closed = true;
            root.queueCommit();
        }
    }
    Connections {
        target: root._nativeDialog
        function onVisibleChanged() { if (!target.visible) root.queueCommit(); }
    }
    Connections {
        target: root._nativeDialog && root._nativeDialog.active !== undefined ? root._nativeDialog : null
        function onActiveChanged() { if (!target.active) root.queueCommit(); }
    }
    Connections {
        target: root.host
        function onWindowChanged() { root.checkCurrent(); }
        function onVisibleChanged() { root.checkCurrent(); }
        function onEnabledChanged() { root.checkCurrent(); }
    }
    Connections {
        target: root._anchor
        function onWindowChanged() { root.checkCurrent(); }
        function onParentChanged() { root.checkCurrent(); }
        function onVisibleChanged() { root.checkCurrent(); }
        function onEnabledChanged() { root.checkCurrent(); }
    }
    Connections {
        target: root._pendingHost
        function onWindowChanged() { root.checkPending(); }
        function onVisibleChanged() { root.checkPending(); }
        function onEnabledChanged() { root.checkPending(); }
    }
    Connections {
        target: root._pendingAnchor
        function onWindowChanged() { root.checkPending(); }
        function onParentChanged() { root.checkPending(); }
        function onVisibleChanged() { root.checkPending(); }
        function onEnabledChanged() { root.checkPending(); }
    }
    Connections {
        target: root._hostWindow
        function onVisibleChanged() { root.checkCurrent(); }
    }
    Connections {
        target: root._pendingWindow
        function onVisibleChanged() { root.checkPending(); }
    }
    Component.onDestruction: shutdown()
}
