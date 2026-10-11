import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import org.kde.taskmanager as TaskManager
import org.kde.plasma.private.mpris as Mpris
import "../code/Logic.js" as Logic
import "../code/Profiles.js" as Profiles

Item {
    id: root
    objectName: "dock"
    required property var configuration
    property bool popAbove: false
    property date now: new Date()
    property string notice: ""
    property var menuData: ({})
    property int menuRow: -1
    property real menuAnchorX: 0
    property bool ready: false
    property alias tasksModel: tasks
    property alias pomodoro: focusTimer
    property alias integrations: localIntegrations
    property alias appearance: appearanceState
    property alias systemBattery: power
    property alias profiles: profileState
    readonly property var presentation: profileState.effective
    readonly property string launcherSnapshot: JSON.stringify(presentation.launchers)
    property string selectedIntegration: "quota"
    readonly property bool light: appearanceState.effective.baseTheme === "paper"
    readonly property color foreground: appearanceState.effective.tokens.foreground
    readonly property color muted: appearanceState.effective.tokens.muted
    readonly property color accent: appearanceState.effective.tokens.accent
    readonly property color surface: appearanceState.overridden ? appearanceState.effective.tokens.surface : light ? "#f4f0e8" : presentation.appearance.theme === "midnight" ? "#111923" : "#db283542"
    readonly property int motion: appearanceState.effective.tokens.reducedMotion ? 0 : Kirigami.Units.shortDuration
    readonly property int requestedIconSize: appearanceState.effective.tokens.iconSize
    readonly property int tileSize: Math.max(16, Math.min(requestedIconSize, height > 0 ? height - 36 : requestedIconSize))
    readonly property int outerMargin: 10
    readonly property int laneGap: 6
    readonly property bool localEventsRequested: Boolean(configuration.showLocalToasts)
    readonly property int settingsLaneWidth: settingsButton.implicitWidth
    readonly property int minimumTaskWidth: tileSize + 16
    readonly property int innerWidth: Math.max(0, width - outerMargin * 2)
    readonly property int candidateEventSlotWidth: Math.min(224, Math.floor(innerWidth * 0.30),
        Math.max(0, innerWidth - settingsLaneWidth - laneGap * 2 - minimumTaskWidth))
    readonly property bool localEventsProfileReady: profileState.writable
        && (profileState.initialized || profileState.savedJSON === "")
    readonly property bool localEventsActive: localEventsRequested && localEventsProfileReady
        && candidateEventSlotWidth >= 48
    readonly property int eventSlotWidth: localEventsActive ? candidateEventSlotWidth : 0
    readonly property int centerViewportWidth: localEventsActive
        ? Math.max(0, innerWidth - settingsLaneWidth - laneGap * 2 - eventSlotWidth) : innerWidth
    implicitWidth: localEventsRequested
        ? settingsLaneWidth + content.implicitWidth + laneGap * 2 + 144 + outerMargin * 2
        : content.implicitWidth + 24
    implicitHeight: requestedIconSize + 38

    ProfileState {
        id: profileState
        configuration: root.configuration
        transitionGuard: () => !appearanceState.dirty
    }
    AppearanceState {
        id: appearanceState
        configuration: root.presentation.appearance
        scopeKey: profileState.activeProfileId
        writeAppearance: (next, scope, signature) => {
            if (scope !== profileState.activeProfileId || signature !== appearanceState.signature) return false;
            return profileState.commitPresentation({appearance: {appearanceJSON: next}}, scope, profileState.revision);
        }
    }
    QtObject {
        id: calendarContext
        readonly property var configuration: ({calendarEvents: root.presentation.calendarEvents})
        readonly property date now: root.now
        readonly property color foreground: root.foreground
        readonly property color muted: root.muted
    }
    function widgetVisible(id) { const widget = presentation.widgets.find(entry => entry.id === id); return Boolean(widget && widget.visible); }
    function mediaText(value, limit) { return musicControls.mediaState.boundedText(value, limit); }
    function openWidget(id) {
        if (!widgetVisible(id)) return false;
        if (id === "clock") calendarPopup.open();
        else if (id === "pomodoro") pomodoroPopup.open();
        else if (id === "music") musicPopup.open();
        else if (id === "systemBattery") batteryPopup.open();
        else { selectedIntegration = id; integrationPopup.open(); }
        return true;
    }
    function closeContext() {
        taskMenu.close(); addDialog.close();
        calendarPopup.close(); pomodoroPopup.close(); musicPopup.close(); batteryPopup.close(); integrationPopup.close();
        menuRow = -1; menuData = {}; appInput.clear();
    }
    Connections {
        target: profileState
        function onActiveProfileIdChanged() {
            if (!root.ready) return;
            root.closeContext();
            const scope = profileState.activeProfileId;
            Qt.callLater(() => {
                if (root && root.ready && settings && profileState && appearanceState
                    && settings.visible && scope === profileState.activeProfileId) appearanceState.begin();
            });
        }
    }
    onPresentationChanged: if (ready) {
        if (!widgetVisible("clock")) calendarPopup.close();
        if (!widgetVisible("pomodoro")) pomodoroPopup.close();
        if (!widgetVisible("music")) musicPopup.close();
        if (!widgetVisible("systemBattery")) batteryPopup.close();
        if (!widgetVisible(selectedIntegration)) integrationPopup.close();
    }
    onLauncherSnapshotChanged: if (ready) reloadLaunchers()
    // Use Qt's URL semantics for identity; keep the validated saved spelling.
    function launcherKey(url) { return String(Qt.resolvedUrl(url)); }
    function reloadLaunchers() {
        const nativeKeys = Array.from(tasks.launcherList).map(launcherKey);
        const savedKeys = presentation.launchers.map(launcherKey).filter((key, index, keys) => keys.indexOf(key) === index);
        if (JSON.stringify(nativeKeys) !== JSON.stringify(savedKeys)) tasks.launcherList = Profiles.copy(presentation.launchers);
    }
    function saveLaunchers(value, scope, revision) {
        const saved = profileState.commitPresentation({launchers: value}, scope, revision);
        if (!saved) { reloadLaunchers(); notice = profileState.error; }
        return saved;
    }

    function activateTask(row) {
        if (row < 0 || row >= tasks.count) return;
        const index = tasks.makeModelIndex(row);
        if (tasks.data(index, TaskManager.AbstractTasksModel.IsActive) && tasks.data(index, TaskManager.AbstractTasksModel.IsMinimizable))
            tasks.requestToggleMinimized(index);
        else tasks.requestActivate(index);
    }
    function addLauncher(input, expectedScope, expectedRevision) {
        const scope = expectedScope === undefined ? profileState.activeProfileId : expectedScope;
        const revision = expectedRevision === undefined ? profileState.revision : expectedRevision;
        const url = Logic.launcherUrl(input);
        if (!profileState.writable || scope !== profileState.activeProfileId || revision !== profileState.revision) return false;
        const original = Profiles.copy(presentation.launchers);
        const before = Array.from(tasks.launcherList);
        if (!Profiles.validLauncher(url) || original.length >= 32 || !tasks.requestAddLauncher(url)) {
            notice = qsTr("Não foi possível fixar. Use um arquivo .desktop instalado.");
            return false;
        }
        const beforeKeys = before.map(launcherKey), originalKeys = original.map(launcherKey);
        const additions = Array.from(tasks.launcherList).filter(value => beforeKeys.indexOf(launcherKey(value)) === -1 && originalKeys.indexOf(launcherKey(value)) === -1)
            .map(value => launcherKey(value) === launcherKey(url) ? url : value);
        if (!additions.every(Profiles.validLauncher) || !saveLaunchers(original.concat(additions), scope, revision)) { reloadLaunchers(); return false; }
        notice = "";
        return true;
    }
    function moveTask(from, to) {
        const scope = profileState.activeProfileId, revision = profileState.revision;
        if (!profileState.writable) return false;
        const original = Profiles.copy(presentation.launchers);
        const before = Array.from(tasks.launcherList);
        if (from < 0 || to < 0 || from >= tasks.count || to >= tasks.count) return false;
        const changed = tasks.move(from, to);
        tasks.syncLaunchers();
        if (!changed) return false;
        const originalKeys = original.map(launcherKey), beforeKeys = before.map(launcherKey);
        const orderedKeys = Array.from(tasks.launcherList).map(launcherKey)
            .filter((key, index, keys) => originalKeys.indexOf(key) !== -1 && keys.indexOf(key) === index);
        const ordered = [];
        for (const key of orderedKeys)
            for (const url of original) if (launcherKey(url) === key) ordered.push(url);
        const candidate = original.map(url => beforeKeys.indexOf(launcherKey(url)) !== -1 && orderedKeys.indexOf(launcherKey(url)) !== -1 ? ordered.shift() : url);
        return saveLaunchers(candidate, scope, revision);
    }
    function removeLauncher(url, expectedScope, expectedRevision) {
        const scope = expectedScope === undefined ? profileState.activeProfileId : expectedScope;
        const revision = expectedRevision === undefined ? profileState.revision : expectedRevision;
        if (!profileState.writable || scope !== profileState.activeProfileId || revision !== profileState.revision) return false;
        const original = Profiles.copy(presentation.launchers);
        const before = Array.from(tasks.launcherList);
        if (!tasks.requestRemoveLauncher(url)) return false;
        const after = Array.from(tasks.launcherList);
        const afterKeys = after.map(launcherKey);
        const removed = before.map(launcherKey).filter(key => afterKeys.indexOf(key) === -1);
        return saveLaunchers(original.filter(value => removed.indexOf(launcherKey(value)) === -1), scope, revision);
    }
    function showTaskMenu(row, data) {
        captureTaskMenu(row, data, null);
        taskMenu.open();
    }
    function captureTaskMenu(row, data, sourceItem) {
        // Capture identity: model rows may change while a menu is open.
        menuRow = row;
        menuData = { title: data.AppName || data.display, url: String(data.LauncherUrlWithoutIcon || ""),
            scope: profileState.activeProfileId, revision: profileState.revision,
            window: Boolean(data.IsWindow), pinned: Boolean(data.HasLauncher || data.IsLauncher),
            ids: JSON.stringify(data.WinIdList || []), minimizable: Boolean(data.IsMinimizable),
            closable: Boolean(data.IsClosable), canLaunch: Boolean(data.CanLaunchNewInstance) };
        if (sourceItem) menuAnchorX = sourceItem.mapToItem(root, sourceItem.width / 2, 0).x;
        else menuAnchorX = (row + 1) * (root.tileSize + 16);
        return menuAnchorX;
    }
    function showTaskMenuAt(row, data, sourceItem) {
        captureTaskMenu(row, data, sourceItem);
        taskMenu.open();
    }
    function menuIndex() {
        if (menuData.scope !== profileState.activeProfileId || menuData.revision !== profileState.revision) return null;
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
    function revealInViewport(control) {
        if (!localEventsActive || !control || !control.activeFocus) return;
        const point = control.mapToItem(content, 0, 0);
        const maximum = Math.max(0, viewport.contentWidth - viewport.width);
        if (point.x < viewport.contentX) viewport.contentX = Math.max(0, point.x);
        else if (point.x + control.width > viewport.contentX + viewport.width)
            viewport.contentX = Math.min(maximum, control.width > viewport.width ? point.x : point.x + control.width - viewport.width);
    }

    TaskManager.TasksModel {
        id: tasks
        groupMode: TaskManager.TasksModel.GroupDisabled
        sortMode: TaskManager.TasksModel.SortManual
        separateLaunchers: false
        launchInPlace: true
        hideActivatedLaunchers: true
        filterByCurrentVirtualDesktop: root.presentation.currentDesktopOnly
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
        active: root.widgetVisible("quota") || root.widgetVisible("peripherals") || root.widgetVisible("recording")
    }
    Component.onCompleted: { ready = true; reloadLaunchers(); }
    Component.onDestruction: ready = false
    Mpris.Mpris2Model { id: media }
    property var mediaSource: media
    readonly property var player: mediaSource ? mediaSource.currentPlayer : null
    SystemBattery {
        id: power
        objectName: "systemBattery"
        active: root.widgetVisible("systemBattery")
    }
    readonly property string powerSubtitle: power.status === "absent" ? qsTr("Sem bateria do sistema")
        : power.status === "loading" ? qsTr("Lendo bateria…")
        : !power.percentKnown ? qsTr("Bateria indisponível")
        : power.charging === "charging" ? qsTr("Carregando")
        : power.onBattery === "ac" ? qsTr("Na tomada")
        : power.onBattery === "battery" ? qsTr("Na bateria") : qsTr("Energia desconhecida")
    Pomodoro {
        id: focusTimer
        configuration: root.configuration
        onFinished: {
            const accepted = localEventState.submit({
                kind: "completion", key: "pomodoro:completion", scope: "global",
                title: root.configuration.timerBreak ? qsTr("Foco concluído") : qsTr("Pausa concluída"),
                detail: root.configuration.timerBreak ? qsTr("Hora de uma pausa!") : qsTr("Pronto para focar?")
            }, focusTimer.now);
            if (!accepted) root.notice = root.configuration.timerBreak
                ? qsTr("Foco concluído. Hora de uma pausa!") : qsTr("Pausa concluída. Pronto para focar?");
        }
    }
    EventState { id: localEventState; enabled: root.localEventsActive }
    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.now = new Date() }
    Timer { interval: 8000; running: root.notice.length > 0; onTriggered: root.notice = "" }
    Rectangle {
        objectName: "dockSurface"
        anchors.fill: parent
        radius: appearanceState.effective.tokens.radius
        color: root.surface
        opacity: appearanceState.overridden ? appearanceState.effective.tokens.opacity : 1
        border.width: 1
        border.color: appearanceState.effective.tokens.border
        Behavior on color { ColorAnimation { duration: root.motion } }
        Rectangle { x: 16; y: 1; width: parent.width - 32; height: 1; color: root.light ? "#ffffff" : "#526482"; opacity: 0.55 }
    }
    Item {
        id: settingsLane
        objectName: "localSettingsLane"
        x: root.outerMargin
        y: root.outerMargin
        width: root.settingsLaneWidth
        height: Math.max(0, root.height - root.outerMargin * 2)
        visible: root.localEventsActive
        z: 3
    }
    Item {
        id: settingsDividerLane
        objectName: "localSettingsDividerLane"
        x: settingsLane.x + settingsLane.width
        y: settingsLane.y
        width: root.laneGap
        height: settingsLane.height
        visible: root.localEventsActive
        z: 3
    }
    Tile {
        id: settingsButton
        objectName: "settingsButton"
        parent: root.localEventsActive ? settingsLane : settingsPlaceholder
        anchors.verticalCenter: parent.verticalCenter
        iconSource: Qt.resolvedUrl("../images/orla.svg")
        iconSize: root.tileSize - 10
        foreground: root.accent; accent: root.accent; animationDuration: root.motion
        tooltip: qsTr("Personalizar Orla Dock")
        onClicked: settings.open()
    }
    Rectangle {
        id: settingsDivider
        parent: root.localEventsActive ? settingsDividerLane : settingsDividerPlaceholder
        anchors.centerIn: parent
        width: 1
        height: 30
        color: root.muted
        opacity: 0.3
    }
    Flickable {
        id: viewport
        objectName: "appsViewport"
        x: root.localEventsActive ? settingsLane.x + settingsLane.width + root.laneGap : root.outerMargin
        y: root.outerMargin
        width: root.centerViewportWidth
        height: Math.max(0, root.height - root.outerMargin * 2)
        contentWidth: content.width
        contentHeight: height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.HorizontalFlick
        Controls.ScrollBar.horizontal: Controls.ScrollBar { policy: Controls.ScrollBar.AsNeeded }
        Row {
            id: content
            objectName: "dockContent"
            height: viewport.height
            spacing: appearanceState.effective.tokens.spacing
            Item {
                id: settingsPlaceholder
                objectName: "settingsPlaceholder"
                visible: !root.localEventsActive
                width: root.localEventsActive ? 0 : settingsButton.implicitWidth
                height: parent.height
            }
            Item {
                id: settingsDividerPlaceholder
                objectName: "settingsDividerPlaceholder"
                visible: !root.localEventsActive
                width: root.localEventsActive ? 0 : 1
                height: parent.height
            }
            Repeater {
                id: taskRepeater
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
                    onActiveFocusChanged: if (activeFocus) root.revealInViewport(taskTile)
                    onClicked: root.activateTask(index)
                    onPressAndHold: root.showTaskMenuAt(index, model, taskTile)
                    Keys.onMenuPressed: root.showTaskMenuAt(index, model, taskTile)
                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_F10 && event.modifiers === Qt.ShiftModifier) {
                            root.showTaskMenuAt(index, model, taskTile);
                            event.accepted = true;
                        }
                    }
                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: root.showTaskMenuAt(taskTile.index, taskTile.model, taskTile) }
                }
            }
            Tile {
                objectName: "addButton"
                anchors.verticalCenter: parent.verticalCenter
                iconSource: "list-add"
                iconSize: Math.max(12, root.tileSize - 16)
                foreground: root.muted; accent: root.accent; animationDuration: root.motion
                tooltip: qsTr("Fixar aplicativo · ou arraste um app para o dock")
                onActiveFocusChanged: if (activeFocus) root.revealInViewport(this)
                onClicked: addDialog.open()
            }
            Rectangle { objectName: "widgetDivider"; anchors.verticalCenter: parent.verticalCenter; visible: widgetStrip.visible; width: 1; height: 30; color: root.muted; opacity: 0.3 }
            WidgetStrip { id: widgetStrip; objectName: "widgetStrip"; dock: root; height: parent.height }

        }
    }
    EventSurface {
        id: localEventSurface
        x: root.width - root.outerMargin - width
        y: root.outerMargin
        width: root.eventSlotWidth
        height: Math.max(0, root.height - root.outerMargin * 2)
        visible: root.localEventsActive
        z: 3
        eventState: localEventState
        surfaceColor: root.surface
        borderColor: appearanceState.effective.tokens.border
        foregroundColor: root.foreground
        mutedColor: root.muted
        accentColor: root.accent
        animationDuration: root.motion
    }
    DropArea {
        anchors.fill: parent
        onDropped: drop => {
            let accepted = false;
            for (const url of drop.urls) accepted = root.addLauncher(String(url)) || accepted;
            if (accepted) drop.acceptProposedAction();
        }
        Rectangle { anchors.fill: parent; radius: appearanceState.effective.tokens.radius; visible: parent.containsDrag; color: "transparent"; border.color: root.accent; border.width: 2 }
    }
    Controls.Menu {
        id: taskMenu
        objectName: "taskContextMenu"
        popupType: Controls.Popup.Window
        x: Math.max(0, Math.min(root.width - width, root.menuAnchorX - width / 2))
        y: root.popAbove ? -height - 8 : root.height + 8
        Controls.MenuItem { text: root.menuData.title || ""; enabled: false }
        Controls.MenuSeparator {}
        Controls.MenuItem {
            text: root.menuData.pinned ? qsTr("Desafixar") : qsTr("Fixar no dock")
            enabled: Boolean(root.menuData.url)
            onTriggered: { if (root.menuData.pinned) root.removeLauncher(root.menuData.url, root.menuData.scope, root.menuData.revision); else root.addLauncher(root.menuData.url, root.menuData.scope, root.menuData.revision); }
        }
        Controls.MenuItem { text: qsTr("Nova janela"); enabled: Boolean(root.menuData.canLaunch); onTriggered: { const index = root.menuIndex(); if (index) tasks.requestNewInstance(index); } }
        Controls.MenuItem { text: qsTr("Mover para a esquerda"); enabled: root.menuRow > 0; onTriggered: root.moveMenuTask(-1) }
        Controls.MenuItem { text: qsTr("Mover para a direita"); enabled: root.menuRow < tasks.count - 1; onTriggered: root.moveMenuTask(1) }
        Controls.MenuSeparator { visible: Boolean(root.menuData.window) }
        Controls.MenuItem { text: qsTr("Minimizar / restaurar"); visible: Boolean(root.menuData.window); enabled: Boolean(root.menuData.minimizable); onTriggered: { const index = root.menuIndex(); if (index) tasks.requestToggleMinimized(index); } }
        Controls.MenuItem { text: qsTr("Fechar janela"); visible: Boolean(root.menuData.window); enabled: Boolean(root.menuData.closable); onTriggered: { const index = root.menuIndex(); if (index) tasks.requestClose(index); } }
    }
    // Keep the editor legible even when the draft uses low-contrast dock colors.
    Item {
        id: settingsAnchor
        anchors.fill: parent
        readonly property bool popAbove: root.popAbove
        readonly property bool light: root.presentation.appearance.theme === "paper"
        readonly property color surface: light ? "#f4f0e8" : "#111923"
        readonly property color foreground: light ? "#252b35" : "#edf1f9"
        readonly property color accent: light ? "#167361" : "#69d7c2"
    }
    DockPopup {
        id: settings
        objectName: "settingsPopup"
        // Screen.height bounds the current monitor; desktopAvailableHeight
        // excludes reserved areas but describes the entire virtual desktop.
        property real heightBudget: Math.max(1, Math.min(root.Screen.height || 640, root.Screen.desktopAvailableHeight || 640) - 40)
        height: Math.min(implicitHeight, heightBudget)
        dock: settingsAnchor
        title: qsTr("Seu dock, do seu jeito")
        onAboutToShow: appearanceState.begin()
        onClosed: appearanceState.cancel()
        SettingsContents {
            configuration: root.configuration
            profiles: profileState
            resetTimer: focusTimer.reset
            appearance: appearanceState
            onAppearanceCanceled: settings.close()
        }
    }
    DockPopup {
        id: addDialog
        objectName: "addPopup"
        property string scope: ""
        property int revision: -1
        dock: root
        title: qsTr("Fixar aplicativo")
        onOpened: { scope = profileState.activeProfileId; revision = profileState.revision; appInput.forceActiveFocus(); }
        ColumnLayout {
            Controls.Label { Layout.fillWidth: true; text: qsTr("Arraste um aplicativo do menu do KDE para o dock, ou informe o ID abaixo."); wrapMode: Text.WordWrap }
            Controls.TextField { id: appInput; objectName: "launcherInput"; Layout.fillWidth: true; placeholderText: "org.kde.dolphin.desktop"; onAccepted: pinButton.clicked() }
            Controls.Label { Layout.fillWidth: true; text: root.notice; visible: text.length > 0; wrapMode: Text.WordWrap }
            Controls.Button { id: pinButton; text: qsTr("Fixar aplicativo"); enabled: appInput.text.trim().length > 0; onClicked: if (root.addLauncher(appInput.text, addDialog.scope, addDialog.revision)) { appInput.clear(); addDialog.close(); } }
        }
    }
    DockPopup {
        id: calendarPopup
        objectName: "calendarPopup"
        dock: root
        title: Qt.formatDate(root.now, "MMMM yyyy")
        CalendarAgenda { objectName: "calendarAgenda"; dock: calendarContext }
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
        title: qsTr("Sua música")
        MediaControls {
            id: musicControls
            objectName: "mediaControls"
            Layout.fillWidth: true
            media: root.mediaSource
            foreground: root.foreground
            muted: root.muted
        }
    }
    DockPopup {
        id: batteryPopup
        dock: root
        title: qsTr("Energia")
        ColumnLayout {
            Controls.Label { Layout.fillWidth: true; text: power.summary; font.bold: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
            Controls.Label { Layout.fillWidth: true; text: root.powerSubtitle; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
            Controls.Label {
                Layout.fillWidth: true
                visible: power.estimatedTimeKind !== "unknown"
                text: power.estimatedTimeKind === "full"
                    ? qsTr("Estimativa até completar: %1 min").arg(Math.ceil(power.estimatedTimeSeconds / 60))
                    : qsTr("Estimativa restante: %1 min").arg(Math.ceil(power.estimatedTimeSeconds / 60))
                wrapMode: Text.WordWrap; textFormat: Text.PlainText
            }
            Controls.Label {
                Layout.fillWidth: true
                text: qsTr("Bateria do computador. Baterias de periféricos continuam no PeriGauge.")
                wrapMode: Text.WordWrap; textFormat: Text.PlainText; opacity: 0.65
            }
        }
    }
    Controls.ToolTip { parent: root; visible: root.notice.length > 0 && !addDialog.opened; text: root.notice; timeout: 8000 }
}
