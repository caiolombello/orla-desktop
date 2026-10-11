import json
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Fusion')

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression


ROOT = Path(__file__).resolve().parents[1]


class PeripheralsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    def setUp(self):
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend(value.toString() for value in values))
        self.engine.load(QUrl.fromLocalFile(str(ROOT / 'tests/IntegrationHarness.qml')))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.integration = self.engine.rootObjects()[0]
        self.details = self.integration.findChild(QObject, 'peripheralsDetailsUnderTest')
        self.assertIsNotNone(self.details)

    def tearDown(self):
        self.engine.deleteLater()
        self.app.processEvents()

    def accept(self, peripherals):
        value = {'schemaVersion': 1, 'quota': {'status': 'missing', 'windows': [], 'costs': []},
                 'peripherals': peripherals, 'recording': {'status': 'missing', 'state': 'unknown'}}
        expression = QQmlExpression(self.engine.rootContext(), self.integration,
                                    'acceptSnapshot(' + json.dumps(json.dumps(value)) + ')')
        accepted, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.assertTrue(accepted)
        self.app.processEvents()

    def test_summary_distinguishes_absent_stale_unknown_and_missing_cache(self):
        cases = (
            ({'status': 'unknown', 'devices': [{'name': 'Mouse', 'present': False, 'stale': True, 'percent': None}]},
             'Mouse · fora de alcance'),
            ({'status': 'stale', 'devices': [{'name': 'Mouse', 'present': True, 'stale': True, 'percent': None}]},
             'Dados desatualizados'),
            ({'status': 'unknown', 'devices': [{'name': 'Mouse', 'present': True, 'stale': False, 'percent': None}]},
             'Percentual desconhecido'),
            ({'status': 'missing', 'devices': []}, 'Sem cache local'),
        )
        for peripherals, expected in cases:
            with self.subTest(expected=expected):
                self.accept(peripherals)
                self.assertEqual(self.integration.property('batterySummary'), expected)

    def test_details_show_origin_limit_and_cache_only_refresh(self):
        self.accept({'status': 'ready', 'generatedAt': 1791658800.0, 'source': 'oneshot',
                     'producerVersion': '0.1.0-alpha.3', 'limited': True,
                     'devices': [{'name': 'Mouse', 'present': True, 'stale': False, 'percent': 0, 'estimated': True}]})
        metadata = self.details.findChild(QObject, 'peripheralsMetadata')
        button = self.details.findChild(QObject, 'refreshCacheButton')
        self.assertIsNotNone(metadata)
        self.assertIsNotNone(button)
        self.assertIn('coleta pontual', metadata.property('text'))
        self.assertIn('modelo limitado', metadata.property('text'))
        self.assertEqual(button.property('text'), 'Reler cache local')
        expression = QQmlExpression(self.engine.rootContext(), self.details,
                                    "stateText({present: true, stale: false, percent: 0, estimated: true})")
        state, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.assertEqual(state, '0% · estimativa')

    def test_legacy_snapshot_remains_usable_without_new_metadata(self):
        self.accept({'status': 'ready', 'devices': [{'name': 'Teclado', 'stale': False, 'percent': 64}]})
        self.assertEqual(self.integration.property('batterySummary'), 'Teclado · 64%')
        self.assertEqual(self.details.findChild(QObject, 'peripheralsMetadata').property('visible'), False)


if __name__ == '__main__':
    unittest.main()
