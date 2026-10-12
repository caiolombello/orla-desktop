import QtQuick
import org.kde.plasma.core as PlasmaCore

// Production surface: anchored Plasma dialog, not a generic Qt.Popup whose Wayland
// xdg_popup parent may be the panel's layer-shell surface. The menu remains a
// Controls.Popup.Item, hosted in this full-height window rather than the panel.
PlasmaCore.Dialog {
    id: host
    visible: false
    // PopupMenu avoids Dialog.AppletPopup's deliberate screen-center snapping.
    type: PlasmaCore.Dialog.PopupMenu
    flags: Qt.Window | Qt.FramelessWindowHint
    location: PlasmaCore.Types.TopEdge
    hideOnWindowDeactivate: true
    backgroundHints: PlasmaCore.Dialog.StandardBackground
    property var activePopup: null
    property alias hostItem: content

    function showPopup(popup, anchor) {
        activePopup = popup;
        visualParent = anchor;
        visible = true;
        requestActivate();
    }
    function hidePopup(popup) {
        if (activePopup !== popup) return;
        activePopup = null;
        visible = false;
    }
    onVisibleChanged: if (!visible && activePopup && activePopup.visible) activePopup.close()

    mainItem: Item {
        id: content
        width: host.activePopup ? host.activePopup.width : 1
        height: host.activePopup ? Math.max(1, host.activePopup.implicitHeight) : 1
    }
}
