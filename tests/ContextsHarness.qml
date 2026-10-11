import QtQuick
import "../package/contents/ui" as DockUI
import "../package/contents/code/Contexts.js" as Contexts

Item {
    id: harness
    property var sourceSnapshot: ({
        outputName: "",
        activity: {status: "loading", currentId: "", ids: [], names: []},
        desktop: {status: "loading", currentId: "", ids: [], names: []}
    })
    property string fixtureContextsJSON: ""
    property int writeCount: 0
    property bool countWrites: false
    property string previewDraft: "owned-dirty-preview"
    property bool previewDirty: true
    property QtObject timerWitness: timer

    QtObject {
        id: configuration
        objectName: "contextsConfiguration"
        property string contextsJSON: harness.fixtureContextsJSON
        onContextsJSONChanged: if (harness.countWrites) harness.writeCount++
    }
    QtObject {
        id: profileState
        objectName: "profilesDependency"
        property string activeProfileId: "legacy"
        property int revision: 7
        property bool writable: true
        property var profiles: [
            {id: "work", name: "Trabalho"},
            {id: "personal", name: "Pessoal"},
            {id: "games", name: "Jogos"}
        ]
        property int selectCalls: 0
        function select() { selectCalls++; return false; }
    }
    QtObject {
        id: timer
        objectName: "timerWitness"
        property double deadline: 1234567890000
        property int remaining: 731
    }

    DockUI.ContextState {
        id: contextState
        objectName: "contextState"
        sourceSnapshot: harness.sourceSnapshot
    }
    DockUI.ContextBindingsState {
        id: bindingsState
        objectName: "contextBindingsState"
        configuration: configuration
        profiles: profileState
        contexts: contextState
    }

    Component {
        id: bindingsFactory
        DockUI.ContextBindingsState {
            objectName: "reloadedContextBindingsState"
        }
    }

    function setSource(value) { sourceSnapshot = value; }
    function installMutableDomainWitness() {
        var currentIdReads = 0;
        var activity = {status: "ready", ids: ["a1"], names: ["Foco"]};
        Object.defineProperty(activity, "currentId", {
            enumerable: true,
            get: function() {
                currentIdReads++;
                return currentIdReads === 1 ? "a1" : "other";
            }
        });
        sourceSnapshot = {
            outputName: "DP-1",
            activity: activity,
            desktop: {status: "ready", currentId: "d1", ids: ["d1"], names: ["Um"]}
        };
        return JSON.stringify({reads: currentIdReads, snapshot: contextState.snapshot});
    }
    function installMutableTopLevelWitness() {
        var outputReads = 0;
        var source = {
            activity: {status: "ready", currentId: "a1", ids: ["a1"], names: ["Foco"]},
            desktop: {status: "ready", currentId: "d1", ids: ["d1"], names: ["Um"]}
        };
        Object.defineProperty(source, "outputName", {
            enumerable: true,
            get: function() {
                outputReads++;
                return outputReads === 1 ? "DP-1" : "forged-output";
            }
        });
        sourceSnapshot = source;
        return JSON.stringify({reads: outputReads, snapshot: contextState.snapshot});
    }
    function parse(raw) { return Contexts.parse(raw); }
    function recreateBindings() {
        return bindingsFactory.createObject(harness, {
            configuration: configuration, profiles: profileState, contexts: contextState
        });
    }
    Component.onCompleted: countWrites = true
}
