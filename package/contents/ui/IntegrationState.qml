import QtQuick

Item {
    id: root
    property bool active: false
    property var enabledModules: []
    property var transport: null
    readonly property var selectedModules: active && Array.isArray(enabledModules)
        ? ["quota", "peripherals", "recording"].filter(module => enabledModules.indexOf(module) >= 0) : []
    readonly property string selectionKey: JSON.stringify(selectedModules)
    property bool loading: false
    property string error: ""
    property var snapshot: emptySnapshot([])
    QtObject {
        id: internal
        property bool completed: false
        property int generation: 0
        property var flight: null
    }
    readonly property var quota: snapshot.quota
    readonly property var peripherals: snapshot.peripherals
    readonly property var recording: snapshot.recording
    readonly property string quotaSummary: {
        if (error) return qsTr("Integração indisponível");
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
        if (error) return qsTr("Integração indisponível");
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
        if (peripherals.source === "daemon") parts.push(qsTr("coleta do daemon"));
        else if (peripherals.source === "oneshot") parts.push(qsTr("coleta pontual"));
        if (peripherals.producerVersion) parts.push("PeriGauge " + peripherals.producerVersion);
        if (typeof peripherals.generatedAt === "number" && isFinite(peripherals.generatedAt))
            parts.push(qsTr("atualizado em %1").arg(Qt.formatDateTime(new Date(peripherals.generatedAt * 1000), "d MMM, HH:mm")));
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
                        || (module === "peripherals" && !Array.isArray(item.devices))
                        || (module === "recording" && typeof item.state !== "string")) return null;
                value[module] = item;
            }
            return value;
        } catch (_) { return null; }
    }
    function acceptSnapshot(text, modules) {
        if (!Array.isArray(modules)) { unavailable(qsTr("Formato de integração incompatível.")); return false; }
        const value = decodeSnapshot(text, modules);
        publish(value || emptySnapshot(modules), value ? "" : qsTr("Formato de integração incompatível."));
        return value !== null;
    }
    function publish(value, message) {
        const generation = internal.generation;
        error = message;
        if (generation === internal.generation) snapshot = value;
    }
    function unavailable(message) { publish(emptySnapshot(selectedModules), message); }
    function selectionChanged() {
        const generation = ++internal.generation;
        publish(emptySnapshot(selectedModules), "");
        if (generation !== internal.generation) return;
        loading = internal.flight !== null && selectedModules.length > 0;
        Qt.callLater(refresh);
    }
    function finish(operation, reply, failed) {
        if (internal.flight !== operation || operation.settling) return;
        operation.settling = true;
        if (operation.generation === internal.generation && selectionKey === operation.key) {
            // Publish before releasing loading: observers may change the profile or refresh.
            if (failed) unavailable(qsTr("Atualize ou ative a ponte local nas integrações do instalador."));
            else acceptSnapshot(reply ? String(reply.value) : "", operation.modules);
        }
        const changed = operation.generation !== internal.generation;
        if (internal.flight !== operation) return;
        internal.flight = null;
        loading = false;
        if (changed) Qt.callLater(refresh);
    }
    function refresh() {
        if (!internal.completed || internal.flight !== null || !selectedModules.length) return;
        const modules = selectedModules.slice();
        const operation = {generation: internal.generation, key: selectionKey, modules: modules};
        internal.flight = operation;
        loading = true;
        // A loading observer can revoke the request before the transport dispatches it.
        if (operation.generation !== internal.generation) { finish(operation, null, true); return; }
        const message = {service: "org.caiodock.Integrations", path: "/org/caiodock/Integrations",
            iface: "org.caiodock.Integrations1", member: "SnapshotFor", signature: "(as)", arguments: [modules]};
        try {
            if (transport === null) { finish(operation, null, true); return; }
            transport.asyncCall(message, reply => finish(operation, reply, false), () => finish(operation, null, true));
        } catch (_) { finish(operation, null, true); }
    }
    onSelectionKeyChanged: selectionChanged()
    Component.onCompleted: { internal.completed = true; selectionChanged(); }
    Timer { interval: 15000; running: root.selectedModules.length > 0; repeat: true; onTriggered: root.refresh() }
}
