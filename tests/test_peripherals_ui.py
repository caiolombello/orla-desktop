import json
import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QUICK_BACKEND', 'software')
os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Fusion')

from PySide6.QtCore import QObject, QUrl, QCoreApplication, QEvent
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
        QCoreApplication.sendPostedEvents(self.engine, QEvent.DeferredDelete)
        self.app.processEvents()
        self.assertEqual(self.warnings, [])

    def evaluate(self, source, target=None):
        expression = QQmlExpression(self.engine.rootContext(), target or self.integration, source)
        value, _ = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        self.app.processEvents()
        return value

    def accept(self, frame):
        self.evaluate('enabledModules=["peripherals"]; active=true; refresh()')
        transport = self.integration.findChild(QObject, 'fixtureTransport')
        self.evaluate('reply(' + json.dumps(json.dumps(frame)) + ')', transport)

    def test_summary_distinguishes_absent_stale_unknown_and_missing_export(self):
        from test_addon_peripherals import peripheral_frame, missing_frame
        cases = (
            # Disconnected devices are hidden (user request), so none is left to describe.
            (peripheral_frame(present=False), 'Nenhum periférico conectado'),
            (peripheral_frame(stale=True), 'Dados desatualizados'),
            (peripheral_frame(percent=None), 'Percentual desconhecido'),
            (missing_frame(), 'Sem cache local'),
        )
        for frame, expected in cases:
            with self.subTest(expected=expected):
                self.evaluate('invalidateAddons()')
                self.accept(frame)
                self.assertEqual(self.integration.property('batterySummary'), expected)

    def test_details_show_generic_origin_limit_zero_estimate_and_cache_only_refresh(self):
        from test_addon_peripherals import peripheral_frame
        frame = peripheral_frame(percent=0, estimated=True)
        frame['peripherals']['limited'] = True
        self.accept(frame)
        metadata = self.details.findChild(QObject, 'peripheralsMetadata')
        button = self.details.findChild(QObject, 'refreshCacheButton')
        self.assertIsNotNone(metadata)
        self.assertIsNotNone(button)
        self.assertIn('exportação local', metadata.property('text'))
        self.assertNotIn('PeriGauge', metadata.property('text'))
        self.assertIn('modelo limitado', metadata.property('text'))
        self.assertEqual(button.property('text'), 'Reler cache local')
        self.assertEqual(self.evaluate('stateText(integrations.peripherals.devices[0])', self.details), '0% · estimativa')

    def test_old_private_projection_cannot_bypass_addon_validation(self):
        self.accept({'schemaVersion': 2, 'modules': ['peripherals'],
            'peripherals': {'status': 'ready', 'devices': [{'name': 'PRIVATE-SENTINEL', 'percent': 64}]}})
        self.assertEqual(self.integration.property('addonErrorCode'), 'invalid_response')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.assertEqual(self.details.findChild(QObject, 'peripheralsMetadata').property('visible'), False)

    def test_coarse_charging_components_and_stale_values_use_only_lease_gated_projection(self):
        from test_addon_peripherals import peripheral_frame
        frame = peripheral_frame(percent=None, level='low', charging='charging', estimated=True,
            components=[dict(label='left', percent=0, charging='charging'),
                        dict(label='right', percent=75, charging='discharging')])
        self.accept(frame)
        self.assertEqual(self.evaluate('stateText(integrations.peripherals.devices[0])', self.details),
            'Nível baixo · estimativa · carregando')
        components = json.loads(self.evaluate("JSON.stringify((function collect(item) { let result = item.objectName === 'peripheralComponent' ? [item.text] : []; for (const child of item.children) result = result.concat(collect(child)); return result; })(this))", self.details))
        self.assertEqual(set(components),
            {'Esquerdo · 0% · carregando', 'Direito · 75%'})
        self.assertFalse(self.details.findChild(QObject, 'legacyProjectLink').property('visible'))
        self.assertNotIn('PeriGauge', self.details.findChild(QObject, 'integrationDescription').property('text'))
        self.evaluate('nowMsOverride=130000')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.assertIn('Dados desatualizados', self.details.findChild(QObject, 'integrationEmptyState').property('text'))
        self.assertEqual(json.loads(self.evaluate("JSON.stringify((function collect(item) { let result = item.objectName === 'peripheralComponent' ? [item.text] : []; for (const child of item.children) result = result.concat(collect(child)); return result; })(this))", self.details)), [])



if __name__ == '__main__':
    unittest.main()
