import QtQuick
import "../code/Logic.js" as Logic
import "../code/Style.js" as Style

// Only existing built-in tiles are constructed here; providers live in DockView.
Row {
    id: strip
    required property var dock
    spacing: dock.appearance.effective.tokens.spacing
    visible: dock.presentation.widgets.some(widget => widget.visible)
    function finiteNumber(value) { return typeof value === "number" && isFinite(value); }
    function meaningful(key) {
        if (key === "clock" || key === "pomodoro") return true;
        if (key === "music") return Boolean(dock.player);
        if (key === "systemBattery") return dock.systemBattery.status === "ready"
            && dock.systemBattery.percentKnown;
        if (dock.integrations.error) return false;
        if (key === "quota") return (dock.integrations.quota.status === "ready"
                || dock.integrations.quota.status === "stale")
            && (dock.integrations.quota.windows || [])
                .some(window => window && finiteNumber(window.usedPercent));
        if (key === "peripherals") return (dock.integrations.peripherals.devices || [])
            .some(device => device && ((dock.integrations.peripherals.status === "ready"
                    || dock.integrations.peripherals.status === "stale") && finiteNumber(device.percent)
                || device.present === false && typeof device.name === "string" && device.name.trim().length > 0));
        const state = dock.integrations.recording.state;
        return state === "starting" || state === "recording" || state === "stopped";
    }
    function ratio(value) { return finiteNumber(value) ? Math.max(0, Math.min(1, value / 100)) : -1; }
    // Ring color for a remaining level (battery) or a used share (quota).
    function remainingColor(percent) {
        return percent <= 10 ? Style.levels.critical : percent <= 20 ? Style.levels.low : Style.levels.good;
    }
    function usedColor(percent) {
        return percent >= 90 ? Style.levels.critical : percent >= 75 ? Style.levels.low : Style.levels.good;
    }
    function timerProgress() {
        const total = dock.pomodoro.phaseSeconds;
        return finiteNumber(total) && total > 0 ? Math.max(0, Math.min(1, 1 - dock.pomodoro.secondsLeft / total)) : 0;
    }
    // Text stays in title/subtitle for the hover label and screen readers; the
    // icon itself only shows a short value.
    function info(key) {
        const live = meaningful(key);
        if (key === "clock") return {live: true, data: {},
            title: Qt.formatTime(dock.now, "HH:mm"), subtitle: Qt.formatDate(dock.now, Qt.DefaultLocaleLongDate)};
        if (key === "pomodoro") return {live: true,
            data: {value: Math.ceil(dock.pomodoro.secondsLeft / 60), progress: timerProgress(),
                palette: dock.configuration.timerBreak ? "sea" : "coral"},
            title: Logic.duration(dock.pomodoro.secondsLeft), subtitle: dock.configuration.timerBreak ? qsTr("Pausa") : qsTr("Foco")};
        if (key === "music") return {live: live,
            data: {art: dock.player ? dock.player.artUrl || "" : "", active: Boolean(dock.mediaPlaying)},
            title: dock.player ? dock.mediaText(dock.player.track || dock.player.identity, 512) : qsTr("Sua música"),
            subtitle: dock.player ? dock.mediaText(dock.player.artist || dock.player.identity, 256) : qsTr("Nenhum player aberto")};
        if (key === "systemBattery") {
            const percent = Math.round(dock.systemBattery.percent);
            return {live: live,
                data: {value: percent, progress: ratio(percent), ring: remainingColor(percent),
                    charging: live && dock.systemBattery.charging === "charging", glyph: "battery-100-symbolic"},
                title: dock.systemBattery.percentKnown ? percent + "%" : qsTr("Energia"), subtitle: dock.powerSubtitle};
        }
        const title = key === "quota" ? "QuotaLantern" : key === "peripherals" ? "PeriGauge" : "FalaTrace";
        const subtitle = key === "quota" ? dock.integrations.quotaSummary : key === "peripherals" ? dock.integrations.batterySummary : dock.integrations.recordingSummary;
        if (key === "recording") return {live: live,
            data: {active: live && dock.integrations.recording.state === "recording"}, title: title, subtitle: subtitle};
        const windows = (dock.integrations.quota.windows || []).filter(window => window && finiteNumber(window.usedPercent));
        const devices = (dock.integrations.peripherals.devices || []).filter(device => device && finiteNumber(device.percent));
        const used = windows.length ? Math.round(Math.max(...windows.map(window => window.usedPercent))) : -1;
        const lowest = devices.length ? Math.round(Math.min(...devices.map(device => device.percent))) : -1;
        const percent = key === "quota" ? used : lowest;
        return {live: live,
            data: {value: live && percent >= 0 ? percent : "", progress: live ? ratio(percent) : -1,
                ring: key === "quota" ? usedColor(percent) : remainingColor(percent),
                glyph: key === "quota" ? "office-chart-pie-symbolic" : "input-mouse-symbolic"},
            title: title, subtitle: subtitle};
    }
    Repeater {
        model: strip.dock.presentation.widgets
        delegate: Tile {
            required property var modelData
            readonly property var info: strip.info(modelData.id)
            objectName: modelData.id === "pomodoro" ? "pomodoroButton" : modelData.id + "Tile"
            anchors.verticalCenter: parent.verticalCenter
            visible: modelData.visible
            iconSize: strip.dock.tileSize
            liveKind: modelData.id
            liveInfo: info.data
            live: info.live
            now: strip.dock.now
            title: info.title
            subtitle: info.subtitle
            tooltip: info.title + " · " + info.subtitle
            nativeLabel: Boolean(strip.dock.nativePopups)
            foreground: strip.dock.foreground; muted: strip.dock.muted; accent: strip.dock.accent
            animationDuration: strip.dock.motion
            onClicked: strip.dock.openWidget(modelData.id, this)
            onHoveredChanged: if (strip.dock.hoverTile) strip.dock.hoverTile(this, hovered)
        }
    }
}
