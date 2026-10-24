import QtQuick
import QtQuick.Window

// Loads the Orla KWin decoration against the test double in kwin-decoration-mock.
Window {
    id: window
    width: 700
    height: 400
    visible: true
    color: "#000000"
    property alias decorationItem: loader.item
    QtObject {
        id: fixture
        objectName: "fixture"
        property var buttonsLeft: [7, 5, 6]   // close, minimize, maximize ("XIA")
        property var buttonsRight: []
        property color window: "#202326"
        property color text: "#fcfcfc"
    }
    QtObject {
        id: decoration
        objectName: "decorationFixture"
        property int requested: -1
        property Item titleItem: null
        property QtObject client: QtObject {
            objectName: "clientFixture"
            property bool active: true
            property bool maximized: false
            property string caption: "Janela sintética"
            property int width: 500
            property int height: 260
        }
        function installTitleItem(item) { titleItem = item; }
    }
    Loader {
        id: loader
        source: Qt.resolvedUrl("../themes/kwin-decoration/contents/ui/main.qml")
    }
}
