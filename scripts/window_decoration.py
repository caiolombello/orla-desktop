#!/usr/bin/env python3
"""Install and switch the optional Orla window decoration (macOS-style title bar).

  window_decoration.py install    install or update the KWin decoration package
  window_decoration.py apply      remember the current decoration, then use Orla
                                  with close, minimize and zoom on the left
  window_decoration.py restore    put the remembered decoration settings back
  window_decoration.py status     print the active decoration and the saved state

Only the user's kwinrc keys below change; `restore` rewrites the saved values or
removes keys that were not set, so the look-and-feel defaults apply again.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "themes" / "kwin-decoration"
# KWin caches a decoration's QML by path for its whole session, so each content
# version installs under its own id: an update then loads without logging out.
PLUGIN_PREFIX = "kwin4_decoration_qml_orla"
GROUP = "org.kde.kdecoration2"
KEYS = ("library", "theme", "ButtonsOnLeft", "ButtonsOnRight")
LIBRARY = "org.kde.kwin.aurorae"
# Close, minimize, maximize on the left; nothing on the right, as in macOS.
BUTTONS = {"ButtonsOnLeft": "XIA", "ButtonsOnRight": ""}


def plugin_id(package: Path = PACKAGE) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in package.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(package)).encode() + b"\0" + path.read_bytes() + b"\0")
    return f"{PLUGIN_PREFIX}_{digest.hexdigest()[:10]}"


def orla_values() -> dict:
    return {"library": LIBRARY, "theme": plugin_id(), **BUTTONS}


def _state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "orla" / "window-decoration.json"


def _config_file() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kwinrc"


def user_values() -> dict:
    """The keys as set in the user's own kwinrc; None when absent there."""
    values = {key: None for key in KEYS}
    path = _config_file()
    if not path.exists():
        return values
    group = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            group = stripped[1:-1]
        elif group == GROUP and "=" in stripped:
            key, value = stripped.split("=", 1)
            if key in values:
                values[key] = value
    return values


def _write(key: str, value: str | None) -> None:
    command = ["kwriteconfig6", "--file", "kwinrc", "--group", GROUP, "--key", key]
    command += ["--delete"] if value is None else [value]
    subprocess.run(command, check=True, timeout=10)


def _reconfigure() -> None:
    subprocess.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"],
                   check=True, timeout=15, stdout=subprocess.DEVNULL)


def _decorations() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "kwin" / "decorations"


def installed() -> bool:
    return (_decorations() / plugin_id() / "metadata.json").exists()


def is_orla(values: dict) -> bool:
    return values.get("library") == LIBRARY and str(values.get("theme") or "").startswith(PLUGIN_PREFIX)


def install() -> Path:
    # A plain copy: Aurorae loads contents/ui/main.qml itself, while
    # kpackagetool6 would demand a code/main.qml that KWin never reads.
    ident = plugin_id()
    root = _decorations()
    target = root / ident
    staging = root / (ident + ".new")
    if staging.exists():
        shutil.rmtree(staging)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PACKAGE, staging)
    metadata = json.loads((staging / "metadata.json").read_text(encoding="utf-8"))
    metadata["KPlugin"]["Id"] = ident
    (staging / "metadata.json").write_text(json.dumps(metadata, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)
    # Older Orla versions go away once the new one is in place.
    for old in root.glob(PLUGIN_PREFIX + "*"):
        if old != target and old.is_dir():
            shutil.rmtree(old)
    return target


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("install", "apply", "restore", "status"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    command = argv[1]
    state = _state_file()
    if command == "install":
        print(install())
        if is_orla(user_values()):
            _write("theme", plugin_id())
            _reconfigure()
        return 0
    if command == "status":
        saved = json.loads(state.read_text(encoding="utf-8")) if state.exists() else None
        print(json.dumps({"active": user_values(), "saved": saved, "installed": installed(), "id": plugin_id()}))
        return 0
    if command == "apply":
        if not installed():
            print("Install the decoration first: window_decoration.py install", file=sys.stderr)
            return 1
        current = user_values()
        # Keep the first saved state: applying twice must not forget the original.
        if not state.exists() and not is_orla(current):
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({"previous": current}) + "\n", encoding="utf-8")
        for key, value in orla_values().items():
            _write(key, value)
        _reconfigure()
        return 0
    if not state.exists():
        print("Nothing to restore.", file=sys.stderr)
        return 1
    previous = json.loads(state.read_text(encoding="utf-8"))["previous"]
    for key in KEYS:
        _write(key, previous.get(key))
    _reconfigure()
    state.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
