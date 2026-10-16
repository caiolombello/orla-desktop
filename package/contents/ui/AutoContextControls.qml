import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

Card {
    id: controls
    radius: Style.radius.module
    required property var automation
    required property var profiles
    signal focusRequested(var control)
    readonly property var choices: profiles ? profiles.profiles : []
    function revealFocused(control) {
        // Layout can change when the status or the help expands. Never reclaim focus.
        const owner = controls;
        Qt.callLater(() => {
            if (Qt.isQtObject(owner) && Qt.isQtObject(control) && control.visible && control.activeFocus)
                owner.focusRequested(control);
        });
    }
    function revealDetails() {
        if (visible && detailsToggle.activeFocus)
            focusRequested(detailsToggle.checked ? detailsGroup : detailsToggle);
    }
    onHeightChanged: if (detailsToggle.checked) Qt.callLater(revealDetails)
    contentItem: ColumnLayout {
        spacing: Style.space.sm
        SectionLabel { text: qsTr("Perfis automáticos") }
        Controls.Label {
            Layout.fillWidth: true
            text: qsTr("Adapte o dock à sua Activity ou área de trabalho.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Controls.Label { text: qsTr("Perfil padrão"); textFormat: Text.PlainText }
        Controls.ComboBox {
            id: defaultSelector
            objectName: "autoContextDefaultProfile"
            Layout.fillWidth: true
            enabled: controls.profiles && controls.profiles.initialized && controls.profiles.writable
            model: controls.choices
            textRole: "name"
            // Keep keyboard ownership on the ComboBox with KDE's Menu popup.
            popup.focus: false
            currentIndex: controls.automation
                ? controls.choices.findIndex(entry => entry.id === controls.automation.defaultProfileId) : -1
            displayText: currentIndex < 0 ? qsTr("Escolha um perfil padrão") : currentText
            Accessible.name: qsTr("Perfil padrão do modo automático")
            Accessible.onPressAction: {
                if (!defaultSelector.enabled || !defaultSelector.visible) return;
                defaultSelector.forceActiveFocus(Qt.OtherFocusReason);
                if (defaultSelector.popup.visible) defaultSelector.popup.close();
                else defaultSelector.popup.open();
            }
            onActivated: index => controls.automation.setDefaultProfile(controls.choices[index].id)
            onActiveFocusChanged: if (activeFocus) controls.revealFocused(this)
            delegate: Controls.ItemDelegate {
                id: defaultOption
                required property var modelData
                width: defaultSelector.width
                text: modelData.name
                Accessible.onPressAction: {
                    if (defaultOption.enabled && defaultOption.visible && defaultSelector.popup.visible)
                        defaultOption.click();
                }
                contentItem: Text {
                    text: parent.text
                    textFormat: Text.PlainText
                    color: defaultSelector.palette.text
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: -Style.space.xxs
                color: "transparent"
                radius: Style.radius.control
                border.width: defaultSelector.activeFocus ? 2 : 0
                border.color: defaultSelector.palette.highlight
            }
        }
        Controls.Label {
            Layout.fillWidth: true
            visible: !controls.profiles || !controls.profiles.initialized
            text: qsTr("Crie seus perfis na aba Perfis para configurar o automático.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Controls.CheckBox {
            id: enabledToggle
            objectName: "autoContextEnabled"
            Layout.fillWidth: true
            text: qsTr("Trocar o perfil automaticamente")
            enabled: controls.automation && (controls.automation.enabled || controls.automation.canEnable)
            checked: controls.automation ? controls.automation.enabled : false
            onToggled: controls.automation.setEnabled(checked)
            onActiveFocusChanged: if (activeFocus) controls.revealFocused(this)
        }
        Controls.Label {
            objectName: "autoContextStatus"
            Layout.fillWidth: true
            text: controls.automation ? controls.automation.statusText : ""
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        OrlaButton {
            objectName: "autoContextResume"
            Layout.fillWidth: true
            visible: controls.automation && controls.automation.enabled && controls.automation.manualOverride
            onVisibleChanged: {
                if (!visible && activeFocus && controls.visible)
                    (enabledToggle.enabled ? enabledToggle : defaultSelector.enabled ? defaultSelector : detailsToggle)
                        .forceActiveFocus(Qt.TabFocusReason);
            }
            text: qsTr("Retomar automático agora")
            onClicked: {
                if (activeFocus) enabledToggle.forceActiveFocus(focusReason);
                controls.automation.resume();
            }
            onActiveFocusChanged: if (activeFocus) controls.revealFocused(this)
        }
        ColumnLayout {
            id: detailsGroup
            objectName: "autoContextDetailsGroup"
            Layout.fillWidth: true
            spacing: Style.space.sm
            OrlaButton {
                id: detailsToggle
                objectName: "autoContextHelpToggle"
                variant: "ghost"
                text: checked ? qsTr("Ocultar detalhes") : qsTr("Como funciona")
                checkable: true
                onToggled: Qt.callLater(controls.revealDetails)
                onActiveFocusChanged: if (activeFocus) Qt.callLater(controls.revealDetails)
            }
            Controls.Label {
                objectName: "autoContextHelp"
                Layout.fillWidth: true
                visible: detailsToggle.checked
                text: qsTr("Prioridade: Activity, área de trabalho e perfil padrão. Associe os perfis abaixo.\n\nUma escolha manual vale até mudar de contexto ou retomar aqui. Ao reiniciar, o automático volta. Com o contexto indisponível, o perfil atual fica mantido.\n\nAs opções são salvas na hora. A troca aguarda o fim de edições e interações, inclusive o fechamento destas opções. Não troca a Activity nem a área de trabalho.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
        }
    }
}
