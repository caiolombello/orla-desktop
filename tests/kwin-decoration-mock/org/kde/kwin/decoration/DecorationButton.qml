import QtQuick
// Test double for KWin's DecorationButton: hover/press flags and the request.
Item {
    property int buttonType: 0
    property bool hovered: false
    property bool pressed: false
    property bool toggled: false
    function click() { decoration.requested = buttonType; }
}
