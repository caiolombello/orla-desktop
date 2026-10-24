.pragma library

// Orla design tokens: the single source of visual truth for every surface.
// Canonical file: package/contents/code/Style.js. The bar and launcher carry
// byte-identical copies; edit this file, then run `python3 scripts/design.py sync`.
// Rules and examples: docs/DESIGN_SYSTEM.md. Keep this file plain JavaScript:
// no Qt, Kirigami or QML APIs, so CI can evaluate it without a desktop.

var version = 1;

// Brand primitives (docs/brand.md). UI code uses the semantic roles below.
var brand = {
    ink: "#111923",
    slate: "#283542",
    sea: "#69d7c2",
    deepSea: "#167361",
    foam: "#eaf4f1",
    paper: "#f4f0e8"
};

// Semantic roles for Orla-owned surfaces. Popups, cards and the launcher pick
// `dark` or `light` from the system color scheme so native KDE controls inside
// them always match; only the dock body follows the user's dock theme.
var schemes = {
    dark: {
        canvas: "#111923",       // launcher window, deepest layer
        surface: "#151f2a",      // popups and menus
        raised: "#1d2935",       // cards inside a surface
        sunken: "#0d141c",       // tracks, wells, input backgrounds
        border: "#2a3846",       // hairlines around surfaces and cards
        borderStrong: "#3b4c5e", // dividers that must stay visible
        rim: "#ffffff",          // 1px inner highlight, used at rimOpacity
        rimOpacity: 0.07,
        text: "#eaf4f1",
        textMuted: "#a5b4bf",
        accent: "#69d7c2",
        accentHover: "#8fe4d4",
        onAccent: "#0b2a27",
        focus: "#69d7c2",
        success: "#69d7c2",
        warning: "#f2b866",
        danger: "#ff9a8f"
    },
    light: {
        canvas: "#f4f0e8",
        surface: "#faf8f3",
        raised: "#ffffff",
        sunken: "#ebe6dc",
        border: "#ddd6c9",
        borderStrong: "#c6bdae",
        rim: "#ffffff",
        rimOpacity: 0.7,
        text: "#1c2530",
        textMuted: "#56626e",
        accent: "#167361",
        accentHover: "#0f5f50",
        onAccent: "#ffffff",
        focus: "#167361",
        success: "#167361",
        warning: "#8a5300",
        danger: "#b3261e"
    }
};

// Dock body defaults. They mirror Appearance.legacy(), which persists user
// tokens; scripts/design.py check keeps both in agreement.
var dockThemes = {
    glass: {scheme: "dark", foreground: "#edf1f9", muted: "#9da9bf", accent: "#69d7c2",
        surface: "#283542", border: "#3c4b65", opacity: 219 / 255},
    midnight: {scheme: "dark", foreground: "#edf1f9", muted: "#9da9bf", accent: "#69d7c2",
        surface: "#111923", border: "#3c4b65", opacity: 1},
    paper: {scheme: "light", foreground: "#252b35", muted: "#606c79", accent: "#167361",
        surface: "#f4f0e8", border: "#cec9bf", opacity: 1}
};

// 4 px grid. Prefer these steps over ad hoc numbers.
var space = {xxs: 2, xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32};

// Corner radii by role. The dock body radius is a user token (default 21).
// Nested shapes stay concentric: inner radius = outer radius - padding.
var radius = {xs: 4, sm: 6, control: 8, tile: 12, card: 14, module: 18, popup: 20, pill: 999};

// Dock geometry, macOS-like: artwork fills most of its slot, slots sit close
// together and the glass hugs the row. Slot height stays iconSize + 16.
var dock = {
    artwork: 6,         // app artwork = iconSize + artwork
    slotGap: 8,         // slot width = iconSize + slotGap
    glassInset: 4,      // glass edge, measured outward from the content lane
    glassPadding: 3,    // glass above and below the slot row
    iconRadius: 0.225,  // squircle corner ratio for live icons
    // With the Orla Plasma theme, the bottom panel frame's blur mask is the slab:
    // a rounded rectangle this far inside the frame (scripts/plasma_theme.py).
    systemGlassBandX: 10,
    systemGlassBandY: 12
};

// Glass treatment for Orla surfaces: a soft top sheen, a specular rim brighter at
// the top, a hairline and a shadow. Applets cannot ask KWin for blur themselves;
// the optional Orla Plasma theme supplies it (scripts/plasma_theme.py).
var glass = {
    sheenDark: 0.07, sheenLight: 0.4,
    rimTopDark: 0.28, rimTopLight: 0.9,
    rimBottomDark: 0.04, rimBottomLight: 0.35,
    shadowDark: 0.42, shadowLight: 0.16,
    shadowBlur: 18, shadowOffset: 5,
    highlight: "#ffffff", shade: "#000000",
    // With KWin blur behind (Orla Plasma theme): tint opacity of a translucent
    // dock, module fill and hairline inside blurred popups, and the theme's
    // dialog margin that popups subtract from their own padding.
    frostTint: 0.5, frostModule: 0.07, frostBorder: 0.09, frameMargin: 10
};

// Live widget icons: gradient squircles from the brand illustration palette.
// `ink` is the glyph/text color and must keep 3:1 against both stops (checked).
var iconTiles = {
    paper: {top: "#fbf9f4", bottom: "#e6dfd2", ink: "#1c2530", accent: "#167361"},
    coral: {top: "#d9736c", bottom: "#9c3f58", ink: "#ffffff", accent: "#ffffff"},
    sea: {top: "#2fa597", bottom: "#1d6f78", ink: "#ffffff", accent: "#ffffff"},
    deepSea: {top: "#3a97a6", bottom: "#17485a", ink: "#ffffff", accent: "#ffffff"},
    slate: {top: "#4f5f6d", bottom: "#253240", ink: "#ffffff", accent: "#69d7c2"},
    ink: {top: "#2b3747", bottom: "#111923", ink: "#eaf4f1", accent: "#69d7c2"}
};
var widgetTiles = {clock: "ink", pomodoro: "coral", music: "sea", systemBattery: "ink",
    quota: "slate", peripherals: "deepSea", recording: "ink", controlCenter: "slate"};
// Battery and quota rings change color as levels get critical.
var levels = {good: "#69d7c2", low: "#f2b866", critical: "#ff8a7a"};
function iconTile(kind) { return iconTiles[widgetTiles[kind] || "slate"]; }

// Type roles in logical pixels. Body copy keeps the system font size; set a
// pixel size only for these named roles.
var type = {
    overline: 10,   // section labels, uppercase with letterSpacing
    caption: 11,    // secondary lines, hints, metadata
    label: 12,      // compact control labels
    body: 13,       // custom Text that must match body copy
    title: 15,      // popup and card titles
    headline: 20,   // launcher brand line, large values
    display: 40     // single hero number (timer, battery)
};
var weight = {regular: 400, medium: 500, demiBold: 600, bold: 700};
var letterSpacing = {overline: 1.2};

// Component sizes.
var size = {
    control: 36,       // default button/field height
    target: 40,        // minimum primary target (launcher, Control Center)
    iconButton: 28,    // header and inline icon buttons
    iconSm: 16,
    iconMd: 20,
    iconLg: 28,
    ringStroke: 3,
    indicator: 4,      // running-app dot
    popupWidth: 350,
    divider: 1
};

// Motion. Multiply by motionScale(reducedMotion) so reduced motion is instant.
var motion = {fast: 120, normal: 180, slow: 260, hoverScale: 1.04, pressScale: 0.9, lift: 3, bounce: 10};
function duration(base, reducedMotion) { return reducedMotion ? 0 : base; }

// Overlay opacities applied to the current foreground color.
var state = {hover: 0.08, pressed: 0.14, selected: 0.16, chip: 0.05, disabled: 0.38};

function scheme(name) { return schemes[name === "light" ? "light" : "dark"]; }
function dockTheme(name) { return dockThemes[dockThemes[name] ? name : "glass"]; }

// Returns "#AARRGGBB", the QML color string with alpha first.
function alpha(color, opacity) {
    const hex = String(color).replace("#", "");
    const rgb = hex.length === 8 ? hex.slice(2) : hex;
    const value = Math.max(0, Math.min(255, Math.round(opacity * 255)));
    return "#" + (value < 16 ? "0" : "") + value.toString(16) + rgb.toLowerCase();
}

function channel(value) {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
function luminance(color) {
    const hex = String(color).replace("#", "");
    const rgb = hex.length === 8 ? hex.slice(2) : hex;
    return 0.2126 * channel(parseInt(rgb.slice(0, 2), 16))
        + 0.7152 * channel(parseInt(rgb.slice(2, 4), 16))
        + 0.0722 * channel(parseInt(rgb.slice(4, 6), 16));
}
function contrast(first, second) {
    const a = luminance(first), b = luminance(second);
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
// Picks the Orla scheme whose lightness matches a system background color.
function schemeFor(background) {
    return luminance(background) > 0.4 ? "light" : "dark";
}
