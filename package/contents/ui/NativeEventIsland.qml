import QtQuick
import org.kde.plasma.core as PlasmaCore
import "../code/Style.js" as Style

// The event island's window: centered at the top of the dock's screen, over the
// empty middle of the menu bar, like the iPhone's Dynamic Island. It never takes
// focus or input. Loaded only by the production panel backend.
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
        eventState: window.owner.eventIslandState
        reducedMotion: window.owner.motion <= 0
    }
}
