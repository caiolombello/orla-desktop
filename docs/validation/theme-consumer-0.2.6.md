# Experimental theme consumer validation — 0.2.6 alpha

This record covers the first applet consumer of the `0.1-experimental` JSON
theme format. It records source and bounded fixture validation for the 0.2.6 alpha
package. It does not qualify a stable theme API or native Plasma behavior.

## Behavior reviewed

Appearance contains a collapsible **Experimental JSON theme** section. The user
pastes plain JSON and explicitly selects **Use in preview**. The consumer checks
the full external envelope, canonicalizes the ten tokens, and places them in the
existing temporary appearance draft while preserving its current valid base
preset. The existing Apply/Cancel/Escape/Undo path remains the persistence and
recovery path. Apply writes only the current profile's normal appearance; the
source document and its declared name, author, version and license are not
persisted.

Profile-scoped fixture checks confirmed that applying the preview does not
change other profiles or the flat settings path. Widget state, ordering and the
shared Pomodoro timer remain on their existing independent paths.

Pending non-empty text and parse errors block Apply and profile create/switch.
An invalid attempt preserves the last good preview. Clear JSON clears the
pending input/error and keeps that preview. Metadata is displayed as plain text
with an explicit notice that identity and rights are unverified. The parser
rejects unknown fields, executable/resource fields, duplicate keys, malformed
JSON, excessive depth and oversized input. The input is text already decoded by
Qt, so the size bound does not establish the original file encoding and does not
strictly bound transient native clipboard memory.

## Evidence

- The independent review approved the eight frozen implementation/test files
  with zero blocking findings. It checked the source hashes, four protected
  reference hashes, and repeated the freeze check after testing.
- 879 adversarial JavaScript/Python parser cases had zero acceptance or
  canonicalization mismatch. The corpus covered duplicate escaped keys,
  prototype-like keys, Unicode/Latin boundaries, syntax, BOM, depth, size,
  multibyte text, underflow, subnormal values and deterministic long fractions.
- Five parser checks passed; 33 focused parser/appearance/profile checks passed
  in the local offscreen environment with KDE modules and Qt/PySide6 6.11.2. Sixteen profile-guard checks
  passed, excluding the known original TaskManager settle failure. Four focused
  KDE-style checks and twelve separate CLI theme-format checks passed.
- Ten focused fixture tests passed in the independent review, including the new
  Appearance and profile-theme cases, existing Apply/Cancel/defaults/Undo
  controls, and profile Undo after a widget commit.
- The complete fixture run was **not green**: 63 total, 59 passed, one existing
  encoded TaskManager settle test failed, and three native-only tests were
  skipped. The same TaskManager failure reproduced on the unchanged baseline;
  it was not repaired or hidden for this change.
- The first separate Qt 6.12 selection included two older harness tests that
  require KDE imports absent from PySide6-Essentials: 18 passed and two failed.
  The corrected portable selection (five parser tests and five new plain
  Appearance consumer tests) passed all ten checks in 0.829 seconds with no
  warnings. The failed selection is retained; implementation bytes did not
  change. CI uses these selected checks in separate processes. A remote CI
  result is not established by this local run.

## Limits

Native `Popup.Window` behavior, Wayland focus/grabs, keyboard behavior in a real
Plasma panel, screen-reader output, contrast against imported colors, scaling,
multi-monitor layout, KConfig persistence/restart and human clipboard interaction
remain unqualified. The tests used synthetic fixtures and do not prove those
properties. Theme authorship/license fields are declarations, not identity or
rights verification. The `0.1-experimental` format can change; no file chooser,
download, URL loader, package installer, metadata store, gallery, catalog, SDK or
theme marketplace ships in this increment.

The parser bounds its work at 65,536 UTF-8-equivalent bytes and four nested
object/array levels. A very large clipboard value may already have entered the
Qt text control before that parser check. The parser and CLI reject large integer
values, but may report different error codes for runtime-specific numeric
representation limits. Do not infer general error-code parity when one document
contains multiple independent failures.
