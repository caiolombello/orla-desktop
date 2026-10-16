import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

Controls.ScrollView {
    id: controls
    objectName: "profileControls"
    required property var profiles
    required property var appearance
    required property var configuration
    required property var contextBindings
    property var preset: null
    property bool sessionOpen: true
    readonly property bool dirty: appearance.dirty || (preset !== null && preset.dirty)
    property string pendingId: profiles.activeProfileId
    readonly property var choices: [{id: "legacy", name: qsTr("Preferências anteriores")}].concat(profiles.profiles)
    readonly property var activeProfile: profiles.profiles.find(profile => profile.id === profiles.activeProfileId)
    property bool renameOpen: false
    property var renameOwner: null
    property string renameScope: ""
    property int renameRevision: -1
    property int renameEpoch: 0
    property string renameError: ""
    readonly property bool renameStale: renameOpen && (profiles !== renameOwner
        || profiles.activeProfileId !== renameScope || profiles.revision !== renameRevision)
    readonly property string renameProblem: !renameOpen ? ""
        : dirty ? qsTr("Aplique ou cancele a prévia na aba Aparência antes de renomear.")
        : renameStale ? qsTr("O perfil mudou. Cancele esta edição e abra Renomear novamente; seu rascunho foi mantido.")
        : !profiles.writable ? qsTr("Não é possível renomear enquanto a configuração estiver protegida.")
        : renameError
    property var removal: null
    property string removeDestination: ""
    property string removeError: ""
    property int removeEpoch: 0
    property int destinationEpoch: 0
    property int impactEpoch: 0
    property bool removing: false
    readonly property bool removeOpen: removal !== null
    readonly property string removeProblem: !removal ? ""
        : dirty ? qsTr("Aplique ou cancele a prévia na aba Aparência antes de remover.")
        : removal.impactError ? removal.impactError
        : !profiles.writable ? qsTr("A configuração está protegida. Cancele esta confirmação e confira os perfis.")
        : !removalCurrent(removal) ? qsTr("A configuração mudou. Cancele esta confirmação e abra Remover novamente.")
        : !removeDestination ? qsTr("Escolha o perfil que o dock usará após a remoção.") : removeError
    readonly property bool canRemove: Boolean(removal && !dirty && !renameOpen && !removal.impactError
        && removalCurrent(removal) && removal.choices.some(choice => choice.id === removeDestination))
    contentWidth: availableWidth
    clip: true
    function reveal(control) {
        const viewport = contentItem;
        const point = control.mapToItem(viewport, 0, 0);
        if (point.y < 0) viewport.contentY += point.y;
        else if (point.y + control.height > viewport.height) viewport.contentY += point.y + control.height - viewport.height;
    }
    function revealRename(control) {
        // Layout changes may settle later; scroll only for the control that still owns focus.
        const owner = controls;
        const epoch = renameEpoch;
        const target = renameOpen && control !== renameToggle ? renameEditor : renameToggle;
        Qt.callLater(() => {
            if (!Qt.isQtObject(owner) || !Qt.isQtObject(control) || !Qt.isQtObject(target)
                    || !owner.sessionOpen || !owner.visible || epoch !== owner.renameEpoch
                    || !control.visible || !control.activeFocus) return;
            const viewport = owner.contentItem;
            const point = target.mapToItem(viewport, 0, 0);
            const rim = Style.space.xs;
            const height = Math.min(target.height + rim * 2, viewport.height);
            if (point.y - rim < 0) viewport.contentY += point.y - rim;
            else if (point.y - rim + height > viewport.height)
                viewport.contentY += point.y - rim + height - viewport.height;
        });
    }
    function beginRename() {
        if (!sessionOpen || !visible || removeOpen || !profiles.writable || !activeProfile) return;
        renameEpoch++;
        renameOwner = profiles;
        renameScope = profiles.activeProfileId;
        renameRevision = profiles.revision;
        renameError = "";
        renameName.text = activeProfile.name;
        renameOpen = true;
        revealRename(renameToggle);
    }
    function resetRename() {
        renameEpoch++;
        renameOpen = false;
        renameOwner = null;
        renameScope = "";
        renameRevision = -1;
        renameError = "";
        renameName.clear();
    }
    function cancelRename(previousFocus = null) {
        const window = controls.Window.window;
        const focus = previousFocus || (window ? window.activeFocusItem : null);
        const owned = focus === renameName || focus === renameSave || focus === renameCancel;
        const epoch = renameEpoch;
        resetRename();
        if (sessionOpen && visible && renameEpoch === epoch + 1 && !renameOpen && owned
                && window && window.activeFocusItem === focus)
            renameToggle.forceActiveFocus(Qt.TabFocusReason);
    }
    function saveRename() {
        if (!sessionOpen || !visible || !renameOpen || !renameSave.visible || !renameSave.enabled
                || dirty || renameStale || !profiles.writable) return;
        const owner = renameOwner;
        const scope = renameScope;
        const revision = renameRevision;
        const epoch = renameEpoch;
        const draft = renameName.text;
        const focused = controls.Window.window ? controls.Window.window.activeFocusItem : null;
        const accepted = owner.rename(draft, scope, revision);
        // A synchronous writer can run other UI handlers. Never close a newer editor or reclaim its focus.
        if (!sessionOpen || !visible || !renameOpen || renameEpoch !== epoch || profiles !== owner
                || renameOwner !== owner || renameScope !== scope || renameRevision !== revision
                || renameName.text !== draft) return;
        if (accepted && owner.activeProfileId === scope && activeProfile && activeProfile.name === draft.trim()
                && (owner.revision === revision || owner.revision === revision + 1)) cancelRename(focused);
        else renameError = owner.error || qsTr("Não foi possível renomear. Cancele e abra a edição novamente.");
    }
    function sameImpact(intent) {
        return Boolean(configuration && contextBindings && configuration === intent.configuration && profiles === intent.profiles
            && contextBindings === intent.bindings && impactEpoch === intent.impactEpoch
            && profiles.configuration === configuration && contextBindings.configuration === configuration
            && contextBindings.profiles === profiles && contextBindings.writable
            && contextBindings.revision === intent.bindingRevision && contextBindings.savedJSON === intent.bindingRaw
            && configuration.autoContextDefaultProfile === intent.defaultId
            && configuration.autoContextEnabled === intent.enabled && configuration.autoContextPolicy === intent.policy);
    }
    function removalCurrent(intent) {
        return Boolean(intent && sameImpact(intent) && profiles.writable && profiles.activeProfileId === intent.scope
            && profiles.revision === intent.revision && profiles.savedJSON === intent.raw);
    }
    function beginRemoval() {
        if (!sessionOpen || !visible || renameOpen || !profiles.writable || !activeProfile) return;
        let count = 0, impactError = "";
        if (!configuration || !contextBindings || profiles.configuration !== configuration || contextBindings.configuration !== configuration
                || contextBindings.profiles !== profiles)
            impactError = qsTr("Não foi possível conferir os donos da configuração. Cancele e abra Remover novamente.");
        else if (!contextBindings.writable)
            impactError = qsTr("As associações estão inválidas ou indisponíveis. Confira Contextos antes de remover.");
        else count = contextBindings.bindings.activityBindings.concat(contextBindings.bindings.desktopBindings)
            .filter(binding => binding.profileId === profiles.activeProfileId).length;
        removeEpoch++;
        removeDestination = "";
        removeError = "";
        removal = {profiles: profiles, configuration: configuration, bindings: contextBindings,
            scope: profiles.activeProfileId, name: activeProfile.name, revision: profiles.revision, raw: profiles.savedJSON,
            bindingRevision: contextBindings ? contextBindings.revision : -1, bindingRaw: contextBindings ? contextBindings.savedJSON : undefined, impactEpoch: impactEpoch,
            defaultId: configuration ? configuration.autoContextDefaultProfile : undefined, enabled: configuration ? configuration.autoContextEnabled : undefined,
            policy: configuration ? configuration.autoContextPolicy : undefined, count: count, impactError: impactError,
            choices: [{id: "legacy", name: qsTr("Preferências anteriores")}]
                .concat(profiles.profiles.filter(profile => profile.id !== profiles.activeProfileId))};
        // A newly populated native ComboBox selects row zero; destination is always explicit.
        removeSelector.currentIndex = -1;
        revealRemoval(removeToggle);
    }
    function resetRemoval() { removeEpoch++; removal = null; removeDestination = ""; removeError = ""; }
    function cancelRemoval() {
        const window = controls.Window.window;
        const focused = window ? window.activeFocusItem : null;
        const owned = focused === removeSelector || focused === removeConfirm || focused === removeCancel;
        const epoch = removeEpoch;
        resetRemoval();
        if (sessionOpen && visible && removeEpoch === epoch + 1 && !removeOpen && owned
                && window.activeFocusItem === focused && removeToggle.enabled)
            removeToggle.forceActiveFocus(Qt.TabFocusReason);
    }
    function confirmRemoval() {
        if (removing || !sessionOpen || !appearance.editing || !visible || !removeConfirm.visible || !canRemove) return;
        const intent = removal, destination = removeDestination, epoch = removeEpoch, destinationTicket = destinationEpoch;
        const window = controls.Window.window;
        const focused = window ? window.activeFocusItem : null;
        const valid = () => Boolean(sessionOpen && appearance.editing && visible && removal === intent && removeEpoch === epoch
            && destinationEpoch === destinationTicket && removeDestination === destination && !dirty && !renameOpen && removalCurrent(intent));
        let accepted = false;
        removing = true;
        try { accepted = intent.profiles.removeCurrent(destination, intent.scope, intent.revision, valid) === true; }
        catch (_) { accepted = false; }
        finally { removing = false; }
        if (!sessionOpen || !visible || removal !== intent || removeEpoch !== epoch || destinationEpoch !== destinationTicket || removeDestination !== destination
                || profiles !== intent.profiles || configuration !== intent.configuration || contextBindings !== intent.bindings) return;
        if (accepted && sameImpact(intent) && profiles.revision === intent.revision + 1
                && profiles.activeProfileId === destination && !profiles.profiles.some(profile => profile.id === intent.scope)) {
            resetRemoval();
            if (sessionOpen && visible && removeEpoch === epoch + 1 && !removeOpen && controls.Window.window === window
                    && window && (window.activeFocusItem === focused || window.activeFocusItem === activeProfileCard)
                    && (focused === removeSelector || focused === removeConfirm || focused === removeCancel))
                selector.forceActiveFocus(Qt.TabFocusReason);
        } else {
            removeError = profiles.error || qsTr("Não foi possível remover. Confira o perfil ativo e abra a confirmação novamente.");
            if (window && window.activeFocusItem === focused && focused === removeConfirm && !removeConfirm.enabled)
                removeCancel.forceActiveFocus(Qt.TabFocusReason);
        }
    }
    function revealRemoval(control) {
        const owner = controls, epoch = removeEpoch;
        Qt.callLater(() => {
            if (!Qt.isQtObject(owner) || !Qt.isQtObject(control) || !owner.sessionOpen || !owner.visible
                    || owner.removeEpoch !== epoch || !control.visible || !control.activeFocus) return;
            const viewport = owner.contentItem, rim = Style.space.xs;
            const target = control === removeConfirm || control === removeCancel ? removeRecovery : control;
            const item = target.height + rim * 2 <= viewport.height ? target : control;
            const point = item.mapToItem(viewport, 0, 0);
            if (point.y - rim < 0) viewport.contentY += point.y - rim;
            else if (point.y + item.height + rim > viewport.height)
                viewport.contentY += point.y + item.height + rim - viewport.height;
        });
    }
    onSessionOpenChanged: if (!sessionOpen) { resetRename(); resetRemoval(); }
    onRemoveDestinationChanged: destinationEpoch++
    Keys.onEscapePressed: event => {
        if (removeOpen) {
            if (removeSelector.popup.visible) removeSelector.popup.close(); else cancelRemoval();
            event.accepted = true;
        } else if (renameOpen) { cancelRename(); event.accepted = true; }
        else event.accepted = false;
    }
    onConfigurationChanged: impactEpoch++
    onContextBindingsChanged: impactEpoch++
    onProfilesChanged: impactEpoch++
    Connections {
        target: controls.configuration || null
        function onAutoContextDefaultProfileChanged() { controls.impactEpoch++; }
        function onAutoContextEnabledChanged() { controls.impactEpoch++; }
        function onAutoContextPolicyChanged() { controls.impactEpoch++; }
    }
    Connections { target: controls.profiles; function onConfigurationChanged() { controls.impactEpoch++; } }
    Connections {
        target: controls.contextBindings || null
        function onConfigurationChanged() { controls.impactEpoch++; }
        function onProfilesChanged() { controls.impactEpoch++; }
    }
    Connections { target: controls.profiles; function onActiveProfileIdChanged() { controls.pendingId = controls.profiles.activeProfileId; } }
    Connections {
        target: controls.contentItem
        function onContentHeightChanged() {
            if (controls.renameOpen)
                for (const control of [renameName, renameSave, renameCancel])
                    if (control.activeFocus) controls.revealRename(control);
            if (controls.removeOpen)
                for (const control of [removeToggle, removeSelector, removeConfirm, removeCancel])
                    if (control.activeFocus) controls.revealRemoval(control);
        }
    }
    ColumnLayout {
        width: controls.availableWidth
        spacing: 8
        Controls.Label { Layout.fillWidth: true; text: qsTr("Perfis guardam apps fixados, aparência e widgets deste dock. O Pomodoro continua compartilhado."); textFormat: Text.PlainText; wrapMode: Text.WordWrap }
        Controls.Label { Layout.fillWidth: true; visible: !controls.profiles.initialized; text: qsTr("Criar os perfis Trabalho, Pessoal e Jogos copia suas preferências salvas e mantém o dock atual."); textFormat: Text.PlainText; wrapMode: Text.WordWrap }
        Controls.Button {
            objectName: "profileInitialize"
            Layout.fillWidth: true
            visible: !controls.profiles.initialized
            text: qsTr("Criar Trabalho, Pessoal e Jogos")
            enabled: controls.profiles.writable && !controls.dirty
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onClicked: controls.profiles.initializeDefaults(controls.profiles.activeProfileId, controls.profiles.revision)
        }
        Controls.Label { text: qsTr("Escolher perfil"); font.bold: true }
        Controls.ComboBox {
            id: selector
            objectName: "profileSelector"
            Layout.fillWidth: true
            model: controls.choices
            textRole: "name"
            currentIndex: controls.choices.findIndex(choice => choice.id === controls.pendingId)
            Accessible.name: qsTr("Perfil a usar")
            Accessible.onPressAction: {
                if (!selector.enabled || !selector.visible) return;
                selector.forceActiveFocus(Qt.OtherFocusReason);
                if (selector.popup.visible) selector.popup.close();
                else selector.popup.open();
            }
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onActivated: index => controls.pendingId = controls.choices[index].id
            // Keep the native style TextInput; ComboBox display text is literal.
            delegate: Controls.ItemDelegate {
                id: profileOption
                required property var modelData
                width: selector.width
                text: modelData.name
                Accessible.onPressAction: {
                    if (profileOption.enabled && profileOption.visible && selector.popup.visible)
                        profileOption.click();
                }
                contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: selector.palette.text; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
            }
        }
        Controls.Button {
            objectName: "profileUse"
            Layout.fillWidth: true
            text: qsTr("Usar perfil")
            enabled: controls.profiles.writable && !controls.dirty && controls.pendingId !== controls.profiles.activeProfileId
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onClicked: controls.profiles.select(controls.pendingId, controls.profiles.activeProfileId, controls.profiles.revision)
        }
        Card {
            id: activeProfileCard
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: Style.space.sm
                SectionLabel { text: qsTr("Perfil ativo") }
                Controls.Label {
                    objectName: "profileActiveName"
                    Layout.fillWidth: true
                    text: controls.activeProfile ? controls.activeProfile.name : qsTr("Preferências anteriores")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Style.space.sm
                    OrlaButton {
                        id: renameToggle
                        objectName: "profileRenameToggle"
                        text: qsTr("Renomear")
                        variant: "ghost"
                        checkable: true
                        checked: controls.renameOpen
                        enabled: Boolean(controls.activeProfile) && controls.profiles.writable && !controls.removeOpen
                        Accessible.name: qsTr("Renomear perfil ativo")
                        onClicked: {
                            if (!enabled || !visible || !controls.sessionOpen) return;
                            if (controls.renameOpen) controls.cancelRename(); else controls.beginRename();
                        }
                        onActiveFocusChanged: if (activeFocus) controls.revealRename(this)
                    }
                    OrlaButton {
                        id: removeToggle
                        objectName: "profileRemoveToggle"
                        text: qsTr("Remover…")
                        variant: "ghost"
                        checkable: true
                        checked: controls.removeOpen
                        enabled: Boolean(controls.activeProfile) && controls.profiles.writable && !controls.renameOpen
                        Accessible.name: qsTr("Preparar remoção do perfil ativo")
                        onClicked: {
                            if (!enabled || !visible || !controls.sessionOpen) return;
                            if (controls.removeOpen) controls.cancelRemoval(); else controls.beginRemoval();
                        }
                        onActiveFocusChanged: if (activeFocus) controls.revealRemoval(this)
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Style.space.sm
                    visible: controls.removeOpen
                    onHeightChanged: {
                        for (const control of [removeToggle, removeSelector, removeConfirm, removeCancel])
                            if (control.activeFocus) controls.revealRemoval(control);
                    }
                    Controls.Label {
                        objectName: "profileRemoveQuestion"
                        Layout.fillWidth: true
                        text: controls.removal ? qsTr("Remover “%1”?").arg(controls.removal.name) : ""
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        font.bold: true
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: qsTr("Remove as preferências salvas deste perfil, sem Desfazer. Apps instalados e Pomodoro são preservados.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        visible: controls.removal && controls.removal.choices.length === 1
                        text: qsTr("Este é o último perfil. Escolha Preferências anteriores para continuar.")
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                    }
                    Controls.Label { text: qsTr("Após remover, usar"); textFormat: Text.PlainText }
                    Controls.ComboBox {
                        id: removeSelector
                        objectName: "profileRemoveDestination"
                        Layout.fillWidth: true
                        model: controls.removal ? controls.removal.choices : []
                        textRole: "name"
                        popup.focus: false
                        currentIndex: -1
                        displayText: currentIndex < 0 ? qsTr("Escolha o perfil de destino") : currentText
                        Accessible.name: qsTr("Perfil a usar após remover")
                        Accessible.onPressAction: {
                            if (!enabled || !visible || !controls.sessionOpen) return;
                            forceActiveFocus(Qt.OtherFocusReason);
                            if (popup.visible) popup.close(); else popup.open();
                        }
                        onActivated: index => {
                            if (enabled && visible && controls.removal && index >= 0 && index < controls.removal.choices.length)
                                controls.removeDestination = controls.removal.choices[index].id;
                        }
                        onActiveFocusChanged: if (activeFocus) controls.revealRemoval(this)
                        Keys.onEscapePressed: event => {
                            if (popup.visible) popup.close(); else controls.cancelRemoval();
                            event.accepted = true;
                        }
                        delegate: Controls.ItemDelegate {
                            id: removeOption
                            required property var modelData
                            objectName: "profileRemoveOption-" + modelData.id
                            width: removeSelector.width
                            text: modelData.name
                            Accessible.onPressAction: {
                                if (enabled && visible && removeSelector.popup.visible) click();
                            }
                            contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: removeSelector.palette.text; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
                        }
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: -Style.space.xxs
                            color: "transparent"
                            radius: Style.radius.control
                            border.width: removeSelector.activeFocus ? 2 : 0
                            border.color: removeSelector.palette.highlight
                        }
                    }
                    ColumnLayout {
                        id: removeRecovery
                        Layout.fillWidth: true
                        spacing: Style.space.sm
                        Controls.Label {
                            id: removeImpact
                            objectName: "profileRemoveImpact"
                            Layout.fillWidth: true
                            text: !controls.removal || controls.removal.impactError ? ""
                                : qsTr("%1 associações de Activity/área serão mantidas por ID e ficarão indisponíveis. Revise em Contextos.").arg(controls.removal.count)
                                    + (controls.removal.defaultId === controls.removal.scope
                                        ? (controls.removal.enabled ? qsTr("\nÉ o padrão do automático ligado. A alternância aguardará um novo padrão válido.")
                                            : qsTr("\nÉ o padrão do automático desligado. Escolha um novo padrão antes de ativá-lo.")) : "")
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Style.space.sm
                            OrlaButton {
                                id: removeCancel
                                objectName: "profileRemoveCancel"
                                variant: "ghost"
                                text: qsTr("Cancelar")
                                Accessible.name: qsTr("Cancelar remoção do perfil")
                                onClicked: if (visible && controls.sessionOpen) controls.cancelRemoval()
                                onActiveFocusChanged: if (activeFocus) controls.revealRemoval(this)
                                Keys.onEscapePressed: event => { controls.cancelRemoval(); event.accepted = true; }
                            }
                            OrlaButton {
                                id: removeConfirm
                                objectName: "profileRemoveConfirm"
                                text: qsTr("Remover perfil")
                                enabled: controls.canRemove
                                Accessible.name: controls.removal ? qsTr("Confirmar remoção de %1").arg(controls.removal.name) : qsTr("Confirmar remoção")
                                Accessible.description: removeImpact.text + (removeSelector.currentIndex < 0 ? "" : qsTr(" Após remover, usar %1.").arg(removeSelector.currentText))
                                onClicked: controls.confirmRemoval()
                                onEnabledChanged: {
                                    const window = controls.Window.window;
                                    if (!enabled && !controls.removing && controls.removeOpen && controls.visible
                                            && window && window.activeFocusItem === removeConfirm)
                                        removeCancel.forceActiveFocus(Qt.TabFocusReason);
                                }
                                onActiveFocusChanged: if (activeFocus) controls.revealRemoval(this)
                                Keys.onEscapePressed: event => { controls.cancelRemoval(); event.accepted = true; }
                            }
                        }
                        Controls.Label {
                            objectName: "profileRemoveStatus"
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: controls.removeProblem
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            Accessible.role: Accessible.AlertMessage
                        }
                    }
                }
                ColumnLayout {
                    id: renameEditor
                    objectName: "profileRenameEditor"
                    Layout.fillWidth: true
                    spacing: Style.space.sm
                    visible: controls.renameOpen
                    onHeightChanged: {
                        for (const control of [renameName, renameSave, renameCancel])
                            if (control.activeFocus) controls.revealRename(control);
                    }
                    Controls.TextField {
                        id: renameName
                        objectName: "profileRenameName"
                        Layout.fillWidth: true
                        maximumLength: 48
                        Accessible.name: qsTr("Novo nome do perfil ativo")
                        onActiveFocusChanged: if (activeFocus) controls.revealRename(this)
                        Keys.onEscapePressed: event => { controls.cancelRename(); event.accepted = true; }
                        Rectangle {
                            objectName: "profileRenameFocusRing"
                            anchors.fill: parent
                            anchors.margins: -Style.space.xxs
                            color: "transparent"
                            radius: Style.radius.control
                            border.width: renameName.activeFocus ? 2 : 0
                            border.color: renameName.palette.highlight
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Style.space.sm
                        OrlaButton {
                            id: renameSave
                            objectName: "profileRenameSave"
                            text: qsTr("Renomear")
                            enabled: controls.profiles.writable && !controls.dirty && !controls.renameStale
                            onClicked: controls.saveRename()
                            onActiveFocusChanged: if (activeFocus) controls.revealRename(this)
                            Keys.onEscapePressed: event => { controls.cancelRename(); event.accepted = true; }
                        }
                        OrlaButton {
                            id: renameCancel
                            objectName: "profileRenameCancel"
                            text: qsTr("Cancelar")
                            variant: "ghost"
                            onClicked: if (visible && controls.sessionOpen) controls.cancelRename()
                            onActiveFocusChanged: if (activeFocus) controls.revealRename(this)
                            Keys.onEscapePressed: event => { controls.cancelRename(); event.accepted = true; }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    Controls.Label {
                        objectName: "profileRenameStatus"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: controls.renameProblem
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        Accessible.role: Accessible.AlertMessage
                    }
                }
            }
        }
        Controls.Label { text: qsTr("Novo perfil a partir do que está salvo"); Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText; font.bold: true }
        Controls.TextField {
            id: name
            objectName: "profileName"
            Layout.fillWidth: true
            maximumLength: 48
            placeholderText: qsTr("Nome do perfil")
            Accessible.name: qsTr("Nome do novo perfil")
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
        }
        Controls.Button {
            objectName: "profileCreate"
            Layout.fillWidth: true
            text: qsTr("Criar e usar")
            enabled: controls.profiles.writable && !controls.dirty && name.text.trim().length > 0
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onClicked: if (controls.profiles.create(name.text, controls.profiles.activeProfileId, controls.profiles.revision)) name.clear()
        }
        Controls.Label {
            objectName: "profileStatus"
            Layout.fillWidth: true
            visible: text.length > 0
            text: controls.dirty ? qsTr("Aplique ou cancele a prévia na aba Aparência antes de trocar, criar ou renomear um perfil.") : controls.profiles.error || controls.profiles.message
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.AlertMessage
        }
    }
}
