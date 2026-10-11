.pragma library

// UPower display-device contract: https://upower.freedesktop.org/docs/UPower.html
// -1 is an unavailable value, never a measured zero.
function empty(status) {
    return {status: status, percent: -1, charging: "unknown", state: "unknown",
        onBattery: "unknown", estimatedTimeSeconds: -1, estimatedTimeKind: "unknown"};
}

function finiteNumber(value) {
    return typeof value === "number" && isFinite(value);
}

// Plasma's decoder retains D-Bus numeric value types with a .value member.
// See Plasma 6.7.5 components/dbus/dbusdecoder.cpp and dbustype.h.
function scalar(value) {
    return value !== null && typeof value === "object" && value.value !== undefined
        ? value.value : value;
}

function display(properties) {
    if (!properties || typeof properties !== "object" || Array.isArray(properties)
        || typeof properties.IsPresent !== "boolean") return empty("unavailable");
    if (!properties.IsPresent) return empty("absent");
    // DisplayDevice is the aggregate, not a real device: PowerSupply is not
    // among its guaranteed properties. Only battery/UPS types are accepted.
    const type = scalar(properties.Type);
    const percent = scalar(properties.Percentage);
    if ((type !== 2 && type !== 3) || !finiteNumber(percent) || percent < 0
        || percent > 100) return empty("unavailable");
    const result = empty("ready");
    result.percent = percent;
    const states = ["unknown", "charging", "discharging", "empty", "fully-charged",
        "pending-charge", "pending-discharge"];
    const state = scalar(properties.State);
    if (finiteNumber(state) && state % 1 === 0 && state >= 0 && state < states.length) {
        result.state = states[state];
        if (state > 0) result.charging = state === 1 ? "charging" : "not-charging";
    }
    const estimate = scalar(state === 1 ? properties.TimeToFull : state === 2 ? properties.TimeToEmpty : -1);
    if (finiteNumber(estimate) && estimate > 0 && estimate <= Number.MAX_SAFE_INTEGER && estimate % 1 === 0) {
        result.estimatedTimeSeconds = estimate;
        result.estimatedTimeKind = state === 1 ? "full" : "empty";
    }
    return result;
}
