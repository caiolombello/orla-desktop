import QtQuick
import QtQuick.Controls as Controls

Item {
    id: surface
    objectName: "localEventSurface"

    required property var eventState
    property color surfaceColor: "#182231"
    property color borderColor: "#53647a"
    property color foregroundColor: "#f4f7fb"
    property color mutedColor: "#aeb9c8"
    property color accentColor: "#70d7c7"
    property int animationDuration: 120
    property alias closeControl: closeButton
    readonly property bool hasEvent: Boolean(eventState.current)
    readonly property int mode: width >= 144 ? 3 : width >= 80 ? 2 : width >= 56 ? 1 : width >= 48 ? 0 : -1
    readonly property string fullAccessibleName: hasEvent
        ? eventState.current.title + (eventState.current.detail ? ". " + eventState.current.detail : "")
        : qsTr("Eventos locais")
    readonly property string accessibleName: fullAccessibleName
    property real contentOpacity: hasEvent ? 1 : 0.72

    Accessible.role: Accessible.Pane
    Accessible.name: fullAccessibleName
    Accessible.description: hasEvent ? qsTr("Confirmação local dentro do dock") : qsTr("Área de eventos locais sem avisos")

    Connections {
        target: surface.eventState
        function onCurrentChanged() {
            if (surface.eventState.current) surface.Accessible.announce(surface.fullAccessibleName, Accessible.Polite);
        }
    }
    Behavior on contentOpacity {
        enabled: surface.animationDuration > 0
        NumberAnimation { duration: surface.animationDuration; easing.type: Easing.OutCubic }
    }

    Rectangle {
        anchors.fill: parent
        radius: Math.min(14, height / 2)
        color: surface.surfaceColor
        border.color: surface.hasEvent ? surface.accentColor : surface.borderColor
        border.width: 1
        opacity: surface.contentOpacity
    }

    Text {
        id: glyph
        visible: surface.mode !== 1
        anchors.left: parent.left
        anchors.leftMargin: surface.mode === 0 ? 6 : 8
        anchors.verticalCenter: parent.verticalCenter
        width: surface.mode === 0 ? 12 : 16
        text: surface.hasEvent ? "✓" : "•"
        color: surface.hasEvent ? surface.accentColor : surface.mutedColor
        font.pixelSize: surface.mode === 0 ? 13 : 15
        font.bold: surface.hasEvent
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        Accessible.ignored: true
    }

    Text {
        visible: surface.mode === 1
        anchors.left: parent.left
        anchors.leftMargin: 7
        anchors.right: closeButton.left
        anchors.rightMargin: 3
        anchors.verticalCenter: parent.verticalCenter
        text: surface.hasEvent ? qsTr("Fim") : "•"
        color: surface.foregroundColor
        font.pixelSize: 9
        font.bold: surface.hasEvent
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        Accessible.ignored: true
    }

    Text {
        id: oneLine
        objectName: "localEventOneLine"
        visible: surface.mode === 2
        anchors.left: glyph.right
        anchors.leftMargin: 5
        anchors.right: closeButton.left
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        text: surface.hasEvent ? surface.eventState.current.title : qsTr("Eventos")
        color: surface.hasEvent ? surface.foregroundColor : surface.mutedColor
        font.pixelSize: 11
        font.bold: surface.hasEvent
        elide: Text.ElideRight
        textFormat: Text.PlainText
        Accessible.ignored: true
    }

    Column {
        visible: surface.mode === 3
        anchors.left: glyph.right
        anchors.leftMargin: 6
        anchors.right: closeButton.left
        anchors.rightMargin: 5
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0
        Text {
            width: parent.width
            text: surface.hasEvent ? surface.eventState.current.title : qsTr("Eventos locais")
            color: surface.hasEvent ? surface.foregroundColor : surface.mutedColor
            font.pixelSize: 11
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
            font.pixelSize: 9
            elide: Text.ElideRight
            textFormat: Text.PlainText
            Accessible.ignored: true
        }
    }

    Controls.Button {
        id: closeButton
        objectName: "localEventClose"
        anchors.right: parent.right
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        width: 24
        height: 24
        padding: 0
        text: "×"
        activeFocusOnTab: true
        Accessible.name: surface.hasEvent ? qsTr("Fechar aviso %1").arg(surface.fullAccessibleName) : qsTr("Fechar eventos")
        Accessible.description: surface.hasEvent ? qsTr("Descarta este aviso local") : qsTr("Nenhum aviso para descartar")
        onClicked: surface.eventState.dismiss()
        Keys.onEscapePressed: surface.eventState.dismiss()
        Keys.onReturnPressed: surface.eventState.dismiss()
        Keys.onEnterPressed: surface.eventState.dismiss()
        background: Rectangle {
            radius: 8
            color: closeButton.down ? Qt.rgba(0.5, 0.6, 0.8, 0.26)
                : closeButton.visualFocus ? Qt.rgba(0.5, 0.6, 0.8, 0.14) : "transparent"
            border.width: closeButton.visualFocus ? 2 : 0
            border.color: surface.accentColor
        }
        contentItem: Text {
            text: closeButton.text
            color: surface.foregroundColor
            font.pixelSize: 16
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
        }
    }
}
