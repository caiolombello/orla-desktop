#!/usr/bin/env python3
"""Swap KDE's notification popups for Orla's macOS-style banners, and back.

  macos_notifications.py install   install or update Orla Notifications from this checkout
  macos_notifications.py apply     in each system tray that shows KDE's notifications
                                   applet, put Orla Notifications in its place
  macos_notifications.py restore   the tray item lists saved before the first apply
  macos_notifications.py status    the trays found and which presenter each one uses

Only one presenter may show popups, so this replaces the tray item instead of
adding one. Plasma's notification service, history, actions and Do Not Disturb
stay KDE's. Changes go through Plasma's scripting API; the tray loads and
unloads the applets at once. Orla Notifications must be installed first
(`install`, or kpackagetool6 -t Plasma/Applet -i notifications).

Updating or removing a tray applet's package makes the tray forget it. So
`install` puts Orla back after updating it, and `apply` repairs a tray that
lost it; before removing the package, run `restore` to get KDE's applet back.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

KDE = "org.kde.plasma.notifications"
ORLA = "org.orla.notifications"
KEYS = ("extraItems", "hiddenItems", "shownItems", "knownItems")

SCRIPT = """
var input = %s;
var KEYS = ["extraItems", "hiddenItems", "shownItems", "knownItems"];
var trays = [];
panels().forEach(function (panel) {
    panel.widgets().forEach(function (w) {
        if (w.type !== "org.kde.plasma.systemtray") return;
        w.currentConfigGroup = ["General"];
        var wanted = input.write ? input.write[String(w.id)] : null;
        if (wanted) {
            KEYS.forEach(function (key) { w.writeConfig(key, wanted[key]); });
            if (typeof w.reloadConfig === "function") w.reloadConfig();
        }
        var values = {};
        KEYS.forEach(function (key) {
            var value = w.readConfig(key, []);
            values[key] = Array.isArray(value) ? value : value ? String(value).split(",") : [];
        });
        trays.push({id: w.id, panel: panel.id, values: values});
    });
});
print(JSON.stringify({trays: trays}));
"""


class SwapError(Exception):
    pass


def render(write: dict | None = None) -> str:
    return SCRIPT % json.dumps({"write": write})


def _items(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 128:
        raise SwapError("unexpected tray settings")
    result = []
    for item in value:
        if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", item):
            raise SwapError("unexpected tray settings")
        result.append(item)
    return result


def parse_reply(output: str) -> dict:
    try:
        result = ast.literal_eval(output.strip())
        if not isinstance(result, tuple) or len(result) != 1 or not isinstance(result[0], str):
            raise ValueError
        reply = json.loads(result[0])
    except (ValueError, SyntaxError) as exc:
        raise SwapError("invalid Plasma script reply") from exc
    trays = reply.get("trays") if isinstance(reply, dict) else None
    if not isinstance(trays, list) or len(trays) > 16:
        raise SwapError("invalid Plasma script reply")
    result = {}
    for tray in trays:
        if (not isinstance(tray, dict) or set(tray) != {"id", "panel", "values"} or type(tray["id"]) is not int
                or type(tray["panel"]) is not int or str(tray["id"]) in result
                or not isinstance(tray["values"], dict) or set(tray["values"]) != set(KEYS)):
            raise SwapError("invalid Plasma script reply")
        result[str(tray["id"])] = {key: _items(tray["values"][key]) for key in KEYS}
    return result


def evaluate(write: dict | None = None) -> dict:
    command = ["gdbus", "call", "--session", "--timeout", "8", "--dest", "org.kde.plasmashell",
               "--object-path", "/PlasmaShell", "--method", "org.kde.PlasmaShell.evaluateScript", render(write)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SwapError("Plasma is not answering") from exc
    if result.returncode:
        raise SwapError("Plasma is not answering")
    return parse_reply(result.stdout)


def repaired(values: dict, previous: dict) -> dict:
    """A tray that forgot Orla (its package was updated): add it back like the swap did."""
    result = {key: list(values[key]) for key in KEYS}
    result["extraItems"] = list(dict.fromkeys(result["extraItems"] + [ORLA]))
    result["knownItems"] = list(dict.fromkeys(result["knownItems"] + [ORLA]))
    for key in ("hiddenItems", "shownItems"):
        if KDE in previous[key]:
            result[key] = list(dict.fromkeys(result[key] + [ORLA]))
    return result


def swapped(values: dict, old: str, new: str) -> dict:
    """The same lists with `new` where `old` was; `old` stays known, so the tray keeps it off."""
    result = {}
    for key in ("extraItems", "hiddenItems", "shownItems"):
        items = [new if item == old else item for item in values[key]]
        result[key] = list(dict.fromkeys(items))
    result["knownItems"] = list(dict.fromkeys(values["knownItems"] + [new]))
    return result


def installed() -> bool:
    homes = [Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")]
    homes += [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
    return any((home / "plasma/plasmoids" / ORLA / "metadata.json").is_file() for home in homes)


def install() -> None:
    package = Path(__file__).resolve().parents[1] / "notifications"
    action = "-u" if installed() else "-i"
    try:
        result = subprocess.run(["kpackagetool6", "-t", "Plasma/Applet", action, str(package)],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SwapError("kpackagetool6 is not available") from exc
    if result.returncode or not installed():
        raise SwapError("Orla Notifications could not be installed")
    # The tray forgets an updated applet when the package signal arrives; let
    # it settle, then, if Orla was in use, put it back.
    if _saved() is not None:
        time.sleep(1.5)
        apply()


def _state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "orla" / "macos-notifications.json"


def _saved() -> dict | None:
    path = _state_file()
    if not path.exists():
        return None
    previous = json.loads(path.read_text(encoding="utf-8"))["previous"]
    return {tray: {key: _items(values[key]) for key in KEYS} for tray, values in previous.items()}


def _save(previous: dict) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"previous": previous}, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def apply() -> dict:
    if not installed():
        raise SwapError("Orla Notifications is not installed")
    current = evaluate()
    saved = _saved() or {}
    targets = {tray: values for tray, values in current.items() if KDE in values["extraItems"]}
    lost = {tray: values for tray, values in current.items()
            if tray in saved and tray not in targets and ORLA not in values["extraItems"]}
    if not targets and not lost:
        return current
    # Keep the first values: applying twice must not forget the original.
    previous = {**{tray: current[tray] for tray in targets}, **saved}
    if previous != saved:
        _save(previous)
    writes = {tray: swapped(values, KDE, ORLA) for tray, values in targets.items()}
    writes.update({tray: repaired(values, previous[tray]) for tray, values in lost.items()})
    after = evaluate(writes)
    if any(KDE in after[tray]["extraItems"] or ORLA not in after[tray]["extraItems"] for tray in writes):
        raise SwapError("the tray did not take Orla Notifications")
    return after


def restore() -> dict:
    saved = _saved()
    if saved is None:
        raise SwapError("nothing saved to restore")
    current = evaluate()
    present = {tray: values for tray, values in saved.items() if tray in current}
    after = evaluate(present) if present else current
    if any(after[tray] != values for tray, values in present.items()):
        raise SwapError("the tray did not take its saved items back")
    _state_file().unlink()
    return after


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("install", "apply", "restore", "status"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        if argv[1] == "install":
            install()
            print(json.dumps({"installed": True}))
            return 0
        if argv[1] == "status":
            current = evaluate()
            # None means no presenter at all: run `apply` (repair) or `restore`.
            presenters = {tray: (ORLA if ORLA in values["extraItems"] else KDE if KDE in values["extraItems"] else None)
                          for tray, values in current.items()}
            print(json.dumps({"presenters": presenters, "installed": installed(), "saved": _saved() is not None},
                             sort_keys=True))
            return 0
        result = apply() if argv[1] == "apply" else restore()
    except SwapError as exc:
        print(f"macos_notifications: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"trays": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
