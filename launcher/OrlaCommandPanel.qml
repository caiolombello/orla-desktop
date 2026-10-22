import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "Style.js" as Style
import "AddonPeripherals.js" as Peripherals

// Result of one explicit Orla command. The reply is validated by the dock's
// own parser (a synced copy); nothing here starts collection or changes state.
Item {
    id: panel
    // The launcher is a dark overlay in every system scheme.
    readonly property var ui: Style.scheme("dark")
    objectName: "orlaCommandPanel"
    implicitWidth: 0
    implicitHeight: 0
    clip: true
    required property var controller
    property bool operationStartBlocked: false
    // Evaluated once per reply with the time it arrived.
    property var reading: null
    property string replyError: ""
    signal backRequested()
    function focusFirst() { backButton.forceActiveFocus() }
    function evaluate() {
        reading = null
        replyError = ""
        if (!controller || controller.status !== "ready") return
        const decoded = Peripherals.decode(controller.reply)
        if (decoded.error) { replyError = decoded.error; return }
        try { reading = Peripherals.current(decoded.value, Date.now()) }
        catch (_) { replyError = "invalid_response" }
    }
    function deviceName(device) {
        const labels = {mouse: qsTr("Mouse"), keyboard: qsTr("Teclado"), earbuds: qsTr("Fones de ouvido"),
            headset: qsTr("Headset"), touchpad: qsTr("Touchpad"), gamepad: qsTr("Controle"), other: qsTr("Periférico")}
        return labels[device.kind] + device.name.slice(device.kind.length)
    }
    function stateText(entry) {
        if (entry.present === false) return qsTr("Fora de alcance")
        if (entry.stale) return qsTr("Leitura desatualizada")
        const levels = {critical: qsTr("Nível crítico"), low: qsTr("Nível baixo"), good: qsTr("Nível bom"), full: qsTr("Bateria cheia")}
        const value = typeof entry.percent === "number" ? Math.round(entry.percent) + "%"
            : levels[entry.level] || qsTr("Percentual desconhecido")
        return value + (entry.estimated ? qsTr(" · estimativa") : "")
            + (entry.charging === "charging" ? qsTr(" · carregando") : entry.charging === "full" ? qsTr(" · carga completa") : "")
    }
    function summary() {
        if (!controller) return ""
        if (controller.status === "reading") return qsTr("Lendo a última bateria compartilhada…")
        if (controller.status === "error")
            return controller.errorCode === "timeout" ? qsTr("O serviço de complementos não respondeu a tempo.")
                : controller.errorCode === "invalid_response" ? qsTr("A resposta do serviço de complementos é inválida.")
                : qsTr("O serviço de complementos está indisponível.")
        if (replyError === "invalid_response") return qsTr("A resposta do serviço de complementos é inválida.")
        if (replyError.length > 0) return qsTr("O serviço de complementos recusou a leitura. Tente novamente.")
        if (!reading) return ""
        switch (reading.addon.reason) {
        case "not_installed": return qsTr("Nenhum complemento de bateria instalado. Adicione o arquivo em Personalizar Orla Dock → Widgets.")
        case "disabled": return qsTr("O complemento está instalado, mas a leitura está desativada.")
        case "profile_hidden": return qsTr("A leitura está oculta pelo perfil atual.")
        case "export_missing": return qsTr("Sem dados compartilhados. Confira a ativação do complemento e a permissão no aplicativo de origem.")
        case "export_invalid": return qsTr("Os dados compartilhados são inválidos.")
        case "ready": return qsTr("Baterias compartilhadas pelo aplicativo de origem.")
        case "unknown": return qsTr("Sem percentual conhecido no momento.")
        default: return qsTr("Dados desatualizados. Aguarde uma nova coleta no aplicativo de origem.")
        }
    }
    Connections {
        target: panel.controller
        function onChanged() { panel.evaluate() }
    }
    Component.onCompleted: evaluate()

    ScrollView {
        id: panelScroll
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            x: Style.space.xs
            width: panelScroll.width - panelScroll.effectiveScrollBarWidth - Style.space.sm
            spacing: Style.space.md
            Item { Layout.preferredHeight: Style.space.xs }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    id: backButton
                    objectName: "commandBackButton"
                    text: qsTr("← Busca")
                    Accessible.name: qsTr("Voltar à busca local")
                    KeyNavigation.priority: KeyNavigation.BeforeItem
                    KeyNavigation.tab: rereadButton
                    KeyNavigation.backtab: rereadButton
                    onClicked: panel.backRequested()
                    contentItem: Text { text: parent.text; color: ui.accent; font.pixelSize: Style.type.label; textFormat: Text.PlainText }
                    background: Rectangle { radius: Style.radius.control; color: ui.surface; border.width: parent.activeFocus ? 2 : 0; border.color: ui.accent }
                }
                Item { Layout.fillWidth: true }
                Text { text: qsTr("LEITURA PASSIVA"); color: ui.textMuted; font.pixelSize: Style.type.overline; font.letterSpacing: Style.letterSpacing.overline; textFormat: Text.PlainText }
            }
            Text {
                Layout.fillWidth: true; text: panel.controller ? panel.controller.title : ""; color: ui.text
                font.pixelSize: Style.type.headline; font.weight: Font.DemiBold; textFormat: Text.PlainText; elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: ui.textMuted; font.pixelSize: Style.type.label; textFormat: Text.PlainText
                text: qsTr("A mesma leitura que a dock usa, vinda do complemento ativado. O Orla não inicia coleta nem altera o complemento.")
            }
            Text {
                objectName: "commandStatus"
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: ui.text; font.pixelSize: Style.type.body; textFormat: Text.PlainText
                maximumLineCount: 6; elide: Text.ElideRight
                text: panel.summary()
            }
            Repeater {
                model: panel.reading ? panel.reading.devices : []
                delegate: ColumnLayout {
                    id: device
                    required property var modelData
                    objectName: "commandDevice"
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        Layout.fillWidth: true; text: panel.deviceName(device.modelData); color: ui.text
                        font.pixelSize: Style.type.title; font.weight: Font.DemiBold; textFormat: Text.PlainText; elide: Text.ElideRight
                    }
                    Text {
                        objectName: "commandDeviceState"
                        Layout.fillWidth: true; text: panel.stateText(device.modelData); color: ui.textMuted
                        font.pixelSize: Style.type.label; textFormat: Text.PlainText; wrapMode: Text.Wrap
                    }
                    Repeater {
                        model: device.modelData.components || []
                        delegate: Text {
                            required property var modelData
                            Layout.fillWidth: true; color: ui.textMuted; font.pixelSize: Style.type.label; textFormat: Text.PlainText; wrapMode: Text.Wrap
                            text: ({left: qsTr("Esquerdo"), right: qsTr("Direito"), case: qsTr("Estojo")})[modelData.label] + " · " + panel.stateText(modelData)
                        }
                    }
                }
            }
            Text {
                objectName: "commandSharedAt"
                Layout.fillWidth: true; wrapMode: Text.Wrap; color: ui.textMuted; font.pixelSize: Style.type.caption; textFormat: Text.PlainText
                visible: !!panel.reading && panel.reading.source === "addon"
                text: visible ? qsTr("Compartilhado às %1 pelo aplicativo de origem.")
                    .arg(new Date(panel.reading.generatedAtMs).toLocaleTimeString(Qt.locale(), Locale.ShortFormat)) : ""
            }
            Button {
                id: rereadButton
                objectName: "commandRereadButton"
                Layout.fillWidth: true; Layout.preferredHeight: Style.size.target
                enabled: !!panel.controller && !panel.controller.busy && !panel.operationStartBlocked && panel.controller.commandId.length > 0
                KeyNavigation.priority: KeyNavigation.BeforeItem
                KeyNavigation.tab: backButton
                KeyNavigation.backtab: backButton
                text: panel.controller && panel.controller.busy ? qsTr("Lendo…") : qsTr("Ler novamente")
                onClicked: if (!panel.operationStartBlocked) panel.controller.read(panel.controller.commandId)
                contentItem: Text { text: parent.text; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; color: parent.enabled ? ui.text : ui.textMuted; font.pixelSize: Style.type.label; font.weight: Font.DemiBold; textFormat: Text.PlainText }
                background: Rectangle { radius: Style.radius.control; color: ui.raised; border.width: parent.activeFocus ? 2 : 0; border.color: ui.accent }
            }
            Item { Layout.preferredHeight: Style.space.xs }
        }
    }
}
