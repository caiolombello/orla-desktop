import QtQuick
import org.kde.kwin.decoration

// Orla window decoration, macOS style: a 28 px title bar in the window color,
// round top corners, a hairline edge, traffic lights on the left (their glyphs
// show while the pointer is over the group) and a soft shadow in the padding.
// Button order comes from the system (Orla's apply sets close, minimize, zoom
// on the left); colors follow the active color scheme.
Decoration {
    id: root
    // Geometry, in logical pixels. Keep in sync with tests/test_window_decoration.py.
    readonly property int titleHeight: 28
    readonly property int cornerRadius: 10
    readonly property int lightPitch: 20
    readonly property int lightInset: 4
    readonly property int shadowLayers: 10
    readonly property var shadowPadding: ({left: 24, top: 18, right: 24, bottom: 32})
    readonly property bool maximized: decoration.client.maximized
    readonly property bool active: decoration.client.active
    readonly property color windowColor: colors.background(true, ColorHelper.NormalBackground)
    readonly property color textColor: colors.foreground(active, ColorHelper.NormalText)
    readonly property bool darkScheme: windowColor.hslLightness < 0.5
    property int hoveredLights: 0
    readonly property bool lightsHovered: hoveredLights > 0
    alpha: true

    ColorHelper { id: colors }
    DecorationOptions {
        id: options
        deco: decoration
    }

    // The window outline: what the shadow and the hairline follow.
    readonly property rect frame: Qt.rect(maximized ? 0 : padding.left, maximized ? 0 : padding.top,
        width - (maximized ? 0 : padding.left + padding.right),
        height - (maximized ? 0 : padding.top + padding.bottom))

    // Soft shadow: stacked outlines outside the window only, darker near the
    // edge and longer below, like macOS. Inactive windows cast a lighter one.
    Repeater {
        objectName: "orlaShadow"
        model: root.maximized ? 0 : root.shadowLayers
        Rectangle {
            required property int index
            readonly property real grow: (index + 1) * root.shadowPadding.left / root.shadowLayers
            readonly property real drop: (index + 1) * (root.shadowPadding.bottom - root.shadowPadding.top) / (2 * root.shadowLayers)
            x: root.frame.x - grow
            y: root.frame.y - grow + drop
            width: root.frame.width + 2 * grow
            height: root.frame.height + 2 * grow
            radius: root.cornerRadius + grow
            color: "transparent"
            border.width: root.shadowPadding.left / root.shadowLayers + 0.5
            border.color: Qt.rgba(0, 0, 0, (root.active ? 0.07 : 0.04) * (root.shadowLayers - index) / root.shadowLayers)
        }
    }

    // Title bar with round top corners; the client covers everything below it.
    Item {
        id: chrome
        x: root.frame.x
        y: root.frame.y
        width: root.frame.width
        height: root.frame.height
        clip: true
        Rectangle {
            width: parent.width
            // Extend below the title bar so only the top corners round.
            height: root.titleHeight + root.cornerRadius + 1
            radius: root.maximized ? 0 : root.cornerRadius
            color: root.windowColor
        }
        Rectangle {
            // Thin side and bottom edges where the client does not paint.
            anchors.fill: parent
            anchors.topMargin: root.titleHeight
            color: root.windowColor
            visible: !root.maximized
        }
    }
    Rectangle {
        // Hairline around the window: light on dark schemes, dark on light ones.
        x: root.frame.x
        y: root.frame.y
        width: root.frame.width
        height: root.frame.height
        visible: !root.maximized
        color: "transparent"
        radius: root.cornerRadius
        border.width: 1
        border.color: root.darkScheme ? Qt.rgba(1, 1, 1, root.active ? 0.14 : 0.09) : Qt.rgba(0, 0, 0, root.active ? 0.16 : 0.1)
    }

    Item {
        id: titleRow
        objectName: "orlaTitleRow"
        x: root.frame.x
        y: root.frame.y
        width: root.frame.width
        height: root.titleHeight
        ButtonGroup {
            id: leftButtons
            spacing: 0
            explicitSpacer: root.lightPitch
            buttons: options.titleButtonsLeft
            closeButton: closeComponent
            minimizeButton: minimizeComponent
            maximizeButton: maximizeComponent
            menuButton: emptyComponent
            appMenuButton: emptyComponent
            helpButton: emptyComponent
            keepAboveButton: emptyComponent
            keepBelowButton: emptyComponent
            shadeButton: emptyComponent
            allDesktopsButton: emptyComponent
            // The group has no height of its own: pin its row to the bar's top.
            height: root.titleHeight
            anchors.left: parent.left
            anchors.leftMargin: root.lightInset
            anchors.top: parent.top
        }
        ButtonGroup {
            id: rightButtons
            spacing: 0
            explicitSpacer: root.lightPitch
            buttons: options.titleButtonsRight
            closeButton: closeComponent
            minimizeButton: minimizeComponent
            maximizeButton: maximizeComponent
            menuButton: emptyComponent
            appMenuButton: emptyComponent
            helpButton: emptyComponent
            keepAboveButton: emptyComponent
            keepBelowButton: emptyComponent
            shadeButton: emptyComponent
            allDesktopsButton: emptyComponent
            height: root.titleHeight
            anchors.right: parent.right
            anchors.rightMargin: root.lightInset
            anchors.top: parent.top
        }
        Text {
            id: caption
            objectName: "orlaCaption"
            // Centered on the window, kept clear of the buttons on both sides.
            readonly property real reserve: Math.max(leftButtons.width, rightButtons.width) + root.lightInset + 8
            x: reserve
            width: Math.max(0, parent.width - 2 * reserve)
            height: parent.height
            text: decoration.client.caption
            textFormat: Text.PlainText
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideMiddle
            font.family: options.titleFont.family
            font.pointSize: options.titleFont.pointSize > 0 ? options.titleFont.pointSize : 10
            font.weight: Font.DemiBold
            color: root.textColor
            opacity: root.active ? 0.9 : 0.5
            renderType: Text.NativeRendering
        }
        Component.onCompleted: decoration.installTitleItem(titleRow)
    }

    Component { id: emptyComponent; Item { width: 0; height: 0 } }
    Component { id: closeComponent; TrafficLight { buttonType: DecorationOptions.DecorationButtonClose } }
    Component { id: minimizeComponent; TrafficLight { buttonType: DecorationOptions.DecorationButtonMinimize } }
    Component { id: maximizeComponent; TrafficLight { buttonType: DecorationOptions.DecorationButtonMaximizeRestore } }

    Component.onCompleted: {
        borders.setBorders(1);
        borders.setTitle(titleHeight);
        maximizedBorders.setBorders(0);
        maximizedBorders.setTitle(titleHeight);
        // 1 px edges are too thin to grab: widen the resize area invisibly.
        extendedBorders.setAllBorders(4);
        padding.left = shadowPadding.left;
        padding.top = shadowPadding.top;
        padding.right = shadowPadding.right;
        padding.bottom = shadowPadding.bottom;
    }
}
