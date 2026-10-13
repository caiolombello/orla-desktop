"""Portable appearance uses the real profile writer and dock presentation."""
import json
import unittest
from pathlib import Path

import test_profiles_dock as fixtures
from PySide6.QtCore import Qt, QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QSignalSpy, QTest


class AppearancePresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("AppearancePresetHarness.qml").resolve())))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.config = self.window.findChild(QObject, "configuration")
        self.dock = self.window.findChild(QQuickItem, "dock")
        self.popup = self.window.findChild(QObject, "settingsPopup")
        QTest.qWait(20)
    tearDown = fixtures.ProfilesDockTests.tearDown
    dispose = fixtures.ProfilesDockTests.dispose
    evaluate = fixtures.ProfilesDockTests.evaluate
    command = fixtures.ProfilesDockTests.command
    initialize = fixtures.ProfilesDockTests.initialize
    owned_item = fixtures.ProfilesDockTests.owned_item
    focus = fixtures.ProfilesDockTests.focus
    settle = fixtures.ProfilesDockTests.settle
    flat = fixtures.ProfilesDockTests.flat

    def exported(self):
        self.assertTrue(self.evaluate("appearancePreset.exportSaved()"))
        return json.loads(self.evaluate("appearancePreset.exportText"))

    def candidate(self):
        data = self.exported()
        data['appearance']['baseTheme'] = 'paper'
        data['appearance']['tokens']['radius'] = 8
        data['appearance']['tokens']['reducedMotion'] = True
        data['widgets'].reverse()
        data['widgets'][0]['visible'] = True
        data['widgets'][-1]['visible'] = False
        return data

    def preview(self, data):
        self.evaluate("appearancePreset.setInputText(" + json.dumps(json.dumps(data)) + ")")
        self.assertTrue(self.evaluate("appearancePreset.previewImport()"))

    def test_combined_preview_apply_undo_preserves_other_data_and_writes_once(self):
        self.initialize()
        self.evaluate("appearance.begin()")
        before = self.config.property('profilesJSON')
        flat = self.flat()
        data = self.candidate()
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.preview(data)
        self.assertEqual(self.config.property('profilesJSON'), before)
        self.assertEqual(json.loads(self.evaluate('JSON.stringify(displayWidgets)')), data['widgets'])
        self.assertEqual(self.evaluate('appearance.effective.tokens.radius'), 8)
        self.assertFalse(self.command('select', 'personal'))
        self.assertTrue(self.evaluate('appearancePreset.apply()'))
        self.assertEqual(writes.count(), 1)
        saved = json.loads(self.config.property('profilesJSON'))
        original = json.loads(before)
        for profile in saved['profiles']:
            old = next(p for p in original['profiles'] if p['id'] == profile['id'])
            if profile['id'] != 'work':
                self.assertEqual(profile, old)
            else:
                self.assertEqual(profile['widgets'], data['widgets'])
                self.assertEqual(json.loads(profile['appearance']['appearanceJSON']), data['appearance'])
                for key in ('launchers', 'calendarEvents', 'currentDesktopOnly', 'showAudioHud'):
                    self.assertEqual(profile[key], old[key])
        self.assertEqual(self.flat(), flat)
        self.assertTrue(self.evaluate('appearancePreset.undo()'))
        self.assertEqual(writes.count(), 2)
        self.assertEqual(json.loads(self.config.property('profilesJSON')), original)
        self.assertEqual(self.flat(), flat)

    def test_keyboard_import_apply_and_escape_cancel_fit_420_pixels(self):
        self.initialize()
        self.popup.setProperty('heightBudget', 420)
        self.evaluate('open()', self.popup)
        QTest.qWait(30)
        before = self.config.property('profilesJSON')
        data = self.candidate()
        disclosure = self.owned_item('appearancePresetJSON')
        self.assertIsNotNone(disclosure)
        self.focus(disclosure)
        QTest.keyClick(self.window, Qt.Key_Space)
        field = self.owned_item('appearancePresetInput')
        field.setProperty('text', json.dumps(data))
        self.focus(field)
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetPreview')
        QTest.keyClick(self.window, Qt.Key_Return)
        self.assertTrue(self.evaluate('appearancePreset.hasPreview'), self.evaluate('JSON.stringify({error:appearancePreset.error,text:appearancePreset.inputText,pending:appearancePreset.pending,editing:appearance.editing})'))
        self.assertEqual(self.config.property('profilesJSON'), before)
        self.assertEqual(json.loads(self.evaluate('JSON.stringify(displayWidgets)')), data['widgets'])
        self.focus(field)
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.settle(lambda: not self.popup.property('visible'))
        self.assertEqual(self.config.property('profilesJSON'), before)
        self.assertEqual(self.evaluate('appearancePreset.inputText'), '')
        self.assertEqual(json.loads(self.evaluate('JSON.stringify(displayWidgets)')),
                         next(p for p in json.loads(before)['profiles'] if p['id'] == 'work')['widgets'])
        self.evaluate('open()', self.popup)
        QTest.qWait(30)
        self.preview(data)
        apply = self.owned_item('appearanceApply')
        self.focus(apply)
        QTest.keyClick(self.window, Qt.Key_Return)
        self.assertEqual(json.loads(self.evaluate('JSON.stringify(presentation.widgets)')), data['widgets'])
        self.focus(self.owned_item('appearanceUndo'))
        QTest.keyClick(self.window, Qt.Key_Return)
        self.assertEqual(json.loads(self.config.property('profilesJSON')), json.loads(before))

    def test_reentrant_input_edit_remains_pending_and_cannot_apply_old_preview(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        data = self.candidate()
        before = self.config.property('profilesJSON')
        self.evaluate("appearance.draftChanged.connect(function handler() { appearance.draftChanged.disconnect(handler); appearancePreset.setInputText('{invalid}'); })")
        self.evaluate('appearancePreset.setInputText(' + json.dumps(json.dumps(data)) + ')')
        self.assertFalse(self.evaluate('appearancePreset.previewImport()'))
        self.assertEqual(self.evaluate('appearancePreset.inputText'), '{invalid}')
        self.assertFalse(self.evaluate('appearancePreset.canApply'))
        self.assertFalse(self.evaluate('appearancePreset.apply()'))
        self.assertEqual(self.config.property('profilesJSON'), before)

    def test_export_saved_ignores_draft_and_rejects_corrupted_saved_profile(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        saved = self.exported()
        self.evaluate("appearance.setToken('radius', 11)")
        self.assertEqual(self.exported(), saved)
        self.config.setProperty('profilesJSON', '{"formatVersion":"future"}')
        raw = self.config.property('profilesJSON')
        self.assertFalse(self.evaluate('appearancePreset.exportSaved()'))
        self.assertEqual(self.config.property('profilesJSON'), raw)

    def test_invalid_import_keeps_good_preview_and_clear_recovers_without_writing(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        data = self.candidate()
        self.preview(data)
        before = self.config.property('profilesJSON')
        self.evaluate("appearancePreset.setInputText('{bad}')")
        self.assertFalse(self.evaluate('appearancePreset.previewImport()'))
        self.assertEqual(self.evaluate('appearance.effective.tokens.radius'), 8)
        self.assertEqual(json.loads(self.evaluate('JSON.stringify(displayWidgets)')), data['widgets'])
        self.assertFalse(self.evaluate('appearancePreset.canApply'))
        self.assertFalse(self.evaluate('appearancePreset.apply()'))
        self.assertEqual(self.config.property('profilesJSON'), before)
        self.evaluate('appearancePreset.clearInput()')
        self.assertTrue(self.evaluate('appearancePreset.canApply'))
        self.assertTrue(self.evaluate('appearancePreset.apply()'))

    def test_external_revision_revokes_preview_and_newer_widget_edit_revokes_undo(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        data = self.candidate()
        self.preview(data)
        self.assertTrue(self.command('commitPresentation', {'calendarEvents': True}))
        saved = self.config.property('profilesJSON')
        self.assertFalse(self.evaluate('appearancePreset.hasPreview'))
        self.assertFalse(self.evaluate('appearancePreset.apply()'))
        self.assertEqual(self.config.property('profilesJSON'), saved)
        self.evaluate('appearancePreset.clearInput()')
        self.preview(data)
        self.assertTrue(self.evaluate('appearancePreset.apply()'))
        widgets = data['widgets'][:]
        widgets[1] = dict(widgets[1], visible=not widgets[1]['visible'])
        self.assertTrue(self.command('commitPresentation', {'widgets': widgets}))
        newer = self.config.property('profilesJSON')
        self.assertFalse(self.evaluate('appearancePreset.canUndo'))
        self.assertFalse(self.evaluate('appearancePreset.undo()'))
        self.assertEqual(self.config.property('profilesJSON'), newer)

    def test_reentrant_cancel_during_commit_cannot_publish_undo_or_confirm_old_intent(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        self.preview(self.candidate())
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.evaluate("configuration.profilesJSONChanged.connect(function handler() { configuration.profilesJSONChanged.disconnect(handler); appearancePreset.cancel(); })")
        self.assertFalse(self.evaluate('appearancePreset.apply()'))
        self.assertEqual(writes.count(), 1)
        self.assertFalse(self.evaluate('appearancePreset.canUndo'))
        self.assertFalse(self.evaluate('appearancePreset.hasPreview'))

    def test_reentrant_newer_edit_during_apply_finalization_cannot_be_undone(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        self.preview(self.candidate())
        self.evaluate("appearance.draftChanged.connect(function handler() { appearance.draftChanged.disconnect(handler); profiles.commitPresentation({calendarEvents:true},profiles.activeProfileId,profiles.revision); })")
        self.assertFalse(self.evaluate('appearancePreset.apply()'))
        saved = self.config.property('profilesJSON')
        self.assertTrue(self.evaluate('presentation.calendarEvents'))
        self.assertFalse(self.evaluate('appearancePreset.canUndo'))
        self.assertFalse(self.evaluate('appearancePreset.undo()'))
        self.assertEqual(self.config.property('profilesJSON'), saved)

    def test_legacy_export_guides_to_existing_profile_creation_without_migration(self):
        self.evaluate('open()', self.popup)
        QTest.qWait(30)
        before = self.config.property('profilesJSON')
        data = self.exported()
        self.evaluate('appearancePreset.setInputText(' + json.dumps(json.dumps(data)) + ')')
        self.assertFalse(self.evaluate('appearancePreset.previewImport()'))
        self.assertEqual(self.config.property('profilesJSON'), before)
        self.evaluate('appearancePreset.clearInput()')
        disclosure = self.owned_item('appearancePresetJSON')
        disclosure.setProperty('checked', True)
        link = self.owned_item('appearancePresetProfiles')
        self.focus(link)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(self.owned_item('settingsTabs').property('currentIndex'), 2)
        initialize = self.owned_item('profileInitialize')
        self.assertTrue(initialize.property('enabled'))
        self.focus(initialize)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertTrue(self.evaluate('profiles.initialized'))
        self.assertEqual(self.evaluate('profiles.activeProfileId'), 'legacy')

    def test_reentrant_token_edit_during_preview_preserves_newer_draft(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        data = self.candidate()
        before = self.config.property('profilesJSON')
        self.evaluate("appearance.draftChanged.connect(function handler() { appearance.draftChanged.disconnect(handler); appearance.setToken('radius',17); })")
        self.evaluate('appearancePreset.setInputText(' + json.dumps(json.dumps(data)) + ')')
        self.assertFalse(self.evaluate('appearancePreset.previewImport()'))
        self.assertEqual(self.evaluate('appearance.draft.tokens.radius'), 17)
        self.assertEqual(self.evaluate('appearance.effective.tokens.radius'), 17)
        self.assertFalse(self.evaluate('appearancePreset.canApply'))
        self.assertEqual(self.config.property('profilesJSON'), before)
        self.evaluate('appearancePreset.clearInput()')
        self.assertTrue(self.evaluate('appearance.apply()'))
        self.assertEqual(self.evaluate('appearance.active.tokens.radius'), 17)

    def test_reentrant_scope_change_while_clearing_preview_cannot_receive_old_undo(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        self.preview(self.candidate())
        self.evaluate("appearancePreset.inputTextChanged.connect(function handler() { if (appearancePreset.inputText.length) return; appearancePreset.inputTextChanged.disconnect(handler); const doc=JSON.parse(configuration.profilesJSON); doc.activeProfileId='personal'; configuration.profilesJSON=JSON.stringify(doc); })")
        self.assertFalse(self.evaluate('appearancePreset.apply()'))
        self.assertEqual(self.evaluate('profiles.activeProfileId'), 'personal')
        saved = self.config.property('profilesJSON')
        self.assertFalse(self.evaluate('appearancePreset.canUndo'))
        self.assertFalse(self.evaluate('appearancePreset.undo()'))
        self.assertEqual(self.config.property('profilesJSON'), saved)

    def test_keyboard_can_reach_export_and_select_output_before_import(self):
        self.initialize()
        self.evaluate('open()', self.popup)
        QTest.qWait(30)
        disclosure = self.owned_item('appearancePresetJSON')
        disclosure.setProperty('checked', True)
        self.focus(disclosure)
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetExport')
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetOutput')
        QTest.keyClick(self.window, Qt.Key_A, Qt.ControlModifier)
        output = self.owned_item('appearancePresetOutput')
        self.assertEqual(output.property('selectedText'), self.evaluate('appearancePreset.exportText'))
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetInput')
        QTest.keyClick(self.window, Qt.Key_Backtab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetOutput')

    def test_empty_import_input_tab_leaves_for_enabled_action(self):
        self.initialize()
        self.evaluate('open()', self.popup)
        QTest.qWait(30)
        self.owned_item('appearancePresetJSON').setProperty('checked', True)
        field = self.owned_item('appearancePresetInput')
        self.focus(field)
        self.assertEqual(field.property('text'), '')
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetClear')
        QTest.keyClick(self.window, Qt.Key_Backtab)
        self.assertEqual(self.window.activeFocusItem(), field)
        self.evaluate('appearancePreset.setInputText(' + json.dumps(json.dumps(self.candidate())) + ')')
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetPreview')
        QTest.keyClick(self.window, Qt.Key_Tab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetClear')
        QTest.keyClick(self.window, Qt.Key_Backtab)
        self.assertEqual(self.window.activeFocusItem().objectName(), 'appearancePresetPreview')

    def test_preview_status_keeps_focused_button_inside_scroll_viewport(self):
        self.initialize()
        self.popup.setProperty('heightBudget', 420)
        self.evaluate('open()', self.popup)
        QTest.qWait(30)
        self.owned_item('appearancePresetJSON').setProperty('checked', True)
        self.evaluate('appearancePreset.setInputText(' + json.dumps(json.dumps(self.candidate())) + ')')
        button = self.owned_item('appearancePresetPreview')
        self.focus(button)
        QTest.keyClick(self.window, Qt.Key_Return)
        QTest.qWait(50)
        viewport = button.parentItem()
        while viewport is not None and viewport.property('contentY') is None:
            viewport = viewport.parentItem()
        self.assertIsNotNone(viewport)
        from PySide6.QtCore import QPointF
        point = button.mapToItem(viewport, QPointF(0, 0))
        self.assertGreaterEqual(point.y(), 0)
        self.assertLessEqual(point.y() + button.height(), viewport.height() + 1)
        self.assertEqual(self.window.activeFocusItem(), button)
        ring = json.loads(self.evaluate("var outline = background.children.find(item => item.visible && item.border && item.border.width === 2); var p = outline.mapToItem(null, 0, 0); JSON.stringify({y:p.y,height:outline.height})", button))
        viewport_top = viewport.mapToScene(QPointF(0, 0)).y()
        self.assertGreaterEqual(ring['y'], viewport_top)
        self.assertLessEqual(ring['y'] + ring['height'], viewport_top + viewport.height() + 1)

    def test_applied_preset_reloads_and_export_contains_no_profile_data(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        before_timer = {key: self.config.property(key) for key in ('timerDeadline', 'timerRemaining', 'timerBreak', 'completedFocus')}
        contexts = self.config.property('contextsJSON')
        data = self.candidate()
        raw = self.evaluate('appearancePreset.exportText')
        for excluded in ('launchers', 'applications:', 'calendarEvents', 'currentDesktopOnly', 'showAudioHud', 'timerDeadline', 'activeProfileId', 'Trabalho', 'contextsJSON'):
            self.assertNotIn(excluded, raw)
        self.preview(data)
        self.assertTrue(self.evaluate('appearancePreset.apply()'))
        saved = self.config.property('profilesJSON')
        self.evaluate('recreateState()')
        state = self.window.findChild(QObject, 'reloadedProfiles')
        self.assertIsNotNone(state)
        reloaded = json.loads(self.evaluate('JSON.stringify(effective)', state))
        self.assertEqual(reloaded['widgets'], data['widgets'])
        self.assertEqual(json.loads(reloaded['appearance']['appearanceJSON']), data['appearance'])
        self.assertEqual(self.config.property('profilesJSON'), saved)
        self.assertEqual(self.config.property('contextsJSON'), contexts)
        for key, value in before_timer.items():
            self.assertEqual(self.config.property(key), value)

    def test_cancel_during_profile_error_clear_blocks_apply_before_any_write(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        self.preview(self.candidate())
        self.assertFalse(self.command('commitPresentation', {'unknown': 'synthetic'}))
        saved = self.config.property('profilesJSON')
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.evaluate("profiles.errorChanged.connect(function handler() { if (profiles.error.length) return; profiles.errorChanged.disconnect(handler); appearancePreset.cancel(); })")
        self.assertFalse(self.evaluate('appearancePreset.apply()'))
        self.assertEqual(writes.count(), 0)
        self.assertEqual(self.config.property('profilesJSON'), saved)
        self.assertFalse(self.evaluate('appearancePreset.hasPreview'))

    def test_cancel_during_profile_error_clear_blocks_undo_before_any_write(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        self.preview(self.candidate())
        self.assertTrue(self.evaluate('appearancePreset.apply()'))
        self.assertFalse(self.command('commitPresentation', {'unknown': 'synthetic'}))
        saved = self.config.property('profilesJSON')
        writes = QSignalSpy(self.config.profilesJSONChanged)
        self.evaluate("profiles.errorChanged.connect(function handler() { if (profiles.error.length) return; profiles.errorChanged.disconnect(handler); appearancePreset.cancel(); })")
        self.assertFalse(self.evaluate('appearancePreset.undo()'))
        self.assertEqual(writes.count(), 0)
        self.assertEqual(self.config.property('profilesJSON'), saved)

    def test_profile_writer_continuation_is_strict_and_preserves_legacy_contract(self):
        self.initialize()
        saved = self.config.property('profilesJSON')
        writes = QSignalSpy(self.config.profilesJSONChanged)
        for callback in ('null', 'false', "'invalid'", '() => false', '() => 1', '() => { throw new Error("synthetic"); }'):
            with self.subTest(callback=callback):
                self.assertFalse(self.evaluate('profiles.commitPresentation({calendarEvents:true},profiles.activeProfileId,profiles.revision,' + callback + ')'))
                self.assertEqual(self.config.property('profilesJSON'), saved)
                self.assertEqual(writes.count(), 0)
        self.assertTrue(self.evaluate('profiles.commitPresentation({calendarEvents:true},profiles.activeProfileId,profiles.revision,() => true)'))
        self.assertEqual(writes.count(), 1)
        self.assertTrue(self.command('select', 'legacy'))
        saved = self.config.property('profilesJSON')
        self.assertFalse(self.evaluate('profiles.commitPresentation({calendarEvents:true},profiles.activeProfileId,profiles.revision,() => true)'))
        self.assertEqual(self.config.property('profilesJSON'), saved)
        self.assertFalse(self.config.property('calendarEvents'))
        self.assertTrue(self.command('commitPresentation', {'calendarEvents': True}))
        self.assertTrue(self.config.property('calendarEvents'))
