import QtQuick

Item {
    id: root
    // Captured JavaScript record survives queued work without reading a destroyed QObject.
    property var callbackLifetime: ({alive: true})
    property bool active: false
    property var enabledModules: []
    property var transport: null
    property var selectedModules: []
    property string selectionKey: "[]"
    property bool addonSuspended: false
    property var addonIdentity: null
    property double nowMsOverride: -1
    property bool legacyLoading: false
    property bool addonLoading: false
    readonly property bool addonCallPending: addons.callPending
    property bool loading: false
    property string legacyError: ""
    property string addonError: ""
    property string addonErrorCode: ""
    property string error: ""
    property var legacyModules: []
    property string legacyKey: "[]"
    property var snapshot: emptySnapshot([])
    AddonPeripheralsState {
        id: addons
        active: root.active && root.selectedModules.indexOf("peripherals") >= 0
        suspended: root.addonSuspended
        // Read the inputs directly: derived selection may still be notifying observers.
        admissionAllowed: function() {
            return root.active && !root.addonSuspended && Array.isArray(root.enabledModules)
                && root.enabledModules.indexOf("peripherals") >= 0;
        }
        transport: root.transport
        expectedIdentity: root.addonIdentity
        nowMsOverride: root.nowMsOverride
        onLoadingChanged: root.addonLoading = loading
        onErrorCodeChanged: root.addonErrorChangedFrom(errorCode)
        onValueChanged: root.peripheralChanged(value)
    }
    QtObject {
        id: internal
        property bool completed: false
        property int generation: 0
        property var flight: null
        property var legacy: root.emptySnapshot([])
        property var peripheral: ({status: "disabled", devices: []})
    }
    readonly property var quota: snapshot.quota
    readonly property var peripherals: snapshot.peripherals
    readonly property var recording: snapshot.recording
    readonly property string quotaSummary: {
        if (legacyError) return qsTr("Integração indisponível");
        if (quota.status === "stale") return qsTr("Dados desatualizados");
        const windows = quota.windows || [];
        let selected = null;
        for (const window of windows) {
            if (!window.stale && typeof window.usedPercent === "number" && isFinite(window.usedPercent)
                && (!selected || window.usedPercent > selected.usedPercent)) selected = window;
        }
        return selected ? selected.provider + " · " + Math.round(selected.usedPercent) + "% usado"
            : qsTr("Sem leitura disponível");
    }
    readonly property string batterySummary: {
        if (addonError) return qsTr("Integração indisponível");
        const devices = peripherals.devices || [];
        const available = devices.filter(device => device.present !== false && !device.stale
            && typeof device.percent === "number" && isFinite(device.percent));
        available.sort((a, b) => a.percent - b.percent);
        if (available.length) return available[0].name + " · " + Math.round(available[0].percent) + "%";
        const absent = devices.find(device => device.present === false);
        if (absent) return absent.name + " · " + qsTr("fora de alcance");
        if (peripherals.status === "stale" || devices.some(device => device.stale)) return qsTr("Dados desatualizados");
        if (devices.length) return qsTr("Percentual desconhecido");
        return peripherals.status === "missing" ? qsTr("Sem cache local") : qsTr("Sem bateria disponível");
    }
    readonly property string peripheralsMetadataSummary: {
        const parts = [];
        if (peripherals.source === "addon") parts.push(qsTr("exportação local"));
        if (typeof peripherals.generatedAt === "number" && isFinite(peripherals.generatedAt))
            parts.push(qsTr("atualizado em %1").arg(new Date(peripherals.generatedAt * 1000).toLocaleString(Qt.locale(), "d MMM, HH:mm")));
        if (peripherals.limited === true) parts.push(qsTr("modelo limitado"));
        return parts.join(" · ");
    }
    readonly property string recordingSummary: recording.state === "stopped" ? qsTr("Sessão encerrada")
        : recording.state === "recording" ? qsTr("Estado salvo · gravando")
        : recording.state === "starting" ? qsTr("Estado salvo · iniciando")
        : recording.status === "idle" ? qsTr("Sem sessão registrada") : qsTr("Sem estado disponível")

    function emptySnapshot(modules) {
        return {quota: {status: modules.indexOf("quota") >= 0 ? "unknown" : "disabled", windows: [], costs: []},
            peripherals: {status: modules.indexOf("peripherals") >= 0 ? "unknown" : "disabled", devices: []},
            recording: {status: modules.indexOf("recording") >= 0 ? "unknown" : "disabled", state: "unknown"}};
    }
    function decodeSnapshot(text, modules) {
        try {
            const data = JSON.parse(text);
            if (!data || data.schemaVersion !== 2 || data.error
                    || JSON.stringify(data.modules) !== JSON.stringify(modules)) return null;
            const value = emptySnapshot(modules);
            for (const module of modules) {
                const item = data[module];
                if (!item || typeof item !== "object" || Array.isArray(item) || typeof item.status !== "string"
                        || (module === "quota" && !Array.isArray(item.windows))
                        || (module === "recording" && typeof item.state !== "string")) return null;
                value[module] = item;
            }
            return value;
        } catch (_) { return null; }
    }
    function errorFor(module) {
        return selectedModules.indexOf(module) < 0 ? "" : module === "peripherals" ? addonError : legacyError;
    }
    function invalidateAddons() { addons.invalidate(); }
    function acceptSnapshot(text, modules) {
        if (!Array.isArray(modules) || modules.indexOf("peripherals") >= 0) { unavailable(qsTr("Formato de integração incompatível.")); return false; }
        const value = decodeSnapshot(text, modules);
        publish(value || emptySnapshot(modules), value ? "" : qsTr("Formato de integração incompatível."));
        return value !== null;
    }
    function updateLoading() { loading = legacyLoading || addonLoading; }
    function updateError() {
        const hasAddon = selectedModules.indexOf("peripherals") >= 0;
        error = legacyModules.length && hasAddon ? (legacyError && addonError ? legacyError : "")
            : hasAddon ? addonError : legacyError;
    }
    function addonErrorChangedFrom(code) {
        addonErrorCode = code;
        if (addons.errorCode !== code) return;
        addonError = code ? qsTr("Integração de periféricos indisponível.") : "";
    }
    function syncSnapshot() {
        snapshot = {quota: internal.legacy.quota, peripherals: internal.peripheral, recording: internal.legacy.recording};
    }
    function peripheralChanged(value) { internal.peripheral = value; syncSnapshot(); }
    function publish(value, message) {
        const generation = internal.generation;
        legacyError = message;
        if (generation === internal.generation) { internal.legacy = value; syncSnapshot(); }
    }
    function unavailable(message) { publish(emptySnapshot(legacyModules), message); }
    function queueLegacyRefresh(generation) {
        const lifetime = callbackLifetime;
        Qt.callLater(function() {
            if (!lifetime.alive) return;
            if (generation === internal.generation) root.refreshLegacy();
        });
    }
    function selectionChanged(invalidateAddon) {
        if (!internal.completed) return;
        const generation = ++internal.generation;
        const selected = active && Array.isArray(enabledModules)
            ? ["quota", "peripherals", "recording"].filter(module => enabledModules.indexOf(module) >= 0) : [];
        const modules = selected.filter(module => module !== "peripherals");
        // Clear legacy state before addon notifications can reenter through snapshot.
        internal.legacy = emptySnapshot(modules);
        legacyModules = modules;
        if (generation !== internal.generation) return;
        legacyKey = JSON.stringify(modules);
        if (generation !== internal.generation) return;
        selectedModules = selected;
        if (generation !== internal.generation) return;
        selectionKey = JSON.stringify(selected);
        if (generation !== internal.generation) return;
        if (invalidateAddon) addons.invalidate();
        if (generation !== internal.generation) return;
        publish(internal.legacy, "");
        if (generation !== internal.generation) return;
        legacyLoading = internal.flight !== null && modules.length > 0;
        updateError();
        if (generation === internal.generation) queueLegacyRefresh(generation);
    }
    function finish(operation, reply, failed) {
        if (internal.flight !== operation || operation.settling) return;
        operation.settling = true;
        if (operation.generation === internal.generation && legacyKey === operation.key) {
            // Publish before releasing loading: observers may change the profile or refresh.
            if (failed) unavailable(qsTr("Atualize ou ative a ponte local nas integrações do instalador."));
            else acceptSnapshot(reply && typeof reply.value === "string" ? reply.value : "", operation.modules);
        }
        const changed = operation.generation !== internal.generation;
        if (internal.flight !== operation) return;
        internal.flight = null;
        legacyLoading = false;
        if (changed) queueLegacyRefresh(internal.generation);
    }
    function refresh() { if (!active) return; refreshLegacy(); if (active) addons.refresh(); }
    function refreshLegacy() {
        if (!internal.completed || !active || internal.flight !== null || !legacyModules.length) return;
        const modules = legacyModules.slice();
        const operation = {generation: internal.generation, key: legacyKey, modules: modules};
        internal.flight = operation;
        legacyLoading = true;
        // A loading observer can revoke the request before the transport dispatches it.
        if (operation.generation !== internal.generation) { finish(operation, null, true); return; }
        const message = {service: "org.caiodock.Integrations", path: "/org/caiodock/Integrations",
            iface: "org.caiodock.Integrations1", member: "SnapshotFor", signature: "(as)", arguments: [modules]};
        try {
            if (transport === null) { finish(operation, null, true); return; }
            const lifetime = callbackLifetime;
            transport.asyncCall(message,
                reply => { if (lifetime.alive) finish(operation, reply, false); },
                () => { if (lifetime.alive) finish(operation, null, true); });
        } catch (_) { finish(operation, null, true); }
    }
    onLegacyLoadingChanged: updateLoading()
    onAddonLoadingChanged: updateLoading()
    onLegacyErrorChanged: updateError()
    onAddonErrorChanged: updateError()
    onEnabledModulesChanged: selectionChanged(false)
    onActiveChanged: selectionChanged(true)
    Component.onDestruction: callbackLifetime.alive = false
    Component.onCompleted: { internal.completed = true; selectionChanged(true); }
    Timer { interval: 15000; running: root.selectedModules.length > 0; repeat: true; onTriggered: root.refreshLegacy() }
}
