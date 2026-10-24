import QtQuick
// Test double for KWin's Aurorae::Borders.
QtObject {
    property int left: 0
    property int right: 0
    property int top: 0
    property int bottom: 0
    property int title: 0
    function setAllBorders(value) { left = right = top = bottom = value; }
    function setBorders(value) { left = right = bottom = value; }
    function setSideBorders(value) { left = right = value; }
    function setTitle(value) { title = value; }
}
