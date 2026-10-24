#!/usr/bin/env python3
"""Build, install and switch the optional Orla Plasma theme.

The theme only replaces the frames that shape the macOS look: translucent
panel, rounded glass for dialogs and notifications, tooltips and transparent
popup headings. KWin blurs and saturates whatever sits behind them. Every other
Plasma image falls back to the default theme, and colors follow the system
color scheme, so light and dark both work.

  plasma_theme.py build OUTDIR      write the theme directory (deterministic)
  plasma_theme.py install           build into ~/.local/share/plasma/desktoptheme/orla
  plasma_theme.py apply             remember the current theme, then switch to Orla
  plasma_theme.py restore           switch back to the remembered theme
  plasma_theme.py status            print the active theme and what restore would use
"""
from __future__ import annotations

import gzip
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

THEME_ID = "orla"
VERSION = "0.1.0"

# Corner radius, content margin and fill opacity per frame. Translucent
# variants are used when KWin can blur; the base ones stay nearly opaque.
FRAMES = {
    "dialogs/background": {"radius": 16, "margin": 10, "fill": 0.94, "translucent": 0.74, "rim": 0.16, "shadow": 22},
    "widgets/tooltip": {"radius": 8, "margin": 6, "fill": 0.95, "translucent": 0.8, "rim": 0.16, "shadow": 14},
    # The bar keeps Breeze's 4 px margins, which its layout tests assume. Like
    # the macOS menu bar it has no shadow and only a faint edge.
    "widgets/panel-background": {"radius": 16, "margin": 4, "fill": 0.92, "translucent": 0.46, "rim": 0.08, "shadow": 0},
}
# The edge tile length; Plasma stretches it, so its size only affects rounding.
TILE = 4
# The bottom panel ("south" prefix) frames the Orla dock: an invisible frame
# whose blur mask is the dock's glass slab, `band` inside the frame. The dock
# measures the frame and draws its tint over that mask; the band must equal
# Style.dock.systemGlassBandX/Y, which the tests check.
DOCK_FRAME = {"radius": 21, "margin": 4, "band": (10, 12)}
# Markers Orla looks for before relying on the theme's glass.
POPUP_MARKER = "hint-orla-glass"
DOCK_MARKER = "south-hint-orla-dock"
SHADOW_LAYERS = 10
SHADOW_ALPHA = 0.06
CORNERS = ("topleft", "topright", "bottomleft", "bottomright")
EDGES = ("top", "bottom", "left", "right")

PLASMARC = """[ContrastEffect]
enabled=true
contrast=0.3
intensity=1.0
saturation=1.8

[BlurBehindEffect]
enabled=true

[AdaptiveTransparency]
enabled=true
"""

STYLE = """<style type="text/css" id="current-color-scheme">
.ColorScheme-Text { color:#232629; }
.ColorScheme-Background { color:#eff0f1; }
</style>"""


def _n(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _bounds(element: str, x: float, y: float, w: float, h: float) -> str:
    # An invisible rect pins each element's bounds to its exact tile.
    return f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" style="fill:none;stroke:none"/>'


def _corner_path(cx: float, cy: float, r: float, sx: int, sy: int) -> str:
    """Quarter disc of radius r centered at (cx, cy), opening away by (sx, sy)."""
    return (f"M {_n(cx + sx * r)},{_n(cy)} A {_n(r)},{_n(r)} 0 0 {1 if sx * sy > 0 else 0} "
            f"{_n(cx)},{_n(cy + sy * r)} L {_n(cx)},{_n(cy)} Z")


def _frame(prefix: str, ox: float, oy: float, radius: int, fill: float | None, rim: float,
           mask: bool = False, band: tuple[int, int] = (0, 0)) -> list[str]:
    """Nine tiles of a rounded rectangle whose top-left corner sits at (ox, oy).

    `band` keeps a transparent strip (x, y) between the tile edges and the
    glass, so a frame can be drawn smaller than the window it belongs to.
    """
    r, t = radius, TILE
    bx, by = band
    cw, ch = bx + r, by + r
    out = []
    fill_style = ("fill:#000000" if mask else
                  f"fill:currentColor;fill-opacity:{_n(fill)}" if fill is not None else "fill:none")
    # Filled, not stroked: a stroke would widen each tile's bounds by half a pixel.
    rim_style = f"fill:currentColor;fill-opacity:{_n(rim)}"
    cls_fill = "" if mask else ' class="ColorScheme-Background"'
    cls_rim = ' class="ColorScheme-Text"'
    tiles = {
        "topleft": (0, 0, cw, ch), "top": (cw, 0, t, ch), "topright": (cw + t, 0, cw, ch),
        "left": (0, ch, cw, t), "center": (cw, ch, t, t), "right": (cw + t, ch, cw, t),
        "bottomleft": (0, ch + t, cw, ch), "bottom": (cw, ch + t, t, ch), "bottomright": (cw + t, ch + t, cw, ch),
    }
    for name, (tx, ty, tw, th) in tiles.items():
        x, y = ox + tx, oy + ty
        parts = [_bounds(name, x, y, tw, th)]
        if name in CORNERS:
            sx = -1 if "left" in name else 1
            sy = -1 if name.startswith("top") else 1
            # The arc center is the tile corner that touches the frame's center.
            cx = x + (tw if sx < 0 else 0)
            cy = y + (th if sy < 0 else 0)
            parts.append(f'<path{cls_fill} style="{fill_style}" d="{_corner_path(cx, cy, r, sx, sy)}"/>')
            if not mask and rim > 0:
                sweep = 1 if sx * sy > 0 else 0
                inner = r - 1
                ring = (f"M {_n(cx + sx * r)},{_n(cy)} A {_n(r)},{_n(r)} 0 0 {sweep} {_n(cx)},{_n(cy + sy * r)} "
                        f"L {_n(cx)},{_n(cy + sy * inner)} A {_n(inner)},{_n(inner)} 0 0 {1 - sweep} "
                        f"{_n(cx + sx * inner)},{_n(cy)} Z")
                parts.append(f'<path{cls_rim} style="{rim_style}" d="{ring}"/>')
        else:
            # The glass part of an edge tile: the side next to the center.
            glass = {"top": (x, y + by, tw, r), "bottom": (x, y, tw, r), "left": (x + bx, y, r, th),
                     "right": (x, y, r, th), "center": (x, y, tw, th)}[name]
            parts.append(f'<rect{cls_fill} style="{fill_style}" x="{_n(glass[0])}" y="{_n(glass[1])}" '
                         f'width="{_n(glass[2])}" height="{_n(glass[3])}"/>')
            if not mask and rim > 0 and name != "center":
                gx, gy, gw, gh = glass
                line = {"top": (gx, gy, gw, 1), "bottom": (gx, gy + gh - 1, gw, 1),
                        "left": (gx, gy, 1, gh), "right": (gx + gw - 1, gy, 1, gh)}[name]
                parts.append(f'<rect{cls_rim} style="{rim_style}" x="{_n(line[0])}" y="{_n(line[1])}" '
                             f'width="{_n(line[2])}" height="{_n(line[3])}"/>')
        element = f"{prefix}{name}"
        out.append(f'<g id="{element}">' + "".join(parts) + "</g>")
    return out


def _shadow(ox: float, oy: float, radius: int, spread: int) -> list[str]:
    """Layered shadow around a rounded rectangle; nothing is drawn under the glass."""
    r, s, t = radius, spread, TILE
    out = []
    step = s / SHADOW_LAYERS
    style = f"fill:#000000;fill-opacity:{_n(SHADOW_ALPHA)};fill-rule:evenodd"
    # Corner tiles reach under the window by the radius, so the rounded corner's
    # outside gets shadow while the glass itself does not.
    corner = r + s
    layout = {
        "topleft": (0, 0, corner, corner), "top": (corner, 0, t, s), "topright": (corner + t, 0, corner, corner),
        "left": (0, corner, s, t), "right": (corner + t + corner - s, corner, s, t),
        "bottomleft": (0, corner + t, corner, corner), "bottom": (corner, corner + t + corner - s, t, s),
        "bottomright": (corner + t, corner + t, corner, corner),
    }
    for name, (tx, ty, tw, th) in layout.items():
        x, y = ox + tx, oy + ty
        parts = [_bounds(name, x, y, tw, th)]
        for layer in range(1, SHADOW_LAYERS + 1):
            d = step * layer
            if name in CORNERS:
                sx = -1 if "left" in name else 1
                sy = -1 if name.startswith("top") else 1
                # The arc center is the tile corner that reaches under the window.
                cx = x + (tw if sx < 0 else 0)
                cy = y + (th if sy < 0 else 0)
                outer, inner = r + d, r
                sweep = 1 if sx * sy > 0 else 0
                back = 0 if sweep else 1
                path = (f"M {_n(cx + sx * outer)},{_n(cy)} A {_n(outer)},{_n(outer)} 0 0 {sweep} "
                        f"{_n(cx)},{_n(cy + sy * outer)} L {_n(cx)},{_n(cy + sy * inner)} "
                        f"A {_n(inner)},{_n(inner)} 0 0 {back} {_n(cx + sx * inner)},{_n(cy)} Z")
                parts.append(f'<path style="{style}" d="{path}"/>')
            else:
                if name == "top":
                    rect = (x, y + th - d, tw, d)
                elif name == "bottom":
                    rect = (x, y, tw, d)
                elif name == "left":
                    rect = (x + tw - d, y, d, th)
                else:
                    rect = (x, y, d, th)
                parts.append(f'<rect style="{style}" x="{_n(rect[0])}" y="{_n(rect[1])}" '
                             f'width="{_n(rect[2])}" height="{_n(rect[3])}"/>')
        out.append(f'<g id="shadow-{name}">' + "".join(parts) + "</g>")
    # How far the shadow reaches beyond the window on each side.
    hx = ox + 2 * corner + t + 8
    for index, side in enumerate(("top", "bottom", "left", "right")):
        w, h = (2, s) if side in ("top", "bottom") else (s, 2)
        out.append(f'<rect id="shadow-hint-{side}-margin" x="{_n(hx + index * (s + 4))}" y="{_n(oy)}" '
                   f'width="{_n(w)}" height="{_n(h)}" style="fill:none;stroke:none"/>')
    return out


def _hints(ox: float, oy: float, margin: int, prefix: str = "") -> list[str]:
    out = []
    for index, side in enumerate(("top", "bottom", "left", "right")):
        w, h = (2, margin) if side in ("top", "bottom") else (margin, 2)
        out.append(f'<rect id="{prefix}hint-{side}-margin" x="{_n(ox + index * (margin + 4))}" y="{_n(oy)}" '
                   f'width="{_n(w)}" height="{_n(h)}" style="fill:none;stroke:none"/>')
    return out


def _document(body: list[str], width: float, height: float) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(width)}" height="{_n(height)}" '
            f'viewBox="0 0 {_n(width)} {_n(height)}">' + STYLE + "".join(body) + "</svg>\n")


def _marker(element: str, x: float, y: float) -> str:
    return f'<rect id="{element}" x="{_n(x)}" y="{_n(y)}" width="2" height="2" style="fill:none;stroke:none"/>'


def frame_svg(name: str, spec: dict, translucent: bool) -> str:
    r, s = spec["radius"], spec["shadow"]
    size = 2 * r + TILE
    fill = spec["translucent"] if translucent else spec["fill"]
    body = _frame("", 0, 0, r, fill, spec["rim"])
    body += _frame("mask-", size + 8, 0, r, None, 0, mask=True)
    body += _hints(0, size + 8, spec["margin"])
    height = size + 8 + spec["margin"] + 8
    width = 2 * size + 16
    if name == "dialogs/background":
        body.append(_marker(POPUP_MARKER, 2 * size + 16, 0))
        width += 4
    if s:
        body += _shadow(0, height, r, s)
        width = max(width, 2 * (r + s) + TILE + 8 + 4 * (s + 4))
        height += 2 * (r + s) + TILE
    if name == "widgets/panel-background":
        dock = DOCK_FRAME
        dr, (bx, by) = dock["radius"], dock["band"]
        dsize = (2 * (bx + dr) + TILE, 2 * (by + dr) + TILE)
        # Invisible glass: only its mask matters, for KWin's blur.
        body += _frame("south-", 0, height, dr, 0, 0, band=dock["band"])
        body += _frame("mask-south-", dsize[0] + 8, height, dr, None, 0, mask=True, band=dock["band"])
        body += _hints(0, height + dsize[1] + 8, dock["margin"], prefix="south-")
        body.append(_marker(DOCK_MARKER, 2 * dsize[0] + 16, height))
        width = max(width, 2 * dsize[0] + 20)
        height += dsize[1] + 8 + dock["margin"] + 8
    return _document(body, width, height)


def heading_svg() -> str:
    """Popup headings without a band: only a hairline separates them, as in macOS."""
    body = []
    for row, prefix in enumerate(("header-", "footer-")):
        oy = row * (2 * 4 + TILE + 8)
        tiles = {
            "topleft": (0, 0, 4, 4), "top": (4, 0, TILE, 4), "topright": (4 + TILE, 0, 4, 4),
            "left": (0, 4, 4, TILE), "center": (4, 4, TILE, TILE), "right": (4 + TILE, 4, 4, TILE),
            "bottomleft": (0, 4 + TILE, 4, 4), "bottom": (4, 4 + TILE, TILE, 4), "bottomright": (4 + TILE, 4 + TILE, 4, 4),
        }
        line = "bottom" if prefix == "header-" else "top"
        for name, (x, y, w, h) in tiles.items():
            parts = [_bounds(name, x, oy + y, w, h)]
            if name == line:
                ly = oy + y + (h - 1 if line == "bottom" else 0)
                parts.append(f'<rect class="ColorScheme-Text" style="fill:currentColor;fill-opacity:0.12" '
                             f'x="{_n(x)}" y="{_n(ly)}" width="{_n(w)}" height="1"/>')
            body.append(f'<g id="{prefix}{name}">' + "".join(parts) + "</g>")
    body += _hints(40, 0, 4)
    body.append('<rect id="hint-stretch-borders" x="80" y="0" width="2" height="2" style="fill:none;stroke:none"/>')
    return _document(body, 90, 2 * (2 * 4 + TILE + 8))


def metadata() -> dict:
    return {
        "KPlugin": {
            "Authors": [{"Name": "Orla Desktop contributors"}],
            "Description": "Vidro translúcido do Orla para painéis, popups e dicas; segue o esquema de cores do sistema.",
            "EnabledByDefault": True,
            "Id": THEME_ID,
            "License": "MIT",
            "Name": "Orla",
            "Version": VERSION,
            "Website": "https://github.com/caiolombello/orla-desktop",
        },
        "X-Plasma-API": "5.0",
    }


def _svgz(text: str) -> bytes:
    buffer = io.BytesIO()
    # mtime=0 keeps the archive byte-identical between builds.
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, filename="") as handle:
        handle.write(text.encode("utf-8"))
    return buffer.getvalue()


def build(output: Path) -> Path:
    theme = output / THEME_ID
    if theme.exists():
        shutil.rmtree(theme)
    theme.mkdir(parents=True)
    (theme / "metadata.json").write_text(json.dumps(metadata(), indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    (theme / "plasmarc").write_text(PLASMARC, encoding="utf-8")
    for name, spec in FRAMES.items():
        for translucent, base in ((False, theme), (True, theme / "translucent")):
            path = base / f"{name}.svgz"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_svgz(frame_svg(name, spec, translucent)))
    heading = theme / "widgets" / "plasmoidheading.svgz"
    heading.write_bytes(_svgz(heading_svg()))
    return theme


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")


def _state_file() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return base / "orla" / "plasma-theme.json"


def current_theme() -> str:
    result = subprocess.run(["kreadconfig6", "--file", "plasmarc", "--group", "Theme", "--key", "name"],
                            capture_output=True, text=True, timeout=10)
    return result.stdout.strip() or "default"


def _switch(name: str) -> None:
    subprocess.run(["plasma-apply-desktoptheme", name], check=True, timeout=30)


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("build", "install", "apply", "restore", "status"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    command = argv[1]
    if command == "build":
        if len(argv) != 3:
            print("usage: plasma_theme.py build OUTDIR", file=sys.stderr)
            return 2
        print(build(Path(argv[2])))
        return 0
    if command == "install":
        print(build(_data_home() / "plasma" / "desktoptheme"))
        return 0
    state = _state_file()
    if command == "status":
        saved = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
        print(json.dumps({"active": current_theme(), "restoreTo": saved.get("previous")}))
        return 0
    if command == "apply":
        if not (_data_home() / "plasma" / "desktoptheme" / THEME_ID / "metadata.json").exists():
            print("Install the theme first: plasma_theme.py install", file=sys.stderr)
            return 1
        active = current_theme()
        if active != THEME_ID:
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps({"previous": active}) + "\n", encoding="utf-8")
        _switch(THEME_ID)
        return 0
    # Without a saved state Orla never switched the theme: leave it alone.
    if not state.exists():
        print("Nothing to restore.", file=sys.stderr)
        return 1
    previous = json.loads(state.read_text(encoding="utf-8")).get("previous") or "default"
    _switch(previous)
    state.unlink()
    print(previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
