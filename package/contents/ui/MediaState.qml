import QtQml
import QtQml.Models
import org.kde.plasma.private.mpris as Mpris

QtObject {
    id: root
    // Plasma 6.7.5: Mpris2Model.currentPlayer/currentIndex and its model roles.
    required property var media
    readonly property var player: media ? media.currentPlayer : null
    readonly property bool playing: Boolean(player && player.playbackStatus === Mpris.PlaybackStatus.Playing)
    readonly property bool paused: Boolean(player && player.playbackStatus === Mpris.PlaybackStatus.Paused)
    readonly property bool knownStatus: Boolean(player && (player.playbackStatus === Mpris.PlaybackStatus.Playing
        || player.playbackStatus === Mpris.PlaybackStatus.Paused || player.playbackStatus === Mpris.PlaybackStatus.Stopped))
    readonly property bool canPlayPause: Boolean(player && player.canControl && knownStatus
        && (playing ? player.canPause : player.canPlay))
    readonly property bool canPrevious: Boolean(player && player.canControl && player.canGoPrevious)
    readonly property bool canNext: Boolean(player && player.canControl && player.canGoNext)
    property bool selectionMade: false
    property Instantiator candidates: Instantiator {
        model: root.media
        delegate: QtObject {
            required property int index
            required property string identity
            required property string desktopEntry
            required property bool isMultiplexer
            onIdentityChanged: Qt.callLater(root.preferSpotify)
            onDesktopEntryChanged: Qt.callLater(root.preferSpotify)
        }
        onObjectAdded: Qt.callLater(root.preferSpotify)
    }
    property string actionError: ""
    onPlayerChanged: actionError = ""

    function boundedText(value, maximum) {
        // Bound text before layout, and render it as PlainText in the view.
        return String(value || "").slice(0, maximum).replace(/\s+/g, " ").trim();
    }
    function preferSpotify() {
        if (!media || selectionMade) return;
        for (let i = 0; i < candidates.count; ++i) {
            const candidate = candidates.objectAt(i);
            if (!candidate || candidate.isMultiplexer) continue;
            const desktop = candidate.desktopEntry.toLowerCase().replace(/\.desktop$/, "");
            if (desktop === "spotify" || desktop === "com.spotify.client"
                    || candidate.identity.toLowerCase() === "spotify") {
                choosePlayer(i);
                return;
            }
        }
    }
    function choosePlayer(index) {
        if (!media || index < 0 || index >= candidates.count) return false;
        media.currentIndex = index;
        selectionMade = true;
        actionError = "";
        return true;
    }
    function playPause() {
        if (!canPlayPause) return false;
        try {
            // PlayPause() requires both canPlay and canPause in libkmpris.
            if (playing) player.Pause();
            else player.Play();
            actionError = "";
            return true;
        } catch (error) {
            actionError = qsTr("O player não pôde receber o comando. Tente novamente.");
            return false;
        }
    }
    function previous() {
        if (!canPrevious) return false;
        try { player.Previous(); actionError = ""; return true; }
        catch (error) { actionError = qsTr("O player não pôde receber o comando. Tente novamente."); return false; }
    }
    function next() {
        if (!canNext) return false;
        try { player.Next(); actionError = ""; return true; }
        catch (error) { actionError = qsTr("O player não pôde receber o comando. Tente novamente."); return false; }
    }
}
