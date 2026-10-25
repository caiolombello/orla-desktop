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
    // Batteries always, and quota once an active addon replaced the legacy cache.
    readonly property bool addonRoute: selected === "peripherals"
        || (selected === "quota" && integrations.quotaAddonActive === true)
    readonly property bool reloadRequired: addonRoute && addonsSession !== null && addonsSession.reloadRequired === true
    // Shared quota is grouped by provider, as in QuotaLantern's tray; the legacy cache keeps its list.
    readonly property bool groupedQuota: selected === "quota" && addonRoute
        && Array.isArray(integrations.quota.providers) && integrations.quota.providers.length > 0
    // The integrations' own clock, so countdowns and data age agree (tests pin it).
    function clock() {
        return integrations.nowMsOverride !== undefined && integrations.nowMsOverride >= 0 ? integrations.nowMsOverride : Date.now();
    }
    property double nowMs: clock()
    spacing: Style.space.md

    Timer {
        // Reset countdowns move by the minute while the details are shown.
        interval: 30000
        repeat: true
        running: root.visible && root.groupedQuota
        triggeredOnStart: true
        onTriggered: root.nowMs = root.clock()
    }

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
        text: root.integrations.errorFor(root.selected) || (root.selected === "quota" ? (root.addonRoute
                ? qsTr("Uso de quota compartilhado por um aplicativo externo. Cada janela é independente; custos não fazem parte do compartilhamento.")
                : qsTr("Leituras já coletadas pelo QuotaLantern. Cada janela é independente; custos não são percentuais de quota."))
            : root.selected === "peripherals" ? qsTr("Baterias compartilhadas por um aplicativo externo. Estimativas e dados antigos são identificados.")
            : qsTr("Último estado salvo pelo FalaTrace. A atividade da captura não foi verificada. Abra o aplicativo para controlar a gravação."))
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        color: root.dock.muted
    }
    Controls.Label {
        objectName: root.selected === "quota" ? "quotaMetadata" : "peripheralsMetadata"
        Layout.fillWidth: true
        visible: root.addonRoute && text.length > 0
        text: (root.selected === "quota" ? root.integrations.quotaMetadataSummary : root.integrations.peripheralsMetadataSummary) || ""
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
        text: {
            if (root.selected === "recording") return root.integrations.recordingSummary;
            if (!root.addonRoute) return qsTr("Sem quota recente. Abra o QuotaLantern para atualizar suas leituras.");
            const status = root.selected === "quota" ? root.integrations.quota.status : root.integrations.peripherals.status;
            return status === "missing" ? qsTr("Sem dados compartilhados. Confira a ativação do complemento e a permissão no aplicativo de origem.")
                : status === "invalid" ? qsTr("Os dados compartilhados são inválidos.")
                : status === "stale" ? qsTr("Dados desatualizados. Aguarde uma nova coleta no aplicativo de origem.")
                : root.selected === "quota" ? qsTr("Sem quota disponível.") : qsTr("Sem bateria externa disponível.");
        }
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
        color: root.dock.foreground
    }
    Controls.ScrollView {
        objectName: "quotaUsageScroll"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(quotaUsage.implicitHeight, 460)
        visible: root.groupedQuota
        clip: true
        contentWidth: availableWidth
        Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
        QuotaUsage {
            id: quotaUsage
            objectName: "quotaUsage"
            width: parent.width
            providers: root.groupedQuota ? root.integrations.quota.providers : []
            nowMs: root.nowMs
            foreground: root.dock.foreground
            muted: root.dock.muted
        }
    }
    Controls.ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: root.selected === "recording" || root.groupedQuota ? 0 : Math.min(entries.implicitHeight, 230)
        visible: root.selected !== "recording" && !root.groupedQuota
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
                        text: modelData.resetAt ? qsTr("Reinicia: %1").arg(new Date(modelData.resetAt).toLocaleString(Qt.locale(), "d MMM, HH:mm")) : modelData.resetDescription || ""
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
            text: root.reloadRequired ? qsTr("Recarregar complementos") : qsTr("Reler cache local")
            enabled: !(root.addonRoute ? root.integrations.addonLoading : root.integrations.legacyLoading)
                && !(root.addonRoute && root.addonsSession && root.addonsSession.busy)
            onClicked: {
                if (root.reloadRequired) root.addonsSession.reload();
                else root.integrations.refresh();
            }
        }
        OrlaButton {
            objectName: "legacyProjectLink"
            Layout.fillWidth: true
            visible: !root.addonRoute
            text: qsTr("Projeto GitHub")
            onClicked: Qt.openUrlExternally("https://github.com/caiolombello/" + root.project)
        }
        Controls.Label {
            objectName: "addonReloadGuidance"
            Layout.fillWidth: true
            visible: root.reloadRequired
            text: root.addonsSession ? root.addonsSession.feedback : ""
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.dock.muted
        }
    }
}
