import QtQuick
// Test double for KWin's Decoration base item; sizes follow the fake client.
Item {
    property QtObject borders: Borders {}
    property QtObject maximizedBorders: Borders {}
    property QtObject extendedBorders: Borders {}
    property QtObject padding: Borders {}
    property bool alpha: true
    width: decoration.client.width + 2 + (decoration.client.maximized ? 0 : padding.left + padding.right)
    height: decoration.client.height + borders.title + 1 + (decoration.client.maximized ? 0 : padding.top + padding.bottom)
}
