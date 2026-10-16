import QtQuick
import "../code/Profiles.js" as Profiles

QtObject {
    id: state
    required property var configuration
    property var transitionGuard: null
    readonly property string activeProfileId: internal.document ? internal.document.activeProfileId : "legacy"
    readonly property int revision: internal.revision
    readonly property bool initialized: internal.document !== null
    // Initial restoration is not a choice; nested command loads have their own provenance.
    readonly property alias hydratingInitial: internalState.hydratingInitial
    readonly property bool writable: internal.savedError.length === 0
    // Detached read snapshot. Consumers must not mutate it; Qt's freeze is best effort.
    readonly property var effective: Profiles.freeze(Profiles.copy(internal.presentation))
    readonly property var profiles: Profiles.freeze(internal.document
        ? internal.document.profiles.map(profile => ({id: profile.id, name: profile.name})) : [])
    readonly property string error: internal.savedError || internal.commandError
    readonly property string message: internal.message
    readonly property var savedJSON: configuration.profilesJSON === undefined ? "" : configuration.profilesJSON
    readonly property var legacyPresentation: Profiles.flat(configuration)

    property QtObject internal: QtObject {
        id: internalState
        property bool hydratingInitial: false
        property bool completed: false
        property var document: null
        property var presentation: Profiles.flat(state.configuration)
        property int revision: 0
        property string savedError: ""
        property string commandError: ""
        property string message: ""
        property int idCounter: 0
    }

    function fail(message) { internal.commandError = message; return false; }
    function check(expectedScope, expectedRevision, transition) {
        internal.commandError = "";
        internal.message = "";
        if (!writable) return false;
        if (expectedScope !== activeProfileId || expectedRevision !== revision)
            return fail(qsTr("A configuração mudou. Abra novamente antes de salvar."));
        if (transition && transitionGuard !== null) {
            try {
                if (typeof transitionGuard !== "function" || transitionGuard() !== true)
                    return fail(qsTr("Aplique ou cancele a prévia de aparência antes de trocar o perfil."));
            } catch (_) { return fail(qsTr("Não foi possível verificar a prévia de aparência.")); }
        }
        // The hook may run other QML handlers; repeat the precondition afterwards.
        if (!writable || expectedScope !== activeProfileId || expectedRevision !== revision)
            return fail(qsTr("A configuração mudou. Abra novamente antes de salvar."));
        return true;
    }
    function load(initial = false) {
        const previous = internal.hydratingInitial;
        internal.hydratingInitial = initial === true;
        try {
            const result = Profiles.parse(savedJSON);
            internal.revision++;
            internal.commandError = "";
            internal.message = "";
            internal.savedError = result.error;
            if (result.error) return;
            internal.document = result.value ? Profiles.freeze(result.value) : null;
            refresh();
        } finally {
            internal.hydratingInitial = previous;
        }
    }
    function refresh() {
        internal.presentation = Profiles.freeze(Profiles.copy(activeProfileId === "legacy" ? Profiles.flat(configuration)
            : Profiles.presentation(internal.document.profiles.find(profile => profile.id === activeProfileId))));
    }
    function store(document, beforeWrite) {
        const raw = JSON.stringify(document);
        const result = Profiles.parse(raw);
        if (result.error) return fail(result.error);
        if (beforeWrite !== undefined && beforeWrite() !== true) return false;
        configuration.profilesJSON = raw;
        return true;
    }
    function initializeDefaults(expectedScope, expectedRevision) {
        if (!check(expectedScope, expectedRevision, true)) return false;
        if (savedJSON !== "") return fail(qsTr("Os perfis já foram criados."));
        const captured = Profiles.capture(Profiles.flat(configuration));
        if (captured.error) return fail(captured.error);
        const document = {formatVersion: Profiles.formatVersion, activeProfileId: "legacy", profiles: [
            {id: "work", name: "Trabalho"}, {id: "personal", name: "Pessoal"}, {id: "games", name: "Jogos"}
        ].map(entry => Object.assign(Profiles.copy(captured.value), entry))};
        if (!store(document)) return false;
        internal.message = captured.message;
        return true;
    }
    function create(name, expectedScope, expectedRevision) {
        if (!check(expectedScope, expectedRevision, true)) return false;
        if (typeof name !== "string") return fail(qsTr("Escolha um nome de perfil válido."));
        name = name.trim();
        if (!Profiles.validName(name)) return fail(qsTr("Use um nome de perfil com até 48 caracteres."));
        if (internal.document && (internal.document.profiles.length >= 16
                || internal.document.profiles.some(profile => profile.name === name)))
            return fail(qsTr("Nome repetido ou limite de 16 perfis atingido."));
        const captured = Profiles.capture(internal.presentation);
        if (captured.error) return fail(captured.error);
        const document = internal.document ? Profiles.copy(internal.document)
            : {formatVersion: Profiles.formatVersion, activeProfileId: "legacy", profiles: []};
        let id;
        do { id = "custom-" + Date.now().toString(36) + "-" + (++internal.idCounter).toString(36); }
        while (document.profiles.some(profile => profile.id === id));
        document.profiles.push(Object.assign(captured.value, {id: id, name: name}));
        document.activeProfileId = id;
        if (!store(document)) return false;
        internal.message = captured.message;
        return true;
    }
    function rename(name, expectedScope, expectedRevision) {
        if (!check(expectedScope, expectedRevision, true)) return false;
        if (activeProfileId === "legacy") return fail(qsTr("Escolha um perfil para renomear."));
        if (typeof name !== "string") return fail(qsTr("Escolha um nome de perfil válido."));
        name = name.trim();
        if (!Profiles.validName(name)) return fail(qsTr("Use um nome de perfil com até 48 caracteres."));
        if (internal.document.profiles.some(profile => profile.id !== activeProfileId && profile.name === name))
            return fail(qsTr("Já existe um perfil com esse nome."));
        // Keep optional fields absent in older valid documents; rename is a name-only edit.
        const raw = savedJSON;
        const document = JSON.parse(raw);
        const beforeWrite = () => writable && expectedScope === activeProfileId
            && expectedRevision === revision && savedJSON === raw;
        const profile = document.profiles.find(profile => profile.id === activeProfileId);
        if (profile.name === name) return beforeWrite();
        profile.name = name;
        return store(document, beforeWrite);
    }
    function select(id, expectedScope, expectedRevision, continuationGuard) {
        if (continuationGuard !== undefined && typeof continuationGuard !== "function") return false;
        if (!check(expectedScope, expectedRevision, true)) return false;
        if (typeof id !== "string" || (id !== "legacy"
                && (!internal.document || !internal.document.profiles.some(profile => profile.id === id))))
            return fail(qsTr("O perfil selecionado não existe."));
        const beforeWrite = () => {
            if (!writable || expectedScope !== activeProfileId || expectedRevision !== revision) return false;
            if (continuationGuard !== undefined) {
                try { if (continuationGuard() !== true) return false; }
                catch (_) { return false; }
            }
            // A caller may synchronously select or edit another profile.
            return writable && expectedScope === activeProfileId && expectedRevision === revision;
        };
        if (id === activeProfileId) return beforeWrite();
        const document = Profiles.copy(internal.document);
        document.activeProfileId = id;
        return store(document, beforeWrite);
    }
    // Patches are plain data; configuration is the typed, writable KConfig map.
    // Legacy field writes are not a backend transaction if a setter throws.
    function commitPresentation(patch, expectedScope, expectedRevision, continuationGuard) {
        if (continuationGuard !== undefined && typeof continuationGuard !== "function") return false;
        if (!check(expectedScope, expectedRevision, false)) return false;
        const validated = Profiles.validatePatch(patch);
        if (validated.error) return fail(validated.error);
        if (!check(expectedScope, expectedRevision, false)) return false;
        if (activeProfileId === "legacy") {
            // A guarded legacy launcher patch still has exactly one setter.
            if (continuationGuard !== undefined) {
                const keys = Object.keys(validated.value);
                if (keys.length !== 1 || keys[0] !== "launchers") return false;
                try { if (continuationGuard() !== true) return false; }
                catch (_) { return false; }
                if (!writable || expectedScope !== activeProfileId || expectedRevision !== revision) return false;
                configuration.launchers = validated.value.launchers;
                return true;
            }
            if (validated.value.widgets && validated.value.widgets.some((widget, index) => widget.id !== Profiles.widgetIds[index]))
                return fail(qsTr("Crie/use um perfil para organizar os widgets"));
            // Validate the whole patch first; legacy writes only its supplied fields.
            for (const key of Object.keys(validated.value)) {
                if (key === "appearance") {
                    for (const field of Object.keys(validated.value.appearance))
                        configuration[field] = validated.value.appearance[field];
                } else if (key === "widgets") {
                    validated.value.widgets.forEach((widget, index) => configuration[Profiles.widgetKeys[index]] = widget.visible);
                } else configuration[key] = validated.value[key];
            }
            return true;
        }
        const document = Profiles.copy(internal.document);
        const index = document.profiles.findIndex(profile => profile.id === activeProfileId);
        const profile = document.profiles[index];
        document.profiles[index] = Object.assign(Profiles.merge(Profiles.presentation(profile), validated.value),
            {id: profile.id, name: profile.name});
        const beforeWrite = () => {
            if (!writable || expectedScope !== activeProfileId || expectedRevision !== revision) return false;
            if (continuationGuard !== undefined) {
                try { if (continuationGuard() !== true) return false; }
                catch (_) { return false; }
            }
            // The caller guard may itself dispatch a synchronous handler.
            return writable && expectedScope === activeProfileId && expectedRevision === revision;
        };
        if (JSON.stringify(document) === JSON.stringify(internal.document)) return beforeWrite();
        return store(document, beforeWrite);
    }
    onSavedJSONChanged: if (internal.completed) load()
    onLegacyPresentationChanged: if (internal.completed && activeProfileId === "legacy" && writable) {
        internal.revision++;
        refresh();
    }
    Component.onCompleted: { internal.completed = true; load(true); }
}
