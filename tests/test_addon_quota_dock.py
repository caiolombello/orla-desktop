"""Dock routing for quota-usage addons: source takeover, fallback and turn-taking. Synthetic only."""
import json
import unittest

from test_integration_state import IntegrationStateCase
from test_addon_peripherals import peripheral_frame


def quota_frame(enabled=True, reason='ready'):
    addon = dict(id=None, sha256=None, enabled=False, generation=None, producerNamespace=None,
                 reason=reason, errorCode=None)
    if not enabled:
        quota = dict(status='missing', generatedAt=None, source=None, producerVersion=None, limited=False,
                     providers=[], generatedAtMs=None, expiresAtMs=None, leaseMs=None, addon=addon)
    else:
        addon.update(id='org.example.quota', sha256='a' * 64, generation='b' * 32,
                     producerNamespace='synthetic-quota', enabled=True)
        quota = dict(status='ready', generatedAt=100.0, source='addon', producerVersion='0.1.0', limited=True,
            generatedAtMs=100000, expiresAtMs=130000, leaseMs=30000, addon=addon, providers=[
                dict(id='codex', state='ready', observedAt=100.0, observedAtMs=100000, windows=[
                    dict(key='primary', usedPercent=0, windowMinutes=300, resetAtMs=103600000),
                    dict(key='secondary', usedPercent=42, windowMinutes=10080, resetAtMs=None)]),
                dict(id='claude', state='stale', observedAt=99.0, observedAtMs=99000, windows=[
                    dict(key='primary', usedPercent=None, windowMinutes=None, resetAtMs=None)]),
                dict(id='gemini', state='unavailable', observedAt=None, observedAtMs=None, windows=[])])
    return dict(schemaVersion=2, modules=['quota'], quota=quota)


class QuotaDockRoutingTests(IntegrationStateCase):
    ADDONS = 'org.orla.Addons'
    LEGACY = 'org.caiodock.Integrations'

    def setUp(self):
        super().setUp()
        self.evaluate('addonQuotaEnabled = true')

    def routed(self):
        return [(m['service'], m['arguments']) for m in self.calls()]

    def answer(self, service, frame, failed=False):
        self.evaluate(f'reply({json.dumps(json.dumps(frame))}, {str(failed).lower()}, {json.dumps(service)})',
                      self.transport)

    def test_an_active_quota_addon_replaces_the_legacy_quota_read(self):
        self.select(['quota'])
        self.assertCountEqual(self.routed(), [(self.ADDONS, [['quota']]), (self.LEGACY, [['quota']])])
        self.answer(self.ADDONS, quota_frame())
        self.assertTrue(self.state.property('quotaAddonActive'))
        self.assertEqual(self.evaluate('quota.source'), 'addon')
        self.assertEqual(self.evaluate('quota.status'), 'ready')
        windows = json.loads(self.evaluate('JSON.stringify(quota.windows)'))
        self.assertEqual([(w['provider'], w['label'], w['usedPercent'], w['stale']) for w in windows], [
            ('Codex', 'Janela principal (5h)', 0, False), ('Codex', 'Janela secundária (7d)', 42, False),
            ('Claude', 'Janela principal', None, True), ('Gemini', 'Sem leitura', None, False)])
        self.assertEqual(windows[0]['resetAt'], '1970-01-02T04:46:40.000Z')
        self.assertEqual(self.evaluate('quotaSummary'), 'Codex · 42% usado')
        # A late legacy answer no longer reaches the view, and no new legacy quota read starts.
        self.answer(self.LEGACY, {'schemaVersion': 2, 'modules': ['quota'],
                                  'quota': {'status': 'ready', 'windows': [{'provider': 'legacy', 'usedPercent': 99}]}})
        self.assertEqual(self.evaluate('quota.source'), 'addon')
        before = len(self.calls())
        self.evaluate('refresh()')
        self.assertEqual(self.routed()[before:], [(self.ADDONS, [['quota']])])

    def test_without_a_quota_addon_the_legacy_reader_stays_in_charge(self):
        self.select(['quota'])
        self.answer(self.ADDONS, quota_frame(enabled=False))
        self.assertFalse(self.state.property('quotaAddonActive'))
        self.reply(['quota'])
        self.assertEqual(self.evaluate('quota.windows[0].usedPercent'), 42)
        self.assertNotEqual(self.evaluate('quota.source'), 'addon')
        self.evaluate('refresh()')
        self.answer(self.ADDONS, quota_frame(enabled=False, reason='disabled'))
        self.assertFalse(self.state.property('quotaAddonActive'))
        self.assertIn((self.LEGACY, [['quota']]), self.routed())

    def test_failure_after_takeover_never_falls_back_to_private_history(self):
        self.select(['quota'])
        self.answer(self.ADDONS, quota_frame())
        self.answer(self.LEGACY, {'schemaVersion': 2, 'modules': ['quota'], 'quota': {'status': 'ready', 'windows': []}})
        self.evaluate('refresh()')
        self.answer(self.ADDONS, {}, failed=True)
        self.assertTrue(self.state.property('quotaAddonActive'))
        self.assertEqual(self.evaluate('errorFor("quota")'), 'Integração de quota indisponível.')
        self.assertEqual(self.evaluate('quota.windows.length'), 0)
        self.assertNotIn(self.LEGACY, [service for service, _ in self.routed()[2:]])
        # Without the manager's new identity, a different registry is a source change.
        self.evaluate('refresh()')
        disabled = quota_frame(enabled=False, reason='disabled')
        disabled['quota']['addon']['generation'] = 'c' * 32
        self.answer(self.ADDONS, disabled)
        self.assertTrue(self.state.property('quotaAddonActive'))
        self.assertEqual(self.state.property('quotaAddonErrorCode'), 'source_changed')
        # Once the coordinator publishes it, a validated "disabled" hands quota back to the legacy reader.
        self.evaluate('quotaIdentity = ({generation: "%s", sha256: null})' % ('c' * 32))
        self.evaluate('refresh()')
        self.answer(self.ADDONS, disabled)
        self.assertFalse(self.state.property('quotaAddonActive'))
        self.assertIn((self.LEGACY, [['quota']]), self.routed()[-2:])

    def test_battery_and_quota_reads_take_turns_on_the_host(self):
        self.select(['quota', 'peripherals'])
        addon_calls = [args for service, args in self.routed() if service == self.ADDONS]
        self.assertEqual(len(addon_calls), 1)
        first = addon_calls[0]
        if first == [['peripherals']]:
            self.evaluate(f'reply({json.dumps(json.dumps(peripheral_frame()))}, false, "{self.ADDONS}")', self.transport)
        else:
            self.answer(self.ADDONS, quota_frame())
        addon_calls = [args for service, args in self.routed() if service == self.ADDONS]
        self.assertEqual(len(addon_calls), 2)
        self.assertCountEqual(addon_calls, [[['peripherals']], [['quota']]])
        self.assertTrue(self.state.property('addonCallPending'))

    def answer_addons_until_idle(self, limit=6):
        """Answers the single pending addon read at a time; returns how many were answered."""
        answered = 0
        while self.state.property('addonCallPending') and answered < limit:
            last = [args for service, args in self.routed() if service == self.ADDONS][-1]
            frame = peripheral_frame() if last == [['peripherals']] else quota_frame()
            self.evaluate(f'reply({json.dumps(json.dumps(frame))}, false, "{self.ADDONS}")', self.transport)
            answered += 1
        return answered

    def test_a_round_of_turns_ends_instead_of_handing_the_turn_back(self):
        # Native validation caught the two readers restarting each other forever.
        self.select(['quota', 'peripherals'])
        self.assertEqual(self.answer_addons_until_idle(), 2)
        self.assertCountEqual([args for service, args in self.routed() if service == self.ADDONS],
                              [[['peripherals']], [['quota']]])
        # A periodic refresh runs exactly one more round.
        self.evaluate('refresh()')
        self.assertEqual(self.answer_addons_until_idle(), 2)
        self.assertEqual(len([1 for service, _ in self.routed() if service == self.ADDONS]), 4)

    def answer_round(self, percent):
        """Answers one round in the order the host received it; returns that order."""
        order = []
        while self.state.property('addonCallPending') and len(order) < 3:
            last = [args for service, args in self.routed() if service == self.ADDONS][-1]
            order.append(last[0][0])
            frame = peripheral_frame(percent=percent) if last == [['peripherals']] else quota_frame()
            self.evaluate(f'reply({json.dumps(json.dumps(frame))}, false, "{self.ADDONS}")', self.transport)
        return order

    def test_the_reader_that_hands_over_its_turn_keeps_its_own_result(self):
        # Installed dock: the waiting reader started inside the first one's settlement,
        # and the first then dropped its validated result as if it had lost admission.
        self.select(['quota', 'peripherals'])
        self.assertEqual(self.answer_round(70), ['quota', 'peripherals'])
        self.assertTrue(self.state.property('quotaAddonActive'))
        self.assertEqual(self.evaluate('quota.source'), 'addon')
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)
        self.evaluate('refresh()')
        self.assertEqual(self.answer_round(60), ['peripherals', 'quota'])
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 60)
        self.assertEqual(self.evaluate('quota.source'), 'addon')

    def test_opt_out_fixture_keeps_the_legacy_only_route(self):
        self.evaluate('addonQuotaEnabled = false')
        self.select(['quota'])
        self.assertEqual(self.routed(), [(self.LEGACY, [['quota']])])

    def test_opting_out_after_takeover_restores_the_legacy_reader(self):
        self.select(['quota'])
        self.answer(self.ADDONS, quota_frame())
        # Settle the legacy read that was already in flight; the legacy reader runs one at a time.
        self.answer(self.LEGACY, {'schemaVersion': 2, 'modules': ['quota'], 'quota': {'status': 'ready', 'windows': []}})
        before = len(self.calls())
        self.evaluate('addonQuotaEnabled = false')
        self.assertFalse(self.state.property('quotaAddonActive'))
        self.assertEqual(self.routed()[before:], [(self.LEGACY, [['quota']])])
        self.assertNotEqual(self.evaluate('quota.source'), 'addon')



import test_addon_manager_state as manager_tests
from test_addon_manager_state import manifest as manager_manifest, GEN, SHA, OTHER


class QuotaManagerListingTests(unittest.TestCase):
    """Reuses the manager harness helpers; only listing rules for two modules are new here."""
    setUpClass = classmethod(manager_tests.AddonManagerStateTests.setUpClass.__func__)
    setUp = manager_tests.AddonManagerStateTests.setUp
    tearDown = manager_tests.AddonManagerStateTests.tearDown
    js = manager_tests.AddonManagerStateTests.js
    data = manager_tests.AddonManagerStateTests.data
    reply = manager_tests.AddonManagerStateTests.reply
    activate = manager_tests.AddonManagerStateTests.activate

    def quota_manifest(self, addon_id='org.example.quota'):
        return manager_manifest(id=addon_id, name='Quota local', renderer='quota-usage',
                                source=dict(namespace='quota-example', formatVersion='0.1-experimental'))

    def rows(self):
        return self.data('state.addons.map(row => [row.id, row.renderer, row.enabled])')

    def test_battery_and_quota_can_both_be_active(self):
        self.activate(dict(generation=GEN, addons=[
            dict(manifest=manager_manifest(), sha256=SHA, previousSha256=None, enabled=True),
            dict(manifest=self.quota_manifest(), sha256=OTHER, previousSha256=None, enabled=True)]))
        self.assertTrue(self.js('state.valid'))
        self.assertEqual(self.rows(), [['org.example.battery', 'peripheral-battery', True],
                                       ['org.example.quota', 'quota-usage', True]])

    def test_two_active_addons_of_one_module_are_refused(self):
        self.activate(dict(generation=GEN, addons=[
            dict(manifest=self.quota_manifest(), sha256=SHA, previousSha256=None, enabled=True),
            dict(manifest=self.quota_manifest('org.example.quota-two'), sha256=OTHER, previousSha256=None, enabled=True)]))
        self.assertFalse(self.js('state.valid'))
        self.assertEqual(self.rows(), [])

    def test_unknown_renderer_is_not_listed(self):
        self.activate(dict(generation=GEN, addons=[
            dict(manifest=manager_manifest(renderer='cost-usage'), sha256=SHA, previousSha256=None, enabled=False)]))
        self.assertFalse(self.js('state.valid'))


import test_addon_manager as manager_view
from PySide6.QtTest import QTest


class QuotaManagerCardTests(unittest.TestCase):
    """Presentation only: copy and availability follow each addon's module."""
    setUpClass = classmethod(manager_view.AddonManagerTests.setUpClass.__func__)
    setUp = manager_view.AddonManagerTests.setUp
    tearDown = manager_view.AddonManagerTests.tearDown
    control = manager_view.AddonManagerTests.control

    def test_an_active_battery_addon_does_not_block_a_quota_addon(self):
        battery = manager_view.package(enabled=True, renderer='peripheral-battery')
        quota = manager_view.package(id='org.example.quota', sha256='c' * 64, name='Quota local',
                                     renderer='quota-usage')
        other = manager_view.package(id='org.example.quota-two', sha256='d' * 64, renderer='quota-usage')
        self.manager.setProperty('addons', [battery, quota])
        QTest.qWait(40)
        self.assertTrue(self.control('addonEnable-org.example.quota').isEnabled())
        self.assertIn('Ative para permitir', self.control('addonGuidance-org.example.quota').property('text'))
        quota['enabled'] = True
        self.manager.setProperty('addons', [battery, quota, other])
        self.manager.setProperty('profileQuotaVisible', False)
        QTest.qWait(40)
        self.assertFalse(self.control('addonEnable-org.example.quota-two').isEnabled())
        self.assertIn('outro complemento de quota', self.control('addonGuidance-org.example.quota-two').property('text'))
        self.assertIn('QuotaLantern neste perfil', self.control('addonGuidance-org.example.quota').property('text'))
        self.assertNotIn('Periféricos', self.control('addonGuidance-org.example.quota').property('text'))

    def test_quota_preview_states_its_own_read_only_permission(self):
        self.manager.setProperty('preview', manager_view.package(id='org.example.quota', sha256='c' * 64,
                                                                  renderer='quota-usage'))
        QTest.qWait(40)
        text = self.control('addonPreviewPermission').property('text')
        self.assertIn('uso de quota de IA', text)
        self.assertIn('sem contas nem custos', text)
        self.assertIn('Instalar não ativa a leitura', text)


import test_addon_composition as composition


class QuotaCoordinatorIdentityTests(unittest.TestCase):
    """Actual manager, coordinator and data state: one identity pin per module."""
    setUpClass = classmethod(composition.AddonCompositionTests.setUpClass.__func__)
    setUp = composition.AddonCompositionTests.setUp
    tearDown = composition.AddonCompositionTests.tearDown
    js = composition.AddonCompositionTests.js
    value = composition.AddonCompositionTests.value
    reply = composition.AddonCompositionTests.reply
    metadata = composition.AddonCompositionTests.metadata

    def test_listing_pins_battery_and_quota_identities_separately(self):
        battery = self.metadata()['result']['addons'][0]
        quota = json.loads(json.dumps(battery))
        quota['manifest'].update(id='org.example.quota', renderer='quota-usage',
                                 source=dict(namespace='synthetic-quota', formatVersion='0.1-experimental'))
        quota['sha256'] = 'e' * 64
        self.reply(0, peripheral_frame())
        self.js('surfaceOpen = true')
        QTest.qWait(5)
        self.reply(1, self.metadata(addons=[battery, quota]))
        self.assertTrue(self.js('manager.valid'))
        self.assertEqual(self.value('data.addonIdentity'), dict(generation='b' * 32, sha256='a' * 64))
        self.assertEqual(self.value('data.quotaIdentity'), dict(generation='b' * 32, sha256='e' * 64))
        quota['enabled'] = False
        self.js("manager.refresh()")
        QTest.qWait(5)
        self.reply(2, self.metadata(generation='c' * 32, addons=[battery, quota]))
        self.assertEqual(self.value('data.quotaIdentity'), dict(generation='c' * 32, sha256=None))


if __name__ == '__main__':
    unittest.main()
