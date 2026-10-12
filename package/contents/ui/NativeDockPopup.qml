import QtQuick
import org.kde.plasma.core as PlasmaCore

// Loaded only by the production panel backend; fixtures keep Controls.Popup.
PlasmaCore.Dialog {
    id: dialog
    readonly property var owner: popupOwner
    objectName: "nativeDockDialog"
    // Retain the tile center, but place the popup outside the complete dock.
    property Item anchorProxy: Item {
        parent: dialog.owner.dock
        width: dialog.owner.anchorControl ? dialog.owner.anchorControl.width : 1
        x: dialog.owner.anchorX - width / 2
        y: -10
        height: dialog.owner.dock.height + 20
    }
    visualParent: anchorProxy
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
