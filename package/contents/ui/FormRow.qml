import QtQuick
import QtQuick.Layouts
import "../code/Style.js" as Style

// One row of a grouped settings list, macOS style. Put rows in a ColumnLayout
// (spacing 0) inside `Card { padding: 0 }`: label left, control right, and a
// hairline below every row except the `last` one.
Item {
    id: row
    property bool last: false
    default property alias content: layout.data
    Layout.fillWidth: true
    implicitWidth: layout.implicitWidth + Style.space.md + Style.space.sm
    implicitHeight: Math.max(Style.size.target + Style.space.xs, layout.implicitHeight + Style.space.sm * 2)
    RowLayout {
        id: layout
        anchors.fill: parent
        anchors.leftMargin: Style.space.md
        anchors.rightMargin: Style.space.sm
        spacing: Style.space.sm
    }
    Rectangle {
        visible: !row.last
        anchors.left: parent.left
        anchors.leftMargin: Style.space.md
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Style.alpha(row.palette.windowText, 0.1)
    }
}
