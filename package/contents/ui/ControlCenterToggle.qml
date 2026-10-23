import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import "../code/Style.js" as Style

// One macOS Control Center row: a round toggle, then the name and its state.
// With `actionText`, the name side becomes a button that opens the matching
// KDE page (hover tint, focus ring and tooltip); without it, it is plain text.
RowLayout {
    id: row
    property alias toggle: toggleButton
    property alias statusLabel: statusText
    property alias action: details
    property string title: ""
    property string status: ""
    property string actionText: ""
    property color foreground: palette.windowText
    property color muted: palette.windowText
    signal toggled()
    signal actionTriggered()
    spacing: Style.space.sm

    OrlaIconButton {
        id: toggleButton
        // A little under the 40 px target so names fit half-width modules.
        implicitWidth: Style.size.control
        implicitHeight: Style.size.control
        Layout.alignment: Qt.AlignVCenter
        onClicked: row.toggled()
    }
    Templates.Button {
        id: details
        readonly property bool interactive: row.actionText.length > 0
        Layout.fillWidth: true
        implicitWidth: implicitContentWidth + leftPadding + rightPadding
        implicitHeight: Math.max(Style.size.target, implicitContentHeight + topPadding + bottomPadding)
        enabled: interactive
        focusPolicy: interactive ? Qt.StrongFocus : Qt.NoFocus
        hoverEnabled: interactive
        padding: Style.space.xxs
        leftPadding: Style.space.xs
        Accessible.role: interactive ? Accessible.Button : Accessible.StaticText
        Accessible.name: interactive ? row.actionText : row.title
        Accessible.description: row.status
        Controls.ToolTip.visible: interactive && hovered
        Controls.ToolTip.text: row.actionText
        Controls.ToolTip.delay: 650
        onClicked: row.actionTriggered()
        contentItem: ColumnLayout {
            spacing: 0
            Controls.Label {
                Layout.fillWidth: true
                text: row.title
                textFormat: Text.PlainText
                // Half-width modules wrap a long name, as macOS does.
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
                font.weight: Style.weight.demiBold
                color: row.foreground
            }
            Controls.Label {
                id: statusText
                Layout.fillWidth: true
                visible: text.length > 0
                text: row.status
                textFormat: Text.PlainText
                font.pixelSize: Style.type.caption
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
                color: row.muted
            }
        }
        background: Rectangle {
            radius: Style.radius.control
            color: details.down ? Style.alpha(row.foreground, Style.state.pressed)
                : details.hovered ? Style.alpha(row.foreground, Style.state.hover) : "transparent"
            Rectangle {
                anchors.fill: parent
                anchors.margins: -2
                radius: parent.radius + 2
                color: "transparent"
                visible: details.visualFocus
                border.width: 2
                border.color: details.palette.highlight
            }
        }
    }
}
