import QtQuick
import "../code/Island.js" as Island

// Turns battery readings into island notices: the laptop plugged in or running
// low (UPower), and a paired phone running low (KDE Connect). Each reading is
// compared with the previous one, so only changes raise a notice.
QtObject {
    id: notices
    objectName: "islandNotices"
    required property var eventState
    property bool enabled: false
    // {percent, state} with UPower's Device.State, or null.
    property var power: null
    // [{id, name, charge, charging}] for paired, reachable phones.
    property var phones: []
    property var lastPower: null
    property var lastPhones: ({})

    function submit(notice, title, detail) {
        return eventState.submit({kind: "power", action: notice.action, value: notice.value,
            title: title, detail: detail}, Date.now());
    }
    function readPower() {
        const current = enabled ? power : null;
        const notice = Island.powerNotice(lastPower, current);
        lastPower = current;
        if (!notice) return false;
        return notice.action === "charging"
            ? submit(notice, qsTr("Carregando"), qsTr("%1% de bateria").arg(notice.value))
            : submit(notice, qsTr("Bateria fraca"), qsTr("%1% restantes").arg(notice.value));
    }
    function readPhones() {
        const seen = {};
        let raised = false;
        for (const phone of (enabled && phones) || []) {
            if (!phone || typeof phone.id !== "string" || !phone.id.length) continue;
            seen[phone.id] = {charge: phone.charge, charging: Boolean(phone.charging)};
            const notice = Island.phoneNotice(lastPhones[phone.id], seen[phone.id]);
            if (notice) raised = submit(notice, qsTr("Celular com bateria fraca"),
                Island.bounded(phone.name, 64) + " · " + notice.value + "%") || raised;
        }
        lastPhones = seen;
        return raised;
    }
    onPowerChanged: readPower()
    onPhonesChanged: readPhones()
    onEnabledChanged: { readPower(); readPhones(); }
}
