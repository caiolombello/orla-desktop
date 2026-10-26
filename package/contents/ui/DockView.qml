import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import org.kde.taskmanager as TaskManager
import org.kde.plasma.private.mpris as Mpris
import "../code/Logic.js" as Logic
import "../code/Profiles.js" as Profiles
import "../code/Style.js" as Style
import "../controlcenter" as SharedControls

Item {
    id: root
    objectName: "dock"
    required property var configuration
    property bool popAbove: false
    property bool nativePopups: false
    // Set by the panel host when the Orla Plasma theme gives the panel frame
    // the slab's shape (KWin blurs behind it) and when dialogs get theme glass.
    property bool systemGlass: false
    property bool systemPopupGlass: false
    // Space between the dock and the panel frame, {left, top, right, bottom},
    // as measured by the host; null assumes Breeze's 4 px panel margins.
    property var systemGlassMargins: null
    // The dock's screen in global coordinates, set by the panel host; the
    // event island centers on it.
    property rect screenGeometry: Qt.rect(0, 0, -1, -1)
    readonly property var frameMargins: systemGlassMargins || ({left: 4, top: 4, right: 4, bottom: 4})
    readonly property rect glassFrame: Qt.rect(-frameMargins.left, -frameMargins.top,
        width + frameMargins.left + frameMargins.right, height + frameMargins.top + frameMargins.bottom)
    property date now: new Date()
    property string notice: ""
    property var menuData: ({})
    property int menuRow: -1
    property real menuAnchorX: 0
    property bool ready: false
    property alias tasksModel: tasks
    property alias pomodoro: focusTimer
    property alias integrations: localIntegrations
    property alias addonsSession: addonsSession
    property var addonTransportOverride: null
    property alias appearance: appearanceState
    property alias appearancePreset: appearancePresetState
    property alias systemBattery: power
    property alias profiles: profileState
    property alias taskDrag: taskDragState
    property alias contexts: contextState
    property alias contextBindings: contextBindingsState
    property alias autoContextProfiles: autoContextState
    property alias desktopSwitch: desktopSwitchState
    property var desktopSwitchBackendOverride: null
    // Qualified with the final adapter against a private Qt/KDE service fixture.
    property bool desktopSwitchWriterQualified: true
    property bool contextCommandsVisible: false
    readonly property bool nativeDesktopSwitchBackendLoaded: desktopSwitchBackendLoader.item !== null
    property var contextSnapshotOverride: null
    property var controlCenterBackendOverride: null
    property var audioBackendOverride: null
    property var brightnessBackendOverride: null
    property var doNotDisturbBackendOverride: null
    property var microphoneBackendOverride: null
    property var powerProfileBackendOverride: null
    property var wifiBackendOverride: null
    property var bluetoothBackendOverride: null
    property var lastStableDockControl: null
    readonly property bool nativeContextSourceLoaded: contextSourceLoader.item !== null
    // The area switcher lives in Settings › Contextos and in the Control Center.
    readonly property bool desktopCommandsShown: (settings.visible && contextCommandsVisible && settingsContents.contextsTabActive)
        || controlCenterPopup.visible
    readonly property bool nativeControlCenterBackendLoaded: nativeControlCenterBackend.item !== null
    readonly property bool nativeAudioBackendLoaded: nativeAudioBackend.item !== null
    readonly property var presentation: profileState.effective
    readonly property var displayWidgets: appearancePresetState.previewWidgets || presentation.widgets
    readonly property string launcherSnapshot: JSON.stringify(presentation.launchers)
    property bool launcherOrderBusy: false
    property bool launcherReloadPending: false
    property string selectedIntegration: "quota"
    readonly property bool light: appearanceState.effective.baseTheme === "paper"
    readonly property color foreground: appearanceState.effective.tokens.foreground
    readonly property color muted: appearanceState.effective.tokens.muted
    readonly property color accent: appearanceState.effective.tokens.accent
    readonly property color surface: appearanceState.overridden ? appearanceState.effective.tokens.surface
        : light ? Style.dockThemes.paper.surface : presentation.appearance.theme === "midnight" ? Style.dockThemes.midnight.surface
        : Style.alpha(Style.dockThemes.glass.surface, Style.dockThemes.glass.opacity)
    // Custom tokens can make any theme light; depth effects follow the real surface.
    readonly property bool lightSurface: Style.luminance(surface) > 0.4
    // Popups and menus follow the system color scheme's lightness (see DESIGN_SYSTEM.md).
    readonly property var popupScheme: Style.scheme(Style.schemeFor(systemColors.Kirigami.Theme.backgroundColor))
    readonly property int motion: appearanceState.effective.tokens.reducedMotion ? 0 : Kirigami.Units.shortDuration
    readonly property int requestedIconSize: appearanceState.effective.tokens.iconSize
    readonly property int tileSize: Math.max(16, Math.min(requestedIconSize, height > 0 ? height - 36 : requestedIconSize))
    readonly property int outerMargin: 10
    readonly property int laneGap: 6
    readonly property bool localEventsRequested: Boolean(configuration.showLocalToasts)
        || Boolean(presentation.showAudioHud)
    readonly property int settingsLaneWidth: settingsButton.implicitWidth
    readonly property int minimumTaskWidth: tileSize + 16
    // The lane for slots: inside the glass by its inset when frosted, else by outerMargin.
    readonly property real laneStart: systemGlass ? dockSurface.x + Style.dock.glassInset : outerMargin
    readonly property real laneEnd: systemGlass ? dockSurface.x + dockSurface.width - Style.dock.glassInset : width - outerMargin
    readonly property int innerWidth: Math.max(0, Math.floor(laneEnd - laneStart))
    readonly property int candidateEventSlotWidth: Math.min(224, Math.floor(innerWidth * 0.30),
        Math.max(0, innerWidth - settingsLaneWidth - laneGap * 2 - minimumTaskWidth))
    readonly property bool localEventsProfileReady: profileState.writable
        && (profileState.initialized || profileState.savedJSON === "")
    // Events go either to the island at the top of the screen or to a slot in the dock.
    readonly property bool eventIslandActive: Boolean(configuration.eventIsland)
        && localEventsRequested && localEventsProfileReady
    readonly property bool localEventsActive: localEventsRequested && localEventsProfileReady
        && !eventIslandActive && candidateEventSlotWidth >= 48
    readonly property var eventIslandState: localEventState
    readonly property int eventSlotWidth: localEventsActive ? candidateEventSlotWidth : 0
    readonly property int centerViewportWidth: innerWidth
    // The legacy lane reserves 4 px after the content; the glass skips it. The
    // theme's frame is symmetric, so the frosted slab gives the reserve up.
    readonly property int trailingReserve: systemGlass ? 0 : 4
    // Frosted, ask for exactly the slab the frame will draw: content, glass insets
    // and the theme band, less what the panel already adds around the dock.
    implicitWidth: systemGlass
        ? content.implicitWidth + 2 * (Style.dock.glassInset + Style.dock.systemGlassBandX)
            - frameMargins.left - frameMargins.right
        : content.implicitWidth + root.outerMargin * 2 + trailingReserve
    implicitHeight: requestedIconSize + 38

    ProfileState {
        id: profileState
        configuration: root.configuration
        transitionGuard: () => !appearanceState.dirty && !appearancePresetState.dirty
    }
    TaskDragState {
        id: taskDragState
        profiles: profileState
        viewActive: root.ready && root.visible && root.enabled && !root.popupOpen
        readOrder: () => root.taskOrder()
        commitMove: (from, to, guard) => root.moveTask(from, to, guard)
    }
    property string taskDragGeometry: ""
    property int taskFocusEpoch: 0
    function dragGeometry() {
        const point = viewport.mapToItem(root.Window.window.contentItem, 0, 0);
        return JSON.stringify([point.x, point.y, viewport.width, viewport.height,
            viewport.contentX, root.eventSlotWidth, localEventSurface.visible]);
    }
    function insideTaskViewport(point) {
        const window = root.Window.window;
        if (!window || viewport.moving) return false;
        const position = viewport.mapFromItem(window.contentItem, point.x, point.y);
        const usable = viewport.width - (localEventSurface.visible ? root.eventSlotWidth : 0);
        return position.x >= 0 && position.x < usable && position.y >= 0 && position.y < viewport.height;
    }
    function taskAtPoint(point) {
        const window = root.Window.window;
        if (!insideTaskViewport(point)) return null;
        const usable = viewport.width - (localEventSurface.visible ? root.eventSlotWidth : 0);
        const rows = taskOrder();
        if (rows === null) return null;
        for (let row = 0; row < rows.length; ++row) {
            const tile = taskRepeater.itemAt(row);
            if (!tile || !tile.visible || !tile.enabled) continue;
            const top = tile.mapToItem(viewport, 0, 0);
            if (top.x < 0 || top.x + tile.width > usable || top.y < 0 || top.y + tile.height > viewport.height) continue;
            const local = tile.mapFromItem(window.contentItem, point.x, point.y);
            if (local.x >= 0 && local.x < tile.width && local.y >= 0 && local.y < tile.height)
                return {tile: tile, identity: rows[row].identity, after: local.x >= tile.width / 2};
        }
        return null;
    }
    function beginTaskDrag(tile, point) {
        if (launcherOrderBusy || viewport.moving) return false;
        const target = taskAtPoint(point);
        if (!target || target.tile !== tile || !taskDragState.begin(target.identity)) return false;
        taskDragGeometry = dragGeometry();
        return true;
    }
    function updateTaskDrag(point) {
        if (taskDragGeometry !== dragGeometry() || !insideTaskViewport(point)) { taskDragState.cancel(); return; }
        const target = taskAtPoint(point);
        // Crossing a slot gap clears the marker without ending a valid gesture.
        taskDragState.update(target ? target.identity : "", target ? target.after : false);
    }
    function finishTaskDrag(point, sourceItem) {
        updateTaskDrag(point);
        const captured = taskDragState.intent;
        const window = root.Window.window;
        const restore = captured !== null && window && window.active && sourceItem.activeFocus;
        const visualFocus = sourceItem.visualFocus;
        const accepted = taskDragState.finish();
        if (!accepted || !restore) return;
        const focused = window.activeFocusItem;
        if (focused && focused !== sourceItem && focused !== window.contentItem) return;
        const generation = taskDragState.generation, epoch = taskFocusEpoch;
        Qt.callLater(() => {
            if (root.Window.window !== window || !window.active || !root.visible || !root.enabled || root.popupOpen
                || taskDragState.generation !== generation || taskFocusEpoch !== epoch || window.activeFocusItem !== focused) return;
            const rows = taskOrder();
            const row = rows === null ? -1 : rows.findIndex(entry => entry.identity === captured.identity);
            const tile = row >= 0 ? taskRepeater.itemAt(row) : null;
            if (tile && tile.visible && tile.enabled) tile.forceActiveFocus(visualFocus ? Qt.TabFocusReason : Qt.MouseFocusReason);
        });
    }
    function invalidateTaskDrag() {
        if (taskDragState.pressed && !taskDragState.committing) taskDragState.cancel();
    }
    function checkTaskDragGeometry() {
        if (taskDragState.pressed && taskDragGeometry !== dragGeometry()) invalidateTaskDrag();
    }
    function taskDropTile() {
        if (!taskDragState.active || !taskDragState.intent || !taskDragState.destination.length) return null;
        const row = taskDragState.intent.rows.findIndex(entry => entry.identity === taskDragState.destination);
        return row >= 0 ? taskRepeater.itemAt(row) : null;
    }
    Connections {
        target: tasks
        function onRowsAboutToBeInserted() { root.invalidateTaskDrag(); }
        function onRowsAboutToBeRemoved() { root.invalidateTaskDrag(); }
        function onRowsAboutToBeMoved() { root.invalidateTaskDrag(); }
        function onModelAboutToBeReset() { root.invalidateTaskDrag(); }
        function onLayoutAboutToBeChanged() { root.invalidateTaskDrag(); }
        function onDataChanged() {
            if (taskDragState.pressed && !taskDragState.committing && !taskDragState.releaseValid(taskDragState.intent))
                taskDragState.cancel();
        }
    }
    Keys.onEscapePressed: event => {
        if (taskDragState.pressed) { taskDragState.cancel(); event.accepted = true; }
    }
    readonly property var unavailableContextSnapshot: ({
        outputName: "",
        activity: {status: "unavailable", currentId: "", ids: [], names: []},
        desktop: {status: "unavailable", currentId: "", ids: [], names: []}
    })
    Loader {
        id: contextSourceLoader
        objectName: "contextSourceLoader"
        active: root.contextSnapshotOverride === null
            && (autoContextState.observing || (settings.visible && settingsContents.contextsTabActive)
                || controlCenterPopup.visible)
        source: active ? Qt.resolvedUrl("KdeContextSource.qml") : ""
    }
    ContextState {
        id: contextState
        objectName: "dockContextState"
        sourceSnapshot: root.contextSnapshotOverride !== null ? root.contextSnapshotOverride
            : contextSourceLoader.item ? contextSourceLoader.item.snapshot : root.unavailableContextSnapshot
    }
    Loader {
        id: desktopSwitchBackendLoader
        objectName: "desktopSwitchBackendLoader"
        active: root.desktopSwitchWriterQualified && root.desktopSwitchBackendOverride === null
            && root.contextSnapshotOverride === null && root.desktopCommandsShown
        source: active ? Qt.resolvedUrl("KdeDesktopSwitchBackend.qml") : ""
        onLoaded: { item.contexts = contextState; item.active = true; }
    }
    DesktopSwitchState {
        id: desktopSwitchState
        objectName: "dockDesktopSwitchState"
        contexts: contextState
        backend: root.desktopSwitchBackendOverride !== null ? root.desktopSwitchBackendOverride : desktopSwitchBackendLoader.item
        active: root.desktopCommandsShown
    }
    ContextBindingsState {
        id: contextBindingsState
        objectName: "dockContextBindingsState"
        configuration: root.configuration
        profiles: profileState
        contexts: contextState
    }
    AutoContextProfileState {
        id: autoContextState
        objectName: "dockAutoContextProfiles"
        configuration: root.configuration
        profiles: profileState
        contexts: contextState
        bindingsState: contextBindingsState
        active: root.ready
        interactionBusy: root.autoContextInteractionBusy
    }
    AppearancePresetState {
        id: appearancePresetState
        profiles: profileState
        appearance: appearanceState
    }
    ThemeFileTransport { id: nativeThemeFileTransport }
    AppearanceState {
        id: appearanceState
        themeFileTransport: nativeThemeFileTransport
        themeFileBlocked: appearancePresetState.dirty
        configuration: root.presentation.appearance
        scopeKey: profileState.activeProfileId
        writeAppearance: (next, scope, signature) => {
            if (scope !== profileState.activeProfileId || signature !== appearanceState.signature) return false;
            return profileState.commitPresentation({appearance: {appearanceJSON: next}}, scope, profileState.revision);
        }
    }
    // Samples the system scheme. Keep it visible: hidden items report black.
    Item {
        id: systemColors
        width: 0
        height: 0
        Kirigami.Theme.inherit: false
        Kirigami.Theme.colorSet: Kirigami.Theme.Window
    }
    // Colors for content inside popups; dock tokens only style the dock body.
    QtObject {
        id: popupContext
        readonly property var configuration: ({calendarEvents: root.presentation.calendarEvents})
        readonly property date now: root.now
        readonly property color foreground: root.popupScheme.text
        readonly property color muted: root.popupScheme.textMuted
        readonly property color accent: root.popupScheme.accent
        readonly property color background: root.popupScheme.surface
    }
    // Floating name label (DockLabel) follows the hovered slot in Plasma.
    property Item labelTarget: null
    readonly property bool popupOpen: settings.visible || addDialog.visible || calendarPopup.visible
        || integrationPopup.visible || controlCenterPopup.visible || pomodoroPopup.visible
        || musicPopup.visible || batteryPopup.visible || nativeTaskMenu.visible || taskMenu.visible
    readonly property bool autoContextInteractionBusy: !ready || popupOpen
        || appearanceState.editing || appearanceState.dirty
        || appearancePresetState.dirty || appearancePresetState.busy
        || settingsContents.widgetDrag !== null
        || taskDragState.pressed || taskDragState.committing
        || launcherOrderBusy || launcherReloadPending || viewport.moving
        || audioControlState.pendingKind.length > 0 || audioControlState.volumeGestureActive
        || brightnessControlState.pendingAny || doNotDisturbState.pending || microphoneState.pending || powerProfileState.pending || wifiState.pending || bluetoothState.pending
        || settings.interactionBusy || addDialog.interactionBusy || calendarPopup.interactionBusy
        || integrationPopup.interactionBusy || pomodoroPopup.interactionBusy
        || musicPopup.interactionBusy || batteryPopup.interactionBusy || nativeTaskMenu.interactionBusy
        || controlCenterPopup.contextSwitchBusy || taskMenu.contextSwitchBusy
    function hoverTile(tile, hovered) {
        if (hovered && !taskDragState.active) labelTarget = tile;
        else if (labelTarget === tile) labelTarget = null;
    }
    Loader {
        objectName: "dockLabelLoader"
        property var labelOwner: root
        active: root.nativePopups
        source: active ? Qt.resolvedUrl("DockLabel.qml") : ""
    }
    Loader {
        objectName: "eventIslandLoader"
        property var islandOwner: root
        active: root.nativePopups && root.eventIslandActive
        source: active ? Qt.resolvedUrl("NativeEventIsland.qml") : ""
    }
    function widgetVisible(id) { const widget = displayWidgets.find(entry => entry.id === id); return Boolean(widget && widget.visible); }
    function mediaText(value, limit) { return musicControls.mediaState.boundedText(value, limit); }
    function openWidget(id, sourceItem) {
        if (!widgetVisible(id)) return false;
        if (id === "clock") calendarPopup.openAt(sourceItem);
        else if (id === "pomodoro") pomodoroPopup.openAt(sourceItem);
        else if (id === "music") musicPopup.openAt(sourceItem);
        else if (id === "systemBattery") batteryPopup.openAt(sourceItem);
        else { selectedIntegration = id; integrationPopup.openAt(sourceItem); }
        return true;
    }
    function closeContext() {
        taskMenu.close(); nativeTaskMenu.close(); addDialog.close();
        calendarPopup.close(); pomodoroPopup.close(); musicPopup.close(); batteryPopup.close(); integrationPopup.close(); controlCenterPopup.closeSession();
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
    onDisplayWidgetsChanged: if (ready) {
        if (!widgetVisible("clock")) calendarPopup.close();
        if (!widgetVisible("pomodoro")) pomodoroPopup.close();
        if (!widgetVisible("music")) musicPopup.close();
        if (!widgetVisible("systemBattery")) batteryPopup.close();
        if (!widgetVisible(selectedIntegration)) integrationPopup.close();
    }
    onLauncherSnapshotChanged: if (ready) reloadLaunchers()
    // Use Qt's URL semantics for identity; keep the validated saved spelling.
    function launcherKey(url) { return String(Qt.resolvedUrl(url)); }
    function taskOrder() {
        const rows = [], seen = [];
        for (let row = 0; row < tasks.count; ++row) {
            const index = tasks.makeModelIndex(row);
            const url = String(tasks.data(index, TaskManager.AbstractTasksModel.LauncherUrlWithoutIcon) || "");
            const window = Boolean(tasks.data(index, TaskManager.AbstractTasksModel.IsWindow));
            const launcher = Boolean(tasks.data(index, TaskManager.AbstractTasksModel.IsLauncher));
            const ids = Array.from(tasks.data(index, TaskManager.AbstractTasksModel.WinIdList) || []).map(String);
            if ((!window && !launcher) || (window && ids.length === 0)) return null;
            const identity = JSON.stringify(window ? ["window", ids, url] : ["launcher", url]);
            if (seen.indexOf(identity) !== -1) return null;
            seen.push(identity);
            // KDE resolves preferred applications and equivalent launcher URLs.
            rows.push({identity: identity, rank: tasks.launcherPosition(url), order: row});
        }
        return rows;
    }
    function taskTopology(rows) {
        return rows === null ? "" : JSON.stringify(rows.map(row => JSON.stringify([row.identity, row.rank])).sort());
    }
    function taskMembership(rows) {
        return rows === null ? "" : JSON.stringify(rows.map(row => row.identity).sort());
    }
    function finishLauncherOrder() {
        launcherOrderBusy = false;
        if (launcherReloadPending) Qt.callLater(root.reloadLaunchers);
    }
    function reloadLaunchers() {
        if (launcherOrderBusy) { launcherReloadPending = true; return; }
        launcherReloadPending = false;
        launcherOrderBusy = true;
        const scope = profileState.activeProfileId, revision = profileState.revision;
        const current = () => scope === profileState.activeProfileId && revision === profileState.revision;
        try {
            const nativeKeys = Array.from(tasks.launcherList).map(launcherKey);
            const savedKeys = presentation.launchers.map(launcherKey).filter((key, index, keys) => keys.indexOf(key) === index);
            if (JSON.stringify(nativeKeys) !== JSON.stringify(savedKeys)) tasks.launcherList = Profiles.copy(presentation.launchers);
            if (!current()) { launcherReloadPending = true; return; }
            const rows = taskOrder();
            if (rows === null) return;
            const topology = taskTopology(rows);
            const pinned = rows.filter(row => row.rank >= 0).sort((left, right) => left.rank - right.rank || left.order - right.order);
            const target = rows.map(row => row.rank >= 0 ? pinned.shift().identity : row.identity);
            for (let position = 0; position < target.length; ++position) {
                if (!current()) { launcherReloadPending = true; return; }
                const before = taskOrder();
                if (taskTopology(before) !== topology) { launcherReloadPending = true; return; }
                const from = before.findIndex(row => row.identity === target[position]);
                if (from === position) continue;
                if (from < position || !tasks.move(from, position)) {
                    notice = qsTr("Não foi possível restaurar a ordem dos apps. Tente novamente.");
                    return;
                }
                if (!current()) { launcherReloadPending = true; return; }
                const after = taskOrder();
                if (taskTopology(after) !== topology) { launcherReloadPending = true; return; }
                if (after.slice(0, position + 1).some((row, index) => row.identity !== target[index])) {
                    notice = qsTr("A lista de janelas mudou. Tente organizar os apps novamente.");
                    return;
                }
            }
            // Authority flows from the saved list into the manual map here.
            // syncLaunchers exports the opposite direction and can drop hidden order.
        } finally { finishLauncherOrder(); }
    }
    function saveLaunchers(value, scope, revision, continuationGuard) {
        const saved = profileState.commitPresentation({launchers: value}, scope, revision, continuationGuard);
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
    function moveTask(from, to, continuationGuard) {
        const scope = profileState.activeProfileId, revision = profileState.revision;
        if (!profileState.writable || launcherOrderBusy) return false;
        const allowed = () => {
            try { return continuationGuard === undefined || (typeof continuationGuard === "function" && continuationGuard() === true); }
            catch (_) { return false; }
        };
        if (!allowed()) return false;
        const original = Profiles.copy(presentation.launchers);
        const before = Array.from(tasks.launcherList);
        if (from < 0 || to < 0 || from >= tasks.count || to >= tasks.count) return false;
        const beforeRows = taskOrder();
        if (beforeRows === null) return false;
        const expected = beforeRows.map(row => row.identity);
        expected.splice(to, 0, expected.splice(from, 1)[0]);
        const matchesMove = () => {
            const rows = taskOrder();
            return rows !== null && JSON.stringify(rows.map(row => row.identity)) === JSON.stringify(expected);
        };
        launcherOrderBusy = true;
        const current = () => scope === profileState.activeProfileId && revision === profileState.revision;
        try {
            if (!tasks.move(from, to)) return false;
            if (!current()) {
                launcherReloadPending = true;
                notice = qsTr("A configuração mudou. Tente organizar os apps novamente.");
                return false;
            }
            if (!allowed() || !matchesMove()) {
                launcherReloadPending = true;
                notice = qsTr("A lista de janelas mudou. Tente organizar os apps novamente.");
                return false;
            }
            tasks.syncLaunchers();
            if (!current() || !allowed() || !matchesMove()) {
                launcherReloadPending = true;
                notice = qsTr("A lista de janelas mudou. Tente organizar os apps novamente.");
                return false;
            }
            const originalKeys = original.map(launcherKey), beforeKeys = before.map(launcherKey);
            const orderedKeys = Array.from(tasks.launcherList).map(launcherKey)
                .filter((key, index, keys) => originalKeys.indexOf(key) !== -1 && keys.indexOf(key) === index);
            const ordered = [];
            for (const key of orderedKeys)
                for (const url of original) if (launcherKey(url) === key) ordered.push(url);
            const candidate = original.map(url => beforeKeys.indexOf(launcherKey(url)) !== -1 && orderedKeys.indexOf(launcherKey(url)) !== -1 ? ordered.shift() : url);
            const post = JSON.stringify(taskOrder());
            const guard = scope === "legacy" && continuationGuard === undefined ? undefined
                : () => current() && allowed() && JSON.stringify(taskOrder()) === post;
            return saveLaunchers(candidate, scope, revision, guard);
        } finally { finishLauncherOrder(); }
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
        if (nativePopups) nativeTaskMenu.openAt(null);
        else taskMenu.open();
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
        if (nativePopups) nativeTaskMenu.openAt(sourceItem);
        else taskMenu.open();
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
        if (!control || !control.activeFocus) return;
        let item = control;
        while (item && item !== content) item = item.parent;
        if (item !== content) return;
        const point = control.mapToItem(content, 0, 0);
        const coveredWidth = localEventSurface.visible ? root.eventSlotWidth : 0;
        const visibleWidth = Math.max(0, viewport.width - coveredWidth);
        const maximum = Math.max(0, viewport.contentWidth - viewport.width);
        if (point.x < viewport.contentX) viewport.contentX = Math.max(0, point.x);
        else if (point.x + control.width > viewport.contentX + visibleWidth)
            viewport.contentX = Math.min(maximum, control.width > visibleWidth ? point.x : point.x + control.width - visibleWidth);
    }
    function revealAfterGeometryChange() {
        Qt.callLater(() => {
            const window = root.Window.window;
            if (root.ready && localEventSurface.visible && window)
                root.revealInViewport(window.activeFocusItem);
        });
    }
    function rememberStableDockControl(control) {
        let item = control;
        while (item && item !== content) item = item.parent;
        if (item === content && control.visible && control.enabled)
            lastStableDockControl = control;
    }
    function restoreStableDockControl(closingControl) {
        const target = lastStableDockControl;
        Qt.callLater(() => {
            const window = root.Window.window;
            if (!window || !window.active || !target || !target.visible || !target.enabled) return;
            let item = target;
            while (item && item !== content) item = item.parent;
            if (item !== content) return;
            const focused = window.activeFocusItem;
            if (focused && focused !== closingControl && focused !== window.contentItem) return;
            target.forceActiveFocus(Qt.TabFocusReason);
        });
    }
    Connections {
        target: root.Window.window
        enabled: target !== null
        // External window loss invalidates even while the native adapter is committing.
        function onActiveChanged() { if (!target.active && taskDragState.pressed) taskDragState.cancel(); }
        function onVisibleChanged() { if (!target.visible && taskDragState.pressed) taskDragState.cancel(); }
        function onClosing() { if (taskDragState.pressed) taskDragState.cancel(); }
        function onActiveFocusItemChanged() {
            root.taskFocusEpoch++;
            const control = root.Window.window.activeFocusItem;
            root.rememberStableDockControl(control);
            root.revealInViewport(control);
        }
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
        active: enabledModules.length > 0
        enabledModules: ["quota", "peripherals", "recording"].filter(module => root.widgetVisible(module))
    }
    AddonTransport { id: nativeAddonTransport }
    AddonsSession {
        id: addonsSession
        objectName: "dockAddonsSession"
        running: root.ready
        dataState: localIntegrations
        transport: root.addonTransportOverride !== null ? root.addonTransportOverride : nativeAddonTransport
        surfaceActive: settings.visible && root.contextCommandsVisible && settingsContents.widgetsTabActive
        owner: settingsContents
        scopeKey: profileState.activeProfileId + ":" + profileState.revision
        onOriginApproved: origin => Qt.openUrlExternally(origin)
    }
    AddonFilePicker {
        id: addonPicker
        objectName: "dockAddonFilePicker"
        manager: addonsSession.manager
        parentWindow: settings.nativeDialog
        active: addonsSession.surfaceActive
    }
    Binding {
        target: settings.nativeDialog
        property: "hideOnWindowDeactivate"
        // A modal chooser legitimately takes activation from this popup.
        value: !addonPicker.visible && !addonsSession.manager.selecting
        when: settings.nativeDialog !== null
    }
    function requestControlCenter(client, host, anchor) {
        return ready && controlCenterPopup.openFromClient(client, host, anchor);
    }
    function releaseControlCenter(client) { return controlCenterPopup.releaseClient(client); }
    function controlCenterVisibleFor(client) { return controlCenterPopup.visibleFor(client); }
    function controlCenterErrorFor(client) { return controlCenterPopup.errorFor(client); }
    Component.onCompleted: {
        ready = true;
        reloadLaunchers();
        SharedControls.Registry.registerOwner(root, 1);
    }
    Component.onDestruction: {
        ready = false;
        SharedControls.Registry.unregisterOwner(root);
        controlCenterPopup.shutdown();
    }
    Mpris.Mpris2Model { id: media }
    property var mediaSource: media
    readonly property var player: mediaSource ? mediaSource.currentPlayer : null
    readonly property bool mediaPlaying: musicControls.mediaState.playing
    SystemBattery {
        id: power
        objectName: "systemBattery"
        active: root.widgetVisible("systemBattery") || controlCenterPopup.visible
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
    EventState {
        id: localEventState
        enabled: root.localEventsProfileReady && (root.eventIslandActive || root.candidateEventSlotWidth >= 48)
        completionEnabled: enabled && Boolean(root.configuration.showLocalToasts)
        audioEnabled: enabled && Boolean(root.presentation.showAudioHud)
        activeScope: "profile:" + profileState.activeProfileId
        activeContextGeneration: profileState.revision
    }
    Timer { interval: 1000; running: true; repeat: true; onTriggered: root.now = new Date() }
    Timer { interval: 8000; running: root.notice.length > 0; onTriggered: root.notice = "" }
    // Glass slab: hugs the slot row like the macOS dock and leaves the rest of the
    // panel transparent. Tokens still drive its color, radius, border and opacity.
    readonly property int glassHeight: systemGlass ? Math.max(0, glassFrame.height - 2 * Style.dock.systemGlassBandY)
        : Math.min(height, tileSize + 16 + Style.dock.glassPadding * 2)
    readonly property real glassTop: dockSurface.y
    // Frosted: KWin blurs behind the slab, so a translucent theme lets it through.
    // Opaque themes (Midnight, Paper, custom opacity 1) stay opaque.
    readonly property real surfaceOpacity: appearanceState.overridden ? appearanceState.effective.tokens.opacity
        : light || presentation.appearance.theme === "midnight" ? 1 : Style.dockThemes.glass.opacity
    readonly property bool frosted: systemGlass && surfaceOpacity < 1
    readonly property color surfaceBase: appearanceState.overridden ? appearanceState.effective.tokens.surface
        : Style.dockThemes.glass.surface
    GlassShadow {
        target: dockSurface
        radius: dockSurface.radius
        // A drawn shadow would darken the glass from below once it is translucent.
        strength: root.frosted ? 0 : root.lightSurface ? Style.glass.shadowLight : Style.glass.shadowDark
        blur: Style.space.sm + Style.space.xs
        offset: Style.space.xxs
    }
    Rectangle {
        id: dockSurface
        objectName: "dockSurface"
        // Frosted, the slab is exactly the theme frame's blur mask.
        x: root.systemGlass ? root.glassFrame.x + Style.dock.systemGlassBandX : root.outerMargin - Style.dock.glassInset
        width: root.systemGlass ? Math.max(0, root.glassFrame.width - 2 * Style.dock.systemGlassBandX)
            : Math.max(0, root.width - 2 * x - root.trailingReserve)
        height: root.glassHeight
        y: root.systemGlass ? root.glassFrame.y + Style.dock.systemGlassBandY : Math.round((root.height - height) / 2)
        radius: appearanceState.effective.tokens.radius
        color: root.frosted ? Style.alpha(root.surfaceBase, Style.glass.frostTint) : root.surface
        opacity: !root.frosted && appearanceState.overridden ? appearanceState.effective.tokens.opacity : 1
        border.width: 1
        border.color: appearanceState.effective.tokens.border
        Behavior on color { ColorAnimation { duration: root.motion } }
        GlassRim {
            anchors.fill: parent
            radius: Math.min(parent.radius, parent.height / 2)
            light: root.lightSurface
        }
    }
    Tile {
        id: settingsButton
        objectName: "settingsButton"
        parent: settingsPlaceholder
        anchors.verticalCenter: parent.verticalCenter
        iconSource: Qt.resolvedUrl("../images/orla.svg")
        iconSize: root.tileSize
        // The local-events lane math reserves this width for the first slot.
        implicitWidth: root.tileSize + 6
        foreground: root.accent; accent: root.accent; animationDuration: root.motion
        tooltip: qsTr("Personalizar Orla Dock")
        nativeLabel: root.nativePopups
        onHoveredChanged: root.hoverTile(this, hovered)
        onActiveFocusChanged: if (activeFocus) root.revealInViewport(settingsButton)
        onClicked: settings.openAt(settingsButton)
    }
    Rectangle {
        id: settingsDivider
        parent: settingsDividerPlaceholder
        anchors.centerIn: parent
        // Like Finder, the Orla slot needs no separator; the lane keeps its width.
        visible: false
        width: Style.size.divider
        height: Math.round(root.tileSize * 0.72)
        radius: width / 2
        color: Style.alpha(root.foreground, 0.2)
    }
    Flickable {
        id: viewport
        objectName: "appsViewport"
        x: root.laneStart
        // Full height: lifted and bouncing icons may rise above the glass.
        y: 0
        width: root.centerViewportWidth
        height: root.height
        // Extend Qt's actual bounds without moving or resizing ordinary controls.
        contentWidth: content.width + (localEventSurface.visible ? root.eventSlotWidth : 0)
        onWidthChanged: { root.checkTaskDragGeometry(); root.revealAfterGeometryChange(); }
        onHeightChanged: root.checkTaskDragGeometry()
        onXChanged: root.checkTaskDragGeometry()
        onYChanged: root.checkTaskDragGeometry()
        onContentXChanged: root.checkTaskDragGeometry()
        contentHeight: height
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.HorizontalFlick
        interactive: !taskDragState.pressed
        Controls.ScrollBar.horizontal: Controls.ScrollBar { policy: Controls.ScrollBar.AlwaysOff }
        Row {
            id: content
            objectName: "dockContent"
            onWidthChanged: root.revealAfterGeometryChange()
            height: viewport.height
            spacing: appearanceState.effective.tokens.spacing
            Item {
                id: settingsPlaceholder
                objectName: "settingsPlaceholder"
                width: settingsButton.implicitWidth
                height: parent.height
            }
            Item {
                id: settingsDividerPlaceholder
                objectName: "settingsDividerPlaceholder"
                width: 1
                height: parent.height
            }
            Repeater {
                id: taskRepeater
                model: tasks
                delegate: Tile {
                    id: taskTile
                    objectName: "taskTile" + index
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
                    launching: Boolean(model.IsStartup)
                    activeTask: Boolean(model.IsActive)
                    attention: Boolean(model.IsDemandingAttention)
                    nativeLabel: root.nativePopups || taskDragState.active
                    onHoveredChanged: root.hoverTile(taskTile, hovered)
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
                    DragHandler {
                        id: taskPointer
                        objectName: "taskDragHandler" + taskTile.index
                        target: null
                        acceptedButtons: Qt.LeftButton
                        acceptedModifiers: Qt.NoModifier
                        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                        property var ownedIntent: null
                        property bool everActive: false
                        property int pointId: -1
                        function cancelOwned() {
                            if (ownedIntent !== null && taskDragState.intent === ownedIntent) taskDragState.cancel();
                            ownedIntent = null;
                        }
                        onActiveChanged: if (active) {
                            everActive = true;
                            if (taskDragState.intent === ownedIntent && ownedIntent !== null && taskDragState.activate()) {
                                root.labelTarget = null;
                                root.updateTaskDrag(centroid.scenePosition);
                            }
                        }
                        onCentroidChanged: if (active && ownedIntent !== null && taskDragState.intent === ownedIntent)
                            root.updateTaskDrag(centroid.scenePosition)
                        onGrabChanged: (transition, point) => {
                            if (transition === PointerDevice.GrabPassive && point.state === EventPoint.Pressed) {
                                everActive = false;
                                pointId = point.id;
                                ownedIntent = root.beginTaskDrag(taskTile, point.scenePosition) ? taskDragState.intent : null;
                            } else if (point.id === pointId) {
                                if (transition === PointerDevice.UngrabExclusive) {
                                    if (point.state === EventPoint.Released && everActive && ownedIntent !== null && taskDragState.intent === ownedIntent) {
                                        // syncLaunchers may recreate this delegate; retire its ticket before committing.
                                        ownedIntent = null;
                                        root.finishTaskDrag(point.scenePosition, taskTile);
                                    } else cancelOwned();
                                } else if (transition === PointerDevice.CancelGrabExclusive || transition === PointerDevice.CancelGrabPassive
                                    || (transition === PointerDevice.UngrabPassive && !everActive)) cancelOwned();
                            }
                        }
                        Component.onDestruction: {
                            if (taskDragState && !taskDragState.committing && ownedIntent !== null
                                && taskDragState.intent === ownedIntent) taskDragState.cancel();
                        }
                    }
                }
            }
            Tile {
                objectName: "addButton"
                anchors.verticalCenter: parent.verticalCenter
                iconSource: "list-add-symbolic"
                iconSize: Math.max(12, Math.round(root.tileSize * 0.5))
                opacity: hovered || visualFocus ? 1 : 0.6
                foreground: root.foreground; accent: root.accent; animationDuration: root.motion
                tooltip: qsTr("Fixar aplicativo · ou arraste um app para o dock")
                nativeLabel: root.nativePopups
                onHoveredChanged: root.hoverTile(this, hovered)
                onActiveFocusChanged: if (activeFocus) root.revealInViewport(this)
                onClicked: addDialog.openAt(this)
            }
            Tile {
                objectName: "controlCenterButton"
                anchors.verticalCenter: parent.verticalCenter
                visible: Boolean(root.configuration.showControlCenter)
                liveKind: "controlCenter"
                live: true
                iconSize: root.tileSize
                foreground: root.foreground; muted: root.muted; accent: root.accent
                animationDuration: root.motion
                tooltip: qsTr("Central de Controle")
                nativeLabel: root.nativePopups
                onHoveredChanged: root.hoverTile(this, hovered)
                onActiveFocusChanged: if (activeFocus) root.revealInViewport(this)
                onClicked: controlCenterPopup.openAt(this)
            }
            Rectangle { objectName: "widgetDivider"; anchors.verticalCenter: parent.verticalCenter; visible: widgetStrip.visible; width: Style.size.divider; height: Math.round(root.tileSize * 0.72); radius: width / 2; color: Style.alpha(root.foreground, 0.2) }
            WidgetStrip { id: widgetStrip; objectName: "widgetStrip"; dock: root; height: parent.height }
            // The Trash closes the dock after its own divider, as in macOS (optional, global).
            Rectangle { objectName: "trashDivider"; anchors.verticalCenter: parent.verticalCenter; visible: trashLoader.active; width: Style.size.divider; height: Math.round(root.tileSize * 0.72); radius: width / 2; color: Style.alpha(root.foreground, 0.2) }
            Loader {
                id: trashLoader
                anchors.verticalCenter: parent.verticalCenter
                active: Boolean(root.configuration.showTrash)
                // An unloaded Loader keeps its last width; hidden, the Row skips it.
                visible: active
                sourceComponent: TrashTile {
                    objectName: "trashTile"
                    iconSize: root.tileSize
                    foreground: root.foreground; muted: root.muted; accent: root.accent
                    animationDuration: root.motion
                    nativeLabel: root.nativePopups
                    onHoveredChanged: root.hoverTile(this, hovered)
                    onActiveFocusChanged: if (activeFocus) root.revealInViewport(this)
                }
            }

        }
    }
    Rectangle {
        id: taskDropIndicator
        objectName: "taskDropIndicator"
        parent: viewport
        readonly property Item destinationTile: root.taskDropTile()
        visible: taskDragState.active && destinationTile !== null
        x: destinationTile ? destinationTile.mapToItem(viewport,
            taskDragState.after ? destinationTile.width : 0, 0).x - width / 2 : 0
        y: (viewport.height - height) / 2
        width: Style.space.xxs
        height: root.tileSize
        radius: width / 2
        color: root.accent
        z: 2
    }
    EventSurface {
        id: localEventSurface
        x: root.laneEnd - width
        // Inside the glass, whatever the panel thickness.
        y: dockSurface.y + Style.dock.glassPadding + 1
        width: root.eventSlotWidth
        height: Math.max(0, dockSurface.height - 2 * (Style.dock.glassPadding + 1))
        visible: root.localEventsActive && Boolean(localEventState.current)
        onVisibleChanged: root.checkTaskDragGeometry()
        z: 3
        eventState: localEventState
        surfaceColor: root.surface
        borderColor: appearanceState.effective.tokens.border
        foregroundColor: root.foreground
        mutedColor: root.muted
        accentColor: root.accent
        animationDuration: root.motion
        onFocusRestoreRequested: root.restoreStableDockControl(closeControl)
    }
    DropArea {
        anchors.fill: parent
        onDropped: drop => {
            let accepted = false;
            for (const url of drop.urls) accepted = root.addLauncher(String(url)) || accepted;
            if (accepted) drop.acceptProposedAction();
        }
        Rectangle { x: dockSurface.x; y: dockSurface.y; width: dockSurface.width; height: dockSurface.height; radius: dockSurface.radius; visible: parent.containsDrag; color: Style.alpha(root.accent, 0.1); border.color: root.accent; border.width: 2 }
    }
    Controls.Menu {
        id: taskMenu
        objectName: "taskContextMenu"
        property int interactionEpoch: 0
        property bool interactionActive: false
        readonly property bool contextSwitchBusy: visible || interactionActive
        onAboutToShow: { interactionEpoch++; interactionActive = true; }
        onAboutToHide: { interactionEpoch++; interactionActive = true; }
        onClosed: {
            const epoch = interactionEpoch;
            const menu = taskMenu;
            Qt.callLater(() => {
                if (Qt.isQtObject(menu) && epoch === menu.interactionEpoch && !menu.visible)
                    menu.interactionActive = false;
            });
        }
        parent: root
        margins: -1
        popupType: Controls.Popup.Window
        x: Math.max(0, Math.min(Math.max(0, root.width - width), root.menuAnchorX - width / 2))
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
    DockPopup {
        id: nativeTaskMenu
        objectName: "nativeTaskContextMenu"
        dock: root
        width: 300 + 2 * shadowMargin - 2 * frameMargin
        title: root.menuData.title || ""
        ColumnLayout {
            id: nativeTaskActions
            Layout.fillWidth: true
            spacing: 2
            function advanceFocus(direction) {
                const actions = Array.from(children).filter(item => item.visible && item.enabled && item.forceActiveFocus && item.text !== undefined);
                if (!actions.length) return;
                const current = actions.findIndex(item => item.activeFocus);
                const next = current < 0 ? (direction > 0 ? 0 : actions.length - 1)
                    : (current + direction + actions.length) % actions.length;
                actions[next].forceActiveFocus(Qt.TabFocusReason);
            }
            Keys.onDownPressed: event => { advanceFocus(1); event.accepted = true; }
            Keys.onUpPressed: event => { advanceFocus(-1); event.accepted = true; }
            Controls.MenuItem { Layout.fillWidth: true; focusPolicy: Qt.StrongFocus;
                text: root.menuData.pinned ? qsTr("Desafixar") : qsTr("Fixar no dock")
                enabled: Boolean(root.menuData.url)
                onTriggered: { nativeTaskMenu.close(); if (root.menuData.pinned) root.removeLauncher(root.menuData.url, root.menuData.scope, root.menuData.revision); else root.addLauncher(root.menuData.url, root.menuData.scope, root.menuData.revision); }
            }
            Controls.MenuItem { Layout.fillWidth: true; focusPolicy: Qt.StrongFocus; text: qsTr("Nova janela"); enabled: Boolean(root.menuData.canLaunch); onTriggered: { nativeTaskMenu.close(); const index = root.menuIndex(); if (index) tasks.requestNewInstance(index); } }
            Controls.MenuItem { Layout.fillWidth: true; focusPolicy: Qt.StrongFocus; text: qsTr("Mover para a esquerda"); enabled: root.menuRow > 0; onTriggered: { nativeTaskMenu.close(); root.moveMenuTask(-1); } }
            Controls.MenuItem { Layout.fillWidth: true; focusPolicy: Qt.StrongFocus; text: qsTr("Mover para a direita"); enabled: root.menuRow < tasks.count - 1; onTriggered: { nativeTaskMenu.close(); root.moveMenuTask(1); } }
            Controls.MenuSeparator { Layout.fillWidth: true; visible: Boolean(root.menuData.window) }
            Controls.MenuItem { Layout.fillWidth: true; focusPolicy: Qt.StrongFocus; text: qsTr("Minimizar / restaurar"); visible: Boolean(root.menuData.window); enabled: Boolean(root.menuData.minimizable); onTriggered: { nativeTaskMenu.close(); const index = root.menuIndex(); if (index) tasks.requestToggleMinimized(index); } }
            Controls.MenuItem { Layout.fillWidth: true; focusPolicy: Qt.StrongFocus; text: qsTr("Fechar janela"); visible: Boolean(root.menuData.window); enabled: Boolean(root.menuData.closable); onTriggered: { nativeTaskMenu.close(); const index = root.menuIndex(); if (index) tasks.requestClose(index); } }
        }
        onOpened: nativeTaskActions.advanceFocus(1)
    }

    // Keep the editor legible even when the draft uses low-contrast dock colors.
    Item {
        id: settingsAnchor
        anchors.fill: parent
        readonly property bool popAbove: root.popAbove
        readonly property bool nativePopups: root.nativePopups
        readonly property var popupScheme: root.popupScheme
        readonly property real glassTop: root.glassTop
        readonly property bool systemPopupGlass: root.systemPopupGlass
    }
    DockPopup {
        id: settings
        objectName: "settingsPopup"
        // Leave room for the panel and gap on the current monitor.
        property real heightBudget: maximumPopupHeight
        height: Math.min(implicitHeight, heightBudget)
        dock: settingsAnchor
        title: qsTr("Seu dock, do seu jeito")
        onAboutToShow: { root.contextCommandsVisible = true; appearanceState.begin(); }
        onAboutToHide: { root.contextCommandsVisible = false; appearancePresetState.cancel(); }
        onClosed: appearancePresetState.cancel()
        SettingsContents {
            themeFileWindow: settings.nativeDialog
            id: settingsContents
            configuration: root.configuration
            profiles: profileState
            resetTimer: focusTimer.reset
            appearance: appearanceState
            appearancePreset: appearancePresetState
            contexts: contextState
            contextBindings: contextBindingsState
            desktopSwitch: desktopSwitchState
            automation: autoContextState
            integrations: localIntegrations
            addonsSession: addonsSession
            addonScheme: root.popupScheme
            onAddonFileRequested: addonPicker.open()
            onAddonWaitCanceled: settings.close()
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
            spacing: Style.space.sm
            Controls.Label { Layout.fillWidth: true; text: qsTr("Arraste um aplicativo do menu do KDE para o dock, ou informe o ID abaixo."); color: root.popupScheme.textMuted; wrapMode: Text.WordWrap }
            Controls.TextField { id: appInput; objectName: "launcherInput"; Layout.fillWidth: true; placeholderText: "org.kde.dolphin.desktop"; onAccepted: pinButton.clicked() }
            Controls.Label { Layout.fillWidth: true; text: root.notice; visible: text.length > 0; color: root.popupScheme.danger; wrapMode: Text.WordWrap }
            OrlaButton { id: pinButton; variant: "primary"; Layout.alignment: Qt.AlignRight; text: qsTr("Fixar aplicativo"); enabled: appInput.text.trim().length > 0; onClicked: if (root.addLauncher(appInput.text, addDialog.scope, addDialog.revision)) { appInput.clear(); addDialog.close(); } }
        }
    }
    DockPopup {
        id: calendarPopup
        objectName: "calendarPopup"
        dock: root
        // Today's date, as the macOS Calendar widget shows it; the grid names the month.
        // The user's long date format without the year ("domingo, 25 de outubro").
        title: { const format = Qt.locale().dateFormat(Locale.LongFormat).replace(/,?\s*('[^']*'\s*)?y{2,4}\.?/, "");
            const text = root.now.toLocaleDateString(Qt.locale(), format);
            return text.charAt(0).toLocaleUpperCase() + text.slice(1); }
        CalendarAgenda {
            objectName: "calendarAgenda"
            dock: popupContext
            active: calendarPopup.visible
        }
        Controls.Button {
            objectName: "calendarConfigureButton"
            readonly property string accessibilityDescription: qsTr("Abre o KOrganizer. A seleção de calendários também é usada pelo relógio do KDE.")
            text: qsTr("Configurar no KOrganizer")
            Accessible.name: text
            Accessible.description: accessibilityDescription
            onClicked: root.openCalendarApp()
        }
    }
    DockPopup {
        id: integrationPopup
        objectName: "integrationPopup"
        dock: root
        title: root.selectedIntegration === "quota" ? "QuotaLantern" : root.selectedIntegration === "peripherals" ? qsTr("Bateria de periféricos") : "FalaTrace"
        IntegrationDetails { dock: popupContext; integrations: localIntegrations; selected: root.selectedIntegration; addonsSession: addonsSession }
    }
    Connections {
        target: root.configuration
        function onShowControlCenterChanged() {
            if (!root.configuration.showControlCenter) controlCenterPopup.closeDockOrigin();
        }
    }
    Loader {
        id: nativeControlCenterBackend
        objectName: "controlCenterNativeLoader"
        active: controlCenterPopup.visible && root.controlCenterBackendOverride === null
        source: active ? Qt.resolvedUrl("NativeKdeControlActions.qml") : ""
    }
    KdeControlActions {
        id: kdeControlActions
        objectName: "kdeControlActions"
        backend: root.controlCenterBackendOverride !== null ? root.controlCenterBackendOverride
            : nativeControlCenterBackend.item
    }
    Loader {
        id: nativeAudioBackend
        objectName: "controlCenterAudioNativeLoader"
        active: controlCenterPopup.visible && root.audioBackendOverride === null
        source: active ? Qt.resolvedUrl("NativePulseAudio.qml") : ""
    }
    Loader {
        id: nativeBrightnessBackend
        objectName: "controlCenterBrightnessNativeLoader"
        // PowerDevil's module exists only in the production Plasma session.
        active: controlCenterPopup.visible && root.brightnessBackendOverride === null && root.nativePopups
        source: active ? Qt.resolvedUrl("NativeBrightness.qml") : ""
    }
    BrightnessControlState {
        id: brightnessControlState
        objectName: "brightnessControlState"
        active: controlCenterPopup.visible
        backend: root.brightnessBackendOverride !== null ? root.brightnessBackendOverride : nativeBrightnessBackend.item
    }
    Loader {
        id: nativeDoNotDisturbBackend
        objectName: "controlCenterDoNotDisturbNativeLoader"
        // Plasma's notification manager is only meaningful inside plasmashell.
        active: controlCenterPopup.visible && root.doNotDisturbBackendOverride === null && root.nativePopups
        source: active ? Qt.resolvedUrl("NativeDoNotDisturb.qml") : ""
    }
    DoNotDisturbState {
        id: doNotDisturbState
        objectName: "doNotDisturbState"
        active: controlCenterPopup.visible
        backend: root.doNotDisturbBackendOverride !== null ? root.doNotDisturbBackendOverride : nativeDoNotDisturbBackend.item
    }
    Loader {
        id: nativeMicrophoneBackend
        objectName: "controlCenterMicrophoneNativeLoader"
        // Plasma-PA's input model is only used inside plasmashell.
        active: controlCenterPopup.visible && root.microphoneBackendOverride === null && root.nativePopups
        source: active ? Qt.resolvedUrl("NativeMicrophone.qml") : ""
    }
    MicrophoneState {
        id: microphoneState
        objectName: "microphoneState"
        active: controlCenterPopup.visible
        backend: root.microphoneBackendOverride !== null ? root.microphoneBackendOverride : nativeMicrophoneBackend.item
    }
    Loader {
        id: nativePowerProfileBackend
        objectName: "controlCenterPowerProfileNativeLoader"
        // PowerDevil is read only while the Control Center is open.
        active: controlCenterPopup.visible && root.powerProfileBackendOverride === null && root.nativePopups
        source: active ? Qt.resolvedUrl("NativePowerProfile.qml") : ""
    }
    PowerProfileState {
        id: powerProfileState
        objectName: "powerProfileState"
        active: controlCenterPopup.visible
        backend: root.powerProfileBackendOverride !== null ? root.powerProfileBackendOverride : nativePowerProfileBackend.item
    }
    Loader {
        id: nativeWifiBackend
        objectName: "controlCenterWifiNativeLoader"
        // Plasma's network library is read only while the Control Center is open.
        active: controlCenterPopup.visible && root.wifiBackendOverride === null && root.nativePopups
        source: active ? Qt.resolvedUrl("NativeWifi.qml") : ""
    }
    WifiState {
        id: wifiState
        objectName: "wifiState"
        active: controlCenterPopup.visible
        backend: root.wifiBackendOverride !== null ? root.wifiBackendOverride : nativeWifiBackend.item
    }
    Loader {
        id: nativeBluetoothBackend
        objectName: "controlCenterBluetoothNativeLoader"
        // BluezQt is read only while the Control Center is open.
        active: controlCenterPopup.visible && root.bluetoothBackendOverride === null && root.nativePopups
        source: active ? Qt.resolvedUrl("NativeBluetooth.qml") : ""
    }
    BluetoothState {
        id: bluetoothState
        objectName: "bluetoothState"
        active: controlCenterPopup.visible
        backend: root.bluetoothBackendOverride !== null ? root.bluetoothBackendOverride : nativeBluetoothBackend.item
    }
    AudioControlState {
        id: audioControlState
        objectName: "audioControlState"
        active: controlCenterPopup.visible
        backend: root.audioBackendOverride !== null ? root.audioBackendOverride : nativeAudioBackend.item
        requestOriginScope: "profile:" + profileState.activeProfileId
        requestContextGeneration: profileState.revision
        onConfirmed: receipt => {
            let title = "";
            let detail = receipt.targetLabel;
            if (receipt.action === "volume") title = qsTr("Volume · %1%").arg(receipt.value);
            else if (receipt.action === "mute") title = receipt.value ? qsTr("Som silenciado") : qsTr("Som ativado");
            else title = qsTr("Saída de áudio alterada");
            localEventState.submit({
                kind: "audio", action: receipt.action, targetId: receipt.targetId,
                originScope: receipt.originScope, contextGeneration: receipt.contextGeneration,
                value: receipt.value, title: title, detail: detail
            }, Date.now());
        }
    }
    ControlCenterPopup {
        id: controlCenterPopup
        objectName: "controlCenterPopup"
        owner: root
        actions: kdeControlActions
        player: root.player
        battery: ({status: power.status, summary: power.summary, subtitle: root.powerSubtitle,
            percent: power.percent, percentKnown: power.percentKnown, charging: power.charging === "charging"})
        playing: root.mediaPlaying
        mediaState: musicControls.mediaState
        audio: audioControlState
        brightness: brightnessControlState
        doNotDisturb: doNotDisturbState
        microphone: microphoneState
        powerProfile: powerProfileState
        wifi: wifiState
        bluetooth: bluetoothState
        desktopSwitch: desktopSwitchState
        backendLifetime: nativeAudioBackend.item
        validateClient: function(client) {
            return root.ready && client && client.available
                && SharedControls.Registry.status === "ready" && SharedControls.Registry.owner === root;
        }
    }
    DockPopup {
        id: pomodoroPopup
        objectName: "pomodoroPopup"
        dock: root
        title: root.configuration.timerBreak ? qsTr("Respire um pouco") : qsTr("Uma coisa de cada vez")
        Item {
            Layout.fillWidth: true
            implicitHeight: timerRing.height + Style.space.sm
            ProgressRing {
                id: timerRing
                objectName: "pomodoroRing"
                anchors.centerIn: parent
                width: 172
                height: width
                lineWidth: 6
                progress: 1 - focusTimer.secondsLeft / Math.max(1, focusTimer.phaseSeconds)
                color: root.popupScheme.accent
                trackColor: Style.alpha(root.popupScheme.text, 0.08)
                animationDuration: root.motion
            }
            Column {
                anchors.centerIn: parent
                spacing: Style.space.xxs
                Controls.Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: Logic.duration(focusTimer.secondsLeft)
                    textFormat: Text.PlainText
                    color: root.popupScheme.text
                    font.pixelSize: Style.type.display
                    font.weight: Style.weight.medium
                    font.features: {"tnum": 1}
                }
                Controls.Label {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: (root.configuration.timerBreak ? qsTr("Pausa") : qsTr("Foco")).toUpperCase()
                    textFormat: Text.PlainText
                    color: root.popupScheme.accent
                    font.pixelSize: Style.type.overline
                    font.weight: Style.weight.bold
                    font.letterSpacing: Style.letterSpacing.overline
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Style.space.sm
            OrlaButton { objectName: "toggleTimer"; variant: "primary"; Layout.fillWidth: true; text: focusTimer.running ? qsTr("Pausar") : qsTr("Iniciar"); onClicked: focusTimer.toggle() }
            OrlaButton { Layout.fillWidth: true; text: qsTr("Reiniciar"); onClicked: focusTimer.reset() }
        }
        Controls.Label { Layout.alignment: Qt.AlignHCenter; text: qsTr("%1 sessões concluídas").arg(root.configuration.completedFocus); color: root.popupScheme.textMuted; textFormat: Text.PlainText }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: Style.space.md
            rowSpacing: Style.space.sm
            Controls.Label { Layout.fillWidth: true; text: qsTr("Foco (min)"); textFormat: Text.PlainText }
            Controls.SpinBox { from: 1; to: 120; value: root.configuration.focusMinutes; enabled: !focusTimer.running; onValueModified: { root.configuration.focusMinutes = value; focusTimer.reset(); } }
            Controls.Label { Layout.fillWidth: true; text: qsTr("Pausa (min)"); textFormat: Text.PlainText }
            Controls.SpinBox { from: 1; to: 60; value: root.configuration.breakMinutes; enabled: !focusTimer.running; onValueModified: { root.configuration.breakMinutes = value; focusTimer.reset(); } }
        }
    }
    DockPopup {
        id: musicPopup
        objectName: "musicPopup"
        dock: root
        title: qsTr("Sua música")
        MediaControls {
            id: musicControls
            objectName: "mediaControls"
            Layout.fillWidth: true
            media: root.mediaSource
            foreground: root.popupScheme.text
            muted: root.popupScheme.textMuted
        }
    }
    DockPopup {
        id: batteryPopup
        objectName: "batteryPopup"
        dock: root
        title: qsTr("Energia")
        RowLayout {
            Layout.fillWidth: true
            spacing: Style.space.lg
            Item {
                implicitWidth: 72
                implicitHeight: 72
                ProgressRing {
                    anchors.fill: parent
                    lineWidth: 5
                    progress: power.percentKnown ? power.percent / 100 : 0
                    color: root.popupScheme.accent
                    trackColor: Style.alpha(root.popupScheme.text, 0.08)
                    animationDuration: root.motion
                }
                Controls.Label {
                    anchors.centerIn: parent
                    text: power.percentKnown ? Math.round(power.percent) + "%" : "—"
                    textFormat: Text.PlainText
                    font.pixelSize: Style.type.title
                    font.weight: Style.weight.demiBold
                    font.features: {"tnum": 1}
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: Style.space.xxs
                Controls.Label { Layout.fillWidth: true; text: power.summary; font.weight: Style.weight.demiBold; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
                Controls.Label { Layout.fillWidth: true; text: root.powerSubtitle; color: root.popupScheme.textMuted; wrapMode: Text.WordWrap; textFormat: Text.PlainText }
                Controls.Label {
                    Layout.fillWidth: true
                    visible: power.estimatedTimeKind !== "unknown"
                    text: power.estimatedTimeKind === "full"
                        ? qsTr("Estimativa até completar: %1 min").arg(Math.ceil(power.estimatedTimeSeconds / 60))
                        : qsTr("Estimativa restante: %1 min").arg(Math.ceil(power.estimatedTimeSeconds / 60))
                    color: root.popupScheme.textMuted
                    wrapMode: Text.WordWrap; textFormat: Text.PlainText
                }
            }
        }
        Controls.Label {
            Layout.fillWidth: true
            text: qsTr("Bateria do computador. Baterias externas ficam em Periféricos.")
            color: root.popupScheme.textMuted
            font.pixelSize: Style.type.caption
            wrapMode: Text.WordWrap; textFormat: Text.PlainText
        }
    }
    Controls.ToolTip { parent: root; visible: root.notice.length > 0 && !addDialog.visible; text: root.notice; timeout: 8000 }
}
