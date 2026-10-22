import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import QtQuick.Window
import "../code/Style.js" as Style

Controls.ScrollView {
    id: root
    property alias cfg_showOrlaMenu: showOrlaMenu.checked
    property alias cfg_showControlCenter: showControlCenter.checked
    property alias cfg_showApplicationName: showApplicationName.checked
    property alias cfg_menuLabel: menuLabel.text
    property alias cfg_showMenuLabel: showMenuLabel.checked
    property alias cfg_compactHeight: compactHeight.checked
    property string cfg_menuIcon: "orla"
    property bool menuExpanded: false
    property bool helpExpanded: false
    readonly property var ui: Style.scheme(Style.schemeFor(palette.window))
    implicitWidth: Style.size.popupWidth + Style.space.xxxl * 2
    implicitHeight: Style.size.target * 12
    contentWidth: availableWidth
    clip: true
    padding: Style.space.xs
    Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
    Accessible.name: qsTr("Configurações da barra")

    function inside(item, section) {
        for (let current = item; current; current = current.parent)
            if (current === section) return true;
        return false;
    }
    function restoreSectionFocus(section, disclosure) {
        const host = root.Window.window;
        if (root.visible && host && inside(host.activeFocusItem, section))
            disclosure.forceActiveFocus(Qt.TabFocusReason);
    }
    function setMenuOpen(open) {
        if (!open) restoreSectionFocus(menuFields, menuDisclosure);
        menuExpanded = !!open;
        Qt.callLater(revealFocused);
    }
    function setHelpOpen(open) {
        if (!open) restoreSectionFocus(compositionHelp, helpDisclosure);
        helpExpanded = !!open;
        Qt.callLater(revealFocused);
    }
    function revealFocused() {
        const host = root.Window.window;
        const control = host ? host.activeFocusItem : null;
        const viewport = root.contentItem;
        if (!root.visible || !control || !control.visible || !inside(control, body)) return;
        const y = control.mapToItem(body, 0, 0).y;
        let end = y + control.height;
        if (control === menuDisclosure && menuExpanded)
            end = menuFields.mapToItem(body, 0, menuFields.height).y;
        else if (control === helpDisclosure && helpExpanded)
            end = compositionHelp.mapToItem(body, 0, compositionHelp.height).y;
        const margin = Style.space.xs;
        const top = y - margin;
        const bottom = end + margin;
        let next = viewport.contentY;
        if (top < next || bottom - top > viewport.height) next = top;
        else if (bottom > next + viewport.height) next = bottom - viewport.height;
        viewport.contentY = Math.max(0, Math.min(next, Math.max(0, body.height - viewport.height)));
    }
    onHeightChanged: Qt.callLater(revealFocused)
    onContentHeightChanged: Qt.callLater(revealFocused)
    onVisibleChanged: if (!visible) { setMenuOpen(false); setHelpOpen(false); }
    Connections {
        target: root.Window.window
        function onActiveFocusItemChanged() { root.revealFocused(); }
    }

    component FocusRing: Rectangle {
        anchors.fill: parent
        color: Style.alpha(root.palette.highlight, 0)
        radius: Style.radius.control
        border.width: 2
        border.color: root.palette.highlight
        visible: parent.activeFocus
    }
    component SettingCheckBox: Controls.CheckBox {
        id: check
        Layout.fillWidth: true
        contentItem: Controls.Label {
            text: check.text
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            leftPadding: check.indicator.width + check.spacing
            verticalAlignment: Text.AlignVCenter
        }
        FocusRing {}
    }
    component Note: Controls.Label {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        color: root.ui.textMuted
        font.pixelSize: Style.type.label
    }
    // The bar is an independent applet; GroupBox keeps native grouping semantics
    // while using the same module fill, rim and padding as Orla's Card.
    component SettingsGroup: Controls.GroupBox {
        id: group
        Layout.fillWidth: true
        padding: Style.space.lg
        topPadding: padding + implicitLabelHeight + Style.space.sm
        label: Controls.Label {
            x: group.leftPadding
            y: group.padding
            width: group.availableWidth
            text: group.title
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            font.pixelSize: Style.type.title
            font.weight: Style.weight.demiBold
        }
        background: Rectangle {
            radius: Style.radius.module
            color: group.palette.base
            border.width: 1
            border.color: group.palette.mid
        }
    }
    component Disclosure: Controls.ItemDelegate {
        Layout.fillWidth: true
        implicitHeight: Math.max(Style.size.target, implicitContentHeight + topPadding + bottomPadding)
        focusPolicy: Qt.StrongFocus
        checkable: true
        icon.name: checked ? "arrow-down" : "arrow-right"
        FocusRing {}
    }

    ColumnLayout {
        id: body
        width: root.availableWidth - root.effectiveScrollBarWidth
        spacing: Style.space.lg
        SettingsGroup {
            title: qsTr("Conteúdo da barra")
            ColumnLayout {
                anchors.fill: parent
                spacing: Style.space.xs
                SettingCheckBox {
                    id: showOrlaMenu
                    objectName: "showOrlaMenuSetting"
                    checked: true
                    text: qsTr("Mostrar Menu Orla")
                }
                SettingCheckBox {
                    id: showApplicationName
                    objectName: "showApplicationNameSetting"
                    text: qsTr("Mostrar nome do aplicativo ativo")
                }
                SettingCheckBox {
                    id: showControlCenter
                    objectName: "showControlCenterSetting"
                    checked: false
                    text: qsTr("Mostrar Central de Controle")
                }
                Note { text: qsTr("A Central de Controle usa uma única Orla Dock ativa.") }
            }
        }
        SettingsGroup {
            title: qsTr("Aparência")
            ColumnLayout {
                anchors.fill: parent
                spacing: Style.space.sm
                SettingCheckBox {
                    id: compactHeight
                    objectName: "compactHeightSetting"
                    text: qsTr("Usar controles compactos (28 px)")
                }
                Controls.Button {
                    objectName: "applyMacInspiredPreset"
                    Layout.fillWidth: true
                    implicitHeight: Math.max(Style.size.target, implicitContentHeight + topPadding + bottomPadding)
                    text: qsTr("Aplicar estilo inspirado no Mac")
                    onClicked: {
                        root.cfg_menuIcon = "orla";
                        root.cfg_showMenuLabel = false;
                        root.cfg_compactHeight = true;
                        root.cfg_showApplicationName = true;
                    }
                    FocusRing {}
                }
                Note {
                    objectName: "barPresetSummary"
                    text: qsTr("Usa o ícone Orla sem nome ao lado, controles compactos e o nome do aplicativo ativo. Mantém suas escolhas de Menu Orla e Central de Controle.")
                }
                Disclosure {
                    id: menuDisclosure
                    objectName: "barMenuCustomizationDisclosure"
                    text: qsTr("Personalizar o menu")
                    checked: root.menuExpanded
                    onToggled: root.setMenuOpen(checked)
                }
                ColumnLayout {
                    id: menuFields
                    objectName: "barMenuCustomizationFields"
                    Layout.fillWidth: true
                    spacing: Style.space.sm
                    visible: root.menuExpanded
                    Note {
                        visible: !showOrlaMenu.checked
                        text: qsTr("Ative Mostrar Menu Orla para usar estas opções. Suas escolhas ficam guardadas.")
                    }
                    Controls.Label {
                        text: qsTr("Ícone do menu")
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                    Controls.ComboBox {
                        id: menuIcon
                        objectName: "menuIconSetting"
                        Layout.fillWidth: true
                        enabled: showOrlaMenu.checked
                        model: [qsTr("Orla"), qsTr("Sem ícone")]
                        currentIndex: root.cfg_menuIcon === "none" ? 1 : 0
                        onActivated: root.cfg_menuIcon = currentIndex === 1 ? "none" : "orla"
                        Accessible.name: qsTr("Ícone do menu")
                        FocusRing {}
                    }
                    SettingCheckBox {
                        id: showMenuLabel
                        objectName: "showMenuLabelSetting"
                        enabled: showOrlaMenu.checked && root.cfg_menuIcon !== "none"
                        text: qsTr("Mostrar nome do menu junto ao ícone")
                    }
                    Note {
                        visible: root.cfg_menuIcon === "none"
                        text: qsTr("Sem ícone, o nome do menu aparece sempre.")
                    }
                    Controls.Label {
                        text: qsTr("Nome do menu")
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                    Controls.TextField {
                        id: menuLabel
                        objectName: "menuLabelSetting"
                        Layout.fillWidth: true
                        enabled: showOrlaMenu.checked && (showMenuLabel.checked || root.cfg_menuIcon === "none")
                        maximumLength: 32
                        placeholderText: "Orla"
                        Accessible.name: qsTr("Nome do menu")
                        FocusRing {}
                    }
                    Note {
                        visible: showOrlaMenu.checked && root.cfg_menuIcon !== "none" && !showMenuLabel.checked
                        text: qsTr("Ative Mostrar nome do menu para exibir o nome ao lado do ícone.")
                    }
                }
            }
        }
        Disclosure {
            id: helpDisclosure
            objectName: "barCompositionHelpDisclosure"
            text: qsTr("Como organizar a barra")
            checked: root.helpExpanded
            onToggled: root.setHelpOpen(checked)
        }
        Note {
            id: compositionHelp
            objectName: "barCompositionHelpText"
            visible: root.helpExpanded
            text: qsTr("Para usar a Central à direita, adicione outra Barra Orla e oculte nela o Menu Orla e o nome do aplicativo.\n\nAltura, monitor e posição são ajustados no painel KDE. Menu Global, relógio e bandeja são widgets nativos separados.")
        }
    }
}
