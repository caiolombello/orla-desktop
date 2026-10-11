# Foundation 0.2.2 — evidence and limits

Verified on 2026-10-10: Fedora 44, Plasma 6.7.5, Qt/PySide6 6.11.2, Python 3.14.7, Wayland. This is a bounded alpha increment; R1/R2 and the 0.3 milestone remain open.

## Implemented and checked

- Installation and upgrade continue when PySide6.QtDBus, busctl, or the user bus is absent. Doctor identifies optional dependencies. A failed optional ReloadConfig reports a warning after installation; integrity and foreign-service protections remain fatal.
- Menu and Shift+F10 open the corresponding task's context menu. Escape closes it and restores focus in the in-window Qt Quick test renderer. The test checks both Dolphin and Konsole identities.
- The synthetic calendar test explicitly polishes pending parent/view layouts before inspecting event titles. This avoids relying on rendering a window that may be occluded or behind a locked session.

Foundation test command, **43 PASS**:

```sh
PYTHONPATH=tests python3 -m unittest test_calendar test_integrations test_package_cli test_qml -v
```

Portable CLI tests include absent optional dependencies, registration recovery, ReloadConfig nonzero/OSError/timeout, and preservation of synthetic configuration/cache/service files. Qt tests require the installed KDE runtime; portable CI does not run the graphical suite.

## Native installation proof

Real `kpackagetool6`, new temporary XDG data/config/cache/state homes, and a private `dbus-run-session` were used. A private Python venv without system packages proved PySide6 was absent. Clean install and upgrade returned 0 and extracted the actual applet. Reinstall with system Python restored the owned D-Bus service and refreshed only the private bus. Uninstall removed the applet and its owned service. Synthetic configuration, cache, state, and an unrelated service retained their SHA256 hashes throughout. Temporary homes were removed afterwards.

The harness used `QT_QPA_PLATFORM=minimal` for headless version detection. An earlier offscreen attempt failed during `plasmashell --version`; it is excluded from the passing proof. No panels, graphical login settings, existing applet installation, or user project data were changed. The proof establishes the package lifecycle in isolated homes, not installation by a new person on every distribution.

## Gates still open

- Native Popup.Window placement, Wayland seat grabs, Escape/focus in a real Plasma panel, autohide/fullscreen, two monitors and restart.
- Complete launcher installation/dependency lifecycle, global shortcut and activation-token/focus qualification.
- Google account setup and real calendar sync, Spotify/hardware qualification, plugin isolation and AI authorization.
- Daily-use pilot and validation by new contributors/users.

Menu/event/launcher experiments are separate from this release. An exported Qt menu and passive LayerShell surface have worked in owned native windows. Notification models share a backend within one process in a private fixture; a second process does not become an observer of the existing owner. This does not qualify global notification replacement or native popup suppression. No roadmap gate is closed solely by these experiments.

## Português

A alpha 0.2.2 entrega instalação resiliente e menus de teclado. Os 43 testes da base passaram; instalar/atualizar sem PySide6, recuperar as integrações e desinstalar foi verificado com ferramentas reais em diretórios temporários e D-Bus privado, preservando os dados sintéticos. A interação de teclado usa o renderer dentro da janela. Painel real, foco/grabs Wayland, múltiplos monitores, launcher completo e uso diário continuam pendentes. A publicação desta correção não declara o marco 0.3 concluído.
