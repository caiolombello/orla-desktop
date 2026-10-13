import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Profiles.js" as Profiles
import "../code/Style.js" as Style

ColumnLayout {
    id: settings
    required property var configuration
    required property var resetTimer
    required property var appearance
    required property var profiles
    required property var contexts
    property var desktopSwitch: null
    required property var contextBindings
    readonly property bool contextsTabActive: tabs.currentIndex === 3
    signal appearanceCanceled()
    spacing: Style.space.sm
    function setPreference(key, value) {
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
    function reveal(control) {
        const viewport = widgetScroll.contentItem;
        const point = control.mapToItem(viewport, 0, 0);
        if (point.y < 0) viewport.contentY += point.y;
        else if (point.y + control.height > viewport.height) viewport.contentY += point.y + control.height - viewport.height;
    }
    SegmentedTabs {
        id: tabs
        objectName: "settingsTabs"
        Layout.fillWidth: true
        SegmentTab { text: qsTr("Aparência") }
        SegmentTab { text: qsTr("Widgets") }
        SegmentTab { text: qsTr("Perfis") }
        SegmentTab { objectName: "contextsTab"; text: qsTr("Contextos") }
    }
    Controls.Label {
        Layout.fillWidth: true
        text: qsTr("Perfil: %1").arg(settings.profiles.activeProfileId === "legacy" ? qsTr("Preferências anteriores")
            : (settings.profiles.profiles.find(profile => profile.id === settings.profiles.activeProfileId)?.name || ""))
        textFormat: Text.PlainText
        font.pixelSize: Style.type.caption
        opacity: 0.72
        elide: Text.ElideRight
    }
    StackLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 470
        currentIndex: tabs.currentIndex
        AppearanceEditor { appearance: settings.appearance; onCanceled: settings.appearanceCanceled() }
        Controls.ScrollView {
            id: widgetScroll
            contentWidth: availableWidth
            clip: true
            ColumnLayout {
                width: widgetScroll.availableWidth
                spacing: Style.space.sm
                Controls.Label { Layout.fillWidth: true; text: qsTr("Widgets e filtro de janelas são salvos imediatamente. Cancelar aparência não desfaz estas opções."); wrapMode: Text.WordWrap; textFormat: Text.PlainText }
                Controls.CheckBox { objectName: "filterDesktop"; enabled: settings.profiles.writable; text: qsTr("Janelas apenas da área de trabalho atual"); checked: settings.profiles.effective.currentDesktopOnly; onToggled: settings.setPreference("currentDesktopOnly", checked); onActiveFocusChanged: if (activeFocus) settings.reveal(this) }
                Controls.CheckBox { objectName: "calendarEvents"; enabled: settings.profiles.writable; text: qsTr("Eventos sincronizados pelo KDE"); checked: settings.profiles.effective.calendarEvents; onToggled: settings.setPreference("calendarEvents", checked); onActiveFocusChanged: if (activeFocus) settings.reveal(this) }
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
                    enabled: settings.profiles.writable
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
                Card {
                    Layout.fillWidth: true
                    padding: 0
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0
                        Repeater {
                            id: widgetRows
                            model: settings.profiles.effective.widgets
                            FormRow {
                                required property var modelData
                                required property int index
                                property string widgetId: modelData.id
                                property alias upButton: up
                                property alias downButton: down
                                property alias checkbox: checkbox
                                last: index === widgetRows.count - 1
                                Controls.CheckBox {
                                    id: checkbox
                                    objectName: "widgetVisible" + modelData.id
                                    Layout.fillWidth: true
                                    text: modelData.id === "clock" ? qsTr("Relógio e calendário") : modelData.id === "pomodoro" ? qsTr("Pomodoro")
                                        : modelData.id === "music" ? qsTr("Música (MPRIS)") : modelData.id === "systemBattery" ? qsTr("Bateria do computador")
                                        : modelData.id === "quota" ? "QuotaLantern" : modelData.id === "peripherals" ? "PeriGauge" : "FalaTrace"
                                    enabled: settings.profiles.writable
                                    checked: modelData.visible
                                    onToggled: settings.setWidgetVisible(modelData.id, checked)
                                    onActiveFocusChanged: if (activeFocus) settings.reveal(this)
                                }
                                Controls.ToolButton {
                                    id: up
                                    objectName: "widgetUp" + modelData.id
                                    Layout.preferredWidth: Style.size.iconButton + Style.space.xs
                                    text: "↑"
                                    Accessible.name: qsTr("Mover %1 para antes").arg(checkbox.text)
                                    enabled: settings.profiles.writable && settings.profiles.activeProfileId !== "legacy" && index > 0
                                    onClicked: settings.moveWidget(modelData.id, -1)
                                    onActiveFocusChanged: if (activeFocus) settings.reveal(this)
                                }
                                Controls.ToolButton {
                                    id: down
                                    objectName: "widgetDown" + modelData.id
                                    Layout.preferredWidth: Style.size.iconButton + Style.space.xs
                                    text: "↓"
                                    Accessible.name: qsTr("Mover %1 para depois").arg(checkbox.text)
                                    enabled: settings.profiles.writable && settings.profiles.activeProfileId !== "legacy" && index < 6
                                    onClicked: settings.moveWidget(modelData.id, 1)
                                    onActiveFocusChanged: if (activeFocus) settings.reveal(this)
                                }
                            }
                        }
                    }
                }
                Controls.Label { Layout.fillWidth: true; text: settings.profiles.error; visible: text.length > 0; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
                Controls.Label { Layout.fillWidth: true; text: qsTr("Para ocultar automaticamente: configure a visibilidade do painel no modo de edição do Plasma."); wrapMode: Text.WordWrap; opacity: 0.65 }
            }
        }
        ProfileControls { profiles: settings.profiles; appearance: settings.appearance }
        ContextControls {
            objectName: "contextControls"
            desktopSwitch: settings.desktopSwitch
            contexts: settings.contexts
            bindingsState: settings.contextBindings
            profiles: settings.profiles
            active: settings.contextsTabActive
        }
    }
}
