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
