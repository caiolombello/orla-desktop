.pragma library

// Live activities for the top island, picked the way the iPhone's Dynamic
// Island does: one activity owns the capsule, a transient notice takes it over
// while it lasts, and privacy indicators ride along on the trailing edge.
// Plain JavaScript: IslandState.qml feeds it, the views only read the result.

var priorities = {meeting: 40, timer: 30, media: 20, privacy: 10};
// A meeting shows from this long before it starts until a bit after.
var meetingLead = 10 * 60 * 1000;
var meetingTail = 5 * 60 * 1000;
// Battery levels that raise a notice once while discharging.
var lowLevels = [20, 10];

function bounded(value, limit) {
    return String(value === undefined || value === null ? "" : value).slice(0, limit).replace(/\s+/g, " ").trim();
}

function privacyState(value) {
    return {microphone: Boolean(value && value.microphone), camera: Boolean(value && value.camera)};
}

// input: {meeting: {title, startMs, endMs, nowMs}, timer: {running,
// secondsLeft, isBreak}, media: {playing, held, title, artist, artUrl},
// privacy: {microphone, camera}}. Highest priority first.
function activities(input) {
    const source = input || {};
    const list = [];
    const meeting = source.meeting || {};
    const start = Number(meeting.startMs), now = Number(meeting.nowMs);
    if (Number.isFinite(start) && Number.isFinite(now) && start > 0)
        list.push({kind: "meeting", priority: priorities.meeting, title: bounded(meeting.title, 256),
            startMs: start, endMs: Number(meeting.endMs) || start,
            minutes: Math.max(0, Math.ceil((start - now) / 60000))});
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

// The calendar event the island should announce: the earliest timed event that
// starts within meetingLead or started less than meetingTail ago. All-day
// events never count. events: [{title, startMs, endMs, allDay}].
function nextMeeting(events, nowMs) {
    let best = null;
    for (const event of events || []) {
        const start = Number(event && event.startMs);
        if (!event || event.allDay || !Number.isFinite(start)) continue;
        if (start - nowMs > meetingLead || nowMs - start > meetingTail) continue;
        if (!best || start < best.startMs)
            best = {title: bounded(event.title, 256), startMs: start, endMs: Number(event.endMs) || start};
    }
    return best;
}

// UPower Device.State: 1 charging, 4 fully charged, 5 pending charge count as
// plugged in. Returns {action, value} for a notice, or null.
function pluggedIn(state) { return [1, 4, 5].indexOf(Number(state)) >= 0; }
function powerNotice(previous, current) {
    // An unknown state (0) is not "unplugged": the first real reading is no plug-in.
    if (!previous || !current || !Number(previous.state)) return null;
    const before = Number(previous.percent), now = Number(current.percent);
    if (!Number.isFinite(now) || now < 0 || now > 100) return null;
    const value = Math.round(now);
    if (!pluggedIn(previous.state) && pluggedIn(current.state)) return {action: "charging", value: value};
    if (pluggedIn(current.state) || !Number.isFinite(before)) return null;
    for (const level of lowLevels) {
        if (before > level && now <= level) return {action: "low", value: value};
    }
    return null;
}

// A paired phone through KDE Connect: {charge, charging}. Only the drop below a
// low level raises a notice; the phone shows its own charging.
function phoneNotice(previous, current) {
    if (!previous || !current || current.charging) return null;
    const before = Number(previous.charge), now = Number(current.charge);
    if (!Number.isFinite(before) || !Number.isFinite(now) || now < 0 || now > 100) return null;
    for (const level of lowLevels) {
        if (before > level && now <= level) return {action: "phone-low", value: Math.round(now)};
    }
    return null;
}
