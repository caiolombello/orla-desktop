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

    DockView {
        id: dock
        anchors.fill: parent
        configuration: Plasmoid.configuration
        nativePopups: true
        popAbove: Plasmoid.location === PlasmaCore.Types.BottomEdge
    }
}
