"""Automatic profile selection with real portable states; no KDE/service access."""
import json
import math
import os
from pathlib import Path
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtTest import QSignalSpy, QTest


class AutoContextProfilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.create()

    def create(self, properties=None):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        if properties:
            self.engine.setInitialProperties(properties)
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

    def test_wait_status_names_missing_domains_without_selecting_until_both_ready(self):
        self.initialize()
        self.enable("work")
        saved = self.config.property("profilesJSON")
        writes = self.root.property("writes")
        cases = [
            ("unavailable", "ready", "Activity atual indisponível."),
            ("ready", "unavailable", "área de trabalho atual indisponível."),
            ("unavailable", "unavailable", "Activity e área de trabalho atuais indisponíveis."),
            ("loading", "ready", "carregamento em andamento."),
            ("ready", "loading", "carregamento em andamento."),
            ("loading", "loading", "carregamento em andamento."),
            ("loading", "unavailable", "área de trabalho atual indisponível."),
            ("unavailable", "loading", "Activity atual indisponível."),
        ]
        for activity_status, desktop_status, reason in cases:
            with self.subTest(activity=activity_status, desktop=desktop_status):
                self.context(activity_status=activity_status, desktop_status=desktop_status)
                status = self.evaluate("automatic.statusText")
                self.assertEqual(status, "Aguardando contexto KDE: " + reason)
                self.assertLessEqual(len(status), 160)
                self.assertTrue(self.evaluate("automatic.observing"))
                self.assertEqual(self.selected(), "legacy")
                self.assertEqual(self.config.property("profilesJSON"), saved)
                self.assertEqual(self.root.property("writes"), writes)
        self.context()
        self.assertEqual(self.selected(), "work")
        self.assertEqual(self.root.property("writes"), writes + 1)
        self.assertIn("padrão", self.evaluate("automatic.statusText"))
        self.assertEqual(self.config.property("timerDeadline"), 1234567890000)

    def test_wait_status_preserves_existing_priority_and_manual_choice(self):
        self.initialize()
        self.context(activity_status="unavailable")
        self.assertEqual(self.evaluate("automatic.statusText"), "Alternância automática desativada.")
        self.assertTrue(self.evaluate("automatic.setDefaultProfile('work'); automatic.setEnabled(true)"))
        self.assertEqual(self.evaluate("automatic.statusText"), "Aguardando a dock ficar pronta.")
        self.evaluate("running=true; configuration.autoContextDefaultProfile='missing'")
        self.assertEqual(self.evaluate("automatic.statusText"), "Confira os perfis, as associações e o perfil padrão.")
        self.evaluate("configuration.autoContextDefaultProfile='work'; busy=true")
        saved = self.config.property("profilesJSON")
        writes = self.root.property("writes")
        self.assertEqual(self.evaluate("automatic.statusText"), "Aguardando contexto KDE: Activity atual indisponível.")
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.assertEqual(self.root.property("writes"), writes)
        self.context()
        self.assertEqual(self.evaluate("automatic.statusText"), "Troca de perfil adiada durante a interação.")
        self.assertEqual(self.selected(), "legacy")
        self.assertEqual(self.root.property("writes"), writes)
        self.evaluate("busy=false")
        self.assertEqual(self.selected(), "work")
        self.manual("personal")
        self.assertTrue(self.override())
        saved = self.config.property("profilesJSON")
        writes = self.root.property("writes")
        self.context(activity_status="unavailable")
        self.evaluate("busy=true")
        self.assertEqual(self.evaluate("automatic.statusText"), "Seleção manual até mudar de contexto ou reiniciar a dock.")
        self.assertEqual(self.selected(), "personal")
        self.assertEqual(self.config.property("profilesJSON"), saved)
        self.assertEqual(self.root.property("writes"), writes)
        self.assertEqual(self.config.property("timerDeadline"), 1234567890000)

    def test_rename_keeps_profile_identity_and_manual_override_until_context_changes(self):
        self.prepare()
        self.bind("activity", "work")
        self.context("a2")
        self.bind("activity", "personal")
        self.context()
        self.enable("games")
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.override())
        fields = ("contextsJSON", "autoContextEnabled", "autoContextDefaultProfile", "autoContextPolicy",
                  "launchers", "theme", "appearanceJSON", "iconSize", "animations", "showClock", "showMusic",
                  "showSystemBattery", "showPomodoro", "showQuota", "showPeripherals", "showRecording",
                  "showAudioHud", "calendarEvents", "currentDesktopOnly", "timerDeadline", "timerRemaining",
                  "timerBreak", "focusMinutes", "breakMinutes", "completedFocus")
        def preferences():
            return json.loads(self.evaluate("JSON.stringify(" + json.dumps(list(fields))
                                            + ".map(key=>configuration[key]))"))
        baseline = preferences()
        expected = json.loads(self.config.property("profilesJSON"))
        selections = QSignalSpy(self.profiles.activeProfileIdChanged)
        for name, manual in (("Novo trabalho", False), ("Trabalho manual", True)):
            if manual:
                self.manual("personal")
                self.assertTrue(self.override())
                expected["activeProfileId"] = "personal"
            count = selections.count()
            writes = self.root.property("writes")
            profile_id = self.selected()
            self.assertTrue(self.evaluate("rename(" + json.dumps(name) + ",activeProfileId,revision)", self.profiles))
            next(profile for profile in expected["profiles"] if profile["id"] == profile_id)["name"] = name
            self.assertEqual(json.loads(self.config.property("profilesJSON")), expected)
            self.assertEqual(self.root.property("writes"), writes + 1)
            self.assertEqual(selections.count(), count)
            self.assertEqual(self.override(), manual)
            self.assertEqual(preferences(), baseline)
            self.assertIn(name, self.evaluate("automatic.statusText") if not manual else
                          self.evaluate("JSON.stringify(profileState.profiles)"))
        # The next confirmed identity still resolves the same stored ID under its new name.
        self.context("a2")
        self.assertEqual(self.selected(), "personal")
        self.assertFalse(self.override())
        self.assertIn("Trabalho manual", self.evaluate("automatic.statusText"))
        self.context()
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.override())
        self.assertIn("Novo trabalho", self.evaluate("automatic.statusText"))
        expected["activeProfileId"] = "work"
        self.assertEqual(json.loads(self.config.property("profilesJSON")), expected)
        self.assertEqual(preferences(), baseline)

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

    def test_desktop_policy_resolves_without_activity_and_preserves_associations(self):
        self.prepare()
        self.bind("activity", "work")
        self.bind("desktop", "personal")
        bindings = self.config.property("contextsJSON")
        original = json.loads(self.config.property("profilesJSON"))
        timer = {key: self.config.property(key) for key in
                 ("timerDeadline", "timerRemaining", "timerBreak", "completedFocus", "focusMinutes", "breakMinutes")}
        self.config.setProperty("autoContextPolicy", "desktop")
        self.context(activity_status="unavailable")
        self.enable("games")
        self.assertEqual(self.selected(), "personal")
        self.assertIn("pela área", self.evaluate("automatic.statusText"))
        self.context(desktop="d2", activity_status="loading")
        self.assertEqual(self.selected(), "games")
        self.context()
        self.assertEqual(self.selected(), "personal", "Activity binding must be ignored, not removed")
        expected = dict(original, activeProfileId="personal")
        self.assertEqual(json.loads(self.config.property("profilesJSON")), expected)
        self.assertEqual(self.config.property("contextsJSON"), bindings)
        self.assertEqual({key: self.config.property(key) for key in timer}, timer)

    def test_policy_invalid_raw_pauses_and_legacy_undefined_or_missing_stays_strict(self):
        self.prepare()
        self.enable("work")
        for value in ("", "future-policy", None, 17, False, {"policy": "desktop"}):
            with self.subTest(raw=value):
                self.evaluate("configuration.autoContextPolicy=" + json.dumps(value))
                before = self.config.property("profilesJSON")
                writes = self.root.property("writes")
                self.assertFalse(self.evaluate("automatic.policyValid"))
                self.assertFalse(self.evaluate("automatic.observing"))
                self.assertEqual(self.evaluate("JSON.stringify(automatic.policy)"), json.dumps(value, separators=(',', ':')))
                self.assertEqual(self.evaluate("automatic.statusText"), "Escolha como o automático deve usar os contextos.")
                self.context("a2", "d2")
                self.assertEqual(self.config.property("profilesJSON"), before)
                self.assertEqual(self.root.property("writes"), writes)
                self.assertEqual(self.evaluate("JSON.stringify(configuration.autoContextPolicy)"), json.dumps(value, separators=(',', ':')))
        self.evaluate("configuration.autoContextPolicy=undefined")
        self.assertEqual(self.evaluate("automatic.policy"), "activity-desktop")
        self.assertTrue(self.evaluate("automatic.policyValid && configuration.autoContextPolicy===undefined"))
        self.evaluate("const real=configuration; automatic.configuration={"
            "get autoContextEnabled(){return real.autoContextEnabled},"
            "get autoContextDefaultProfile(){return real.autoContextDefaultProfile}}")
        self.assertEqual(self.evaluate("automatic.policy"), "activity-desktop")
        self.assertTrue(self.evaluate("automatic.policyValid"))
        self.context(activity_status="unavailable")
        self.assertIn("Activity atual indisponível", self.evaluate("automatic.statusText"))

    def test_policy_repair_ignores_invalid_documents_and_same_value_never_writes(self):
        self.config.setProperty("profilesJSON", "FUTURE-PROFILES")
        self.config.setProperty("contextsJSON", "FUTURE-BINDINGS")
        self.evaluate("configuration.autoContextPolicy='future';spyPreferenceSetters()")
        self.assertTrue(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertEqual(self.root.property("preferenceSetters"), 1)
        self.assertTrue(self.evaluate("automatic.setPolicy('desktop')"))
        for value in ("", "future", None, 2, False):
            self.assertFalse(self.evaluate("automatic.setPolicy(" + json.dumps(value) + ")"))
        self.assertEqual(self.root.property("preferenceSetters"), 1)
        self.assertEqual(self.config.property("autoContextPolicy"), "desktop")
        self.assertFalse(self.evaluate("automatic.enabled"))
        self.assertEqual(self.config.property("profilesJSON"), "FUTURE-PROFILES")
        self.assertEqual(self.config.property("contextsJSON"), "FUTURE-BINDINGS")

    def test_desktop_policy_waits_for_required_desktop_and_missing_target(self):
        self.prepare()
        self.bind("desktop", "personal")
        self.evaluate("configuration.autoContextPolicy='desktop';"
            "configuration.profilesJSON=JSON.stringify(Object.assign({},JSON.parse(configuration.profilesJSON),"
            "{profiles:JSON.parse(configuration.profilesJSON).profiles.filter(p=>p.id!=='personal')}))")
        before = self.config.property("profilesJSON")
        self.enable("work")
        self.assertEqual(self.config.property("profilesJSON"), before)
        self.assertIn("perfil associado", self.evaluate("automatic.statusText"))
        for status in ("loading", "unavailable"):
            self.context(activity_status="unavailable", desktop_status=status)
            self.assertEqual(self.config.property("profilesJSON"), before)
            message = self.evaluate("automatic.statusText")
            self.assertNotIn("Activity", message)
            self.assertIn("área de trabalho", message)
        self.context(desktop="not-in-list", activity_status="unavailable")
        self.assertEqual(self.config.property("profilesJSON"), before)
        self.assertFalse(self.override())

    def test_desktop_manual_identity_ignores_activity_and_survives_same_desktop_recovery(self):
        self.prepare()
        self.bind("desktop", "personal")
        self.evaluate("configuration.autoContextPolicy='desktop'")
        self.enable("games")
        self.assertEqual(self.selected(), "personal")
        self.manual("work")
        before = self.config.property("profilesJSON")
        for activity, status in (("a2", "ready"), ("a1", "loading"), ("a3", "unavailable"), ("a1", "ready")):
            self.context(activity, activity_status=status)
            self.assertEqual(self.config.property("profilesJSON"), before)
            self.assertTrue(self.override())
        self.evaluate("sourceSnapshot=Object.assign({},sourceSnapshot,{outputName:'Other synthetic output',"
            "desktop:Object.assign({},sourceSnapshot.desktop,{names:['Renamed','Dois','Três']})})")
        self.context(desktop_status="loading")
        self.context()
        self.assertEqual(self.config.property("profilesJSON"), before)
        self.assertTrue(self.override())
        raw = self.config.property("contextsJSON")
        self.config.setProperty("contextsJSON", "FUTURE-BYTES")
        self.context(desktop="d2", settle=False)
        self.context(desktop="d1", settle=False)
        self.config.setProperty("contextsJSON", raw)
        self.settle()
        self.assertFalse(self.override())
        self.assertEqual(self.selected(), "personal")

    def test_committed_policy_waits_while_busy_and_same_policy_keeps_manual(self):
        self.prepare()
        self.bind("activity", "work")
        self.bind("desktop", "personal")
        self.enable("games")
        self.manual("games")
        self.evaluate("busy=true")
        before = self.config.property("profilesJSON")
        self.assertTrue(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertEqual(self.config.property("profilesJSON"), before)
        self.assertFalse(self.override())
        self.evaluate("busy=false")
        self.assertEqual(self.selected(), "personal")
        self.manual("work")
        self.evaluate("spyPreferenceSetters()")
        self.assertTrue(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertEqual(self.root.property("preferenceSetters"), 0)
        self.assertTrue(self.override())
        self.assertEqual(self.selected(), "work")

    def test_policy_raw_callback_manual_selection_precedes_controller_reconciliation(self):
        self.prepare()
        self.bind("activity", "work")
        self.enable("games")
        self.manual("games")
        self.context(desktop_status="loading")
        self.evaluate("busy=true;policyHook=() => { policyTrace=policyTrace.concat([{raw:configuration.autoContextPolicy,"
            "manualBefore:automatic.manualOverride}]);profileState.select('personal',profileState.activeProfileId,profileState.revision); }")
        self.assertTrue(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(policyTrace)")), [{"raw": "desktop", "manualBefore": True}])
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.evaluate("policyHook=null;busy=false")
        self.context()
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.context("a2")
        self.assertEqual(self.selected(), "personal")
        self.context("a2", "d2")
        self.assertEqual(self.selected(), "games")
        self.assertFalse(self.override())
        self.evaluate("busy=true;policyHook=() => {profileState.select('personal',profileState.activeProfileId,profileState.revision);}")
        self.evaluate("configuration.autoContextPolicy='activity-desktop';policyHook=null;busy=false")
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())

    def test_manual_before_first_ready_identity_attaches_without_losing_choice(self):
        self.initialize()
        self.enable("work")
        self.manual("personal")
        self.assertTrue(self.override())
        self.context()
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.context("a2")
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.override())

    def test_policy_change_then_manual_before_first_desktop_attaches_and_resume_releases(self):
        self.initialize()
        self.enable("work")
        self.assertTrue(self.evaluate("automatic.setPolicy('desktop')"))
        self.manual("personal")
        self.assertTrue(self.override())
        self.context(activity_status="unavailable")
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.assertTrue(self.evaluate("automatic.resume()"))
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.override())

    def test_failed_policy_writes_cannot_release_manual_or_claim_success(self):
        self.prepare()
        self.enable("work")
        self.manual("personal")
        self.evaluate("spyPreferenceSetters();policyWriteHook=() => {throw new Error('synthetic_refusal')}")
        self.assertFalse(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertEqual(self.config.property("autoContextPolicy"), "activity-desktop")
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.evaluate("policyWriteHook=() => {}")
        self.assertFalse(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertTrue(self.override())
        self.evaluate("spyPreferenceSetters(true)")
        self.assertFalse(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertTrue(self.override())
        self.assertEqual(self.selected(), "personal")

    def test_reentrant_policy_writer_cannot_publish_false_success(self):
        self.prepare()
        self.enable("work")
        self.manual("personal")
        self.evaluate("spyPreferenceSetters();policyWriteHook=value => { configuration.autoContextPolicy=value;"
            "configuration.autoContextPolicy='activity-desktop'; }")
        self.assertFalse(self.evaluate("automatic.setPolicy('desktop')"))
        self.assertEqual(self.config.property("autoContextPolicy"), "activity-desktop")
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.override())
        self.manual("personal")
        self.evaluate("policyWriteHook=value => {configuration.autoContextPolicy=value;"
            "configuration.autoContextPolicy='activity-desktop';configuration.autoContextPolicy=value;}")
        self.assertFalse(self.evaluate("automatic.setPolicy('desktop')"), "ABA must not publish the outer write as owned")
        self.assertEqual(self.config.property("autoContextPolicy"), "desktop")
        self.assertEqual(self.selected(), "work")
        self.assertFalse(self.override())

    def test_policy_aba_revokes_old_profile_intent_and_commits_latest_once(self):
        self.prepare()
        self.bind("activity", "work")
        self.bind("desktop", "personal")
        self.evaluate("useSelectionAdapter=true")
        self.enable("games")
        for middle in ("desktop", "unknown"):
            with self.subTest(middle=middle):
                self.context("a3", "d3")
                self.assertEqual(self.selected(), "games")
                self.evaluate("busy=true;selectionResults=[]")
                self.context()
                before = self.root.property("writes")
                self.evaluate("transitionHook=() => {transitionHook=null;configuration.autoContextPolicy=" + json.dumps(middle)
                    + ";configuration.autoContextPolicy='activity-desktop';return true;};busy=false")
                results = json.loads(self.evaluate("JSON.stringify(selectionResults)"))
                self.assertEqual(results[0], {"target": "work", "accepted": False})
                self.assertEqual(results[-1], {"target": "work", "accepted": True})
                self.assertEqual(self.selected(), "work")
                self.assertEqual(self.root.property("writes"), before + 1)
                self.assertFalse(self.override())

    def test_old_false_result_cannot_mark_new_policy_epoch_manual(self):
        self.prepare()
        self.bind("activity", "work")
        self.bind("desktop", "personal")
        self.evaluate("useSelectionAdapter=true;rejectSelectionResult=true;"
            "selectionHook=() => {if(profileState.activeProfileId==='work')configuration.autoContextPolicy='desktop';"
            "else if(profileState.activeProfileId==='personal')rejectSelectionResult=false;}")
        self.enable("games")
        self.assertEqual(self.selected(), "personal")
        self.assertFalse(self.override())
        results = json.loads(self.evaluate("JSON.stringify(selectionResults)"))
        self.assertEqual(results[0], {"target": "work", "accepted": False})
        self.assertEqual(results[-1], {"target": "personal", "accepted": True})

    def test_invalid_nan_policy_reconciliation_becomes_idle_without_rewriting(self):
        self.evaluate("const probe={reads:0,raw:NaN};policyProbe=probe;const real=configuration;"
            "automatic.configuration={get autoContextEnabled(){return real.autoContextEnabled},"
            "get autoContextDefaultProfile(){return real.autoContextDefaultProfile},"
            "get autoContextPolicy(){probe.reads++;return probe.raw}}")
        self.assertFalse(self.evaluate("automatic.policyValid"))
        self.assertTrue(self.evaluate("Number.isNaN(automatic.policy) && Number.isNaN(policyProbe.raw)"))
        QTest.qWait(30)
        reads = self.evaluate("policyProbe.reads")
        QTest.qWait(30)
        self.assertEqual(self.evaluate("policyProbe.reads"), reads, "Invalid policy must not reschedule itself while OFF")

    def test_new_policy_manual_choice_matching_old_admitted_target_is_manual(self):
        self.prepare()
        self.bind("activity", "work")
        self.bind("desktop", "personal")
        self.evaluate("useSelectionAdapter=true;afterGuardHook=() => {afterGuardHook=null;"
            "automatic.setPolicy('desktop');profileState.select('work',profileState.activeProfileId,profileState.revision);}")
        self.enable("games")
        self.assertEqual(self.selected(), "work")
        self.assertTrue(self.override())

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

    def cold_start(self, policy):
        self.initialize()
        document = json.loads(self.config.property("profilesJSON"))
        document["activeProfileId"] = "work"
        bindings = {"formatVersion": "0.1-experimental", "activityBindings": [], "desktopBindings": []}
        bindings["desktopBindings"] = [{"contextId": "d1", "lastKnownName": "Synthetic one", "profileId": "personal"}]
        frame = {"outputName": "Synthetic-output",
                 "activity": {"status": "unavailable" if policy == "desktop" else "ready", "currentId": "a1",
                              "ids": ["a1"], "names": ["Synthetic activity"]},
                 "desktop": {"status": "ready", "currentId": "d1", "ids": ["d1", "d2"],
                             "names": ["Synthetic one", "Synthetic two"]}}
        self.tearDown()
        self.create({"initialProfilesJSON": json.dumps(document), "initialBindingsJSON": json.dumps(bindings),
                     "initialEnabled": True, "initialDefaultProfile": "games", "initialPolicy": policy,
                     "initialActive": True, "initialSourceJSON": json.dumps(frame)})
        self.settle()
        return document

    def test_cold_start_desktop_policy_recomputes_saved_work_without_manual_selection(self):
        original = self.cold_start("desktop")
        self.assertEqual(self.selected(), "personal")
        self.assertFalse(self.override())
        self.assertEqual(json.loads(self.config.property("profilesJSON")), dict(original, activeProfileId="personal"))

    def test_cold_start_strict_policy_recomputes_saved_work_without_manual_selection(self):
        original = self.cold_start("activity-desktop")
        self.assertEqual(self.selected(), "personal")
        self.assertFalse(self.override())
        self.assertEqual(json.loads(self.config.property("profilesJSON")), dict(original, activeProfileId="personal"))

    def test_initial_load_provenance_suspends_for_nested_real_selection(self):
        self.prepare()
        self.enable("games")
        self.evaluate("let fired=false;hydrationHook=() => {hydrationTrace=hydrationTrace.concat([profileState.hydratingInitial]);"
            "if(profileState.hydratingInitial && !fired){fired=true;"
            "if(!profileState.select('personal',profileState.activeProfileId,profileState.revision))throw new Error('nested_select_refused');}}")
        self.evaluate("profileState.load(true)")
        self.assertEqual(json.loads(self.evaluate("JSON.stringify(hydrationTrace)")), [True, False, True, False])
        self.assertFalse(self.evaluate("profileState.hydratingInitial"))
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.context(desktop="d2")
        self.assertEqual(self.selected(), "games")
        self.assertFalse(self.override())

    def test_manual_selection_during_initial_load_unwind_remains_authoritative(self):
        self.prepare()
        self.enable("games")
        self.evaluate("let fired=false;hydrationHook=() => {if(!profileState.hydratingInitial && !fired){fired=true;"
            "if(!profileState.select('personal',profileState.activeProfileId,profileState.revision))throw new Error('unwind_select_refused');}}")
        self.evaluate("profileState.load(true)")
        self.assertEqual(self.selected(), "personal")
        self.assertTrue(self.override())
        self.assertFalse(self.evaluate("profileState.hydratingInitial"))

    def test_external_profile_load_after_startup_remains_manual(self):
        self.cold_start("desktop")
        document = json.loads(self.config.property("profilesJSON"))
        document["activeProfileId"] = "work"
        raw = json.dumps(document)
        self.config.setProperty("profilesJSON", raw)
        self.settle()
        self.assertEqual(self.config.property("profilesJSON"), raw)
        self.assertEqual(self.selected(), "work")
        self.assertTrue(self.override())

    def test_initial_load_error_restores_provenance_without_repairing_raw(self):
        self.prepare()
        raw = 'FUTURE-PROFILES'
        self.config.setProperty('profilesJSON', raw)
        self.evaluate('profileState.load(true)')
        self.assertFalse(self.evaluate('profileState.hydratingInitial'))
        self.assertFalse(self.profiles.property('writable'))
        self.assertEqual(self.config.property('profilesJSON'), raw)

    def test_real_timer_ticks_across_automatic_profiles_and_recreation(self):
        self.initialize()
        document = json.loads(self.config.property('profilesJSON'))
        personal = next(profile for profile in document['profiles'] if profile['id'] == 'personal')
        next(widget for widget in personal['widgets'] if widget['id'] == 'pomodoro')['visible'] = False
        self.config.setProperty('profilesJSON', json.dumps(document))

        def desktop(current):
            self.evaluate('sourceSnapshot=' + json.dumps({
                'outputName': 'Synthetic-output',
                'activity': {'status': 'ready', 'currentId': 'a1', 'ids': ['a1'], 'names': ['Synthetic activity']},
                'desktop': {'status': 'ready', 'currentId': current,
                            'ids': ['d0', 'd1'], 'names': ['Synthetic zero', 'Synthetic one']},
            }))

        desktop('d0')
        self.bind('desktop', 'work')
        desktop('d1')
        self.bind('desktop', 'personal')
        desktop('d0')
        self.enable('games')
        self.assertEqual(self.selected(), 'work')
        baseline = json.loads(self.config.property('profilesJSON'))
        bindings = self.config.property('contextsJSON')
        self.evaluate('configuration.timerDeadline=Date.now()+60000')
        fields = ('timerDeadline', 'timerRemaining', 'timerBreak', 'focusMinutes', 'breakMinutes', 'completedFocus')
        saved = {key: self.config.property(key) for key in fields}
        self.assertEqual(saved['timerRemaining'], 371)
        self.assertFalse(saved['timerBreak'])
        self.assertEqual(saved['completedFocus'], 3)
        self.assertTrue(self.evaluate('createTimer()'))
        timer = self.root.findChild(QObject, 'fixturePomodoro')
        self.assertIsNotNone(timer)

        def preserved(profile, visible):
            expected = dict(baseline, activeProfileId=profile)
            self.assertEqual(json.loads(self.config.property('profilesJSON')), expected)
            self.assertEqual(self.config.property('contextsJSON'), bindings)
            self.assertEqual({key: self.config.property(key) for key in fields}, saved)
            self.assertEqual(self.evaluate("profileState.effective.widgets.find(w=>w.id==='pomodoro').visible"), visible)
            self.assertTrue(timer.property('running'))
            self.assertEqual(timer.property('phaseSeconds'), 1500)
            # The ticker can be up to one interval behind this independent wall-clock read.
            earliest = time.time()
            seconds = timer.property('secondsLeft')
            latest = time.time()
            self.assertGreaterEqual(seconds, math.ceil(saved['timerDeadline'] / 1000 - latest) - 1)
            self.assertLessEqual(seconds, math.ceil(saved['timerDeadline'] / 1000 - earliest) + 1)
            self.assertGreater(seconds, 0)
            self.assertLess(seconds, saved['timerRemaining'])
            return seconds

        def next_tick():
            before = timer.property('secondsLeft')
            changed = QSignalSpy(timer.secondsLeftChanged)
            self.assertTrue(changed.wait(1600), 'The real 500 ms ticker must advance without poll()')
            self.assertLess(timer.property('secondsLeft'), before)

        first = preserved('work', True)
        next_tick()
        next_tick()
        self.assertLess(preserved('work', True), first)
        desktop('d1')
        self.assertEqual(self.selected(), 'personal')
        preserved('personal', False)
        next_tick()
        desktop('d0')
        self.assertEqual(self.selected(), 'work')
        before_recreation = preserved('work', True)
        destroyed = QSignalSpy(timer.destroyed)
        self.assertTrue(self.evaluate('retireTimer()'))
        if not destroyed.count():
            self.assertTrue(destroyed.wait(1000))
        self.assertEqual(destroyed.count(), 1)
        QTest.qWait(1100)  # Real elapsed time while no Pomodoro instance exists.
        self.assertTrue(self.evaluate('createTimer()'))
        timer = self.root.findChild(QObject, 'fixturePomodoro')
        self.assertIsNotNone(timer)
        self.assertLess(preserved('work', True), before_recreation)
        next_tick()
        preserved('work', True)

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
