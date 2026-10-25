import QtQuick
import org.kde.plasma.private.kicker as Kicker

// Private Kicker model verified against Plasma 6.7.5 and isolated by Loader.
// https://invent.kde.org/plasma/plasma-workspace/-/blob/v6.7.5/applets/kicker/recentusagemodel.h
// Standalone it names apps without the parent menu's name format.
Item {
    id: root
    readonly property string status: "ready"
    property var items: []
    Kicker.RecentUsageModel {
        id: recent
        shownItems: Kicker.RecentUsageModel.OnlyApps
        ordering: Kicker.RecentUsageModel.Recent
    }
    Instantiator {
        id: rows
        model: recent
        delegate: QtObject {
            required property int index
            required property var display
            required property var decoration
            required property var favoriteId
        }
        onObjectAdded: root.update()
        onObjectRemoved: root.update()
    }
    Connections {
        target: recent
        function onDataChanged() { root.update(); }
        function onModelReset() { root.update(); }
    }
    function update() {
        const result = [];
        for (let row = 0; row < rows.count && result.length < 8; row++) {
            const entry = rows.objectAt(row);
            if (!entry) continue;
            result.push({id: String(entry.favoriteId || ""), name: String(entry.display || ""),
                icon: typeof entry.decoration === "string" ? entry.decoration : ""});
        }
        items = result;
    }
    // Launch by ID: the order changes as soon as another app starts.
    function launch(id) {
        for (let row = 0; row < rows.count; row++) {
            const entry = rows.objectAt(row);
            if (entry && String(entry.favoriteId) === id) return recent.trigger(row, "", null) === true;
        }
        return false;
    }
}
