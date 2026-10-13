import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property alias cfg_showOrlaMenu: showOrlaMenu.checked
    property alias cfg_showControlCenter: showControlCenter.checked
    property alias cfg_showApplicationName: showApplicationName.checked
    property alias cfg_menuLabel: menuLabel.text
    property alias cfg_showMenuLabel: showMenuLabel.checked
    property alias cfg_compactHeight: compactHeight.checked
    property string cfg_menuIcon: "orla"
    Controls.CheckBox {
        id: showOrlaMenu
        objectName: "showOrlaMenuSetting"
        checked: true
        text: qsTr("Mostrar Menu Orla")
        Layout.fillWidth: true
        contentItem: Controls.Label {
            text: showOrlaMenu.text
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            leftPadding: showOrlaMenu.indicator.width + showOrlaMenu.spacing
            verticalAlignment: Text.AlignVCenter
        }
    }
    Controls.CheckBox {
        id: showControlCenter
        objectName: "showControlCenterSetting"
        checked: false
        text: qsTr("Mostrar Central de Controle")
        Layout.fillWidth: true
        contentItem: Controls.Label {
            text: showControlCenter.text
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            leftPadding: showControlCenter.indicator.width + showControlCenter.spacing
            verticalAlignment: Text.AlignVCenter
        }
    }
    Controls.Label {
        text: qsTr("A Central de Controle usa uma única Orla Dock ativa. Adicione outra Barra Orla à direita e oculte nela o menu e o nome do aplicativo.")
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Controls.CheckBox {
        id: showApplicationName
        text: qsTr("Mostrar nome do aplicativo ativo")
    }
    Controls.Button {
        objectName: "applyMacInspiredPreset"
        text: qsTr("Aplicar estilo inspirado no Mac")
        onClicked: {
            root.cfg_menuIcon = "orla";
            root.cfg_showMenuLabel = false;
            root.cfg_compactHeight = true;
            root.cfg_showApplicationName = true;
        }
    }
    Controls.CheckBox {
        id: showMenuLabel
        text: qsTr("Mostrar nome do menu junto ao ícone")
    }
    Controls.CheckBox {
        id: compactHeight
        text: qsTr("Usar controles compactos (28 px)")
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
