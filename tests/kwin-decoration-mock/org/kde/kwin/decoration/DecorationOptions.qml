import QtQuick
// Test double for Aurorae::DecorationOptions; tests set the button lists.
QtObject {
    enum DecorationButton {
        DecorationButtonNone, DecorationButtonMenu, DecorationButtonApplicationMenu,
        DecorationButtonOnAllDesktops, DecorationButtonQuickHelp, DecorationButtonMinimize,
        DecorationButtonMaximizeRestore, DecorationButtonClose, DecorationButtonKeepAbove,
        DecorationButtonKeepBelow, DecorationButtonShade, DecorationButtonResize,
        DecorationButtonExplicitSpacer
    }
    property var deco
    property var titleButtonsLeft: fixture.buttonsLeft
    property var titleButtonsRight: fixture.buttonsRight
    property font titleFont: Qt.font({family: "Sans", pointSize: 10})
}
