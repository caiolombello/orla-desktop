#!/usr/bin/env python3
"""Keep Orla's visual system consistent: token copies, style lint, contrast and gallery.

    python3 scripts/design.py sync     # copy the canonical tokens to bar/ and launcher/
    python3 scripts/design.py check    # fail on drift, hardcoded style values or low contrast
    python3 scripts/design.py gallery  # render every surface to PNGs for visual review

The rules are documented in docs/DESIGN_SYSTEM.md.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = Path("package/contents/code/Style.js")
COPIES = (Path("bar/contents/code/Style.js"), Path("launcher/Style.js"))
LINTED_GLOBS = ("package/contents/ui/*.qml", "bar/contents/ui/*.qml", "launcher/*.qml", "workspace/*.qml")
# Persisted user tokens and the token file itself are the only places for raw colors.
JS_COLOR_ALLOWLIST = (CANONICAL, *COPIES, Path("package/contents/code/Appearance.js"))
EXEMPT = "design-exempt:"

RULES = (
    ("hex-color", re.compile(r"[\"']#[0-9A-Fa-f]{3,8}[\"']"),
     "Use a Style.js role (Style.scheme(...).text, dock tokens) instead of a hex color."),
    ("named-color", re.compile(r"[\"'](?:white|black|red|green|blue|gray|grey|yellow|orange|pink|purple)[\"']"),
     "Use a Style.js role instead of a named color."),
    ("rgba", re.compile(r"\bQt\.(?:rgba|hsla|hsva)\s*\("),
     "Use Style.alpha(role, opacity) so translucent colors derive from a token."),
    ("pixel-size", re.compile(r"\bpixelSize\s*:\s*\d"),
     "Use Style.type.<role>; body copy keeps the system font."),
    ("radius", re.compile(r"\bradius\s*:\s*[1-9]\d*\s*(?:[;}]|$)"),
     "Use Style.radius.<role> or a value derived from a dock token."),
)
MINIMUM_TEXT_CONTRAST = 4.5
# Live icon glyphs and numbers are large and bold (WCAG large text / graphics).
MINIMUM_ICON_CONTRAST = 3.0


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sync(root: Path = ROOT) -> list[Path]:
    source = root / CANONICAL
    written = []
    for copy in COPIES:
        target = root / copy
        if not target.exists() or target.read_bytes() != source.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written.append(target)
    return written


def copy_errors(root: Path = ROOT) -> list[str]:
    source = (root / CANONICAL).read_bytes()
    return [f"{copy}: differs from {CANONICAL}; run `python3 scripts/design.py sync`."
            for copy in COPIES if not (root / copy).exists() or (root / copy).read_bytes() != source]


def lint_text(name: str, text: str, javascript: bool = False) -> list[str]:
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        if EXEMPT in line:
            continue
        code = line.split("//", 1)[0] if "//" in line and "://" not in line else line
        for rule, pattern, advice in RULES:
            if javascript and rule != "hex-color":
                continue
            if pattern.search(code):
                errors.append(f"{name}:{number}: [{rule}] {advice}")
    return errors


def lint_errors(root: Path = ROOT) -> list[str]:
    errors = []
    for pattern in LINTED_GLOBS:
        for path in sorted(root.glob(pattern)):
            errors.extend(lint_text(path.relative_to(root).as_posix(), path.read_text(encoding="utf-8")))
    allowed = {root / path for path in JS_COLOR_ALLOWLIST}
    for path in sorted((root / "package/contents/code").glob("*.js")) + sorted((root / "bar/contents/code").glob("*.js")):
        if path not in allowed:
            errors.extend(lint_text(path.relative_to(root).as_posix(), path.read_text(encoding="utf-8"), True))
    return errors


def _load(engine, root: Path, path: Path, names: tuple[str, ...]):
    """Evaluate a `.pragma library` file in its own scope, as QML does, and export names."""
    source = (root / path).read_text(encoding="utf-8").replace(".pragma library", "")
    exports = ", ".join(f"{name}: {name}" for name in names)
    result = engine.evaluate(f"(function() {{\n{source}\nreturn {{{exports}}};\n}})()")
    if result.isError():
        raise RuntimeError(f"{path}: {result.toString()}")
    return result


def _libraries(root: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQml import QJSEngine
    QCoreApplication.instance() or QCoreApplication([])
    engine = QJSEngine()
    style = _load(engine, root, CANONICAL, ("schemes", "dockThemes", "iconTiles", "contrast"))
    appearance = _load(engine, root, Path("package/contents/code/Appearance.js"), ("legacy",))
    return engine, style, appearance


def contrast_errors(root: Path = ROOT) -> list[str]:
    engine, style, appearance = _libraries(root)
    contrast = style.property("contrast")
    schemes = style.property("schemes").toVariant()
    errors = []

    def ratio(first: str, second: str) -> float:
        return contrast.call([first, second]).toNumber()

    for name, roles in schemes.items():
        for background in ("canvas", "surface", "raised", "sunken"):
            for role in ("text", "textMuted", "accent", "warning", "danger"):
                value = ratio(roles[role], roles[background])
                if value < MINIMUM_TEXT_CONTRAST:
                    errors.append(f"Style.schemes.{name}.{role} on {background}: {value:.2f}:1 < 4.5:1")
        value = ratio(roles["onAccent"], roles["accent"])
        if value < MINIMUM_TEXT_CONTRAST:
            errors.append(f"Style.schemes.{name}.onAccent on accent: {value:.2f}:1 < 4.5:1")
    for name, tile in style.property("iconTiles").toVariant().items():
        for stop in ("top", "bottom"):
            value = ratio(tile["ink"], tile[stop])
            if value < MINIMUM_ICON_CONTRAST:
                errors.append(f"Style.iconTiles.{name}.ink on {stop}: {value:.2f}:1 < 3:1")
    legacy = appearance.property("legacy")
    for name, theme in style.property("dockThemes").toVariant().items():
        for role in ("foreground", "muted"):
            value = ratio(theme[role], theme["surface"])
            if value < MINIMUM_TEXT_CONTRAST:
                errors.append(f"Style.dockThemes.{name}.{role} on surface: {value:.2f}:1 < 4.5:1")
        saved = legacy.call([engine.toScriptValue({"iconSize": 42, "animations": True}), name]).toVariant()["tokens"]
        for role in ("foreground", "muted", "accent", "surface", "border"):
            if saved[role].lower() != theme[role].lower():
                errors.append(f"Style.dockThemes.{name}.{role} {theme[role]} != Appearance.legacy {saved[role]}")
        if abs(saved["opacity"] - theme["opacity"]) > 1e-9:
            errors.append(f"Style.dockThemes.{name}.opacity differs from Appearance.legacy")
    return errors


def check(root: Path = ROOT) -> list[str]:
    return copy_errors(root) + lint_errors(root) + contrast_errors(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync", help="copy the canonical Style.js to the bar and launcher")
    commands.add_parser("check", help="verify copies, lint QML style literals and token contrast")
    gallery = commands.add_parser("gallery", help="render dock, popups, bar and launcher to PNG files")
    gallery.add_argument("--output", type=Path, default=ROOT / ".runtime/design-gallery")
    gallery.add_argument("--style", choices=("org.kde.desktop", "Fusion"), default="org.kde.desktop")
    args = parser.parse_args(argv)
    if args.command == "sync":
        for path in sync():
            print(f"updated {_relative(path)}")
        return 0
    if args.command == "check":
        errors = check()
        for error in errors:
            print(error, file=sys.stderr)
        print("design check: " + ("FAILED" if errors else "ok") + f" ({len(errors)} issue(s))")
        return 1 if errors else 0
    environment = os.environ.copy()
    environment.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE=args.style)
    return subprocess.run([sys.executable, "-B", str(ROOT / "tests/design_gallery.py"), str(args.output)],
                          cwd=ROOT, env=environment).returncode


if __name__ == "__main__":
    raise SystemExit(main())
