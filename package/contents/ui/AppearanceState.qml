import QtQuick
import "../code/Appearance.js" as Appearance

QtObject {
    id: state
    required property var configuration
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
    readonly property bool canUndo: previousJSON !== null
    readonly property bool canApply: editing && error.length === 0 && draft !== null
    readonly property var effective: editing && preview ? preview : active
    readonly property bool overridden: editing && preview ? !defaultsDraft : Boolean(saved.value)

    function begin() {
        draft = Appearance.copy(active);
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
        if (!canApply) return false;
        const result = Appearance.validate(draft);
        if (!result.value) { error = result.error; return false; }
        const next = defaultsDraft ? "" : JSON.stringify(result.value);
        if (savedJSON !== next) {
            previousJSON = savedJSON;
            configuration.appearanceJSON = next;
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
        if (!canUndo) return;
        configuration.appearanceJSON = previousJSON;
        previousJSON = null;
        begin();
        message = qsTr("Aparência anterior restaurada.");
    }
}
