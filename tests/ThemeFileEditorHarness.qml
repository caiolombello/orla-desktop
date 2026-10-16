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
    property var appearance: state
    property var editor: editorView
    property var configuration: config
    property QtObject config: QtObject {
        property string appearanceJSON: ""
        property string theme: "glass"
        property int iconSize: 42
        property bool animations: true
        property int writes: 0
        onAppearanceJSONChanged: writes++
    }
    property QtObject transport: QtObject {
        property int calls: 0
        function loadThemeFile(url, resolve, reject) { calls++; }
    }
    Candidate.AppearanceState { id: state; configuration: config; themeFileTransport: harness.transport }
    Candidate.AppearanceEditor {
        id: editorView
        anchors.fill: parent
        appearance: state
        themeFileWindow: harness
    }
    Component.onCompleted: state.begin()
}
