.pragma library

var formatVersion = "0.1-experimental";
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
            || ["glass", "midnight", "paper"].indexOf(value.baseTheme) === -1)
        return {error: "Aparência inválida. Use um tema e formato conhecidos."};
    const tokens = value.tokens;
    if (!exactKeys(tokens, colorKeys.concat(Object.keys(ranges), ["reducedMotion"])))
        return {error: "Aparência inválida. Verifique os campos de aparência."};
    const result = {formatVersion: formatVersion, baseTheme: value.baseTheme, tokens: {}};
    for (const key of colorKeys) {
        if (typeof tokens[key] !== "string" || !/^#[0-9a-fA-F]{6}$/.test(tokens[key]))
            return {error: key + ": use uma cor no formato #RRGGBB."};
        result.tokens[key] = tokens[key].toLowerCase();
    }
    for (const key of Object.keys(ranges)) {
        const number = tokens[key];
        const bounds = ranges[key];
        if (typeof number !== "number" || !isFinite(number) || number < bounds[0] || number > bounds[1])
            return {error: key + ": use um número entre " + bounds[0] + " e " + bounds[1] + "."};
        result.tokens[key] = number;
    }
    if (typeof tokens.reducedMotion !== "boolean")
        return {error: "reducedMotion: escolha ativado ou desativado."};
    result.tokens.reducedMotion = tokens.reducedMotion;
    return {value: result, error: ""};
}
function parse(raw) {
    if (typeof raw !== "string" || raw.length > 4096) return {error: "Aparência salva inválida."};
    try { return validate(JSON.parse(raw)); }
    catch (_) { return {error: "Aparência salva inválida."}; }
}
function legacy(configuration, theme) {
    theme = theme || configuration.theme;
    if (["glass", "midnight", "paper"].indexOf(theme) === -1) theme = "glass";
    const light = theme === "paper";
    return {formatVersion: formatVersion, baseTheme: theme, tokens: {
        foreground: light ? "#252b35" : "#edf1f9",
        muted: light ? "#657180" : "#9da9bf",
        accent: light ? "#167361" : "#69d7c2",
        surface: light ? "#f4f0e8" : theme === "midnight" ? "#111923" : "#283542",
        border: light ? "#cec9bf" : "#3c4b65",
        radius: 21, spacing: 5, opacity: theme === "glass" ? 219 / 255 : 1,
        iconSize: Math.max(24, Math.min(64, configuration.iconSize)), reducedMotion: !configuration.animations
    }};
}
