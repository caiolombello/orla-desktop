"""Optional Qt companion for the existing layout transactions.

Qt imports stay here so the ordinary CLI keeps working without PySide6.
The synchronous backend runs off the GUI thread and outlives Plasma restarts.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import signal
import sys

from PySide6.QtCore import QObject, Property, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

if __package__:
    from .panel_layout import LayoutError
else:
    from panel_layout import LayoutError


def _failure_diagnostics(exc):
    if not isinstance(exc, LayoutError):
        return {"code": "UNEXPECTED_FAILURE", "operation": "TRANSACTION", "returncode": None}
    # Facts are mutable. Reapply the canonical closed vocabulary and hash/exit
    # bounds, accepting only plain strings so no payload-bearing objects survive.
    facts = exc.facts if type(exc.facts) is dict else {}
    code, operation = facts.get("code"), facts.get("operation")
    hashes = {key: facts.get(key) for key in ("expectedSha256", "actualSha256")}
    return LayoutError("", code=code if type(code) is str else None,
                       operation=operation if type(operation) is str else None,
                       returncode=facts.get("returncode"),
                       hashes=hashes if all(type(value) is str for value in hashes.values()) else None).facts


class _Operation(QThread):
    def __init__(self, callback, parent):
        super().__init__(parent)
        self.callback = callback
        self.result = None
        self.failed = False
        self.failure_kind = "unknown"
        self.failure_diagnostics = {}

    def run(self):
        try:
            self.result = self.callback()
        except Exception as exc:
            # Reads have no transaction journal. Keep only resanitized facts;
            # exception text can contain paths, widget configuration or accounts.
            self.failed = True
            self.failure_diagnostics = _failure_diagnostics(exc)
            message = str(exc)
            if message == "panel composition requires Plasma 6.7.5":
                self.failure_kind = "compatibility"
            elif message.startswith("selected native widgets are unavailable: "):
                self.failure_kind = "widgets"
            elif message in ("reviewed composition state changed", "layout state changed while reading",
                             "layout configuration changed; original and current layouts retained"):
                self.failure_kind = "drift"
            elif message == "include the existing tray's panel in the reviewed replacement selection":
                self.failure_kind = "tray"
            elif message == "another layout transaction is active":
                self.failure_kind = "busy"


class WorkspaceController(QObject):
    changed = Signal()
    closeReady = Signal()

    def __init__(self, session, template, connectors, parent=None):
        super().__init__(parent)
        self.session = session
        self.template = copy.deepcopy(template)
        self._connectors = list(connectors)
        self._state = {"phase": "UNKNOWN"}
        self._review = {}
        self._job = None
        self._kind = ""
        self._problem = ""
        self._failure_diagnostics = {}
        self._closing = False
        self._close_signaled = False
        self._screens_changed = False

    state = Property("QVariantMap", lambda self: self._state, notify=changed)
    review = Property("QVariantMap", lambda self: self._review, notify=changed)
    connectors = Property("QStringList", lambda self: self._connectors, notify=changed)
    busy = Property(bool, lambda self: self._job is not None, notify=changed)
    stage = Property(str, lambda self: self._kind, notify=changed)
    problem = Property(str, lambda self: self._problem, notify=changed)
    failureDiagnostics = Property("QVariantMap", lambda self: copy.deepcopy(self._failure_diagnostics), notify=changed)
    closePending = Property(bool, lambda self: self._closing, notify=changed)

    def _start(self, kind, callback):
        if self.busy or self._closing:
            return False
        self._kind = kind
        self._problem = ""
        self._failure_diagnostics = {}
        self._review = {}
        self._screens_changed = False
        job = _Operation(callback, self)
        self._job = job
        job.finished.connect(self._finished)
        self.changed.emit()
        job.start()
        return True

    @Slot()
    def _finished(self):
        job = self._job
        # Join before publishing idle or destroying the owner (Qt thread-local
        # cleanup may continue after finished). No backend object is read sooner.
        job.wait()
        self._job = None
        if job.failed:
            self._failure_diagnostics = copy.deepcopy(job.failure_diagnostics)
            self._state = {"phase": "UNKNOWN"}
            messages = {
                "compatibility": self.tr("Esta composição exige Plasma 6.7.5. Seu layout foi mantido."),
                "widgets": self.tr("Faltam widgets para a barra. Instale o Menu Orla e os widgets KDE indicados na documentação de composição; depois atualize a leitura."),
                "drift": self.tr("O layout mudou desde a revisão. Os arquivos e backups foram mantidos. Atualize a leitura e revise novamente."),
                "tray": self.tr("Selecione também o painel que contém a bandeja deste monitor para evitar duas bandejas."),
                "busy": self.tr("Outra operação de layout está em andamento. Aguarde e atualize a leitura."),
            }
            self._problem = messages.get(job.failure_kind, self.tr("Não foi possível concluir a operação. Atualize a leitura para verificar o layout e a recuperação."))
        elif self._kind == "read":
            self._state = job.result
        elif self._kind == "review":
            self._review = job.result
        else:
            self._state = job.result
        if self._screens_changed:
            self.session.discard()
            self._review = {}
            self._state = {"phase": "UNKNOWN"}
            self._problem = self.tr("Os monitores mudaram. Atualize a leitura antes de continuar.")
        job.deleteLater()
        self.changed.emit()
        if self._closing:
            self._signal_close()

    @Slot(str, result=bool)
    def refresh(self, connector=""):
        return self._start("read", lambda: self.session.read(connector))

    @Slot(str, "QVariantList", result=bool)
    def prepareApply(self, connector, panel_ids):
        manifest = copy.deepcopy(self.template)
        manifest["screen"]["connector"] = connector
        manifest["replacePanelIds"] = list(panel_ids)
        manifest["reuseWidgetIds"] = {}
        return self._start("review", lambda: self.session.review_apply(manifest))

    @Slot(str, result=bool)
    def prepareOperation(self, action):
        if action not in ("disable", "restore", "recover"):
            return False
        return self._start("review", lambda: self.session.review_operation(action))

    @Slot(result=bool)
    def discard(self):
        if self.busy or self._closing:
            return False
        self.session.discard()
        self._failure_diagnostics = {}
        self._review = {}
        self.changed.emit()
        return True

    @Slot(result=bool)
    def confirm(self):
        if not self._review or self.busy or self._closing:
            return False
        token = self._review["token"]

        def execute():
            result = self.session.execute(token)
            try:
                return self.session.read(result["connector"])
            except Exception:
                return {"phase": result["phase"], "verificationUnavailable": True}

        return self._start("execute", execute)

    def set_connectors(self, connectors):
        if list(connectors) == self._connectors:
            return
        self._connectors = list(connectors)
        if self.busy:
            self._screens_changed = True
        else:
            self.session.discard()
            self._review = {}
            self._state = {"phase": "UNKNOWN"}
        self.changed.emit()

    def _signal_close(self):
        if not self._close_signaled:
            self._close_signaled = True
            self.closeReady.emit()

    @Slot(result=bool)
    def requestClose(self):
        # Latch before notifications: a result handler cannot start new work
        # while an older close request is waiting for the transaction to finish.
        self._closing = True
        self.changed.emit()
        if self.busy:
            return False
        self._signal_close()
        return True


def launch(service):
    if __package__:
        from . import panel_layout, workspace_layout
    else:
        import panel_layout
        import workspace_layout
    root = Path(__file__).resolve().parents[1]
    template = panel_layout.read_json(root / "layouts/mac-inspired-topbar.json")
    config = os.environ.get("XDG_CONFIG_HOME", "")
    config = Path(config) if config.startswith("/") else Path.home() / ".config"
    state = os.environ.get("XDG_STATE_HOME", "")
    state = Path(state) if state.startswith("/") else Path.home() / ".local/state"
    store = panel_layout.FileStore(config, state / "orla/layouts")
    session = workspace_layout.CompositionSession(panel_layout.NativeRuntime(service), store, template)
    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Orla — Composição")
    app.setQuitOnLastWindowClosed(False)

    def connectors():
        return sorted(set(screen.name() for screen in app.screens()))

    controller = WorkspaceController(session, template, connectors())
    controller.closeReady.connect(app.quit)
    app.screenAdded.connect(lambda _: controller.set_connectors(connectors()))
    app.screenRemoved.connect(lambda _: controller.set_connectors(connectors()))
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("workspaceController", controller)
    engine.load(QUrl.fromLocalFile(str(root / "workspace/Workspace.qml")))
    if not engine.rootObjects():
        return 1
    old_handlers = {}
    for number in (signal.SIGINT, signal.SIGTERM):
        old_handlers[number] = signal.signal(number, lambda *_: controller.requestClose())
    # Python handlers need regular interpreter dispatch while Qt owns the loop.
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(100)
    QTimer.singleShot(0, lambda: controller.refresh(""))
    try:
        return app.exec()
    finally:
        heartbeat.stop()
        for number, handler in old_handlers.items():
            signal.signal(number, handler)
