"""Prove lazy D-Bus activation and QML consumption using private synthetic data."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


def inside():
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtDBus import QDBusConnection, QDBusMessage
    from PySide6.QtTest import QTest
    from scripts import caiodock

    root = Path(__file__).resolve().parents[1]
    data = Path(os.environ["XDG_DATA_HOME"])
    archive = caiodock.build(root, Path(os.environ["HOME"]) / "artifacts")
    caiodock.install(archive, data)
    history = Path(os.environ["HOME"]) / ".local/share/codexbar-linux/history.jsonl"
    history.parent.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    history.write_text(json.dumps({"timestamp": now, "providers": [{"provider": "codex", "updated_at": now,
        "primary": {"used_percent": 42, "window_minutes": 300}}]}) + "\n")
    app = QGuiApplication([])
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(value.toString() for value in values))
    engine.load(QUrl.fromLocalFile(str(root / "tests/IntegrationHarness.qml")))
    assert engine.rootObjects(), warnings
    integration = engine.rootObjects()[0]
    try:
        deadline = time.monotonic() + 8
        while integration.property("loading") and time.monotonic() < deadline:
            QTest.qWait(30)
        assert not integration.property("loading"), "D-Bus call timed out"
        assert not integration.property("error"), integration.property("error")
        assert integration.property("quotaSummary") == "codex · 42% usado", integration.property("quotaSummary")
        assert warnings == [], warnings
        print(json.dumps({"success": True, "activation": "private D-Bus service", "qmlSummary": integration.property("quotaSummary"), "warnings": warnings}))
    finally:
        # This bus was created by the outer test; stop only its bridge process.
        message = QDBusMessage.createMethodCall("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetConnectionUnixProcessID")
        message.setArguments(["org.caiodock.Integrations"])
        reply = QDBusConnection.sessionBus().call(message)
        if reply.type() == QDBusMessage.ReplyMessage and reply.arguments():
            os.kill(int(reply.arguments()[0]), signal.SIGTERM)
        engine.deleteLater()
        app.processEvents()


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if "--inside" in sys.argv:
        inside()
        return
    with tempfile.TemporaryDirectory(prefix="caiodock-dbus-") as temporary:
        private = Path(temporary)
        env = os.environ.copy()
        env.update(HOME=str(private), XDG_DATA_HOME=str(private / "data"), XDG_STATE_HOME=str(private / "state"),
                   XDG_CONFIG_HOME=str(private / "config"), XDG_CACHE_HOME=str(private / "cache"),
                   QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
        for key in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            Path(env[key]).mkdir()
        result = subprocess.run(["dbus-run-session", "--", sys.executable, str(Path(__file__).resolve()), "--inside"], env=env, text=True, capture_output=True, timeout=20)
        print(result.stdout, end="")
        if result.returncode:
            print(result.stderr, file=sys.stderr, end="")
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
