#!/usr/bin/env python3
"""Show the date beside the time in the Orla top bar, as the macOS menu bar does.

  menu_bar_clock.py apply     "sáb. 25 out. 11:20" in the clock of each top panel
                              that holds Orla Menu (org.orla.bar)
  menu_bar_clock.py restore   the clock settings saved before the first apply
  menu_bar_clock.py status    the clocks found and what restore would bring back

Changes go through Plasma's scripting API, so the clock updates at once and no
restart is needed. Other clocks (the desktop, other panels) are left alone.
Plasma scripting cannot delete a key: restore writes back the values read
before the first apply, which for keys that were not set are KDE's defaults.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys

# Keys of org.kde.plasma.digitalclock (Plasma 6.7.5 main.xml, group Appearance).
MACOS = {"showDate": True, "dateFormat": "custom", "customDateFormat": "ddd d MMM", "dateDisplayFormat": 1}
DEFAULTS = {"showDate": True, "dateFormat": "shortDate", "customDateFormat": "ddd d", "dateDisplayFormat": 0}
DATE_FORMATS = ("shortDate", "longDate", "isoDate", "custom")

SCRIPT = """
var input = %s;
var KEYS = ["showDate", "dateFormat", "customDateFormat", "dateDisplayFormat"];
var DEFAULTS = %s;
var clocks = [];
panels().forEach(function (panel) {
    if (panel.location !== "top") return;
    var widgets = panel.widgets();
    if (!widgets.some(function (w) { return w.type === "org.orla.bar"; })) return;
    widgets.forEach(function (w) {
        if (w.type !== "org.kde.plasma.digitalclock") return;
        w.currentConfigGroup = ["Appearance"];
        var wanted = input.write ? input.write[String(w.id)] : null;
        if (wanted) {
            KEYS.forEach(function (key) { w.writeConfig(key, wanted[key]); });
            if (typeof w.reloadConfig === "function") w.reloadConfig();
        }
        var values = {};
        KEYS.forEach(function (key) { values[key] = w.readConfig(key, DEFAULTS[key]); });
        clocks.push({id: w.id, panel: panel.id, values: values});
    });
});
print(JSON.stringify({clocks: clocks}));
"""


class ClockError(Exception):
    pass


def render(write: dict | None = None) -> str:
    return SCRIPT % (json.dumps({"write": write}), json.dumps(DEFAULTS))


def _values(raw: object) -> dict:
    """Plasma returns typed values for keys in the clock's schema; accept their text form too."""
    if not isinstance(raw, dict) or set(raw) != set(MACOS):
        raise ClockError("unexpected clock settings")
    show, kind, custom, display = raw["showDate"], raw["dateFormat"], raw["customDateFormat"], raw["dateDisplayFormat"]
    if show in ("true", "false"):
        show = show == "true"
    if isinstance(display, str) and re.fullmatch(r"[0-2]", display):
        display = int(display)
    if (type(show) is not bool or kind not in DATE_FORMATS or not isinstance(custom, str)
            or not 0 < len(custom) <= 64 or not custom.isprintable()
            or type(display) is not int or display not in (0, 1, 2)):
        raise ClockError("unexpected clock settings")
    return {"showDate": show, "dateFormat": kind, "customDateFormat": custom, "dateDisplayFormat": display}


def parse_reply(output: str) -> dict:
    """gdbus prints a one-string tuple; the string is the script's JSON."""
    try:
        result = ast.literal_eval(output.strip())
        if not isinstance(result, tuple) or len(result) != 1 or not isinstance(result[0], str):
            raise ValueError
        reply = json.loads(result[0])
    except (ValueError, SyntaxError) as exc:
        raise ClockError("invalid Plasma script reply") from exc
    clocks = reply.get("clocks") if isinstance(reply, dict) else None
    if not isinstance(clocks, list) or len(clocks) > 16:
        raise ClockError("invalid Plasma script reply")
    result = {}
    for clock in clocks:
        if (not isinstance(clock, dict) or set(clock) != {"id", "panel", "values"}
                or type(clock["id"]) is not int or type(clock["panel"]) is not int or str(clock["id"]) in result):
            raise ClockError("invalid Plasma script reply")
        result[str(clock["id"])] = _values(clock["values"])
    return result


def evaluate(write: dict | None = None) -> dict:
    command = ["gdbus", "call", "--session", "--timeout", "8", "--dest", "org.kde.plasmashell",
               "--object-path", "/PlasmaShell", "--method", "org.kde.PlasmaShell.evaluateScript", render(write)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClockError("Plasma is not answering") from exc
    if result.returncode:
        raise ClockError("Plasma is not answering")
    return parse_reply(result.stdout)


def _state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "orla" / "menu-bar-clock.json"


def _saved() -> dict | None:
    path = _state_file()
    if not path.exists():
        return None
    previous = json.loads(path.read_text(encoding="utf-8"))["previous"]
    return {clock: _values(values) for clock, values in previous.items()}


def _save(previous: dict) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"previous": previous}, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def apply() -> dict:
    current = evaluate()
    saved = _saved() or {}
    # Keep the first values: applying twice must not forget the original.
    previous = {**current, **saved}
    if current and previous != saved:
        _save(previous)
    if not current:
        return {}
    after = evaluate({clock: MACOS for clock in current})
    if any(after.get(clock) != MACOS for clock in current):
        raise ClockError("the clock did not take the new format")
    return after


def restore() -> dict:
    saved = _saved()
    if saved is None:
        raise ClockError("nothing saved to restore")
    current = evaluate()
    present = {clock: values for clock, values in saved.items() if clock in current}
    after = evaluate(present) if present else current
    if any(after.get(clock) != values for clock, values in present.items()):
        raise ClockError("the clock did not take the saved format back")
    _state_file().unlink()
    return after


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("apply", "restore", "status"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        if argv[1] == "status":
            current = evaluate()
            print(json.dumps({"clocks": current, "applied": bool(current) and all(v == MACOS for v in current.values()),
                              "saved": _saved()}, sort_keys=True))
            return 0
        result = apply() if argv[1] == "apply" else restore()
    except ClockError as exc:
        print(f"menu_bar_clock: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"clocks": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
