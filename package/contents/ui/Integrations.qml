import QtQuick
import org.kde.plasma.workspace.dbus as DBus

Item {
    id: root
    property bool active: false
    property bool loading: false
    property string error: ""
    property var snapshot: ({quota: {status: "missing", windows: [], costs: []}, peripherals: {status: "missing", devices: []}, recording: {status: "missing", state: "unknown"}})
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

    function acceptSnapshot(text) {
        try {
            const data = JSON.parse(text);
            if (data.schemaVersion !== 1 || !data.quota || !Array.isArray(data.quota.windows)
                || !data.peripherals || !Array.isArray(data.peripherals.devices) || !data.recording) {
                unavailable(qsTr("Formato de integração incompatível."));
                return false;
            }
            snapshot = data;
            error = "";
            return true;
        } catch (_) {
            unavailable(qsTr("Formato de integração incompatível."));
            return false;
        }
    }
    function unavailable(message) {
        snapshot = {quota: {status: "unknown", windows: [], costs: []}, peripherals: {status: "unknown", devices: []}, recording: {status: "unknown", state: "unknown"}};
        error = message;
    }
    function refresh() {
        if (loading || !active) return;
        loading = true;
        DBus.SessionBus.asyncCall({service: "org.caiodock.Integrations", path: "/org/caiodock/Integrations",
            iface: "org.caiodock.Integrations1", member: "Snapshot", signature: "()", arguments: []}, reply => {
                loading = false;
                acceptSnapshot(String(reply.value));
            }, reply => {
                loading = false;
                unavailable(qsTr("Ative as integrações locais pelo instalador do Orla Dock."));
            });
    }
    onActiveChanged: if (active) refresh()
    Component.onCompleted: if (active) refresh()
    Timer { interval: 15000; running: root.active; repeat: true; onTriggered: root.refresh() }
}
