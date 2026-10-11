# Changelog

User-visible changes are recorded here for each published release.

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
