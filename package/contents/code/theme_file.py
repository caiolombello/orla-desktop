#!/usr/bin/env python3
"""Read one explicitly selected local theme URL; no Qt or service dependency."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote_to_bytes

if __package__:
    from .theme_format import FORMAT_VERSION, MAX_BYTES, ThemeError, load_theme
else:
    # Isolated Python (-I) omits the script directory: use only our installed sibling.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from theme_format import FORMAT_VERSION, MAX_BYTES, ThemeError, load_theme

MAX_URL_BYTES = 16384
_URI_PATH = re.compile(r"(?:[A-Za-z0-9._~!$&'()*+,;=:@/-]|%[0-9A-Fa-f]{2})+")


def _url_error() -> ThemeError:
    return ThemeError("$", "file", "Cannot read this regular theme file.")


def load_theme_url(local_url: str) -> dict:
    """Decode one bounded file:/// URL once, then use the canonical regular-file loader."""
    if type(local_url) is not str or len(local_url) > MAX_URL_BYTES:
        raise _url_error()
    try:
        if len(local_url.encode("utf-8", errors="strict")) > MAX_URL_BYTES:
            raise _url_error()
    except UnicodeEncodeError:
        raise _url_error() from None
    if not local_url.startswith("file:///") or _URI_PATH.fullmatch(local_url[7:]) is None:
        raise _url_error()
    try:
        decoded = unquote_to_bytes(local_url[7:]).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise _url_error() from None
    if not decoded.startswith("/") or decoded.startswith("//") or any(
            ord(character) < 32 or 127 <= ord(character) <= 159 for character in decoded):
        raise _url_error()
    return load_theme(Path(decoded))


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    try:
        if len(arguments) != 1:
            raise _url_error()
        theme = load_theme_url(arguments[0])
        response = {"formatVersion": FORMAT_VERSION, "valid": True, "theme": theme}
        code = 0
    except ThemeError as error:
        response = {"formatVersion": FORMAT_VERSION, "valid": False, "errors": error.errors}
        code = 2 if len(arguments) != 1 or (type(arguments[0]) is str and arguments[0].startswith("-")) else 1
    output = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if len(output.encode("utf-8")) > MAX_BYTES:
        error = ThemeError("$", "size", f"Use at most {MAX_BYTES} bytes.")
        output = json.dumps({"formatVersion": FORMAT_VERSION, "valid": False, "errors": error.errors},
                            sort_keys=True, separators=(",", ":")) + "\n"
        code = 1
    sys.stdout.write(output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
