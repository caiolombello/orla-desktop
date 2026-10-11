import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

ColumnLayout {
    id: settings
    required property var configuration
    required property var resetTimer
    required property var appearance
    signal appearanceCanceled()
    spacing: 8
    Controls.Label { text: "Orla Dock 0.2.4 alpha · Plasma 6.7+"; opacity: 0.6 }
    Controls.TabBar {
        id: tabs
        Layout.fillWidth: true
        Controls.TabButton { text: qsTr("Aparência") }
        Controls.TabButton { text: qsTr("Widgets") }
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
                spacing: 8
                Controls.Label {
                    Layout.fillWidth: true
                    text: qsTr("Widgets e filtro de janelas são salvos imediatamente. Cancelar aparência não desfaz estas opções.")
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                Controls.CheckBox { text: qsTr("Janelas apenas da área de trabalho atual"); checked: settings.configuration.currentDesktopOnly; onToggled: settings.configuration.currentDesktopOnly = checked }
                Controls.Label { text: qsTr("Widgets"); font.bold: true }
                Controls.CheckBox { text: qsTr("Relógio e calendário"); checked: settings.configuration.showClock; onToggled: settings.configuration.showClock = checked }
                Controls.CheckBox { text: qsTr("Eventos sincronizados pelo KDE"); checked: settings.configuration.calendarEvents; onToggled: settings.configuration.calendarEvents = checked }
                Controls.CheckBox { text: qsTr("Pomodoro"); checked: settings.configuration.showPomodoro; onToggled: settings.configuration.showPomodoro = checked }
                Controls.CheckBox { text: qsTr("Música (MPRIS)"); checked: settings.configuration.showMusic; onToggled: settings.configuration.showMusic = checked }
                Controls.CheckBox { text: qsTr("Bateria do computador"); checked: settings.configuration.showSystemBattery; onToggled: settings.configuration.showSystemBattery = checked }
                Controls.CheckBox { text: qsTr("Quotas de IA · QuotaLantern"); checked: settings.configuration.showQuota; onToggled: settings.configuration.showQuota = checked }
                Controls.CheckBox { text: qsTr("Baterias · PeriGauge"); checked: settings.configuration.showPeripherals; onToggled: settings.configuration.showPeripherals = checked }
                Controls.CheckBox { text: qsTr("Gravação · FalaTrace"); checked: settings.configuration.showRecording; onToggled: settings.configuration.showRecording = checked }
                Controls.Label { Layout.fillWidth: true; text: qsTr("Para ocultar automaticamente: configure a visibilidade do painel no modo de edição do Plasma."); wrapMode: Text.WordWrap; opacity: 0.65 }
            }
        }
    }
}
