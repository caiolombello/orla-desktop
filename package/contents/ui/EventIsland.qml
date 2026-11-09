import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import QtQuick.Controls.impl as ControlsImpl
import "../code/Island.js" as Island
import "../code/Style.js" as Style

// The top island, a black capsule like the iPhone's Dynamic Island. It morphs
// between three looks: a transient notice (icon, title and detail; volume adds
// a level bar), a compact live activity (music, the Pomodoro, or the
// microphone or camera in use) and, on click, that activity expanded with its
// controls. Presentation only: IslandState decides what to show.
// In a layer-shell window the item is only as large as the capsule, so the
// rest of the screen keeps its clicks; it grows at once and shrinks after the
// capsule has. Plasma's Dialog keeps its first size, so with `fixedSize` the
// item reserves room for a notice from the start and never expands.
Item {
    id: island
    objectName: "eventIsland"
    required property var islandState
    // MediaState and Pomodoro in the dock; fixtures in tests.
    property var mediaController: null
    property var timerController: null
    property bool interactive: false
    property bool fixedSize: false
    property bool reducedMotion: false
    // How long the expanded island waits for the pointer to come back.
    property int collapseDelay: 1200
    readonly property var eventState: islandState ? islandState.eventState : null
    readonly property var event: eventState ? eventState.current : null
    readonly property bool hasEvent: event !== null && event !== undefined
    readonly property string mode: islandState ? islandState.mode : "idle"
    readonly property string look: fixedSize && mode === "expanded" ? "compact" : mode
    readonly property var activity: islandState ? islandState.primary : null
    readonly property var privacy: islandState ? islandState.privacy : ({microphone: false, camera: false})
    // The last notice and activity stay drawn while the capsule fades out.
    property var shown: null
    property var shownActivity: null
    // Reads `event` itself: `hasEvent` may not have updated yet in this handler.
    onEventChanged: if (event) shown = event
    onActivityChanged: if (activity) shownActivity = activity
    Component.onCompleted: {
        if (event) shown = event;
        if (activity) shownActivity = activity;
        if (look !== "idle") sizeLook = look;
        fitHost();
    }
    // The window stays mapped until the fade-out ends.
    readonly property bool showing: mode !== "idle" || capsule.opacity > 0
    readonly property string kind: shownActivity ? shownActivity.kind : ""
    readonly property bool volume: shown !== null && shown.kind === "audio" && shown.action === "volume"
    readonly property bool power: shown !== null && shown.kind === "power"
    readonly property int level: volume || power ? Math.max(0, Math.min(100, Number(shown.value) || 0)) : 0
    // Battery bars as the levels elsewhere: green while charging, amber or red when low.
    readonly property color levelColor: !power ? scheme.text : shown.action === "charging" ? Style.levels.good
        : level <= 10 ? Style.levels.critical : Style.levels.low
    readonly property var scheme: Style.scheme("dark")
    readonly property color timerTint: Style.iconTiles.coral.top

    readonly property real compactHeight: Style.size.iconMd + Style.space.xs
    readonly property real noticeHeight: Math.ceil(titleMetrics.height + detailMetrics.height) + Style.space.sm * 2
    // The capsule keeps its last size while it fades out.
    property string sizeLook: "compact"
    onLookChanged: if (look !== "idle") sizeLook = look
    readonly property real targetWidth: sizeLook === "expanded" ? Style.size.popupWidth
        : sizeLook === "transient" ? Math.min(Style.size.popupWidth, noticeRow.implicitWidth + Style.space.lg * 2)
        : Math.min(Style.size.popupWidth, compactRow.implicitWidth + Style.space.md * 2)
    readonly property real targetHeight: sizeLook === "expanded" ? expandedContent.implicitHeight + Style.space.lg * 2
        : sizeLook === "transient" ? noticeRow.implicitHeight + Style.space.sm * 2
        : compactHeight

    property real hostWidth: 0
    property real hostHeight: 0
    implicitWidth: fixedSize ? Style.size.popupWidth : hostWidth
    implicitHeight: fixedSize ? noticeHeight : hostHeight
    onTargetWidthChanged: fitHost()
    onTargetHeightChanged: fitHost()
    function fitHost() {
        if (targetWidth >= hostWidth && targetHeight >= hostHeight) {
            shrinkHost.stop();
            hostWidth = targetWidth;
            hostHeight = targetHeight;
        } else {
            hostWidth = Math.max(hostWidth, targetWidth);
            hostHeight = Math.max(hostHeight, targetHeight);
            shrinkHost.restart();
        }
    }
    Timer {
        id: shrinkHost
        interval: Style.duration(Style.motion.slow, island.reducedMotion)
        onTriggered: {
            island.hostWidth = island.targetWidth;
            island.hostHeight = island.targetHeight;
        }
    }

    FontMetrics { id: titleMetrics; font.pixelSize: Style.type.body; font.weight: Style.weight.demiBold }
    FontMetrics { id: detailMetrics; font.pixelSize: Style.type.caption }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: hasEvent ? event.title + (event.detail ? ". " + event.detail : "") : summary()
    Accessible.ignored: mode === "idle"

    function summary() {
        if (!activity) return "";
        if (activity.kind === "meeting") return activity.title + ". " + meetingWhen(activity);
        if (activity.kind === "timer")
            return (activity.isBreak ? qsTr("Pausa") : qsTr("Foco")) + ". " + qsTr("%1 restantes").arg(Island.clock(activity.secondsLeft));
        if (activity.kind === "media")
            return (activity.playing ? qsTr("Tocando") : qsTr("Pausado")) + ". " + activity.title;
        return privacyText(activity);
    }
    function meetingWhen(value) {
        return value && value.minutes > 0 ? qsTr("Em %1 min").arg(value.minutes) : qsTr("Agora");
    }
    function meetingSpan(value) {
        if (!value) return "";
        const start = Qt.formatTime(new Date(value.startMs), Qt.locale().timeFormat(Locale.ShortFormat));
        const end = Qt.formatTime(new Date(value.endMs), Qt.locale().timeFormat(Locale.ShortFormat));
        return value.endMs > value.startMs ? start + " – " + end : start;
    }
    function privacyText(value) {
        if (!value) return "";
        if (value.microphone && value.camera) return qsTr("Microfone e câmera em uso");
        return value.camera ? qsTr("Câmera em uso") : qsTr("Microfone em uso");
    }
    function iconName() {
        if (shown === null) return "";
        if (shown.kind === "completion") return "chronometer-symbolic";
        if (shown.kind === "power") {
            if (shown.action === "phone-low") return "phone-battery-symbolic";
            if (shown.action === "low") return "battery-caution-symbolic";
            const tens = Math.round(level / 10) * 10;
            return "battery-" + (tens < 10 ? "00" : tens < 100 ? "0" : "") + tens + "-charging-symbolic";
        }
        if (shown.action === "mute") return shown.value ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic";
        if (shown.action === "default-output") return "audio-speakers-symbolic";
        return level === 0 ? "audio-volume-muted-symbolic" : level < 34 ? "audio-volume-low-symbolic"
            : level < 67 ? "audio-volume-medium-symbolic" : "audio-volume-high-symbolic";
    }

    // Round icon button drawn for the always-dark island. Kirigami stays out
    // so the portable CI can load the island; the island never takes keyboard
    // focus, and the same actions stay reachable by keyboard in the dock popups.
    component IslandButton: T.AbstractButton {
        id: button
        property string iconName: ""
        property bool prominent: false
        implicitWidth: prominent ? Style.size.target + Style.space.xs : Style.size.target
        implicitHeight: implicitWidth
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        opacity: enabled ? 1 : 1 - Style.state.disabled
        Accessible.name: text
        background: Rectangle {
            radius: width / 2
            color: Style.alpha(island.scheme.text, button.pressed ? Style.state.pressed
                : button.hovered ? Style.state.hover : button.prominent ? Style.state.chip : 0)
        }
        contentItem: Item {
            ControlsImpl.IconImage {
                anchors.centerIn: parent
                name: button.iconName
                color: island.scheme.text
                sourceSize.width: button.prominent ? Style.size.iconLg : Style.size.iconMd
                sourceSize.height: button.prominent ? Style.size.iconLg : Style.size.iconMd
            }
        }
    }

    Rectangle {
        id: capsule
        objectName: "eventIslandCapsule"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        width: island.targetWidth
        height: island.targetHeight
        radius: island.sizeLook === "expanded" ? Style.radius.popup + Style.space.sm : height / 2
        color: Style.glass.shade
        clip: true
        opacity: island.mode !== "idle" ? 1 : 0
        scale: island.mode !== "idle" ? 1 : 0.85
        transformOrigin: Item.Top
        Behavior on width { NumberAnimation { duration: Style.duration(Style.motion.normal, island.reducedMotion); easing.type: Easing.OutCubic } }
        Behavior on height { NumberAnimation { duration: Style.duration(Style.motion.normal, island.reducedMotion); easing.type: Easing.OutCubic } }
        Behavior on radius { NumberAnimation { duration: Style.duration(Style.motion.normal, island.reducedMotion); easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Style.duration(Style.motion.fast, island.reducedMotion) } }
        Behavior on scale { NumberAnimation { duration: Style.duration(Style.motion.normal, island.reducedMotion); easing.type: Easing.OutBack } }

        // A click expands the live activity or dismisses the notice. Buttons
        // declared later sit above it and keep their own clicks.
        MouseArea {
            objectName: "islandTapArea"
            anchors.fill: parent
            enabled: island.interactive && island.mode !== "idle"
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                if (island.mode === "transient") island.eventState.dismiss();
                else island.islandState.toggle();
            }
        }
        HoverHandler { id: hover; enabled: island.interactive }
        Timer {
            interval: island.collapseDelay
            running: island.mode === "expanded" && !hover.hovered
            onTriggered: island.islandState.collapse()
        }

        // Transient notice.
        RowLayout {
            id: noticeRow
            objectName: "islandNotice"
            anchors.centerIn: parent
            spacing: Style.space.sm
            opacity: island.look === "transient" ? 1 : 0
            // Shown as soon as it is chosen: a hidden layout keeps a stale size.
            visible: island.look === "transient" || opacity > 0
            Behavior on opacity { NumberAnimation { duration: Style.duration(Style.motion.fast, island.reducedMotion) } }
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
                Layout.maximumWidth: Style.size.popupWidth - Style.size.iconMd - Style.space.xxxl * 3 - Style.space.lg * 2
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
            // The volume as a white capsule bar, as the iPhone shows it; battery tinted.
            Rectangle {
                objectName: "eventIslandLevel"
                visible: island.volume || island.power
                Layout.preferredWidth: Style.space.xxxl * 2
                Layout.preferredHeight: Style.space.xs
                Layout.alignment: Qt.AlignVCenter
                radius: height / 2
                color: Style.alpha(island.scheme.text, Style.state.selected)
                Accessible.role: Accessible.ProgressBar
                Accessible.name: island.volume ? qsTr("Volume %1%").arg(island.level)
                    : island.power ? qsTr("Bateria %1%").arg(island.level) : ""
                Rectangle {
                    objectName: "eventIslandLevelFill"
                    width: parent.width * island.level / 100
                    height: parent.height
                    radius: height / 2
                    color: island.levelColor
                }
            }
        }

        // Compact live activity: a leading mark, a short text and a trailing
        // state, plus the privacy icons when another activity owns the capsule.
        RowLayout {
            id: compactRow
            objectName: "islandCompact"
            anchors.centerIn: parent
            spacing: Style.space.sm
            opacity: island.look === "compact" ? 1 : 0
            visible: island.look === "compact" || opacity > 0
            Behavior on opacity { NumberAnimation { duration: Style.duration(Style.motion.fast, island.reducedMotion) } }
            Item {
                Layout.preferredWidth: Style.size.iconSm
                Layout.preferredHeight: Style.size.iconSm
                Layout.alignment: Qt.AlignVCenter
                CoverArt {
                    id: compactCover
                    objectName: "islandCompactCover"
                    anchors.fill: parent
                    url: island.kind === "media" ? island.shownActivity.artUrl : ""
                    cornerRadius: Style.radius.xs
                }
                ControlsImpl.IconImage {
                    objectName: "islandCompactIcon"
                    anchors.fill: parent
                    visible: !compactCover.visible
                    name: island.kind === "meeting" ? "appointment-soon-symbolic"
                        : island.kind === "timer" ? "chronometer-symbolic"
                        : island.kind === "media" ? "audio-x-generic-symbolic"
                        : island.kind === "privacy" && island.shownActivity.microphone ? "audio-input-microphone-symbolic"
                        : island.kind === "privacy" ? "camera-web-symbolic" : ""
                    color: island.kind === "meeting" ? island.scheme.accent
                        : island.kind === "timer" ? island.timerTint
                        : island.kind === "privacy" && island.shownActivity.microphone ? Style.privacy.microphone
                        : island.kind === "privacy" ? Style.privacy.camera : island.scheme.text
                    sourceSize.width: Style.size.iconSm
                    sourceSize.height: Style.size.iconSm
                }
            }
            Text {
                objectName: "islandCompactText"
                Layout.maximumWidth: Style.size.popupWidth / 2
                Layout.alignment: Qt.AlignVCenter
                visible: text.length > 0
                // The meeting's title waits for the expanded view, off a shared screen.
                text: island.kind === "media" ? island.shownActivity.title
                    : island.kind === "meeting" ? island.meetingWhen(island.shownActivity)
                    : island.kind === "privacy" ? island.privacyText(island.shownActivity)
                    : island.kind === "timer" ? (island.shownActivity.isBreak ? qsTr("Pausa") : qsTr("Foco")) : ""
                textFormat: Text.PlainText
                elide: Text.ElideRight
                maximumLineCount: 1
                font.pixelSize: Style.type.label
                font.weight: Style.weight.medium
                color: island.scheme.text
            }
            Text {
                objectName: "islandClock"
                visible: island.kind === "timer"
                Layout.alignment: Qt.AlignVCenter
                text: island.kind === "timer" ? Island.clock(island.shownActivity.secondsLeft) : ""
                textFormat: Text.PlainText
                font.pixelSize: Style.type.label
                font.weight: Style.weight.demiBold
                font.features: ({"tnum": 1})
                color: island.timerTint
            }
            // Music bars while playing, a pause mark while paused.
            Row {
                id: bars
                objectName: "islandBars"
                visible: island.kind === "media" && island.shownActivity.playing
                Layout.preferredHeight: Style.size.iconSm
                Layout.alignment: Qt.AlignVCenter
                spacing: Style.space.xxs
                property var levels: [0.5, 0.9, 0.65]
                Repeater {
                    model: 3
                    Rectangle {
                        required property int index
                        anchors.bottom: parent ? parent.bottom : undefined
                        width: Style.space.xxs * 1.5
                        height: Math.max(width, bars.height * bars.levels[index])
                        radius: width / 2
                        color: island.scheme.text
                        Behavior on height { NumberAnimation { duration: Style.duration(Style.motion.slow, island.reducedMotion); easing.type: Easing.InOutQuad } }
                    }
                }
                Timer {
                    interval: Style.motion.slow + Style.motion.fast
                    repeat: true
                    running: bars.visible && island.look === "compact" && !island.reducedMotion
                    onTriggered: bars.levels = [0.3 + Math.random() * 0.7, 0.3 + Math.random() * 0.7, 0.3 + Math.random() * 0.7]
                }
            }
            ControlsImpl.IconImage {
                objectName: "islandPausedMark"
                visible: island.kind === "media" && !island.shownActivity.playing
                name: "media-playback-pause-symbolic"
                color: island.scheme.textMuted
                sourceSize.width: Style.size.iconSm
                sourceSize.height: Style.size.iconSm
                Layout.alignment: Qt.AlignVCenter
            }
            ControlsImpl.IconImage {
                objectName: "islandPrivacyMicrophone"
                visible: island.kind !== "privacy" && island.privacy.microphone
                name: "audio-input-microphone-symbolic"
                color: Style.privacy.microphone
                sourceSize.width: Style.size.iconSm
                sourceSize.height: Style.size.iconSm
                Layout.alignment: Qt.AlignVCenter
                Accessible.name: qsTr("Microfone em uso")
            }
            ControlsImpl.IconImage {
                objectName: "islandPrivacyCamera"
                visible: island.kind !== "privacy" && island.privacy.camera
                name: "camera-web-symbolic"
                color: Style.privacy.camera
                sourceSize.width: Style.size.iconSm
                sourceSize.height: Style.size.iconSm
                Layout.alignment: Qt.AlignVCenter
                Accessible.name: qsTr("Câmera em uso")
            }
        }

        // Expanded activity with its controls.
        ColumnLayout {
            id: expandedContent
            objectName: "islandExpanded"
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: Style.space.lg
            spacing: Style.space.md
            opacity: island.look === "expanded" ? 1 : 0
            visible: island.look === "expanded" || opacity > 0
            Behavior on opacity { NumberAnimation { duration: Style.duration(Style.motion.normal, island.reducedMotion) } }

            // Music: cover, title and artist, progress and transport.
            RowLayout {
                visible: island.kind === "media"
                Layout.fillWidth: true
                spacing: Style.space.md
                Item {
                    Layout.preferredWidth: Style.size.target + Style.space.sm
                    Layout.preferredHeight: Style.size.target + Style.space.sm
                    Rectangle {
                        anchors.fill: parent
                        visible: !expandedCover.visible
                        radius: Style.radius.control
                        color: Style.alpha(island.scheme.text, Style.state.selected)
                        ControlsImpl.IconImage {
                            anchors.centerIn: parent
                            name: "audio-x-generic-symbolic"
                            color: island.scheme.textMuted
                            sourceSize.width: Style.size.iconLg
                            sourceSize.height: Style.size.iconLg
                        }
                    }
                    CoverArt {
                        id: expandedCover
                        objectName: "islandExpandedCover"
                        anchors.fill: parent
                        url: island.kind === "media" ? island.shownActivity.artUrl : ""
                        cornerRadius: Style.radius.control
                    }
                    // The cover opens the player, as in the dock's music popup.
                    MouseArea {
                        objectName: "islandRaisePlayer"
                        anchors.fill: parent
                        enabled: island.interactive && Boolean(island.mediaController && island.mediaController.canRaise)
                        cursorShape: Qt.PointingHandCursor
                        onClicked: island.mediaController.raise()
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Style.space.xxs
                    Text {
                        objectName: "islandMediaTitle"
                        Layout.fillWidth: true
                        text: island.kind === "media" ? island.shownActivity.title || qsTr("Sem título") : ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: Style.type.body
                        font.weight: Style.weight.demiBold
                        color: island.scheme.text
                    }
                    Text {
                        objectName: "islandMediaArtist"
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: island.kind === "media" ? island.shownActivity.artist : ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        font.pixelSize: Style.type.caption
                        color: island.scheme.textMuted
                    }
                }
            }
            ColumnLayout {
                objectName: "islandMediaProgress"
                visible: island.kind === "media" && Boolean(island.mediaController) && island.mediaController.lengthUs > 0
                Layout.fillWidth: true
                spacing: Style.space.xxs
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Style.space.xs
                    radius: height / 2
                    color: Style.alpha(island.scheme.text, Style.state.selected)
                    Rectangle {
                        width: parent.visible && island.mediaController && island.mediaController.lengthUs > 0
                            ? parent.width * island.mediaController.positionUs / island.mediaController.lengthUs : 0
                        height: parent.height
                        radius: height / 2
                        color: island.scheme.text
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: island.mediaController ? island.mediaController.timeText(island.mediaController.positionUs) : ""
                        textFormat: Text.PlainText
                        font.pixelSize: Style.type.caption
                        font.features: ({"tnum": 1})
                        color: island.scheme.textMuted
                    }
                    Item { Layout.fillWidth: true }
                    Text {
                        text: island.mediaController ? island.mediaController.timeText(island.mediaController.lengthUs) : ""
                        textFormat: Text.PlainText
                        font.pixelSize: Style.type.caption
                        font.features: ({"tnum": 1})
                        color: island.scheme.textMuted
                    }
                }
                // libkmpris only refreshes the position when asked.
                Timer {
                    interval: 1000
                    repeat: true
                    running: island.look === "expanded" && island.kind === "media" && island.shownActivity.playing
                    triggeredOnStart: true
                    onTriggered: if (island.mediaController) island.mediaController.refreshPosition()
                }
            }
            RowLayout {
                visible: island.kind === "media"
                Layout.alignment: Qt.AlignHCenter
                spacing: Style.space.lg
                IslandButton {
                    objectName: "islandPrevious"
                    iconName: "media-skip-backward-symbolic"
                    text: qsTr("Faixa anterior")
                    enabled: island.interactive && Boolean(island.mediaController && island.mediaController.canPrevious)
                    onClicked: island.mediaController.previous()
                }
                IslandButton {
                    objectName: "islandPlayPause"
                    prominent: true
                    iconName: island.kind === "media" && island.shownActivity.playing
                        ? "media-playback-pause-symbolic" : "media-playback-start-symbolic"
                    text: island.kind === "media" && island.shownActivity.playing ? qsTr("Pausar") : qsTr("Tocar")
                    enabled: island.interactive && Boolean(island.mediaController && island.mediaController.canPlayPause)
                    onClicked: island.mediaController.playPause()
                }
                IslandButton {
                    objectName: "islandNext"
                    iconName: "media-skip-forward-symbolic"
                    text: qsTr("Próxima faixa")
                    enabled: island.interactive && Boolean(island.mediaController && island.mediaController.canNext)
                    onClicked: island.mediaController.next()
                }
            }

            // Pomodoro: the phase, the time left and its two actions.
            RowLayout {
                visible: island.kind === "timer"
                Layout.fillWidth: true
                spacing: Style.space.md
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        objectName: "islandTimerPhase"
                        text: island.kind === "timer" && island.shownActivity.isBreak ? qsTr("Pausa") : qsTr("Foco")
                        textFormat: Text.PlainText
                        font.pixelSize: Style.type.caption
                        color: island.timerTint
                    }
                    Text {
                        objectName: "islandTimerClock"
                        text: island.kind === "timer" ? Island.clock(island.shownActivity.secondsLeft) : ""
                        textFormat: Text.PlainText
                        font.pixelSize: Style.type.headline
                        font.weight: Style.weight.demiBold
                        font.features: ({"tnum": 1})
                        color: island.scheme.text
                    }
                }
                IslandButton {
                    objectName: "islandTimerToggle"
                    iconName: "media-playback-pause-symbolic"
                    text: qsTr("Pausar o Pomodoro")
                    enabled: island.interactive && Boolean(island.timerController)
                    onClicked: island.timerController.toggle()
                }
                IslandButton {
                    objectName: "islandTimerReset"
                    iconName: "edit-reset-symbolic"
                    text: qsTr("Reiniciar o Pomodoro")
                    enabled: island.interactive && Boolean(island.timerController)
                    onClicked: island.timerController.reset()
                }
            }

            // Meeting: title, time and how soon it starts.
            RowLayout {
                visible: island.kind === "meeting"
                Layout.fillWidth: true
                spacing: Style.space.md
                ControlsImpl.IconImage {
                    name: "appointment-soon-symbolic"
                    color: island.scheme.accent
                    sourceSize.width: Style.size.iconLg
                    sourceSize.height: Style.size.iconLg
                    Layout.alignment: Qt.AlignTop
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Style.space.xxs
                    Text {
                        objectName: "islandMeetingTitle"
                        Layout.fillWidth: true
                        text: island.kind === "meeting" ? island.shownActivity.title || qsTr("Sem título") : ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        maximumLineCount: 2
                        wrapMode: Text.Wrap
                        font.pixelSize: Style.type.body
                        font.weight: Style.weight.demiBold
                        color: island.scheme.text
                    }
                    Text {
                        objectName: "islandMeetingTime"
                        Layout.fillWidth: true
                        text: island.kind === "meeting"
                            ? island.meetingSpan(island.shownActivity) + " · " + island.meetingWhen(island.shownActivity) : ""
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        font.pixelSize: Style.type.caption
                        color: island.scheme.textMuted
                    }
                }
            }

            // Microphone and camera in use, one line each.
            Repeater {
                model: island.kind === "privacy" ? [
                    {key: "microphone", icon: "audio-input-microphone-symbolic", label: qsTr("Microfone em uso"), tint: Style.privacy.microphone},
                    {key: "camera", icon: "camera-web-symbolic", label: qsTr("Câmera em uso"), tint: Style.privacy.camera}
                ].filter(entry => island.shownActivity[entry.key]) : []
                RowLayout {
                    required property var modelData
                    objectName: "islandPrivacyRow"
                    Layout.fillWidth: true
                    spacing: Style.space.sm
                    ControlsImpl.IconImage {
                        name: modelData.icon
                        color: modelData.tint
                        sourceSize.width: Style.size.iconMd
                        sourceSize.height: Style.size.iconMd
                    }
                    Text {
                        Layout.fillWidth: true
                        text: modelData.label
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                        font.pixelSize: Style.type.body
                        color: island.scheme.text
                    }
                }
            }
        }
    }
}
