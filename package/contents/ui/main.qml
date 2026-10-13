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
        const alone = inPanel && host.applets.length === 1;
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

    DockView {
        id: dock
        anchors.fill: parent
        configuration: Plasmoid.configuration
        nativePopups: true
        popAbove: Plasmoid.location === PlasmaCore.Types.BottomEdge
    }
}
