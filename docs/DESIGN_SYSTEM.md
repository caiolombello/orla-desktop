# Orla design system

How Orla looks, and the rules that keep it looking that way when people and AI
agents change it. [brand.md](brand.md) defines identity; [UX_UI.md](UX_UI.md) defines
product behavior. This file is the visual contract for code.

Every value lives in one file: [`package/contents/code/Style.js`](../package/contents/code/Style.js).
The bar (`bar/contents/code/Style.js`) and launcher (`launcher/Style.js`) carry
byte-identical copies. `python3 scripts/design.py check` fails the build when a copy
drifts, a QML file hardcodes a style value, or a color pair loses contrast.

## Direction

Modern macOS composition (the current glass era) in Orla's own coastal identity:
dark ink, sea-glass accent, warm paper, and the brand's illustration gradients.
Composition and feel are macOS-like; marks, icons and assets are Orla's own (no Apple
symbols, wallpapers or app icons).

- **The dock is icons only.** A glass slab hugs one row of artwork. Apps show their
  theme icon; widgets are *live icons* (gradient squircles that draw their data).
  No text inside the dock: names and details live in the hover label and tooltips.
- **Glass, not boxes.** Surfaces are translucent-looking slabs with a soft top sheen,
  a specular 1 px rim that is brightest at the top, a hairline and a soft shadow.
  Large, concentric corners. Never a panel frame around a panel frame.
- **Popovers and modules.** Popups are floating glass popovers without close buttons
  (Esc and clicking outside close them). Related controls sit in rounded modules,
  Control Center style: capsule sliders, round toggles, grouped settings lists.
- **One accent per surface**, for the selection, the primary action and progress.

## Where color comes from

| Surface | Source | Why |
|---|---|---|
| Dock glass and its separators | The user's dock tokens (`appearance.effective.tokens`; defaults in `Style.dockThemes`) | The dock is what people customize |
| Live widget icons | `Style.iconTiles` via `Style.widgetTiles` (and `Style.levels` for rings) | Fixed artwork, like app icons |
| Popovers, menus, cards, the hover label | `dock.popupScheme` = `Style.scheme(Style.schemeFor(system background))` | Native KDE controls follow the system scheme; matching its lightness keeps them consistent |
| Bar | Plasma's palette (`palette.window`, `palette.windowText`, `palette.highlight`) | It sits in a Plasma panel |
| Launcher | `Style.scheme("dark")` as `ui` | A dark overlay in every system scheme |

`DockPopup` applies its scheme to both `palette` and `Kirigami.Theme`, so `Label`,
`OrlaButton`, `OrlaIconButton`, `Card`, `FormRow` and `SegmentedTabs` inside it inherit
the right colors. Do not pass dock tokens (`root.foreground`, `root.muted`) into popup
content; use `root.popupScheme` or the `popupContext` object.

### Scheme roles

| Role | Use |
|---|---|
| `canvas` | Deepest background (launcher window) |
| `surface` | Popovers and menus |
| `raised` | Cards, modules and inputs on a surface (`palette.base`) |
| `sunken` | Tracks, wells, text areas |
| `border` / `borderStrong` | Hairlines / dividers that must stay visible |
| `rim` + `rimOpacity` | 1 px inner highlight on surfaces |
| `text` / `textMuted` | Primary and secondary copy (both ≥ 4.5:1 on every background) |
| `accent` / `accentHover` / `onAccent` | Selection, primary action, progress; text on accent |
| `focus` | Focus rings |
| `success` / `warning` / `danger` | States, always with a label or icon |

Translucency derives from a role: `Style.alpha(role, opacity)` returns the QML
`#AARRGGBB` string. Hover, pressed and chip fills use `Style.state.*` opacities over
the current foreground, so they work on light and dark surfaces alike.

## Tokens

| Group | Values | Notes |
|---|---|---|
| `Style.space` | `xxs 2, xs 4, sm 8, md 12, lg 16, xl 20, xxl 24, xxxl 32` | 4 px grid |
| `Style.radius` | `xs 4, sm 6, control 8, tile 12, card 14, module 18, popup 20, pill 999` | Nested shapes stay concentric (inner = outer − padding). The dock radius is the user token (default 21) |
| `Style.dock` | `artwork 6, slotGap 8, glassInset 4, glassPadding 3, iconRadius 0.225` | Slot width `iconSize + slotGap`, slot height `iconSize + 16`, app artwork `iconSize + artwork`, live squircle `iconSize + 2` |
| `Style.glass` | sheen, rim and shadow strengths for dark/light, `shadowBlur`, `shadowOffset`, `highlight`, `shade` | Used by `GlassRim` and `GlassShadow` |
| `Style.iconTiles` / `Style.widgetTiles` / `Style.levels` | Gradient squircle palettes, the widget → palette map, ring colors by level | `ink` keeps ≥ 3:1 on both gradient stops (checked) |
| `Style.type` | `overline 10, caption 11, label 12, body 13, title 15, headline 20, display 40` | Body copy keeps the system font; set `pixelSize` only for these roles |
| `Style.weight` | `regular 400, medium 500, demiBold 600, bold 700` | Popover titles bold; overlines bold uppercase with `Style.letterSpacing.overline` |
| `Style.size` | `control 36, target 40, iconButton 28, ringStroke 3, indicator 4, popupWidth 350` | Primary targets in the launcher and Control Center are ≥ 40 px |
| `Style.motion` | `fast 120, normal 180, slow 260, hoverScale 1.04, pressScale 0.9, lift 3, bounce 10` | Use the dock's `motion` (0 under reduced motion) or `Style.duration(base, reducedMotion)` |
| `Style.state` | `hover .08, pressed .14, selected .16, chip .05, disabled .38` | Overlay opacities |

Numbers show tabular figures with `font.features: {"tnum": 1}` (timer, percentages).

## Dock anatomy

- **Slots.** `Tile` is the only dock control. Artwork sits slightly above center so the
  running dot fits underneath. No hover box: hover lifts the artwork 3 px and scales it
  to 1.04 (it must stay inside its slot); press scales to 0.9; keyboard focus shows a
  2 px accent ring around the artwork.
- **State.** Running apps get a 4 px dot (55 % opacity, full for the active window,
  warning color for attention). Launching and attention bounce the artwork
  (`Style.motion.bounce`), never under reduced motion.
- **Glass.** `dockSurface` hugs the slot row (`glassHeight`, centered), keeps the
  user's color, radius, border and opacity, and adds `GlassRim` plus `GlassShadow`.
  The applet area outside it is transparent.
- **Separators.** One hairline before the widgets (`widgetDivider`). The Orla slot,
  like Finder, has none.
- **Labels.** In Plasma, `DockLabel` floats the hovered slot's `tooltip` above the
  artwork with no delay and never takes focus. Fixtures keep the Controls tooltip.
- **Host panel.** When the dock is the only widget of a panel, `main.qml` hides that
  panel's frame (`backgroundHints = NoBackground`, not saved) so frames never stack;
  it restores the frame when another widget joins or the dock leaves.

### Live icons

`LiveIcon` faces: analog `clock`; ring faces for `pomodoro`, `systemBattery`, `quota`
and `peripherals` (ring = progress, center = a short value of at most three
characters, glyph when idle); `music` (local album art when the player offers a
`file:` URL, otherwise a note, with a play/pause badge); `recording` (pulsing dot);
`controlCenter` (two toggles). Rules:

- Squircle corner = `size × Style.dock.iconRadius`; gradient from `Style.iconTiles`.
- Show data, not sentences. Titles and details go to `title`/`subtitle`/`tooltip`.
- Never fetch remote images; only local artwork is drawn.
- New widget → add a palette in `widgetTiles` and a face, then check both schemes.

## Components

All live in `package/contents/ui/`. Reuse them before writing a new one.

| Component | Use it for | Key properties |
|---|---|---|
| `Tile` | Every dock slot | `iconSource` or `liveKind` + `liveInfo` + `live`, `running`/`activeTask`/`attention`/`launching`, `tooltip`, `nativeLabel` |
| `LiveIcon` | Widget artwork (also the Control Center "now playing") | `kind`, `info`, `live`, `now` |
| `GlassRim` | Sheen + specular rim inside any glass surface | `radius`, `light` |
| `GlassShadow` | Soft shadow behind a sibling surface (layered, cheap to resize) | `target`, `radius`, `strength`, `blur`, `offset` |
| `DockPopup` | Every dock popover (glass, shadow margin, title, no close button) | `title`; body is the default property; `shadowMargin`, `edgeGap` |
| `DockLabel` | The floating name label (native only) | follows `dock.labelTarget` |
| `ProgressRing` | Circular progress (timer, battery, quota) | `progress`, `color`, `trackColor`, `lineWidth` |
| `Card` | Groups and Control Center modules | `radius` (`Style.radius.module` for modules) |
| `FormRow` | One row of a grouped settings list inside `Card { padding: 0 }` | `last` |
| `OrlaButton` | Text actions | `variant`: `primary` (at most one per surface), `secondary`, `ghost` |
| `OrlaIconButton` | Round toggles (mute) | `iconName`, `checked`; `text` is the accessible name |
| `SegmentedTabs` + `SegmentTab` | Switching sections in a popover | `TabBar` API (`currentIndex`) |
| `SectionLabel` | Opening a group of settings | Short text; rendered uppercase |
| `EventSurface` | In-dock confirmations | Geometry is test-pinned; change colors only through tokens |

Native `Controls` (TextField, ComboBox, SpinBox, CheckBox) stay native inside Orla
surfaces so keyboard, input methods and accessibility keep KDE behavior. Sliders keep
`Controls.Slider` semantics with an Orla capsule `background`/`handle`.

## Other surfaces

- **Launcher (Spotlight-like).** Frameless, transparent window; the visible part is a
  rounded glass panel inside a shadow margin. `WindowSession.setBlurRegion()` asks KWin
  to blur behind that panel. Search is a capsule with a magnifier; results show the
  app's own theme icon (`iconName` from KRunner, drawn with `IconImage`) and the
  selected row is filled with the accent. The header drags the window.
- **Appearance.** Keep presets and portable JSON behind the initially collapsed
  “Presets e aparência portátil” control. Names and current preview status stay
  visible; a saved preset identity must never be inferred. Basic themes and
  form/motion precede advanced colors/theme JSON. Pending or invalid input reveals
  its editor and keeps recovery reachable. Collapsing moves focused descendants
  before hiding them; cancel/reopen resets only presentation state. Preserve the
  fixed footer and popup budget; use the short-screen gallery in both schemes.
- **Widget ordering.** Keep the grip, native checkbox and keyboard arrow actions
  together in each grouped row. A held drag shows one insertion line and writes
  nothing; only a valid release saves. Escape first cancels the gesture. Reveal
  the whole focused row so the destination is visible in a short viewport. Keep
  wrapped labels and native font/target sizes at 350 and 420 px. Closing editing
  invalidates the gesture before any popup exit animation finishes.
  Expose each row as a named accessible group while keeping its checkbox and
  buttons as children. Name the existing ScrollView and its clipped content
  viewport; do not substitute the card or outer panel bounds for that viewport.
  Focus on any row control reveals the whole row, including its grip and arrows.
- **Bar.** Menu-bar style: a monochrome Orla mark in the text color, the bold app
  name, compact menus (rows `Style.size.control − 10`, radius `Style.radius.sm`).
  Panel margins can leave a 24 px applet viewport inside a 32 px panel. Fit the
  buttons, glyphs and focus rings to the allocated height; keep the preferred
  28/32 px sizes and the 20 px menu mark. Adapt vertical padding within the panel
  budget while preserving the system font. Review the short-host gallery in both schemes.

## Icons

- Widget and status glyphs use Breeze `*-symbolic` names. Check that a name exists:
  `find /usr/share/icons/breeze -name '<name>.svg'`.
- App icons are never masked or tinted.
- No text glyphs as icons in new code where a symbolic icon exists.

## Rules

Do:
- Take every color, size, radius, duration and opacity from `Style.js` or from the dock tokens.
- Keep one primary action per surface and put it first in keyboard order.
- Show state with text or an icon as well as color.
- Give every interactive control a visible focus ring (2 px, accent/highlight).
- Respect reduced motion: animations use the dock `motion` or `Style.duration(...)`.
- Keep strings plain text (`textFormat: Text.PlainText`) and bounded.

Don't:
- Hardcode `#hex`, named colors, `Qt.rgba(...)`, numeric `pixelSize` or non-zero numeric `radius` in QML.
- Put text inside the dock or draw a frame around the dock's glass.
- Draw shadows with a blurred `Canvas` on surfaces that resize (popovers, the dock):
  every resize repaints on the CPU. Use `GlassShadow`.
- Let a shadow spread beyond the transparent margin that holds it; the window edge
  would cut it.
- Import `org.kde.*` in files loaded by portable CI tests (`AppearanceEditor`, `AppearanceState`,
  `OrlaButton`, `SectionLabel`, `FormRow`, `Card`, `EventState`, `AudioControlState`,
  profile/context state, `BarView`).
- Hide `Kirigami.Theme` samplers with `visible: false`; hidden items report black.
- Change test-pinned geometry (event slot math, the `+24` lane width, popup budgets) to
  make something look better; redesign within it or update the test with a stated reason.

A line that must break a rule carries `// design-exempt: <reason>`; reviewers check the reason.

## Workflow for UI changes

1. Edit QML using the tokens and components above.
2. `python3 scripts/design.py check` — must print `design check: ok`.
3. `python3 scripts/design.py gallery` — renders every surface with synthetic data to
   `.runtime/design-gallery/` (`index.png` is the contact sheet). Each system scheme
   renders in a private Breeze Dark / Breeze Light config, so dark and light popovers
   look exactly as they would on that desktop. Open the images and compare before/after.
4. Run the affected QML suites (see [CONTRIBUTING.md](../CONTRIBUTING.md)); for
   launcher QML or C++, build it and run its CTests (see [launcher/README.md](../launcher/README.md)).
5. In the pull request, attach gallery captures for both schemes and mention any
   `design-exempt` lines.

## Changing tokens

Edit the canonical `Style.js`, then `python3 scripts/design.py sync` and `check`.
The check enforces 4.5:1 for text, accent, warning and danger on every scheme
background, `onAccent` on `accent`, 3:1 for live icon ink on both gradient stops, and
that `Style.dockThemes` matches the persisted defaults in `Appearance.legacy()`.
Update this document in the same change.
