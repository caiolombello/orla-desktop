import QtQuick
import "../code/Appearance.js" as Appearance
import "../code/Theme.js" as Theme
import "../code/ThemeFile.js" as ThemeFile

QtObject {
    id: state
    required property var configuration
    property var writeAppearance: null
    property var themeFileTransport: null
    property bool themeFileBlocked: false
    property int themeFileTimeoutMs: 5000
    readonly property alias themeFileSelecting: fileRequestState.selecting
    readonly property alias themeFileLoading: fileRequestState.loading
    readonly property alias busy: fileRequestState.busy
    property QtObject fileRequest: QtObject {
        id: fileRequestState
        property bool selecting: false
        property bool loading: false
        property bool busy: false
        property int generation: 0
        property var current: null
        property string phase: ""
    }
    property Timer themeFileTimer: Timer {
        repeat: false
        onTriggered: state.expireThemeFile()
    }
    function publishFilePhase(phase, generation) {
        if (fileRequest.generation !== generation) return false;
        fileRequest.phase = phase;
        if (phase !== "selecting") fileRequest.selecting = false;
        if (fileRequest.generation !== generation) return false;
        if (phase !== "loading") fileRequest.loading = false;
        if (fileRequest.generation !== generation) return false;
        fileRequest.busy = phase.length > 0;
        if (fileRequest.generation !== generation) return false;
        if (phase === "selecting") fileRequest.selecting = true;
        if (fileRequest.generation !== generation) return false;
        if (phase === "loading") fileRequest.loading = true;
        return fileRequest.generation === generation;
    }
    function invalidateThemeFile() {
        if (!fileRequest) return true;
        const generation = ++fileRequest.generation;
        fileRequest.current = null;
        if (themeFileTimer) themeFileTimer.stop();
        return publishFilePhase("", generation);
    }
    function fileSelectionLive(intent) {
        return Boolean(intent && fileRequest.current === intent && intent.generation === fileRequest.generation
            && editing && !stale && !themeFileBlocked && Qt.isQtObject(intent.owner)
            && configuration === intent.configuration && themeFileTransport === intent.transport
            && scopeKey === intent.scope && signature === intent.signature
            && draft === intent.draft && JSON.stringify(draft) === intent.draftJSON && themeText === intent.text);
    }
    function beginThemeFileSelection(owner) {
        if (!editing || stale || !draft || themeFileBlocked || !Qt.isQtObject(owner)) return null;
        const intent = {token: Object.freeze({}), owner: owner, generation: ++fileRequest.generation,
            configuration: configuration, scope: scopeKey, signature: signature,
            draft: draft, draftJSON: JSON.stringify(draft), text: themeText, transport: themeFileTransport};
        themeFileTimer.stop();
        fileRequest.current = intent;
        if (!publishFilePhase("selecting", intent.generation)) return null;
        return fileSelectionLive(intent) ? intent.token : null;
    }
    function cancelThemeFileSelection(token) {
        const intent = fileRequest.current;
        if (!intent || token !== intent.token) return false;
        const generation = ++fileRequest.generation;
        fileRequest.current = null;
        themeFileTimer.stop();
        publishFilePhase("", generation);
        return true;
    }
    function fileMessage(code) {
        if (code === "timeout") return qsTr("A leitura do tema demorou demais. Tente novamente.");
        if (code === "busy") return qsTr("Outro tema está sendo lido. Tente novamente.");
        if (code === "unavailable") return qsTr("A leitura de arquivos de tema não está disponível.");
        if (code === "file") return qsTr("Não foi possível ler este arquivo de tema.");
        if (code === "cleanup_failed") return qsTr("Não foi possível concluir a leitura do tema. Tente novamente.");
        if (code === "invalid_response") return qsTr("A resposta da leitura do tema é inválida.");
        return qsTr("O arquivo não contém um tema válido. Confira o formato 0.1-experimental.");
    }
    function expireThemeFile() {
        const intent = fileRequest.current;
        if (!intent || intent.generation !== fileRequest.generation || fileRequest.phase !== "loading") return;
        // A vanished owner cannot receive an error, but its read still has a deadline.
        if (!fileSelectionLive(intent)) { cancelThemeFileSelection(intent.token); return; }
        failThemeFile(intent, "timeout");
    }
    function failThemeFile(intent, code) {
        if (!fileSelectionLive(intent)) return false;
        themeFileTimer.stop();
        themeError = fileMessage(code);
        if (!fileSelectionLive(intent)) return false;
        themeErrors = [{field: "$", code: code, message: themeError}];
        if (!fileSelectionLive(intent)) return false;
        fileRequest.current = null;
        publishFilePhase("", intent.generation);
        return false;
    }
    function receiveThemeFile(intent, raw) {
        if (!fileSelectionLive(intent) || fileRequest.phase !== "loading") return false;
        const result = ThemeFile.decode(raw);
        if (!fileSelectionLive(intent)) return false;
        if (!result.text) return failThemeFile(intent, result.code);
        themeFileTimer.stop();
        intent.text = result.text;
        themeText = result.text;
        if (!fileSelectionLive(intent)) return false;
        themePending = true;
        if (!fileSelectionLive(intent)) return false;
        themeError = "";
        if (!fileSelectionLive(intent)) return false;
        themeErrors = [];
        if (!fileSelectionLive(intent)) return false;
        fileRequest.current = null;
        return publishFilePhase("", intent.generation);
    }
    function acceptThemeFileSelection(token, encodedUrl) {
        const intent = fileRequest.current;
        if (!intent || token !== intent.token || fileRequest.phase !== "selecting" || !fileSelectionLive(intent)) return false;
        if (typeof encodedUrl !== "string" || !encodedUrl.length) return failThemeFile(intent, "file");
        if (!intent.transport || typeof intent.transport.loadThemeFile !== "function") return failThemeFile(intent, "unavailable");
        themeFileTimer.interval = Math.max(1, Math.min(5000, themeFileTimeoutMs));
        themeFileTimer.restart();
        if (!fileSelectionLive(intent)) return false;
        if (!publishFilePhase("loading", intent.generation) || !fileSelectionLive(intent)) return false;
        try { intent.transport.loadThemeFile(encodedUrl, raw => state.receiveThemeFile(intent, raw),
            () => state.failThemeFile(intent, "unavailable")); }
        catch (_) { return failThemeFile(intent, "unavailable"); }
        return true;
    }
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
    readonly property bool dirty: editing && draft !== null && (busy || error.length > 0
        || themeText.length > 0 || themeError.length > 0
        || (defaultsDraft ? savedJSON.length > 0 : JSON.stringify(draft) !== beginDraftJSON))
    readonly property bool canUndo: previousJSON !== null && previousScope === scopeKey && undoSignature === signature
    readonly property bool canApply: editing && !busy && !stale && error.length === 0 && !themePending && themeError.length === 0 && draft !== null
    readonly property var effective: editing && preview ? preview : active
    readonly property bool overridden: editing && preview ? !defaultsDraft : Boolean(saved.value)

    function clearThemeInput() {
        if (!invalidateThemeFile()) return false;
        const generation = fileRequest.generation;
        const live = () => fileRequest.generation === generation;
        themeText = "";
        if (!live()) return false;
        themePending = false;
        if (!live()) return false;
        themeError = "";
        if (!live()) return false;
        themeErrors = [];
        if (!live()) return false;
        themeMetadata = null;
        if (!live()) return false;
        themeModified = false;
        return live();
    }
    function setThemeText(text) {
        if (!invalidateThemeFile()) return false;
        if (!editing) return false;
        if (themeText === text) return true;
        const generation = fileRequest.generation;
        const live = () => fileRequest.generation === generation;
        themeText = text;
        if (!live()) return false;
        themePending = text.length > 0;
        if (!live()) return false;
        themeError = "";
        if (!live()) return false;
        themeErrors = [];
        return live();
    }
    function previewTheme() {
        if (!invalidateThemeFile()) return false;
        if (!editing || stale || !draft || themeFileBlocked) return false;
        const generation = fileRequest.generation, text = themeText, owner = configuration, scope = scopeKey, savedSignature = signature;
        const live = () => editing && !stale && !themeFileBlocked && fileRequest.generation === generation
            && configuration === owner && scopeKey === scope && signature === savedSignature && themeText === text;
        const parsed = Theme.parse(text);
        if (!parsed.value) {
            themePending = text.length > 0;
            if (!live()) return false;
            themeError = parsed.error;
            if (!live()) return false;
            themeErrors = parsed.errors;
            return false;
        }
        const next = Appearance.validate({formatVersion: Appearance.formatVersion,
            baseTheme: draft.baseTheme, tokens: parsed.value.tokens});
        if (!next.value) return false;
        defaultsDraft = false;
        if (!live() || !refreshDraft(next.value, live)) return false;
        const current = () => live() && draft === next.value;
        if (!current()) return false;
        themeMetadata = {id: parsed.value.id, name: parsed.value.name, author: parsed.value.author,
            license: parsed.value.license, version: parsed.value.version};
        if (!current()) return false;
        themeModified = false;
        if (!current()) return false;
        themePending = false;
        if (!current()) return false;
        themeError = "";
        if (!current()) return false;
        themeErrors = [];
        return current();
    }
    function begin() {
        if (!invalidateThemeFile()) return false;
        if (!clearThemeInput()) return false;
        let generation = fileRequest.generation;
        const live = () => fileRequest.generation === generation;
        draft = Appearance.copy(active);
        if (!live()) return false;
        beginScope = scopeKey;
        if (!live()) return false;
        beginSignature = signature;
        if (!live()) return false;
        beginDraftJSON = JSON.stringify(draft);
        if (!live()) return false;
        preview = null;
        if (!live()) return false;
        defaultsDraft = false;
        if (!live()) return false;
        if (!editing) generation++;
        editing = true;
        if (!live()) return false;
        error = "";
        if (!live()) return false;
        message = "";
        return live();
    }
    function refreshDraft(value, guard) {
        if (fileRequest.current && !invalidateThemeFile()) return false;
        const live = () => typeof guard !== "function" || guard() === true;
        const result = Appearance.validate(value);
        if (!live()) return false;
        draft = value;
        // A newer token edit may run synchronously from draftChanged.
        const current = () => live() && (typeof guard !== "function" || draft === value);
        if (!current()) return false;
        error = result.error;
        if (!current()) return false;
        message = "";
        if (!current()) return false;
        if (result.value) preview = result.value;
        return current();
    }
    function setToken(key, value) {
        if (!invalidateThemeFile()) return false;
        if (!editing || !draft) return;
        const next = Appearance.copy(draft);
        next.tokens[key] = value;
        defaultsDraft = false;
        if (themeMetadata) themeModified = true;
        refreshDraft(next);
    }
    function selectTheme(theme) {
        if (!invalidateThemeFile()) return false;
        if (!editing) return;
        if (!clearThemeInput()) return false;
        const generation = fileRequest.generation;
        const live = () => fileRequest.generation === generation;
        defaultsDraft = false;
        if (!live()) return false;
        return refreshDraft(Appearance.legacy(configuration, theme), live);
    }
    function restoreDefaults() {
        if (!invalidateThemeFile()) return false;
        if (!editing) return;
        if (!clearThemeInput()) return false;
        const generation = fileRequest.generation;
        const live = () => fileRequest.generation === generation;
        if (!refreshDraft(Appearance.copy(legacy), live)) return false;
        defaultsDraft = true;
        return live();
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
        if (!invalidateThemeFile()) return false;
        if (!clearThemeInput()) return false;
        let generation = fileRequest.generation;
        const live = () => fileRequest.generation === generation;
        if (editing) generation++;
        editing = false;
        if (!live()) return false;
        preview = null;
        if (!live()) return false;
        draft = null;
        if (!live()) return false;
        defaultsDraft = false;
        if (!live()) return false;
        error = "";
        if (!live()) return false;
        message = "";
        return live();
    }
    function undo() {
        if (!invalidateThemeFile()) return false;
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
    onThemeTextChanged: {
        if (fileRequest && fileRequest.current && themeText !== fileRequest.current.text) invalidateThemeFile();
    }
    onDraftChanged: if (fileRequest && fileRequest.current) invalidateThemeFile()
    onDefaultsDraftChanged: if (fileRequest && fileRequest.current) invalidateThemeFile()
    onEditingChanged: invalidateThemeFile()
    onConfigurationChanged: invalidateThemeFile()
    onSignatureChanged: invalidateThemeFile()
    onThemeFileBlockedChanged: invalidateThemeFile()
    onThemeFileTransportChanged: invalidateThemeFile()
    onScopeKeyChanged: {
        previousJSON = null;
        cancel();
    }
}
