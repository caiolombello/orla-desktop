import QtQuick
import "../code/Style.js" as Style
import "../code/Shapes.js" as Shapes

// Sheen and specular rim for a rounded glass surface. Fill its parent surface;
// it only adds light, so the surface keeps its own color, border and opacity.
Canvas {
    id: rim
    property real radius: Style.radius.popup
    property bool light: false
    onRadiusChanged: requestPaint()
    onLightChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const context = getContext("2d");
        context.reset();
        if (width < 4 || height < 4) return;
        const white = Style.glass.highlight;
        const sheen = context.createLinearGradient(0, 0, 0, height);
        sheen.addColorStop(0, Style.alpha(white, light ? Style.glass.sheenLight : Style.glass.sheenDark));
        sheen.addColorStop(0.55, Style.alpha(white, 0));
        context.fillStyle = sheen;
        Shapes.roundedRect(context, 1, 1, width - 2, height - 2, radius - 1);
        context.fill();
        const edge = context.createLinearGradient(0, 0, 0, height);
        edge.addColorStop(0, Style.alpha(white, light ? Style.glass.rimTopLight : Style.glass.rimTopDark));
        edge.addColorStop(0.5, Style.alpha(white, light ? Style.glass.rimBottomLight : Style.glass.rimBottomDark));
        edge.addColorStop(1, Style.alpha(white, light ? Style.glass.rimBottomLight : Style.glass.rimBottomDark));
        context.lineWidth = 1;
        context.strokeStyle = edge;
        Shapes.roundedRect(context, 1.5, 1.5, width - 3, height - 3, radius - 1.5);
        context.stroke();
    }
}
