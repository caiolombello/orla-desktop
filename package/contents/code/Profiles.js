.pragma library
.import "Appearance.js" as Appearance

var formatVersion = "0.2-experimental";
var widgetIds = ["clock", "pomodoro", "music", "systemBattery", "quota", "peripherals", "recording"];
var widgetKeys = ["showClock", "showPomodoro", "showMusic", "showSystemBattery", "showQuota", "showPeripherals", "showRecording"];
var legacyPresentationKeys = ["launchers", "appearance", "widgets", "calendarEvents", "currentDesktopOnly"];
// Keys added after the first format: optional when read, filled with these defaults.
// doNotDisturb is the profile's Focus mode: "on" or "off" switches Plasma's Do Not
// Disturb when the profile becomes active; "keep" leaves it as it is.
var optionalPresentation = {showAudioHud: false, doNotDisturb: "keep"};
var focusModes = ["keep", "on", "off"];
var presentationKeys = legacyPresentationKeys.concat(Object.keys(optionalPresentation));
var appearanceKeys = ["theme", "iconSize", "animations", "appearanceJSON"];
var controls = /[\u0000-\u001f\u007f-\u009f]/;

function copy(value) { return JSON.parse(JSON.stringify(value)); }
function freeze(value) {
    if (value && typeof value === "object") {
        Object.keys(value).forEach(key => freeze(value[key]));
        Object.freeze(value);
    }
    return value;
}
function flat(configuration) {
    return {launchers: Array.from(configuration.launchers), appearance: {
        theme: configuration.theme, iconSize: configuration.iconSize,
        animations: configuration.animations, appearanceJSON: configuration.appearanceJSON
    }, widgets: widgetIds.map((id, index) => ({id: id, visible: configuration[widgetKeys[index]]})),
        calendarEvents: configuration.calendarEvents, currentDesktopOnly: configuration.currentDesktopOnly,
        showAudioHud: Boolean(configuration.showAudioHud), doNotDisturb: "keep"};
}
// The keys of the first format, plus any of the optional ones (and `extra`).
function knownShape(value, extra) {
    const required = legacyPresentationKeys.concat(extra || []);
    const allowed = presentationKeys.concat(extra || []);
    return value !== null && typeof value === "object" && !Array.isArray(value)
        && required.every(key => key in value) && Object.keys(value).every(key => allowed.indexOf(key) !== -1);
}
function withDefaults(value) {
    const next = copy(value);
    Object.keys(optionalPresentation).forEach(key => { if (!(key in next)) next[key] = optionalPresentation[key]; });
    return next;
}
function capture(value) {
    const next = copy(value);
    const invalid = next.appearance.appearanceJSON.length && !Appearance.parse(next.appearance.appearanceJSON).value;
    if (invalid) next.appearance.appearanceJSON = "";
    const result = validatePresentation(next);
    result.message = invalid ? "Aparência salva inválida; o perfil usa as preferências anteriores." : "";
    return result;
}
function objectWithKnownKeys(value, keys) {
    return value !== null && typeof value === "object" && !Array.isArray(value)
        && Object.keys(value).every(key => keys.indexOf(key) !== -1);
}
function validName(value) {
    return typeof value === "string" && value.length > 0 && value.length <= 48
        && value.trim() === value && !controls.test(value);
}
// Experimental internal allocator; callers supply the live and referenced IDs.
function nextCustomId(timestamp, counter, reservedIds) {
    let id;
    do { id = "custom-" + timestamp.toString(36) + "-" + (++counter).toString(36); }
    while (reservedIds.indexOf(id) !== -1);
    return {id: id, counter: counter};
}
function validLauncher(value) {
    if (typeof value !== "string" || value.length > 2048 || controls.test(value)) return false;
    // Keep KDE's default-app binding instead of pinning today's resolved app.
    if (/^preferred:\/\/(browser|mailer|terminal|filemanager)$/.test(value)) return true;
    if (/^applications:[A-Za-z0-9_.-]+\.desktop$/.test(value)) return true;
    if (!/^file:\/\/\/(?!\/)[^?#\\]+\.desktop$/.test(value) || /%(?![0-9A-Fa-f]{2})/.test(value)) return false;
    try {
        const path = decodeURIComponent(value.slice(7));
        return !controls.test(path) && !path.startsWith("//")
            && !path.split("/").some(part => part === "." || part === "..");
    } catch (_) { return false; }
}
function fieldError(key, value) {
    if (key === "launchers") {
        if (!Array.isArray(value) || value.length > 32 || !value.every(validLauncher)
                || new Set(value).size !== value.length) return "Apps fixados inválidos. Use até 32 apps .desktop locais ou apps padrão do KDE.";
    } else if (key === "widgets") {
        if (!Array.isArray(value) || value.length !== widgetIds.length
                || !value.every(entry => Appearance.exactKeys(entry, ["id", "visible"])
                    && widgetIds.indexOf(entry.id) !== -1 && typeof entry.visible === "boolean")
                || new Set(value.map(entry => entry.id)).size !== widgetIds.length)
            return "Organização inválida. Use cada widget conhecido uma vez.";
    } else if (key === "calendarEvents" || key === "currentDesktopOnly" || key === "showAudioHud") {
        if (typeof value !== "boolean") return "Preferência inválida. Escolha ativado ou desativado.";
    } else if (key === "doNotDisturb") {
        if (focusModes.indexOf(value) === -1) return "Modo de foco inválido. Escolha manter, ligar ou desligar.";
    } else if (key === "theme") {
        if (Appearance.themes.indexOf(value) === -1) return "Tema inválido.";
    } else if (key === "iconSize") {
        if (!Number.isInteger(value) || value < 24 || value > 64) return "Tamanho de ícone inválido. Use de 24 a 64.";
    } else if (key === "animations") {
        if (typeof value !== "boolean") return "Preferência de movimento inválida.";
    } else if (key === "appearanceJSON") {
        if (typeof value !== "string" || (value.length > 0 && !Appearance.parse(value).value))
            return "Aparência salva inválida.";
    }
    return "";
}
function validatePatch(patch) {
    if (!objectWithKnownKeys(patch, presentationKeys)) return {error: "Alteração de perfil inválida."};
    for (const key of Object.keys(patch)) {
        if (key === "appearance") {
            if (!objectWithKnownKeys(patch.appearance, appearanceKeys)) return {error: "Alteração de aparência inválida."};
            for (const field of Object.keys(patch.appearance)) {
                const error = fieldError(field, patch.appearance[field]);
                if (error) return {error: error};
            }
        } else {
            const error = fieldError(key, patch[key]);
            if (error) return {error: error};
        }
    }
    return {value: copy(patch), error: ""};
}
function validatePresentation(value) {
    if (!knownShape(value) || !Appearance.exactKeys(value.appearance, appearanceKeys))
        return {error: "Configuração de perfil inválida."};
    return validatePatch(withDefaults(value));
}
function presentation(profile) {
    const value = {};
    presentationKeys.forEach(key => value[key] = profile[key]);
    return copy(value);
}
function merge(value, patch) {
    const result = copy(value);
    Object.keys(patch).forEach(key => {
        if (key === "appearance") Object.assign(result.appearance, copy(patch.appearance));
        else result[key] = copy(patch[key]);
    });
    return result;
}
function validate(value) {
    if (!Appearance.exactKeys(value, ["formatVersion", "activeProfileId", "profiles"])
            || (value.formatVersion !== formatVersion && value.formatVersion !== "0.1-experimental")
            || !Array.isArray(value.profiles) || value.profiles.length > 16
            || (value.profiles.length === 0 && value.formatVersion === "0.1-experimental"))
        return {error: "Perfis salvos inválidos ou incompatíveis."};
    const ids = new Set();
    const names = new Set();
    for (const profile of value.profiles) {
        if (!knownShape(profile, ["id", "name"]) || typeof profile.id !== "string" || profile.id.length > 48
                || !/^[a-z0-9][a-z0-9_-]*$/.test(profile.id) || profile.id === "legacy"
                || !validName(profile.name) || ids.has(profile.id) || names.has(profile.name))
            return {error: "Nome ou identificador de perfil inválido ou repetido."};
        const result = validatePresentation(presentation(withDefaults(profile)));
        if (result.error) return result;
        ids.add(profile.id);
        names.add(profile.name);
    }
    if (value.activeProfileId !== "legacy" && !ids.has(value.activeProfileId))
        return {error: "O perfil selecionado não existe."};
    const normalized = copy(value);
    normalized.profiles = value.profiles.map(withDefaults);
    return {value: normalized, error: ""};
}
function parse(raw) {
    if (raw === "") return {value: null, error: ""};
    if (typeof raw !== "string" || raw.length > 131072) return {error: "Perfis salvos inválidos ou muito grandes."};
    try { return validate(JSON.parse(raw)); }
    catch (_) { return {error: "Perfis salvos inválidos ou incompatíveis."}; }
}
