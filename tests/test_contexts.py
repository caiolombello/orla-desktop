import gc
import json
import os
from pathlib import Path
import tempfile
import unittest


_ORIGINAL_HOME = os.environ.get("HOME")
_ORIGINAL_CODEX_HOME = os.environ.get("CODEX_HOME")
_PRIVATE_ENV = tempfile.TemporaryDirectory(prefix="orla-contexts-")
for _name in ("config", "data", "cache", "runtime"):
    Path(_PRIVATE_ENV.name, _name).mkdir(mode=0o700)
os.environ["XDG_CONFIG_HOME"] = str(Path(_PRIVATE_ENV.name, "config"))
os.environ["XDG_DATA_HOME"] = str(Path(_PRIVATE_ENV.name, "data"))
os.environ["XDG_CACHE_HOME"] = str(Path(_PRIVATE_ENV.name, "cache"))
os.environ["XDG_RUNTIME_DIR"] = str(Path(_PRIVATE_ENV.name, "runtime"))
os.environ["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + str(Path(_PRIVATE_ENV.name, "absent-session-bus"))
os.environ["DBUS_SYSTEM_BUS_ADDRESS"] = "unix:path=" + str(Path(_PRIVATE_ENV.name, "absent-system-bus"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Fusion"
assert os.environ.get("HOME") == _ORIGINAL_HOME
assert os.environ.get("CODEX_HOME") == _ORIGINAL_CODEX_HOME

from PySide6.QtCore import QObject, QEvent, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression


class ContextsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ContextsHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.harness = self.engine.rootObjects()[0]
        self.contexts = self.harness.findChild(QObject, "contextState")
        self.bindings = self.harness.findChild(QObject, "contextBindingsState")
        self.configuration = self.harness.findChild(QObject, "contextsConfiguration")
        self.profiles = self.harness.findChild(QObject, "profilesDependency")
        self.timer = self.harness.findChild(QObject, "timerWitness")

    def tearDown(self):
        self.harness = None
        self.contexts = None
        self.bindings = None
        self.configuration = None
        self.profiles = None
        self.timer = None
        self.engine.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.engine = None
        gc.collect()
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.harness, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def set_source(self, activity, desktop, output="DP-1"):
        value = {"outputName": output, "activity": activity, "desktop": desktop}
        self.evaluate("setSource(" + json.dumps(value) + ")")
        self.app.processEvents()

    def snapshot(self):
        return json.loads(self.evaluate("JSON.stringify(snapshot)", self.contexts))

    def bind_current(self, kind, profile_id="work"):
        return self.evaluate(
            f"bind('{kind}', contexts.snapshot.{kind}, {json.dumps(profile_id)}, "
            "profiles.activeProfileId, profiles.revision, contexts.revision, revision)", self.bindings)

    def parse(self, raw):
        return json.loads(self.evaluate("JSON.stringify(parse(" + json.dumps(raw) + "))"))

    def unbind(self, kind, context_id):
        return self.evaluate(
            f"unbind('{kind}', {json.dumps(context_id)}, profiles.activeProfileId, "
            "profiles.revision, contexts.revision, revision)", self.bindings)

    def test_empty_document_stays_empty_until_explicit_bind_and_domains_normalize_independently(self):
        self.assertEqual(os.environ.get("HOME"), _ORIGINAL_HOME)
        self.assertEqual(os.environ.get("CODEX_HOME"), _ORIGINAL_CODEX_HOME)
        self.assertTrue(os.environ["DBUS_SESSION_BUS_ADDRESS"].endswith("/absent-session-bus"))
        self.assertTrue(os.environ["DBUS_SYSTEM_BUS_ADDRESS"].endswith("/absent-system-bus"))
        self.assertEqual(self.configuration.property("contextsJSON"), "")
        self.assertEqual(self.harness.property("writeCount"), 0)
        self.assertEqual(self.profiles.property("selectCalls"), 0)
        self.set_source(
            {"status": "ready", "currentId": "activity-work", "ids": ["activity-work"], "names": ["Trabalho"]},
            {"status": "ready", "currentId": "desktop-1", "ids": ["desktop-1"], "names": ["Área 1"]},
        )
        self.assertEqual(self.snapshot(), {
            "outputName": "DP-1",
            "activity": {"status": "ready", "id": "activity-work", "name": "Trabalho"},
            "desktop": {"status": "ready", "id": "desktop-1", "name": "Área 1"},
            "activities": [{"id": "activity-work", "name": "Trabalho", "current": True}],
            "desktops": [{"id": "desktop-1", "name": "Área 1", "current": True}],
        })
        self.assertEqual(self.configuration.property("contextsJSON"), "")
        self.assertEqual(self.harness.property("writeCount"), 0)

    def test_bind_captures_each_caller_context_primitive_once(self):
        self.set_source(
            {"status": "ready", "currentId": "a1", "ids": ["a1"], "names": ["Foco"]},
            {"status": "ready", "currentId": "d1", "ids": ["d1"], "names": ["Um"]},
        )
        result = json.loads(self.evaluate("""
            JSON.stringify((function() {
                var reads = {status: 0, id: 0, name: 0};
                var candidate = {};
                Object.defineProperty(candidate, "status", {enumerable: true, get: function() {
                    reads.status++; return reads.status === 1 ? "ready" : "unavailable";
                }});
                Object.defineProperty(candidate, "id", {enumerable: true, get: function() {
                    reads.id++; return reads.id === 1 ? "a1" : "forged-id";
                }});
                Object.defineProperty(candidate, "name", {enumerable: true, get: function() {
                    reads.name++; return reads.name === 1 ? "Foco" : "forged-name";
                }});
                var ok = bind("activity", candidate, "work", profiles.activeProfileId,
                    profiles.revision, contexts.revision, revision);
                return {ok: ok, reads: reads, raw: savedJSON};
            })())
        """, self.bindings))
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["reads"], {"status": 1, "id": 1, "name": 1})
        self.assertEqual(result["raw"], "")

    def install_noncanonical_binding(self):
        raw = json.dumps({
            "formatVersion": "0.1-experimental",
            "activityBindings": [
                {"contextId": "a1", "lastKnownName": "Foco", "profileId": "work"}
            ],
            "desktopBindings": [],
        }, ensure_ascii=False, indent=2)
        self.configuration.setProperty("contextsJSON", raw)
        self.app.processEvents()
        return raw, self.harness.property("writeCount"), self.bindings.property("revision")

    def test_identical_rebind_is_a_semantic_noop_preserving_raw_and_revision(self):
        self.set_source(
            {"status": "ready", "currentId": "a1", "ids": ["a1"], "names": ["Foco"]},
            {"status": "ready", "currentId": "d1", "ids": ["d1"], "names": ["Um"]},
        )
        raw, writes, revision = self.install_noncanonical_binding()
        self.assertTrue(self.bind_current("activity"))
        self.assertEqual(self.configuration.property("contextsJSON"), raw)
        self.assertEqual(self.harness.property("writeCount"), writes)
        self.assertEqual(self.bindings.property("revision"), revision)

    def test_absent_unbind_is_a_semantic_noop_preserving_raw_and_revision(self):
        raw, writes, revision = self.install_noncanonical_binding()
        self.assertTrue(self.unbind("activity", "already-absent"))
        self.assertEqual(self.configuration.property("contextsJSON"), raw)
        self.assertEqual(self.harness.property("writeCount"), writes)
        self.assertEqual(self.bindings.property("revision"), revision)

    def test_snapshot_deduplicates_updates_and_invalidates_only_the_malformed_domain(self):
        activity = {"status": "ready", "currentId": "a1", "ids": ["a1", "a2"], "names": ["Foco", "Casa"]}
        desktop = {"status": "ready", "currentId": "d2", "ids": ["d1", "d2"], "names": ["Um", "Dois"]}
        self.set_source(activity, desktop)
        revision = self.contexts.property("revision")
        detached = self.snapshot()
        detached["activity"]["name"] = "mutated outside"
        self.assertEqual(self.snapshot()["activity"]["name"], "Foco")

        self.set_source(activity, desktop)
        self.assertEqual(self.contexts.property("revision"), revision)
        renamed = dict(activity)
        renamed["names"] = ["Foco renomeado", "Casa"]
        self.set_source(renamed, desktop)
        self.assertEqual(self.contexts.property("revision"), revision + 1)
        self.assertEqual(self.snapshot()["activity"]["id"], "a1")

        duplicate = {"status": "ready", "currentId": "a1", "ids": ["a1", "a1"], "names": ["A", "B"]}
        self.set_source(duplicate, desktop)
        current = self.snapshot()
        self.assertEqual(current["activity"], {"status": "unavailable", "id": "", "name": ""})
        self.assertEqual(current["activities"], [])
        self.assertEqual(current["desktop"]["id"], "d2")

        mismatched = {"status": "ready", "currentId": "d2", "ids": ["d1", "d2"], "names": ["Um"]}
        self.set_source(activity, mismatched)
        current = self.snapshot()
        self.assertEqual(current["activity"]["id"], "a1")
        self.assertEqual(current["desktop"], {"status": "unavailable", "id": "", "name": ""})

        activity_with_unknown_key = {**activity, "unexpected": True}
        self.set_source(activity_with_unknown_key, desktop)
        current = self.snapshot()
        self.assertEqual(current["activity"], {"status": "unavailable", "id": "", "name": ""})
        self.assertEqual(current["desktop"]["id"], "d2")

    def test_mutable_source_accessors_fail_closed_without_an_incoherent_snapshot(self):
        domain = json.loads(self.evaluate("installMutableDomainWitness()"))
        self.assertEqual(domain["reads"], 1)
        self.assertEqual(domain["snapshot"]["activity"], {"status": "unavailable", "id": "", "name": ""})
        self.assertEqual(domain["snapshot"]["activities"], [])
        self.assertEqual(domain["snapshot"]["desktop"]["id"], "d1")
        self.assertEqual([item for item in domain["snapshot"]["desktops"] if item["current"]], [
            {"id": "d1", "name": "Um", "current": True}
        ])

        top_level = json.loads(self.evaluate("installMutableTopLevelWitness()"))
        self.assertEqual(top_level["reads"], 1)
        self.assertEqual(top_level["snapshot"]["outputName"], "")
        self.assertEqual(top_level["snapshot"]["activity"]["status"], "unavailable")
        self.assertEqual(top_level["snapshot"]["desktop"]["status"], "unavailable")

    def test_explicit_bind_writes_once_reloads_and_does_not_touch_profile_preview_or_timer(self):
        self.set_source(
            {"status": "ready", "currentId": "a1", "ids": ["a1"], "names": ["Foco"]},
            {"status": "ready", "currentId": "d1", "ids": ["d1"], "names": ["Um"]},
        )
        profile_scope = self.profiles.property("activeProfileId")
        profile_revision = self.profiles.property("revision")
        preview = self.harness.property("previewDraft")
        timer_deadline = self.timer.property("deadline")
        self.assertTrue(self.bind_current("activity"))
        self.assertEqual(self.harness.property("writeCount"), 1)
        self.assertEqual(json.loads(self.configuration.property("contextsJSON")), {
            "formatVersion": "0.1-experimental",
            "activityBindings": [{"contextId": "a1", "lastKnownName": "Foco", "profileId": "work"}],
            "desktopBindings": [],
        })
        self.assertEqual(self.profiles.property("activeProfileId"), profile_scope)
        self.assertEqual(self.profiles.property("revision"), profile_revision)
        self.assertEqual(self.harness.property("previewDraft"), preview)
        self.assertTrue(self.harness.property("previewDirty"))
        self.assertEqual(self.timer.property("deadline"), timer_deadline)
        self.assertEqual(self.harness.property("timerWitness"), self.timer)
        self.assertEqual(self.profiles.property("selectCalls"), 0)
        writes = self.harness.property("writeCount")
        self.assertTrue(self.bind_current("activity"))
        self.assertEqual(self.harness.property("writeCount"), writes)
        self.evaluate("recreateBindings()")
        self.app.processEvents()
        reloaded = self.harness.findChild(QObject, "reloadedContextBindingsState")
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(bindings)", reloaded))["activityBindings"][0]["contextId"], "a1")

    def test_parser_rejects_unknown_types_duplicates_versions_and_utf16_or_collection_overflow(self):
        valid_binding = {"contextId": "c" * 256, "lastKnownName": "n" * 128, "profileId": "p" * 48}
        valid = {"formatVersion": "0.1-experimental", "activityBindings": [valid_binding], "desktopBindings": []}
        self.assertFalse(self.parse(json.dumps(valid))["error"])
        invalid = [
            None, [], True, {}, {**valid, "formatVersion": "future"}, {**valid, "extra": False},
            {**valid, "activityBindings": "bad"},
            {**valid, "activityBindings": [valid_binding, valid_binding]},
            {**valid, "activityBindings": [{**valid_binding, "contextId": ""}]},
            {**valid, "activityBindings": [{**valid_binding, "contextId": "x" * 257}]},
            {**valid, "activityBindings": [{**valid_binding, "lastKnownName": "x" * 129}]},
            {**valid, "activityBindings": [{**valid_binding, "profileId": "legacy"}]},
            {**valid, "activityBindings": [{**valid_binding, "profileId": "Upper"}]},
            {**valid, "activityBindings": [{**valid_binding, "extra": 1}]},
        ]
        for index, value in enumerate(invalid):
            with self.subTest(case=index):
                self.assertTrue(self.parse(json.dumps(value))["error"])
        sixty_four = [{"contextId": f"a{index}", "lastKnownName": "", "profileId": "work"} for index in range(64)]
        self.assertFalse(self.parse(json.dumps({**valid, "activityBindings": sixty_four}))["error"])
        self.assertTrue(self.parse(json.dumps({**valid, "activityBindings": sixty_four + [{"contextId": "overflow", "lastKnownName": "", "profileId": "work"}]}))["error"])
        raw = json.dumps({"formatVersion": "0.1-experimental", "activityBindings": [], "desktopBindings": []})
        self.assertFalse(self.parse(raw + " " * (131072 - len(raw)))["error"])
        self.assertIn("grandes", self.parse("😀" * 65537)["error"])

    def test_stale_scope_profile_context_and_binding_revisions_reject_without_extra_write(self):
        self.set_source(
            {"status": "ready", "currentId": "a1", "ids": ["a1"], "names": ["Foco"]},
            {"status": "ready", "currentId": "d1", "ids": ["d1"], "names": ["Um"]},
        )
        scope = self.profiles.property("activeProfileId")
        profile_revision = self.profiles.property("revision")
        context_revision = self.contexts.property("revision")
        binding_revision = self.bindings.property("revision")
        candidate = {"status": "ready", "id": "a1", "name": "Foco"}
        saved = self.configuration.property("contextsJSON")

        self.set_source(
            {"status": "ready", "currentId": "a2", "ids": ["a2"], "names": ["Outro"]},
            {"status": "ready", "currentId": "d1", "ids": ["d1"], "names": ["Um"]},
        )
        self.assertFalse(self.evaluate(
            "bind('activity'," + json.dumps(candidate) + f",'work',{json.dumps(scope)},{profile_revision},{context_revision},{binding_revision})",
            self.bindings))
        self.assertEqual(self.configuration.property("contextsJSON"), saved)

        self.profiles.setProperty("revision", profile_revision + 1)
        self.assertFalse(self.evaluate(
            "bind('activity',contexts.snapshot.activity,'work',profiles.activeProfileId," +
            f"{profile_revision},contexts.revision,revision)", self.bindings))
        self.profiles.setProperty("revision", profile_revision)
        self.profiles.setProperty("activeProfileId", "work")
        self.assertFalse(self.evaluate(
            f"bind('activity',contexts.snapshot.activity,'work',{json.dumps(scope)},profiles.revision,contexts.revision,revision)",
            self.bindings))
        self.profiles.setProperty("activeProfileId", scope)

        external = '{"formatVersion":"0.1-experimental","activityBindings":[],"desktopBindings":[]}'
        before_external = self.harness.property("writeCount")
        self.configuration.setProperty("contextsJSON", external)
        self.app.processEvents()
        self.assertEqual(self.harness.property("writeCount"), before_external + 1)
        self.assertFalse(self.evaluate(
            "bind('activity',contexts.snapshot.activity,'work',profiles.activeProfileId,profiles.revision,contexts.revision," +
            str(binding_revision) + ")", self.bindings))
        self.assertEqual(self.harness.property("writeCount"), before_external + 1)

    def test_identity_is_id_domains_are_independent_and_removed_bindings_survive_until_explicit_unbind(self):
        self.set_source(
            {"status": "ready", "currentId": "same", "ids": ["same"], "names": ["Nome inicial"]},
            {"status": "ready", "currentId": "same", "ids": ["same"], "names": ["Área inicial"]},
        )
        self.assertTrue(self.bind_current("activity", "work"))
        self.assertTrue(self.bind_current("desktop", "personal"))
        self.set_source(
            {"status": "ready", "currentId": "same", "ids": ["same"], "names": ["Renomeada"]},
            {"status": "ready", "currentId": "same", "ids": ["same"], "names": ["Área renomeada"]},
        )
        self.assertTrue(self.bind_current("activity", "games"))
        document = json.loads(self.configuration.property("contextsJSON"))
        self.assertEqual(document["activityBindings"], [{"contextId": "same", "lastKnownName": "Renomeada", "profileId": "games"}])
        self.assertEqual(document["desktopBindings"], [{"contextId": "same", "lastKnownName": "Área inicial", "profileId": "personal"}])

        self.set_source(
            {"status": "unavailable", "currentId": "", "ids": [], "names": []},
            {"status": "ready", "currentId": "other", "ids": ["other"], "names": ["Outra"]},
        )
        self.assertEqual(json.loads(self.configuration.property("contextsJSON")), document)
        self.assertTrue(self.unbind("activity", "same"))
        after = json.loads(self.configuration.property("contextsJSON"))
        self.assertEqual(after["activityBindings"], [])
        self.assertEqual(after["desktopBindings"], document["desktopBindings"])

    def test_invalid_raw_keeps_last_valid_bindings_and_profile_failure_blocks_only_associations(self):
        self.set_source(
            {"status": "ready", "currentId": "a1", "ids": ["a1"], "names": ["Foco"]},
            {"status": "ready", "currentId": "d1", "ids": ["d1"], "names": ["Um"]},
        )
        self.assertTrue(self.bind_current("activity"))
        valid_bindings = json.loads(self.evaluate("JSON.stringify(bindings)", self.bindings))
        invalid_raw = '{"formatVersion":"future","preserve":"owned bytes"}'
        self.configuration.setProperty("contextsJSON", invalid_raw)
        self.app.processEvents()
        self.assertFalse(self.bindings.property("writable"))
        self.assertEqual(self.configuration.property("contextsJSON"), invalid_raw)
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(bindings)", self.bindings)), valid_bindings)
        before = self.harness.property("writeCount")
        self.assertFalse(self.bind_current("desktop"))
        self.assertEqual(self.harness.property("writeCount"), before)
        self.assertTrue(self.profiles.property("writable"))

        self.configuration.setProperty("contextsJSON", "")
        self.app.processEvents()
        self.profiles.setProperty("writable", False)
        before = self.harness.property("writeCount")
        self.assertFalse(self.bind_current("activity"))
        self.assertFalse(self.bind_current("activity", "legacy"))
        self.assertFalse(self.bind_current("activity", "missing"))
        self.assertEqual(self.harness.property("writeCount"), before)
        self.assertEqual(self.configuration.property("contextsJSON"), "")


if __name__ == "__main__":
    unittest.main()
