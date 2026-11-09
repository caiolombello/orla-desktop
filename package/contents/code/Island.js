.pragma library

// Live activities for the top island, picked the way the iPhone's Dynamic
// Island does: one activity owns the capsule, a transient notice takes it over
// while it lasts, and privacy indicators ride along on the trailing edge.
// Plain JavaScript: IslandState.qml feeds it, the views only read the result.

var priorities = {timer: 30, media: 20, privacy: 10};

function bounded(value, limit) {
    return String(value === undefined || value === null ? "" : value).slice(0, limit).replace(/\s+/g, " ").trim();
}

function privacyState(value) {
    return {microphone: Boolean(value && value.microphone), camera: Boolean(value && value.camera)};
}

// input: {timer: {running, secondsLeft, isBreak}, media: {playing, held, title,
// artist, artUrl}, privacy: {microphone, camera}}. Highest priority first.
function activities(input) {
    const source = input || {};
    const list = [];
    const timer = source.timer || {};
    const seconds = Number(timer.secondsLeft);
    if (timer.running && Number.isFinite(seconds))
        list.push({kind: "timer", priority: priorities.timer, secondsLeft: Math.max(0, Math.floor(seconds)),
            isBreak: Boolean(timer.isBreak)});
    const media = source.media || {};
    if (media.playing || media.held)
        list.push({kind: "media", priority: priorities.media, playing: Boolean(media.playing),
            title: bounded(media.title, 256), artist: bounded(media.artist, 256),
            // Only local or HTTPS covers load, as in MediaState.
            artUrl: /^(https:\/\/|file:\/\/)\S{1,2040}$/.test(String(media.artUrl || "")) ? String(media.artUrl) : ""});
    // Privacy gets the capsule only when nothing else is live; otherwise it
    // stays a trailing indicator next to the other activity.
    const privacy = privacyState(source.privacy);
    if (!list.length && (privacy.microphone || privacy.camera))
        list.push({kind: "privacy", priority: priorities.privacy, microphone: privacy.microphone, camera: privacy.camera});
    list.sort((left, right) => right.priority - left.priority);
    return list;
}

// "transient" while a notice is up; otherwise "expanded" or "compact" when an
// activity is live, else "idle".
function mode(hasEvent, list, expanded) {
    if (hasEvent) return "transient";
    if (!list || !list.length) return "idle";
    return expanded ? "expanded" : "compact";
}

// "m:ss", or "h:mm:ss" past an hour.
function clock(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const hours = Math.floor(total / 3600), minutes = Math.floor(total % 3600 / 60), rest = total % 60;
    const pad = value => (value < 10 ? "0" : "") + value;
    return hours > 0 ? hours + ":" + pad(minutes) + ":" + pad(rest) : minutes + ":" + pad(rest);
}
