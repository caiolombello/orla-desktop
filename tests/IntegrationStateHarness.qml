import QtQuick
import "../package/contents/ui" as Orla

Item {
    id: root
    property bool revokeOnLoading: false
    property bool changeOnCommit: false
    property bool replayOnCommit: false
    property bool refreshAfterLoad: false
    property bool changeOnError: false
    property int readyCommits: 0
    property bool suspendOnAddonLoading: false
    property bool cycleOnAddonCommit: false
    property bool replayOnAddonCommit: false
    property int addonCommits: 0
    property bool replayBadOnPhysicalSettlement: false
    QtObject {
        id: transport
        objectName: "transport"
        property var messages: []
        property var queue: []
        property var replay: null
        property string lastText: ""
        property bool throwOnCall: false
        property bool immediateReply: false
        function asyncCall(message, resolve, reject) {
            messages = messages.concat([message]);
            if (throwOnCall) throw new Error("fixture transport failure");
            if (immediateReply) {
                resolve({value: JSON.stringify({schemaVersion: 2, modules: ["quota"],
                    quota: {status: "ready", windows: []}})});
                return;
            }
            queue = queue.concat([{service: message.service, resolve: resolve, reject: reject}]);
        }
        function reply(text, failed, service) {
            const index = service ? queue.findIndex(item => item.service === service) : 0;
            const next = queue[index];
            queue = queue.filter((item, i) => i !== index);
            replay = next.resolve;
            lastText = text;
            if (failed) next.reject();
            else next.resolve({value: text});
        }
    }
    Orla.IntegrationState {
        id: state
        objectName: "state"
        transport: transport
        nowMsOverride: 100000
        onAddonLoadingChanged: if (addonLoading && root.suspendOnAddonLoading) addonSuspended = true
        onAddonCallPendingChanged: if (!addonCallPending && root.replayBadOnPhysicalSettlement) {
            root.replayBadOnPhysicalSettlement = false;
            transport.replay({value: "{}"});
        }
        onLoadingChanged: {
            if (loading && root.revokeOnLoading) active = false;
            if (!loading && root.refreshAfterLoad) { root.refreshAfterLoad = false; refresh(); }
        }
        onErrorChanged: if (error && root.changeOnError) enabledModules = ["recording"]
        onSnapshotChanged: {
            if (snapshot.peripherals.status === "ready") {
                root.addonCommits++;
                if (root.cycleOnAddonCommit) { root.cycleOnAddonCommit = false; active = false; active = true; }
                if (root.replayOnAddonCommit) {
                    root.replayOnAddonCommit = false;
                    transport.replay({value: transport.lastText});
                }
            }
            if (snapshot.quota.status === "ready") {
                root.readyCommits++;
                if (root.changeOnCommit) enabledModules = ["peripherals"];
                if (root.replayOnCommit) {
                    root.replayOnCommit = false;
                    transport.replay({value: transport.lastText});
                }
            }
        }
    }
}
