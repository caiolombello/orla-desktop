.pragma library
.import "Theme.js" as Theme
var formatVersion = "0.1-experimental";
var codes = ["type", "size", "utf8", "json", "depth", "duplicate_key", "nonfinite", "unknown_key",
    "required", "format_version", "length", "format", "range", "file", "busy", "timeout", "unavailable",
    "invalid_response", "cleanup_failed"];
// Plasma decodes the single D-Bus string argument into a STRING value type.
function replyText(reply) {
    if (!reply || !reply.values || typeof reply.values !== "object" || reply.values.length !== 1) return undefined;
    const value = reply.value;
    return value && typeof value === "object" && !Array.isArray(value) && typeof value.value === "string"
        ? value.value : undefined;
}
// Only Qt selectedFile.toString() display form, not arbitrary URI normalization.
function encodedSelection(text) {
    if (typeof text !== "string" || !text.length) return "";
    try { return encodeURI(text).replace(/%25([0-9a-fA-F]{2})/g, "%$1"); }
    catch (_) { return ""; }
}
function decode(raw) {
    const invalid = {code: "invalid_response"};
    const parsed = Theme.parseDocument(raw, value => {
        if (value === null || typeof value !== "object" || Array.isArray(value)
                || value.formatVersion !== formatVersion) return invalid;
        const keys = Object.keys(value);
        if (value.valid === true && keys.length === 3 && keys.every(key => ["formatVersion", "valid", "theme"].indexOf(key) >= 0)) {
            const theme = Theme.validate(value.theme);
            return theme.value ? {text: JSON.stringify(theme.value), code: ""} : invalid;
        }
        if (value.valid === false && keys.length === 3 && keys.every(key => ["formatVersion", "valid", "code"].indexOf(key) >= 0)
                && typeof value.code === "string" && codes.indexOf(value.code) >= 0)
            return {code: value.code};
        return invalid;
    }, ["valid", "theme", "code"].concat(Theme.rootFields, Theme.tokenFields));
    return parsed && typeof parsed.code === "string" ? parsed : invalid;
}
