import QtQuick
import QtQuick.Dialogs as Dialogs
import "../code/ThemeFile.js" as ThemeFile

QtObject {
    id: picker
    required property var appearance
    property var parentWindow: null
    property bool active: true
    property var selectionState: null
    property var selectionToken: null
    readonly property bool visible: chooser.visible

    function cancelSelection() {
        const state = selectionState, token = selectionToken;
        selectionState = null;
        selectionToken = null;
        if (chooser) chooser.close();
        if (state && token) state.cancelThemeFileSelection(token);
    }
    function open() {
        if (!active || !appearance || !parentWindow) return false;
        cancelSelection();
        const state = appearance, window = parentWindow;
        const token = state.beginThemeFileSelection(picker);
        if (!token) return false;
        selectionState = state;
        selectionToken = token;
        if (!active || appearance !== state || parentWindow !== window || !state.themeFileSelecting) {
            cancelSelection();
            return false;
        }
        chooser.open();
        return true;
    }
    onActiveChanged: if (!active) cancelSelection()
    onParentWindowChanged: cancelSelection()
    onAppearanceChanged: cancelSelection()
    Component.onDestruction: cancelSelection()
    property Connections stateConnections: Connections {
        target: picker.selectionState
        function onBusyChanged() {
            if (picker.selectionState && !picker.selectionState.busy) picker.cancelSelection();
        }
    }
    property Dialogs.FileDialog chooser: Dialogs.FileDialog {
        id: chooser
        objectName: "appearanceThemeFileDialog"
        parentWindow: picker.parentWindow
        modality: Qt.WindowModal
        title: qsTr("Importar tema")
        fileMode: Dialogs.FileDialog.OpenFile
        nameFilters: [qsTr("Tema JSON (*.json)")]
        onAccepted: {
            const state = picker.selectionState, token = picker.selectionToken;
            if (state && token)
                state.acceptThemeFileSelection(token, ThemeFile.encodedSelection(selectedFile.toString()));
        }
        onRejected: picker.cancelSelection()
    }
}
