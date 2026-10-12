# Experimental AI provider compatibility — source validation

**Status:** The A0.1 compatibility slice is experimental, integrated Source; this Source change integrates the reviewed operational Ollama text slice described below. Neither is an end-user feature in the published 0.2.9 assets. The [PR #20](https://github.com/caiolombello/orla-desktop/pull/20) source commit `579e181a8dbe9b3cc690410cb1c0e9b0398e00db` was merged at 2026-10-11 05:36:17 UTC as `9d286eb2899c8e1c09b36d545eec4048745415f2`. [CI run 38115242191/job 114398735163](https://github.com/caiolombello/orla-desktop/actions/runs/38115242191/job/114398735163) passed at 05:35:40 UTC. Release 0.2.9 bundles only `scripts/ai.py` and `tests/test_ai.py` in its ZIP; it still excludes the launcher C++/QML, AI panel, and bar. The helper files are not a published AI feature or proof of AI readiness.

## What the A0.1 compatibility slice does

The launcher adds an **IA** panel, initially off. Opening it starts no helper or provider process. The explicit **Verificar clientes instalados** action asks a fixed helper to inspect a fixed list: Codex, Claude Code, OpenCode, Ollama and LM Studio. Version commands are restricted to recognized CLIs; Ollama is presence-only because its version command may contact a live service. Each provider remains `enabled: false`.

A separate explicit consent action tests one narrow Codex compatibility exchange, `initialize` followed by `initialized`, for the recognized Codex version. It is a protocol handshake, not authentication, session reuse, model startup, a turn, text generation, usage reporting, or an API entitlement check. Neither operation takes search text, selected text, or other user context. There is no credentials store, chat, text-selection workflow, or terminal handoff in this slice.

## Historical PR #20 CI scope

The PR workflow passed portable Python/QML checks and produced a Source ZIP artifact. The ZIP contains `scripts/ai.py` and `tests/test_ai.py`; the launcher C++/QML files remain excluded. Its CI run passed the helper suite, 19 tests in 13.065 seconds. This workflow did **not** compile the launcher C++/QML or run the controller CTests. The 0.2.9 release reuses the helper files in its ZIP, but this does not package the launcher panel. This CI result is separate from the local controller/helper and one-shot evidence below.

## Historical A0.1 bounded source evidence

- The controller/UI round-two Source review approved with zero blockers. Its focused CTest suite passed 4/4 in 30.69 seconds; a separate independent targeted run passed 6 cases in 3.492 seconds. These exercise fake helpers, private test buses, lifecycle/cancellation, and capability semantics.
- The helper round-four Source review approved with zero blockers. The synthetic helper suite passed 19 tests in 12.866 seconds; eight independent targeted fixtures passed. These use synthetic ELF data and a Bubblewrap shim, not proof of real namespace enforcement.
- A bounded one-shot run observed Codex CLI `0.162.1`, Claude Code `2.1.287` and OpenCode `2.0.24`; Ollama and LM Studio CLIs were absent from that run's fixed PATH. This says nothing about GUI applications or other environments. The separate Codex operation completed one `initialize`/`initialized` exchange. The receipt recorded zero paid requests. For recognized clients, authentication, inference, real cancellation and usage remain `unknown`; authentication, inference, cancellation behavior and billing were not exercised.
- For this local observation, namespace and network-denial enforcement were configured but **UNOBSERVED**; process-group cleanup observation was **NON_EXHAUSTIVE**. Installed client bytes are user-controlled, vendor provenance is unknown, and path-based metadata checks retain a same-user TOCTOU risk. A recognized CLI version or handshake does not prove account/provider permission or runtime isolation.

The panel therefore demonstrates only a bounded compatibility-reporting path in Source and one local protocol observation. It is not native launcher admission, provider readiness, or evidence that AI works in Orla as an end-user feature. Native Qt/KDE/Wayland behavior, normal launcher session/focus, packaging/install, authentication/session flows, model requests, inference, cancellation semantics, streaming/tools, usage, billing and general network/namespace enforcement remain UNRUN.

## Offline text contract foundation (T1)

The Source checkout also includes `scripts/ai_text.py`, a separate experimental
text-contract foundation. It validates bounded rewrite, summarize and translate
requests and parses a supported text-only subset of Ollama NDJSON and OpenAI
Responses SSE. Unknown event fields, unsupported tools, calls, images and
contradictory lifecycle states are rejected. Published deltas keep contiguous sequence numbers and the
4,096-event limit reserves a terminal slot. Provider error details are sanitized;
reported usage is validated and cost remains unknown.

The framing parser accepts credential bytes supplied by its caller. The module
does not acquire credentials from stores or the environment, authenticate, use
credentials in transport, make network requests or connect to the launcher UI.
Its command-line entry point returns
`unsupported_transport`. It is not functional AI or a release feature. Real
transport, cancellation, authentication, subscriptions, model access and billing
remain separate gates; a provider subscription does not establish API credit.

Independent Source review approved the offline contract after adversarial bounds
and lifecycle checks. Its 23 author tests use only Python's standard library:

```bash
python3 -B -m unittest discover -s tests -p 'test_ai_text.py' -v
```

The foundation was integrated by [PR #28](https://github.com/caiolombello/orla-desktop/pull/28),
Source `bf3e6fc9adf3c4b5e5ffaf2b83a724c14894429c`.
[CI run 38126133261](https://github.com/caiolombello/orla-desktop/actions/runs/38126133261)
passed the 23 text tests and all five launcher CTests. It does not admit
provider/network or native behavior. The generated CI Source ZIP includes this
module and its tests; the published 0.2.9 assets remain unchanged and exclude it.

## Fake text transport lifecycle foundation (T2.1/T2.2)

`scripts/ai_text_transport.py` adds a private lifecycle around the frozen T1
contract. It frames a caller-supplied request and ephemeral credential, checks
cancellation and the absolute budget at each injected boundary, and holds the
terminal event batch until stream EOF and local cleanup. Cleanup failures,
cancellation and transport errors have a fixed precedence. Events contain no
raw headers, bodies, exceptions or credentials.

The T2.1/T2.2 baseline was integrated by [PR #30](https://github.com/caiolombello/orla-desktop/pull/30). Independent Source review approved that slice after cancellation, secret/body
overlap and credential ownership adversaries. Its maintained suites contained
23 T1 tests and 29 T2 tests; all transport, input, signal, timer, clock and sink
boundaries were fakes. [CI run 38132537208](https://github.com/caiolombello/orla-desktop/actions/runs/38132537208) passed these tests, 17 package tests and all five launcher CTests. Best-effort buffer wiping is attempted independently on
failure; it does not promise perfect erasure.

```bash
python3 -B -m unittest discover -s tests -p 'test_ai_text_transport.py' -v
```

At the T2.1/T2.2 baseline, HTTP headers/framing, sockets, DNS, TLS and production
signal adapters were not implemented. The command-line entry point remains
`unsupported_transport`. CI Source ZIPs include the script and tests; published
0.2.9 assets remain unchanged.

## Numeric Ollama adapter foundation (T2.3)

The Source module now contains a private adapter for literal loopback IPv4 and
IPv6 Ollama endpoints. It selects AF_INET or AF_INET6 directly, builds an
explicit HTTP request using public standard-library methods, and checks status,
media type, duplicate headers, transfer framing and declared length before
passing a response to the lifecycle. Response bytes remain capped at 512 KiB.

All verification uses injected connections, sockets and byte streams in memory.
Some fixtures exercise the real public HTTPConnection/HTTPResponse parser on
these fakes, including persistent responses rejected before wrapper transfer,
partial connection setup, premature EOF, body bounds and cleanup faults. Tests
deny real socket creation and DNS resolution. Acquired socket and response
ownership must be closed before a successful provider terminal batch is
released. Failed cleanup instead emits the cleanup-failure terminal and retains
unconfirmed resource ownership. The maintained suites contain 23 T1 tests and
46 T2 tests. This is Source verification, with no provider request or runtime
isolation claim.

The adapter checks the 64-header and 32-KiB metadata limits after the standard
library has parsed headers. These checks do not provide an aggregate preparse
allocation bound; the upstream parser has its own line and count limits.

At this historical T2.3 point, the adapter was not wired into the command-line
entry point or a default transport factory. Signal/timer adapters, operational
CLI, TLS/OpenAI transport, launcher text UI and real cancellation were separate
work. Authentication,
credentials stores, subscriptions, inference, usage and billing were not
exercised. A local model endpoint or a provider subscription does not establish
account permission or API credit. The module is a Source foundation; published
0.2.9 assets remain unchanged.

## Private OpenAI adapter foundation (PR #34)

[PR #34](https://github.com/caiolombello/orla-desktop/pull/34) historically
integrated a bounded private HTTPS adapter for OpenAI into the transport module.
It remains unwired: there is no operational entrypoint, credential acquisition,
provider selection or launcher UI for it. The operational slice below does
not import or select that connector and must not be described as generic cloud
API support.

## Operational Ollama text integrated in this Source change

This Source change integrates `scripts/ai_text_ollama.py`, `AiTextController`
and the explicit text UI. Its component reviews and fresh composition checks
passed. Remote main integration, release and installation for this slice remain
unverified. Hosted checks passed on `1f59e0c`; the later `2c8b750` run has an
unexplained UI process SIGSEGV after passing assertions, detailed below.
This is Source adoption, not runtime admission.

The UI accepts only an explicitly chosen numeric loopback host (`127.0.0.1` or
`::1`), port, model, task, text and translation language when required. It shows
the normalized destination, model/task/data and unknown cost before session
consent. Editing host, port or model revokes consent. Opening, editing and
consenting do not execute anything; only **Gerar** starts a request. During the
request inputs are locked, **Cancelar** stays available, deltas stream to a
read-only review area, partial output is retained and copy is manual. Closing
the panel or switching from AI to Steam cancels both AI controllers before
leaving that panel. UI-requested closing and the visible+active shortcut route
wait for AI compatibility, AI text and Steam owners before finishing once.
A newly admitted attempt clears previous output/usage before preflight; ignored
busy/closing attempts preserve the live result. All four QML result execution
routes now share a live guard for the three busy owners and pending dismissal:
Return/Enter, result delegates, the primary footer and action footer. Delayed
callbacks carrying a mouse-pressed ticket also pass through that guard. The
controls display a localized waiting state and re-enable after actual cleanup;
search typing and navigation stay available. This covers the QML entry points,
not arbitrary external direct C++ calls. Cleanup failure emits property NOTIFY
on the first changed state, avoids duplicate identical poll notifications and
keeps the busy/retry/close barrier until cleanup succeeds.

The controller invokes exactly `python -I -B ai_text_ollama.py run-ollama` by
absolute paths in a private cwd with an empty child environment. This is
deliberately distinct from the isolated test runner preserving the parent
`HOME` and `CODEX_HOME` literals. The shim supplies fd input/output and POSIX
signal/timer boundaries to the protected T2 lifecycle and selects only the
numeric Ollama connector. Direct T1/T2 execution remains fail-closed as
`unsupported_transport`.

The author evidence records six operational shim tests, a six-test full CTest
union, twelve corrected controller cases and ten UI cases. The private integrated
fixture covers controller → helper → ephemeral `QTcpServer`, fragmented
streaming, EOF retention, cancellation/disconnect, preserved partial output and
the three-owner close barrier. The fresh shim review and fresh UI correction
review approved their bounded Source. The controller R3 fresh review also
approved the confirmed-absence cleanup correction. A fresh normal composition
build, all six isolated CTests and 90 selected Python tests passed (6 shim,
23 T1 and 61 T2). UI had 10 passing cases and the controller had 12. These
bounded results describe the initial composition and do not establish provider,
native or installation readiness.

The [PR #36](https://github.com/caiolombello/orla-desktop/pull/36) follow-up
corrects four reviewed behaviors: outer timeout remains `operation_timeout`
after cleanup; unknown usage is labelled unknown; leaving AI through Steam
cancels both AI owners; and usage is published only after the full completion
event, including cost, validates. A fresh combined normal build and all six
isolated CTests passed with 19 controller and 17 UI entries. An extra owned Qt
case first showed reported zero usage, then rejected malformed cost on the same
controller and showed empty usage and the actual unknown QML label. These are
synthetic helpers and offscreen interactions, not a real model or native focus.

Two subsequent independent Source reviews approved clearing stale results before
preflight and routing the active-window shortcut through QML requestDismiss(false).
The final exact composition passed a fresh 40-step all-target build and all six
isolated CTests once (66.197 s): 24 controller entries, 18 UI entries and six
actual process-exit-zero/owned-bus cleanup receipts. Regression rows cover prior
completed results rejected for invalid model/language or missing helper, ignored
busy/closing requests, and three real owned resistant helpers before exactly one
hide. An independent baseline RED reproduced early hiding; a plain owned active
QQuickWindow without the QML method stayed visible on repeated callbacks. This
does not exercise global key registration or compositor focus.

The first portable job on `6364572` failed on Python 3.12.3 because test
fixtures handed a manually closed stdin to `communicate()`. Commit `1f59e0c`
sets that reference to `None` after close, preserving the EOF assertion and
existing test bodies. All six shim tests passed in Python 3.12.3 and 3.14.7,
including independent runs in an owned harness that preserves actual parent
HOME/CODEX_HOME literals. The exact hosted command was not replayed locally.
Both hosted checks subsequently passed on `1f59e0c`. On `2c8b750`, the portable
job passed. In the [launcher job](https://github.com/caiolombello/orla-desktop/actions/runs/38159702441/job/114529858525),
all 17 UI entries and the other five CTests passed, but the UI process returned
`-11` after Finished testing. Cause UNKNOWN; no hosted stack was supplied.
Bounded local normal/GDB/allocator runs exited zero and do not establish a fix.

The workflow now retains the original failing CTest step and adds a two-minute
failure-only diagnostic selected by the exact launcher-ui LastTestsFailed entry.
It uses an exact Fedora GDB pin, the unchanged isolated runner and private bus,
a bounded backtrace and child-result propagation. Owned checks verified exit0,
exit42, a controlled synthetic SIGSEGV with stack, and the exact UI diagnostic
command exiting zero. The independent review approved diagnosis only. Hosted
checks subsequently passed on `57c2aa0`: both jobs succeeded and the launcher
job reports all six CTests passing. The GDB diagnostic was skipped because the
original CTest step passed; passing Qt child stdout is not included in those
hosted summaries. A bounded read-only lifetime audit found no supported
introduced unsafe-lifetime path. Neither this audit nor the green run explains
the historical SIGSEGV; cause UNKNOWN and original failure evidence are retained.
The two additional corrections notify cleanup failure on state transitions and
guard result execution while any owner is busy or dismissal is pending. The
final exact composition passed a fresh 40-step ALL build and all six isolated
CTests once (75.026 s), with 25 controller and 27 UI entries. All six actual child
exit-zero and private-bus cleanup receipts were retained; UI took 24.75 s under
the unchanged 30-second cap. Controller checks cover first failure notification,
identical-poll deduplication, retry and retained close barriers. Nine UI rows
cover keyboard, delegate/footer/action, earlier pressed tickets, Steam and
pending-close paths using real owned resistant helpers and one final hide.

During private review, the new Steam row failed on a cached visual delegate;
one targeted GDB run confirmed isEnabled at that new assertion after the model
refresh. The corrected test uses guarded pointers and reacquires the current
identity/generation while preserving all prior checks and the actual pressed
ticket. Its focused row and full normal UI suite passed. Final baseline-QML REDs
with exact final tests reproduce the premature URI opening and late action copy
as ordinary exit-one failures after cleanup. The copy oracle reads only Qt's
owned in-process offscreen clipboard after checking the platform; no native
clipboard is accessed. This new test fault is separate from the historical2c
suite-complete SIGSEGV. Independent final UI review approved the corrected Source and an additional
valid-pressed-ticket/three-owner/pending-close challenge; no findings remain.
Hosted checks for the next revision and remote main integration remain pending.

No real Ollama, model, provider identity, semantic output, authentication,
external service, native clipboard, accessibility runtime, native Wayland session,
package, install, release or deployment was used. There is no automatic probe,
server start, model download, default context, clipboard read, history, context
file, auth or paid API. Numeric loopback constrains the socket destination; it
does not prove that Ollama owns the listener, that processing is offline or
private, or that the listening process will not forward data to another network.
The full Source ZIP does not install the launcher, and helper paths are currently
compile-time absolute rather than finished relocatable packaging. This change
does not upgrade the existing Source 32 launcher installation, which still has
no new AI text UI.

## Historical reviewed source pins

The separately reviewed controller/UI and helper revisions used these source hashes:

```text
3d43bd01dd51d4fea5f868870d0d50e1716b3900535e9182e18eaea79fb4098e  launcher/AiProviderController.h
9e81da1016698a879e8e2d1520386c9058857abd8449c481e0e555c0e9eb70bc  launcher/AiProviderController.cpp
c53e53f8c43abff804c78af516c0f01f58358df3ba23944f2698b00521ea1c6a  launcher/AiSettings.qml
76025f6686074c11e6149605cda66c59957a834d541dda91bd42afdd18d1e220  launcher/Launcher.qml
6089f32d3562d64298e18277403a15892e3b647a66c9c3f2e24e1044260db58e  launcher/main.cpp
a42be491343eeb05ac7748913a9c7275c6fea22280a1559cfbc99864e68e8306  launcher/CMakeLists.txt
15d867871b50be81df72f763e4fced8daa60d4d898d675b3e789a12408aef56e  scripts/ai.py
6b7662d364d7f0131e09cbbbf846dfd8975a7e48ffa39b245ff562b5e724221c  tests/test_ai.py
```

See the [launcher build/source guide](../../launcher/README.md) and the [long-term integration proposal](../AI_INTEGRATIONS.md). The reviewed component-level reports and local one-shot receipt remain preserved as private evidence; they are not public API guarantees.

### Final close notification and pending quit follow-up

Both hosted jobs passed on `28c5ef4`; its launcher job reports six CTests passing
in 74.04 s, including UI in 24.27 s. Successful child output does not directly
print the Qt entry counts. The failure-only GDB diagnostic was skipped; the
historical2c crash cause remains UNKNOWN.

The next two corrections publish the final property notification before
`closeReady`, retaining the close barrier against reentrant generation during
that notification, and latch quit intent until owner cleanup completes.
Repeated active shortcut dismissal cannot downgrade a pending quit. An
immediately ready dismissal uses the same final commit and consumes its flags
before dispatch, preventing a second close and an inherited quit in a later
non-quit cycle.

The exact four-code-path composition passed a fresh 40-step ALL build and all
six isolated CTests once in 75.925 s. Controller and UI each reported 27 entries,
zero failures/skips and actual child exit zero; UI took 24.60 s under its
unchanged 30-second cap. Six private-bus cleanup receipts were retained. The
separate behavior fixture retains its expected skip, covered by the owned-app
test. The other 178 Source paths and all 182 modes stayed unchanged.

Independent controller Source review passed its normal 27 entries and actual
unchanged AiSettings forced/timeout rows. Its supplemental cooperative row
passed final bindings/order/cleanup assertions, then failed an additional
confirmed-only cancellation oracle: actual cancellation was unconfirmed and
the exact cause remains UNKNOWN. The earlier supplemental empty-Python
harness failure and both failed logs are retained, without a passing claim
or a normal-suite rerun.

Independent quit Source review passed a fresh normal ALL build and all 27 UI
entries once (24.88 s). A separate combined challenge used the frozen P1
controller and three actual helpers; final changed observed all owners idle,
pending quit/dismiss still true, all captured helpers/groups/runtimes removed
and the distinct final text closeReady not yet emitted. The actual active
WindowSession shortcut committed immediately once. Later closeReady caused no
second close/hide/engine quit, and a fresh nonquit cycle inherited no quit.
The first supplemental attempt failed its last-owner ordering precondition
because it assumed Steam grace was 2 s instead of the actual 3 s. Causal checks
were UNRUN there. Its source/binary/log remain preserved; the corrected fresh
supplemental build changed only an exposed fixture grace value, not production
timers/caps or the normal candidate, and passed its single challenge.

### Usage publication after helper EOF and process validation

The next controller correction stages validated terminal usage privately.
It commits the metadata only after complete framing, normal exit zero and
confirmed owned-group/runtime cleanup. Rejected suffixes, extra events,
nonzero exit, cancellation and timeout discard pending usage while retaining
reviewable partial text. Busy/closing ignored calls preserve the live request;
the final property notification still precedes closeReady with reentrant
generation blocked.

Seven actual helper regression rows passed, including clean EOF, rejected
framing/exit, cancellation, deadline and temporary runtime-cleanup rejection,
each followed by a valid retry. The exact final tests with baseline controller
code failed seven ordinary causal assertions after captured PID/group/runtime
cleanup. Only the two authorized old early-publication expectations changed;
the remaining original tests stayed byte-exact.

Independent Source review passed a fresh ALL40 build and controller 34 once.
Its additional five-entry challenge closed helper stdout while the process and
group remained alive: usage stayed private until valid process completion,
reported and unknown results committed correctly, and closing discarded the
pending usage while preserving changed-before-closeReady and the close barrier.
The challenge passed its first execution with actual original/retry cleanup.

The exact three-code-path composition passed a fresh ALL40 build and all six
isolated CTests once in 78.502 s. Controller reported 34 entries and UI 27,
with no failures or skips in either; UI took 24.508 s under the unchanged
30-second cap. Six actual child exit-zero/bus cleanup receipts were retained.
The other 179 candidate Source paths and all 182 modes were preserved. The
behavior fixture retained its expected skip, separately covered by owned-app.

This follow-up remains Source validation. New-head CI and main integration are
pending; real KDE/Wayland, provider/model, native clipboard/accessibility,
installation, relocatable packaging, release and the full roadmap remain open.


### Failure precedence during cancellation and rejected stdout

The fifth follow-up preserves the first observed failure when cancellation or
close begins after it, including protocol/provider failures, actual abnormal
exit, FailedToStart and cleanup rejection. The first cancellation captures
that private failure once; an earlier ordinary cancellation cannot be promoted
by later cancel/close calls. Timeout precedence and pre-start cancellation
remain intact. No default exit status is inferred as process-exit evidence.
After the first protocol error, stdout is drained without parsing and residual
framing is cleared; only previously accepted partial text survives. Private
usage and the changed-before-closeReady barrier remain unchanged.

Seventeen new actual-helper rows cover twelve late-failure cancel/close cases,
two pre-start negative controls and three stdout delivery paths. Each checks
owned process/group/runtime cleanup before the causal outcome and valid retry.
Baseline controller/header with the final tests reported fifteen causal
failures and two passing controls (plus init/cleanup), exit15, after cleanup.
Thirty-three old test bodies remain byte-exact; one shared late-close cleanup
body now requires the demonstrated original failure instead of masked cancel.
The final normal controller suite passed 51 entries once, with no failures or
skips and the unchanged 40-second cap.

Independent Source review passed a fresh ALL40 and controller51 once. An
additional real-helper/QtObject challenge proves ordinary cancellation before
failure remains ordinary across repeated cancel/close and real runtime mode
rejection; recovered cleanup, final consumer bindings, blocked reentrant
generation and valid retry were observed. Its initial Qt setup failed before
helpers (2FAIL, exit2); the original component status was unrecorded and stays
UNKNOWN. A separately approved owned harness correction used a local file URL
and logged/bounded component readiness; its first execution passed four
entries, exit0. No production repair or normal-suite replay occurred. The
serialized QML event array is null and is not chronological evidence; asserted
consumer flags and unchanged Source ordering support only the stated bounds.
Inspection guard failures are retained separately, not test failures.

The exact three-path composition passed a fresh ALL40 and all six isolated
CTests once in 81.147 seconds: controller51 and UI27, with UI24.663 seconds
under the unchanged 30-second cap. Six child exit-zero/private-bus cleanup
receipts were retained; other179 Source paths and all182 modes were preserved.
The behavior fixture's expected skip remains separately covered by owned-app.
The prior 8d137cf hosted jobs both passed (six CTests78.72s); its local cold
build passed six in79.47s but was not installed before these new reviews.
Historical 2c8b750 SIGSEGV and the earlier cooperative supplemental challenge
retain UNKNOWN causes. New-head CI/main integration and real native/provider,
clipboard/accessibility, install, distribution/release and full-roadmap
admission remain open at this Source publication checkpoint.

### Subsequent hosted failure and local canary — 5aaf518

Hosted run 38175193804/job114576003847 failed: launcher-behavior printed
7 PASS/0 FAIL/1 expected SKIP and cleanup/Finished, then the isolated runner
reported returncode -11. The five other CTests passed; the portable job passed.
Cause is UNKNOWN and distinct from the historical 2c8b750 UI crash. One local
GDB execution against the exact permanent behavior ELF exited 0 without
reproduction or a causal stack. Two unnamed LWPs exiting after Totals are not
proof of KRunner thread identity. Twenty-seven direct closure pins matched
before/after; 116 mapped-library pins were collected only after the run.

The workflow extension selects one fixed failed target from exact allowlisted
log entries, prioritizing behavior before UI. Behavior retains no private-PATH
flag; UI retains it. Seven author selector fixtures, ten independent fixtures
and two independent bash syntax checks passed. The original failure condition,
CTest result, environment and step/job/runner caps remain unchanged. This is
diagnostic coverage, not a crash fix; new-head hosted CI and merge are pending.

A separate reversible local canary was authorized and installed from Source
5aaf518. A fresh permanent ALL40 build and six isolated CTests passed once in
80.85s (UI27/24.408s Qt; controller51/11.248s Qt). ELF has no RPATH/RUNPATH;
five helpers use permanent paths and installed library resolution was checked.
Only the launcher's wrapper binary-path literal changed; unit/desktop/autostart
targets remained exact and the backup was retained. Initial preparation review
found wrapper-to-ELF startup/rollback races; corrected bounded observation was
reviewed before installation. The nominal five-second transition deadline has
individual twenty-second service-query limits and is not a strict aggregate cap.

Actual KDE checks observed shortcut opening, Escape restoring T3 Code focus,
AI panel opening, Tab scrolling to the focused task field, an in-window task
popup, Escape closing it while preserving the panel, and calculator 2+2 showing
4 without execution/copy. Ctrl+Q left the named service inactive with exit0;
restart reached the exact ELF, then shortcut/Down/Escape worked again. Final
service was active/running/enabled with success/exit0. Temporary virtual input
devices were closed and absent. A restart helper import failed before commands;
adding its own directory to sys.path corrected only that preparation lookup.

This covers basic flows on this machine, not full native admission. Actual AI
discovery/generation, provider identity/semantics, native clipboard/accessibility,
multi-monitor/DPI, real calendar accounts, relocatable distribution/update and
release remain open. Local screenshots stay private. The full roadmap is active.

### Further review — cleanup recovery, idle starts and publication signals

Three accepted findings add narrowly scoped recovery/start guards and preserve
lifecycle exceptions during stdout publication. Real-helper controller rows
reproduce malformed output/nonzero exit followed by transient runtime-removal
refusal without explicit cancellation; after recovery the original error and
message are restored before notification. UI rows reproduce late work on an
initially idle owner during another owner's close barrier. Direct/queued
callbacks now reject starts while preserving busy Cancel, Back and quit intent.
The guard covers pending drain/commit; the existing asynchronous native hide
interval is not qualified by these offscreen tests.

Transport tests cover real owned SIGTERM/SIGALRM after a complete fixture delta
write, inside the actual shim sink. The two lifecycle exceptions retain their
classification; genuine sink exceptions remain fail-closed. This does not
guarantee atomic partial writes or a terminal if started publication itself is
interrupted. Return-based event counters, framing and automatic retry remain
unchanged. Response/connector cleanup, timer cancellation and credential wiping
precede the terminal publication attempt; original signal handlers and the signal
mask are restored afterward in the finalizer.

All three Source reviews approved their bounded scopes. The UI author's focused
run reached five PASS assertions and then child SIGSEGV/runner245; normal full
UI was not run there. One independent GDB capture on the exact ELF exited0
without reproducing; cause UNKNOWN, no crash fix claimed. Historical UI/behavior
crashes and the cooperative supplemental challenge retain UNKNOWN status.

The combined candidate passed a fresh ALL40 build. Root's first CTest attempt
failed in all six wrappers before Qt or private-bus startup because its owned
TMPDIR had not been created; retained as setup failure, not application failure.
Only creating that directory0700 justified the corrected invocation, with the
same compiled artifacts, runner, asserts and limits. All six CTests then passed
in 83.64s: UI30/26.404s Qt (26.51s CTest, cap30), controller53/11.684s Qt;
behavior retained its one expected skip. Python AI text suites passed 93 tests
in 1.167s. Each runner reported process0 and owned-daemon cleanup; owned TMP was
empty afterward. These are bounded local Source checks, not a cause explanation
for the earlier SIGSEGV, hosted CI, native/provider/release admission.

CI at preceding Source5f898ce passed both jobs (run38177233983, six CTests80.42s),
with GDB skipped. CI and merge for this follow-up remain pending. The permanent
launcher canary remains `5aaf518`; no new installed payload, real provider, personal
calendar, native clipboard or full roadmap acceptance is claimed.

### Failed-event validation and compact launcher — subsequent composition

A parsed `failed` provider code remains staged until all stdout has been drained,
framing is valid, and the actual process exits normally with code0. Actual bad
exit cause staging still precedes stdout drain. The first explicit cancellation
snapshots an already-known cause or a syntactically accepted failed event when
protocol-valid; later cancellation does not recapture it. Without that earlier
explicit cancellation, a failed event followed by another event, unterminated
bytes, or actual exit7 reports `invalid_helper_response` after cleanup. Partial
accepted text remains reviewable; invalid usage remains unpublished.

Four new real-helper rows hold EOF after the failed line, then exercise those
three invalid outcomes and a clean failed control through synthetic runtime
removal refusal and real recovery. They verify captured PID/group/runtime
absence before final cause, notification, partial text and fresh-retry oracles.
RED produced three causal failures and a passing valid control; GREEN focused6
and the normal controller57 passed. All53 prior test entries and the header
remain byte-exact. Independent Source review approved this bounded correction.

The separate compact UI changes the default to660×420 while preserving the
440×380 minimum. IA/Steam header targets and AI Back remain at least40×40;
keyboard actions and pending-close guards are preserved. AI content uses the
ScrollView available width; provider names and valid long versions wrap.
Two header geometry/keyboard rows and the existing narrow-provider scenario
cover440/660 widths and long-version containment. The compact author's one
normal UI run passed32 in27.41s CTest under cap30. A prior CTest-tool loader127
occurred before Qt; using prefix libraries only for the CTest tool corrected
that setup, while the registered Qt child still strips LD_LIBRARY_PATH.
Mock renders are local layout evidence, not native KDE validation.

Root then built the exact five-path code/test combination from baseabee586 in
40 fresh build steps and ran all six registered CTests once. All passed in
84.38s CTest (84.425s driver): behavior7 with one expected skip, owned-app3,
UI32/26.588s Qt (26.72s CTest, cap30), provider22, Steam12, and controller57/
12.621s Qt (12.76s CTest, cap40). Six child-exit0 and owned-private-bus-stopped
receipts were retained; owned TMP0700 was empty afterward. Python scripts/tests
are byte-exact to the preceding93PASS record; Python was not rerun here.
No timer, cap, runner, CMake, helper, API or ownership policy changed.

CI/merge for this combined revision and compact native-layout checks remain
pending. The permanent installed launcher is still5aaf518. Historical UI,
behavior and supplemental challenge SIGSEGV causes remain UNKNOWN; these
passing checks do not establish a crash fix, actual model generation, native
clipboard/accessibility, multiple-display coverage, release or full admission.


### Started publication and actionable local failure messages

Typed cancellation or timeout while publishing `started` now uses the existing
started finalizer once publication has begun. The complete-write fixture covers
SIGTERM/SIGALRM after all started bytes but before the sink returns: a canonical
cancelled/timeout terminal follows, without starting the connector. Returned
publication counters remain truthful. Partial/no-write ambiguity remains; this
is no delivery, atomic-write, acknowledgment or automatic-retry guarantee.

All accepted stable failure codes now have fixed, translated recovery messages.
Missing models, connection failures, rate limits and unavailable providers are
shown accurately after valid EOF/normal exit and cleanup; malformed/nonzero
responses retain the validation error. No provider body or credential is shown.
Independent reviews approved both changes. Their causal RED records and two
controller-author provenance caveats remain preserved.

The exact five-file composition passed a fresh 40-step build, all six registered
CTests once (90.697s driver), and 116 Python tests (14.636s unittest;14.801s driver).
Controller 83 and UI 32 passed within the unchanged 40/30-second caps; behavior had
one expected skip and the separate owned-app test passed. Observed owned
processes, groups and runtime paths were absent afterward; private TMP was empty.
These are bounded Source/local checks. Hosted CI for this follow-up, compact
native tests, real providers, release and full-roadmap admission remain open.
The installed launcher remains `5aaf518`; historical SIGSEGV causes remain UNKNOWN.


### Pre-write signal window

A later causal real SIGTERM/SIGALRM fixture reproduced a terminal without the
initial started record. Lifecycle handlers are now deferred through the bounded
initial publication and its returned ACK/ledger commit. Queued signals then use
the existing finalizer; counters reflect both successfully returned frames.
Original parser/sink errors keep precedence over a signal delivered on restore.
Mask acquisition/restoration failures retain cleanup and original-mask recovery.

Independent Source review approved the three-file fix. The complete AI suite
passed 118 tests once (14.343s unittest), including actual pre-write, post-write
and delta signal boundaries with owned process/group/runtime cleanup. Three
existing fault-injection ordinals changed to account for the added mask; other
113 prior test bodies remain identical. SIGALRM is deferred inside this initial
write: blocked stdout still requires the controller's outer forced cleanup.
This does not promise a generic blocking-I/O timeout or atomic line delivery.
C++ code is unchanged; the preceding six-suite result remains historical.
Hosted CI and native provider qualification for this follow-up remain open.


### Pending finalizer signals, NUL preflight and test-owned runner lifetimes

Queued SIGTERM/SIGALRM are delivered while nonraising late lifecycle handlers
remain installed. A selected completed or operational-failure outcome is retained,
including both signals queued together. Original handlers/mask are restored;
genuine restoration failures retain the existing finalization-failed classification.
The actual child RED/GREEN evidence and independent Source reviews cover single
and mixed signals, original failure, masks, retry and cleanup. Readiness JSON is
published by atomic rename, with a deterministic partial-write regression.

Text containing U+0000 is rejected as invalid_request before creating runtime or
helper. The regression verifies the real helper parser mismatch, clearing prior
output/usage, immediate idle rejection, no new process and a valid retry.

The installed Fedora calculator plugin separately reproduced a shared-calculator
lifetime fault with two simultaneous KRunner managers. Test-only controller
owners now load the same closed runner whitelist eagerly, retain actual runner
identities and wait for their destruction before allowing another fixture. This
changes fixture initialization timing; production construction is unchanged. The
500ms predicate deadline cannot bound synchronous destruction/Qt handlers, so the
existing outer CTest caps remain unchanged. Old test bodies and queries remain
identical after the ownership declaration substitutions. The new guard proves
serialized fixture ownership, not support for simultaneous production managers.

Root's exact nine-file composition passed a fresh 40-step build (49.312s), all
six registered CTests once (90.288s driver), and 122 Python tests once (15.019s
driver). UI33 and controller84 finished normally within their 30/40s caps. The
behavior suite retained its expected owned-app skip; the separate owned-app
CTest passed. Source183 bytes/modes and 174 protected base paths stayed exact;
private TMP was empty and all six owned bus cleanup receipts were present.

The original hosted post-totals SIGSEGV remains CAUSE UNKNOWN; the independently
reproduced calculator fault does not prove its origin. These checks do not
qualify hosted CI, a new permanent launcher payload, real provider operations,
native compact UI, release or the full roadmap. The installed launcher remains
5aaf518. Masked started writes still need the outer controller cleanup if stdout
blocks; no generic I/O timeout or atomic line-delivery guarantee is added.
