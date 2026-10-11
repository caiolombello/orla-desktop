# Battery and media increment 0.2.4 — validation

Recorded: 2026-10-10 (America/Sao_Paulo). Environment: Fedora 44,
Plasma 6.7.5, Qt/PySide6 6.11.2, Wayland, UPower 1.91.4.
This is an alpha increment; **M1, B1 and C1 remain open**.

## Delivered behavior

- System battery is opt-in (`showSystemBattery=false` by default). Only
  UPower `GetDisplayDevice` and aggregate properties are read; peripheral
  enumeration and hardware controls are absent. PeriGauge remains unchanged.
- Refresh runs every 30 seconds while enabled, with a five-second request
  timeout. Valid 0% is displayed. Absent/unavailable/invalid data stays neutral;
  AC/battery, charging and estimated time are shown only when supplied.
- Dock and controls use one native Plasma `Mpris2Model`. Spotify is preferred
  initially when discovered; a manual choice is retained for the session.
  Track/artist text is plain and bounded. Play and Pause are separate calls,
  gated by `canControl` and the current `canPlay`/`canPause`; Previous/Next use
  their respective capabilities. Player removal recovers selection and focus.

## Tests and receipts

The combined regression command passed **96 tests in 32.607 seconds**:

```bash
PYTHONPATH=tests python3 -B -m unittest test_integrations test_package_cli test_calendar test_qml test_appearance test_themes test_release test_battery test_media -v
```

| Group | Tests | Scope |
|---|---:|---|
| Integrations / package CLI | 13 / 17 | Local adapters, optional dependencies, installation and error paths |
| Calendar / dock QML | 3 / 12 | Synthetic UI, including battery opt-in and shared media model wiring |
| Appearance / themes / release bundle | 10 / 12 / 1 | Existing regression coverage and bundle contract |
| Battery | 16 | Typed D-Bus replies, aggregate protocol, 0%, absent/error/timeout, late replies and recovery |
| Media | 12 | Selection, text limits, capabilities, command failure, removal and compact keyboard layout |

Targeted commands:

```bash
python3 -B -m unittest discover -s tests -p 'test_battery.py' -v
python3 -B -m unittest discover -s tests -p 'test_media.py' -v
```

The media suite also passed separately with offscreen, Fusion and
`org.kde.desktop` styles. A Wayland run passed 24 tests (12 media + 12 dock
QML); synthetic input in these tests does not qualify a human panel gesture.
Independent battery, media and dock-wiring reviews reported no outstanding
findings on the reviewed implementation.

Synthetic appearance key tests first assert settled focus on their owned Qt
control before sending one QtTest gesture. This fixes event-loop ordering in
the fixture without claiming native seat activation or changing the product.

A read-only QML SystemBus probe of the real UPower aggregate returned 99%,
AC, fully charged/not charging, with no warnings. This is one point-in-time
observation, not a charge/discharge or multi-device matrix.

A private D-Bus fixture used the actual Plasma 6.7.5 `Mpris2Model` and two
owned synthetic QtDBus receivers identifying as Spotify and VLC. Eight checks
passed: discovery/preference, separately gated Pause and Play, Previous/Next,
revoked control, manual routing, selected-player removal and final empty state.
Receiver ledgers and native signals confirmed the commands; warnings were
empty. The fixture had no actual Spotify client or audio playback.

Separately, an earlier frozen appearance snapshot in a private native Plasma
panel proved Apply/Cancel and KConfig persistence/reload after restarting the
owned shell through programmatic actions. Its package metadata was 0.2.2;
this is evidence about the frozen appearance bytes, not a complete native
qualification of 0.2.4. Programmatic `Popup.Window.open()` closed without an
`opened` signal; attach/transient-parent warnings and missing input serial
leave popup presentation, layout, focus and grabs unqualified. An earlier
help-command attempt had unknown isolation; subsequent positive receipts
used explicit private bus/XDG guards.

## Remaining acceptance work

- Real Spotify with a second real player, audible playback, client opening,
  artwork and progress. No Spotify Web API, account or paid API was used.
- Real desktop without a battery, multiple batteries, UPS and charge/discharge
  transitions. Those states have protocol fixtures, not hardware qualification.
- Human gestures in an installed panel, popup focus/grabs/layout, accessibility,
  scale, multi-monitor geometry and prolonged daily use.
- Full M1/B1/C1 acceptance, stable/beta readiness and other roadmap modules.

The launcher is excluded from this release and its bundle. Portable CI does
not reproduce the complete native/Wayland matrix. Receipts are local validation
artifacts; private absolute paths and personal data are not needed to reproduce
the public test commands above.
