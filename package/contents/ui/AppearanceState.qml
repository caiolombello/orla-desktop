import QtQuick
import "../code/Appearance.js" as Appearance
import "../code/Theme.js" as Theme

QtObject {
    id: state
    required property var configuration
    property var writeAppearance: null
    property string scopeKey: "legacy"
    readonly property string savedJSON: typeof configuration.appearanceJSON === "string" ? configuration.appearanceJSON : ""
    readonly property var saved: savedJSON.length ? Appearance.parse(savedJSON) : ({error: ""})
    readonly property var legacy: Appearance.legacy(configuration)
    readonly property var active: saved.value || legacy
    property bool editing: false
    property var draft: null
    property var preview: null
    property bool defaultsDraft: false
    property string themeText: ""
    property bool themePending: false
    property string themeError: ""
    property var themeErrors: []
    property var themeMetadata: null
    property bool themeModified: false
    property string error: ""
    property string message: ""
    property var previousJSON: null
    property string previousScope: ""
    property string undoSignature: ""
    property string beginScope: ""
    property string beginSignature: ""
    property string beginDraftJSON: ""
    readonly property string signature: JSON.stringify({savedJSON: savedJSON, theme: configuration.theme,
        iconSize: configuration.iconSize, animations: configuration.animations})
    readonly property bool stale: editing && (beginScope !== scopeKey || beginSignature !== signature)
    readonly property bool dirty: editing && draft !== null && (error.length > 0
        || themeText.length > 0 || themeError.length > 0
        || (defaultsDraft ? savedJSON.length > 0 : JSON.stringify(draft) !== beginDraftJSON))
    readonly property bool canUndo: previousJSON !== null && previousScope === scopeKey && undoSignature === signature
    readonly property bool canApply: editing && !stale && error.length === 0 && !themePending && themeError.length === 0 && draft !== null
    readonly property var effective: editing && preview ? preview : active
    readonly property bool overridden: editing && preview ? !defaultsDraft : Boolean(saved.value)

    function clearThemeInput() {
        themeText = "";
        themePending = false;
        themeError = "";
        themeErrors = [];
        themeMetadata = null;
        themeModified = false;
    }
    function setThemeText(text) {
        if (!editing) return;
        if (themeText === text) return;
        themeText = text;
        themePending = text.length > 0;
        themeError = "";
        themeErrors = [];
    }
    function previewTheme() {
        if (!editing || stale || !draft) return false;
        const parsed = Theme.parse(themeText);
        if (!parsed.value) {
            themePending = themeText.length > 0;
            themeError = parsed.error;
            themeErrors = parsed.errors;
            return false;
        }
        const next = Appearance.validate({formatVersion: Appearance.formatVersion,
            baseTheme: draft.baseTheme, tokens: parsed.value.tokens});
        if (!next.value) return false;
        defaultsDraft = false;
        refreshDraft(next.value);
        themeMetadata = {id: parsed.value.id, name: parsed.value.name, author: parsed.value.author,
            license: parsed.value.license, version: parsed.value.version};
        themeModified = false;
        themePending = false;
        themeError = "";
        themeErrors = [];
        return true;
    }
    function begin() {
        clearThemeInput();
        draft = Appearance.copy(active);
        beginScope = scopeKey;
        beginSignature = signature;
        beginDraftJSON = JSON.stringify(draft);
        preview = null;
        defaultsDraft = false;
        editing = true;
        error = "";
        message = "";
    }
    function refreshDraft(value) {
        draft = value;
        const result = Appearance.validate(value);
        error = result.error;
        message = "";
        if (result.value) preview = result.value;
    }
    function setToken(key, value) {
        if (!editing || !draft) return;
        const next = Appearance.copy(draft);
        next.tokens[key] = value;
        defaultsDraft = false;
        if (themeMetadata) themeModified = true;
        refreshDraft(next);
    }
    function selectTheme(theme) {
        if (!editing) return;
        clearThemeInput();
        defaultsDraft = false;
        refreshDraft(Appearance.legacy(configuration, theme));
    }
    function restoreDefaults() {
        if (!editing) return;
        clearThemeInput();
        refreshDraft(Appearance.copy(legacy));
        defaultsDraft = true;
    }
    function apply() {
        if (stale) { error = qsTr("A aparência salva mudou. Cancele e abra novamente antes de aplicar."); return false; }
        if (!canApply) return false;
        const result = Appearance.validate(draft);
        if (!result.value) { error = result.error; return false; }
        const next = defaultsDraft ? "" : JSON.stringify(result.value);
        if (savedJSON !== next) {
            const old = savedJSON;
            if (!write(next, beginScope, beginSignature)) return false;
            previousJSON = old;
            previousScope = scopeKey;
            undoSignature = signature;
        }
        begin();
        message = qsTr("Aparência aplicada.");
        return true;
    }
    function cancel() {
        clearThemeInput();
        editing = false;
        preview = null;
        draft = null;
        defaultsDraft = false;
        error = "";
        message = "";
    }
    function undo() {
        if (!canUndo) return false;
        if (!write(previousJSON, scopeKey, undoSignature)) return false;
        previousJSON = null;
        begin();
        message = qsTr("Aparência anterior restaurada.");
        return true;
    }
    function write(next, expectedScope, expectedSignature) {
        if (expectedScope !== scopeKey || expectedSignature !== signature) return false;
        if (writeAppearance !== null) {
            if (typeof writeAppearance !== "function" || writeAppearance(next, expectedScope, expectedSignature) !== true) {
                error = qsTr("Não foi possível salvar a aparência neste perfil.");
                return false;
            }
        } else configuration.appearanceJSON = next;
        return true;
    }
    onScopeKeyChanged: {
        previousJSON = null;
        cancel();
    }
}
