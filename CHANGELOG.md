# Changelog

User-visible changes are recorded here for each published release.


## 0.2.8 — 2026-10-11 — Alpha prerelease

- Add a fourth **Contextos** settings tab with separate Activity and virtual-desktop cards. Opening that tab is the only time the read-only native discovery Loader is active; selectors stage a choice and only explicit bind/remove actions save an association to an existing managed profile.
- Keep Activity and desktop associations in the separate empty-default `contextsJSON` setting. Stable IDs, stale-intent rejection and invalid/future raw-byte preservation avoid silent cleanup or profile/context switching. Associations do not auto-select profiles, switch KDE contexts, apply/cancel appearance previews, or change Pomodoro identity/deadline.
- The pure-core local Qt 6.12.0 run passed 11 tests in 0.201 seconds; the focused dock integration passed 12 tests and its independent adversarial rerun passed 2. Independent Source reviews approved the core and dock integration. The native adapter only observes KDE models. P2 remains partial and W1 switching is unstarted; native plugin construction, KConfig/restart and session behavior remain unqualified.
- Published as [v0.2.8](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.8) (alpha prerelease, `latest=false`) from source `9e42decd42fc4a9a705dd48e6087b17aaca51d29` (PR 18, merge `c87930bc9881523a390ca492af1e0af6dfc328ca`). CI run [38113776729](https://github.com/caiolombello/orla-desktop/actions/runs/38113776729), job 114394497503, succeeded. Anonymous HTTP 200 checks confirmed exact source-build matches for the `.plasmoid`, ZIP and `SHA256SUMS`; see the [validation record](docs/validation/contexts-0.2.8.md) for hashes. Two release-candidate builds and one exact-commit build matched (139 Source files, 113 ZIP entries, 35 applet entries). Installation remains UNRUN and native admission is false.

## 0.2.7 — 2026-10-11 — Alpha prerelease

- Add an opt-in local toast for completion of a Pomodoro focus or break period. The global Widgets setting is off by default; when enabled, the dock shows a short plain-text message in its own reserved area. KDE notifications remain independent.
- Keep the existing Pomodoro timer, deadline and owner. Invalid or unsupported profile data clears local presentation and uses the existing legacy notice path without rewriting saved profile data. The setting is global; per-profile event rules are not included.
- Published as [v0.2.7](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.7) from source commit `9ca1792ee3e9c20ad770042d2d441aa1ae6efbce` (PR 16; CI run [38111731691](https://github.com/caiolombello/orla-desktop/actions/runs/38111731691) succeeded). Anonymous downloads of the applet, ZIP and `SHA256SUMS` returned HTTP 200 and matched the exact release build; the [validation record](docs/validation/local-events-0.2.7.md) lists hashes and limits. Installation and native admission remain unverified.
- The 14-check product suite and the existing 9-pass/3-pre-existing-skip offscreen QML suite passed before the compact-boundary correction. After that change, two focused surface tests passed with zero warnings; the full product suite was not rerun. Independent review approved both corrections and additionally checked pointer/geometry behavior at 48 pixels. The synthetic package check also passed after the correction, with exact current event/config bytes and two reproducible builds. Native panel, popup, focus, screen-reader and install/upgrade behavior remain unqualified. See the [local events guide](docs/local-events.md) and [validation record](docs/validation/local-events-0.2.7.md).

## Unreleased — experimental source components

- Add optional Menu Orla (`org.orla.bar`, component version 0.1.0) for Plasma 6.7.x: an Orla icon or text-only label, bounded plain-text active application name, and explicit system/settings/configuration and capability-aware session actions. Keep the application label stable from menu opening through closure; distinguish an unnamed active application from the desktop.
- Isolate the private Plasma session adapter behind a 6.7.x guard, with source/API checks against 6.7.5. Logout, reboot and shutdown request native confirmation; successful dispatch does not prove completion.
- Ten injected mock tests passed with Fusion and KDE styles; independent review repeated ten KDE tests and approved experimental source publication. Four components compiled without errors, without native instantiation. Real dialogs/actions, panel/focus, human gestures and multi-monitor composition remain UNRUN; T1/T2/T3 are open.
- This component is excluded from the 0.2.5, 0.2.6, 0.2.7 and 0.2.8 bundles. Manual source installation is described in the [component guide](https://github.com/caiolombello/orla-desktop/blob/main/bar/README.md); no bar installer, panel preset, autostart, Control Center, Global Menu or tray is delivered.


## 0.2.6 — 2026-10-11 — Alpha prerelease

- Add a paste-only experimental `0.1-experimental` JSON theme preview in Appearance. Preview and declared metadata stay in memory; Apply saves only the current profile's normal appearance. No file import, package installation, gallery or stable theme API is included.
- Add an experimental Steam inventory CLI for explicitly supplied roots and indexed libraries. Bound KV1 parsing, filesystem access, worker time and output; report conservative presence candidates and partial/unknown states. Generate only validated URI strings, without launching them. Twenty synthetic tests and independent review passed; real Steam libraries, accounts and handlers remain untested. Obvious path-like names are neutralized, without a general anonymization promise. Dock/provider/search/favorites remain planned; S1 is partial. The 0.2.6 ZIP includes this CLI; published 0.2.5 assets remain unchanged.
- Ten selected portable Qt 6.12 theme checks passed. Independent review approved the eight implementation/test files and 879 adversarial parser cases. The broader local fixture run remains 59 PASS, one baseline TaskManager failure and three native-only SKIP; see [theme validation](docs/validation/theme-consumer-0.2.6.md).
- The optional Menu Orla and standalone launcher remain separate Source components and are excluded from this bundle. Theme file import, stable SDK, Steam dock UI and native popup qualification remain open.

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
