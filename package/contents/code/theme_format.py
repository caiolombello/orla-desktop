#!/usr/bin/env python3
"""Validate experimental, data-only Orla themes. No code is loaded or executed."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import sys


FORMAT_VERSION = "0.1-experimental"
MAX_BYTES = 65536
MAX_DEPTH = 4
ID_PATTERN = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+"
VERSION_PATTERN = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
TEXT_CHARACTERS = r"A-Za-z0-9À-ÖØ-öø-ÿ.,_+\-"
TEXT_PATTERN = rf"[{TEXT_CHARACTERS}](?:[{TEXT_CHARACTERS} ]*[{TEXT_CHARACTERS}])?"
COLORS = ("foreground", "muted", "accent", "surface", "border")
RANGES = {"radius": (0, 32), "spacing": (0, 16), "opacity": (0.4, 1), "iconSize": (24, 64)}
ROOT_FIELDS = ("formatVersion", "id", "name", "author", "license", "version", "tokens")
TOKEN_FIELDS = (*COLORS, *RANGES, "reducedMotion")


class ThemeError(ValueError):
    """Validation failure with safe, structured field/code/message entries."""

    def __init__(self, field: str, code: str, message: str):
        self.errors = [{"field": field, "code": code, "message": message}]
        super().__init__(f"{field}: {message} ({code})")


def _object(value: object, field: str, fields: tuple[str, ...]) -> dict:
    if type(value) is not dict:
        raise ThemeError(field, "type", "Expected an object.")
    if any(type(key) is not str or key not in fields for key in value):
        raise ThemeError(field, "unknown_key", "Remove unrecognized fields.")
    for key in fields:
        if key not in value:
            raise ThemeError(f"{field}/{key}", "required", "This field is required.")
    return value


def _text(value: object, field: str, pattern: str, maximum: int) -> str:
    if type(value) is not str:
        raise ThemeError(field, "type", "Expected a string.")
    if not 1 <= len(value) <= maximum:
        raise ThemeError(field, "length", f"Use 1 to {maximum} characters.")
    if re.fullmatch(pattern, value) is None:
        raise ThemeError(field, "format", "Use the documented plain-text format.")
    return value


def validate_theme(value: object) -> dict:
    """Return a new, canonical theme dictionary or raise ThemeError."""
    source = _object(value, "$", ROOT_FIELDS)
    result = {}
    if source["formatVersion"] != FORMAT_VERSION:
        raise ThemeError("$/formatVersion", "format_version", f"Use {FORMAT_VERSION}.")
    result["formatVersion"] = FORMAT_VERSION
    for key, pattern, maximum in (
        ("id", ID_PATTERN, 120), ("name", TEXT_PATTERN, 120),
        ("author", TEXT_PATTERN, 120), ("license", TEXT_PATTERN, 80),
        ("version", VERSION_PATTERN, 32),
    ):
        result[key] = _text(source[key], f"$/{key}", pattern, maximum)
    tokens = _object(source["tokens"], "$/tokens", TOKEN_FIELDS)
    result["tokens"] = {}
    for key in COLORS:
        result["tokens"][key] = _text(tokens[key], f"$/tokens/{key}", r"#[0-9A-Fa-f]{6}", 7).lower()
    for key, (minimum, maximum) in RANGES.items():
        number = tokens[key]
        if type(number) not in (int, float):
            raise ThemeError(f"$/tokens/{key}", "type", "Expected a number, not a boolean.")
        if type(number) is float and not math.isfinite(number):
            raise ThemeError(f"$/tokens/{key}", "nonfinite", "Use a finite number.")
        if not minimum <= number <= maximum:
            raise ThemeError(f"$/tokens/{key}", "range", f"Use a number from {minimum} to {maximum}.")
        result["tokens"][key] = int(number) if number == int(number) else number
    if type(tokens["reducedMotion"]) is not bool:
        raise ThemeError("$/tokens/reducedMotion", "type", "Expected a boolean.")
    result["tokens"]["reducedMotion"] = tokens["reducedMotion"]
    return result


def parse_theme(data: bytes) -> dict:
    """Decode bounded strict UTF-8 JSON bytes and validate without execution."""
    if type(data) is not bytes:
        raise ThemeError("$", "type", "Expected UTF-8 bytes.")
    if len(data) > MAX_BYTES:
        raise ThemeError("$", "size", f"Use at most {MAX_BYTES} bytes.")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ThemeError("$", "utf8", "Encode the file as strict UTF-8.") from None
    # Bound nesting before json.loads, which otherwise recurses on hostile input.
    depth, quoted, escaped = 0, False, False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise ThemeError("$", "depth", f"Use at most {MAX_DEPTH} container levels.")
        elif character in "]}":
            depth -= 1

    class Pairs(list):
        pass

    def finite_number(number):
        result = float(number)
        if not math.isfinite(result):
            raise ThemeError("$", "nonfinite", "Use finite JSON numbers.")
        return result

    def unique_objects(value, field):
        if isinstance(value, Pairs):
            result = {}
            for key, child in value:
                child_field = f"{field}/{key}" if key in (*ROOT_FIELDS, *TOKEN_FIELDS) else field
                if key in result:
                    raise ThemeError(child_field, "duplicate_key", "Remove duplicate object keys.")
                result[key] = unique_objects(child, child_field)
            return result
        if type(value) is list:
            return [unique_objects(child, f"{field}/{index}") for index, child in enumerate(value)]
        return value

    try:
        decoded = json.loads(text, object_pairs_hook=Pairs,
                             parse_float=finite_number, parse_constant=finite_number)
    except ThemeError:
        raise
    except (ValueError, RecursionError):
        raise ThemeError("$", "json", "Use a single valid JSON document without a BOM.") from None
    return validate_theme(unique_objects(decoded, "$"))


def load_theme(path: Path) -> dict:
    """Read at most 64 KiB from an explicit regular file, rejecting symlinks."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except (OSError, ValueError):
        raise ThemeError("$", "file", "Cannot read this regular theme file.") from None
    try:
        with os.fdopen(descriptor, "rb") as stream:
            information = os.fstat(stream.fileno())
            if not stat.S_ISREG(information.st_mode):
                raise ThemeError("$", "file", "Use a regular file, not a link or device.")
            if information.st_size > MAX_BYTES:
                raise ThemeError("$", "size", f"Use at most {MAX_BYTES} bytes.")
            data = stream.read(MAX_BYTES + 1)
    except OSError:
        raise ThemeError("$", "file", "Cannot read this regular theme file.") from None
    return parse_theme(data)


def canonical_bytes(value: object) -> bytes:
    """Validated UTF-8 JSON: sorted keys, compact separators, one final newline."""
    theme = validate_theme(value)
    return (json.dumps(theme, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def pack_theme(source: Path, output_dir: Path) -> Path:
    """Atomically publish a complete JSON artifact without replacing files."""
    theme = load_theme(source)
    data = canonical_bytes(theme)
    output_dir = Path(output_dir)
    name = f"{theme['id']}-{theme['version']}.orla-theme.json"
    temporary = f".orla-theme-{secrets.token_hex(16)}.tmp"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        directory = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, ValueError):
        raise ThemeError("$", "output", "Cannot create the artifact in this directory.") from None
    owns_temporary = False
    try:
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o644, dir_fd=directory)
            owns_temporary = True
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
            # A same-directory hardlink publishes only the closed, complete file.
            # link() cannot replace any existing destination, including a symlink.
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False)
        finally:
            if owns_temporary:
                os.unlink(temporary, dir_fd=directory)
    except FileExistsError:
        raise ThemeError("$", "exists", "Output already exists; choose another directory.") from None
    except OSError:
        raise ThemeError("$", "output", "Cannot create the artifact in this directory.") from None
    finally:
        os.close(directory)
    return output_dir / name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Experimental data-only Orla theme format 0.1. No installation.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate", help="read and validate one theme file")
    validate.add_argument("file", type=Path)
    validate.add_argument("--json", action="store_true", help="emit structured validation results")
    pack = subcommands.add_parser("pack", help="create canonical .orla-theme.json without overwriting")
    pack.add_argument("file", type=Path)
    pack.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    machine_output = arguments.command == "validate" and arguments.json
    try:
        if arguments.command == "validate":
            theme = load_theme(arguments.file)
            if machine_output:
                print(json.dumps({"valid": True, "formatVersion": FORMAT_VERSION, "theme": theme}, ensure_ascii=False))
            else:
                print(f"Valid experimental theme: {theme['id']} ({theme['version']})")
        else:
            print(pack_theme(arguments.file, arguments.output))
    except ThemeError as error:
        if machine_output:
            print(json.dumps({"valid": False, "formatVersion": FORMAT_VERSION, "errors": error.errors}))
        else:
            print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
