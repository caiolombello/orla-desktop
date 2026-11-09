import QtQuick

// An album cover with rounded corners, center-cropped to a square. Drawn on a
// Canvas without a shader, so software rendering shows the cover too. Visible
// only once the cover at `url` has loaded; callers draw their own placeholder.
Canvas {
    id: art
    property string url: ""
    property real cornerRadius: 0
    property string loadedUrl: ""
    visible: url.length > 0 && loadedUrl === url && artSource.status === Image.Ready
    onUrlChanged: if (url.length > 0) loadImage(url)
    onImageLoaded: {
        if (isImageLoaded(url)) loadedUrl = url;
        requestPaint();
    }
    onVisibleChanged: requestPaint()
    onWidthChanged: requestPaint()
    onCornerRadiusChanged: requestPaint()
    Component.onCompleted: if (url.length > 0) loadImage(url)
    onPaint: {
        const context = getContext("2d");
        context.reset();
        const naturalWidth = artSource.implicitWidth, naturalHeight = artSource.implicitHeight;
        if (!visible || naturalWidth <= 0 || naturalHeight <= 0) return;
        // Crop the center square, like PreserveAspectCrop.
        const side = Math.min(naturalWidth, naturalHeight);
        context.beginPath();
        context.roundedRect(0, 0, width, height, cornerRadius, cornerRadius);
        context.clip();
        context.drawImage(url, (naturalWidth - side) / 2, (naturalHeight - side) / 2, side, side,
            0, 0, width, height);
    }
    // Natural size of the cover, for the center crop.
    Image {
        id: artSource
        visible: false
        source: art.url
        asynchronous: true
    }
}
