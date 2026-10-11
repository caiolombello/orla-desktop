# Changelog

User-visible changes are recorded here for each published release.

## Unreleased

- Add an experimental standalone Qt Quick launcher in the source checkout, using public KRunner application/calculator APIs with anonymous configuration and stale-selection guards.
- Three CTests passed with private D-Bus, temporary XDG/runtime and automatic service activation blocked; independent review approved the component. Actual global Wayland shortcut/focus, daily use and optional installation remain open. Release 0.2.4 excludes this component.

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
