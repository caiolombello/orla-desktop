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


import test_peripherals_ui as details_ui
from PySide6.QtCore import QObject


class QuotaDetailsTests(unittest.TestCase):
    """The quota popup follows the battery one once quota comes from an addon."""
    setUpClass = classmethod(details_ui.PeripheralsUiTests.setUpClass.__func__)
    setUp = details_ui.PeripheralsUiTests.setUp
    tearDown = details_ui.PeripheralsUiTests.tearDown
    evaluate = details_ui.PeripheralsUiTests.evaluate

    def quota_details(self):
        details = self.integration.findChild(QObject, 'quotaDetailsUnderTest')
        self.assertIsNotNone(details)
        return details

    def part(self, name):
        part = self.quota_details().findChild(QObject, name)
        self.assertIsNotNone(part, name)
        return part

    def answer_addon(self, frame):
        self.evaluate('addonQuotaEnabled = true; enabledModules = ["quota"]; active = true')
        transport = self.integration.findChild(QObject, 'fixtureTransport')
        self.evaluate('reply(%s, "org.orla.Addons")' % json.dumps(json.dumps(frame)), transport)

    def grouped(self, expression):
        """Evaluate on the grouped quota view inside QML; only JSON comes back to Python."""
        source = ("(function() { const find = item => { if (item.objectName === 'quotaUsage') return item;"
                  " for (let i = 0; i < item.children.length; ++i) { const f = find(item.children[i]); if (f) return f; }"
                  " return null; }; let u = null; for (let i = 0; i < children.length && !u; ++i) u = find(children[i]);"
                  " return JSON.stringify(u ? (%s) : null); })()" % expression)
        return json.loads(self.evaluate(source, self.quota_details()))

    def test_addon_quota_is_grouped_like_the_tray_menu(self):
        frame = quota_frame()
        H, D, now = 3600000, 86400000, 100000
        def ready(pid, windows):
            return dict(id=pid, state='ready', observedAt=now / 1000, observedAtMs=now, windows=windows)
        frame['quota']['providers'] = [
            ready('codex', [dict(key='primary', usedPercent=12, windowMinutes=300, resetAtMs=now + 4 * H + 600000),
                            dict(key='secondary', usedPercent=42, windowMinutes=10080, resetAtMs=now + 2 * D + 5 * H)]),
            ready('claude', [dict(key='primary', usedPercent=96, windowMinutes=300, resetAtMs=now + H + 1200000)]),
            ready('opencode-go', [dict(key='primary', usedPercent=78, windowMinutes=None, resetAtMs=None)]),
            dict(id='grok', state='stale', observedAt=0.05, observedAtMs=50, windows=[
                dict(key='primary', usedPercent=None, windowMinutes=None, resetAtMs=None)]),
            dict(id='gemini', state='unavailable', observedAt=None, observedAtMs=None, windows=[])]
        self.answer_addon(frame)
        self.assertTrue(self.integration.property('quotaAddonActive'))
        # Sections in the tray's order, the most used first inside each one.
        self.assertEqual(self.grouped("u.view.sections.map(s => [s.key, s.providers.map(p => p.name)])"), [
            ['limit', ['Claude']], ['active', ['OpenCode Go', 'Codex']], ['stale', ['Grok']], ['offline', ['Gemini']]])
        bottleneck = self.grouped("[u.view.bottleneck.provider.name, u.windowName(u.view.bottleneck.window),"
                                  " u.resetText(u.view.bottleneck.window)]")
        self.assertEqual(bottleneck, ['Claude', 'Sessão · 5 h', 'zera em 1 h 20 min'])
        codex = "u.view.sections[1].providers[1]"
        self.assertEqual(self.grouped(f"{codex}.windows.map(w => u.windowName(w) + ' ' + u.resetText(w))"),
                         ['Sessão · 5 h zera em 4 h 10 min', 'Semana · 7 d zera em 2 d 5 h'])
        self.assertEqual(self.grouped("u.view.sections.map(s => s.providers.map(p => u.stateText(p)))"),
                         [['96%'], ['78%', '42%'], ['sem leitura recente'], ['não conectado']])
        self.assertTrue(self.evaluate("groupedQuota", self.quota_details()))

    def test_legacy_quota_keeps_the_flat_list(self):
        self.evaluate('enabledModules = ["quota"]; active = true')
        self.assertFalse(self.evaluate("groupedQuota", self.quota_details()))

    def test_legacy_quota_keeps_the_project_and_cache_wording(self):
        self.evaluate('enabledModules = ["quota"]; active = true')
        self.assertIn('QuotaLantern', self.part('integrationDescription').property('text'))
        self.assertTrue(self.part('legacyProjectLink').property('visible'))
        self.assertFalse(self.part('quotaMetadata').property('visible'))
        self.assertEqual(self.part('refreshCacheButton').property('text'), 'Reler cache local')

    def test_addon_quota_shows_origin_and_time_without_naming_or_linking_a_project(self):
        self.answer_addon(quota_frame())
        self.assertTrue(self.integration.property('quotaAddonActive'))
        self.assertNotIn('QuotaLantern', self.part('integrationDescription').property('text'))
        metadata = self.part('quotaMetadata')
        self.assertTrue(metadata.property('visible'))
        self.assertIn('exportação local', metadata.property('text'))
        self.assertIn('atualizado em', metadata.property('text'))
        self.assertFalse(self.part('legacyProjectLink').property('visible'))

    def test_addon_quota_without_shared_data_points_to_the_sharing_permission(self):
        frame = quota_frame()
        frame['quota'].update(status='missing', generatedAt=None, source=None, producerVersion=None, limited=False,
                              providers=[], generatedAtMs=None, expiresAtMs=None, leaseMs=None)
        frame['quota']['addon']['reason'] = 'export_missing'
        self.answer_addon(frame)
        self.assertTrue(self.integration.property('quotaAddonActive'))
        self.assertIn('permissão no aplicativo de origem', self.part('integrationEmptyState').property('text'))
        # Installed dock: "exportação local" stayed visible with nothing shared.
        self.assertFalse(self.part('quotaMetadata').property('visible'))

    def test_addon_quota_changed_outside_settings_offers_the_reload(self):
        self.answer_addon(quota_frame())
        session = self.integration.findChild(QObject, 'sessionFixture')
        session.setProperty('reloadRequired', True)
        button = self.part('refreshCacheButton')
        self.assertEqual(button.property('text'), 'Recarregar complementos')
        self.assertTrue(self.part('addonReloadGuidance').property('visible'))
        self.evaluate('clicked()', button)
        self.assertEqual(session.property('reloads'), 1)


if __name__ == '__main__':
    unittest.main()
