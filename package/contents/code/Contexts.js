.pragma library

var formatVersion = "0.1-experimental";
var controls = /[\u0000-\u001f\u007f-\u009f]/;

function copy(value) { return JSON.parse(JSON.stringify(value)); }
function freeze(value) {
    if (value && typeof value === "object") {
        Object.keys(value).forEach(key => freeze(value[key]));
        Object.freeze(value);
    }
    return value;
}
function objectWithExactKeys(value, keys) {
    return value !== null && typeof value === "object" && !Array.isArray(value)
        && Object.keys(value).length === keys.length
        && Object.keys(value).every(key => keys.indexOf(key) !== -1);
}
function emptyDocument() {
    return {formatVersion: formatVersion, activityBindings: [], desktopBindings: []};
}
function unavailable(status) { return {status: status, id: "", name: ""}; }
function validText(value, maximum, allowEmpty) {
    return typeof value === "string" && value.length <= maximum
        && (allowEmpty || value.length > 0) && !controls.test(value);
}
function captureDataObject(value, keys) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
    try {
        const actual = Object.keys(value);
        if (actual.length !== keys.length || !actual.every(key => keys.indexOf(key) !== -1)) return null;
        const captured = {};
        for (let index = 0; index < keys.length; index++) {
            const key = keys[index];
            const descriptor = Object.getOwnPropertyDescriptor(value, key);
            if (!descriptor || descriptor.get !== undefined || descriptor.set !== undefined) return null;
            captured[key] = value[key];
        }
        return captured;
    } catch (_) { return null; }
}
function captureArray(value, maximum) {
    if (!Array.isArray(value)) return null;
    try {
        const length = value.length;
        if (!Number.isInteger(length) || length < 0 || length > maximum) return null;
        const captured = [];
        for (let index = 0; index < length; index++) {
            const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
            if (!descriptor || descriptor.get !== undefined || descriptor.set !== undefined) return null;
            captured.push(value[index]);
        }
        return captured;
    } catch (_) { return null; }
}
function normalizeDomain(value, singular) {
    const captured = captureDataObject(value, ["status", "currentId", "ids", "names"]);
    if (!captured || ["loading", "ready", "unavailable"].indexOf(captured.status) === -1)
        return {current: unavailable("unavailable"), items: []};
    if (captured.status !== "ready") return {current: unavailable(captured.status), items: []};
    const idsValues = captureArray(captured.ids, 256);
    const nameValues = captureArray(captured.names, 256);
    if (!validText(captured.currentId, 256, false) || !idsValues || !nameValues
            || idsValues.length !== nameValues.length || idsValues.length === 0)
        return {current: unavailable("unavailable"), items: []};
    const ids = new Set();
    const items = [];
    for (let index = 0; index < idsValues.length; index++) {
        const id = idsValues[index], name = nameValues[index];
        if (!validText(id, 256, false) || !validText(name, 128, true) || ids.has(id))
            return {current: unavailable("unavailable"), items: []};
        ids.add(id);
        items.push({id: id, name: name || (singular + " " + (index + 1)), current: id === captured.currentId});
    }
    const selected = items.find(item => item.id === captured.currentId);
    if (!selected) return {current: unavailable("unavailable"), items: []};
    return {current: {status: "ready", id: selected.id, name: selected.name}, items: items};
}
function normalizeSnapshot(value) {
    const captured = captureDataObject(value, ["outputName", "activity", "desktop"]);
    if (!captured) return {outputName: "", activity: unavailable("unavailable"),
        desktop: unavailable("unavailable"), activities: [], desktops: []};
    const activity = normalizeDomain(captured.activity, "Activity");
    const desktop = normalizeDomain(captured.desktop, "Área");
    return {outputName: validText(captured.outputName, 128, true) ? captured.outputName : "",
        activity: activity.current, desktop: desktop.current,
        activities: activity.items, desktops: desktop.items};
}
function validProfileId(value) {
    return typeof value === "string" && value !== "legacy" && value.length <= 48
        && /^[a-z0-9][a-z0-9_-]*$/.test(value);
}
function captureContext(value) {
    if (value === null || typeof value !== "object" || Array.isArray(value))
        return {error: "Associação de contexto inválida."};
    let keys, captured;
    try {
        keys = Object.keys(value);
        if (keys.length !== 3 || !keys.every(key => ["status", "id", "name"].indexOf(key) !== -1))
            return {error: "Associação de contexto inválida."};
        captured = {status: value.status, id: value.id, name: value.name};
    } catch (_) { return {error: "Associação de contexto inválida."}; }
    if (captured.status !== "ready" || !validText(captured.id, 256, false)
            || !validText(captured.name, 128, true))
        return {error: "Associação de contexto inválida."};
    return {value: captured, error: ""};
}
function validateBinding(value) {
    return objectWithExactKeys(value, ["contextId", "lastKnownName", "profileId"])
        && validText(value.contextId, 256, false)
        && validText(value.lastKnownName, 128, true)
        && validProfileId(value.profileId);
}
function validateBindings(values) {
    if (!Array.isArray(values) || values.length > 64 || !values.every(validateBinding)) return false;
    return new Set(values.map(binding => binding.contextId)).size === values.length;
}
function validate(value) {
    if (!objectWithExactKeys(value, ["formatVersion", "activityBindings", "desktopBindings"])
            || value.formatVersion !== formatVersion
            || !validateBindings(value.activityBindings) || !validateBindings(value.desktopBindings))
        return {error: "Associações de contexto salvas inválidas ou incompatíveis."};
    return {value: copy(value), error: ""};
}
function parse(raw) {
    if (raw === "") return {value: emptyDocument(), error: "", empty: true};
    if (typeof raw !== "string" || raw.length > 131072)
        return {error: "Associações de contexto salvas inválidas ou muito grandes."};
    try { return validate(JSON.parse(raw)); }
    catch (_) { return {error: "Associações de contexto salvas inválidas ou incompatíveis."}; }
}
function bindingKey(kind) {
    return kind === "activity" ? "activityBindings" : kind === "desktop" ? "desktopBindings" : "";
}
function bind(document, kind, context, profileId) {
    const key = bindingKey(kind);
    const captured = captureContext(context);
    if (!key || captured.error || !validProfileId(profileId))
        return {error: "Associação de contexto inválida."};
    const result = validate(document);
    if (result.error) return result;
    const next = result.value;
    const binding = {contextId: captured.value.id, lastKnownName: captured.value.name, profileId: profileId};
    const index = next[key].findIndex(item => item.contextId === captured.value.id);
    if (index < 0) {
        if (next[key].length >= 64) return {error: "Limite de 64 associações de contexto atingido."};
        next[key].push(binding);
    } else {
        const previous = next[key][index];
        if (previous.contextId === binding.contextId && previous.lastKnownName === binding.lastKnownName
                && previous.profileId === binding.profileId)
            return {value: next, error: "", changed: false};
        next[key][index] = binding;
    }
    return {value: next, error: "", changed: true};
}
function unbind(document, kind, contextId) {
    const key = bindingKey(kind);
    if (!key || !validText(contextId, 256, false)) return {error: "Associação de contexto inválida."};
    const result = validate(document);
    if (result.error) return result;
    const index = result.value[key].findIndex(item => item.contextId === contextId);
    if (index < 0) {
        result.changed = false;
        return result;
    }
    result.value[key].splice(index, 1);
    result.changed = true;
    return result;
}
