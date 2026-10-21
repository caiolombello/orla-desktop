"""Production QML, actual native controls, keyboard and clipped-viewport checks."""
import json
from pathlib import Path
import sys
import unittest
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
import test_updates_desktop_process as process

class ViewTests(process.ProcessFixture):

    def setUp(self):
        super().setUp()
        self.host = self.host('import time;time.sleep(.12);print(' + repr(json.dumps(process.payload())) + ')')
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda values: self.warnings.extend((v.toString() for v in values)))
        self.engine.rootContext().setContextProperty('updatesController', self.host)
        self.engine.load(QUrl.fromLocalFile(str(process.ROOT / 'workspace/Updates.qml')))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.window.resize(350, 620)
        QTest.qWait(30)

    def tearDown(self):
        self.host.requestClose()
        self.wait(self.host)
        self.window.close()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        super().tearDown()
        self.assertEqual(self.warnings, [])

    def item(self, name):
        item = self.window.findChild(QQuickItem, name)
        self.assertIsNotNone(item, name)
        return item

    def expr(self, item, text):
        expression = QQmlExpression(self.engine.rootContext(), item, text)
        value = expression.evaluate()
        self.assertFalse(expression.hasError(), expression.error().toString())
        return value

    def focus(self, item):
        item.forceActiveFocus(Qt.TabFocusReason)
        QTest.qWait(35)

    def test_keyboard_one_activation_and_no_completion_focus_theft(self):
        check = self.item('updatesCheck')
        self.focus(check)
        QTest.keyClick(self.window, Qt.Key_Space)
        self.assertTrue(self.host.busy)
        channel = self.item('updatesChannel')
        self.focus(self.item('updatesDetails'))
        self.wait(self.host)
        self.assertEqual(len(self.argv), 1)
        self.assertTrue(self.item('updatesDetails').hasActiveFocus())
        self.assertIn('2.0.0', self.item('updatesStatus').property('text'))

    def test_public_accessibility_press_is_unique_and_dispatches_once(self):
        from PySide6.QtGui import QAccessible, QAccessibleActionInterface
        previous = QAccessible.isActive()
        QAccessible.setActive(True)
        try:
            interface = QAccessible.queryAccessibleInterface(self.item('updatesCheck'))
            self.assertIsNotNone(interface)
            action = interface.actionInterface()
            names = action.actionNames()
            press = QAccessibleActionInterface.pressAction()
            self.assertEqual(names.count(press), 1)
            self.assertEqual(len(names), len(set(names)))
            action.doAction(press)
            self.assertTrue(self.host.busy)
            self.wait(self.host)
            self.assertEqual(len(self.argv), 1)
        finally:
            QAccessible.setActive(previous)

    def test_actual_view_check_close_reopen_and_dated_history(self):
        check = self.item('updatesCheck')
        self.focus(check)
        QTest.keyClick(self.window, Qt.Key_Return)
        self.wait(self.host)
        self.assertIn('Última tentativa', self.item('updatesDates').property('text'))
        self.assertEqual(len(self.argv), 1)

    def test_combo_escape_menu_first_and_tab_order(self):
        channel = self.item('updatesChannel')
        self.focus(channel)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(80)
        self.assertTrue(self.expr(channel, 'popup.visible')[0])
        QTest.keyClick(self.window, Qt.Key_Escape)
        for _ in range(60):
            if not self.expr(channel, 'popup.visible')[0]:
                break
            QTest.qWait(10)
        self.assertFalse(self.expr(channel, 'popup.visible')[0])
        self.assertFalse(self.host.closePending)
        self.focus(self.item('updatesCheck'))
        QTest.keyClick(self.window, Qt.Key_Tab)
        QTest.qWait(30)
        self.assertTrue(channel.hasActiveFocus())

    def test_current_focus_fits_real_viewport_at_narrow_short_and_large_text(self):
        for width in (320, 350, 420):
            self.window.resize(width, 240)
            for name in ('updatesCheck', 'updatesChannel', 'updatesDetails'):
                control = self.item(name)
                self.focus(control)
                viewport = self.item('updatesViewport')
                point = control.mapToItem(viewport, QPointF(0, 0))
                self.assertGreaterEqual(point.y() - 3, -1, (width, name, point.y()))
                self.assertLessEqual(point.y() + control.height() + 3, viewport.height() + 1, (width, name))
                self.assertLessEqual(control.width(), viewport.width())
        self.expr(self.window, 'font.pointSize = font.pointSize * 2')
        self.host.reference=dict(self.host.reference,version='1.2.3+'+'x'*110)
        self.host.changed.emit()
        for width in (320,350,420):
            self.window.resize(width,240)
            for name in ('updatesCheck','updatesChannel','updatesDetails'):
                control=self.item(name);self.focus(control)
                viewport=self.item('updatesViewport');point=control.mapToItem(viewport,QPointF(0,0))
                self.assertGreaterEqual(point.y()-3,-1,(width,name))
                self.assertLessEqual(point.y()+control.height()+3,viewport.height()+1,(width,name))
                self.assertLessEqual(control.width(),viewport.width())

    def test_failure_after_success_has_historical_copy(self):
        self.host.check()
        self.wait(self.host)
        helper = self.path / 'failure.py'
        helper.write_text('print(' + repr(json.dumps(process.payload('unavailable'))) + ');raise SystemExit(2)')
        self.host._runner = lambda *args: (sys.executable, ['-I', '-B', str(helper)])
        self.host.check()
        self.wait(self.host)
        self.assertIn('Não foi possível', self.item('updatesStatus').property('text'))
        self.assertIn('salvo', self.item('updatesHistory').property('text'))

    def test_saved_dates_are_localized_across_midnight_without_rewriting_history(self):
        from PySide6.QtCore import QLocale
        from scripts.updates_desktop import UpdatesController
        from scripts.updates_desktop_state import Store, history_key
        from unittest.mock import patch
        import os
        import time
        previous_locale = QLocale()
        data = process.payload()
        data['checked_at'] = '2026-10-20T01:30:00Z'
        record = dict(attemptedAt=data['checked_at'], completedAt='2026-10-20T01:31:00Z', result=data)
        store = Store(self.path)
        store.save_history({'stable': dict(key=history_key(process.REF, 'stable'), attempt=record, lastCompleted=record)})
        before = store.cache.read_bytes()
        def forbid(*args):
            self.fail('formatting or reopening started a query')
        try:
            with patch.dict(os.environ, {'TZ': 'America/Sao_Paulo'}):
                time.tzset()
                QLocale.setDefault(QLocale('pt_BR'))
                reopened = UpdatesController(process.ROOT, process.REF, runner=forbid, storage_root=self.path)
                self.hosts.append(reopened)
                self.window.setProperty('controller', reopened)
                QTest.qWait(40)
                text = self.item('updatesDates').property('text')
                self.assertIn('19/10/2026', text)
                self.assertIn('22:30', text)
                self.assertIn('22:31', text)
                self.assertNotIn('2026-10-20T', text)
                self.assertIn('Resultado salvo de 19/10/2026', self.item('updatesStatus').property('text'))
                self.assertTrue(reopened.state['historical'])
                self.assertEqual(reopened.state['record'], record)
                self.assertEqual(store.cache.read_bytes(), before)
                self.focus(self.item('updatesDetails'))
                QTest.keyClick(self.window, Qt.Key_Space)
                QTest.qWait(40)
                canonical = self.item('updatesCanonicalDates')
                self.assertTrue(canonical.isVisible())
                self.assertIn('2026-10-20T01:30:00Z', canonical.property('text'))
                self.assertIn('2026-10-20T01:31:00Z', canonical.property('text'))
                self.assertEqual(store.cache.read_bytes(), before)
        finally:
            QLocale.setDefault(previous_locale)
            time.tzset()

    def test_qualified_reference_and_unknowns_move_into_passive_disclosure(self):
        reference = self.item('updatesReference')
        self.assertEqual(reference.property('text'), '1.2.3')
        self.assertIn('pacote fonte do dock', self.item('updatesReferenceOrigin').property('text'))
        details = self.item('updatesDetails')
        unknowns = self.item('updatesComponentVersions')
        self.assertFalse(unknowns.isVisible())
        self.assertEqual(list(self.path.iterdir()), [self.path / 'helper0.py'])
        self.focus(self.item('updatesCheck'))
        for expected in ('updatesChannel', 'updatesDetails'):
            QTest.keyClick(self.window, Qt.Key_Tab)
            QTest.qWait(35)
            self.assertTrue(self.item(expected).hasActiveFocus())
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        self.assertTrue(unknowns.isVisible())
        self.assertEqual(unknowns.property('text'), 'Dock instalada: não encontrada para este usuário\nDock em execução: não verificada')
        self.assertTrue(details.hasActiveFocus())
        self.assertIn('pergunta ao Plasma quais docks ele carregou', self.item('updatesComponentScope').property('text'))
        self.assertEqual(self.argv, [])
        self.host.reference = dict(process.REF, role='bundle', component='workspace', origin='verified-manifest')
        self.host.changed.emit()
        QTest.qWait(30)
        self.assertEqual(reference.property('text'), '1.2.3')
        self.assertIn('esta cópia do Workspace', self.item('updatesReferenceOrigin').property('text'))
        self.assertIn('bundle verificado', self.item('updatesReferenceOrigin').property('text'))
        self.assertEqual(unknowns.property('text'), 'Dock instalada: não encontrada para este usuário\nDock em execução: não verificada')
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        self.assertFalse(unknowns.isVisible())
        self.assertTrue(details.hasActiveFocus())
        QTest.keyClick(self.window, Qt.Key_Backtab)
        QTest.qWait(35)
        self.assertTrue(self.item('updatesChannel').hasActiveFocus())
        self.assertEqual(self.argv, [])

    def test_installed_dock_becomes_the_reference_with_its_origin(self):
        package = self.path / 'data/plasma/plasmoids/org.caiodock.dock'
        package.mkdir(parents=True)
        (package / 'metadata.json').write_text(json.dumps({'KPlugin': {'Id': 'org.caiodock.dock', 'Version': '0.2.9'}}))
        self.host.resolve_reference()
        self.host.changed.emit()
        QTest.qWait(30)
        self.assertEqual(self.item('updatesReference').property('text'), '0.2.9')
        self.assertEqual(self.item('updatesReferenceOrigin').property('text'), 'dock instalada para este usuário')
        self.focus(self.item('updatesDetails'))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        versions = self.item('updatesComponentVersions')
        self.assertTrue(versions.isVisible())
        self.assertEqual(versions.property('text'), 'Dock instalada: 0.2.9 · metadados deste usuário\n'
                         'Dock em execução: não verificada\nPacote fonte do dock: 1.2.3')
        self.assertEqual(self.argv, [])

    def test_running_dock_is_read_only_on_request_and_reports_each_state(self):
        requests = []
        self.host._running_probe = lambda parent, done: requests.append(done)
        package = self.path / 'data/plasma/plasmoids/org.caiodock.dock'
        package.mkdir(parents=True)
        (package / 'metadata.json').write_text(json.dumps({'KPlugin': {'Id': 'org.caiodock.dock', 'Version': '0.2.9'}}))
        self.host.resolve_reference()
        self.host.changed.emit()
        self.focus(self.item('updatesDetails'))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        versions, button, differs = self.item('updatesComponentVersions'), self.item('updatesReadRunning'), self.item('updatesRunningDiffers')
        self.assertEqual(requests, [])
        self.assertIn('Dock em execução: não verificada', versions.property('text'))
        self.focus(button)
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.keyClick(self.window, Qt.Key_Return)
        QTest.qWait(30)
        self.assertEqual(len(requests), 1)
        self.assertTrue(self.host.readingRunning)
        self.assertFalse(button.property('enabled'))
        cases = [('found', ['0.2.9'], 'Dock em execução: 0.2.9 · lida do Plasma', False),
                 ('found', ['0.2.8'], 'Dock em execução: 0.2.8 · lida do Plasma', True),
                 ('found', ['0.2.8', '0.2.9'], 'Dock em execução: 0.2.8, 0.2.9 · lida do Plasma', True),
                 ('absent', [], 'Dock em execução: não carregada no Plasma', False),
                 ('unavailable', [], 'Dock em execução: não foi possível ler agora', False)]
        for index, (status, found, line, mismatch) in enumerate(cases):
            with self.subTest(status=status, found=found):
                if index:
                    self.host.readRunning()
                requests[-1](status, found)
                requests[-1](status, ['9.9.9'])  # a duplicate callback is ignored
                QTest.qWait(30)
                self.assertEqual(len(requests), index + 1)
                self.assertFalse(self.host.readingRunning)
                self.assertEqual(versions.property('text').split('\n')[1], line)
                self.assertEqual(differs.isVisible(), mismatch)
        self.host._running_probe = lambda parent, done: (_ for _ in ()).throw(RuntimeError('no bus'))
        self.host.readRunning()
        QTest.qWait(30)
        self.assertEqual(versions.property('text').split('\n')[1], 'Dock em execução: não foi possível ler agora')
        self.assertEqual(self.argv, [])

    def test_future_saved_clock_stays_unreliable_after_formatting(self):
        from scripts.updates_desktop import UpdatesController
        from scripts.updates_desktop_state import Store, history_key
        data = process.payload()
        data['checked_at'] = '2099-01-01T01:30:00Z'
        record = dict(attemptedAt=data['checked_at'], completedAt='2099-01-01T01:31:00Z', result=data)
        store = Store(self.path)
        store.save_history({'stable': dict(key=history_key(process.REF, 'stable'), attempt=record, lastCompleted=record)})
        before = store.cache.read_bytes()
        def forbid(*args):
            self.fail('future clock started a query')
        reopened = UpdatesController(process.ROOT, process.REF, runner=forbid, storage_root=self.path)
        self.hosts.append(reopened)
        self.window.setProperty('controller', reopened)
        QTest.qWait(40)
        self.assertTrue(reopened.state['timeUnreliable'])
        self.assertTrue(reopened.state['historical'])
        self.assertIn('Resultado salvo de', self.item('updatesStatus').property('text'))
        self.assertNotIn('2099-01-01T', self.item('updatesDates').property('text'))
        visible_text = [item.property('text') for item in self.window.findChildren(QQuickItem) if item.isVisible()]
        self.assertIn('Horário não confiável. O registro permanece apenas como histórico.', visible_text)
        self.assertEqual(store.cache.read_bytes(), before)

    def test_offline_over_saved_history_keeps_failure_and_readable_dates(self):
        from scripts.updates_desktop import UpdatesController
        from scripts.updates_desktop_state import Store, history_key
        data = process.payload()
        data['checked_at'] = '2026-01-01T01:30:00Z'
        record = dict(attemptedAt=data['checked_at'], completedAt='2026-01-01T01:31:00Z', result=data)
        store = Store(self.path)
        store.save_history({'stable': dict(key=history_key(process.REF, 'stable'), attempt=record, lastCompleted=record)})
        helper = self.path / 'offline.py'
        helper.write_text('print(' + repr(json.dumps(process.payload('unavailable'))) + ');raise SystemExit(2)')
        opened = []
        reopened = UpdatesController(process.ROOT, process.REF, storage_root=self.path,
                                     runner=lambda *args: (sys.executable, ['-I', '-B', str(helper)]),
                                     opener=lambda url: opened.append(url) or True)
        self.hosts.append(reopened)
        self.window.setProperty('controller', reopened)
        self.focus(self.item('updatesCheck'))
        QTest.keyClick(self.window, Qt.Key_Return)
        self.wait(reopened)
        self.assertIn('Não foi possível consultar agora', self.item('updatesStatus').property('text'))
        history = self.item('updatesHistory')
        self.assertTrue(history.isVisible())
        self.assertIn('Histórico salvo:', history.property('text'))
        self.assertIn('2.0.0', history.property('text'))
        self.assertNotIn('2026-01-01T', history.property('text'))
        self.assertNotIn('2026-10-20T', self.item('updatesDates').property('text'))
        self.assertEqual(reopened.state['lastCompleted'], record)
        self.assertFalse(self.item('updatesRelease').isVisible())
        self.assertEqual(opened, [])

    def test_expanded_disclosure_keeps_order_and_short_large_text_focus(self):
        self.host.check()
        self.wait(self.host)
        self.focus(self.item('updatesDetails'))
        QTest.keyClick(self.window, Qt.Key_Space)
        QTest.qWait(40)
        self.assertTrue(self.item('updatesComponentVersions').isVisible())
        for scale in (1, 2):
            if scale == 2:
                self.expr(self.window, 'font.pointSize = font.pointSize * 2')
            for width in (320, 350, 420):
                self.window.resize(width, 240)
                self.focus(self.item('updatesCheck'))
                for name in ('updatesChannel', 'updatesDetails', 'updatesReadRunning', 'updatesRelease'):
                    QTest.keyClick(self.window, Qt.Key_Tab)
                    QTest.qWait(40)
                    control = self.item(name)
                    self.assertTrue(control.hasActiveFocus(), (scale, width, name))
                    viewport = self.item('updatesViewport')
                    point = control.mapToItem(viewport, QPointF(0, 0))
                    self.assertGreaterEqual(point.x() - 3, -1, (scale, width, name))
                    self.assertLessEqual(point.x() + control.width() + 3, viewport.width() + 1, (scale, width, name))
                    self.assertGreaterEqual(point.y() - 3, -1, (scale, width, name))
                    self.assertLessEqual(point.y() + control.height() + 3, viewport.height() + 1, (scale, width, name))
                for name in ('updatesReadRunning', 'updatesDetails', 'updatesChannel', 'updatesCheck'):
                    QTest.keyClick(self.window, Qt.Key_Backtab)
                    QTest.qWait(40)
                    self.assertTrue(self.item(name).hasActiveFocus(), (scale, width, name))
                self.focus(self.item('updatesDetails'))
                QTest.keyClick(self.window, Qt.Key_Space)
                QTest.qWait(40)
                self.assertFalse(self.item('updatesComponentVersions').isVisible())
                self.assertTrue(self.item('updatesDetails').hasActiveFocus())
                QTest.keyClick(self.window, Qt.Key_Space)
                QTest.qWait(40)
        self.assertEqual(len(self.argv), 1)
