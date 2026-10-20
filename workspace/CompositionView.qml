import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import QtQuick.Window
import "../package/contents/ui" as Orla
import "../package/contents/code/Style.js" as Style

Controls.Control {
    id: root
    objectName: "compositionView"
    required property var controller
    property string connector: ""
    property var selectedPanels: []
    readonly property var state: controller.state
    readonly property var review: controller.review
    readonly property bool reviewing: !!review.token
    readonly property string phase: state.phase || "UNKNOWN"
    readonly property bool available: !controller.busy && !controller.closePending
    readonly property bool liveInventory: state.shellRunning === true && !!state.inventory && !state.verificationUnavailable
    readonly property bool canCompose: phase === "UNMANAGED" || phase === "RESTORED"
    readonly property bool interrupted: !!state.recordPresent && !canCompose && phase !== "COMMITTED" && phase !== "DISABLED" && phase !== "UNKNOWN"
    readonly property var ui: Style.scheme(Style.schemeFor(palette.window))
    padding: Style.space.md
    leftPadding: padding
    rightPadding: padding
    topPadding: padding
    bottomPadding: padding
    focusPolicy: Qt.StrongFocus
    Accessible.name: qsTr("Composição Orla")

    function titleFor(action) {
        if (action === "apply") return qsTr("Ativar dock + barra");
        if (action === "disable") return qsTr("Usar só o dock");
        if (action === "recover") return qsTr("Recuperar composição");
        return qsTr("Restaurar layout original");
    }
    function phaseText() {
        if (controller.busy) return controller.stage === "execute" ? qsTr("Aplicando mudanças…") : qsTr("Verificando composição…");
        if (state.verificationUnavailable) return qsTr("Operação registrada; atualize a leitura");
        if (state.shellRunning === false) return qsTr("Plasma está parado");
        if (phase === "COMMITTED") return qsTr("Composição Orla registrada");
        if (phase === "DISABLED") return qsTr("Barra Orla desativada");
        if (interrupted) return qsTr("Recuperação necessária");
        if (canCompose) return qsTr("Seu dock, com a barra que você escolher");
        return qsTr("Verifique seu layout para continuar");
    }
    function panels() {
        const info = state.inventory;
        if (!info || !info.selectedScreen) return [];
        return info.panels.filter(panel => panel.screen === info.selectedScreen.id);
    }
    function hasDock(panel) {
        return panel.widgets.some(widget => widget.type === "org.caiodock.dock");
    }
    function widgets(panel) {
        const names = {"org.kde.plasma.systemtray": qsTr("Bandeja do sistema"),
            "org.kde.plasma.digitalclock": qsTr("Relógio"), "org.kde.plasma.icontasks": qsTr("Aplicativos fixados"),
            "org.kde.plasma.taskmanager": qsTr("Janelas abertas"), "org.kde.plasma.kickoff": qsTr("Menu de aplicativos"),
            "org.kde.plasma.appmenu": qsTr("Menu do aplicativo"), "org.kde.plasma.panelspacer": qsTr("Espaço flexível"),
            "org.orla.bar": qsTr("Menu Orla"), "org.caiodock.dock": qsTr("Orla Dock")};
        return panel.widgets.map(widget => (names[widget.type] || widget.type) + " · " + widget.id).join("\n");
    }
    function choose(id, checked) {
        controller.discard();
        selectedPanels = checked ? selectedPanels.concat([id]) : selectedPanels.filter(value => value !== id);
    }
    function moduleName(key) {
        const names = {"menu": qsTr("Menu Orla"), "global-menu": qsTr("Menu do aplicativo"),
            "spacer": qsTr("Espaço flexível"), "tray": qsTr("Bandeja do sistema"), "clock": qsTr("Relógio")};
        return names[key] || key;
    }
    function revealFocused() {
        const host = root.Window.window;
        const control = host ? host.activeFocusItem : null;
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
    onHeightChanged: Qt.callLater(revealFocused)
    Connections {
        target: root.Window.window
        function onActiveFocusItemChanged() { Qt.callLater(root.revealFocused); }
    }
    Connections {
        target: root.controller
        function onChanged() {
            if (root.connector && root.controller.connectors.indexOf(root.connector) < 0) {
                root.connector = "";
                root.selectedPanels = [];
            }
        }
    }
    Keys.onEscapePressed: event => {
        if (root.reviewing && root.available) { root.controller.discard(); event.accepted = true; }
        else event.accepted = false;
    }

    component Copy: Controls.Label {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
        maximumLineCount: 12
        elide: Text.ElideRight
    }
    component FocusRing: Rectangle {
        anchors.fill: parent
        radius: Style.radius.control
        color: "transparent"
        border.width: 2
        border.color: root.palette.highlight
        visible: parent.activeFocus
    }

    contentItem: ColumnLayout {
        spacing: Style.space.lg
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.space.xs
            RowLayout {
                Layout.fillWidth: true
                spacing: Style.space.sm
                Copy { text: qsTr("Composição Orla"); font.pixelSize: Style.type.headline; font.weight: Style.weight.demiBold }
                Orla.OrlaButton {
                    objectName: "compositionRefresh"
                    visible: !root.reviewing
                    enabled: root.available
                    variant: "ghost"
                    Layout.preferredHeight: Style.size.iconButton
                    text: qsTr("Atualizar")
                    Accessible.name: qsTr("Atualizar leitura do layout")
                    onClicked: { root.selectedPanels = []; root.controller.refresh(root.connector); }
                }
            }
            Copy { objectName: "compositionStatus"; text: root.phaseText(); color: root.ui.textMuted }
        }
        Controls.ScrollView {
            id: scroll
            objectName: "compositionScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            padding: Style.space.xs
            Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
            onAvailableHeightChanged: Qt.callLater(root.revealFocused)
            onContentHeightChanged: Qt.callLater(root.revealFocused)
            ColumnLayout {
                id: body
                onHeightChanged: Qt.callLater(root.revealFocused)
                width: scroll.availableWidth - scroll.effectiveScrollBarWidth
                spacing: Style.space.lg
                Copy {
                    visible: !!root.controller.problem
                    objectName: "compositionProblem"
                    text: root.controller.problem
                    color: root.ui.danger
                }
                Copy {
                    visible: root.controller.closePending
                    text: qsTr("A janela fechará quando a operação terminar. Aguarde para preservar a recuperação.")
                }
                Copy {
                    visible: !!root.state.verificationUnavailable
                    text: qsTr("A transação terminou, mas a leitura final não está disponível. Atualize antes de continuar.")
                }
                Copy {
                    visible: root.state.shellRunning === false
                    text: qsTr("Inicie a sessão Plasma escolhida e atualize a leitura. Uma recuperação interrompida pode ser revisada mesmo com o Plasma parado.")
                }
                Orla.Card {
                    Layout.fillWidth: true
                    visible: !root.reviewing
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.md
                        Copy { text: qsTr("Dock e barra, à sua maneira"); font.weight: Style.weight.demiBold }
                        Copy { text: qsTr("A dock é independente. A barra superior reúne Menu Orla, menus do aplicativo, bandeja e relógio."); color: root.ui.textMuted }
                        Copy {
                            visible: root.phase === "DISABLED"
                            text: qsTr("Para ativar a barra novamente, restaure o layout original e prepare uma nova composição.")
                        }
                        Copy {
                            visible: root.interrupted
                            text: qsTr("A recuperação segue o registro da operação interrompida. Ela pode restaurar a barra anterior, em vez do layout original.")
                        }
                        Orla.OrlaButton {
                            objectName: "compositionRestore"
                            Layout.fillWidth: true
                            visible: root.phase === "COMMITTED" || root.phase === "DISABLED"
                            enabled: root.available && root.liveInventory
                            text: qsTr("Restaurar layout original…")
                            onClicked: root.controller.prepareOperation("restore")
                        }
                    }
                }
                Orla.Card {
                    visible: root.canCompose && !root.reviewing
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.md
                        Copy { text: qsTr("Onde usar a barra"); font.weight: Style.weight.demiBold }
                        Controls.ComboBox {
                            id: monitor
                            objectName: "compositionMonitor"
                            Layout.fillWidth: true
                            model: root.controller.connectors
                            currentIndex: root.connector ? root.controller.connectors.indexOf(root.connector) : -1
                            displayText: currentIndex < 0 ? qsTr("Escolher monitor…") : currentText
                            enabled: root.available
                            Accessible.name: qsTr("Monitor da barra")
                            onActivated: index => {
                                root.connector = root.controller.connectors[index];
                                root.selectedPanels = [];
                                root.controller.refresh(root.connector);
                            }
                            FocusRing {}
                        }
                        Copy { text: qsTr("Selecione os painéis que serão substituídos. A dock e os painéis não selecionados serão mantidos."); color: root.ui.textMuted }
                        Copy {
                            visible: !!root.connector && root.panels().length === 0
                            text: qsTr("Nenhum painel disponível neste monitor. Escolha outro monitor. Esta versão precisa de um painel existente para substituir.")
                        }
                        Repeater {
                            model: root.panels()
                            ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: Style.space.xs
                                Controls.CheckBox {
                                    objectName: "compositionPanel" + modelData.id
                                    Layout.fillWidth: true
                                    enabled: root.available && !root.hasDock(modelData)
                                    checked: root.selectedPanels.indexOf(modelData.id) >= 0
                                    text: qsTr("Painel %1 · monitor %2").arg(modelData.id).arg(root.connector)
                                    onToggled: root.choose(modelData.id, checked)
                                    FocusRing {}
                                }
                                Copy { text: root.hasDock(modelData) ? qsTr("Contém a dock; será mantido.") : root.widgets(modelData); color: root.ui.textMuted; wrapMode: Text.WrapAnywhere }
                            }
                        }
                        Copy { text: qsTr("Os widgets da nova barra usam as configurações padrão. Os painéis originais ficam guardados para restauração."); color: root.ui.textMuted }
                    }
                }
                Orla.Card {
                    visible: root.reviewing
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Style.space.md
                        Copy { text: root.titleFor(root.review.action); font.pixelSize: Style.type.title; font.weight: Style.weight.demiBold }
                        Copy { text: qsTr("Monitor: %1").arg(root.review.connector || "") }
                        Copy {
                            visible: root.review.action === "apply"
                            text: qsTr("Criar barra superior de %1 px com: %2.").arg(root.review.height || "").arg((root.review.modules || []).map(root.moduleName).join(", "))
                        }
                        Copy {
                            visible: root.review.action === "apply"
                            text: qsTr("Substituir painéis: %1").arg((root.review.replacePanelIds || []).join(", "))
                        }
                        Repeater {
                            model: root.review.selectedPanels || []
                            Copy { required property var modelData; text: root.widgets(modelData); color: root.ui.textMuted; wrapMode: Text.WrapAnywhere }
                        }
                        Copy {
                            text: root.review.action === "apply" ? qsTr("A dock e os demais painéis serão mantidos. Os widgets da nova barra usarão as configurações padrão do Orla.")
                                : root.review.action === "disable" ? qsTr("Remover apenas a barra Orla. Os painéis substituídos não serão recriados agora; o backup original será mantido.")
                                : root.review.action === "recover" ? qsTr("Recuperar o estado registrado antes da operação interrompida. O destino depende do registro e será verificado pelo gerenciador.")
                                : qsTr("Restaurar os arquivos do layout original guardado antes da composição. Alterações posteriores podem impedir a restauração.")
                        }
                        Copy { text: qsTr("O Plasma será reiniciado durante a operação. Fechar esta janela aguardará o término."); color: root.ui.textMuted }
                    }
                }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.space.sm
            Orla.OrlaButton {
                objectName: "compositionConfirm"
                Layout.fillWidth: true
                visible: root.reviewing
                enabled: root.available
                variant: "primary"
                text: root.titleFor(root.review.action)
                onClicked: root.controller.confirm()
            }
            Orla.OrlaButton {
                objectName: "compositionBack"
                Layout.fillWidth: true
                visible: root.reviewing
                enabled: root.available
                text: qsTr("Voltar sem alterar")
                onClicked: root.controller.discard()
            }
            Orla.OrlaButton {
                objectName: "compositionPrepare"
                Layout.fillWidth: true
                visible: !root.reviewing && root.canCompose
                enabled: root.available && root.liveInventory && !!root.connector && root.selectedPanels.length > 0
                variant: "primary"
                text: qsTr("Revisar dock + barra")
                onClicked: root.controller.prepareApply(root.connector, root.selectedPanels)
            }
            Orla.OrlaButton {
                objectName: "compositionDisable"
                Layout.fillWidth: true
                visible: !root.reviewing && root.phase === "COMMITTED"
                enabled: root.available && root.liveInventory
                text: qsTr("Usar só o dock…")
                onClicked: root.controller.prepareOperation("disable")
            }
            Orla.OrlaButton {
                objectName: "compositionRecover"
                Layout.fillWidth: true
                visible: !root.reviewing && root.interrupted
                enabled: root.available
                variant: "primary"
                text: qsTr("Revisar recuperação…")
                onClicked: root.controller.prepareOperation("recover")
            }
        }
    }
}
