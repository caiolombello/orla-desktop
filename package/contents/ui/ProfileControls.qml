import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

Controls.ScrollView {
    id: controls
    objectName: "profileControls"
    required property var profiles
    required property var appearance
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
        if (!sessionOpen || !visible || !profiles.writable || !activeProfile) return;
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
    onSessionOpenChanged: if (!sessionOpen) resetRename()
    Connections { target: controls.profiles; function onActiveProfileIdChanged() { controls.pendingId = controls.profiles.activeProfileId; } }
    Connections {
        target: controls.contentItem
        function onContentHeightChanged() {
            if (controls.renameOpen)
                for (const control of [renameName, renameSave, renameCancel])
                    if (control.activeFocus) controls.revealRename(control);
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
                OrlaButton {
                    id: renameToggle
                    objectName: "profileRenameToggle"
                    text: qsTr("Renomear")
                    variant: "ghost"
                    checkable: true
                    checked: controls.renameOpen
                    enabled: Boolean(controls.activeProfile) && controls.profiles.writable
                    Accessible.name: qsTr("Renomear perfil ativo")
                    Accessible.onPressAction: if (enabled && visible && controls.sessionOpen) click()
                    onClicked: {
                        if (!enabled || !visible || !controls.sessionOpen) return;
                        if (controls.renameOpen) controls.cancelRename(); else controls.beginRename();
                    }
                    onActiveFocusChanged: if (activeFocus) controls.revealRename(this)
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
                            Accessible.onPressAction: if (enabled && visible) click()
                            onActiveFocusChanged: if (activeFocus) controls.revealRename(this)
                            Keys.onEscapePressed: event => { controls.cancelRename(); event.accepted = true; }
                        }
                        OrlaButton {
                            id: renameCancel
                            objectName: "profileRenameCancel"
                            text: qsTr("Cancelar")
                            variant: "ghost"
                            onClicked: if (visible && controls.sessionOpen) controls.cancelRename()
                            Accessible.onPressAction: if (enabled && visible) click()
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
