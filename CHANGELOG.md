# Changelog

User-visible changes are recorded here for each published release.

## Unreleased — experimental source component

- Add optional Menu Orla (`org.orla.bar`, component version 0.1.0) for Plasma 6.7.x: an Orla icon or text-only label, bounded plain-text active application name, and explicit system/settings/configuration and capability-aware session actions. Keep the application label stable from menu opening through closure; distinguish an unnamed active application from the desktop.
- Isolate the private Plasma session adapter behind a 6.7.x guard, with source/API checks against 6.7.5. Logout, reboot and shutdown request native confirmation; successful dispatch does not prove completion.
- Ten injected mock tests passed with Fusion and KDE styles; independent review repeated ten KDE tests and approved experimental source publication. Four components compiled without errors, without native instantiation. Real dialogs/actions, panel/focus, human gestures and multi-monitor composition remain UNRUN; T1/T2/T3 are open.
- This component is excluded from the published 0.2.5 assets. Manual source installation is described in the [component guide](https://github.com/caiolombello/orla-desktop/blob/main/bar/README.md); no bar installer, panel preset, autostart, Control Center, Global Menu or tray is delivered.

## 0.2.5 — 2026-10-10 — Alpha prerelease

- Add explicit manual dock profiles: initialize Work/Personal/Games from saved preferences without switching, or create and use a custom clone. Preserve the previous flat preferences without automatic migration.
- Save pinned apps, appearance, seven known widgets' order/visibility, calendar-event visibility and current-desktop filtering per profile. Keep the global Pomodoro object/deadline during profile selection; cross-process timer resume remains unqualified.
- Organize settings into Appearance, Widgets and Profiles. Apply or cancel dirty appearance previews before creating/switching; keep Undo scoped to the current profile. Reject invalid/future profile JSON without overwriting it.
- Profile implementation review approved; 49 targeted checks passed with Fusion and KDE styles, and the recorded combined regression passed 123 tests. A private native snapshot proved KConfig Apply/Cancel/disk/restart and one owned remove/re-add cycle. Its metadata is 0.2.4 with frozen profile overlays; it does not qualify the full 0.2.5 release or popup/focus behavior. See [profile validation](docs/validation/profiles-0.2.5.md).
- Include the experimental Linux release-check CLI in the release ZIP. It compares an explicit version against official stable/beta releases with bounded anonymous requests and structured errors; it does not detect the running version or install packages. Seventeen offline tests and independent review passed; see [usage and limits](docs/updates.md).
- Source also includes an experimental standalone Qt Quick launcher using public KRunner application/calculator APIs. Three private CTests and independent review passed. It requires a separate build and remains excluded from the release; global Wayland shortcut/focus, daily use and optional installation remain open.
- P1/C1 remain partial; profile association with Activities/desktops and selection of bar/launcher/event surfaces remain planned.

## 0.2.4 — 2026-10-10 — Alpha

- Add an opt-in system battery widget (off by default), reading only UPower’s aggregate display device. Preserve valid 0%, show absent/unavailable states neutrally, and display power/charging/time only when supplied; PeriGauge peripheral readings remain separate.
- Share one native Plasma MPRIS model across the dock and media controls. Prefer Spotify initially, allow manual session selection, and show bounded plain-text track/artist metadata.
- Gate Play, Pause, Previous and Next by the selected player’s current capabilities; recover selection and focus after a player disappears.
- Battery fixtures (16 tests), media fixtures (12 tests across offscreen/Fusion/KDE styles), and private native MPRIS receiver checks passed. Independent battery, media and dock-wiring reviews have no outstanding findings. The combined regression suite passed all 96 tests.
- A read-only real UPower aggregate probe and a private two-player native MPRIS fixture passed. Real Spotify/audio, the hardware matrix and human panel interaction remain unqualified; M1/B1/C1 remain open. See [validation](docs/validation/battery-media-0.2.4.md).
- This release does not include the launcher; it remains a separate review and delivery.

## 0.2.3 — 2026-10-10 — Alpha

- Preview dock colors, opacity, spacing, corners, icon size and reduced motion; Apply saves the appearance, while Cancel, Escape or closing settings discards the preview.
- Undo the previous applied appearance once per session, or prepare restoration of earlier preferences before applying. Existing settings remain available through a separate appearance override.
- Keep settings readable independently of custom dock colors and constrain the preferences popup to the screen budget; keyboard navigation reveals scrolled fields.
- Include the experimental data-only theme validator, schema, two examples and canonical packer in the contributor bundle. It does not import/apply community theme files yet.
- Independent review and 66 local tests passed. Native panel focus/grabs, real KConfig persistence and the hardware matrix retain their own acceptance gates.

## 0.2.2 — 2026-10-10 — Alpha

- Install and upgrade the dock without optional project-integration dependencies; restore integrations by reinstalling after dependencies are available.
- Report optional D-Bus refresh failures without failing an otherwise successful dock installation; preserve settings and caches.
- Open application context menus with Menu or Shift+F10 and close with Escape.
- Make the synthetic calendar UI test flush pending layouts before inspecting event titles. Native panel popup/focus and multi-monitor qualification remain open.

## 0.2.1 — 2026-10-10 — Alpha

- Introduces the Orla Desktop name and visual identity for the existing Plasma dock.
- Publishes installation, contribution, security, and project-status guidance.
- Retains the existing Plasma package ID and D-Bus integration service for compatibility.
- The optional menu bar, launcher, system controls, notification surfaces, Spotify-specific features, system battery, Steam, automatic updates, and expanded integrations remain planned.
