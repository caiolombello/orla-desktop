import QtQuick

QtObject {
    id: state
    objectName: "localEventState"

    property bool enabled: false
    property var current: null
    property var pending: []
    property int sequence: 0
    readonly property int count: (current ? 1 : 0) + pending.length
    readonly property int maximumTransients: 8
    readonly property int completionDuration: 8000

    function cleanText(value, limit) {
        if (typeof value !== "string") return null;
        return value.replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, limit);
    }

    function validCompletion(event) {
        if (!event || typeof event !== "object" || Array.isArray(event)) return false;
        if (Object.keys(event).sort().join(",") !== "detail,key,kind,scope,title") return false;
        return event.kind === "completion" && event.key === "pomodoro:completion"
            && event.scope === "global" && cleanText(event.title, 96) !== null
            && cleanText(event.detail, 160) !== null;
    }

    function schedule(timestamp) {
        expiry.stop();
        if (!current) return;
        expiry.interval = Math.max(1, current.deadline - timestamp);
        expiry.restart();
    }

    function presentNext(timestamp) {
        while (pending.length && pending[0].deadline <= timestamp) pending = pending.slice(1);
        current = pending.length ? pending[0] : null;
        pending = pending.length ? pending.slice(1) : [];
        schedule(timestamp);
    }

    function submit(event, timestamp) {
        if (!enabled || !validCompletion(event) || typeof timestamp !== "number"
                || !isFinite(timestamp) || timestamp < 0) return false;
        const candidate = {
            kind: event.kind,
            key: event.key,
            scope: event.scope,
            title: cleanText(event.title, 96),
            detail: cleanText(event.detail, 160),
            sequence: ++sequence,
            deadline: timestamp + completionDuration
        };
        if (current && current.key === candidate.key && current.scope === candidate.scope) {
            candidate.sequence = current.sequence;
            current = candidate;
            schedule(timestamp);
            return true;
        }
        for (let index = 0; index < pending.length; index++) {
            if (pending[index].key === candidate.key && pending[index].scope === candidate.scope) {
                const next = pending.slice();
                candidate.sequence = next[index].sequence;
                next[index] = candidate;
                pending = next;
                return true;
            }
        }
        if (!current) {
            current = candidate;
            schedule(timestamp);
            return true;
        }
        if (count >= maximumTransients) pending = pending.slice(1);
        pending = pending.concat([candidate]);
        return true;
    }

    function advance(timestamp) {
        if (typeof timestamp !== "number" || !isFinite(timestamp)) return false;
        if (current && current.deadline <= timestamp) {
            current = null;
            presentNext(timestamp);
            return true;
        }
        schedule(timestamp);
        return false;
    }

    function dismiss() {
        const hadCurrent = Boolean(current);
        current = null;
        expiry.stop();
        if (pending.length) presentNext(Date.now());
        return hadCurrent;
    }

    function clear() {
        current = null;
        pending = [];
        expiry.stop();
    }

    onEnabledChanged: if (!enabled) clear()

    property Timer expiry: Timer {
        repeat: false
        onTriggered: state.advance(Date.now())
    }
}
