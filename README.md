# Orla Desktop

![Orla Desktop — native dock for KDE Plasma](website/assets/share.png)

**A personal dock for KDE Plasma, with a calm coastal identity and room to grow.**

Orla Dock is an open-source Plasma applet for pinning applications, switching between open windows, and keeping a few useful tools close by. It is an early alpha: the dock works today. The source checkout also has experimental components for an optional menu bar, launcher, and first Control Center slice; full integration, notification surfaces, and several integrations remain planned.

> [Project website](https://orla-desktop.sunlit-duck-7687.chatgpt.site) · [Português brasileiro](README.pt-BR.md) · [Roadmap](ROADMAP.md) · [Brand guide](docs/brand.md)

The source checkout also includes an [experimental standalone launcher](https://github.com/caiolombello/orla-desktop/blob/main/launcher/README.md) for local applications and calculations. It requires a separate C++/Qt/KF6 build. Releases 0.2.5–0.2.9 do not package or install the launcher; global Wayland focus and complete launcher integration remain open. The launcher source also has an experimental AI compatibility panel, integrated in PR [#20](https://github.com/caiolombello/orla-desktop/pull/20) with portable CI. Release 0.2.9 bundles only `scripts/ai.py` and `tests/test_ai.py`; the launcher and its AI panel remain excluded. It is off by default and does not authenticate or generate responses; see the [source validation record](docs/validation/ai-provider-source.md).

The source checkout includes [Menu Orla, the first experimental bar component](https://github.com/caiolombello/orla-desktop/blob/main/bar/README.md), with a system menu and active application name for Plasma 6.7.x. It requires separate manual installation and is excluded from releases 0.2.5–0.2.9. Native session dialogs, panel/focus behavior and multi-monitor composition remain untested. Global Menu, tray and clock are future sibling KDE widgets.

The 0.2.9 release bundle includes an [experimental update-check CLI](docs/updates.md). It checks official stable/beta releases only when invoked, compares an explicit version, and reports network failures separately. Run it from the extracted bundle; the `.plasmoid` alone has no CLI or update UI. Caching and installation recovery remain planned.

The 0.2.9 alpha prerelease ZIP includes the experimental local Steam inventory CLI. It reads bounded library metadata from explicitly supplied roots and reports partial/unknown states; it does not launch games, access an account or prove ownership. Dock search/favorites and real Steam validation remain planned. The 0.2.5 release assets remain unchanged and do not include it. The 0.2.6, 0.2.7 and 0.2.8 ZIPs also bundle this CLI; the standalone `.plasmoid` has no CLI. See the [Steam guide](docs/steam.md).

## What works today

Alpha 0.2.9 publishes the first experimental Control Center slice: an optional global dock button, off by default, with shared media and battery status plus explicit shortcuts to KDE settings. Independent Source review approved this slice, but native popup/KCM and service or hardware behavior remain unqualified; see the [Control Center guide](docs/control-center.md) and [validation record](docs/validation/control-center-peripherals-0.2.9.md).

The current source checkout also has an [experimental KDE calendar slice](docs/calendar.md). It enables KDE's existing PIM event plugin in the calendar model only while the popup is open and reports only states the plugin API can support without guessing. Disabling the model entry does not prove that KDE backend processes stopped. Its tests use synthetic events and do not access Akonadi, Google accounts or personal calendars. This change is not a new release; the published 0.2.9 assets remain unchanged.

- Pin, reorder, launch, and remove applications; switch to or minimize open windows. Open app menus with Menu or Shift+F10; Escape closes them.
- Start from Glass, Midnight or Paper and preview colors, opacity, spacing, corners, icon size and reduced motion. Apply saves; Cancel, Escape or closing settings discards the preview. Undo restores the previous applied appearance once per session.
- Use the clock, Pomodoro timer, KDE calendar view, and MPRIS media controls with player selection, track/artist text, and capability-aware playback buttons. An optional local in-dock notice marks the completion of a Pomodoro focus or break period; it is off by default and does not use KDE notifications.
- Enable the optional system battery widget in settings (off by default) to read the UPower aggregate; PeriGauge remains separate for peripherals.
- Read optional local snapshots from QuotaLantern, PeriGauge, and FalaTrace when those projects have written supported state files.
- Create and explicitly select manual profiles for pinned apps, appearance, widget order/visibility, calendar events and the current-desktop window filter. The Pomodoro remains shared.
- Keep the dock in a Plasma panel and configure its position and visibility through Plasma.

The calendar reads the same calendar selection as KDE's calendar components without changing it. Changing that selection in KDE also changes KDE's clock/calendar. Orla does not connect Google Calendar by itself: use **Configure in KOrganizer** to add and authenticate the Google resource through KDE PIM, then enable synced events in the desired Orla profile. An empty day cannot distinguish no events from an unavailable or unconfigured KDE PIM backend; see the [calendar guide](docs/calendar.md).

Media controls share one native Plasma MPRIS model. They initially prefer Spotify when discovered and keep a manual player choice for the session. Play, Pause, Previous and Next respect the selected player’s capabilities; track and artist render as bounded plain text. A private D-Bus fixture qualified the native model with two synthetic players, not the real Spotify client or audio playback. Artwork, progress and opening the client remain planned.

System battery reads only UPower’s aggregate display device, every 30 seconds while enabled, with a five-second request timeout. A genuine 0% reading stays visible; absent or unavailable data has a neutral state. External power, charging and estimated time appear only when supplied. It does not control hardware or enumerate peripheral batteries. See [battery and media validation](docs/validation/battery-media-0.2.4.md) for test coverage and limits. Local project integrations read existing state files; they do not start the other apps or call their online APIs.

Appearance uses a separate override, preserving earlier theme/icon/motion preferences. Restore prepares those preferences for preview and requires Apply. The editor now has a paste-only **Experimental JSON theme** preview for the `0.1-experimental` format. It previews ten tokens in memory; Apply saves only the current profile's ordinary appearance. It does not read files, install a theme package, or save its declared metadata. The format and consumer remain experimental; see the [theme guide](docs/theme-format.md) and [consumer validation](docs/validation/theme-consumer-0.2.6.md) for coverage and native limits.

The [local Pomodoro notice](docs/local-events.md) is a separate opt-in preference in **Widgets**, global across profiles and off by default. It lasts up to eight seconds inside a reserved dock area. Only focus and break completion use it; HUD/island surfaces and KDE notification integration remain unimplemented. See the [0.2.7 validation record](docs/validation/local-events-0.2.7.md) for test and native limits.

## Use profiles

Open dock settings and choose **Perfis** (Profiles), alongside **Aparência** (Appearance), **Widgets** and **Contextos** (Contexts). **Criar Trabalho, Pessoal e Jogos** copies your saved preferences into Work, Personal and Games profiles while keeping **Preferências anteriores** (Previous preferences) active. Choose a profile and press **Usar perfil**; changing the selector alone does not activate it. To clone the saved active presentation, enter a unique name and press **Criar e usar**. Apply or cancel an appearance preview before creating or switching profiles.

In **Widgets**, visibility, order, calendar events and the window filter save immediately for the active profile; appearance Cancel does not undo them. Widget ordering requires a profile. Return to **Preferências anteriores** to use the original flat preferences. There is no automatic migration. See the [profile guide](docs/profiles.md) for limits and the [validation record](docs/validation/profiles-0.2.5.md) for the private KConfig/restart proof. The published alpha 0.2.8 adds the first experimental **Contexts** tab for explicitly associating the current Activity or virtual desktop with an existing managed profile. It does not switch either context or select profiles automatically; see the [Contexts guide](docs/contexts.md) and [0.2.8 validation](docs/validation/contexts-0.2.8.md). P2 remains partial, W1 is unstarted, and native session qualification remains open.

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

These commands target the [0.2.9 alpha prerelease](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.9). Download its release `.zip`, verify its checksum using the published `SHA256SUMS`, and extract it. The bundle contains the helper and applet archive together:

```bash
cd ~/Downloads
sha256sum --ignore-missing -c SHA256SUMS
unzip orla-dock-0.2.9.zip
cd orla-dock-0.2.9
python3 scripts/orla.py doctor
python3 scripts/orla.py install orla-dock-0.2.9.plasmoid
```

The helper registers the local integration service when its packaged bridge and optional dependencies are available. `doctor` reports missing optional dependencies separately. After restoring them, reinstall the same package to activate integrations. A failed D-Bus refresh reports a warning while preserving the installed dock. The helper does not need administrator access. After installation, add **Orla Dock** from Plasma's Add Widgets interface. Keep the extracted directory if you may want to run the helper again.

To build and install from a source checkout instead:

```bash
git clone https://github.com/caiolombello/orla-desktop.git
cd orla-desktop
python3 scripts/orla.py doctor
python3 scripts/orla.py build
python3 scripts/orla.py install dist/orla-dock-0.2.9.plasmoid
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

Calendar QML checks are the exception: run `python3 -B tests/run_calendar_tests.py` (and add `--style org.kde.desktop` for the KDE style). This stdlib supervisor starts Qt offscreen in a separate process with owned XDG directories and an unavailable session-bus endpoint. Do not combine `test_calendar` with graphical dock suites in one `unittest` process.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. For security concerns, follow [SECURITY.md](SECURITY.md).

## Project status

Orla Desktop is an alpha project. The current component keeps the existing Plasma package identifier `org.caiodock.dock` and D-Bus service `org.caiodock.Integrations` to preserve existing installations and settings. The name shown to users is Orla Dock; these internal identifiers are compatibility details.

Manual dock profiles and widget organization are the partial P1/C1 increment shipped in 0.2.5. Version 0.2.6 added the first paste-only experimental theme consumer and bundled the experimental Steam CLI. The 0.2.7 ZIP carries that CLI forward and adds one opt-in in-dock Pomodoro focus-or-break completion notice. The 0.2.8 alpha release adds explicit profile associations for the current Activity or virtual desktop; P2 remains partial, W1 is unstarted, and native context behavior remains unqualified. The 0.2.9 alpha publishes the first optional Control Center slice; CC0 remains partial and native behavior unqualified. The native panel and system-notification behavior also remain unqualified. The system battery reader and player selection/control increment shipped in 0.2.4; the full B1/M1 milestones remain open for hardware and real-client qualification. The full macOS-inspired optional bar, Control Center, complete Raycast-like launcher integration, AI authentication/inference and selected-text workflow, HUD/island and broader notifications, Spotify artwork/progress/client opening, Steam dock integration, automatic profile selection from desktop/Activity context, desktop/activity switching, automatic updates, and fuller project integrations are roadmap items. A stable theme contract, gallery, file import, public extension SDK, independently sold addons, and optional AI integrations are also planned.

See the [complete roadmap](ROADMAP.md) for sequencing, dependencies, and acceptance criteria, with companion proposals for [UX/UI](docs/UX_UI.md), [themes and extensions](docs/EXTENSIONS.md), [AI access and providers](docs/AI_INTEGRATIONS.md), and [developer experience](docs/DX.md). Declarative themes come before executable plugins; AI adapters use each provider's supported authorization route. The core remains useful without an Orla account, paid addon, or AI subscription. Marketplace checkout and the extension SDK have not been implemented.

## License

Orla Desktop is distributed under the [MIT License](LICENSE).
