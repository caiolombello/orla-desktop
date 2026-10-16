import QtQuick
import "../package/contents/ui" as Candidate
import "../package/contents/code/ThemeFile.js" as ThemeFile
QtObject {
    id: harness
    property var appearance: state
    property QtObject owner: QtObject { objectName: "owner" }
    property QtObject otherOwner: QtObject { objectName: "otherOwner" }
    property QtObject configuration: QtObject {
        property string appearanceJSON: ""
        property string theme: "glass"
        property int iconSize: 42
        property bool animations: true
        property int writes: 0
        onAppearanceJSONChanged: writes++
    }
    property QtObject transport: QtObject {
        property var requests: []
        property bool throwOnLoad: false
        function loadThemeFile(url,resolve,reject) {
            if (throwOnLoad) throw new Error("synthetic transport failure");
            requests = requests.concat([{url:url,resolve:resolve,reject:reject}]);
        }
        function succeed(index,raw) { requests[index].resolve(raw); }
        function reject(index) { requests[index].reject({message:"private synthetic path"}); }
    }
    property QtObject candidate: Candidate.AppearanceState { id: state; configuration: harness.configuration }
    function decode(raw) { return ThemeFile.decode(raw); }
    function encoded(text) { return ThemeFile.encodedSelection(text); }
    function replyText(reply) { return ThemeFile.replyText(reply); }
    property var token2: null
    property var token: null
    Component.onCompleted: state.begin()
}
