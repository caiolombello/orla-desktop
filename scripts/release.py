#!/usr/bin/env python3
"""Create the public alpha bundle and checksums from an explicit source allowlist."""

from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import zipfile

import caiodock


# The optional menu is Source-only; its fixtures need bar/, which is not bundled.
# Design checks and the gallery compare the bar and launcher token copies too.
SOURCE_ONLY_TESTS = frozenset(("tests/test_bar.py", "tests/BarHarness.qml",
                               "tests/test_shared_control_center.py", "tests/SharedControlCenterBarHarness.qml",
                               "tests/test_design_system.py", "tests/design_gallery.py"))


def bundle(root: Path) -> tuple[Path, Path, Path]:
    package, version = caiodock.package_inputs(root)
    plasmoid = caiodock.build(root)
    output = root / "dist" / f"orla-dock-{version}.zip"
    sources = [root / name for name in (
        "LICENSE", "README.md", "README.pt-BR.md", "CONTRIBUTING.md",
        "SECURITY.md", "CHANGELOG.md", "ROADMAP.md", ".gitignore",
    )]
    for directory in (package, root / "scripts", root / "tests", root / "docs", root / "themes", root / "website", root / ".github"):
        sources.extend(path for path in directory.rglob("*")
                       if path.is_file() and not path.is_symlink()
                       and "__pycache__" not in path.parts
                       and path.suffix not in (".pyc", ".pyo")
                       and path.relative_to(root).as_posix() not in SOURCE_ONLY_TESTS)
    entries = [(path, path.relative_to(root).as_posix()) for path in sources]
    entries.append((plasmoid, plasmoid.name))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in sorted(entries, key=lambda entry: entry[1]):
            if path.is_symlink() or not path.is_file():
                raise caiodock.PackageError(f"release input must be a regular file: {path}")
            info = zipfile.ZipInfo(f"orla-dock-{version}/{name}", (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    checksums = root / "dist" / "SHA256SUMS"
    checksums.write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in (plasmoid, output)
    ), encoding="utf-8")
    return plasmoid, output, checksums


if __name__ == "__main__":
    for artifact in bundle(Path(__file__).resolve().parents[1]):
        print(artifact)
