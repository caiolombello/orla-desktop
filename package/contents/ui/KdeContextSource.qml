import QtQuick
import QtQml.Models
import org.kde.activities as Activities
import org.kde.taskmanager as TaskManager

Item {
    id: source
    visible: false
    width: 0
    height: 0
    property bool refreshPending: false
    property var snapshot: ({
        outputName: "",
        activity: {status: "loading", currentId: "", ids: [], names: []},
        desktop: {status: "loading", currentId: "", ids: [], names: []}
    })

    function scheduleRefresh() {
        if (refreshPending) return;
        refreshPending = true;
        Qt.callLater(() => {
            if (!source) return;
            refreshPending = false;
            refresh();
        });
    }
    function refresh() {
        const activityIds = [], activityNames = [];
        let currentActivity = "";
        for (let index = 0; index < activityItems.count; index++) {
            const item = activityItems.objectAt(index);
            if (!item) continue;
            activityIds.push(item.activityId);
            activityNames.push(item.activityName);
            if (item.isCurrent) currentActivity = item.activityId;
        }
        const desktopIds = Array.from(desktopModel.desktopIds || []).map(value => String(value));
        const desktopNames = Array.from(desktopModel.desktopNames || []).map(value => String(value));
        const currentDesktop = String(desktopModel.currentDesktop || "");
        snapshot = {
            outputName: "",
            activity: currentActivity.length > 0 ? {
                status: "ready", currentId: currentActivity, ids: activityIds, names: activityNames
            } : {status: "unavailable", currentId: "", ids: [], names: []},
            desktop: currentDesktop.length > 0 && desktopIds.indexOf(currentDesktop) !== -1 ? {
                status: "ready", currentId: currentDesktop, ids: desktopIds, names: desktopNames
            } : {status: "unavailable", currentId: "", ids: [], names: []}
        };
    }

    Activities.ActivityModel { id: activityModel }
    Instantiator {
        id: activityItems
        model: activityModel
        delegate: QtObject {
            required property var model
            property string activityId: String(model.id || "")
            property string activityName: String(model.name || "")
            property bool isCurrent: Boolean(model.current)
            onActivityIdChanged: source.scheduleRefresh()
            onActivityNameChanged: source.scheduleRefresh()
            onIsCurrentChanged: source.scheduleRefresh()
            Component.onCompleted: source.scheduleRefresh()
            Component.onDestruction: source.scheduleRefresh()
        }
        onObjectAdded: source.scheduleRefresh()
        onObjectRemoved: source.scheduleRefresh()
    }
    TaskManager.VirtualDesktopInfo { id: desktopModel }
    Connections {
        target: desktopModel
        function onCurrentDesktopChanged() { source.scheduleRefresh(); }
        function onCurrentDesktopForScreenChanged() { source.scheduleRefresh(); }
        function onDesktopIdsChanged() { source.scheduleRefresh(); }
        function onDesktopNamesChanged() { source.scheduleRefresh(); }
    }
    Component.onCompleted: scheduleRefresh()
}
