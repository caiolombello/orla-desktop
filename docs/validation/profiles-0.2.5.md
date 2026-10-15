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
drag acceptance. Installation and native qualification were checked separately
below. Private records are under `root-reachability-r1/`,
`root-reachability-open-r1/`, `root-a11y-probe-r1/`, `root-a11y-validation-r1/`
and `root-a11y-gallery-r1/` in the widget evidence area.

The correction `aad9ca1` was subsequently installed with a backup and one
controlled Plasma stop/start. Only SettingsContents changed in the 67-file
package. The case-preserving configuration map, panel/app inventory, protected
files and modes, actual launcher unit/link facts and resident launcher remained
equal. Runtime profile-key absence and an inert timer were checked before stop.

A fresh production visit rebound to the new shell/window identity, opened
Settings and selected Widgets through pointer clicks. After public accessibility
focus on the clock checkbox, a physical Tab focused Pomodoro. The named actual
Flickable measured 297×470; both complete 297×50 row groups were contained in it.
Escape closed the popup, all four tab headers became absent/not showing, and the
dock retracted. Configuration bytes, package and the visit's shell identity were
preserved, with the launcher unchanged, accessibility restored and all owned
devices/observer removed. This qualifies that particular native Tab/focus path
and row geometry on the single fractional-scale setup. Managed-profile dragging,
reversal, other keyboard paths and other screens remain open. Receipts are in
`root-a11y-local-r1/`, `root-a11y-panel-read-r1/` and `root-a11y-native-r1/`.

### Production managed-profile drag and reversal — 15 October 2026

A subsequent attempt failed before its first acknowledgment or any drag: the
first agreed disk/runtime value after Create was still empty. The new profile
appeared in a later read. The original finite custody refused deletion without
an acknowledgment and left the original desktop running; that attempt remains
FAILED. A separate reviewed recovery matched the sole synthetic profile to the
exact name emitted by that attempt and verified that removing only its key
restored the entire original case-sensitive configuration map. It then stopped
Plasma once, deleted only `profilesJSON`, restarted once and confirmed the full
map, original key absence, package, inventory, protected files/modes and resident
launcher. It did not fabricate doc0 or reopen the failed custody instance.

The next private controller distinguishes read consistency from completion: it
waits up to five seconds for the expected full document, checking the deadline
after a guarded read as well. Only the exact preceding value may be retried;
unexpected new data fails immediately. Ten synthetic-clock cases passed,
including delayed completion, foreign data, guard errors and late responses.
These are controller checks, not additional product or native gesture tests.

A distinct fresh episode then passed on the uninstrumented 67-file production
package containing `aad9ca1`, in Plasma 6.7.5/Wayland on the single fractional-scale
output. It opened Settings through normal autohide reveal and pointer clicks,
created exactly one new profile through the public form, and durably acknowledged
its complete doc0 before further input. Public accessibility focus anchored the
clock checkbox; three actual Tabs, including enabled managed-profile controls,
reached Pomodoro. Both whole rows and enabled grips were measured inside the
named actual clipped viewport.

Two pointer gestures were emitted through the owned temporary input device:
clock after Pomodoro, then Pomodoro after clock. The first persisted doc1 equaled
doc0 with only the first two widgets exchanged, preserving visibility and every
other field. Fresh Settings-row geometry also showed that exchange. The reverse
persisted doc2 equaled doc0 in both parsed content and complete raw bytes, with
the Settings rows restored. Selecting the previous preferences through the
public selector/Home/Use path produced doc3 with only the active ID changed to
legacy and the owned profile record unchanged. All four full raw documents and
their hash/length/parsed receipts were retained privately and checked again.

Escape closed the popup and the dock retracted. Input devices, observer, owned
bus name/connection and temporary accessibility state were released before one
controlled cleanup stop/start. Only the owned profile key was deleted. Fresh
final readback confirmed the exact original configuration map, profile-key
absence on disk/runtime, inert timer, inventory, source/installed package,
protected files/modes and actual launcher unit/link/process; no temporary input
device remained. The new episode had no primary or cleanup errors. Independent
static review of the saved chain found no material overclaim. The initial failed
episode and its separate recovery remain distinct from this acceptance.

This qualifies one managed-profile widget-order-and-reverse flow on the installed
product. It does not qualify held indicator pixels, native setter/hover-write
counts, the dock's WidgetStrip rendering, external-application focus return,
application-tile dragging or other output configurations. C1/P1/UX1 remain
partial. Private records: `root-managed-native-r1/`,
`root-late-profile-recovery-r1/`, `root-managed-native-r2/` and
`sol61-managed-native-audit-r1/`. The successful raw RESULT retains a stale
preparation-only `scope` label; its status, guards, documents and final readback
establish the bounded result without rewriting that receipt.

Both hosted jobs also passed on the accessibility/focus Source checkpoint
`f2a1086ff87363c01fb29f5276c30439038d3a22` in
[run 38741910764](https://github.com/caiolombello/orla-desktop/actions/runs/38741910764).
The subsequent native visits changed no product Source.

### Running app order recovery — 15 October 2026

An isolated KWin 6.7.5/Wayland experiment reproduced a distinction between the
saved launcher list and the manual task map. With two dormant synthetic pins,
assigning the original list restored their order. With both apps running, the
same assignment left visible B/A while `launcherList` already reported A/B.
Moving by current window identity restored A/B. This is consistent with the
[KDE move/sync contract](https://github.com/KDE/plasma-workspace/blob/cc1ab7963f94a9b76836412855caed6b94066188/libtaskmanager/tasksmodel.h#L887-L911);
list equality alone is not visual recovery evidence.

The actual production DockView then reproduced the failure through its existing
`moveTask` entrypoint. A one-shot `rowsMoved` observer committed an unrelated
calendar preference, advancing the managed profile revision. The attempted move
returned false and left the saved launcher bytes A/B intact, but the real task
rows remained B/A. The candidate now postpones nested reloads until the native
move/sync returns and reconciles the manual map against the newest saved
authority. KDE's public `launcherPosition()` supplies the rank; only pinned slots
are sorted, with window identities and within-pin order retained. This direction
does not call `syncLaunchers()` or write configuration. Obsolete moves stop
before their profile write; managed saves also recheck the current model.

The same regression passed after the correction. Its repository version,
`tests/native/task_order.py`, also failed on an isolated copy of the unchanged
base with exit 1 and `SOURCE_REFUSAL_LEFT_RUNNING_ORDER_CHANGED`, then passed on
the candidate with exit 0. Both recorded one fixture configuration signal from
the unrelated observer, unchanged saved launcher bytes and the actual task-row
order. These are Qt fixture setter counts, not native KConfig write counts.

Additional isolated cases passed: selecting a newer profile from `rowsMoved`
produced no launcher-list change inside that callback, no obsolete profile write
and the newest profile's B/A display. Returning to A/B and performing a normal
move then saved B/A once. A seven-window case included the fixture window, two
windows for A, pinned B/C and unpinned U/V. Changing the authoritative pin order
to C/B/A preserved the exact unpinned/fixture slots and A-window relative order;
a following normal move/sync produced coherent saved/displayed order with one
fixture setter. No TaskManager activation/close command or host input was requested.

All experiments used a separate D-Bus session, virtual compositor and four
private XDG directories. Interpreter metadata requested only
`org_kde_plasma_window_management` through normal KWin permission checks. Earlier
attempts that did not observe the windows remain FAILED; debug output identified
a trailing semicolon being read as part of the permission token. Correcting that
private metadata enabled the experiment without a permission bypass or KDE ID
impersonation. Every run confirmed host shell/configuration unchanged and owned
processes gone. The original model-only runner could exit 0 while its inner probe
failed; acceptance consumed the inner result. The repository regression returns
nonzero on failure.

To repeat the repository regression, prepare fresh owned A/B desktop fixtures
and interpreter metadata in an isolated KWin/D-Bus session. Set runtime, config,
data and cache XDG paths to strict subdirectories of the same private area, then run
`python3 -B tests/native/task_order.py --area /absolute/private/area` with an outer
bounded compositor lifecycle. The script refuses ordinary non-private XDG paths
and writes `PROBE-RESULT.json` exclusively. It requires the local KDE QML modules
and is intentionally outside portable CI; it does not create its compositor or
authorize a client in the user's session. A negative check confirmed that runtime
equal to the area is refused before workers start, keeping readiness files inside
the private area.

Design check, seven design guards, gallery generation and the 67-file package
build passed; the dark/light dock captures were inspected. The combined
`test_profiles_dock test_qml` run had 56 tests, four skips and one failure in each
Fusion/KDE style. The failure at `test_qml.py:300` was a native popup not becoming
visible on the offscreen platform. The isolated Fusion test failed identically
with both the candidate and the unchanged base. It remains a separate unresolved
check; the suite is not reported as entirely green.

Product Source `b32e1b0` was installed with backup and exactly one controlled shell
stop/start. Fresh readback confirmed all 67 package hashes and modes, the original
configuration map and inventory, protected files and resident launcher. Automatic
locking remained false. No physical post-install input was performed for this
increment. App dragging, cancellation/focus of that future gesture, preferred
bindings/encoded aliases/unavailable pins in this new reconciliation, topology
churn during reconciliation and other output/desktop configurations remain
unqualified. C1/UX1 remain partial; no release asset changed. Private receipts:
`.runtime/app-order-20261015/root-evidence-r1/`, `root-local-install-r1/` and the
static Source/install reviews.

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


### App tile dragging — 15 October 2026

The existing app Tile now owns a mouse/touchpad DragHandler. A portable
`TaskDragState` captures the profile, revision, saved launchers, complete row
identities/order and gesture generation at press. Icons stay in their model
positions while held; one thin before/after marker uses dock tokens. Internal
gaps clear the destination; outside/covered/clipped destinations cannot commit.
Only an activated exclusive grab released with `EventPoint.Released` may call
the native move adapter. Escape, window loss, changed profile/model/geometry and
cancellation invalidate the intent. Normal clicks, Space and menu actions remain.
The Qt terminal-event distinction follows [PointerHandler](https://doc.qt.io/qt-6.11/qml-qtquick-pointerhandler.html)
and [eventPoint](https://doc.qt.io/qt-6.11/qml-qtquick-eventpoint.html).

Actual Source counterexamples were retained before each correction:

- Without the gesture, pointer release left AB unchanged (zero writes/clicks).
- Crossing a measured 5 px tile gap canceled a valid move. The correction clears
  only the marker and allows the same captured intent to continue.
- Deactivation left an active ticket after grab loss. Window transitions now
  cancel directly, including during commit; a non-release ungrab cannot save.
- A synchronous second native move preserved membership but published BCA instead
  of the requested BAC. The adapter now requires the exact identity splice after
  move and sync. The corrected case refused with zero writes and restored ABC.
- A valid drop rebuilt its focused delegate and lost focus. The root now restores
  by identity after the move only when the original window/focus ownership still
  holds; a newer control focus is preserved.

`tests/native/task_order.py --area PRIVATE_AREA --gesture` passed 12 bounded cases
on the real Qt/TaskManager stack in an isolated virtual KWin session: managed
forward/reverse across the measured gap, newer control focus, restoring order,
self-drop, delivered Escape, outside-and-return, held revision change, owned Tool
window deactivation with unchanged topology, short click and Space, and legacy
forward/reverse. Changed-order releases each produced one configuration signal;
held updates/canceled gestures produced none, and drags emitted no `clicked`.
The revision case counted its one separate external update. The legacy writer
accepts a guard only for one validated launcher-list setter, rechecking revision
and scope after the guard. Multi-field guarded legacy writes remain rejected.

The same script's default refusal case and `--competing-move` case also passed;
the latter needs the synthetic Model C desktop entry. All runs require a fresh
owned private area with strict descendant XDG directories and an independently
owned compositor/DBus session; they do not create that session or run against the
user's desktop. Fixtures launch only their own synthetic windows, never desktop
Exec entries. Every wrapper confirmed host shell/config unchanged and its own
workers gone. Early setup/warning failures remain in the private receipts.

Verified locally: `test_profiles test_task_drag_state test_profiles_dock` ran 49
entries per Fusion/KDE style (48 passed, 1 skipped); design check, seven design
guards, gallery and applet build passed. The broader 78-entry run per style had
73 passes, four skips and the already reproduced offscreen popup failure at
`test_qml.py:300`. It is not an entirely green full suite. Portable state tests
are now included in CI without KDE, network, accounts or hardware.

The held captures below use synthetic windows, not personal apps. The marker
keeps existing tile sizes and event-lane budgets. Both captures and the ordinary
dock gallery were visually inspected.

![Dark dock with insertion marker](captures/app-drag-dark-held.png)

![Light dock with insertion marker](captures/app-drag-light-held.png)

The final 68-file applet was installed with a backup and exactly one controlled
shell stop/start. Readback confirmed package hashes/modes, the complete existing
configuration map, inventory, protected files and resident launcher. Automatic
locking remained disabled; no new DockView/TaskDragState component warnings were
captured after reload. A readback-script path error for the root LICENSE was
corrected without repeating installation; the initial error is retained privately.

This is Qt event delivery in an owned Wayland fixture, not physical input into
the installed Plasma panel. Physical panel focus/Escape delivery, long-content
scroll/overflow and touchscreen gestures, multiple outputs/scales and broader
context/topology churn remain unqualified. No marketplace/release readiness is
implied. Private receipts are under `.runtime/app-drag-20261015/` (gesture matrix,
RED/GREEN cases, final reviews, regression logs and gallery).

## Installed legacy app drag and reversal — 15 October 2026

A fresh episode on the installed 68-file applet passed two physical pointer
drags in Plasma 6.7.5/Wayland, Qt 6.11.2, one output at scale 1.45. The unchanged
production package matched `ea3958f`; no UI instrumentation or temporary profile
was added. Accessibility located the first two app slots by technical ID within
the owned panel, without reading app or window names. The saved launcher list
had seven distinct entries and no managed profile.

The first drag produced exactly the first saved-pair swap. Reacquiring both
slots and dragging back restored the original full configuration map. The dock
revealed at the bottom edge and hid again after the pointer left. Package,
inventory, protected files and the resident launcher remained unchanged. All
temporary input devices, observer, bus name and accessibility flags were
released or restored. No recovery configuration write was needed.

Two earlier attempts remain failed: the first rejected a Qt `V4Sequence` before
input because it was not a JavaScript Array; the second observed the forward
swap and eventual restoration but rejected a read overlapping Plasma's write.
The final test retains strict JSON-list and complete-map checks. It waits only
when both complete snapshots equal one of the two precomputed allowed states;
unknown or mixed changes remain fatal, within the existing five-second deadline.

This proves the installed legacy pair's physical drag/reversal and auto-hide in
that episode. It does not measure held-pixel feedback, hover write counts, exact
setter counts or prove absence of app dispatch. No foreign active-window UUID
was observed; keyboard focus, Escape, managed-profile dragging, overflow,
touchscreen, other outputs and context churn have separate gates. The prior
isolated Qt gesture matrix remains separate evidence. Private receipts:
`.runtime/app-drag-native-20261015/root-native-r1`, `root-native-r2` and
`root-native-r3` (final status `PASS_LEGACY_APP_SLOT_DRAG_REVERSED`).

## Scrolled app viewport and event exclusion — 15 October 2026

`tests/native/task_order.py --area PRIVATE_AREA --viewport` exercises four
pointer cases against the actual Source DockView and TaskManager in an owned
virtual KWin/DBus session. It needs synthetic Model A/B/C desktop entries and a
separate permission entry matching the probe interpreter with
`X-KDE-Wayland-Interfaces=org_kde_plasma_window_management`. The script requires
four strict descendant XDG directories; it neither creates a compositor nor
targets the installed panel. This is a native KDE prerequisite, outside portable CI.

- A valid drop in a pre-scrolled 113 px viewport moves ABC to BAC while retaining
  all window identities, including the separate probe row. Both complete 50 px
  app tiles and the held insertion marker remain inside the viewport. Structural
  model signals, persistence signals and observed delegate clicks stay at zero
  during the hold. Release emits one `profilesJSONChanged`, zero legacy signals
  and zero observed clicks. An independent expected document permits only the
  active profile's launcher splice; every other saved field/profile is preserved.
- A third app with only 3 px visible rejects the pointer inside that visible
  intersection, without a marker or saved/native order change.
- A fully visible app covered by the event body also rejects the drag. The
  pointer is independently inside the app/body intersection, outside the close
  control. The current event, pending queue and sequence are preserved.
- A completion arriving during a valid held move cancels before further motion.
  Clearing it intentionally preserves the sequence; a distinct subsequent move,
  confirmed by the actual DragHandler centroid, cannot rearm the same gesture.

Refused/canceled cases preserve the complete saved JSON bytes and full task-order
snapshot, with zero structural model/persistence/click signals through release.
The spies observe notifications, not exact setter invocations or global app
dispatch. Structural observation covers moves, insertions, removals, resets and
layout changes; snapshots separately check task identities and geometry.

Three private product mutants were rejected at their intended assertions:
removing whole-tile right-bound validation, removing event-width exclusion, and
removing the event visibility invalidation. These copies were never installed.
The final four-case Source run passed without QML warnings; each episode verified
the host shell, installed package, protected configuration and launcher unchanged,
and its owned processes gone. A setup permission failure and a later test-only
handler lookup failure remain recorded; neither is promoted to a product failure.

The existing `--gesture` matrix also passed all 12 cases on the final Source.
Design check reported zero issues, seven design guards passed, and CLI help and
`git diff --check` passed. These native episodes used Fusion; no new KDE-style
or full portable-suite result is claimed for this test-only increment.

No product QML/JS changed in this increment, and no installation or shell reload
was needed. This qualifies stable pre-scrolled geometry in an isolated fixture,
not wheel/touchpad scrolling, autoscroll, held pixel appearance, physical panel
overflow, multiple outputs/scales or changing contexts. Private receipts are under
`.runtime/task-viewport-20261015/`; the final matrix status is
`PASS_SOURCE_TASK_VIEWPORT_GESTURES`.
