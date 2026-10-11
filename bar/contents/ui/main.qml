import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kcmutils as KCMUtils

PlasmoidItem {
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    Layout.minimumWidth: 48
    Layout.minimumHeight: 32
    Layout.preferredWidth: bar.implicitWidth
    Layout.preferredHeight: bar.implicitHeight
    BarView {
        id: bar
        anchors.fill: parent
        showApplicationName: Plasmoid.configuration.showApplicationName
        menuLabel: Plasmoid.configuration.menuLabel
        menuIcon: Plasmoid.configuration.menuIcon
        onOpenRequested: kind => {
            if (kind === "system") KCMUtils.KCMLauncher.openInfoCenter("kcm_about-distro");
            else if (kind === "settings") KCMUtils.KCMLauncher.openSystemSettings("");
            else if (kind === "configure") Plasmoid.containment.configureRequested(Plasmoid);
        }
    }
}
