"""Owned synthetic Wayland window; no desktop Exec is launched."""
import json
import os
from pathlib import Path
import signal
import sys
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow

assert len(sys.argv)==2 and sys.argv[1] in ("A","B")
app=QGuiApplication([])
QGuiApplication.setDesktopFileName("org.orla.Model"+sys.argv[1])
window=QQuickWindow();window.setTitle(sys.argv[1]);window.resize(240,160)
def close(*_):
    window.close();app.quit()
signal.signal(signal.SIGTERM,close)
signal.signal(signal.SIGINT,close)
pulse=QTimer();pulse.timeout.connect(lambda:None);pulse.start(100)
QTimer.singleShot(30000,close)
def readiness():
    value={"platformName":app.platformName(),"visible":window.isVisible(),"exposed":window.isExposed(),"desktopFile":app.desktopFileName()}
    path=Path(os.environ["XDG_RUNTIME_DIR"]).parent/("Model"+sys.argv[1]+".ready.json")
    with path.open("x") as stream:json.dump(value,stream)
QTimer.singleShot(1000,readiness)
window.show()
try:sys.exit(app.exec())
finally:window.close()
