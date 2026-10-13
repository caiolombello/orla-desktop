# Orla Desktop — agent rules

Orla Desktop is a modular KDE Plasma workspace: the Orla Dock applet, an optional
top-bar menu, and a separately built launcher. Alpha software; MIT licensed.
Read this file first, then [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) before any UI change.

## Stack
- KDE Plasma 6.7+, Qt 6.11.2 / Qt Quick, KDE Frameworks 6.30 (Kirigami, TaskManager, PlasmaCore).
- QML + `.pragma library` JavaScript for applets; C++17 + CMake 3.24 for the launcher.
- Python 3.10+ helpers and tests; PySide6 6.11+ (CI pins 6.12) drives QML tests offscreen.

## Map
- `package/` — Orla Dock applet (`org.caiodock.dock`). `contents/ui/*.qml` components,
  `contents/code/*.js` pure logic and the design tokens (`Style.js`).
- `package/contents/controlcenter/` — package-local, experimental routing singleton.
  The dock owns the single view/audio state; bar clients borrow a popup host only.
- `bar/` — Menu Orla top bar (`org.orla.bar`), source-only.
- `launcher/` — Orla Launcher (C++/Qt Quick), its own CMake build and CTests.
- `scripts/` — `orla.py` (doctor/build/install/preview/layout), `release.py`, `design.py`, helpers.
- `tests/` — Python unittest suites plus `*Harness.qml` fixtures; `design_gallery.py` renders captures.
- `docs/` — product, UX, brand, design system and validation records. `.runtime/` is scratch (gitignored).

## Commands
- Design check (always, after any QML/JS UI edit): `python3 scripts/design.py check`
- Visual review: `python3 scripts/design.py gallery` → `.runtime/design-gallery/index.png`
- Sync token copies after editing `package/contents/code/Style.js`: `python3 scripts/design.py sync`
- One QML suite: `PYTHONPATH=tests QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Fusion python3 -B -m unittest test_qml`
- Dock UI suites: `test_qml test_widget_strip test_appearance test_control_center test_local_events test_profiles_dock test_contexts_dock test_calendar test_media`
- Bar suite: `python3 bar/run_tests.py` (add `--style org.kde.desktop` when the KDE style is installed)
- Shared controls: `PYTHONPATH=tests QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software python3 -B -m unittest test_shared_control_center_registry test_control_center_session`;
  `test_shared_control_center` additionally needs the local KDE QML modules.
- Design guards: `python3 -B -m unittest discover -s tests -p 'test_design_system.py'`
- Build the applet: `python3 scripts/orla.py build`; release bundle: `python3 scripts/release.py`
- Portable CI list: `.github/workflows/ci.yml`. Run the QML suites with both `Fusion` and
  `org.kde.desktop` styles when touching shared controls.

## UI rules (summary of docs/DESIGN_SYSTEM.md)
- Direction: modern macOS composition in Orla's own identity. The dock is icons only on a
  glass slab (widgets are live squircle icons, names live in the hover label); popups are
  glass popovers without close buttons; settings and Control Center use rounded modules,
  capsule sliders, round toggles and grouped lists; the launcher is Spotlight-like.
- Every color, font size, radius, spacing step, duration and opacity comes from
  `Style.js` (`Style.scheme(...)`, `Style.space`, `Style.radius`, `Style.type`,
  `Style.dock`, `Style.glass`, `Style.iconTiles`, `Style.motion`, `Style.state`,
  `Style.alpha`) or from the user's dock tokens. `design.py check` rejects hex colors,
  named colors, `Qt.rgba`, numeric `pixelSize` and non-zero numeric `radius` in QML.
- Dock glass = user dock theme. Popovers/cards = `dock.popupScheme` (system lightness).
  Bar = Plasma palette. Launcher = dark scheme (`ui`). Live icons = `Style.iconTiles`.
- Reuse `Tile`, `LiveIcon`, `GlassRim`, `GlassShadow`, `DockPopup`, `ProgressRing`, `Card`,
  `FormRow`, `OrlaButton`, `OrlaIconButton`, `SegmentedTabs`/`SegmentTab`, `SectionLabel`
  before creating a component. At most one `primary` button per surface.
- No text inside the dock and no frame around its glass. Shadows use `GlassShadow`
  (layered), never a blurred Canvas on surfaces that resize.
- Widget/status icons: Breeze `*-symbolic`, tinted. Never tint app icons.
- Keep native `Controls` (TextField, ComboBox, SpinBox, CheckBox) inside Orla surfaces.
- Show state with text or icon, not color alone; keep a visible 2 px focus ring; honor reduced motion.
- Strings are PT-BR through `qsTr`, rendered with `textFormat: Text.PlainText`, and bounded.
- A rule break needs `// design-exempt: <reason>` on that line.
- After a UI change, look at the gallery in both schemes before calling it done.

## Code conventions
- Separate state from presentation: `*State.qml` owns data and rules; views bind to it.
- Pure logic goes in `contents/code/*.js` (`.pragma library`), no QML or Kirigami APIs.
- Give testable controls an `objectName`; tests find them by name, not by tree position.
- Inject fixtures through existing `*Override` / backend properties, never through globals.
- Files loaded by portable CI harnesses (`AppearanceEditor`, `AppearanceState`, `OrlaButton`,
  `SectionLabel`, `FormRow`, `Card`, `EventState`, `AudioControlState`, profile/context state,
  `BarView`, shared Registry/Entry/Session) must not import `org.kde.*`; CI has PySide6 only.
- Shared CC transfers must fully close before changing host. Preserve exact-client release,
  newer requests and newer focus; never add a second audio backend to the bar.
- Comments explain why, briefly. Match the surrounding density.

## Boundaries
- Never rename `org.caiodock.dock`, `org.caiodock.Integrations` or `org.orla.bar` without a designed migration.
- Never change test-pinned geometry (tile widths, event slot math, popup budgets) to make a visual fit;
  redesign within it or update the test with a stated reason.
- Never put personal data in fixtures, captures or logs (names, calendars, window titles, home paths).
- Tests and CI must not need paid AI calls, accounts, network or real hardware.
- Do not claim native Plasma/Wayland behavior from offscreen tests; say what was and wasn't run.
- Ask before installing into the user's live Plasma session, restarting `plasmashell`,
  pushing, or opening/merging pull requests.
- Keep unrelated refactors out of a change.

## Commits and PRs
- Conventional Commits with a scope: `feat(dock): …`, `fix(bar): …`, `docs(design): …`.
- UI PRs include gallery captures for dark and light schemes, keyboard/focus notes, and the
  tests that were run. Maintainers handle versions and release notes.
