import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kcmutils as KCMUtils

PlasmoidItem {
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    Layout.minimumWidth: 48
    Layout.minimumHeight: bar.implicitHeight
    Layout.preferredWidth: bar.implicitWidth
    Layout.preferredHeight: bar.implicitHeight
    NativePopupHost {
        id: nativePopupHost
        location: Plasmoid.location
    }
    BarView {
        id: bar
        popupHost: nativePopupHost
        menuTooltipBackend: nativeMenuTooltip
        anchors.fill: parent
        showApplicationName: Plasmoid.configuration.showApplicationName
        showMenuLabel: Plasmoid.configuration.showMenuLabel
        compactHeight: Plasmoid.configuration.compactHeight
        menuLabel: Plasmoid.configuration.menuLabel
        menuIcon: Plasmoid.configuration.menuIcon
        onOpenRequested: kind => {
            if (kind === "system") KCMUtils.KCMLauncher.openInfoCenter("kcm_about-distro");
            else if (kind === "settings") KCMUtils.KCMLauncher.openSystemSettings("");
            else if (kind === "configure") Plasmoid.containment.configureRequested(Plasmoid);
        }
    }
    PlasmaCore.ToolTipArea {
        id: nativeMenuTooltip
        parent: bar.menuControl
        anchors.fill: parent
        mainText: qsTr("Menu Orla")
        textFormat: Text.PlainText
        location: Plasmoid.location
        interactive: false
        active: bar.menuControl.enabled && !bar.menuControl.down && !bar.menuIsOpen
    }

}
