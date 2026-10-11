# Manual profiles 0.2.5 — validation / Validação

Recorded for the 0.2.5 alpha prerelease, 2026-10-10 (America/Sao_Paulo).
Baseline: Fedora 44, Plasma 6.7.5, Qt/PySide6 6.11.2, Wayland.
**P1/C1 remain partial. Publication and full native release qualification are separate.**

## Delivered and reviewed

The 16-file profile implementation/test manifest was independently reviewed and approved. It adds explicit initialization, creation/selection, preserved flat preferences, profile-scoped appearance/Undo, pinned apps, seven-widget order/visibility, calendar-event visibility and current-desktop filtering. The JSON format remains `0.1-experimental`; invalid/future JSON is preserved and presentation writes are blocked. No passive migration or launcher-list autosave is introduced. The same global Pomodoro/provider objects remain outside the profile renderer. See [the user guide](../profiles.md).

## Recorded tests

The targeted suite passed **49 tests** separately with Fusion (12.055 s) and `org.kde.desktop` (14.269 s): 13 profile core, 14 profile integration, 12 dock QML and 10 appearance checks.

```bash
PYTHONPATH=tests QT_QUICK_CONTROLS_STYLE=Fusion python3 -B -m unittest test_profiles_dock test_qml test_appearance test_profiles -v
PYTHONPATH=tests QT_QUICK_CONTROLS_STYLE=org.kde.desktop python3 -B -m unittest test_profiles_dock test_qml test_appearance test_profiles -v
```

Run these sequentially. The root regression subsequently passed **123 tests with KDE style in 39.200 s**. The portable profile core also passed **13 tests** with PySide6 Essentials 6.12.0 using offscreen Qt; CI runs that core in a separate process. These are recorded local results, not a claim about every CI/platform configuration. Coverage includes explicit activation, saved cloning, stale scope/revision, preview/Cancel/Undo, immediate widget/calendar changes, hidden-all widgets, same-dock timer preservation, missing apps and Qt URL alias identity with original saved spelling preserved. Owned `.desktop` fixtures are not launched. Synthetic focus/key checks qualify their Qt controls, not native seat activation.

Local receipts: `.runtime/profiles-dock/report.md`, `evidence.json`, `source-sha256.txt` and the final Fusion/KDE, root-regression and `portable-qt-6.12.log` logs. These validation artifacts are not release contents; public reproduction uses the tests above.

## Private native persistence and one lifecycle cycle

A frozen snapshot with **metadata 0.2.4 plus reviewed profile overlays, 26 package files**, was copied and installed with 26/26 hash agreement in a private native Plasma shell. It used owned XDG trees, private D-Bus without automatic activation, virtual KWin and filesystem/PID/network isolation. Baseline and profile launchers were synthetic, never executed; external widgets/events were disabled.

Programmatic fixture actions observed actual `KConfigPropertyMap` configuration:

- Initialization retained Previous preferences and cloned Work/Personal/Games from the saved flat baseline; custom creation and profile selection worked.
- Apply saved profile appearance, reversed/hidden widgets, a synthetic pinned launcher and the window filter. The controller waited for exactly encoded KConfig disk content and verified decoded JSON equality before proceeding.
- Cancel discarded a preview without changing the applied product configuration group.
- Restart of the owned shell reloaded identical JSON, active profile and presentation; baseline flat fields matched in memory and disk.
- The same Pomodoro object/deadline survived profile selection with its widget hidden. It was explicitly reset before shell restart: **cross-process timer resume is UNRUN**.
- After saving persistence receipts, one separate cycle removed the owned applet and re-added a new applet ID, explicitly seeding the new applet with the saved JSON and observing the expected presentation while the shell stayed alive. This proves one bounded teardown/recreation and rehydration cycle, not automatic recovery of configuration after deleting an applet or qualification of every destruction path.

Attempt 2 completed in **14.75 s**, exit 0, without timeout or observed fatal/segfault. Logs retain warnings including realtime priority and unavailable PipeWire. Independent receipt review approved the bounded proof with zero blockers: 26/26 snapshot/installed hashes, independently decoded KConfig JSON, untrimmed Apply/Cancel/Restart product-group equality and the one seeded lifecycle cycle. Current source differs from the snapshot only in metadata/version label 0.2.4 → 0.2.5. The native evidence establishes programmatic persistence for the frozen bytes, not the full 0.2.5 package.

Attempt 1 is preserved as **FAIL**: its fixture compared raw JSON against KConfig's escaped representation. Apply/disk were observed, but Cancel/restart/teardown were **UNRUN** in that attempt. Diagnosis checked exact encoded and decoded equality against documented KConfig 6.30.0 string encoding; attempt 2 used new owned runtime/bus trees and the same frozen product bytes. It did not rewrite attempt 1 as passing.

Local native receipts: `.runtime/profiles-native-proof/REPORT.md`, `evidence/summary.json`, the retained `attempt1/` and attempt-2 disk/receipt/lifecycle artifacts, plus `.runtime/profiles-native-proof-review/REPORT.md`. The successful bootstrap is historical and refuses replay of its consumed fixture.

## Remaining acceptance / Aceite pendente

- Human gestures in an installed panel; `Popup.Window` presentation, input serial/grab/focus/layout, accessibility, scaling and multiple monitors.
- Resume of a running Pomodoro across processes; extended daily use and further teardown paths.
- Real apps/games/Spotify/calendar/accounts and launcher activation.
- P1 selection of bar/launcher/event surfaces; P2 Activity association and W1 desktop/Activity switching.
- Complete 0.2.5 release/install/upgrade qualification and all remaining C1/P1 gates.

A prior `kactivitymanagerd --help` attempt with inherited environment remains UNKNOWN; this isolated proof does not establish that all user-session configuration was unchanged.

**Resumo em português:** 49 testes direcionados passaram em Fusion e KDE; a regressão registrada passou 123 testes. A implementação de perfis foi aprovada em revisão. A prova nativa privada, com metadata 0.2.4 e 26 arquivos congelados incluindo overlays de perfis, comprovou Apply/Cancel/disco/reinício e um ciclo próprio de remover/recriar, com JSON salvo explicitamente atribuído ao novo applet; não prova recuperação automática após apagar. A revisão independente dos recibos aprovou a prova delimitada sem blockers. A primeira tentativa falhou no comparador da fixture e permanece preservada. Os comandos/sinais foram programáticos: popup, foco, gesto humano, retomada do timer entre processos e release completa continuam sem qualificação. P1/C1 permanecem parciais; P2/W1 são trilhas separadas.
