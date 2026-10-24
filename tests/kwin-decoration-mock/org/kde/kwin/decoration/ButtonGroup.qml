import QtQuick
// Test double for KWin's ButtonGroup: one Loader per button, left to right.
Item {
    id: group
    property var buttons: []
    property int explicitSpacer
    property alias spacing: row.spacing
    property var closeButton
    property var helpButton
    property var keepAboveButton
    property var keepBelowButton
    property var maximizeButton
    property var menuButton
    property var appMenuButton
    property var minimizeButton
    property var allDesktopsButton
    property var shadeButton
    width: childrenRect.width
    Row {
        id: row
        Repeater {
            model: group.buttons
            Loader {
                required property var modelData
                sourceComponent: modelData === DecorationOptions.DecorationButtonClose ? group.closeButton
                    : modelData === DecorationOptions.DecorationButtonMinimize ? group.minimizeButton
                    : modelData === DecorationOptions.DecorationButtonMaximizeRestore ? group.maximizeButton
                    : group.menuButton
            }
        }
    }
}
