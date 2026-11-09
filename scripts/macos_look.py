#!/usr/bin/env python3
"""Apply or undo Orla's macOS-like look for the whole KDE session, in one step.

  macos_look.py apply      Orla Plasma theme (glass panels and popups), Orla window
                           decoration (traffic lights), an app switcher with large
                           icons and one entry per app (like Cmd+Tab), the
                           Magic Lamp minimize animation (like the Genie effect),
                           the date beside the time in the Orla top bar,
                           macOS-style notification banners, a sparse tray and
                           hot corners (top left: Overview, like Mission
                           Control; bottom right: show the desktop) and a
                           floating KRunner near the top centre (a provisional
                           Spotlight). If KWin cannot load Magic Lamp, Squash
                           stays and status says so.
  macos_look.py restore    undo all of it, back to the saved settings
  macos_look.py status     print what is active and what restore would bring back

The theme, decoration, top bar clock and notifications keep their own saved
states (see plasma_theme.py, window_decoration.py, menu_bar_clock.py and
macos_notifications.py). The KWin and KRunner keys below are saved here before
the first change; restore rewrites them or removes keys that were not set.
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
    # Hot corners, as macOS users set them. 7 is KWin's TopLeft edge. The top
    # right stays free: the top bar's Control Center and clock live there.
    ("Effect-overview", "BorderActivate"): "7",
    ("ElectricBorders", "BottomRight"): "ShowDesktop",
}
# Squash in place of Magic Lamp, for a KWin that cannot load it.
SQUASH = {("Plugins", "magiclampEnabled"): "false", ("Plugins", "squashEnabled"): "true"}
# KRunner floats near the top centre like Spotlight. History and the prior
# search are on by KDE default; a user who turned them off keeps that choice.
KRUNNER = {("General", "FreeFloating"): "true"}


def _state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "orla" / "macos-look.json"


def _config(name: str) -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / name


def user_values(name: str = "kwinrc", keys: dict = KWIN) -> dict:
    """The keys as set in the user's own config file; None when absent there."""
    values = {f"{group}/{key}": None for group, key in keys}
    path = _config(name)
    if not path.exists():
        return values
    group = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            group = stripped[1:-1]
        elif group and "=" in stripped:
            key, value = stripped.split("=", 1)
            entry = f"{group}/{key}"
            if entry in values:
                values[entry] = value
    return values


def _write(group: str, key: str, value: str | None, name: str = "kwinrc", notify: bool = False) -> None:
    # --notify reaches running KConfigWatchers (KRunner), without restarting them.
    command = ["kwriteconfig6"] + (["--notify"] if notify else [])
    command += ["--file", name, "--group", group, "--key", key]
    command += ["--delete"] if value is None else [value]
    subprocess.run(command, check=True, timeout=10)


def _flat(keys: dict) -> dict:
    return {f"{group}/{key}": value for (group, key), value in keys.items()}


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


def _effect_loaded(effect: str) -> bool | None:
    """KWin's answer, or None when it gives none (then nothing is switched)."""
    result = subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/Effects", "org.kde.kwin.Effects",
                             "isEffectLoaded", "s", effect],
                            timeout=15, capture_output=True, text=True)
    # busctl prints a boolean reply as "b true" or "b false".
    answer = result.stdout.split() if result.returncode == 0 else []
    if len(answer) != 2 or answer[0] != "b":
        return None
    return {"true": True, "false": False}.get(answer[1])


def _reconfigure() -> None:
    subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"],
                   check=True, timeout=15, stdout=subprocess.DEVNULL)


def _script(name: str, command: str, allow_failure: bool = False) -> int:
    result = subprocess.run([sys.executable, str(SCRIPTS / name), command], timeout=120,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if result.returncode and not allow_failure:
        raise SystemExit(f"{name} {command} failed: {result.stderr.strip()}")
    return result.returncode


def _save(state: Path, saved: dict) -> None:
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(saved) + "\n", encoding="utf-8")


def _wanted(saved: dict | None) -> dict:
    keys = dict(KWIN)
    if saved and saved.get("minimize") == "squash":
        keys.update(SQUASH)
    return _flat(keys)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("apply", "restore", "status"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    command = argv[1]
    state = _state_file()
    saved = json.loads(state.read_text(encoding="utf-8")) if state.exists() else None
    if command == "status":
        print(json.dumps({"kwinApplied": user_values() == _wanted(saved), "kwin": user_values(),
                          "krunnerApplied": user_values("krunnerrc", KRUNNER) == _flat(KRUNNER),
                          "krunner": user_values("krunnerrc", KRUNNER),
                          # "squash": Magic Lamp did not load and Squash stayed;
                          # "unverified": KWin did not say whether it loaded.
                          "minimize": (saved or {}).get("minimize"), "saved": saved}))
        return 0
    if command == "apply":
        for name in ("plasma_theme.py", "window_decoration.py"):
            _script(name, "install")
            _script(name, "apply")
        # Keep the first saved state: applying twice must not forget the original.
        # A state saved before KRunner was part of the look gains its entry now.
        saved = saved or {"previous": user_values()}
        saved.setdefault("krunner", user_values("krunnerrc", KRUNNER))
        _save(state, saved)
        for (group, key), value in KWIN.items():
            _write(group, key, value)
        _reconfigure()
        _effects(_flat(KWIN))
        # Some KWin builds or GPUs lack Magic Lamp; then keep Squash, not no effect.
        # Without an answer from KWin nothing is switched and status says so.
        loaded = _effect_loaded("magiclamp")
        minimize = {True: "magiclamp", False: "squash", None: "unverified"}[loaded]
        if loaded is False:
            for (group, key), value in SQUASH.items():
                _write(group, key, value)
            _reconfigure()
            _effects(_flat(SQUASH))
            print("macos_look: Magic Lamp unavailable, minimize stays as Squash", file=sys.stderr)
        saved["minimize"] = minimize
        _save(state, saved)
        for (group, key), value in KRUNNER.items():
            _write(group, key, value, "krunnerrc", notify=True)
        # Without a running Plasma or an Orla top bar the clock is simply skipped.
        if _script("menu_bar_clock.py", "apply", allow_failure=True):
            print("macos_look: top bar clock left unchanged", file=sys.stderr)
        # Banners need the Orla Notifications package; without it KDE's popups stay.
        if (_script("macos_notifications.py", "install", allow_failure=True)
                or _script("macos_notifications.py", "apply", allow_failure=True)):
            print("macos_look: notifications left as KDE's", file=sys.stderr)
        if _script("menu_bar_tray.py", "apply", allow_failure=True):
            print("macos_look: tray left unchanged", file=sys.stderr)
        return 0
    if saved:
        previous = saved["previous"]
        for (group, key) in KWIN:
            _write(group, key, previous.get(f"{group}/{key}"))
        _reconfigure()
        _effects(previous)
        # Older states have no KRunner entry: that apply never touched krunnerrc.
        for name, value in (saved.get("krunner") or {}).items():
            group, key = name.split("/", 1)
            _write(group, key, value, "krunnerrc", notify=True)
        state.unlink()
    # Each part restores only what it changed; an already restored part is fine.
    _script("menu_bar_tray.py", "restore", allow_failure=True)
    _script("macos_notifications.py", "restore", allow_failure=True)
    _script("menu_bar_clock.py", "restore", allow_failure=True)
    _script("window_decoration.py", "restore", allow_failure=True)
    _script("plasma_theme.py", "restore", allow_failure=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
