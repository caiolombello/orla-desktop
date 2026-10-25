#!/usr/bin/env python3
"""Apply or undo Orla's macOS-like look for the whole KDE session, in one step.

  macos_look.py apply      Orla Plasma theme (glass panels and popups), Orla window
                           decoration (traffic lights), an app switcher with large
                           icons and one entry per app (like Cmd+Tab), the
                           Magic Lamp minimize animation (like the Genie effect),
                           the date beside the time in the Orla top bar and
                           macOS-style notification banners
  macos_look.py restore    undo all of it, back to the saved settings
  macos_look.py status     print what is active and what restore would bring back

The theme, decoration, top bar clock and notifications keep their own saved
states (see plasma_theme.py, window_decoration.py, menu_bar_clock.py and
macos_notifications.py). The KWin keys below are saved here before the first
change; restore rewrites them or removes keys that were not set.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
KWIN = {
    # Large icons, one per application, without dimming the other windows.
    ("TabBox", "LayoutName"): "big_icons",
    ("TabBox", "ApplicationsMode"): "1",
    ("TabBox", "HighlightWindows"): "false",
    # Minimize into the dock like the Genie effect.
    ("Plugins", "magiclampEnabled"): "true",
    ("Plugins", "squashEnabled"): "false",
}


def _state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "orla" / "macos-look.json"


def _kwinrc() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kwinrc"


def user_values() -> dict:
    """The KWin keys as set in the user's own kwinrc; None when absent there."""
    values = {f"{group}/{key}": None for group, key in KWIN}
    path = _kwinrc()
    if not path.exists():
        return values
    group = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            group = stripped[1:-1]
        elif group and "=" in stripped:
            key, value = stripped.split("=", 1)
            name = f"{group}/{key}"
            if name in values:
                values[name] = value
    return values


def _write(group: str, key: str, value: str | None) -> None:
    command = ["kwriteconfig6", "--file", "kwinrc", "--group", group, "--key", key]
    command += ["--delete"] if value is None else [value]
    subprocess.run(command, check=True, timeout=10)


# KWin's own defaults, used when a restored key was not set before.
EFFECT_DEFAULTS = {"magiclamp": False, "squash": True}


def _effects(values: dict) -> None:
    """Load or unload the minimize effects now; reconfigure alone leaves them as they were."""
    for effect, default in EFFECT_DEFAULTS.items():
        value = values.get(f"Plugins/{effect}Enabled")
        enabled = default if value is None else value == "true"
        subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/Effects", "org.kde.kwin.Effects",
                        "loadEffect" if enabled else "unloadEffect", "s", effect],
                       check=True, timeout=15, stdout=subprocess.DEVNULL)


def _reconfigure() -> None:
    subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"],
                   check=True, timeout=15, stdout=subprocess.DEVNULL)


def _script(name: str, command: str, allow_failure: bool = False) -> int:
    result = subprocess.run([sys.executable, str(SCRIPTS / name), command], timeout=120,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode and not allow_failure:
        raise SystemExit(f"{name} {command} failed: {result.stderr.strip()}")
    return result.returncode


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("apply", "restore", "status"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    command = argv[1]
    state = _state_file()
    if command == "status":
        saved = json.loads(state.read_text(encoding="utf-8")) if state.exists() else None
        wanted = {f"{group}/{key}": value for (group, key), value in KWIN.items()}
        print(json.dumps({"kwinApplied": user_values() == wanted, "kwin": user_values(), "saved": saved}))
        return 0
    if command == "apply":
        for name in ("plasma_theme.py", "window_decoration.py"):
            _script(name, "install")
            _script(name, "apply")
        # Keep the first saved state: applying twice must not forget the original.
        if not state.exists():
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({"previous": user_values()}) + "\n", encoding="utf-8")
        for (group, key), value in KWIN.items():
            _write(group, key, value)
        _reconfigure()
        _effects({f"{group}/{key}": value for (group, key), value in KWIN.items()})
        # Without a running Plasma or an Orla top bar the clock is simply skipped.
        if _script("menu_bar_clock.py", "apply", allow_failure=True):
            print("macos_look: top bar clock left unchanged", file=sys.stderr)
        # Banners need the Orla Notifications package; without it KDE's popups stay.
        if (_script("macos_notifications.py", "install", allow_failure=True)
                or _script("macos_notifications.py", "apply", allow_failure=True)):
            print("macos_look: notifications left as KDE's", file=sys.stderr)
        return 0
    if state.exists():
        previous = json.loads(state.read_text(encoding="utf-8"))["previous"]
        for (group, key) in KWIN:
            _write(group, key, previous.get(f"{group}/{key}"))
        _reconfigure()
        _effects(previous)
        state.unlink()
    # Each part restores only what it changed; an already restored part is fine.
    _script("macos_notifications.py", "restore", allow_failure=True)
    _script("menu_bar_clock.py", "restore", allow_failure=True)
    _script("window_decoration.py", "restore", allow_failure=True)
    _script("plasma_theme.py", "restore", allow_failure=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
