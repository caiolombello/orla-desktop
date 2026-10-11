# Contexts first-slice validation — 0.2.8 alpha prerelease

The Contexts integration has independent Source approval with no blocking or actionable Source findings. The [0.2.8 alpha prerelease](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.8) is published (GitHub marks it prerelease, `latest=false`). It was built from source commit `9e42decd42fc4a9a705dd48e6087b17aaca51d29`; PR 18 merged as `c87930bc9881523a390ca492af1e0af6dfc328ca`. CI run [38113776729](https://github.com/caiolombello/orla-desktop/actions/runs/38113776729), job 114394497503, succeeded at 05:08:09 UTC; merge time was 05:08:31 UTC. A root-owned anonymous download verification at 05:09:44 UTC returned HTTP 200 for all three public assets and confirmed exact build matches. Installation is UNRUN and native admission is false.

| Public asset | Bytes | SHA-256 | Build match |
|---|---:|---|---|
| `orla-dock-0.2.8.plasmoid` | 57,092 | `205c74df60433b0ee219a434a9f3482eca65bfa342187a95648fe6d4a3a01bed` | Exact |
| `orla-dock-0.2.8.zip` | 462,757 | `9218e4ee44e032e3ae1d6467f91046ea4c7bda1f7711670e8fe3794e99304a85` | Exact |
| `SHA256SUMS` | 177 | `c1171addd1a379432561a390a29eef96de915662b21caf5309ca11e21b67a96e` | Exact |

Two candidate builds and one build from the exact source commit were identical: 139 Source files, 113 ZIP entries and 35 applet entries. This publication/build evidence is separate from native KDE admission.

## Bounded evidence

- The integration's focused local QML/Fusion union passed 12 tests, including separate empty-default storage, explicit bind/unbind, selector navigation without writes, stale-intent rejection, preservation of dirty appearance and Pomodoro state, invalid/future raw-byte preservation, lazy Loader suppression, independent domain availability, stale-ID retention and keyboard/scroll checks.
- An independent adversarial run passed 2 focused cases: a stale context target is rejected without a write until a fresh intent is captured, and removal of a pending managed profile invalidates the selector without changing context bindings.
- A separate local portable run of the pure Contexts core with Qt 6.12.0 passed all 11 tests in 0.201 seconds (`.runtime/contexts-publication/core-portable.log`). This is not a CI result.
- The pure Contexts core's round-three independent review approved with zero blocking and zero non-blocking findings. The earlier core review findings were addressed by single-read snapshots, semantic no-ops that avoid rewrites, and fixture isolation of both session and system bus paths before Qt import.
- API references were checked against Plasma Activities and Plasma Workspace 6.7.5 source: [ActivityModel](https://raw.githubusercontent.com/KDE/plasma-activities/v6.7.5/src/imports/activitymodel.h) and [VirtualDesktopInfo](https://raw.githubusercontent.com/KDE/plasma-workspace/v6.7.5/libtaskmanager/virtualdesktopinfo.h). The adapter observes `ActivityModel` roles `id`, `name`, `current` and `VirtualDesktopInfo` properties/signals; it does not call context activation APIs.

These checks used isolated synthetic/offscreen QML fixtures. They do not establish native plugin compilation/construction or model propagation. This host lacks `qmllint` and `qmlcachegen`; native compilation was not performed. The portable CI workflow includes the pure-core `test_contexts.py` suite. CI run 38113776729 passed; that result does not qualify native plugin construction or KDE behavior.

## Behavior and persistence boundary

A new empty-default `contextsJSON` preference stores Activity and desktop bindings separately from profile data. Selector navigation stages an intent; only the explicit bind/unbind action writes. The action rejects stale context/profile/binding revisions, and a missing/invalid managed profile cannot be bound. Invalid or future association JSON keeps its exact original text and last valid in-memory view while disabling association controls. Stale IDs remain preserved rather than being silently cleaned up. The UI reports their count only; it has no stale-association list or per-stale-item removal action. The Remove button applies to the current context only.

The native discovery Loader is active only when the Settings popup is visible, the Contextos tab is selected, and no test override is injected. The data source only observes KDE models. Separate status handling lets one domain be unavailable while the other is usable. No output/monitor identity is synthesized when the adapter has no reliable value.

The slice does not select a profile from an association or switch Activities/desktops. The adapter makes no explicit provider/service activation or mutation call; whether native model construction activates or waits on KDE services, and service readiness, remain UNRUN. The slice also does not alter a dirty appearance draft or create another timer owner. Association only records an explicit relation to an existing managed profile.

## Not qualified

Native `ActivityModel`/`VirtualDesktopInfo` construction and service readiness, session-bus/model behavior, actual Activity/desktop switching, monitor/output mapping, KDE-style rendering, installed plasmoid/KConfig persistence, restart, panel focus, accessibility assistive technology, user configuration, automatic profile switching, full native/session regression, P2 completion and W1 selection/switching remain UNRUN or open. Neither the 12+2 integration checks nor the separate 11-test core run qualify these paths.
