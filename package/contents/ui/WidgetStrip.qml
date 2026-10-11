import QtQuick
import "../code/Logic.js" as Logic

// Only existing built-in tiles are constructed here; providers live in DockView.
Row {
    id: strip
    required property var dock
    spacing: dock.appearance.effective.tokens.spacing
    visible: dock.presentation.widgets.some(widget => widget.visible)
    function info(key) {
        if (key === "clock") return {width: 112, icon: "clock", title: Qt.formatTime(dock.now, "HH:mm"),
            subtitle: Qt.formatDate(dock.now, "ddd, d MMM"), tooltip: Qt.formatDate(dock.now, Qt.DefaultLocaleLongDate)};
        if (key === "pomodoro") return {width: 126, icon: dock.pomodoro.running ? "media-playback-pause" : "chronometer",
            title: Logic.duration(dock.pomodoro.secondsLeft), subtitle: dock.configuration.timerBreak ? qsTr("Pausa") : qsTr("Foco · Pomodoro"), tooltip: qsTr("Pomodoro · iniciar, pausar ou reiniciar")};
        if (key === "music") return {width: 158, icon: dock.player ? dock.player.iconName || "audio-x-generic" : "audio-x-generic",
            title: dock.player ? dock.mediaText(dock.player.track || dock.player.identity, 512) : qsTr("Sua música"),
            subtitle: dock.player ? dock.mediaText(dock.player.artist || dock.player.identity, 256) : qsTr("Nenhum player aberto"), tooltip: qsTr("Controles de mídia")};
        if (key === "systemBattery") return {width: 132, icon: dock.systemBattery.charging === "charging" ? "battery-charging" : "battery",
            title: dock.systemBattery.percentKnown ? Math.round(dock.systemBattery.percent) + "%" : qsTr("Energia"),
            subtitle: dock.powerSubtitle, tooltip: qsTr("Bateria do sistema") + " · " + dock.powerSubtitle};
        const title = key === "quota" ? "QuotaLantern" : key === "peripherals" ? "PeriGauge" : "FalaTrace";
        const subtitle = key === "quota" ? dock.integrations.quotaSummary : key === "peripherals" ? dock.integrations.batterySummary : dock.integrations.recordingSummary;
        return {width: 164, icon: key === "quota" ? "office-chart-pie" : key === "peripherals" ? "battery" : "media-record", title: title, subtitle: subtitle, tooltip: title + " · " + subtitle};
    }
    Repeater {
        model: strip.dock.presentation.widgets
        delegate: Tile {
            required property var modelData
            readonly property var info: strip.info(modelData.id)
            objectName: modelData.id === "pomodoro" ? "pomodoroButton" : modelData.id + "Tile"
            anchors.verticalCenter: parent.verticalCenter
            visible: modelData.visible
            wide: true
            implicitWidth: info.width
            iconSize: strip.dock.tileSize
            iconSource: info.icon
            title: info.title
            subtitle: info.subtitle
            tooltip: info.tooltip
            foreground: strip.dock.foreground; muted: strip.dock.muted; accent: strip.dock.accent
            animationDuration: strip.dock.motion
            onClicked: strip.dock.openWidget(modelData.id)
        }
    }
}
