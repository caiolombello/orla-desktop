import QtQuick
import "../package/contents/ui" as DockUI

Item {
    id: harness
    property alias first: primary
    property alias second: replacement
    property var currentProfiles: primary
    property bool viewEligible: true
    property var rows: initialRows()
    property int calls: 0
    property int writes: 0
    property int lastFrom: -1
    property int lastTo: -1
    property bool guardBeforeMove: false
    property bool guardAfterMove: false
    property bool intentAliveAfterSignals: false
    property string signalOrder: "saved-first"
    QtObject {
        id: primary
        property string activeProfileId: "work"
        property int revision: 1
        property bool writable: true
        property var effective: ({launchers:["applications:A.desktop", "applications:B.desktop"]})
    }
    QtObject {
        id: replacement
        property string activeProfileId: "work"
        property int revision: 1
        property bool writable: true
        property var effective: ({launchers:["applications:A.desktop", "applications:B.desktop"]})
    }
    function initialRows() {
        return [{identity:"A",rank:0,order:0}, {identity:"B",rank:1,order:1}, {identity:"U",rank:-1,order:2}];
    }
    function reset() {
        drag.cancel();
        currentProfiles = primary;
        primary.activeProfileId = "work";
        primary.writable = true;
        primary.revision = 1;
        primary.effective = {launchers:["applications:A.desktop", "applications:B.desktop"]};
        rows = initialRows();
        viewEligible = true;
        calls = 0; writes = 0; lastFrom = -1; lastTo = -1;
        guardBeforeMove = false; guardAfterMove = false; intentAliveAfterSignals = false;
    }
    function commit(from, to, guard) {
        calls++;
        lastFrom = from; lastTo = to;
        guardBeforeMove = guard();
        if (!guardBeforeMove) return false;
        const next = rows.map(row => ({identity:row.identity, rank:row.rank, order:row.order}));
        const moved = next.splice(from, 1)[0];
        next.splice(to, 0, moved);
        rows = next.map((row, index) => ({identity:row.identity, rank:row.rank, order:index}));
        // The callback now sees a changed model, while its captured domain is unchanged.
        guardAfterMove = guard();
        if (!guardAfterMove) return false;
        const owner = currentProfiles;
        const launchers = rows.filter(row => row.rank >= 0).map(row => "applications:" + row.identity + ".desktop");
        if (JSON.stringify(owner.effective.launchers) !== JSON.stringify(launchers)) {
            writes++;
            if (signalOrder === "revision-first") owner.revision++;
            owner.effective = {launchers:launchers};
            if (signalOrder !== "revision-first") owner.revision++;
            intentAliveAfterSignals = drag.pressed;
        }
        return true;
    }
    DockUI.TaskDragState {
        id: drag
        objectName: "taskDragState"
        profiles: harness.currentProfiles
        viewActive: harness.viewEligible
        readOrder: () => harness.rows
        commitMove: (from, to, guard) => harness.commit(from, to, guard)
    }
}
