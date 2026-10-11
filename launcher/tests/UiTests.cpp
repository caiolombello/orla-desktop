#include <QtTest>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QQuickItem>
#include <QDir>
#include <QFile>
#include <QTemporaryDir>
#include "AiProviderController.h"
#include "AiTextController.h"
#include "LauncherController.h"
#include "SteamProviderController.h"
#include "BusChecks.h"

// Synthetic Qt key events verify handlers only; they do not qualify Wayland/global-shortcut focus.
class UiTests final : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void initTestCase() { verifyPrivateTestBus(); }
    void ownWindowRendersResultsWithoutExecuting()
    {
        LauncherController controller;
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-ai-helper.py"));
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-ai-text-helper.py"));
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-steam-helper.py"));
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        QVERIFY(QTest::qWaitForWindowExposed(window));
        const QString capture = qEnvironmentVariable("ORLA_UI_CAPTURE_DIR");
        const auto snapshot = [&](const QString &name) {
            QTest::qWait(100);
            const QImage image = window->grabWindow();
            QVERIFY(!image.isNull());
            if (!capture.isEmpty()) QVERIFY(image.save(QDir(capture).filePath(name + QStringLiteral(".png"))));
        };
        snapshot(QStringLiteral("idle"));
        controller.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("ready"), 5000);
        QCOMPARE(controller.rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        QVERIFY(!controller.rows().first().toMap().value("actions").toList().isEmpty());
        snapshot(QStringLiteral("calculator"));
        window->resize(440, 380);
        snapshot(QStringLiteral("calculator-narrow"));
        controller.setQuery(QStringLiteral("OrlaNoResultOwnedNonexistent573849"));
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("empty"), 5000);
        snapshot(QStringLiteral("empty"));
        controller.setQuery(QString(513, QLatin1Char('x')));
        QCOMPARE(controller.status(), QStringLiteral("error"));
        snapshot(QStringLiteral("error"));
        controller.dismiss();
    }
    void searchKeyboardAndEscape()
    {
        LauncherController controller;
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-ai-helper.py"));
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-ai-text-helper.py"));
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-steam-helper.py"));
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        QVERIFY(search);
        search->forceActiveFocus();
        QTest::keyClick(window, Qt::Key_2);
        QTest::keyClick(window, Qt::Key_Plus);
        QTest::keyClick(window, Qt::Key_2);
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("ready"), 5000);
        QCOMPARE(controller.rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        QTest::keyClick(window, Qt::Key_Down);
        QCOMPARE(controller.selectedIndex(), 0);
        QTest::keyClick(window, Qt::Key_Up);
        QCOMPARE(controller.selectedIndex(), 0);
        QTest::keyClick(window, Qt::Key_Return);
        QCOMPARE(controller.query(), QStringLiteral("4"));
        QSignalSpy closed(&controller, &LauncherController::closeRequested);
        QTest::keyClick(window, Qt::Key_Escape);
        QCOMPARE(closed.count(), 1);
        QVERIFY(controller.rows().isEmpty());
    }
    void aiPanelRequiresExplicitActionsAndEscapeRestoresSearchFocus()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString probeMarker = directory.filePath(QStringLiteral("probe-started"));
        const QByteArray caps = R"({"installation":"absent","anonymous_protocol":"absent","authentication":"unknown","inference":"absent","cancellation":"absent","usage_reporting":"unknown"})";
        const QByteArray providers = QByteArray("[")
            + R"({"id":"codex","displayName":"Codex","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"owned_app_server","messageCode":"cli_not_found"},)"
            + R"({"id":"claude","displayName":"Claude Code","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"official_terminal_handoff","messageCode":"cli_not_found"},)"
            + R"({"id":"opencode","displayName":"OpenCode","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"selected_local_server","messageCode":"cli_not_found"},)"
            + R"({"id":"ollama","displayName":"Ollama","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"selected_local_server","messageCode":"cli_not_found"},)"
            + R"({"id":"lmstudio","displayName":"LM Studio","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"selected_local_server","messageCode":"cli_not_found"}])";
        const QByteArray document = QByteArray("{\"schemaVersion\":1,\"providers\":") + providers + "}\n";
        const QByteArray probeDocument = R"({"schemaVersion":1,"provider":{"id":"codex","displayName":"Codex","enabled":false,"clientVersion":"0.162.1","capabilities":{"installation":"supported","anonymous_protocol":"supported","authentication":"unknown","inference":"unknown","cancellation":"unknown","usage_reporting":"unknown"},"route":"owned_app_server","messageCode":"anonymous_protocol_supported"}})" "\n";
        const QString helper = directory.filePath(QStringLiteral("helper.py"));
        QFile helperFile(helper);
        QVERIFY(helperFile.open(QIODevice::WriteOnly));
        helperFile.write("import base64,pathlib,sys\nargs=sys.argv[1:]\nif len(args) == 5 and args[0] == 'detect' and args[1] == '--runtime-root' and args[3] == '--runtime-root-id':\n pathlib.Path(r'");
        helperFile.write(marker.toUtf8());
        helperFile.write("').touch()\n sys.stdout.buffer.write(base64.b64decode('");
        helperFile.write(document.toBase64());
        helperFile.write("'))\nelif len(args) == 5 and args[0] == 'probe-codex-anonymous' and args[1] == '--runtime-root' and args[3] == '--runtime-root-id':\n pathlib.Path(r'");
        helperFile.write(probeMarker.toUtf8());
        helperFile.write("').touch()\n sys.stdout.buffer.write(base64.b64decode('");
        helperFile.write(probeDocument.toBase64());
        helperFile.write("'))\nelse:\n raise SystemExit(2)\n");
        helperFile.close();

        LauncherController controller;
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-ai-text-helper.py"));
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-steam-helper.py"));
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        auto *entry = window->findChild<QQuickItem *>(QStringLiteral("aiEntryButton"));
        auto *panel = window->findChild<QQuickItem *>(QStringLiteral("aiSettings"));
        auto *back = window->findChild<QQuickItem *>(QStringLiteral("aiBackButton"));
        auto *discover = window->findChild<QQuickItem *>(QStringLiteral("aiDiscoverButton"));
        auto *probe = window->findChild<QQuickItem *>(QStringLiteral("aiProbeButton"));
        auto *task = window->findChild<QQuickItem *>(QStringLiteral("aiTextTask"));
        auto *model = window->findChild<QQuickItem *>(QStringLiteral("aiTextModel"));
        auto *host = window->findChild<QQuickItem *>(QStringLiteral("aiTextHost"));
        auto *port = window->findChild<QQuickItem *>(QStringLiteral("aiTextPort"));
        auto *text = window->findChild<QQuickItem *>(QStringLiteral("aiTextInput"));
        auto *consent = window->findChild<QQuickItem *>(QStringLiteral("aiTextConsent"));
        auto *generate = window->findChild<QQuickItem *>(QStringLiteral("aiTextGenerate"));
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        auto *header = window->findChild<QQuickItem *>(QStringLiteral("launcherHeader"));
        auto *scroll = window->findChild<QQuickItem *>(QStringLiteral("aiSettingsScroll"));
        QVERIFY(entry && panel && back && discover && probe && task && model && host && port
                && text && consent && generate && search && header && scroll);
        const QString capture = qEnvironmentVariable("ORLA_UI_CAPTURE_DIR");
        const auto snapshot = [&](const QString &name) {
            if (capture.isEmpty()) return;
            QTest::qWait(100);
            const QImage image = window->grabWindow();
            QVERIFY(!image.isNull());
            QVERIFY(image.save(QDir(capture).filePath(name + QStringLiteral(".png"))));
        };
        QVERIFY(!QFile::exists(marker));
        QVERIFY(QMetaObject::invokeMethod(entry, "click"));
        QVERIFY(panel->isVisible());
        QVERIFY(back->hasActiveFocus());
        QVERIFY(!QFile::exists(marker));
        QCOMPARE(ai.status(), QStringLiteral("disabled"));
        QCOMPARE(aiText.status(), QStringLiteral("disabled"));
        QVERIFY(!aiText.busy());
        QVERIFY(!generate->isEnabled());
        QVERIFY(text->setProperty("text", QStringLiteral("Texto explícito de teste")));
        QVERIFY(consent->setProperty("checked", true));
        QTRY_VERIFY(generate->isEnabled());
        QVERIFY(model->setProperty("text", QStringLiteral("modelo-teste:1")));
        QVERIFY(QMetaObject::invokeMethod(model, "textEdited"));
        QCOMPARE(consent->property("checked").toBool(), false);
        QVERIFY(consent->setProperty("checked", true));
        QVERIFY(host->setProperty("currentIndex", 1));
        QVERIFY(QMetaObject::invokeMethod(host, "activated", Q_ARG(int, 1)));
        QCOMPARE(consent->property("checked").toBool(), false);
        QVERIFY(consent->setProperty("checked", true));
        QVERIFY(port->setProperty("value", 11435));
        QVERIFY(QMetaObject::invokeMethod(port, "valueModified"));
        QCOMPARE(consent->property("checked").toBool(), false);
        QVERIFY(!aiText.busy()); // Editing and granting consent never creates a process.
        window->resize(440, 380);
        snapshot(QStringLiteral("ai-disabled-narrow"));
        QTest::keyClick(window, Qt::Key_Tab);
        QVERIFY(discover->hasActiveFocus());
        QTest::keyClick(window, Qt::Key_Space);
        QTRY_COMPARE_WITH_TIMEOUT(ai.providers().size(), 5, 3000);
        QVERIFY(!ai.busy());
        QVERIFY(header->mapToScene(QPointF()).y() >= 20);
        QVERIFY(QFile::exists(marker));
        snapshot(QStringLiteral("ai-detected-narrow"));
        QVERIFY(!QFile::exists(probeMarker));
        QTest::keyClick(window, Qt::Key_Tab);
        QVERIFY(probe->hasActiveFocus());
        QTest::keyClick(window, Qt::Key_Space);
        QTRY_COMPARE_WITH_TIMEOUT(ai.providers().first().toMap().value("messageCode").toString(),
                                  QStringLiteral("anonymous_protocol_supported"), 3000);
        QVERIFY(!ai.busy());
        QVERIFY(QFile::exists(probeMarker));
        snapshot(QStringLiteral("ai-protocol-narrow"));
        auto *scrollContent = scroll->property("contentItem").value<QObject *>();
        QVERIFY(scrollContent);
        const qreal maximumContentY = qMax<qreal>(0, scrollContent->property("contentHeight").toReal()
                                                     - scrollContent->property("height").toReal());
        QVERIFY(maximumContentY > 0);
        QVERIFY(scrollContent->setProperty("contentY", maximumContentY));
        snapshot(QStringLiteral("ai-text-config-narrow"));
        QTest::keyClick(window, Qt::Key_Escape);
        QVERIFY(!panel->isVisible());
        QVERIFY(search->hasActiveFocus());
        QVERIFY(QMetaObject::invokeMethod(entry, "click"));
        QCOMPARE(ai.providers().size(), 5); // Session report survives panel navigation.
        QVERIFY(QMetaObject::invokeMethod(back, "click"));
        QVERIFY(search->hasActiveFocus());
    }

    void steamPanelRequiresExplicitLoadAndEscapeRestoresSearchFocus()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("steam-started"));
        const QByteArray document = R"({"apps":[],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"available"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"available"}],"schema_version":"0.1-experimental","status":"available"})" "\n";
        const QString helper = directory.filePath(QStringLiteral("steam-helper.py"));
        QFile helperFile(helper);
        QVERIFY(helperFile.open(QIODevice::WriteOnly));
        helperFile.write("import base64,pathlib,sys\npathlib.Path(r'");
        helperFile.write(marker.toUtf8());
        helperFile.write("').touch()\nsys.stdout.buffer.write(base64.b64decode('");
        helperFile.write(document.toBase64());
        helperFile.write("'))\n");
        helperFile.close();

        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-ai-helper.py"));
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), QStringLiteral("/missing/orla-ai-text-helper.py"));
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        LauncherController controller(&steam);
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        auto *entry = window->findChild<QQuickItem *>(QStringLiteral("steamEntryButton"));
        auto *panel = window->findChild<QQuickItem *>(QStringLiteral("steamSettings"));
        auto *back = window->findChild<QQuickItem *>(QStringLiteral("steamBackButton"));
        auto *input = window->findChild<QQuickItem *>(QStringLiteral("steamRootInput"));
        auto *scan = window->findChild<QQuickItem *>(QStringLiteral("steamScanButton"));
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        QVERIFY(entry && panel && back && input && scan && search);
        QVERIFY(!QFile::exists(marker));
        QVERIFY(QMetaObject::invokeMethod(entry, "click"));
        QVERIFY(panel->isVisible());
        QVERIFY(back->hasActiveFocus());
        QVERIFY(!QFile::exists(marker));
        QVERIFY(input->setProperty("text", QStringLiteral("native=/synthetic/root")));
        QVERIFY(QMetaObject::invokeMethod(scan, "click"));
        QTRY_COMPARE_WITH_TIMEOUT(steam.status(), QStringLiteral("available"), 3000);
        QVERIFY(QFile::exists(marker));
        QTest::keyClick(window, Qt::Key_Escape);
        QVERIFY(!panel->isVisible());
        QVERIFY(search->hasActiveFocus());
    }

    void aiTextPanelGeneratesStreamsLocksAndCancels()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("ai-text-started"));
        const QString helper = directory.filePath(QStringLiteral("ai-text-stream.py"));
        QFile helperFile(helper);
        QVERIFY(helperFile.open(QIODevice::WriteOnly));
        helperFile.write("import json,pathlib,sys,time\npathlib.Path(r'");
        helperFile.write(marker.toUtf8());
        helperFile.write("').touch()\nrequest=json.loads(sys.stdin.buffer.readline())\nbase={'schemaVersion':1,'requestId':request['requestId']}\nevents=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='resultado parcial')]\nfor event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\ntime.sleep(60)\n");
        helperFile.close();

        LauncherController controller;
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                directory.filePath(QStringLiteral("missing-ai.py")));
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                      directory.filePath(QStringLiteral("missing-steam.py")));
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        auto *entry = window->findChild<QQuickItem *>(QStringLiteral("aiEntryButton"));
        auto *back = window->findChild<QQuickItem *>(QStringLiteral("aiBackButton"));
        auto *model = window->findChild<QQuickItem *>(QStringLiteral("aiTextModel"));
        auto *text = window->findChild<QQuickItem *>(QStringLiteral("aiTextInput"));
        auto *consent = window->findChild<QQuickItem *>(QStringLiteral("aiTextConsent"));
        auto *generate = window->findChild<QQuickItem *>(QStringLiteral("aiTextGenerate"));
        auto *result = window->findChild<QQuickItem *>(QStringLiteral("aiTextResult"));
        auto *copy = window->findChild<QQuickItem *>(QStringLiteral("aiTextCopy"));
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        QVERIFY(entry && back && model && text && consent && generate && result && copy && search);

        QVERIFY(!QFile::exists(marker));
        QVERIFY(QMetaObject::invokeMethod(entry, "click"));
        QVERIFY(text->setProperty("text", QStringLiteral("Texto controlado pela fixture")));
        QVERIFY(consent->setProperty("checked", true));
        QVERIFY(!QFile::exists(marker));
        QTRY_VERIFY(generate->isEnabled());
        QVERIFY(QMetaObject::invokeMethod(generate, "click"));
        QTRY_VERIFY_WITH_TIMEOUT(aiText.busy() && QFile::exists(marker), 1500);
        QVERIFY(!model->isEnabled());
        QVERIFY(!text->isEnabled());
        QCOMPARE(generate->property("text").toString(), QStringLiteral("Cancelar"));
        QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("resultado parcial"), 1500);
        QCOMPARE(result->property("readOnly").toBool(), true);
        QVERIFY(result->isVisible());
        QVERIFY(copy->isEnabled()); // Copy remains explicit; the test does not touch the host clipboard.

        QVERIFY(QMetaObject::invokeMethod(generate, "click"));
        QTRY_VERIFY_WITH_TIMEOUT(!aiText.busy(), 2500);
        QVERIFY(aiText.status() == QStringLiteral("cancelled_confirmed")
                || aiText.status() == QStringLiteral("cancelled_unconfirmed"));
        QCOMPARE(aiText.output(), QStringLiteral("resultado parcial"));
        QVERIFY(model->isEnabled());
        QVERIFY(text->isEnabled());
        QVERIFY(QMetaObject::invokeMethod(back, "click"));
        QVERIFY(search->hasActiveFocus());
    }

    void steamBusyStateDisablesCompetingActionsAndShowsCancel()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("steam-busy"));
        const QString helper = directory.filePath(QStringLiteral("steam-sleep.py"));
        QFile helperFile(helper);
        QVERIFY(helperFile.open(QIODevice::WriteOnly));
        helperFile.write("import pathlib,signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\npathlib.Path(r'");
        helperFile.write(marker.toUtf8());
        helperFile.write("').touch()\ntime.sleep(60)\n");
        helperFile.close();

        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                directory.filePath(QStringLiteral("missing-ai.py")));
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                directory.filePath(QStringLiteral("missing-ai-text.py")));
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        LauncherController controller(&steam);
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        auto *entry = window->findChild<QQuickItem *>(QStringLiteral("steamEntryButton"));
        auto *input = window->findChild<QQuickItem *>(QStringLiteral("steamRootInput"));
        auto *scan = window->findChild<QQuickItem *>(QStringLiteral("steamScanButton"));
        auto *cancel = window->findChild<QQuickItem *>(QStringLiteral("steamCancelButton"));
        auto *downloads = window->findChild<QQuickItem *>(QStringLiteral("steamDownloadsButton"));
        QVERIFY(entry && input && scan && cancel && downloads);
        QVERIFY(QMetaObject::invokeMethod(entry, "click"));
        QVERIFY(input->setProperty("text", QStringLiteral("native=/synthetic/root")));
        QVERIFY(QMetaObject::invokeMethod(scan, "click"));
        QTRY_VERIFY_WITH_TIMEOUT(steam.busy() && QFile::exists(marker), 1000);
        QTRY_VERIFY_WITH_TIMEOUT(!scan->isEnabled() && cancel->isVisible() && !downloads->isEnabled(), 1000);
        QVERIFY(QMetaObject::invokeMethod(cancel, "click"));
        QTRY_VERIFY_WITH_TIMEOUT(!steam.busy(), 7000);
    }

    void threeOwnerCloseBarrierWaitsForSteamAndAiTextExactlyOnce()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString aiHelper = directory.filePath(QStringLiteral("ai-text-sleep.py"));
        QFile aiHelperFile(aiHelper);
        QVERIFY(aiHelperFile.open(QIODevice::WriteOnly));
        aiHelperFile.write(
            "import json,sys,time\n"
            "request=json.loads(sys.stdin.buffer.readline())\n"
            "base={'schemaVersion':1,'requestId':request['requestId']}\n"
            "events=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='parcial')]\n"
            "for event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\n"
            "time.sleep(60)\n");
        aiHelperFile.close();

        const QString steamHelper = directory.filePath(QStringLiteral("steam-resistant.py"));
        QFile steamHelperFile(steamHelper);
        QVERIFY(steamHelperFile.open(QIODevice::WriteOnly));
        steamHelperFile.write("import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(60)\n");
        steamHelperFile.close();

        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                directory.filePath(QStringLiteral("missing-ai.py")));
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), aiHelper);
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), steamHelper);
        LauncherController controller(&steam);
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);

        steam.scan({QStringLiteral("native=/synthetic/root")});
        aiText.generate(QStringLiteral("barrier-request"), QStringLiteral("summarize"),
                        QVariant(), QStringLiteral("texto"), QStringLiteral("modelo:1"),
                        QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(steam.busy() && aiText.busy(), 1500);
        QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("parcial"), 1500);

        QSignalSpy dismissed(&controller, &LauncherController::closeRequested);
        QVERIFY(QMetaObject::invokeMethod(window, "requestDismiss",
                                          Q_ARG(QVariant, QVariant(false))));
        QCOMPARE(window->property("pendingDismiss").toBool(), true);
        QTRY_VERIFY_WITH_TIMEOUT(!aiText.busy(), 2000);
        QVERIFY(steam.busy());
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(window->property("pendingDismiss").toBool(), true);
        QTRY_VERIFY_WITH_TIMEOUT(!steam.busy(), 7000);
        QTRY_COMPARE_WITH_TIMEOUT(dismissed.count(), 1, 1000);
        QCOMPARE(window->property("pendingDismiss").toBool(), false);
        QTest::qWait(100);
        QCOMPARE(dismissed.count(), 1);
    }

    void windowCloseAndQuitWaitForAllThreeOwnersExactlyOnce()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());

        const QString providerHelper = directory.filePath(QStringLiteral("ai-provider-resistant.py"));
        QFile providerHelperFile(providerHelper);
        QVERIFY(providerHelperFile.open(QIODevice::WriteOnly));
        providerHelperFile.write(
            "import signal,time\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            "time.sleep(60)\n");
        providerHelperFile.close();

        const QString textHelper = directory.filePath(QStringLiteral("ai-text-close.py"));
        QFile textHelperFile(textHelper);
        QVERIFY(textHelperFile.open(QIODevice::WriteOnly));
        textHelperFile.write(
            "import json,sys,time\n"
            "request=json.loads(sys.stdin.buffer.readline())\n"
            "base={'schemaVersion':1,'requestId':request['requestId']}\n"
            "events=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='parcial-close')]\n"
            "for event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\n"
            "time.sleep(60)\n");
        textHelperFile.close();

        const QString steamHelper = directory.filePath(QStringLiteral("steam-close-resistant.py"));
        QFile steamHelperFile(steamHelper);
        QVERIFY(steamHelperFile.open(QIODevice::WriteOnly));
        steamHelperFile.write(
            "import signal,time\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            "time.sleep(60)\n");
        steamHelperFile.close();

        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), providerHelper,
                                {}, nullptr, {}, 500);
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), textHelper,
                                {}, nullptr, {}, 100);
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), steamHelper);
        LauncherController controller(&steam);
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("aiProviders", &ai);
        engine.rootContext()->setContextProperty("aiText", &aiText);
        engine.rootContext()->setContextProperty("steamProvider", &steam);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        QVERIFY(QTest::qWaitForWindowExposed(window));

        ai.discover();
        aiText.generate(QStringLiteral("window-close-request"), QStringLiteral("summarize"),
                        QVariant(), QStringLiteral("texto"), QStringLiteral("modelo:1"),
                        QStringLiteral("127.0.0.1"), 11434, true);
        steam.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_VERIFY_WITH_TIMEOUT(ai.busy() && aiText.busy() && steam.busy(), 1500);
        QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("parcial-close"), 1500);

        QSignalSpy dismissed(&controller, &LauncherController::closeRequested);
        QSignalSpy quitRequested(&engine, &QQmlApplicationEngine::quit);
        QVERIFY(QMetaObject::invokeMethod(window, "requestDismiss",
                                          Q_ARG(QVariant, QVariant(true))));
        QCOMPARE(window->property("pendingDismiss").toBool(), true);
        QCOMPARE(window->property("pendingQuit").toBool(), true);
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(quitRequested.count(), 0);

        QVERIFY(!window->close()); // Real owned-window close reaches onClosing and is vetoed.
        QVERIFY(window->isVisible());
        QCOMPARE(window->property("pendingDismiss").toBool(), true);
        QCOMPARE(window->property("pendingQuit").toBool(), true);
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(quitRequested.count(), 0);

        QTRY_VERIFY_WITH_TIMEOUT(!aiText.busy(), 1500);
        QVERIFY(ai.busy() || steam.busy());
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(quitRequested.count(), 0);
        QVERIFY(window->isVisible());

        QTRY_VERIFY_WITH_TIMEOUT(!ai.busy(), 2500);
        QVERIFY(steam.busy());
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(quitRequested.count(), 0);

        QTRY_VERIFY_WITH_TIMEOUT(!steam.busy(), 7000);
        QTRY_COMPARE_WITH_TIMEOUT(dismissed.count(), 1, 1000);
        QTRY_COMPARE_WITH_TIMEOUT(quitRequested.count(), 1, 1000);
        QCOMPARE(window->property("pendingDismiss").toBool(), false);
        QCOMPARE(window->property("pendingQuit").toBool(), false);
        QTest::qWait(100);
        QCOMPARE(dismissed.count(), 1);
        QCOMPARE(quitRequested.count(), 1);
    }
};
QTEST_MAIN(UiTests)
#include "UiTests.moc"
