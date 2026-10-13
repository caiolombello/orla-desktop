import QtQuick
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

// One dock slot, macOS-like: artwork only, a dot for running apps, a gentle lift
// on hover and a bounce while launching or asking for attention. Widgets set
// `liveKind` and render a LiveIcon instead of a theme icon.
Controls.AbstractButton {
    id: tile
    property var iconSource: ""
    property string title: ""
    property string subtitle: ""
    property color foreground: Style.dockThemes.glass.foreground
    property color muted: Style.dockThemes.glass.muted
    property color accent: Style.dockThemes.glass.accent
    property string liveKind: ""
    property var liveInfo: ({})
    // True when a widget has data worth showing; false shows its idle face.
    property bool live: false
    property date now: new Date()
    property bool running: false
    property bool activeTask: false
    property bool attention: false
    property bool launching: false
    property int iconSize: 42
    property int animationDuration: Style.motion.fast
    property string tooltip: title
    // DockView draws a floating label in Plasma; fixtures keep the Controls tooltip.
    property bool nativeLabel: false
    readonly property var scheme: Style.scheme(Style.luminance(foreground) < 0.4 ? "light" : "dark")
    readonly property int artworkSize: iconSize + Style.dock.artwork
    readonly property bool lifted: (hovered || visualFocus) && !down
    readonly property bool bouncing: (launching || attention) && animationDuration > 0
    readonly property alias artwork: artworkBox
    implicitWidth: iconSize + Style.dock.slotGap
    implicitHeight: iconSize + 16
    padding: 0
    hoverEnabled: true
    Accessible.name: tooltip
    Controls.ToolTip {
        id: hoverTip
        parent: tile
        text: tile.tooltip
        visible: tile.hovered && tile.tooltip.length > 0 && !tile.nativeLabel
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
    background: Item {}
    contentItem: Item {
        Item {
            id: artworkBox
            objectName: "tileArtwork"
            width: tile.artworkSize
            height: width
            x: Math.round((parent.width - width) / 2)
            // Sit above center so the running dot has room underneath.
            y: Math.round((parent.height - height) / 2) - 2
            scale: tile.down ? Style.motion.pressScale : tile.lifted ? Style.motion.hoverScale : 1
            transformOrigin: Item.Bottom
            transform: [
                Translate {
                    y: tile.lifted ? -Style.motion.lift : 0
                    Behavior on y { NumberAnimation { duration: tile.animationDuration; easing.type: Easing.OutCubic } }
                },
                Translate { id: bounce }
            ]
            Behavior on scale { NumberAnimation { duration: tile.animationDuration; easing.type: Easing.OutCubic } }
            Kirigami.Icon {
                anchors.fill: parent
                visible: tile.liveKind.length === 0
                source: tile.iconSource
                color: tile.foreground
                active: tile.hovered
            }
            LiveIcon {
                anchors.centerIn: parent
                width: tile.iconSize + 2
                height: width
                visible: tile.liveKind.length > 0
                kind: tile.liveKind
                info: tile.liveInfo
                live: tile.live
                now: tile.now
                animationDuration: tile.animationDuration
            }
        }
        Rectangle {
            objectName: "tileFocusRing"
            // Keep focus inside the hit target while its artwork lifts or bounces.
            anchors.horizontalCenter: parent.horizontalCenter
            y: artworkBox.y
            width: Math.min(tile.artworkSize, parent.width)
            height: width
            radius: Math.round(width * Style.dock.iconRadius)
            visible: tile.visualFocus
            color: "transparent"
            border.width: 2
            border.color: tile.accent
        }
        SequentialAnimation {
            running: tile.bouncing
            loops: Animation.Infinite
            alwaysRunToEnd: true
            NumberAnimation { target: bounce; property: "y"; to: -Style.motion.bounce; duration: Style.motion.slow; easing.type: Easing.OutQuad }
            NumberAnimation { target: bounce; property: "y"; to: 0; duration: Style.motion.slow * 2; easing.type: Easing.OutBounce }
            PauseAnimation { duration: Style.motion.slow * 2 }
        }
        Rectangle {
            id: indicator
            objectName: "tileIndicator"
            visible: tile.running || tile.attention
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            width: Style.size.indicator
            height: width
            radius: width / 2
            color: tile.attention ? tile.scheme.warning : tile.foreground
            opacity: tile.attention || tile.activeTask ? 1 : 0.55
            Behavior on opacity { NumberAnimation { duration: tile.animationDuration } }
        }
    }
}
