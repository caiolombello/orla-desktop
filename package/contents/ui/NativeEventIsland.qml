import QtQuick
import org.kde.plasma.core as PlasmaCore
import "../code/Style.js" as Style

// The island's window outside Wayland, where layer-shell is unavailable:
// centered at the top of the dock's screen, over the empty middle of the menu
// bar. It never takes focus or input, so it shows notices and compact
// activities but never expands. Loaded only by the production panel backend.
PlasmaCore.Dialog {
    id: window
    readonly property var owner: islandOwner
    readonly property rect area: owner.screenGeometry
    // Notification, not OnScreenDisplay: KWin keeps both above panels, but it
    // places OSD windows itself (centered, low on the screen) and ignores x/y.
    type: PlasmaCore.Dialog.Notification
    flags: Qt.WindowDoesNotAcceptFocus
    location: PlasmaCore.Types.Floating
    backgroundHints: PlasmaCore.Dialog.NoBackground
    color: "transparent"
    outputOnly: true
    hideOnWindowDeactivate: false
    x: area.x + Math.round((area.width - width) / 2)
    y: area.y + Style.space.xs
    visible: area.width > 0 && island.showing

    mainItem: EventIsland {
        id: island
        islandState: window.owner.islandModel
        fixedSize: true
        reducedMotion: window.owner.motion <= 0
    }
}
