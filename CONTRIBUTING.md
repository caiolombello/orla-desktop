# Contributing to Orla Desktop

Thanks for helping improve Orla. The project is an early alpha, so focused reports and small changes that include a clear reproduction path are especially useful.

## Before opening an issue or pull request

- Search existing issues and the [roadmap](ROADMAP.md).
- For a bug report, include the Orla version, distribution, Plasma and Qt versions, session type (Wayland or X11), steps to reproduce, and what happened versus what you expected.
- Remove personal data from logs and screenshots. Do not attach calendar contents, window titles, account names, tokens, or full home-directory paths.
- For a change, explain the user-visible behavior and any KDE/Plasma version assumptions. Keep unrelated refactors out of the patch.

Reports, translations, accessibility feedback, documentation, synthetic test fixtures, and KDE/hardware validation are welcome today. The applet now accepts pasted JSON for an experimental theme preview; the data format, consumer UI and CLI remain experimental and are not a stable public API. Preview is memory-only and Apply saves the current profile's normal appearance, without retaining theme metadata. File import, theme gallery, extension tooling, a public SDK and catalog remain planned. See the [theme guide](docs/theme-format.md), [consumer validation](docs/validation/theme-consumer-0.2.6.md), and proposals for [UX/UI](docs/UX_UI.md), [extensions](docs/EXTENSIONS.md), [AI integrations](docs/AI_INTEGRATIONS.md), and [DX](docs/DX.md). Discuss changes to public contracts, permissions, or distribution before implementation, including an acceptance criterion and validation path.

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

Manual dock profiles use the experimental `0.1-experimental` JSON format, independently versioned from Orla. Read the [profile guide](docs/profiles.md) and [validation bounds](docs/validation/profiles-0.2.5.md) before changing it. Preserve flat preferences and invalid/future JSON; profile selection is explicit. Profile QML checks can run sequentially with each supported style:

```bash
PYTHONPATH=tests QT_QUICK_CONTROLS_STYLE=Fusion python3 -B -m unittest test_profiles test_profiles_dock test_qml test_appearance -v
PYTHONPATH=tests QT_QUICK_CONTROLS_STYLE=org.kde.desktop python3 -B -m unittest test_profiles test_profiles_dock test_qml test_appearance -v
```

The profile core also runs independently in portable CI with offscreen Qt; the dock integration suites above need KDE/Qt. These synthetic checks do not qualify native popups or human panel gestures. The private KConfig proof covers a frozen snapshot and one owned remove/re-add cycle with the new applet explicitly seeded from saved JSON; timer resume across processes, real apps and full release qualification remain separate.

The source checkout has a separate experimental [C++/Qt Quick launcher](https://github.com/caiolombello/orla-desktop/blob/main/launcher/README.md). Its guide lists the versioned dependencies and build/CTest commands. All five CTests guard a private D-Bus and temporary XDG/runtime; the execution fixture launches only its own desktop entry, the AI controller fixtures use fake helpers, and the Steam controller fixtures use a synthetic tree and injected opener. The `launcher-build-and-ctest` job compiles the component in a digest-pinned Fedora 44 container; [its hosted run passed all five CTests](https://github.com/caiolombello/orla-desktop/actions/runs/38124013823/job/114424469019). This does not configure a required status check or qualify global focus, native Plasma/Wayland behavior, real providers, installation, or release.

The source checkout also includes [Menu Orla, an experimental optional bar component](https://github.com/caiolombello/orla-desktop/blob/main/bar/README.md), independently identified as `org.orla.bar` 0.1.0. It is excluded from release 0.2.5. Its injected-backend tests need Python/PySide6 and Qt Quick Controls, but no graphical session or native session/task adapters:

```bash
python3 bar/run_tests.py
# Optional, with the KDE style installed:
python3 bar/run_tests.py --style org.kde.desktop
```

The wrapper owns temporary XDG roots and unavailable private bus addresses, removes inherited display/session-starter variables, and uses offscreen/software Qt. The default Fusion run is suitable for portable CI. Ten mocks check explicit actions, capabilities, keyboard/Escape, errors, bounded plain text, label preservation throughout menu opening/closure, and native-loader isolation. Native dialogs/Cancel, real actions/settings dispatch, panel/focus and two-monitor composition remain UNRUN. Compilation and mock dispatch are separate from native qualification; do not mark T1/T2/T3 complete from these checks.

The experimental [release-check CLI](docs/updates.md) uses Python's standard library on Linux. Run its offline tests in their own process with `python3 -m unittest discover -s tests -p 'test_updates.py' -v`; no network or provider account is required. These tests are included in portable CI. Live release checks are explicit commands and never run during tests.

The experimental [Steam collector](https://github.com/caiolombello/orla-desktop/blob/main/docs/steam.md) also uses only Python's standard library on Linux. Its twenty synthetic checks run separately with `python3 -B -m unittest discover -s tests -p 'test_steam.py' -v` and in portable CI. Never point fixtures at a personal Steam library. The worker forks: invoke the CLI in its own process, not inside a threaded Qt process. Native/Flatpak are caller-supplied hints, and manifest presence never proves ownership or client installation.

Contributions and CI must not require paid AI calls, an AI subscription, or private account credentials. The experimental AI helper's nineteen offline tests use synthetic clients, ELF fixtures and a Bubblewrap shim; run them separately with `python3 -B -m unittest discover -s tests -p 'test_ai.py' -v`. Portable CI includes this suite; it does not prove real namespace/network enforcement, authentication or inference. Live provider checks are separate, manually initiated, and opt-in. See the [bounded validation record](docs/validation/ai-provider-source.md). UI changes include the relevant loading, empty, error, long-text, keyboard/focus, contrast, and reduced-motion states. Captures should use synthetic data.

## Pull requests

- Keep the change focused and explain how you checked it.
- Add or update tests when behavior changes and the relevant test harness can verify it.
- Preserve the existing package ID `org.caiodock.dock` and D-Bus name `org.caiodock.Integrations` unless a migration is explicitly designed.
- Do not include runtime captures, user cache files, private project state, generated archives, credentials, or unreviewed dependency updates.
- Use clear commit messages. Maintainers handle version numbers and release notes.

By submitting a contribution, you agree that it may be distributed under the project's MIT License.

That rule applies to contributions accepted into this repository. A separately distributed addon may use its author's declared license. Include clear authorship and redistribution rights for assets/dependencies; the core's MIT License does not license third-party content automatically. External sales are part of the proposed ecosystem, not a checkout or commercial support service operated by Orla today.
