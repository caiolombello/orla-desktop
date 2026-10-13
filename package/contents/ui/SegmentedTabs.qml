import QtQuick
import QtQuick.Templates as Templates
import "../code/Style.js" as Style

// Equal-width segmented control with a sliding selection pill. Use with SegmentTab.
Templates.TabBar {
    id: bar
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset,
                            contentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset,
                             contentHeight + topPadding + bottomPadding)
    padding: Style.space.xs - 1
    spacing: Style.space.xxs
    contentItem: ListView {
        model: bar.contentModel
        currentIndex: bar.currentIndex
        spacing: bar.spacing
        orientation: ListView.Horizontal
        interactive: false
        highlightMoveDuration: Style.motion.normal
        highlightResizeDuration: Style.motion.normal
        highlightFollowsCurrentItem: true
        highlight: Rectangle {
            radius: Style.radius.control - 2
            color: bar.palette.base
            border.width: 1
            border.color: bar.palette.mid
        }
    }
    background: Rectangle {
        implicitHeight: Style.size.control
        radius: Style.radius.control
        color: Style.alpha(bar.palette.windowText, Style.state.chip + 0.01)
    }
}
