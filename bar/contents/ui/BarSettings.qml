import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property alias cfg_showApplicationName: showApplicationName.checked
    property alias cfg_menuLabel: menuLabel.text
    property string cfg_menuIcon: "orla"
    Controls.CheckBox {
        id: showApplicationName
        text: qsTr("Mostrar nome do aplicativo ativo")
    }
    Controls.Label { text: qsTr("Nome do menu"); textFormat: Text.PlainText }
    Controls.TextField {
        id: menuLabel
        maximumLength: 32
        placeholderText: "Orla"
        Accessible.name: qsTr("Nome do menu")
    }
    Controls.Label { text: qsTr("Ícone do menu"); textFormat: Text.PlainText }
    Controls.ComboBox {
        model: [qsTr("Orla"), qsTr("Sem ícone")]
        currentIndex: root.cfg_menuIcon === "none" ? 1 : 0
        onActivated: root.cfg_menuIcon = currentIndex === 1 ? "none" : "orla"
        Accessible.name: qsTr("Ícone do menu")
    }
    Controls.Label {
        text: qsTr("A altura, o monitor e a posição são configurados no painel KDE.\nMenu Global, relógio e bandeja são widgets nativos separados.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Item { Layout.fillHeight: true }
}
