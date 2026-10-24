import QtQuick
import QtCore
import Qt.labs.folderlistmodel

// The Trash at the end of the dock, as in macOS: an empty or full bin that
// opens the trash in the file manager. It only watches the trash folder; it
// never deletes or restores anything.
Tile {
    id: trash
    // Tests point these at a private folder and a recorder.
    property url filesFolder: StandardPaths.writableLocation(StandardPaths.GenericDataLocation) + "/Trash/files"
    property var opener: url => Qt.openUrlExternally(url)
    readonly property int count: contents.count
    readonly property bool full: count > 0
    iconSource: full ? "user-trash-full" : "user-trash"
    title: qsTr("Lixeira")
    subtitle: count === 0 ? qsTr("Vazia") : count === 1 ? qsTr("1 item") : qsTr("%1 itens").arg(count)
    tooltip: title + " · " + subtitle
    onClicked: opener("trash:/")

    FolderListModel {
        id: contents
        folder: trash.filesFolder
        showDirs: true
        showDotAndDotDot: false
        showHidden: true
        showOnlyReadable: false
        sortField: FolderListModel.Unsorted
    }
}
