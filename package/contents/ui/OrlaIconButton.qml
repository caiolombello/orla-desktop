import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Templates as Templates
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

// Round icon button, like a macOS Control Center toggle. `checked` fills it with
// the accent. `text` is the accessible name and tooltip; it is not drawn.
// `flat` drops the resting fill, for secondary actions in module headers.
Templates.Button {
    id: control
    property string iconName: ""
    implicitWidth: Style.size.target
    implicitHeight: Style.size.target
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 1 - Style.state.disabled
    Accessible.name: text
    Controls.ToolTip.visible: hovered && text.length > 0
    Controls.ToolTip.text: text
    Controls.ToolTip.delay: 650
    contentItem: Item {
        Kirigami.Icon {
            anchors.centerIn: parent
            width: Style.size.iconMd
            height: width
            source: control.iconName
            isMask: true
            color: control.checked ? control.palette.highlightedText : control.palette.windowText
            opacity: control.flat && !control.checked ? 0.72 : 1
        }
    }
    background: Rectangle {
        radius: width / 2
        color: control.checked ? control.palette.highlight
            : control.flat ? "transparent" : Style.alpha(control.palette.windowText, Style.state.hover + 0.02)
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: control.checked ? control.palette.highlightedText : control.palette.windowText
            opacity: control.down ? Style.state.pressed : control.hovered ? Style.state.hover : 0
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: width / 2
            color: "transparent"
            visible: control.visualFocus
            border.width: 2
            border.color: control.palette.highlight
        }
    }
}
