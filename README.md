# Orla Desktop

![Orla Desktop — native dock for KDE Plasma](website/assets/share.png)

**A personal dock for KDE Plasma, with a calm coastal identity and room to grow.**

Orla Dock is an open-source Plasma applet for pinning applications, switching between open windows, and keeping a few useful tools close by. It is an early alpha: the dock works today, while the optional top bar, launcher, notification surfaces, system controls, and several integrations remain planned.

> [Project website](https://orla-desktop.sunlit-duck-7687.chatgpt.site) · [Português brasileiro](README.pt-BR.md) · [Roadmap](ROADMAP.md) · [Brand guide](docs/brand.md)

The source checkout also includes an [experimental standalone launcher](https://github.com/caiolombello/orla-desktop/blob/main/launcher/README.md) for local applications and calculations. It requires a separate C++/Qt/KF6 build. Release 0.2.5 does not package or install it; global Wayland focus and complete launcher integration remain open.

The 0.2.5 release bundle includes an [experimental update-check CLI](docs/updates.md). It checks official stable/beta releases only when invoked, compares an explicit version, and reports network failures separately. Run it from the extracted bundle; the `.plasmoid` alone has no CLI or update UI. Caching and installation recovery remain planned.

## What works today

- Pin, reorder, launch, and remove applications; switch to or minimize open windows. Open app menus with Menu or Shift+F10; Escape closes them.
- Start from Glass, Midnight or Paper and preview colors, opacity, spacing, corners, icon size and reduced motion. Apply saves; Cancel, Escape or closing settings discards the preview. Undo restores the previous applied appearance once per session.
- Use the clock, Pomodoro timer, KDE calendar view, and MPRIS media controls with player selection, track/artist text, and capability-aware playback buttons.
- Enable the optional system battery widget in settings (off by default) to read the UPower aggregate; PeriGauge remains separate for peripherals.
- Read optional local snapshots from QuotaLantern, PeriGauge, and FalaTrace when those projects have written supported state files.
- Create and explicitly select manual profiles for pinned apps, appearance, widget order/visibility, calendar events and the current-desktop window filter. The Pomodoro remains shared.
- Keep the dock in a Plasma panel and configure its position and visibility through Plasma.

The calendar uses the same calendar selection as KDE's calendar components. Orla does not connect Google Calendar by itself. To use Google events, first add and configure a Google account through KOrganizer/KDE PIM, then enable synced events in Orla. Account setup and sync depend on KDE PIM resources installed on your system.

Media controls share one native Plasma MPRIS model. They initially prefer Spotify when discovered and keep a manual player choice for the session. Play, Pause, Previous and Next respect the selected player’s capabilities; track and artist render as bounded plain text. A private D-Bus fixture qualified the native model with two synthetic players, not the real Spotify client or audio playback. Artwork, progress and opening the client remain planned.

System battery reads only UPower’s aggregate display device, every 30 seconds while enabled, with a five-second request timeout. A genuine 0% reading stays visible; absent or unavailable data has a neutral state. External power, charging and estimated time appear only when supplied. It does not control hardware or enumerate peripheral batteries. See [battery and media validation](docs/validation/battery-media-0.2.4.md) for test coverage and limits. Local project integrations read existing state files; they do not start the other apps or call their online APIs.

Appearance uses a separate override, preserving earlier theme/icon/motion preferences. Restore prepares those preferences for preview and requires Apply. The [experimental theme kit](docs/theme-format.md) validates and packages community data; importing/applying those files remains planned. See [appearance validation](docs/validation/appearance-0.2.3.md) for test coverage and native limits.

## Use profiles

Open dock settings and choose **Perfis** (Profiles), alongside **Aparência** (Appearance) and **Widgets**. **Criar Trabalho, Pessoal e Jogos** copies your saved preferences into Work, Personal and Games profiles while keeping **Preferências anteriores** (Previous preferences) active. Choose a profile and press **Usar perfil**; changing the selector alone does not activate it. To clone the saved active presentation, enter a unique name and press **Criar e usar**. Apply or cancel an appearance preview before creating or switching profiles.

In **Widgets**, visibility, order, calendar events and the window filter save immediately for the active profile; appearance Cancel does not undo them. Widget ordering requires a profile. Return to **Preferências anteriores** to use the original flat preferences. There is no automatic migration. See the [profile guide](docs/profiles.md) for limits and the [validation record](docs/validation/profiles-0.2.5.md) for the private KConfig/restart proof. Activity/desktop association, selecting bar/launcher/event surfaces and native popup/focus qualification remain open.

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

These commands target the 0.2.5 alpha prerelease; use them when its assets are published. Download the release `.zip` from the [GitHub Releases page](https://github.com/caiolombello/orla-desktop/releases), verify its checksum using the published `SHA256SUMS`, and extract it. The bundle contains the helper and applet archive together:

```bash
cd ~/Downloads
sha256sum --ignore-missing -c SHA256SUMS
unzip orla-dock-0.2.5.zip
cd orla-dock-0.2.5
python3 scripts/orla.py doctor
python3 scripts/orla.py install orla-dock-0.2.5.plasmoid
```

The helper registers the local integration service when its packaged bridge and optional dependencies are available. `doctor` reports missing optional dependencies separately. After restoring them, reinstall the same package to activate integrations. A failed D-Bus refresh reports a warning while preserving the installed dock. The helper does not need administrator access. After installation, add **Orla Dock** from Plasma's Add Widgets interface. Keep the extracted directory if you may want to run the helper again.

To build and install from a source checkout instead:

```bash
git clone https://github.com/caiolombello/orla-desktop.git
cd orla-desktop
python3 scripts/orla.py doctor
python3 scripts/orla.py build
python3 scripts/orla.py install dist/orla-dock-0.2.5.plasmoid
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

Manual dock profiles and widget organization are the partial P1/C1 increment prepared for 0.2.5. The system battery reader and player selection/control increment shipped in 0.2.4; the full B1/M1 milestones remain open for hardware and real-client qualification. The macOS-inspired optional menu bar, Control Center, Raycast-like launcher, Dynamic Island/HUD/toasts, Spotify artwork/progress/client opening, Steam, profile association with desktops/Activities, desktop/activity switching, automatic updates, and fuller project integrations are roadmap items. Community themes, a versioned extension SDK, independently sold addons, and optional AI integrations are also planned. They are not included in the current release.

See the [complete roadmap](ROADMAP.md) for sequencing, dependencies, and acceptance criteria, with companion proposals for [UX/UI](docs/UX_UI.md), [themes and extensions](docs/EXTENSIONS.md), [AI access and providers](docs/AI_INTEGRATIONS.md), and [developer experience](docs/DX.md). Declarative themes come before executable plugins; AI adapters use each provider's supported authorization route. The core remains useful without an Orla account, paid addon, or AI subscription. Marketplace checkout and the extension SDK have not been implemented.

## License

Orla Desktop is distributed under the [MIT License](LICENSE).
