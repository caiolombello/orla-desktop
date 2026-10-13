import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

Card {
    id: root
    radius: Style.radius.module
    property var command: null
    readonly property var choices: command ? command.desktops.map((item, index, items) => ({id:item.id,
        label:items.some(other => other.id !== item.id && other.name === item.name)
            ? qsTr("%1 (%2)").arg(item.name).arg(index + 1) : item.name})) : []
    signal focusRequested(var control)
    contentItem: ColumnLayout {
        spacing: Style.space.sm
        SectionLabel { text: qsTr("Área de trabalho") }
        Controls.Label {
            objectName: "desktopSwitchCurrent"
            Layout.fillWidth: true
            text: root.command && root.command.sourceReady ? qsTr("Área atual: %1").arg(root.command.currentName)
                : qsTr("Áreas de trabalho indisponíveis")
            textFormat: Text.PlainText
            elide: Text.ElideRight
            maximumLineCount: 2
            wrapMode: Text.WordWrap
        }
        Controls.ComboBox {
            id: selector
            objectName: "desktopSwitchSelector"
            Layout.fillWidth: true
            model: root.choices
            textRole: "label"
            currentIndex: root.command ? root.choices.findIndex(item => item.id === root.command.selectedId) : -1
            enabled: root.command && root.command.available && !root.command.pending
            Accessible.name: qsTr("Área de trabalho de destino")
            onActivated: index => root.command.selectDesktop(root.choices[index].id)
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            delegate: Controls.ItemDelegate {
                required property var modelData
                width: selector.width
                text: modelData.label
                contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: selector.palette.text; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: -Style.space.xxs
                color: "transparent"
                radius: Style.radius.control
                border.width: selector.activeFocus ? 2 : 0
                border.color: selector.palette.highlight
            }
        }
        OrlaButton {
            objectName: "desktopSwitchButton"
            Layout.fillWidth: true
            text: qsTr("Trocar área")
            enabled: root.command && root.command.canRequest
            Accessible.name: text
            onClicked: root.command.requestDesktopSwitch(root.command.selectedId, root.command.desktopRevision)
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
        }
        Controls.Label {
            objectName: "desktopSwitchStatus"
            Layout.fillWidth: true
            text: !root.command || !root.command.active ? qsTr("Abra Contextos para consultar as áreas.")
                : root.command.pending ? qsTr("Aguardando confirmação…")
                : root.command.status === "failed" ? root.command.error
                : root.command.status === "observed" && root.command.selectedId === root.command.currentId ? qsTr("Área selecionada está ativa.")
                : root.command.backend && root.command.backend.status === "loading" ? qsTr("Consultando a disponibilidade…")
                : !root.command.available ? qsTr("A troca não está disponível nesta sessão.")
                : qsTr("Selecione uma área e acione Trocar área.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            Accessible.name: text
            Accessible.role: root.command && root.command.status === "failed" ? Accessible.AlertMessage : Accessible.StaticText
        }
        Controls.Label {
            Layout.fillWidth: true
            text: qsTr("A troca segue a tela ativa do KDE.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
    }
}
