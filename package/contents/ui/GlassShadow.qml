import QtQuick
import "../code/Style.js" as Style

// Soft drop shadow behind `target` (a sibling declared after this item), made of
// stacked translucent outlines. Resizing it costs nothing, unlike a blurred
// Canvas, so surfaces that change height stay responsive. Needs `spread` pixels
// of free space around the target.
Item {
    id: shadow
    required property Item target
    property real radius: Style.radius.popup
    property real strength: Style.glass.shadowDark
    property real blur: Style.glass.shadowBlur
    property real offset: Style.glass.shadowOffset
    readonly property int layers: 6
    readonly property real spread: blur + offset
    x: target.x
    y: target.y + offset
    width: target.width
    height: target.height
    visible: target.visible && strength > 0
    Repeater {
        model: shadow.layers
        Rectangle {
            required property int index
            readonly property real grow: shadow.blur * (index + 1) / shadow.layers
            x: -grow
            y: -grow
            width: shadow.width + grow * 2
            height: shadow.height + grow * 2
            radius: shadow.radius + grow
            // Inner layers are darker; together they fade out like a blur.
            color: Style.alpha(Style.glass.shade, shadow.strength * (shadow.layers - index) / (shadow.layers * 4))
        }
    }
}
