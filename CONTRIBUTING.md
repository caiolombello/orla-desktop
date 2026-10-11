# Contributing to Orla Desktop

Thanks for helping improve Orla. The project is an early alpha, so focused reports and small changes that include a clear reproduction path are especially useful.

## Before opening an issue or pull request

- Search existing issues and the [roadmap](ROADMAP.md).
- For a bug report, include the Orla version, distribution, Plasma and Qt versions, session type (Wayland or X11), steps to reproduce, and what happened versus what you expected.
- Remove personal data from logs and screenshots. Do not attach calendar contents, window titles, account names, tokens, or full home-directory paths.
- For a change, explain the user-visible behavior and any KDE/Plasma version assumptions. Keep unrelated refactors out of the patch.

Reports, translations, accessibility feedback, documentation, synthetic test fixtures, and KDE/hardware validation are welcome today. Source checkouts also include an [experimental declarative theme format](docs/theme-format.md), validator and two examples. They validate and package data; applying community themes, extension tooling, a public SDK, and the catalog remain planned. Do not depend on an experimental interface as stable. See the proposals for [UX/UI](docs/UX_UI.md), [extensions](docs/EXTENSIONS.md), [AI integrations](docs/AI_INTEGRATIONS.md), and [DX](docs/DX.md). Discuss changes to public contracts, permissions, or distribution before implementation, including an acceptance criterion and validation path.

## Local checks

Use Python 3.10 or newer with PySide6 QtDBus, and make `dbus-run-session` available for the private service test. Run the portable tests and package build:

```bash
python3 -m unittest discover -s tests -p 'test_integrations.py' -v
python3 -m unittest discover -s tests -p 'test_package_cli.py' -v
python3 -m unittest discover -s tests -p 'test_themes.py' -v
python3 -m unittest discover -s tests -p 'test_release.py' -v
python3 scripts/release.py
```

Theme validation and its tests need only Python 3.10 or newer on Linux, without
KDE, Qt, a provider account or paid calls. From a source checkout:

```bash
python3 scripts/themes.py validate themes/examples/essential.json --json
python3 scripts/themes.py pack themes/examples/mare.json --output dist/themes
```

Packing never replaces an existing artifact; choose a new output directory for
a revised example. See [the format guide](docs/theme-format.md) for fields,
structured errors and limits. The format is `0.1-experimental`, independently
versioned from Orla. These commands do not install or apply a theme.

QML interaction tests need the KDE/Qt runtime and a graphical session. Before changing a Plasma API or claiming native behavior, verify it on the stated Plasma version and record that version in the pull request. The continuous integration job checks portable behavior and package generation; it does not prove panel, Wayland, multi-monitor, or notification behavior.

The source checkout has a separate experimental [C++/Qt Quick launcher](launcher/README.md). Its guide lists the versioned dependencies and build/CTest commands. All three CTests guard a private D-Bus and temporary XDG/runtime; the execution fixture launches only its own desktop entry. Portable CI does not compile this component. Its global focus and installation gates remain independent of the dock tests.

The experimental [release-check CLI](docs/updates.md) uses Python's standard library on Linux. Run its offline tests in their own process with `python3 -m unittest discover -s tests -p 'test_updates.py' -v`; no network or provider account is required. These tests are included in portable CI. Live release checks are explicit commands and never run during tests.

Contributions and CI must not require paid AI calls, an AI subscription, or private account credentials. Future provider tests use synthetic mocks by default; live tests are separate, manually initiated, and opt-in. UI changes include the relevant loading, empty, error, long-text, keyboard/focus, contrast, and reduced-motion states. Captures should use synthetic data.

## Pull requests

- Keep the change focused and explain how you checked it.
- Add or update tests when behavior changes and the relevant test harness can verify it.
- Preserve the existing package ID `org.caiodock.dock` and D-Bus name `org.caiodock.Integrations` unless a migration is explicitly designed.
- Do not include runtime captures, user cache files, private project state, generated archives, credentials, or unreviewed dependency updates.
- Use clear commit messages. Maintainers handle version numbers and release notes.

By submitting a contribution, you agree that it may be distributed under the project's MIT License.

That rule applies to contributions accepted into this repository. A separately distributed addon may use its author's declared license. Include clear authorship and redistribution rights for assets/dependencies; the core's MIT License does not license third-party content automatically. External sales are part of the proposed ecosystem, not a checkout or commercial support service operated by Orla today.
