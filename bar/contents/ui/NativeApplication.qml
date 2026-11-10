import QtQuick
import org.kde.taskmanager as TaskManager
import "../code/AppMenu.js" as AppMenu

// Reads the application name and window states; window/document titles are
// never requested.
Item {
    id: root
    property bool hasActiveApplication: false
    property string appName: ""
    // The app the menu acts on, captured when the menu opened.
    property var menuTarget: null
    // Ungrouped: every window is a row, so the app's windows can be listed.
    TaskManager.TasksModel { id: tasks; groupMode: TaskManager.TasksModel.GroupDisabled }
    function update() {
        // QModelIndex.valid is the QML value-type property, not isValid().
        // Qt 6.11.2: src/qmlmodels/qqmlmodelindexvaluetype_p.h, Q_PROPERTY(valid).
        const activeTask = tasks.activeTask;
        hasActiveApplication = activeTask.valid;
        appName = hasActiveApplication
            ? String(tasks.data(activeTask, TaskManager.AbstractTasksModel.AppName) || "").slice(0, 160) : "";
    }
    function rows() {
        const roles = TaskManager.AbstractTasksModel;
        const result = [];
        for (let row = 0; row < tasks.count; row++) {
            const index = tasks.makeModelIndex(row);
            const ids = tasks.data(index, roles.WinIdList);
            result.push({index: index, appId: String(tasks.data(index, roles.AppId) || ""),
                isWindow: Boolean(tasks.data(index, roles.IsWindow)),
                active: Boolean(tasks.data(index, roles.IsActive)),
                minimized: Boolean(tasks.data(index, roles.IsMinimized)),
                minimizable: Boolean(tasks.data(index, roles.IsMinimizable)),
                closable: Boolean(tasks.data(index, roles.IsClosable)),
                winIds: ids === undefined || ids === null ? [] : Array.from(ids).map(String)});
        }
        return result;
    }
    function captureActions() {
        const all = rows();
        menuTarget = AppMenu.target(all);
        return AppMenu.summary(all, menuTarget);
    }
    // Rows are read again at trigger time. Targets are collected before any
    // request: KWin answers asynchronously, so rows stay put while the loop runs.
    function hide() {
        for (const window of AppMenu.hideTargets(AppMenu.appWindows(rows(), menuTarget)))
            tasks.requestToggleMinimized(window.index);
    }
    function hideOthers() {
        for (const window of AppMenu.hideTargets(AppMenu.otherWindows(rows(), menuTarget)))
            tasks.requestToggleMinimized(window.index);
    }
    function showAll() {
        for (const window of AppMenu.showTargets(rows())) tasks.requestToggleMinimized(window.index);
    }
    // Asks each window to close, like its title-bar button; never kills a process.
    function quit() {
        for (const window of AppMenu.closeTargets(AppMenu.appWindows(rows(), menuTarget)))
            tasks.requestClose(window.index);
    }
    Connections {
        target: tasks
        function onActiveTaskChanged() { root.update(); }
        function onDataChanged() { root.update(); }
        function onModelReset() { root.update(); }
    }
    Component.onCompleted: update()
}
