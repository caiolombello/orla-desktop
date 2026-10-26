import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore

PlasmoidItem {
    id: applet
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    Layout.minimumWidth: 240
    Layout.minimumHeight: 64
    Layout.preferredWidth: dock.implicitWidth
    Layout.preferredHeight: dock.implicitHeight

    // The dock draws its own glass. When it is the only widget of a panel, hide
    // the panel's frame so two surfaces do not stack; restore it otherwise. The
    // change is not saved: the panel gets its frame back if the dock is removed.
    // With the Orla Plasma theme on a bottom panel, the frame stays: it is an
    // invisible slab-shaped region that lets KWin blur behind the dock's tint.
    readonly property bool frostedDock: systemGlass.dockFrame && Plasmoid.location === PlasmaCore.Types.BottomEdge
    onFrostedDockChanged: { adoptHostPanel(); Qt.callLater(measurePanelFrame); }
    readonly property bool dockAlone: Boolean(Plasmoid.containment && Plasmoid.containment.applets
        && Plasmoid.containment.applets.length === 1)
    property var hostHints: undefined
    property var hostPanel: null
    function restoreHostPanel() {
        if (hostPanel && hostHints !== undefined) hostPanel.backgroundHints = hostHints;
        hostPanel = null;
        hostHints = undefined;
    }
    function adoptHostPanel() {
        const host = Plasmoid.containment;
        if (hostPanel && hostPanel !== host) restoreHostPanel();
        if (!host || !host.applets) return;
        const inPanel = Plasmoid.formFactor === PlasmaCore.Types.Horizontal
            || Plasmoid.formFactor === PlasmaCore.Types.Vertical;
        const alone = inPanel && host.applets.length === 1 && !applet.frostedDock;
        if (alone && hostHints === undefined) {
            hostPanel = host;
            hostHints = host.backgroundHints;
            host.backgroundHints = PlasmaCore.Types.NoBackground;
        } else if (!alone && hostHints !== undefined) {
            restoreHostPanel();
        }
    }
    Connections {
        target: Plasmoid.containment
        ignoreUnknownSignals: true
        function onAppletsChanged() { applet.adoptHostPanel(); }
    }
    Connections {
        target: Plasmoid
        function onContainmentChanged() { applet.adoptHostPanel(); }
    }
    Component.onCompleted: adoptHostPanel()
    Component.onDestruction: restoreHostPanel()

    NativeSystemGlass { id: systemGlass }

    // Where the panel frame lies in dock coordinates. The panel's containment
    // item fills the frame of a floating panel, so the slab can follow the frame
    // whatever margins the containment gives its widgets.
    property Item containmentItem: null
    // Space between the dock and the frame on each side: {left, top, right, bottom}.
    property var panelMargins: null
    function measurePanelFrame() {
        if (!containmentItem) {
            for (let node = applet.parent; node; node = node.parent) {
                if (node.plasmoid !== undefined && node.plasmoid === Plasmoid.containment) {
                    containmentItem = node;
                    break;
                }
            }
        }
        if (!containmentItem) return;
        const origin = containmentItem.mapToItem(dock, 0, 0);
        const margins = {left: -origin.x, top: -origin.y,
            right: containmentItem.width + origin.x - dock.width,
            bottom: containmentItem.height + origin.y - dock.height};
        const old = panelMargins;
        if (!old || old.left !== margins.left || old.top !== margins.top
                || old.right !== margins.right || old.bottom !== margins.bottom)
            panelMargins = margins;
    }
    onWidthChanged: Qt.callLater(measurePanelFrame)
    onHeightChanged: Qt.callLater(measurePanelFrame)
    onXChanged: Qt.callLater(measurePanelFrame)
    Connections {
        target: applet.containmentItem
        function onWidthChanged() { Qt.callLater(applet.measurePanelFrame); }
        function onHeightChanged() { Qt.callLater(applet.measurePanelFrame); }
    }
    Connections {
        target: applet.parent
        ignoreUnknownSignals: true
        function onXChanged() { Qt.callLater(applet.measurePanelFrame); }
        function onYChanged() { Qt.callLater(applet.measurePanelFrame); }
    }

    DockView {
        id: dock
        anchors.fill: parent
        configuration: Plasmoid.configuration
        // The frame matches the slab only when the dock fills its panel alone.
        systemGlass: applet.frostedDock && applet.dockAlone
        systemGlassMargins: applet.panelMargins
        systemPopupGlass: systemGlass.popupFrame
        nativePopups: true
        screenGeometry: Plasmoid.containment ? Plasmoid.containment.screenGeometry : Qt.rect(0, 0, -1, -1)
        popAbove: Plasmoid.location === PlasmaCore.Types.BottomEdge
    }
}
