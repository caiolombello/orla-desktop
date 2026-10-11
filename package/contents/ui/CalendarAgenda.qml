import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.plasma.workspace.calendar as PlasmaCalendar

ColumnLayout {
    id: root
    required property var dock
    property var fixtureEvents: null
    property bool usePimEvents: dock.configuration && dock.configuration.calendarEvents !== undefined
        ? dock.configuration.calendarEvents : true
    property alias selectedDate: monthView.currentDate
    readonly property alias enabledPlugins: plugins.enabledPlugins
    property var agendaEvents: []
    spacing: 8

    function refreshAgenda() {
        if (!monthView) return;
        agendaEvents = fixtureEvents !== null ? fixtureEvents
            : usePimEvents ? monthView.daysModel.eventsForDate(monthView.currentDate) : [];
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
            ? Qt.formatTime(end, "HH:mm") : Qt.formatDateTime(end, "d MMM, HH:mm");
        return Qt.formatTime(start, "HH:mm") + " – " + endLabel;
    }
    onFixtureEventsChanged: refreshAgenda()
    onUsePimEventsChanged: refreshAgenda()
    Component.onCompleted: refreshAgenda()

    PlasmaCalendar.EventPluginsManager {
        id: plugins
        enabledPlugins: root.fixtureEvents === null && root.usePimEvents ? ["pimevents"] : []
    }
    PlasmaCalendar.MonthView {
        id: monthView
        objectName: "calendarMonthView"
        Layout.fillWidth: true
        Layout.preferredHeight: 290
        today: root.dock.now !== undefined ? root.dock.now : new Date()
        eventPluginsManager: plugins
        onCurrentDateChanged: root.refreshAgenda()
    }
    Connections {
        target: monthView.daysModel
        function onAgendaUpdated(updatedDate) { root.refreshAgenda(); }
    }
    Controls.Label {
        Layout.fillWidth: true
        color: root.dock.foreground
        text: Qt.formatDate(root.selectedDate, Qt.DefaultLocaleLongDate)
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        font.bold: true
    }
    Controls.Label {
        objectName: "calendarEmptyState"
        Layout.fillWidth: true
        visible: root.agendaEvents.length === 0
        text: root.usePimEvents ? qsTr("Nenhum evento disponível para esta data. Confira os calendários selecionados no KDE.")
            : qsTr("Eventos do KDE desativados. Ative-os nas preferências do dock.")
        color: root.dock.muted
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    ListView {
        id: agenda
        objectName: "calendarAgendaList"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(contentHeight, 170)
        visible: count > 0
        clip: true
        spacing: 8
        boundsBehavior: Flickable.StopAtBounds
        model: root.agendaEvents
        Controls.ScrollBar.vertical: Controls.ScrollBar {}
        delegate: ColumnLayout {
            required property var modelData
            width: agenda.width - 14
            spacing: 2
            Controls.Label {
                objectName: "calendarEventTitle"
                Layout.fillWidth: true
                text: modelData.title || qsTr("Sem título")
                textFormat: Text.PlainText
                color: root.dock.foreground
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Controls.Label {
                Layout.fillWidth: true
                text: root.eventTime(modelData)
                textFormat: Text.PlainText
                color: root.dock.muted
                wrapMode: Text.WordWrap
            }
        }
    }
    Controls.Label {
        Layout.fillWidth: true
        text: qsTr("Usa a seleção de calendários compartilhada com o relógio do KDE. Para Google, configure a sincronização no KOrganizer.")
        textFormat: Text.PlainText
        color: root.dock.muted
        wrapMode: Text.WordWrap
        font.pixelSize: 11
    }
    Controls.Button {
        text: qsTr("Abrir Google Agenda")
        onClicked: Qt.openUrlExternally("https://calendar.google.com/")
    }
}
