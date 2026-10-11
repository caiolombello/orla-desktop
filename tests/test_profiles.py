import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression


class ProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("ProfilesHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.harness = self.engine.rootObjects()[0]
        self.state = self.harness.findChild(QObject, "profileState")
        self.config = self.harness.findChild(QObject, "profilesConfiguration")

    def tearDown(self):
        self.engine.deleteLater()
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.state, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def configuration_value(self, key):
        value = self.config.property(key)
        return value.toVariant() if hasattr(value, "toVariant") else value

    def initialize(self):
        self.assertTrue(self.evaluate("initializeDefaults(activeProfileId, revision)"))
        return json.loads(self.config.property("profilesJSON"))

    def parse(self, value):
        raw = value if isinstance(value, str) else json.dumps(value)
        return json.loads(self.evaluate(f"JSON.stringify(parse({json.dumps(raw)}))", self.harness))

    def command(self, name, *args):
        return self.evaluate(f"{name}({','.join(json.dumps(value) for value in args)},activeProfileId,revision)")

    def snapshot(self):
        return json.loads(self.evaluate("JSON.stringify(effective)"))

    def test_empty_configuration_stays_legacy_until_explicit_initialization(self):
        baseline = {key: self.configuration_value(key) for key in ("profilesJSON", "appearanceJSON", "launchers", "timerDeadline")}
        self.assertEqual(self.state.property("activeProfileId"), "legacy")
        self.assertEqual(self.evaluate("effective.appearance.iconSize"), 42)
        self.evaluate("legacyPresentation.widgets[0].visible = false; legacyPresentation.appearance.iconSize = 64")
        self.assertTrue(self.evaluate("initializeDefaults(activeProfileId, revision)"))
        saved = json.loads(self.config.property("profilesJSON"))
        self.assertEqual(saved["activeProfileId"], "legacy")
        self.assertEqual([profile["name"] for profile in saved["profiles"]], ["Trabalho", "Pessoal", "Jogos"])
        self.assertEqual(saved["profiles"][0]["appearance"]["iconSize"], 42)
        self.assertTrue(saved["profiles"][0]["widgets"][0]["visible"])
        for key in ("appearanceJSON", "launchers", "timerDeadline"):
            self.assertEqual(self.configuration_value(key), baseline[key])
        self.assertEqual(self.warnings, [])

    def test_invalid_document_and_composition_are_rejected_without_rewriting(self):
        saved = self.initialize()
        invalid = [{**saved, "activeProfileId": "missing"}, {**saved, "profiles": []},
                   {**saved, "formatVersion": "future"}, {**saved, "timerDeadline": 10}]
        for field, value in (("id", "legacy"), ("name", " "), ("name", "bad\nname"),
                             ("widgets", saved["profiles"][0]["widgets"][:-1]),
                             ("launchers", ["https://example.org/a.desktop"]),
                             ("calendarEvents", 1)):
            candidate = json.loads(json.dumps(saved))
            candidate["profiles"][0][field] = value
            invalid.append(candidate)
        for index, candidate in enumerate(invalid):
            with self.subTest(case=index):
                raw = json.dumps(candidate)
                self.assertTrue(self.parse(raw)["error"])
                self.config.setProperty("profilesJSON", raw)
                self.assertFalse(self.state.property("writable"))
                self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertEqual(self.warnings, [])

    def test_switch_create_and_partial_commits_keep_other_profiles_and_flat_state(self):
        flat = self.snapshot()
        deadline = self.config.property("timerDeadline")
        self.initialize()
        self.assertTrue(self.command("select", "work"))
        self.assertTrue(self.command("commitPresentation", {"appearance": {"iconSize": 56}}))
        widgets = self.snapshot()["widgets"]
        widgets.reverse()
        widgets[0]["visible"] = False
        self.assertTrue(self.command("commitPresentation", {"widgets": widgets, "calendarEvents": False}))
        self.assertTrue(self.command("commitPresentation", {"appearance": {"theme": "paper"}}))
        work = self.snapshot()
        self.assertEqual(work["widgets"], widgets)
        self.assertFalse(work["calendarEvents"])
        self.assertTrue(self.command("select", "personal"))
        self.assertEqual(self.snapshot(), flat)
        self.assertTrue(self.command("select", "work"))
        self.assertTrue(self.command("create", "Custom"))
        custom_id = self.state.property("activeProfileId")
        self.assertNotIn(custom_id, ("work", "personal", "games", "legacy"))
        self.assertEqual(self.snapshot(), work)
        self.assertTrue(self.command("commitPresentation", {"launchers": []}))
        self.assertTrue(self.command("select", "work"))
        self.assertEqual(self.snapshot(), work)
        self.assertTrue(self.command("select", "legacy"))
        self.assertEqual(self.snapshot(), flat)
        self.assertEqual(self.config.property("timerDeadline"), deadline)
        self.evaluate("recreateState()", self.harness)
        reloaded = self.harness.findChild(QObject, "reloadedProfiles")
        self.assertEqual(self.evaluate("activeProfileId", reloaded), "legacy")
        self.assertEqual(self.evaluate("JSON.stringify(effective)", reloaded), self.evaluate("JSON.stringify(effective)"))
        self.assertEqual(self.warnings, [])

    def test_scope_revision_and_transition_guard_reject_stale_writes(self):
        self.initialize()
        revision = self.state.property("revision")
        saved = self.config.property("profilesJSON")
        for expression in ("select('work')", "initializeDefaults()", "create('X')",
                           "commitPresentation({calendarEvents:false})",
                           f"select('work','personal',{revision})", f"select('work','legacy',{revision - 1})"):
            self.assertFalse(self.evaluate(expression))
            self.assertEqual(self.config.property("profilesJSON"), saved)
        self.evaluate("transitionGuard = function() { return false; }")
        self.assertFalse(self.command("select", "work"))
        self.assertFalse(self.command("create", "X"))
        self.assertIn("prévia", self.state.property("error"))
        self.evaluate("transitionGuard = function() { configuration.calendarEvents = false; return true; }")
        self.assertFalse(self.command("select", "work"))
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.evaluate("transitionGuard = null")
        self.assertTrue(self.command("select", "work"))
        self.assertFalse(self.evaluate(f"commitPresentation({{calendarEvents:false}},'legacy',{revision})"))
        stable = self.config.property("profilesJSON")
        self.assertTrue(self.command("select", "work"))
        self.assertEqual(self.config.property("profilesJSON"), stable)

    def test_validator_enforces_bounded_names_ids_arrays_types_and_local_urls(self):
        doc = self.initialize()
        doc["profiles"] = doc["profiles"][:1]
        baseline = json.loads(json.dumps(doc))
        invalid_fields = [
            ("id", "x" * 49), ("id", "Upper"), ("id", ""), ("name", "x" * 49),
            ("name", "bad\u0085name"), ("launchers", ["applications:a.desktop"] * 2),
            ("launchers", [f"applications:a{i}.desktop" for i in range(33)]),
            ("launchers", ["file:///" + "a" * 2048 + ".desktop"]),
            ("widgets", [doc["profiles"][0]["widgets"][0]] * 7), ("currentDesktopOnly", "false")]
        for url in ("a.desktop", "file://remote/a.desktop", "file:////remote/a.desktop", "file:///a.desktop?q=x",
                    "file:///a.desktop#x", "file:///a%xy.desktop", "file:///a%.desktop",
                    "file:///a%FF.desktop", "file:///a%0a.desktop", "file:///a\t.desktop", "file:///../a.desktop",
                    "file:///%2e%2e/a.desktop", "https://site/a.desktop", "file:///a\\b.desktop", "file:///%2fhost/a.desktop"):
            invalid_fields.append(("launchers", [url]))
        for index, (field, value) in enumerate(invalid_fields):
            candidate = json.loads(json.dumps(baseline))
            candidate["profiles"][0][field] = value
            with self.subTest(field=field, case=index):
                self.assertTrue(self.parse(candidate)["error"])
        for field, value in (("theme", "unknown"), ("iconSize", 23), ("iconSize", 65), ("iconSize", 24.5),
                             ("iconSize", True), ("animations", 1), ("appearanceJSON", "bad"),
                             ("appearanceJSON", "x" * 4097)):
            candidate = json.loads(json.dumps(baseline))
            candidate["profiles"][0]["appearance"][field] = value
            self.assertTrue(self.parse(candidate)["error"], field)
        for extra in ("timerDeadline", "sourceComponent", "unexpected"):
            candidate = json.loads(json.dumps(baseline))
            candidate["profiles"][0][extra] = 1
            self.assertTrue(self.parse(candidate)["error"])
        candidate = json.loads(json.dumps(baseline))
        candidate["profiles"][0]["widgets"][0]["visible"] = 1
        self.assertTrue(self.parse(candidate)["error"])
        candidate = json.loads(json.dumps(baseline))
        candidate["profiles"][0]["appearance"]["extra"] = False
        self.assertTrue(self.parse(candidate)["error"])
        candidate = json.loads(json.dumps(baseline))
        candidate["profiles"] *= 2
        self.assertTrue(self.parse(candidate)["error"])
        for invalid in (None, [], True, {}, "{", "x" * 131073):
            self.assertTrue(self.parse(invalid)["error"])

        valid = json.loads(json.dumps(baseline))
        valid["profiles"][0]["name"] = "n" * 48
        valid["profiles"][0]["id"] = "i" * 48
        valid["profiles"][0]["launchers"] = [f"applications:a{i}.desktop" for i in range(32)]
        valid["profiles"][0]["widgets"] = [{"id": widget["id"], "visible": False} for widget in valid["profiles"][0]["widgets"]]
        self.assertFalse(self.parse(valid)["error"])
        for url in ("file:///home/test/My%20App.desktop", "file:///home/test/My App.desktop", "file:///" + "a" * 2032 + ".desktop", "applications:org.test.App.desktop"):
            valid["profiles"][0]["launchers"] = [url]
            self.assertFalse(self.parse(valid)["error"], url[:64])
        raw = json.dumps(baseline)
        self.assertFalse(self.parse(raw + " " * (131072 - len(raw)))["error"])
        self.assertTrue(self.parse(raw + " " * (131073 - len(raw)))["error"])
        valid = json.loads(json.dumps(baseline))
        valid["profiles"] = [{**valid["profiles"][0], "id": f"p{i}", "name": f"Profile {i}"} for i in range(16)]
        self.assertFalse(self.parse(valid)["error"])
        valid["profiles"].append({**valid["profiles"][0], "id": "extra", "name": "Extra"})
        self.assertTrue(self.parse(valid)["error"])

    def test_invalid_runtime_keeps_last_valid_scope_and_cold_reload_uses_flat(self):
        self.initialize()
        self.assertTrue(self.command("select", "work"))
        self.assertTrue(self.command("commitPresentation", {"appearance": {"iconSize": 60}}))
        previous_revision = self.state.property("revision")
        previous = self.snapshot()
        valid_raw = self.config.property("profilesJSON")
        invalid_raw = '{"formatVersion":"future"}'
        self.config.setProperty("profilesJSON", invalid_raw)
        self.assertFalse(self.state.property("writable"))
        self.assertGreater(self.state.property("revision"), previous_revision)
        self.assertEqual(self.state.property("activeProfileId"), "work")
        self.assertEqual(self.snapshot(), previous)
        for name, argument in (("select", "legacy"), ("create", "Custom"), ("commitPresentation", {"calendarEvents": False})):
            self.assertFalse(self.command(name, argument))
            self.assertEqual(self.config.property("profilesJSON"), invalid_raw)
        self.assertFalse(self.evaluate("initializeDefaults(activeProfileId,revision)"))
        self.evaluate("recreateState()", self.harness)
        reloaded = self.harness.findChild(QObject, "reloadedProfiles")
        self.assertEqual(self.evaluate("activeProfileId", reloaded), "legacy")
        self.assertEqual(self.evaluate("effective.appearance.iconSize", reloaded), 42)
        self.assertFalse(self.evaluate("writable", reloaded))
        self.assertEqual(self.config.property("profilesJSON"), invalid_raw)
        self.config.setProperty("profilesJSON", valid_raw)
        self.assertTrue(self.state.property("writable"))
        self.assertEqual(self.snapshot(), previous)
        self.assertFalse(self.evaluate(f"commitPresentation({{calendarEvents:false}},'work',{previous_revision})"))
        self.config.setProperty("profilesJSON", "")
        self.assertEqual(self.state.property("activeProfileId"), "legacy")
        self.assertEqual(self.snapshot()["appearance"]["iconSize"], 42)

    def test_legacy_patch_is_atomic_on_validation_and_cannot_persist_order_or_timer_fields(self):
        before = self.snapshot()
        timer_keys = ["focusMinutes", "breakMinutes", "timerDeadline", "timerRemaining", "timerBreak", "completedFocus"]
        timer = {key: self.config.property(key) for key in timer_keys}
        self.assertFalse(self.command("commitPresentation", {"calendarEvents": False, "appearance": {"iconSize": 12}}))
        self.assertEqual(self.snapshot(), before)
        widgets = before["widgets"]
        widgets.reverse()
        self.assertFalse(self.command("commitPresentation", {"widgets": widgets}))
        self.assertIn("Crie/use um perfil", self.state.property("error"))
        for key in timer_keys:
            self.assertFalse(self.command("commitPresentation", {key: 0}))
        widgets.reverse()
        widgets[0]["visible"] = False
        self.assertTrue(self.command("commitPresentation", {"widgets": widgets, "appearance": {"iconSize": 55}, "calendarEvents": False}))
        self.assertFalse(self.config.property("showClock"))
        self.assertEqual(self.config.property("iconSize"), 55)
        self.assertEqual(self.config.property("profilesJSON"), "")
        self.assertEqual({key: self.config.property(key) for key in timer_keys}, timer)
        self.assertTrue(self.evaluate("initializeDefaults(activeProfileId,revision)"))
        self.assertTrue(self.command("select", "games"))
        self.assertTrue(self.command("commitPresentation", {"widgets": list(reversed(widgets))}))
        self.assertEqual({key: self.config.property(key) for key in timer_keys}, timer)

    def test_capture_invalid_appearance_preserves_flat_bytes_and_base_preferences(self):
        self.config.setProperty("appearanceJSON", "{invalid")
        self.config.setProperty("theme", "midnight")
        self.config.setProperty("iconSize", 53)
        self.config.setProperty("animations", False)
        saved = self.initialize()
        self.assertTrue(self.state.property("message"))
        self.assertEqual(self.config.property("appearanceJSON"), "{invalid")
        self.assertEqual(saved["profiles"][0]["appearance"], {"theme": "midnight", "iconSize": 53, "animations": False, "appearanceJSON": ""})
        self.assertTrue(self.command("select", "work"))
        self.assertTrue(self.command("select", "legacy"))
        self.assertEqual(self.snapshot()["appearance"]["appearanceJSON"], "{invalid")
        self.assertTrue(self.command("commitPresentation", {"calendarEvents": False}))
        self.assertEqual(self.config.property("appearanceJSON"), "{invalid")
        self.config.setProperty("profilesJSON", "")
        self.config.setProperty("theme", "unknown")
        self.assertFalse(self.evaluate("initializeDefaults(activeProfileId,revision)"))
        self.assertEqual(self.config.property("profilesJSON"), "")

    def test_public_snapshot_mutations_never_change_saved_or_captured_state(self):
        self.initialize()
        self.assertTrue(self.command("select", "work"))
        before = self.snapshot()
        raw = self.config.property("profilesJSON")
        self.evaluate("effective.appearance.iconSize = 64; effective.widgets[0].visible = false")
        self.evaluate("try { effective.launchers.push('applications:bad.desktop'); } catch (_) {}")
        self.evaluate("try { Array.prototype.push.call(effective.widgets,{id:'foreign',visible:true}); } catch (_) {}")
        self.evaluate("effective.launchers[0] = 'applications:other.desktop'")
        self.evaluate("try { Array.prototype.push.call(profiles,{id:'foreign',name:'Foreign'}); } catch (_) {}")
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.evaluate("recreateState()", self.harness)
        reloaded = self.harness.findChild(QObject, "reloadedProfiles")
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(effective)", reloaded)), before)
        self.assertTrue(self.command("create", " Custom "))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(json.loads(self.config.property("profilesJSON"))["profiles"][-1]["name"], "Custom")
        stable = self.config.property("profilesJSON")
        for name in ("Custom", "  ", "a" * 49, "bad\nname"):
            self.assertFalse(self.command("create", name))
            self.assertEqual(self.config.property("profilesJSON"), stable)

    def test_oversize_candidate_and_invalid_partial_patch_never_replace_saved_document(self):
        self.initialize()
        self.assertTrue(self.command("select", "work"))
        long_urls = ["file:///" + str(i) + "x" * 2020 + ".desktop" for i in range(32)]
        self.assertTrue(self.command("commitPresentation", {"launchers": long_urls}))
        self.assertTrue(self.command("select", "personal"))
        stable = self.config.property("profilesJSON")
        self.assertFalse(self.command("commitPresentation", {"launchers": long_urls}))
        self.assertEqual(self.config.property("profilesJSON"), stable)
        for patch in ({"appearance": {"timerDeadline": 1}}, {"widgets": []}, {"launchers": ["https://invalid/a.desktop"]}, {"calendarEvents": "true"}):
            self.assertFalse(self.command("commitPresentation", patch))
            self.assertEqual(self.config.property("profilesJSON"), stable)
        self.assertEqual(self.warnings, [])

    def test_custom_creation_from_empty_is_explicit_bounded_and_preserves_timer(self):
        before = self.snapshot()
        self.assertTrue(self.command("create", "First"))
        self.assertEqual(len(json.loads(self.config.property("profilesJSON"))["profiles"]), 1)
        self.assertEqual(self.snapshot(), before)
        for index in range(1, 16):
            self.assertTrue(self.command("create", f"Custom {index}"))
        saved = self.config.property("profilesJSON")
        profiles = json.loads(saved)["profiles"]
        self.assertEqual(len({profile["id"] for profile in profiles}), 16)
        self.assertFalse(self.command("create", "Seventeenth"))
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.assertFalse(self.evaluate("initializeDefaults(activeProfileId,revision)"))
        self.assertEqual(self.config.property("timerDeadline"), 1234567890000)
        self.assertEqual(self.config.property("completedFocus"), 3)

    def test_appearance_override_uses_existing_validator_and_profile_clone_remains_independent(self):
        override = {"formatVersion": "0.1-experimental", "baseTheme": "paper", "tokens": {
            "foreground": "#252b35", "muted": "#657180", "accent": "#167361", "surface": "#f4f0e8",
            "border": "#cec9bf", "radius": 12, "spacing": 8, "opacity": 0.7, "iconSize": 48, "reducedMotion": True}}
        raw = json.dumps(override)
        self.config.setProperty("appearanceJSON", raw)
        self.initialize()
        self.assertTrue(self.command("select", "work"))
        self.assertEqual(self.snapshot()["appearance"]["appearanceJSON"], raw)
        stable = self.config.property("profilesJSON")
        invalid = [{**override, "formatVersion": "future"}, {**override, "unexpected": True}]
        for key, value in (("radius", 33), ("opacity", True), ("accent", "#fff"), ("reducedMotion", "true")):
            candidate = json.loads(raw)
            candidate["tokens"][key] = value
            invalid.append(candidate)
        for candidate in invalid:
            self.assertFalse(self.command("commitPresentation", {"appearance": {"appearanceJSON": json.dumps(candidate)}}))
            self.assertEqual(self.config.property("profilesJSON"), stable)
        for number in ("NaN", "Infinity", "-Infinity"):
            self.assertFalse(self.evaluate(f"commitPresentation({{appearance:{{iconSize:{number}}}}},activeProfileId,revision)"))
        self.assertTrue(self.command("commitPresentation", {"appearance": {"appearanceJSON": ""}}))
        self.assertTrue(self.command("select", "personal"))
        self.assertEqual(self.snapshot()["appearance"]["appearanceJSON"], raw)
        self.assertEqual(self.config.property("appearanceJSON"), raw)

    def test_reentrant_patch_read_cannot_save_into_a_different_profile(self):
        self.initialize()
        self.assertTrue(self.command("select", "work"))
        original = json.loads(self.config.property("profilesJSON"))
        switched = {**original, "activeProfileId": "personal"}
        switched_raw = json.dumps(switched)
        source = """(function() {
            const scope = activeProfileId;
            const expectedRevision = revision;
            const patch = {};
            Object.defineProperty(patch, 'calendarEvents', {enumerable:true, get:function() {
                configuration.profilesJSON = %s;
                return false;
            }});
            return commitPresentation(patch, scope, expectedRevision);
        })()""" % json.dumps(switched_raw)
        self.assertFalse(self.evaluate(source))
        self.assertIn("configuração mudou", self.state.property("error"))
        self.assertEqual(self.state.property("activeProfileId"), "personal")
        self.assertEqual(self.config.property("profilesJSON"), switched_raw)
        self.assertEqual(json.loads(self.config.property("profilesJSON"))["profiles"], original["profiles"])
        self.assertTrue(self.snapshot()["calendarEvents"])
        self.assertEqual(self.warnings, [])


if __name__ == "__main__":
    unittest.main()
