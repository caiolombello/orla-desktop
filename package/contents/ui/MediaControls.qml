import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

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
            Controls.Label {
                objectName: "mediaTrack"
                Layout.fillWidth: true
                visible: Boolean(root.mediaState.player)
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
                visible: Boolean(root.mediaState.player)
                text: root.mediaState.player ? root.mediaState.boundedText(root.mediaState.player.artist || root.mediaState.player.identity, 512) : ""
                textFormat: Text.PlainText
                elide: Text.ElideRight
                maximumLineCount: 1
                color: root.muted
                opacity: 0.75
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
                    font.pixelSize: 22
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
                    font.pixelSize: 22
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
        }
    }
}
