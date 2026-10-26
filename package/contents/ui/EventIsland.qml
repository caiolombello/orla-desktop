import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.impl as ControlsImpl
import "../code/Style.js" as Style

// Orla's own events in a black capsule at the top of the screen, like the
// iPhone's Dynamic Island: an icon, the title and a short detail; volume
// changes add a level bar. Presentation only: EventState owns the events.
// The item keeps a fixed width so its window never resizes; the capsule grows
// and shrinks inside it.
Item {
    id: island
    objectName: "eventIsland"
    required property var eventState
    property bool reducedMotion: false
    readonly property var event: eventState ? eventState.current : null
    readonly property bool hasEvent: event !== null && event !== undefined
    // The last event stays drawn while the capsule fades out.
    property var shown: null
    // Reads `event` itself: `hasEvent` may not have updated yet in this handler.
    onEventChanged: if (event) shown = event
    Component.onCompleted: if (event) shown = event
    // The window stays mapped until the fade-out ends.
    readonly property bool showing: hasEvent || capsule.opacity > 0
    readonly property bool volume: shown !== null && shown.kind === "audio" && shown.action === "volume"
    readonly property int level: volume ? Math.max(0, Math.min(100, Number(shown.value) || 0)) : 0
    readonly property var scheme: Style.scheme("dark")

    implicitWidth: Style.size.popupWidth
    implicitHeight: capsule.height
    Accessible.role: Accessible.AlertMessage
    Accessible.name: hasEvent ? event.title + (event.detail ? ". " + event.detail : "") : ""
    Accessible.ignored: !hasEvent

    function iconName() {
        if (shown === null) return "";
        if (shown.kind === "completion") return "chronometer-symbolic";
        if (shown.action === "mute") return shown.value ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic";
        if (shown.action === "default-output") return "audio-speakers-symbolic";
        return level === 0 ? "audio-volume-muted-symbolic" : level < 34 ? "audio-volume-low-symbolic"
            : level < 67 ? "audio-volume-medium-symbolic" : "audio-volume-high-symbolic";
    }

    Rectangle {
        id: capsule
        objectName: "eventIslandCapsule"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: Math.min(island.width, row.implicitWidth + Style.space.lg * 2)
        height: row.implicitHeight + Style.space.sm * 2
        radius: height / 2
        color: Style.glass.shade
        opacity: island.hasEvent ? 1 : 0
        scale: island.hasEvent ? 1 : 0.85
        transformOrigin: Item.Top
        Behavior on width { NumberAnimation { duration: Style.duration(Style.motion.normal, island.reducedMotion); easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Style.duration(Style.motion.fast, island.reducedMotion) } }
        Behavior on scale { NumberAnimation { duration: Style.duration(Style.motion.normal, island.reducedMotion); easing.type: Easing.OutBack } }

        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: Style.space.sm
            ControlsImpl.IconImage {
                objectName: "eventIslandIcon"
                name: island.iconName()
                color: island.scheme.text
                sourceSize.width: Style.size.iconMd
                sourceSize.height: Style.size.iconMd
                Layout.alignment: Qt.AlignVCenter
            }
            ColumnLayout {
                spacing: 0
                // Leaves room for the icon, the level bar and the capsule's ends.
                Layout.maximumWidth: island.width - Style.size.iconMd - Style.space.xxxl * 3 - Style.space.lg * 2
                Text {
                    objectName: "eventIslandTitle"
                    Layout.fillWidth: true
                    text: island.shown ? island.shown.title : ""
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    font.pixelSize: Style.type.body
                    font.weight: Style.weight.demiBold
                    color: island.scheme.text
                }
                Text {
                    objectName: "eventIslandDetail"
                    Layout.fillWidth: true
                    visible: text.length > 0 && !island.volume
                    text: island.shown && island.shown.detail ? island.shown.detail : ""
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    font.pixelSize: Style.type.caption
                    color: island.scheme.textMuted
                }
            }
            // The volume as a white capsule bar, as the iPhone shows it.
            Rectangle {
                objectName: "eventIslandLevel"
                visible: island.volume
                Layout.preferredWidth: Style.space.xxxl * 2
                Layout.preferredHeight: Style.space.xs
                Layout.alignment: Qt.AlignVCenter
                radius: height / 2
                color: Style.alpha(island.scheme.text, Style.state.selected)
                Accessible.role: Accessible.ProgressBar
                Accessible.name: island.volume ? qsTr("Volume %1%").arg(island.level) : ""
                Rectangle {
                    objectName: "eventIslandLevelFill"
                    width: parent.width * island.level / 100
                    height: parent.height
                    radius: height / 2
                    color: island.scheme.text
                }
            }
        }
    }
}
