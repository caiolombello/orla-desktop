import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import org.kde.kirigami as Kirigami
import org.kde.plasma.workspace.calendar as PlasmaCalendar
import "../code/Style.js" as Style

ColumnLayout {
    id: root
    required property var dock
    property bool active: false
    property var fixtureEvents: null
    // Test-only: tomorrow's events when the selected date is today.
    property var fixtureTomorrowEvents: null
    // Test-only nullable override. null always inspects the installed metadata model.
    property var pimPluginMetadataAvailableOverride: null
    property bool usePimEvents: dock.configuration && dock.configuration.calendarEvents !== undefined
        ? dock.configuration.calendarEvents : true
    property alias selectedDate: monthView.currentDate
    readonly property alias enabledPlugins: plugins.enabledPlugins
    readonly property bool pimPluginMetadataAvailable: pluginMetadataAvailable("pimevents")
    readonly property string providerState: !usePimEvents ? "disabled"
        : agendaEvents.length > 0 ? "events-present"
        : !pimPluginMetadataAvailable ? "plugin-metadata-missing" : "no-events-observed"
    property var agendaEvents: []
    // Like the macOS Calendar widget: what comes tomorrow, shown while today is selected.
    property var tomorrowEvents: []
    readonly property bool selectedIsToday: sameDay(selectedDate, dock.now !== undefined ? dock.now : new Date())
    spacing: 8
    Kirigami.Theme.inherit: false
    Kirigami.Theme.colorSet: Kirigami.Theme.Window
    Kirigami.Theme.textColor: root.dock.foreground
    Kirigami.Theme.disabledTextColor: root.dock.muted
    Kirigami.Theme.backgroundColor: root.dock.background

    function pluginMetadataAvailable(pluginId) {
        if (pimPluginMetadataAvailableOverride !== null)
            return pimPluginMetadataAvailableOverride === true;
        const metadata = plugins.model;
        if (!metadata) return false;
        for (let row = 0; row < metadata.rowCount(); row++) {
            if (String(metadata.get(row, "pluginId")) === pluginId) return true;
        }
        return false;
    }
    function sameDay(a, b) {
        return a instanceof Date && b instanceof Date && !isNaN(a.getTime()) && !isNaN(b.getTime())
            && a.toDateString() === b.toDateString();
    }
    function refreshAgenda() {
        if (!monthView) return;
        agendaEvents = fixtureEvents !== null ? fixtureEvents
            : active && usePimEvents ? monthView.daysModel.eventsForDate(monthView.currentDate) : [];
        let tomorrow = [];
        if (selectedIsToday) {
            const next = new Date(monthView.currentDate);
            next.setDate(next.getDate() + 1);
            tomorrow = fixtureTomorrowEvents !== null ? fixtureTomorrowEvents
                : active && usePimEvents ? monthView.daysModel.eventsForDate(next) : [];
        }
        tomorrowEvents = tomorrow;
    }
    // The calendar's own color, as macOS marks events; the accent when it has none.
    function eventColor(event) {
        const value = String(event && event.eventColor || "");
        return /^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(value) ? value : root.dock.accent;
    }
    function dayTitle() {
        if (selectedIsToday) return qsTr("Hoje");
        return Qt.formatDate(root.selectedDate, Qt.DefaultLocaleLongDate);
    }
    function applyMonthLabelTheme(item) {
        // Plasma 6.7 DayDelegate switches disabled dates to the system palette;
        // bind every MonthView text item back to this dock's foreground.
        if (item.text !== undefined && item.color !== undefined) {
            item.Kirigami.Theme.inherit = false;
            item.Kirigami.Theme.textColor = Qt.binding(() => root.dock.foreground);
            item.Kirigami.Theme.disabledTextColor = Qt.binding(() => root.dock.foreground);
            item.color = Qt.binding(() => root.dock.foreground);
        }
        for (let child of item.children) applyMonthLabelTheme(child);
    }
    function applyMonthNavigationTheme() {
        const header = monthView.viewHeader;
        // The macOS calendar has no Days/Months/Years tabs; the arrows and Today remain.
        if (header.tabBar) header.tabBar.visible = false;
        for (let button of [header.previousButton, header.nextButton]) {
            if (!button) continue;
            button.Kirigami.Theme.inherit = false;
            button.Kirigami.Theme.textColor = root.dock.foreground;
            button.Kirigami.Theme.buttonTextColor = root.dock.foreground;
            button.icon.name = "";
            button.icon.source = "";
            button.display = Templates.AbstractButton.TextOnly;
            applyNavigationGlyph(button.contentItem,
                button === header.previousButton ? "‹" : "›");
        }
    }
    function applyNavigationGlyph(item, glyph) {
        if (item.text !== undefined && item.color !== undefined) {
            item.text = glyph;
            item.color = Qt.binding(() => root.dock.foreground);
            item.font.pixelSize = 18;
            return true;
        }
        for (let child of item.children) {
            if (applyNavigationGlyph(child, glyph)) return true;
        }
        return false;
    }
    function scheduleMonthLabelTheme() {
        monthThemeTimer.remainingPasses = 12;
        monthThemeTimer.restart();
    }
    function previousMonth() { monthView.showMonthView(); monthView.previousView(); }
    function nextMonth() { monthView.showMonthView(); monthView.nextView(); }
    function today() { monthView.resetToToday(); }
    function eventTime(event) {
        if (event.isAllDay) return qsTr("Dia inteiro");
        const start = new Date(event.startDateTime);
        const end = new Date(event.endDateTime);
        if (isNaN(start.getTime())) return qsTr("Horário não disponível");
        if (isNaN(end.getTime())) return Qt.formatTime(start, "HH:mm");
        const endLabel = start.toDateString() === end.toDateString()
            ? Qt.formatTime(end, "HH:mm") : end.toLocaleString(Qt.locale(), "d MMM, HH:mm");
        return Qt.formatTime(start, "HH:mm") + " – " + endLabel;
    }
    onFixtureEventsChanged: refreshAgenda()
    onFixtureTomorrowEventsChanged: refreshAgenda()
    onSelectedIsTodayChanged: refreshAgenda()
    onActiveChanged: refreshAgenda()
    onUsePimEventsChanged: refreshAgenda()
    Component.onCompleted: {
        refreshAgenda();
        scheduleMonthLabelTheme();
    }

    PlasmaCalendar.EventPluginsManager {
        id: plugins
        enabledPlugins: root.active && root.usePimEvents && root.fixtureEvents === null
            ? ["pimevents"] : []
    }
    Timer {
        id: monthThemeTimer
        property int remainingPasses: 0
        interval: 25
        repeat: true
        onTriggered: {
            root.applyMonthNavigationTheme();
            root.applyMonthLabelTheme(monthView);
            remainingPasses--;
            if (remainingPasses <= 0) stop();
        }
    }
    Controls.Control {
        id: calendarPalette
        Layout.fillWidth: true
        Layout.preferredHeight: 290
        padding: 0
        palette.window: root.dock.background
        palette.windowText: root.dock.foreground
        palette.text: root.dock.foreground
        palette.buttonText: root.dock.foreground
        palette.disabled.windowText: root.dock.muted
        palette.disabled.text: root.dock.muted
        palette.disabled.buttonText: root.dock.muted
        Kirigami.Theme.inherit: false
        Kirigami.Theme.colorSet: Kirigami.Theme.Window
        Kirigami.Theme.textColor: root.dock.foreground
        Kirigami.Theme.disabledTextColor: root.dock.muted
        Kirigami.Theme.backgroundColor: root.dock.background
        contentItem: PlasmaCalendar.MonthView {
            id: monthView
            objectName: "calendarMonthView"
            today: root.dock.now !== undefined ? root.dock.now : new Date()
            eventPluginsManager: plugins
            onCurrentDateChanged: {
                root.refreshAgenda();
                root.scheduleMonthLabelTheme();
            }
            onCurrentIndexChanged: root.scheduleMonthLabelTheme()
            onSelectedMonthChanged: root.scheduleMonthLabelTheme()
            onSelectedYearChanged: root.scheduleMonthLabelTheme()
        }
    }
    Connections {
        target: root.dock
        ignoreUnknownSignals: true
        function onForegroundChanged() { root.scheduleMonthLabelTheme(); }
    }
    Connections {
        target: monthView.daysModel
        function onAgendaUpdated(updatedDate) { root.refreshAgenda(); }
    }
    component EventRow: RowLayout {
        id: row
        required property var modelData
        readonly property string accessibilityLabel: (modelData.title || qsTr("Sem título"))
            + ". " + root.eventTime(modelData)
        readonly property alias titleItem: eventTitle
        spacing: Style.space.sm
        Accessible.role: Accessible.ListItem
        Accessible.name: accessibilityLabel
        // A rounded bar in the calendar's color, as in the macOS Calendar widget.
        Rectangle {
            Layout.preferredWidth: Style.space.xxs + 1
            Layout.fillHeight: true
            radius: width / 2
            color: root.eventColor(row.modelData)
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Controls.Label {
                id: eventTitle
                objectName: "calendarEventTitle"
                Layout.fillWidth: true
                text: row.modelData.title || qsTr("Sem título")
                textFormat: Text.PlainText
                color: root.dock.foreground
                font.weight: Style.weight.demiBold
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Controls.Label {
                Layout.fillWidth: true
                text: root.eventTime(row.modelData)
                textFormat: Text.PlainText
                color: root.dock.muted
                font.pixelSize: Style.type.caption
                wrapMode: Text.WordWrap
            }
        }
    }
    Controls.Label {
        objectName: "calendarDayTitle"
        Layout.fillWidth: true
        color: root.dock.foreground
        text: root.dayTitle()
        textFormat: Text.PlainText
        Accessible.name: root.selectedIsToday ? Qt.formatDate(root.selectedDate, Qt.DefaultLocaleLongDate) : text
        wrapMode: Text.WordWrap
        font.weight: Style.weight.bold
    }
    Controls.Label {
        objectName: "calendarEmptyState"
        Layout.fillWidth: true
        visible: root.agendaEvents.length === 0
        text: root.providerState === "disabled"
            ? qsTr("Eventos do KDE desativados neste perfil.")
            : root.providerState === "plugin-metadata-missing"
                ? qsTr("O componente de eventos PIM do KDE não foi encontrado.")
                : qsTr("Nenhum evento foi recebido para esta data. Isso também pode ocorrer sem calendário selecionado ou com o KDE PIM indisponível.")
        color: root.dock.muted
        textFormat: Text.PlainText
        Accessible.name: text
        wrapMode: Text.WordWrap
    }
    ListView {
        id: agenda
        objectName: "calendarAgendaList"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(contentHeight, 170)
        visible: count > 0
        clip: true
        spacing: Style.space.sm
        boundsBehavior: Flickable.StopAtBounds
        model: root.agendaEvents
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        delegate: EventRow { width: agenda.width - Style.space.md }
    }
    Controls.Label {
        objectName: "calendarTomorrowTitle"
        Layout.fillWidth: true
        Layout.topMargin: Style.space.xs
        visible: root.tomorrowEvents.length > 0
        text: qsTr("Amanhã")
        textFormat: Text.PlainText
        color: root.dock.foreground
        font.weight: Style.weight.bold
    }
    ListView {
        id: tomorrowAgenda
        objectName: "calendarTomorrowList"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(contentHeight, 110)
        visible: count > 0
        clip: true
        spacing: Style.space.sm
        boundsBehavior: Flickable.StopAtBounds
        model: root.tomorrowEvents
        delegate: EventRow { width: tomorrowAgenda.width - Style.space.md }
    }
    // Why a day may look empty; with events on screen it is not needed.
    Controls.Label {
        objectName: "calendarProviderExplanation"
        Layout.fillWidth: true
        visible: root.agendaEvents.length === 0
        text: qsTr("O Orla usa, sem alterá-la, a seleção compartilhada com o relógio/calendário do KDE. Mudar essa seleção no KDE também muda o relógio. Contas e sincronização, inclusive Google, são configuradas no KOrganizer; atualidade e disponibilidade são geridas pelo KDE.")
        textFormat: Text.PlainText
        Accessible.name: text
        color: root.dock.muted
        wrapMode: Text.WordWrap
        font.pixelSize: Style.type.caption
    }
    Controls.Button {
        objectName: "calendarGoogleButton"
        text: qsTr("Abrir Google Agenda")
        Accessible.name: text
        Accessible.description: qsTr("Abre o site do Google Agenda no navegador.")
        onClicked: Qt.openUrlExternally("https://calendar.google.com/")
    }
}
