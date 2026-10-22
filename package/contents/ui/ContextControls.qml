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
    property string pendingActivityProfileId: ""
    property string pendingDesktopProfileId: ""
    property var activityIntent: null
    property var desktopIntent: null
    readonly property var choices: profiles.profiles
    contentWidth: availableWidth
    clip: true

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
