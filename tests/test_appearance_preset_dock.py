"""Additional local KDE Dock wiring; portable CI uses test_appearance_preset."""
import json
import unittest
import test_profiles_dock as fixtures
import test_appearance_preset as portable

class AppearancePresetDockTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.ProfilesDockTests.setUpClass.__func__)
    setUp = fixtures.ProfilesDockTests.setUp
    tearDown = fixtures.ProfilesDockTests.tearDown
    dispose = fixtures.ProfilesDockTests.dispose
    evaluate = fixtures.ProfilesDockTests.evaluate
    command = fixtures.ProfilesDockTests.command
    initialize = fixtures.ProfilesDockTests.initialize
    owned_item = fixtures.ProfilesDockTests.owned_item
    focus = fixtures.ProfilesDockTests.focus
    settle = fixtures.ProfilesDockTests.settle
    flat = fixtures.ProfilesDockTests.flat
    open_catalog = portable.AppearancePresetTests.open_catalog
    exported = portable.AppearancePresetTests.exported
    candidate = portable.AppearancePresetTests.candidate
    preview = portable.AppearancePresetTests.preview
    test_combined_preview_apply_undo_preserves_other_data_and_writes_once = portable.AppearancePresetTests.test_combined_preview_apply_undo_preserves_other_data_and_writes_once
    test_keyboard_import_apply_and_escape_cancel_fit_420_pixels = portable.AppearancePresetTests.test_keyboard_import_apply_and_escape_cancel_fit_420_pixels

    test_preview_status_keeps_focused_button_inside_scroll_viewport = portable.AppearancePresetTests.test_preview_status_keeps_focused_button_inside_scroll_viewport

    test_collapsed_catalog_skips_choices_and_space_enters_first_choice = portable.AppearancePresetTests.test_collapsed_catalog_skips_choices_and_space_enters_first_choice

    test_successful_preview_can_collapse_from_child_with_visible_status_and_focus = portable.AppearancePresetTests.test_successful_preview_can_collapse_from_child_with_visible_status_and_focus

    test_pending_invalid_portable_input_reveals_both_sections_and_cancel_resets = portable.AppearancePresetTests.test_pending_invalid_portable_input_reveals_both_sections_and_cancel_resets

    test_catalog_tab_backtab_return_and_escape_keep_focus_visible_without_writes = portable.AppearancePresetTests.test_catalog_tab_backtab_return_and_escape_keep_focus_visible_without_writes

    def test_widget_strip_and_open_guard_follow_temporary_visibility(self):
        self.initialize()
        self.evaluate('appearance.begin()')
        data = self.candidate()
        for widget in data['widgets']:
            widget['visible'] = False
        saved = self.config.property('profilesJSON')
        self.preview(data)
        strip = self.owned_item('widgetStrip')
        self.assertFalse(strip.isVisible())
        self.assertFalse(self.evaluate("widgetVisible('clock')"))
        self.assertFalse(self.evaluate("openWidget('clock',this)"))
        self.evaluate('appearancePreset.cancel()')
        self.assertTrue(strip.isVisible())
        self.assertTrue(self.evaluate("widgetVisible('clock')"))
        self.assertEqual(self.config.property('profilesJSON'), saved)
