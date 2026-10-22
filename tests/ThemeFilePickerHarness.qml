import QtQuick
import QtQuick.Window
import QtQuick.Controls as Controls
import QtQuick.Dialogs as Dialogs
import "source/ui" as Candidate

Controls.ApplicationWindow {
    id: harness
    width: 440
    height: 640
    visible: true
    property bool selectionActive: true
    property var selectedAppearance: primaryState
    property var selectedWindow: harness
    property var picker: filePicker
    property var appearance: primaryState
    property var otherAppearance: alternateState
    property var transport: fakeTransport
    property var configuration: config
    property var otherWindow: alternateWindow
    property QtObject config: QtObject {
        property string appearanceJSON: ""
        property string theme: "glass"
        property int iconSize: 42
        property bool animations: true
        property int writes: 0
        onAppearanceJSONChanged: writes++
    }
    property QtObject transportObject: QtObject {
        id: fakeTransport
        property var requests: []
        function loadThemeFile(url, resolve, reject) {
            requests = requests.concat([{url:url, resolve:resolve, reject:reject}]);
        }
        function succeed(index, raw) { requests[index].resolve(raw); }
        function fail(index) { requests[index].reject({message:"synthetic failure"}); }
    }
    Candidate.AppearanceState {
        id: primaryState
        configuration: config
        themeFileTransport: fakeTransport
    }
    Candidate.AppearanceState {
        id: alternateState
        configuration: config
        themeFileTransport: fakeTransport
    }
    Window { id: alternateWindow; visible: false; width: 440; height: 640 }
    QtObject { id: newerOwner }
    property var foreignToken: null
    function claimNewerSelection() { foreignToken = primaryState.beginThemeFileSelection(newerOwner); }
    Candidate.ThemeFilePicker {
        id: filePicker
        objectName: "fixtureThemeFilePicker"
        appearance: harness.selectedAppearance
        parentWindow: harness.selectedWindow
        active: harness.selectionActive
    }
    function snapshot() {
        return JSON.stringify({text:primaryState.themeText, error:primaryState.themeError,
            draft:primaryState.draft, preview:primaryState.preview,
            otherText:alternateState.themeText, otherError:alternateState.themeError,
            writes:config.writes});
    }
    function shutdown() {
        filePicker.cancelSelection(); primaryState.cancel(); alternateState.cancel(); alternateWindow.close();
    }
    Component.onCompleted: {
        // Public Qt option selects the portable Quick fallback; no production override seam.
        filePicker.chooser.options = Dialogs.FileDialog.DontUseNativeDialog;
        filePicker.chooser.currentFolder = Qt.resolvedUrl(".");
        primaryState.begin(); alternateState.begin();
    }
}
