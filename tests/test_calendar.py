import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "wayland" if os.environ.get("WAYLAND_DISPLAY") else "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


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

    def test_empty_calendar_does_not_load_pim(self):
        self.assertEqual(self.evaluate("enabledPlugins.length"), 0)
        self.assertEqual(self.evaluate("agendaEvents.length"), 0)
        self.assertTrue(self.window.findChild(QObject, "calendarEmptyState").property("visible"))
        self.assertEqual(self.warnings, [])

    def test_fixture_can_enable_preference_without_loading_pim(self):
        self.evaluate("usePimEvents = true; fixtureEvents = [{title: '<b>Sintético</b>', isAllDay: true}, {title: 'Reunião', isAllDay: false, startDateTime: new Date(2026,9,10,9,0), endDateTime: new Date(2026,9,10,10,0)}]")
        QTest.qWait(60)
        self.assertEqual(self.evaluate("enabledPlugins.length"), 0)
        self.assertEqual(self.evaluate("agendaEvents.length"), 2)
        self.assertEqual(self.evaluate("eventTime(agendaEvents[0])"), "Dia inteiro")
        self.assertEqual(self.evaluate("eventTime(agendaEvents[1])"), "09:00 – 10:00")
        self.assertEqual(self.evaluate("agendaEvents[0].title"), "<b>Sintético</b>")
        agenda = self.window.findChild(QQuickItem, "calendarAgendaList")
        # A hidden/occluded Wayland test window may not receive a render tick.
        # Flush the pending parent layout and view before inspecting a delegate.
        self.calendar.ensurePolished()
        agenda.ensurePolished()
        expression = QQmlExpression(self.engine.rootContext(), agenda, "forceLayout(); itemAtIndex(0).children[0].textFormat")
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.assertEqual(value, 0)
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
