# Experimental AI provider compatibility — source validation

**Status:** Experimental, integrated Source; not an end-user feature in the published 0.2.9 assets. The [PR #20](https://github.com/caiolombello/orla-desktop/pull/20) source commit `579e181a8dbe9b3cc690410cb1c0e9b0398e00db` was merged at 2026-10-11 05:36:17 UTC as `9d286eb2899c8e1c09b36d545eec4048745415f2`. [CI run 38115242191/job 114398735163](https://github.com/caiolombello/orla-desktop/actions/runs/38115242191/job/114398735163) passed at 05:35:40 UTC. Release 0.2.9 bundles only `scripts/ai.py` and `tests/test_ai.py` in its ZIP; it still excludes the launcher C++/QML, AI panel, and bar. The helper files are not a published AI feature or proof of AI readiness.

## What this slice does

The launcher adds an **IA** panel, initially off. Opening it starts no helper or provider process. The explicit **Verificar clientes instalados** action asks a fixed helper to inspect a fixed list: Codex, Claude Code, OpenCode, Ollama and LM Studio. Version commands are restricted to recognized CLIs; Ollama is presence-only because its version command may contact a live service. Each provider remains `enabled: false`.

A separate explicit consent action tests one narrow Codex compatibility exchange, `initialize` followed by `initialized`, for the recognized Codex version. It is a protocol handshake, not authentication, session reuse, model startup, a turn, text generation, usage reporting, or an API entitlement check. Neither operation takes search text, selected text, or other user context. There is no credentials store, chat, text-selection workflow, or terminal handoff in this slice.

## PR CI scope

The PR workflow passed portable Python/QML checks and produced a Source ZIP artifact. The ZIP contains `scripts/ai.py` and `tests/test_ai.py`; the launcher C++/QML files remain excluded. Its CI run passed the helper suite, 19 tests in 13.065 seconds. This workflow did **not** compile the launcher C++/QML or run the controller CTests. The 0.2.9 release reuses the helper files in its ZIP, but this does not package the launcher panel. This CI result is separate from the local controller/helper and one-shot evidence below.

## Bounded source evidence

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

The adapter is not wired into the command-line entry point or a default
transport factory. Signal/timer adapters, operational CLI, TLS/OpenAI transport,
launcher text UI and real cancellation remain separate work. Authentication,
credentials stores, subscriptions, inference, usage and billing were not
exercised. A local model endpoint or a provider subscription does not establish
account permission or API credit. The module is a Source foundation; published
0.2.9 assets remain unchanged.

## Reviewed source pins

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

See the [launcher build/source guide](../../launcher/README.md) and the [long-term integration proposal](../AI_INTEGRATIONS.md). The reviewed component-level reports and local one-shot receipt are preserved in the repository's private `.runtime` evidence area; they are not public API guarantees.
