import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

// Uppercase overline that opens a group of settings. Keep the text short.
Controls.Label {
    Layout.fillWidth: true
    Layout.topMargin: Style.space.xs
    textFormat: Text.PlainText
    font.capitalization: Font.AllUppercase
    font.pixelSize: Style.type.overline
    font.weight: Style.weight.bold
    font.letterSpacing: Style.letterSpacing.overline
    opacity: 0.72
    elide: Text.ElideRight
}
