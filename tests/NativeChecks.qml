import QtQuick
import QtQuick.Window
import org.kde.taskmanager as TaskManager

Item {
    id: checks
    required property var targetDock
    required property string screenshotPath
    required property string launcherUrl
    property int stage: 0
    property int attempts: 0
    property bool launcherAdded: false
    property bool launched: false

    function finish(success, reason) {
        ticker.stop();
        const tasks = targetDock.tasksModel;
        for (let i = 0; i < tasks.count; i++) {
            const index = tasks.makeModelIndex(i);
            if (tasks.data(index, TaskManager.AbstractTasksModel.IsWindow)
                && String(tasks.data(index, Qt.DisplayRole)).includes("CaioDock acceptance probe")) tasks.requestClose(index);
        }
        console.info("CAIODOCK_NATIVE_RESULT " + JSON.stringify({success: success, reason: reason, tasks: targetDock.tasksModel.count, launcherAdded: launcherAdded, launched: launched, stage: stage}));
        Qt.quit();
    }
    Timer {
        id: ticker
        interval: 700
        running: true
        repeat: true
        onTriggered: {
            attempts++;
            if (attempts > 30) { checks.finish(false, "probe window not ready"); return; }
            const tasks = checks.targetDock.tasksModel;
            if (!checks.launcherAdded) {
                if (!checks.targetDock.addLauncher(checks.launcherUrl)) { checks.finish(false, "pin probe failed"); return; }
                checks.launcherAdded = true;
            }
            if (!checks.launched) {
                for (let i = 0; i < tasks.count; i++) {
                    const index = tasks.makeModelIndex(i);
                    if (tasks.data(index, TaskManager.AbstractTasksModel.IsLauncher)
                        && String(tasks.data(index, TaskManager.AbstractTasksModel.LauncherUrlWithoutIcon)).endsWith("caiodock-acceptance.desktop")) {
                        checks.targetDock.activateTask(i);
                        checks.launched = true;
                    }
                }
                return;
            }
            let row = -1;
            for (let i = 0; i < tasks.count; i++) {
                const index = tasks.makeModelIndex(i);
                if (tasks.data(index, TaskManager.AbstractTasksModel.IsWindow)
                    && String(tasks.data(index, Qt.DisplayRole)).includes("CaioDock acceptance probe")) row = i;
            }
            if (row < 0) return;
            const index = tasks.makeModelIndex(row);
            if (checks.stage === 0) {
                // Activate only the window created by this test.
                if (tasks.data(index, TaskManager.AbstractTasksModel.IsActive)) tasks.requestToggleMinimized(index);
                checks.stage = 1;
            } else if (checks.stage === 1) {
                checks.targetDock.activateTask(row);
                checks.stage = 2;
            } else if (checks.stage === 2) {
                if (!tasks.data(index, TaskManager.AbstractTasksModel.IsActive)) { checks.finish(false, "activate failed"); return; }
                checks.targetDock.activateTask(row);
                checks.stage = 3;
            } else if (checks.stage === 3) {
                if (!tasks.data(index, TaskManager.AbstractTasksModel.IsMinimized)) { checks.finish(false, "minimize failed"); return; }
                checks.targetDock.activateTask(row);
                checks.stage = 4;
            } else if (checks.stage === 4) {
                if (tasks.data(index, TaskManager.AbstractTasksModel.IsMinimized)) { checks.finish(false, "restore failed"); return; }
                ticker.stop();
                checks.targetDock.grabToImage(result => {
                    const saved = result.saveToFile(checks.screenshotPath);
                    checks.finish(saved, saved ? "pin/launch/activate/minimize/restore and screenshot passed" : "screenshot failed");
                });
            }
        }
    }
}
