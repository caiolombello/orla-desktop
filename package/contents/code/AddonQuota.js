.pragma library
.import "AddonPeripherals.js" as Base

// Quota-usage snapshots from org.orla.Addons. Reuses the battery parser's
// bounded JSON and field checks; adds provider windows and their leases.
const states = ["ready", "stale", "unknown", "unavailable"];
const keys = ["primary", "secondary", "tertiary"];
const reasons = ("not_installed disabled profile_hidden export_missing export_invalid future expired ready stale unknown").split(" ");
const backendCodes = ("type size utf8 json depth duplicate_key nonfinite fields format range lease file missing unsafe drift hash state busy limit not_found no_previous exists io").split(" ");
const codes = backendCodes.concat(["unavailable", "timeout", "invalid_response", "cleanup_failed", "source_changed", "cancelled"]);

function validate(p) {
    Base.fields(p, "status generatedAt source producerVersion limited providers generatedAtMs expiresAtMs leaseMs addon");
    Base.requireValue(Base.choice(p.status, ["missing", "invalid", "ready", "stale", "unknown"]) && typeof p.limited === "boolean");
    Base.requireValue(Array.isArray(p.providers) && p.providers.length <= 32);
    const a = p.addon;
    Base.fields(a, "id sha256 enabled generation producerNamespace reason errorCode");
    Base.requireValue(Base.nullableHex(a.generation, 32) && Base.nullableHex(a.sha256, 64) && typeof a.enabled === "boolean"
        && Base.choice(a.reason, reasons) && (a.errorCode === null || Base.choice(a.errorCode, backendCodes)));
    if (a.enabled) {
        Base.requireValue(typeof a.id === "string" && a.id.length <= 120
            && /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+$/.test(a.id)
            && Base.hex(a.sha256, 64) && Base.hex(a.generation, 32)
            && typeof a.producerNamespace === "string" && /^[a-z][a-z0-9-]{0,63}$/.test(a.producerNamespace)
            && ["not_installed", "disabled"].indexOf(a.reason) < 0);
    } else Base.requireValue(a.id === null && a.sha256 === null && a.producerNamespace === null
        && ["not_installed", "disabled"].indexOf(a.reason) >= 0);
    if (p.source === null) {
        Base.requireValue(p.generatedAt === null && p.generatedAtMs === null && p.expiresAtMs === null
            && p.leaseMs === null && p.producerVersion === null && p.providers.length === 0
            && ["missing", "invalid"].indexOf(p.status) >= 0);
        Base.requireValue(["not_installed", "disabled", "profile_hidden", "export_missing", "export_invalid"].indexOf(a.reason) >= 0);
        Base.requireValue(p.status === (a.reason === "export_invalid" ? "invalid" : "missing"));
        return p;
    }
    Base.requireValue(p.source === "addon" && a.enabled && a.errorCode === null
        && Base.stamp(p.generatedAtMs) && Base.stamp(p.expiresAtMs) && Base.integer(p.leaseMs, 30000, 10800000)
        && p.leaseMs % 3000 === 0 && p.expiresAtMs === p.generatedAtMs + p.leaseMs
        && p.generatedAt === p.generatedAtMs / 1000
        && typeof p.producerVersion === "string" && /^[A-Za-z0-9.+_-]{1,40}$/.test(p.producerVersion));
    if (a.reason === "future" || a.reason === "expired") Base.requireValue(p.status === "stale" && p.providers.length === 0 && p.limited);
    else Base.requireValue(Base.choice(p.status, ["ready", "stale", "unknown"]) && a.reason === p.status);
    const ids = {};
    for (const provider of p.providers) {
        Base.fields(provider, "id state observedAt observedAtMs windows");
        Base.requireValue(typeof provider.id === "string" && /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/.test(provider.id)
            && !ids[provider.id] && Base.choice(provider.state, states)
            && (provider.observedAtMs === null || Base.stamp(provider.observedAtMs))
            && provider.observedAt === (provider.observedAtMs === null ? null : provider.observedAtMs / 1000)
            && Array.isArray(provider.windows) && provider.windows.length <= 3);
        ids[provider.id] = true;
        let order = -1;
        for (const window of provider.windows) {
            Base.fields(window, "key usedPercent windowMinutes resetAtMs");
            Base.requireValue(Base.choice(window.key, keys) && keys.indexOf(window.key) > order
                && Base.percent(window.usedPercent) && (window.usedPercent === null || provider.state === "ready")
                && (window.windowMinutes === null || Base.integer(window.windowMinutes, 1, 525600))
                && (window.resetAtMs === null || Base.stamp(window.resetAtMs)));
            order = keys.indexOf(window.key);
        }
    }
    return p;
}

function decode(text) {
    try {
        const frame = Base.parse(text);
        if (frame && frame.formatVersion === "0.1-experimental" && frame.ok === false) {
            Base.fields(frame, "formatVersion ok error");
            Base.fields(frame.error, "code committed generation");
            const e = frame.error;
            Base.requireValue(Base.choice(e.code, codes) && (e.committed === null || typeof e.committed === "boolean")
                && Base.nullableHex(e.generation, 32) && (e.committed !== true || Base.hex(e.generation, 32))
                && (e.committed !== false || e.generation === null));
            return {error: e.code};
        }
        Base.fields(frame, "schemaVersion modules quota");
        Base.requireValue(frame.schemaVersion === 2 && Array.isArray(frame.modules)
            && frame.modules.length === 1 && frame.modules[0] === "quota");
        return {value: validate(frame.quota)};
    } catch (_) { return {error: "invalid_response"}; }
}

function empty(active) { return {status: active ? "unknown" : "disabled", providers: []}; }
function identity(p) { return Base.identity(p); }
function matches(p, expected) { return Base.matches(p, expected); }

// Time re-evaluation: a lease or observation that ages out clears usage.
function current(value, now, freshnessFloor) {
    const p = JSON.parse(JSON.stringify(validate(value)));
    Base.requireValue(Base.stamp(now) && (freshnessFloor === undefined || Base.stamp(freshnessFloor)));
    const ageNow = freshnessFloor === undefined ? now : Math.max(now, freshnessFloor);
    if (p.source !== "addon") return p;
    if (now < p.generatedAtMs || ageNow >= p.expiresAtMs) {
        p.status = "stale"; p.limited = true; p.providers = [];
        p.addon.reason = now < p.generatedAtMs ? "future" : "expired";
        return p;
    }
    for (const provider of p.providers) {
        if (provider.state !== "ready") continue;
        const observed = provider.observedAtMs;
        if (observed === null || now < observed || observed > p.generatedAtMs || ageNow - observed >= p.leaseMs) {
            provider.state = "stale";
            for (const window of provider.windows) window.usedPercent = null;
            p.limited = true;
        }
    }
    const ready = p.providers.some(provider => provider.windows.some(window => window.usedPercent !== null));
    p.status = ready ? "ready" : p.providers.some(provider => provider.state === "stale") ? "stale" : "unknown";
    p.addon.reason = p.status;
    return p;
}

function deadline(p, now) {
    if (!p || p.source !== "addon" || now < p.generatedAtMs || now >= p.expiresAtMs) return 0;
    let next = p.expiresAtMs;
    for (const provider of p.providers) if (provider.state === "ready" && provider.observedAtMs !== null)
        next = Math.min(next, provider.observedAtMs + p.leaseMs);
    return next;
}
