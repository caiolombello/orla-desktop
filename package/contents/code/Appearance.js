.pragma library

var formatVersion = "0.1-experimental";
// "auto" is a base theme whose colors and opacity follow the system scheme.
var themes = ["glass", "midnight", "paper", "frost", "auto"];
var colorKeys = ["foreground", "muted", "accent", "surface", "border"];
var ranges = {radius: [0, 32], spacing: [0, 16], opacity: [0.4, 1], iconSize: [24, 64]};

function copy(value) { return JSON.parse(JSON.stringify(value)); }
function exactKeys(value, keys) {
    return value !== null && typeof value === "object" && !Array.isArray(value)
        && Object.keys(value).length === keys.length
        && Object.keys(value).every(key => keys.indexOf(key) !== -1);
}
function validate(value) {
    if (!exactKeys(value, ["formatVersion", "baseTheme", "tokens"]) || value.formatVersion !== formatVersion
            || themes.indexOf(value.baseTheme) === -1)
        return {error: "Aparência inválida. Use um tema e formato conhecidos."};
    const result = validateTokens(value.tokens);
    if (!result.value) return result;
    return {value: {formatVersion: formatVersion, baseTheme: value.baseTheme, tokens: result.value}, error: ""};
}
function tokenFailure(key, code, message) {
    return {error: message, errors: [{field: key ? "$/tokens/" + key : "$/tokens", code: code, message: message}]};
}
function validateTokens(tokens) {
    const keys = colorKeys.concat(Object.keys(ranges), ["reducedMotion"]);
    if (tokens === null || typeof tokens !== "object" || Array.isArray(tokens))
        return tokenFailure("", "type", "Aparência inválida. Verifique os campos de aparência.");
    if (Object.keys(tokens).some(key => keys.indexOf(key) === -1))
        return tokenFailure("", "unknown_key", "Aparência inválida. Verifique os campos de aparência.");
    for (const key of keys) {
        if (!Object.prototype.hasOwnProperty.call(tokens, key))
            return tokenFailure(key, "required", "Aparência inválida. Verifique os campos de aparência.");
    }
    const result = {};
    for (const key of colorKeys) {
        const message = key + ": use uma cor no formato #RRGGBB.";
        if (typeof tokens[key] !== "string") return tokenFailure(key, "type", message);
        if (tokens[key].length < 1 || tokens[key].length > 7) return tokenFailure(key, "length", message);
        if (!/^#[0-9a-fA-F]{6}(?![\s\S])/.test(tokens[key])) return tokenFailure(key, "format", message);
        result[key] = tokens[key].toLowerCase();
    }
    for (const key of Object.keys(ranges)) {
        const number = tokens[key];
        const bounds = ranges[key];
        const message = key + ": use um número entre " + bounds[0] + " e " + bounds[1] + ".";
        if (typeof number !== "number") return tokenFailure(key, "type", message);
        if (!isFinite(number)) return tokenFailure(key, "nonfinite", message);
        if (number < bounds[0] || number > bounds[1]) return tokenFailure(key, "range", message);
        result[key] = number;
    }
    if (typeof tokens.reducedMotion !== "boolean")
        return tokenFailure("reducedMotion", "type", "reducedMotion: escolha ativado ou desativado.");
    result.reducedMotion = tokens.reducedMotion;
    return {value: result, error: "", errors: []};
}

function parse(raw) {
    if (typeof raw !== "string" || raw.length > 4096) return {error: "Aparência salva inválida."};
    try { return validate(JSON.parse(raw)); }
    catch (_) { return {error: "Aparência salva inválida."}; }
}
function concrete(theme, systemLight) {
    return theme === "auto" ? (systemLight ? "frost" : "glass") : theme;
}
function legacy(configuration, theme, systemLight) {
    theme = theme || configuration.theme;
    if (themes.indexOf(theme) === -1) theme = "glass";
    const base = concrete(theme, systemLight);
    const light = base === "paper" || base === "frost";
    return {formatVersion: formatVersion, baseTheme: theme, tokens: {
        foreground: base === "frost" ? "#1d2430" : light ? "#252b35" : "#edf1f9",
        muted: base === "frost" ? "#5b6675" : light ? "#606c79" : "#9da9bf",
        accent: light ? "#167361" : "#69d7c2",
        surface: base === "frost" ? "#eef1f6" : light ? "#f4f0e8" : base === "midnight" ? "#111923" : "#283542",
        border: base === "frost" ? "#d3d9e2" : light ? "#cec9bf" : "#3c4b65",
        radius: 21, spacing: 5, opacity: base === "glass" ? 219 / 255 : base === "frost" ? 199 / 255 : 1,
        iconSize: Math.max(24, Math.min(64, configuration.iconSize)), reducedMotion: !configuration.animations
    }};
}
// An automatic appearance keeps its shape and motion tokens and takes the
// colors and opacity of the theme the system scheme selects.
var followedKeys = colorKeys.concat(["opacity"]);
function resolve(value, systemLight) {
    if (!value || !value.tokens || value.baseTheme !== "auto") return value;
    const theme = legacy({iconSize: value.tokens.iconSize, animations: !value.tokens.reducedMotion},
        concrete("auto", systemLight)).tokens;
    const tokens = copy(value.tokens);
    for (const key of followedKeys) tokens[key] = theme[key];
    return {formatVersion: value.formatVersion, baseTheme: "auto", tokens: tokens};
}
