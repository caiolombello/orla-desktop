"""Entry for the relocatable Workspace archive and its passive UI diagnosis."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# Managed generations stay immutable even when the caller omits Python's -B.
sys.dont_write_bytecode = True


def parser():
    def service(value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@:-]{0,127}\.service", value):
            raise argparse.ArgumentTypeError("select a literal current-user Plasma service name")
        return value
    result = argparse.ArgumentParser(prog="orla-workspace", description="Open a verified Orla Workspace bundle", allow_abbrev=False)
    action = result.add_mutually_exclusive_group(required=True)
    action.add_argument("--service", type=service, help="literal current-user Plasma service selected for composition")
    action.add_argument("--diagnose", action="store_true", help="check bundle and Qt UI without contacting Plasma")
    action.add_argument("--version", action="store_true", help="read bundle version and source commit")
    action.add_argument("--_probe-ui", action="store_true", help=argparse.SUPPRESS)
    return result


def _runtime():
    versions = {"python": ".".join(map(str, sys.version_info[:3]))}
    try:
        import PySide6
        from PySide6.QtCore import qVersion
    except ImportError:
        return {"status": "qt_runtime_missing", "versions": versions}
    versions.update(pyside=PySide6.__version__, qt=qVersion())
    def supported(value):
        match = re.match(r"^(\d+)\.(\d+)(?:\.|$)", value)
        return match is not None and tuple(map(int, match.groups())) >= (6, 11)
    if sys.version_info < (3, 10) or not all(supported(versions[key]) for key in ("pyside", "qt")):
        return {"status": "unsupported_runtime", "versions": versions}
    return {"status": "ready", "versions": versions}


def _probe_ui(root):
    runtime = _runtime()
    if runtime["status"] != "ready":
        return runtime
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from scripts.workspace_setup import WorkspaceController
    except ImportError:
        return {"status": "qt_runtime_missing", "versions": runtime["versions"]}
    app = QGuiApplication([])
    app.setQuitOnLastWindowClosed(False)
    # This controller is inert: the probe never constructs a NativeRuntime or
    # schedules a read. It checks the actual QML imports, not a copied view.
    controller = WorkspaceController(None, {}, [])
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(values))
    engine.rootContext().setContextProperty("workspaceController", controller)
    engine.setInitialProperties({"visible": False})
    engine.load(QUrl.fromLocalFile(str(root / "workspace/Workspace.qml")))
    app.processEvents()
    ready = len(engine.rootObjects()) == 1 and not warnings
    for window in engine.rootObjects():
        window.close()
    return {"status": "ready" if ready else "qml_load_failed", "versions": runtime["versions"]}


def diagnose(root, manifest):
    with tempfile.TemporaryDirectory(prefix="orla-workspace-check-") as directory:
        private = Path(directory)
        environment = os.environ.copy()
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "PYTHONPATH", "QML_IMPORT_PATH", "QML2_IMPORT_PATH",
                    "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QUICK_CONTROLS_CONF"):
            environment.pop(key, None)
        for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
            path = private / key.lower(); path.mkdir(mode=0o700)
            environment[key] = str(path)
        for key in ("DBUS_SESSION_BUS_ADDRESS", "DBUS_SYSTEM_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS"):
            environment[key] = "unix:path=" + str(private / "absent-bus")
        environment.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                           QT_QUICK_CONTROLS_STYLE="Fusion", QT_QPA_PLATFORMTHEME="", QML_DISABLE_DISK_CACHE="1")
        try:
            result = subprocess.run([sys.executable, "-I", "-B", str(root / "workspace/main.py"), "--_probe-ui"],
                                    cwd=private, env=environment, capture_output=True, text=True, timeout=20)
            if result.returncode or len(result.stdout) > 16384:
                probe = {"status": "qt_probe_failed"}
            else:
                probe = json.loads(result.stdout)
                if type(probe) is not dict or set(probe) != {"status", "versions"}:
                    probe = {"status": "qt_probe_failed"}
        except subprocess.TimeoutExpired:
            probe = {"status": "qt_probe_timeout"}
        except (OSError, ValueError):
            probe = {"status": "qt_probe_failed"}
    report = {"component": manifest["component"], "version": manifest["version"], "commit": manifest["commit"],
              "bundle": "verified", "runtime": probe, "nativeValidated": False, "serviceContacted": False}
    print(json.dumps(report, sort_keys=True))
    return 0 if probe["status"] == "ready" else 1


def main(argv=None):
    args = parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    # -I ignores cwd/PYTHONPATH. Only this bundle root supplies application code.
    sys.path.insert(0, str(root))
    try:
        from workspace import package
    except ImportError:
        print("orla-workspace: bundle verifier unavailable", file=sys.stderr)
        return 1
    try:
        manifest = package.verify_directory(root)
        if args.version:
            print(json.dumps({key: manifest[key] for key in ("component", "version", "commit")}, sort_keys=True))
            return 0
        if args._probe_ui:
            print(json.dumps(_probe_ui(root), sort_keys=True))
            return 0
        if args.diagnose:
            return diagnose(root, manifest)
        if _runtime()["status"] != "ready":
            print("orla-workspace: Qt for Python 6.11+ with Qt Quick is required", file=sys.stderr)
            return 1
        from scripts import workspace_setup
        from scripts.panel_layout import LayoutError
        try:
            return workspace_setup.launch(args.service)
        except (LayoutError, OSError):
            print("orla-workspace: startup failed; run --diagnose before trying again", file=sys.stderr)
            return 1
    except package.PackageError as exc:
        print("orla-workspace: " + str(exc), file=sys.stderr)
        return 1
    except ImportError:
        print("orla-workspace: Qt for Python 6.11+ with Qt Quick is required", file=sys.stderr)
        return 1
    except OSError:
        print("orla-workspace: could not access bundle or diagnostic workspace", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
