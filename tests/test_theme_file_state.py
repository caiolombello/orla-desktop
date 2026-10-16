import json,unittest
from pathlib import Path
from PySide6.QtCore import QUrl,QCoreApplication,QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine,QQmlComponent,QQmlExpression
from PySide6.QtTest import QTest,QSignalSpy
HERE=Path(__file__).resolve().parent
REPO_ROOT=HERE.parent
class ThemeFileStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])
    def setUp(self):
        self.engine=QQmlEngine();self.warnings=[]
        self.engine.warnings.connect(lambda values:self.warnings.extend(v.toString() for v in values))
        self.component=QQmlComponent(self.engine,QUrl.fromLocalFile(str(HERE/'ThemeFileStateHarness.qml')))
        self.root=self.component.create()
        self.assertIsNotNone(self.root,[v.toString() for v in self.component.errors()])
        self.state=self.root.property('appearance')
    def tearDown(self):
        self.root.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.engine.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.assertEqual(self.warnings,[])
    def evaluate(self,source,target=None):
        expression=QQmlExpression(QQmlEngine.contextForObject(target or self.root),target or self.root,source)
        value,_=expression.evaluate()
        self.assertFalse(expression.hasError(),expression.error().toString())
        return value.toVariant() if hasattr(value,'toVariant') else value
    def theme(self):
        return json.loads(next((REPO_ROOT/'themes/examples').glob('*.json')).read_text())
    def success(self):return json.dumps({'formatVersion':'0.1-experimental','valid':True,'theme':self.theme()})
    def start(self):
        self.evaluate('appearance.themeFileTransport=transport;token=appearance.beginThemeFileSelection(owner)')
        self.assertTrue(self.evaluate('token!==null'))
    def accept(self):return self.evaluate('appearance.acceptThemeFileSelection(token,"file:///synthetic/theme.json")')
    def test_begin_chooser_is_busy_and_cancel_is_owned_without_writes(self):
        self.assertTrue(self.evaluate('typeof appearance.beginThemeFileSelection === "function"'), 'Public chooser lifetime API is absent')
        good=self.evaluate('JSON.stringify(appearance.effective)')
        self.start()
        self.assertTrue(self.evaluate('appearance.themeFileSelecting && appearance.busy && appearance.dirty'))
        self.assertFalse(self.evaluate('appearance.canApply'))
        self.assertEqual(self.evaluate('transport.requests.length'),0)
        self.assertFalse(self.evaluate('appearance.cancelThemeFileSelection({})'))
        self.assertTrue(self.evaluate('appearance.themeFileSelecting'))
        self.assertTrue(self.evaluate('appearance.cancelThemeFileSelection(token)'))
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertEqual(self.evaluate('JSON.stringify(appearance.effective)'),good)
        self.assertEqual(self.evaluate('configuration.writes'),0)

    def test_read_fills_pending_input_only_then_explicit_preview_apply_and_undo(self):
        good=self.evaluate('JSON.stringify(appearance.effective)')
        self.start()
        self.assertTrue(self.accept())
        self.assertTrue(self.evaluate('appearance.themeFileLoading && appearance.busy'))
        self.assertEqual(self.evaluate('transport.requests.length'),1)
        self.evaluate('transport.succeed(0,'+json.dumps(self.success())+')')
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertTrue(self.evaluate('appearance.themePending'))
        self.assertFalse(self.evaluate('appearance.canApply'))
        self.assertEqual(json.loads(self.evaluate('appearance.themeText')),self.theme())
        self.assertEqual(self.evaluate('JSON.stringify(appearance.effective)'),good)
        self.assertEqual(self.evaluate('configuration.writes'),0)
        self.assertTrue(self.evaluate('appearance.previewTheme()'))
        self.assertTrue(self.evaluate('appearance.canApply'))
        self.assertEqual(self.evaluate('configuration.writes'),0)
        self.assertTrue(self.evaluate('appearance.apply()'))
        self.assertEqual(self.evaluate('configuration.writes'),1)
        self.assertTrue(self.evaluate('appearance.undo()'))
        self.assertEqual(self.evaluate('configuration.writes'),2)
        self.assertEqual(self.evaluate('configuration.appearanceJSON'),'')

    def test_legitimate_edits_and_aba_revoke_read_before_late_response(self):
        mutations=[
            'appearance.setThemeText("new input")',
            'appearance.setThemeText("other");appearance.setThemeText("")',
            'appearance.setToken("radius",8)',
            'appearance.clearThemeInput()',
            'appearance.selectTheme("paper")',
            'appearance.restoreDefaults()',
            'appearance.refreshDraft(JSON.parse(JSON.stringify(appearance.draft)))',
            'appearance.begin()',
            'appearance.cancel();appearance.begin()',
            'configuration.theme="paper";configuration.theme="glass"',
            'appearance.themeFileBlocked=true;appearance.themeFileBlocked=false',
            'const old=appearance.themeFileTransport;appearance.themeFileTransport=null;appearance.themeFileTransport=old',
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.evaluate('appearance.cancel();appearance.begin()')
                self.start();self.assertTrue(self.accept())
                index=self.evaluate('transport.requests.length-1')
                self.evaluate('(function(){'+mutation+'})()')
                before=self.evaluate('JSON.stringify({draft:appearance.draft,text:appearance.themeText,error:appearance.themeError,editing:appearance.editing})')
                self.assertFalse(self.evaluate('appearance.busy'),'Invalidation must release the busy barrier')
                self.evaluate('transport.succeed('+str(index)+','+json.dumps(self.success())+')')
                self.assertEqual(self.evaluate('JSON.stringify({draft:appearance.draft,text:appearance.themeText,error:appearance.themeError,editing:appearance.editing})'),before)
                self.assertEqual(self.evaluate('configuration.writes'),0)

    def test_encoded_selection_matches_actual_qurl_fully_encoded(self):
        for name in ['Maré ?#%23.json','plain space.json','percent%23.json','a&b+comma,;=@.json','漢字 😀.json']:
            with self.subTest(name=name):
                url=QUrl.fromLocalFile('/synthetic/'+name)
                actual=self.evaluate('encoded('+json.dumps(url.toString())+')')
                self.assertEqual(actual,url.toString(QUrl.ComponentFormattingOption.FullyEncoded))
                self.assertEqual(QUrl(actual).toLocalFile(),'/synthetic/'+name)
        for expression in ['null','12','({})','""','"\\ud800"']:
            self.assertEqual(self.evaluate('encoded('+expression+')'),'')

    def test_plasma_reply_unwraps_one_string_value_type_without_coercion(self):
        self.assertEqual(self.evaluate('replyText({values:[{}],value:{value:"theme-json"}})'), 'theme-json')
        for expression in ['null', '({})', '({values:[],value:{value:"x"}})',
                           '({values:[{},{}],value:{value:"x"}})', '({values:"x",value:{value:"x"}})',
                           '({values:[{}],value:"x"})', '({values:[{}],value:{value:12}})',
                           '({values:[{}],value:["x"]})']:
            with self.subTest(reply=expression):
                self.assertTrue(self.evaluate('typeof replyText('+expression+') === "undefined"'))

    def test_existing_preview_theme_cannot_clear_reentrant_newer_input(self):
        self.start();self.assertTrue(self.accept())
        self.evaluate('transport.succeed(0,'+json.dumps(self.success())+')')
        self.evaluate('appearance.draftChanged.connect(function newer(){appearance.draftChanged.disconnect(newer);appearance.setThemeText("{newer input}");})')
        self.assertFalse(self.evaluate('appearance.previewTheme()'))
        self.assertEqual(self.evaluate('appearance.themeText'),'{newer input}')
        self.assertTrue(self.evaluate('appearance.themePending'))
        self.assertFalse(self.evaluate('appearance.canApply'))
        self.assertEqual(self.evaluate('configuration.writes'),0)

    def test_strict_response_schema_duplicate_depth_and_utf8_byte_budget(self):
        valid=self.success()
        value=json.loads(valid)
        canonical=self.evaluate('decode('+json.dumps(valid)+').text')
        cases=[None,12,{},[], '', '\ufeff'+valid, valid+' true',
            valid.replace('"valid": true','"valid":true,"valid":true'),
            valid.replace('"radius":','"radius":8,"radius":',1),
            json.dumps(dict(value, extra=True)), json.dumps(dict(value,valid=1)),
            json.dumps(dict(value,formatVersion='future')),
            json.dumps({'formatVersion':'0.1-experimental','valid':False,'code':'unknown'}),
            '{"formatVersion":"0.1-experimental","valid":false,"code":"file","theme":{}}',
            '[[[[[{}]]]]]', valid.replace('"radius": 21','"radius": Infinity')]
        # Finite theme radius may differ by example: force a nested invalid token.
        bad=json.loads(valid);bad['theme']['tokens']['radius']=100
        cases.append(json.dumps(bad))
        for raw in cases:
            if raw==valid:continue
            with self.subTest(raw=str(raw)[:70]):
                result=self.evaluate('decode('+json.dumps(raw)+')')
                self.assertEqual(result,{'code':'invalid_response'})
        for code in ['type','size','utf8','json','depth','duplicate_key','nonfinite','unknown_key','required','format_version','length','format','range','file','busy','timeout','unavailable','invalid_response','cleanup_failed']:
            raw=json.dumps({'formatVersion':'0.1-experimental','valid':False,'code':code})
            self.assertEqual(self.evaluate('decode('+json.dumps(raw)+')'),{'code':code})
        unicode_value=json.loads(valid);unicode_value['theme']['author']='Maré'
        raw=json.dumps(unicode_value,ensure_ascii=False)
        padded=raw+' '*(65536-len(raw.encode('utf-8')))
        self.assertEqual(self.evaluate('decode('+json.dumps(padded)+').code'),'')
        self.assertEqual(self.evaluate('decode('+json.dumps(padded+' ')+').code'),'invalid_response')
        self.assertTrue(canonical)

    def test_timeout_budget_starts_before_loading_publication_can_reenter(self):
        self.evaluate('appearance.themeFileTimeoutMs=20')
        self.start()
        def block_loading():
            if self.evaluate('appearance.themeFileLoading'):QTest.qWait(80)
        self.state.themeFileLoadingChanged.connect(block_loading)
        try:self.accept()
        finally:self.state.themeFileLoadingChanged.disconnect(block_loading)
        self.assertEqual(self.evaluate('transport.requests.length'),0,'Expired accept must not dispatch after a reentrant loading observer')
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertEqual(self.evaluate('appearance.themeErrors[0].code'),'timeout')

    def test_timeout_late_reply_new_read_and_same_text_error_recovery(self):
        self.evaluate('appearance.themeFileTimeoutMs=25;appearance.setToken("radius",13)')
        good=self.evaluate('JSON.stringify(appearance.effective)')
        self.start();self.assertTrue(self.accept());QTest.qWait(100)
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertEqual(self.evaluate('appearance.themeErrors[0].code'),'timeout')
        self.evaluate('transport.succeed(0,'+json.dumps(self.success())+')')
        self.assertEqual(self.evaluate('appearance.themeText'),'')
        self.assertEqual(self.evaluate('JSON.stringify(appearance.effective)'),good)
        self.start();self.assertTrue(self.accept())
        self.evaluate('transport.succeed(1,'+json.dumps(self.success())+')')
        text=self.evaluate('appearance.themeText')
        self.assertEqual(self.evaluate('appearance.themeError'),'')
        self.start();self.assertTrue(self.accept())
        failure=json.dumps({'formatVersion':'0.1-experimental','valid':False,'code':'file'})
        self.evaluate('transport.succeed(2,'+json.dumps(failure)+')')
        self.assertTrue(self.evaluate('appearance.themeError.length>0'))
        self.assertEqual(self.evaluate('appearance.themeText'),text)
        self.start();self.assertTrue(self.accept())
        self.evaluate('transport.succeed(3,'+json.dumps(self.success())+')')
        self.assertEqual(self.evaluate('appearance.themeText'),text)
        self.assertEqual(self.evaluate('appearance.themeError'),'')
        self.assertTrue(self.evaluate('appearance.themePending'))
        self.assertEqual(self.evaluate('JSON.stringify(appearance.effective)'),good)
        self.assertEqual(self.evaluate('configuration.writes'),0)

    def test_newer_selection_at_selecting_and_loading_publications_wins(self):
        self.evaluate('appearance.themeFileTransport=transport;appearance.themeFileSelectingChanged.connect(function newer(){if(!appearance.themeFileSelecting)return;appearance.themeFileSelectingChanged.disconnect(newer);token2=appearance.beginThemeFileSelection(otherOwner);})')
        self.evaluate('token=appearance.beginThemeFileSelection(owner)')
        self.assertTrue(self.evaluate('token===null && token2!==null && appearance.themeFileSelecting'))
        self.assertFalse(self.evaluate('appearance.cancelThemeFileSelection(token)'))
        self.evaluate('appearance.cancelThemeFileSelection(token2)')
        self.start()
        self.evaluate('appearance.themeFileLoadingChanged.connect(function newer(){if(!appearance.themeFileLoading)return;appearance.themeFileLoadingChanged.disconnect(newer);token2=appearance.beginThemeFileSelection(otherOwner);})')
        self.assertFalse(self.accept())
        self.assertTrue(self.evaluate('appearance.themeFileSelecting'))
        self.assertEqual(self.evaluate('transport.requests.length'),0)
        self.assertTrue(self.evaluate('appearance.acceptThemeFileSelection(token2,"file:///synthetic/new.json")'))
        self.assertEqual(self.evaluate('transport.requests.length'),1)
        self.evaluate('transport.succeed(0,'+json.dumps(self.success())+')')
        self.assertFalse(self.evaluate('appearance.busy'))

    def test_response_publications_preserve_newer_input_aba_and_token_preview(self):
        for signal,body in [
            ('themeTextChanged','const same=appearance.themeText;appearance.setThemeText("new input");appearance.setThemeText(same);'),
            ('themePendingChanged','appearance.setToken("radius",17);'),
            ('themeErrorChanged','token2=appearance.beginThemeFileSelection(otherOwner);')]:
            with self.subTest(signal=signal):
                self.evaluate('appearance.cancel();appearance.begin()')
                self.start();self.assertTrue(self.accept())
                index=self.evaluate('transport.requests.length-1')
                self.evaluate('appearance.'+signal+'.connect(function newer(){appearance.'+signal+'.disconnect(newer);'+body+'})')
                raw=json.dumps({'formatVersion':'0.1-experimental','valid':False,'code':'file'}) if signal=='themeErrorChanged' else self.success()
                self.evaluate('transport.succeed('+str(index)+','+json.dumps(raw)+')')
                if signal=='themeErrorChanged':
                    self.assertTrue(self.evaluate('appearance.themeFileSelecting && token2!==null'))
                    self.assertTrue(self.evaluate('appearance.cancelThemeFileSelection(token2)'))
                elif signal=='themePendingChanged':
                    self.assertEqual(self.evaluate('appearance.effective.tokens.radius'),17)
                    self.assertTrue(self.evaluate('appearance.themePending'))
                else:
                    self.assertTrue(self.evaluate('appearance.themePending'))
                self.assertEqual(self.evaluate('configuration.writes'),0)

    def test_invalidation_publication_cannot_overwrite_newer_edit_or_selection(self):
        self.start()
        self.evaluate('appearance.busyChanged.connect(function newer(){if(appearance.busy)return;appearance.busyChanged.disconnect(newer);appearance.setToken("radius",17);})')
        self.evaluate('appearance.restoreDefaults()')
        self.assertEqual(self.evaluate('appearance.effective.tokens.radius'),17)
        self.start()
        self.evaluate('appearance.busyChanged.connect(function newer(){if(appearance.busy)return;appearance.busyChanged.disconnect(newer);token2=appearance.beginThemeFileSelection(otherOwner);})')
        self.evaluate('appearance.setThemeText("old cancelled edit")')
        self.assertTrue(self.evaluate('appearance.themeFileSelecting && token2!==null'))
        self.assertEqual(self.evaluate('appearance.themeText'),'')
        self.assertEqual(self.evaluate('configuration.writes'),0)

    def test_owner_scope_saved_configuration_aba_and_wrong_tokens_are_passive(self):
        self.start();self.assertTrue(self.accept())
        self.evaluate('token2=appearance.beginThemeFileSelection(otherOwner)')
        self.assertFalse(self.evaluate('appearance.acceptThemeFileSelection(token,"file:///old")'))
        self.assertFalse(self.evaluate('appearance.cancelThemeFileSelection(token)'))
        self.evaluate('transport.succeed(0,'+json.dumps(self.success())+')')
        self.assertTrue(self.evaluate('appearance.themeFileSelecting'))
        self.assertEqual(self.evaluate('appearance.themeText'),'')
        self.evaluate('appearance.cancelThemeFileSelection(token2)')
        self.start();self.assertTrue(self.accept())
        self.evaluate('appearance.scopeKey="other";appearance.scopeKey="legacy";appearance.begin()')
        self.evaluate('transport.succeed(1,'+json.dumps(self.success())+')')
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertEqual(self.evaluate('appearance.themeText'),'')
        self.start();self.assertTrue(self.accept())
        qml='import QtQml; QtObject { property string appearanceJSON: ""; property string theme: "glass"; property int iconSize:42; property bool animations:true }'
        other=self.evaluate('Qt.createQmlObject('+json.dumps(qml)+',owner)')
        original=self.evaluate('configuration')
        self.state.setProperty('configuration',other);self.state.setProperty('configuration',original)
        self.assertFalse(self.evaluate('appearance.busy'))
        self.evaluate('transport.succeed(2,'+json.dumps(self.success())+')')
        self.assertEqual(self.evaluate('appearance.themeText'),'')
        self.start();self.assertTrue(self.accept())
        self.evaluate('configuration.appearanceJSON="invalid saved";configuration.appearanceJSON=""')
        self.assertFalse(self.evaluate('appearance.busy'))
        self.evaluate('transport.succeed(3,'+json.dumps(self.success())+')')
        self.assertEqual(self.evaluate('appearance.themeText'),'')
        # UI cancels its exact token on owner destruction; this remains safe even
        # after QObject ownership has vanished, and late transport cannot revive it.
        self.start();self.assertTrue(self.accept())
        self.evaluate('owner').deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.assertTrue(self.evaluate('appearance.cancelThemeFileSelection(token)'))
        self.evaluate('transport.succeed(4,'+json.dumps(self.success())+')')
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertEqual(self.evaluate('appearance.themeText'),'')

    def test_transport_failures_and_cancel_keep_last_preview_and_do_not_echo_paths(self):
        self.evaluate('appearance.setToken("radius",13)')
        good=self.evaluate('JSON.stringify(appearance.effective)')
        self.start();self.assertTrue(self.accept())
        self.evaluate('transport.reject(0)')
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertEqual(self.evaluate('appearance.themeErrors[0].code'),'unavailable')
        self.assertNotIn('private',self.evaluate('appearance.themeError'))
        self.start();self.evaluate('transport.throwOnLoad=true')
        self.assertFalse(self.accept())
        self.assertFalse(self.evaluate('appearance.busy'))
        self.assertEqual(self.evaluate('appearance.themeErrors[0].code'),'unavailable')
        self.evaluate('transport.throwOnLoad=false;appearance.clearThemeInput()')
        self.start();self.assertTrue(self.accept())
        self.assertTrue(self.evaluate('appearance.cancelThemeFileSelection(token)'))
        self.evaluate('transport.succeed(1,'+json.dumps(self.success())+')')
        self.assertEqual(self.evaluate('appearance.themeText'),'')
        self.assertEqual(self.evaluate('JSON.stringify(appearance.effective)'),good)
        self.assertEqual(self.evaluate('configuration.writes'),0)
        self.evaluate('appearance.clearThemeInput()')
        self.assertTrue(self.evaluate('appearance.canApply'))

    def test_one_timeout_per_accept_not_selection_and_previous_deadline_cannot_hit_new_read(self):
        self.evaluate('appearance.themeFileTimeoutMs=25')
        self.start();QTest.qWait(80)
        self.assertTrue(self.evaluate('appearance.themeFileSelecting'))
        self.assertEqual(self.evaluate('appearance.themeError'),'')
        self.assertTrue(self.accept());QTest.qWait(10)
        self.evaluate('appearance.cancelThemeFileSelection(token);appearance.themeFileTimeoutMs=160')
        self.start();self.assertTrue(self.accept());QTest.qWait(70)
        self.assertTrue(self.evaluate('appearance.themeFileLoading'))
        self.evaluate('transport.succeed(1,'+json.dumps(self.success())+')')
        text=self.evaluate('appearance.themeText')
        QTest.qWait(180)
        self.assertEqual(self.evaluate('appearance.themeError'),'')
        self.assertEqual(self.evaluate('appearance.themeText'),text)
        self.assertFalse(self.evaluate('appearance.busy'))
        for name in ['themeFileSelecting','themeFileLoading','busy']:
            prop=self.state.metaObject().property(self.state.metaObject().indexOfProperty(name))
            self.assertFalse(prop.isWritable(),name)

    def test_input_clear_and_callers_preserve_reentrant_received_file(self):
        for command in ['appearance.clearThemeInput()', 'appearance.setThemeText("")',
                        'appearance.begin()', 'appearance.selectTheme("paper")',
                        'appearance.restoreDefaults()', 'appearance.cancel()']:
            with self.subTest(command=command):
                self.evaluate('appearance.cancel();appearance.begin();appearance.setThemeText("old input");appearance.themeFileTransport=transport')
                before=self.evaluate('JSON.stringify(appearance.effective)')
                index=self.evaluate('transport.requests.length')
                self.evaluate('appearance.themeTextChanged.connect(function newer(){appearance.themeTextChanged.disconnect(newer);'
                    'token2=appearance.beginThemeFileSelection(otherOwner);'
                    'appearance.acceptThemeFileSelection(token2,"file:///synthetic/new.json");'
                    'transport.succeed('+str(index)+','+json.dumps(self.success())+');})')
                self.assertFalse(self.evaluate(command))
                self.assertEqual(json.loads(self.evaluate('appearance.themeText')),self.theme())
                self.assertTrue(self.evaluate('appearance.editing && appearance.themePending'))
                self.assertFalse(self.evaluate('appearance.canApply || appearance.busy'))
                self.assertEqual(self.evaluate('JSON.stringify(appearance.effective)'),before)
                self.assertEqual(self.evaluate('configuration.writes'),0)

    def test_loading_owner_destroyed_without_cancel_releases_at_deadline(self):
        self.evaluate('appearance.themeFileTimeoutMs=35')
        self.start()
        self.assertTrue(self.accept())
        self.assertTrue(self.evaluate('appearance.themeFileLoading && appearance.busy && appearance.dirty'))
        self.evaluate('owner').deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        # No cancelThemeFileSelection: loading has its own bounded timeout.
        QTest.qWait(180)
        self.assertEqual(self.evaluate('configuration.writes'), 0)
        self.assertFalse(self.evaluate('appearance.busy'), 'DEAD_OWNER_LOADING_TIMEOUT_LEFT_BUSY')
        self.assertFalse(self.evaluate('appearance.dirty'))
        self.assertFalse(self.evaluate('appearance.themeFileLoading'))
        # Late old completion cannot revive input or touch a newer request.
        self.evaluate('token2=appearance.beginThemeFileSelection(otherOwner)')
        self.assertTrue(self.evaluate('token2!==null && appearance.themeFileSelecting'))
        self.evaluate('transport.succeed(0,' + __import__('json').dumps(self.success()) + ')')
        self.assertTrue(self.evaluate('appearance.themeFileSelecting'))
        self.assertEqual(self.evaluate('appearance.themeText'), '')
        self.assertEqual(self.evaluate('configuration.writes'), 0)


    def test_old_clear_cannot_approve_reentrant_new_file_without_preview(self):
        self.evaluate('appearance.themeFileTransport=transport;appearance.setThemeText("old input")')
        self.evaluate('appearance.themeTextChanged.connect(function newer(){'
            'appearance.themeTextChanged.disconnect(newer);'
            'token2=appearance.beginThemeFileSelection(otherOwner);'
            'appearance.acceptThemeFileSelection(token2,"file:///synthetic/new-theme.json");'
            'transport.succeed(0,'+json.dumps(self.success())+');})')
        self.evaluate('appearance.clearThemeInput()')
        facts = {
            'themeTextIsNewTheme': json.loads(self.evaluate('appearance.themeText')) == self.theme(),
            'themePending': self.evaluate('appearance.themePending'),
            'canApply': self.evaluate('appearance.canApply'),
            'busy': self.evaluate('appearance.busy'),
            'writes': self.evaluate('configuration.writes'),
            'requests': self.evaluate('transport.requests.length'),
        }
        print(json.dumps(facts))
        self.assertTrue(facts['themeTextIsNewTheme'])
        self.assertEqual(facts['writes'], 0)
        self.assertEqual(facts['requests'], 1)
        self.assertTrue(facts['themePending'], 'OLD_CLEAR_REMOVED_NEW_FILE_PREVIEW_OBLIGATION')
        self.assertFalse(facts['canApply'])
