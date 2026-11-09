import QtQuick
import QtQuick.Window
import org.kde.layershell as LayerShell
import "../code/Style.js" as Style

// The island's window in a Wayland session: a layer-shell surface anchored to
// the top edge, which KWin centers horizontally, as large as the capsule. Only
// the capsule takes clicks: the surface ends where it ends. The top layer sits
// over the menu bar and under fullscreen windows, as macOS hides its menu bar.
// It never takes keyboard focus. Loaded only by the production panel backend.
Window {
    id: window
    readonly property var owner: islandOwner
    readonly property rect area: owner.screenGeometry
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
    LayerShell.Window.layer: LayerShell.Window.LayerTop
    LayerShell.Window.anchors: LayerShell.Window.AnchorTop
    LayerShell.Window.margins.top: Style.space.xs
    // -1: over the bar's reserved strip instead of below it.
    LayerShell.Window.exclusionZone: -1
    LayerShell.Window.keyboardInteractivity: LayerShell.Window.KeyboardInteractivityNone
    LayerShell.Window.scope: "orla-island"
    // The dock's screen. Layer surfaces pick their output when they map, so a
    // screen change applies the next time the island shows.
    screen: dockScreen()
    width: Math.max(1, Math.ceil(island.implicitWidth))
    height: Math.max(1, Math.ceil(island.implicitHeight))
    visible: area.width > 0 && island.showing

    function dockScreen() {
        const screens = Qt.application.screens;
        for (let index = 0; index < screens.length; ++index) {
            if (screens[index].virtualX === area.x && screens[index].virtualY === area.y) return screens[index];
        }
        return screens.length ? screens[0] : null;
    }

    EventIsland {
        id: island
        anchors.fill: parent
        islandState: window.owner.islandModel
        mediaController: window.owner.islandMedia
        timerController: window.owner.pomodoro
        interactive: true
        reducedMotion: window.owner.motion <= 0
    }
}
