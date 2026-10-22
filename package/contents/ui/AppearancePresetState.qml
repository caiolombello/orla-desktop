import QtQuick
import "../code/Appearance.js" as Appearance
import "../code/AppearancePreset.js" as Preset
import "../code/Profiles.js" as Profiles

QtObject {
    id: state
    required property var profiles
    required property var appearance
    property string inputText: ""
    property string exportText: ""
    property string error: ""
    property string message: ""
    property bool pending: false
    readonly property string scope: profiles.activeProfileId
    readonly property int revision: profiles.revision
    readonly property bool editing: appearance.editing
    readonly property bool managed: profiles.writable && scope !== "legacy"
    readonly property bool busy: internal.busy
    readonly property bool dirty: inputText.length > 0 || pending || error.length > 0 || internal.preview !== null
    readonly property bool hasPreview: valid(internal.preview)
    readonly property var previewWidgets: hasPreview ? Profiles.copy(internal.preview.widgets) : null
    readonly property bool canApply: managed && hasPreview && !busy && !pending && !error.length && appearance.canApply
        && JSON.stringify(appearance.effective) === JSON.stringify(internal.preview.appearance)
        && JSON.stringify(appearance.draft) === JSON.stringify(internal.preview.appearance)
    readonly property bool canUndo: !busy && !dirty && internal.previous !== null
        && internal.undoScope === scope && internal.undoRevision === revision
    property QtObject internal: QtObject {
        property int generation: 0
        property bool busy: false
        property var preview: null
        property var previous: null
        property string undoScope: ""
        property int undoRevision: -1
    }
    function valid(intent) {
        return intent !== null && managed && editing && !appearance.stale
            && intent.scope === scope && intent.revision === revision;
    }
    function live(intent) { return valid(intent) && intent.generation === internal.generation; }
    function advance() {
        internal.generation++;
        // Text edits keep the most recent good preview, but revoke an in-flight one.
        if (internal.preview !== null) internal.preview = Object.assign({}, internal.preview, {generation:internal.generation});
    }
    function setInputText(text) {
        if (busy || !editing || inputText === text) return;
        advance();
        inputText = text;
        pending = text.length > 0;
        error = "";
        message = "";
    }
    function clearInput() {
        if (busy) return;
        advance();
        inputText = "";
        pending = false;
        error = "";
        message = "";
    }
    function clearPreview() {
        internal.generation++;
        internal.preview = null;
        inputText = "";
        pending = false;
        error = "";
        message = "";
    }
    function cancel() { clearPreview(); appearance.cancel(); }
    function exportSaved() {
        if (!profiles.writable || appearance.saved.error) {
            exportText = "";
            error = qsTr("A configuração salva está inválida. Corrija-a antes de exportar.");
            return false;
        }
        const result = Preset.capture(appearance.active, profiles.effective.widgets);
        if (!result.value) { error = qsTr("Não foi possível exportar a aparência salva."); return false; }
        exportText = Preset.serialize(result.value);
        return exportText.length > 0;
    }
    function previewImport() {
        if (busy || !editing || appearance.stale) return false;
        if (!managed) { error = qsTr("Crie ou escolha um perfil na aba Perfis para importar a organização."); return false; }
        if (appearance.themeText.length || appearance.themePending || appearance.themeError.length) {
            error = qsTr("Limpe o JSON de tema antes de importar a aparência portátil."); return false;
        }
        const parsed = Preset.parse(inputText);
        if (!parsed.value) { pending = inputText.length > 0; error = parsed.error; return false; }
        const intent = {scope:scope, revision:revision, generation:++internal.generation,
            appearance:Appearance.copy(parsed.value.appearance), widgets:Profiles.copy(parsed.value.widgets)};
        const oldDraft = appearance.draft;
        appearance.defaultsDraft = false;
        if (!live(intent) || appearance.draft !== oldDraft) return false;
        if (!appearance.refreshDraft(Appearance.copy(intent.appearance), () => live(intent))) return false;
        if (!live(intent)) return false;
        // Publish the intent and its widgets together, never a mixed pair.
        internal.preview = intent;
        if (!live(intent)) return false;
        pending = false;
        if (!live(intent)) return false;
        error = "";
        if (!live(intent)) return false;
        message = qsTr("Prévia de aparência e widgets. Aplicar salva neste perfil.");
        return live(intent);
    }
    function expectedDocument(patch) {
        const result = Profiles.parse(profiles.savedJSON);
        if (!result.value) return "";
        const document = Profiles.copy(result.value);
        const index = document.profiles.findIndex(profile => profile.id === scope);
        if (index < 0) return "";
        document.profiles[index] = Object.assign(Profiles.merge(Profiles.presentation(document.profiles[index]), patch),
            {id:document.profiles[index].id, name:document.profiles[index].name});
        return JSON.stringify(document);
    }
    function commit(patch, intent) {
        const expected = expectedDocument(patch);
        if (!expected.length || !live(intent)) return false;
        if (!profiles.commitPresentation(patch, intent.scope, intent.revision, () => live(intent))) return false;
        // A synchronous setter may trigger cancellation or a newer profile edit.
        return intent.generation === internal.generation && scope === intent.scope
            && (revision === intent.revision || revision === intent.revision + 1)
            && profiles.savedJSON === expected;
    }
    function apply() {
        if (!canApply) return false;
        const intent = internal.preview;
        const previous = {appearance:{appearanceJSON:profiles.effective.appearance.appearanceJSON},
            widgets:Profiles.copy(profiles.effective.widgets)};
        const patch = {appearance:{appearanceJSON:JSON.stringify(intent.appearance)}, widgets:Profiles.copy(intent.widgets)};
        internal.busy = true;
        try {
            if (!commit(patch, intent)) { error = qsTr("A configuração mudou. A importação não foi confirmada."); return false; }
            const completed = {scope:intent.scope, revision:revision, generation:internal.generation + 1, savedJSON:profiles.savedJSON};
            clearPreview();
            if (!confirmed(completed)) {
                internal.previous = null;
                error = qsTr("A configuração mudou. A importação não foi confirmada.");
                return false;
            }
            appearance.previousJSON = null;
            internal.previous = previous;
            internal.undoScope = completed.scope;
            internal.undoRevision = completed.revision;
            appearance.begin();
            if (!confirmed(completed)) {
                internal.previous = null;
                error = qsTr("A configuração mudou. A importação não foi confirmada.");
                return false;
            }
            message = qsTr("Aparência e widgets aplicados.");
            return confirmed(completed);
        } finally { internal.busy = false; }
    }
    function undo() {
        if (!canUndo || !managed || !editing) return false;
        const intent = {scope:scope, revision:revision, generation:internal.generation};
        internal.busy = true;
        try {
            if (!commit(Profiles.copy(internal.previous), intent)) { error = qsTr("A configuração mudou. Não foi possível desfazer."); return false; }
            const completed = {scope:scope, revision:revision, generation:internal.generation, savedJSON:profiles.savedJSON};
            internal.previous = null;
            appearance.previousJSON = null;
            appearance.begin();
            if (!confirmed(completed)) {
                error = qsTr("A configuração mudou. Não foi possível confirmar a reversão.");
                return false;
            }
            message = qsTr("Aparência e widgets anteriores restaurados.");
            return confirmed(completed);
        } finally { internal.busy = false; }
    }
    function confirmed(completed) {
        return editing && scope === completed.scope && revision === completed.revision
            && internal.generation === completed.generation && profiles.savedJSON === completed.savedJSON;
    }
    function domainChanged() {
        if (busy) return;
        internal.previous = null;
        exportText = "";
        if (!dirty) return;
        const wasEditing = editing;
        clearPreview();
        appearance.cancel();
        if (wasEditing) appearance.begin();
        error = qsTr("O perfil mudou. Cole novamente para iniciar uma prévia.");
    }
    onScopeChanged: domainChanged()
    onRevisionChanged: domainChanged()
    onEditingChanged: if (!editing) clearPreview()
}
