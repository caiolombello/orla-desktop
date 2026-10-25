"""Actual addon wire shape through fake async transport and public QML properties."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
from PySide6.QtTest import QTest
from PySide6.QtQml import QQmlExpression
from test_integration_state import IntegrationStateCase


def peripheral_frame(generated=100000, observed=100000, percent=70, **device_changes):
    device = dict(name='mouse', kind='mouse', percent=percent, level=None, charging='discharging',
        estimated=False, stale=False, present=True, observedAt=None if observed is None else observed/1000,
        observedAtMs=observed, components=[])
    device.update(device_changes)
    return dict(schemaVersion=2, modules=['peripherals'], peripherals=dict(status='ready',
        generatedAt=generated/1000, source='addon', producerVersion='0.1.0', limited=False,
        devices=[device], generatedAtMs=generated, expiresAtMs=generated+30000, leaseMs=30000,
        addon=dict(id='org.example.battery', sha256='a'*64, enabled=True, generation='b'*32,
            producerNamespace='synthetic-battery', reason='ready', errorCode=None)))


def missing_frame():
    return dict(schemaVersion=2, modules=['peripherals'], peripherals=dict(status='missing',
        generatedAt=None, source=None, producerVersion=None, limited=False, devices=[],
        generatedAtMs=None, expiresAtMs=None, leaseMs=None,
        addon=dict(id=None, sha256=None, enabled=False, generation=None,
            producerNamespace=None, reason='not_installed', errorCode=None)))


class AddonPeripheralsTests(IntegrationStateCase):
    def addon_reply(self, frame=None, failed=False):
        text = json.dumps(peripheral_frame() if frame is None else frame)
        self.evaluate(f'reply({json.dumps(text)}, {str(failed).lower()}, "org.orla.Addons")', self.transport)

    def raw_reply(self, text):
        self.evaluate(f'reply({json.dumps(text)}, false, "org.orla.Addons")', self.transport)

    def test_legacy_failure_or_stall_cannot_suppress_addon_and_reverse(self):
        self.select(['quota', 'peripherals', 'recording'])
        self.addon_reply()
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)
        self.assertEqual(self.state.property('batterySummary'), 'Mouse · 70%')
        self.assertTrue(self.state.property('legacyLoading'))
        self.reply(['quota', 'recording'], failed=True)
        self.assertTrue(self.state.property('legacyError'))
        self.assertEqual(self.state.property('error'), '')
        self.assertEqual(self.evaluate('errorFor("peripherals")'), '')
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)
        self.evaluate('refresh()')
        self.reply(['quota', 'recording'])
        self.assertTrue(self.state.property('addonLoading'))
        self.addon_reply(failed=True)
        self.assertEqual(self.state.property('quotaSummary'), 'fixture · 42% usado')
        self.assertEqual(self.state.property('error'), '')
        self.assertEqual(self.evaluate('errorFor("quota")'), '')
        self.assertTrue(self.evaluate('errorFor("peripherals")'))
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_profile_aba_detaches_stalled_flight_and_ignores_old_duplicate_callbacks(self):
        self.select(['peripherals'])
        self.select(['peripherals'], False)
        self.assertEqual(self.evaluate('peripherals.status'), 'disabled')
        self.select(['peripherals'])
        self.assertEqual(len(self.calls()), 2)
        self.addon_reply()  # First generation, still in the fake transport queue.
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.assertTrue(self.state.property('addonLoading'))
        self.evaluate('replay({value:lastText})', self.transport)
        self.assertTrue(self.state.property('addonLoading'))
        self.addon_reply(peripheral_frame(percent=0))
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)
        self.assertFalse(self.state.property('addonLoading'))

    def test_queued_aba_dispatches_only_current_generation(self):
        self.evaluate('enabledModules=["peripherals"]; active=true; active=false; active=true; invalidateAddons(); invalidateAddons()')
        self.assertEqual(len(self.calls()), 1)
        self.addon_reply()
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)

    def test_host_mutation_suspends_before_dispatch_and_revokes_visible_and_pending_data(self):
        self.root.setProperty('suspendOnAddonLoading', True)
        self.select(['peripherals'])
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertFalse(self.state.property('addonLoading'))
        self.root.setProperty('suspendOnAddonLoading', False)
        self.evaluate('addonSuspended=false')
        self.addon_reply()
        self.evaluate('refresh()')
        self.evaluate('addonSuspended=true; invalidateAddons(); refresh()')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        count = len(self.calls())
        self.addon_reply()
        self.assertEqual(len(self.calls()), count)
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.evaluate('addonSuspended=false')
        self.assertEqual(len(self.calls()), count+1)
        self.addon_reply()
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)
        self.assertTrue(all(m['member'] == 'SnapshotFor' for m in self.calls()))

    def test_reentrant_profile_cycle_on_commit_cannot_restore_old_values(self):
        self.select(['peripherals'])
        self.root.setProperty('cycleOnAddonCommit', True)
        self.addon_reply()
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(self.state.property('addonLoading'))
        self.addon_reply(peripheral_frame(percent=0))
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)

    def test_reentrant_duplicate_callback_settles_once(self):
        self.select(['peripherals'])
        self.root.setProperty('replayOnAddonCommit', True)
        self.root.setProperty('refreshAfterLoad', True)
        self.addon_reply()
        self.assertEqual(self.root.property('addonCommits'), 1)
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(self.state.property('addonLoading'))
        self.addon_reply()
        self.assertFalse(self.state.property('addonLoading'))

    def test_receipt_expiry_future_observation_and_display_expiry_clear_readings(self):
        self.select(['peripherals'])
        self.evaluate('nowMsOverride=130000')
        self.addon_reply()
        self.assertEqual(self.evaluate('peripherals.status'), 'stale')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.evaluate('nowMsOverride=100000')
        self.addon_reply(peripheral_frame(generated=100001))
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.evaluate('invalidateAddons()')
        self.addon_reply(peripheral_frame(observed=None))
        self.assertIsNone(self.evaluate('peripherals.devices[0].percent'))
        self.evaluate('refresh()')
        self.addon_reply(peripheral_frame(observed=90000))
        self.evaluate('nowMsOverride=120000')
        self.assertIsNone(self.evaluate('peripherals.devices[0].percent'))
        self.assertTrue(self.evaluate('peripherals.devices[0].stale'))
        self.evaluate('nowMsOverride=130000')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_real_deadline_timer_expires_while_refresh_is_stalled(self):
        self.evaluate('nowMsOverride=-1')
        stamp = int(time.time()*1000)-29800
        self.select(['peripherals'])
        self.addon_reply(peripheral_frame(generated=stamp, observed=stamp))
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)
        self.evaluate('refresh()')
        QTest.qWait(350)
        self.app.processEvents()
        self.assertTrue(self.state.property('addonLoading'))
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.assertEqual(self.evaluate('peripherals.status'), 'stale')

    def test_clock_rollback_revokes_pending_and_displayed_values(self):
        self.select(['peripherals'])
        self.addon_reply()
        self.evaluate('refresh(); nowMsOverride=99999')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.addon_reply()
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.evaluate('nowMsOverride=100000')
        self.addon_reply()
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)

    def test_identity_pin_and_host_expectation_reject_obsolete_registry_or_sha(self):
        self.select(['peripherals'])
        self.addon_reply()
        frame = peripheral_frame()
        frame['peripherals']['addon']['sha256'] = 'c'*64
        self.evaluate('refresh()')
        self.addon_reply(frame)
        self.assertEqual(self.state.property('addonErrorCode'), 'source_changed')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.evaluate('addonSuspended=true; addonIdentity=({generation:"'+'b'*32+'",sha256:"'+'c'*64+'"}); addonSuspended=false')
        self.addon_reply()  # Old package, although the request generation is current.
        self.assertEqual(self.state.property('addonErrorCode'), 'source_changed')
        self.evaluate('refresh()')
        self.addon_reply(frame)
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)

    def test_zero_coarse_absent_stale_unknown_and_case_only_are_not_conflated(self):
        self.select(['peripherals'])
        cases = [(dict(percent=0, estimated=True, charging='charging'), 0, None, 'charging', True),
            (dict(percent=None, level='low'), None, 'low', 'discharging', False),
            (dict(stale=True), None, None, 'unknown', False),
            (dict(observed=None), None, None, 'unknown', False),
            (dict(kind='earbuds', name='earbuds', components=[dict(label='case', percent=80, charging='charging')]),
                None, None, 'unknown', False)]
        for index, (changes, percent, level, charging, estimated) in enumerate(cases):
            with self.subTest(changes=changes):
                if index: self.evaluate('refresh()')
                self.addon_reply(peripheral_frame(**changes))
                self.assertEqual(self.evaluate('peripherals.devices[0].percent'), percent)
                self.assertEqual(self.evaluate('peripherals.devices[0].level'), level)
                self.assertEqual(self.evaluate('peripherals.devices[0].charging'), charging)
                self.assertEqual(self.evaluate('peripherals.devices[0].estimated'), estimated)
                if changes.get('kind') == 'earbuds':
                    self.assertEqual(self.evaluate('peripherals.devices[0].components[0].percent'), 80)
                    self.assertNotIn('%', self.state.property('batterySummary'))

    def test_disconnected_devices_are_hidden_and_shared_names_replace_generic_labels(self):
        self.select(['peripherals'])
        frame = peripheral_frame()
        away = dict(frame['peripherals']['devices'][0], name='keyboard', kind='keyboard', present=False)
        frame['peripherals']['devices'].append(away)
        self.addon_reply(frame)
        self.assertEqual(self.evaluate('peripherals.devices.length'), 1)
        self.assertEqual(self.state.property('batterySummary'), 'Mouse · 70%')
        self.evaluate('refresh()')
        frame = peripheral_frame()
        frame['peripherals']['devices'][0]['displayName'] = 'Mouse de teste'
        self.addon_reply(frame)
        self.assertEqual(self.state.property('addonErrorCode'), '')
        self.assertEqual(self.state.property('batterySummary'), 'Mouse de teste · 70%')

    def test_malformed_and_management_frames_clear_previous_values_without_sensitive_errors(self):
        self.select(['peripherals'])
        self.addon_reply()
        bad = []
        for path, value in [(('peripherals', 'generatedAt'), 100000),
            (('peripherals', 'leaseMs'), 0), (('peripherals', 'limited'), 1),
            (('peripherals', 'addon', 'sha256'), 'PRIVATE-SENTINEL'),
            (('peripherals', 'addon', 'generation'), 'B'*32),
            (('peripherals', 'addon', 'errorCode'), 'PRIVATE-SENTINEL'),
            (('peripherals', 'devices', 0, 'percent'), 100.5),
            (('peripherals', 'devices', 0, 'present'), 1),
            (('peripherals', 'devices', 0, 'name'), 'PRIVATE-SENTINEL'),
            (('peripherals', 'devices', 0, 'observedAt'), 100000),
            (('peripherals', 'devices', 0, 'privateId'), 'PRIVATE-SENTINEL')]:
            frame = peripheral_frame()
            cursor = frame
            for key in path[:-1]: cursor = cursor[key]
            cursor[path[-1]] = value
            bad.append(json.dumps(frame))
        good = json.dumps(peripheral_frame())
        bad.extend([good.replace('"schemaVersion": 2', '"schemaVersion": 2, "schemaVersion": 2'),
            good+' {}', '"'+'x'*262145+'"', good.replace('70', '1e999', 1),
            '{"formatVersion":"0.1-experimental","ok":false,"error":{"code":"timeout","generation":null}}',
            '{"formatVersion":"0.1-experimental","ok":true,"result":'+good+'}'])
        for text in bad:
            with self.subTest(text=text[:70]):
                self.evaluate('refresh()')
                self.raw_reply(text)
                self.assertEqual(self.state.property('addonErrorCode'), 'invalid_response')
                self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
                self.assertNotIn('PRIVATE-SENTINEL', self.state.property('addonError'))
        self.evaluate('refresh()')
        self.addon_reply(dict(formatVersion='0.1-experimental', ok=False,
            error=dict(code='timeout', committed=None, generation=None)))
        self.assertEqual(self.state.property('addonErrorCode'), 'timeout')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_actual_backend_variants_are_accepted_without_settings_or_legacy_transport(self):
        from test_addons import load, manifest, export
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            backend = load('addon_store')
            paths = backend.AddonPaths(home=home, data_home=home/'data', state_home=home/'state')
            package = home/'synthetic.json'
            package.write_text(json.dumps(manifest()))
            package.chmod(0o600)
            digest = hashlib.sha256(package.read_bytes()).hexdigest()
            self.select(['peripherals'])
            def receive(expected):
                self.evaluate('invalidateAddons()')
                # Discard any prior request detached by invalidation.
                self.evaluate('queue=queue.slice(-1)', self.transport)
                p = backend.snapshot_peripherals(paths=paths, now_ms=100000)
                self.addon_reply(dict(schemaVersion=2, modules=['peripherals'], peripherals=p))
                self.assertEqual(self.state.property('addonErrorCode'), '')
                self.assertEqual(self.evaluate('peripherals.status'), expected)
            receive('missing')
            backend.install_addon(paths=paths, file=package, expected_sha256=digest)
            receive('missing')
            backend.enable_addon(paths=paths, addon_id='org.example.battery', expected_current_sha256=digest)
            receive('missing')
            target = home/'state/synthetic-battery/exports/orla-peripherals-v1.json'
            target.parent.mkdir(mode=0o700, parents=True)
            target.parent.parent.chmod(0o700)
            variants = [(export(), 'ready')]
            # A disconnected device is dropped, so nothing is left to be stale.
            for changes, status in [(dict(present=False), 'unknown'), (dict(observedAtMs=None), 'stale'),
                                    (dict(stale=True), 'stale')]:
                e = export()
                e['devices'][0].update(changes)
                variants.append((e, status))
            e = export()
            e['devices'][0]['battery'].update(percent=None, level='low')
            variants.append((e, 'ready'))
            e = export()
            e['devices'][0]['battery']['percent'] = None
            variants.append((e, 'unknown'))
            e = export()
            e.update(generatedAtMs=70000, expiresAtMs=100000)
            variants.append((e, 'stale'))
            e = export()
            e.update(generatedAtMs=100001, expiresAtMs=130001)
            variants.append((e, 'stale'))
            for value, status in variants:
                target.write_text(json.dumps(value))
                target.chmod(0o600)
                receive(status)
            target.write_text('{"private":"PRIVATE-SENTINEL"}')
            receive('invalid')
            self.assertNotIn('PRIVATE-SENTINEL', self.evaluate('JSON.stringify(peripherals)'))
            self.assertTrue(all(m['service'] == 'org.orla.Addons' for m in self.calls()))

    def test_reply_must_be_one_string_and_json_byte_depth_and_component_bounds_hold(self):
        self.select(['peripherals'])
        frame = peripheral_frame()
        bad = [json.dumps(frame, ensure_ascii=False)+' '*262145,
            '['*9+'0'+']'*9,
            json.dumps(frame).replace('"producerVersion": "0.1.0"', '"producerVersion": "'+'é'*131073+'"'),
            json.dumps(frame).replace('"name": "mouse"', '"name": "\\ud800"')]
        for field, value in [('devices', [{}]*129)]:
            f = peripheral_frame()
            f['peripherals'][field] = value
            bad.append(json.dumps(f))
        f = peripheral_frame(components=[dict(label='case', percent=10, charging='unknown')]*2)
        bad.append(json.dumps(f))
        for text in bad:
            self.raw_reply(text)
            self.assertEqual(self.state.property('addonErrorCode'), 'invalid_response')
            self.evaluate('refresh()')
        self.evaluate('reply(["one", "two"], false, "org.orla.Addons")', self.transport)
        self.assertEqual(self.state.property('addonErrorCode'), 'invalid_response')
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_generic_ordinals_are_local_to_each_snapshot(self):
        self.select(['peripherals'])
        frame = peripheral_frame()
        first = frame['peripherals']['devices'][0]
        second = dict(first, name='mouse 2', percent=10)
        first['name'] = 'mouse 1'
        frame['peripherals']['devices'].append(second)
        self.addon_reply(frame)
        self.assertEqual(self.evaluate('peripherals.devices.map(d=>d.name).join(",")'), 'Mouse 1,Mouse 2')
        self.evaluate('refresh()')
        self.addon_reply(peripheral_frame(percent=10))
        self.assertEqual(self.evaluate('peripherals.devices[0].name'), 'Mouse')

    def test_wire_identifiers_hashes_and_versions_refuse_trailing_controls(self):
        self.select(['peripherals'])
        for path in [('addon', 'sha256'), ('addon', 'generation'), ('addon', 'id'),
                     ('addon', 'producerNamespace'), ('producerVersion',)]:
            with self.subTest(path=path):
                self.evaluate('invalidateAddons()')
                self.evaluate('queue=queue.slice(-1)', self.transport)
                frame = peripheral_frame()
                cursor = frame['peripherals']
                for key in path[:-1]: cursor = cursor[key]
                cursor[path[-1]] += '\n'
                self.addon_reply(frame)
                self.assertEqual(self.state.property('addonErrorCode'), 'invalid_response')
                self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_reentrant_refresh_during_profile_revocation_cannot_dispatch_old_selection(self):
        self.select(['peripherals'])
        self.addon_reply()
        self.evaluate('refresh()')
        before = len(self.calls())
        self.root.setProperty('refreshAfterLoad', True)
        self.select(['peripherals'], False)
        self.assertEqual(len(self.calls()), before)
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_logical_revocation_does_not_settle_the_physical_addon_call(self):
        self.select(['peripherals'])
        self.assertTrue(self.state.property('addonCallPending'))
        self.evaluate('addonSuspended=true; invalidateAddons()')
        self.assertFalse(self.state.property('addonLoading'))
        self.assertTrue(self.state.property('addonCallPending'))
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
        self.select(['peripherals'], False)
        self.assertTrue(self.state.property('addonCallPending'))
        self.addon_reply()
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_old_physical_callback_cannot_settle_a_newer_outstanding_call(self):
        self.select(['peripherals'])
        self.select(['peripherals'], False)
        self.select(['peripherals'])
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(self.state.property('addonCallPending'))
        self.addon_reply()  # Settles the revoked first call, not the second one.
        self.assertTrue(self.state.property('addonCallPending'))
        self.evaluate('replay({value:lastText})', self.transport)
        self.assertTrue(self.state.property('addonCallPending'))
        self.addon_reply()
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)

    def test_physical_call_settles_on_sync_reply_dispatch_throw_or_rejection(self):
        self.transport.setProperty('throwOnCall', True)
        self.select(['peripherals'])
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertEqual(self.state.property('addonErrorCode'), 'unavailable')
        self.transport.setProperty('throwOnCall', False)
        self.transport.setProperty('immediateReply', True)
        self.evaluate('refresh()')
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertEqual(self.state.property('addonErrorCode'), 'invalid_response')
        self.transport.setProperty('immediateReply', False)
        self.evaluate('refresh()')
        self.assertTrue(self.state.property('addonCallPending'))
        self.addon_reply(failed=True)
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertEqual(self.state.property('addonErrorCode'), 'unavailable')

    def test_physical_settlement_observer_cannot_replace_the_first_callback(self):
        self.select(['peripherals'])
        self.root.setProperty('replayBadOnPhysicalSettlement', True)
        self.addon_reply()
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertEqual(self.state.property('addonErrorCode'), '')
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 70)
        self.assertEqual(self.root.property('addonCommits'), 1)

    def test_module_revocation_cannot_dispatch_addon_from_legacy_module_notification(self):
        self.select(['quota','peripherals'])
        self.addon_reply()
        before=len([m for m in self.calls() if m['service']=='org.orla.Addons'])
        fired=[]
        def on_change():
            if not fired:
                fired.append(True)
                e=QQmlExpression(self.engine.rootContext(), self.state, 'refresh()')
                e.evaluate()
                assert not e.hasError(), e.error().toString()
        self.state.legacyModulesChanged.connect(on_change)
        self.select(['recording'])
        self.assertTrue(fired)
        self.assertEqual(self.evaluate('peripherals.status'), 'disabled')
        after=len([m for m in self.calls() if m['service']=='org.orla.Addons'])
        self.assertEqual(after, before, 'refresh dispatched peripherals after enabledModules revoked it, before selectedModules caught up')


    def test_actual_backend_changed_package_is_not_adopted_after_clock_rollback(self):
        import hashlib, tempfile
        from pathlib import Path
        from test_addons import load, manifest, export
        backend=load('addon_store')
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary)
            paths=backend.AddonPaths(home=home,data_home=home/'data',state_home=home/'state')
            package=home/'synthetic.json'
            def install(version):
                m=manifest(); m['version']=version
                package.write_text(json.dumps(m)); package.chmod(0o600)
                digest=hashlib.sha256(package.read_bytes()).hexdigest()
                backend.install_addon(paths=paths,file=package,expected_sha256=digest)
                backend.enable_addon(paths=paths,addon_id=m['id'],expected_current_sha256=digest)
            install('1.0.0')
            e=export(); e.update(generatedAtMs=90000,expiresAtMs=120000); e['devices'][0]['observedAtMs']=90000
            target=home/'state/synthetic-battery/exports/orla-peripherals-v1.json'
            target.parent.mkdir(parents=True,mode=0o700); target.parent.parent.chmod(0o700)
            target.write_text(json.dumps(e)); target.chmod(0o600)
            def frame(now):
                return dict(schemaVersion=2,modules=['peripherals'],peripherals=backend.snapshot_peripherals(paths=paths,now_ms=now))
            self.select(['peripherals']); original=frame(100000); self.addon_reply(original)
            install('2.0.0'); changed=frame(100000)
            self.assertNotEqual(original['peripherals']['addon']['generation'],changed['peripherals']['addon']['generation'])
            self.assertNotEqual(original['peripherals']['addon']['sha256'],changed['peripherals']['addon']['sha256'])
            self.evaluate('refresh()'); self.addon_reply(changed)
            self.assertEqual(self.state.property('addonErrorCode'),'source_changed')
            self.evaluate('nowMsOverride=99999'); self.addon_reply(frame(99999))
            self.assertEqual(self.state.property('addonErrorCode'),'source_changed', 'actual backend version 2 snapshot was silently adopted after 1 ms rollback')

            self.assertEqual(self.evaluate('peripherals.devices.length'), 0)
            self.evaluate('invalidateAddons()')
            self.addon_reply(frame(99999))
            self.assertEqual(self.state.property('addonErrorCode'), '')
            self.assertEqual(self.evaluate('peripherals.devices[0].percent'), 0)


    def test_clock_rollback_does_not_implicitly_adopt_changed_source(self):
        self.select(['peripherals'])
        self.addon_reply()
        frame=peripheral_frame(); frame['peripherals']['addon']['sha256']='c'*64; frame['peripherals']['addon']['generation']='d'*32
        self.evaluate('refresh()'); self.addon_reply(frame)
        self.assertEqual(self.state.property('addonErrorCode'), 'source_changed')
        self.evaluate('nowMsOverride=99999')
        self.assertEqual(self.state.property('addonErrorCode'), 'source_changed')
        frame=peripheral_frame(generated=99999, observed=99999)
        frame['peripherals']['addon']['sha256']='c'*64; frame['peripherals']['addon']['generation']='d'*32
        self.addon_reply(frame)
        self.assertEqual(self.state.property('addonErrorCode'), 'source_changed', 'backward clock automatically cleared the source pin')


    def test_observation_expiry_envelope_expiry_and_future_receipt_keep_source_pin(self):
        self.select(['peripherals'])
        for generated, observed, later in ((100000, 90000, 120000),
                                           (100000, 100000, 130000),
                                           (100001, 100001, 100002)):
            with self.subTest(generated=generated, observed=observed, later=later):
                self.evaluate('nowMsOverride=100000; invalidateAddons()')
                self.evaluate('queue=queue.slice(-1)', self.transport)
                self.addon_reply(peripheral_frame(generated=generated, observed=observed))
                self.evaluate('nowMsOverride='+str(later)+'; refresh()')
                changed = peripheral_frame(generated=later, observed=later)
                changed['peripherals']['addon'].update(sha256='c'*64, generation='d'*32)
                self.addon_reply(changed)
                self.assertEqual(self.state.property('addonErrorCode'), 'source_changed')
                self.assertEqual(self.evaluate('peripherals.devices.length'), 0)

    def test_invalidate_reentrant_refresh_preserves_loading(self):
        self.select(['peripherals'])
        self.addon_reply()
        fired=[]
        def on_change():
            if not fired and self.state.property('peripherals').toVariant()['status']=='unknown':
                fired.append(True)
                e=QQmlExpression(self.engine.rootContext(), self.state, 'refresh()')
                e.evaluate()
                assert not e.hasError(), e.error().toString()
        self.state.snapshotChanged.connect(on_change)
        self.evaluate('invalidateAddons()')
        self.assertTrue(fired)
        self.assertTrue(self.state.property('addonCallPending'))
        self.assertTrue(self.state.property('addonLoading'), 'current physical call was dispatched by a snapshot observer inside invalidate(), then invalidate() reset loading=false')

        self.assertTrue(self.state.property('loading'))

    def test_qml_physical_settlement_defers_new_call_without_false_pending_or_warnings(self):
        self.select(['peripherals'])
        self.evaluate('let first=transport.queue[0]; let fired=false; addonCallPendingChanged.connect(function(){ if (!addonCallPending && !fired) { fired=true; addonSuspended=true; addonSuspended=false; refresh(); } else if (addonCallPending && fired) { first.reject(); first.resolve({value:"{}"}); } });')
        self.addon_reply()
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(self.evaluate('queue.length',self.transport), 1)
        self.assertTrue(self.state.property('addonLoading'))
        self.assertTrue(self.state.property('addonCallPending'))
        self.evaluate('replay({value:lastText}); replay({value:"{}"})',self.transport)
        self.assertTrue(self.state.property('addonCallPending'))
        self.evaluate('let call=queue[0]; queue=[]; call.resolve({value:'+json.dumps(json.dumps(peripheral_frame(percent=0)))+'}); call.reject(); call.resolve({value:"{}"})',self.transport)
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'),0)
        self.assertFalse(self.state.property('addonCallPending'))
        self.assertFalse(self.state.property('addonLoading'))

    def test_expired_observation_and_envelope_cannot_revive_after_rollback(self):
        self.select(['peripherals'])
        for deadline in (120000, 130000):
            with self.subTest(deadline=deadline):
                self.evaluate('nowMsOverride=100000; invalidateAddons()')
                self.evaluate('queue=queue.slice(-1)',self.transport)
                frame=peripheral_frame(observed=90000)
                self.addon_reply(frame)
                self.assertEqual(self.evaluate('peripherals.devices[0].percent'),70)
                self.evaluate('nowMsOverride='+str(deadline))
                self.assertFalse(self.evaluate('peripherals.devices.some(d=>d.percent!==null)'))
                self.evaluate('nowMsOverride='+str(deadline-1))
                self.addon_reply(frame)
                self.assertFalse(self.evaluate('peripherals.devices.some(d=>d.percent!==null)'), 'expired data revived after rollback')

    def test_freshness_floor_allows_new_observation_and_explicit_host_recovery(self):
        self.select(['peripherals'])
        old=peripheral_frame(observed=90000)
        self.addon_reply(old)
        self.evaluate('nowMsOverride=120000; nowMsOverride=119999')
        self.addon_reply(old)
        self.assertIsNone(self.evaluate('peripherals.devices[0].percent'))
        self.evaluate('refresh()')
        self.addon_reply(peripheral_frame(generated=119999, observed=119999,percent=0))
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'),0)
        self.evaluate('invalidateAddons()')
        self.addon_reply(old)
        self.assertEqual(self.evaluate('peripherals.devices[0].percent'),70)

    def test_actual_backend_same_bytes_do_not_revive_expired_observation(self):
        from test_addons import load,manifest,export
        backend=load('addon_store')
        with tempfile.TemporaryDirectory() as temporary:
            home=Path(temporary); paths=backend.AddonPaths(home=home,data_home=home/'data',state_home=home/'state')
            package=home/'synthetic.json'; package.write_text(json.dumps(manifest())); package.chmod(0o600)
            digest=hashlib.sha256(package.read_bytes()).hexdigest()
            backend.install_addon(paths=paths,file=package,expected_sha256=digest)
            backend.enable_addon(paths=paths,addon_id='org.example.battery',expected_current_sha256=digest)
            target=home/'state/synthetic-battery/exports/orla-peripherals-v1.json'
            target.parent.mkdir(mode=0o700,parents=True); target.parent.parent.chmod(0o700)
            e=export(); e['devices'][0]['observedAtMs']=90000
            target.write_text(json.dumps(e)); target.chmod(0o600)
            before=target.read_bytes()
            def frame(now):
                return dict(schemaVersion=2,modules=['peripherals'],peripherals=backend.snapshot_peripherals(paths=paths,now_ms=now))
            initial=frame(100000)
            self.select(['peripherals']); self.addon_reply(initial)
            self.assertEqual(self.evaluate('peripherals.devices[0].percent'),0)
            self.evaluate('nowMsOverride=120000')
            self.assertIsNone(self.evaluate('peripherals.devices[0].percent'))
            self.evaluate('nowMsOverride=119999')
            later=frame(119999)
            self.assertEqual(initial['peripherals']['addon'],later['peripherals']['addon'])
            self.assertEqual(target.read_bytes(),before)
            self.addon_reply(later)
            self.assertIsNone(self.evaluate('peripherals.devices[0].percent'),'actual backend, unchanged export, expired observation revived after 1ms rollback')
