import QtQuick
import "../code/Style.js" as Style

// Circular progress around an icon badge. `progress` is 0..1; negative hides the arc.
Canvas {
    id: ring
    property real progress: 0
    property color color: Style.schemes.dark.accent
    property color trackColor: Style.alpha(color, 0.22)
    property real lineWidth: Style.size.ringStroke
    property int animationDuration: Style.motion.normal
    property real shown: Math.max(0, Math.min(1, progress))
    Behavior on shown {
        enabled: ring.animationDuration > 0
        NumberAnimation { duration: ring.animationDuration; easing.type: Easing.OutCubic }
    }
    antialiasing: true
    onShownChanged: requestPaint()
    onColorChanged: requestPaint()
    onTrackColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const context = getContext("2d");
        context.reset();
        const radius = Math.min(width, height) / 2 - lineWidth / 2;
        if (radius <= 0) return;
        context.lineWidth = lineWidth;
        context.lineCap = "round";
        context.strokeStyle = trackColor;
        context.beginPath();
        context.arc(width / 2, height / 2, radius, 0, 2 * Math.PI);
        context.stroke();
        if (shown <= 0) return;
        context.strokeStyle = color;
        context.beginPath();
        context.arc(width / 2, height / 2, radius, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * shown);
        context.stroke();
    }
}
