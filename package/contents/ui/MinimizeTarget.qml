import QtQuick
import QtQuick.Window
import "../code/MinimizeTarget.js" as Geometry

// The landing box of KWin's minimize effect for one task, placed over the
// artwork's resting slot. It is the delegate handed to
// TasksModel.requestPublishDelegateGeometry: Wayland reads this item's own
// scene geometry, X11 the global rect, so hover lift and bounce never move it.
Item {
    id: minimizeTarget
    // Anything with makeModelIndex(row) and requestPublishDelegateGeometry(index, rect, delegate).
    property var publisher: null
    property int row: -1
    // Only rows with windows have something to minimize.
    property bool active: false
    // Changes when a window joins or leaves the row.
    property string windows: ""
    property Item artwork: null
    // The visible lane; tiles scrolled out of view target its nearest edge.
    property Item bounds: null
    // Bumped by the dock whenever something above the tile moves.
    property int epoch: 0
    property string publishedKey: ""
    property var publishedWindow: null
    readonly property bool pending: throttle.running
    visible: false
    enabled: false

    function schedule() {
        if (active && !throttle.running) throttle.start();
    }
    function forget() {
        publishedKey = "";
        publishedWindow = null;
        schedule();
    }
    function publish() {
        if (!active || !publisher || !artwork || !artwork.parent || !parent || row < 0 || !Window.window) return false;
        // Map from the artwork's parent: its own lift, scale and bounce stay out.
        const origin = artwork.parent.mapToItem(parent, artwork.x, artwork.y);
        let clip = null;
        if (bounds) {
            const corner = bounds.mapToItem(parent, 0, 0);
            clip = {x: corner.x, y: corner.y, width: bounds.width, height: bounds.height};
        }
        const local = Geometry.stableRect({x: origin.x, y: origin.y, width: artwork.width, height: artwork.height}, clip);
        if (!local) return false;
        x = local.x;
        y = local.y;
        width = local.width;
        height = local.height;
        const rect = Geometry.globalRect(local, mapToGlobal(0, 0));
        const key = Geometry.publicationKey(row, windows, rect);
        if (key === publishedKey && publishedWindow === Window.window) return false;
        publisher.requestPublishDelegateGeometry(publisher.makeModelIndex(row),
            Qt.rect(rect.x, rect.y, rect.width, rect.height), minimizeTarget);
        publishedKey = key;
        publishedWindow = Window.window;
        return true;
    }

    Timer {
        id: throttle
        interval: Geometry.publishInterval
        onTriggered: minimizeTarget.publish()
    }
    onActiveChanged: forget()
    onPublisherChanged: forget()
    onRowChanged: schedule()
    onWindowsChanged: schedule()
    onEpochChanged: schedule()
    Window.onWindowChanged: forget()
    Connections {
        // A shown-again panel may own a new surface; the old target died with it.
        target: minimizeTarget.Window.window
        function onVisibleChanged() { if (target.visible) minimizeTarget.forget(); }
    }
    Connections {
        target: minimizeTarget.parent
        ignoreUnknownSignals: true
        function onXChanged() { minimizeTarget.schedule(); }
        function onYChanged() { minimizeTarget.schedule(); }
        function onWidthChanged() { minimizeTarget.schedule(); }
        function onHeightChanged() { minimizeTarget.schedule(); }
    }
    Connections {
        target: minimizeTarget.artwork
        function onXChanged() { minimizeTarget.schedule(); }
        function onYChanged() { minimizeTarget.schedule(); }
        function onWidthChanged() { minimizeTarget.schedule(); }
        function onHeightChanged() { minimizeTarget.schedule(); }
    }
    Component.onCompleted: schedule()
}
