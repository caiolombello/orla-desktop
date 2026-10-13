import QtQuick
import QtQuick.Window
import "../controlcenter" as Shared

QtObject {
    id: root
    readonly property int apiVersion: 1
    readonly property string status: Shared.Registry.status
    readonly property bool available: Shared.Registry.apiVersion === apiVersion && status === "ready"
    readonly property bool isOpen: visibleForClient()
    readonly property string error: _error || ownerError()
    property string _error: ""
    property QtObject _dispatchOwner: null
    property Item _host: null
    property Item _anchor: null
    // Plasma panels use C++ QQuickViews rather than QML Window instances.
    property QtObject _window: null
    property int _requestGeneration: 0
    property bool _releasing: false

    function visibleForClient() {
        if (!_dispatchOwner) return false;
        try { return _dispatchOwner.controlCenterVisibleFor(root) === true; }
        catch (_) { return false; }
    }
    function ownerError() {
        if (!_dispatchOwner || typeof _dispatchOwner.controlCenterErrorFor !== "function") return "";
        try {
            const message = _dispatchOwner.controlCenterErrorFor(root);
            return typeof message === "string" ? message.replace(/\s+/g, " ").trim().slice(0, 256) : "";
        } catch (_) { return ""; }
    }
    function release() {
        if (_releasing) return;
        _releasing = true;
        _requestGeneration += 1;
        const previous = _dispatchOwner;
        _dispatchOwner = null;
        _host = null;
        _anchor = null;
        _window = null;
        // Release the accepted/prepared owner, never the next unique registry owner.
        if (Qt.isQtObject(previous)) {
            try { previous.releaseControlCenter(root); } catch (_) {}
        }
        _releasing = false;
    }
    function reconcile() {
        if (_releasing || !_dispatchOwner) return;
        if (!available || Shared.Registry.owner !== _dispatchOwner
                || !_host || !_anchor || !_window || !_window.visible
                || _host.Window.window !== _window || _anchor.Window.window !== _window)
            release();
    }
    function open(host, anchor) {
        if (_releasing) return false;
        release();
        _error = "";
        if (!available || !Shared.Registry.validHost(host, anchor)) {
            _error = status === "ambiguous" ? qsTr("Há mais de um dock disponível para a Central de Controle.")
                : qsTr("Central de Controle indisponível.");
            return false;
        }
        const candidate = Shared.Registry.owner;
        const registryGeneration = Shared.Registry.generation;
        const requestGeneration = _requestGeneration;
        _window = host.Window.window;
        _host = host;
        _anchor = anchor;
        // Remember before dispatch so a reentrant registry change can cancel it.
        _dispatchOwner = candidate;
        const accepted = Shared.Registry.requestOpen(root, host, anchor, apiVersion);
        if (_requestGeneration !== requestGeneration) return false;
        if (!accepted || _dispatchOwner !== candidate
                || Shared.Registry.generation !== registryGeneration || !available
                || !Shared.Registry.validHost(_host, _anchor)) {
            release();
            _error = qsTr("Não foi possível abrir a Central de Controle.");
            return false;
        }
        return true;
    }

    on_DispatchOwnerChanged: if (!_dispatchOwner && !_releasing) release()
    on_HostChanged: if (!_host && _dispatchOwner) release()
    on_AnchorChanged: if (!_anchor && _dispatchOwner) release()
    on_WindowChanged: if (!_window && _dispatchOwner) release()
    property Connections _registryChanges: Connections {
        target: Shared.Registry
        function onGenerationChanged() { root.reconcile(); }
        function onOwnerChanged() { root.reconcile(); }
        function onStatusChanged() { root.reconcile(); }
    }
    property Connections _hostChanges: Connections {
        target: root._host
        function onWindowChanged() { root.reconcile(); }
        function onVisibleChanged() { if (root._host && !root._host.visible) root.release(); }
    }
    property Connections _anchorChanges: Connections {
        target: root._anchor
        function onWindowChanged() { root.reconcile(); }
        function onVisibleChanged() { if (root._anchor && !root._anchor.visible) root.release(); }
        function onEnabledChanged() { if (root._anchor && !root._anchor.enabled) root.release(); }
    }
    property Connections _windowChanges: Connections {
        target: root._window
        function onVisibleChanged() { root.reconcile(); }
    }
    Component.onDestruction: release()
}
