import QtQuick
import QtQuick.Controls as Controls
import "../package/contents/code/Style.js" as Style

Controls.ApplicationWindow {
    id: window
    width: 580
    height: 720
    minimumWidth: 320
    minimumHeight: 240
    visible: true
    title: qsTr("Composição Orla")
    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
    readonly property var ui: Style.scheme(Style.schemeFor(systemPalette.window))
    color: ui.canvas
    palette.window: ui.surface
    palette.base: ui.raised
    palette.alternateBase: ui.sunken
    palette.mid: ui.border
    palette.windowText: ui.text
    palette.text: ui.text
    palette.buttonText: ui.text
    palette.button: ui.raised
    palette.highlight: ui.accent
    palette.highlightedText: ui.onAccent
    onClosing: event => { event.accepted = workspaceController.requestClose(); }

    CompositionView {
        anchors.fill: parent
        controller: workspaceController
    }
}
