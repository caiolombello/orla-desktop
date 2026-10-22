import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

Controls.ScrollView {
    id: controls
    property var desktopSwitch: null
    property var automation: null
    required property var contexts
    required property var bindingsState
    required property var profiles
    property bool active: false
    property var configuration: null
    property bool sessionOpen: false
    property bool savedOpen: false
    property var savedIntent: null
    property int savedTicket: 0
    property int savedImpactEpoch: 0
    property bool savedRemoving: false
    property string savedError: ""
    // Restoring a preference or owner inside a callback is still newer authority.
    property var savedAuthority: [configuration, bindingsState, profiles, contexts,
        profiles ? profiles.configuration : null, bindingsState ? bindingsState.configuration : null,
        bindingsState ? bindingsState.profiles : null, bindingsState ? bindingsState.contexts : null,
        configuration ? configuration.autoContextEnabled : undefined,
        configuration ? configuration.autoContextDefaultProfile : undefined,
        configuration ? configuration.autoContextPolicy : undefined]
    onSavedAuthorityChanged: savedImpactEpoch++
    readonly property bool savedWritable: Boolean(configuration && profiles && contexts && bindingsState
        && profiles.configuration === configuration && bindingsState.configuration === configuration
        && bindingsState.profiles === profiles && bindingsState.contexts === contexts && bindingsState.writable)
    readonly property var savedEntries: !savedWritable ? [] :
        bindingsState.bindings.activityBindings.map(entry => savedOption("activity", entry))
        .concat(bindingsState.bindings.desktopBindings.map(entry => savedOption("desktop", entry)))
    readonly property string savedProblem: savedIntent && !savedCurrent(savedIntent)
        ? qsTr("A associação ou configuração mudou. Cancele e escolha novamente.") : savedError
    property string pendingActivityProfileId: ""
    property string pendingDesktopProfileId: ""
    property var activityIntent: null
    property var desktopIntent: null
    readonly property var choices: profiles.profiles
    contentWidth: availableWidth
    clip: true

    function savedOption(kind, entry) {
        const domain = kind === "activity" ? qsTr("Activity") : qsTr("Área");
        const name = entry.lastKnownName || (kind === "activity" ? qsTr("Activity sem nome") : qsTr("Área sem nome"));
        return {kind: kind, entry: entry, label: domain + " · " + name};
    }
    function savedOwners(intent) {
        return savedWritable && configuration === intent.configuration && bindingsState === intent.bindings
            && profiles === intent.profiles && contexts === intent.contexts && savedImpactEpoch === intent.impact
            && profiles.savedJSON === intent.profileRaw && profiles.activeProfileId === intent.scope
            && profiles.revision === intent.profileRevision && contexts.revision === intent.contextRevision;
    }
    function savedCurrent(intent) {
        return Boolean(intent && savedOwners(intent) && bindingsState.savedJSON === intent.raw
            && bindingsState.revision === intent.revision);
    }
    function resetSaved() {
        savedTicket++;
        savedIntent = null;
        savedError = "";
        savedSelector.currentIndex = -1;
    }
    function toggleSaved() {
        if (!sessionOpen || !visible) return;
        if (savedOpen) {
            const window = controls.Window.window;
            const focused = window ? window.activeFocusItem : null;
            const owned = focused === savedSelector || focused === savedCancel || focused === savedRemove;
            if (owned) savedToggle.forceActiveFocus(Qt.TabFocusReason);
            resetSaved();
            savedOpen = false;
        } else {
            resetSaved();
            savedOpen = true;
            revealSaved(savedToggle);
        }
    }
    function selectSaved(index) {
        if (!sessionOpen || !visible || !savedOpen || savedIntent || !savedWritable
                || index < 0 || index >= savedEntries.length) return;
        const option = savedEntries[index];
        const entry = JSON.parse(JSON.stringify(option.entry));
        const document = JSON.parse(JSON.stringify(bindingsState.bindings));
        const key = option.kind === "activity" ? "activityBindings" : "desktopBindings";
        document[key] = document[key].filter(value => value.contextId !== entry.contextId);
        savedTicket++;
        savedError = "";
        savedIntent = {configuration: configuration, bindings: bindingsState, profiles: profiles, contexts: contexts,
            kind: option.kind, entry: entry, label: option.label, profileName: profileName(entry.profileId),
            raw: bindingsState.savedJSON, revision: bindingsState.revision, profileRaw: profiles.savedJSON,
            scope: profiles.activeProfileId, profileRevision: profiles.revision, contextRevision: contexts.revision,
            impact: savedImpactEpoch, expected: JSON.stringify(document), options: savedEntries};
        // The selector becomes disabled; continue at the safe explicit action.
        if (savedSelector.activeFocus) savedCancel.forceActiveFocus(Qt.TabFocusReason);
    }
    function cancelSaved() {
        const window = controls.Window.window;
        const focused = window ? window.activeFocusItem : null;
        const owned = focused === savedSelector || focused === savedCancel || focused === savedRemove;
        const ticket = savedTicket;
        resetSaved();
        if (sessionOpen && visible && savedOpen && savedTicket === ticket + 1 && !savedIntent
                && window && window.activeFocusItem === focused && owned)
            (savedSelector.enabled ? savedSelector : savedToggle).forceActiveFocus(Qt.TabFocusReason);
    }
    function removeSaved() {
        const intent = savedIntent, ticket = savedTicket;
        if (savedRemoving || !sessionOpen || !visible || !savedOpen || !savedRemove.visible || !savedCurrent(intent)) return;
        const window = controls.Window.window, focused = window ? window.activeFocusItem : null;
        const valid = () => Boolean(sessionOpen && visible && savedOpen && savedIntent === intent
            && savedTicket === ticket && savedRemove.visible && savedCurrent(intent));
        let accepted = false;
        savedRemoving = true;
        try { accepted = intent.bindings.unbind(intent.kind, intent.entry.contextId, intent.scope,
            intent.profileRevision, intent.contextRevision, intent.revision, valid) === true; }
        catch (_) { accepted = false; }
        finally { savedRemoving = false; }
        if (!sessionOpen || !visible || !savedOpen || savedIntent !== intent || savedTicket !== ticket) return;
        // The own write advances bindings. A true return never owns newer UI callbacks.
        if (accepted && savedOwners(intent) && bindingsState.savedJSON === intent.expected
                && bindingsState.revision === intent.revision + 1) {
            resetSaved();
            if (sessionOpen && visible && savedOpen && savedTicket === ticket + 1 && !savedIntent && window
                    && controls.Window.window === window && (window.activeFocusItem === focused || window.activeFocusItem === savedCard)
                    && (focused === savedCancel || focused === savedRemove))
                (savedSelector.enabled ? savedSelector : savedToggle).forceActiveFocus(Qt.TabFocusReason);
        } else savedError = bindingsState.error || qsTr("Não foi possível remover a associação. Cancele e escolha novamente.");
    }
    function revealSaved(control) {
        const owner = controls, ticket = savedTicket, window = controls.Window.window;
        Qt.callLater(() => {
            if (!Qt.isQtObject(owner) || !Qt.isQtObject(control) || !owner.sessionOpen || !owner.visible
                    || owner.savedTicket !== ticket || owner.Window.window !== window || !control.visible || !control.activeFocus) return;
            const viewport = owner.contentItem, rim = Style.space.xs;
            const target = control === savedToggle && owner.savedOpen ? savedCard
                : control === savedCancel || control === savedRemove ? savedRecovery : control;
            const item = target.height + rim * 2 <= viewport.height ? target : control;
            const point = item.mapToItem(viewport, 0, 0);
            if (point.y - rim < 0) viewport.contentY += point.y - rim;
            else if (point.y + item.height + rim > viewport.height)
                viewport.contentY += point.y + item.height + rim - viewport.height;
        });
    }
    onSessionOpenChanged: {
        if (!sessionOpen) { resetSaved(); savedOpen = false; }
        else if (savedToggle.activeFocus) revealSaved(savedToggle);
    }
    Keys.onEscapePressed: event => {
        if (savedSelector.popup.visible) { savedSelector.popup.close(); event.accepted = true; }
        else if (savedIntent) { cancelSaved(); event.accepted = true; }
        else event.accepted = false;
    }
    Connections {
        target: controls.contentItem
        function onContentHeightChanged() {
            if (savedToggle.activeFocus) controls.revealSaved(savedToggle);
            if (controls.savedOpen)
                for (const control of [savedSelector, savedCancel, savedRemove])
                    if (control.activeFocus) controls.revealSaved(control);
        }
    }
    function currentChoice(id) { return choices.findIndex(choice => choice.id === id); }
    function ensureChoice(kind) {
        const pending = kind === "activity" ? pendingActivityProfileId : pendingDesktopProfileId;
        const selected = currentChoice(pending) >= 0 ? pending : choices.length > 0 ? choices[0].id : "";
        if (kind === "activity") pendingActivityProfileId = selected;
        else pendingDesktopProfileId = selected;
        return selected;
    }
    function captureIntent(kind) {
        const selected = ensureChoice(kind);
        const context = kind === "activity" ? contexts.snapshot.activity : contexts.snapshot.desktop;
        const intent = {
            context: {status: context.status, id: context.id, name: context.name},
            profileId: selected,
            profileScope: profiles.activeProfileId,
            profileRevision: profiles.revision,
            contextRevision: contexts.revision,
            bindingsRevision: bindingsState.revision
        };
        if (kind === "activity") activityIntent = intent;
        else desktopIntent = intent;
        return intent;
    }
    function chooseProfile(kind, id) {
        if (kind === "activity") pendingActivityProfileId = id;
        else pendingDesktopProfileId = id;
        return captureIntent(kind);
    }
    function bindIntent(kind) {
        const intent = kind === "activity" ? activityIntent : desktopIntent;
        if (!intent) return false;
        const saved = bindingsState.bind(kind, intent.context, intent.profileId,
            intent.profileScope, intent.profileRevision, intent.contextRevision, intent.bindingsRevision);
        if (saved) captureIntent(kind);
        return saved;
    }
    function unbindIntent(kind) {
        const intent = kind === "activity" ? activityIntent : desktopIntent;
        if (!intent) return false;
        const saved = bindingsState.unbind(kind, intent.context.id, intent.profileScope,
            intent.profileRevision, intent.contextRevision, intent.bindingsRevision);
        if (saved) captureIntent(kind);
        return saved;
    }
    function bindingFor(kind, id) {
        const values = kind === "activity" ? bindingsState.bindings.activityBindings
            : bindingsState.bindings.desktopBindings;
        return values.find(binding => binding.contextId === id) || null;
    }
    function profileName(id) {
        const profile = choices.find(entry => entry.id === id);
        return profile ? profile.name : qsTr("Perfil indisponível");
    }
    function staleCount(kind) {
        const items = kind === "activity" ? contexts.snapshot.activities : contexts.snapshot.desktops;
        const values = kind === "activity" ? bindingsState.bindings.activityBindings
            : bindingsState.bindings.desktopBindings;
        return values.filter(binding => !items.some(item => item.id === binding.contextId)).length;
    }
    function orphanProfileCount(kind) {
        if (!bindingsState.writable) return 0;
        const values = kind === "activity" ? bindingsState.bindings.activityBindings
            : bindingsState.bindings.desktopBindings;
        return values.filter(binding => !choices.some(profile => profile.id === binding.profileId)).length;
    }
    function reveal(control) {
        const viewport = contentItem;
        const point = control.mapToItem(viewport, 0, 0);
        const height = Math.min(control.height, viewport.height);
        if (point.y < 0) viewport.contentY += point.y;
        else if (point.y + height > viewport.height)
            viewport.contentY += point.y + height - viewport.height;
    }
    function restoreFocus(control) { Qt.callLater(() => { if (control && control.enabled) control.forceActiveFocus(Qt.TabFocusReason); }); }
    onActiveChanged: if (active) { captureIntent("activity"); captureIntent("desktop"); }

    ColumnLayout {
        width: controls.availableWidth
        spacing: Style.space.md
        AutoContextControls {
            objectName: "autoContextControls"
            Layout.fillWidth: true
            visible: controls.automation !== null
            automation: controls.automation
            profiles: controls.profiles
            onFocusRequested: control => controls.reveal(control)
        }
        DesktopSwitchControls {
            Layout.fillWidth: true
            command: controls.desktopSwitch
            onFocusRequested: control => controls.reveal(control)
        }
        Controls.Label {
            objectName: "contextBindingsExplanation"
            Layout.fillWidth: true
            text: controls.automation !== null
                ? controls.automation.policy === "desktop"
                    ? qsTr("Associações por ID. Em Somente áreas, as associações de Activity ficam preservadas e são ignoradas pelo automático.")
                    : qsTr("Associações por ID. Com o automático ativado, a Activity tem prioridade sobre a área de trabalho.")
                : qsTr("Associar organiza suas preferências. As associações não trocam a Activity ou a área de trabalho.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }

        Controls.Label {
            objectName: "orphanProfileBindings"
            Layout.fillWidth: true
            readonly property int activityCount: controls.orphanProfileCount("activity")
            readonly property int desktopCount: controls.orphanProfileCount("desktop")
            visible: activityCount + desktopCount > 0
            text: qsTr("Associações com perfil indisponível: %1 de Activity e %2 de área. Nos contextos disponíveis, escolha outro perfil e associe novamente ou use Remover. As demais associações continuam preservadas por ID.")
                .arg(activityCount).arg(desktopCount)
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }

        Card {
            id: savedCard
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: Style.space.sm
                OrlaButton {
                    id: savedToggle
                    objectName: "savedContextToggle"
                    Layout.fillWidth: true
                    variant: "ghost"
                    text: qsTr("Associações salvas")
                    checkable: true
                    checked: controls.savedOpen
                    onClicked: controls.toggleSaved()
                    onActiveFocusChanged: if (activeFocus) controls.revealSaved(this)
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: controls.savedOpen
                    spacing: Style.space.sm
                    Controls.Label {
                        Layout.fillWidth: true
                        objectName: "savedContextAvailability"
                        visible: !controls.savedWritable || controls.savedEntries.length === 0
                        text: !controls.savedWritable ? qsTr("As associações estão protegidas ou indisponíveis. Confira os avisos e a configuração dos perfis.")
                            : qsTr("Nenhuma associação salva.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                    }
                    Controls.Label { visible: controls.savedEntries.length > 0; text: qsTr("Associação salva"); textFormat: Text.PlainText }
                    Controls.ComboBox {
                        id: savedSelector
                        objectName: "savedContextSelector"
                        Layout.fillWidth: true
                        enabled: controls.savedWritable && controls.savedEntries.length > 0 && !controls.savedIntent
                        model: controls.savedIntent ? controls.savedIntent.options : controls.savedEntries
                        textRole: "label"
                        currentIndex: -1
                        displayText: currentIndex < 0 ? qsTr("Escolha uma associação") : currentText
                        popup.focus: false
                        Accessible.name: qsTr("Associação salva para revisar")
                        Accessible.onPressAction: {
                            if (!enabled || !visible || !controls.sessionOpen || !controls.savedOpen) return;
                            forceActiveFocus(Qt.OtherFocusReason);
                            if (popup.visible) popup.close(); else popup.open();
                        }
                        onActivated: index => controls.selectSaved(index)
                        onModelChanged: if (!controls.savedIntent) currentIndex = -1
                        onActiveFocusChanged: if (activeFocus) controls.revealSaved(this)
                        delegate: Controls.MenuItem {
                            id: savedOption
                            required property var modelData
                            required property int index
                            objectName: "savedContextOption" + index
                            width: savedSelector.width
                            text: modelData.label
                            Accessible.description: modelData.kind + " · " + modelData.entry.contextId + " · " + controls.profileName(modelData.entry.profileId)
                            contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: savedSelector.palette.text; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                        }
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: -Style.space.xxs
                            color: "transparent"
                            radius: Style.radius.control
                            border.width: savedSelector.activeFocus ? 2 : 0
                            border.color: savedSelector.palette.highlight
                        }
                    }
                    Controls.Label {
                        id: savedDetails
                        objectName: "savedContextDetails"
                        Layout.fillWidth: true
                        visible: Boolean(controls.savedIntent)
                        text: controls.savedIntent ? qsTr("%1\nIdentificador: %2\nPerfil: %3").arg(controls.savedIntent.label)
                            .arg(controls.savedIntent.entry.contextId).arg(controls.savedIntent.profileName) : ""
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                    }
                    ColumnLayout {
                        id: savedRecovery
                        Layout.fillWidth: true
                        visible: Boolean(controls.savedIntent)
                        spacing: Style.space.sm
                        Controls.Label {
                            objectName: "savedContextQuestion"
                            Layout.fillWidth: true
                            text: qsTr("Remover esta associação?")
                            font.bold: true
                            textFormat: Text.PlainText
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: qsTr("O perfil e o contexto não serão apagados. Se usada pelo automático, outras associações ou o padrão poderão valer ao terminar esta interação.")
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: qsTr("Para escolher outra associação, cancele esta confirmação.")
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            OrlaButton {
                                id: savedCancel
                                objectName: "savedContextCancel"
                                variant: "ghost"
                                text: qsTr("Cancelar")
                                onClicked: if (visible && controls.sessionOpen) controls.cancelSaved()
                                onActiveFocusChanged: if (activeFocus) controls.revealSaved(this)
                            }
                            OrlaButton {
                                id: savedRemove
                                objectName: "savedContextRemove"
                                Layout.fillWidth: true
                                variant: "secondary"
                                text: qsTr("Remover associação")
                                enabled: controls.savedCurrent(controls.savedIntent)
                                Accessible.description: savedDetails.text
                                onClicked: controls.removeSaved()
                                onActiveFocusChanged: if (activeFocus) controls.revealSaved(this)
                            }
                        }
                        Controls.Label {
                            objectName: "savedContextStatus"
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: controls.savedProblem
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            Accessible.role: Accessible.AlertMessage
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: activityColumn.implicitHeight + 20
            radius: Style.radius.card
            color: "transparent"
            border.width: 1
            border.color: activityBind.activeFocus || activityUnbind.activeFocus ? controls.palette.highlight : controls.palette.mid
            ColumnLayout {
                id: activityColumn
                anchors.fill: parent
                anchors.margins: 10
                spacing: 7
                Controls.Label { text: qsTr("Activity atual"); font.bold: true; textFormat: Text.PlainText }
                Controls.Label {
                    objectName: "activityContextName"
                    Layout.fillWidth: true
                    text: controls.contexts.snapshot.activity.status === "ready"
                        ? controls.contexts.snapshot.activity.name : qsTr("Activities não disponíveis nesta sessão")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    wrapMode: Text.WordWrap
                }
                Controls.Label {
                    Layout.fillWidth: true
                    readonly property var binding: controls.bindingFor("activity", controls.contexts.snapshot.activity.id)
                    text: binding ? qsTr("Associada a %1").arg(controls.profileName(binding.profileId)) : qsTr("Sem associação")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Controls.ComboBox {
                    id: activitySelector
                    objectName: "activityProfileSelector"
                    Layout.fillWidth: true
                    model: controls.choices
                    textRole: "name"
                    currentIndex: controls.currentChoice(controls.pendingActivityProfileId)
                    enabled: controls.contexts.snapshot.activity.status === "ready" && controls.choices.length > 0
                    Accessible.name: qsTr("Perfil para esta Activity")
                    onActivated: index => controls.chooseProfile("activity", controls.choices[index].id)
                    onActiveFocusChanged: if (activeFocus) controls.reveal(this)
                    delegate: Controls.ItemDelegate {
                        required property var modelData
                        width: activitySelector.width
                        text: modelData.name
                        contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: activitySelector.palette.text; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Button {
                        id: activityBind
                        objectName: "activityBind"
                        Layout.fillWidth: true
                        text: qsTr("Associar Activity atual")
                        enabled: controls.bindingsState.writable && controls.activityIntent
                            && controls.activityIntent.context.status === "ready"
                            && controls.currentChoice(controls.activityIntent.profileId) >= 0
                        onClicked: { controls.bindIntent("activity"); controls.restoreFocus(activityBind); }
                        onActiveFocusChanged: if (activeFocus) controls.reveal(this)
                    }
                    Controls.Button {
                        id: activityUnbind
                        objectName: "activityUnbind"
                        text: qsTr("Remover")
                        enabled: controls.bindingsState.writable && controls.activityIntent
                            && Boolean(controls.bindingFor("activity", controls.activityIntent.context.id))
                        Accessible.name: qsTr("Remover associação da Activity atual")
                        onClicked: { controls.unbindIntent("activity"); controls.restoreFocus(activityUnbind); }
                        onActiveFocusChanged: if (activeFocus) controls.reveal(this)
                    }
                }
                Controls.Label {
                    objectName: "staleActivityBindings"
                    Layout.fillWidth: true
                    visible: controls.staleCount("activity") > 0
                    text: qsTr("%1 associação antiga preservada por ID").arg(controls.staleCount("activity"))
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    opacity: 0.65
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            implicitHeight: desktopColumn.implicitHeight + 20
            radius: Style.radius.card
            color: "transparent"
            border.width: 1
            border.color: desktopBind.activeFocus || desktopUnbind.activeFocus ? controls.palette.highlight : controls.palette.mid
            ColumnLayout {
                id: desktopColumn
                anchors.fill: parent
                anchors.margins: 10
                spacing: 7
                Controls.Label { text: qsTr("Área de trabalho atual"); font.bold: true; textFormat: Text.PlainText }
                Controls.Label {
                    objectName: "desktopContextName"
                    Layout.fillWidth: true
                    text: controls.contexts.snapshot.desktop.status === "ready"
                        ? controls.contexts.snapshot.desktop.name : qsTr("Área de trabalho indisponível nesta sessão")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    wrapMode: Text.WordWrap
                }
                Controls.Label {
                    Layout.fillWidth: true
                    visible: controls.contexts.snapshot.outputName.length > 0
                    text: qsTr("Saída observada: %1").arg(controls.contexts.snapshot.outputName)
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Controls.Label {
                    Layout.fillWidth: true
                    readonly property var binding: controls.bindingFor("desktop", controls.contexts.snapshot.desktop.id)
                    text: binding ? qsTr("Associada a %1").arg(controls.profileName(binding.profileId)) : qsTr("Sem associação")
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
                Controls.ComboBox {
                    id: desktopSelector
                    objectName: "desktopProfileSelector"
                    Layout.fillWidth: true
                    model: controls.choices
                    textRole: "name"
                    currentIndex: controls.currentChoice(controls.pendingDesktopProfileId)
                    enabled: controls.contexts.snapshot.desktop.status === "ready" && controls.choices.length > 0
                    Accessible.name: qsTr("Perfil para esta área de trabalho")
                    onActivated: index => controls.chooseProfile("desktop", controls.choices[index].id)
                    onActiveFocusChanged: if (activeFocus) controls.reveal(this)
                    delegate: Controls.ItemDelegate {
                        required property var modelData
                        width: desktopSelector.width
                        text: modelData.name
                        contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: desktopSelector.palette.text; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Button {
                        id: desktopBind
                        objectName: "desktopBind"
                        Layout.fillWidth: true
                        text: qsTr("Associar área atual")
                        enabled: controls.bindingsState.writable && controls.desktopIntent
                            && controls.desktopIntent.context.status === "ready"
                            && controls.currentChoice(controls.desktopIntent.profileId) >= 0
                        onClicked: { controls.bindIntent("desktop"); controls.restoreFocus(desktopBind); }
                        onActiveFocusChanged: if (activeFocus) controls.reveal(this)
                    }
                    Controls.Button {
                        id: desktopUnbind
                        objectName: "desktopUnbind"
                        text: qsTr("Remover")
                        enabled: controls.bindingsState.writable && controls.desktopIntent
                            && Boolean(controls.bindingFor("desktop", controls.desktopIntent.context.id))
                        Accessible.name: qsTr("Remover associação da área atual")
                        onClicked: { controls.unbindIntent("desktop"); controls.restoreFocus(desktopUnbind); }
                        onActiveFocusChanged: if (activeFocus) controls.reveal(this)
                    }
                }
                Controls.Label {
                    objectName: "staleDesktopBindings"
                    Layout.fillWidth: true
                    visible: controls.staleCount("desktop") > 0
                    text: qsTr("%1 associação antiga preservada por ID").arg(controls.staleCount("desktop"))
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    opacity: 0.65
                }
            }
        }
        Controls.Label {
            objectName: "contextsStatus"
            Layout.fillWidth: true
            visible: text.length > 0
            text: controls.bindingsState.error
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.AlertMessage
        }
    }
}
