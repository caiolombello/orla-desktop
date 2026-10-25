import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style
import "../code/QuotaView.js" as QuotaView

// Shared quota, laid out like QuotaLantern's tray: the bottleneck ring first,
// then providers grouped as at the limit, active, without a recent reading and
// not connected, each with its windows, a bar and the time until it resets.
ColumnLayout {
    id: root
    required property var providers
    property double nowMs: Date.now()
    property color foreground: palette.windowText
    property color muted: palette.windowText
    readonly property var view: QuotaView.group(providers)
    spacing: Style.space.sm

    function windowName(window) {
        const names = {primary: qsTr("Sessão"), secondary: qsTr("Semana"), tertiary: qsTr("Extra")};
        const length = QuotaView.span(window.minutes);
        const suffix = !length ? "" : length.days ? qsTr("%1 d").arg(length.days)
            : length.hours ? qsTr("%1 h").arg(length.hours) : qsTr("%1 min").arg(length.minutes);
        return (names[window.key] || window.key) + (suffix ? " · " + suffix : "");
    }
    function resetText(window) {
        const left = QuotaView.remaining(window.resetAtMs, nowMs);
        if (!left) return "";
        if (left.total === 0) return qsTr("zerando");
        if (left.days > 0) return left.hours > 0 ? qsTr("zera em %1 d %2 h").arg(left.days).arg(left.hours)
                                                 : qsTr("zera em %1 d").arg(left.days);
        if (left.hours > 0) return left.minutes > 0 ? qsTr("zera em %1 h %2 min").arg(left.hours).arg(left.minutes)
                                                    : qsTr("zera em %1 h").arg(left.hours);
        return qsTr("zera em %1 min").arg(left.minutes);
    }
    function sectionTitle(key) {
        return key === "limit" ? qsTr("No limite") : key === "active" ? qsTr("Ativos")
            : key === "stale" ? qsTr("Sem leitura recente") : qsTr("Não conectados");
    }
    function stateText(provider) {
        const top = QuotaView.worst(provider);
        if (top) return Math.round(top.usedPercent) + "%";
        return QuotaView.section(provider) === "offline" ? qsTr("não conectado") : qsTr("sem leitura recente");
    }

    // The bottleneck, as the tray icon's ring shows it.
    RowLayout {
        objectName: "quotaBottleneck"
        Layout.fillWidth: true
        visible: root.view.bottleneck !== null
        spacing: Style.space.md
        Item {
            Layout.preferredWidth: Style.size.target + Style.space.lg
            Layout.preferredHeight: Style.size.target + Style.space.lg
            ProgressRing {
                anchors.fill: parent
                lineWidth: Style.space.xs + Style.space.xxs
                progress: root.view.bottleneck ? root.view.bottleneck.window.usedPercent / 100 : 0
                color: root.view.bottleneck ? QuotaView.color(root.view.bottleneck.window.usedPercent) : root.muted
                trackColor: Style.alpha(root.foreground, 0.12)
                animationDuration: 0
            }
            Controls.Label {
                anchors.centerIn: parent
                text: root.view.bottleneck ? Math.round(root.view.bottleneck.window.usedPercent) + "%" : ""
                textFormat: Text.PlainText
                font.pixelSize: Style.type.label
                font.weight: Style.weight.bold
                font.features: {"tnum": 1}
                color: root.foreground
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Controls.Label {
                Layout.fillWidth: true
                text: qsTr("Mais usado")
                textFormat: Text.PlainText
                font.pixelSize: Style.type.caption
                color: root.muted
            }
            Controls.Label {
                objectName: "quotaBottleneckName"
                Layout.fillWidth: true
                text: root.view.bottleneck ? root.view.bottleneck.provider.name + " · " + root.windowName(root.view.bottleneck.window) : ""
                textFormat: Text.PlainText
                elide: Text.ElideRight
                font.weight: Style.weight.demiBold
                color: root.foreground
            }
            Controls.Label {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.view.bottleneck ? root.resetText(root.view.bottleneck.window) : ""
                textFormat: Text.PlainText
                font.pixelSize: Style.type.caption
                color: root.muted
            }
        }
    }

    Repeater {
        model: root.view.sections
        delegate: ColumnLayout {
            id: sectionBlock
            required property var modelData
            Layout.fillWidth: true
            spacing: Style.space.xs
            SectionLabel {
                objectName: "quotaSection"
                Layout.fillWidth: true
                Layout.topMargin: Style.space.xs
                text: root.sectionTitle(sectionBlock.modelData.key) + " · " + sectionBlock.modelData.providers.length
            }
            Repeater {
                model: sectionBlock.modelData.providers
                delegate: Card {
                    id: providerCard
                    required property var modelData
                    readonly property var heaviest: QuotaView.worst(modelData)
                    objectName: "quotaProvider"
                    Layout.fillWidth: true
                    radius: Style.radius.module
                    padding: Style.space.sm
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.xs
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Style.space.sm
                            // Level shown by color and by the percent beside it.
                            Rectangle {
                                Layout.preferredWidth: Style.space.sm
                                Layout.preferredHeight: Style.space.sm
                                radius: width / 2
                                color: providerCard.heaviest ? QuotaView.color(providerCard.heaviest.usedPercent) : Style.alpha(root.foreground, 0.3)
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                text: providerCard.modelData.name
                                textFormat: Text.PlainText
                                elide: Text.ElideRight
                                font.weight: Style.weight.demiBold
                                color: root.foreground
                            }
                            Controls.Label {
                                objectName: "quotaProviderState"
                                text: root.stateText(providerCard.modelData)
                                textFormat: Text.PlainText
                                font.weight: providerCard.heaviest ? Style.weight.bold : Style.weight.regular
                                font.pixelSize: providerCard.heaviest ? Style.type.body : Style.type.caption
                                font.features: {"tnum": 1}
                                color: providerCard.heaviest ? root.foreground : root.muted
                            }
                        }
                        Repeater {
                            model: providerCard.modelData.windows.filter(window => QuotaView.finite(window.usedPercent))
                            delegate: ColumnLayout {
                                id: windowRow
                                required property var modelData
                                objectName: "quotaWindow"
                                Layout.fillWidth: true
                                spacing: Style.space.xxs
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Style.space.sm
                                    Controls.Label {
                                        Layout.fillWidth: true
                                        text: root.windowName(windowRow.modelData)
                                        textFormat: Text.PlainText
                                        elide: Text.ElideRight
                                        font.pixelSize: Style.type.caption
                                        color: root.muted
                                    }
                                    Controls.Label {
                                        text: Math.round(windowRow.modelData.usedPercent) + "%"
                                            + (root.resetText(windowRow.modelData) ? " · " + root.resetText(windowRow.modelData) : "")
                                        textFormat: Text.PlainText
                                        font.pixelSize: Style.type.caption
                                        font.features: {"tnum": 1}
                                        color: root.muted
                                    }
                                }
                                // A capsule bar, like the block bar in the tray menu.
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Style.space.xs + Style.space.xxs
                                    radius: height / 2
                                    color: Style.alpha(root.foreground, 0.12)
                                    Rectangle {
                                        width: parent.width * Math.max(0, Math.min(1, windowRow.modelData.usedPercent / 100))
                                        height: parent.height
                                        radius: height / 2
                                        color: QuotaView.color(windowRow.modelData.usedPercent)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
