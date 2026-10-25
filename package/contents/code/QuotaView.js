.pragma library
.import "Style.js" as Style

// Groups shared quota readings the way QuotaLantern's tray menu does: the
// bottleneck first, then providers at the limit, active, without a recent
// reading and not connected. Pure data; the view adds the words.

const limitAt = 90;   // Same thresholds as the quota tile's ring (Style.levels).
const warnAt = 75;

function finite(value) { return typeof value === "number" && isFinite(value); }

// The most used window of a provider, or null without any reading.
function worst(provider) {
    let found = null;
    for (const window of provider.windows || [])
        if (finite(window.usedPercent) && (found === null || window.usedPercent > found.usedPercent)) found = window;
    return found;
}
function level(percent) {
    return !finite(percent) ? "none" : percent >= limitAt ? "critical" : percent >= warnAt ? "low" : "good";
}
function color(percent) {
    const name = level(percent);
    return name === "critical" ? Style.levels.critical : name === "low" ? Style.levels.low : Style.levels.good;
}
// Section of a provider: "limit", "active", "stale" (no recent reading) or "offline".
function section(provider) {
    const top = worst(provider);
    if (top) return top.usedPercent >= limitAt ? "limit" : "active";
    if (provider.state === "stale" || provider.state === "unknown") return "stale";
    return (provider.windows || []).length ? "stale" : "offline";
}
function group(providers) {
    const order = ["limit", "active", "stale", "offline"];
    const sections = order.map(key => ({key: key, providers: []}));
    let bottleneck = null;
    for (const provider of providers || []) {
        sections[order.indexOf(section(provider))].providers.push(provider);
        const top = worst(provider);
        if (top && (bottleneck === null || top.usedPercent > bottleneck.window.usedPercent))
            bottleneck = {provider: provider, window: top};
    }
    // Inside a section, the most used first, as the tray ring reads.
    for (const part of sections)
        part.providers.sort((a, b) => ((worst(b) || {usedPercent: -1}).usedPercent) - ((worst(a) || {usedPercent: -1}).usedPercent));
    return {bottleneck: bottleneck, sections: sections.filter(part => part.providers.length > 0)};
}
// Window length in whole days, hours or minutes: {days, hours, minutes} with one set.
function span(minutes) {
    if (!finite(minutes) || minutes <= 0) return null;
    if (minutes % 1440 === 0) return {days: minutes / 1440};
    if (minutes % 60 === 0) return {hours: minutes / 60};
    return {minutes: minutes};
}
// Time left until a reset, rounded down to the two largest units.
function remaining(resetAtMs, nowMs) {
    if (!finite(resetAtMs) || !finite(nowMs)) return null;
    const left = Math.max(0, Math.floor((resetAtMs - nowMs) / 60000));
    return {days: Math.floor(left / 1440), hours: Math.floor(left % 1440 / 60), minutes: left % 60, total: left};
}
