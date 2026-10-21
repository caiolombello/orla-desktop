import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

ColumnLayout {
    id: root
    property string widgetId: ""
    property bool shown: false
    property var integrations: null
    readonly property bool known: ["quota", "peripherals", "recording"].indexOf(widgetId) >= 0
    readonly property string project: widgetId === "quota" ? "QuotaLantern"
        : widgetId === "peripherals" ? qsTr("Bateria de periféricos") : widgetId === "recording" ? "FalaTrace" : ""
    readonly property var reading: known && integrations ? integrations[widgetId] : null
    readonly property string statusText: {
        if (!known) return "";
        if (!shown) return qsTr("Desativado neste perfil");
        if (!integrations || integrations.errorFor(widgetId)) return qsTr("Integração indisponível");
        if (widgetId === "peripherals" ? integrations.addonLoading : integrations.legacyLoading) return qsTr("Relendo cache local…");
        if (!reading) return qsTr("Sem estado disponível");
        if (reading.status === "missing") return qsTr("Sem cache local");
        if (reading.status === "invalid") return qsTr("Cache local inválido");
        if (reading.status === "stale") return qsTr("Dados desatualizados");
        if (widgetId === "recording") return integrations.recordingSummary || qsTr("Sem estado disponível");
        return reading.status === "ready" ? qsTr("Leitura disponível") : qsTr("Sem leitura confirmada");
    }
    signal revealRequested(var control)
    visible: known
    spacing: Style.space.sm
    onVisibleChanged: if (!visible) disclosure.checked = false
    onWidgetIdChanged: disclosure.checked = false
    // Expansion and wrapping can settle after the first deferred call.
    onHeightChanged: if (disclosure.checked) Qt.callLater(revealExpanded)
    function revealExpanded() {
        if (visible && disclosure.activeFocus)
            revealRequested(disclosure.checked ? root : disclosure);
    }

    Controls.ToolButton {
        id: disclosure
        objectName: "moduleDisclosure"
        Layout.fillWidth: true
        text: qsTr("Sobre %1").arg(root.project)
        icon.name: checked ? "arrow-down-symbolic" : "arrow-right-symbolic"
        checkable: true
        Accessible.name: text
        onToggled: Qt.callLater(root.revealExpanded)
        onActiveFocusChanged: if (activeFocus) Qt.callLater(root.revealExpanded)
    }
    ColumnLayout {
        visible: disclosure.checked
        Layout.fillWidth: true
        Layout.leftMargin: Style.space.md
        Layout.rightMargin: Style.space.md
        Layout.bottomMargin: Style.space.md
        spacing: Style.space.sm
        Controls.Label {
            Layout.fillWidth: true
            text: root.widgetId === "peripherals" ? qsTr("Complemento externo · Experimental") : qsTr("Adaptador local incluído · Experimental")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            font.pixelSize: Style.type.caption
        }
        Controls.Label {
            objectName: "moduleDescription"
            Layout.fillWidth: true
            text: root.widgetId === "quota" ? qsTr("Acompanhe quotas de IA a partir do cache do QuotaLantern.")
                : root.widgetId === "peripherals" ? qsTr("Veja baterias compartilhadas localmente por um aplicativo externo.")
                : qsTr("Consulte o último estado salvo pelo FalaTrace. A captura ao vivo não é verificada.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Controls.Label {
            objectName: "moduleStatus"
            Layout.fillWidth: true
            text: root.statusText
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            font.weight: Style.weight.demiBold
        }
        Controls.Label {
            objectName: "moduleRequirements"
            Layout.fillWidth: true
            text: root.widgetId === "peripherals"
                ? qsTr("Mostrar neste perfil, ativar o complemento e permitir o compartilhamento no aplicativo são escolhas separadas. Adicionar um arquivo não ativa a leitura.")
                : qsTr("Requer o aplicativo e a ponte local atualizada. Só os módulos ativados neste perfil têm seus caches lidos pela dock.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            font.pixelSize: Style.type.caption
        }
    }
}
