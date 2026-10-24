import QtQuick
import org.kde.kwin.decoration

// One macOS traffic light: a 12 px disc in a 20 × 28 hit area. The glyph shows
// while the pointer is anywhere over the group; inactive windows turn gray.
DecorationButton {
    id: light
    objectName: buttonType === DecorationOptions.DecorationButtonClose ? "orlaClose"
        : buttonType === DecorationOptions.DecorationButtonMinimize ? "orlaMinimize" : "orlaMaximize"
    width: root.lightPitch
    height: root.titleHeight
    readonly property int diameter: 12
    // Fill, rim and glyph per button, as in macOS.
    readonly property var palette: buttonType === DecorationOptions.DecorationButtonClose
        ? {fill: "#ff5f57", rim: "#e0443e", glyph: "#4d0000"}
        : buttonType === DecorationOptions.DecorationButtonMinimize
        ? {fill: "#febc2e", rim: "#dea123", glyph: "#995700"}
        : {fill: "#28c840", rim: "#1aab29", glyph: "#006500"}
    readonly property bool lit: enabled && (root.active || root.lightsHovered)
    onHoveredChanged: root.hoveredLights += hovered ? 1 : -1
    Component.onDestruction: if (hovered) root.hoveredLights -= 1

    Rectangle {
        id: disc
        objectName: "disc"
        anchors.centerIn: parent
        width: light.diameter
        height: light.diameter
        radius: width / 2
        color: light.lit ? (light.pressed ? Qt.darker(light.palette.fill, 1.18) : light.palette.fill)
            : Qt.rgba(root.textColor.r, root.textColor.g, root.textColor.b, root.darkScheme ? 0.22 : 0.18)
        border.width: 0.5
        border.color: light.lit ? light.palette.rim : "transparent"

        Item {
            objectName: "glyph"
            anchors.fill: parent
            visible: light.lit && root.lightsHovered
            opacity: 0.85
            // ×, − or +, drawn with bars so they stay crisp at any scale.
            Rectangle {
                anchors.centerIn: parent
                width: 6.5
                height: 1.2
                radius: 0.6
                color: light.palette.glyph
                rotation: light.buttonType === DecorationOptions.DecorationButtonClose ? 45 : 0
            }
            Rectangle {
                anchors.centerIn: parent
                width: 6.5
                height: 1.2
                radius: 0.6
                color: light.palette.glyph
                visible: light.buttonType !== DecorationOptions.DecorationButtonMinimize
                rotation: light.buttonType === DecorationOptions.DecorationButtonClose ? -45 : 90
            }
        }
    }
}
