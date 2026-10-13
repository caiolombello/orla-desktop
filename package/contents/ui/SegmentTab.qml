import QtQuick
import QtQuick.Templates as Templates
import "../code/Style.js" as Style

// One segment of SegmentedTabs. The selection pill is drawn by the bar.
Templates.TabButton {
    id: tab
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Style.size.control - 2 * (Style.space.xs - 1)
    padding: Style.space.xs
    hoverEnabled: true
    font.pixelSize: Style.type.label
    font.weight: checked ? Style.weight.demiBold : Style.weight.medium
    Accessible.name: text
    contentItem: Text {
        text: tab.text
        font: tab.font
        color: tab.palette.windowText
        opacity: tab.checked ? 1 : 0.72
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        textFormat: Text.PlainText
    }
    background: Rectangle {
        radius: Style.radius.control - 2
        color: tab.hovered && !tab.checked ? Style.alpha(tab.palette.windowText, Style.state.chip) : "transparent"
        border.width: tab.visualFocus ? 2 : 0
        border.color: tab.palette.highlight
    }
}
