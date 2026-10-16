#!/usr/bin/env python3
"""Compatibility CLI/API for the canonical, packaged data-only theme format."""
import importlib.util as _importlib
from pathlib import Path as _Path

# A namespace import could select an unrelated regular package named "package".
_spec = _importlib.spec_from_file_location("_orla_theme_format",
    _Path(__file__).resolve().parents[1] / "package/contents/code/theme_format.py")
_format = _importlib.module_from_spec(_spec)
_spec.loader.exec_module(_format)

FORMAT_VERSION = _format.FORMAT_VERSION
MAX_BYTES = _format.MAX_BYTES
MAX_DEPTH = _format.MAX_DEPTH
ID_PATTERN = _format.ID_PATTERN
VERSION_PATTERN = _format.VERSION_PATTERN
TEXT_CHARACTERS = _format.TEXT_CHARACTERS
TEXT_PATTERN = _format.TEXT_PATTERN
COLORS = _format.COLORS
RANGES = _format.RANGES
ROOT_FIELDS = _format.ROOT_FIELDS
TOKEN_FIELDS = _format.TOKEN_FIELDS
ThemeError = _format.ThemeError
validate_theme = _format.validate_theme
parse_theme = _format.parse_theme
load_theme = _format.load_theme
canonical_bytes = _format.canonical_bytes
pack_theme = _format.pack_theme
main = _format.main

if __name__ == "__main__":
    raise SystemExit(main())
