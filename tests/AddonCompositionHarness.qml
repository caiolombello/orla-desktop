import QtQuick
import QtQuick.Controls as Controls
import "../package/contents/ui" as UI

Controls.ApplicationWindow {
    id: harness
    width: 350
    height: 360
    visible: true
    property bool surfaceOpen: false
    property string scope: "profile-a"
    property var token: null
    property var calls: []
    property var data: dataState
    property var manager: session.manager
    property var coordinator: session
    property var surfaceOwner: harness
    property string reenter: ""
    property int resumeLeaks: 0
    QtObject {
        id: fake
        function asyncCall(message, resolve, reject) {
            harness.calls = harness.calls.concat([{message: message, resolve: resolve, reject: reject}]);
        }
    }
    UI.IntegrationState {
        id: dataState
        active: true
        enabledModules: ["peripherals"]
        transport: fake
        nowMsOverride: 100000
    }
    UI.AddonsSession {
        id: session
        dataState: dataState
        surfaceActive: harness.surfaceOpen
        owner: harness.surfaceOwner
        scopeKey: harness.scope
        transport: fake
    }
    Connections {
        target: dataState
        function onAddonIdentityChanged() {
            if (harness.reenter === "resume-open" && !harness.surfaceOpen) {
                harness.reenter = "";
                harness.surfaceOpen = true;
            }
        }
        function onAddonSuspendedChanged() {
            if (!dataState.addonSuspended && harness.surfaceOpen) harness.resumeLeaks++;
        }
    }
    Connections {
        target: session.manager
        function onAddonsChanged() {
            if (session.manager.addons.length && harness.reenter === "close-publish") harness.surfaceOpen = false;
        }
    }
    Controls.ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        UI.AddonManager {
            objectName: "composedManager"
            width: parent.availableWidth
            addons: session.manager.addons
            preview: session.manager.preview
            busy: session.busy
            loading: session.manager.loading
            feedback: session.feedback
            onInstallRequested: sha => session.manager.installAddon(sha)
            onEnableRequested: (id, sha) => session.manager.enableAddon(id, sha)
            onDisableRequested: (id, sha) => session.manager.disableAddon(id, sha)
            onRemoveRequested: (id, sha) => session.manager.removeAddon(id, sha)
            onRollbackRequested: (id, sha) => session.manager.rollbackAddon(id, sha)
        }
    }
    function reply(index, raw) {
        const call = calls[index];
        call.resolve(call.message.member === "SnapshotFor" ? {value: raw}
            : {values: [{}], value: {value: raw}});
    }
}
