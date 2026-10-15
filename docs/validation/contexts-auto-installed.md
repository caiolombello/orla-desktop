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

## Next native gates

First qualify enabled selection from the real KDE models in a separately owned
instance, with private preferences and no changes to the user's dock profiles.
A positive test needs both real contexts ready; this session's missing current
Activity does not meet that precondition. Desktop-only automation needs an
explicit policy for stable absence versus transient unavailability before code
or fallback rules change.
A real `plasmawindowed` host can qualify that narrower path, but cannot establish
panel behavior or reaction to a context transition by itself. A private XDG
directory does not isolate its session-bus singleton; an existing host must be
detected rather than reused or displaced ([Plasma 6.7.5 implementation](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/plasma-windowed/main.cpp)).

Then qualify actual desktop transitions, Activity precedence, manual override and
Resume, dirty appearance/Cancel/Apply, restart with automation enabled,
rename/removal of associated contexts, Pomodoro continuity and monitor behavior.
Any temporary desktop or panel needs a separately reviewed cleanup path before
creation. Offscreen tests, the controlled package reload and this no-edit visit
do not close those gates. [P2's acceptance criteria](../../ROADMAP.md#05--perfis-activities-e-áreas-de-trabalho)
remain unchanged.
