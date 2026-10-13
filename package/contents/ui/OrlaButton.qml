import QtQuick
import QtQuick.Templates as Templates
import "../code/Style.js" as Style

// Orla action button. Colors come from the inherited palette, which every Orla
// surface sets from a Style scheme, so it works in Plasma and in CI.
// variant: "primary" (one per surface), "secondary" (default) or "ghost".
Templates.Button {
    id: control
    property string variant: "secondary"
    readonly property bool primary: variant === "primary"
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(Style.size.control, implicitContentHeight + topPadding + bottomPadding)
    padding: Style.space.sm
    leftPadding: Style.space.lg
    rightPadding: Style.space.lg
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    font.weight: primary ? Style.weight.demiBold : Style.weight.medium
    opacity: enabled ? 1 : 1 - Style.state.disabled
    Accessible.name: text
    contentItem: Text {
        text: control.text
        font: control.font
        color: control.primary ? control.palette.highlightedText : control.palette.windowText
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        textFormat: Text.PlainText
    }
    background: Rectangle {
        implicitWidth: Style.size.target * 2
        implicitHeight: Style.size.control
        radius: Style.radius.control
        color: control.primary ? control.palette.highlight
            : control.variant === "ghost" ? "transparent"
            : Style.alpha(control.palette.windowText, Style.state.chip + 0.02)
        border.width: control.variant === "secondary" ? 1 : 0
        border.color: Style.alpha(control.palette.windowText, Style.state.hover + 0.02)
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            color: control.primary ? control.palette.highlightedText : control.palette.windowText
            opacity: control.down ? Style.state.pressed : control.hovered ? Style.state.hover : 0
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: parent.radius + 3
            color: "transparent"
            visible: control.visualFocus
            border.width: 2
            border.color: control.palette.highlight
        }
    }
}
