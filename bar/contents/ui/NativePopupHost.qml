import QtQuick
import QtQuick.Controls as Controls
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
    property alias hostItem: popupContent
    // Plasma resizes contentItem before the QWindow. Qt 6.11's overlay can
    // retain an origin calculated against the previous window size.
    function syncOverlayGeometry() {
        const overlay = content.Controls.Overlay.overlay;
        if (!overlay) return;
        overlay.x = (host.width - host.contentItem.width) / 2;
        overlay.y = (host.height - host.contentItem.height) / 2;
    }
    onWidthChanged: syncOverlayGeometry()
    onHeightChanged: syncOverlayGeometry()

    function showPopup(popup, anchor) {
        activePopup = popup;
        visualParent = anchor;
        visible = true;
        syncOverlayGeometry();
        requestActivate();
    }
    function hidePopup(popup) {
        if (activePopup !== popup) return;
        activePopup = null;
        visible = false;
    }
    onVisibleChanged: if (!visible && activePopup && activePopup.visible) activePopup.close()

    // Keep the popup parent in overlay coordinates. When Plasma resizes its
    // window, overlay movement then invalidates Qt's cached popup position.
    // Preserve the dialog frame margins without imposing a menu height.
    Item {
        id: popupContent
        parent: content.Controls.Overlay.overlay
        x: content.x
        y: content.y
        width: content.width
        height: content.height
    }

    mainItem: Item {
        id: content
        width: host.activePopup ? host.activePopup.width : 1
        height: host.activePopup ? Math.max(1, host.activePopup.implicitHeight) : 1
    }
}
