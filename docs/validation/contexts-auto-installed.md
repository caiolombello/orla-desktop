# Automatic profiles — installed default-off validation

## Result and boundary

On 2026-10-15, the applet from Source commit
`c5509a156a2e0a2fb20c28e4fc3c719d9fff2d34` was installed into the live
Plasma 6.7.5 / Wayland session. A separate no-edit visit passed on the installed
applet. Automatic profiles remained disabled throughout. P2 is still partial;
this record does not qualify enabled profile selection or publish a release.

The versioned filename remains `orla-dock-0.2.9.plasmoid`, but these bytes are a
development build, not the published 0.2.9 asset. Its SHA-256 is
`526d1fecea10d780735ea5d6ec7e9655bf64e0cd607606cd80fdef96a7e52970`.
The installed package and the Source/archive maps matched all 72 files.

## Installation and preservation

The operator verified the previous 70-file package, the current 14-file bar,
the exact panel/applet inventory and target binding before mutation. It created
and independently verified a read-only backup and a mode-correct rollback archive
for the previous package. The direct public KPackage upgrade ran while Plasma
was stopped; one explicit start restored the shell. Installation and post-start
checks passed without rollback, secondary errors or automatic service restarts.

The bar, launcher, protected settings and managed layout banks were unchanged.
The applet configuration's complete case-sensitive map remained equal to the
immutable original map plus the previously declared Control Center dialog-size
footprint (`810`/`630`). That footprint predates this update; its geometry
correlation remains unqualified. The original map/banks were not rewritten,
adopted or repaired to make comparison pass.

The dock's `profilesJSON`, `contextsJSON`, `autoContextEnabled` and
`autoContextDefaultProfile` keys remained absent from disk. Separate typed
runtime reads returned empty profile/context documents, automation `false`, an
empty default and timer `0`. Cached key membership was recorded separately;
it was not used as evidence of disk presence. These checks establish the
observed off state, not enabled-mode persistence across a restart.

## Live no-edit visit

The session was unlocked, with no pre-existing own popup. Input used the existing
bounded relative bridge; KWin observations and own-process accessibility nodes
identified the dock and controls. Two clicks performed this finite sequence:

1. Reveal the hidden dock by edge contact and click its Settings control.
2. Select **Contextos**; verify four enabled header tabs with Contextos uniquely
   checked and focused on the same Settings surface.
3. Observe an unchecked, disabled automatic-mode checkbox; a disabled default
   selector showing **Escolha um perfil padrão**; status **Alternância automática
   desativada.**; and no visible Resume control.
4. Send Escape only after confirming the own focused header and active Plasma
   process. Confirm Settings closure, the dock hidden again and no own popup
   remaining in a fresh KWin response.

The sequence passed with 9 relative nudges / 86 total displacement units within
the reviewed 20 / 240 budget. The temporary input devices, observer and bus name
were released; prior accessibility flags were restored. No foreign activation
was observed. Final independent checks again confirmed package, configuration,
inventory, bar, launcher and bank preservation, with automatic mode still off.

This is accessible-state and observed-window evidence. It does not establish
pixel-perfect rendering, hardware input, keyboard-seat routing, focus return to
another application, setter counts or exact discovery-loader lifetime. Opening
Contextos may load the read-only KDE context source even while automation is off.
No screenshot of personal context names or complete accessibility tree was
published.

## Enabled host diagnosis and accessible tabs

A subsequent pristine `plasmawindowed` experiment used a separate owned process,
private XDG directories, a byte-exact copy of the installed 72-file package and
three synthetic profiles. Automation was enabled before launch with a managed
default. The attempt failed its expectation of selecting that default: the
previous profile remained selected. That original FAILED record is retained;
the following diagnosis does not turn it into a positive-selection PASS.

A separate diagnostic copy added only a read-only monitor to `DockView.qml`.
At timer ticks 1, 3 and 6, preferences and all three profiles were loaded,
automation was active and observing, and every interaction/focus blocker was
false. The desktop context was ready; the Activity context was unavailable.
A bounded read of the real ActivityManager service independently returned an
empty current Activity, which its [version-matched contract](https://raw.githubusercontent.com/KDE/plasma-activities/v6.7.5/src/lib/consumer.h)
permits. The existing requirement for both contexts therefore explains the pause.
No Activity or desktop was created or switched. The monitor stayed in the
temporary copy and is absent from Source and the installed package.

Public accessibility navigation also exposed a separate defect: the settings
PageTab controls advertised SetFocus but no Press. Qt's
[PageTab action enumeration](https://raw.githubusercontent.com/qt/qtdeclarative/v6.11.2/src/quick/accessible/qaccessiblequickitem.cpp)
does not add Press automatically. Commit `72ea3ad` supplies the explicit attached
action through the real TabButton click lifecycle. A regression failed on the
old component and passed after the fix in Fusion and KDE; it also checks exclusive
selection, one click per action and refusal while disabled. The affected profile,
context and design suites passed 55 tests with two expected skips per style.
Design check, package build and the synthetic gallery passed; both settings
schemes were visually reviewed. The fix changes no styling or keyboard bindings.

The uninstrumented Source candidate passed five advertised Press actions in a
real Wayland host: Settings → Perfis → Contextos → Aparência → Cancelar.
Accessibility readback showed the prior profile, enabled automation, the chosen
default and status **Aguardando contexto KDE.** The process exited normally,
its singleton disappeared, accessibility flags were restored and all main-session
guards passed. This qualifies candidate AT-SPI navigation and the unavailable
context state, without proving positive automatic selection, physical input,
focus return or panel equivalence.

The one-file fix was then installed with another verified 72-file backup and
mode-correct rollback archive. One controlled stop/start completed without
rollback or secondary errors. Fresh independent checks confirmed Source equals
installed 72, the bar remains 14, and the original configuration projection,
layout banks, launcher and inventory are preserved. Automatic mode remains off
on the user's dock, with all four profile/automation keys absent. The new
development archive SHA-256 is
`3b483b75573e882d5137ab4c38da08b3de56449958436c14a331c4909676666a`;
the public 0.2.9 asset is unchanged. The physical no-edit panel journey above was
not repeated after this final one-file update.

## Private KDE backend transition

A separate isolated KDE episode passed on 2026-10-15 with a private session bus,
virtual KWin compositor and real ActivityManager. A real `plasmawindowed` process
loaded an uninstrumented, byte-exact 72-file applet copy from runtime Source
`72ea3ad`. Preferences, three synthetic profiles and desktop associations were
seeded before launch; no external profile writer or selection hook ran after launch.
With a valid private Activity and two private desktops, real desktop transitions
produced **work → personal → work** in that same process. Semantic document
checks preserved all other profile fields. The final work selection remained in
the private configuration after the host exited normally. No network or input
was used; this is a backend result, not a panel or keyboard journey.

The preceding Phase1 qualified infrastructure only. Phase2's first attempt failed
before desktop creation or applet launch because its guard expected the wrong
`desktops` signature. Its FAILED receipt remains intact. The second attempt
corrected that guard to `a(iss)`, matching the
[KWin 6.7.5 public XML](https://raw.githubusercontent.com/KDE/kwin/v6.7.5/src/org.kde.KWin.VirtualDesktopManager.xml),
and passed without a product-code change. Private sockets and owned children
were removed, with no cleanup errors. A fresh independent postcheck confirmed
the main session's configuration/packages were preserved and its current
Activity remained empty.

Commit `81b22a5` also makes the same accessible-tab regression part of the
existing portable appearance suite: **38/38 passed in both styles, without
skips**. That commit adds test coverage only; the runtime applet above remains
Source `72ea3ad`. Documentation-only updates do not change those tested bytes.

This qualifies real private desktop transitions and semantic on-disk profile
selection, including flush after normal exit. It does not qualify enabled
restart, Activity precedence, UI opt-in, manual override/Resume, appearance
editing, Pomodoro continuity, the user's panel, focus/seat or monitor behavior.
P2 remains partial and the user's installed dock remains automatic-off.

## Waiting-state explanation

Commit `bd695bc` replaces the generic wait message with the unavailable domain:
Activity, desktop or both, with a separate loading state. The both-ready policy,
manual-choice priority, selection logic, focus and visual tokens are unchanged.
Two regressions first failed on the generic message. The updated controller,
dock contexts and design suites then passed **57 tests with one expected skip
per style** (58 cases), in Fusion and KDE. They cover all eight incomplete pairs,
no profile writes while waiting, recovery and existing status priorities.
Design check returned zero issues, the package matched all 72 Source entries,
and four new synthetic 350 px captures were reviewed in both schemes:
[dark](../screenshots/contexts-auto-dark-both-unavailable-350.png) /
[light](../screenshots/contexts-auto-light-both-unavailable-350.png).

This one-file change was installed with a verified read-only 72-file backup and
one controlled stop/start. A fresh independent check confirmed Source, archive
and installed files match; configuration, bar, launcher and original banks are
preserved. Automation stays off, its four disk keys remain absent, autolock is
false and no automatic shell restart occurred. The development archive is
`8c16c527efb31d8b6dca7f9bd4e8012f81f2dc0d357476c24827162f5de6b3a9`;
the public release asset is unchanged. The new message was not exercised in a
native popup after installation. The earlier private backend result qualifies
the previous runtime bytes, not this subsequent text update.

## Private KDE enabled restart

A further private KDE episode used the current 72-file package from `bd695bc`,
including the waiting-state text update. It repeated work → personal → work,
then closed the first applet host normally. With that host and its singleton
absent, changing only the private desktop left the saved work profile intact.
A new host, identified by its own process lifetime and bus owner, loaded the
same configuration and selected personal automatically. No seed, association
or external profile writer ran after the first launch. Personal remained saved
after the second normal exit and after restoring the private desktop while the
host was absent.

Both hosts and the private KDE infrastructure were reaped without cleanup
errors. A fresh independent check confirmed the same main shell process,
unchanged configuration/packages/inventory/bar/launcher/banks, an empty main
Activity, unlocked screen and automation still off. This qualifies enabled
restart and desktop transitions for the private backend on the current runtime
bytes. It does not qualify UI opt-in, manual override/Resume, Activity precedence,
the new waiting message in a native popup, the user's panel or focus/seat.

## Private KDE Activity precedence

The same current runtime also passed private Activity precedence. One Activity
was associated with work, the original desktop with personal, and the default
was games. Six confirmed real context pairs produced work, work, games,
personal, work, work in one host, without an external profile/config writer
after launch. This distinguishes the Activity rule from both desktop and default,
then exercises both fallbacks. Returning to the first Activity restored its last
desktop through KWin; the following desktop change was an explicit public setter.
The host exited normally with work persisted, no cleanup errors and a fresh
main-session preservation check. This is private backend precedence, not UI or
user-panel qualification.

## Accessible profile selectors and installed update

A subsequent private Wayland accessibility visit passed five public navigation
actions without changing preferences. It found that both real profile ComboBoxes
offered only SetFocus, and neither offered an action to open its list. Their real
list delegates also lacked Press in the portable regression. The controls now
expose Press explicitly: the ComboBox opens/closes its existing popup, and each
option calls its own native button `click()`. The ComboBox's normal activation
path still owns selection. Disabled/hidden controls remain inactive.

The regression first failed on the missing action, then passed for opening,
closing, focus acquisition and real option selection in Fusion and KDE styles.
Choosing a manual option only updates the pending choice until **Usar perfil**;
choosing a default does not enable automation or change the active profile.
Eight affected suites passed **170 tests, with two expected TaskManager skips,
per style**. The design check found zero issues. The complete gallery and
additional selector captures were reviewed in both schemes, without QML warnings.
These are synthetic captures, not screenshots of the user's session:
[profiles dark](../screenshots/profiles-selector-dark-350.png) /
[light](../screenshots/profiles-selector-light-350.png),
[contexts dark](../screenshots/contexts-selector-dark-350.png) /
[light](../screenshots/contexts-selector-light-350.png).

The two-file correction is installed locally. One controlled stop/start and a
new read-only backup preserved the complete declared configuration, bar,
launcher, inventory and original banks. A fresh check verified all 72 installed
entries against Source and archive
`ad5328ee89893f70d9ba6f5f4ad7c8c40d453e14bd8cef03fb649968db2df883`.
Automation remains off, all four profile/automation disk keys remain absent,
autolock is false and the screen is unlocked. The public release is unchanged.
The earlier backend episodes tested the preceding runtime. The subsequent UI
journey below uses this installed selector correction.

## Private native opt-in, manual choice and Resume

The corrected installed package passed a complete public accessibility journey
in a private real Wayland/KWin session: **19 Press actions, one SetFocus and nine
strict configuration milestones**. The same applet process and real
Activity/desktop pair remained alive throughout:

- Choosing work as the default kept automation off and the prior profile active.
- Enabling automation kept that prior profile while Settings was open; work
  became active after closing Settings.
- Choosing personal only changed the pending choice. **Usar perfil** committed
  personal, which remained active after closing Settings in the same context.
- A public SetFocus revealed the clipped Resume button. Fresh visibility,
  enabled state and manual/configuration witnesses were revalidated before Press.
  Resume kept personal while Settings was open, then work returned after closure.

The final document persisted after normal host exit. Profiles, associations,
legacy fields and timer were checked semantically at each milestone; only the
intended active profile and two automation preferences changed. No external
profile/configuration writer ran after launch. This does not measure native
setter counts. All owned children exited without forced termination or cleanup
errors; the private accessibility daemon exited and its socket disappeared.
A fresh independent check preserved the main shell process, packages, complete
declared configuration, bar, launcher and original banks. The user's dock remains
off, with its four profile/automation disk keys absent and autolock disabled.

Two earlier full-journey attempts remain FAILED. The first exhausted a shared
deadline without enough timing detail to distinguish total and phase limits.
The second stopped at the Resume eligibility guard without recording which flag
was false. Qt 6.11.2 sets AT-SPI VISIBLE and SHOWING together, so the visitor's
assumption that an offscreen control could have only VISIBLE was incorrect
([version-matched mapping](https://raw.githubusercontent.com/qt/qtbase/v6.11.2/src/gui/accessible/linux/qspi_constant_mappings.cpp)).
The successful independent episode explicitly allowed one focus navigation to
the exact enabled/focusable Resume control after positive manual-state witnesses,
then required fresh VISIBLE and SHOWING before activation. It recorded both
flags false before reveal and true afterward. This does not retroactively identify
the missing flags in the failed attempt. Reader allowance was explicitly 40 s;
the 8 s phase limit, 60 s outer limit and cleanup bounds remained enforced. The
successful reader took 29.358 s. No production patch followed those visitor fixes.

This qualifies the bounded private UI journey, not physical keyboard input,
Wayland seat/focus restoration, the user's panel, dirty appearance drafts,
Pomodoro continuity or multiple monitors. P2 remains partial.

## Private appearance drafts during desktop transitions

Two portable composition regressions exercise the actual profile, appearance,
context and automation states through public accessible theme/footer actions.
Their only new fixture input supplies a normalized context snapshot; popup
visibility supplies the real busy state. The complete appearance suite passed
**42 tests in Fusion and 42 in KDE**, without QML warnings; design check found
zero issues. No production UI or installed package changed in this follow-up.

The installed 72-entry package then passed a private real KWin/Wayland journey:
**16 Press actions, one public SetFocus, 11 configuration milestones and a final
normal-exit/flush check**. With Settings open, changing the real desktop preserved
the selected Paper preview and the saved profile document byte for byte. The
Contexts tab's public current-desktop feedback confirmed that the same Source
observer had consumed each new desktop before returning to Appearance. The
feedback label was read through accessibility; its rendered visibility is not
claimed.

Cancel discarded Work's draft and allowed automatic Personal. In Personal,
another desktop change kept the draft and owner while Settings remained open.
Apply saved only Personal's appearance JSON, Undo restored it, and Paper/Apply
saved the same result again. Closing Settings allowed automatic Work; reopening
showed Glass with no carried draft. The full document persisted after normal
exit. Other profile fields, associations, global preferences, all 13 disabled
legacy flags and the zero timer remained exact. No external configuration/profile
writer ran after host launch. The reader took 35.633 s within its unchanged 40 s
budget; outer runtime and cleanup took 39.788 s. Cleanup completed without errors
or forced termination, and a fresh independent check preserved the main session.

This episode explicitly seeded a private KWin rule before compositor startup to
keep the exact `org.kde.plasmawindowed` class on all desktops. The versioned
[host app ID](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/plasma-windowed/main.cpp)
and [KWin desktop rule](https://raw.githubusercontent.com/KDE/kwin/v6.7.5/src/rules.cpp)
define that fixture; actual visible/enabled controls and Source desktop feedback
remained required. It neither changes the user's window rules nor disables
Orla's popup deactivation/cancellation behavior.

The first episode remains FAILED: after two Press actions, one SetFocus and two
milestones, the Contexts action target was ineligible following the desktop
change. Its exact false visibility/enabled flag and the subsequent profile state
were not recorded. Host residency/focus loss and popup cancellation are a
plausible explanation, not a proven retrospective cause. All children were
reaped without force and the main session was preserved; the inherited cleanup
assertion still reported the reader's failed exit. A separate fresh preservation
helper initially failed on its project import path, before any native check;
only that import path changed in the successful independent postcheck.

These results qualify the bounded private draft/Cancel/Apply/Undo journey.
Physical keyboard/focus/seat, the user's panel, active timer continuity, native
setter counts and monitor behavior remain open. P2 is not complete.

## Private desktop rename, removal and recreation

The same installed package passed a private KWin/Wayland lifecycle journey:
**13 public Press actions, no SetFocus, ten configuration checkpoints and a final
normal-exit persistence check**. The existing owned host/all-desktop fixture and
unchanged runtime limits were reused. The reader took 25.812 s; outer runtime
and cleanup took 30.029 s.

Renaming D1 retained its ID and automatic Personal. Selecting Work through the
real ComboBox remained pending until **Usar perfil**. A second rename retained
manual Work and its exact saved JSON; closing Settings kept that choice in D1.
Removing the current D1 left only D0 and made it current, confirmed by real
readback without a corrective desktop setter. Work at this point alone does
not prove release of manual authority.

Creating D2 reused D1's final name, also equal to the association's saved name,
but produced a different ID. Entering D2 selected default Games, distinguishing
it from both associated Personal and manual Work. The public Contexts feedback
reported one old association preserved by ID. Source name feedback confirmed
both renames; no direct Source-ID read or rendered visibility of these labels
is claimed. The versioned [KWin interface](https://raw.githubusercontent.com/KDE/kwin/v6.7.5/src/org.kde.KWin.VirtualDesktopManager.xml)
defines the public rename/remove/create calls used in this episode.

All profile data remained exact; only the intended active ID changed.
Association JSON stayed byte-identical throughout, including the removed D1
binding. Other global preferences, disabled legacy flags and zero timer stayed
unchanged. Games persisted after normal host exit. Only then was D0 restored
and the owned D2 removed, with the original single-desktop readback and Games
still persisted. Cleanup and a fresh main-session preservation check passed.

The matching portable public-control case also covers an unavailable interval
and repeats the same-name contrast against the saved association name. The
complete appearance/composition suite passed **43 tests per style**, Fusion and
KDE, without warnings. No production package changed. That episode did not
qualify active timer continuity or Activity rename/removal; the separate
journeys below do. Other interaction drafts, the user's panel, focus/seat,
monitor behavior and native setter counts remain open; P2 is still partial.

## Active Pomodoro across automatic profiles and process restart

The unchanged installed 72-entry package passed a separate private KDE/Wayland
journey with the real Pomodoro and public accessible countdown. Synthetic setup
enabled the Pomodoro tile only in Work, bound D0 to Work and D1 to Personal, and
seeded one ten-minute absolute deadline before the first host launch. The actual
Source QML/JavaScript parser, including its Appearance dependency, validated the
profile document. No profile contains timer fields.

The saved remaining value was deliberately 371 seconds, distinct from the
running countdown. The original deadline, remaining value, focus phase,
completed-focus count 3 and 25/5-minute durations stayed exact throughout.
Entire profile documents allowed only activeProfileId changes; raw associations
and all 13 legacy flags were preserved. No external configuration writer ran
after the first launch, and no Press, SetFocus, timer method or clock override
supplied the observations.

| Observation | Real countdown, seconds | Witness |
| --- | --- | --- |
| W1 | 597 | Work, own visible/showing/enabled Pomodoro tile |
| W2 | 596 | Same host, 1.224 seconds after W1 |
| Personal | Hidden | Actual D1/Personal; one Pomodoro node, zero showing; independent host marker still visible/showing/enabled |
| W3 | 593 | Actual D0/Work again |
| W4 | 589 | New host epoch and bus owner, same saved configuration |
| W5 | 587 | Second host, 1.292 seconds after W4 |

Each count matched the original deadline against real wall time. Both hosts
shared a guarded wall/monotonic anchor. The single public name getter had a
400 ms bound; the integer-count interval included an explicit 1000 ms delivery
allowance before rounding. This is compatibility with a quantized countdown,
not a claim of a maximum one-second age or observation of every ticker update.

The certified host-absent interval was **2.601 seconds**, measured from observed
reaped termination to just before the second launch. After a conservative
100 ms clock-error discount, 2500 ms remained. W4 and W5 also had to be below
the minimum count predicted if that entire interval had been paused: **589 <
590** and **587 < 589**. Thus decreasing values alone could not pass a missed
offline interval. The protocol was reviewed and frozen before execution; the
original proposed 1.1-second gap was rejected during static review, never run.

Both hosts exited normally with code 0 and flushed Work with unchanged timer
globals. Each accessibility infrastructure cycle ended completely before the
next. Only after both hosts were absent was D0 restored and the owned D1
removed. Direct children were reaped, daemon exits confirmed and sockets absent,
without forced termination or cleanup errors. The whole episode took 15.311
seconds within its fixed 60-second runtime plus 10-second cleanup budget; the
readers used 5.255/16 and 2.554/12 seconds.

A fresh independent postcheck preserved Source/installation equality, the
complete main configuration, bar, launcher, inventory and original layout
banks. Main automation remained off with all four disk keys absent; autolock
remained disabled, the screen unlocked and the original Plasma process intact.

The matching portable regression uses the production timer's real ticker,
automatic Work/Personal/Work state, confirmed destruction, elapsed time and
recreation. Its complete module passed **32/32 in Fusion and 32/32 in KDE**,
without warnings or skips; design check found zero issues. This portable test
qualifies Qt-instance recreation, separately from the native process restart.
Production code did not change, so no reinstall, reload, version or release
asset was needed. Rendered appearance, user-panel restart, physical focus/seat,
completion/break/reset/sound and full P1/P2 acceptance remain separate.

## Activity rename, current removal and same-name recreation

The same unchanged installed package passed a separate private KDE/Wayland
Activity journey with **13 public Press actions, zero SetFocus, nine strict
configuration checkpoints and one normal-exit persistence check**. There was
one unchanged desktop D0 and no desktop association. The private daemon's
worker-created Activity R was retained as the restoration anchor. Its other
fresh, namespace-created default Activity became subject A with a synthetic
name. The exact two-ID universe was checked before setup and mutations; no
Activity from the main session was adopted or changed.

Synthetic setup bound A to Personal and chose Games as the default. All profile
data, raw associations and 13 legacy flags stayed intact; only activeProfileId
could change. The six inactive-timer values stayed 0/371/false/3/25/5 for deadline,
remaining, break phase, completed focus, focus minutes and break minutes.
No external configuration writer ran after launch.

| Step | Observed result |
| --- | --- |
| Initial A | Automatic Personal |
| Rename A from N1 to N2 | Same ID, updated public Source label, byte-identical saved Personal |
| Choose Work in the public selector | Personal stayed saved until **Usar perfil**; then manual Work |
| Rename A back to N1 | Same ID and manual status, updated Source label, byte-identical saved Work |
| Close Settings | Manual Work remained in A |
| Remove A while it was current | Actual daemon selected R, list contained only R and A's name was absent; automatic Games replaced Work |
| Create C with N1 and select it | New returned ID, distinct from A/R; Games stayed selected |
| Visit Contexts | New current name N1 and exactly one old Activity association preserved by ID |

No corrective Activity setter selected R during A's removal. Games distinguishes
the new confirmed context from both manual Work and associated Personal. C used
the exact last live name and saved lastKnownName of A; retaining Games excludes
adopting the old association by name. Public label reads establish Source
feedback, without claiming their rendered visibility or a directly exposed
Source ID. Every Press required a unique own-PID control with the expected role,
an announced Press action and fresh visible/showing/enabled state.

The private host rule explicitly included all Activities as well as all desktops,
using the versioned KWin [activity/activityrule settings](https://raw.githubusercontent.com/KDE/kwin/v6.7.5/src/rulesettings.kcfg).
It was written and read back before compositor startup, only inside the private
configuration. This is not a direct observation of onAllActivities and does not
qualify the user's panel. Consumed Activity method signatures were checked against
the actual daemon's introspection before new mutations. An older cached XML
differs from the currently published tag; neither unused overloads nor the whole
remote XML were assumed to describe the installed binary.

The host exited normally with code 0 and flushed Games. Only after host absence
was R restored and the owned C removed; the final universe contained R with its
original name and D0 unchanged. Deleted A was not recreated. Direct children
were reaped, accessibility daemon exit confirmed and private sockets absent,
without forced termination or cleanup errors. The reader took **24.704/40
seconds**; the full episode and cleanup took **29.224 seconds** within the
unchanged 60-second runtime plus 10-second cleanup budget. A fresh independent
postcheck preserved the main process, full configuration, bar, launcher,
inventory, original banks and Source/installation equality. Main automation
remained off, its four disk keys absent, autolock disabled and screen unlocked.

The portable lifecycle case now shares its public-control scenario between
desktop and Activity domains, preserving the desktop expectations. The Activity
case additionally checks a synthetic unavailable interval before the confirmed
anchor; it does not claim that exact intermediate frame occurred natively.
The complete composition module passed **44/44 in Fusion and 44/44 in KDE**,
without warnings or skips. No production code, package, reload or release asset
changed. Other interaction drafts, main-panel operation/restart, physical
focus/seat, monitors and native setter counts remain open; P2 is still partial.

## Evidence identifiers

Private execution records are retained locally; they are not shipped as fixtures
or logs. These hashes identify the records summarized above:

| Record | SHA-256 |
| --- | --- |
| Reviewed installer R2 | `42827cd00713c6d6ad16d438d816b704f43e9c64ea24408d37f0c299c780da4e` |
| Installation result | `207b45cd5f21200c894fb5c1070b48868ad687a7eb384b37e9878091f82e99a1` |
| Default-off visitor | `84ad8af058ef219f3e5462e186aa2effdea4f81c3e08372ae84f88ea6d82b71e` |
| Default-off visit result | `3c51d6dd07cde53183d3b960593289979768ac07a48c828b656b57c367150c93` |
| Fresh final preservation result | `9159baddf4c8861bf62379657e9dda90e69d8f12c4ea07227f7405a0477ff527` |
| Original enabled-host FAILED result | `3f0bf805197baf6a1322d3cda49198126c2cedafe021ebb8776437d3550c6443` |
| Instrumented diagnostic result | `7896a26147374bbdd46ada90745871867c054fcfed36da0896df2cb0469fcb07` |
| Read-only Activity service observation | `bae2cb1fdaaf1322ce65352440ae4000507f8d34882c95ea0ed6b7734dda289f` |
| Source candidate AT-SPI result | `92f27093083cc62664199ee133cfb2dbadcd85287fdc0b24429dd970796b9718` |
| Final one-file installation result | `9b87b9157ac0fb2aad1ec8747a7e8b42d040dc7872a7f970739f81bd6f4ffe81` |
| Fresh one-file install/backup verification | `96ff061b862f141fc19da896aaaa8a0e0c789214714c18da04c57dee68da3423` |
| Private KDE Phase1 infrastructure result | `323a4528f2d3f8f65259c8005d14371f98dc1a81958884334c0e5997945cf4bf` |
| Original private KDE Phase2 FAILED result | `7da0268ea2c493423e89cd72f384e74b8fb34b03f1ffc7031bd95570d16d3706` |
| Private KDE Phase2 backend result | `38c9e62c45bf87ae0b81d61b0822e4219b3bf7e1052fade8e7a8faf8ccd0e963` |
| Fresh private KDE Phase2 postcheck | `4a67ee4cd22f54b65c6b283910bdee837f96ce02fe5bcb2a7ac99d4eb9e118d8` |
| Waiting explanation RED result | `e9c6a9bae98937a779f7bba07e045cb3c3233871ac9faf9ac07f4086c297073e` |
| Waiting explanation GREEN/design/gallery result | `2ca4443e77955d5ccf12a0aa083a2b7c55782e82ac3492942391d68587ec4aaf` |
| Waiting explanation installation result | `4550676fd3aa3dd14edfcaeb8df18717413a46247d3898f92f71598a99c84092` |
| Fresh waiting explanation install/backup check | `d0737518cbb76e91fb8ebe45a4d0db273ac17d4e88c50fcddf86e1e7140bafb7` |
| Private KDE enabled-restart result | `73cb29e3b6c542e051c61fabbc97d4b0b1fc1319d82da9a0c143daf2297b1c21` |
| Fresh enabled-restart postcheck | `66b3a707e741d854032b328d167d684c501b58d127e4f3fc4f638f1953933b25` |
| Private KDE Activity-precedence result | `8b26643e15bcefe02013970bf18c38f80f1ef5958e71eb9abdae231d13b74cd7` |
| Fresh Activity-precedence postcheck | `628e2c4a76750839c47820918e4a75da5241c8257fb53af4c1e1641de74c8c5f` |
| Private native accessibility discovery | `2ac91e8b0bab17fcc1ba75a101c943f06b401724b0f3bf5b478a795e17773e34` |
| Fresh accessibility-discovery postcheck | `e8f0a52a18dffa22265648347e030b4f4f8e4ef185d8e965a260ec703bc0f5aa` |
| Selector missing-Press RED | `713d736c56caaf87dfa74c7f86978a0f1d3bbda5abf6ac25ecfa6251a2af2f8c` |
| Selector final affected suites | `4da7270d5c1c2a3f991e24400e559c62ccbe6953ab434caa55f827551dc97a2a` |
| Selector related suites | `b9b94a65ed1a79110499f5d10bd0e3e617267606f6c70e5ea2ea6f07cf8425b2` |
| Final selector gallery/captures manifest | `286021fb842d1c64a2450c6caa8c44cd72fe248414535e82083c6c2e8fcf7f92` |
| Selector installation result | `7a0ea058f451e06c8b789a14da04554bb9b16a5b3f4f4a11d6accb1262a3e2ea` |
| Fresh selector installation/backup check | `b18783ab35df5d13c3d57eec9902d32a91786d3f217e7ad871811273ed801087` |
| First full UI journey FAILED | `a07086790490ea56cae55db74ff8a9561138e9d896075032db02d6bd520e8a08` |
| First failed-journey main preservation | `926c20613ce1e8bdf04a372c9005f6434b3df2764eb660ed6815c9efcabb7a43` |
| Second full UI journey FAILED | `0ef76addbd80828b3a1c32df51d8377443fe63cd1b3828efabc3e66a9a86a670` |
| Second failed-journey main preservation | `9db759fe293416aa07024c37794d6a9dfde081d18137128e80c39704fdfb2c02` |
| Private full UI journey PASS | `34b45b19c6b4ce427219babb2bb4a03510d8d4e65d27e87306ec9625bebd9055` |
| Private UI actions/configuration milestones | `78a515e9659d1df1168f914f9e1e7755871fe399bc5649d5123f379d41cbf7b7` |
| Fresh full UI journey postcheck | `b651d123c41f27cfb28a16b4849972582282c490cf18ddb70f231af58a04635d` |
| Complete portable appearance composition suite | `f22f4b4bf4b33582fd9d36c101e4f41b59b2dde360124a03c737fca425272330` |
| First private appearance journey FAILED | `8c51ea5d7d2c17de340308bab024b4e5221ffd7ca6281b314147373976350323` |
| Failed appearance journey main preservation | `61fd13ed1d1cbdb1f7aee010ab83615aeff77f934df46558e6daf5729984f9cf` |
| Private appearance journey PASS | `d04fd0b3dc4e6088f78625d8ac8a3b04679eebf4d6939deff29fabc6aaa826c9` |
| Appearance actions/configuration milestones | `9bbf75d19b3f9920137ab7dbf64748e57372a3794aefaab7ebe0cfdef1b18bed` |
| Fresh appearance journey postcheck | `de515e43bb61e45c288d70cd2567bf3a26944b8aa9076df9141f2131d8f21357` |
| Complete portable lifecycle composition suite | `0676f8c1f7c0b7013fc66da49486d636a9fe78092dddfe2bd6490b05c9f2efc3` |
| Private desktop lifecycle journey PASS | `fc53af663ba40bc460a290ac4845761b69176847d6f76e073d39f3cd8a6f54ee` |
| Lifecycle actions/configuration milestones | `f55782a159ae91083a1e84592f9a460068aee97233be7bb16640895e6851f860` |
| Fresh lifecycle journey postcheck | `634cadd047e3cc1f688f8158f3b25632f654007d3fccdfad99e3046215837773` |
| Pomodoro native journey PASS | `a607304ccdaeb2ebdb3e9ad93f7c3e42f78a86cfc742d8e68a7d3b894d70a71c` |
| Pomodoro first-host observations | `67d291acbed526a58c353d309a3b2358dcef95a35d6501dd232013dc01ccd8fb` |
| Pomodoro restarted-host observations | `9e63f78c07bbd5981336143cd8474af61a8b876e7a00a0fdad0c89fe48ad5650` |
| Fresh Pomodoro journey postcheck | `141cb49f0f18a5fdce2902775cb78a43729de22c4512d46782a1f351bb02f15e` |
| Complete portable Activity composition suite | `8238fcca6a5cf8f2af3f51fbd2e040b43629f09d381534ea43b60bc9390dd3fc` |
| Private Activity lifecycle journey PASS | `a702280231a7a8dd9a1ab9b2b871a502e80c2078b0189840f5b2a2d3976ff61e` |
| Activity actions/configuration checkpoints | `7ecc6825c2a3be5c54599daf80d7634450d275ea9f963afd8c618dd5dc2b2849` |
| Fresh Activity lifecycle postcheck | `64a94e571b6be984cca648f3365299ecf750672ca68b99b3fb2981a692277c9e` |

## Explicit desktop-only policy in Source

The current Source adds a per-dock `autoContextPolicy` String preference. Its
`activity-desktop` default preserves the existing both-ready rule. Choosing
**Somente áreas** explicitly uses desktop bindings and the default while ignoring
Activity availability; retained Activity associations are unchanged. This is a
user choice, not outage classification. Selecting the policy never enables
automation. Unknown saved values pause without rewriting them; the selector stays
repairable. `undefined` is the legacy absence sentinel for portable callers.

A committed policy change resumes the rule after existing interaction barriers
clear. A newer manual choice wins, including a selection from the raw preference
notification before the controller handles it. With no confirmed required
identity yet, the first ready identity attaches that choice; only a later
different identity, Resume or another committed policy change releases it. This
deliberate startup rule also applies to the combined mode.

Causal regressions first refused the previous Source. Review also reproduced and
fixed a newer matching-target manual selection being mistaken for an older
automatic commit, and an invalid `NaN` policy repeatedly scheduling work while
off. Public selector tests cover accessible actions, actual option clicks,
keyboard selection/Escape/Tab, invalid-value repair, one-key-only writes and
short-viewport focus. The new row and expanded help both keep their full focus
rings visible; no popup budget or design token changed.

The final controller suite passed 47/47 per style. Contexts composition passed
27 tests with one expected TaskManager skip per style. Appearance composition
passed 44/44, and manual-profile composition passed 31 tests with one expected
TaskManager skip per style. Total: **149 passed and two expected skips per style**,
in Fusion and `org.kde.desktop`, without QML warnings. Design check and all seven
design guards passed. The synthetic gallery was rendered in both schemes;
350/420 px menus, help and focus were reviewed. These are offscreen results,
separate from installing or exercising this new policy in KDE.

| Source verification | SHA-256 |
| --- | --- |
| Controller suite, Fusion | `30c8b8a6fcb10b72134ff3695c71df29801f6fd145dd711c19f3fb53d2ff410b` |
| Controller suite, KDE | `6df28d7c163a707844f4634f26f46c7684506993fd700f9bd15fbdad02bdf048` |
| Contexts composition, KDE | `ae6c19f60f60cd8df8f219d77ab003d36bfc6d824cbd5c6cfce11e1c85f59230` |
| Final appearance/profile consumers, both styles | `7275df00bd5354de628ce206d8ae23a6081c83bb19ba5760deb95f815d9ecf4d` |

## Desktop-only development package installation

The 72-entry development archive `de59d4c58099edad3eaaa36205fe2ed0249f9421bf25c64dddce1fe2e14c4a15`
was installed with one controlled Plasma stop/start. Only the schema, automatic
controller, automatic controls and Contexts explanation changed within the
package. The old package has a new read-only durable backup and a verified
rollback archive preserving its original modes. No rollback was needed.

A fresh independent postcheck confirmed Source/archive/installed equality,
the complete original main configuration plus the previously declared 810/630
dialog overlay, inventory, bar roles and bytes, launcher and original layout
banks. Automation stayed OFF; all five profile/automation disk keys, including
`autoContextPolicy`, remain absent. The typed runtime read is paired with the
pinned new String schema default `activity-desktop`; a caller fallback before
the upgrade was explicitly recorded only as a fallback. Cache membership is
not used as evidence of disk presence. Autolock remains false, the screen was
unlocked and automatic shell restarts stayed zero. This installation check does
not itself qualify the new policy UI or automatic behavior.

| Installation evidence | SHA-256 |
| --- | --- |
| Controlled installation | `f43d26403b36d98d3f42596f8fc58ffe0b6d6aafed5d973d516307ffb86a0290` |
| Fresh package/backup/main-preservation check | `efb9b0cbae65735e35d49bff0e41828ad13c2658939a28e58fbe3c823c8cef67` |

## Desktop-only private KDE attempt R1

The first attempt failed at the unchanged eight-second `choose_policy` phase
deadline. It reached two public Press actions and one SetFocus: the policy
control became visible/showing after focus, but the reader stopped before
pressing it. The sole completed milestone was the initial strict-policy/OFF
state. A real owned ActivityManager reported an empty Activity list and current
Activity. This attempt did not select the new policy, enable automation or
qualify desktop switching; it does not demonstrate a production defect.

The outer result retained `namespace_exit`, and the reader retained
`reader_phase_deadline`. The nested lifecycle also retained
`reader_cleanup_AssertionError`: its already-failed reader exited with code 1.
Every recorded direct child was nevertheless reaped without forced cleanup,
the accessibility daemon exit was confirmed, and private sockets were absent.
A fresh independent postcheck confirmed the main session, installed package,
configuration and five absent keys were preserved. That preservation PASS does
not change the failed journey result.

The R2 reader replaces redundant full accessibility-tree traversals with one
fresh frame per checkpoint. It discards the pre-focus frame after SetFocus and
retains a separate fresh eligibility check before Press. Source, actions,
deadlines, disk/context guards and cleanup are unchanged. Individual R1 scan
durations were not measured, so the structural reduction is not a measured
speedup or a conclusive explanation of every elapsed millisecond.

| R1 evidence | SHA-256 |
| --- | --- |
| Failed outer episode | `1f233de0927f75313b6085125e34b67157cc192e6b2993871cece63ea24987ae` |
| Failed reader | `09e8a9246597bafb78755e6d4561a7baa3d15adac0d80360ba73908833eb7544` |
| Fresh main-session preservation | `dff7a618c5e61a3cc42fc425f7ca70e9df609c2179dcc936ac732109bcee53d3` |

## Desktop-only private KDE attempt R2

The first host completed all six reader milestones in 15.369 seconds with
seven public Press actions and one SetFocus. With the same live empty
ActivityManager, selecting **Somente áreas** kept automation OFF and the legacy
profile unchanged. Explicitly enabling it while Settings was open still kept
that profile. Closing Settings then selected Work on D0; real KWin transitions
selected Personal on D1 and Work on D0. The host exited normally and its saved
document, raw bindings, default, thirteen flat flags and six timer fields met
the strict fixture checks. The complete 72-entry package stayed unchanged.
This qualifies that bounded public UI and single-host automatic journey.

With the host absent, changing only the desktop to D1 left the saved profile
at Work, confirming the restart test was non-vacuous. The second host reached
the `private-host-discovery` stage, whose implementation also waits for the
expected saved profile before starting the accessibility reader. That stage
failed with `TimeoutExpired` / `owned_wait_deadline`; no second-reader receipt
exists. The post-cleanup document still selected Work. The record does not
identify the exact timed-out configuration read or the second host's in-memory
state. It therefore leaves this policy's restart gate open; the overall R2
result remains FAILED despite the completed first-host journey.

All recorded children were reaped without forced cleanup; accessibility daemon
exits and socket removal were confirmed, with no lifecycle cleanup errors.
A fresh independent postcheck again confirmed the complete declared main
session and package were preserved, automation OFF, five disk keys absent,
autolock false, screen unlocked and zero automatic shell restarts. It records
the missing second reader as `ABSENT`, without manufacturing a completion.

| R2 evidence | SHA-256 |
| --- | --- |
| Failed overall episode | `9bf2c9ff02ffddbf23fb1013b27f4d260fc2737c842e41bd7f62959d3a83a550` |
| Passed first-host reader | `107440c33db992e033c6ff617ecd8703f816375d05d6c7c813cfa08d2995a8a4` |
| Session lifecycle and restart failure | `8fb1a38e3af59f1aca7b4419b5a854365128894eb3d7c5eade73df5e8cd42e71` |
| Fresh main-session preservation | `df98cbcedf6edd33626ceb98b6d25720b1fd0ee4c4281cb8507833b664694902` |

## Next native gates

The private backend transition, enabled-restart and Activity-precedence gates,
plus the bounded private UI opt-in/manual/Resume and appearance draft journeys,
are now qualified;
the earlier main-session
experiment still lacks a current Activity and remains a preserved negative
case under the combined policy. The explicit desktop-only Source choice above
does not reinterpret that earlier negative result.

The bounded desktop and Activity rename/removal/recreation and active Pomodoro
journeys are now qualified in the private KDE fixture on the preceding installed
package. The new desktop-only policy has Source/UI/tests, the guarded local
installation and the first-host empty-Activity/public-opt-in/desktop journey
above. Its restart using the same saved configuration remains open after R2.
Diagnose the second-host wait before changing Source or retrying; neither a
larger timeout nor the first-host PASS can substitute for a verified restart.
Other interaction drafts, the user's panel, focus/seat and monitor behavior also
remain open. Persisted timerRemaining alone is not the running countdown; the
Pomodoro qualification above required the original deadline and real counts.
Private backend desktop transitions do not establish these behaviors
in the user's panel. A private XDG directory alone does not isolate the
`plasmawindowed` session-bus singleton; the successful episode used a private bus
([Plasma 6.7.5 implementation](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/plasma-windowed/main.cpp)).
Any temporary desktop or panel needs a separately reviewed cleanup path before
creation. Offscreen tests, package reloads and this bounded private backend
result do not close the remaining gates.
[P2's acceptance criteria](../../ROADMAP.md#05--perfis-activities-e-áreas-de-trabalho)
remain unchanged.
