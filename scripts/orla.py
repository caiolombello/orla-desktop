#!/usr/bin/env python3
"""Orla Dock command-line entry point."""

if __package__:
    from .caiodock import main
else:
    from caiodock import main


if __name__ == "__main__":
    raise SystemExit(main())
