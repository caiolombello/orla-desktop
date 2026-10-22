import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls as Controls

Item {
    id: popup
    required property var dock
    property string title: ""
    property real anchorX: dock.width / 2
    property var anchorControl: dock
    property bool nativeOpenActive: false
    readonly property bool nativeBackend: Boolean(dock.nativePopups)
    readonly property real screenHeight: dock.Screen.height > 0 ? dock.Screen.height : 640
    readonly property real maximumPopupHeight: Math.max(1, screenHeight - dock.height - 30)
    readonly property alias popupSurface: surface
    readonly property alias nativeDialog: nativeLoader.item
    property alias popupType: fallback.popupType
    property real margins: -1
    default property alias body: bodyColumn.data
    signal aboutToShow()
    signal aboutToHide()
    signal opened()
    signal closed()
    parent: dock
    visible: false
    width: 350
    implicitHeight: surface.implicitHeight
    height: Math.min(implicitHeight, maximumPopupHeight)
    x: Math.max(0, Math.min(Math.max(0, dock.width - width), anchorX - width / 2))
    y: dock.popAbove ? -height - 10 : dock.height + 10

    function openAt(control) {
        anchorControl = control || dock;
        anchorX = anchorControl.mapToItem(dock, anchorControl.width / 2, 0).x;
        open();
    }
    function open() {
        if (visible) return;
        if (nativeBackend) {
            surface.parent = nativeDialog.contentItem;
            // Dialog synchronizes mainItem sizes; reset the current facade budget.
            surface.width = Qt.binding(() => popup.width);
            surface.height = Qt.binding(() => popup.height);
            surface.visible = true;
            aboutToShow();
            nativeOpenActive = true;
            visible = true;
        } else fallback.open();
    }
    function close() {
        if (nativeBackend) {
            if (!visible) return;
            aboutToHide();
            visible = false;
        } else fallback.close();
    }

    Controls.Popup {
        id: fallback
        parent: popup.dock
        popupType: Controls.Popup.Window
        width: popup.width
        height: popup.height
        x: popup.x
        y: popup.y
        margins: popup.margins
        padding: 0
        focus: true
        closePolicy: Controls.Popup.CloseOnEscape | Controls.Popup.CloseOnPressOutside
        background: Item {}
        contentItem: popup.nativeBackend ? null : surface
        onAboutToShow: { surface.parent = fallback.background.parent; popup.visible = true; popup.aboutToShow(); }
        onAboutToHide: popup.aboutToHide()
        onOpened: popup.opened()
        onClosed: { popup.visible = false; popup.closed(); }
    }
    onVisibleChanged: {
        if (!nativeBackend || visible || !nativeOpenActive) return;
        nativeOpenActive = false;
        // Keep the shared content owned by this facade while its host is hidden.
        surface.parent = popup;
        closed();
        const control = anchorControl;
        Qt.callLater(() => {
            const ownerWindow = control ? control.Window.window : null;
            if (ownerWindow && ownerWindow.active && control.visible && control.enabled)
                control.forceActiveFocus(Qt.PopupFocusReason);
        });
    }
    Loader {
        id: nativeLoader
        objectName: "nativeDockPopupLoader"
        property var popupOwner: popup
        active: popup.nativeBackend
        source: active ? Qt.resolvedUrl("NativeDockPopup.qml") : ""
    }
    Controls.Pane {
        id: surface
        width: popup.width
        height: popup.height
        padding: 20
        focus: true
        Keys.onEscapePressed: event => { popup.close(); event.accepted = true; }
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
}
