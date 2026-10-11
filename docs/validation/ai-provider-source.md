# Experimental AI provider compatibility — source validation

**Status:** Source-only candidate. This panel is part of the optional standalone launcher checkout; it is not included in the published 0.2.8 `.plasmoid` or ZIP. No version, PR/CI result, or release publication is claimed here. The public downloads remain the immutable 0.2.8 assets.

## What this slice does

The launcher adds an **IA** panel, initially off. Opening it starts no helper or provider process. The explicit **Verificar clientes instalados** action asks a fixed helper to inspect a fixed list: Codex, Claude Code, OpenCode, Ollama and LM Studio. Version commands are restricted to recognized CLIs; Ollama is presence-only because its version command may contact a live service. Each provider remains `enabled: false`.

A separate explicit consent action tests one narrow Codex compatibility exchange, `initialize` followed by `initialized`, for the recognized Codex version. It is a protocol handshake, not authentication, session reuse, model startup, a turn, text generation, usage reporting, or an API entitlement check. Neither operation takes search text, selected text, or other user context. There is no credentials store, chat, text-selection workflow, or terminal handoff in this slice.

## Bounded source evidence

- The controller/UI round-two Source review approved with zero blockers. Its focused CTest suite passed 4/4 in 30.69 seconds; a separate independent targeted run passed 6 cases in 3.492 seconds. These exercise fake helpers, private test buses, lifecycle/cancellation, and capability semantics.
- The helper round-four Source review approved with zero blockers. The synthetic helper suite passed 19 tests in 12.866 seconds; eight independent targeted fixtures passed. These use synthetic ELF data and a Bubblewrap shim, not proof of real namespace enforcement.
- A bounded one-shot run observed Codex CLI `0.162.1`, Claude Code `2.1.287` and OpenCode `2.0.24`; Ollama and LM Studio CLIs were absent from that run's fixed PATH. This says nothing about GUI applications or other environments. The separate Codex operation completed one `initialize`/`initialized` exchange. The receipt recorded zero paid requests. For recognized clients, authentication, inference, real cancellation and usage remain `unknown`; authentication, inference, cancellation behavior and billing were not exercised.
- For this local observation, namespace and network-denial enforcement were configured but **UNOBSERVED**; process-group cleanup observation was **NON_EXHAUSTIVE**. Installed client bytes are user-controlled, vendor provenance is unknown, and path-based metadata checks retain a same-user TOCTOU risk. A recognized CLI version or handshake does not prove account/provider permission or runtime isolation.

The panel therefore demonstrates only a bounded compatibility-reporting path in Source and one local protocol observation. It is not native launcher admission, provider readiness, or evidence that AI works in Orla as an end-user feature. Native Qt/KDE/Wayland behavior, normal launcher session/focus, packaging/install, authentication/session flows, model requests, inference, cancellation semantics, streaming/tools, usage, billing and general network/namespace enforcement remain UNRUN.

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
