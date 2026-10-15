import QtQuick
import "../code/Profiles.js" as Profiles

QtObject {
    id: state
    required property var configuration
    required property var profiles
    required property var contexts
    required property var bindingsState
    property bool active: false
    property bool interactionBusy: false
    readonly property bool enabled: configuration && configuration.autoContextEnabled === true
    readonly property string defaultProfileId: configuration && typeof configuration.autoContextDefaultProfile === "string"
        ? configuration.autoContextDefaultProfile : ""
    readonly property bool canEnable: Boolean(profiles && profiles.initialized && profiles.writable
        && bindingsState && bindingsState.writable && managedProfile(defaultProfileId))
    readonly property bool observing: active && enabled && canEnable
    readonly property bool manualOverride: internal.manual
    readonly property string statusText: {
        if (!enabled) return qsTr("Alternância automática desativada.");
        if (!active) return qsTr("Aguardando a dock ficar pronta.");
        if (!canEnable) return qsTr("Confira os perfis, as associações e o perfil padrão.");
        if (manualOverride) return qsTr("Seleção manual até mudar de contexto ou reiniciar a dock.");
        if (!readyPair()) {
            const snapshot = contexts && contexts.snapshot;
            if (!snapshot) return qsTr("Aguardando contexto KDE.");
            const activityUnavailable = snapshot.activity.status === "unavailable";
            const desktopUnavailable = snapshot.desktop.status === "unavailable";
            if (activityUnavailable && desktopUnavailable)
                return qsTr("Aguardando contexto KDE: Activity e área de trabalho atuais indisponíveis.");
            if (activityUnavailable) return qsTr("Aguardando contexto KDE: Activity atual indisponível.");
            if (desktopUnavailable) return qsTr("Aguardando contexto KDE: área de trabalho atual indisponível.");
            return qsTr("Aguardando contexto KDE: carregamento em andamento.");
        }
        if (interactionBusy) return qsTr("Troca de perfil adiada durante a interação.");
        if (internal.problem) return internal.problem;
        const target = resolveTarget();
        if (!managedProfile(target.id)) return qsTr("O perfil associado não está disponível.");
        const profile = profiles.profiles.find(entry => entry.id === target.id);
        const reason = target.reason === "activity" ? qsTr("pela Activity")
            : target.reason === "desktop" ? qsTr("pela área de trabalho") : qsTr("padrão");
        return qsTr("Automático · %1 · %2").arg(String(profile.name).slice(0, 48)).arg(reason).slice(0, 160);
    }

    property QtObject internal: QtObject {
        property bool completed: false
        property bool queued: false
        property int generation: 0
        property int epoch: 0
        property string pair: ""
        property bool manual: false
        property string problem: ""
        property var attempt: null
    }

    function managedProfile(id) {
        return typeof id === "string" && id !== "legacy" && id.length > 0 && profiles
            && Array.isArray(profiles.profiles) && profiles.profiles.some(entry => entry.id === id);
    }
    function readyPair() {
        if (!contexts || !contexts.snapshot) return "";
        const snapshot = contexts.snapshot;
        return snapshot.activity.status === "ready" && snapshot.desktop.status === "ready"
            ? JSON.stringify([snapshot.activity.id, snapshot.desktop.id]) : "";
    }
    function schedule() {
        if (!internal || !internal.completed || internal.queued) return;
        internal.queued = true;
        Qt.callLater(() => {
            if (!state) return;
            internal.queued = false;
            evaluate();
        });
    }
    function invalidate() {
        if (!internal || !internal.completed) return;
        internal.generation++;
        schedule();
    }
    function observeContext() {
        if (!internal || !internal.completed || !active || !enabled) return;
        const pair = readyPair();
        // Observe every confirmed pair synchronously: coalescing must not erase ABA.
        if (pair && pair !== internal.pair) {
            internal.epoch++;
            internal.pair = pair;
            internal.manual = false;
        }
    }
    function selected() {
        if (!internal.completed) return;
        // A snapshot observer can select before ContextState publishes its revision.
        observeContext();
        const attempt = internal.attempt;
        // Admission is recorded only by the final select guard, not before transitionGuard.
        const own = attempt && attempt.admitted && attempt.profiles === profiles
            && profiles.activeProfileId === attempt.target
            && profiles.revision === attempt.expectedRevision && profiles.savedJSON === attempt.expectedJSON;
        if (own) {
            attempt.ownEvents++;
            attempt.ownEpoch = internal.epoch;
        }
        else if (active && enabled && internal.pair) {
            internal.manual = true;
            internal.generation++;
        }
        schedule();
    }
    function resolveTarget() {
        const snapshot = contexts.snapshot, bindings = bindingsState.bindings;
        const activity = bindings.activityBindings.find(entry => entry.contextId === snapshot.activity.id);
        if (activity) return {id:activity.profileId, reason:"activity"};
        const desktop = bindings.desktopBindings.find(entry => entry.contextId === snapshot.desktop.id);
        return desktop ? {id:desktop.profileId, reason:"desktop"} : {id:defaultProfileId, reason:"default"};
    }
    function valid(intent) {
        return internal.attempt === intent && observing && !interactionBusy && !manualOverride
            && intent.generation === internal.generation && intent.epoch === internal.epoch
            && intent.configuration === configuration && intent.profiles === profiles
            && intent.contexts === contexts && intent.bindingsState === bindingsState
            && intent.defaultId === defaultProfileId && intent.pair === readyPair()
            && intent.contextRevision === contexts.revision && intent.bindingRevision === bindingsState.revision
            && intent.bindingJSON === bindingsState.savedJSON
            && intent.scope === profiles.activeProfileId && intent.profileRevision === profiles.revision
            && intent.profileJSON === profiles.savedJSON && managedProfile(intent.target);
    }
    function evaluate() {
        if (!observing || interactionBusy || manualOverride || !readyPair()) return;
        internal.problem = "";
        const target = resolveTarget().id;
        if (!managedProfile(target)) { internal.problem = qsTr("O perfil associado não está disponível."); return; }
        if (target === profiles.activeProfileId) return;
        const document = Profiles.parse(profiles.savedJSON).value;
        if (!document) return;
        document.activeProfileId = target;
        const intent = {configuration:configuration, profiles:profiles, contexts:contexts, bindingsState:bindingsState,
            generation:internal.generation, epoch:internal.epoch, pair:readyPair(), contextRevision:contexts.revision,
            bindingRevision:bindingsState.revision, bindingJSON:bindingsState.savedJSON, defaultId:defaultProfileId,
            scope:profiles.activeProfileId, profileRevision:profiles.revision, profileJSON:profiles.savedJSON,
            target:target, expectedJSON:JSON.stringify(document), expectedRevision:-1, admitted:false, ownEvents:0, ownEpoch:-1};
        internal.attempt = intent;
        let accepted = false;
        try {
            accepted = intent.profiles.select(intent.target, intent.scope, intent.profileRevision, () => {
                if (!valid(intent)) return false;
                intent.expectedRevision = intent.profileRevision + 1;
                intent.admitted = true;
                return true;
            }) === true;
        } catch (_) { accepted = false; }
        finally {
            // Busy/context notifications during our committed setter cannot erase its receipt.
            if (internal.attempt === intent) internal.attempt = null;
        }
        if (!accepted) {
            if (intent.ownEvents && intent.ownEpoch === internal.epoch && intent.profiles === profiles
                    && active && enabled && internal.pair) {
                internal.manual = true;
                internal.generation++;
            }
            internal.problem = qsTr("A troca automática não foi concluída; confira o perfil e a prévia.");
        }
    }
    function setDefaultProfile(id) {
        if (typeof id !== "string") return false;
        if (id === defaultProfileId) return true;
        if (!profiles || !profiles.initialized || !profiles.writable || !managedProfile(id)) return false;
        try { configuration.autoContextDefaultProfile = id; }
        catch (_) { return false; }
        return defaultProfileId === id;
    }
    function setEnabled(value) {
        if (typeof value !== "boolean") return false;
        if (value === enabled) return true;
        if (value && !canEnable) return false;
        try { configuration.autoContextEnabled = value; }
        catch (_) { return false; }
        return enabled === value;
    }
    function resume() {
        if (!observing) return false;
        internal.manual = false;
        invalidate();
        return true;
    }
    onEnabledChanged: {
        if (internal && internal.completed) {
            internal.manual = false;
            if (!enabled) internal.pair = "";
            observeContext();
            invalidate();
        }
    }
    onActiveChanged: {
        if (internal && internal.completed) {
            if (!active) { internal.manual = false; internal.pair = ""; }
            observeContext();
            invalidate();
        }
    }
    onObservingChanged: { observeContext(); invalidate(); }
    onInteractionBusyChanged: invalidate()
    onDefaultProfileIdChanged: invalidate()
    onConfigurationChanged: invalidate()
    onProfilesChanged: invalidate()
    onContextsChanged: { observeContext(); invalidate(); }
    onBindingsStateChanged: invalidate()
    property Connections contextChanges: Connections {
        target: state.contexts
        function onRevisionChanged() { state.observeContext(); state.invalidate(); }
    }
    property Connections bindingChanges: Connections {
        target: state.bindingsState
        function onRevisionChanged() { state.invalidate(); }
        function onWritableChanged() { state.invalidate(); }
    }
    property Connections profileChanges: Connections {
        target: state.profiles
        function onActiveProfileIdChanged() { state.selected(); }
        function onRevisionChanged() { state.schedule(); }
        function onWritableChanged() { state.invalidate(); }
        function onInitializedChanged() { state.invalidate(); }
    }
    Component.onCompleted: { internal.completed = true; observeContext(); invalidate(); }
}
