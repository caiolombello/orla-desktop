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
from PySide6.QtTest import QTest, QSignalSpy

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(ROOT))
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
    # Synthetic events: colored bars per calendar, today and tomorrow (filled in after opening).
    # Not right after "calendar": the same popup may still be closing.
    ("calendar-events", "calendarPopup.openAt(settingsButton)"),
)
# Set on an object found by name once its popup is open (popup content has its own context).
POPUP_FIXTURES = {
    "calendar-events": ("calendarAgenda",
        "usePimEvents = true; "
        "fixtureEvents = [{title: 'Reunião de equipe', isAllDay: false, eventColor: '#3d8ee6', "
        "startDateTime: new Date(2026, 9, 25, 10, 0), endDateTime: new Date(2026, 9, 25, 11, 0)}, "
        "{title: 'Aniversário sintético', isAllDay: true, eventColor: '#e0708a'}]; "
        "fixtureTomorrowEvents = [{title: 'Consulta', isAllDay: false, eventColor: '#5bbf84', "
        "startDateTime: new Date(2026, 9, 26, 14, 30), endDateTime: new Date(2026, 9, 26, 15, 0)}]"),
}
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
        if host == "dark":
            # The optional Trash closes the dock after its own divider, as in macOS.
            config.setProperty("showTrash", True)
            QTest.qWait(50)
            # A private empty folder: the capture never reads the user's own trash.
            empty_trash = tempfile.mkdtemp(prefix="orla-gallery-trash-")
            window.findChild(QQuickItem, "trashTile").setProperty("filesFolder", QUrl.fromLocalFile(empty_trash))
            QTest.qWait(200)
            self.save("dock-glass-trash", window, self.scene_rect(dock))
            shutil.rmtree(empty_trash, ignore_errors=True)
            config.setProperty("showTrash", False)
            QTest.qWait(100)
        for name, source in POPUPS:
            evaluate("closeContext(); settings.close()")
            QTest.qWait(60)
            evaluate(source)
            if name in POPUP_FIXTURES:
                QTest.qWait(60)
                target_name, fixture = POPUP_FIXTURES[name]
                target = window.findChild(QObject, target_name)
                expression = QQmlExpression(engine.rootContext(), target, fixture)
                expression.evaluate()
                if expression.hasError():
                    raise RuntimeError(expression.error().toString())
            # Let content set from the scene (such as synthetic events) lay out before capture.
            QTest.qWait(120)
            visible = [popup for popup in (evaluate(identifier) for identifier in POPUP_IDS) if popup.property("visible")]
            if not visible:
                raise RuntimeError(f"popup scene {name} left no popup open")
            popup = visible[0]
            self.save(f"popup-{host}-{name}", window, self.scene_rect(popup))
        # The lower Control Center cards (Areas, Energy and its power profile) sit below the fold.
        # Three synthetic areas and two Activities show the area switcher and the Activity name.
        evaluate("closeContext(); settings.close()")
        QTest.qWait(60)
        QQmlExpression(engine.rootContext(), window,
                       "contextSnapshot = ({outputName: 'DP-1', activity: {status: 'ready', currentId: 'activity-work',"
                       " ids: ['activity-work', 'activity-home'], names: ['Foco', 'Casa']}, desktop: {status: 'ready',"
                       " currentId: 'desktop-1', ids: ['desktop-1', 'desktop-2', 'desktop-3'],"
                       " names: ['Área 1', 'Área 2', 'Área 3']}})").evaluate()
        evaluate("controlCenterPopup.openAt(settingsButton)")
        QTest.qWait(100)
        flick = window.findChild(QQuickItem, "controlCenterScroll").property("contentItem")
        flick.setProperty("contentY", max(0.0, flick.property("contentHeight") - flick.property("height")))
        QTest.qWait(100)
        self.save(f"popup-{host}-control-center-energy", window,
                  self.scene_rect(evaluate("controlCenterPopup")))
        # The Wi-Fi page: networks in range, as macOS opens from the Wi-Fi name.
        evaluate("controlCenterPopup.contents.showWifi()")
        QTest.qWait(150)
        self.save(f"popup-{host}-control-center-wifi", window,
                  self.scene_rect(evaluate("controlCenterPopup")))
        evaluate("controlCenterPopup.contents.showMain(); controlCenterPopup.contents.showBluetooth()")
        QTest.qWait(150)
        self.save(f"popup-{host}-control-center-bluetooth", window,
                  self.scene_rect(evaluate("controlCenterPopup")))
        evaluate("closeContext(); settings.close()")
        window.close()
        engine.deleteLater()

    def auto_contexts(self, host: str) -> None:
        """Opt-in and manual override in the real dock composition, synthetic data."""
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "QmlHarness.qml")))
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))
        popup = window.findChild(QQuickItem, "settingsPopup")

        def evaluate(source, target=dock):
            expression = QQmlExpression(context if target is dock else QQmlEngine.contextForObject(target), target, source)
            value, _ = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            return value

        def open_settings(width):
            popup.setProperty("width", width)
            popup.open()
            window.findChild(QQuickItem, "settingsTabs").setProperty("currentIndex", 3)
            QTest.qWait(60)

        def close_settings():
            popup.close()
            QTest.qWait(300)

        try:
            window.setWidth(900)
            window.setHeight(900)
            popup.setProperty("popupType", 0)
            popup.setProperty("heightBudget", 540)
            evaluate("anchors.centerIn=undefined;x=40;y=24;"
                     "profiles.initializeDefaults(profiles.activeProfileId,profiles.revision);"
                     "profiles.select('work',profiles.activeProfileId,profiles.revision);"
                     "autoContextProfiles.setDefaultProfile('games')")
            open_settings(350)
            self.save(f"contexts-auto-{host}-off-350", window, self.scene_rect(popup))
            evaluate("autoContextProfiles.setEnabled(true)")
            self.save(f"contexts-auto-{host}-waiting-350", window, self.scene_rect(popup))
            snapshot = json.loads(evaluate("JSON.stringify(contextSnapshot)", window))
            for name, activity_status, desktop_status in (
                ("activity-unavailable", "unavailable", "ready"),
                ("both-unavailable", "unavailable", "unavailable"),
            ):
                frame = json.loads(json.dumps(snapshot))
                frame["activity"]["status"] = activity_status
                frame["desktop"]["status"] = desktop_status
                evaluate("contextSnapshot=" + json.dumps(frame), window)
                self.save(f"contexts-auto-{host}-{name}-350", window, self.scene_rect(popup))
            evaluate("contextSnapshot=" + json.dumps(snapshot), window)
            details = window.findChild(QQuickItem, "autoContextHelpToggle")
            details.forceActiveFocus(Qt.TabFocusReason)
            QTest.keyClick(window, Qt.Key_Space)
            self.save(f"contexts-auto-{host}-help-350", window, self.scene_rect(popup))
            close_settings()
            evaluate("profiles.select('personal',profiles.activeProfileId,profiles.revision)")
            assert evaluate("autoContextProfiles.manualOverride")
            open_settings(420)
            window.findChild(QQuickItem, "autoContextHelpToggle").setProperty("checked", False)
            window.findChild(QQuickItem, "autoContextResume").forceActiveFocus(Qt.TabFocusReason)
            self.save(f"contexts-auto-{host}-manual-420", window, self.scene_rect(popup))
            close_settings()
            assert evaluate("autoContextProfiles.setPolicy('desktop')")
            desktop_only = json.loads(json.dumps(snapshot))
            desktop_only["activity"] = {"status": "unavailable", "currentId": "", "ids": [], "names": []}
            evaluate("contextSnapshot=" + json.dumps(desktop_only), window)
            policy = window.findChild(QQuickItem, "autoContextPolicy")
            for width in (350, 420):
                details.setProperty("checked", False)
                open_settings(width)
                policy.forceActiveFocus(Qt.TabFocusReason)
                self.save(f"contexts-policy-{host}-desktop-focus-{width}", window, self.scene_rect(popup))
                evaluate("Accessible.pressAction()", policy)
                self.save(f"contexts-policy-{host}-desktop-open-{width}", window, self.scene_rect(popup))
                evaluate("Accessible.pressAction()", policy)
                details.forceActiveFocus(Qt.TabFocusReason)
                QTest.keyClick(window, Qt.Key_Space)
                self.save(f"contexts-policy-{host}-desktop-help-{width}", window, self.scene_rect(popup))
                close_settings()
        finally:
            close_settings()
            window.close()
            engine.deleteLater()

    def profile_rename(self, host: str) -> None:
        """Active-name editing and its error in the unchanged short settings popup."""
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "ProfilesDockHarness.qml")))
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        popup = window.findChild(QQuickItem, "settingsPopup")
        context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))

        def evaluate(source):
            expression = QQmlExpression(context, dock, source)
            value, _ = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            return value

        def control(name):
            item = window.findChild(QQuickItem, name)
            if item is None:
                raise RuntimeError("Missing profile gallery control: " + name)
            return item

        def focus(item):
            item.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(60)
            assert window.activeFocusItem() == item
            viewport = control("profileControls").property("contentItem")
            point = item.mapToItem(viewport, QPointF(0, 0))
            rim = 2 if item.objectName() == "profileRenameName" else 3
            assert point.x() - rim >= 0 and point.y() - rim >= 0
            assert point.x() + item.width() + rim <= viewport.width()
            assert point.y() + item.height() + rim <= viewport.height()

        try:
            window.setWidth(900)
            window.setHeight(900)
            popup.setProperty("popupType", 0)
            popup.setProperty("heightBudget", 420)
            evaluate("anchors.centerIn=undefined;x=40;y=24;"
                     "profiles.initializeDefaults(profiles.activeProfileId,profiles.revision);"
                     "profiles.select('work',profiles.activeProfileId,profiles.revision)")
            for width in (350, 420):
                popup.setProperty("width", width)
                popup.open()
                window.findChild(QQuickItem, "settingsTabs").setProperty("currentIndex", 2)
                QTest.qWait(60)
                disclosure = control("profileRenameToggle")
                field = control("profileRenameName")
                save = control("profileRenameSave")
                focus(disclosure)
                self.save(f"profiles-rename-{host}-compact-{width}", window, self.scene_rect(popup))
                QTest.keyClick(window, Qt.Key_Space)
                field.setProperty("text", "Trabalho e projetos compartilhados")
                focus(field)
                self.save(f"profiles-rename-{host}-editing-{width}", window, self.scene_rect(popup))
                field.setProperty("text", "Pessoal")
                focus(save)
                QTest.keyClick(window, Qt.Key_Space)
                assert field.isVisible()
                assert "Já existe" in control("profileRenameStatus").property("text")
                self.save(f"profiles-rename-{host}-error-{width}", window, self.scene_rect(popup))
                QTest.keyClick(window, Qt.Key_Tab)
                assert window.activeFocusItem() == control("profileRenameCancel")
                self.save(f"profiles-rename-{host}-cancel-focus-{width}", window, self.scene_rect(popup))
                field.setProperty("text", "Projetos pessoais" if width == 350 else "Trabalho em equipe")
                focus(save)
                QTest.keyClick(window, Qt.Key_Space)
                assert not field.isVisible()
                assert window.activeFocusItem() == disclosure
                self.save(f"profiles-rename-{host}-saved-{width}", window, self.scene_rect(popup))
                popup.close()
                QTest.qWait(300)
        finally:
            popup.close()
            window.close()
            engine.deleteLater()

    def profile_remove(self, host: str) -> None:
        """Captured impact, last profile and recovery in the existing short popup."""
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "ProfilesDockHarness.qml")))
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        popup = window.findChild(QQuickItem, "settingsPopup")
        config = window.findChild(QObject, "configuration")
        context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))

        def evaluate(source, target=dock):
            expression = QQmlExpression(context if target is dock else QQmlEngine.contextForObject(target), target, source)
            value, _ = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            return value

        def control(name):
            item = window.findChild(QQuickItem, name)
            if item is None:
                raise RuntimeError("Missing removal gallery control: " + name)
            return item

        def focus(item):
            item.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(60)
            assert window.activeFocusItem() == item
            viewport = control("profileControls").property("contentItem")
            point = item.mapToItem(viewport, QPointF(0, 0))
            assert point.y() - 3 >= 0 and point.y() + item.height() + 3 <= viewport.height()

        try:
            window.setWidth(900)
            window.setHeight(900)
            popup.setProperty("popupType", 0)
            popup.setProperty("heightBudget", 420)
            evaluate("anchors.centerIn=undefined;x=40;y=24;profiles.initializeDefaults(profiles.activeProfileId,profiles.revision);profiles.select('work',profiles.activeProfileId,profiles.revision)")
            base = json.loads(config.property("profilesJSON"))
            bindings = {"formatVersion": "0.1-experimental", "activityBindings": [
                {"contextId": "activity-work", "lastKnownName": "Foco", "profileId": "work"},
                {"contextId": "activity-old", "lastKnownName": "Anterior", "profileId": "work"}],
                "desktopBindings": [{"contextId": "desktop-old", "lastKnownName": "Antiga", "profileId": "work"}]}
            for width in (350, 420):
                for state in ("default", "last", "orphan", "stale"):
                    document = json.loads(json.dumps(base))
                    if state == "last":
                        document["profiles"] = [profile for profile in document["profiles"] if profile["id"] == "work"]
                    config.setProperty("autoContextEnabled", False)
                    config.setProperty("profilesJSON", json.dumps(document))
                    config.setProperty("contextsJSON", json.dumps(bindings))
                    config.setProperty("autoContextDefaultProfile", "work")
                    config.setProperty("autoContextEnabled", state != "last")
                    popup.setProperty("width", width)
                    popup.open()
                    control("settingsTabs").setProperty("currentIndex", 2)
                    focus(control("profileRemoveToggle"))
                    QTest.keyClick(window, Qt.Key_Space)
                    destination = control("profileRemoveDestination")
                    assert destination.property("currentIndex") == -1
                    focus(destination)
                    if state == "last":
                        self.save(f"profiles-remove-{host}-{state}-{width}", window, self.scene_rect(popup))
                        popup.close()
                        QTest.qWait(300)
                        continue
                    QTest.keyClick(window, Qt.Key_Down)
                    assert destination.property("currentIndex") == 0
                    focus(control("profileRemoveConfirm"))
                    if state == "stale":
                        config.setProperty("autoContextPolicy", "desktop")
                        focus(control("profileRemoveCancel"))
                        assert "mudou" in control("profileRemoveStatus").property("text")
                    elif state == "orphan":
                        QTest.keyClick(window, Qt.Key_Space)
                        control("settingsTabs").setProperty("currentIndex", 3)
                        QTest.qWait(60)
                        orphan = control("orphanProfileBindings")
                        controls = control("contextControls")
                        viewport = controls.property("contentItem")
                        point = orphan.mapToItem(viewport, QPointF(0, 0))
                        viewport.setProperty("contentY", viewport.property("contentY") + point.y())
                    self.save(f"profiles-remove-{host}-{state}-{width}", window, self.scene_rect(popup))
                    popup.close()
                    QTest.qWait(300)
                    config.setProperty("autoContextPolicy", "activity-desktop")
        finally:
            popup.close()
            window.close()
            engine.deleteLater()

    def saved_contexts(self, host: str) -> None:
        """Saved identities, protected documents and explicit inline cleanup."""
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "ContextsDockHarness.qml")))
        window = engine.rootObjects()[0]
        dock = window.findChild(QQuickItem, "dock")
        popup = window.findChild(QQuickItem, "settingsPopup")
        config = window.findChild(QObject, "configuration")

        def evaluate(source, target=dock):
            expression = QQmlExpression(QQmlEngine.contextForObject(target), target, source)
            value, _ = expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())
            return value

        def control(name):
            item = window.findChild(QQuickItem, name)
            if item is None:
                raise RuntimeError("Missing saved association control: " + name)
            return item

        def focus(item):
            # Reused popup fixtures can retain the same focused object after close.
            # Enter through the existing tab control to exercise an actual focus change.
            if window.activeFocusItem() == item:
                control("settingsTabs").forceActiveFocus(Qt.TabFocusReason)
            item.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(100)
            viewport = control("contextControls").property("contentItem")
            point = item.mapToItem(viewport, QPointF(0,0))
            assert window.activeFocusItem() == item
            assert point.y()-3 >= 0 and point.y()+item.height()+3 <= viewport.height(), (item.objectName(),point.y(),item.height(),viewport.height(),control("contextControls").property("sessionOpen"))

        try:
            window.setWidth(1000)
            window.setHeight(900)
            popup.setProperty("popupType", 0)
            popup.setProperty("heightBudget", 420)
            evaluate("anchors.centerIn=undefined;x=40;y=24;profiles.initializeDefaults(profiles.activeProfileId,profiles.revision)")
            base = {"formatVersion":"0.1-experimental", "activityBindings":[
                {"contextId":"activity-old", "lastKnownName":"Contexto anterior", "profileId":"missing"}],
                "desktopBindings":[{"contextId":"activity-old", "lastKnownName":"Contexto anterior", "profileId":"work"}]}
            for width in (350,420):
                for state in ("empty", "list", "details", "confirm", "stale", "protected"):
                    document = json.loads(json.dumps(base))
                    if state == "empty":
                        document["activityBindings"] = []
                        document["desktopBindings"] = []
                    elif state == "list":
                        for kind in ("activityBindings", "desktopBindings"):
                            document[kind] = [{"contextId":str(i), "lastKnownName":"Contexto sintético " + str(i+1), "profileId":"work"} for i in range(64)]
                    elif state == "details":
                        document["activityBindings"][0]["contextId"] = ("contexto-" + "x"*256)[:256]
                        document["activityBindings"][0]["lastKnownName"] = "<b>Nome salvo literal</b>"
                    config.setProperty("contextsJSON", '{"formatVersion":"future","owned":true}' if state == "protected" else json.dumps(document))
                    config.setProperty("autoContextPolicy", "activity-desktop")
                    popup.setProperty("width", width)
                    popup.open()
                    control("settingsTabs").setProperty("currentIndex", 3)
                    QTest.qWait(300)
                    focus(control("savedContextToggle"))
                    QTest.keyClick(window, Qt.Key_Space)
                    selector = control("savedContextSelector")
                    assert selector.property("currentIndex") == -1
                    rect = self.scene_rect(popup)
                    if state == "list":
                        focus(selector)
                        QTest.keyClick(window, Qt.Key_Space)
                        QTest.qWait(150)
                        assert evaluate("popup.visible", selector)
                        menu = evaluate("popup.contentItem", selector)
                        rect = rect.united(self.scene_rect(menu))
                    elif state in ("details", "confirm", "stale"):
                        focus(selector)
                        QTest.keyClick(window, Qt.Key_Down)
                        QTest.keyClick(window, Qt.Key_Return)
                        QTest.qWait(100)
                        if state == "stale":
                            config.setProperty("autoContextPolicy", "desktop")
                            focus(control("savedContextCancel"))
                        elif state == "confirm":
                            focus(control("savedContextRemove"))
                        else:
                            # A reading position, with no hidden focused control.
                            window.contentItem().forceActiveFocus(Qt.OtherFocusReason)
                            details = control("savedContextDetails")
                            viewport = control("contextControls").property("contentItem")
                            point = details.mapToItem(viewport, QPointF(0,0))
                            viewport.setProperty("contentY", viewport.property("contentY") + point.y())
                    self.save(f"contexts-saved-{host}-{state}-{width}", window, rect)
                    popup.close()
                    QTest.qWait(300)
        finally:
            popup.close()
            window.close()
            engine.deleteLater()

    def appearance_catalog(self, host: str) -> None:
        """Compact and expanded preset states in the unchanged short popup."""
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
            # Limit delegate lookup to this preset component, not native items
            # belonging to other popups in the complete fixture.
            disclosure = window.findChild(QQuickItem, "appearancePresetCatalogDisclosure")
            if disclosure is None:
                raise RuntimeError("Missing preset catalog disclosure")
            target = disclosure.parentItem()
            source = "(function find(item) { if (item.objectName === " + json.dumps(name) + ") return item; for (const child of item.children) { const found = find(child); if (found) return found; } return null; })(this)"
            expression = QQmlExpression(QQmlEngine.contextForObject(target), target, source)
            value, _ = expression.evaluate()
            if expression.hasError() or value is None:
                raise RuntimeError("Missing preset gallery control: " + name)
            return value

        def focus(item):
            assert item.isVisible() and item.isEnabled()
            item.forceActiveFocus(Qt.TabFocusReason)
            QTest.qWait(60)
            assert window.activeFocusItem() == item

        try:
            window.setProperty("width", 900)
            window.setProperty("height", 900)
            evaluate('root.anchors.centerIn=undefined;root.x=40;root.y=24;settings.popupType=0;'
                     'settings.width=420;settings.heightBudget=420;settings.open()')
            QTest.qWait(60)
            popup = window.findChild(QQuickItem, "settingsPopup")
            outer = control("appearancePresetCatalogDisclosure")
            assert not outer.property("checked")
            assert not control("appearancePresetCatalog-essencial").isVisible()
            assert control("appearancePresetCatalogProfiles").isVisible()
            self.save(f"preset-compact-{host}-legacy-420", window, self.scene_rect(popup))

            closed = QSignalSpy(popup.closed)
            evaluate('settings.close()')
            if not closed.count():
                assert closed.wait(1000)
            evaluate('profiles.initializeDefaults(profiles.activeProfileId,profiles.revision);'
                     'profiles.select("work",profiles.activeProfileId,profiles.revision)')
            QTest.qWait(60)
            opened = QSignalSpy(popup.opened)
            evaluate('settings.open()')
            if not opened.count():
                assert opened.wait(1000)
            assert not outer.property("checked")
            assert not control("appearancePresetCatalog-essencial").isVisible()
            assert not control("appearancePresetCatalogProfiles").isVisible()
            self.save(f"preset-compact-{host}-managed-420", window, self.scene_rect(popup))

            focus(outer)
            QTest.keyClick(window, Qt.Key_Space)
            assert outer.property("checked")
            choice = control("appearancePresetCatalog-essencial")
            focus(choice)
            steps, name = (4, "macos") if host == "dark" else (3, "jogo")
            for _ in range(steps):
                QTest.keyClick(window, Qt.Key_Tab)
                QTest.qWait(20)
            assert window.activeFocusItem().objectName() == "appearancePresetCatalog-" + name
            QTest.keyClick(window, Qt.Key_Return)
            assert evaluate("appearancePreset.hasPreview")
            self.save(f"preset-catalog-{host}-{name}-420", window, self.scene_rect(popup))

            # Pending/invalid input must reopen both groups without discarding
            # the last valid preview. Capture its real editor error state.
            evaluate('appearancePreset.clearInput()')
            outer.setProperty("checked", False)
            assert not outer.property("checked")
            invalid = '{"name":"Aparência portátil sintética incompleta"}'
            evaluate("appearancePreset.setInputText(" + json.dumps(invalid) + ")")
            assert not evaluate("appearancePreset.previewImport()")
            QTest.qWait(60)
            assert outer.property("checked")
            assert control("appearancePresetJSON").property("checked")
            assert control("appearanceError").isVisible()
            field = control("appearancePresetInput")
            assert field.property("text") == invalid
            assert not control("appearanceApply").isEnabled()
            focus(field)
            self.save(f"preset-portable-{host}-invalid-420", window, self.scene_rect(popup))
            # No Apply: every preview/import here belongs only to this fixture.
        finally:
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
            focus(control("appearanceThemeFileImport"))
            self.save(f"appearance-{host}-file-import-420", window, self.scene_rect(popup))
            evaluate('settings.width=350')
            QTest.qWait(60)
            focus(control("appearanceThemeFileImport"))
            self.save(f"appearance-{host}-file-import-350", window, self.scene_rect(popup))
            evaluate('settings.width=420')
            QTest.qWait(60)
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

    def widget_order(self, host: str) -> None:
        """Owned grip interaction at the two existing settings widths."""
        for width in (350, 420):
            engine = self.engine()
            window = None
            try:
                engine.load(QUrl.fromLocalFile(str(TESTS / "QmlHarness.qml")))
                window = engine.rootObjects()[0]
                dock = window.findChild(QQuickItem, "dock")
                config = window.findChild(QObject, "configuration")
                context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))

                def evaluate(source, target=dock):
                    expression = QQmlExpression(context if target is dock else QQmlEngine.contextForObject(target), target, source)
                    value, _ = expression.evaluate()
                    if expression.hasError():
                        raise RuntimeError(expression.error().toString())
                    return value

                def control(name):
                    declared = window.findChild(QQuickItem, name)
                    if declared is not None:
                        return declared
                    rows = window.findChild(QQuickItem, "widgetRowsList")
                    if rows is None:
                        raise RuntimeError("Missing widget list")
                    source = "(function find(item) { if (item.objectName === " + json.dumps(name) + ") return item; for (const child of item.children) { const found = find(child); if (found) return found; } return null; })(this)"
                    found = evaluate(source, rows)
                    if found is None:
                        raise RuntimeError("Missing widget gallery control: " + name)
                    return found

                def focus(item):
                    assert item.isVisible() and item.isEnabled()
                    item.forceActiveFocus(Qt.TabFocusReason)
                    QTest.qWait(30)
                    assert window.activeFocusItem() == item

                window.setProperty("width", 900)
                window.setProperty("height", 900)
                evaluate('root.anchors.centerIn=undefined;root.x=40;root.y=24;settings.popupType=0;'
                         'settings.width=' + str(width) + ';settings.heightBudget=420;'
                         'profiles.initializeDefaults(profiles.activeProfileId,profiles.revision);'
                         'profiles.select("work",profiles.activeProfileId,profiles.revision)')
                popup = window.findChild(QQuickItem, "settingsPopup")
                opened = QSignalSpy(popup.opened)
                evaluate('settings.open()')
                if not opened.count():
                    assert opened.wait(1000)
                window.findChild(QQuickItem, "settingsTabs").setProperty("currentIndex", 1)
                QTest.qWait(30)  # Match the qualified tab/layout precondition.
                grip, target = control("widgetDragclock"), control("widgetDragpomodoro")
                focus(target)
                focus(grip)
                QTest.qWait(30)
                for handle in (grip, target):
                    geometry = json.loads(evaluate('(function() { let row=parent; while (row && row.widgetId === undefined) row=row.parent; if (!row) return "null"; const p=row.mapToItem(widgetScroll,0,0); return JSON.stringify({top:p.y,height:row.height,viewport:widgetScroll.height}); })()', handle))
                    assert geometry is not None
                    assert geometry["top"] >= 0
                    assert geometry["top"] + geometry["height"] <= geometry["viewport"]
                start = grip.mapToScene(QPointF(grip.width() / 2, grip.height() / 2)).toPoint()
                end = target.mapToScene(QPointF(target.width() / 2, target.height() * .75)).toPoint()
                assert 0 <= start.y() < window.height() and 0 <= end.y() < window.height()
                original = config.property("profilesJSON")
                writes = QSignalSpy(config.profilesJSONChanged)
                self.save(f"widgets-{host}-idle-{width}", window, self.scene_rect(popup))
                QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
                try:
                    QTest.mouseMove(window, end, 30)
                    QTest.qWait(20)
                    assert control("widgetDropIndicatorpomodoro").property("visible")
                    assert config.property("profilesJSON") == original and writes.count() == 0
                    self.save(f"widgets-{host}-drag-{width}", window, self.scene_rect(popup))
                    assert config.property("profilesJSON") == original and writes.count() == 0
                finally:
                    # This fixture owns synthetic profile data; release may
                    # commit it. Never leave a held pointer for the next scene.
                    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end)
                QTest.qWait(30)
                module = control("moduleDetailsquota")
                disclosure = module.findChild(QQuickItem, "moduleDisclosure")
                focus(disclosure)
                QTest.keyClick(window, Qt.Key_Space)
                QTest.qWait(30)
                assert module.property("statusText") == "Desativado neste perfil"
                viewport = control("widgetScroll").property("contentItem")
                for label_name in ("moduleDescription", "moduleStatus", "moduleRequirements"):
                    label = module.findChild(QQuickItem, label_name)
                    point = label.mapToItem(viewport, QPointF(0, 0))
                    assert 0 <= point.y() and point.y() + label.height() <= viewport.height()
                self.save(f"modules-{host}-disabled-{width}", window, self.scene_rect(popup))
            finally:
                if window is not None:
                    window.close()
                    window.deleteLater()
                    QCoreApplication.sendPostedEvents(window, QEvent.DeferredDelete)
                    QTest.qWait(10)
                engine.deleteLater()
                QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)
                QTest.qWait(10)

    def bar(self, host: str) -> None:
        from test_bar import FixtureApplication, FixtureControlCenter, FixtureRecent, FixtureSession
        session, application, center = FixtureSession(), FixtureApplication(), FixtureControlCenter()
        recent = FixtureRecent()
        engine = self.engine()
        engine.rootContext().setContextProperty("fixtureRecent", recent)
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

    def island(self, host: str) -> None:
        """The event island over the host's bar color: Pomodoro completion and volume."""
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "EventIslandHarness.qml")))
        window = engine.rootObjects()[0]
        island = window.findChild(QQuickItem, "eventIsland")
        state = window.findChild(QObject, "islandEventState")

        def run(target, source: str) -> None:
            expression = QQmlExpression(engine.rootContext(), target, source)
            expression.evaluate()
            if expression.hasError():
                raise RuntimeError(f"{source}: {expression.error().toString()}")

        run(window, "color = palette.window")
        scenes = (
            ("completion", "submit({kind:'completion',key:'pomodoro:completion',scope:'global',"
                           "title:'Foco concluído',detail:'Hora de uma pausa!'},Date.now())"),
            ("volume", "clear(); submit({kind:'audio',action:'volume',targetId:'speakers',"
                       "originScope:'profile:work',contextGeneration:2,value:65,"
                       "title:'Volume · 65%',detail:'Alto-falantes'},Date.now())"),
        )
        for name, source in scenes:
            run(state, source)
            QTest.qWait(120)
            self.save(f"island-{host}-{name}", window, self.scene_rect(island))
        window.close()
        engine.deleteLater()

    def bar_settings(self, host: str) -> None:
        """Configuration content only; Plasma owns the native dialog footer."""
        engine = self.engine()
        engine.load(QUrl.fromLocalFile(str(TESTS / "BarSettingsHarness.qml")))
        window = engine.rootObjects()[0]
        settings = window.findChild(QQuickItem, "barSettingsUnderTest")
        context = QQmlEngine.contextForObject(settings)

        def evaluate(source):
            expression = QQmlExpression(context, settings, source)
            expression.evaluate()
            if expression.hasError():
                raise RuntimeError(expression.error().toString())

        self.save(f"bar-{host}-settings", window)
        window.resize(320, 560)
        self.save(f"bar-{host}-settings-narrow", window)
        window.resize(520, 900)
        evaluate('setMenuOpen(true); cfg_menuIcon = "none"; cfg_showMenuLabel = false')
        self.save(f"bar-{host}-settings-expanded", window)
        window.resize(320, 240)
        name = window.findChild(QQuickItem, "menuLabelSetting")
        QQmlExpression(context, name, "forceActiveFocus(Qt.TabFocusReason)").evaluate()
        self.save(f"bar-{host}-settings-short-focus", window)
        window.close()
        engine.deleteLater()

    def workspace(self, host: str) -> None:
        """Real companion view/controller; no native layout or session access."""
        from test_workspace_view import FixtureSession
        from scripts.workspace_setup import WorkspaceController
        session = FixtureSession()
        template = json.loads((ROOT / "layouts/mac-inspired-topbar.json").read_text())
        controller = WorkspaceController(session, template, ["DP-1"])
        engine = self.engine()
        engine.rootContext().setContextProperty("workspaceController", controller)
        engine.load(QUrl.fromLocalFile(str(ROOT / "workspace/Workspace.qml")))
        if not engine.rootObjects():
            raise RuntimeError("workspace gallery window did not load")
        window = engine.rootObjects()[0]
        view = window.findChild(QQuickItem, "compositionView")

        def wait():
            for _ in range(200):
                QTest.qWait(10)
                if not controller.busy:
                    return
            raise RuntimeError("synthetic composition did not finish")

        try:
            controller.refresh("DP-1"); wait()
            view.setProperty("connector", "DP-1")
            view.setProperty("selectedPanels", [28])
            for width in (350, 420):
                window.resize(width, 620)
                self.save(f"workspace-{host}-selection-{width}", window)
            controller.prepareApply("DP-1", [28]); wait()
            for width in (350, 420):
                window.resize(width, 620)
                self.save(f"workspace-{host}-review-{width}", window)
            window.resize(350, 240)
            focus = window.findChild(QQuickItem, "compositionConfirm")
            QQmlExpression(QQmlEngine.contextForObject(focus), focus, "forceActiveFocus(Qt.TabFocusReason)").evaluate()
            self.save(f"workspace-{host}-short-focus", window)
            controller.discard()
            session.phase = "COMMITTED"
            controller.refresh("DP-1"); wait()
            focus = window.findChild(QQuickItem, "compositionRestore")
            QQmlExpression(QQmlEngine.contextForObject(focus), focus, "forceActiveFocus(Qt.TabFocusReason)").evaluate()
            self.save(f"workspace-{host}-committed-short-focus", window)
            window.resize(350, 620)
            self.save(f"workspace-{host}-committed", window)
            session.read_override = {"phase": "COMMITTED", "verificationUnavailable": True}
            controller.refresh(""); wait()
            self.save(f"workspace-{host}-unverified", window)
            session.read_override = None
            session.phase = "RECOVERY_REQUIRED"
            controller.refresh("DP-1"); wait()
            window.resize(350, 620)
            self.save(f"workspace-{host}-recovery", window)
        finally:
            window.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(engine, QEvent.DeferredDelete)

    def updates(self, host: str) -> None:
        """Actual service-free update window, synthetic separate CLI and history."""
        from scripts.updates_desktop import UpdatesController
        from scripts.updates_desktop_state import Store, history_key
        from scripts.updates_contract import result
        from datetime import datetime, timezone
        reference=dict(role='source', component='dock', origin='source-metadata',
                       version='1.2.3', commit=None, digest='a'*64)
        mode={'status':'update_available'}
        with tempfile.TemporaryDirectory(prefix='orla-updates-gallery-') as directory:
            root=Path(directory)
            def runner(_root, _reference, channel):
                status=mode['status'];version='2.0.0' if status=='update_available' else None
                url='https://github.com/caiolombello/orla-desktop/releases/tag/v2.0.0' if version else None
                reason='network_error' if status=='unavailable' else 'rate_limit' if status=='rate_limited' else None
                stamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                data=result(status,reason,'1.2.3',channel,stamp,version,url)
                helper=root/'fixture.py'
                helper.write_text('import time;time.sleep(.7);print('+repr(json.dumps(data))+');raise SystemExit('+str(2 if reason else 0)+')')
                return sys.executable,['-I','-B',str(helper)]
            controller=UpdatesController(ROOT,reference,runner=runner,storage_root=root,opener=lambda url:True)
            engine=self.engine();engine.rootContext().setContextProperty('updatesController',controller)
            engine.load(QUrl.fromLocalFile(str(ROOT/'workspace/Updates.qml')))
            if not engine.rootObjects():raise RuntimeError('updates gallery window did not load')
            window=engine.rootObjects()[0]
            def wait():
                for _ in range(300):
                    if not controller.busy:return
                    QTest.qWait(10)
                raise RuntimeError('synthetic check did not finish')
            try:
                for width in (320,350,420):
                    window.resize(width,720);self.save(f'updates-{host}-initial-{width}',window)
                window.resize(350,720);controller.check()
                self.save(f'updates-{host}-checking',window);wait()
                self.save(f'updates-{host}-newer',window)
                mode['status']='no_release';controller.check();wait()
                self.save(f'updates-{host}-no-release',window)
                mode['status']='rate_limited';controller.check();wait()
                self.save(f'updates-{host}-rate-limit',window)
                stale=result('update_available',None,'1.2.3','stable','2026-01-01T12:00:00Z',
                             '2.0.0','https://github.com/caiolombello/orla-desktop/releases/tag/v2.0.0')
                record=dict(attemptedAt=stale['checked_at'],completedAt='2026-01-01T12:00:01Z',result=stale)
                Store(root).save_history({'stable':dict(key=history_key(reference,'stable'),attempt=record,lastCompleted=record)})
                old_controller=controller
                controller=UpdatesController(ROOT,reference,runner=runner,storage_root=root,opener=lambda url:True)
                window.setProperty('controller',controller)
                self.save(f'updates-{host}-saved-stale-history',window)
                mode['status']='unavailable';controller.check();wait()
                self.save(f'updates-{host}-offline-history',window)
                window.resize(350,240)
                focus=window.findChild(QQuickItem,'updatesChannel');focus.forceActiveFocus(Qt.TabFocusReason)
                self.save(f'updates-{host}-short-channel',window)
                focus=window.findChild(QQuickItem,'updatesCheck');focus.forceActiveFocus(Qt.TabFocusReason)
                self.save(f'updates-{host}-short-retry',window)
                package=root/'data/plasma/plasmoids/org.caiodock.dock';package.mkdir(parents=True)
                (package/'metadata.json').write_text(json.dumps({'KPlugin':{'Id':'org.caiodock.dock','Version':'1.2.3'}}))
                controller=UpdatesController(ROOT,reference,runner=runner,storage_root=root,opener=lambda url:True)
                window.setProperty('controller',controller);window.resize(350,720)
                details=window.findChild(QQuickItem,'updatesDetails');details.setProperty('checked',True)
                self.save(f'updates-{host}-installed-details',window)
                controller._running_probe=lambda parent,done:done('found',['1.2.2'])
                controller.readRunning()
                self.save(f'updates-{host}-running-differs',window)
                details.setProperty('checked',False)
                window.resize(420,720)
                font=window.property('font');font.setPointSizeF(font.pointSizeF()*2);window.setProperty('font',font)
                self.save(f'updates-{host}-large-text',window)
            finally:
                wait();window.close();engine.deleteLater()
                QCoreApplication.sendPostedEvents(engine,QEvent.DeferredDelete)

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
    gallery.auto_contexts(host)
    gallery.profile_rename(host)
    gallery.profile_remove(host)
    gallery.saved_contexts(host)
    gallery.appearance_catalog(host)
    gallery.appearance_advanced(host)
    gallery.widget_order(host)
    gallery.bar(host)
    gallery.island(host)
    gallery.bar_settings(host)
    gallery.workspace(host)
    gallery.updates(host)
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


def private_bus(command: list[str]) -> list[str]:
    """Run a render on its own session bus: the dock's native models (MPRIS players,
    notifications) must never see the user's session, or captures show private data."""
    runner = shutil.which("dbus-run-session")
    return [runner, "--", *command] if runner else command


def main(argv: list[str]) -> int:
    if len(argv)>2 and argv[1]=='--render-updates':
        app=QGuiApplication.instance() or QGuiApplication([])
        gallery=Gallery(Path(argv[3]));gallery.updates(argv[2]);app.processEvents()
        if gallery.warnings:
            raise RuntimeError("\n".join(gallery.warnings))
        return 0
    if len(argv)>2 and argv[1]=='--updates-only':
        output=Path(argv[2]);output.mkdir(parents=True,exist_ok=True)
        for host in ('dark','light'):
            with tempfile.TemporaryDirectory(prefix='orla-updates-scheme-') as config:
                result=subprocess.run(private_bus([sys.executable,'-B',__file__,'--render-updates',host,str(output)]),
                    cwd=ROOT,env=host_environment(host,Path(config)),timeout=60)
                if result.returncode:return result.returncode
        return 0
    if len(argv) > 2 and argv[1] == "--render":
        return render(argv[2], Path(argv[3]))
    output = Path(argv[1]) if len(argv) > 1 else ROOT / ".runtime/design-gallery"
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.png"):
        stale.unlink()
    for host in ("dark", "light"):
        with tempfile.TemporaryDirectory(prefix=f"orla-gallery-{host}-") as config:
            result = subprocess.run(private_bus([sys.executable, "-B", __file__, "--render", host, str(output)]),
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
