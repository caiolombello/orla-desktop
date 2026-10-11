.pragma library
.import "Appearance.js" as Appearance

var formatVersion = "0.1-experimental";
var widgetIds = ["clock", "pomodoro", "music", "systemBattery", "quota", "peripherals", "recording"];
var widgetKeys = ["showClock", "showPomodoro", "showMusic", "showSystemBattery", "showQuota", "showPeripherals", "showRecording"];
var presentationKeys = ["launchers", "appearance", "widgets", "calendarEvents", "currentDesktopOnly"];
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
        calendarEvents: configuration.calendarEvents, currentDesktopOnly: configuration.currentDesktopOnly};
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
function validLauncher(value) {
    if (typeof value !== "string" || value.length > 2048 || controls.test(value)) return false;
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
                || new Set(value).size !== value.length) return "Apps fixados inválidos. Use até 32 arquivos .desktop locais.";
    } else if (key === "widgets") {
        if (!Array.isArray(value) || value.length !== widgetIds.length
                || !value.every(entry => Appearance.exactKeys(entry, ["id", "visible"])
                    && widgetIds.indexOf(entry.id) !== -1 && typeof entry.visible === "boolean")
                || new Set(value.map(entry => entry.id)).size !== widgetIds.length)
            return "Organização inválida. Use cada widget conhecido uma vez.";
    } else if (key === "calendarEvents" || key === "currentDesktopOnly") {
        if (typeof value !== "boolean") return "Preferência inválida. Escolha ativado ou desativado.";
    } else if (key === "theme") {
        if (["glass", "midnight", "paper"].indexOf(value) === -1) return "Tema inválido.";
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
    if (!Appearance.exactKeys(value, presentationKeys) || !Appearance.exactKeys(value.appearance, appearanceKeys))
        return {error: "Configuração de perfil inválida."};
    return validatePatch(value);
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
            || value.formatVersion !== formatVersion || !Array.isArray(value.profiles)
            || value.profiles.length < 1 || value.profiles.length > 16)
        return {error: "Perfis salvos inválidos ou incompatíveis."};
    const ids = new Set();
    const names = new Set();
    for (const profile of value.profiles) {
        if (!Appearance.exactKeys(profile, presentationKeys.concat(["id", "name"]))
                || typeof profile.id !== "string" || profile.id.length > 48
                || !/^[a-z0-9][a-z0-9_-]*$/.test(profile.id) || profile.id === "legacy"
                || !validName(profile.name) || ids.has(profile.id) || names.has(profile.name))
            return {error: "Nome ou identificador de perfil inválido ou repetido."};
        const result = validatePresentation(presentation(profile));
        if (result.error) return result;
        ids.add(profile.id);
        names.add(profile.name);
    }
    if (value.activeProfileId !== "legacy" && !ids.has(value.activeProfileId))
        return {error: "O perfil selecionado não existe."};
    return {value: copy(value), error: ""};
}
function parse(raw) {
    if (raw === "") return {value: null, error: ""};
    if (typeof raw !== "string" || raw.length > 131072) return {error: "Perfis salvos inválidos ou muito grandes."};
    try { return validate(JSON.parse(raw)); }
    catch (_) { return {error: "Perfis salvos inválidos ou incompatíveis."}; }
}
