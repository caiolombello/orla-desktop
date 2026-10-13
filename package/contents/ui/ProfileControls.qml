import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

Controls.ScrollView {
    id: controls
    required property var profiles
    required property var appearance
    property var preset: null
    readonly property bool dirty: appearance.dirty || (preset !== null && preset.dirty)
    property string pendingId: profiles.activeProfileId
    readonly property var choices: [{id: "legacy", name: qsTr("Preferências anteriores")}].concat(profiles.profiles)
    contentWidth: availableWidth
    clip: true
    function reveal(control) {
        const viewport = contentItem;
        const point = control.mapToItem(viewport, 0, 0);
        if (point.y < 0) viewport.contentY += point.y;
        else if (point.y + control.height > viewport.height) viewport.contentY += point.y + control.height - viewport.height;
    }
    Connections { target: controls.profiles; function onActiveProfileIdChanged() { controls.pendingId = controls.profiles.activeProfileId; } }
    ColumnLayout {
        width: controls.availableWidth
        spacing: 8
        Controls.Label { Layout.fillWidth: true; text: qsTr("Perfis guardam apps fixados, aparência e widgets deste dock. O Pomodoro continua compartilhado."); textFormat: Text.PlainText; wrapMode: Text.WordWrap }
        Controls.Label { Layout.fillWidth: true; visible: !controls.profiles.initialized; text: qsTr("Criar os perfis Trabalho, Pessoal e Jogos copia suas preferências salvas e mantém o dock atual."); textFormat: Text.PlainText; wrapMode: Text.WordWrap }
        Controls.Button {
            objectName: "profileInitialize"
            Layout.fillWidth: true
            visible: !controls.profiles.initialized
            text: qsTr("Criar Trabalho, Pessoal e Jogos")
            enabled: controls.profiles.writable && !controls.dirty
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onClicked: controls.profiles.initializeDefaults(controls.profiles.activeProfileId, controls.profiles.revision)
        }
        Controls.Label { text: qsTr("Escolher perfil"); font.bold: true }
        Controls.ComboBox {
            id: selector
            objectName: "profileSelector"
            Layout.fillWidth: true
            model: controls.choices
            textRole: "name"
            currentIndex: controls.choices.findIndex(choice => choice.id === controls.pendingId)
            Accessible.name: qsTr("Perfil a usar")
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onActivated: index => controls.pendingId = controls.choices[index].id
            // Keep the native style TextInput; ComboBox display text is literal.
            delegate: Controls.ItemDelegate {
                required property var modelData
                width: selector.width
                text: modelData.name
                contentItem: Text { text: parent.text; textFormat: Text.PlainText; color: selector.palette.text; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
            }
        }
        Controls.Button {
            objectName: "profileUse"
            Layout.fillWidth: true
            text: qsTr("Usar perfil")
            enabled: controls.profiles.writable && !controls.dirty && controls.pendingId !== controls.profiles.activeProfileId
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onClicked: controls.profiles.select(controls.pendingId, controls.profiles.activeProfileId, controls.profiles.revision)
        }
        Controls.Label { text: qsTr("Novo perfil a partir do que está salvo"); Layout.fillWidth: true; wrapMode: Text.WordWrap; textFormat: Text.PlainText; font.bold: true }
        Controls.TextField {
            id: name
            objectName: "profileName"
            Layout.fillWidth: true
            maximumLength: 48
            placeholderText: qsTr("Nome do perfil")
            Accessible.name: qsTr("Nome do novo perfil")
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
        }
        Controls.Button {
            objectName: "profileCreate"
            Layout.fillWidth: true
            text: qsTr("Criar e usar")
            enabled: controls.profiles.writable && !controls.dirty && name.text.trim().length > 0
            onActiveFocusChanged: if (activeFocus) controls.reveal(this)
            onClicked: if (controls.profiles.create(name.text, controls.profiles.activeProfileId, controls.profiles.revision)) name.clear()
        }
        Controls.Label {
            objectName: "profileStatus"
            Layout.fillWidth: true
            visible: text.length > 0
            text: controls.dirty ? qsTr("Aplique ou cancele a prévia na aba Aparência antes de trocar ou criar um perfil.") : controls.profiles.error || controls.profiles.message
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            Accessible.role: Accessible.AlertMessage
        }
    }
}
