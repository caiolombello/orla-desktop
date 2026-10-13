import os
import time
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Property, Signal, Slot, QUrl, Qt, QPointF
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class FixtureSession(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.values = dict(status="ready", canLock=True, canSuspend=True,
                           canLogout=True, canReboot=True, canShutdown=True)
        self.calls = []

    def update(self, **values):
        self.values.update(values)
        self.changed.emit()

    status = Property(str, lambda self: self.values["status"], notify=changed)
    canLock = Property(bool, lambda self: self.values["canLock"], notify=changed)
    canSuspend = Property(bool, lambda self: self.values["canSuspend"], notify=changed)
    canLogout = Property(bool, lambda self: self.values["canLogout"], notify=changed)
    canReboot = Property(bool, lambda self: self.values["canReboot"], notify=changed)
    canShutdown = Property(bool, lambda self: self.values["canShutdown"], notify=changed)

    @Slot()
    def lock(self):
        self.calls.append("lock")

    @Slot()
    def suspend(self):
        self.calls.append("suspend")

    @Slot()
    def requestLogout(self):
        self.calls.append("logout")

    @Slot()
    def requestReboot(self):
        self.calls.append("reboot")

    @Slot()
    def requestShutdown(self):
        self.calls.append("shutdown")

    @Slot(str)
    def open(self, kind):
        self.calls.append(kind)


class FixtureApplication(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.name = "Aplicativo sintético"
        self.active = True

    appName = Property(str, lambda self: self.name, notify=changed)
    hasActiveApplication = Property(bool, lambda self: self.active, notify=changed)


class FixtureControlCenter(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.values = dict(apiVersion=1, status="ready", available=True, isOpen=False, error="")
        self.calls = []
        self.on_open = None
        self.on_release = None

    def update(self, **values):
        self.values.update(values); self.changed.emit()

    apiVersion = Property(int, lambda self: self.values["apiVersion"], notify=changed)
    status = Property(str, lambda self: self.values["status"], notify=changed)
    available = Property(bool, lambda self: self.values["available"], notify=changed)
    isOpen = Property(bool, lambda self: self.values["isOpen"], notify=changed)
    error = Property(str, lambda self: self.values["error"], notify=changed)

    @Slot(QObject, QObject, result=bool)
    def open(self, host, anchor):
        self.calls.append(("open", host, anchor)); self.update(isOpen=True)
        if self.on_open: self.on_open()
        return True

    @Slot()
    def release(self):
        self.calls.append(("release",))
        if self.on_release: self.on_release()
        self.update(isOpen=False)


class BarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.session = FixtureSession()
        self.application = FixtureApplication()
        self.control_center = FixtureControlCenter()
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.rootContext().setContextProperty("fixtureSession", self.session)
        self.engine.rootContext().setContextProperty("fixtureApplication", self.application)
        self.engine.rootContext().setContextProperty("fixtureControlCenter", self.control_center)
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("BarHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.bar = self.window.findChild(QQuickItem, "barUnderTest")
        QTest.qWait(30)

    def tearDown(self):
        if self.engine.rootObjects():
            self.window.close()
            self.window.deleteLater()
            QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
            self.app.processEvents()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.bar, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def wait_property(self, target, name, expected):
        deadline = time.monotonic() + 1.0
        while target.property(name) != expected and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertEqual(target.property(name), expected, name)

    def key_window(self):
        menu = self.window.findChild(QObject, "orlaMenu")
        if menu is not None and menu.property("visible"):
            return next(window for window in self.app.topLevelWindows()
                        if window != self.window and window.isVisible() and window.flags() & Qt.Popup)
        return self.window

    def wait_restored_focus(self, button):
        # The offscreen plugin does not reactivate a transient popup's parent.
        # First prove the control owns logical focus, then simulate compositor
        # activation; this is not proof of native Wayland activation behavior.
        self.wait_property(button, "focus", True)
        self.window.requestActivate()
        self.wait_property(button, "activeFocus", True)

    def test_cc_is_opt_in_and_keyboard_dispatches_exact_same_window_anchor(self):
        button = self.item("barControlCenterButton")
        self.assertFalse(button.property("visible"))
        self.assertTrue(self.bar.property("showOrlaMenu"))
        self.evaluate("showOrlaMenu = false; showApplicationName = false; showControlCenter = true")
        self.assertFalse(self.item("orlaMenuButton").property("visible"))
        self.assertTrue(button.property("visible"))
        self.assertTrue(button.property("enabled"))
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(self.control_center.calls, [("open", self.bar, button)])
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(self.control_center.calls[-1], ("release",))
        self.assertEqual(self.session.calls, [])

    def test_cc_unavailable_incompatible_and_invalid_host_never_dispatch(self):
        self.evaluate("showControlCenter = true")
        button = self.item("barControlCenterButton")
        for values in (dict(status="unavailable", available=False), dict(status="ambiguous", available=False),
                       dict(status="ready", available=True, apiVersion=2)):
            self.control_center.update(**values)
            self.assertFalse(button.property("enabled"))
            self.evaluate("clicked()", button)
            self.assertEqual(self.control_center.calls, [])
        self.control_center.update(apiVersion=1, status="ready", available=True)
        self.evaluate("controlCenterHost = null")
        self.assertFalse(button.property("enabled"))
        self.evaluate("clicked()", button)
        self.assertEqual(self.control_center.calls, [])
        self.assertEqual(self.session.calls, [])

    def test_cc_hide_and_client_replacement_release_only_its_lease(self):
        self.evaluate("showControlCenter = true")
        button = self.item("barControlCenterButton")
        self.evaluate("clicked()", button)
        self.evaluate("showControlCenter = false")
        self.assertEqual(self.control_center.calls, [("open", self.bar, button), ("release",)])
        self.evaluate("showControlCenter = true")
        self.evaluate("clicked()", button)
        self.evaluate("controlCenterClient = null")
        self.assertEqual(self.control_center.calls[-1], ("release",))
        self.assertFalse(button.property("enabled"))
        self.assertEqual(self.session.calls, [])

    def test_cc_client_swapped_inside_open_releases_exact_dispatch_client(self):
        replacement = FixtureControlCenter()
        self.evaluate("showControlCenter = true")
        button = self.item("barControlCenterButton")
        self.control_center.on_open = lambda: self.bar.setProperty("controlCenterClient", replacement)
        self.assertFalse(self.evaluate("toggleControlCenter()"))
        self.assertEqual(self.control_center.calls, [("open", self.bar, button), ("release",)])
        self.assertFalse(self.control_center.values["isOpen"])
        self.evaluate("showControlCenter = false")
        self.assertEqual(replacement.calls, [])
        self.assertEqual(self.session.calls, [])

    def test_cc_open_cancels_when_context_changes_even_if_it_returns_to_same_values(self):
        replacement = FixtureControlCenter()
        self.evaluate("showControlCenter = true")
        button = self.item("barControlCenterButton")
        def client_cycle():
            self.bar.setProperty("controlCenterClient", replacement)
            self.bar.setProperty("controlCenterClient", self.control_center)
        def availability_cycle():
            self.control_center.update(status="ambiguous", available=False)
            self.control_center.update(status="ready", available=True)
        mutations = (
            lambda: self.evaluate("showControlCenter = false; showControlCenter = true"),
            lambda: self.bar.setProperty("controlCenterHost", self.window.contentItem()),
            client_cycle, availability_cycle,
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.__name__):
                self.bar.setProperty("controlCenterHost", self.bar)
                self.control_center.calls.clear()
                self.control_center.on_open = mutation
                self.assertFalse(self.evaluate("toggleControlCenter()"))
                self.assertEqual(self.control_center.calls, [("open", self.bar, button), ("release",)])
                self.assertFalse(self.control_center.values["isOpen"])
                self.evaluate("showControlCenter = false; showControlCenter = true")
                self.assertEqual(self.control_center.calls.count(("release",)), 1)
                self.assertEqual(replacement.calls, [])
        self.control_center.on_open = None
        self.assertEqual(self.session.calls, [])

    def test_cc_release_callback_cannot_reenter_open_or_release_a_new_client(self):
        replacement = FixtureControlCenter()
        reentrant_results = []
        self.evaluate("showControlCenter = true")
        self.assertTrue(self.evaluate("toggleControlCenter()"))
        def releasing():
            self.bar.setProperty("controlCenterClient", replacement)
            reentrant_results.append(self.evaluate("toggleControlCenter()"))
            reentrant_results.append(self.evaluate("releaseControlCenter()"))
        self.control_center.on_release = releasing
        self.assertTrue(self.evaluate("toggleControlCenter()"))
        self.assertEqual(reentrant_results, [False, False])
        self.assertFalse(self.control_center.values["isOpen"])
        self.assertEqual(self.control_center.calls.count(("release",)), 1)
        self.assertEqual(replacement.calls, [])
        self.assertTrue(self.evaluate("toggleControlCenter()"))
        self.assertEqual(replacement.calls, [("open", self.bar, self.item("barControlCenterButton"))])
        self.assertEqual(self.session.calls, [])

    def test_cc_open_callback_cannot_dispatch_a_nested_open(self):
        results = []
        self.evaluate("showControlCenter = true")
        self.control_center.on_open = lambda: results.append(self.evaluate("toggleControlCenter()"))
        self.assertTrue(self.evaluate("toggleControlCenter()"))
        self.assertEqual(results, [False])
        self.assertEqual(self.control_center.calls, [("open", self.bar, self.item("barControlCenterButton"))])
        self.assertEqual(self.session.calls, [])

    def test_cc_tab_focus_has_two_pixel_ring_and_reduced_motion(self):
        self.evaluate("showOrlaMenu = false; showApplicationName = false; showControlCenter = true; forceActiveFocus()")
        QTest.keyClick(self.window, Qt.Key_Tab)
        button = self.item("barControlCenterButton")
        self.assertTrue(button.property("visualFocus"))
        self.assertEqual(self.evaluate("background.border.width", button), 2)
        self.assertTrue(self.evaluate("background.visible", button))
        self.evaluate("reducedMotion = true")
        animation = self.window.findChild(QObject, "barControlCenterHoverAnimation")
        self.assertIsNotNone(animation)
        self.assertEqual(animation.property("duration"), 0)
        self.assertEqual(self.control_center.calls, [])
        self.assertEqual(self.session.calls, [])

    def test_cc_cross_window_host_refuses_and_host_replacement_releases(self):
        from PySide6.QtQuick import QQuickWindow
        other = QQuickWindow()
        try:
            self.evaluate("showControlCenter = true")
            self.bar.setProperty("controlCenterHost", other.contentItem())
            button = self.item("barControlCenterButton")
            self.assertFalse(button.property("enabled"))
            self.evaluate("clicked()", button)
            self.assertEqual(self.control_center.calls, [])
            self.bar.setProperty("controlCenterHost", self.bar)
            self.evaluate("clicked()", button)
            self.bar.setProperty("controlCenterHost", self.window.contentItem())
            self.assertEqual(self.control_center.calls, [("open", self.bar, button), ("release",)])
        finally:
            other.deleteLater()
            QCoreApplication.sendPostedEvents(other, QEvent.DeferredDelete)

    def test_cc_settings_are_opt_in_and_presentation_preset_preserves_choice(self):
        path = Path(__file__).resolve().parents[1] / "bar/contents/ui/BarSettings.qml"
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(path)))
        settings = component.create()
        self.assertIsNotNone(settings, [error.toString() for error in component.errors()])
        try:
            self.assertTrue(settings.property("cfg_showOrlaMenu"))
            self.assertFalse(settings.property("cfg_showControlCenter"))
            self.evaluate("cfg_showOrlaMenu = false; cfg_showControlCenter = true", settings)
            self.evaluate("clicked()", settings.findChild(QQuickItem, "applyMacInspiredPreset"))
            self.assertFalse(settings.property("cfg_showOrlaMenu"))
            self.assertTrue(settings.property("cfg_showControlCenter"))
        finally:
            settings.deleteLater()
            QCoreApplication.sendPostedEvents(settings, QEvent.DeferredDelete)

    def test_cc_error_is_plain_bounded_and_shows_real_status(self):
        self.evaluate("showControlCenter = true")
        self.control_center.update(status="ambiguous", available=False, error="<b>Central indisponível</b>" + "x" * 1000)
        self.assertEqual(self.bar.property("controlCenterStatus"), "ambiguous")
        self.assertLessEqual(len(self.bar.property("controlCenterError")), 240)
        tooltip = self.item("barControlCenterTooltipText")
        self.assertEqual(self.evaluate("Number(textFormat)", tooltip), 0)  # Text.PlainText
        self.assertEqual(tooltip.property("text"), self.bar.property("controlCenterError"))
        self.assertFalse(self.item("barControlCenterButton").property("enabled"))
        self.assertEqual(self.control_center.calls, [])

    def test_icon_only_label_control_and_text_only_fallback(self):
        button = self.item("orlaMenuButton")
        label = self.item("orlaMenuLabel")
        self.evaluate("showMenuLabel = false; compactHeight = true")
        QTest.qWait(20)
        self.assertFalse(label.property("visible"))
        self.assertEqual(self.bar.property("implicitHeight"), 28)
        self.assertLessEqual(button.property("implicitWidth"), 36)
        self.evaluate("menuIcon = 'none'")
        QTest.qWait(20)
        self.assertTrue(label.property("visible"))
        self.assertGreater(button.property("implicitWidth"), 36)
        self.evaluate("showMenuLabel = true; compactHeight = false; menuIcon = 'orla'")
        QTest.qWait(20)
        self.assertTrue(label.property("visible"))
        self.assertEqual(self.bar.property("implicitHeight"), 32)
        self.assertGreater(button.property("implicitWidth"), 36)

    def test_popup_opens_below_own_control_outside_tiny_panel_window(self):
        self.window.setHeight(28)
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.key_window(), Qt.Key_Space)
        menu = self.window.findChild(QObject, "orlaMenu")
        self.wait_property(menu, "opened", True)
        top = self.evaluate("contentItem.mapToGlobal(0, 0).y - topPadding", menu)
        bottom = self.evaluate("mapToGlobal(0, height).y", button)
        self.assertGreaterEqual(top, bottom)
        self.assertLessEqual(top - bottom, 4)
        popup_window = self.key_window()
        self.assertNotEqual(popup_window, self.window)
        geometry = popup_window.geometry()
        self.assertTrue(popup_window.screen().availableGeometry().contains(geometry))
        QTest.keyClick(popup_window, Qt.Key_Escape)
        self.wait_property(menu, "visible", False)
        self.wait_restored_focus(button)
        self.assertEqual(self.session.calls, [])

    def test_popup_is_constrained_to_screen_at_right_edge(self):
        bounds = self.window.screen().availableGeometry()
        self.window.setWidth(48)
        self.window.setHeight(28)
        self.window.setPosition(bounds.right() - 47, bounds.top())
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.key_window(), Qt.Key_Space)
        menu = self.window.findChild(QObject, "orlaMenu")
        self.wait_property(menu, "opened", True)
        popup_window = self.key_window()
        self.assertTrue(bounds.contains(popup_window.geometry()))
        self.assertGreater(popup_window.width(), self.window.width())
        QTest.keyClick(popup_window, Qt.Key_Escape)
        self.wait_property(menu, "visible", False)
        self.wait_restored_focus(button)
        self.assertEqual(self.session.calls, [])

    def test_preset_sets_only_presentation_controls_and_remains_customizable(self):
        path = Path(__file__).resolve().parents[1] / "bar/contents/ui/BarSettings.qml"
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(path)))
        settings = component.create()
        self.assertIsNotNone(settings, [error.toString() for error in component.errors()])
        try:
            self.evaluate("cfg_menuLabel = 'Meu menu'; cfg_menuIcon = 'none'; cfg_showMenuLabel = true; cfg_compactHeight = false; cfg_showApplicationName = false", settings)
            preset = settings.findChild(QQuickItem, "applyMacInspiredPreset")
            self.assertIsNotNone(preset)
            self.evaluate("clicked()", preset)
            self.assertEqual(settings.property("cfg_menuLabel"), "Meu menu")
            self.assertEqual(settings.property("cfg_menuIcon"), "orla")
            self.assertFalse(settings.property("cfg_showMenuLabel"))
            self.assertTrue(settings.property("cfg_compactHeight"))
            self.assertTrue(settings.property("cfg_showApplicationName"))
            self.evaluate("cfg_showMenuLabel = true; cfg_compactHeight = false; cfg_showApplicationName = false", settings)
            self.assertTrue(settings.property("cfg_showMenuLabel"))
            self.assertFalse(settings.property("cfg_compactHeight"))
            self.assertFalse(settings.property("cfg_showApplicationName"))
        finally:
            settings.deleteLater()
            QCoreApplication.sendPostedEvents(settings, QEvent.DeferredDelete)

    def test_hidden_availability_row_does_not_leave_a_menu_gap(self):
        self.evaluate("forceActiveFocus()", self.item("orlaMenuButton"))
        QTest.keyClick(self.window, Qt.Key_Space)
        self.wait_property(self.window.findChild(QObject, "orlaMenu"), "opened", True)
        availability = self.item("sessionAvailability")
        self.assertFalse(availability.property("visible"))
        self.assertEqual(availability.height(), 0)
        self.session.update(status="loading")
        self.assertTrue(availability.property("visible"))
        # Visible rows take the menu's row height (compact, macOS-like menus).
        self.assertEqual(availability.height(), availability.property("implicitHeight"))
        self.assertGreater(availability.height(), 20)
        self.assertFalse(availability.property("enabled"))
        self.session.update(status="ready")
        self.assertEqual(availability.height(), 0)
        self.assertEqual(self.session.calls, [])

    def test_full_sized_popup_host_keeps_menu_outside_panel_and_closes_passively(self):
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(Path(__file__).with_name("PopupHostHarness.qml"))))
        host = component.create()
        self.assertIsNotNone(host, [error.toString() for error in component.errors()])
        try:
            self.bar.setProperty("popupHost", host)
            self.assertEqual(self.bar.property("popupHost"), host)
            self.window.setHeight(28)
            button = self.item("orlaMenuButton")
            self.evaluate("forceActiveFocus()", button)
            QTest.keyClick(self.window, Qt.Key_Space)
            menu = self.window.findChild(QObject, "orlaMenu")
            self.wait_property(menu, "opened", True)
            self.assertTrue(host.isVisible())
            self.assertGreater(host.height(), self.window.height())
            self.assertEqual(self.evaluate("parent", menu), host.property("hostItem"))
            self.assertEqual(self.evaluate("popupType", menu), 0)  # Popup.Item inside full host
            self.assertEqual(self.evaluate("contentItem.mapToGlobal(0, 0).y - topPadding", menu), host.y())
            self.assertGreaterEqual(host.y(), self.evaluate("mapToGlobal(0, height).y", button))
            self.application.active = False
            self.application.changed.emit()
            self.assertEqual(self.item("activeApplicationName").property("text"), "Aplicativo sintético")
            QTest.keyClick(host, Qt.Key_Escape)
            self.wait_property(menu, "visible", False)
            self.assertFalse(host.isVisible())
            self.wait_restored_focus(button)
            self.assertEqual(self.session.calls, [])
            # Native host deactivation must close the same menu, not dispatch.
            QTest.keyClick(self.window, Qt.Key_Space)
            self.wait_property(menu, "opened", True)
            host.setVisible(False)
            self.wait_property(menu, "visible", False)
            self.assertEqual(self.session.calls, [])
            self.assertTrue(self.evaluate("open('about')"))
            about = self.window.findChild(QObject, "aboutOrlaPopup")
            self.wait_property(about, "opened", True)
            self.assertTrue(host.isVisible())
            self.assertGreater(host.height(), self.window.height())
            self.assertEqual(self.evaluate("parent", about), host.property("hostItem"))
            host.setVisible(False)
            self.wait_property(about, "visible", False)
            self.assertEqual(self.session.calls, [])
        finally:
            self.bar.setProperty("popupHost", None)
            host.close()
            host.deleteLater()
            QCoreApplication.sendPostedEvents(host, QEvent.DeferredDelete)

    def test_external_tooltip_remains_visible_outside_short_panel_and_allows_click(self):
        button = self.item("orlaMenuButton")
        self.window.setHeight(24)
        self.engine.rootContext().setContextProperty("fixtureTooltipButton", button)
        self.engine.rootContext().setContextProperty("fixtureTooltipBar", self.bar)
        component = QQmlComponent(self.engine)
        component.setData(b"""
            import QtQuick
            import QtQuick.Window
            Window {
                flags: Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowTransparentForInput
                    | Qt.WindowDoesNotAcceptFocus
                width: 110
                height: 28
                x: fixtureTooltipButton.mapToGlobal(0, 0).x
                y: fixtureTooltipButton.mapToGlobal(0, fixtureTooltipButton.height).y + 4
                visible: fixtureTooltipButton.hovered && !fixtureTooltipButton.down
                    && fixtureTooltipBar.menuIsOpen !== true
                function hideImmediately() { close(); }
                Text { anchors.centerIn: parent; text: "Menu Orla" }
            }
        """, QUrl())
        tooltip = component.create()
        self.assertIsNotNone(tooltip, [error.toString() for error in component.errors()])
        try:
            self.bar.setProperty("menuTooltipBackend", tooltip)
            self.evaluate("compactHeight = true; showMenuLabel = false")
            QTest.qWait(30)
            point = button.mapToScene(QPointF(button.width() / 2, button.height() / 2)).toPoint()
            QTest.mouseMove(self.window, point)
            QTest.qWait(1200)
            self.assertTrue(tooltip.property("visible"))
            self.assertTrue(button.property("hoverEnabled"))
            self.assertTrue(button.property("hovered"))
            global_point = button.mapToGlobal(QPointF(button.width() / 2, button.height() / 2)).toPoint()
            self.assertFalse(tooltip.geometry().contains(global_point))
            presses = []
            # Mouse activation is the regression boundary; keyboard activation
            # alone never proved the hovered tooltip leaves the button reachable.
            menu = self.window.findChild(QObject, "orlaMenu")
            menu.aboutToShow.connect(lambda: presses.append("opened"))
            QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
            self.wait_property(menu, "opened", True)
            self.assertEqual(presses, ["opened"])
            self.assertFalse(tooltip.property("visible"))
            QTest.keyClick(self.key_window(), Qt.Key_Escape)
            self.wait_property(menu, "visible", False)
            self.wait_restored_focus(button)
            # Feedback and pointer activation recover after dismissal/re-entry.
            QTest.mouseMove(self.window, QPointF(self.window.width() - 1, 20).toPoint())
            QTest.mouseMove(self.window, point)
            QTest.qWait(1200)
            self.assertTrue(tooltip.property("visible"))
            QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, point)
            self.wait_property(menu, "opened", True)
            self.assertEqual(presses, ["opened", "opened"])
            self.assertFalse(tooltip.property("visible"))
            self.assertEqual(self.session.calls, [])
        finally:
            self.evaluate("close()", self.window.findChild(QObject, "orlaMenu"))
            self.bar.setProperty("menuTooltipBackend", None)
            self.evaluate("close()", tooltip)
            tooltip.deleteLater()
            QCoreApplication.sendPostedEvents(tooltip, QEvent.DeferredDelete)

    @unittest.skipUnless(Path("/usr/lib64/qt6/qml/org/kde/plasma/core/qmldir").exists(),
                         "Requires the optional installed PlasmaCore native adapter")
    def test_native_host_keeps_all_menu_rows_in_its_allocated_viewport_on_reopen(self):
        self.engine.addImportPath("/usr/lib64/qt6/qml")
        path = Path(__file__).resolve().parents[1] / "bar/contents/ui/NativePopupHost.qml"
        component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(path)))
        host = component.create()
        self.assertIsNotNone(host, [error.toString() for error in component.errors()])
        try:
            self.bar.setProperty("popupHost", host)
            menu = self.window.findChild(QObject, "orlaMenu")
            button = self.item("orlaMenuButton")
            QTest.mouseMove(self.window, QPointF(self.window.width() - 1, 20).toPoint())
            for _ in range(2):
                self.evaluate("forceActiveFocus()", button)
                QTest.keyClick(self.window, Qt.Key_Space)
                self.wait_property(menu, "opened", True)
                QTest.qWait(1000)
                # Test visible bounds, rather than an internal overlay formula:
                # the complete menu and final enabled row must fit its own host.
                main = host.property("mainItem")
                content = menu.property("contentItem")
                self.assertAlmostEqual(menu.property("height"), menu.property("implicitHeight"), delta=1,
                    msg=f"iteration={_}; host={host.width()}x{host.height()}; main={main.width()}x{main.height()}; overlay={content.parentItem().parentItem().x()},{content.parentItem().parentItem().y()}; menuXY={menu.property('x')},{menu.property('y')}; popupXY={content.parentItem().x()},{content.parentItem().y()}; mainXY={main.x()},{main.y()}")
                self.assertGreaterEqual(main.height(), menu.property("height"))
                self.assertGreaterEqual(content.mapToScene(QPointF(0, 0)).y(), 0)
                self.assertLessEqual(content.mapToScene(QPointF(0, content.height())).y(), host.height())
                last = self.item("sessionShutdown")
                self.assertGreaterEqual(self.evaluate("mapToItem(parent.parent, 0, 0).y", last), 0)
                self.assertLessEqual(self.evaluate("mapToItem(parent.parent, 0, height).y", last), content.height())
                for _step in range(menu.property("count")):
                    if last.property("highlighted"):
                        break
                    QTest.keyClick(host, Qt.Key_Down)
                self.assertTrue(last.property("highlighted"))
                QTest.keyClick(host, Qt.Key_Escape)
                self.wait_property(menu, "visible", False)
                self.assertFalse(host.isVisible())
                self.wait_restored_focus(button)
                self.assertEqual(self.session.calls, [])
        finally:
            self.bar.setProperty("popupHost", None)
            host.close()
            host.deleteLater()
            QCoreApplication.sendPostedEvents(host, QEvent.DeferredDelete)

    def test_loading_and_unavailable_never_dispatch_session_actions(self):
        for status in ("loading", "unavailable"):
            self.session.update(status=status)
            for action in ("lock", "suspend", "logout", "reboot", "shutdown"):
                self.assertFalse(self.evaluate(f"requestSession('{action}')"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


    def item(self, name):
        result = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(result, name)
        return result

    def test_menu_navigation_is_passive_and_explicit_actions_recheck_capabilities(self):
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.key_window(), Qt.Key_Space)
        QTest.qWait(20)
        for key in (Qt.Key_Down, Qt.Key_Down, Qt.Key_Up):
            QTest.keyClick(self.key_window(), key)
        self.assertEqual(self.session.calls, [])
        self.session.update(canReboot=False)
        self.assertFalse(self.item("sessionReboot").property("enabled"))
        self.assertFalse(self.evaluate("requestSession('reboot')"))
        for action in ("lock", "suspend", "logout", "shutdown"):
            self.assertTrue(self.evaluate(f"requestSession('{action}')"))
        self.assertEqual(self.session.calls, ["lock", "suspend", "logout", "shutdown"])
        self.session.update(canReboot=True)
        self.assertTrue(self.evaluate("requestSession('reboot')"))
        self.assertEqual(self.session.calls[-1], "reboot")
        self.assertFalse(self.evaluate("requestSession('arbitrary')"))
        self.assertEqual(self.warnings, [])


    def test_application_and_button_names_are_plain_bounded_and_optional(self):
        self.application.name = "<b>" + "X" * 5000 + "\nPrivate document title"
        self.application.changed.emit()
        title = self.item("activeApplicationName")
        self.assertLessEqual(len(title.property("text")), 160)
        self.assertEqual(self.evaluate("textFormat", title), 0)
        self.evaluate("menuLabel = '<b>' + 'X'.repeat(5000)")
        self.assertLessEqual(len(self.item("orlaMenuButton").property("text")), 32)
        self.evaluate("showApplicationName = false")
        self.assertFalse(title.property("visible"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])

    def test_compact_menu_keeps_its_icon_inside_and_keyboard_accessible(self):
        button = self.item("orlaMenuButton")
        icon = self.item("orlaMenuIcon")
        label = self.item("orlaMenuLabel")
        for width in (48, 72, 96, 400):
            self.window.setWidth(width)
            QTest.qWait(30)
            self.assertTrue(icon.property("visible"))
            self.assertGreaterEqual(self.evaluate("mapToItem(parent.parent, 0, 0).x", icon), 0)
            self.assertLessEqual(self.evaluate("mapToItem(parent.parent, width, 0).x", icon), button.width())
            if label.property("visible"):
                self.assertGreaterEqual(label.x(), icon.x() + icon.width() + 4)
                self.assertLessEqual(label.x() + label.width(), button.property("availableWidth"))
        self.assertTrue(label.property("visible"))
        self.window.setWidth(48)
        QTest.qWait(30)
        self.assertFalse(label.property("visible"))
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.key_window(), Qt.Key_Space)
        menu = self.window.findChild(QObject, "orlaMenu")
        self.wait_property(menu, "opened", True)
        QTest.keyClick(self.key_window(), Qt.Key_Escape)
        self.wait_property(menu, "visible", False)
        self.wait_restored_focus(button)
        self.assertEqual(self.session.calls, [])


    def test_menu_items_dispatch_their_own_action_and_revoked_actions_stay_passive(self):
        for name, action, capability in (("sessionLock", "lock", "canLock"),
                ("sessionSuspend", "suspend", "canSuspend"),
                ("sessionLogout", "logout", "canLogout"),
                ("sessionReboot", "reboot", "canReboot"),
                ("sessionShutdown", "shutdown", "canShutdown")):
            self.session.calls.clear()
            self.evaluate("triggered()", self.item(name))
            self.assertEqual(self.session.calls, [action])
            self.session.update(**{capability: False})
            self.evaluate("triggered()", self.item(name))
            self.assertEqual(self.session.calls, [action])
            self.session.update(**{capability: True})
        self.assertEqual(self.warnings, [])

    def test_links_are_explicit_and_about_does_not_open_external_applications(self):
        self.evaluate("triggered()", self.item("aboutOrla"))
        self.assertEqual(self.session.calls, [])
        for name, expected in (("aboutSystem", "system"), ("systemSettings", "settings"), ("configureBar", "configure")):
            self.evaluate("triggered()", self.item(name))
            self.assertEqual(self.session.calls[-1], expected)
        self.assertFalse(self.evaluate("open('arbitrary command')"))
        self.assertEqual(self.session.calls, ["system", "settings", "configure"])
        self.assertEqual(self.warnings, [])

    def test_mock_backends_prevent_native_adapters_even_on_a_supported_host(self):
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertEqual(self.bar.property("sessionStatus"), "ready")
        self.evaluate("hostVersion = '6.8.0'; sessionBackend = null; applicationBackend = null")
        self.assertEqual(self.bar.property("sessionStatus"), "unavailable")
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertFalse(self.evaluate("requestSession('shutdown')"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])

    def test_transport_error_is_visible_without_optimistic_success(self):
        self.evaluate("sessionBackend = ({status: 'ready', canShutdown: true, requestShutdown: function() { throw new Error('private receiver details'); }})")
        self.assertFalse(self.evaluate("requestSession('shutdown')"))
        self.assertIn("Não foi possível", self.bar.property("actionError"))
        self.assertTrue(self.item("sessionActionError").property("visible"))
        self.assertNotIn("private receiver", self.bar.property("actionError"))
        self.assertEqual(self.session.calls, [])
        self.evaluate("sessionBackend = fixtureSession")
        self.assertEqual(self.bar.property("actionError"), "")
        self.assertTrue(self.evaluate("requestSession('shutdown')"))
        self.assertEqual(self.session.calls, ["shutdown"])
        self.assertEqual(self.bar.property("sessionStatus"), "ready")
        self.assertEqual(self.bar.property("actionError"), "")
        self.assertEqual(self.warnings, [])

    def test_escape_closes_the_menu_without_dispatch_and_returns_to_button(self):
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.key_window(), Qt.Key_Space)
        menu = self.window.findChild(QObject, "orlaMenu")
        self.wait_property(menu, "opened", True)
        QTest.keyClick(self.key_window(), Qt.Key_Escape)
        self.wait_property(menu, "visible", False)
        self.wait_restored_focus(button)
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


    def test_application_name_is_preserved_from_menu_entry_until_closed(self):
        menu = self.window.findChild(QObject, "orlaMenu")
        self.evaluate("enter = Qt.createQmlObject('import QtQuick; Transition { PauseAnimation { duration: 120 } }', this)", menu)
        self.evaluate("exit = Qt.createQmlObject('import QtQuick; Transition { PauseAnimation { duration: 120 } }', this)", menu)
        # A focus change can occur before opened becomes true. The signal is
        # emitted by real Menu.open(); the boundary remains our synthetic source.
        def lose_active_application():
            self.application.active = False
            self.application.name = ""
            self.application.changed.emit()
        menu.aboutToShow.connect(lose_active_application)
        button = self.item("orlaMenuButton")
        self.evaluate("forceActiveFocus()", button)
        QTest.keyClick(self.key_window(), Qt.Key_Space)
        self.assertFalse(menu.property("opened"))
        self.assertEqual(self.item("activeApplicationName").property("text"), "Aplicativo sintético")
        self.wait_property(menu, "opened", True)
        self.application.active = True
        self.application.name = "Segundo aplicativo"
        self.application.changed.emit()
        self.assertEqual(self.item("activeApplicationName").property("text"), "Aplicativo sintético")
        QTest.keyClick(self.key_window(), Qt.Key_Escape)
        self.assertEqual(self.item("activeApplicationName").property("text"), "Aplicativo sintético")
        self.wait_property(menu, "visible", False)
        self.assertEqual(self.item("activeApplicationName").property("text"), "Segundo aplicativo")
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


    def test_active_unnamed_and_whitespace_apps_are_distinct_from_no_active_app(self):
        title = self.item("activeApplicationName")
        self.application.active = True
        for name in ("", " \t\n ", " " * 500):
            self.application.name = name
            self.application.changed.emit()
            self.assertEqual(title.property("text"), "Aplicativo")
        self.application.name = "  Aplicativo real  "
        self.application.changed.emit()
        self.assertEqual(title.property("text"), "Aplicativo real")
        # An idle source must not show an obsolete name from its previous task.
        self.application.active = False
        self.application.changed.emit()
        self.assertEqual(title.property("text"), "Área de trabalho")
        self.assertFalse(self.bar.property("nativeApplicationLoaded"))
        self.assertFalse(self.bar.property("nativeSessionLoaded"))
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
