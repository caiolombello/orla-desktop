import QtQuick
import QtQuick.Window

// Host contract only. This is not the native Plasma shell surface implementation.
Window {
    id: host
    objectName: "fixturePopupHost"
    visible: false
    flags: Qt.Window | Qt.FramelessWindowHint
    property var activePopup: null
    property alias hostItem: content
    width: content.width
    height: content.height
    function showPopup(popup, anchor) {
        activePopup = popup;
        const point = anchor.mapToGlobal(0, anchor.height + 2);
        x = point.x; y = point.y;
        visible = true;
        requestActivate();
    }
    function hidePopup(popup) {
        if (activePopup !== popup) return;
        activePopup = null;
        visible = false;
    }
    onVisibleChanged: if (!visible && activePopup && activePopup.visible) activePopup.close()
    Item {
        id: content
        width: host.activePopup ? host.activePopup.width : 1
        height: host.activePopup ? Math.max(1, host.activePopup.implicitHeight) : 1
    }
}
