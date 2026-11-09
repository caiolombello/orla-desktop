import QtQuick
import "../code/AppActions.js" as AppActions

// Routes the dock's app-wide actions. The tasks model and the KWin backend are
// injected, so portable harnesses drive it without any org.kde import.
QtObject {
    id: root
    // TasksModel-like: count, makeModelIndex, data, requestToggleMinimized,
    // requestClose and requestVirtualDesktops.
    property var model: null
    // Role ids for {appId, isWindow, minimized, minimizable, closable, winIds,
    // desktops, allDesktops, desktopsChangeable}; DockView passes TaskManager's.
    property var roles: ({})
    // {desktopIds, desktopNames, windowViewAvailable, showWindowView(handles)}.
    property var backend: null
    readonly property var desktopIds: backend && backend.desktopIds ? Array.from(backend.desktopIds).map(String) : []
    readonly property var desktopNames: backend && backend.desktopNames ? Array.from(backend.desktopNames).map(String) : []
    readonly property bool windowViewAvailable: Boolean(backend) && backend.windowViewAvailable === true
        && typeof backend.showWindowView === "function"
    readonly property bool canMove: Boolean(model) && typeof model.requestVirtualDesktops === "function"
    readonly property var emptySummary: ({count: 0, hideable: 0, closable: 0, handles: 0, desktops: []})

    function list(value) {
        return value === undefined || value === null ? [] : Array.from(value).map(String);
    }
    function rows() {
        const result = [];
        if (!model) return result;
        for (let row = 0; row < model.count; row++) {
            const index = model.makeModelIndex(row);
            const value = name => roles[name] === undefined ? undefined : model.data(index, roles[name]);
            const changeable = value("desktopsChangeable");
            result.push({ index: index, appId: String(value("appId") || ""), isWindow: Boolean(value("isWindow")),
                minimized: Boolean(value("minimized")), minimizable: Boolean(value("minimizable")),
                closable: Boolean(value("closable")), winIds: list(value("winIds")),
                desktops: list(value("desktops")), allDesktops: Boolean(value("allDesktops")),
                desktopsChangeable: changeable === undefined ? true : Boolean(changeable) });
        }
        return result;
    }
    function windows(appId, winIds) {
        return AppActions.appWindows(rows(), appId, winIds);
    }
    function summary(appId, winIds) {
        const result = AppActions.summary(windows(appId, winIds), desktopIds, desktopNames);
        if (!canMove) result.desktops = [];
        return result;
    }
    // Targets are collected before any request: KWin answers asynchronously,
    // so rows stay put while the loop runs.
    function hide(appId, winIds) {
        if (!model) return 0;
        const targets = AppActions.hideTargets(windows(appId, winIds));
        for (const target of targets) model.requestToggleMinimized(target.index);
        return targets.length;
    }
    // Asks each window to close, like its title-bar button; never kills a process.
    function quit(appId, winIds) {
        if (!model) return 0;
        const targets = AppActions.closeTargets(windows(appId, winIds));
        for (const target of targets) model.requestClose(target.index);
        return targets.length;
    }
    function showAllWindows(appId, winIds) {
        const handles = AppActions.windowHandles(windows(appId, winIds));
        if (!windowViewAvailable || !handles.length) return false;
        try {
            backend.showWindowView(handles);
            return true;
        } catch (_) {
            return false;
        }
    }
    function moveToDesktop(appId, winIds, desktopId) {
        const position = desktopIds.indexOf(String(desktopId));
        if (position === -1 || !canMove) return 0;
        // X11 ids are numbers and Wayland's are strings; hand KWin its own value.
        const original = Array.from(backend.desktopIds)[position];
        const targets = AppActions.moveTargets(windows(appId, winIds), desktopIds[position]);
        for (const target of targets) model.requestVirtualDesktops(target.index, [original]);
        return targets.length;
    }
}
