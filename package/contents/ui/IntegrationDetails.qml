import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

ColumnLayout {
    id: root
    required property var dock
    required property var integrations
    property string selected: "quota"
    readonly property string project: selected === "quota" ? "quotalantern" : selected === "peripherals" ? "perigauge" : "falatrace"
    spacing: 10

    Controls.Label {
        Layout.fillWidth: true
        text: root.integrations.error || (root.selected === "quota" ? qsTr("Leituras já coletadas pelo QuotaLantern. Cada janela é independente; custos não são percentuais de quota.")
            : root.selected === "peripherals" ? qsTr("Últimas leituras do PeriGauge. Estimativas e dados antigos são identificados.")
            : qsTr("Último estado salvo pelo FalaTrace. A atividade da captura não foi verificada. Abra o aplicativo para controlar a gravação."))
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        color: root.dock.muted
    }
    Controls.Label {
        Layout.fillWidth: true
        visible: root.selected === "quota" ? !(root.integrations.quota.windows || []).length
            : root.selected === "peripherals" ? !(root.integrations.peripherals.devices || []).length : true
        text: root.selected === "quota" ? qsTr("Sem quota recente. Abra o QuotaLantern para atualizar suas leituras.")
            : root.selected === "peripherals" ? qsTr("Sem bateria disponível. Abra o PeriGauge para coletar seus periféricos.")
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
            spacing: 12
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
                        Layout.fillWidth: true
                        text: modelData.stale ? qsTr("Leitura desatualizada")
                            : root.selected === "quota" ? (typeof modelData.usedPercent === "number" ? Math.round(modelData.usedPercent) + "% usado" : qsTr("Quota desconhecida"))
                            : (typeof modelData.percent === "number" ? Math.round(modelData.percent) + "%" + (modelData.estimated ? qsTr(" · estimativa") : "") : qsTr("Percentual desconhecido"))
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.dock.muted
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        visible: root.selected === "quota" && Boolean(modelData.resetAt || modelData.resetDescription)
                        text: modelData.resetAt ? qsTr("Reinicia: %1").arg(Qt.formatDateTime(new Date(modelData.resetAt), "d MMM, HH:mm")) : modelData.resetDescription || ""
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                        color: root.dock.muted
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
    RowLayout {
        Controls.Button { text: qsTr("Reler dados locais"); enabled: !root.integrations.loading; onClicked: root.integrations.refresh() }
        Controls.Button { text: qsTr("Projeto GitHub"); onClicked: Qt.openUrlExternally("https://github.com/caiolombello/" + root.project) }
    }
}
