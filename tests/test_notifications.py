import json
import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QJSEngine, QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "notifications/contents/code/NotificationView.js"


def view_engine():
    engine = QJSEngine()
    source = VIEW.read_text(encoding="utf-8").replace(".pragma library", "")
    names = ("limits", "plain", "plainBody", "iconSource", "effectiveTimeout", "age", "actions", "stack", "groups",
             "thumbnail", "reply")
    exports = ", ".join(f"{name}: {name}" for name in names)
    result = engine.evaluate(f"(function() {{\n{source}\nreturn {{{exports}}};\n}})()")
    assert not result.isError(), result.toString()
    engine.globalObject().setProperty("View", result)
    return engine


class NotificationViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        cls.engine = view_engine()

    def js(self, expression):
        result = self.engine.evaluate("JSON.stringify(" + expression + ")")
        self.assertFalse(result.isError(), result.toString())
        return json.loads(result.toString())

    def test_bodies_become_bounded_plain_text(self):
        body = "<b>Olá</b> &amp; <i>bem-vindo</i><br/>linha 2<p>p&aacute;</p>  <a href='x'>link</a>\n\n\n fim"
        self.assertEqual(self.js(f"View.plainBody({json.dumps(body)})"),
                         "Olá & bem-vindo\nlinha 2\np&aacute;\nlink\nfim")
        self.assertEqual(len(self.js("View.plainBody('x'.repeat(5000))")), 1200)
        self.assertEqual(self.js("View.plain('  um\\n dois\\t ', 5)"), "um do")
        self.assertEqual(self.js("View.plain(null, 10)"), "")

    def test_icons_are_theme_names_or_local_sources(self):
        for value, expected in (("dialog-information", "dialog-information"), ("file:///tmp/a.png", "file:///tmp/a.png"),
                                ("https://example.invalid/a.png", ""), ("../../x", ""), ("a b", ""), ("", "")):
            self.assertEqual(self.js(f"View.iconSource({json.dumps(value)})"), expected, value)

    def test_timeouts_follow_kde_rules(self):
        self.assertEqual(self.js("View.effectiveTimeout(-1, 5000, 0)"), 5000)
        self.assertEqual(self.js("View.effectiveTimeout(0, 5000, 0)"), 0)
        self.assertEqual(self.js("View.effectiveTimeout(8000, 5000, 0)"), 8000)
        self.assertEqual(self.js("View.effectiveTimeout(0, 5000, 5000)"), 5000)

    def test_ages_and_actions(self):
        self.assertEqual(self.js("View.age(1000, 30000)"), {"kind": "now", "value": 0})
        self.assertEqual(self.js("View.age(0, 30000)"), {"kind": "unknown", "value": 0})
        self.assertEqual(self.js("View.age(1000, 1000 + 5 * 60000)"), {"kind": "minutes", "value": 5})
        self.assertEqual(self.js("View.age(1000, 1000 + 3 * 3600000)"), {"kind": "hours", "value": 3})
        self.assertEqual(self.js("View.age(1000, 1000 + 2 * 86400000)")["kind"], "date")
        actions = self.js("View.actions(['default', 'a', 'a', 'b', '', 'c', 'd'], ['Abrir', 'Ação A', 'Repetida', ' ', 'Vazia', 'C', 'D'])")
        self.assertEqual(actions, [{"name": "a", "label": "Ação A"}, {"name": "c", "label": "C"}, {"name": "d", "label": "D"}])

    def test_banners_stack_from_the_top_and_keep_the_first(self):
        places = self.js("View.stack({x: 0, y: 32, width: 1000, height: 400}, [100, 120, 200], 12, 8, 0.8)")
        self.assertEqual([p["y"] for p in places], [44, 152, 280])
        self.assertEqual([p["visible"] for p in places], [True, True, False])
        self.assertTrue(self.js("View.stack({x: 0, y: 0, width: 10, height: 10}, [500], 12, 8, 0.8)")[0]["visible"])

    def test_thumbnails_are_local_images_and_replies_are_bounded(self):
        urls = ["https://example.invalid/a.png", "file:///tmp/notes.txt", "file:///tmp/a b.png",
                "file:///tmp/Captura.PNG", "file:///tmp/second.jpg"]
        self.assertEqual(self.js(f"View.thumbnail({json.dumps(urls)})"), "file:///tmp/Captura.PNG")
        self.assertEqual(self.js("View.thumbnail([])"), "")
        self.assertEqual(self.js("View.thumbnail(null)"), "")
        self.assertIsNone(self.js("View.reply(false, 'Responder', '', '')"))
        self.assertEqual(self.js("View.reply(true, ' Responder\\n', 'x'.repeat(200), '')"),
                         {"label": "Responder", "placeholder": "x" * 80, "submit": ""})

    def test_history_groups_by_app_newest_first(self):
        items = [dict(id="1", appKey="a", appName="A", createdMs=10), dict(id="2", appKey="b", appName="B", createdMs=30),
                 dict(id="3", appKey="a", appName="A", createdMs=20)]
        groups = self.js(f"View.groups({json.dumps(items)})")
        self.assertEqual([g["key"] for g in groups], ["b", "a"])
        self.assertEqual([i["id"] for i in groups[1]["items"]], ["3", "1"])


class NotificationSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(ROOT / "tests/NotificationsHarness.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.banner = self.window.findChild(QQuickItem, "bannerUnderTest")
        self.center = self.window.findChild(QQuickItem, "centerUnderTest")
        QTest.qWait(20)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(self.window, QEvent.DeferredDelete)
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual([w for w in self.warnings if "IconImage" not in w], [])

    def evaluate(self, source, target):
        expression = QQmlExpression(self.engine.rootContext(), target, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    # Repeater delegates only get a visual parent, so walk childItems().
    def items(self, parent, name):
        found = []
        pending = [parent]
        while pending:
            current = pending.pop()
            if current.objectName() == name:
                found.append(current)
            pending.extend(current.childItems())
        return found

    def item(self, parent, name):
        found = self.items(parent, name)
        self.assertTrue(found, name)
        return found[0]

    def events(self):
        return list(self.window.property("events").toVariant()) if hasattr(self.window.property("events"), "toVariant") \
            else list(self.window.property("events"))

    def notify(self, **values):
        base = dict(id="1", appName="Aplicativo sintético", appIcon="", summary="Título", body="Corpo", actions=[],
                    hasDefaultAction=True, closable=True, critical=False, createdMs=1000, job=None)
        base.update(values)
        self.evaluate("notification = " + json.dumps(base), self.banner)
        QTest.qWait(10)

    def test_banner_is_plain_macos_layout_with_bounded_text(self):
        self.notify(summary="<b>Reunião</b>", body="<i>Começa</i> em 5 min &amp; já", appName="X" * 300)
        self.assertEqual(self.item(self.banner, "notificationSummary").property("text"), "<b>Reunião</b>")
        self.assertEqual(self.item(self.banner, "notificationBody").property("text"), "Começa em 5 min & já")
        self.assertEqual(len(self.item(self.banner, "notificationApp").property("text")), 60)
        self.assertEqual(self.item(self.banner, "notificationTime").property("text"), "agora")
        for name in ("notificationSummary", "notificationBody", "notificationApp"):
            self.assertEqual(self.evaluate("textFormat", self.item(self.banner, name)), 0)
        # The icon sits left of the text, as in macOS.
        icon = self.item(self.banner, "notificationIcon")
        summary = self.item(self.banner, "notificationSummary")
        self.assertLess(icon.mapToScene(QPointF(0, 0)).x(), summary.mapToScene(QPointF(0, 0)).x())

    def test_close_and_actions_appear_only_when_engaged_and_keyboard_works(self):
        self.notify(actions=[dict(name="reply", label="Responder")])
        close = self.item(self.banner, "notificationClose")
        actions = self.item(self.banner, "notificationActions")
        self.assertFalse(close.property("visible"))
        self.assertFalse(actions.property("visible"))
        self.banner.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.qWait(10)
        self.assertTrue(close.property("visible"))
        self.assertTrue(actions.property("visible"))
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.evaluate("clicked()", self.item(self.banner, "notificationAction"))
        self.assertEqual(self.events(), ["activated", "close", "action:reply"])
        # Without a default action, Enter does nothing; an unclosable one ignores Escape.
        self.notify(hasDefaultAction=False, closable=False)
        self.window.setProperty("events", [])
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertEqual(self.events(), [])

    def test_timeout_expires_but_pauses_while_engaged(self):
        self.notify()
        self.banner.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        self.evaluate("timeout = 50", self.banner)
        QTest.qWait(120)
        self.assertEqual(self.events(), [])
        self.window.findChild(QQuickItem, "centerUnderTest").forceActiveFocus()
        deadline = time.monotonic() + 2
        while "expired" not in self.events() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertEqual(self.events(), ["expired"])
        # Zero keeps the banner.
        self.window.setProperty("events", [])
        self.evaluate("timeout = 0", self.banner)
        QTest.qWait(80)
        self.assertEqual(self.events(), [])

    def test_reply_opens_a_field_sends_trimmed_text_and_escape_cancels(self):
        self.notify(reply=dict(label="Responder", placeholder="Escreva…", submit="Enviar"))
        reply = self.item(self.banner, "notificationReply")
        self.banner.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.qWait(10)
        self.assertTrue(reply.property("visible"))
        self.assertFalse(self.item(self.banner, "notificationReplyRow").property("visible"))
        self.evaluate("clicked()", reply)
        QTest.qWait(30)
        self.assertTrue(self.banner.property("replying"))
        self.assertTrue(self.item(self.banner, "notificationReplyRow").property("visible"))
        field = self.item(self.banner, "notificationReplyField")
        self.assertTrue(field.property("activeFocus"))
        self.assertEqual(field.property("placeholderText"), "Escreva…")
        # The banner stays while a reply is written, whatever the timeout.
        self.evaluate("timeout = 30", self.banner)
        QTest.qWait(90)
        self.assertNotIn("expired", self.events())
        field.setProperty("text", "   ")
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertEqual([e for e in self.events() if e.startswith("reply")], [])
        field.setProperty("text", "  oi, já vou  ")
        QTest.keyClick(self.window, Qt.Key.Key_Return)
        self.assertIn("reply:oi, já vou", self.events())
        self.assertFalse(self.banner.property("replying"))
        # Escape closes the field without sending.
        self.evaluate("timeout = 0", self.banner)
        self.window.setProperty("events", [])
        self.evaluate("beginReply()", self.banner)
        QTest.qWait(30)
        field.setProperty("text", "rascunho")
        QTest.keyClick(self.window, Qt.Key.Key_Escape)
        self.assertFalse(self.banner.property("replying"))
        self.assertEqual(self.events(), [])
        # Without an offer there is no reply.
        self.notify()
        self.assertFalse(self.evaluate("beginReply()", self.banner))

    def test_thumbnail_shows_a_local_image(self):
        image = QImage(64, 48, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.darkCyan)
        path = Path(self.tmp.name) / "captura.png"
        image.save(str(path))
        self.notify(thumbnail=path.as_uri())
        thumb = self.item(self.banner, "notificationThumbnail")
        deadline = time.monotonic() + 2
        while not thumb.property("visible") and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(thumb.property("visible"), (self.evaluate("status", thumb), thumb.property("source"), thumb.width()))
        self.notify(thumbnail="")
        self.assertFalse(thumb.property("visible"))

    def test_job_banner_shows_progress_and_controls(self):
        self.notify(job=dict(state="running", percentage=42, suspendable=True, killable=True, error=""))
        self.assertTrue(self.item(self.banner, "notificationJob").property("visible"))
        self.assertEqual(self.item(self.banner, "notificationJobState").property("text"), "42%")
        self.banner.forceActiveFocus(Qt.FocusReason.TabFocusReason)
        QTest.qWait(10)
        self.evaluate("clicked()", self.item(self.banner, "notificationJobPause"))
        self.evaluate("clicked()", self.item(self.banner, "notificationJobCancel"))
        self.assertEqual(self.events(), ["job:suspend", "job:kill"])
        self.notify(job=dict(state="stopped", percentage=100, suspendable=False, killable=False, error="falha"))
        self.assertEqual(self.item(self.banner, "notificationJobState").property("text"), "Falhou")

    def test_center_groups_clears_and_toggles_do_not_disturb(self):
        self.assertTrue(self.item(self.center, "notificationsEmpty").property("visible"))
        self.assertFalse(self.item(self.center, "notificationsClearAll").property("enabled"))
        groups = [dict(key="a", appName="App A", appIcon="", items=[
            dict(id=str(n), summary=f"Aviso {n}", body="<b>texto</b>", createdMs=1000, closable=True, hasDefaultAction=True)
            for n in range(5)])]
        self.evaluate("groups = " + json.dumps(groups), self.center)
        QTest.qWait(20)
        self.assertFalse(self.item(self.center, "notificationsEmpty").property("visible"))
        self.assertTrue(self.item(self.center, "notificationsClearAll").property("enabled"))
        self.assertEqual(len(self.items(self.center, "notificationHistoryItem")), 3)
        self.assertEqual(self.item(self.center, "notificationGroupMore").property("text"), "Mais 2")
        self.evaluate("clicked()", self.item(self.center, "notificationsClearAll"))
        self.evaluate("clicked()", self.item(self.center, "notificationGroupClear"))
        self.evaluate("clicked()", self.item(self.center, "notificationHistoryClose"))
        dnd = self.item(self.center, "notificationsDoNotDisturb")
        self.evaluate("toggle(); toggled()", dnd)
        events = self.events()
        self.assertEqual(events[:2] + events[3:], ["clearAll", "clearGroup:a", "dnd:true"])
        self.assertIn(events[2], ["closeItem:0", "closeItem:1", "closeItem:2"])
        self.evaluate("doNotDisturbAvailable = false", self.center)
        self.assertFalse(dnd.property("enabled"))
        self.assertEqual(self.item(self.center, "notificationsDoNotDisturbDetail").property("text"), "Indisponível")


if __name__ == "__main__":
    unittest.main()
