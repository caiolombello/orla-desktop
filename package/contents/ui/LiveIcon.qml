import QtQuick
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style
import "../code/Shapes.js" as Shapes

// Widget artwork for the dock: a gradient squircle that shows live data the way
// an app icon would. `info` is kind-specific and comes from WidgetStrip:
//   value (short text), progress (0..1, <0 hides), ring (color), glyph (icon name),
//   palette (iconTiles key), art (local image URL), active (bool), charging (bool).
Item {
    id: icon
    property string kind: ""
    property bool live: false
    property var info: ({})
    property date now: new Date()
    property int animationDuration: Style.motion.fast
    readonly property var tile: Style.iconTiles[info.palette || Style.widgetTiles[kind] || "slate"]
    // Faces are drawn on a 44 px grid and scale with the icon.
    readonly property real unit: width / 44
    implicitWidth: 44
    implicitHeight: 44

    Rectangle {
        id: base
        anchors.fill: parent
        radius: Math.round(width * Style.dock.iconRadius)
        antialiasing: true
        gradient: Gradient {
            GradientStop { position: 0; color: icon.tile.top }
            GradientStop { position: 1; color: icon.tile.bottom }
        }
    }
    Loader {
        anchors.fill: parent
        sourceComponent: icon.kind === "clock" ? clockFace
            : icon.kind === "music" ? musicFace
            : icon.kind === "recording" ? recordingFace
            : icon.kind === "controlCenter" ? togglesFace : ringFace
    }
    GlassRim {
        anchors.fill: parent
        radius: base.radius
        light: Style.luminance(icon.tile.top) > 0.4
    }

    component Hand: Rectangle {
        id: hand
        property real length: 10
        property real turn: 0
        height: length
        radius: width / 2
        antialiasing: true
        x: icon.width / 2 - width / 2
        y: icon.height / 2 - length + width / 2
        transform: Rotation { origin.x: hand.width / 2; origin.y: hand.length - hand.width / 2; angle: hand.turn }
    }

    Component {
        id: clockFace
        // A paper dial inside the dark squircle reads on light and dark docks alike.
        Item {
            id: clockDial
            readonly property var dial: Style.iconTiles.paper
            readonly property real hours: icon.now.getHours() % 12 + icon.now.getMinutes() / 60
            readonly property real minutes: icon.now.getMinutes() + icon.now.getSeconds() / 60
            Rectangle {
                anchors.fill: parent
                anchors.margins: icon.unit * 3
                radius: width / 2
                antialiasing: true
                gradient: Gradient {
                    GradientStop { position: 0; color: clockDial.dial.top }
                    GradientStop { position: 1; color: clockDial.dial.bottom }
                }
            }
            Repeater {
                model: 12
                Rectangle {
                    required property int index
                    readonly property bool major: index % 3 === 0
                    width: Math.max(1, icon.unit * (major ? 2 : 1.2))
                    height: icon.unit * (major ? 4 : 2.6)
                    radius: width / 2
                    antialiasing: true
                    color: Style.alpha(clockDial.dial.ink, major ? 0.85 : 0.35)
                    x: icon.width / 2 - width / 2
                    y: icon.unit * 6
                    transform: Rotation { origin.x: width / 2; origin.y: icon.height / 2 - icon.unit * 6; angle: index * 30 }
                }
            }
            Hand { width: icon.unit * 2.8; length: icon.unit * 9.5; turn: clockDial.hours * 30; color: clockDial.dial.ink }
            Hand { width: icon.unit * 2; length: icon.unit * 13.5; turn: clockDial.minutes * 6; color: clockDial.dial.ink }
            Hand { width: Math.max(1, icon.unit); length: icon.unit * 14.5; turn: icon.now.getSeconds() * 6; color: clockDial.dial.accent }
            Rectangle {
                anchors.centerIn: parent
                width: icon.unit * 3.4
                height: width
                radius: width / 2
                color: clockDial.dial.accent
            }
        }
    }

    Component {
        id: ringFace
        Item {
            readonly property string value: icon.live && icon.info.value !== undefined && icon.info.value !== null
                ? String(icon.info.value) : ""
            ProgressRing {
                anchors.fill: parent
                anchors.margins: icon.unit * 5
                lineWidth: icon.unit * 3.4
                progress: icon.live && icon.info.progress >= 0 ? icon.info.progress : 0
                color: icon.info.ring || icon.tile.accent
                trackColor: Style.alpha(icon.tile.ink, 0.22)
                animationDuration: icon.animationDuration
            }
            Text {
                anchors.centerIn: parent
                visible: parent.value.length > 0
                text: parent.value
                textFormat: Text.PlainText
                color: icon.tile.ink
                font.pixelSize: Math.round(icon.unit * (parent.value.length > 2 ? 10.5 : 14))
                font.weight: Style.weight.bold
                font.features: {"tnum": 1}
            }
            Kirigami.Icon {
                anchors.centerIn: parent
                visible: parent.value.length === 0 && Boolean(icon.info.glyph)
                width: Math.round(icon.unit * 17)
                height: width
                source: icon.info.glyph || ""
                isMask: true
                color: icon.tile.ink
                opacity: icon.live ? 1 : 0.75
            }
            Kirigami.Icon {
                visible: Boolean(icon.info.charging)
                anchors.horizontalCenter: parent.horizontalCenter
                y: icon.unit * 1.5
                width: Math.round(icon.unit * 9)
                height: width
                source: "flash-symbolic"
                isMask: true
                color: icon.info.ring || icon.tile.accent
            }
        }
    }

    Component {
        id: musicFace
        Item {
            Canvas {
                id: cover
                // Only local artwork: the dock never fetches remote URLs.
                readonly property string art: icon.info.art && String(icon.info.art).startsWith("file:") ? String(icon.info.art) : ""
                property bool ready: false
                anchors.fill: parent
                visible: ready
                onArtChanged: { ready = false; if (art) loadImage(art); requestPaint(); }
                onImageLoaded: { ready = art.length > 0 && isImageLoaded(art); requestPaint(); }
                onWidthChanged: requestPaint()
                onPaint: {
                    const context = getContext("2d");
                    context.reset();
                    if (!ready) return;
                    context.save();
                    Shapes.roundedRect(context, 0, 0, width, height, base.radius);
                    context.clip();
                    context.drawImage(art, 0, 0, width, height);
                    context.restore();
                }
            }
            Kirigami.Icon {
                anchors.centerIn: parent
                visible: !cover.visible
                width: Math.round(icon.unit * 22)
                height: width
                source: "library-music-symbolic"
                isMask: true
                color: icon.tile.ink
                opacity: icon.live ? 1 : 0.8
            }
            Rectangle {
                visible: icon.live
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: icon.unit * 2.5
                width: icon.unit * 15
                height: width
                radius: width / 2
                color: Style.alpha(Style.glass.shade, 0.55)
                Kirigami.Icon {
                    anchors.centerIn: parent
                    width: Math.round(parent.width * 0.6)
                    height: width
                    source: icon.info.active ? "media-playback-pause-symbolic" : "media-playback-start-symbolic"
                    isMask: true
                    color: Style.glass.highlight
                }
            }
        }
    }

    Component {
        id: recordingFace
        Item {
            Rectangle {
                anchors.centerIn: parent
                width: icon.unit * 16
                height: width
                radius: width / 2
                color: icon.info.active ? Style.levels.critical : Style.alpha(icon.tile.ink, 0.35)
                border.width: icon.unit * 2
                border.color: Style.alpha(icon.tile.ink, 0.9)
                SequentialAnimation on opacity {
                    running: Boolean(icon.info.active) && icon.animationDuration > 0
                    loops: Animation.Infinite
                    alwaysRunToEnd: true
                    NumberAnimation { to: 0.45; duration: Style.motion.slow * 3; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1; duration: Style.motion.slow * 3; easing.type: Easing.InOutSine }
                }
            }
        }
    }

    Component {
        id: togglesFace
        Item {
            Column {
                anchors.centerIn: parent
                spacing: icon.unit * 4
                Repeater {
                    model: [true, false]
                    Rectangle {
                        required property bool modelData
                        width: icon.unit * 24
                        height: icon.unit * 10
                        radius: height / 2
                        color: modelData ? icon.tile.accent : Style.alpha(icon.tile.ink, 0.3)
                        Rectangle {
                            width: parent.height - icon.unit * 2.4
                            height: width
                            radius: width / 2
                            y: icon.unit * 1.2
                            x: parent.modelData ? parent.width - width - icon.unit * 1.2 : icon.unit * 1.2
                            color: icon.tile.ink
                        }
                    }
                }
            }
        }
    }
}
