.pragma library
.import "Appearance.js" as Appearance
.import "Profiles.js" as Profiles
.import "Theme.js" as Theme

var formatVersion = "0.1-experimental";
var kind = "orla-appearance-preset";
var rootFields = ["formatVersion", "kind", "appearance", "widgets"];
var appearanceFields = ["formatVersion", "baseTheme", "tokens"];
var widgetFields = ["id", "visible"];

function validate(value) {
    const envelopeError = Theme.objectError(value, "$", rootFields);
    if (envelopeError) return envelopeError;
    if (value.formatVersion !== formatVersion)
        return Theme.failure("$/formatVersion", "format_version", "Use o formato 0.1-experimental.");
    if (value.kind !== kind)
        return Theme.failure("$/kind", "kind", "Use um preset de aparência Orla.");
    const appearanceError = Theme.objectError(value.appearance, "$/appearance", appearanceFields);
    if (appearanceError) return appearanceError;
    const appearance = Appearance.validate(value.appearance);
    if (!appearance.value) {
        const errors = appearance.errors;
        if (!errors || !errors.length)
            return Theme.failure("$/appearance", "appearance", "Use uma aparência válida.");
        return Theme.failure(errors[0].field.replace("$/tokens", "$/appearance/tokens"),
                             errors[0].code, errors[0].message);
    }
    if (!Array.isArray(value.widgets) || value.widgets.length !== Profiles.widgetIds.length)
        return Theme.failure("$/widgets", "widgets", "Use cada widget conhecido uma vez.");
    const seen = new Set(), widgets = [];
    for (let index = 0; index < value.widgets.length; index++) {
        const entry = value.widgets[index], field = "$/widgets/" + index;
        const error = Theme.objectError(entry, field, widgetFields);
        if (error) return error;
        if (Profiles.widgetIds.indexOf(entry.id) === -1 || seen.has(entry.id))
            return Theme.failure(field + "/id", "widget_id", "Use cada widget conhecido uma vez.");
        if (typeof entry.visible !== "boolean")
            return Theme.failure(field + "/visible", "type", "Escolha ativado ou desativado.");
        seen.add(entry.id);
        widgets.push({id: entry.id, visible: entry.visible});
    }
    return {value: {formatVersion: formatVersion, kind: kind,
                    appearance: appearance.value, widgets: widgets}, error: "", errors: []};
}
function capture(savedAppearance, widgets) {
    // Only the saved appearance and widget presentation are exportable.
    return validate({formatVersion: formatVersion, kind: kind, appearance: savedAppearance, widgets: widgets});
}
function parse(text) {
    return Theme.parseDocument(text, validate, rootFields.concat(appearanceFields, Theme.tokenFields, widgetFields));
}
function serialize(value) {
    const result = validate(value);
    return result.value ? JSON.stringify(result.value) : "";
}
