# Manual profiles 0.2.5 — validation / Validação

Recorded for the 0.2.5 alpha prerelease, 2026-10-10 (America/Sao_Paulo).
Baseline: Fedora 44, Plasma 6.7.5, Qt/PySide6 6.11.2, Wayland.
**P1/C1 remain partial. Publication and full native release qualification are separate.**

## Delivered and reviewed

The 16-file profile implementation/test manifest was independently reviewed and approved. It adds explicit initialization, creation/selection, preserved flat preferences, profile-scoped appearance/Undo, pinned apps, seven-widget order/visibility, calendar-event visibility and current-desktop filtering. The JSON format remains `0.1-experimental`; invalid/future JSON is preserved and presentation writes are blocked. No passive migration or launcher-list autosave is introduced. The same global Pomodoro/provider objects remain outside the profile renderer. See [the user guide](../profiles.md).

## Recorded tests

The targeted suite passed **49 tests** separately with Fusion (12.055 s) and `org.kde.desktop` (14.269 s): 13 profile core, 14 profile integration, 12 dock QML and 10 appearance checks.

```bash
PYTHONPATH=tests QT_QUICK_CONTROLS_STYLE=Fusion python3 -B -m unittest test_profiles_dock test_qml test_appearance test_profiles -v
PYTHONPATH=tests QT_QUICK_CONTROLS_STYLE=org.kde.desktop python3 -B -m unittest test_profiles_dock test_qml test_appearance test_profiles -v
```

Run these sequentially. The root regression subsequently passed **123 tests with KDE style in 39.200 s**. The portable profile core also passed **13 tests** with PySide6 Essentials 6.12.0 using offscreen Qt; CI runs that core in a separate process. These are recorded local results, not a claim about every CI/platform configuration. Coverage includes explicit activation, saved cloning, stale scope/revision, preview/Cancel/Undo, immediate widget/calendar changes, hidden-all widgets, same-dock timer preservation, missing apps and Qt URL alias identity with original saved spelling preserved. Owned `.desktop` fixtures are not launched. Synthetic focus/key checks qualify their Qt controls, not native seat activation.

Local receipts: `.runtime/profiles-dock/report.md`, `evidence.json`, `source-sha256.txt` and the final Fusion/KDE, root-regression and `portable-qt-6.12.log` logs. These validation artifacts are not release contents; public reproduction uses the tests above.

## Private native persistence and one lifecycle cycle

A frozen snapshot with **metadata 0.2.4 plus reviewed profile overlays, 26 package files**, was copied and installed with 26/26 hash agreement in a private native Plasma shell. It used owned XDG trees, private D-Bus without automatic activation, virtual KWin and filesystem/PID/network isolation. Baseline and profile launchers were synthetic, never executed; external widgets/events were disabled.

Programmatic fixture actions observed actual `KConfigPropertyMap` configuration:

- Initialization retained Previous preferences and cloned Work/Personal/Games from the saved flat baseline; custom creation and profile selection worked.
- Apply saved profile appearance, reversed/hidden widgets, a synthetic pinned launcher and the window filter. The controller waited for exactly encoded KConfig disk content and verified decoded JSON equality before proceeding.
- Cancel discarded a preview without changing the applied product configuration group.
- Restart of the owned shell reloaded identical JSON, active profile and presentation; baseline flat fields matched in memory and disk.
- The same Pomodoro object/deadline survived profile selection with its widget hidden. It was explicitly reset before shell restart: **cross-process timer resume is UNRUN**.
- After saving persistence receipts, one separate cycle removed the owned applet and re-added a new applet ID, explicitly seeding the new applet with the saved JSON and observing the expected presentation while the shell stayed alive. This proves one bounded teardown/recreation and rehydration cycle, not automatic recovery of configuration after deleting an applet or qualification of every destruction path.

Attempt 2 completed in **14.75 s**, exit 0, without timeout or observed fatal/segfault. Logs retain warnings including realtime priority and unavailable PipeWire. Independent receipt review approved the bounded proof with zero blockers: 26/26 snapshot/installed hashes, independently decoded KConfig JSON, untrimmed Apply/Cancel/Restart product-group equality and the one seeded lifecycle cycle. Current source differs from the snapshot only in metadata/version label 0.2.4 → 0.2.5. The native evidence establishes programmatic persistence for the frozen bytes, not the full 0.2.5 package.

Attempt 1 is preserved as **FAIL**: its fixture compared raw JSON against KConfig's escaped representation. Apply/disk were observed, but Cancel/restart/teardown were **UNRUN** in that attempt. Diagnosis checked exact encoded and decoded equality against documented KConfig 6.30.0 string encoding; attempt 2 used new owned runtime/bus trees and the same frozen product bytes. It did not rewrite attempt 1 as passing.

Local native receipts: `.runtime/profiles-native-proof/REPORT.md`, `evidence/summary.json`, the retained `attempt1/` and attempt-2 disk/receipt/lifecycle artifacts, plus `.runtime/profiles-native-proof-review/REPORT.md`. The successful bootstrap is historical and refuses replay of its consumed fixture.

## Remaining acceptance / Aceite pendente

- Human gestures in an installed panel; `Popup.Window` presentation, input serial/grab/focus/layout, accessibility, scaling and multiple monitors.
- Resume of a running Pomodoro across processes; extended daily use and further teardown paths.
- Real apps/games/Spotify/calendar/accounts and launcher activation.
- P1 selection of bar/launcher/event surfaces; P2 Activity association and W1 desktop/Activity switching.
- Complete 0.2.5 release/install/upgrade qualification and all remaining C1/P1 gates.

A prior `kactivitymanagerd --help` attempt with inherited environment remains UNKNOWN; this isolated proof does not establish that all user-session configuration was unchanged.

**Resumo em português:** 49 testes direcionados passaram em Fusion e KDE; a regressão registrada passou 123 testes. A implementação de perfis foi aprovada em revisão. A prova nativa privada, com metadata 0.2.4 e 26 arquivos congelados incluindo overlays de perfis, comprovou Apply/Cancel/disco/reinício e um ciclo próprio de remover/recriar, com JSON salvo explicitamente atribuído ao novo applet; não prova recuperação automática após apagar. A revisão independente dos recibos aprovou a prova delimitada sem blockers. A primeira tentativa falhou no comparador da fixture e permanece preservada. Os comandos/sinais foram programáticos: popup, foco, gesto humano, retomada do timer entre processos e release completa continuam sem qualificação. P1/C1 permanecem parciais; P2/W1 são trilhas separadas.


## Widget grip reordering — 15 October 2026

This current Source increment adds direct manipulation to Settings → Widgets in
an explicitly chosen managed profile. It retains the native checkbox and existing
up/down actions. The grip has a symbolic icon, hover help and keyboard guidance.
A held drag shows a single insertion line; only a valid release saves through the
existing profile writer. There is no hover write, implicit legacy migration,
new saved preference, data format, dependency or popup-budget change. Source code
for this increment is pinned at `1d41dca79f37d3986d5d253330ca25da30393302`.

The press captures its profile object, scope, revision and full widget snapshot
before requesting focus, then rechecks the capture. Release uses stable widget
IDs, refuses an off-viewport target and submits at most one guarded profile write.
Click-without-drag, self-drop, outside release, Escape, tab/popup close, import,
readonly state or changed scope/revision cancel without an additional order write.
The first Escape during a held gesture cancels it; the next closes settings.
Targets must be visible; there is no edge autoscroll or cross-panel drag in this
increment. The existing arrow controls remain available to reach any row.

A still-focused grip parks focus on the stable list before its delegate is
rebuilt. Restoration requires that list still own focus, the same gesture ticket,
profile and exact postwrite revision/widgets. A newer focus owner is preserved.
Closing the editing session invalidates the gesture immediately, even while KDE
keeps the popup visible for its exit animation. Cancellation before the setter
prevents the write; cancellation after an already completed setter invalidates
later focus work and does not pretend to undo that write.

### Verification

- The first public pointer test failed against the prior UI because there was no
  grip. With the implementation it observes a held destination line, zero writes
  during movement, exactly one on release, the rendered dock order, unchanged
  visibility/other profile data/flat preferences, and the preserved appearance
  draft. Arrow-key reorder/focus coverage remains unchanged.
- Six new cases run in the actual Dock fixture. Five also run in the existing
  portable Settings fixture through the `test_appearance_preset` CI module:
  normal focus restoration, preservation of newer focus, click/self/outside/Escape,
  held invalidation and legacy/readonly refusal. The detailed rendered-dock/data
  test remains local; no hidden Tile geometry is inferred from the portable fixture.
- Final related suites ran **101 tests under each of Fusion and org.kde.desktop:
  100 passed, one skipped**. The skipped desktop-URL/TaskManager case needs a
  Wayland/X11 connection. The suites were profiles/dock, widget strip, appearance,
  portable appearance, its dock fixture and parser. These are offscreen Qt pointer
  events, not native seat/grab or physical-pointer qualification.
- The initial KDE full run had two real close-during-animation failures, one per
  fixture. Both were retained and then passed the focused regression and final
  complete run after the editing-lifecycle guard. The earlier static review missed
  that animation window; a second review covered the correction.
- Early fixture failures are retained: tab layout was not yet settled before
  mapping pointer positions; a portable import scenario had lost its editing
  session after a profile change. Tests now wait for actual popup close/reopen and
  assert editing/pending preconditions. A separate real geometry finding revealed
  only the grip, clipping the target row by eight pixels; focusing now reveals the
  entire row, without widening the popup or weakening bounds.
- Design check reported zero issues and all seven design guards passed. The final
  complete gallery generated 70 PNGs including its index. Eight new states below
  were inspected in both schemes at 350/420 px. The final images are byte-identical
  to the reviewed images before the nonvisual close guard; names wrap at 350 px
  without changing fonts or targets. All captures contain synthetic data.

| State | Dark | Light |
| --- | --- | --- |
| Idle, 350 px | [Capture](../screenshots/widget-order/widgets-dark-idle-350.png) | [Capture](../screenshots/widget-order/widgets-light-idle-350.png) |
| Held destination, 350 px | [Capture](../screenshots/widget-order/widgets-dark-drag-350.png) | [Capture](../screenshots/widget-order/widgets-light-drag-350.png) |
| Idle, 420 px | [Capture](../screenshots/widget-order/widgets-dark-idle-420.png) | [Capture](../screenshots/widget-order/widgets-light-idle-420.png) |
| Held destination, 420 px | [Capture](../screenshots/widget-order/widgets-dark-drag-420.png) | [Capture](../screenshots/widget-order/widgets-light-drag-420.png) |

Reproduce the current related checks in a compatible KDE/Qt environment:

```bash
for orla_style in Fusion org.kde.desktop; do
  PYTHONPATH=tests QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE="$orla_style" python3 -B -m unittest test_profiles_dock test_widget_strip test_appearance test_appearance_preset test_appearance_preset_dock test_appearance_preset_parser -v
done
python3 scripts/design.py check
python3 scripts/design.py gallery
```

The historical broader commands above remain historical evidence; this increment
does not relabel previously recorded unrelated native-dialog/audio failures green.

A separate host checkpoint found that [PR #74](https://github.com/caiolombello/orla-desktop/pull/74)
passed its portable job but failed [launcher UI cleanup in CI](https://github.com/caiolombello/orla-desktop/actions/runs/38683861698/job/116254167457).
The Steam-departure body reported successful cancellation/reaping; its owned-runner
teardown then exceeded 500 ms, and the next case aborted because runners remained.
Launcher sources were unchanged by this widget increment. The cause remains open;
no timeout relaxation, hidden rerun or launcher fix is claimed here. This CI failure
must be diagnosed before proceeding with broader native acceptance.

### Local installation and remaining Native acceptance

The public applet installer updated the actual local package after the final
checks. A full previous-package backup and rollback archive were retained. The
67-member package changed only `SettingsContents.qml`, now matching SHA-256
`256a44f0ade96bef41abb3cef02c7995b51173da2841274b6eafd5ae3c92d9f8`.
One guarded Plasma stop/install/start passed. Readiness waited through three
unmapped-screen observations, then admitted an exact inventory match. Panel/app
IDs, configuration target, the resident launcher and the 132 protected file/hash/
mode entries remained unchanged. No release asset/version was replaced.

This update proves installation/reload and those preservation checks only.
**Actual installed widget dragging/reversal, physical pointer entry, native
pixels/focus, cross-process persistence and other displays/scales remain UNRUN
for this increment.** Installation did not invoke profile creation, selection or
migration. The prior compact-popup keyboard proof is a different, explicitly
bounded increment and does not qualify widget dragging. A planned native canary
must create only an owned profile, drag/reverse with actual input, return to the
original selection and restore only its guarded profile key, including original
presence/absence. Until that runs, C1/P1/UX1 remain partial; app dragging and the
other roadmap gates also remain open.
