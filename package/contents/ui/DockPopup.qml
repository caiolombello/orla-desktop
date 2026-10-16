import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami
import "../code/Style.js" as Style

Item {
    id: popup
    required property var dock
    property string title: ""
    property real anchorX: dock ? dock.width / 2 : 0
    property var anchorControl: dock
    property bool nativeOpenActive: false
    property int _focusRestoreGeneration: 0
    property int _restoreTicket: 0
    property bool _restorePending: false
    readonly property bool _nativeFocusHeld: nativeDialog
        ? (nativeDialog.activeFocusItem !== undefined
            ? nativeDialog.activeFocusItem !== null : nativeDialog.active === true) : false
    readonly property bool interactionBusy: visible || nativeOpenActive || _restorePending
        || Boolean(nativeDialog && nativeDialog.visible) || _nativeFocusHeld
    onAnchorControlChanged: _focusRestoreGeneration++
    onDockChanged: _focusRestoreGeneration++
    readonly property bool nativeBackend: Boolean(dock && dock.nativePopups)
    readonly property real screenHeight: dock && dock.Screen.height > 0 ? dock.Screen.height : 640
    readonly property real maximumPopupHeight: Math.max(1, screenHeight - (dock ? dock.height : 0) - 30)
    readonly property alias popupSurface: surface
    readonly property alias background: surfaceBackground
    readonly property alias contentItem: surface.contentItem
    // Popups follow the system's lightness with Orla tones, so native KDE
    // controls inside them always match. The dock body keeps the user theme.
    readonly property var scheme: dock && dock.popupScheme !== undefined ? dock.popupScheme : Style.scheme("dark")
    readonly property alias nativeDialog: nativeLoader.item
    // Transparent room around the glass for its shadow; the dialog window
    // includes it, so spacing is measured between visible surfaces.
    readonly property int shadowMargin: Style.space.md + Style.space.xxs
    readonly property real glassEdge: dock && dock.glassTop !== undefined ? dock.glassTop : 0
    readonly property real edgeGap: Style.space.sm + Style.space.xxs
    readonly property bool lightScheme: Style.luminance(scheme.surface) > 0.4
    property alias popupType: fallback.popupType
    property real margins: -1
    default property alias body: bodyColumn.data
    signal aboutToShow()
    signal aboutToHide()
    signal opened()
    signal closed()
    parent: dock
    visible: false
    width: Style.size.popupWidth + 2 * shadowMargin
    implicitHeight: surface.implicitHeight
    height: Math.min(implicitHeight, maximumPopupHeight)
    // Typed hosts clear during teardown, before their owned facade is deleted.
    x: dock ? Math.max(0, Math.min(Math.max(0, dock.width - width), anchorX - width / 2)) : 0
    y: dock ? (dock.popAbove ? glassEdge + shadowMargin - edgeGap - height : dock.height - glassEdge - shadowMargin + edgeGap) : 0

    function openAt(control) {
        anchorControl = control || dock;
        anchorX = anchorControl.mapToItem(dock, anchorControl.width / 2, 0).x;
        open();
    }
    function open() {
        if (visible) return;
        if (nativeBackend) {
            surface.parent = nativeDialog.contentItem;
            // Dialog synchronizes mainItem sizes; reset the current facade budget.
            surface.width = Qt.binding(() => popup.width);
            surface.height = Qt.binding(() => popup.height);
            surface.visible = true;
            aboutToShow();
            nativeOpenActive = true;
            visible = true;
        } else fallback.open();
    }
    function close() {
        if (nativeBackend) {
            if (!visible) return;
            aboutToHide();
            visible = false;
        } else fallback.close();
    }

    Controls.Popup {
        id: fallback
        parent: popup.dock
        popupType: Controls.Popup.Window
        width: popup.width
        height: popup.height
        x: popup.x
        y: popup.y
        margins: popup.margins
        padding: 0
        focus: true
        closePolicy: Controls.Popup.CloseOnEscape | Controls.Popup.CloseOnPressOutside
        background: Item {}
        contentItem: popup.nativeBackend ? null : surface
        onAboutToShow: { surface.parent = fallback.background.parent; popup.visible = true; popup.aboutToShow(); }
        onAboutToHide: popup.aboutToHide()
        onOpened: popup.opened()
        onClosed: { popup.visible = false; popup.closed(); }
    }
    onVisibleChanged: {
        const generation = ++_focusRestoreGeneration;
        if (!nativeBackend || visible || !nativeOpenActive) return;
        const ticket = ++_restoreTicket;
        _restorePending = true;
        nativeOpenActive = false;
        // Keep the shared content owned by this facade while its host is hidden.
        surface.parent = popup;
        const control = anchorControl;
        const ownerWindow = control ? control.Window.window : null;
        closed();
        Qt.callLater(() => {
            try {
                // Close observers may cancel, reopen, rehost or choose a newer control.
                if (generation !== _focusRestoreGeneration || visible || nativeOpenActive
                    || anchorControl !== control || !Qt.isQtObject(control) || !Qt.isQtObject(ownerWindow)
                    || control.Window.window !== ownerWindow || !ownerWindow.visible || !ownerWindow.active
                    || !control.visible || !control.enabled) return;
                const focused = ownerWindow.activeFocusItem;
                if (focused && focused !== ownerWindow.contentItem && focused !== control
                    && focused.visible && focused.enabled) return;
                control.forceActiveFocus(Qt.PopupFocusReason);
            } finally {
                if (ticket === _restoreTicket) _restorePending = false;
            }
        });
    }
    Loader {
        id: nativeLoader
        objectName: "nativeDockPopupLoader"
        property var popupOwner: popup
        active: popup.nativeBackend
        source: active ? Qt.resolvedUrl("NativeDockPopup.qml") : ""
    }
    Controls.Pane {
        id: surface
        width: popup.width
        height: popup.height
        leftInset: popup.shadowMargin
        rightInset: popup.shadowMargin
        topInset: popup.shadowMargin
        bottomInset: popup.shadowMargin
        padding: Style.space.lg + popup.shadowMargin
        focus: true
        Keys.onEscapePressed: event => { popup.close(); event.accepted = true; }
        palette.window: popup.scheme.surface
        palette.windowText: popup.scheme.text
        palette.text: popup.scheme.text
        palette.buttonText: popup.scheme.text
        palette.base: popup.scheme.raised
        palette.alternateBase: popup.scheme.sunken
        palette.button: popup.scheme.raised
        palette.mid: popup.scheme.border
        palette.dark: popup.scheme.borderStrong
        palette.highlight: popup.scheme.accent
        palette.highlightedText: popup.scheme.onAccent
        palette.placeholderText: popup.scheme.textMuted
        palette.link: popup.scheme.accent
        Kirigami.Theme.inherit: false
        Kirigami.Theme.colorSet: Kirigami.Theme.Window
        Kirigami.Theme.backgroundColor: popup.scheme.surface
        Kirigami.Theme.alternateBackgroundColor: popup.scheme.raised
        Kirigami.Theme.textColor: popup.scheme.text
        Kirigami.Theme.disabledTextColor: popup.scheme.textMuted
        Kirigami.Theme.highlightColor: popup.scheme.accent
        Kirigami.Theme.highlightedTextColor: popup.scheme.onAccent
        Kirigami.Theme.linkColor: popup.scheme.accent
        Kirigami.Theme.focusColor: popup.scheme.focus
        Kirigami.Theme.hoverColor: popup.scheme.accent
        background: Item {
            GlassShadow {
                target: surfaceBackground
                radius: surfaceBackground.radius
                strength: popup.lightScheme ? Style.glass.shadowLight : Style.glass.shadowDark
                blur: popup.shadowMargin - Style.space.xs
                offset: Style.space.xs
            }
            Rectangle {
                id: surfaceBackground
                objectName: "dockPopupBackground"
                anchors.fill: parent
                color: popup.scheme.surface
                radius: Style.radius.popup
                border.width: 1
                border.color: popup.scheme.border
                GlassRim {
                    anchors.fill: parent
                    radius: parent.radius
                    light: popup.lightScheme
                }
            }
        }
        contentItem: ColumnLayout {
            spacing: Style.space.md
            Controls.Label {
                objectName: "dockPopupTitle"
                Layout.fillWidth: true
                visible: text.length > 0
                text: popup.title
                textFormat: Text.PlainText
                color: popup.scheme.text
                font.pixelSize: Style.type.title
                font.weight: Style.weight.bold
                wrapMode: Text.WordWrap
            }
            ColumnLayout { id: bodyColumn; Layout.fillWidth: true; spacing: Style.space.md }
        }
    }
}
