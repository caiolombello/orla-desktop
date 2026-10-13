import QtQuick
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

Item {
    id: surface
    objectName: "localEventSurface"

    required property var eventState
    property color surfaceColor: Style.schemes.dark.surface
    property color borderColor: Style.schemes.dark.borderStrong
    property color foregroundColor: Style.schemes.dark.text
    property color mutedColor: Style.schemes.dark.textMuted
    property color accentColor: Style.schemes.dark.accent
    property int animationDuration: Style.motion.fast
    property alias closeControl: closeButton
    property bool closeOwnedFocus: false
    signal focusRestoreRequested()
    readonly property bool hasEvent: Boolean(eventState.current)
    readonly property int mode: width >= 144 ? 3 : width >= 80 ? 2 : width >= 56 ? 1 : width >= 48 ? 0 : -1
    readonly property string fullAccessibleName: hasEvent
        ? eventState.current.title + (eventState.current.detail ? ". " + eventState.current.detail : "") : ""
    readonly property string accessibleName: fullAccessibleName
    property real contentOpacity: hasEvent ? 1 : 0

    onHasEventChanged: {
        if (hasEvent) closeOwnedFocus = false;
        else if (closeOwnedFocus) {
            closeOwnedFocus = false;
            focusRestoreRequested();
        }
    }

    Accessible.ignored: !hasEvent
    Accessible.role: Accessible.Pane
    Accessible.name: fullAccessibleName
    Accessible.description: hasEvent ? qsTr("Confirmação local dentro do dock") : ""

    Connections {
        target: surface.eventState
        function onAnnouncementRequested(event) {
            if (!event) return;
            const name = event.accessibleName || (event.title
                + (event.detail ? ". " + event.detail : ""));
            surface.Accessible.announce(name, Accessible.Polite);
        }
    }
    Behavior on contentOpacity {
        enabled: surface.animationDuration > 0
        NumberAnimation { duration: surface.animationDuration; easing.type: Easing.OutCubic }
    }

    Rectangle {
        visible: surface.hasEvent
        anchors.fill: parent
        radius: Math.min(Style.radius.tile, height / 2)
        color: surface.surfaceColor
        border.color: surface.accentColor
        border.width: 1
        opacity: surface.contentOpacity
    }

    Text {
        id: glyph
        visible: surface.hasEvent && surface.mode !== 1
        anchors.left: parent.left
        anchors.leftMargin: surface.mode === 0 ? 6 : 8
        anchors.verticalCenter: parent.verticalCenter
        width: surface.mode === 0 ? 12 : 16
        text: surface.hasEvent ? "✓" : ""
        color: surface.accentColor
        font.pixelSize: surface.mode === 0 ? Style.type.body : Style.type.title
        font.bold: surface.hasEvent
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        Accessible.ignored: true
    }

    Text {
        visible: surface.hasEvent && surface.mode === 1
        anchors.left: parent.left
        anchors.leftMargin: 7
        anchors.right: closeButton.left
        anchors.rightMargin: 3
        anchors.verticalCenter: parent.verticalCenter
        text: surface.hasEvent ? qsTr("Fim") : ""
        color: surface.foregroundColor
        font.pixelSize: Style.type.overline
        font.bold: surface.hasEvent
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        Accessible.ignored: true
    }

    Text {
        id: oneLine
        objectName: "localEventOneLine"
        visible: surface.hasEvent && surface.mode === 2
        anchors.left: glyph.right
        anchors.leftMargin: 5
        anchors.right: closeButton.left
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        text: surface.hasEvent ? surface.eventState.current.title : ""
        color: surface.foregroundColor
        font.pixelSize: Style.type.caption
        font.bold: surface.hasEvent
        elide: Text.ElideRight
        textFormat: Text.PlainText
        Accessible.ignored: true
    }

    Column {
        visible: surface.hasEvent && surface.mode === 3
        anchors.left: glyph.right
        anchors.leftMargin: 6
        anchors.right: closeButton.left
        anchors.rightMargin: 5
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0
        Text {
            width: parent.width
            text: surface.hasEvent ? surface.eventState.current.title : ""
            color: surface.foregroundColor
            font.pixelSize: Style.type.caption
            font.bold: surface.hasEvent
            elide: Text.ElideRight
            textFormat: Text.PlainText
            Accessible.ignored: true
        }
        Text {
            width: parent.width
            visible: surface.hasEvent
            text: surface.hasEvent ? surface.eventState.current.detail : ""
            color: surface.mutedColor
            font.pixelSize: Style.type.overline
            elide: Text.ElideRight
            textFormat: Text.PlainText
            Accessible.ignored: true
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: surface.hasEvent
        acceptedButtons: Qt.AllButtons
        preventStealing: true
        onWheel: wheel => wheel.accepted = true
    }

    Controls.Button {
        id: closeButton
        objectName: "localEventClose"
        visible: surface.hasEvent
        enabled: surface.hasEvent
        anchors.right: parent.right
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        width: 24
        height: 24
        padding: 0
        text: "×"
        activeFocusOnTab: surface.hasEvent
        Accessible.ignored: !surface.hasEvent
        Accessible.name: surface.hasEvent ? qsTr("Fechar aviso %1").arg(surface.fullAccessibleName) : ""
        Accessible.description: surface.hasEvent ? qsTr("Descarta este aviso local") : ""
        onActiveFocusChanged: {
            if (activeFocus) surface.closeOwnedFocus = true;
            else if (surface.hasEvent) surface.closeOwnedFocus = false;
        }
        onClicked: surface.eventState.dismiss()
        Keys.onEscapePressed: surface.eventState.dismiss()
        Keys.onReturnPressed: surface.eventState.dismiss()
        Keys.onEnterPressed: surface.eventState.dismiss()
        background: Rectangle {
            radius: Style.radius.control
            color: closeButton.down ? Style.alpha(surface.foregroundColor, Style.state.pressed)
                : closeButton.hovered || closeButton.visualFocus ? Style.alpha(surface.foregroundColor, Style.state.hover) : "transparent"
            border.width: closeButton.visualFocus ? 2 : 0
            border.color: surface.accentColor
        }
        contentItem: Text {
            text: closeButton.text
            color: surface.foregroundColor
            font.pixelSize: Style.type.title
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
        }
    }
}
