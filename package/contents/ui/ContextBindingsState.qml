import QtQuick
import "../code/Contexts.js" as Contexts

QtObject {
    id: state
    required property var configuration
    required property var profiles
    required property var contexts
    readonly property int revision: internal.revision
    readonly property bool writable: internal.savedError.length === 0 && profiles.writable === true
    readonly property string error: internal.savedError || internal.commandError
    readonly property var bindings: Contexts.freeze(Contexts.copy(internal.document))
    readonly property var savedJSON: configuration.contextsJSON === undefined ? "" : configuration.contextsJSON

    property QtObject internal: QtObject {
        property bool completed: false
        property int revision: 0
        property string savedError: ""
        property string commandError: ""
        property var document: Contexts.emptyDocument()
    }

    function fail(message) { internal.commandError = message; return false; }
    function captureCallerContext(value) {
        if (value === null || typeof value !== "object" || Array.isArray(value))
            return {error: "Associação de contexto inválida."};
        try {
            const keys = Object.keys(value);
            if (keys.length !== 3 || !keys.every(key => ["status", "id", "name"].indexOf(key) !== -1))
                return {error: "Associação de contexto inválida."};
            if (keys.some(key => {
                const descriptor = Object.getOwnPropertyDescriptor(value, key);
                return !descriptor || descriptor.get !== undefined || descriptor.set !== undefined;
            })) return {error: "Associação de contexto inválida."};
            return Contexts.captureContext({status: value.status, id: value.id, name: value.name});
        } catch (_) { return {error: "Associação de contexto inválida."}; }
    }
    function currentProfileExists(profileId) {
        const listed = profiles.profiles;
        if (!Array.isArray(listed)) return false;
        return listed.some(profile => {
            if (!profile) return false;
            const id = profile.id;
            return id === profileId && Contexts.validProfileId(id);
        });
    }
    function check(expectedProfileScope, expectedProfileRevision, expectedContextRevision, expectedRevision) {
        internal.commandError = "";
        if (internal.savedError.length > 0) return false;
        if (profiles.writable !== true) return fail(qsTr("Os perfis salvos não estão disponíveis para associação."));
        if (expectedProfileScope !== profiles.activeProfileId || expectedProfileRevision !== profiles.revision
                || expectedContextRevision !== contexts.revision || expectedRevision !== revision)
            return fail(qsTr("O contexto ou perfil mudou. Abra novamente antes de salvar."));
        return true;
    }
    function store(document, expectedProfileScope, expectedProfileRevision, expectedContextRevision,
                   expectedRevision, requiredProfileId) {
        const validated = Contexts.validate(document);
        if (validated.error) return fail(validated.error);
        const raw = JSON.stringify(validated.value);
        if (!check(expectedProfileScope, expectedProfileRevision, expectedContextRevision, expectedRevision)) return false;
        if (requiredProfileId && !currentProfileExists(requiredProfileId))
            return fail(qsTr("O perfil escolhido não existe."));
        if (!check(expectedProfileScope, expectedProfileRevision, expectedContextRevision, expectedRevision)) return false;
        try { configuration.contextsJSON = raw; }
        catch (_) { return fail(qsTr("Não foi possível salvar a associação de contexto.")); }
        return configuration.contextsJSON === raw;
    }
    function bind(kind, context, profileId, expectedProfileScope, expectedProfileRevision,
                  expectedContextRevision, expectedRevision) {
        const captured = captureCallerContext(context);
        if (captured.error) return fail(captured.error);
        if (!check(expectedProfileScope, expectedProfileRevision, expectedContextRevision, expectedRevision)) return false;
        if (!currentProfileExists(profileId)) return fail(qsTr("O perfil escolhido não existe."));
        const snapshot = contexts.snapshot;
        const live = kind === "activity" ? snapshot.activity
            : kind === "desktop" ? snapshot.desktop : null;
        if (!live || live.status !== "ready" || captured.value.id !== live.id
                || captured.value.name !== live.name)
            return fail(qsTr("O contexto mudou. Escolha novamente antes de salvar."));
        const result = Contexts.bind(internal.document, kind, captured.value, profileId);
        if (result.error) return fail(result.error);
        if (!result.changed) return true;
        return store(result.value, expectedProfileScope, expectedProfileRevision,
            expectedContextRevision, expectedRevision, profileId);
    }
    function unbind(kind, contextId, expectedProfileScope, expectedProfileRevision,
                    expectedContextRevision, expectedRevision) {
        if (!check(expectedProfileScope, expectedProfileRevision, expectedContextRevision, expectedRevision)) return false;
        const result = Contexts.unbind(internal.document, kind, contextId);
        if (result.error) return fail(result.error);
        if (!result.changed) return true;
        return store(result.value, expectedProfileScope, expectedProfileRevision,
            expectedContextRevision, expectedRevision, "");
    }
    function load() {
        const result = Contexts.parse(savedJSON);
        internal.revision++;
        internal.commandError = "";
        internal.savedError = result.error || "";
        if (!result.error) internal.document = Contexts.freeze(result.value);
    }

    onSavedJSONChanged: if (internal.completed) load()
    Component.onCompleted: { internal.completed = true; load(); }
}
