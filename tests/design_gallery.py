#!/usr/bin/env python3
"""Render Orla surfaces with synthetic data so people and agents can review visuals.

Run through `python3 scripts/design.py gallery [--output DIR]`. Every capture uses
owned fixtures: no real apps, accounts, providers or personal data are read.
Each system scheme renders in its own process with a private XDG_CONFIG_HOME
holding Breeze Dark or Breeze Light, so popups pick their Orla scheme exactly as
they would on that desktop. Writes one PNG per surface plus `index.png`.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(TESTS))
MARGIN = 12
POPUPS = (
    ("settings", "settings.openAt(settingsButton)"),
    ("control-center", "controlCenterPopup.openAt(settingsButton)"),
    ("pomodoro", "pomodoroPopup.openAt(settingsButton)"),
    ("calendar", "calendarPopup.openAt(settingsButton)"),
    ("battery", "batteryPopup.openAt(settingsButton)"),
    ("music", "musicPopup.openAt(settingsButton)"),
    ("pin-app", "addDialog.openAt(settingsButton)"),
)
POPUP_IDS = ("settings", "addDialog", "calendarPopup", "integrationPopup", "controlCenterPopup",
             "pomodoroPopup", "musicPopup", "batteryPopup", "nativeTaskMenu")


class Gallery:
    def __init__(self, output: Path):
        self.output = output
        self.output.mkdir(parents=True, exist_ok=True)
        self.captures: list[tuple[str, Path]] = []
        self.warnings: list[str] = []

    def engine(self) -> QQmlApplicationEngine:
        engine = QQmlApplicationEngine()
        engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        return engine

    def save(self, name: str, window: QQuickWindow, rect: QRectF | None = None) -> None:
        QTest.qWait(300)
        image = window.grabWindow()
        if rect is not None:
            ratio = image.devicePixelRatio()
            bounds = rect.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)
            image = image.copy(QRect(int(max(0, bounds.x()) * ratio), int(max(0, bounds.y()) * ratio),
                                     int(bounds.width() * ratio), int(bounds.height() * ratio)))
        path = self.output / f"{name}.png"
        image.save(str(path))
        self.captures.append((name, path))

    @staticmethod
    def scene_rect(item: QQuickItem) -> QRectF:
        origin = item.mapToScene(QPointF(0, 0))
        return QRectF(origin.x(), origin.y(), item.width(), item.height())

    def dock(self, host: str) -> None:
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "QmlHarness.qml")))
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        config = window.findChild(QObject, "configuration")
        context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))

        def evaluate(source: str):
            expression = QQmlExpression(context, dock, source)
            value, _ = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(f"{source}: {expression.error().toString()}")
            return value

        window.setProperty("width", 1100)
        window.setProperty("height", 1000)
        QTest.qWaitForWindowExposed(window, 3000)
        QTest.qWait(500)
        evaluate("root.anchors.centerIn = undefined; root.x = 40; root.y = 24")
        evaluate("for (const id of [" + ", ".join(POPUP_IDS) + "]) id.popupType = 0")
        for key in ("showSystemBattery", "showControlCenter"):
            config.setProperty(key, True)
        if host == "dark":
            for theme in ("glass", "midnight", "paper"):
                config.setProperty("theme", theme)
                QTest.qWait(150)
                self.save(f"dock-{theme}", window, self.scene_rect(dock))
        config.setProperty("theme", "glass")
        for name, source in POPUPS:
            evaluate("closeContext(); settings.close()")
            QTest.qWait(60)
            evaluate(source)
            popup = next(popup for popup in (evaluate(identifier) for identifier in POPUP_IDS)
                         if popup.property("visible"))
            self.save(f"popup-{host}-{name}", window, self.scene_rect(popup))
        evaluate("closeContext(); settings.close()")
        window.close()
        engine.deleteLater()

    def bar(self, host: str) -> None:
        from test_bar import FixtureApplication, FixtureSession
        session, application = FixtureSession(), FixtureApplication()
        engine = self.engine()
        engine.rootContext().setContextProperty("fixtureSession", session)
        engine.rootContext().setContextProperty("fixtureApplication", application)
        engine.rootContext().setContextProperty("fixtureControlCenter", None)
        engine.load(QUrl.fromLocalFile(str(TESTS / "BarHarness.qml")))
        window = engine.rootObjects()[0]
        bar = window.findChild(QQuickItem, "barUnderTest")
        menu = window.findChild(QObject, "orlaMenu")
        context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "orlaMenuButton"))
        # Draw the bar on its panel color and keep the menu inside the capture.
        QQmlExpression(context, bar, "anchors.fill = undefined; width = 420; height = implicitHeight;"
                                     "Window.window.color = palette.window; Window.window.width = 440;"
                                     "Window.window.height = 440; menu.popupType = 0;"
                                     # The panel uses a native tooltip; keep the Item one out of captures.
                                     "menuTooltipBackend = ({hideImmediately: function() {}})").evaluate()
        QTest.mouseMove(window, QPointF(430, 430).toPoint())
        self.save(f"bar-{host}", window, QRectF(0, 0, 420, bar.height()))
        QQmlExpression(context, bar, "menu.open()").evaluate()
        QTest.qWait(200)
        self.save(f"bar-{host}-menu", window, QRectF(0, 0, menu.property("width") + 8,
                                                     bar.height() + menu.property("height") + 8))
        window.close()
        engine.deleteLater()

    def launcher(self) -> None:
        engine = self.engine()
        stubs = QQmlComponent(engine)
        stubs.setData(LAUNCHER_STUBS.encode(), QUrl.fromLocalFile(str(TESTS / "LauncherGalleryStubs.qml")))
        holder = stubs.create()
        if holder is None:
            raise RuntimeError(stubs.errorString())
        for name in ("launcher", "aiProviders", "aiText", "steamProvider", "windowSession"):
            engine.rootContext().setContextProperty(name, holder.property(name))
        engine.load(QUrl.fromLocalFile(str(ROOT / "launcher/Launcher.qml")))
        window = engine.rootObjects()[0]
        launcher = holder.property("launcher")
        self.save("launcher-results", window)
        launcher.setProperty("rows", [])
        launcher.setProperty("status", "idle")
        launcher.setProperty("selectedIndex", -1)
        self.save("launcher-empty", window)
        window.setProperty("height", 640)
        window.setProperty("activePanel", "ai")
        self.save("launcher-ai", window)
        window.setProperty("activePanel", "steam")
        self.save("launcher-steam", window)
        window.close()
        engine.deleteLater()
        holder.deleteLater()

    def contact_sheet(self) -> Path:
        width, padding, label = 1600, 24, 28
        images = [(name, QImage(str(path))) for name, path in self.captures]
        rows, row, x, row_height = [], [], padding, 0
        for name, image in images:
            scale = min(1.0, (width - 2 * padding) / max(1, image.width()))
            size = (int(image.width() * scale), int(image.height() * scale))
            if row and x + size[0] > width - padding:
                rows.append((row, row_height))
                row, x, row_height = [], padding, 0
            row.append((name, image, size, x))
            x += size[0] + padding
            row_height = max(row_height, size[1] + label)
        if row:
            rows.append((row, row_height))
        height = padding + sum(height + padding for _, height in rows)
        sheet = QImage(width, height, QImage.Format_ARGB32)
        sheet.fill(QColor("#0b1118"))
        painter = QPainter(sheet)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        font = QFont()
        font.setPixelSize(13)
        painter.setFont(font)
        y = padding
        for entries, height in rows:
            for name, image, size, left in entries:
                painter.setPen(QColor("#a5b4bf"))
                painter.drawText(left, y + 16, name)
                painter.drawImage(QRect(left, y + label, size[0], size[1]), image)
            y += height + padding
        painter.end()
        path = self.output / "index.png"
        sheet.save(str(path))
        return path


LAUNCHER_STUBS = """
import QtQuick
QtObject {
    property QtObject launcher: QtObject {
        signal changed()
        property string query: "dol"
        property string status: "ready"
        property string error: ""
        property int selectedIndex: 0
        property var rows: [
            {id: "dolphin", kind: "app", iconName: "system-file-manager", title: "Dolphin", description: "Gerenciador de arquivos", source: "Aplicativos",
             categoryLabel: "APLICATIVOS", generation: 1, enabled: true,
             actions: [{id: "new-window", text: "Nova janela", row: 0, generation: 1, resultId: "dolphin"}]},
            {id: "dolphin-root", kind: "app", iconName: "utilities-terminal", title: "Konsole", description: "Terminal",
             source: "Aplicativos", categoryLabel: "APLICATIVOS", generation: 1, enabled: true, actions: []},
            {id: "calc", kind: "calculator", iconName: "accessories-calculator", title: "= 168", description: "24 * 7", source: "Calculadora",
             categoryLabel: "CALCULADORA", generation: 1, enabled: true, actions: []},
            {id: "steam-1", kind: "steam", title: "Jogo sintético", description: "Biblioteca Steam local", source: "Steam",
             categoryLabel: "STEAM", generation: 1, enabled: true, actions: []}
        ]
        function select(row) { selectedIndex = row; }
        function moveSelection(delta) {}
        function execute(row, generation, id, actionId) {}
        function dismiss() {}
    }
    property QtObject aiProviders: QtObject {
        signal closeReady()
        property bool busy: false
        property string status: "idle"
        property string operation: ""
        property string error: ""
        property string requestId: ""
        property var providers: [
            {id: "codex", name: "Codex", displayName: "Codex", clientVersion: "", capabilities: {installation: "absent", anonymous_protocol: "unknown"},
             messageCode: "cli_present_version_not_queried"}
        ]
        function cancelAll() {}
        function cancel() {}
        function requestClose() { return true; }
        function discover() {}
        function probeCodex() {}
    }
    property QtObject aiText: QtObject {
        signal closeReady()
        property bool busy: false
        property string status: "idle"
        property string error: ""
        property string output: ""
        property string finishReason: ""
        property string requestId: ""
        property var usage: ({})
        function cancelAll() {}
        function cancel() {}
        function requestClose() { return true; }
        function generate() { return false; }
    }
    property QtObject steamProvider: QtObject {
        signal closeReady()
        property bool busy: false
        property string status: "ready"
        property string error: ""
        property int rootsCount: 1
        property int issueCount: 0
        property var apps: [{appId: "1", name: "Jogo sintético", installState: "installed"}]
        function cancelAll() {}
        function requestClose() { return true; }
        function scan() {}
        function openDownloads() {}
    }
    property QtObject windowSession: QtObject {
        property string notice: ""
        property string shortcutText: "Meta+Espaço"
    }
}
"""


def render(host: str, output: Path) -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    gallery = Gallery(output)
    gallery.dock(host)
    gallery.bar(host)
    if host == "dark":
        gallery.launcher()
    app.processEvents()
    unique = sorted(set(gallery.warnings))
    if unique:
        print(f"{host}: {len(unique)} QML warning(s) while rendering:", file=sys.stderr)
        for warning in unique[:20]:
            print("  " + warning, file=sys.stderr)
    return 0


def host_environment(host: str, config: Path) -> dict[str, str]:
    scheme = "BreezeDark" if host == "dark" else "BreezeLight"
    source = Path("/usr/share/color-schemes") / f"{scheme}.colors"
    if source.exists():
        shutil.copyfile(source, config / "kdeglobals")
    with (config / "kdeglobals").open("a", encoding="utf-8") as handle:
        handle.write(f"\n[General]\nColorScheme={scheme}\n")
    environment = os.environ.copy()
    environment["XDG_CONFIG_HOME"] = str(config)
    # Plasma's platform theme gives the bar the same palette it gets in a panel.
    environment["QT_QPA_PLATFORMTHEME"] = "kde"
    return environment


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "--render":
        return render(argv[2], Path(argv[3]))
    output = Path(argv[1]) if len(argv) > 1 else ROOT / ".runtime/design-gallery"
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.png"):
        stale.unlink()
    for host in ("dark", "light"):
        with tempfile.TemporaryDirectory(prefix=f"orla-gallery-{host}-") as config:
            result = subprocess.run([sys.executable, "-B", __file__, "--render", host, str(output)],
                                    env=host_environment(host, Path(config)), timeout=300)
            if result.returncode:
                return result.returncode
    app = QGuiApplication.instance() or QGuiApplication([])
    gallery = Gallery(output)
    order = ("dock-", "popup-dark-", "popup-light-", "bar-", "launcher-")
    paths = sorted(output.glob("*.png"), key=lambda path: (
        next((index for index, prefix in enumerate(order) if path.name.startswith(prefix)), len(order)), path.name))
    gallery.captures = [(path.stem, path) for path in paths]
    sheet = gallery.contact_sheet()
    app.processEvents()
    for _, path in gallery.captures:
        print(path)
    print(f"contact sheet: {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
