# Appearance increment 0.2.3 — validation

Environment: Fedora 44, Plasma 6.7.5, Qt/PySide6 6.11.2, Wayland,
Python 3.14.7. This is an alpha increment of C1/UX1; those milestones remain open.

## Delivered behavior

`appearanceJSON` is a separate, validated override. An empty or invalid override
uses the existing theme/icon/motion preferences without rewriting them. Preview
changes the rendered dock only. Apply persists a validated snapshot; Cancel,
Escape and closing settings discard the preview. Undo restores the previous
applied snapshot once per session. Restore prepares the earlier preferences and
requires Apply before clearing the override. Widget settings retain their
existing immediate-save behavior, stated in their separate tab.

The editor uses a stable palette independently of custom dock colors. Fields
scroll; Apply/Cancel/Undo remain outside that scroll area. Preferences height is
bounded by the attached screen budget, and focused fields are revealed.

## Evidence

- 10 new appearance interaction tests pass, including actual control clicks and
  keyboard events, invalid colors/nonfinite/range/type/version rejection,
  component recreation, preview/cancel/undo/restore, and rendered dock properties.
- The full settings composition with a 420 px height budget keeps all three
  actions inside its content area; Shift+Tab reveals Restore in the viewport.
- 10 existing QML tests, 3 calendar tests, 13 integration tests, 17 CLI tests,
  12 theme tests and one release-bundle test pass: **66 tests total**.
- Independent review approved the final implementation with no outstanding
  findings. Synthetic screenshots of the editor and full popup were inspected.

Reproduce in a compatible KDE/Qt environment:

```bash
PYTHONPATH=tests python3 -m unittest test_calendar test_integrations test_package_cli test_qml test_appearance test_themes test_release -v
```

Appearance tests use synthetic configuration. Popup interaction tests select
`Popup.Item` because synthetic Qt events do not provide a Wayland seat grab
serial. Recreating the state component proves serialization/rehydration in that
fixture; it does not prove persistence in a user's running Plasma/KConfig.
Portable CI runs integration, CLI, theme and bundle tests. QML/appearance tests
require the KDE runtime and remain separately qualified here.

## Remaining acceptance work

Native panel popup positioning, real focus/grabs, KConfig/restart, reserved
geometry on multiple monitors, scale/long-text/accessibility matrices, widget
organization, profiles and configuration import/export remain open. Declarative
community theme files can be validated/packed but are not imported/applied by
this editor. No blur, full C1 completion or 1.0 daily-use qualification is claimed.


## Progressive appearance — 15 October 2026

This later Source increment keeps the original history above. Presets and theme
cards lead into form/motion; colors and experimental theme JSON live under an
initially collapsed **Ajustes avançados**. Expansion is view state only. Apply and
Undo preserve it during the same edit; cancel/reopen resets it. Hidden controls
leave the Tab chain, and collapsing a valid focused section returns focus before
hiding it. Space and Return operate the disclosure. Escape still discards the
whole settings preview through the existing popup lifecycle.

Canonical token validation reveals invalid colors. Pending/invalid theme JSON
keeps its nested editor accessible. A valid previously previewed theme can also
block portable import because its text remains: the UI exposes **Limpar JSON**
even during that import, while theme editing/preview stay disabled. Clearing
preserves portable input and the last good appearance; an explicit retry previews
the portable candidate. No new preferences, tokens, data formats or popup budgets
were introduced.

Verification on Qt/PySide6 6.11.2:

- The three initial behavior tests failed against the old editor before the UI
  change. A separate portable/theme conflict test failed before its recovery fix.
- Appearance, portable appearance/parser/dock and profile suites: 78 passed and
  one Wayland-dependent test skipped under **each** of Fusion and org.kde.desktop.
  The five new component cases are included explicitly in portable CI; the new
  conflict case runs with the existing portable-preset suite.
- Design check: zero issues; seven design guards passed. The complete gallery
  generated 56 captures, including four new frames per scheme. Root inspected
  both schemes at the existing 420 px budget. No screenshot uses user data.
- The broader 108-test run was **not green**: the production native-dialog test
  failed under both styles, and the audio pointer-confirmation test also failed
  under KDE. Both failures reproduced in an isolated copy using the previous
  editor. They are outside this change and remain open; four Wayland cases were
  skipped in each broader run. No full-suite/native success is inferred.
- Early harness failures were corrected: unrestricted Python child-item traversal
  hit a local Shiboken assertion; scoped lookup avoids unrelated native wrappers.
  Gallery lookup scope errors were fixed without changing launcher product code.

The applet package was built and installed into the actual local Plasma session,
with a complete previous-package backup and rollback archive. Only
`AppearanceEditor.qml` differed from the previously installed package. Plasma was
stopped/started once through its verified current-user service. An immediate
inventory observation saw panels with screen=-1 and was retained as FAILED;
a later read-only observation matched the original inventory exactly, with no
second install/restart or configuration rewrite. The managed launcher retained
the same PID/invocation. Panel/app IDs, configuration bytes after stop, shortcut
and layout-bank pins were unchanged; current-shell journal inspection found no
relevant AppearanceEditor/dock QML error. This proves installation/reload and
preservation only. **Physical interaction, native popup anchoring, focus/grabs,
assistive technology, multiple monitors and light native Plasma remain UNRUN for
this increment.** No release version or published asset changed.

| State at 420 px | Dark | Light |
| --- | --- | --- |
| Initial, advanced collapsed | [Capture](../screenshots/appearance-advanced/appearance-dark-collapsed-420.png) | [Capture](../screenshots/appearance-advanced/appearance-light-collapsed-420.png) |
| Common controls, keyboard focus | [Capture](../screenshots/appearance-advanced/appearance-dark-common-420.png) | [Capture](../screenshots/appearance-advanced/appearance-light-common-420.png) |
| Advanced colors | [Capture](../screenshots/appearance-advanced/appearance-dark-colors-420.png) | [Capture](../screenshots/appearance-advanced/appearance-light-colors-420.png) |
| Recoverable JSON error | [Capture](../screenshots/appearance-advanced/appearance-dark-json-error-420.png) | [Capture](../screenshots/appearance-advanced/appearance-light-json-error-420.png) |

Next acceptance work is the bounded physical visit to the installed popup,
followed by density/scroll review on short screens. C1/UX1/DX2 remain partial.


## Installed popup keyboard followup — 15 October 2026

The later bounded visit used the **actual installed Orla applet** in the running
Plasma 6.7.5/Wayland session, with one enabled output at scale 1.45. Installed
`AppearanceEditor.qml` matched product commit `77a7b854581da516f8327ee066626a85ba88fb91`
(SHA-256 `a2d4083493a6d5d155349a41445e2d5df626ae7bd337d37abbe1746490d902cf`).
No new package install, shell/launcher restart or product instrumentation occurred.

AT-SPI selected only the confirmed Plasma process and exact known Orla control
names. Its native Press action opened settings; SetFocus explicitly selected
controls, including those initially below the scroll viewport. Temporary uinput
devices then sent actual keys through the session. Success required subsequent
accessible UI outcomes, rather than input-emission acknowledgements alone:

- The installed editor began with advanced colors/JSON hidden. Physical Space
  expanded the section; Tab focused the first color field.
- After explicit AT-SPI focus on the disclosure, Space collapsed it and retained
  that focus. This does **not** prove automatic focus return from a descendant.
- Enter expanded it again. The theme editor accepted the synthetic text `invalid`
  from physical keys. Tab reached its preview action; Space rejected the input,
  retained that text, returned focus to the field and left Apply disabled. The
  specific rendered error message was not checked.
- Escape closed the popup. Reopening via the accessibility action started
  collapsed; physical Space on the explicitly focused Cancel action closed it.
  No Apply, defaults, preset/profile change or app launch was requested.

The final attempt completed without input-cleanup errors. Accessibility IsEnabled
and ScreenReaderEnabled were initially false and were restored to those values.
The four checked configuration files (Plasma applets, plasmashell, global shortcuts
and KWin) retained their SHA-256 hashes. Plasma and the managed launcher retained
the same MainPID/ActiveState/InvocationID snapshots. A separate read-only pass
confirmed 132 previously protected file/hash/mode entries, including launcher
and layout banks. No whole-configuration or general focus-safety claim follows
from those specific checks.

Earlier attempts are preserved privately: physical pointer opening did not reach
the expected popup; later scripts needed to distinguish clipped controls from
hidden sections and the two identically named preview buttons. The final route
uses the actual Tab chain for the theme preview. These were validation-selector
changes, not product changes. Every attempt restored temporary accessibility and
reported unchanged checked configuration/service snapshots.

**Qualified here:** installed-popup keyboard interactions with explicitly stated
accessibility opening/focus, recoverable invalid theme input and cancel/reopen.
**Still unqualified:** precise physical pointer entry, spontaneous focus/grabs,
automatic descendant-to-disclosure focus return in native Plasma, native pixel
review/capture, assistive-technology usability, light native scheme and multiple
monitors. The synthetic gallery above remains the visual evidence.

Both CI checks passed on the product commit: [portable tests/package](https://github.com/caiolombello/orla-desktop/actions/runs/38681023171/job/116245380180)
and [launcher build/CTest](https://github.com/caiolombello/orla-desktop/actions/runs/38681023171/job/116245380342).
The unrelated broader offscreen failures recorded above remain open.

Next UX work reduces preset/common-control density on short screens while
preserving error recovery, preview/cancel and the existing popup budget.


## Compact preset chooser — 15 October 2026

The next UX1 increment folds the preset grid and portable appearance behind
**Presets e aparência portátil**, initially closed. The four names and current
preview status remain outside the fold. Exact preview identity is derived from
the effective appearance and widget list; no saved/last-used preset identity is
invented. A legacy configuration keeps its visible **Ir para Perfis** route and
cannot choose a preset or import implicitly.

Opening preserves the existing four cards and their keyboard order. A pending
or invalid portable input reveals both sections and prevents hiding the recovery
path. A valid preview can be collapsed manually with its status retained; focus
moves from a descendant before hiding it. Cancel/reopen resets the two view-only
sections. Apply/Undo within the same edit preserve their openness. Deferred issue
revelation checks current state, so a synchronous successful catalog choice does
not unexpectedly open JSON. No persisted preference, parser format, token,
font, target size or popup budget changed.

At the existing 420 px gallery budget, the collapsed managed view now shows all
three basic theme cards earlier. The legacy profile route uses extra space and
common numeric controls still require scrolling; this does not claim that the
entire editor fits without scrolling. The narrow 350 px dock test caught a
selected **Estúdio · Em prévia** caption overflow. The card suffix became
**· Prévia**, while status and accessibility keep **Em prévia**. Neither geometry
nor the text-fit tolerance was relaxed.

Verification on Qt/PySide6 6.11.2:

- Three new behavior cases exercised closed Tab skipping/Space expansion,
  collapsing from a focused child with preview status retained, and pending/error
  revelation plus clean cancel/reopen. The old UI lacked the new disclosure and
  failed the initial checks. Existing expanded navigation and persistence guards
  remain covered, including the real-dock fixture at its default width.
- Appearance, portable appearance/parser/dock and profile suites ran 86 tests
  under **each** of Fusion and org.kde.desktop: **85 passed, one skipped**. The
  skipped desktop-URL/TaskManager case needs a Wayland/X11 session. These counts
  include both fixture variants of the new cases.
- Design check reported zero issues; all seven design guards passed. The complete
  gallery generated 62 PNGs including its index. Eight relevant synthetic frames
  below were inspected across both schemes. The gallery waits for actual popup
  closed/opened signals when changing its synthetic profile, rather than racing
  the exit animation.
- Earlier failing runs and gallery lifecycle failures remain in private evidence.
  The broader unrelated native-dialog/audio offscreen failures recorded above
  were not rerun or relabeled green. No launcher/C++ change or local CTest run is
  included in this increment.

| State at 420 px | Dark | Light |
| --- | --- | --- |
| Compact, legacy preferences | [Capture](../screenshots/appearance-compact/preset-compact-dark-legacy-420.png) | [Capture](../screenshots/appearance-compact/preset-compact-light-legacy-420.png) |
| Compact, managed profile | [Capture](../screenshots/appearance-compact/preset-compact-dark-managed-420.png) | [Capture](../screenshots/appearance-compact/preset-compact-light-managed-420.png) |
| Catalog preview, Maré / Jogo | [Capture](../screenshots/appearance-compact/preset-catalog-dark-mare-420.png) | [Capture](../screenshots/appearance-compact/preset-catalog-light-jogo-420.png) |
| Invalid portable input retained | [Capture](../screenshots/appearance-compact/preset-portable-dark-invalid-420.png) | [Capture](../screenshots/appearance-compact/preset-portable-light-invalid-420.png) |


### Installed compact popup: bounded keyboard visit

The public applet installer updated the local package, with a durable previous
package/rollback backup. The package contained the same 67 members and only
`AppearancePresetControls.qml` changed from the prior installed package. The
installed file matches SHA-256
`f81d720a5aac684d937fd8b52c5078df1bf4ec136aebb4e3f1a1211c67dd359f`.
A single guarded Plasma stop/install/start completed. Read-only readiness checks
waited through three temporary unmapped-screen observations before admitting an
exact inventory match; no second installation/restart or configuration repair
occurred. Panel/app IDs, configuration target, launcher process/invocation and
protected files were preserved. No published release asset/version changed.

The later visit used the installed applet in Plasma 6.7.5/Wayland, one enabled
output at scale 1.45. Its current configuration uses legacy preferences: no
profile was initialized, selected or migrated. AT-SPI Press opened the known
settings control, and SetFocus explicitly selected known controls. Temporary
uinput devices sent actual keys; completion required accessible UI outcomes:

- The chooser began collapsed. Tab from its explicitly focused disclosure
  reached the visible legacy **Ir para Perfis** route.
- Space expanded the chooser. The four actual card buttons were disabled in
  legacy mode. Return on the explicitly focused portable disclosure expanded its
  editor; export was available and import remained disabled. Neither was invoked.
- After explicit focus on Export, AT-SPI activation of the outer disclosure
  collapsed both groups; the header reported focus and the inner controls were
  hidden. This observes the resulting focus state, not internal timing or a
  physical pointer interaction.
- Return reopened the catalog with portable JSON collapsed. Space expanded the
  portable section; Escape closed the popup. Reopening began with both sections
  collapsed; Space on explicitly focused Cancel closed it without Apply.

**The next Tab from the legacy profile route to the first theme remains
UNQUALIFIED.** The observer did not confirm focus on the theme checkbox. Earlier
attempts that expected it remain FAILED, alongside registration readiness and
homonymous card/label selector failures. Later selectors distinguish actual card
button roles; no product workaround was added. Multiple remembered accessibility
focus states across Plasma windows do not identify a unique keyboard receiver.
The final bounded functional result therefore does not qualify that next Tab,
spontaneous focus/grabs, native pointer entry, managed preset selection/import,
native pixel review, other schemes/displays or general accessibility usability.
Managed selection/import and complete focus chains remain offscreen evidence.

Every visit restored temporary accessibility flags and reported unchanged hashes
for the four checked configuration files plus unchanged Plasma/launcher service
snapshots. A separate final read confirmed all 132 protected file/hash/mode
entries and absence of all five created input-device pairs. No Apply, export,
preset/profile change, app launch or native screenshot was performed. The visual
evidence remains the synthetic gallery above. C1/UX1/DX2 remain partial.
