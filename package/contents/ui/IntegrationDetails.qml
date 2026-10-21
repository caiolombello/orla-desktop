import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

ColumnLayout {
    id: root
    required property var dock
    required property var integrations
    property string selected: "quota"
    property var addonsSession: null
    readonly property string project: selected === "quota" ? "quotalantern" : "falatrace"
    spacing: Style.space.md

    function stateText(modelData) {
        if (root.selected === "peripherals" && modelData.present === false) return qsTr("Fora de alcance");
        if (modelData.stale) return qsTr("Leitura desatualizada");
        if (root.selected === "quota") return typeof modelData.usedPercent === "number"
            ? Math.round(modelData.usedPercent) + "% usado" : qsTr("Quota desconhecida");
        const levels = {critical: qsTr("Nível crítico"), low: qsTr("Nível baixo"), good: qsTr("Nível bom"), full: qsTr("Bateria cheia")};
        const reading = typeof modelData.percent === "number" ? Math.round(modelData.percent) + "%"
            : levels[modelData.level] || qsTr("Percentual desconhecido");
        return reading + (modelData.estimated ? qsTr(" · estimativa") : "")
            + (modelData.charging === "charging" ? qsTr(" · carregando") : modelData.charging === "full" ? qsTr(" · carga completa") : "");
    }

    Controls.Label {
        objectName: "integrationDescription"
        Layout.fillWidth: true
        text: root.integrations.errorFor(root.selected) || (root.selected === "quota" ? qsTr("Leituras já coletadas pelo QuotaLantern. Cada janela é independente; custos não são percentuais de quota.")
            : root.selected === "peripherals" ? qsTr("Baterias compartilhadas por um aplicativo externo. Estimativas e dados antigos são identificados.")
            : qsTr("Último estado salvo pelo FalaTrace. A atividade da captura não foi verificada. Abra o aplicativo para controlar a gravação."))
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        color: root.dock.muted
    }
    Controls.Label {
        objectName: "peripheralsMetadata"
        Layout.fillWidth: true
        visible: root.selected === "peripherals" && text.length > 0
        text: root.integrations.peripheralsMetadataSummary || ""
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: root.dock.muted
        font.pixelSize: Style.type.caption
    }
    Controls.Label {
        objectName: "integrationEmptyState"
        Layout.fillWidth: true
        visible: root.selected === "quota" ? !(root.integrations.quota.windows || []).length
            : root.selected === "peripherals" ? !(root.integrations.peripherals.devices || []).length : true
        text: root.selected === "quota" ? qsTr("Sem quota recente. Abra o QuotaLantern para atualizar suas leituras.")
            : root.selected === "peripherals" ? (root.integrations.peripherals.status === "missing"
                ? qsTr("Sem dados compartilhados. Confira a ativação do complemento e a permissão no aplicativo de origem.") : root.integrations.peripherals.status === "invalid"
                ? qsTr("Os dados compartilhados são inválidos.") : root.integrations.peripherals.status === "stale"
                ? qsTr("Dados desatualizados. Aguarde uma nova coleta no aplicativo de origem.") : qsTr("Sem bateria externa disponível."))
            : root.integrations.recordingSummary
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: root.dock.foreground
    }
    Controls.ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: root.selected === "recording" ? 0 : Math.min(entries.implicitHeight, 230)
        visible: root.selected !== "recording"
        clip: true
        ColumnLayout {
            id: entries
            width: parent.width
            spacing: Style.space.md
            Repeater {
                model: root.selected === "quota" ? root.integrations.quota.windows || [] : root.integrations.peripherals.devices || []
                delegate: ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Controls.Label {
                        Layout.fillWidth: true
                        text: root.selected === "quota" ? modelData.provider + " · " + modelData.label : modelData.name
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        font.bold: true
                        color: root.dock.foreground
                    }
                    Controls.Label {
                        objectName: root.selected === "peripherals" ? "peripheralStateText" : "quotaStateText"
                        Layout.fillWidth: true
                        text: root.stateText(modelData)
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.dock.muted
                    }
                    Repeater {
                        model: root.selected === "peripherals" ? modelData.components || [] : []
                        delegate: Controls.Label {
                            required property var modelData
                            objectName: "peripheralComponent"
                            Layout.fillWidth: true
                            text: {
                                const labels = {left: qsTr("Esquerdo"), right: qsTr("Direito"), case: qsTr("Estojo")};
                                return labels[modelData.label] + " · " + root.stateText(modelData);
                            }
                            textFormat: Text.PlainText
                            wrapMode: Text.WordWrap
                            color: root.dock.muted
                        }
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        visible: root.selected === "quota" && Boolean(modelData.resetAt || modelData.resetDescription)
                        text: modelData.resetAt ? qsTr("Reinicia: %1").arg(Qt.formatDateTime(new Date(modelData.resetAt), "d MMM, HH:mm")) : modelData.resetDescription || ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.dock.muted
                        font.pixelSize: Style.type.caption
                    }
                }
            }
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        OrlaButton {
            objectName: "refreshCacheButton"
            Layout.fillWidth: true
            text: root.selected === "peripherals" && root.addonsSession && root.addonsSession.reloadRequired
                ? qsTr("Recarregar complementos") : qsTr("Reler cache local")
            enabled: !(root.selected === "peripherals" ? root.integrations.addonLoading : root.integrations.legacyLoading)
                && !(root.addonsSession && root.selected === "peripherals" && root.addonsSession.busy)
            onClicked: {
                if (root.selected === "peripherals" && root.addonsSession && root.addonsSession.reloadRequired) root.addonsSession.reload();
                else root.integrations.refresh();
            }
        }
        OrlaButton {
            objectName: "legacyProjectLink"
            Layout.fillWidth: true
            visible: root.selected !== "peripherals"
            text: qsTr("Projeto GitHub")
            onClicked: Qt.openUrlExternally("https://github.com/caiolombello/" + root.project)
        }
        Controls.Label {
            objectName: "addonReloadGuidance"
            Layout.fillWidth: true
            visible: root.selected === "peripherals" && root.addonsSession !== null && root.addonsSession.reloadRequired
            text: root.addonsSession ? root.addonsSession.feedback : ""
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.dock.muted
        }
    }
}
