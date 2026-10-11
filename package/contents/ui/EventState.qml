import QtQuick

QtObject {
    id: state
    objectName: "localEventState"

    property bool enabled: true
    property bool completionEnabled: enabled
    property bool audioEnabled: enabled
    property string activeScope: ""
    property int activeContextGeneration: -1
    property var nowProvider: function() { return Date.now(); }
    property var current: null
    property var pending: []
    property int sequence: 0
    readonly property int count: (current ? 1 : 0) + pending.length
    readonly property int maximumTransients: 8
    readonly property int completionDuration: 8000
    readonly property int audioDuration: 1800
    readonly property int completionPriority: 10
    readonly property int audioPriority: 20
    readonly property int audioQuietDelay: 200
    readonly property int audioMaximumDelay: 1000

    property string _audioCycleIdentity: ""
    property int _audioCycleSequence: 0
    property bool _audioCycleAnnounced: false
    property string _latestAccessibleName: ""

    signal announcementRequested(var event)

    function nowMs() {
        try {
            const value = Number(nowProvider());
            return Number.isFinite(value) ? value : Date.now();
        } catch (_) { return Date.now(); }
    }
    function cleanText(value, limit) {
        if (typeof value !== "string" || value.length > limit) return null;
        return value.replace(/[\u0000-\u001f\u007f]/g, " ");
    }
    function exactKeys(value, expected) {
        return value && typeof value === "object" && !Array.isArray(value)
            && Object.keys(value).sort().join(",") === expected.slice().sort().join(",");
    }
    function validCompletion(event) {
        return exactKeys(event, ["detail", "key", "kind", "scope", "title"])
            && event.kind === "completion" && event.key === "pomodoro:completion"
            && event.scope === "global" && cleanText(event.title, 96) !== null
            && cleanText(event.detail, 160) !== null;
    }
    function validAudio(event) {
        if (!exactKeys(event, ["action", "contextGeneration", "detail", "kind",
                "originScope", "targetId", "title", "value"])) return false;
        if (event.kind !== "audio" || ["volume", "mute", "default-output"].indexOf(event.action) < 0
                || typeof event.originScope !== "string" || !event.originScope.length
                || event.originScope.length > 96 || !Number.isInteger(event.contextGeneration)
                || event.contextGeneration < 0 || typeof event.targetId !== "string"
                || !event.targetId.length || event.targetId.length > 256
                || cleanText(event.originScope, 96) !== event.originScope
                || cleanText(event.targetId, 256) !== event.targetId
                || cleanText(event.title, 96) === null || cleanText(event.detail, 160) === null) return false;
        if (event.action === "volume") return Number.isInteger(event.value) && event.value >= 0 && event.value <= 100;
        if (event.action === "mute") return typeof event.value === "boolean";
        return typeof event.value === "string" && event.value === event.targetId;
    }
    function identity(event) {
        return event.kind === "completion" ? "completion\u0000global\u0000pomodoro:completion"
            : ["audio", event.originScope, event.contextGeneration, event.action, event.targetId].join("\u0000");
    }
    function normalize(event, timestamp, assignedSequence) {
        if (event.kind === "completion") return {
            kind: "completion", key: "pomodoro:completion", scope: "global",
            title: cleanText(event.title, 96), detail: cleanText(event.detail, 160),
            identity: identity(event), priority: completionPriority, sequence: assignedSequence,
            deadline: timestamp + completionDuration, announced: false
        };
        return {
            kind: "audio", action: event.action, targetId: event.targetId,
            originScope: event.originScope, contextGeneration: event.contextGeneration,
            value: event.value, title: cleanText(event.title, 96), detail: cleanText(event.detail, 160),
            identity: identity(event), priority: audioPriority, sequence: assignedSequence,
            deadline: timestamp + audioDuration
        };
    }
    function compare(left, right) {
        if (left.priority !== right.priority) return right.priority - left.priority;
        return left.sequence - right.sequence;
    }
    function selectPrevalidated(records) {
        const ordered = records.slice().sort(compare);
        const selected = ordered.length ? ordered[0] : null;
        let rest = ordered.slice(1);
        while (rest.length > maximumTransients - 1) {
            let victim = 0;
            for (let index = 1; index < rest.length; ++index) {
                if (rest[index].priority < rest[victim].priority
                        || (rest[index].priority === rest[victim].priority
                            && rest[index].sequence < rest[victim].sequence)) victim = index;
            }
            rest.splice(victim, 1);
        }
        rest.sort(compare);
        return {current: selected, pending: rest};
    }
    function allEvents() { return (current ? [current] : []).concat(pending); }
    function fullName(event) { return event.title + (event.detail ? ". " + event.detail : ""); }
    function cancelAudioAnnouncement() {
        audioQuiet.stop(); audioMaximum.stop();
        _audioCycleIdentity = ""; _audioCycleSequence = 0;
        _audioCycleAnnounced = false; _latestAccessibleName = "";
    }
    function startAudioCycle(event) {
        cancelAudioAnnouncement();
        _audioCycleIdentity = event.identity; _audioCycleSequence = event.sequence;
        _latestAccessibleName = fullName(event);
        audioQuiet.interval = audioQuietDelay; audioMaximum.interval = audioMaximumDelay;
        audioQuiet.restart(); audioMaximum.restart();
    }
    function presentCurrent(previous, timestamp, coalescedCurrent) {
        schedule(timestamp);
        if (!current) { cancelAudioAnnouncement(); return; }
        const same = previous && previous.identity === current.identity && previous.sequence === current.sequence;
        if (current.kind === "completion") {
            cancelAudioAnnouncement();
            if (!current.announced) {
                const next = Object.assign({}, current, {announced: true});
                current = next;
                announcementRequested(next);
            }
            return;
        }
        if (!same || _audioCycleIdentity !== current.identity || _audioCycleSequence !== current.sequence) {
            startAudioCycle(current); return;
        }
        _latestAccessibleName = fullName(current);
        if (_audioCycleAnnounced) startAudioCycle(current);
        else if (coalescedCurrent) { audioQuiet.interval = audioQuietDelay; audioQuiet.restart(); }
    }
    function schedule(timestamp) {
        expiry.stop();
        if (!current) return;
        expiry.interval = Math.max(1, current.deadline - timestamp);
        expiry.restart();
    }
    function applyPool(pool, timestamp, coalescedCurrent) {
        const previous = current;
        const selected = selectPrevalidated(pool);
        current = selected.current;
        pending = selected.pending;
        presentCurrent(previous, timestamp, coalescedCurrent);
    }
    function prune(timestamp) {
        const survivors = allEvents().filter(event => event.deadline > timestamp);
        if (survivors.length === count) return false;
        applyPool(survivors, timestamp, false);
        return true;
    }
    function admitted(event) {
        if (event.kind === "completion") return completionEnabled && validCompletion(event);
        return audioEnabled && validAudio(event)
            && event.originScope === activeScope
            && event.contextGeneration === activeContextGeneration;
    }
    function submit(event, timestamp) {
        if (typeof timestamp !== "number" || !Number.isFinite(timestamp) || timestamp < 0) return false;
        prune(timestamp);
        if (!event || typeof event !== "object" || !admitted(event)) return false;
        const incomingIdentity = identity(event);
        if (current && current.identity === incomingIdentity) {
            const next = normalize(event, timestamp, current.sequence);
            if (current.kind === "completion") next.announced = current.announced;
            current = next;
            presentCurrent(current, timestamp, true);
            return true;
        }
        for (let index = 0; index < pending.length; ++index) {
            if (pending[index].identity !== incomingIdentity) continue;
            const nextPending = pending.slice();
            const next = normalize(event, timestamp, nextPending[index].sequence);
            if (next.kind === "completion") next.announced = nextPending[index].announced;
            nextPending[index] = next;
            pending = nextPending.sort(compare);
            return true;
        }
        const candidate = normalize(event, timestamp, ++sequence);
        const pool = allEvents().concat([candidate]);
        applyPool(pool, timestamp, false);
        return Boolean((current && current.sequence === candidate.sequence)
            || pending.some(entry => entry.sequence === candidate.sequence));
    }
    function advance(timestamp) {
        if (typeof timestamp !== "number" || !Number.isFinite(timestamp)) return false;
        const changed = prune(timestamp);
        schedule(timestamp);
        return changed;
    }
    function dismiss(timestamp) {
        const hadCurrent = Boolean(current);
        if (!hadCurrent) return false;
        const now = typeof timestamp === "number" && Number.isFinite(timestamp) ? timestamp : nowMs();
        cancelAudioAnnouncement();
        const survivors = pending.filter(event => event.deadline > now);
        // Replace directly so a queued promotion never exposes an empty surface.
        applyPool(survivors, now, false);
        return true;
    }
    function removeKind(kind) {
        const now = nowMs();
        const survivors = allEvents().filter(event => event.kind !== kind && event.deadline > now);
        applyPool(survivors, now, false);
    }
    function clear() {
        current = null; pending = []; expiry.stop(); cancelAudioAnnouncement();
    }
    function finishAudioAnnouncement(timestamp) {
        if (!_audioCycleIdentity || _audioCycleAnnounced || !current || current.kind !== "audio"
                || current.identity !== _audioCycleIdentity || current.sequence !== _audioCycleSequence
                || !audioEnabled || current.originScope !== activeScope
                || current.contextGeneration !== activeContextGeneration || current.deadline <= timestamp) {
            cancelAudioAnnouncement(); return false;
        }
        _audioCycleAnnounced = true;
        audioQuiet.stop(); audioMaximum.stop();
        announcementRequested(Object.assign({}, current, {accessibleName: _latestAccessibleName}));
        return true;
    }
    function fireAudioQuiet(timestamp) {
        return finishAudioAnnouncement(timestamp === undefined ? nowMs() : timestamp);
    }
    function fireAudioMaximum(timestamp) {
        return finishAudioAnnouncement(timestamp === undefined ? nowMs() : timestamp);
    }

    onEnabledChanged: if (!enabled) clear()
    onCompletionEnabledChanged: if (!completionEnabled) removeKind("completion")
    onAudioEnabledChanged: if (!audioEnabled) removeKind("audio")
    onActiveScopeChanged: removeKind("audio")
    onActiveContextGenerationChanged: removeKind("audio")

    property Timer expiry: Timer { repeat: false; onTriggered: state.advance(state.nowMs()) }
    property Timer audioQuiet: Timer { repeat: false; onTriggered: state.fireAudioQuiet() }
    property Timer audioMaximum: Timer { repeat: false; onTriggered: state.fireAudioMaximum() }
}
