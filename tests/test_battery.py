import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest


class SystemBatteryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("BatteryHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.harness = self.engine.rootObjects()[0]
        self.battery = self.harness.findChild(QQuickItem, "batteryUnderTest")

    def tearDown(self):
        self.battery.setProperty("active", False)
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.battery, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def resolve(self, index, value):
        self.evaluate(f"resolve({index}, {json.dumps(value)})", self.harness)

    def read(self, properties=None, on_battery=False):
        offset = self.evaluate("calls.length", self.harness)
        self.battery.setProperty("active", True)
        self.resolve(offset, "/org/freedesktop/UPower/devices/DisplayDevice")
        self.resolve(offset + 1, properties if properties is not None else {
            "IsPresent": True, "Type": 2, "Percentage": 58.5, "State": 1,
            "TimeToFull": 1800, "TimeToEmpty": 0})
        if self.battery.property("loading"):
            self.resolve(offset + 2, on_battery)

    def assert_neutral(self, status):
        self.assertEqual(self.battery.property("status"), status)
        self.assertFalse(self.battery.property("loading"))
        self.assertFalse(self.battery.property("percentKnown"))
        self.assertEqual(self.battery.property("percent"), -1)
        self.assertEqual(self.battery.property("charging"), "unknown")
        self.assertEqual(self.battery.property("onBattery"), "unknown")
        self.assertEqual(self.battery.property("estimatedTimeSeconds"), -1)
        self.assertNotIn("0%", self.battery.property("summary"))

    def test_reads_display_battery_and_ac_without_claiming_full_charge(self):
        self.assertFalse(self.battery.property("active"))
        self.assertEqual(self.evaluate("parent.calls.length"), 0)
        self.read()
        self.assertEqual(self.battery.property("status"), "ready")
        self.assertEqual(self.battery.property("percent"), 58.5)
        self.assertEqual(self.battery.property("charging"), "charging")
        self.assertEqual(self.battery.property("onBattery"), "ac")
        self.assertEqual(self.battery.property("estimatedTimeSeconds"), 1800)
        self.assertEqual(self.battery.property("estimatedTimeKind"), "full")
        self.assertEqual(self.warnings, [])

    def test_zero_is_a_real_battery_reading_and_full_charge_is_not_charging(self):
        self.read({"IsPresent": True, "Type": 2, "Percentage": 0, "State": 3}, True)
        self.assertTrue(self.battery.property("percentKnown"))
        self.assertEqual(self.battery.property("summary"), "0%")
        self.assertEqual(self.battery.property("onBattery"), "battery")
        self.battery.setProperty("active", False)
        self.read({"IsPresent": True, "Type": 3, "Percentage": 100, "State": 4})
        self.assertEqual(self.battery.property("percent"), 100)
        self.assertEqual(self.battery.property("charging"), "not-charging")
        self.assertEqual(self.battery.property("state"), "fully-charged")
        self.assertEqual(self.battery.property("onBattery"), "ac")

    def test_decodes_plasma_typed_dbus_values(self):
        self.battery.setProperty("active", True)
        self.evaluate("resolveNativePath(0)", self.harness)
        self.assertEqual(self.battery.property("status"), "loading")
        self.evaluate("resolveNativeBattery(1)", self.harness)
        self.resolve(2, True)
        self.assertEqual(self.battery.property("status"), "ready")
        self.assertEqual(self.battery.property("percent"), 25)
        self.assertEqual(self.battery.property("state"), "discharging")
        self.assertEqual(self.battery.property("estimatedTimeSeconds"), 900)
        self.assertEqual(self.warnings, [])

    def test_absent_desktop_does_not_display_false_zero_or_read_onbattery(self):
        self.read({"IsPresent": False, "Type": 0, "Percentage": 0, "State": 0})
        self.assert_neutral("absent")
        self.assertEqual(self.evaluate("parent.calls.length"), 2)

    def test_rejects_nonbattery_and_invalid_or_missing_presence_and_percent(self):
        baseline = {"IsPresent": True, "Type": 2, "Percentage": 42, "State": 2}
        invalid = [{**baseline, "Percentage": value} for value in (-1, 101, True, "42", None)]
        invalid += [{**baseline, "Type": value} for value in (0, 1, 5, "2", True)]
        invalid += [{**baseline, "IsPresent": value} for value in (None, 1, "true")]
        invalid += [{}, [], None]
        for properties in invalid:
            with self.subTest(properties=properties):
                self.battery.setProperty("active", False)
                offset = self.evaluate("parent.calls.length")
                self.battery.setProperty("active", True)
                self.resolve(offset, "/org/freedesktop/UPower/devices/DisplayDevice")
                self.resolve(offset + 1, properties)
                self.assert_neutral("unavailable")
        for expression in ("NaN", "Infinity", "-Infinity"):
            self.battery.setProperty("active", False)
            offset = self.evaluate("parent.calls.length")
            self.battery.setProperty("active", True)
            self.resolve(offset, "/org/freedesktop/UPower/devices/DisplayDevice")
            self.evaluate(f"resolve({offset + 1}, {{IsPresent:true, Type:2, Percentage:{expression}}})", self.harness)
            self.assert_neutral("unavailable")

    def test_unknown_state_and_zero_estimate_remain_unknown(self):
        for state in (0, 8, "1", True, None):
            with self.subTest(state=state):
                self.battery.setProperty("active", False)
                self.read({"IsPresent": True, "Type": 2, "Percentage": 20, "State": state,
                           "TimeToFull": 200, "TimeToEmpty": 400}, True)
                self.assertEqual(self.battery.property("state"), "unknown")
                self.assertEqual(self.battery.property("charging"), "unknown")
                self.assertEqual(self.battery.property("estimatedTimeSeconds"), -1)
        for estimate in (0, -1, True, "500", 1.5):
            self.battery.setProperty("active", False)
            self.read({"IsPresent": True, "Type": 2, "Percentage": 20, "State": 2,
                       "TimeToEmpty": estimate}, True)
            self.assertEqual(self.battery.property("estimatedTimeSeconds"), -1)
        self.battery.setProperty("active", False)
        self.read({"IsPresent": True, "Type": 2, "Percentage": 20, "State": 2,
                   "TimeToEmpty": 600}, True)
        self.assertEqual(self.battery.property("estimatedTimeSeconds"), 600)
        self.assertEqual(self.battery.property("estimatedTimeKind"), "empty")

    def test_pending_charge_is_not_claimed_as_charging(self):
        for state, expected in ((5, "pending-charge"), (6, "pending-discharge")):
            self.battery.setProperty("active", False)
            self.read({"IsPresent": True, "Type": 2, "Percentage": 42, "State": state})
            self.assertEqual(self.battery.property("charging"), "not-charging")
            self.assertEqual(self.battery.property("state"), expected)

    def test_refresh_clears_previous_reading_and_errors_do_not_keep_it_fresh(self):
        self.read()
        self.assertTrue(self.evaluate("refresh()"))
        self.assertEqual(self.battery.property("status"), "loading")
        self.assertEqual(self.battery.property("percent"), -1)
        self.assertFalse(self.evaluate("refresh()"))
        self.evaluate("reject(3)", self.harness)
        self.assert_neutral("unavailable")
        self.assertNotIn("private fixture", self.battery.property("summary"))

    def test_errors_at_every_dbus_stage_and_malformed_onbattery_are_neutral(self):
        for stage in (0, 1, 2):
            self.battery.setProperty("active", False)
            offset = self.evaluate("parent.calls.length")
            self.battery.setProperty("active", True)
            if stage >= 1:
                self.resolve(offset, "/org/freedesktop/UPower/devices/DisplayDevice")
            if stage >= 2:
                self.resolve(offset + 1, {"IsPresent": True, "Type": 2, "Percentage": 20, "State": 1})
            self.evaluate(f"reject({offset + stage})", self.harness)
            self.assert_neutral("unavailable")
        self.battery.setProperty("active", False)
        self.read(on_battery="false")
        self.assert_neutral("unavailable")

    def test_inactive_stops_refresh_and_late_callbacks_cannot_restore_data(self):
        self.battery.setProperty("active", True)
        self.battery.setProperty("active", False)
        self.resolve(0, "/org/freedesktop/UPower/devices/DisplayDevice")
        self.assert_neutral("inactive")
        self.assertFalse(self.evaluate("refresh()"))
        QTest.qWait(160)
        self.assertEqual(self.evaluate("parent.calls.length"), 1)
        self.read()
        self.resolve(0, "/org/freedesktop/UPower/devices/DisplayDevice")
        self.assertEqual(self.battery.property("percent"), 58.5)
        self.assertEqual(self.evaluate("parent.calls.length"), 4)

    def test_timeout_ignores_old_generation_and_allows_new_read(self):
        self.battery.setProperty("requestTimeoutMs", 100)
        self.battery.setProperty("active", True)
        self.resolve(0, "/org/freedesktop/UPower/devices/DisplayDevice")
        QTest.qWait(180)
        self.assert_neutral("unavailable")
        self.assertTrue(self.evaluate("refresh()"))
        self.resolve(1, {"IsPresent": True, "Type": 2, "Percentage": 99, "State": 1})
        self.assertEqual(self.battery.property("status"), "loading")
        self.resolve(2, "/org/freedesktop/UPower/devices/DisplayDevice")
        self.resolve(3, {"IsPresent": True, "Type": 2, "Percentage": 15, "State": 2})
        self.resolve(4, True)
        self.assertEqual(self.battery.property("percent"), 15)
        self.resolve(1, {"IsPresent": True, "Type": 2, "Percentage": 99, "State": 1})
        self.assertEqual(self.battery.property("percent"), 15)

    def test_does_not_follow_arbitrary_paths_or_expose_device_details(self):
        self.battery.setProperty("active", True)
        self.resolve(0, "/org/freedesktop/UPower/devices/mouse_private")
        self.assert_neutral("unavailable")
        self.assertEqual(self.evaluate("parent.calls.length"), 1)
        self.battery.setProperty("active", False)
        self.read({"IsPresent": True, "Type": 2, "Percentage": 60, "State": 1,
                   "Serial": "private serial", "Vendor": "private vendor", "NativePath": "private path"})
        self.assertEqual(self.battery.property("summary"), "60%")
        self.assertEqual(self.warnings, [])
        self.assertTrue(self.evaluate("parent.calls.every(call => call.service === 'org.freedesktop.UPower' && ['GetDisplayDevice','GetAll','Get'].indexOf(call.member) >= 0)"))

    def test_bad_refresh_interval_cannot_create_busy_loop(self):
        self.battery.setProperty("refreshIntervalMs", 1)
        self.read()
        QTest.qWait(180)
        self.assertEqual(self.evaluate("parent.calls.length"), 3)
        self.assertEqual(self.warnings, [])

    def test_periodic_refresh_reads_again_after_bounded_interval(self):
        self.battery.setProperty("refreshIntervalMs", 1)
        self.read()
        QTest.qWait(15200)
        self.assertEqual(self.battery.property("status"), "loading")
        self.assertEqual(self.battery.property("percent"), -1)
        self.assertEqual(self.evaluate("parent.calls.length"), 4)
        self.resolve(3, "/org/freedesktop/UPower/devices/DisplayDevice")
        self.resolve(4, {"IsPresent": True, "Type": 2, "Percentage": 57, "State": 2})
        self.resolve(5, True)
        self.assertEqual(self.battery.property("percent"), 57)
        self.assertEqual(self.battery.property("onBattery"), "battery")
        self.assertEqual(self.warnings, [])

    def test_transport_change_invalidates_old_request(self):
        self.battery.setProperty("active", True)
        self.resolve(0, "/org/freedesktop/UPower/devices/DisplayDevice")
        self.evaluate("const previous = transport; transport = {asyncCall: (message, resolve, reject) => previous.asyncCall(message, resolve, reject)}")
        self.resolve(1, {"IsPresent": True, "Type": 2, "Percentage": 99, "State": 1})
        self.assertEqual(self.evaluate("parent.calls.length"), 3)
        self.assertEqual(self.battery.property("status"), "loading")
        self.resolve(2, "/org/freedesktop/UPower/devices/DisplayDevice")
        self.resolve(3, {"IsPresent": True, "Type": 2, "Percentage": 30, "State": 2})
        self.resolve(4, True)
        self.assertEqual(self.battery.property("percent"), 30)

    def test_missing_reply_and_thrown_transport_error_are_neutral(self):
        self.battery.setProperty("active", True)
        self.evaluate("pending[0].resolve({})", self.harness)
        self.assert_neutral("unavailable")
        self.evaluate("transport = {asyncCall: () => { throw new Error('private transport details'); }}")
        self.assert_neutral("unavailable")
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
