import QtQuick
import "../package/contents/ui" as DockUI

// Fake TasksModel and KWin backend for the dock's app-wide actions. Rows use
// synthetic app ids and window handles only.
Item {
    id: harness
    property var calls: []
    property alias tasks: fakeTasks
    property alias kwin: fakeKwin
    function record(entry) { calls = calls.concat([entry]); }
    // Same rows behind a model without requestVirtualDesktops, like an older TaskManager.
    function dropMoveSupport() {
        actions.model = {count: fakeTasks.count, makeModelIndex: row => fakeTasks.makeModelIndex(row),
            data: (index, role) => fakeTasks.data(index, role)};
    }
    function row(appId, handle, extra) {
        return Object.assign({appId: appId, isWindow: true, minimized: false, minimizable: true,
            closable: true, winIds: [handle], desktops: ["d1"], allDesktops: false,
            desktopsChangeable: true}, extra || {});
    }

    QtObject {
        id: fakeTasks
        objectName: "fakeTasks"
        property var rows: [
            harness.row("org.example.Editor", "w1"),
            harness.row("org.example.Editor", "w2", {minimized: true, desktops: ["d2"]}),
            harness.row("org.example.Viewer", "w3"),
            harness.row("org.example.Editor", "w4", {closable: false, minimizable: false}),
            {appId: "org.example.Editor", isWindow: false, winIds: [], desktops: []}
        ]
        readonly property int count: rows.length
        function makeModelIndex(row) { return {row: row}; }
        function data(index, role) { return rows[index.row][role]; }
        function requestToggleMinimized(index) { harness.record("minimize:" + rows[index.row].winIds[0]); }
        function requestClose(index) { harness.record("close:" + rows[index.row].winIds[0]); }
        function requestVirtualDesktops(index, desktops) {
            harness.record("desktops:" + rows[index.row].winIds[0] + ">" + JSON.stringify(desktops));
        }
    }
    QtObject {
        id: fakeKwin
        objectName: "fakeKwin"
        property var desktopIds: ["d1", "d2", "d3"]
        property var desktopNames: ["Um", "Dois", "Três"]
        property bool windowViewAvailable: true
        property bool failing: false
        function showWindowView(handles) {
            if (failing) throw new Error("bus gone");
            harness.record("windowview:" + handles.join(","));
        }
    }
    DockUI.DockAppActions {
        id: actions
        objectName: "dockAppActions"
        model: fakeTasks
        roles: ({appId: "appId", isWindow: "isWindow", minimized: "minimized", minimizable: "minimizable",
            closable: "closable", winIds: "winIds", desktops: "desktops", allDesktops: "allDesktops",
            desktopsChangeable: "desktopsChangeable"})
        backend: fakeKwin
    }
}
