.pragma library
// Unread counts for dock tiles. The integration service reads them from the
// Unity LauncherEntry signal; this file only maps tasks to desktop IDs and
// validates the service reply.

var queryLimit = 128;
var countLimit = 2147483647;
var idPattern = /^[A-Za-z0-9][A-Za-z0-9_.+-]{0,200}\.desktop$/;

// TaskManager launcher URLs are `applications:foo.desktop` or a file URL.
function desktopId(url) {
    const text = String(url || "");
    let name = "";
    if (text.indexOf("applications:") === 0) name = text.slice("applications:".length);
    else if (text.indexOf("file:///") === 0) name = text.slice(text.lastIndexOf("/") + 1);
    else return "";
    return idPattern.test(name) ? name : "";
}

// The unique, bounded list sent to the service; extra apps wait for a later poll.
function query(ids) {
    const unique = [];
    for (const id of ids || []) {
        if (typeof id === "string" && idPattern.test(id) && unique.indexOf(id) < 0) unique.push(id);
        if (unique.length === queryLimit) break;
    }
    return unique.sort();
}

// Returns {status, counts} or null when the reply is not the expected shape.
function parse(text, requested) {
    let value;
    try { value = JSON.parse(String(text)); } catch (_) { return null; }
    if (!value || typeof value !== "object" || value.schemaVersion !== 1) return null;
    if (value.status === "unavailable") return {status: "unavailable", counts: {}};
    if (value.status !== "ready" || !Array.isArray(value.entries) || value.entries.length > queryLimit) return null;
    const counts = {};
    for (const entry of value.entries) {
        if (!entry || typeof entry !== "object" || requested.indexOf(entry.desktopId) < 0
                || !Number.isInteger(entry.count) || entry.count < 1 || entry.count > countLimit
                || counts.hasOwnProperty(entry.desktopId)) return null;
        counts[entry.desktopId] = entry.count;
    }
    return {status: "ready", counts: counts};
}

function label(count) {
    return count > 99 ? "99+" : String(count);
}
