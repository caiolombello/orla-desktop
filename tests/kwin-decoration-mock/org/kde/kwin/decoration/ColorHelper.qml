import QtQuick
// Test double for Aurorae::ColorHelper: one window and one text color.
QtObject {
    enum BackgroundRole { NormalBackground }
    enum ForegroundRole { NormalText }
    function background(active, role) { return fixture.window; }
    function foreground(active, role) { return fixture.text; }
}
