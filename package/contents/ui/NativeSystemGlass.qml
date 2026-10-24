import QtQuick
import org.kde.ksvg as KSvg

// Production-only: tells whether the active Plasma theme is the Orla theme,
// whose frames give the dock and its popups KWin's blur. It looks for marker
// elements instead of a theme name, and rechecks when the theme changes.
Item {
    id: root
    visible: false
    property bool dockFrame: false
    property bool popupFrame: false
    function check() {
        dockFrame = panelSvg.hasElement("south-hint-orla-dock");
        popupFrame = dialogSvg.hasElement("hint-orla-glass");
    }
    KSvg.Svg {
        id: panelSvg
        imagePath: "widgets/panel-background"
        onRepaintNeeded: root.check()
    }
    KSvg.Svg {
        id: dialogSvg
        imagePath: "dialogs/background"
        onRepaintNeeded: root.check()
    }
    Component.onCompleted: check()
}
