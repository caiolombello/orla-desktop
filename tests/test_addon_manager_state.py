"""Real portable QML state, asynchronous fake bus boundary, no real IPC or dialog."""
import json
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

# Set before constructing Qt. No inherited display, session bus, HOME or XDG access.
_private = tempfile.TemporaryDirectory(prefix="orla-addon-state-")
for _key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "DBUS_SESSION_BUS_PID",
             "DBUS_STARTER_ADDRESS", "SESSION_MANAGER"):
    os.environ.pop(_key, None)
for _key, _leaf in (("HOME", "home"), ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                    ("XDG_STATE_HOME", "state"), ("XDG_CACHE_HOME", "cache"),
                    ("XDG_RUNTIME_DIR", "run"), ("TMPDIR", "tmp")):
    _path = Path(_private.name) / _leaf
    _path.mkdir(mode=0o700)
    os.environ[_key] = str(_path)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

SHA = "a" * 64
OTHER = "b" * 64
GEN = "1" * 32
URI = "file:///synthetic/arbitrary%20name.data"


def manifest(**changes):
    value = dict(formatVersion="0.1-experimental", id="org.example.battery", name="Bateria local",
                 description="Dados compartilhados localmente.", author="Projeto Exemplo", license="MIT",
                 version="1.2.0", origin="https://example.org/battery", renderer="peripheral-battery",
                 source=dict(namespace="battery-example", formatVersion="0.1-experimental"))
    value.update(changes)
    return value


def listing(enabled=False, sha=SHA, previous=None, generation=GEN):
    return dict(generation=generation, addons=[dict(manifest=manifest(), sha256=sha,
                previousSha256=previous, enabled=enabled)])


def success(result):
    return json.dumps(dict(formatVersion="0.1-experimental", ok=True, result=result), ensure_ascii=False)


def failure(code="io", committed=None, generation=None):
    return json.dumps(dict(formatVersion="0.1-experimental", ok=False,
                          error=dict(code=code, committed=committed, generation=generation)))


class AddonManagerStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("AddonManagerStateHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.h = self.engine.rootObjects()[0]

    def tearDown(self):
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def js(self, source):
        expression = QQmlExpression(QQmlEngine.contextForObject(self.h), self.h, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def data(self, expression):
        return json.loads(self.js("JSON.stringify(" + expression + ")"))

    def reply(self, index, raw):
        self.js(f"succeed({index}, {json.dumps(raw)})")

    def activate(self, value=None):
        self.js("state.active = true")
        QTest.qWait(1)
        self.reply(0, success(value if value is not None else dict(generation=None, addons=[])))

    def preview(self):
        self.js("token = state.beginFileSelection(owner)")
        self.assertTrue(self.js(f"state.acceptFileSelection(owner, token, {json.dumps(URI)})"))
        self.reply(len(self.data("calls")) - 1, success(dict(manifest=manifest(), sha256=SHA)))

    def stage_picker(self):
        # Actual production creation helper/map and native signals; no dialog open().
        self.js("alternateWindow.visible = true; filePicker.parentWindow = alternateWindow")
        self.js("token = state.beginFileSelection(filePicker); filePicker.selectionState = state; filePicker.selectionToken = token")
        self.js("filePicker.chooser = filePicker.createDialog(state, token, alternateWindow); oldDialog = filePicker.chooser")
        selected = Path(os.environ["TMPDIR"]) / "seleção % # ?.data"
        selected.write_bytes(b"")
        self.js("oldDialog.selectedFile = " + json.dumps(selected.as_uri()))
        self.assertFalse(self.js("oldDialog.visible"))
        return selected.as_uri()

    def backend_format(self):
        path = Path(__file__).resolve().parents[1] / "package/contents/code/addon_format.py"
        spec = importlib.util.spec_from_file_location("addon_state_fixture_format", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_preview_install_enable_are_separate_hash_bound_actions(self):
        self.assertFalse(self.js("state.refresh()"))
        self.activate()
        self.preview()
        self.assertEqual(self.data("state.preview")["id"], "org.example.battery")
        self.assertFalse(self.data("state.preview")["enabled"])
        self.assertEqual(len(self.data("calls")), 2)
        self.assertFalse(self.js(f"state.installAddon('{OTHER}')"))
        self.assertTrue(self.js(f"state.installAddon('{SHA}')"))
        self.assertEqual(self.data("calls[2].message"), dict(service="org.orla.Addons", path="/org/orla/Addons",
            iface="org.orla.Addons1", member="InstallAddon", signature="(ss)", arguments=[URI, SHA]))
        self.reply(2, success(listing()))
        self.assertFalse(self.data("state.addons[0].enabled"))
        self.assertIsNone(self.data("state.preview"))
        self.assertTrue(self.js(f"state.enableAddon('org.example.battery','{SHA}')"))
        self.reply(3, success(listing(enabled=True, generation="2" * 32)))
        self.assertTrue(self.data("state.addons[0].enabled"))
        self.assertEqual(self.data("settlements")[0]["busy"], False)
        self.assertEqual(self.warnings, [])

    def test_settlement_releases_busy_before_signal_without_reentrant_dispatch(self):
        self.activate(listing())
        self.js('reenter = "release-disable"')
        self.assertTrue(self.js(f"state.enableAddon('org.example.battery','{SHA}')"))
        self.reply(1, success(listing(enabled=True, generation="2" * 32)))
        self.assertEqual(self.data("settlements")[0]["busy"], False)
        self.assertEqual(self.data("reentries"), [False])
        self.assertEqual(len(self.data("calls")), 2)

    def test_refuses_nonexact_identity_and_generation_without_dispatch(self):
        self.activate(listing())
        for bad in (SHA + "\n", SHA.upper(), SHA[:-1], True, None):
            self.assertFalse(self.js("state.enableAddon('org.example.battery'," + json.dumps(bad) + ")"))
        self.reply(0, success(listing(sha=OTHER)))  # duplicate completion cannot replace current identity
        self.assertEqual(self.data("state.addons[0].sha256"), SHA)
        for bad in (GEN + "\n", "", False, "A" * 32):
            self.assertTrue(self.js("state.refresh()"))
            self.reply(len(self.data("calls")) - 1, success(listing(generation=bad)))
            self.assertFalse(self.js("state.valid"))

    def test_selection_to_inspection_never_exposes_an_idle_reentrant_gap(self):
        self.activate()
        self.js("token = state.beginFileSelection(owner)")
        self.js('reenter = "selection-aba"')
        self.js(f"state.acceptFileSelection(owner, token, {json.dumps(URI)})")
        # If selection releases busy before the read is reserved, the observer closes/reopens
        # and the old URI is incorrectly dispatched into the newer lifetime.
        self.assertTrue(self.js("state.valid"))
        self.assertEqual(self.data("calls[1].message.member"), "InspectAddonFile")
        self.js('reenter = ""')
        self.reply(1, success(dict(manifest=manifest(), sha256=SHA)))
        self.assertIsNotNone(self.data("state.preview"))

    def test_unknown_mutation_bus_failure_reloads_without_retry_or_old_preview(self):
        self.activate()
        self.preview()
        self.js(f"state.installAddon('{SHA}')")
        self.js("fail(2)")
        self.assertIsNone(self.data("state.preview"))
        self.assertFalse(self.js("state.valid"))
        self.assertIsNone(self.data("settlements[0].committed"))
        self.assertFalse(self.js(f"state.installAddon('{SHA}')"))
        QTest.qWait(1)
        self.assertEqual(self.data("calls[3].message.member"), "ListAddons")
        self.reply(3, success(listing()))
        self.assertTrue(self.js("state.valid"))
        self.assertFalse(self.js(f"state.installAddon('{SHA}')"))
        self.reply(2, success(listing(enabled=True)))  # late success after failure is ignored
        self.assertFalse(self.js("state.addons[0].enabled"))
        self.assertEqual(len(self.data("settlements")), 1)
        self.assertEqual([m["member"] for m in self.data("calls.map(c => c.message)")],
                         ["ListAddons", "InspectAddonFile", "InstallAddon", "ListAddons"])
        self.assertEqual(self.warnings, [])

    def test_closed_or_replaced_surface_discards_pending_and_duplicate_reads(self):
        for trigger in ("state.active = false; state.active = true", "state.owner = otherOwner",
                        'state.scopeKey = "next"'):
            with self.subTest(trigger=trigger):
                if not self.js("state.active"):
                    self.js("state.active = true")
                QTest.qWait(1)
                index = len(self.data("calls")) - 1
                self.js(trigger)
                self.assertFalse(self.js("state.refresh()"))
                self.reply(index, success(listing(enabled=True)))
                self.assertFalse(self.js("state.valid"))
                QTest.qWait(1)
                newer = len(self.data("calls")) - 1
                self.assertGreater(newer, index)
                self.reply(newer, success(listing()))
                self.reply(index, success(listing(enabled=True)))
                self.assertFalse(self.js("state.addons[0].enabled"))
                # Reserve another pending read for the next turn.
                self.js("state.refresh()")
        self.js("state.active = false")
        count = len(self.data("calls"))
        self.reply(count - 1, success(listing(enabled=True)))
        QTest.qWait(1)
        self.assertEqual(len(self.data("calls")), count)
        self.assertFalse(self.js("state.valid"))
        self.assertEqual(self.warnings, [])

    def test_reentrant_close_before_dispatch_does_not_send_mutation(self):
        for trigger in ("start-close", "start-aba", "busy-close"):
            with self.subTest(trigger=trigger):
                if not self.js("state.active"):
                    self.js("state.active = true")
                QTest.qWait(1)
                index = len(self.data("calls")) - 1
                self.reply(index, success(listing()))
                count = len(self.data("calls"))
                self.js(f"reenter = {json.dumps(trigger)}")
                self.assertFalse(self.js(f"state.enableAddon('org.example.battery','{SHA}')"))
                self.assertEqual(len(self.data("calls")), count)
                self.assertFalse(self.js("state.valid"))
                self.assertFalse(self.data("settlements")[ -1]["committed"])
                self.js('reenter = ""; state.active = false')
        self.assertEqual(self.warnings, [])

    def test_chooser_cancel_exact_owner_and_opaque_token_aba(self):
        self.activate()
        self.preview()
        self.js("oldToken = state.beginFileSelection(owner)")
        self.assertIsNone(self.data("state.preview"))
        self.assertFalse(self.js("state.cancelFileSelection(otherOwner, oldToken)"))
        self.assertFalse(self.js("state.cancelFileSelection(owner, {})"))
        self.assertTrue(self.js("state.cancelFileSelection(owner, oldToken)"))
        self.js("token = state.beginFileSelection(owner)")
        self.assertFalse(self.js(f"state.acceptFileSelection(owner, oldToken, {json.dumps(URI)})"))
        self.assertFalse(self.js("state.cancelFileSelection(owner, oldToken)"))
        self.assertTrue(self.js("state.ownsFileSelection(owner, token)"))
        self.js("state.active = false; state.active = true")
        self.assertFalse(self.js(f"state.acceptFileSelection(owner, token, {json.dumps(URI)})"))
        self.assertIsNone(self.data("state.preview"))
        self.assertEqual(len(self.data("calls")), 2)

    def test_stale_hash_refusal_requires_new_inspection_and_no_rebound_approval(self):
        self.activate()
        self.preview()
        self.js(f"state.installAddon('{SHA}')")
        self.reply(2, failure("hash", False))
        self.assertIn("mudou", self.js("state.feedback"))
        self.assertFalse(self.js(f"state.installAddon('{SHA}')"))
        QTest.qWait(1)
        self.reply(3, success(listing(sha=OTHER)))
        self.assertFalse(self.js(f"state.installAddon('{OTHER}')"))
        self.assertFalse(self.js(f"state.installAddon('{SHA}')"))
        self.assertFalse(self.js(f"state.enableAddon('org.example.battery','{SHA}')"))

    def test_all_lifecycle_requests_use_current_full_identity_and_restore_stays_off(self):
        self.activate(listing(enabled=True, previous=OTHER))
        self.assertTrue(self.js(f"state.disableAddon('org.example.battery','{SHA}')"))
        self.assertFalse(self.js("state.refresh()"))
        self.assertFalse(self.js(f"state.removeAddon('org.example.battery','{SHA}')"))
        self.reply(1, success(listing(previous=OTHER, generation="2" * 32)))
        self.assertTrue(self.js(f"state.rollbackAddon('org.example.battery','{SHA}')"))
        self.reply(2, success(listing(sha=OTHER, previous=SHA, generation="3" * 32)))
        self.assertFalse(self.js("state.addons[0].enabled"))
        self.assertFalse(self.js(f"state.removeAddon('org.example.battery','{SHA}')"))
        self.assertTrue(self.js(f"state.removeAddon('org.example.battery','{OTHER}')"))
        self.reply(3, success(dict(generation="4" * 32, addons=[])))
        self.assertEqual(self.data("state.addons"), [])
        self.assertFalse(self.js(f"state.enableAddon('org.example.battery','{OTHER}')"))
        self.assertEqual([c["member"] for c in self.data("calls.map(c => c.message)")],
                         ["ListAddons", "DisableAddon", "RollbackAddon", "RemoveAddon"])
        self.assertEqual(self.warnings, [])

    def test_client_deadline_invalidates_unknown_commit_and_late_success(self):
        self.activate(listing())
        self.js("state.deadline.interval = 5")
        self.js(f"state.enableAddon('org.example.battery','{SHA}')")
        QTest.qWait(12)
        self.assertIsNone(self.data("settlements[0].committed"))
        self.assertFalse(self.js("state.valid"))
        self.reply(1, success(listing(enabled=True, generation="2" * 32)))
        self.assertFalse(self.js("state.valid"))
        self.assertEqual(self.data("calls[2].message.member"), "ListAddons")
        self.assertEqual(len(self.data("settlements")), 1)

    def test_failed_inspection_clears_preview_but_keeps_metadata_usable_for_new_choice(self):
        self.activate(listing())
        self.preview()
        self.js("token = state.beginFileSelection(owner)")
        self.js(f"state.acceptFileSelection(owner, token, {json.dumps(URI)})")
        self.reply(2, failure("file", False))
        self.assertIsNone(self.data("state.preview"))
        self.assertTrue(self.js("state.valid"))
        self.assertEqual(self.data("state.addons[0].id"), "org.example.battery")
        self.assertTrue(self.js("token = state.beginFileSelection(owner); token !== null"))
        self.assertFalse(self.js(f"state.installAddon('{SHA}')"))

    def test_scope_invalidation_blocks_reentrant_selection_against_old_listing(self):
        self.activate(listing())
        self.js("token = state.beginFileSelection(owner)")
        self.js('reenter = "scope-reselection"; state.scopeKey = "another-tab"')
        self.assertEqual(self.data("reentries"), [False])
        self.assertFalse(self.js("state.selecting"))
        self.assertFalse(self.js("state.valid"))
        self.js('reenter = ""')
        QTest.qWait(1)
        self.assertEqual(self.data("calls[1].message.member"), "ListAddons")

    def test_strict_management_frames_fail_closed_without_path_feedback(self):
        self.activate(listing())
        valid_frame = success(listing())
        malformed = [None, {}, "", "not json /private/sentinel", valid_frame + "{}",
                     valid_frame.replace('"ok": true', '"ok": false, "ok": true'),
                     valid_frame.replace('"sha256":', '"sha256": "x", "sha\\u0032\\u0035\\u0036":'),
                     success(dict(generation=None, addons=listing()["addons"])),
                     success(dict(generation=GEN, addons={})),
                     success(dict(generation=GEN, addons=listing()["addons"] * 33)),
                     success(dict(generation=GEN, addons=listing()["addons"] * 2)),
                     failure("/private/sentinel", False), failure("io", "false"),
                     failure("io", True), failure("io", False, GEN),
                     '{"formatVersion":"0.1-experimental","ok":true,"result":' + '[' * 9 + ']' * 9 + '}',
                     " " * 262145, "é" * 131073,
                     valid_frame.replace('"enabled": false', '"enabled": 0'),
                     valid_frame.replace('"enabled": false', '"enabled": 1e999'),
                     valid_frame.replace('"sha256":', '"extra":null,"sha256":')]
        for raw in malformed:
            with self.subTest(raw=str(raw)[:110]):
                self.assertTrue(self.js("state.refresh()"))
                self.reply(len(self.data("calls")) - 1, raw)
                self.assertFalse(self.js("state.valid"))
                self.assertEqual(self.data("state.addons"), [])
                self.assertIsNone(self.data("state.preview"))
                self.assertNotIn("sentinel", self.js("state.feedback"))
                self.assertFalse(self.js(f"state.enableAddon('org.example.battery','{SHA}')"))
        self.assertEqual(self.warnings, [])

    def test_invalid_nested_manifest_and_inspect_response_cannot_be_approved(self):
        self.activate()
        mutations = [dict(id="org.example.bad/../../"), dict(id="org.example."),
                     dict(name=""), dict(name="x" * 81), dict(name="unsafe\nname"), dict(name="unsafe\u00a0name"),
                     dict(source=dict(namespace="../outside", formatVersion="0.1-experimental")),
                     dict(version="01.2.3"), dict(renderer="script"), dict(extra="value"),
                     dict(origin="https://user@example.org/project"), dict(origin="http://example.org/"),
                     dict(origin="https://example.org/?secret"), dict(origin="https://example.org/%0A"), dict(origin="https://[:1::2]/"),
                     dict(origin="https://[192.0.2.1::]/")]
        for changes in mutations:
            with self.subTest(changes=changes):
                self.js("token = state.beginFileSelection(owner)")
                self.assertTrue(self.js(f"state.acceptFileSelection(owner, token, {json.dumps(URI)})"))
                self.reply(len(self.data("calls")) - 1, success(dict(manifest=manifest(**changes), sha256=SHA)))
                self.assertIsNone(self.data("state.preview"))
                self.assertFalse(self.js(f"state.installAddon('{SHA}')"))
        self.assertEqual(self.warnings, [])

    def test_invalid_local_uris_never_dispatch_or_keep_old_approval(self):
        self.activate()
        self.preview()
        invalid = ["/synthetic/path", "https://example.org/package", "file://host/path", "file:/path",
                   "file:///a/../b", "file:///a/%2e%2e/b", "file:///a%00b", "file:///a%FFb",
                   "file:///a?query", "file:///a#fragment", "file:///a%xy", "file:///" + "a" * 4096, None, False]
        for uri in invalid:
            with self.subTest(uri=str(uri)[:100]):
                self.js("token = state.beginFileSelection(owner)")
                self.assertFalse(self.js("state.acceptFileSelection(owner, token," + json.dumps(uri) + ")"))
                self.assertIsNone(self.data("state.preview"))
                self.assertFalse(self.js(f"state.installAddon('{SHA}')"))
                self.assertEqual(len(self.data("calls")), 2)
        # A suffix is never used as trust: arbitrary local names go to backend inspection.
        uri = "file:///synthetic/Bateria%20%C3%A1%23%3F.data"
        self.js("token = state.beginFileSelection(owner)")
        self.assertTrue(self.js("state.acceptFileSelection(owner,token," + json.dumps(uri) + ")"))
        self.assertEqual(self.data("calls[2].message.arguments"), [uri])

    def test_32_rows_are_preserved_but_multiple_enabled_providers_are_rejected(self):
        rows = [dict(manifest=manifest(id=f"org.example.battery{i:02d}"), sha256=SHA,
                     enabled=False, previousSha256=None) for i in range(32)]
        self.activate(dict(generation=GEN, addons=rows))
        self.assertEqual(len(self.data("state.addons")), 32)
        rows[0]["enabled"] = True
        rows[1]["enabled"] = True
        self.js("state.refresh()")
        self.reply(1, success(dict(generation=GEN, addons=rows)))
        self.assertFalse(self.js("state.valid"))
        self.assertEqual(self.data("state.addons"), [])

    def test_commit_certainty_and_generation_are_preserved_exactly(self):
        self.activate(listing())
        for committed, generation in ((False, None), (True, "2" * 32), (None, None), (None, "3" * 32)):
            with self.subTest(committed=committed, generation=generation):
                self.assertTrue(self.js(f"state.enableAddon('org.example.battery','{SHA}')"))
                index = len(self.data("calls")) - 1
                self.reply(index, failure("io", committed, generation))
                settled = self.data("settlements")[-1]
                self.assertIs(settled["committed"], committed)
                self.assertEqual(settled["generation"], generation)
                self.assertFalse(settled["busy"])
                QTest.qWait(1)
                self.assertEqual(self.data("calls")[-1]["message"]["member"], "ListAddons")
                self.reply(len(self.data("calls")) - 1, success(listing()))
        self.assertEqual(self.warnings, [])

    def test_malicious_success_cannot_auto_activate_install_or_rollback(self):
        self.activate(listing(previous=OTHER))
        self.preview()
        self.js(f"state.installAddon('{SHA}')")
        self.reply(2, success(listing(enabled=True, generation="2" * 32)))
        self.assertIsNone(self.data("settlements")[0]["committed"])
        self.assertFalse(self.js("state.valid"))
        self.assertIsNone(self.data("state.preview"))
        QTest.qWait(1)
        self.reply(3, success(listing(previous=OTHER)))
        self.js(f"state.rollbackAddon('org.example.battery','{SHA}')")
        self.reply(4, success(listing(enabled=True, sha=OTHER, previous=SHA, generation="3" * 32)))
        self.assertIsNone(self.data("settlements")[1]["committed"])
        self.assertFalse(self.js("state.valid"))

    def test_publication_invalidation_is_atomic_and_newer_lifetime_wins(self):
        self.js('reenter = "publish-aba"; state.active = true')
        QTest.qWait(1)
        self.reply(0, success(listing(enabled=True)))
        self.assertFalse(self.js("state.valid"))
        self.assertEqual(self.data("state.addons"), [])
        self.assertIsNone(self.data("state.preview"))
        self.js('reenter = ""')
        QTest.qWait(1)
        self.reply(1, success(listing()))
        self.assertFalse(self.js("state.addons[0].enabled"))
        self.reply(0, success(listing(enabled=True)))
        self.assertFalse(self.js("state.addons[0].enabled"))

    def test_native_picker_lifetime_cancels_exact_selection_without_opening_dialog(self):
        self.activate()
        self.assertFalse(self.js("filePicker.visible"))
        self.assertFalse(self.js("filePicker.open()"))  # no window: never opens a dialog
        for change in ("pickerActive = false", "filePicker.parentWindow = alternateWindow",
                       "filePicker.manager = null", 'state.scopeKey = "picker-new-tab"'):
            with self.subTest(change=change):
                self.js("filePicker.manager = state; filePicker.parentWindow = null; pickerActive = true")
                self.js("token = state.beginFileSelection(filePicker); filePicker.selectionState = state; filePicker.selectionToken = token")
                self.assertTrue(self.js("state.selecting"))
                self.js(change)
                self.assertFalse(self.js("state.selecting"))
                self.assertIsNone(self.data("filePicker.selectionToken"))
                self.assertFalse(self.js("filePicker.visible"))
        self.assertEqual(len(self.data("calls")), 1)
        self.assertEqual(self.warnings, [])

    def test_stale_picker_cancellation_cannot_release_a_newer_owner(self):
        self.activate()
        self.js("oldToken = state.beginFileSelection(filePicker); filePicker.selectionState = state; filePicker.selectionToken = oldToken")
        self.js("state.cancelFileSelection(filePicker, oldToken); token = state.beginFileSelection(otherOwner)")
        self.js("filePicker.cancelSelection()")
        self.assertTrue(self.js("state.ownsFileSelection(otherOwner, token)"))
        self.assertFalse(self.js("filePicker.visible"))
        self.assertEqual(len(self.data("calls")), 1)
        self.assertEqual(self.warnings, [])

    def test_reinstall_existing_enabled_package_does_not_reuse_consent(self):
        self.activate(listing(enabled=True))
        self.preview()
        self.assertFalse(self.js("state.preview.enabled"))
        self.assertTrue(self.js(f"state.installAddon('{SHA}')"))
        self.reply(2, success(listing(generation="2" * 32)))
        self.assertFalse(self.js("state.addons[0].enabled"))
        self.assertEqual(len(self.data("calls")), 3)
        self.assertFalse(self.js(f"state.installAddon('{SHA}')"))

    def test_bus_reply_must_contain_exactly_one_typed_string(self):
        self.activate()
        for reply in ({"values": [], "value": {"value": success(listing())}},
                      {"values": [{}, {}], "value": {"value": success(listing())}},
                      {"values": [{}], "value": success(listing())},
                      {"values": [{}], "value": {"value": True}},
                      {"values": [{}], "value": {"value": {"ok": True}}}):
            self.assertTrue(self.js("state.refresh()"))
            index = len(self.data("calls")) - 1
            self.js(f"calls[{index}].resolve({json.dumps(reply)})")
            self.assertFalse(self.js("state.valid"))
            self.assertEqual(self.data("state.addons"), [])
        self.assertEqual(self.warnings, [])

    def test_old_unopened_dialog_acceptance_cannot_consume_a_reopened_selection(self):
        self.activate()
        # Construct native dialog objects but never call open(), show() or send input.
        stage = """
            token = state.beginFileSelection(filePicker);
            filePicker.selectionState = state; filePicker.selectionToken = token;
            if (!filePicker.chooser) filePicker.chooser = filePicker.createDialog(state,token,filePicker.parentWindow);
        """
        self.js(stage)
        self.assertTrue(self.js("filePicker.chooser.requestToken===token"))
        selected = Path(os.environ["TMPDIR"]) / "old.data"
        selected.write_bytes(b"")
        self.js("oldDialog = filePicker.chooser; oldDialog.selectedFile = " + json.dumps(selected.as_uri()))
        # One JS turn deliberately retains the closing QObject until its deferred destruction.
        self.js("filePicker.cancelSelection(); " + stage + " oldDialog.accepted()")
        self.assertTrue(self.js("state.ownsFileSelection(filePicker, token)"))
        self.assertEqual(len(self.data("calls")), 1)
        self.assertIsNone(self.data("state.preview"))
        self.assertEqual(self.warnings, [])

    def test_destroyed_surface_owner_cannot_publish_or_dispatch(self):
        self.activate(listing())
        self.js('state.owner = Qt.createQmlObject("import QtQuick; QtObject {}", owner)')
        QTest.qWait(1)
        index = len(self.data("calls")) - 1
        self.js("state.owner.destroy()")
        QTest.qWait(1)
        self.reply(index, success(listing(enabled=True)))
        self.assertFalse(self.js("state.valid"))
        self.assertFalse(self.js("state.refresh()"))
        self.assertFalse(self.js(f"state.enableAddon('org.example.battery','{SHA}')"))
        self.assertEqual(self.warnings, [])

    def test_backend_valid_unicode_and_ipv6_metadata_remain_plain_data(self):
        self.activate()
        for origin in ("https://[::1]/project", "https://[::ffff:192.0.2.1]:443/project", "https://example.org/project", "https://example.org/@project"):
            self.js("token = state.beginFileSelection(owner)")
            self.js(f"state.acceptFileSelection(owner, token, {json.dumps(URI)})")
            self.reply(len(self.data("calls")) - 1, success(dict(manifest=manifest(name="Bateria á 漢字 😀 <b>", origin=origin), sha256=SHA)))
            self.assertEqual(self.data("state.preview.name"), "Bateria á 漢字 😀 <b>")
            self.assertEqual(self.data("state.preview.origin"), origin)
        self.assertEqual(self.warnings, [])

    def test_current_dialog_creation_and_accepted_signal_preserve_exact_token_and_uri(self):
        self.activate()
        uri = self.stage_picker()
        self.assertTrue(self.js("oldDialog.requestToken === token"))
        self.assertTrue(self.js("oldDialog.requestState === state && oldDialog.requestWindow === alternateWindow && oldDialog.parentWindow === alternateWindow"))
        self.js("oldDialog.accepted()")
        self.assertEqual(self.data("calls[1].message.arguments"), [uri])
        self.assertTrue(self.js("state.loading && state.busy && !state.selecting"))
        self.reply(1, success(dict(manifest=manifest(), sha256=SHA)))
        self.assertTrue(self.js(f"state.installAddon('{SHA}')"))
        self.assertEqual(self.data("calls[2].message.arguments"), [uri, SHA])

    def test_picker_handoff_cancellation_observers_prevent_inspect_dispatch(self):
        cases = [(event, action) for event in ("picker-state", "picker-token", "picker-chooser")
                 for action in ("filePicker.active=false", "filePicker.manager=null", "alternateWindow.visible=false",
                                "filePicker.parentWindow=null", "filePicker.active=false;filePicker.active=true")]
        for event, action in cases:
            with self.subTest(event=event, action=action):
                self.tearDown()
                self.setUp()
                self.activate()
                self.stage_picker()
                before = len(self.data("calls"))
                self.js("hook=function(event){if(event==="+json.dumps(event)+"){hook=null;"+action+";}}")
                self.js("oldDialog.accepted()")
                self.assertEqual(len(self.data("calls")), before)
                self.assertFalse(self.js("state.busy || state.selecting"))
                self.assertIsNone(self.data("state.preview"))

    def test_backend_maximum_codepoints_inspect_and_32_row_listing(self):
        fmt = self.backend_format()
        m = manifest(name="😀"*80, description="𝄞"*240, author="𐐀"*120, license="🦀"*80)
        self.assertEqual(fmt.validate_manifest(m), m)
        self.assertEqual(self.js('(function(){let n=0;for(const c of "😀".repeat(80))n++;return n;})()'), 80)
        self.activate()
        self.js("token=state.beginFileSelection(owner)")
        self.js("state.acceptFileSelection(owner,token,"+json.dumps(URI)+")")
        self.reply(1, success(dict(manifest=m, sha256=SHA)))
        self.assertIsNotNone(self.data("state.preview"))
        self.assertEqual(self.data("state.preview")["name"], m["name"])
        self.assertTrue(self.js(f"state.installAddon('{SHA}')"))
        self.reply(2, success(dict(generation=GEN, addons=[dict(manifest=m,sha256=SHA,enabled=False,previousSha256=None)])))
        self.assertTrue(self.js("state.valid"))
        rows=[]
        for i in range(32):
            item=dict(m, id="org.example."+"a"*100+str(i).zfill(2),
                      origin="https://example.org/"+"a"*(512-len("https://example.org/")),version="1."+"1"*28+".0")
            self.assertEqual(fmt.validate_manifest(item),item)
            rows.append(dict(manifest=item,sha256=SHA,enabled=False,previousSha256=OTHER))
        raw=json.dumps(dict(formatVersion="0.1-experimental",ok=True,result=dict(generation=GEN,addons=rows)),ensure_ascii=True,separators=(",",":"))
        self.assertLess(len(raw.encode()),262144)
        self.js("state.refresh()")
        self.reply(3,raw)
        self.assertEqual(len(self.data("state.addons")),32)
        self.assertTrue(self.js("state.valid"))

    def test_picker_handoff_state_signal_revocation_blocks_dispatch_without_idle_gap(self):
        for event in ("loading", "selecting"):
            for action in ("filePicker.active=false", "filePicker.manager=null", "alternateWindow.visible=false"):
                with self.subTest(event=event, action=action):
                    self.tearDown(); self.setUp(); self.activate()
                    self.stage_picker()
                    self.js("hook=function(event){if(event==="+json.dumps(event)+"){hook=null;"+action+";}}")
                    self.js("oldDialog.accepted()")
                    self.assertEqual(len(self.data("calls")),1)
                    self.assertFalse(self.js("state.busy || state.selecting"))
        self.tearDown(); self.setUp(); self.activate()
        uri = self.stage_picker()
        # Successful transfer stays busy from chooser reservation through Inspect.
        self.js('hook=null; reentries=[]; hook=function(event){if(event==="busy") reentries=reentries.concat([state.busy]);}')
        self.js("oldDialog.accepted()")
        self.assertEqual(self.data("reentries"),[])
        self.assertEqual(self.data("calls[1].message.arguments"),[uri])
        self.reply(1,success(dict(manifest=manifest(),sha256=SHA)))
        self.assertEqual(self.data("reentries"),[False])

    def test_handoff_cleanup_and_retired_signals_preserve_a_newer_token(self):
        self.activate()
        self.stage_picker()
        self.js("""hook=function(event){if(event==="picker-state") {
            hook=null; state.cancelFileSelection(filePicker,token);
            oldToken=token; token=state.beginFileSelection(filePicker);
            filePicker.selectionState=state; filePicker.selectionToken=token;
            filePicker.chooser=filePicker.createDialog(state,token,alternateWindow);
        }}; oldDialog.accepted(); oldDialog.rejected();""")
        self.assertTrue(self.js("state.ownsFileSelection(filePicker,token)"))
        self.assertTrue(self.js("filePicker.selectionToken===token && filePicker.chooser.requestToken===token"))
        self.assertEqual(len(self.data("calls")),1)
        self.assertFalse(self.js("state.cancelFileSelection(filePicker,oldToken)"))
        self.js("hook=null; filePicker.cancelSelection()")
        self.assertFalse(self.js("state.busy"))

    def test_supplementary_field_limits_are_codepoints_and_byte_limit_is_independent(self):
        fmt = self.backend_format()
        self.activate()
        for key,limit in (("name",80),("description",240),("author",120),("license",80)):
            for size in (limit//2+1,limit,limit+1):
                with self.subTest(field=key,size=size):
                    m=manifest(**{key:"😀"*size})
                    if size<=limit:
                        self.assertEqual(fmt.validate_manifest(m),m)
                    else:
                        with self.assertRaises(fmt.AddonError): fmt.validate_manifest(m)
                    self.js("token=state.beginFileSelection(owner)")
                    self.js("state.acceptFileSelection(owner,token,"+json.dumps(URI)+")")
                    self.reply(len(self.data("calls"))-1,success(dict(manifest=m,sha256=SHA)))
                    self.assertEqual(self.data("state.preview") is not None,size<=limit)
        raw=success(dict(generation=None,addons=[]))
        self.js("state.refresh()")
        self.reply(len(self.data("calls"))-1,raw+" "*(262144-len(raw.encode())))
        self.assertTrue(self.js("state.valid"))
        self.js("state.refresh()")
        self.reply(len(self.data("calls"))-1,raw+" "*(262145-len(raw.encode())))
        self.assertFalse(self.js("state.valid"))

    def test_nonprinting_metadata_never_publishes_listing_preview_or_install_approval(self):
        fmt=self.backend_format()
        results=[]
        for field in ("name","description","author","license"):
            for character in ("\u0600","\u070f","\ufff9","\ue000","\u0378","\ufdd0"):
                m=manifest(**{field:"synthetic"+character+"label"})
                with self.assertRaises(fmt.AddonError): fmt.validate_manifest(m)
                self.tearDown();self.setUp()
                self.activate(dict(generation=GEN,addons=[dict(manifest=m,sha256=SHA,enabled=False,previousSha256=None)]))
                listing_valid=self.js("state.valid")
                rows=self.data("state.addons")
                self.tearDown();self.setUp();self.activate()
                self.stage_picker()
                self.js("oldDialog.accepted()")
                self.reply(1,success(dict(manifest=m,sha256=SHA)))
                preview=self.data("state.preview")
                install=self.js(f"state.installAddon('{SHA}')")
                results.append(dict(field=field,codepoint=f"U+{ord(character):04X}",listingValid=listing_valid,
                                    rowCount=len(rows),preview=preview is not None,install=install,
                                    installDispatched="InstallAddon" in self.data("calls.map(c=>c.message.member)")))
        self.assertFalse(any(r["listingValid"] or r["rowCount"] or r["preview"] or r["install"] or r["installDispatched"] for r in results),results)

    def test_canonical_profile_matches_actual_state_plain_for_every_scalar(self):
        import hashlib
        from test_addon_text_profile import canonical_oracle, GOLDEN
        _, expected=canonical_oracle()
        actual=bytearray(139264);scalars=0
        for start in range(0,0x110000,4096):
            end=min(start+4096,0x110000)
            values=self.data("""(function(){let values=[];for(let cp=%d;cp<%d;++cp){
                const n=cp-0x10000;
                const character=cp<0x10000 ? String.fromCharCode(cp)
                    : String.fromCharCode(0xd800+Math.floor(n/0x400),0xdc00+n%%0x400);
                values.push(state.plain(character,1));}return values;})()""" % (start,end))
            self.assertEqual(len(values),end-start)
            for offset,accepted in enumerate(values):
                cp=start+offset
                self.assertIs(type(accepted),bool)
                if accepted: actual[cp//8] |= 1 << (cp%8)
                if not 0xd800<=cp<=0xdfff: scalars+=1
        mismatches=[f"U+{cp:04X}" for cp in range(0x110000)
                    if bool(actual[cp//8] & (1<<(cp%8))) != bool(expected[cp//8] & (1<<(cp%8)))]
        self.assertEqual(scalars,1112064)
        self.assertEqual(mismatches,[],str(len(mismatches))+" canonical mismatches; first "+str(mismatches[:16]))
        self.assertEqual(hashlib.sha256(actual).hexdigest(),GOLDEN)
        # Invalid UTF-16 pair shapes and scalar maxima use the consumer entry point too.
        for value in ("\ud800", "\udfff", "\ud800A", "A\udfff", "\udfff\ud800", "", "😀"*81):
            self.assertFalse(self.js('state.plain('+json.dumps(value)+',80)'))
        for value in (" ","e\u0301","😀"*80,"\u1c89","\U00010d40","\U00011bc0","\U0001e5d0"):
            self.assertTrue(self.js('state.plain('+json.dumps(value)+',80)'))

    def test_fixed_profile_refuses_later_assigned_text_before_approval(self):
        for field in ("name", "description", "author", "license"):
            self.tearDown();self.setUp()
            m=manifest(**{field:"synthetic\u088flabel"})
            self.activate(dict(generation=GEN,addons=[dict(manifest=m,sha256=SHA,enabled=False,previousSha256=None)]))
            listing_valid=self.js("state.valid");rows=self.data("state.addons")
            self.tearDown();self.setUp();self.activate()
            self.js("token=state.beginFileSelection(owner)")
            self.js("state.acceptFileSelection(owner,token,"+json.dumps(URI)+")")
            self.reply(1,success(dict(manifest=m,sha256=SHA)))
            self.assertFalse(self.js("state.preview !== null"),field)
            self.assertFalse(self.js("state.installAddon('"+SHA+"')"),field)
            self.assertEqual(self.data("calls.map(c=>c.message.member)"),["ListAddons","InspectAddonFile"])
            self.assertFalse(listing_valid,field);self.assertEqual(rows,[],field)


    def test_interval_boundaries_in_four_fields_use_public_listing_inspect_and_install(self):
        from test_addon_text_profile import canonical_oracle
        profile,vector=canonical_oracle()
        points={0x088f,0x1c89,0x10d40,0x11bc0,0x1e5d0,0xd800,0xdfff}
        for first,last in profile["ranges"]:
            points.update(cp for cp in (first-1,first,last,last+1) if 0<=cp<0x110000)
        cases=[dict(cp=cp,value="synthetic"+chr(cp),expected=bool(vector[cp//8] & (1<<(cp%8)))) for cp in sorted(points)]
        fmt=self.backend_format()
        for case in cases:
            for field in ("name","description","author","license"):
                m=manifest(**{field:case["value"]})
                try: fmt.validate_manifest(m);accepted=True
                except fmt.AddonError: accepted=False
                self.assertEqual(accepted,case["expected"],(field,case["cp"]))
        self.activate()
        checked=0
        for offset in range(0,len(cases),64):
            result=self.data("""(function(){
                const cases=%s,base=%s,sha=%s,uri=%s;
                const failures=[];let checked=0;
                function response(result){succeed(calls.length-1,JSON.stringify({formatVersion:'0.1-experimental',ok:true,result:result}));}
                for(const c of cases)for(const field of ['name','description','author','license']){
                    calls=[];starts=[];settlements=[];
                    const m=JSON.parse(JSON.stringify(base));m[field]=c.value;
                    const row={manifest:m,sha256:sha,enabled:false,previousSha256:null};
                    const sent=state.refresh();response({generation:'11111111111111111111111111111111',addons:[row]});
                    const valid=state.valid && state.addons.length===1;
                    // Inspect independently, after recovering a valid empty registry.
                    state.refresh();response({generation:'11111111111111111111111111111111',addons:[]});calls=[];
                    const token=state.beginFileSelection(owner);
                    const inspected=state.acceptFileSelection(owner,token,uri);
                    response({manifest:m,sha256:sha});
                    const preview=state.preview!==null;
                    const installed=state.installAddon(sha);
                    const correct=c.expected===valid && c.expected===preview && c.expected===installed
                        && sent && inspected && calls.length===(c.expected?2:1)
                        && (!installed || (calls[1].message.member==='InstallAddon'
                            && calls[1].message.arguments[0]===uri && calls[1].message.arguments[1]===sha));
                    if(!correct)failures.push({cp:c.cp,field:field,valid:valid,preview:preview,installed:installed});
                    if(installed)response({generation:'22222222222222222222222222222222',addons:[row]});
                    checked++;
                }return {checked:checked,failures:failures};})()""" %
                (json.dumps(cases[offset:offset+64]),json.dumps(manifest()),json.dumps(SHA),json.dumps(URI)))
            self.assertEqual(result["failures"],[])
            checked+=result["checked"]
        self.assertEqual(checked,len(cases)*4)

    def test_profile_origins_decode_percent_text_and_keep_url_and_id_rules(self):
        from urllib.parse import quote
        fmt=self.backend_format();self.activate()
        cases=[('https://example.org/'+quote(value),expected) for value,expected in
               [('\u088f',False),('\u0600',False),('\ue000',False),('\ufdd0',False),
                ('\u1c89',True),('\U0001e5d0',True),('e\u0301',True),('😀',True),(' ',True)]]
        cases += [('https://user@example.org/p',False),('https://example.org/?x=1',False),
                  ('https://example.org/%ff',False),('https://example.org/%',False),
                  ('https://example.org:65536/p',False),('http://example.org/p',False)]
        for origin,expected in cases:
            m=manifest(origin=origin)
            try: fmt.validate_manifest(m);accepted=True
            except fmt.AddonError: accepted=False
            self.assertEqual(accepted,expected,origin)
            self.js('token=state.beginFileSelection(owner)')
            self.js('state.acceptFileSelection(owner,token,'+json.dumps(URI)+')')
            self.reply(len(self.data('calls'))-1,success(dict(manifest=m,sha256=SHA)))
            self.assertEqual(self.data('state.preview') is not None,expected,origin)
        for identity in ('org.example.\u1c89','org.😀','Org.example','org.example/other'):
            m=manifest(id=identity)
            with self.assertRaises(fmt.AddonError): fmt.validate_manifest(m)
            self.js('token=state.beginFileSelection(owner)')
            self.js('state.acceptFileSelection(owner,token,'+json.dumps(URI)+')')
            self.reply(len(self.data('calls'))-1,success(dict(manifest=m,sha256=SHA)))
            self.assertIsNone(self.data('state.preview'))


if __name__ == "__main__":
    unittest.main()
