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
