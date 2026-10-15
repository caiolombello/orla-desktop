"""Automatic profile selection with real portable states; no KDE/service access."""
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression


class AutoContextProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("AutoContextProfilesHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.root = self.engine.rootObjects()[0]
        self.profiles = self.root.findChild(QObject, "profiles")
        self.config = self.root.findChild(QObject, "configuration")
        self.contexts = self.root.findChild(QObject, "contexts")
        self.bindings = self.root.findChild(QObject, "bindings")

    def tearDown(self):
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None, settle=True):
        expression = QQmlExpression(self.engine.rootContext(), target or self.root, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        if settle:
            self.settle()
        return value

    def settle(self):
        for _ in range(5):
            self.app.processEvents()

    def initialize(self):
        self.assertTrue(self.evaluate("initializeDefaults(activeProfileId, revision)", self.profiles))

    def context(self, activity="a1", desktop="d1", activity_status="ready", desktop_status="ready", settle=True):
        frame = {"outputName":"", "activity":{"status":activity_status,"currentId":activity,
            "ids":["a1","a2","a3"],"names":["Foco","Lazer","Outro"]},
            "desktop":{"status":desktop_status,"currentId":desktop,
            "ids":["d1","d2","d3"],"names":["Um","Dois","Três"]}}
        self.evaluate("sourceSnapshot=" + json.dumps(frame), settle=settle)

    def test_enabled_ready_context_automatically_selects_default_once(self):
        self.initialize()
        self.context()
        before = self.root.property("writes")
        self.evaluate("configuration.autoContextDefaultProfile='work'; configuration.autoContextEnabled=true; running=true")
        self.assertEqual(self.profiles.property("activeProfileId"), "work")
        self.assertEqual(self.root.property("writes"), before + 1)
        self.assertEqual(self.config.property("timerDeadline"), 1234567890000)

    def enable(self, default="games"):
        self.assertTrue(self.evaluate(f"automatic.setDefaultProfile({json.dumps(default)})"))
        self.assertTrue(self.evaluate("automatic.setEnabled(true); running=true; automatic.enabled"))

    def manual(self, profile):
        self.assertTrue(self.evaluate(f"select({json.dumps(profile)},activeProfileId,revision)", self.profiles))

    def bind(self, kind, profile):
        self.assertTrue(self.evaluate(f"bind({json.dumps(kind)},contexts.snapshot.{kind},{json.dumps(profile)},"
            "profiles.activeProfileId,profiles.revision,contexts.revision,revision)", self.bindings))

    def prepare(self):
        self.initialize()
        self.context()

    def selected(self):
        return self.profiles.property("activeProfileId")

    def override(self):
        return self.evaluate("automatic.manualOverride")

    def test_off_preferences_no_implicit_profiles_or_enable_and_invalid_enabled_can_disable(self):
        self.context()
        self.evaluate("running=true")
        self.assertFalse(self.evaluate("automatic.canEnable"))
        self.assertFalse(self.evaluate("automatic.observing"))
        self.assertFalse(self.evaluate("automatic.setEnabled(true)"))
        self.assertFalse(self.evaluate("automatic.setDefaultProfile('legacy')"))
        self.assertEqual(self.config.property("profilesJSON"), "")
        self.initialize()
        before = self.root.property("writes")
        self.assertTrue(self.evaluate("automatic.setDefaultProfile('work')"))
        self.assertFalse(self.evaluate("automatic.enabled"))
        self.assertFalse(self.evaluate("automatic.setEnabled('true')"))
        self.assertEqual(self.root.property("writes"), before)
        self.evaluate("configuration.autoContextEnabled=true; configuration.autoContextDefaultProfile='missing'")
        self.assertFalse(self.evaluate("automatic.canEnable"))
        self.assertTrue(self.evaluate("automatic.setEnabled(false)"))
        self.assertFalse(self.evaluate("automatic.enabled"))

    def test_activity_beats_desktop_then_default_with_real_associations(self):
        self.prepare()
        self.bind("activity", "work")
        self.bind("desktop", "personal")
        self.enable()
        self.assertEqual(self.selected(), "work")
        self.context("a2")
        self.assertEqual(self.selected(), "personal")
        self.context("a2", "d2")
        self.assertEqual(self.selected(), "games")
        before = self.root.property("writes")
        self.context("a3", "d3")
        self.assertEqual(self.selected(), "games")
        self.assertEqual(self.root.property("writes"), before)
        self.assertIn("padrão", self.evaluate("automatic.statusText"))

    def test_observing_does_not_depend_on_ready_and_both_domains_are_required(self):
        self.initialize()
        self.enable("work")
        self.assertTrue(self.evaluate("automatic.observing"))
        self.assertEqual(self.selected(), "legacy")
        self.context(desktop_status="unavailable")
        self.assertEqual(self.selected(), "legacy")
        self.assertIn("Aguardando contexto", self.evaluate("automatic.statusText"))
        self.context()
        self.assertEqual(self.selected(), "work")
        before = self.root.property("writes")
        self.context("a2", activity_status="loading")
        self.assertEqual(self.root.property("writes"), before)

    def test_manual_override_survives_rename_outage_binding_and_default_changes(self):
        self.prepare()
        self.enable("work")
        self.manual("personal")
        self.assertTrue(self.override())
        self.evaluate("sourceSnapshot=Object.assign({},sourceSnapshot,{activity:Object.assign({},sourceSnapshot.activity,{names:['Novo','Lazer','Outro']})})")
        self.assertTrue(self.override())
        self.context("a2", activity_status="unavailable")
        self.context()
        self.bind("activity", "games")
        self.evaluate("automatic.setDefaultProfile('games')")
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.context("a2")
        self.assertFalse(self.override())
        self.assertEqual(self.selected(), "games")

    def test_observed_context_aba_clears_manual_override_even_without_settling(self):
        self.prepare()
        self.bind("activity", "work")
        self.enable()
        self.manual("personal")
        self.context("a2", settle=False)
        self.context("a1", settle=False)
        self.settle()
        self.assertFalse(self.override())
        self.assertEqual(self.selected(), "work")

    def test_busy_keeps_draft_and_timer_and_selects_only_latest_context(self):
        self.prepare()
        self.bind("activity", "work")
        self.context("a2")
        self.bind("activity", "personal")
        self.context()
        self.enable()
        before = self.root.property("writes")
        self.evaluate("busy=true; previewDirty=true")
        self.context("a2")
        self.context("a3")
        self.assertEqual(self.selected(), "work")
        self.assertEqual(self.root.property("writes"), before)
        self.assertTrue(self.root.property("previewDirty"))
        self.assertIn("adiada", self.evaluate("automatic.statusText"))
        self.evaluate("previewDirty=false; busy=false")
        self.assertEqual(self.selected(), "games")
        self.assertEqual(self.root.property("writes"), before + 1)
        self.assertEqual(self.config.property("timerDeadline"), 1234567890000)

    def test_resume_is_explicit_and_disabling_cancels_pending_without_restoration(self):
        self.prepare()
        self.enable("work")
        self.manual("personal")
        self.assertTrue(self.evaluate("automatic.resume()"))
        self.assertEqual(self.selected(), "work")
        self.evaluate("busy=true; automatic.setDefaultProfile('games'); automatic.setEnabled(false); busy=false")
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.evaluate("automatic.observing"))
        self.assertFalse(self.evaluate("automatic.resume()"))

    def test_create_is_manual_but_same_profile_content_edit_is_not(self):
        self.prepare()
        self.enable("work")
        self.assertTrue(self.evaluate("commitPresentation({calendarEvents:false},activeProfileId,revision)", self.profiles))
        self.assertFalse(self.override())
        self.assertTrue(self.evaluate("create('Novo',activeProfileId,revision)", self.profiles))
        self.assertTrue(self.override())
        self.assertTrue(self.selected().startswith("custom-"))

    def test_restart_enabled_hydrates_without_manual_override(self):
        self.prepare()
        self.enable("work")
        self.manual("personal")
        self.assertTrue(self.override())
        self.evaluate("restartController()")
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.override())

    def test_unavailable_binding_target_pauses_instead_of_silent_fallback(self):
        self.prepare()
        self.bind("activity", "personal")
        self.evaluate("configuration.profilesJSON=JSON.stringify(Object.assign({},JSON.parse(configuration.profilesJSON),"
            "{profiles:JSON.parse(configuration.profilesJSON).profiles.filter(p=>p.id!=='personal')}))")
        before = self.root.property("writes")
        self.enable("work")
        self.assertEqual(self.selected(), "legacy")
        self.assertIn("associado", self.evaluate("automatic.statusText"))
        self.assertEqual(self.root.property("writes"), before)

    def test_invalid_saved_documents_remain_byte_exact_without_repair(self):
        self.prepare()
        for key in ("contextsJSON", "profilesJSON"):
            with self.subTest(key=key):
                original = self.config.property(key)
                invalid = '{"formatVersion":"future","opaque":"KEEP"}'
                self.config.setProperty(key, invalid)
                self.evaluate("configuration.autoContextDefaultProfile='work';configuration.autoContextEnabled=true;running=true")
                self.assertFalse(self.evaluate("automatic.canEnable"))
                self.assertEqual(self.config.property(key), invalid)
                self.evaluate("automatic.setEnabled(false)")
                self.config.setProperty(key, original)
                self.settle()

    def test_transition_guard_context_change_cannot_commit_old_target(self):
        self.prepare()
        self.bind("activity", "work")
        self.evaluate("transitionHook=() => { transitionHook=null; sourceSnapshot=Object.assign({},sourceSnapshot,"
            "{activity:Object.assign({},sourceSnapshot.activity,{currentId:'a2'})}); return true; }")
        before = self.root.property("writes")
        self.enable("games")
        self.assertEqual(self.selected(), "games")
        self.assertEqual(self.root.property("writes"), before + 1)
        events = json.loads(self.evaluate("JSON.stringify(selections)"))
        self.assertNotIn("work", events)

    def test_transition_guard_changes_bindings_default_disable_and_profile_removal(self):
        self.prepare()
        self.bind("activity", "work")
        self.evaluate("transitionHook=() => { transitionHook=null; configuration.contextsJSON=JSON.stringify("
            "Object.assign({},JSON.parse(configuration.contextsJSON),{activityBindings:[]})); return true; }")
        self.enable("games")
        self.assertEqual(self.selected(), "games")
        self.assertNotIn("work", json.loads(self.evaluate("JSON.stringify(selections)")))
        self.evaluate("busy=true; automatic.setDefaultProfile('work')")
        self.evaluate("transitionHook=() => { transitionHook=null; automatic.setDefaultProfile('personal'); return true; }; busy=false")
        self.assertEqual(self.selected(), "personal")
        self.evaluate("busy=true;automatic.setDefaultProfile('work');transitionHook=() => { transitionHook=null;"
            "automatic.setEnabled(false);return true;};busy=false")
        self.assertEqual(self.selected(), "personal")
        self.evaluate("busy=true;automatic.setEnabled(true);transitionHook=() => { transitionHook=null;"
            "configuration.profilesJSON=JSON.stringify(Object.assign({},JSON.parse(configuration.profilesJSON),"
            "{profiles:JSON.parse(configuration.profilesJSON).profiles.filter(p=>p.id!=='work')}));return true;};busy=false")
        self.assertEqual(self.selected(), "personal")
        self.assertFalse(self.evaluate("automatic.canEnable"))

    def test_transition_guard_manual_selection_and_profile_aba_win_over_auto(self):
        self.prepare()
        self.evaluate("transitionHook=() => { transitionHook=null; profileState.select('personal',profileState.activeProfileId,"
            "profileState.revision);profileState.select('legacy',profileState.activeProfileId,profileState.revision);return true; }")
        self.enable("work")
        self.assertEqual(self.selected(), "legacy")
        self.assertTrue(self.override())
        self.assertNotIn("work", json.loads(self.evaluate("JSON.stringify(selections)")))

    def test_manual_selection_of_expected_target_after_guard_and_false_result_is_manual(self):
        self.prepare()
        self.evaluate("useSelectionAdapter=true; afterGuardHook=() => { afterGuardHook=null;"
            "profileState.select('work',profileState.activeProfileId,profileState.revision); }")
        self.enable("work")
        self.assertEqual(self.selected(), "work")
        self.assertTrue(self.override())

    def test_false_selection_result_does_not_keep_apparently_owned_commit(self):
        self.prepare()
        self.evaluate("useSelectionAdapter=true; rejectSelectionResult=true")
        self.enable("work")
        self.assertEqual(self.selected(), "work")
        self.assertTrue(self.override())

    def test_busy_from_owned_commit_does_not_erase_ownership_or_make_manual(self):
        self.prepare()
        self.evaluate("selectionHook=() => { busy=true; }")
        self.enable("work")
        self.assertEqual(self.selected(), "work")
        self.assertTrue(self.root.property("busy"))
        self.assertFalse(self.override())
        before = self.root.property("writes")
        self.evaluate("selectionHook=null; busy=false")
        self.assertEqual(self.root.property("writes"), before)
        self.assertFalse(self.override())

    def test_manual_after_owned_guard_wins_even_when_it_returns_to_expected_target(self):
        self.prepare()
        self.evaluate("useSelectionAdapter=true; afterGuardHook=() => { afterGuardHook=null; profileState.select('personal',profileState.activeProfileId,"
            "profileState.revision);profileState.select('work',profileState.activeProfileId,profileState.revision); }")
        self.enable("work")
        self.assertEqual(self.selected(), "work")
        self.assertTrue(self.override())

    def test_two_instances_do_not_change_each_others_profiles_or_override(self):
        self.prepare()
        self.enable("work")
        self.evaluate("createSecond(); second.profileState.initializeDefaults(second.profileState.activeProfileId,second.profileState.revision);"
            "second.sourceSnapshot=sourceSnapshot;second.automatic.setDefaultProfile('games');second.automatic.setEnabled(true);second.running=true")
        self.assertEqual(self.evaluate("second.profileState.activeProfileId"), "games")
        self.manual("personal")
        self.assertTrue(self.override())
        self.assertEqual(self.evaluate("second.profileState.activeProfileId"), "games")
        self.assertFalse(self.evaluate("second.automatic.manualOverride"))

    def test_rejected_transition_does_not_retry_on_error_notifications(self):
        self.prepare()
        self.evaluate("transitionHook=() => false")
        before = self.root.property("writes")
        self.enable("work")
        self.assertEqual(self.selected(), "legacy")
        self.assertEqual(self.root.property("writes"), before)
        self.assertIn("não foi concluída", self.evaluate("automatic.statusText"))
        self.evaluate("profileState.error; profileState.message")
        self.assertEqual(self.root.property("writes"), before)

    def test_reentrant_context_binding_default_busy_mode_aba_revokes_old_intent(self):
        self.prepare()
        self.evaluate("useSelectionAdapter=true")
        self.enable("games")
        mutations = [
            "const saved=sourceSnapshot; sourceSnapshot=Object.assign({},saved,{activity:Object.assign({},saved.activity,{currentId:'a2'})});sourceSnapshot=saved;",
            "const saved=configuration.contextsJSON;configuration.contextsJSON=JSON.stringify({formatVersion:'0.1-experimental',activityBindings:[],desktopBindings:[]});configuration.contextsJSON=saved;",
            "automatic.setDefaultProfile('personal');automatic.setDefaultProfile('work');",
            "busy=true;busy=false;",
            "automatic.setEnabled(false);automatic.setEnabled(true);",
            "useSelectionAdapter=false;useSelectionAdapter=true;",
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.evaluate("busy=true;automatic.setDefaultProfile('games');busy=false")
                self.assertEqual(self.selected(), "games")
                self.evaluate("selectionResults=[];busy=true;automatic.setDefaultProfile('work');"
                    "transitionHook=() => { transitionHook=null;" + mutation + "return true;};busy=false")
                results = json.loads(self.evaluate("JSON.stringify(selectionResults)"))
                self.assertGreaterEqual(len(results), 2)
                self.assertEqual(results[0], {"target":"work", "accepted":False})
                self.assertEqual(results[-1], {"target":"work", "accepted":True})
                self.assertFalse(self.override())
                self.assertEqual(self.selected(), "work")

    def test_default_preference_is_independent_of_invalid_bindings_and_does_not_enable(self):
        self.prepare()
        self.config.setProperty("contextsJSON", "FUTURE-BYTES")
        self.assertTrue(self.evaluate("automatic.setDefaultProfile('games')"))
        self.assertEqual(self.config.property("autoContextDefaultProfile"), "games")
        self.assertEqual(self.config.property("contextsJSON"), "FUTURE-BYTES")
        self.assertFalse(self.evaluate("automatic.setEnabled(true)"))
        self.assertFalse(self.evaluate("automatic.enabled"))
        self.assertTrue(self.evaluate("automatic.setEnabled(false)"))

    def test_same_preference_values_never_call_a_configuration_setter(self):
        self.prepare()
        self.evaluate("spyPreferenceSetters()")
        self.assertTrue(self.evaluate("automatic.setEnabled(false)"))
        self.assertEqual(self.root.property("preferenceSetters"), 0)
        self.assertTrue(self.evaluate("automatic.setDefaultProfile('work')"))
        self.assertEqual(self.root.property("preferenceSetters"), 1)
        self.assertTrue(self.evaluate("automatic.setDefaultProfile('work')"))
        self.assertEqual(self.root.property("preferenceSetters"), 1)
        self.assertTrue(self.evaluate("automatic.setEnabled(true)"))
        self.assertEqual(self.root.property("preferenceSetters"), 2)
        self.assertTrue(self.evaluate("automatic.setEnabled(true)"))
        self.assertEqual(self.root.property("preferenceSetters"), 2)

    def test_reentrant_same_profile_edit_invalidates_old_revision_without_manual_override(self):
        self.prepare()
        self.evaluate("useSelectionAdapter=true; transitionHook=() => { transitionHook=null;"
            "profileState.commitPresentation({calendarEvents:false},profileState.activeProfileId,profileState.revision);return true; }")
        self.enable("work")
        results = json.loads(self.evaluate("JSON.stringify(selectionResults)"))
        self.assertEqual(results[0]["accepted"], False)
        self.assertEqual(results[-1]["accepted"], True)
        self.assertFalse(self.override())
        self.assertEqual(self.selected(), "work")

    def test_status_names_are_bounded_and_mode_off_keeps_last_profile(self):
        self.prepare()
        self.evaluate("configuration.profilesJSON=JSON.stringify(Object.assign({},JSON.parse(configuration.profilesJSON),"
            "{profiles:JSON.parse(configuration.profilesJSON).profiles.map(p=>p.id==='work'?Object.assign({},p,{name:'<b>Texto longo</b>'}):p)}))")
        self.enable("work")
        status = self.evaluate("automatic.statusText")
        self.assertIn("<b>", status)
        self.assertLessEqual(len(status), 160)
        before = self.root.property("writes")
        self.evaluate("automatic.setEnabled(false)")
        self.context("a2")
        self.assertEqual(self.selected(), "work")
        self.assertEqual(self.root.property("writes"), before)

    def test_false_result_does_not_restore_manual_override_after_a_new_confirmed_context(self):
        self.prepare()
        self.bind("activity", "work")
        self.evaluate("useSelectionAdapter=true;afterGuardHook=() => { afterGuardHook=null;"
            "profileState.select('work',profileState.activeProfileId,profileState.revision);"
            "sourceSnapshot=Object.assign({},sourceSnapshot,{activity:Object.assign({},sourceSnapshot.activity,{currentId:'a2'})}); }")
        self.enable("games")
        self.assertEqual(self.selected(), "games")
        self.assertFalse(self.override())

    def test_confirmed_context_aba_clears_manual_override_while_bindings_are_invalid(self):
        self.prepare()
        self.enable("work")
        self.manual("personal")
        self.assertTrue(self.override())
        original = self.config.property("contextsJSON")
        self.config.setProperty("contextsJSON", "FUTURE-BYTES")
        self.assertFalse(self.evaluate("automatic.observing"))
        self.context("a2")
        self.context()
        self.assertEqual(self.selected(), "personal")
        self.config.setProperty("contextsJSON", original)
        self.settle()
        self.assertFalse(self.override())
        self.assertEqual(self.selected(), "work")

    def test_manual_selection_after_ready_snapshot_belongs_to_the_new_context(self):
        self.prepare()
        self.enable("work")

        def select_on_ready_snapshot():
            if self.evaluate("snapshot.activity.id", self.contexts, settle=False) == "a2":
                self.evaluate("profileState.select('personal',profileState.activeProfileId,profileState.revision)", settle=False)

        self.contexts.snapshotChanged.connect(select_on_ready_snapshot)
        self.context("a2")
        self.contexts.snapshotChanged.disconnect(select_on_ready_snapshot)
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())


if __name__ == "__main__":
    unittest.main()
