import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

ColumnLayout {
    id: settings
    required property var configuration
    required property var resetTimer
    spacing: 12
    Controls.Label { text: "Orla Dock 0.2.1 alpha · Plasma 6.7+"; opacity: 0.6 }
    Controls.Label { text: qsTr("Aparência"); font.bold: true }
    RowLayout {
        Repeater {
            model: [{key: "glass", label: "Vidro"}, {key: "midnight", label: "Meia-noite"}, {key: "paper", label: "Papel"}]
            Controls.Button {
                required property var modelData
                text: modelData.label
                checkable: true
                checked: settings.configuration.theme === modelData.key
                onClicked: settings.configuration.theme = modelData.key
            }
        }
    }
    Controls.Label { text: qsTr("Tamanho dos ícones") }
    Controls.Slider { Layout.fillWidth: true; from: 24; to: 64; stepSize: 2; value: settings.configuration.iconSize; onMoved: settings.configuration.iconSize = value }
    Controls.CheckBox { text: qsTr("Animar ícones"); checked: settings.configuration.animations; onToggled: settings.configuration.animations = checked }
    Controls.CheckBox { text: qsTr("Janelas apenas da área de trabalho atual"); checked: settings.configuration.currentDesktopOnly; onToggled: settings.configuration.currentDesktopOnly = checked }
    Controls.Label { text: qsTr("Widgets"); font.bold: true }
    Controls.CheckBox { text: qsTr("Relógio e calendário"); checked: settings.configuration.showClock; onToggled: settings.configuration.showClock = checked }
    Controls.CheckBox { text: qsTr("Eventos sincronizados pelo KDE"); checked: settings.configuration.calendarEvents; onToggled: settings.configuration.calendarEvents = checked }
    Controls.CheckBox { text: qsTr("Pomodoro"); checked: settings.configuration.showPomodoro; onToggled: settings.configuration.showPomodoro = checked }
    Controls.CheckBox { text: qsTr("Música (MPRIS)"); checked: settings.configuration.showMusic; onToggled: settings.configuration.showMusic = checked }
    Controls.CheckBox { text: qsTr("Quotas de IA · QuotaLantern"); checked: settings.configuration.showQuota; onToggled: settings.configuration.showQuota = checked }
    Controls.CheckBox { text: qsTr("Baterias · PeriGauge"); checked: settings.configuration.showPeripherals; onToggled: settings.configuration.showPeripherals = checked }
    Controls.CheckBox { text: qsTr("Gravação · FalaTrace"); checked: settings.configuration.showRecording; onToggled: settings.configuration.showRecording = checked }
    Controls.Label { Layout.fillWidth: true; text: qsTr("Para ocultar automaticamente: configure a visibilidade do painel no modo de edição do Plasma."); wrapMode: Text.WordWrap; opacity: 0.65 }
}
