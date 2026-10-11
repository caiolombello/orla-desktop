#!/usr/bin/env python3
"""Run the optional menu's mock tests without the desktop's display or buses."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", choices=("Fusion", "org.kde.desktop"), default="Fusion")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="orla-bar-tests-") as directory:
        private = Path(directory)
        for name in ("config", "data", "cache", "state", "runtime"):
            (private / name).mkdir(mode=0o700)
        env = os.environ.copy()
        for name in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_STARTER_BUS_ADDRESS", "DBUS_STARTER_BUS_TYPE"):
            env.pop(name, None)
        env.update(
            PYTHONPATH=str(root / "tests"),
            QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
            QT_QUICK_CONTROLS_STYLE=args.style, QT_QPA_PLATFORMTHEME="",
            DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(private / "absent-session"),
            DBUS_SYSTEM_BUS_ADDRESS="unix:path=" + str(private / "absent-system"),
            XDG_CONFIG_HOME=str(private / "config"), XDG_DATA_HOME=str(private / "data"),
            XDG_CACHE_HOME=str(private / "cache"), XDG_STATE_HOME=str(private / "state"),
            XDG_RUNTIME_DIR=str(private / "runtime"),
        )
        try:
            result = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "test_bar", "-v"],
                cwd=root, env=env, timeout=30,
            )
        except subprocess.TimeoutExpired:
            print("Optional menu mock tests exceeded 30 seconds.", file=sys.stderr)
            return 3
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
