# Contributing to Orla Desktop

Thanks for helping improve Orla. The project is an early alpha, so focused reports and small changes that include a clear reproduction path are especially useful.

## Before opening an issue or pull request

- Search existing issues and the [roadmap](ROADMAP.md).
- For a bug report, include the Orla version, distribution, Plasma and Qt versions, session type (Wayland or X11), steps to reproduce, and what happened versus what you expected.
- Remove personal data from logs and screenshots. Do not attach calendar contents, window titles, account names, tokens, or full home-directory paths.
- For a change, explain the user-visible behavior and any KDE/Plasma version assumptions. Keep unrelated refactors out of the patch.

## Local checks

Use Python 3.10 or newer with PySide6 QtDBus, and make `dbus-run-session` available for the private service test. Run the portable tests and package build:

```bash
python3 -m unittest discover -s tests -p 'test_integrations.py' -v
python3 -m unittest discover -s tests -p 'test_package_cli.py' -v
python3 scripts/release.py
```

QML interaction tests need the KDE/Qt runtime and a graphical session. Before changing a Plasma API or claiming native behavior, verify it on the stated Plasma version and record that version in the pull request. The continuous integration job checks portable behavior and package generation; it does not prove panel, Wayland, multi-monitor, or notification behavior.

## Pull requests

- Keep the change focused and explain how you checked it.
- Add or update tests when behavior changes and the relevant test harness can verify it.
- Preserve the existing package ID `org.caiodock.dock` and D-Bus name `org.caiodock.Integrations` unless a migration is explicitly designed.
- Do not include runtime captures, user cache files, private project state, generated archives, credentials, or unreviewed dependency updates.
- Use clear commit messages. Maintainers handle version numbers and release notes.

By submitting a contribution, you agree that it may be distributed under the project's MIT License.
