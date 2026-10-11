import QtQuick
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Controls.AbstractButton {
    id: tile
    property var iconSource: ""
    property string title: ""
    property string subtitle: ""
    property color foreground: "#edf1f9"
    property color muted: "#9da9bf"
    property color accent: "#8cb7ff"
    property bool wide: false
    property bool running: false
    property bool activeTask: false
    property bool attention: false
    property int iconSize: 42
    property int animationDuration: 120
    property string tooltip: title
    implicitWidth: wide ? 158 : iconSize + 16
    implicitHeight: iconSize + 16
    hoverEnabled: true
    Accessible.name: tooltip
    Controls.ToolTip {
        id: hoverTip
        parent: tile
        text: tile.tooltip
        visible: tile.hovered && tile.tooltip.length > 0
        delay: 650
        contentItem: Text {
            objectName: "tileTooltipText"
            text: hoverTip.text
            textFormat: Text.PlainText
            font: hoverTip.font
            color: hoverTip.palette.toolTipText
            wrapMode: Text.Wrap
        }
    }
    background: Rectangle {
        radius: 14
        color: tile.down ? Qt.rgba(0.5, 0.6, 0.8, 0.26)
                        : tile.hovered || tile.visualFocus ? Qt.rgba(0.5, 0.6, 0.8, 0.14) : "transparent"
        border.width: tile.visualFocus ? 2 : 0
        border.color: tile.accent
    }
    contentItem: Item {
        Kirigami.Icon {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: tile.wide ? 10 : (parent.width - width) / 2
            width: tile.wide ? 26 : tile.iconSize
            height: width
            source: tile.iconSource
            color: tile.foreground
            scale: tile.hovered && !tile.wide ? 1.12 : 1
            Behavior on scale { NumberAnimation { duration: tile.animationDuration; easing.type: Easing.OutCubic } }
        }
        Column {
            visible: tile.wide
            anchors.verticalCenter: parent.verticalCenter
            x: 44
            width: parent.width - x - 8
            spacing: 2
            Text { objectName: "tileTitle"; text: tile.title; textFormat: Text.PlainText; color: tile.foreground; font.pixelSize: 13; font.weight: Font.DemiBold; width: parent.width; elide: Text.ElideRight }
            Text { objectName: "tileSubtitle"; text: tile.subtitle; textFormat: Text.PlainText; color: tile.muted; font.pixelSize: 10; width: parent.width; elide: Text.ElideRight }
        }
        Rectangle {
            visible: tile.running || tile.attention
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            width: tile.activeTask ? 16 : 5
            height: 3
            radius: 2
            color: tile.attention ? "#f5b65d" : tile.activeTask ? tile.accent : tile.muted
            Behavior on width { NumberAnimation { duration: tile.animationDuration } }
        }
    }
}
