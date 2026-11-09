import QtQuick
import QtCore
import Qt.labs.folderlistmodel
import "../code/Downloads.js" as Downloads

// The Downloads stack beside the Trash, as in macOS: a folder tile that opens
// the newest downloads in a popup. It only lists the folder; opening a file
// goes to its default application.
Tile {
    id: stack
    // Tests point this at a private folder.
    property url folder: StandardPaths.writableLocation(StandardPaths.DownloadLocation)
    property var entries: []
    readonly property int count: entries.length
    iconSource: "folder-download"
    title: qsTr("Downloads")
    subtitle: count === 0 ? qsTr("Vazio") : count === 1 ? qsTr("1 item recente") : qsTr("%1 itens recentes").arg(count)
    tooltip: title + " · " + subtitle

    function read() {
        const rows = [];
        for (let index = 0; index < contents.count; ++index)
            rows.push({name: contents.get(index, "fileName"), url: contents.get(index, "fileUrl"),
                isDir: contents.get(index, "fileIsDir")});
        entries = Downloads.entries(rows, Downloads.limit);
    }

    FolderListModel {
        id: contents
        folder: stack.folder
        showDirs: true
        showDirsFirst: false
        showDotAndDotDot: false
        showHidden: false
        // Newest first, as QDir sorts by time.
        sortField: FolderListModel.Time
        onCountChanged: Qt.callLater(stack.read)
        onStatusChanged: if (status === FolderListModel.Ready) Qt.callLater(stack.read)
    }
}
