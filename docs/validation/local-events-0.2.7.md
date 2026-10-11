# Local Pomodoro toast validation — 0.2.7 release

This record covers a default-off, in-dock notice for one event class: completion
of a Pomodoro focus or break period. The [0.2.7 alpha release](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.7)
was published from source commit `9ca1792ee3e9c20ad770042d2d441aa1ae6efbce`
(PR 16, merge `1e61a54a8337e854f1369d224a03a38da61d0ff3`). CI run
[38111731691](https://github.com/caiolombello/orla-desktop/actions/runs/38111731691)
succeeded. An anonymous public-download check returned HTTP 200 for all three
assets and found exact build matches. Installation and upgrade were not run;
native admission remains false. This separates publication evidence from bounded
source/fixture evidence and does not qualify native Plasma behavior.

| Public asset | Bytes | SHA-256 | Build match |
|---|---:|---|---|
| `orla-dock-0.2.7.plasmoid` | 48,817 | `58f56b313e3fa60abe9caa48e57221956829d81fc92e9e5a50e291e0b5e08506` | Exact |
| `orla-dock-0.2.7.zip` | 429,793 | `53cd551c59c966020472ff5243c8c0bbc2da8b1b7eba3bae4c9dd13dcb0cba29` | Exact |
| `SHA256SUMS` | 177 | `5632f29dae32db4ede5a945639f838056a6bcc1961a86c51a7d11816a7c51bd0` | Exact |


## Behavior and persistence boundary

The global typed `showLocalToasts` setting defaults to `false`. In Widgets, the
checkbox is labeled **Mostrar conclusões do Pomodoro dentro do dock (global)**.
It writes that global preference only and leaves `profilesJSON` untouched. With
the setting off, the original dock viewport geometry and Pomodoro notice path
remain in use.

With the option on and valid writable profile state, one local event area is
reserved beside the settings control and clipped app strip. It activates only
when at least 48 pixels fit, and the event slot is capped at 224 pixels. Arrival
does not take focus, scroll the app strip, or resize the dock. The exact
completion event is rendered as bounded plain text, coalesces by its fixed key,
and expires after eight seconds. Reduced motion and colors come from the current
appearance. The full accessible name is exposed; narrow modes summarize or
elide visible text, and the close control remains 24 by 24 pixels.

The Pomodoro remains the sole owner of its state and deadline. Disabling the
feature clears local presentation only. If profile data is invalid or
unsupported, local presentation is disabled and cleared; its raw bytes and last
valid presentation snapshot are preserved, and completion returns once through
the existing legacy dock notice. The Pomodoro identity and running deadline
remain unchanged. The preference applies globally; per-profile event rules are
not implemented.

## Evidence

- Product suite: 14 passed with zero failures, errors or warnings. It covers the
  default-off legacy path, preference scope, exact one-destination completion,
  invalid-profile preservation and fallback, event bounds/coalescing/expiry,
  layout sizing, accessibility properties, close/settings clicks, focus order,
  appearance tokens and settled captures.
- After that suite, a compact-layout correction removed overlap between the
  indicator and close target at the minimum 48-pixel event width. One new
  boundary test checks widths 48, 49, 51 and 55 pixels; the existing real-Tile
  compact-surface test was also rerun. The checks were
  `test_minimum_compact_surface_keeps_glyph_clear_of_full_close_target` and
  `test_real_tile_hover_indicator_tooltip_and_compact_surface_fit_the_clip`.
  Both focused tests passed with zero failures, errors or QML warnings. The full
  14-test suite was not rerun after this correction.
- Focused independent rerun of the product regression and reviewer guard:
  2 passed with zero failures, errors or warnings. It observed
  `profilesWritable=false`, local presentation inactive and cleared, unchanged
  Pomodoro deadline, and preserved raw profile bytes.
- Existing offscreen QML regressions: 9 passed; 3 existing TaskManager-dependent
  checks were skipped because the isolated run has no Wayland/X11 connection.
  No skips were added or relaxed.
- Five targeted profile/appearance regressions passed, covering timer
  identity/deadline and single completion, hidden widgets/dividers, keyboard
  focus, settings close/Escape and settings actions at 420 pixels.
- One bounded synthetic package check passed after two reproducible builds. It
  verified that the expected event surface, event state and typed default-off
  configuration were present byte-for-byte in the ZIP and applet archive. It
  did not install, launch or execute the package in Plasma. It predates the
  compact-surface correction. The same synthetic check was rerun after the
  correction: one test passed in 0.215 seconds, again verifying exact current
  event/config bytes and two reproducible builds. Neither run installed a package.
- The independent first review requested one change: invalid/unsupported profile
  data did not disable and clear local presentation. Round two verified the
  guard and regression, approved the frozen source integration with zero blocking
  findings and zero new comments, and confirmed all 19 source/test/review/capture
  pins. Its approval is limited to this C1 Source integration and partial N1
  result; it does not approve version metadata, documentation, package, release
  or native behavior. Round-three review independently passed the two focused
  tests and an additional 48-pixel pointer/geometry check, with zero warnings or
  findings. All fourteen round-three pins matched before and after review.
- Two capture runs within the same minute produced matching hashes. The reviewer
  found that the 320 and 640 pixel captures include the live clock and differ at
  a later minute; this demonstrates settled-frame repeatability for matching
  content, not a timeless golden image.

Checks used private XDG roots, absent owned D-Bus sockets, offscreen/software Qt
with Fusion, and unchanged `HOME`/`CODEX_HOME`. This establishes the bounds of the
fixture run, not host-seat isolation from passive Qt/KDE plugin initialization.

## Not qualified

The tests did not open a native task menu or use an actual TaskManager delegate;
the product coordinate path used the real add tile and a separate synthetic
product Tile fixture. Native task activation/minimize/menu anchoring and focus
restoration remain untested. No Plasma panel, compositor, autohide, Wayland or
X11 host focus, touch, real scaling, multiple displays, screen reader, lock
screen, Do Not Disturb, KDE notification service, MPRIS/provider, installation,
upgrade or user session was exercised. Automated accessibility properties do
not establish screen-reader support. N1 remains partial; N2 and N3 remain open.

Publication receipt: anonymous asset verification confirmed the hashes and build matches above for tag `v0.2.7`. The published assets correspond to the exact source commit listed above. That check did not install or launch the package; native admission remains false.
