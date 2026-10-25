.pragma library

const kinds = ["mouse", "keyboard", "earbuds", "headset", "touchpad", "gamepad", "other"];
const levels = ["critical", "low", "good", "full"];
const charging = ["discharging", "charging", "full", "unknown"];
const backendCodes = ("type size utf8 json depth duplicate_key nonfinite fields format range lease file missing unsafe drift hash state busy limit not_found no_previous exists io").split(" ");
const codes = backendCodes.concat(["unavailable", "timeout", "invalid_response", "cleanup_failed", "source_changed", "cancelled"]);
const reasons = ("not_installed disabled profile_hidden export_missing export_invalid future expired ready stale unknown").split(" ");

function requireValue(ok) { if (!ok) throw new Error("invalid_response"); }
function fields(value, names) {
    requireValue(value !== null && typeof value === "object" && !Array.isArray(value));
    requireValue(Object.keys(value).sort().join(" ") === names.split(" ").sort().join(" "));
}
function integer(value, min, max) {
    return typeof value === "number" && isFinite(value) && Math.floor(value) === value && value >= min && value <= max;
}
function stamp(value) { return integer(value, 1, 9007199254740991); }
function percent(value) { return value === null || integer(value, 0, 100); }
function hex(value, length) { return typeof value === "string" && value.length === length && new RegExp("^[0-9a-f]{" + length + "}$").test(value); }
function choice(value, choices) { return typeof value === "string" && choices.indexOf(value) >= 0; }
function nullableHex(value, length) { return value === null || hex(value, length); }
// A name the user chose to share: up to 64 code points, no control characters, no edge spaces.
function displayName(value) {
    return typeof value === "string" && Array.from(value).length >= 1 && Array.from(value).length <= 64
        && value === value.trim() && !/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(value);
}

// Bound UTF-8 bytes before parsing. JSON.parse alone silently accepts duplicate keys.
function parse(text) {
    requireValue(typeof text === "string" && text.length <= 262144);
    let bytes = 0;
    for (let n = 0; n < text.length; n++) {
        const c = text.charCodeAt(n);
        if (c >= 0xd800 && c <= 0xdbff) {
            const low = text.charCodeAt(++n);
            requireValue(low >= 0xdc00 && low <= 0xdfff);
            bytes += 4;
        } else {
            requireValue(c < 0xdc00 || c > 0xdfff);
            bytes += c < 128 ? 1 : c < 2048 ? 2 : 3;
        }
        requireValue(bytes <= 262144);
    }
    let at = 0;
    function white() { while (at < text.length && /[ \t\r\n]/.test(text[at])) at++; }
    function string() {
        const start = at++;
        while (at < text.length) {
            const c = text[at++];
            if (c === "\\") at++;
            else if (c === '"') return JSON.parse(text.slice(start, at));
        }
        throw new Error("invalid_response");
    }
    function value(depth) {
        white();
        const c = text[at];
        if (c === "{" || c === "[") {
            requireValue(depth < 8);
            const object = c === "{";
            const result = object ? Object.create(null) : [];
            const end = object ? "}" : "]";
            at++;
            white();
            if (text[at] === end) { at++; return result; }
            while (true) {
                white();
                if (object) {
                    requireValue(text[at] === '"');
                    const key = string();
                    requireValue(!Object.prototype.hasOwnProperty.call(result, key));
                    white();
                    requireValue(text[at++] === ":");
                    result[key] = value(depth + 1);
                } else result.push(value(depth + 1));
                white();
                if (text[at] === end) { at++; return result; }
                requireValue(text[at++] === ",");
            }
        }
        if (c === '"') return string();
        const token = /^(?:null|true|false|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.slice(at));
        requireValue(token !== null);
        at += token[0].length;
        const result = JSON.parse(token[0]);
        requireValue(typeof result !== "number" || isFinite(result));
        return result;
    }
    const result = value(0);
    white();
    requireValue(at === text.length);
    return result;
}

function validate(p) {
    fields(p, "status generatedAt source producerVersion limited devices generatedAtMs expiresAtMs leaseMs addon");
    requireValue(choice(p.status, ["missing", "invalid", "ready", "stale", "unknown"]) && typeof p.limited === "boolean");
    requireValue(Array.isArray(p.devices) && p.devices.length <= 128);
    const a = p.addon;
    fields(a, "id sha256 enabled generation producerNamespace reason errorCode");
    requireValue(nullableHex(a.generation, 32) && nullableHex(a.sha256, 64) && typeof a.enabled === "boolean"
        && choice(a.reason, reasons) && (a.errorCode === null || choice(a.errorCode, backendCodes)));
    if (a.enabled) {
        requireValue(typeof a.id === "string" && a.id.length <= 120
            && /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+$/.test(a.id)
            && hex(a.sha256, 64) && hex(a.generation, 32)
            && typeof a.producerNamespace === "string" && /^[a-z][a-z0-9-]{0,63}$/.test(a.producerNamespace)
            && ["not_installed", "disabled"].indexOf(a.reason) < 0);
    } else requireValue(a.id === null && a.sha256 === null && a.producerNamespace === null
        && ["not_installed", "disabled"].indexOf(a.reason) >= 0);
    if (p.source === null) {
        requireValue(p.generatedAt === null && p.generatedAtMs === null && p.expiresAtMs === null
            && p.leaseMs === null && p.producerVersion === null && p.devices.length === 0
            && ["missing", "invalid"].indexOf(p.status) >= 0);
        requireValue(["not_installed", "disabled", "profile_hidden", "export_missing", "export_invalid"].indexOf(a.reason) >= 0);
        requireValue(p.status === (a.reason === "export_invalid" ? "invalid" : "missing"));
        return p;
    }
    requireValue(p.source === "addon" && a.enabled && a.errorCode === null
        && stamp(p.generatedAtMs) && stamp(p.expiresAtMs) && integer(p.leaseMs, 30000, 10800000)
        && p.leaseMs % 3000 === 0 && p.expiresAtMs === p.generatedAtMs + p.leaseMs
        && p.generatedAt === p.generatedAtMs / 1000
        && typeof p.producerVersion === "string" && /^[A-Za-z0-9.+_-]{1,40}$/.test(p.producerVersion));
    if (a.reason === "future" || a.reason === "expired") requireValue(p.status === "stale" && p.devices.length === 0 && p.limited);
    else requireValue(choice(p.status, ["ready", "stale", "unknown"]) && a.reason === p.status);
    const counts = {}, ordinals = {};
    for (const d of p.devices) counts[d.kind] = (counts[d.kind] || 0) + 1;
    for (const d of p.devices) {
        const named = d !== null && typeof d === "object" && Object.prototype.hasOwnProperty.call(d, "displayName");
        fields(d, "name kind percent level charging estimated stale present observedAt observedAtMs components"
            + (named ? " displayName" : ""));
        requireValue(!named || displayName(d.displayName));
        requireValue(choice(d.kind, kinds));
        ordinals[d.kind] = (ordinals[d.kind] || 0) + 1;
        requireValue(d.name === d.kind + (counts[d.kind] > 1 ? " " + ordinals[d.kind] : ""));
        requireValue(percent(d.percent) && (d.level === null || choice(d.level, levels)) && choice(d.charging, charging)
            && typeof d.estimated === "boolean" && typeof d.stale === "boolean" && typeof d.present === "boolean"
            && (d.observedAtMs === null || stamp(d.observedAtMs))
            && d.observedAt === (d.observedAtMs === null ? null : d.observedAtMs / 1000)
            && Array.isArray(d.components) && d.components.length <= 3);
        const labels = [];
        for (const c of d.components) {
            fields(c, "label percent charging");
            requireValue(choice(c.label, ["left", "right", "case"]) && labels.indexOf(c.label) < 0
                && percent(c.percent) && choice(c.charging, charging));
            labels.push(c.label);
        }
    }
    return p;
}

function decode(text) {
    try {
        const frame = parse(text);
        if (frame && frame.formatVersion === "0.1-experimental" && frame.ok === false) {
            fields(frame, "formatVersion ok error");
            fields(frame.error, "code committed generation");
            const e = frame.error;
            requireValue(choice(e.code, codes) && (e.committed === null || typeof e.committed === "boolean")
                && nullableHex(e.generation, 32) && (e.committed !== true || hex(e.generation, 32))
                && (e.committed !== false || e.generation === null));
            return {error: e.code};
        }
        fields(frame, "schemaVersion modules peripherals");
        requireValue(frame.schemaVersion === 2 && Array.isArray(frame.modules)
            && frame.modules.length === 1 && frame.modules[0] === "peripherals");
        return {value: validate(frame.peripherals)};
    } catch (_) { return {error: "invalid_response"}; }
}

function empty(active) { return {status: active ? "unknown" : "disabled", devices: []}; }
function identity(p) { return {generation: p.addon.generation, sha256: p.addon.sha256}; }
function matches(p, expected) {
    if (expected === null) return true;
    try {
        fields(expected, "generation sha256");
        return nullableHex(expected.generation, 32) && nullableHex(expected.sha256, 64)
            && p.addon.generation === expected.generation && p.addon.sha256 === expected.sha256;
    } catch (_) { return false; }
}
function clearDevice(d) {
    d.percent = null; d.level = null; d.charging = "unknown"; d.estimated = false;
    for (const c of d.components) { c.percent = null; c.charging = "unknown"; }
}
function current(value, now, freshnessFloor) {
    const p = JSON.parse(JSON.stringify(validate(value)));
    requireValue(stamp(now) && (freshnessFloor === undefined || stamp(freshnessFloor)));
    const ageNow = freshnessFloor === undefined ? now : Math.max(now, freshnessFloor);
    if (p.source !== "addon") return p;
    if (now < p.generatedAtMs || ageNow >= p.expiresAtMs) {
        p.status = "stale"; p.limited = true; p.devices = [];
        p.addon.reason = now < p.generatedAtMs ? "future" : "expired";
        return p;
    }
    // Disconnected devices stay out of the views, as in the producer's own widget.
    p.devices = p.devices.filter(d => d.present);
    for (const d of p.devices) {
        if (d.stale || d.observedAtMs === null || now < d.observedAtMs
                || d.observedAtMs > p.generatedAtMs || ageNow - d.observedAtMs >= p.leaseMs) {
            clearDevice(d); d.stale = true; p.limited = true;
        } else if (d.kind === "earbuds" && d.components.some(c => c.label === "case")
                && !d.components.some(c => (c.label === "left" || c.label === "right") && c.percent !== null)) {
            d.percent = null; d.level = null; d.charging = "unknown"; d.estimated = false;
        }
    }
    const ready = p.devices.some(d => d.percent !== null || d.level !== null || d.components.some(c => c.percent !== null));
    p.status = ready ? "ready" : p.devices.some(d => d.stale) ? "stale" : "unknown";
    p.addon.reason = p.status;
    return p;
}
function deadline(p, now) {
    if (!p || p.source !== "addon" || now < p.generatedAtMs || now >= p.expiresAtMs) return 0;
    let next = p.expiresAtMs;
    for (const d of p.devices) if (!d.stale && d.present && d.observedAtMs !== null)
        next = Math.min(next, d.observedAtMs + p.leaseMs);
    return next;
}
