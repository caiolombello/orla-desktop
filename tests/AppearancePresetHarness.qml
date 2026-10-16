import QtQuick
import QtQuick.Controls as Controls
import "../package/contents/ui" as DockUI

Controls.ApplicationWindow {
    id: window
    width: 520
    height: 680
    visible: true
    QtObject {
        id: config
        objectName: "configuration"
        property string profilesJSON: ""
        property string contextsJSON: ""
        property bool autoContextEnabled: false
        property string autoContextDefaultProfile: ""
        property bool showLocalToasts: false
        property bool showControlCenter: false
        property var launchers: ["applications:org.kde.dolphin.desktop", "applications:org.kde.konsole.desktop"]
        property string theme: "glass"
        property string appearanceJSON: ""
        property int iconSize: 42
        property bool animations: true
        property bool showClock: true
        property bool showMusic: true
        property bool showSystemBattery: false
        property bool showPomodoro: true
        property bool showQuota: true
        property bool showPeripherals: true
        property bool showRecording: true
        property bool showAudioHud: false
        property bool calendarEvents: false
        property bool currentDesktopOnly: false
        property int focusMinutes: 25
        property int breakMinutes: 5
        property double timerDeadline: 1234567890000
        property int timerRemaining: 731
        property bool timerBreak: true
        property int completedFocus: 3
    }
    Item {
        id: fixture
        objectName: "dock"
        anchors.fill: parent
        property alias configuration: config
        property alias profiles: profileState
        property alias appearance: appearanceState
        property alias appearancePreset: presetState
        readonly property var presentation: profileState.effective
        readonly property var displayWidgets: presetState.previewWidgets || presentation.widgets
        DockUI.ProfileState {
            id: profileState
            configuration: config
            transitionGuard: () => !appearanceState.dirty && !presetState.dirty
        }
        DockUI.AppearanceState {
            id: appearanceState
            configuration: profileState.effective.appearance
            scopeKey: profileState.activeProfileId
            writeAppearance: (next, scope, signature) => {
                if (scope !== profileState.activeProfileId || signature !== appearanceState.signature) return false;
                return profileState.commitPresentation({appearance:{appearanceJSON:next}},scope,profileState.revision);
            }
        }
        DockUI.AppearancePresetState { id: presetState; profiles: profileState; appearance: appearanceState }
        DockUI.ContextState { id: contexts; sourceSnapshot: null }
        DockUI.ContextBindingsState { id: bindings; configuration: config; profiles: profileState; contexts: contexts }
        DockUI.AutoContextProfileState {
            id: automaticProfiles
            configuration: config
            profiles: profileState
            contexts: contexts
            bindingsState: bindings
            active: true
            interactionBusy: popup.visible
        }
        Controls.Popup {
            id: popup
            objectName: "settingsPopup"
            property int heightBudget: 600
            x: 0
            y: 0
            width: 420
            height: heightBudget
            closePolicy: Controls.Popup.CloseOnEscape
            onAboutToShow: appearanceState.begin()
            onAboutToHide: presetState.cancel()
            onClosed: presetState.cancel()
            contentItem: DockUI.SettingsContents {
                configuration: config
                appearance: appearanceState
                appearancePreset: presetState
                profiles: profileState
                contexts: contexts
                contextBindings: bindings
                automation: automaticProfiles
                resetTimer: () => {}
                onAppearanceCanceled: popup.close()
            }
        }
        Component { id: reloadFactory; DockUI.ProfileState { objectName: "reloadedProfiles"; configuration: config } }
        function recreateState() { reloadFactory.createObject(fixture); }
    }
}
