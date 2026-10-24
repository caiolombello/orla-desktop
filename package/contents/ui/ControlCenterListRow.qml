import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

// One row of a Control Center list page (Wi-Fi networks, Bluetooth devices),
// as in macOS: an icon, the name and its state; choosing it asks to connect,
// and the connected row offers a disconnect button.
RowLayout {
    id: row
    property string name: ""
    property string detail: ""
    property string iconName: ""
    // A second, muted icon after the name (the lock of a protected network).
    property string badgeIcon: ""
    property bool connected: false
    property string spokenName: name
    property string disconnectText: ""
    property color foreground: palette.windowText
    property color muted: palette.windowText
    property alias choose: chooseButton
    property alias disconnect: disconnectButton
    signal chosen()
    signal disconnectRequested()
    spacing: 0

    Templates.Button {
        id: chooseButton
        Layout.fillWidth: true
        implicitHeight: Style.size.target
        implicitWidth: implicitContentWidth + leftPadding + rightPadding
        padding: Style.space.xs
        leftPadding: Style.space.sm
        rightPadding: Style.space.sm
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        readonly property string spokenName: row.spokenName
        Accessible.name: spokenName
        onClicked: if (!row.connected) row.chosen()
        contentItem: RowLayout {
            spacing: Style.space.sm
            Kirigami.Icon {
                Layout.preferredWidth: Style.size.iconSm
                Layout.preferredHeight: Style.size.iconSm
                source: row.iconName
                isMask: true
                color: row.connected ? chooseButton.palette.highlight : row.foreground
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Controls.Label {
                    Layout.fillWidth: true
                    text: row.name
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    font.weight: row.connected ? Style.weight.demiBold : Style.weight.regular
                    color: row.foreground
                }
                Controls.Label {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: row.detail
                    textFormat: Text.PlainText
                    font.pixelSize: Style.type.caption
                    elide: Text.ElideRight
                    color: row.muted
                }
            }
            Kirigami.Icon {
                Layout.preferredWidth: Style.size.iconSm
                Layout.preferredHeight: Style.size.iconSm
                visible: row.badgeIcon.length > 0
                source: row.badgeIcon
                isMask: true
                color: row.muted
            }
        }
        background: Rectangle {
            radius: Style.radius.control
            color: chooseButton.down ? Style.alpha(row.foreground, Style.state.pressed)
                : chooseButton.hovered ? Style.alpha(row.foreground, Style.state.hover) : "transparent"
            Rectangle {
                anchors.fill: parent
                radius: parent.radius
                color: "transparent"
                visible: chooseButton.visualFocus
                border.width: 2
                border.color: chooseButton.palette.highlight
            }
        }
    }
    OrlaIconButton {
        id: disconnectButton
        visible: row.connected
        flat: true
        // Monochrome: Breeze's disconnect icon carries a red mark that reads as an error.
        iconName: "media-eject-symbolic"
        text: row.disconnectText
        onClicked: row.disconnectRequested()
    }
}
