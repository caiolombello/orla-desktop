import QtQuick
import QtQuick.Window
import "../package/contents/ui" as Candidate

QtObject {
    id: harness
    property QtObject owner: QtObject {}
    property QtObject otherOwner: QtObject {}
    property bool pickerActive: true
    property QtObject filePicker: Candidate.AddonFilePicker {
        manager: candidate
        active: harness.pickerActive
    }
    property Window alternateWindow: Window { visible: false }
    property var token: null
    property var oldToken: null
    property var oldDialog: null
    property var state: candidate
    property var calls: []
    property string reenter: ""
    property var settlements: []
    property var starts: []
    property var reentries: []
    property QtObject fake: QtObject {
        function asyncCall(message, resolve, reject) {
            harness.calls = harness.calls.concat([{message: message, resolve: resolve, reject: reject}]);
        }
    }
    property QtObject candidate: Candidate.AddonManagerState {
        id: candidate
        owner: harness.owner
        transport: harness.fake
        onMutationStarted: function(member) {
            harness.starts = harness.starts.concat([member]);
            if (harness.reenter === "start-close") active = false;
            if (harness.reenter === "start-aba") { active = false; active = true; }
        }
        onMutationSettled: function(member, committed, generation) {
            harness.settlements = harness.settlements.concat([{member: member, committed: committed,
                generation: generation, busy: busy}]);
        }
        onBusyChanged: {
            if (busy && harness.reenter === "busy-close") active = false;
            if (!busy && harness.reenter === "scope-reselection")
                harness.reentries = harness.reentries.concat([beginFileSelection(harness.owner) !== null]);
            if (!busy && harness.reenter === "selection-aba") {
                active = false; active = true;
            }
            if (!busy && harness.reenter === "release-disable" && addons.length)
                harness.reentries = harness.reentries.concat([disableAddon(addons[0].id, addons[0].sha256)]);
        }
        onAddonsChanged: {
            if (addons.length && harness.reenter === "publish-aba") { active = false; active = true; }
            if (addons.length && harness.reenter === "publish-disable")
                disableAddon(addons[0].id, addons[0].sha256);
        }
    }
    function succeed(index, raw) { calls[index].resolve({values: [{}], value: {value: raw}}); }
    function fail(index) { calls[index].reject({message: "synthetic private failure"}); }
    function messages() { return JSON.stringify(calls.map(call => call.message)); }
    property var hook: null
    function notify(event) { if (typeof hook === "function") hook(event); }
    property Connections pickerChanges: Connections {
        target: harness.filePicker
        function onSelectionStateChanged() { harness.notify("picker-state"); }
        function onSelectionTokenChanged() { harness.notify("picker-token"); }
        function onChooserChanged() { harness.notify("picker-chooser"); }
    }
    property Connections stateChanges: Connections {
        target: harness.state
        function onLoadingChanged() { harness.notify("loading"); }
        function onSelectingChanged() { harness.notify("selecting"); }
        function onBusyChanged() { harness.notify("busy"); }
    }
}
