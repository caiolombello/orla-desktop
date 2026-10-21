import QtQuick
import QtQuick.Controls as Controls
import "../package/contents/ui" as DockUI
import "../package/contents/code/Style.js" as Style

Controls.ApplicationWindow {
    id: window
    width: 350
    height: 360
    visible: true
    property string schemeName: "dark"
    readonly property var ui: Style.scheme(schemeName)
    color: ui.surface
    palette.window: ui.surface
    palette.base: ui.raised
    palette.alternateBase: ui.sunken
    palette.windowText: ui.text
    palette.text: ui.text
    palette.buttonText: ui.text
    palette.button: ui.raised
    palette.mid: ui.border
    palette.highlight: ui.accent
    palette.highlightedText: ui.onAccent
    Controls.ScrollView {
        id: scroll
        objectName: "addonScroll"
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        Column {
            width: scroll.availableWidth
            padding: Style.space.md
            spacing: Style.space.md
            DockUI.AddonManager {
                id: manager
                objectName: "addonManager"
                width: parent.width - parent.padding * 2
                scheme: window.ui
                onRevealRequested: function(control) {
                    if (!control || !scroll.contentItem) return;
                    const top = control.mapToItem(scroll.contentItem.contentItem, 0, -Style.space.sm).y;
                    const bottom = top + control.height + Style.space.sm * 2;
                    const viewport = scroll.availableHeight;
                    if (control.height + Style.space.sm * 2 > viewport || top < scroll.contentItem.contentY)
                        scroll.contentItem.contentY = Math.max(0, top);
                    else if (bottom > scroll.contentItem.contentY + viewport)
                        scroll.contentItem.contentY = Math.max(0, bottom - viewport);
                }
            }
            Controls.Button {
                objectName: "outsideFocus"
                text: qsTr("Outra opção")
            }
        }
    }
}
