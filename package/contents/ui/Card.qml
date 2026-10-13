import QtQuick
import QtQuick.Controls as Controls
import "../code/Style.js" as Style

// Groups related content inside an Orla surface: raised fill, hairline border.
// Colors come from the inherited palette (base = raised, mid = border). Use
// `radius: Style.radius.module` for Control Center modules.
Controls.Frame {
    id: card
    property real radius: Style.radius.card
    padding: Style.space.md
    background: Rectangle {
        radius: card.radius
        color: card.palette.base
        border.width: 1
        border.color: card.palette.mid
    }
}
