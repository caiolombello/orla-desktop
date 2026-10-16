import QtQuick
import QtQml
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Profiles.js" as Profiles
import "../code/Style.js" as Style

ColumnLayout {
    id: settings
    required property var configuration
    required property var resetTimer
    required property var appearance
    property var appearancePreset: null
    readonly property bool importing: appearancePreset !== null && appearancePreset.dirty
    required property var profiles
    required property var contexts
    property var desktopSwitch: null
    property var automation: null
    property var integrations: null
    required property var contextBindings
    readonly property bool contextsTabActive: tabs.currentIndex === 3
    signal appearanceCanceled()
    spacing: Style.space.sm
    function setPreference(key, value) {
        if (importing) return false;
        const patch = {};
        patch[key] = value;
        return profiles.commitPresentation(patch, profiles.activeProfileId, profiles.revision);
    }
    function setWidgetVisible(id, shown) {
        const widgets = Profiles.copy(profiles.effective.widgets);
        const widget = widgets.find(entry => entry.id === id);
        if (!widget) return false;
        widget.visible = shown;
        const scope = profiles.activeProfileId;
        if (!setPreference("widgets", widgets)) return false;
        restoreWidgetFocus(id, 0, scope);
        return true;
    }
    function moveWidget(id, delta) {
        const widgets = Profiles.copy(profiles.effective.widgets);
        const from = widgets.findIndex(widget => widget.id === id);
        const to = from + delta;
        if (from < 0 || to < 0 || to >= widgets.length) return false;
        const widget = widgets.splice(from, 1)[0];
        widgets.splice(to, 0, widget);
        const scope = profiles.activeProfileId;
        if (!setPreference("widgets", widgets)) return false;
        restoreWidgetFocus(id, delta, scope);
        return true;
    }
    function restoreWidgetFocus(id, delta, scope) {
        Qt.callLater(() => {
            if (!settings || !settings.profiles || !widgetRows || scope !== settings.profiles.activeProfileId) return;
            for (let index = 0; index < widgetRows.count; index++) {
                const row = widgetRows.itemAt(index);
                if (row && row.widgetId === id) {
                    const button = delta === 0 ? row.checkbox : delta < 0 ? row.upButton : row.downButton;
                    (button.enabled ? button : row.checkbox).forceActiveFocus(Qt.TabFocusReason);
                    break;
                }
            }
        });
    }
    property var widgetDrag: null
    property string widgetDropId: ""
    property bool widgetDropAfter: false
    property bool widgetDragging: false
    property int widgetFocusTicket: 0
    function cancelWidgetDrag() {
        widgetDrag = null;
        widgetDropId = "";
        widgetDragging = false;
    }
    function widgetDragValid(intent) {
        return intent !== null && widgetDrag === intent && profiles === intent.profiles
            && visible && appearance.editing && tabs.currentIndex === 1 && !importing && profiles.writable
            && profiles.activeProfileId !== "legacy" && profiles.activeProfileId === intent.scope
            && profiles.revision === intent.revision
            && JSON.stringify(profiles.effective.widgets) === intent.snapshot;
    }
    function beginWidgetDrag(id, handle, x, y) {
        cancelWidgetDrag();
        widgetFocusTicket++;
        if (!visible || !appearance.editing || tabs.currentIndex !== 1 || importing || !profiles.writable
                || profiles.activeProfileId === "legacy") return;
        const intent = {id: id, profiles: profiles, scope: profiles.activeProfileId,
            revision: profiles.revision, snapshot: JSON.stringify(profiles.effective.widgets),
            x: x, y: y, ticket: widgetFocusTicket};
        widgetDrag = intent;
        // Focusing may dispatch a profile change; it must not retarget this press.
        handle.forceActiveFocus(Qt.MouseFocusReason);
        if (!widgetDragValid(intent)) cancelWidgetDrag();
    }
    function updateWidgetDrag(handle, x, y) {
        const intent = widgetDrag;
        if (!widgetDragValid(intent)) { cancelWidgetDrag(); return; }
        const dx = x - intent.x, dy = y - intent.y;
        const threshold = Qt.styleHints.startDragDistance;
        if (!widgetDragging && dx * dx + dy * dy < threshold * threshold) return;
        widgetDragging = true;
        widgetDropId = "";
        const viewport = handle.mapToItem(widgetScroll, x, y);
        if (viewport.x < 0 || viewport.x >= widgetScroll.width
                || viewport.y < 0 || viewport.y >= widgetScroll.height) return;
        for (let index = 0; index < widgetRows.count; index++) {
            const row = widgetRows.itemAt(index);
            if (!row) continue;
            const header = row.header;
            const point = handle.mapToItem(header, x, y);
            if (point.x >= 0 && point.x < header.width && point.y >= 0 && point.y < header.height) {
                const top = header.mapToItem(widgetScroll, 0, 0).y;
                if (top < 0 || top + header.height > widgetScroll.height) return;
                widgetDropId = row.widgetId;
                widgetDropAfter = point.y >= header.height / 2;
                return;
            }
        }
    }
    function finishWidgetDrag(handle, x, y) {
        updateWidgetDrag(handle, x, y);
        const intent = widgetDrag;
        if (!widgetDragValid(intent) || !widgetDragging || widgetDropId === "") {
            cancelWidgetDrag(); return;
        }
        const widgets = JSON.parse(intent.snapshot);
        const from = widgets.findIndex(widget => widget.id === intent.id);
        let to = widgets.findIndex(widget => widget.id === widgetDropId);
        if (from < 0 || to < 0) { cancelWidgetDrag(); return; }
        if (widgetDropAfter) to++;
        if (from < to) to--;
        if (from === to) { cancelWidgetDrag(); return; }
        const widget = widgets.splice(from, 1)[0];
        widgets.splice(to, 0, widget);
        // Only the still-focused grip may hand focus to this stable item before delegates rebuild.
        const ownsFocus = handle.activeFocus;
        if (ownsFocus) widgetRowsList.forceActiveFocus(Qt.OtherFocusReason);
        const guard = () => settings.widgetDragValid(intent);
        let committed = false;
        try { committed = intent.profiles.commitPresentation({widgets: widgets}, intent.scope, intent.revision, guard); }
        finally { cancelWidgetDrag(); }
        if (!committed || !ownsFocus) return;
        const revision = intent.revision + 1;
        const expectedWidgets = JSON.stringify(widgets);
        Qt.callLater(() => {
            if (!widgetRowsList.activeFocus || settings.widgetFocusTicket !== intent.ticket
                    || !settings.visible || tabs.currentIndex !== 1 || settings.importing
                    || settings.profiles !== intent.profiles || !settings.profiles.writable
                    || settings.profiles.activeProfileId !== intent.scope || settings.profiles.revision !== revision
                    || JSON.stringify(settings.profiles.effective.widgets) !== expectedWidgets) return;
            for (let index = 0; index < widgetRows.count; index++) {
                const row = widgetRows.itemAt(index);
                if (row && row.widgetId === intent.id && row.dragHandle.enabled) {
                    row.dragHandle.forceActiveFocus(Qt.OtherFocusReason);
                    break;
                }
            }
        });
    }
    onImportingChanged: if (importing) cancelWidgetDrag()
    onProfilesChanged: { cancelWidgetDrag(); widgetFocusTicket++; }
    onAppearanceChanged: { cancelWidgetDrag(); widgetFocusTicket++; }
    onVisibleChanged: if (!visible) { cancelWidgetDrag(); widgetFocusTicket++; }
    Keys.onEscapePressed: event => {
        if (widgetDrag !== null) { cancelWidgetDrag(); widgetFocusTicket++; event.accepted = true; }
        else event.accepted = false;
    }
    Connections {
        target: settings.appearance
        function onEditingChanged() {
            // KDE may keep the popup visible through its exit animation.
            if (!settings.appearance.editing) { settings.cancelWidgetDrag(); settings.widgetFocusTicket++; }
        }
    }
    Connections {
        target: settings.profiles
        function onRevisionChanged() { if (settings.widgetDrag !== null) settings.cancelWidgetDrag(); }
        function onActiveProfileIdChanged() { settings.cancelWidgetDrag(); }
        function onWritableChanged() { if (!settings.profiles.writable) settings.cancelWidgetDrag(); }
    }
    function reveal(control) {
        const viewport = widgetScroll.contentItem;
        const point = control.mapToItem(viewport, 0, 0);
        const height = Math.min(control.height, viewport.height);
        if (point.y < 0) viewport.contentY += point.y;
        else if (point.y + height > viewport.height) viewport.contentY += point.y + height - viewport.height;
    }
    SegmentedTabs {
        id: tabs
        objectName: "settingsTabs"
        onCurrentIndexChanged: { settings.cancelWidgetDrag(); settings.widgetFocusTicket++; }
        Layout.fillWidth: true
        SegmentTab { text: qsTr("Aparência") }
        SegmentTab { text: qsTr("Widgets") }
        SegmentTab { text: qsTr("Perfis") }
        SegmentTab { objectName: "contextsTab"; text: qsTr("Contextos") }
    }
    Controls.Label {
        Layout.fillWidth: true
        readonly property string profileCaption: qsTr("Perfil: %1").arg(settings.profiles.activeProfileId === "legacy" ? qsTr("Preferências anteriores")
            : (settings.profiles.profiles.find(profile => profile.id === settings.profiles.activeProfileId)?.name || ""))
        text: settings.automation && settings.automation.enabled
            ? profileCaption + " · " + settings.automation.statusText : profileCaption
        Accessible.description: settings.automation && settings.automation.enabled ? settings.automation.statusText : ""
        textFormat: Text.PlainText
        font.pixelSize: Style.type.caption
        opacity: 0.72
        elide: Text.ElideRight
    }
    StackLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 470
        currentIndex: tabs.currentIndex
        AppearanceEditor { appearance: settings.appearance; preset: settings.appearancePreset; onProfilesRequested: tabs.currentIndex = 2; onCanceled: settings.appearanceCanceled() }
        Controls.ScrollView {
            id: widgetScroll
            objectName: "widgetScroll"
            Accessible.name: qsTr("Opções dos widgets")
            contentWidth: availableWidth
            clip: true
            Binding {
                target: widgetScroll.contentItem
                property: "Accessible.role"
                value: Accessible.Pane
                when: !!widgetScroll.contentItem
            }
            Binding {
                target: widgetScroll.contentItem
                property: "Accessible.name"
                value: qsTr("Conteúdo das opções de widgets")
                when: !!widgetScroll.contentItem
            }
            ColumnLayout {
                width: widgetScroll.availableWidth
                spacing: Style.space.sm
                Controls.Label { Layout.fillWidth: true; text: qsTr("Widgets e filtro de janelas são salvos imediatamente. Cancelar aparência não desfaz estas opções."); wrapMode: Text.WordWrap; textFormat: Text.PlainText }
                Controls.CheckBox { objectName: "filterDesktop"; enabled: settings.profiles.writable && !settings.importing; text: qsTr("Janelas apenas da área de trabalho atual"); checked: settings.profiles.effective.currentDesktopOnly; onToggled: settings.setPreference("currentDesktopOnly", checked); onActiveFocusChanged: if (activeFocus) settings.reveal(this) }
                Controls.CheckBox { objectName: "calendarEvents"; enabled: settings.profiles.writable && !settings.importing; text: qsTr("Eventos sincronizados pelo KDE"); checked: settings.profiles.effective.calendarEvents; onToggled: settings.setPreference("calendarEvents", checked); onActiveFocusChanged: if (activeFocus) settings.reveal(this) }
                Controls.CheckBox {
                    objectName: "showLocalToasts"
                    Layout.fillWidth: true
                    text: qsTr("Mostrar conclusões do Pomodoro dentro do dock (global)")
                    checked: Boolean(settings.configuration.showLocalToasts)
                    onToggled: settings.configuration.showLocalToasts = checked
                    onActiveFocusChanged: if (activeFocus) settings.reveal(this)
                }
                Controls.Label {
                    Layout.fillWidth: true
                    text: qsTr("Preferência global. Mostra apenas eventos próprios dentro do dock; as notificações do KDE continuam independentes.")
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                    opacity: 0.65
                }
                Controls.CheckBox {
                    objectName: "showAudioHud"
                    Layout.fillWidth: true
                    enabled: settings.profiles.writable && !settings.importing
                    text: qsTr("Mostrar confirmações de áudio dentro do dock")
                    checked: Boolean(settings.profiles.effective.showAudioHud)
                    onToggled: settings.setPreference("showAudioHud", checked)
                    onActiveFocusChanged: if (activeFocus) settings.reveal(this)
                }
                Controls.CheckBox {
                    objectName: "showControlCenter"
                    Layout.fillWidth: true
                    text: qsTr("Mostrar Central de Controle no dock (global)")
                    checked: Boolean(settings.configuration.showControlCenter)
                    onToggled: settings.configuration.showControlCenter = checked
                    onActiveFocusChanged: if (activeFocus) settings.reveal(this)
                }
                Controls.Label {
                    Layout.fillWidth: true
                    text: qsTr("Preferência global salva imediatamente. Não muda com o perfil e pode ser desativada aqui.")
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                    opacity: 0.65
                }
                SectionLabel { text: qsTr("Widgets") }
                Controls.Label { Layout.fillWidth: true; visible: settings.profiles.activeProfileId === "legacy"; text: qsTr("Crie/use um perfil para organizar os widgets. Aqui você pode mudar a visibilidade."); textFormat: Text.PlainText; wrapMode: Text.WordWrap }
                Controls.Label {
                    Layout.fillWidth: true
                    text: qsTr("Arraste pela alça e solte para salvar a ordem. As setas também movem os widgets.")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }
                Card {
                    Layout.fillWidth: true
                    padding: 0
                    ColumnLayout {
                        id: widgetRowsList
                        objectName: "widgetRowsList"
                        anchors.fill: parent
                        spacing: 0
                        Repeater {
                            id: widgetRows
                            model: settings.profiles.effective.widgets
                            ColumnLayout {
                                id: widgetRow
                                required property var modelData
                                required property int index
                                property string widgetId: modelData.id
                                Accessible.role: Accessible.Grouping
                                Accessible.name: qsTr("Widget: %1").arg(checkbox.text)
                                property alias upButton: up
                                property alias downButton: down
                                property alias checkbox: checkbox
                                property alias dragHandle: grip
                                property alias header: widgetHeader
                                Layout.fillWidth: true
                                spacing: 0
                                FormRow {
                                    id: widgetHeader
                                    last: index === widgetRows.count - 1 || moduleInfo.visible
                                    Rectangle {
                                        parent: widgetHeader
                                        objectName: "widgetDropIndicator" + modelData.id
                                        visible: settings.widgetDragging && settings.widgetDropId === modelData.id
                                        x: 0
                                        y: settings.widgetDropAfter ? parent.height - height : 0
                                        width: parent.width
                                        height: Style.space.xxs
                                        color: grip.palette.highlight
                                    }
                                    Controls.ToolButton {
                                        id: grip
                                        objectName: "widgetDrag" + modelData.id
                                        Layout.preferredWidth: Style.size.iconButton + Style.space.xs
                                        icon.name: "drag-handle-symbolic"
                                        Accessible.name: qsTr("Arrastar %1 para reordenar").arg(checkbox.text)
                                        Accessible.description: qsTr("Para mover pelo teclado, use os botões de subir e descer.")
                                        Controls.ToolTip.visible: hovered && enabled && !settings.widgetDragging
                                        Controls.ToolTip.text: qsTr("Arraste %1 ou use as setas.").arg(checkbox.text)
                                        enabled: settings.profiles.writable && !settings.importing && settings.profiles.activeProfileId !== "legacy"
                                        onActiveFocusChanged: if (activeFocus) settings.reveal(widgetRow)
                                        MouseArea {
                                            anchors.fill: parent
                                            preventStealing: true
                                            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                                            onPressed: mouse => settings.beginWidgetDrag(modelData.id, grip, mouse.x, mouse.y)
                                            onPositionChanged: mouse => { if (pressed) settings.updateWidgetDrag(grip, mouse.x, mouse.y); }
                                            onReleased: mouse => settings.finishWidgetDrag(grip, mouse.x, mouse.y)
                                            onCanceled: settings.cancelWidgetDrag()
                                        }
                                    }
                                    Controls.CheckBox {
                                        id: checkbox
                                        objectName: "widgetVisible" + modelData.id
                                        Layout.fillWidth: true
                                        text: modelData.id === "clock" ? qsTr("Relógio e calendário") : modelData.id === "pomodoro" ? qsTr("Pomodoro")
                                            : modelData.id === "music" ? qsTr("Música (MPRIS)") : modelData.id === "systemBattery" ? qsTr("Bateria do computador")
                                            : modelData.id === "quota" ? "QuotaLantern" : modelData.id === "peripherals" ? "PeriGauge" : "FalaTrace"
                                        enabled: settings.profiles.writable && !settings.importing
                                        checked: modelData.visible
                                        onToggled: settings.setWidgetVisible(modelData.id, checked)
                                        onActiveFocusChanged: if (activeFocus) settings.reveal(widgetRow)
                                    }
                                    Controls.ToolButton {
                                        id: up
                                        objectName: "widgetUp" + modelData.id
                                        Layout.preferredWidth: Style.size.iconButton + Style.space.xs
                                        text: "↑"
                                        Accessible.name: qsTr("Mover %1 para antes").arg(checkbox.text)
                                        enabled: settings.profiles.writable && !settings.importing && settings.profiles.activeProfileId !== "legacy" && index > 0
                                        onClicked: settings.moveWidget(modelData.id, -1)
                                        onActiveFocusChanged: if (activeFocus) settings.reveal(widgetRow)
                                    }
                                    Controls.ToolButton {
                                        id: down
                                        objectName: "widgetDown" + modelData.id
                                        Layout.preferredWidth: Style.size.iconButton + Style.space.xs
                                        text: "↓"
                                        Accessible.name: qsTr("Mover %1 para depois").arg(checkbox.text)
                                        enabled: settings.profiles.writable && !settings.importing && settings.profiles.activeProfileId !== "legacy" && index < 6
                                        onClicked: settings.moveWidget(modelData.id, 1)
                                        onActiveFocusChanged: if (activeFocus) settings.reveal(widgetRow)
                                    }
                                }
                                LocalModuleDetails {
                                    id: moduleInfo
                                    objectName: "moduleDetails" + modelData.id
                                    Layout.fillWidth: true
                                    widgetId: modelData.id
                                    shown: modelData.visible
                                    integrations: settings.integrations
                                    onRevealRequested: control => settings.reveal(control)
                                }
                                Rectangle {
                                    visible: moduleInfo.visible && index < widgetRows.count - 1
                                    Layout.fillWidth: true
                                    Layout.leftMargin: Style.space.md
                                    height: 1
                                    color: Style.alpha(widgetHeader.palette.windowText, Style.state.chip * 2)
                                }
                            }
                        }
                    }
                }
                Controls.Label { Layout.fillWidth: true; text: settings.profiles.error; visible: text.length > 0; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
                Controls.Label { Layout.fillWidth: true; text: qsTr("Para ocultar automaticamente: configure a visibilidade do painel no modo de edição do Plasma."); wrapMode: Text.WordWrap; opacity: 0.65 }
            }
        }
        ProfileControls {
            profiles: settings.profiles; appearance: settings.appearance; preset: settings.appearancePreset
            configuration: settings.configuration; contextBindings: settings.contextBindings; sessionOpen: settings.visible
        }
        ContextControls {
            objectName: "contextControls"
            desktopSwitch: settings.desktopSwitch
            automation: settings.automation
            contexts: settings.contexts
            bindingsState: settings.contextBindings
            configuration: settings.configuration
            sessionOpen: settings.visible && settings.appearance.editing
            profiles: settings.profiles
            active: settings.contextsTabActive
        }
    }
}
