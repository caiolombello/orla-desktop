#!/usr/bin/env python3
"""Render Orla surfaces with synthetic data so people and agents can review visuals.

Run through `python3 scripts/design.py gallery [--output DIR]`. Every capture uses
owned fixtures: no real apps, accounts, providers or personal data are read.
Each system scheme renders in its own process with a private XDG_CONFIG_HOME
holding Breeze Dark or Breeze Light, so popups pick their Orla scheme exactly as
they would on that desktop. Writes one PNG per surface plus `index.png`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt, QUrl, QCoreApplication, QEvent
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

    def appearance_catalog(self, host: str) -> None:
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "QmlHarness.qml")))
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))
        def evaluate(source):
            expression = QQmlExpression(context, dock, source)
            value, _ = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            return value
        window.setProperty("width", 900)
        window.setProperty("height", 900)
        evaluate('root.anchors.centerIn=undefined;root.x=40;root.y=24;settings.popupType=0;'
                 'settings.width=420;settings.heightBudget=420;'
                 'profiles.initializeDefaults(profiles.activeProfileId,profiles.revision);'
                 'profiles.select("work",profiles.activeProfileId,profiles.revision);settings.open()')
        QTest.qWait(60)
        popup = window.findChild(QQuickItem, "settingsPopup")
        pending = [window.contentItem()]
        choice = None
        while pending:
            item = pending.pop()
            if item.objectName() == "appearancePresetCatalog-essencial":
                choice = item
                break
            pending.extend(item.childItems())
        assert choice is not None
        choice.forceActiveFocus(Qt.TabFocusReason)
        steps, name = (1, "mare") if host == "dark" else (3, "jogo")
        for _ in range(steps):
            QTest.keyClick(window, Qt.Key_Tab)
            QTest.qWait(20)
        assert window.activeFocusItem().objectName() == "appearancePresetCatalog-" + name
        QTest.keyClick(window, Qt.Key_Return)
        self.save(f"preset-catalog-{host}-{name}-420", window, self.scene_rect(popup))
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(window, QEvent.DeferredDelete)
        QTest.qWait(10)
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)
        QTest.qWait(10)

    def appearance_advanced(self, host: str) -> None:
        """Progressive appearance controls in the existing short popup fixture."""
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "QmlHarness.qml")))
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))

        def evaluate(source):
            expression = QQmlExpression(context, dock, source)
            value, _ = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            return value

        def control(name):
            declared = window.findChild(QQuickItem, name)
            if declared is not None:
                return declared
            # Repeater delegates have visual parents outside QObject.findChild.
            # Traverse our editor in QML, avoiding Python wrappers for unrelated
            # private native items in the complete Plasma fixture.
            advanced = window.findChild(QQuickItem, "appearanceAdvanced")
            if advanced is None:
                raise RuntimeError("Missing appearance disclosure")
            target = advanced.parentItem()
            source = "(function find(item) { if (item.objectName === " + json.dumps(name) + ") return item; for (const child of item.children) { const found = find(child); if (found) return found; } return null; })(this)"
            expression = QQmlExpression(QQmlEngine.contextForObject(target), target, source)
            value, _ = expression.evaluate()
            if expression.hasError() or value is None:
                raise RuntimeError("Missing appearance gallery control: " + name)
            return value

        def focus(item):
            assert item.isVisible()
            item.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(60)  # Let the editor reveal its focused control.

        try:
            window.setProperty("width", 900)
            window.setProperty("height", 900)
            evaluate('root.anchors.centerIn=undefined;root.x=40;root.y=24;settings.popupType=0;'
                     'settings.width=420;settings.heightBudget=420;'
                     'profiles.initializeDefaults(profiles.activeProfileId,profiles.revision);'
                     'profiles.select("work",profiles.activeProfileId,profiles.revision);settings.open()')
            QTest.qWait(60)
            popup = window.findChild(QQuickItem, "settingsPopup")
            advanced = control("appearanceAdvanced")
            assert not advanced.property("checked")
            assert not control("appearanceColorforeground").isVisible()
            assert not control("appearanceThemeJSON").isVisible()
            self.save(f"appearance-{host}-collapsed-420", window, self.scene_rect(popup))
            focus(control("appearanceNumberopacity"))
            self.save(f"appearance-{host}-common-420", window, self.scene_rect(popup))

            focus(advanced)
            QTest.keyClick(window, Qt.Key_Space)
            assert advanced.property("checked")
            focus(control("appearanceColorforeground"))
            self.save(f"appearance-{host}-colors-420", window, self.scene_rect(popup))

            theme = control("appearanceThemeJSON")
            focus(theme)
            QTest.keyClick(window, Qt.Key_Space)
            assert theme.property("checked")
            field = control("appearanceThemeInput")
            assert field.isVisible()
            field.setProperty("text", '{"name":"Tema sintético incompleto para revisão"}')
            focus(control("appearanceThemePreview"))
            QTest.keyClick(window, Qt.Key_Space)
            QTest.qWait(60)
            assert control("appearanceError").isVisible()
            focus(field)
            self.save(f"appearance-{host}-json-error-420", window, self.scene_rect(popup))
            # No Apply: synthetic invalid input is discarded with this window.
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(window, QEvent.DeferredDelete)
            QTest.qWait(10)
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)
            QTest.qWait(10)

    def bar(self, host: str) -> None:
        from test_bar import FixtureApplication, FixtureControlCenter, FixtureSession
        session, application, center = FixtureSession(), FixtureApplication(), FixtureControlCenter()
        engine = self.engine()
        engine.rootContext().setContextProperty("fixtureSession", session)
        engine.rootContext().setContextProperty("fixtureApplication", application)
        engine.rootContext().setContextProperty("fixtureControlCenter", center)
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
        # Plasma's 32-point panel leaves a 24-point applet viewport after margins.
        QQmlExpression(context, bar, "height = 24; showControlCenter = true; showApplicationName = false;"
                                     "controlCenterControl.forceActiveFocus(Qt.TabFocusReason)").evaluate()
        self.save(f"bar-{host}-short-focus", window, QRectF(0, 0, 420, bar.height()))
        QQmlExpression(context, bar, "compactHeight = true").evaluate()
        self.save(f"bar-{host}-compact-focus", window, QRectF(0, 0, 420, bar.height()))
        QQmlExpression(context, bar, "compactHeight = false; height = implicitHeight;"
                                     "showControlCenter = false; showApplicationName = true").evaluate()
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
        context = QQmlEngine.contextForObject(window)
        QQmlExpression(context, window, "openResultActions()").evaluate()
        self.save("launcher-actions", window)
        QTest.keyClick(window, Qt.Key_Escape)
        QQmlExpression(context, window, 'aliasPreferences.begin("manager", null)').evaluate()
        self.save("launcher-aliases-manager", window)
        QQmlExpression(context, window, 'aliasPreferences.begin("edit", {alias:"arquivos", appId:"org.orla.synthetic.desktop"})').evaluate()
        self.save("launcher-aliases-editor", window)
        QTest.keyClick(window, Qt.Key_Escape)
        window.setProperty("width", 440)
        window.setProperty("height", 380)
        QQmlExpression(context, window, "openResultActions()").evaluate()
        QTest.keyClick(window, Qt.Key_Down)
        QTest.keyClick(window, Qt.Key_Down)
        self.save("launcher-actions-narrow-focus", window)
        QTest.keyClick(window, Qt.Key_Escape)
        QQmlExpression(context, window, 'aliasPreferences.begin("manager", null)').evaluate()
        self.save("launcher-aliases-manager-narrow", window)
        QQmlExpression(context, window, 'aliasPreferences.begin("add", {row:0,id:"dolphin"}); aliasPreferences.localError="Este alias já existe."').evaluate()
        self.save("launcher-aliases-error-narrow", window)
        QTest.keyClick(window, Qt.Key_Escape)
        launcher.setProperty("aliases", [])
        launcher.setProperty("aliasesWritable", False)
        launcher.setProperty("aliasError", "O arquivo de aliases não é válido.")
        QQmlExpression(context, window, 'aliasPreferences.begin("manager", null)').evaluate()
        self.save("launcher-aliases-unavailable-narrow", window)
        QTest.keyClick(window, Qt.Key_Escape)
        window.setProperty("width", 660)
        window.setProperty("height", 420)
        launcher.setProperty("rows", [])
        launcher.setProperty("status", "idle")
        launcher.setProperty("selectedIndex", -1)
        self.save("launcher-empty", window)
        # Explicit synthetic favorites; the launcher keeps its fixed dark scheme.
        def favorite_scene(source: str) -> None:
            expression = QQmlExpression(context, window, source)
            expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())

        def favorite_control(name: str) -> QQuickItem:
            pending = [window.contentItem()]
            while pending:
                control = pending.pop()
                if control.objectName() == name:
                    return control
                pending.extend(control.childItems())
            raise RuntimeError(f"Missing synthetic favorite control: {name}")

        favorite_scene('launcher.aliasesWritable=true; launcher.aliasError=""; '
                       'launcher.aliases=[{alias:"arquivos",appId:"org.orla.synthetic.desktop",title:"Arquivos sintéticos",iconName:"system-file-manager",available:true}]; '
                       'launcher.favorites=[{appId:"org.orla.synthetic.desktop",title:"Arquivos sintéticos",iconName:"system-file-manager",available:true}, '
                       '{appId:"org.orla.notes.desktop",title:"Notas sintéticas",iconName:"accessories-text-editor",available:true}]; launcher.showFavorites()')
        self.save("launcher-favorites-empty-query", window)
        QTest.keyClick(window, Qt.Key_K, Qt.ControlModifier)
        self.save("launcher-favorites-actions", window)
        QTest.keyClick(window, Qt.Key_Escape)
        favorite_scene('aliasPreferences.begin("manager", null)')
        self.save("launcher-favorites-manager", window)
        QTest.keyClick(window, Qt.Key_Escape)
        window.setProperty("width", 440)
        self.save("launcher-favorites-empty-query-narrow", window)
        favorite_scene('aliasPreferences.begin("manager", null)')
        self.save("launcher-favorites-manager-narrow", window)
        QTest.keyClick(window, Qt.Key_Escape)
        favorite_scene('launcher.favorites=[{appId:"org.orla.missing.desktop",title:"",iconName:"",available:false}]; '
                       'launcher.showFavorites(); aliasPreferences.begin("manager", null)')
        QTest.qWait(50)
        favorite_control("favoriteRemove0").forceActiveFocus(Qt.TabFocusReason)
        self.save("launcher-favorites-missing-narrow", window)
        QTest.keyClick(window, Qt.Key_Escape)
        favorite_scene('launcher.aliases=[]; launcher.aliasesWritable=false; launcher.aliasError="O arquivo de aliases não é válido."; '
                       'launcher.favorites=[{appId:"org.orla.synthetic.desktop",title:"Arquivos sintéticos",iconName:"system-file-manager",available:true}]; '
                       'launcher.showFavorites(); aliasPreferences.begin("manager", null)')
        self.save("launcher-favorites-aliases-unavailable-narrow", window)
        QTest.keyClick(window, Qt.Key_Escape)
        favorite_scene('launcher.aliasesWritable=true; launcher.aliasError=""; '
                       'launcher.aliases=[{alias:"arquivos",appId:"org.orla.synthetic.desktop",title:"Arquivos sintéticos",iconName:"system-file-manager",available:true}]; '
                       'launcher.favorites=[]; launcher.favoritesWritable=false; launcher.favoriteError="O arquivo de favoritos não é válido."; '
                       'launcher.showFavorites(); aliasPreferences.begin("manager", null)')
        self.save("launcher-favorites-unavailable-aliases-enabled-narrow", window)
        QTest.keyClick(window, Qt.Key_Escape)
        favorite_scene('launcher.favoritesWritable=true; launcher.favoriteError=""; '
                       'launcher.favorites=Array.from({length:16},(_,i)=>({appId:"org.orla.favorite"+i+".desktop",title:"Favorito sintético "+i,iconName:"system-file-manager",available:true})); '
                       'launcher.aliases=Array.from({length:16},(_,i)=>({alias:"alias "+i,appId:"org.orla.alias"+i+".desktop",title:"App sintético "+i,iconName:"system-file-manager",available:true})); '
                       'launcher.showFavorites(); aliasPreferences.begin("manager", null)')
        QTest.qWait(50)
        favorite_control("favoriteRemove0").forceActiveFocus(Qt.TabFocusReason)
        for _ in range(15):
            QTest.keyClick(window, Qt.Key_Tab)
        self.save("launcher-favorites-list-focus-narrow", window)
        QTest.keyClick(window, Qt.Key_Escape)
        window.setProperty("width", 660)
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
        property int generation: 1
        property string aliasRevision: "revision-1"
        property string aliasError: ""
        property bool aliasesWritable: true
        property var aliases: [{alias:"arquivos",appId:"org.orla.synthetic.desktop",title:"Arquivos sintéticos",iconName:"system-file-manager",available:true}, {alias:"indisponível",appId:"org.orla.missing.desktop",title:"",iconName:"",available:false}]
        property string favoriteRevision: "favorite-1"
        property string favoriteError: ""
        property bool favoritesWritable: true
        property var favorites: []
        property var aliasCalls: []
        property int dismissed: 0
        property var executed: []
        property string query: "dol"
        property string status: "ready"
        property string error: ""
        property int selectedIndex: 0
        property var rows: [
            {id: "dolphin", kind: "app", iconName: "system-file-manager", title: "Dolphin", description: "Gerenciador de arquivos", source: "KRunner · Aplicativos",
             categoryLabel: "APLICATIVOS", generation: 1, enabled: true, aliasEligible: true, appId: "org.orla.synthetic.desktop",
             actions: [{id: "new-window", text: "Nova janela", row: 0, generation: 1, resultId: "dolphin"},
                       {id: "other", text: "Outra ação sintética", row: 0, generation: 1, resultId: "dolphin"},
                       {id: "long", text: "Ação sintética com nome longo para conferir os limites", row: 0, generation: 1, resultId: "dolphin"}]},
            {id: "dolphin-root", kind: "app", iconName: "utilities-terminal", title: "Konsole", description: "Terminal",
             source: "Aplicativos", categoryLabel: "APLICATIVOS", generation: 1, enabled: true, actions: []},
            {id: "calc", kind: "calculator", iconName: "accessories-calculator", title: "= 168", description: "24 * 7", source: "Calculadora",
             categoryLabel: "CALCULADORA", generation: 1, enabled: true, actions: []},
            {id: "steam-1", kind: "steam", title: "Jogo sintético", description: "Biblioteca Steam local", source: "Steam",
             categoryLabel: "STEAM", generation: 1, enabled: true, actions: []}
        ]
        function select(row) { selectedIndex = row; }
        function moveSelection(delta) {}
        function execute(row, generation, id, actionId) { executed = executed.concat([{id:id,actionId:actionId}]) }
        function dismiss() { dismissed++ }
        function advance() { generation++; aliasRevision = "revision-" + generation; changed() }
        function rejected(name) { aliasError = name; changed(); return false }
        function check(alias, rev) {
            if (!aliasesWritable || rev !== aliasRevision) return rejected("A lista mudou. Abra o editor novamente.")
            if (aliases.some(entry => entry.alias === alias)) return rejected("Este alias já existe.")
            return true
        }
        function saveAlias(row, gen, id, alias, rev) {
            aliasCalls = aliasCalls.concat([{kind:"save",row:row,generation:gen,id:id,alias:alias,revision:rev}])
            if (gen !== generation || row !== selectedIndex || id !== rows[row].id || !check(alias, rev)) return false
            aliases = aliases.concat([{alias:alias,appId:rows[row].appId}]); aliasError = ""; advance(); return true
        }
        function renameAlias(oldAlias, appId, newAlias, gen, rev) {
            aliasCalls = aliasCalls.concat([{kind:"rename",oldAlias:oldAlias,appId:appId,alias:newAlias,generation:gen,revision:rev}])
            if (gen !== generation || !check(newAlias, rev)) return false
            aliases = aliases.map(entry => entry.alias === oldAlias && entry.appId === appId ? {alias:newAlias,appId:appId} : entry)
            aliasError = ""; advance(); return true
        }
        function removeAlias(alias, appId, gen, rev) {
            aliasCalls = aliasCalls.concat([{kind:"remove",alias:alias,appId:appId,generation:gen,revision:rev}])
            if (!aliasesWritable || gen !== generation || rev !== aliasRevision) return false
            aliases = aliases.filter(entry => entry.alias !== alias || entry.appId !== appId); advance(); return true
        }
        function reloadAliases() {}
        function showFavorites() {
            query = ""
            rows = favorites.map(entry => ({id:"favorite:"+entry.appId,kind:"favorite",category:"favorite",
                categoryLabel:"FAVORITOS",source:"Favorito salvo por você",appId:entry.appId,title:entry.title || "Aplicativo indisponível",
                iconName:entry.iconName || "",favoriteRevision:favoriteRevision,generation:generation,
                enabled:favoritesWritable && entry.available !== false,actions:[]}))
            selectedIndex = rows.findIndex(entry => entry.enabled)
            status = rows.length ? "ready" : "idle"
            changed()
        }
        function pinFavorite(row, gen, id, rev) {
            if (!favoritesWritable || gen !== generation || rev !== favoriteRevision || row !== selectedIndex
                || !rows[row] || rows[row].id !== id || rows[row].kind !== "app" || rows[row].aliasEligible !== true) return false
            const item = rows[row]
            if (!favorites.some(entry => entry.appId === item.appId))
                favorites = favorites.concat([{appId:item.appId,title:item.title,iconName:item.iconName,available:true}])
            favoriteRevision += "-next"; generation++; changed(); return true
        }
        function removeFavorite(appId, gen, rev) {
            if (!favoritesWritable || gen !== generation || rev !== favoriteRevision) return false
            favorites = favorites.filter(entry => entry.appId !== appId)
            favoriteRevision += "-next"; generation++
            if (query === "") showFavorites()
            else changed()
            return true
        }
        function reloadFavorites() {}
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
    gallery.appearance_catalog(host)
    gallery.appearance_advanced(host)
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
