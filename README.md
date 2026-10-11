# Orla Desktop

![Orla Desktop — native dock for KDE Plasma](website/assets/share.png)

**A personal dock for KDE Plasma, with a calm coastal identity and room to grow.**

Orla Dock is an open-source Plasma applet for pinning applications, switching between open windows, and keeping a few useful tools close by. It is an early alpha: the dock works today, while the optional top bar, launcher, notification surfaces, system controls, and several integrations remain planned.

> [Project website](https://orla-desktop.sunlit-duck-7687.chatgpt.site) · [Português brasileiro](README.pt-BR.md) · [Roadmap](ROADMAP.md) · [Brand guide](docs/brand.md)

## What works today

- Pin, reorder, launch, and remove applications; switch to or minimize open windows. Open app menus with Menu or Shift+F10; Escape closes them.
- Start from Glass, Midnight or Paper and preview colors, opacity, spacing, corners, icon size and reduced motion. Apply saves; Cancel, Escape or closing settings discards the preview. Undo restores the previous applied appearance once per session.
- Use the clock, Pomodoro timer, KDE calendar view, and generic MPRIS media controls.
- Read optional local snapshots from QuotaLantern, PeriGauge, and FalaTrace when those projects have written supported state files.
- Keep the dock in a Plasma panel and configure its position and visibility through Plasma.

The calendar uses the same calendar selection as KDE's calendar components. Orla does not connect Google Calendar by itself. To use Google events, first add and configure a Google account through KOrganizer/KDE PIM, then enable synced events in Orla. Account setup and sync depend on KDE PIM resources installed on your system.

Media controls use MPRIS and work with compatible players. Spotify-specific behavior, artwork, and playback have not yet been qualified. Local project integrations read existing state files; they do not start the other apps or call their online APIs.

Appearance uses a separate override, preserving earlier theme/icon/motion preferences. Restore prepares those preferences for preview and requires Apply. The [experimental theme kit](docs/theme-format.md) validates and packages community data; importing/applying those files remains planned. See [appearance validation](docs/validation/appearance-0.2.3.md) for test coverage and native limits.

## Requirements

- KDE Plasma 6.7 or newer.
- Python 3.10 or newer for the packaging helper and local integrations.
- `kpackagetool6` for installation. PySide6 with QtDBus, `busctl`, and a user D-Bus session are optional requirements for local project integrations. Missing them does not block installing the dock.
- KOrganizer and the appropriate KDE PIM calendar resource for synchronized external calendars.

On a Fedora system that already has Plasma 6.7+, install the package tool. Add the optional integration dependencies if you want project widgets, then run `doctor` inside your desktop session:

```bash
sudo dnf install kf6-kpackage
# Optional local project integrations:
sudo dnf install python3-pyside6 systemd
```

The current validation baseline is Fedora 44, Plasma 6.7.5, Qt 6.11.2, and Wayland. Other distributions, Plasma versions, X11 sessions, and multi-monitor behavior still need validation.

## Install a release

Download the release `.zip` from the [GitHub Releases page](https://github.com/caiolombello/orla-desktop/releases), verify its checksum using the published `SHA256SUMS`, and extract it. The bundle contains the helper and applet archive together:

```bash
cd ~/Downloads
sha256sum --ignore-missing -c SHA256SUMS
unzip orla-dock-0.2.3.zip
cd orla-dock-0.2.3
python3 scripts/orla.py doctor
python3 scripts/orla.py install orla-dock-0.2.3.plasmoid
```

The helper registers the local integration service when its packaged bridge and optional dependencies are available. `doctor` reports missing optional dependencies separately. After restoring them, reinstall the same package to activate integrations. A failed D-Bus refresh reports a warning while preserving the installed dock. The helper does not need administrator access. After installation, add **Orla Dock** from Plasma's Add Widgets interface. Keep the extracted directory if you may want to run the helper again.

To build and install from a source checkout instead:

```bash
git clone https://github.com/caiolombello/orla-desktop.git
cd orla-desktop
python3 scripts/orla.py doctor
python3 scripts/orla.py build
python3 scripts/orla.py install dist/orla-dock-0.2.3.plasmoid
```

To check the local setup or remove Orla's managed files:

```bash
python3 scripts/orla.py doctor
python3 scripts/orla.py uninstall
```

Remove Orla Dock from any panels before uninstalling. The command removes the applet and its managed integration service while preserving Plasma's saved widget settings for a later reinstall. It does not ask for confirmation, so run it only when you intend to remove those files.

## Development

Run the portable tests and build check with Python:

```bash
python3 -m unittest discover -s tests -p 'test_integrations.py' -v
python3 -m unittest discover -s tests -p 'test_package_cli.py' -v
python3 scripts/orla.py build
```

QML interaction tests require a running graphical KDE session. Native panel behavior, Wayland focus, global menus, notifications, and multi-monitor behavior are not covered by portable CI; report the exact Plasma version and session type when filing an issue.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. For security concerns, follow [SECURITY.md](SECURITY.md).

## Project status

Orla Desktop is an alpha project. The current component keeps the existing Plasma package identifier `org.caiodock.dock` and D-Bus service `org.caiodock.Integrations` to preserve existing installations and settings. The name shown to users is Orla Dock; these internal identifiers are compatibility details.

The macOS-inspired optional menu bar, Control Center, Raycast-like launcher, Dynamic Island/HUD/toasts, Spotify-specific support, system battery, Steam, profiles, desktop/activity switching, automatic updates, and fuller project integrations are roadmap items. Community themes, a versioned extension SDK, independently sold addons, and optional AI integrations are also planned. They are not included in the current release.

See the [complete roadmap](ROADMAP.md) for sequencing, dependencies, and acceptance criteria, with companion proposals for [UX/UI](docs/UX_UI.md), [themes and extensions](docs/EXTENSIONS.md), [AI access and providers](docs/AI_INTEGRATIONS.md), and [developer experience](docs/DX.md). Declarative themes come before executable plugins; AI adapters use each provider's supported authorization route. The core remains useful without an Orla account, paid addon, or AI subscription. Marketplace checkout and the extension SDK have not been implemented.

## License

Orla Desktop is distributed under the [MIT License](LICENSE).
