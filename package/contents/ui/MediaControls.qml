import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

Controls.Control {
    id: root
    required property var media
    property color foreground: palette.windowText
    property color muted: palette.windowText
    property alias mediaState: mediaStateObject
    implicitWidth: 310
    implicitHeight: body.implicitHeight + topPadding + bottomPadding

    property string focusedTransport: ""
    function reveal(control) {
        const viewport = scroll.contentItem;
        if (!control || !control.visible || !viewport || viewport.height <= 0
                || viewport.contentY === undefined) return;
        const point = control.mapToItem(viewport, 0, 0);
        let offset = viewport.contentY;
        if (point.y < 0) offset += point.y;
        else if (point.y + control.height > viewport.height)
            offset += point.y + control.height - viewport.height;
        viewport.contentY = Math.max(0, Math.min(offset, Math.max(0, viewport.contentHeight - viewport.height)));
    }
    function recoverFocus() {
        focusedTransport = "";
        if (!visible) return;
        if (playerChooser.count > 0) playerChooser.forceActiveFocus();
        else root.forceActiveFocus();
    }
    MediaState { id: mediaStateObject; media: root.media }
    Connections {
        target: root.mediaState
        function onPlayerChanged() {
            if (!root.mediaState.player && root.focusedTransport.length > 0)
                Qt.callLater(root.recoverFocus);
        }
    }
    contentItem: Controls.ScrollView {
        id: scroll
        objectName: "mediaScroll"
        // Keep intrinsic sizing independent of the viewport width in native styles.
        implicitWidth: root.implicitWidth
        contentWidth: availableWidth
        contentHeight: body.implicitHeight
        Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: 10
            Controls.Label {
                Layout.fillWidth: true
                visible: playerChooser.count > 0
                text: qsTr("Player")
                textFormat: Text.PlainText
                color: root.muted
                opacity: 0.75
            }
            Controls.ComboBox {
                id: playerChooser
                objectName: "mediaPlayerChooser"
                Layout.fillWidth: true
                visible: count > 0
                model: root.media
                textRole: "identity"
                currentIndex: root.media ? root.media.currentIndex : -1
                Accessible.name: qsTr("Escolher player de mídia")
                delegate: Controls.ItemDelegate {
                    required property int index
                    required property string identity
                    required property bool isMultiplexer
                    width: playerChooser.width
                    text: isMultiplexer ? qsTr("Automático · %1").arg(identity) : identity
                    highlighted: playerChooser.highlightedIndex === index
                    contentItem: Controls.Label {
                        text: root.mediaState.boundedText(parent.text, 256)
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                // Keep the native TextInput content item expected by desktop styles.
                displayText: root.mediaState.boundedText(currentText, 256)
                onActiveFocusChanged: if (activeFocus) {
                    root.focusedTransport = "";
                    root.reveal(this);
                }
                onActivated: index => root.mediaState.choosePlayer(index)
            }
            Controls.Label {
                objectName: "mediaEmptyState"
                Layout.fillWidth: true
                visible: !root.mediaState.player
                text: root.media ? qsTr("Abra o Spotify ou outro player compatível com MPRIS para controlar sua música aqui.")
                                 : qsTr("Os controles de mídia estão indisponíveis.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.foreground
            }
            // Now playing, as in macOS: the cover beside title, artist and album.
            RowLayout {
                objectName: "mediaNowPlaying"
                Layout.fillWidth: true
                visible: Boolean(root.mediaState.player)
                spacing: Style.space.md
                Item {
                    objectName: "mediaCover"
                    Layout.preferredWidth: Style.size.target + Style.space.lg
                    Layout.preferredHeight: Style.size.target + Style.space.lg
                    Layout.alignment: Qt.AlignTop
                    Rectangle {
                        anchors.fill: parent
                        visible: !art.visible
                        radius: Style.radius.control
                        color: Style.alpha(root.foreground, 0.1)
                        Controls.Label {
                            anchors.centerIn: parent
                            text: "♪"
                            textFormat: Text.PlainText
                            font.pixelSize: Style.type.headline
                            color: root.muted
                        }
                    }
                    // Natural size of the cover, for the center crop below.
                    Image {
                        id: artSource
                        visible: false
                        source: root.mediaState.artUrl
                        asynchronous: true
                    }
                    // Rounded corners without a shader, so software rendering shows the cover too.
                    Canvas {
                        id: art
                        objectName: "mediaArt"
                        anchors.fill: parent
                        readonly property string url: root.mediaState.artUrl
                        property string loadedUrl: ""
                        visible: url.length > 0 && loadedUrl === url && artSource.status === Image.Ready
                        onUrlChanged: if (url.length > 0) loadImage(url)
                        onImageLoaded: {
                            if (isImageLoaded(url)) loadedUrl = url;
                            requestPaint();
                        }
                        onVisibleChanged: requestPaint()
                        onWidthChanged: requestPaint()
                        onPaint: {
                            const context = getContext("2d");
                            context.reset();
                            const naturalWidth = artSource.implicitWidth, naturalHeight = artSource.implicitHeight;
                            if (!visible || naturalWidth <= 0 || naturalHeight <= 0) return;
                            // Crop the center square, like PreserveAspectCrop.
                            const side = Math.min(naturalWidth, naturalHeight);
                            context.beginPath();
                            context.roundedRect(0, 0, width, height, Style.radius.control, Style.radius.control);
                            context.clip();
                            context.drawImage(url, (naturalWidth - side) / 2, (naturalHeight - side) / 2, side, side,
                                0, 0, width, height);
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Style.space.xxs
                    Controls.Label {
                        objectName: "mediaTrack"
                        Layout.fillWidth: true
                        text: root.mediaState.player ? root.mediaState.boundedText(root.mediaState.player.track, 512) || qsTr("Sem título") : ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.bold: true
                        color: root.foreground
                    }
                    Controls.Label {
                        objectName: "mediaArtist"
                        Layout.fillWidth: true
                        text: root.mediaState.player ? root.mediaState.boundedText(root.mediaState.player.artist || root.mediaState.player.identity, 512) : ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        color: root.muted
                        opacity: 0.75
                    }
                    Controls.Label {
                        objectName: "mediaAlbum"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: root.mediaState.album
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: Style.type.caption
                        color: root.muted
                        opacity: 0.75
                    }
                }
            }
            // Elapsed and remaining time over a capsule bar; read only.
            ColumnLayout {
                objectName: "mediaProgress"
                Layout.fillWidth: true
                visible: Boolean(root.mediaState.player) && root.mediaState.lengthUs > 0
                spacing: Style.space.xxs
                Accessible.role: Accessible.ProgressBar
                Accessible.name: qsTr("Posição na faixa")
                Accessible.description: qsTr("%1 de %2").arg(root.mediaState.timeText(root.mediaState.positionUs))
                    .arg(root.mediaState.timeText(root.mediaState.lengthUs))
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Style.space.xs
                    radius: height / 2
                    color: Style.alpha(root.foreground, 0.16)
                    Rectangle {
                        width: parent.width * (root.mediaState.lengthUs > 0 ? root.mediaState.positionUs / root.mediaState.lengthUs : 0)
                        height: parent.height
                        radius: height / 2
                        color: root.foreground
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Label {
                        objectName: "mediaElapsed"
                        text: root.mediaState.timeText(root.mediaState.positionUs)
                        textFormat: Text.PlainText
                        font.pixelSize: Style.type.caption
                        font.features: {"tnum": 1}
                        color: root.muted
                    }
                    Item { Layout.fillWidth: true }
                    Controls.Label {
                        objectName: "mediaRemaining"
                        text: "-" + root.mediaState.timeText(root.mediaState.lengthUs - root.mediaState.positionUs)
                        textFormat: Text.PlainText
                        font.pixelSize: Style.type.caption
                        font.features: {"tnum": 1}
                        color: root.muted
                    }
                }
            }
            Timer {
                interval: 1000
                repeat: true
                running: root.visible && root.mediaState.playing
                onTriggered: root.mediaState.refreshPosition()
            }
            Controls.Label {
                objectName: "mediaPlaybackState"
                Layout.fillWidth: true
                visible: Boolean(root.mediaState.player)
                text: !root.mediaState.player ? "" : !root.mediaState.knownStatus ? qsTr("Estado de reprodução indisponível")
                    : !root.mediaState.player.canControl ? qsTr("Este player não permite controles de mídia")
                    : root.mediaState.playing ? qsTr("Reproduzindo") : root.mediaState.paused ? qsTr("Pausado") : qsTr("Parado")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.muted
                opacity: 0.75
            }
            Controls.Label {
                objectName: "mediaActionError"
                Layout.fillWidth: true
                visible: root.mediaState.actionError.length > 0
                text: root.mediaState.actionError
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: root.foreground
            }
            RowLayout {
                Layout.fillWidth: true
                visible: Boolean(root.mediaState.player)
                spacing: 6
                Controls.Button {
                    id: previousButton
                    objectName: "mediaPrevious"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 44
                    Layout.minimumWidth: 36
                    Layout.maximumWidth: 44
                    text: "‹"
                    font.pixelSize: Style.type.headline
                    enabled: root.mediaState.canPrevious
                    Accessible.name: qsTr("Anterior")
                    Controls.ToolTip.visible: hovered
                    Controls.ToolTip.text: Accessible.name
                    onActiveFocusChanged: {
                        if (activeFocus) {
                            root.focusedTransport = objectName;
                            root.reveal(this);
                        }
                        else if (enabled && visible && root.focusedTransport === objectName) root.focusedTransport = "";
                    }
                    onEnabledChanged: if (!enabled && root.focusedTransport === objectName) Qt.callLater(root.recoverFocus)
                    onClicked: root.mediaState.previous()
                }
                Controls.Button {
                    id: playButton
                    objectName: "mediaPlayPause"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 80
                    text: root.mediaState.playing ? qsTr("Pausar") : qsTr("Reproduzir")
                    icon.name: root.mediaState.playing ? "media-playback-pause" : "media-playback-start"
                    enabled: root.mediaState.canPlayPause
                    Accessible.name: text
                    Controls.ToolTip.visible: hovered
                    Controls.ToolTip.text: Accessible.name
                    onActiveFocusChanged: {
                        if (activeFocus) {
                            root.focusedTransport = objectName;
                            root.reveal(this);
                        }
                        else if (enabled && visible && root.focusedTransport === objectName) root.focusedTransport = "";
                    }
                    onEnabledChanged: if (!enabled && root.focusedTransport === objectName) Qt.callLater(root.recoverFocus)
                    onClicked: root.mediaState.playPause()
                }
                Controls.Button {
                    id: nextButton
                    objectName: "mediaNext"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 44
                    Layout.minimumWidth: 36
                    Layout.maximumWidth: 44
                    text: "›"
                    font.pixelSize: Style.type.headline
                    enabled: root.mediaState.canNext
                    Accessible.name: qsTr("Próxima")
                    Controls.ToolTip.visible: hovered
                    Controls.ToolTip.text: Accessible.name
                    onActiveFocusChanged: {
                        if (activeFocus) {
                            root.focusedTransport = objectName;
                            root.reveal(this);
                        }
                        else if (enabled && visible && root.focusedTransport === objectName) root.focusedTransport = "";
                    }
                    onEnabledChanged: if (!enabled && root.focusedTransport === objectName) Qt.callLater(root.recoverFocus)
                    onClicked: root.mediaState.next()
                }
            }
            Controls.Button {
                objectName: "mediaRaise"
                Layout.fillWidth: true
                flat: true
                visible: Boolean(root.mediaState.player) && root.mediaState.canRaise
                text: qsTr("Abrir %1").arg(root.mediaState.player ? root.mediaState.boundedText(root.mediaState.player.identity, 64) : "")
                onActiveFocusChanged: if (activeFocus) root.reveal(this)
                onClicked: root.mediaState.raise()
            }
        }
    }
}
