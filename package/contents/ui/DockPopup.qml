import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls as Controls

Controls.Popup {
    id: popup
    required property var dock
    property string title: ""
    property real anchorX: dock.width / 2
    readonly property real screenHeight: dock.Screen.height > 0 ? dock.Screen.height : 640
    readonly property real maximumPopupHeight: Math.max(1, screenHeight - dock.height - 30)
    function openAt(control) {
        anchorX = control ? control.mapToItem(dock, control.width / 2, 0).x : dock.width / 2;
        open();
    }
    default property alias body: bodyColumn.data
    parent: dock
    popupType: Controls.Popup.Window
    width: 350
    // Window popups must extend beyond the panel's small enclosing window.
    margins: -1
    height: Math.min(implicitHeight, maximumPopupHeight)
    x: Math.max(0, Math.min(Math.max(0, dock.width - width), anchorX - width / 2))
    y: dock.popAbove ? -height - 10 : dock.height + 10
    padding: 20
    focus: true
    closePolicy: Controls.Popup.CloseOnEscape | Controls.Popup.CloseOnPressOutside
    palette.window: dock.surface
    palette.windowText: dock.foreground
    palette.text: dock.foreground
    palette.buttonText: dock.foreground
    palette.base: dock.light ? "#ffffff" : "#20293b"
    palette.button: dock.light ? "#e4e0d8" : "#2c3850"
    palette.highlight: dock.accent
    background: Rectangle { color: dock.light ? "#f7f3ec" : "#1d2535"; radius: 18; border.width: 1; border.color: dock.light ? "#cec9bf" : "#3c4b65" }
    contentItem: ColumnLayout {
        spacing: 16
        RowLayout {
            Layout.fillWidth: true
            Controls.Label { text: popup.title; font.bold: true; font.pixelSize: 16; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Controls.ToolButton { text: "×"; Accessible.name: qsTr("Fechar"); onClicked: popup.close() }
        }
        ColumnLayout { id: bodyColumn; Layout.fillWidth: true; spacing: 10 }
    }
}
