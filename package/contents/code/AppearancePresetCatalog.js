.pragma library
.import "AppearancePreset.js" as Preset
.import "Style.js" as Style

var definitions = [
    {id:"essencial", base:"paper", reduced:true, radius:Style.radius.popup, spacing:5,
        colors:{muted:"#526170", border:"#788477"}, // design-exempt: reviewed essential theme-example payload tokens
        order:["clock", "systemBattery", "music", "pomodoro", "quota", "peripherals", "recording"], count:2},
    {id:"mare", base:"glass", reduced:false, radius:Style.radius.popup, spacing:5, colors:{},
        order:["clock", "music", "systemBattery", "pomodoro", "quota", "peripherals", "recording"], count:3},
    {id:"estudio", base:"midnight", reduced:true, radius:Style.radius.module, spacing:Style.space.sm, colors:{},
        order:["pomodoro", "music", "clock", "systemBattery", "quota", "peripherals", "recording"], count:4},
    {id:"jogo", base:"midnight", reduced:false, radius:Style.radius.popup, spacing:5,
        colors:{border:"#7f91b0"}, // design-exempt: reviewed mare theme-example payload token
        order:["music", "clock", "systemBattery", "pomodoro", "quota", "peripherals", "recording"], count:3},
    // Like the macOS Dock: frosted glass, larger icons close together, apps only.
    {id:"macos", base:"glass", reduced:false, radius:Style.radius.popup, spacing:Style.space.xs, iconSize:48, colors:{},
        order:["music", "clock", "systemBattery", "pomodoro", "quota", "peripherals", "recording"], count:0}
];

function payload(id) {
    const entry = definitions.find(option => option.id === id);
    if (!entry) return null;
    const theme = Style.dockTheme(entry.base);
    // The two palette overrides are the existing essential/mare theme examples.
    const tokens = Object.assign({foreground:theme.foreground, muted:theme.muted, accent:theme.accent,
        surface:theme.surface, border:theme.border, radius:entry.radius, spacing:entry.spacing,
        opacity:theme.opacity, iconSize:entry.iconSize || 42, reducedMotion:entry.reduced}, entry.colors);
    return Preset.validate({formatVersion:Preset.formatVersion, kind:Preset.kind,
        appearance:{formatVersion:Preset.formatVersion, baseTheme:entry.base, tokens:tokens},
        widgets:entry.order.map((key, index) => ({id:key, visible:index < entry.count}))}).value || null;
}

function entries() {
    return definitions.map(entry => ({id:entry.id, payload:payload(entry.id)}));
}
