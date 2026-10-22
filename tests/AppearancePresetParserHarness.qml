import QtQml
import "../package/contents/code/AppearancePreset.js" as Preset

QtObject {
    function parseResult(text) { return JSON.stringify(Preset.parse(text)); }
    function validateResult(value) { return JSON.stringify(Preset.validate(value)); }
    function captureResult(appearance, widgets) { return JSON.stringify(Preset.capture(appearance, widgets)); }
    function serialized(value) { return Preset.serialize(value); }
}
