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

## Next native gates

The private backend transition, enabled-restart and Activity-precedence gates,
plus the bounded private UI opt-in/manual/Resume journey, are now qualified;
the earlier main-session
experiment still lacks a current Activity and remains a preserved negative
case. Desktop-only automation needs an explicit policy for stable absence versus
transient unavailability before code or fallback rules change.

Next qualify dirty appearance/Cancel/Apply, rename/removal of
associated contexts, Pomodoro continuity, the user's panel, focus/seat and monitor
behavior. Private backend desktop transitions do not establish these behaviors
in the user's panel. A private XDG directory alone does not isolate the
`plasmawindowed` session-bus singleton; the successful episode used a private bus
([Plasma 6.7.5 implementation](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/plasma-windowed/main.cpp)).
Any temporary desktop or panel needs a separately reviewed cleanup path before
creation. Offscreen tests, package reloads and this bounded private backend
result do not close the remaining gates.
[P2's acceptance criteria](../../ROADMAP.md#05--perfis-activities-e-áreas-de-trabalho)
remain unchanged.
