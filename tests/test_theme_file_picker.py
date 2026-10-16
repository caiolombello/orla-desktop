"""Portable Qt Quick picker/editor behavior; signals are simulated, never Native input."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlEngine, QQmlExpression

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


class ThemeFilePickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        cls.fixture_area = tempfile.TemporaryDirectory(prefix="orla-picker-tests-")
        cls.fixture = Path(cls.fixture_area.name)
        # Copy installed-app source controls into an owned, portable fixture.
        # No production file is written, and no integration/DBus transport is instantiated.
        shutil.copytree(ROOT / "package/contents", cls.fixture / "source")
        for name in ("ThemeFilePickerHarness.qml", "ThemeFileEditorHarness.qml"):
            shutil.copyfile(HERE / name, cls.fixture / name)
        cls.theme = json.loads(next((ROOT / "themes/examples").glob("*.json")).read_text())
        cls.synthetic_file = cls.fixture / "Maré ?#%23.json"
        cls.synthetic_file.write_text(json.dumps(cls.theme), encoding="utf-8")
        cls.response = json.dumps({"formatVersion": "0.1-experimental", "valid": True, "theme": cls.theme})

    @classmethod
    def tearDownClass(cls):
        cls.fixture_area.cleanup()

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(v.toString() for v in values))
        self.window = None

    def load(self, name="ThemeFilePickerHarness.qml"):
        self.engine.load(QUrl.fromLocalFile(str(self.fixture / name)))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.app.processEvents()

    def evaluate(self, source, target=None):
        expression = QQmlExpression(QQmlEngine.contextForObject(target or self.window), target or self.window, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value.toVariant() if hasattr(value, "toVariant") else value

    def tearDown(self):
        if self.window is not None:
            if self.window.findChild(QObject, "fixtureThemeFilePicker") is not None:
                self.evaluate("shutdown()")
            else:
                self.evaluate("appearance.cancel()")
            self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def accepted(self):
        # Public dialog selectedFile + accepted signal, deliberately not native chooser automation.
        url = QUrl.fromLocalFile(str(self.synthetic_file))
        self.evaluate("picker.chooser.selectedFile=" + json.dumps(url.toString()) + ";picker.chooser.accepted()")
        return url.toString(QUrl.ComponentFormattingOption.FullyEncoded)

    def test_default_does_not_dispatch_open_is_selecting_and_window_modal(self):
        self.load()
        self.assertFalse(self.evaluate("picker.visible || appearance.busy"))
        self.assertEqual(self.evaluate("transport.requests.length"), 0)
        self.assertTrue(self.evaluate("picker.open()"))
        self.assertTrue(self.evaluate("appearance.themeFileSelecting && appearance.busy && !appearance.canApply"))
        self.assertTrue(self.evaluate("picker.chooser.parentWindow === selectedWindow"))
        self.assertTrue(self.evaluate("picker.chooser.modality === Qt.WindowModal"))
        self.assertTrue(self.evaluate("picker.chooser.fileMode === Dialogs.FileDialog.OpenFile"))
        self.assertEqual(self.evaluate("transport.requests.length"), 0)
        self.assertEqual(self.evaluate("configuration.writes"), 0)

    def test_accepted_dispatches_encoded_url_once_and_rejection_revokes_late_reply(self):
        self.load()
        self.assertTrue(self.evaluate("picker.open()"))
        expected_url = self.accepted()
        self.assertTrue(self.evaluate("appearance.themeFileLoading"))
        self.assertEqual(self.evaluate("transport.requests.length"), 1)
        self.assertEqual(self.evaluate("transport.requests[0].url"), expected_url)
        self.evaluate("picker.chooser.accepted()")
        self.assertEqual(self.evaluate("transport.requests.length"), 1)
        self.evaluate("picker.chooser.rejected()")
        self.assertFalse(self.evaluate("appearance.busy || picker.visible"))
        before = self.evaluate("snapshot()")
        self.evaluate("transport.succeed(0," + json.dumps(self.response) + ");transport.fail(0)")
        self.assertEqual(self.evaluate("snapshot()"), before)
        self.assertEqual(self.evaluate("configuration.writes"), 0)

    def test_picker_reject_or_lifecycle_change_retires_own_intent_only(self):
        self.load()
        mutations = ("picker.chooser.rejected()", "selectionActive=false",
                     "selectedWindow=otherWindow", "selectedAppearance=otherAppearance")
        for mutation in mutations:
            for loading in (False, True):
                with self.subTest(mutation=mutation, loading=loading):
                    self.evaluate("picker.cancelSelection();appearance.cancel();appearance.begin();"
                                  "otherAppearance.cancel();otherAppearance.begin();"
                                  "selectionActive=true;selectedWindow=this;selectedAppearance=appearance")
                    self.assertTrue(self.evaluate("picker.open()"))
                    if loading:
                        self.accepted()
                        index = self.evaluate("transport.requests.length-1")
                    self.evaluate(mutation)
                    self.assertTrue(self.evaluate("picker.selectionState===null && picker.selectionToken===null"))
                    self.assertFalse(self.evaluate("appearance.busy || otherAppearance.busy || picker.visible"))
                    before = self.evaluate("snapshot()")
                    self.evaluate("picker.chooser.accepted()")
                    if loading:
                        self.evaluate("transport.succeed(" + str(index) + "," + json.dumps(self.response) + ");transport.fail(" + str(index) + ")")
                    self.assertEqual(self.evaluate("snapshot()"), before)
                    self.assertEqual(self.evaluate("configuration.writes"), 0)

    def test_picker_cancellation_cannot_cancel_newer_selection_owned_elsewhere(self):
        self.load()
        self.assertTrue(self.evaluate("picker.open()"))
        self.evaluate("claimNewerSelection()")
        self.assertTrue(self.evaluate("foreignToken!==null && appearance.themeFileSelecting"))
        self.evaluate("picker.cancelSelection();picker.chooser.rejected();picker.chooser.accepted()")
        self.assertTrue(self.evaluate("appearance.themeFileSelecting"))
        self.assertEqual(self.evaluate("transport.requests.length"), 0)
        self.assertTrue(self.evaluate("appearance.cancelThemeFileSelection(foreignToken)"))
        self.assertFalse(self.evaluate("appearance.busy"))

    def test_editor_import_button_owns_window_and_hiding_editor_cancels_selection(self):
        self.load("ThemeFileEditorHarness.qml")
        self.evaluate("editor.advancedOpen=true;editor.themeOpen=true")
        button = self.window.findChild(QObject, "appearanceThemeFileImport")
        dialog = self.window.findChild(QObject, "appearanceThemeFileDialog")
        self.assertIsNotNone(button)
        self.assertIsNotNone(dialog)
        self.evaluate("options=Dialogs.FileDialog.DontUseNativeDialog", dialog)
        dialog.setProperty("currentFolder", QUrl.fromLocalFile(str(self.fixture)))
        self.assertTrue(button.property("enabled"))
        button.clicked.emit()  # Portable public signal, not a physical/native click claim.
        self.assertTrue(self.evaluate("appearance.themeFileSelecting"))
        self.assertEqual(dialog.property("parentWindow"), self.window)
        self.assertFalse(button.property("enabled"))
        self.evaluate("editor.visible=false")
        self.assertFalse(self.evaluate("appearance.busy"))
        self.assertFalse(dialog.property("visible"))
        url = QUrl.fromLocalFile(str(self.synthetic_file))
        self.evaluate("selectedFile=" + json.dumps(url.toString()) + ";accepted()", dialog)
        self.assertEqual(self.evaluate("transport.calls"), 0)
        self.assertEqual(self.evaluate("configuration.writes"), 0)


if __name__ == "__main__":
    unittest.main()
