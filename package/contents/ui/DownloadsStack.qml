import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as Templates
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

// The Downloads popup: the newest files in a grid, like a macOS stack. Each
// cell opens its file; the button opens the folder. Arrow keys and Tab move
// between cells.
ColumnLayout {
    id: root
    required property var entries
    required property url folder
    property var opener: url => Qt.openUrlExternally(url)
    property color foreground: Style.scheme("dark").text
    property color muted: Style.scheme("dark").textMuted
    property color accent: Style.scheme("dark").accent
    readonly property int columns: 4
    spacing: Style.space.md

    Text {
        objectName: "downloadsEmpty"
        Layout.fillWidth: true
        visible: root.entries.length === 0
        text: qsTr("Nenhum download recente.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: root.muted
    }
    GridLayout {
        objectName: "downloadsGrid"
        Layout.fillWidth: true
        visible: root.entries.length > 0
        columns: root.columns
        columnSpacing: Style.space.xs
        rowSpacing: Style.space.xs
        Repeater {
            model: root.entries
            Templates.AbstractButton {
                id: cell
                required property var modelData
                required property int index
                objectName: "downloadsCell"
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                implicitHeight: Style.size.target + Style.space.xxxl + Style.space.sm
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                text: modelData.name
                Accessible.name: modelData.name
                Accessible.role: Accessible.Button
                onClicked: root.opener(modelData.url)
                Keys.onRightPressed: nextItemInFocusChain(true).forceActiveFocus(Qt.TabFocusReason)
                Keys.onLeftPressed: nextItemInFocusChain(false).forceActiveFocus(Qt.BacktabFocusReason)
                background: Rectangle {
                    radius: Style.radius.tile
                    color: cell.down ? Style.alpha(root.foreground, Style.state.pressed)
                        : cell.hovered ? Style.alpha(root.foreground, Style.state.hover) : "transparent"
                    border.width: cell.visualFocus ? 2 : 0
                    border.color: root.accent
                }
                contentItem: ColumnLayout {
                    spacing: Style.space.xxs
                    Item {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: Style.space.xs
                        implicitWidth: Style.size.target
                        implicitHeight: Style.size.target
                        Kirigami.Icon {
                            anchors.fill: parent
                            visible: !thumbnail.visible
                            source: cell.modelData.icon
                        }
                        // Images show themselves, small and loaded off the UI thread.
                        Image {
                            id: thumbnail
                            objectName: "downloadsThumbnail"
                            anchors.fill: parent
                            visible: cell.modelData.thumbnail && status === Image.Ready
                            source: cell.modelData.thumbnail ? cell.modelData.url : ""
                            sourceSize.width: Style.size.target * 2
                            sourceSize.height: Style.size.target * 2
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: Style.space.xxs
                        Layout.rightMargin: Style.space.xxs
                        text: cell.modelData.name
                        textFormat: Text.PlainText
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WrapAnywhere
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        font.pixelSize: Style.type.caption
                        color: root.foreground
                    }
                }
            }
        }
    }
    OrlaButton {
        objectName: "downloadsOpenFolder"
        Layout.fillWidth: true
        text: qsTr("Abrir a pasta Downloads")
        onClicked: root.opener(root.folder)
    }
}
