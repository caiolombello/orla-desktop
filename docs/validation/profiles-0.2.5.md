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
no timeout relaxation, hidden rerun or launcher fix is claimed here. The later
diagnosis and its limits are recorded below; passing repeats do not turn the
original failed execution into a pass.

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

### Subsequent diagnostic canary and recovery — 15 October 2026

A later private native episode used a diagnostic package with the same 67 package
members. Only `DockView.qml` differed: it added geometry/state observations,
timers and journal output. The widget gesture implementation itself was unchanged.
The panel was temporarily made always visible because virtual-pointer edge entry
did not reveal the autohiding dock. This episode therefore does **not** qualify
the unmodified production applet or normal autohide entry.

Earlier attempts failed at popup opening, hover, journal access, tab discovery,
row reachability and screenshot coordinates; their receipts remain retained.
The final attempt reused the synthetic profile left by an earlier attempt. It
sent two real pointer drags and reported runtime/disk agreement, a first-pair
exchange, reversal to its starting document, and return to legacy selection.
Its input bridge reported release of its temporary devices. Full before/after
documents were not retained, so their complete equality cannot be independently
rechecked from saved snapshots. Input acknowledgments prove emission only.

The saved reverse trace contains a fresh held destination. The forward trace
shows drag state but no valid destination at that sample. The script's broader
`any(dragging)` predicates included earlier observations and cannot qualify both
held indicators. Native exactly-one-save and no-hover-write counts were not
recorded; those properties remain offscreen-test evidence. Screenshots show
postgesture states, not held state, and remain private because their crops include
background fragments.

The subsequent cleanup failed and left Plasma stopped. Its comparator both
lowercased keys and treated a stored configuration map as a filename; this was
not evidence of actual tray drift, and KConfig key case was not relaxed. A fresh,
case-preserving read of the original raw backup and current file found exactly
one differing key: the owned `profilesJSON` document.

A separate recovery first restored the desktop without deleting a key after a
mode-format comparison refused the write. That refusal is preserved. The next
guarded cleanup compared the actual octal mode representation and correct layout
bank path, stopped the verified shell once, removed only that exact owned key,
and started it once. The final receipt reports:

- `PASS_RECOVERED_AND_CLEANED`, no error in that cleanup execution;
- the original profile-key absence on both physical disk and runtime;
- full case-preserving configuration-map equality with the original raw backup;
- exact real-package and panel-inventory equality;
- 132 protected hashes, the separately recorded direct-file modes, and the
  resident launcher preserved.

This successful recovery does not relabel the earlier attempts or failed cleanup
as an uninterrupted native pass. Private custody is under
`.runtime/widget-drag-20261015/root-native-r1/`, the independent
`sol61-native-evidence-audit-r1/`, and `root-recovery-r1/` / `root-recovery-r2/`.
No personal configuration, trace text or native background image is published.

Next acceptance is a new bounded visit to the **uninstrumented** production
applet: establish popup entry/geometry, create one fresh owned profile, retain
complete documents around drag/reversal, and restore the original key with a
fresh baseline. Accessibility-based opening, pointer opening, held-state pixels,
focus and setter counts must each be described according to what actually ran.
C1/P1/UX1 remain partial.

The subsequent unmodified-production visit opened Settings with the public AT-SPI
`Press` action, read its own accessible tab/control geometry, and closed it with
Cancel. Original accessibility settings, configuration bytes and the shell
process were preserved. No profile or pointer action ran in that visit. Its first
read-only attempt stopped on an unsupported accessibility interface; the corrected
visitor retained that failure separately.

One new physical-pointer attempt then approached the lower screen edge and clicked
the externally measured settings-button center. The ordinary autohide panel did
not open Settings through that input path. All input acknowledgments were emission
only; the popup assertion failed. Temporary input devices were released,
accessibility settings and configuration bytes were restored/preserved, and no
profile was created. The test's premature opened flag also produced a missing-
Cancel cleanup error; the saved UI observation had never shown that popup open.
This remains a failed entry test, not production-drag acceptance. Further work
must distinguish virtual-pointer/edge behavior from a product interaction defect
before another profile-writing gesture. Private receipts are in
`root-production-readonly-r1/`, `root-production-readonly-r2/` and
`root-production-pointer-r1/` under the same widget evidence area.

### Production pointer entry — 15 October 2026

A subsequent bounded visit passed on the unmodified installed applet in Plasma
6.7.5/Wayland, one 2648×1490 logical output at scale 1.45. A temporary getter-only
KWin script observed the actual cursor and the exact Plasma-owned dock window's
`hidden` property. Settings opened through one virtual pointer click at its
fresh AT-SPI button rectangle; Escape closed it, and leaving the dock restored
the hidden state. AT-SPI supplied geometry and observation; it did not activate
the button in this visit.

The diagnostic found limitations in the earlier input procedure. The configured
panel height was 88, while KWin exposed a 104-pixel frame; the first observer's
exact-height filter therefore stopped before input. One edge contact produced
the compositor's one-pixel pushback. Repeating identical absolute values produced
no new observed cursor record. A distinct second contact revealed the panel,
but that absolute-only visit timed out waiting for retraction. The relative
pointer contrast then passed reveal/enter/leave/retraction. Its first one-count
nudge produced a fresh record with the same rounded integer position, so that
visitor's movement assertion stopped; the bounded five-count version observed
actual displacement and passed. These failures remain separate from the passing
episodes. The edge timing and stateful-event explanations are consistent with
the [KWin 6.7.5 implementation](https://raw.githubusercontent.com/KDE/kwin/v6.7.5/src/screenedge.cpp)
and [Linux input protocol](https://docs.kernel.org/input/event-codes.html).

The final popup visitor used ten bounded relative commands, 167 total absolute
axis counts, and a 30-second input-helper TTL. Its two earlier accessibility
attempts stopped before input on unsupported Component interfaces. The final
visitor skipped those unavailable facades and required one actionable,
geometry-capable button. The popup was also confirmed absent during cleanup.
All temporary input devices were released, the owned observer was unloaded,
and accessibility settings were restored. Configuration bytes, the 67-file
installed package, shell identity and resident launcher remained unchanged.
A separate post-check matched 132 protected hashes and the six recorded
direct-file modes. No profile, layout or product Source was changed.

Private receipts are under `.runtime/dock-edge-20261015/`: `root-panel-read-r1/`,
`root-abs-timing-r1/` through `r3/`, `root-relative-r1/` / `r2/`, and
`root-popup-r1/` through `r3/`. Eighteen fake-device checks covered the relative
helper's validation, event sequence, TTL refusal and partial-construction cleanup.
No screenshots or personal configuration are published. This qualifies pointer
entry and dismissal on this setup; fresh-profile dragging, complete document
reversal, focus return, held-state pixels and native setter counts remain open.

A further read-only visit clicked the Widgets tab at its fresh rectangle and
observed its checked state, the legacy guidance and all seven disabled grips.
Only the clock grip was reported showing; the remaining rows were below the
visible content. AT-SPI exposed no scroll/viewport ancestor, so viewport bounds
remain unqualified. No scrolling, toggling, profile creation or drag ran. Escape
and panel retraction completed, with the same preservation/cleanup guards. Since
Cancel is specific to the Appearance tab, a separate subsequent read confirmed
the Widgets tab and Cancel controls absent or not showing; that read also
preserved configuration/shell identity and restored accessibility. These receipts
are in `root-widget-geometry-r1/`. The next gesture episode must establish full
row reachability in its fresh managed profile before starting a drag.

### Accessible widget rows and full-row focus — 15 October 2026

The next production observation found the ScrollView's `panel` ancestor, which
the previous role filter had omitted. The individual FormRow items were absent
from that accessible hierarchy. Public focus on the Pomodoro checkbox scrolled
it into view, but its grip extended below the observed panel bounds. Settings
also retained its selected Widgets tab across reopening, so Cancel was an invalid
opening/closing witness for that visit. The first assertion failure is retained;
a separate continuation observed the open Widgets tab, measured its ancestors,
focused the checkbox, and closed the popup with Escape. The Widgets control's
absence, unchanged configuration/shell and restored accessibility were checked.
No profile was created.

The Source correction names the existing ScrollView and its actual clipped
Flickable, groups each widget row for accessibility, and reveals the complete
row when its checkbox or either arrow receives focus. It retains the controls,
layout, font sizes, geometry budgets and profile writer. A public QAccessible
tree test first failed on the unnamed region and passed with the semantics.
A separate containment test then failed four focus cases at 350/420 px before
the three child focus handlers were corrected, and passed afterwards.

The affected suites passed 63 tests plus one platform-dependent skip under each
of Fusion and org.kde.desktop. Seven design guards passed and design check
reported zero issues. The gallery rendered 70 PNGs; all eight widget captures
were pixel-identical to the published dark/light 350/420 px images. Four of those
new captures were visually reviewed. These tests qualify the accessible tree
and response to focus; they do not establish physical Tab traversal or native
drag acceptance. Installation and native qualification of this correction remain
separate gates. Private records are under `root-reachability-r1/`,
`root-reachability-open-r1/`, `root-a11y-probe-r1/`, `root-a11y-validation-r1/`
and `root-a11y-gallery-r1/` in the widget evidence area.

### Launcher CI diagnosis checkpoint

Both hosted jobs passed on widget Source `7c658596275abc71a696b478a0586408dbcac292`
in [run 38686612789](https://github.com/caiolombello/orla-desktop/actions/runs/38686612789).
This is a later source/checkpoint result; it does not fix or explain the original
PR #74 teardown failure.

The original isolated case passed locally. An observation-only private copy also
passed the original `launcher-ui` partition: 26 QtTest entries, CTest 13.58 s,
with the same 500 ms destruction budget and fail-closed next-owner barrier.
The original hosted GDB diagnostic had exited normally as well. These are
nonreproductions, not repair evidence.

A separate controlled scheduling probe then exercised the actual pinned
KRunner 6.31 ELF (`fd352644c12df0c4fdd4ce18ca01e16155791a941f28805d52156972e1fa2934`)
in a private network-isolated container without the live session. Disassembly
confirmed `quit()` before the two `finished` cleanup connections. The probe
forwarded real `quit()` and joined only the first two allowed workers at that
exact call site, within 50 ms each, forcing completion before the late connections.
Both joins succeeded. The unchanged original ownership test then failed its
500 ms runner-destruction audit with surviving runners: 2 QtTest entries passed,
1 failed, wrapper exit 1. This demonstrates a sufficient mechanism on that pinned
runtime; it does not reconstruct the actual scheduling history of CI #74.

No correction, timeout increase, disabled audit or framework mutation was adopted.
An early cleanup connection added outside the manager is unsafe because upstream
still accesses raw runner pointers after `quit()`. A framework-owner correction
needs its own reviewed build and the same controlled-schedule test. Private
receipts are under `.runtime/runner-teardown-20261015/root-mechanism-r2/`.
