import QtQuick
import org.kde.plasma.core as PlasmaCore

// Loaded only by the production panel backend; fixtures keep Controls.Popup.
PlasmaCore.Dialog {
    id: dialog
    readonly property var owner: popupOwner
    objectName: "nativeDockDialog"
    visualParent: owner.anchorControl
    location: owner.dock.popAbove ? PlasmaCore.Types.BottomEdge : PlasmaCore.Types.TopEdge
    // AppletPopup deliberately snaps near-center controls to screen center.
    type: PlasmaCore.Dialog.PopupMenu
    flags: Qt.Window | Qt.FramelessWindowHint
    backgroundHints: PlasmaCore.Dialog.NoBackground
    color: "transparent"
    hideOnWindowDeactivate: true
    mainItem: owner.popupSurface
    visible: owner.visible
    onVisibleChanged: {
        if (visible) {
            requestActivate();
            mainItem.forceActiveFocus(Qt.PopupFocusReason);
            owner.opened();
        } else if (owner.visible) owner.close();
    }
}
