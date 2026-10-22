import QtQuick
import QtQuick.Dialogs as Dialogs
import "../code/ThemeFile.js" as ThemeFile

// One dialog per opening: late native signals retain their original owner/token.
QtObject {
    id: picker
    required property var manager
    property var parentWindow: null
    property bool active: false
    property var selectionState: null
    property var selectionToken: null
    property var chooser: null
    property var handoff: null
    readonly property bool visible: chooser ? chooser.visible : false

    function clearSelectionRefs(token, dialog) {
        if (selectionToken === token) {
            selectionState = null;
            if (selectionToken === token) selectionToken = null;
        }
        if (chooser === dialog) chooser = null;
    }
    function cancelSelection() {
        const state = selectionState, token = selectionToken, dialog = chooser, transfer = handoff;
        if (transfer && transfer.cancelled) return;
        if (transfer) transfer.cancelled = true;
        clearSelectionRefs(token, dialog);
        if (transfer && (!dialog || dialog === transfer.dialog)) retireHandoff(transfer);
        else if (dialog) { dialog.close(); dialog.destroy(); }
        if (state && token) state.cancelFileSelection(picker, token);
        if (transfer) transfer.state.cancelFileSelection(picker, transfer.token);
        if (handoff === transfer) handoff = null;
    }
    function current(state, token, window) {
        return Qt.isQtObject(state) && active && manager === state && parentWindow === window && window && window.visible
            && state.ownsFileSelection(picker, token);
    }
    function open() {
        if (!active || !manager || !parentWindow || !parentWindow.visible || !parentWindow.active) return false;
        cancelSelection();
        const state = manager, window = parentWindow;
        const token = state.beginFileSelection(picker);
        if (!token) return false;
        selectionState = state;
        selectionToken = token;
        if (!current(state, token, window)) { cancelSelection(); return false; }
        const dialog = createDialog(state, token, window);
        if (!dialog) { cancelSelection(); return false; }
        if (!current(state, token, window)) {
            dialog.destroy();
            cancelSelection();
            return false;
        }
        chooser = dialog;
        dialog.open();
        return true;
    }
    function createDialog(state, token, window) {
        const dialog = dialogComponent.createObject(picker, {parentWindow: window,
            requestState: state, requestWindow: window});
        // The initial-property map copies JS objects in Qt 6.11; direct assignment preserves identity.
        if (dialog) dialog.requestToken = token;
        return dialog;
    }
    function handoffLive(transfer) {
        return handoff === transfer && !transfer.cancelled && Qt.isQtObject(transfer.state)
            && active && manager === transfer.state && parentWindow === transfer.window && transfer.window.visible;
    }
    function retireHandoff(transfer) {
        if (transfer.retired) return;
        transfer.retired = true;
        transfer.dialog.close();
        transfer.dialog.destroy();
    }
    function acceptDialog(dialog) {
        if (handoff || chooser !== dialog || selectionState !== dialog.requestState || selectionToken !== dialog.requestToken) return;
        const state = dialog.requestState, token = dialog.requestToken;
        if (!current(state, token, dialog.requestWindow)) { cancelSelection(); return; }
        const uri = ThemeFile.encodedSelection(dialog.selectedFile.toString());
        const transfer = {state: state, token: token, window: dialog.requestWindow,
            dialog: dialog, cancelled: false, retired: false};
        handoff = transfer;
        // Setters and the state's reservation-to-flight signals can synchronously revoke this opening.
        clearSelectionRefs(token, dialog);
        retireHandoff(transfer);
        if (handoffLive(transfer) && state.ownsFileSelection(picker, token))
            state.acceptFileSelection(picker, token, uri, () => handoffLive(transfer));
        else state.cancelFileSelection(picker, token);
        if (handoff === transfer) handoff = null;
    }
    onActiveChanged: if (!active) cancelSelection()
    onParentWindowChanged: cancelSelection()
    onManagerChanged: cancelSelection()
    Component.onDestruction: cancelSelection()
    property Connections stateConnections: Connections {
        target: picker.selectionState
        function onSelectingChanged() {
            const state = picker.selectionState;
            if (state && !state.ownsFileSelection(picker, picker.selectionToken)) picker.cancelSelection();
        }
    }
    property Connections windowConnections: Connections {
        target: picker.parentWindow
        // A native modal chooser takes activity from its parent; visibility owns this lifetime.
        function onVisibleChanged() { if (picker.parentWindow && !picker.parentWindow.visible) picker.cancelSelection(); }
    }
    property Component dialogComponent: Component {
        Dialogs.FileDialog {
            id: dialog
            property var requestState: null
            property var requestToken: null
            property var requestWindow: null
            objectName: "addonFileDialog"
            modality: Qt.WindowModal
            title: qsTr("Adicionar complemento")
            fileMode: Dialogs.FileDialog.OpenFile
            nameFilters: [qsTr("Todos os arquivos (*)")]
            onAccepted: picker.acceptDialog(dialog)
            onRejected: if (picker.chooser === dialog) picker.cancelSelection()
        }
    }
}
