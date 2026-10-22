import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

// One module for both an uninstalled preview and an installed package.
Card {
    id: root
    property var packageData: ({})
    property bool preview: false
    property bool busy: false
    property bool providerAvailable: true
    property bool profilePeripheralVisible: true
    property string pendingAction: ""
    // Internal owner for this manager's focus lifetime, not a host/backend API.
    property var focusManager: null
    property int intentSerial: 0
    readonly property string addonId: String(packageData.id || "")
    readonly property string digest: String(packageData.sha256 || "")
    readonly property bool identityValid: addonId.length > 0 && addonId.length <= 120 && /^[a-f0-9]{64}$/.test(digest)
    readonly property bool valid: identityValid && packageData.valid !== false && packageData.state !== "invalid"
    readonly property bool active: packageData.enabled === true
    readonly property string suffix: preview ? "Preview" : "-" + addonId
    signal installRequested(string sha256)
    signal enableRequested(string addonId, string sha256)
    signal disableRequested(string addonId, string sha256)
    signal removeRequested(string addonId, string sha256)
    signal rollbackRequested(string addonId, string sha256)
    signal openOriginRequested(string origin)
    signal revealRequested(var control)
    signal focusObserved(var control)
    radius: Style.radius.module
    Accessible.role: Accessible.Grouping
    Accessible.name: bounded(packageData.name, 80)
    Accessible.ignored: false
    Keys.onEscapePressed: event => {
        if (pendingAction) { closeConfirmation(); event.accepted = true; }
        else event.accepted = false;
    }

    function bounded(value, limit) {
        return value === undefined || value === null ? "" : String(value).slice(0, limit);
    }
    function observe(control) {
        focusObserved(control);
        // Capture ownership in the manager before a hide/rehost can revoke it.
        // The manager defers the layout reveal under that original focus scope.
        revealRequested(control === confirm || control === cancel ? confirmationBody : control);
    }
    function observeInput(control, keyboard) {
        if (focusManager) focusManager.rememberInput(control, keyboard);
    }
    function transferScope(control) {
        if (!focusManager || !focusManager.currentControl(control)) return null;
        const scope = focusManager.focusScope();
        if (!focusManager.ownsScope(scope) || scope.control !== control) return null;
        scope.manager = focusManager;
        scope.cardParent = parent;
        scope.data = packageData;
        return scope;
    }
    function canTransfer(scope, target, closing) {
        return scope && scope.manager === focusManager && scope.manager.ownsScope(scope)
            && scope.manager.trackedFocus === scope.control
            && (scope.manager.currentControl(scope.control)
                || (closing && scope.manager.isAncestor(scope.window.activeFocusItem, scope.control)))
            && parent === scope.cardParent && packageData === scope.data
            && root.Window.window === scope.window && visible && enabled && target.visible && target.enabled
            && scope.manager.isAncestor(scope.manager, root)
            && scope.manager.isAncestor(root, scope.control) && scope.manager.isAncestor(root, target);
    }
    function revealExpanded() {
        if (visible && details.activeFocus)
            revealRequested(details.checked ? root : details);
    }
    function revealFocused() {
        if (!visible) return;
        if (details.activeFocus) revealExpanded();
        else if (confirm.activeFocus || cancel.activeFocus) revealRequested(confirmationBody);
    }
    function requestConfirmation(action, control) {
        const scope = transferScope(control);
        if (!scope) return;
        const intent = intentSerial + 1;
        intentSerial = intent;
        if (intentSerial !== intent || !canTransfer(scope, control)) return;
        const publishedIntent = intent + (pendingAction === action ? 0 : 1);
        pendingAction = action;
        Qt.callLater(function() {
            // Validate before assigning focus: its observation would otherwise
            // manufacture new ownership from a revoked confirmation intent.
            if (root.visible && root.enabled && root.intentSerial === publishedIntent
                    && root.pendingAction === action && root.canTransfer(scope, confirm)) {
                confirm.forceActiveFocus(Qt.TabFocusReason);
                Qt.callLater(root.revealFocused);
            }
        });
    }
    function closeConfirmation() {
        const scope = transferScope(confirm.activeFocus ? confirm : cancel);
        const target = pendingAction === "remove" ? remove : rollback;
        pendingAction = "";
        // Hiding the group can retain focus on its now-hidden child/ancestor.
        // Its original owned serial still distinguishes that from newer focus.
        if (pendingAction === "" && canTransfer(scope, target, true)) target.forceActiveFocus(Qt.TabFocusReason);
    }
    onPendingActionChanged: intentSerial++
    onParentChanged: if (focusManager) focusManager.invalidateCard(root)
    onEnabledChanged: if (!enabled && focusManager) focusManager.invalidateCard(root)
    onHeightChanged: Qt.callLater(revealFocused)
    onPackageDataChanged: {
        if (pendingAction) closeConfirmation();
    }
    onVisibleChanged: if (!visible) {
        pendingAction = "";
    }

    component ActionButton: OrlaButton {
        onPressed: root.observeInput(this)
        Keys.onReturnPressed: event => { if (enabled) { root.observeInput(this, true); clicked(); } event.accepted = true; }
        Keys.onEnterPressed: event => { if (enabled) { root.observeInput(this, true); clicked(); } event.accepted = true; }
        Keys.onPressed: event => {
            if (enabled && event.key === Qt.Key_Space) root.observeInput(this, true);
            event.accepted = false;
        }
    }

    component MetadataRow: FormRow {
        required property string metadataKey
        required property string caption
        required property string value
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.space.xs
            Controls.Label {
                Layout.fillWidth: true
                text: caption
                textFormat: Text.PlainText
                font.pixelSize: Style.type.caption
                color: root.palette.windowText
            }
            Controls.Label {
                objectName: "addonMetadata" + metadataKey + root.suffix
                color: root.palette.windowText
                Layout.fillWidth: true
                text: value || qsTr("Não informado")
                textFormat: Text.PlainText
                wrapMode: Text.Wrap
                font.pixelSize: Style.type.body
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: Style.space.sm
        Controls.Label {
            objectName: "addonName" + root.suffix
            color: root.palette.windowText
            Layout.fillWidth: true
            text: root.bounded(root.packageData.name, 80) || qsTr("Complemento sem nome")
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            font.pixelSize: Style.type.title
            font.weight: Style.weight.demiBold
        }
        Controls.Label {
            objectName: "addonStatus" + root.suffix
            Layout.fillWidth: true
            text: {
                if (root.preview) return root.valid && root.packageData.valid === true
                    ? qsTr("Prévia · Ainda não instalado") : qsTr("Arquivo inválido · Instalação indisponível");
                if (!root.valid) return qsTr("Pacote inválido · Ativação indisponível");
                if (!root.active) return qsTr("Instalado · Desativado");
                if (root.packageData.state === "missing") return qsTr("Ativado · Sem dados compartilhados");
                if (root.packageData.state === "stale") return qsTr("Ativado · Dados desatualizados");
                if (root.packageData.state === "unavailable") return qsTr("Ativado · Leitura indisponível");
                return qsTr("Ativado para leitura local");
            }
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: root.palette.windowText
            font.pixelSize: Style.type.label
        }
        Controls.Label {
            objectName: "addonDescription" + root.suffix
            color: root.palette.windowText
            Layout.fillWidth: true
            text: root.bounded(root.packageData.description, 240)
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            visible: text.length > 0
        }
        Controls.Label {
            objectName: root.preview ? "addonPreviewPermission" : "addonPermission" + root.suffix
            color: root.palette.windowText
            Layout.fillWidth: true
            visible: root.preview
            text: qsTr("Permissão: acesso somente leitura aos dados locais de bateria compartilhados pelo aplicativo. Instalar não ativa a leitura.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Controls.Label {
            objectName: "addonGuidance" + root.suffix
            color: root.palette.windowText
            Layout.fillWidth: true
            visible: !root.preview
            text: {
                if (!root.valid) return qsTr("Desative ou remova este pacote e adicione um arquivo válido do projeto.");
                if (!root.active && !root.providerAvailable)
                    return qsTr("Desative o outro complemento de bateria antes de ativar este.");
                if (root.active && !root.profilePeripheralVisible)
                    return qsTr("Para ver os dados no dock, mostre Periféricos neste perfil. O aplicativo de origem também precisa permitir o compartilhamento com o Orla.");
                if (root.active && root.packageData.state === "missing")
                    return qsTr("Abra o aplicativo de origem e permita o compartilhamento com o Orla. Essa permissão é separada da ativação aqui.");
                if (root.active && root.packageData.state === "stale")
                    return qsTr("Abra o aplicativo de origem para atualizar os dados. O Orla não inicia o aplicativo.");
                if (root.active && root.packageData.state === "unavailable")
                    return qsTr("Confira no aplicativo de origem se o compartilhamento com o Orla está permitido.");
                return root.active ? qsTr("A leitura também depende da permissão de compartilhamento no aplicativo e da opção Periféricos neste perfil.")
                    : qsTr("Ative para permitir a leitura. O aplicativo de origem também precisa permitir o compartilhamento com o Orla.");
            }
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        ActionButton {
            objectName: root.preview ? "addonPreviewInstall" : "addonInstall" + root.suffix
            Layout.fillWidth: true
            visible: root.preview
            text: qsTr("Instalar complemento")
            variant: "primary"
            enabled: !root.busy && root.valid && root.packageData.valid === true
            onClicked: root.installRequested(root.digest)
            onActiveFocusChanged: if (activeFocus) root.observe(this)
        }
        ActionButton {
            objectName: "addonEnable" + root.suffix
            Layout.fillWidth: true
            visible: !root.preview && !root.active
            text: qsTr("Ativar leitura")
            enabled: !root.busy && root.valid && root.providerAvailable
            onClicked: root.enableRequested(root.addonId, root.digest)
            onActiveFocusChanged: if (activeFocus) root.observe(this)
        }
        ActionButton {
            objectName: "addonDisable" + root.suffix
            Layout.fillWidth: true
            visible: !root.preview && root.active
            text: qsTr("Desativar leitura")
            enabled: !root.busy && root.identityValid
            onClicked: root.disableRequested(root.addonId, root.digest)
            onActiveFocusChanged: if (activeFocus) root.observe(this)
        }
        Controls.ToolButton {
            id: details
            objectName: "addonDetails" + root.suffix
            Layout.fillWidth: true
            text: checked ? qsTr("Ocultar detalhes") : qsTr("Sobre este complemento")
            icon.name: checked ? "arrow-down-symbolic" : "arrow-right-symbolic"
            icon.color: root.palette.windowText
            checkable: true
            Accessible.name: text
            onPressed: root.observeInput(this)
            Keys.onReturnPressed: event => { root.observeInput(this, true); toggle(); event.accepted = true; }
            Keys.onEnterPressed: event => { root.observeInput(this, true); toggle(); event.accepted = true; }
            Keys.onPressed: event => {
                if (enabled && event.key === Qt.Key_Space) root.observeInput(this, true);
                event.accepted = false;
            }
            onToggled: {
                if (!checked) root.pendingAction = "";
                Qt.callLater(root.revealExpanded);
            }
            onActiveFocusChanged: if (activeFocus) {
                root.focusObserved(this);
                Qt.callLater(root.revealExpanded);
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: -Style.space.xxs
                radius: Style.radius.control
                visible: details.visualFocus
                color: Style.alpha(root.palette.windowText, 0)
                border.width: Style.space.xxs
                border.color: root.palette.highlight
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            visible: details.checked
            spacing: 0
            MetadataRow { metadataKey: "Author"; caption: qsTr("Autoria declarada"); value: root.bounded(root.packageData.author, 120) }
            MetadataRow { metadataKey: "Version"; caption: qsTr("Versão"); value: root.bounded(root.packageData.version, 32) }
            MetadataRow { metadataKey: "License"; caption: qsTr("Licença declarada"); value: root.bounded(root.packageData.license, 80) }
            MetadataRow { metadataKey: "Origin"; caption: qsTr("Origem declarada"); value: root.bounded(root.packageData.origin, 512); last: true }
            Controls.Label {
                Layout.fillWidth: true
                Layout.topMargin: Style.space.sm
                color: root.palette.windowText
                text: qsTr("Autoria, licença e origem são informadas pelo pacote. O Orla não verifica a identidade de quem o publicou.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                font.pixelSize: Style.type.caption
            }
            ActionButton {
                objectName: "addonOrigin" + root.suffix
                Layout.fillWidth: true
                Layout.topMargin: Style.space.sm
                text: qsTr("Abrir origem declarada")
                variant: "ghost"
                enabled: !root.busy && /^https:\/\/[^\s]+$/.test(root.bounded(root.packageData.origin, 512))
                onClicked: root.openOriginRequested(root.bounded(root.packageData.origin, 512))
                onActiveFocusChanged: if (activeFocus) root.observe(this)
            }
            ActionButton {
                id: rollback
                objectName: "addonRollback" + root.suffix
                Layout.fillWidth: true
                visible: !root.preview && /^[a-f0-9]{64}$/.test(String(root.packageData.previousSha256 || ""))
                text: qsTr("Restaurar versão anterior…")
                enabled: !root.busy && root.identityValid
                onClicked: root.requestConfirmation("rollback", this)
                onActiveFocusChanged: if (activeFocus) root.observe(this)
            }
            ActionButton {
                id: remove
                objectName: "addonRemove" + root.suffix
                Layout.fillWidth: true
                visible: !root.preview
                text: qsTr("Remover complemento…")
                variant: "ghost"
                enabled: !root.busy && root.identityValid
                onClicked: root.requestConfirmation("remove", this)
                onActiveFocusChanged: if (activeFocus) root.observe(this)
            }
            ColumnLayout {
                id: confirmationBody
                objectName: "addonConfirmationGroup" + root.suffix
                Layout.fillWidth: true
                Layout.topMargin: Style.space.sm
                spacing: Style.space.sm
                visible: root.pendingAction.length > 0
                Controls.Label {
                    objectName: "addonConfirmation" + root.suffix
                    color: root.palette.windowText
                    Layout.fillWidth: true
                    text: root.pendingAction === "remove"
                        ? qsTr("Remover %1? A leitura será desativada. Suas preferências de perfil serão mantidas.").arg(root.bounded(root.packageData.name, 80))
                        : qsTr("Restaurar a versão anterior de %1? Isso desativa a leitura e não ativa a versão restaurada. Será preciso ativá-la novamente.").arg(root.bounded(root.packageData.name, 80))
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                }
                ActionButton {
                    id: confirm
                    objectName: "addonConfirm" + root.suffix
                    Layout.fillWidth: true
                    text: root.pendingAction === "remove" ? qsTr("Confirmar remoção") : qsTr("Confirmar restauração")
                    enabled: !root.busy && root.identityValid
                    onClicked: {
                        const action = root.pendingAction;
                        const addonId = root.addonId;
                        const digest = root.digest;
                        root.closeConfirmation();
                        if (action === "remove") root.removeRequested(addonId, digest);
                        else if (action === "rollback") root.rollbackRequested(addonId, digest);
                    }
                    onActiveFocusChanged: if (activeFocus) root.observe(this)
                }
                ActionButton {
                    id: cancel
                    objectName: "addonCancel" + root.suffix
                    Layout.fillWidth: true
                    text: qsTr("Cancelar")
                    variant: "ghost"
                    onClicked: root.closeConfirmation()
                    onActiveFocusChanged: if (activeFocus) root.observe(this)
                }
            }
        }
    }
}
