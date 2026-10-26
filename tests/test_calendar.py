import os
from pathlib import Path
import re
import stat
import unittest


def _isolated_environment_valid():
    if os.environ.get("ORLA_CALENDAR_TEST_ISOLATED") != "1":
        return False
    token = os.environ.get("ORLA_CALENDAR_TEST_TOKEN", "")
    if re.fullmatch(r"[0-9a-f]{32}", token) is None:
        return False
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return False
    if os.environ.get("QT_QUICK_BACKEND") != "software":
        return False
    if os.environ.get("QT_QUICK_CONTROLS_STYLE") not in ("Fusion", "org.kde.desktop"):
        return False
    if os.environ.get("PYTHONPATH") != str(Path(__file__).resolve().parent):
        return False
    if any(os.environ.get(key) for key in (
            "DBUS_STARTER_ADDRESS", "DBUS_STARTER_BUS_TYPE", "DISPLAY",
            "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_SESSION_TYPE")):
        return False
    xdg_paths = []
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
        value = os.environ.get(key, "")
        path = Path(value)
        if not value or not path.is_absolute() or not path.is_dir():
            return False
        if stat.S_IMODE(path.stat().st_mode) != 0o700:
            return False
        xdg_paths.append(path)
    parents = {path.parent.resolve() for path in xdg_paths}
    if len(parents) != 1:
        return False
    root = parents.pop()
    absent_bus = root / "absent-session-bus"
    if absent_bus.exists():
        return False
    return os.environ.get("DBUS_SESSION_BUS_ADDRESS") == f"unix:path={absent_bus}"


_ISOLATED = _isolated_environment_valid()

if _ISOLATED:
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtGui import QColor, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest


@unittest.skipUnless(_ISOLATED, "Use tests/run_calendar_tests.py for an isolated Qt process")
class CalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("CalendarHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.calendar = self.window.findChild(QQuickItem, "calendarUnderTest")
        QTest.qWait(80)

    def tearDown(self):
        self.window.close()
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source):
        expression = QQmlExpression(self.engine.rootContext(), self.calendar, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def visual_items(self, item):
        yield item
        for child in item.childItems():
            yield from self.visual_items(child)

    def contrast_ratio(self, foreground, background):
        def luminance(color):
            channels = []
            for channel in (color.redF(), color.greenF(), color.blueF()):
                channels.append(channel / 12.92 if channel <= 0.04045
                                else ((channel + 0.055) / 1.055) ** 2.4)
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
        lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

    def test_inactive_or_disabled_calendar_does_not_load_pim(self):
        self.evaluate("active = false; fixtureEvents = null; usePimEvents = true")
        self.assertEqual(self.evaluate("enabledPlugins.length"), 0)
        self.evaluate("active = true; usePimEvents = false")
        self.assertEqual(self.evaluate("enabledPlugins.length"), 0)
        self.assertEqual(self.evaluate("agendaEvents.length"), 0)
        self.assertEqual(self.evaluate("providerState"), "disabled")
        self.assertTrue(self.window.findChild(QObject, "calendarEmptyState").property("visible"))
        self.assertEqual(self.warnings, [])

    def test_observable_empty_states_do_not_claim_provider_readiness(self):
        self.evaluate("usePimEvents = true; pimPluginMetadataAvailableOverride = false")
        self.assertEqual(self.evaluate("providerState"), "plugin-metadata-missing")
        self.assertIn("não foi encontrado", self.window.findChild(QObject, "calendarEmptyState").property("text"))
        self.evaluate("pimPluginMetadataAvailableOverride = true")
        self.assertEqual(self.evaluate("providerState"), "no-events-observed")
        empty_text = self.window.findChild(QObject, "calendarEmptyState").property("text")
        self.assertIn("Nenhum evento foi recebido", empty_text)
        self.assertIn("KDE PIM indisponível", empty_text)
        QTest.qWait(150)
        self.assertEqual(self.evaluate("providerState"), "no-events-observed")
        self.assertEqual(self.evaluate("enabledPlugins.length"), 0)
        self.assertEqual(self.warnings, [])

    def test_synthetic_events_are_plain_text_accessible_and_observed(self):
        self.evaluate("usePimEvents = true; fixtureEvents = [{title: '<b>Sintético</b>', isAllDay: true}, {title: 'Reunião', isAllDay: false, startDateTime: new Date(2026,9,10,23,0), endDateTime: new Date(2026,9,11,1,30)}]")
        QTest.qWait(60)
        self.assertEqual(self.evaluate("enabledPlugins.length"), 0)
        self.assertEqual(self.evaluate("agendaEvents.length"), 2)
        self.assertEqual(self.evaluate("providerState"), "events-present")
        self.evaluate("pimPluginMetadataAvailableOverride = false")
        self.assertEqual(self.evaluate("providerState"), "events-present")
        self.assertEqual(self.evaluate("eventTime(agendaEvents[0])"), "Dia inteiro")
        cross_day = self.evaluate("eventTime(agendaEvents[1])")
        self.assertTrue(cross_day.startswith("23:00 – 11 "), cross_day)
        self.assertTrue(cross_day.endswith(", 01:30"), cross_day)
        self.assertEqual(self.evaluate("agendaEvents[0].title"), "<b>Sintético</b>")
        agenda = self.window.findChild(QQuickItem, "calendarAgendaList")
        # A hidden/occluded Wayland test window may not receive a render tick.
        # Flush the pending parent layout and view before inspecting a delegate.
        self.calendar.ensurePolished()
        agenda.ensurePolished()
        # Rows start with the calendar color bar; the title is reached by name, not position.
        expression = QQmlExpression(self.engine.rootContext(), agenda, "forceLayout(); itemAtIndex(0).titleItem.textFormat")
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.assertEqual(value, 0)
        expression = QQmlExpression(self.engine.rootContext(), agenda, "itemAtIndex(0).accessibilityLabel")
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.assertEqual(value, "<b>Sintético</b>. Dia inteiro")
        # The calendar's color marks each event; anything else falls back to the accent.
        self.assertEqual(self.evaluate("eventColor({eventColor: '#3d8ee6'})"), "#3d8ee6")
        self.assertEqual(self.evaluate("eventColor({eventColor: 'red; x'}) === dock.accent"), True)
        # With events on screen the long explanation steps aside.
        self.assertFalse(self.window.findChild(QObject, "calendarProviderExplanation").property("visible"))
        # Tomorrow, shown while today is selected.
        self.evaluate("today(); fixtureTomorrowEvents = [{title: 'Consulta', isAllDay: true}]")
        QTest.qWait(60)
        self.assertTrue(self.evaluate("selectedIsToday"))
        self.assertEqual(self.evaluate("tomorrowEvents.length"), 1)
        self.assertTrue(self.window.findChild(QObject, "calendarTomorrowTitle").property("visible"))
        # Another day selected: no "tomorrow" section.
        self.evaluate("selectedDate = new Date(2020, 0, 15)")
        QTest.qWait(60)
        self.assertFalse(self.evaluate("selectedIsToday"))
        self.assertEqual(self.evaluate("tomorrowEvents.length"), 0)
        self.assertEqual(self.warnings, [])

    def test_month_view_inherits_legible_dark_and_light_theme_colors(self):
        month = self.window.findChild(QQuickItem, "calendarMonthView")
        schemes = (
            ("#edf1f9", "#18202e", "#54b8f3"),
            ("#252b35", "#f4f0e8", "#276d91"),
        )
        for foreground_name, background_name, accent_name in schemes:
            self.evaluate(
                f"dock.foreground = '{foreground_name}'; dock.background = '{background_name}'; "
                f"dock.accent = '{accent_name}'"
            )
            QTest.qWait(360)
            month.ensurePolished()
            foreground = QColor(foreground_name)
            background = QColor(background_name)
            self.assertGreaterEqual(self.contrast_ratio(foreground, background), 7.0)
            header = []
            tabs = []
            weekdays = []
            numbers = []
            navigation_icons = []
            for item in self.visual_items(month):
                if not item.isVisible():
                    continue
                text = item.property("text")
                color = item.property("color")
                if str(text) in ("‹", "›"):
                    navigation_icons.append(item)
                if not text or not isinstance(color, QColor) or not color.isValid():
                    continue
                class_name = item.metaObject().className()
                if item.objectName() == "monthHeader":
                    header.append(item)
                elif class_name == "QQuickText":
                    tabs.append(item)
                elif class_name.startswith("Heading_"):
                    weekdays.append(item)
                elif class_name.startswith("Label_") and str(text).isdigit() and len(str(text)) <= 2:
                    numbers.append(item)
            self.assertEqual(len(header), 1)
            # Days/Months/Years tabs are hidden, like the macOS calendar.
            expression = QQmlExpression(self.engine.rootContext(), month, "viewHeader.tabBar.visible")
            tabs_visible, _ = expression.evaluate()
            self.assertFalse(expression.hasError(), expression.error().toString())
            self.assertFalse(tabs_visible)
            self.assertGreaterEqual(len(weekdays), 7)
            self.assertGreaterEqual(len(numbers), 42)
            self.assertEqual(len(navigation_icons), 2)
            for item in header + tabs + weekdays + numbers:
                self.assertEqual(item.property("color").name(), foreground.name(),
                                 (item.metaObject().className(), item.property("text")))
            for name in ("previousButton", "nextButton"):
                expression = QQmlExpression(
                    self.engine.rootContext(), month, f"viewHeader.{name}.display")
                display, _ = expression.evaluate()
                self.assertFalse(expression.hasError(), expression.error().toString())
                self.assertEqual(display, 1)
            for item in navigation_icons:
                self.assertEqual(item.property("color").name(), foreground.name())
                self.assertGreaterEqual(item.property("font").pixelSize(), 18)
        self.assertEqual(self.warnings, [])

    def test_month_navigation_and_return_to_today(self):
        before = self.window.findChild(QObject, "calendarMonthView").property("selectedYear")
        self.evaluate("nextMonth()")
        QTest.qWait(400)
        self.evaluate("previousMonth(); today()")
        QTest.qWait(400)
        self.assertEqual(self.evaluate("selectedDate.toDateString() === new Date().toDateString()"), True)
        self.assertEqual(self.window.findChild(QObject, "calendarMonthView").property("selectedYear"), before)
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
