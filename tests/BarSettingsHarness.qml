import QtQuick
import QtQuick.Window
import "../bar/contents/ui" as BarUI

Window {
    width: 520
    height: 560
    visible: true
    color: settings.palette.window
    BarUI.BarSettings {
        id: settings
        objectName: "barSettingsUnderTest"
        anchors.fill: parent
        cfg_showOrlaMenu: true
        cfg_showControlCenter: false
        cfg_showApplicationName: true
        cfg_showMenuLabel: true
        cfg_compactHeight: false
        cfg_menuLabel: "Orla"
        cfg_menuIcon: "orla"
    }
}
