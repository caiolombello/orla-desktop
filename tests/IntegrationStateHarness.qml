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
            queue = queue.concat([{resolve: resolve, reject: reject}]);
        }
        function reply(text, failed) {
            const next = queue[0];
            queue = queue.slice(1);
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
        onLoadingChanged: {
            if (loading && root.revokeOnLoading) active = false;
            if (!loading && root.refreshAfterLoad) { root.refreshAfterLoad = false; refresh(); }
        }
        onErrorChanged: if (error && root.changeOnError) enabledModules = ["recording"]
        onSnapshotChanged: if (snapshot.quota.status === "ready") {
            root.readyCommits++;
            if (root.changeOnCommit) enabledModules = ["peripherals"];
            if (root.replayOnCommit) {
                root.replayOnCommit = false;
                transport.replay({value: transport.lastText});
            }
        }
    }
}
