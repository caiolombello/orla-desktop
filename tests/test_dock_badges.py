"""Unread badges on dock app icons: pure mapping, the polling state, the tile and the dock wiring.

Offscreen and synthetic: the transport is a fixture, no session bus is used.
"""
import json
from pathlib import Path
import unittest

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QJSEngine, QQmlApplicationEngine, QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "package/contents/ui"


def badges_library():
    engine = QJSEngine()
    source = (ROOT / "package/contents/code/Badges.js").read_text().replace(".pragma library", "", 1)
    result = engine.evaluate(source)
    assert not result.isError(), result.toString()
    return engine


class BadgesLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def call(self, engine, expression):
        result = engine.evaluate(expression)
        self.assertFalse(result.isError(), result.toString())
        return result.toVariant()

    def test_launcher_urls_map_to_desktop_ids_and_reject_anything_else(self):
        engine = badges_library()
        cases = {
            "applications:org.kde.dolphin.desktop": "org.kde.dolphin.desktop",
            "file:///usr/share/applications/org.example.Mail.desktop": "org.example.Mail.desktop",
            "applications:../x.desktop": "",
            "applications:x": "",
            "https://example.test/x.desktop": "",
            "": "",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(self.call(engine, f"desktopId({json.dumps(url)})"), expected)
        self.assertEqual(self.call(engine, "desktopId(undefined)"), "")

    def test_query_is_unique_sorted_and_bounded(self):
        engine = badges_library()
        self.assertEqual(self.call(engine, 'query(["b.desktop", "a.desktop", "b.desktop", "", "../x", 7])'),
                         ["a.desktop", "b.desktop"])
        many = json.dumps([f"app{index}.desktop" for index in range(200)])
        self.assertEqual(self.call(engine, f"query({many}).length"), 128)

    def test_reply_parsing_accepts_only_requested_bounded_counts(self):
        engine = badges_library()
        requested = '["a.desktop", "b.desktop"]'

        def parse(value):
            return self.call(engine, f"parse({json.dumps(json.dumps(value))}, {requested})")
        self.assertEqual(parse({"schemaVersion": 1, "status": "ready", "entries": [{"desktopId": "a.desktop", "count": 3}]}),
                         {"status": "ready", "counts": {"a.desktop": 3}})
        self.assertEqual(parse({"schemaVersion": 1, "status": "unavailable", "entries": []}),
                         {"status": "unavailable", "counts": {}})
        for bad in ({"schemaVersion": 2, "status": "ready", "entries": []},
                    {"schemaVersion": 1, "error": "invalid-ids"},
                    {"schemaVersion": 1, "status": "ready", "entries": [{"desktopId": "c.desktop", "count": 1}]},
                    {"schemaVersion": 1, "status": "ready", "entries": [{"desktopId": "a.desktop", "count": 0}]},
                    {"schemaVersion": 1, "status": "ready", "entries": [{"desktopId": "a.desktop", "count": 1.5}]},
                    {"schemaVersion": 1, "status": "ready", "entries": [{"desktopId": "a.desktop", "count": 1},
                                                                        {"desktopId": "a.desktop", "count": 2}]}):
            with self.subTest(bad=bad):
                self.assertIsNone(parse(bad))
        self.assertIsNone(self.call(engine, f'parse("{{", {requested})'))
        self.assertEqual(self.call(engine, "[label(1), label(99), label(100), label(4000)]"), ["1", "99", "99+", "99+"])


STATE = """
import QtQuick
import "%s" as DockUI
Item {
    property alias state: badges
    property var calls: []
    property var pending: []
    property var ids: ["b.desktop", "a.desktop", "b.desktop"]
    DockUI.BadgeState {
        id: badges
        interval: 60000
        idsProvider: function() { return ids; }
        transport: QtObject {
            function asyncCall(message, resolve, reject) {
                calls.push(message);
                pending.push({resolve: resolve, reject: reject});
            }
        }
    }
    function reply(index, value) { pending[index].resolve({value: JSON.stringify(value)}); }
    function fail(index) { pending[index].reject(); }
}
""" % UI.as_uri()


class BadgeStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlEngine()
        component = QQmlComponent(self.engine)
        component.setData(STATE.encode(), QUrl.fromLocalFile(str(ROOT / "tests/BadgeStateFixture.qml")))
        self.component = component
        self.root = component.create()
        self.assertIsNotNone(self.root, component.errorString())
        QQmlEngine.setObjectOwnership(self.root, QQmlEngine.ObjectOwnership.CppOwnership)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.root.deleteLater()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def evaluate(self, source):
        expression = QQmlExpression(self.engine.rootContext(), self.root, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def test_inactive_state_never_calls_the_service(self):
        self.evaluate("state.refresh()")
        self.assertEqual(self.evaluate("calls.length"), 0)
        self.assertEqual(self.evaluate("state.countFor('a.desktop')"), 0)

    def test_active_state_asks_for_shown_apps_and_reads_counts(self):
        self.evaluate("state.active = true")
        self.assertEqual(self.evaluate("calls.length"), 1)
        message = self.evaluate("calls[0]")
        self.assertEqual((message["member"], message["signature"], message["arguments"]),
                         ("BadgeCounts", "(as)", [["a.desktop", "b.desktop"]]))
        # One call in flight at a time.
        self.evaluate("state.refresh()")
        self.assertEqual(self.evaluate("calls.length"), 1)
        self.evaluate('reply(0, {schemaVersion: 1, status: "ready", entries: [{desktopId: "b.desktop", count: 7}]})')
        self.assertEqual(self.evaluate("state.countFor('b.desktop')"), 7)
        self.assertEqual(self.evaluate("state.countFor('a.desktop')"), 0)
        self.assertEqual(self.evaluate("state.status"), "ready")
        self.evaluate("state.refresh()")
        self.evaluate("fail(1)")
        self.assertEqual(self.evaluate("state.countFor('b.desktop')"), 0)
        self.assertEqual(self.evaluate("state.status"), "unavailable")

    def test_a_reply_after_turning_badges_off_is_ignored(self):
        self.evaluate("state.active = true")
        self.evaluate("state.active = false")
        self.evaluate('reply(0, {schemaVersion: 1, status: "ready", entries: [{desktopId: "a.desktop", count: 2}]})')
        self.assertEqual(self.evaluate("state.counts"), {})
        self.assertEqual(self.evaluate("state.status"), "idle")

    def test_no_apps_means_no_call(self):
        self.evaluate("ids = []")
        self.evaluate("state.active = true")
        self.assertEqual(self.evaluate("calls.length"), 0)




class BadgeTileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_badge_draws_the_bounded_count_without_moving_the_artwork(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
        engine.load(QUrl.fromLocalFile(str(ROOT / "tests/BadgeTileHarness.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        try:
            QTest.qWait(30)
            plain, badged = (window.findChild(QQuickItem, name) for name in ("plain", "badged"))
            self.assertFalse(plain.findChild(QQuickItem, "tileBadge").isVisible())
            badge = badged.findChild(QQuickItem, "tileBadge")
            text = badged.findChild(QQuickItem, "tileBadgeText")
            self.assertTrue(badge.isVisible())
            self.assertEqual(text.property("text"), "3")
            self.assertEqual(QQmlExpression(QQmlEngine.contextForObject(text), text, "textFormat === Text.PlainText").evaluate()[0], True)
            self.assertEqual(QQmlExpression(QQmlEngine.contextForObject(badged), badged, "Accessible.name").evaluate()[0], "Correio, 3 não lidas")
            for name in ("implicitWidth", "implicitHeight"):
                self.assertEqual(plain.property(name), badged.property(name))
            artwork = (plain.findChild(QQuickItem, "tileArtwork"), badged.findChild(QQuickItem, "tileArtwork"))
            self.assertEqual([(item.x(), item.y(), item.width()) for item in artwork][0],
                             [(item.x(), item.y(), item.width()) for item in artwork][1])
            badged.setProperty("badgeCount", 1234)
            self.assertEqual(text.property("text"), "99+")
            # The badge stays on the corner, inside the icon's reach.
            self.assertLessEqual(badge.width(), badged.findChild(QQuickItem, "tileArtwork").width())
            badged.setProperty("liveKind", "clock")
            self.assertFalse(badge.isVisible())
            self.assertEqual(warnings, [])
        finally:
            window.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


class DockBadgeTests(unittest.TestCase):
    """Real DockView with the local KDE modules, as test_qml loads it."""
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_dock_shows_the_count_on_the_matching_launcher_only_while_enabled(self):
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
        engine.load(QUrl.fromLocalFile(str(ROOT / "tests/QmlHarness.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        try:
            dock = window.findChild(QQuickItem, "dock")
            config = window.findChild(QObject, "configuration")
            context = QQmlEngine.contextForObject(window.findChild(QQuickItem, "dockSurface"))

            def evaluate(source):
                expression = QQmlExpression(context, dock, source)
                value, _ = expression.evaluate()
                self.assertFalse(expression.hasError(), f"{source}: {expression.error().toString()}")
                return value.toVariant() if hasattr(value, "toVariant") else value
            QTest.qWait(200)
            evaluate("""badges.transport = Qt.createQmlObject('import QtQml; QtObject { property var calls: []; '
                + 'function asyncCall(m, ok, fail) { calls.push(m); ok({value: JSON.stringify({schemaVersion: 1, '
                + 'status: "ready", entries: [{desktopId: "org.kde.konsole.desktop", count: 4}]})}); } }', badges)""")
            self.assertFalse(evaluate("badges.active"))
            self.assertEqual(evaluate("badges.transport.calls.length"), 0)
            config.setProperty("showBadges", True)
            QTest.qWait(50)
            self.assertEqual(evaluate("badges.transport.calls[0].arguments"),
                             [["org.kde.dolphin.desktop", "org.kde.konsole.desktop"]])
            counts = [evaluate(f"taskRepeater.itemAt({row}).badgeCount") for row in range(2)]
            ids = [evaluate(f"taskRepeater.itemAt({row}).desktopId") for row in range(2)]
            self.assertEqual(dict(zip(ids, counts)), {"org.kde.dolphin.desktop": 0, "org.kde.konsole.desktop": 4})
            config.setProperty("showBadges", False)
            QTest.qWait(50)
            self.assertEqual([evaluate(f"taskRepeater.itemAt({row}).badgeCount") for row in range(2)], [0, 0])
        finally:
            window.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
