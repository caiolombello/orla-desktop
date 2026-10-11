import QtQuick
import org.kde.taskmanager as TaskManager

// Read only the application name; window/document titles are never requested.
Item {
    id: root
    property bool hasActiveApplication: false
    property string appName: ""
    TaskManager.TasksModel { id: tasks }
    function update() {
        // QModelIndex.valid is the QML value-type property, not isValid().
        // Qt 6.11.2: src/qmlmodels/qqmlmodelindexvaluetype_p.h, Q_PROPERTY(valid).
        const activeTask = tasks.activeTask;
        hasActiveApplication = activeTask.valid;
        appName = hasActiveApplication
            ? String(tasks.data(activeTask, TaskManager.AbstractTasksModel.AppName) || "").slice(0, 160) : "";
    }
    Connections {
        target: tasks
        function onActiveTaskChanged() { root.update(); }
        function onDataChanged() { root.update(); }
        function onModelReset() { root.update(); }
    }
    Component.onCompleted: update()
}
