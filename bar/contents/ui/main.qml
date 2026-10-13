import QtQuick
import QtQuick.Window
import QtCore
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kcmutils as KCMUtils
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

PlasmoidItem {
    id: root
    preferredRepresentation: fullRepresentation
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    Layout.minimumWidth: 48
    Layout.minimumHeight: bar.implicitHeight
    Layout.preferredWidth: bar.implicitWidth
    Layout.preferredHeight: bar.implicitHeight
    // Canonical client remains in the dock package; disabling never loads it.
    readonly property url controlCenterSource: Plasmoid.configuration.showControlCenter
        ? StandardPaths.locate(StandardPaths.GenericDataLocation,
            "plasma/plasmoids/org.caiodock.dock/contents/ui/ControlCenterEntry.qml", StandardPaths.LocateFile) : ""
    Loader {
        id: controlCenterEntry
        objectName: "barControlCenterEntryLoader"
        active: Plasmoid.configuration.showControlCenter && root.controlCenterSource.toString() !== ""
        source: active ? root.controlCenterSource : ""
    }
    Item {
        id: nativeControlCenterHost
        objectName: "barControlCenterHost"
        anchors.fill: parent
        readonly property bool nativePopups: true
        readonly property bool popAbove: Plasmoid.location === PlasmaCore.Types.BottomEdge
        readonly property var popupScheme: Style.scheme(Style.schemeFor(bar.menuControl.palette.window))
        // Screen/Window attached geometry belongs to this bar's panel window.
    }
    NativePopupHost {
        id: nativePopupHost
        location: Plasmoid.location
    }
    BarView {
        id: bar
        popupHost: nativePopupHost
        menuTooltipBackend: nativeMenuTooltip
        controlCenterTooltipBackend: nativeControlCenterTooltip
        anchors.fill: parent
        showOrlaMenu: Plasmoid.configuration.showOrlaMenu
        showControlCenter: Plasmoid.configuration.showControlCenter
        controlCenterClient: controlCenterEntry.item
        controlCenterHost: nativeControlCenterHost
        reducedMotion: Kirigami.Units.shortDuration <= 0
        controlCenterLoadError: controlCenterEntry.status === Loader.Error
            ? qsTr("Não foi possível carregar a Central de Controle da Orla Dock.")
            : controlCenterEntry.status === Loader.Loading ? qsTr("Carregando a Central de Controle…")
            : qsTr("Central de Controle indisponível. Instale e ative uma única Orla Dock.")
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
        active: bar.showOrlaMenu && bar.menuControl.enabled && !bar.menuControl.down && !bar.menuIsOpen
    }
    PlasmaCore.ToolTipArea {
        id: nativeControlCenterTooltip
        parent: bar.controlCenterControl
        anchors.fill: parent
        mainText: qsTr("Central de Controle")
        subText: bar.controlCenterDescription
        textFormat: Text.PlainText
        location: Plasmoid.location
        interactive: false
        active: bar.showControlCenter && !bar.controlCenterControl.down && !bar.controlCenterIsOpen
    }

}
