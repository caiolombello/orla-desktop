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
    backgroundHints: PlasmaCore.Dialog.NoBackground
    color: "transparent"
    hideOnWindowDeactivate: false
    mainItem: Rectangle {
        implicitWidth: Math.min(name.implicitWidth, 320) + Style.space.md * 2
        implicitHeight: name.implicitHeight + Style.space.xs * 2 + 2
        radius: Style.radius.control
        color: Style.alpha(label.owner.popupScheme.surface, 0.96)
        border.width: 1
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
