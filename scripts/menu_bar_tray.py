#!/usr/bin/env python3
"""Keep the top bar's tray as sparse as the macOS menu bar, and undo it.

  menu_bar_tray.py apply     move the tray items that the Orla Control Center
                             already covers (brightness) or that macOS does not
                             show (clipboard) into the tray's overflow arrow
  menu_bar_tray.py restore   the tray item lists saved before the first apply
  menu_bar_tray.py status    which of those items are hidden in each tray

Items the user pinned as always shown stay where they are; hidden items
still work from the arrow and their shortcuts (clipboard: Meta+V). Changes go
through Plasma's scripting API, like macos_notifications.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from macos_notifications import KEYS, SwapError, _items, evaluate  # noqa: E402

TIDY = ("org.kde.plasma.brightness", "org.kde.plasma.clipboard")


def tidied(values: dict) -> dict:
    """The same lists with the tidy items hidden, unless the user pinned them as shown."""
    result = {key: list(values[key]) for key in KEYS}
    for item in TIDY:
        if item in values["extraItems"] and item not in values["shownItems"]:
            result["hiddenItems"] = list(dict.fromkeys(result["hiddenItems"] + [item]))
    return result


def _state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "orla" / "menu-bar-tray.json"


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
    current = evaluate()
    targets = {tray: values for tray, values in current.items() if tidied(values) != values}
    if not targets:
        return current
    saved = _saved() or {}
    # Keep the first values: applying twice must not forget the original.
    previous = {**{tray: current[tray] for tray in targets}, **saved}
    if previous != saved:
        _save(previous)
    after = evaluate({tray: tidied(values) for tray, values in targets.items()})
    if any(tidied(after[tray]) != after[tray] for tray in targets):
        raise SwapError("the tray did not take the hidden items")
    return after


def restore() -> dict:
    saved = _saved()
    if saved is None:
        raise SwapError("nothing saved to restore")
    current = evaluate()
    # Unhide only what apply hid; keep any other change made since then.
    writes = {}
    for tray, values in saved.items():
        if tray in current:
            added = [item for item in TIDY if item not in values["hiddenItems"]]
            hidden = [item for item in current[tray]["hiddenItems"] if item not in added]
            writes[tray] = dict(current[tray], hiddenItems=hidden)
    after = evaluate(writes) if writes else current
    if any(after[tray]["hiddenItems"] != values["hiddenItems"] for tray, values in writes.items()):
        raise SwapError("the tray did not take its saved items back")
    _state_file().unlink()
    return after


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("apply", "restore", "status"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        if argv[1] == "status":
            current = evaluate()
            hidden = {tray: [item for item in TIDY if item in values["hiddenItems"]] for tray, values in current.items()}
            print(json.dumps({"hidden": hidden, "saved": _saved() is not None}, sort_keys=True))
            return 0
        result = apply() if argv[1] == "apply" else restore()
    except SwapError as exc:
        print(f"menu_bar_tray: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"trays": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
