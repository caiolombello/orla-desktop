import QtQuick
import "../package/contents/ui" as DockUI

QtObject {
    id: root
    property double fakeNow: 1000
    property var announcements: []
    property QtObject eventState: DockUI.EventState {
        objectName: "eventState"
        enabled: true
        completionEnabled: true
        audioEnabled: true
        activeScope: "profile:work"
        activeContextGeneration: 4
        nowProvider: function() { return root.fakeNow; }
        onAnnouncementRequested: event => root.announcements = root.announcements.concat([event])
    }
}
