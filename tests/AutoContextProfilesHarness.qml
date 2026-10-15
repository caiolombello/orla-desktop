import QtQuick
import "../package/contents/ui" as DockUI

Item {
    id: harness
    property alias configuration: config
    property alias profileState: profiles
    property alias contextState: contexts
    property alias bindingsState: bindings
    property bool running: false
    property bool busy: false
    property bool previewDirty: false
    property var transitionHook: null
    property var selectionHook: null
    property var automatic: null
    property bool useSelectionAdapter: false
    property bool rejectSelectionResult: false
    property var afterGuardHook: null
    property var second: null
    property int preferenceSetters: 0
    property var selectionResults: []
    property int writes: 0
    property var selections: []
    property var sourceSnapshot: ({outputName:"", activity:{status:"loading",currentId:"",ids:[],names:[]},
        desktop:{status:"loading",currentId:"",ids:[],names:[]}})
    QtObject {
        id: config
        objectName: "configuration"
        property string profilesJSON: ""
        property string contextsJSON: ""
        property bool autoContextEnabled: false
        property string autoContextDefaultProfile: ""
        property var launchers: ["applications:org.example.fixture.desktop"]
        property string theme: "glass"
        property string appearanceJSON: ""
        property int iconSize: 42
        property bool animations: true
        property bool showClock: true
        property bool showMusic: true
        property bool showSystemBattery: false
        property bool showPomodoro: true
        property bool showQuota: false
        property bool showPeripherals: false
        property bool showRecording: false
        property bool showAudioHud: false
        property bool calendarEvents: true
        property bool currentDesktopOnly: false
        property double timerDeadline: 1234567890000
        onProfilesJSONChanged: harness.writes++
    }
    DockUI.ProfileState {
        id: profiles
        objectName: "profiles"
        configuration: config
        transitionGuard: () => harness.transitionHook ? harness.transitionHook() : !harness.previewDirty
    }
    DockUI.ContextState { id: contexts; objectName: "contexts"; sourceSnapshot: harness.sourceSnapshot }
    DockUI.ContextBindingsState {
        id: bindings
        objectName: "bindings"
        configuration: config
        profiles: profiles
        contexts: contexts
    }
    Connections {
        target: profiles
        function onActiveProfileIdChanged() {
            harness.selections = harness.selections.concat([profiles.activeProfileId]);
            if (harness.selectionHook) harness.selectionHook();
        }
    }
    QtObject {
        id: selectionAdapter
        readonly property alias initialized: profiles.initialized
        readonly property alias writable: profiles.writable
        readonly property alias activeProfileId: profiles.activeProfileId
        readonly property alias revision: profiles.revision
        readonly property alias profiles: profiles.profiles
        readonly property alias savedJSON: profiles.savedJSON
        function select(id, scope, revision, guard) {
            const accepted = harness.profileState.select(id, scope, revision, () => {
                const allowed = guard();
                if (allowed && harness.afterGuardHook) harness.afterGuardHook();
                return allowed;
            });
            const result = harness.rejectSelectionResult ? false : accepted;
            harness.selectionResults = harness.selectionResults.concat([{target:id, accepted:result}]);
            return result;
        }
    }
    function spyPreferenceSetters() {
        const spy = {};
        for (const key of ["autoContextEnabled", "autoContextDefaultProfile"]) {
            Object.defineProperty(spy, key, {get:() => config[key], set:value => {
                harness.preferenceSetters++;
                config[key] = value;
            }});
        }
        automatic.configuration = spy;
    }
    function createSecond() {
        second = Qt.createComponent("AutoContextProfilesHarness.qml").createObject(harness);
    }
    function createController() {
        const component = Qt.createComponent("../package/contents/ui/AutoContextProfileState.qml");
        automatic = component.createObject(harness, {configuration:config,
            profiles:Qt.binding(() => harness.useSelectionAdapter ? selectionAdapter : profiles),
            contexts:contexts, bindingsState:bindings, active:Qt.binding(() => harness.running),
            interactionBusy:Qt.binding(() => harness.busy)});
        if (!automatic) throw new Error(component.errorString());
    }
    function restartController() { if (automatic) automatic.destroy(); automatic = null; createController(); }
    Component.onCompleted: createController()
}
