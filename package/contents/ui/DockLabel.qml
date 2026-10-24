import QtQuick
import org.kde.plasma.core as PlasmaCore
import "../code/Style.js" as Style

// The name label that floats above the hovered dock slot, like macOS: no delay,
// never takes focus or input. Loaded only by the production panel backend.
PlasmaCore.Dialog {
    id: label
    readonly property var owner: labelOwner
    readonly property Item target: owner.labelTarget
    // A mapped Wayland popup keeps its first anchor. A new slot hides the
    // label and maps it again on the next turn, anchored to that slot.
    property Item shownTarget: null
    property Timer remap: Timer {
        interval: 0
        onTriggered: label.shownTarget = label.target
    }
    readonly property string text: shownTarget ? shownTarget.tooltip : ""
    visualParent: shownTarget ? shownTarget.artwork : null
    // Requiring the new anchor keeps the window from mapping before it has one.
    visible: shownTarget !== null && visualParent === shownTarget.artwork
        && text.length > 0 && !owner.popupOpen
    onTargetChanged: {
        shownTarget = null;
        if (target) remap.restart();
        else remap.stop();
    }
    Component.onCompleted: if (target) remap.restart()
    location: owner.popAbove ? PlasmaCore.Types.BottomEdge : PlasmaCore.Types.TopEdge
    type: PlasmaCore.Dialog.Tooltip
    flags: Qt.ToolTip | Qt.WindowDoesNotAcceptFocus | Qt.FramelessWindowHint
    outputOnly: true
    // With the Orla Plasma theme the tooltip frame is blurred glass, as in macOS.
    readonly property bool systemGlass: Boolean(owner.systemPopupGlass)
    backgroundHints: systemGlass ? PlasmaCore.Dialog.StandardBackground : PlasmaCore.Dialog.NoBackground
    color: "transparent"
    hideOnWindowDeactivate: false
    mainItem: Rectangle {
        // The theme's tooltip frame already pads by its margin.
        implicitWidth: Math.min(name.implicitWidth, 320) + (label.systemGlass ? Style.space.xs : Style.space.md) * 2
        implicitHeight: name.implicitHeight + (label.systemGlass ? 0 : Style.space.xs * 2 + 2)
        radius: Style.radius.control
        color: label.systemGlass ? "transparent" : Style.alpha(label.owner.popupScheme.surface, 0.96)
        border.width: label.systemGlass ? 0 : 1
        border.color: label.owner.popupScheme.border
        Text {
            id: name
            anchors.centerIn: parent
            width: Math.min(implicitWidth, 320)
            text: label.text
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: label.owner.popupScheme.text
            font.pixelSize: Style.type.body
            font.weight: Style.weight.medium
        }
    }
}
