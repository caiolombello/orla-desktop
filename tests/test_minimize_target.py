"""Minimize (magic lamp) target: stable math and the throttled publication."""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtTest import QTest

# Longer than MinimizeTarget.js publishInterval, so one throttle window has elapsed.
SETTLE_MS = 400


class MinimizeTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("MinimizeTargetHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.harness = self.engine.rootObjects()[0]

    def tearDown(self):
        self.harness.close()
        self.harness.deleteLater()
        QCoreApplication.sendPostedEvents(self.harness, QEvent.DeferredDelete)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()

    def evaluate(self, source):
        expression = QQmlExpression(self.engine.rootContext(), self.harness, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def js(self, source):
        return self.evaluate(f"JSON.stringify((function(G) {{ return {source}; }})(geometry()))")

    def calls(self):
        return int(self.evaluate("calls.length"))

    def last_call(self):
        return {key: self.evaluate(f"calls[calls.length - 1].{key}") for key in ("row", "x", "y", "width", "height")}

    def resting_global(self):
        # Where the artwork rests, mapped from its parent so its transforms stay out.
        x = self.evaluate("artwork.parent.mapToGlobal(artwork.x, artwork.y).x")
        y = self.evaluate("artwork.parent.mapToGlobal(artwork.x, artwork.y).y")
        return {"x": round(x), "y": round(y), "width": 46, "height": 46}

    # Pure math (MinimizeTarget.js).

    def test_stable_rect_rounds_and_rejects_empty_slots(self):
        self.assertEqual(self.js("G.stableRect({x: 10.4, y: 3.6, width: 45.6, height: 46.2})"),
                         '{"x":10,"y":4,"width":46,"height":46}')
        self.assertEqual(self.js("G.stableRect({x: 0, y: 0, width: 0, height: 46})"), "null")
        self.assertEqual(self.js("G.stableRect(null)"), "null")

    def test_stable_rect_clamps_a_scrolled_tile_to_the_visible_lane(self):
        bounds = "{x: 30, y: 0, width: 200, height: 100}"
        self.assertEqual(self.js(f"G.stableRect({{x: -60, y: 8, width: 46, height: 46}}, {bounds})"),
                         '{"x":30,"y":8,"width":46,"height":46}')
        self.assertEqual(self.js(f"G.stableRect({{x: 400, y: 8, width: 46, height: 46}}, {bounds})"),
                         '{"x":184,"y":8,"width":46,"height":46}')
        # A lane narrower than the icon leaves the slot alone.
        self.assertEqual(self.js("G.stableRect({x: 400, y: 8, width: 46, height: 46}, {x: 0, y: 0, width: 20, height: 9})"),
                         '{"x":400,"y":8,"width":46,"height":46}')

    def test_global_rect_and_publication_key(self):
        self.assertEqual(self.js("G.globalRect({x: 1, y: 2, width: 46, height: 46}, {x: 100.6, y: 900.2})"),
                         '{"x":101,"y":900,"width":46,"height":46}')
        self.assertEqual(self.js("G.publicationKey(2, 'a,b', {x: 1, y: 2, width: 3, height: 4})"), '"2|a,b|1|2|3|4"')
        self.assertEqual(self.js("G.publicationKey(2, 'a', null)"), '""')

    # The delegate in a dock-shaped fixture.

    def test_publishes_the_resting_artwork_box_once_throttled(self):
        self.assertEqual(self.calls(), 0, "publication waits for the throttle")
        QTest.qWait(SETTLE_MS)
        self.assertEqual(self.calls(), 1)
        self.assertEqual(self.last_call(), {"row": 3, **self.resting_global()})
        # The delegate handed over is the target item, sitting on the resting box
        # (Wayland reads its own geometry; X11 the global rect).
        self.assertTrue(self.evaluate("calls[0].delegate === target"))
        self.assertEqual([self.evaluate(f"target.{key}") for key in ("x", "y", "width", "height")], [6, 4, 46, 46])
        self.assertEqual(self.warnings, [])

    def test_hover_lift_and_bounce_never_move_the_target(self):
        QTest.qWait(SETTLE_MS)
        first = self.last_call()
        self.evaluate("lifted = true; bounce = -12")
        QTest.qWait(SETTLE_MS)
        self.evaluate("target.publish()")
        self.assertEqual(self.calls(), 1)
        self.assertEqual(self.last_call(), first)

    def test_rows_without_windows_do_not_publish_until_a_window_arrives(self):
        self.evaluate("rowActive = false")
        QTest.qWait(SETTLE_MS)
        self.assertEqual(self.calls(), 0)
        self.assertFalse(self.evaluate("target.publish()"))
        self.evaluate("rowActive = true")
        QTest.qWait(SETTLE_MS)
        self.assertEqual(self.calls(), 1)
        # A window joining the row publishes again, for the same box.
        self.evaluate("rowWindows = 'w1,w2'")
        QTest.qWait(SETTLE_MS)
        self.assertEqual(self.calls(), 2)
        self.assertEqual(self.last_call(), {"row": 3, **self.resting_global()})

    def test_a_burst_of_moves_coalesces_into_one_new_publication(self):
        QTest.qWait(SETTLE_MS)
        self.assertEqual(self.calls(), 1)
        for x in (44, 48, 52, 60):
            self.evaluate(f"tile.x = {x}")
        self.assertTrue(self.evaluate("target.pending"))
        QTest.qWait(SETTLE_MS)
        self.assertEqual(self.calls(), 2)
        self.assertEqual(self.last_call(), {"row": 3, **self.resting_global()})
        # An epoch bump with nothing moved finds the same key and stays quiet.
        self.evaluate("target.epoch++")
        QTest.qWait(SETTLE_MS)
        self.assertEqual(self.calls(), 2)

    def test_a_tile_scrolled_out_of_the_lane_targets_its_edge(self):
        QTest.qWait(SETTLE_MS)
        self.evaluate("tile.x = 400")
        QTest.qWait(SETTLE_MS)
        lane_right = self.evaluate("lane.mapToGlobal(lane.width, 0).x")
        call = self.last_call()
        self.assertEqual(call["x"] + call["width"], round(lane_right))
        self.assertEqual(call["width"], 46)


if __name__ == "__main__":
    unittest.main()
