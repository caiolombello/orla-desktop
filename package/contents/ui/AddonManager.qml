import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

// Presentation only. The owner validates data and handles every request.
Controls.Control {
    id: root
    property var dock: null
    property var scheme: dock && dock.popupScheme ? dock.popupScheme : Style.scheme("dark")
    property var addons: []
    property var preview: null
    property bool busy: false
    property bool loading: false
    property string feedback: ""
    property string feedbackKind: "status"
    property bool profilePeripheralVisible: true
    property bool profileQuotaVisible: true
    property var trackedFocus: null
    property bool focusOwned: false
    property int focusSerial: 0
    property var pendingRecovery: null
    property var revealTarget: null
    property bool keyboardFocus: false
    property var gatedFocus: null
    // Captured JS state remains safe after Loader retires the QML context.
    property var callbackLifetime: ({alive: true})
    readonly property var focusWindow: root.Window.window
    signal chooseFileRequested()
    signal installRequested(string sha256)
    signal enableRequested(string addonId, string sha256)
    signal disableRequested(string addonId, string sha256)
    signal removeRequested(string addonId, string sha256)
    signal rollbackRequested(string addonId, string sha256)
    signal openOriginRequested(string origin)
    signal revealRequested(var control)
    // Reads and changes clear the rows until the host answers. Holding the last
    // settled height stops the settings scroll from snapping upward; the hold ends
    // when the answer has been laid out, or shortly after if nothing moved.
    property real settledHeight: 0
    property bool holdingHeight: false
    implicitHeight: holdingHeight ? Math.max(contentItem.implicitHeight, settledHeight) : contentItem.implicitHeight
    function waitChanged() {
        if (loading || busy) { holdingHeight = true; heightRelease.stop(); }
        else if (holdingHeight) heightRelease.restart();
    }
    function contentResized() {
        if (loading || busy) return;
        heightRelease.stop();
        holdingHeight = false;
        settledHeight = contentItem.implicitHeight;
    }
    Connections { target: root.contentItem; function onImplicitHeightChanged() { root.contentResized(); } }
    Timer { id: heightRelease; interval: Style.motion.fast; onTriggered: root.contentResized() }
    padding: 0
    palette.window: scheme.surface
    palette.base: scheme.raised
    palette.windowText: scheme.text
    palette.text: scheme.text
    palette.buttonText: scheme.text
    palette.button: scheme.raised
    palette.mid: scheme.border
    palette.highlight: scheme.accent
    palette.highlightedText: scheme.onAccent
    function findControl(item, name) {
        if (item.objectName === name) return item;
        for (let i = 0; i < item.children.length; ++i) {
            const found = findControl(item.children[i], name);
            if (found) return found;
        }
        return null;
    }
    function isAncestor(item, child) {
        for (let parent = child; parent; parent = parent.parent) {
            if (parent === item) return true;
        }
        return false;
    }
    function currentControl(control) {
        return visible && enabled && control && control.visible && control.enabled
            && isAncestor(root, control) && focusWindow && focusWindow.active
            && focusWindow.activeFocusItem === control && control.activeFocus;
    }
    function rememberFocus(control, inputIntent) {
        if (!currentControl(control)) return;
        // Qt's retained OtherFocusReason notification never authorizes a new
        // lifetime. A still-owned gated action keeps its original scope/ring.
        if (!inputIntent && control.focusReason === Qt.OtherFocusReason) {
            if (focusOwned && trackedFocus === control) scheduleFocusedReveal();
            return;
        }
        const scope = focusScope();
        scope.serial++;
        invalidateFocus();
        if (!sameLifetime(scope) || !currentControl(control)) return;
        trackedFocus = control;
        if (!sameLifetime(scope) || !currentControl(control)) return;
        keyboardFocus = control.visualFocus;
        if (!sameLifetime(scope) || !currentControl(control)) return;
        focusOwned = true;
        return ownsScope(scope) && trackedFocus === control ? scope : null;
    }
    function rememberInput(control, keyboard) {
        const scope = rememberFocus(control, true);
        if (!ownsScope(scope) || trackedFocus !== control || !currentControl(control)) return;
        if (keyboard) control.focusReason = Qt.TabFocusReason;
        if (ownsScope(scope) && trackedFocus === control) scheduleFocusedReveal();
    }
    function invalidateFocus() {
        // Every property notification can synchronously acquire a newer scope.
        const serial = focusSerial + 1;
        focusSerial = serial;
        if (focusSerial !== serial) return;
        focusOwned = false;
        if (focusSerial !== serial) return;
        pendingRecovery = null;
        if (focusSerial !== serial) return;
        gatedFocus = null;
        if (focusSerial !== serial) return;
        revealTarget = null;
    }
    function invalidateCard(card) {
        if (isAncestor(card, trackedFocus)) invalidateFocus();
    }
    function focusScope() {
        return {window: focusWindow, surface: parent, owner: dock, serial: focusSerial,
            control: trackedFocus};
    }
    function sameLifetime(scope) {
        return scope && visible && enabled && focusSerial === scope.serial
            && focusWindow === scope.window && parent === scope.surface && dock === scope.owner
            && scope.window && scope.window.active;
    }
    function ownsScope(scope) { return focusOwned && sameLifetime(scope); }
    function scheduleReveal(target) {
        const lifetime = callbackLifetime;
        const scope = focusScope();
        if (!ownsScope(scope) || !target || !isAncestor(root, target)
                || !isAncestor(target, scope.control)) return;
        revealTarget = target;
        if (!lifetime.alive) return;
        Qt.callLater(function() {
            if (!lifetime.alive) return;
            const control = scope.control;
            if (root.ownsScope(scope) && control && root.trackedFocus === control
                    && scope.window.activeFocusItem === control
                    && control.visible && control.enabled && target.visible
                    && root.isAncestor(root, target) && root.isAncestor(target, control))
                root.revealRequested(target);
        });
    }
    function scheduleFocusedReveal() {
        const control = trackedFocus;
        // A disclosure/confirmation can request its whole containing group.
        const target = revealTarget || (control && !control.checkable ? control : null);
        scheduleReveal(target);
    }
    function gateChanged() {
        const lifetime = callbackLifetime;
        if (busy || loading) {
            if (!gatedFocus && focusOwned && trackedFocus && keyboardFocus)
                gatedFocus = focusScope();
        } else {
            const scope = gatedFocus;
            Qt.callLater(function() {
                if (!lifetime.alive) return;
                if (root.gatedFocus !== scope || root.busy || root.loading) return;
                root.gatedFocus = null;
                if (!lifetime.alive) return;
                // Qt clears the focus reason while a retained button is disabled.
                // Restore only that same keyboard action, never pointer/newer focus.
                if (root.ownsScope(scope) && root.trackedFocus === scope.control
                        && scope.window.activeFocusItem === scope.control
                        && root.isAncestor(root, scope.control) && scope.control.visible
                        && scope.control.enabled && !scope.control.visualFocus)
                    scope.control.focusReason = Qt.TabFocusReason;
            });
            scheduleFocusedReveal();
        }
        if (!lifetime.alive) return;
        if (pendingRecovery) Qt.callLater(attemptRecovery);
    }
    Connections {
        target: root.trackedFocus
        ignoreUnknownSignals: true
        // Layout positions children after the manager's own height notification.
        function onYChanged() { root.scheduleFocusedReveal(); }
        function onHeightChanged() { root.scheduleFocusedReveal(); }
        function onWidthChanged() { root.scheduleFocusedReveal(); }
        function onFocusReasonChanged() {
            if (!root.busy && !root.loading && root.trackedFocus.activeFocus) {
                root.keyboardFocus = root.trackedFocus.visualFocus;
                if (root.trackedFocus.focusReason === Qt.MouseFocusReason)
                    root.gatedFocus = null;
            }
        }
    }
    Connections {
        target: root.focusWindow
        function onActiveFocusItemChanged() {
            const current = root.focusWindow.activeFocusItem;
            // Hiding a child can focus its retained card. Keep that old ownership
            // until a genuine visible control or another window takes over.
            if (root.focusOwned && current && current.visible && current.enabled
                    && current !== root.trackedFocus && !root.isAncestor(current, root.trackedFocus)) {
                root.invalidateFocus();
            }
        }
        function onActiveChanged() {
            if (!root.focusWindow.active) root.invalidateFocus();
        }
    }
    function recoverAfterChange() {
        if (!focusOwned) return;
        if (!pendingRecovery) {
            if (!trackedFocus) return;
            const scope = focusScope();
            scope.name = trackedFocus.objectName;
            scope.visual = trackedFocus.visualFocus === true;
            pendingRecovery = scope;
        }
        Qt.callLater(attemptRecovery);
    }
    function attemptRecovery() {
        const pending = pendingRecovery;
        if (!pending) return;
        if (!ownsScope(pending)) {
            pendingRecovery = null;
            return;
        }
        const current = pending.window.activeFocusItem;
        // Preserve surviving/newer visible focus, not the old card's fallback.
        if (current && current.visible && current.enabled && !isAncestor(current, root)
                && (current === trackedFocus || !isAncestor(current, trackedFocus))) {
            pendingRecovery = null;
            scheduleFocusedReveal();
            return;
        }
        // Projection and gate completion may arrive in separate event turns.
        if (busy || loading) return;
        // Toggling reading swaps the card's action; focus follows it to the same card.
        const toggled = /^addon(Enable|Disable)-/.test(pending.name)
            ? findControl(root, pending.name.replace(/^addon(Enable|Disable)-/,
                (_, kind) => kind === "Enable" ? "addonDisable-" : "addonEnable-")) : null;
        const usable = item => item && item.visible && item.enabled ? item : null;
        const replacement = usable(findControl(root, pending.name)) || usable(toggled) || chooseFile;
        if (replacement.visible && replacement.enabled) {
            pendingRecovery = null;
            // Clearing the observable token can revoke ownership or publish a
            // newer request. Recheck before the focus assignment itself.
            // Keep the last input: a pointer action must not light the keyboard ring.
            // OtherFocusReason would not be tracked, so pointer focus stays MouseFocusReason.
            if (ownsScope(pending) && !pendingRecovery && replacement.visible && replacement.enabled)
                replacement.forceActiveFocus(pending.visual === false ? Qt.MouseFocusReason : Qt.TabFocusReason);
        }
    }
    onAddonsChanged: recoverAfterChange()
    onPreviewChanged: recoverAfterChange()
    onBusyChanged: { waitChanged(); gateChanged(); }
    onLoadingChanged: { waitChanged(); gateChanged(); }
    onVisibleChanged: if (!visible) invalidateFocus()
    onEnabledChanged: if (!enabled) invalidateFocus()
    onParentChanged: invalidateFocus()
    onFocusWindowChanged: invalidateFocus()
    onDockChanged: invalidateFocus()
    onHeightChanged: scheduleFocusedReveal()
    onWidthChanged: scheduleFocusedReveal()
    Component.onDestruction: callbackLifetime.alive = false
    contentItem: ColumnLayout {
        spacing: Style.space.md
        SectionLabel { text: qsTr("Complementos"); color: root.scheme.text }
        Controls.Label {
            color: root.palette.windowText
            Layout.fillWidth: true
            text: qsTr("Bateria de periféricos e uso de quota de IA, a partir de dados locais compartilhados por outro aplicativo.")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        AddonPackageCard {
            objectName: "addonPreview"
            Layout.fillWidth: true
            visible: !!root.preview
            preview: true
            focusManager: root
            packageData: root.preview || ({})
            busy: root.busy || root.loading
            onInstallRequested: function(sha256) { root.installRequested(sha256); }
            onOpenOriginRequested: function(origin) { root.openOriginRequested(origin); }
            onRevealRequested: function(control) { root.scheduleReveal(control); }
            onFocusObserved: function(control) { root.rememberFocus(control); }
        }
        OrlaButton {
            id: chooseFile
            objectName: "addonChooseFile"
            Layout.fillWidth: true
            text: qsTr("Adicionar arquivo…")
            variant: root.preview ? "secondary" : "primary"
            enabled: !root.busy && !root.loading
            Keys.onReturnPressed: event => { if (enabled) { root.rememberInput(this, true); clicked(); } event.accepted = true; }
            Keys.onEnterPressed: event => { if (enabled) { root.rememberInput(this, true); clicked(); } event.accepted = true; }
            Keys.onPressed: event => {
                if (enabled && event.key === Qt.Key_Space) root.rememberInput(this, true);
                event.accepted = false;
            }
            onPressed: root.rememberInput(this, false)
            onClicked: root.chooseFileRequested()
            onActiveFocusChanged: if (activeFocus) {
                root.rememberFocus(this);
                root.scheduleFocusedReveal();
            }
        }
        Controls.Label {
            objectName: "addonProgress"
            color: root.palette.windowText
            Layout.fillWidth: true
            visible: root.loading || root.busy
            text: root.loading ? qsTr("Lendo complementos…") : qsTr("Aplicando alteração…")
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
        }
        Card {
            Layout.fillWidth: true
            radius: Style.radius.module
            visible: root.feedback.length > 0
            contentItem: ColumnLayout {
                spacing: Style.space.xs
                Controls.Label {
                    Layout.fillWidth: true
                    visible: root.feedbackKind === "error"
                    text: qsTr("Não foi possível concluir")
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                    font.weight: Style.weight.demiBold
                    color: root.scheme.danger
                }
                Controls.Label {
                    objectName: "addonFeedback"
                    color: root.palette.windowText
                    Layout.fillWidth: true
                    text: root.feedback.slice(0, 300)
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                }
            }
        }
        Card {
            objectName: "addonEmpty"
            Layout.fillWidth: true
            visible: !root.loading && root.addons.length === 0 && !root.preview
            radius: Style.radius.module
            contentItem: Controls.Label {
                color: root.palette.windowText
                text: qsTr("Nenhum complemento instalado. Adicione o arquivo fornecido pelo projeto do aplicativo.")
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
        }
        SectionLabel {
            color: root.scheme.text
            visible: root.addons.length > 0
            text: qsTr("Instalados")
        }
        Repeater {
            model: root.addons.slice(0, 32)
            AddonPackageCard {
                required property var modelData
                Layout.fillWidth: true
                objectName: "addonCard-" + addonId
                packageData: modelData
                focusManager: root
                busy: root.busy || root.loading
                profilePeripheralVisible: root.profilePeripheralVisible
                profileQuotaVisible: root.profileQuotaVisible
                // One active addon per module: a battery addon never blocks a quota one.
                providerAvailable: !root.addons.some(function(row) {
                    return row.enabled === true && row.id !== modelData.id && row.renderer === modelData.renderer; })
                onEnableRequested: function(addonId, sha256) { root.enableRequested(addonId, sha256); }
                onDisableRequested: function(addonId, sha256) { root.disableRequested(addonId, sha256); }
                onRemoveRequested: function(addonId, sha256) { root.removeRequested(addonId, sha256); }
                onRollbackRequested: function(addonId, sha256) { root.rollbackRequested(addonId, sha256); }
                onOpenOriginRequested: function(origin) { root.openOriginRequested(origin); }
                onRevealRequested: function(control) { root.scheduleReveal(control); }
                onFocusObserved: function(control) { root.rememberFocus(control); }
            }
        }
    }
}
