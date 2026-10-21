import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import "../package/contents/ui" as Orla
import "../package/contents/code/Style.js" as Style

Controls.ApplicationWindow {
    id: window
    objectName: "updatesWindow"
    width: 580
    height: 720
    minimumWidth: 320
    minimumHeight: 240
    visible: true
    title: qsTr("Sobre e atualizações")
    property var controller: updatesController
    property string schemeOverride: ""
    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
    readonly property var ui: Style.scheme(schemeOverride || Style.schemeFor(systemPalette.window))
    readonly property var state: controller.state
    color: ui.canvas
    palette.window: ui.surface
    palette.base: ui.raised
    palette.mid: ui.border
    palette.windowText: ui.text
    palette.text: ui.text
    palette.buttonText: ui.text
    palette.button: ui.raised
    palette.highlight: ui.accent
    palette.highlightedText: ui.onAccent
    Connections {
        target: controller
        function onCloseReady() { window.close(); }
        function onChanged() { Qt.callLater(window.revealFocused); }
    }
    Shortcut {
        sequence: "Escape"
        enabled: !channel.popup.visible
        onActivated: window.close()
    }
    onActiveFocusItemChanged: Qt.callLater(revealFocused)
    onHeightChanged: Qt.callLater(revealFocused)
    function revealFocused() {
        const control = window.activeFocusItem;
        let current = control;
        while (current && current !== body) current = current.parent;
        if (!current || !control.visible) return;
        const top = control.mapToItem(body, 0, 0).y - Style.space.sm;
        const bottom = top + control.height + Style.space.lg;
        let next = scroll.contentItem.contentY;
        if (top < next || bottom - top > scroll.availableHeight) next = top;
        else if (bottom > next + scroll.availableHeight) next = bottom - scroll.availableHeight;
        scroll.contentItem.contentY = Math.max(0, Math.min(next, Math.max(0, body.height - scroll.availableHeight)));
    }
    onClosing: event => { event.accepted = controller.requestClose(); }

    function statusText() {
        if (controller.closePending && controller.busy) return qsTr("Fechando após a consulta…");
        if (!window.state.version) return qsTr("Referência de versão indisponível");
        if (controller.busy) return qsTr("Consultando releases oficiais…");
        const result = window.state.record.result || {};
        if (window.state.historical && result.status) return qsTr("Resultado salvo de %1 · %2").arg(window.displayDate(window.state.record.completedAt || window.state.record.attemptedAt)).arg(resultText(result));
        return resultText(result);
    }
    function resultText(result) {
        if (result.status === "update_available") return qsTr("Há uma release mais recente: %1").arg(result.available_version);
        if (result.status === "up_to_date") return qsTr("Nenhuma release mais recente que a referência %1 neste canal").arg(window.state.version);
        if (result.status === "no_release") return qsTr("Nenhuma release elegível neste canal");
        if (result.status === "rate_limited") return qsTr("Limite de consultas atingido. Tente novamente mais tarde.");
        if (result.status === "unavailable") return qsTr("Não foi possível consultar agora");
        return qsTr("Ainda não consultado");
    }

    function reasonText() {
        const result = window.state.record.result || {};
        if (result.reason === "timeout") return qsTr("A consulta excedeu o tempo limite. Tente novamente.");
        if (result.reason === "network_error") return qsTr("Rede indisponível. Tente novamente quando houver conexão.");
        if (result.status === "unavailable") return qsTr("A consulta não produziu um resultado válido. Você pode tentar novamente.");
        return "";
    }
    function displayDate(value) {
        return new Date(value).toLocaleString(Qt.locale(), Locale.ShortFormat);
    }
    function datesText() {
        let text = window.state.record.attemptedAt ? qsTr("Última tentativa: %1").arg(window.displayDate(window.state.record.attemptedAt)) : "";
        if (window.state.lastCompleted.completedAt) text += "\n" + qsTr("Última consulta concluída: %1").arg(window.displayDate(window.state.lastCompleted.completedAt));
        return text ? text + "\n" + qsTr("Horários locais.") : "";
    }

    component Copy: Controls.Label {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        maximumLineCount: 24
        elide: Text.ElideRight
    }
    Controls.ScrollView {
        id: scroll
        objectName: "updatesScroll"
        anchors.fill: parent
        anchors.margins: Style.space.md
        clip: true
        contentItem.objectName: "updatesViewport"
        Accessible.name: qsTr("Conteúdo de atualizações")
        contentWidth: availableWidth
        Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
        ColumnLayout {
            id: body
            width: scroll.availableWidth
            spacing: Style.space.lg
            onHeightChanged: Qt.callLater(window.revealFocused)
            Copy { text: qsTr("Sobre e atualizações"); font.pixelSize: Style.type.headline; font.weight: Style.weight.bold }
            Copy { text: qsTr("Consulte as releases oficiais do Orla. A consulta não instala atualizações.") }
            Orla.Card {
                Layout.fillWidth: true
                radius: Style.radius.module
                Accessible.role: Accessible.Grouping
                Accessible.name: qsTr("Referência da consulta")
                contentItem: ColumnLayout {
                    spacing: Style.space.sm
                    Copy { text: qsTr("Referência da consulta"); color: window.ui.textMuted }
                    Copy {
                        objectName: "updatesReference"
                        text: window.state.version || qsTr("Referência de versão indisponível")
                        font.pixelSize: Style.type.headline
                        font.weight: Style.weight.bold
                    }
                    Copy {
                        objectName: "updatesReferenceOrigin"
                        visible: !!window.state.version
                        text: window.state.role === "source" ? qsTr("pacote fonte do dock") : qsTr("esta cópia do Workspace · bundle verificado")
                        color: window.ui.textMuted
                    }
                }
            }
            Orla.Card {
                Layout.fillWidth: true
                radius: Style.radius.module
                contentItem: ColumnLayout {
                    spacing: Style.space.md
                    Orla.OrlaButton {
                        id: check
                        objectName: "updatesCheck"
                        Layout.fillWidth: true
                        implicitHeight: Math.max(Style.size.target, implicitContentHeight + verticalPadding * 2)
                        text: qsTr("Consultar agora")
                        variant: "primary"
                        enabled: controller.canCheck
                        onClicked: controller.check()
                        Keys.onReturnPressed: event => { if (!event.isAutoRepeat) clicked(); event.accepted = true; }
                        Keys.onEnterPressed: event => { if (!event.isAutoRepeat) clicked(); event.accepted = true; }
                        Component.onCompleted: if (enabled) forceActiveFocus(Qt.TabFocusReason)
                    }
                    Copy {
                        objectName: "updatesStatus"
                        text: window.statusText()
                    }
                    Copy { text: window.reasonText(); visible: text.length > 0; color: window.ui.textMuted }
                    Copy { objectName: "updatesDates"; text: window.datesText(); visible: text.length > 0; color: window.ui.textMuted }
                    Copy {
                        objectName: "updatesHistory"
                        readonly property var previous: window.state.lastCompleted.result || {}
                        text: previous.status ? qsTr("Histórico salvo: %1 · %2").arg(window.displayDate(window.state.lastCompleted.completedAt)).arg(window.resultText(previous)) : ""
                        visible: !!previous.status && (controller.busy || (window.state.record.result || {}).status === "unavailable" || (window.state.record.result || {}).status === "rate_limited")
                        color: window.ui.textMuted
                    }
                    Copy { text: qsTr("Informação antiga: consulte novamente para obter um resultado atual."); visible: !!window.state.old; color: window.ui.textMuted }
                    Copy { text: qsTr("Horário não confiável. O registro permanece apenas como histórico."); visible: !!window.state.timeUnreliable; color: window.ui.textMuted }
                    Copy { text: qsTr("Não foi possível restaurar ou salvar o histórico e a preferência locais."); visible: !!window.state.storageWarning; color: window.ui.textMuted }
                    Copy { text: qsTr("Abra esta ferramenta em uma cópia completa e válida do Orla para consultar."); visible: !window.state.version; color: window.ui.textMuted }
                    Copy { text: qsTr("Canal"); Accessible.ignored: true }
                    Controls.ComboBox {
                        id: channel
                        objectName: "updatesChannel"
                        Layout.fillWidth: true
                        model: [qsTr("Estável"), qsTr("Beta")]
                        currentIndex: controller.channel === "beta" ? 1 : 0
                        enabled: !controller.busy && !controller.closePending
                        Accessible.name: qsTr("Canal de releases")
                        onActivated: controller.selectChannel(currentIndex === 1 ? "beta" : "stable")
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: -3
                            color: "transparent"
                            radius: Style.radius.control
                            visible: channel.activeFocus
                            border.width: 2
                            border.color: window.ui.focus
                        }
                    }
                    Copy { text: qsTr("Estável exclui pré-releases. Beta também inclui pré-releases."); color: window.ui.textMuted }
                }
            }
            Orla.OrlaButton {
                id: details
                objectName: "updatesDetails"
                Layout.fillWidth: true
                Layout.leftMargin: Style.space.xs
                Layout.rightMargin: Style.space.xs
                text: checked ? qsTr("Ocultar informações dos componentes") : qsTr("Sobre os componentes")
                checkable: true
                onToggled: Qt.callLater(window.revealFocused)
            }
            ColumnLayout {
                Layout.fillWidth: true
                visible: details.checked
                spacing: Style.space.sm
                Copy {
                    objectName: "updatesComponentVersions"
                    text: qsTr("Dock instalada: não verificada") + "\n" + qsTr("Dock em execução: não verificada")
                }
                Copy {
                    objectName: "updatesComponentScope"
                    text: qsTr("Esta consulta compara a referência acima. Não confirma a versão carregada no Plasma.")
                    color: window.ui.textMuted
                }
                Copy {
                    text: qsTr("Dock, Menu Orla, Launcher e Workspace são componentes distintos. Esta referência não comprova suas versões instaladas ou em execução. Uma release da família não garante arquivos compatíveis para cada componente. Histórico e hashes não autenticam o publicador.")
                    color: window.ui.textMuted
                }
                Copy {
                    objectName: "updatesCanonicalDates"
                    text: (window.state.record.attemptedAt ? qsTr("Início da tentativa (UTC): %1").arg(window.state.record.attemptedAt) : "")
                        + (window.state.record.completedAt ? "\n" + qsTr("Registro da conclusão (UTC): %1").arg(window.state.record.completedAt) : "")
                        + (window.state.lastCompleted.completedAt ? "\n" + qsTr("Última consulta concluída (UTC): %1").arg(window.state.lastCompleted.completedAt) : "")
                    visible: text.length > 0
                    color: window.ui.textMuted
                }
            }
            Orla.OrlaButton {
                id: release
                objectName: "updatesRelease"
                Layout.fillWidth: true
                Layout.leftMargin: Style.space.xs
                Layout.rightMargin: Style.space.xs
                text: qsTr("Ver release no GitHub…")
                visible: !!window.state.releaseUrl
                enabled: !controller.busy && !controller.closePending
                Accessible.description: qsTr("Solicita a abertura no navegador externo")
                onClicked: controller.openRelease()
                onVisibleChanged: if (!visible && activeFocus) check.forceActiveFocus(Qt.TabFocusReason)
            }
            Copy { text: qsTr("Não foi possível solicitar a abertura do navegador."); visible: !!window.state.openingFailed }
            Item { Layout.fillWidth: true; implicitHeight: Style.space.sm }
        }
    }
}
