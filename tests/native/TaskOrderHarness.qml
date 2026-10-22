import QtQuick
import org.kde.taskmanager as TaskManager
import ".." as Fixtures

Fixtures.QmlHarness {
    id: probe
    property var sourceDock: null
    property bool armed: false
    property int observerCalls: 0
    property bool observerAccepted: false
    property var movedHandler: null
    function identity(app, url) {
        for (const id of ["org.orla.ModelA", "org.orla.ModelB"])
            if (app === id || app === id + ".desktop" || url.endsWith(id + ".desktop")) return id;
        return "";
    }
    function snapshot() {
        const rows = [];
        for (let i=0; i<sourceDock.tasksModel.count; ++i) {
            const ix=sourceDock.tasksModel.makeModelIndex(i);
            const app=String(sourceDock.tasksModel.data(ix,TaskManager.AbstractTasksModel.AppId)||"");
            const url=String(sourceDock.tasksModel.data(ix,TaskManager.AbstractTasksModel.LauncherUrlWithoutIcon)||"");
            const id=identity(app,url);
            if (id === "") continue;
            rows.push({row:i,id:id,AppId:app,LauncherUrlWithoutIcon:url,
                IsWindow:!!sourceDock.tasksModel.data(ix,TaskManager.AbstractTasksModel.IsWindow),
                IsLauncher:!!sourceDock.tasksModel.data(ix,TaskManager.AbstractTasksModel.IsLauncher),
                HasLauncher:!!sourceDock.tasksModel.data(ix,TaskManager.AbstractTasksModel.HasLauncher),
                WinIdList:Array.from(sourceDock.tasksModel.data(ix,TaskManager.AbstractTasksModel.WinIdList)||[]).map(String)});
        }
        const launchers=Array.from(sourceDock.tasksModel.launcherList);
        return JSON.stringify({rows:rows,launcherList:launchers.filter(url=>identity("",String(url))!==""),
            foreignRowCount:sourceDock.tasksModel.count-rows.length,
            foreignLauncherCount:launchers.filter(url=>identity("",String(url))==="").length});
    }
    function armRefusal() {
        if (armed || observerCalls !== 0) throw new Error("observer_not_fresh");
        armed=true;
        movedHandler=function() {
            if (!armed) return;
            armed=false;
            sourceDock.tasksModel.rowsMoved.disconnect(movedHandler);
            observerCalls++;
            observerAccepted=sourceDock.profiles.commitPresentation(
                {calendarEvents: !sourceDock.profiles.effective.calendarEvents},
                sourceDock.profiles.activeProfileId,sourceDock.profiles.revision);
        };
        sourceDock.tasksModel.rowsMoved.connect(movedHandler);
    }
    function disarm() {
        if (armed) { sourceDock.tasksModel.rowsMoved.disconnect(movedHandler); armed=false; }
    }
    function normalize(from,to) {
        const changed=sourceDock.tasksModel.move(from,to);
        sourceDock.tasksModel.syncLaunchers();return changed;
    }
    function savedLaunchers() { return JSON.stringify(sourceDock.profiles.effective.launchers); }
}
