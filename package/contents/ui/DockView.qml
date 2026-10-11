import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import org.kde.taskmanager as TaskManager
import org.kde.plasma.private.mpris as Mpris
import "../code/Logic.js" as Logic

Item {
    id: root
    objectName: "dock"
    required property var configuration
    property bool popAbove: false
    property date now: new Date()
    property string notice: ""
    property var menuData: ({})
    property int menuRow: -1
    property bool ready: false
    property alias tasksModel: tasks
    property alias pomodoro: focusTimer
    property alias integrations: localIntegrations
    property string selectedIntegration: "quota"
    readonly property bool light: configuration.theme === "paper"
    readonly property color foreground: light ? "#252b35" : "#edf1f9"
    readonly property color muted: light ? "#657180" : "#9da9bf"
    readonly property color accent: light ? "#167361" : "#69d7c2"
    readonly property color surface: light ? "#f4f0e8" : configuration.theme === "midnight" ? "#111923" : "#db283542"
    readonly property int motion: configuration.animations ? Kirigami.Units.shortDuration : 0
    readonly property int requestedIconSize: Math.max(24, Math.min(64, configuration.iconSize))
    readonly property int tileSize: Math.max(16, Math.min(requestedIconSize, height > 0 ? height - 36 : requestedIconSize))
    implicitWidth: content.implicitWidth + 24
    implicitHeight: requestedIconSize + 38

    function activateTask(row) {
        if (row < 0 || row >= tasks.count) return;
        const index = tasks.makeModelIndex(row);
        if (tasks.data(index, TaskManager.AbstractTasksModel.IsActive) && tasks.data(index, TaskManager.AbstractTasksModel.IsMinimizable))
            tasks.requestToggleMinimized(index);
        else tasks.requestActivate(index);
    }
    function addLauncher(input) {
        const url = Logic.launcherUrl(input);
        if (!url || !tasks.requestAddLauncher(url)) {
            notice = qsTr("Não foi possível fixar. Use um arquivo .desktop instalado.");
            return false;
        }
        configuration.launchers = tasks.launcherList;
        notice = "";
        return true;
    }
    function moveTask(from, to) {
        if (from < 0 || to < 0 || from >= tasks.count || to >= tasks.count) return false;
        const changed = tasks.move(from, to);
        tasks.syncLaunchers();
        configuration.launchers = tasks.launcherList;
        return changed;
    }
    function showTaskMenu(row, data) {
        // Capture identity: model rows may change while a menu is open.
        menuRow = row;
        menuData = { title: data.AppName || data.display, url: String(data.LauncherUrlWithoutIcon || ""),
            window: Boolean(data.IsWindow), pinned: Boolean(data.HasLauncher || data.IsLauncher),
            ids: JSON.stringify(data.WinIdList || []), minimizable: Boolean(data.IsMinimizable),
            closable: Boolean(data.IsClosable), canLaunch: Boolean(data.CanLaunchNewInstance) };
        taskMenu.open();
    }
    function menuIndex() {
        for (let i = 0; i < tasks.count; i++) {
            const index = tasks.makeModelIndex(i);
            if (menuData.window) {
                if (JSON.stringify(tasks.data(index, TaskManager.AbstractTasksModel.WinIdList) || []) === menuData.ids) return index;
            } else if (String(tasks.data(index, TaskManager.AbstractTasksModel.LauncherUrlWithoutIcon)) === menuData.url) return index;
        }
        return null;
    }
    function moveMenuTask(delta) {
        const index = menuIndex();
        if (index) moveTask(index.row, index.row + delta);
    }

    TaskManager.TasksModel {
        id: tasks
        groupMode: TaskManager.TasksModel.GroupDisabled
        sortMode: TaskManager.TasksModel.SortManual
        separateLaunchers: false
        launchInPlace: true
        hideActivatedLaunchers: true
        filterByCurrentVirtualDesktop: root.configuration.currentDesktopOnly
        onLauncherListChanged: if (root.ready) root.configuration.launchers = launcherList
    }
    TaskManager.TasksModel {
        id: calendarLauncher
        launcherList: ["applications:org.kde.korganizer.desktop"]
    }
    function openCalendarApp() {
        for (let i = 0; i < calendarLauncher.count; i++) {
            const index = calendarLauncher.makeModelIndex(i);
            if (String(calendarLauncher.data(index, TaskManager.AbstractTasksModel.LauncherUrlWithoutIcon)).endsWith("org.kde.korganizer.desktop")) {
                calendarLauncher.requestActivate(index);
                return;
            }
        }
        notice = qsTr("Instale o KOrganizer para conectar o Google Agenda ao KDE.");
    }
    Integrations {
        id: localIntegrations
        active: root.configuration.showQuota || root.configuration.showPeripherals || root.configuration.showRecording
    }
    Component.onCompleted: { tasks.launcherList = configuration.launchers; ready = true; }
    Mpris.Mpris2Model { id: media }
    readonly property var player: media.currentPlayer
    Pomodoro {
        id: focusTimer
        configuration: root.configuration
        onFinished: root.notice = root.configuration.timerBreak ? qsTr("Foco concluído. Hora de uma pausa!") : qsTr("Pausa concluída. Pronto para focar?")
    }
    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.now = new Date() }
    Timer { interval: 8000; running: root.notice.length > 0; onTriggered: root.notice = "" }
    Rectangle {
        anchors.fill: parent
        radius: 21
        color: root.surface
        border.width: 1
        border.color: root.light ? "#cec9bf" : "#3c4b65"
        Behavior on color { ColorAnimation { duration: root.motion } }
        Rectangle { x: 16; y: 1; width: parent.width - 32; height: 1; color: root.light ? "#ffffff" : "#526482"; opacity: 0.55 }
    }
    Flickable {
        id: viewport
        anchors.fill: parent
        anchors.margins: 10
        contentWidth: content.width
        contentHeight: height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.HorizontalFlick
        Controls.ScrollBar.horizontal: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
        Row {
            id: content
            height: viewport.height
            spacing: 5
            Tile {
                objectName: "settingsButton"
                anchors.verticalCenter: parent.verticalCenter
                iconSource: Qt.resolvedUrl("../images/orla.svg")
                iconSize: root.tileSize - 10
                foreground: root.accent; accent: root.accent; animationDuration: root.motion
                tooltip: qsTr("Personalizar Orla Dock")
                onClicked: settings.open()
            }
            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 1; height: 30; color: root.muted; opacity: 0.3 }
            Repeater {
                model: tasks
                delegate: Tile {
                    id: taskTile
                    required property var model
                    required property int index
                    anchors.verticalCenter: parent.verticalCenter
                    iconSource: model.decoration
                    iconSize: root.tileSize
                    title: model.AppName || model.display
                    tooltip: model.display || model.AppName
                    foreground: root.foreground; muted: root.muted; accent: root.accent
                    animationDuration: root.motion
                    running: Boolean(model.IsWindow || model.IsStartup)
                    activeTask: Boolean(model.IsActive)
                    attention: Boolean(model.IsDemandingAttention)
                    onClicked: root.activateTask(index)
                    onPressAndHold: root.showTaskMenu(index, model)
                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: root.showTaskMenu(taskTile.index, taskTile.model) }
                }
            }
            Tile {
                objectName: "addButton"
                anchors.verticalCenter: parent.verticalCenter
                iconSource: "list-add"
                iconSize: Math.max(12, root.tileSize - 16)
                foreground: root.muted; accent: root.accent; animationDuration: root.motion
                tooltip: qsTr("Fixar aplicativo · ou arraste um app para o dock")
                onClicked: addDialog.open()
            }
            Rectangle { anchors.verticalCenter: parent.verticalCenter; visible: root.configuration.showClock || root.configuration.showMusic || root.configuration.showPomodoro; width: visible ? 1 : 0; height: 30; color: root.muted; opacity: 0.3 }
            Tile {
                anchors.verticalCenter: parent.verticalCenter
                visible: root.configuration.showClock
                wide: true; implicitWidth: 112
                iconSize: root.tileSize
                iconSource: "clock"
                title: Qt.formatTime(root.now, "HH:mm")
                subtitle: Qt.formatDate(root.now, "ddd, d MMM")
                tooltip: Qt.formatDate(root.now, Qt.DefaultLocaleLongDate)
                foreground: root.foreground; muted: root.muted; accent: root.accent; animationDuration: root.motion
                onClicked: calendarPopup.open()
            }
            Tile {
                objectName: "pomodoroButton"
                anchors.verticalCenter: parent.verticalCenter
                visible: root.configuration.showPomodoro
                wide: true; implicitWidth: 126
                iconSize: root.tileSize
                iconSource: focusTimer.running ? "media-playback-pause" : "chronometer"
                title: Logic.duration(focusTimer.secondsLeft)
                subtitle: root.configuration.timerBreak ? qsTr("Pausa") : qsTr("Foco · Pomodoro")
                tooltip: qsTr("Pomodoro · iniciar, pausar ou reiniciar")
                foreground: root.foreground; muted: root.muted; accent: root.accent; animationDuration: root.motion
                onClicked: pomodoroPopup.open()
            }
            Tile {
                anchors.verticalCenter: parent.verticalCenter
                visible: root.configuration.showMusic
                wide: true
                iconSize: root.tileSize
                iconSource: root.player ? root.player.iconName || "audio-x-generic" : "audio-x-generic"
                title: root.player ? root.player.track || root.player.identity : qsTr("Sua música")
                subtitle: root.player ? root.player.artist || root.player.identity : qsTr("Nenhum player aberto")
                tooltip: qsTr("Controles de mídia")
                foreground: root.foreground; muted: root.muted; accent: root.accent; animationDuration: root.motion
                onClicked: musicPopup.open()
            }
            Repeater {
                model: [
                    {key: "quota", shown: root.configuration.showQuota, icon: "office-chart-pie", title: "QuotaLantern", subtitle: localIntegrations.quotaSummary},
                    {key: "peripherals", shown: root.configuration.showPeripherals, icon: "battery", title: "PeriGauge", subtitle: localIntegrations.batterySummary},
                    {key: "recording", shown: root.configuration.showRecording, icon: "media-record", title: "FalaTrace", subtitle: localIntegrations.recordingSummary}
                ]
                delegate: Tile {
                    required property var modelData
                    objectName: modelData.key + "Tile"
                    anchors.verticalCenter: parent.verticalCenter
                    visible: modelData.shown
                    wide: true
                    implicitWidth: 164
                    iconSize: root.tileSize
                    iconSource: modelData.icon
                    title: modelData.title
                    subtitle: modelData.subtitle
                    tooltip: modelData.title + " · " + modelData.subtitle
                    foreground: root.foreground; muted: root.muted; accent: root.accent; animationDuration: root.motion
                    onClicked: { root.selectedIntegration = modelData.key; integrationPopup.open(); }
                }
            }
        }
    }
    DropArea {
        anchors.fill: parent
        onDropped: drop => {
            let accepted = false;
            for (const url of drop.urls) accepted = root.addLauncher(String(url)) || accepted;
            if (accepted) drop.acceptProposedAction();
        }
        Rectangle { anchors.fill: parent; radius: 21; visible: parent.containsDrag; color: "transparent"; border.color: root.accent; border.width: 2 }
    }
    Controls.Menu {
        id: taskMenu
        popupType: Controls.Popup.Window
        x: Math.max(0, Math.min(root.width - width, (root.menuRow + 1) * (root.tileSize + 16)))
        y: root.popAbove ? -height - 8 : root.height + 8
        Controls.MenuItem { text: root.menuData.title || ""; enabled: false }
        Controls.MenuSeparator {}
        Controls.MenuItem {
            text: root.menuData.pinned ? qsTr("Desafixar") : qsTr("Fixar no dock")
            enabled: Boolean(root.menuData.url)
            onTriggered: { if (root.menuData.pinned) tasks.requestRemoveLauncher(root.menuData.url); else root.addLauncher(root.menuData.url); }
        }
        Controls.MenuItem { text: qsTr("Nova janela"); enabled: Boolean(root.menuData.canLaunch); onTriggered: { const index = root.menuIndex(); if (index) tasks.requestNewInstance(index); } }
        Controls.MenuItem { text: qsTr("Mover para a esquerda"); enabled: root.menuRow > 0; onTriggered: root.moveMenuTask(-1) }
        Controls.MenuItem { text: qsTr("Mover para a direita"); enabled: root.menuRow < tasks.count - 1; onTriggered: root.moveMenuTask(1) }
        Controls.MenuSeparator { visible: Boolean(root.menuData.window) }
        Controls.MenuItem { text: qsTr("Minimizar / restaurar"); visible: Boolean(root.menuData.window); enabled: Boolean(root.menuData.minimizable); onTriggered: { const index = root.menuIndex(); if (index) tasks.requestToggleMinimized(index); } }
        Controls.MenuItem { text: qsTr("Fechar janela"); visible: Boolean(root.menuData.window); enabled: Boolean(root.menuData.closable); onTriggered: { const index = root.menuIndex(); if (index) tasks.requestClose(index); } }
    }
    DockPopup {
        id: settings
        objectName: "settingsPopup"
        dock: root
        title: qsTr("Seu dock, do seu jeito")
        SettingsContents { configuration: root.configuration; resetTimer: focusTimer.reset }
    }
    DockPopup {
        id: addDialog
        dock: root
        title: qsTr("Fixar aplicativo")
        onOpened: appInput.forceActiveFocus()
        ColumnLayout {
            Controls.Label { Layout.fillWidth: true; text: qsTr("Arraste um aplicativo do menu do KDE para o dock, ou informe o ID abaixo."); wrapMode: Text.WordWrap }
            Controls.TextField { id: appInput; objectName: "launcherInput"; Layout.fillWidth: true; placeholderText: "org.kde.dolphin.desktop"; onAccepted: pinButton.clicked() }
            Controls.Label { Layout.fillWidth: true; text: root.notice; visible: text.length > 0; wrapMode: Text.WordWrap }
            Controls.Button { id: pinButton; text: qsTr("Fixar aplicativo"); enabled: appInput.text.trim().length > 0; onClicked: if (root.addLauncher(appInput.text)) { appInput.clear(); addDialog.close(); } }
        }
    }
    DockPopup {
        id: calendarPopup
        dock: root
        title: Qt.formatDate(root.now, "MMMM yyyy")
        CalendarAgenda { dock: root }
        Controls.Button { text: qsTr("Configurar no KOrganizer"); onClicked: root.openCalendarApp() }
    }
    DockPopup {
        id: integrationPopup
        dock: root
        title: root.selectedIntegration === "quota" ? "QuotaLantern" : root.selectedIntegration === "peripherals" ? "PeriGauge" : "FalaTrace"
        IntegrationDetails { dock: root; integrations: localIntegrations; selected: root.selectedIntegration }
    }
    DockPopup {
        id: pomodoroPopup
        dock: root
        title: root.configuration.timerBreak ? qsTr("Respire um pouco") : qsTr("Uma coisa de cada vez")
        ColumnLayout {
            Controls.Label { text: Logic.duration(focusTimer.secondsLeft); font.pixelSize: 40; Layout.alignment: Qt.AlignHCenter }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 5
                radius: 3
                color: root.light ? "#ddd8cf" : "#34435b"
                Rectangle {
                    width: parent.width * Math.max(0, Math.min(1, 1 - focusTimer.secondsLeft / focusTimer.phaseSeconds))
                    height: parent.height
                    radius: parent.radius
                    color: root.accent
                }
            }
            RowLayout {
                Controls.Button { objectName: "toggleTimer"; text: focusTimer.running ? qsTr("Pausar") : qsTr("Iniciar"); onClicked: focusTimer.toggle() }
                Controls.Button { text: qsTr("Reiniciar"); onClicked: focusTimer.reset() }
            }
            Controls.Label { text: qsTr("%1 sessões concluídas").arg(root.configuration.completedFocus); opacity: 0.65 }
            RowLayout {
                Controls.Label { text: qsTr("Foco (min)") }
                Controls.SpinBox { from: 1; to: 120; value: root.configuration.focusMinutes; enabled: !focusTimer.running; onValueModified: { root.configuration.focusMinutes = value; focusTimer.reset(); } }
            }
            RowLayout {
                Controls.Label { text: qsTr("Pausa (min)") }
                Controls.SpinBox { from: 1; to: 60; value: root.configuration.breakMinutes; enabled: !focusTimer.running; onValueModified: { root.configuration.breakMinutes = value; focusTimer.reset(); } }
            }
        }
    }
    DockPopup {
        id: musicPopup
        dock: root
        title: root.player ? root.player.identity : qsTr("Sua música")
        ColumnLayout {
            Controls.Label { Layout.fillWidth: true; text: root.player ? root.player.track || qsTr("Sem título") : qsTr("Abra um player compatível com MPRIS, como Elisa, VLC ou Spotify."); wrapMode: Text.WordWrap; font.bold: true }
            Controls.Label { Layout.fillWidth: true; text: root.player ? root.player.artist : ""; wrapMode: Text.WordWrap; opacity: 0.65 }
            RowLayout {
                Controls.Button { text: qsTr("Anterior"); enabled: Boolean(root.player && root.player.canGoPrevious); onClicked: root.player.Previous() }
                Controls.Button { text: root.player && root.player.playbackStatus === Mpris.PlaybackStatus.Playing ? qsTr("Pausar") : qsTr("Reproduzir"); enabled: Boolean(root.player && (root.player.canPlay || root.player.canPause)); onClicked: root.player.PlayPause() }
                Controls.Button { text: qsTr("Próxima"); enabled: Boolean(root.player && root.player.canGoNext); onClicked: root.player.Next() }
            }
        }
    }
    Controls.ToolTip { parent: root; visible: root.notice.length > 0 && !addDialog.opened; text: root.notice; timeout: 8000 }
}
