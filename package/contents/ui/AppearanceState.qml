import QtQuick
import "../code/Appearance.js" as Appearance

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
        || (defaultsDraft ? savedJSON.length > 0 : JSON.stringify(draft) !== beginDraftJSON))
    readonly property bool canUndo: previousJSON !== null && previousScope === scopeKey && undoSignature === signature
    readonly property bool canApply: editing && !stale && error.length === 0 && draft !== null
    readonly property var effective: editing && preview ? preview : active
    readonly property bool overridden: editing && preview ? !defaultsDraft : Boolean(saved.value)

    function begin() {
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
        refreshDraft(next);
    }
    function selectTheme(theme) {
        if (!editing) return;
        defaultsDraft = false;
        refreshDraft(Appearance.legacy(configuration, theme));
    }
    function restoreDefaults() {
        if (!editing) return;
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
