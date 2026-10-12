#include <QtTest>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QQuickItem>
#include <QJSValue>
#include <QClipboard>
#include <QPointer>
#include <QScopeGuard>
#include <QElapsedTimer>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QTemporaryDir>
#include <cerrno>
#include <csignal>
#include "AiProviderController.h"
#include "AiTextController.h"
#include "LauncherController.h"
#include "LauncherControllerTestOwner.h"
#include "SteamProviderController.h"
#include "BusChecks.h"
#include "WindowSession.h"

// Synthetic Qt key events verify handlers only; they do not qualify Wayland/global-shortcut focus.
class UiTests final : public QObject
{
    Q_OBJECT
    static bool helperReapedAndRuntimeRemoved(const QString &receipt)
    {
        QFile file(receipt);
        if (!file.open(QIODevice::ReadOnly)) return false;
        const QList<QByteArray> fields = file.readAll().split('\n');
        if (fields.size() != 2) return false;
        bool valid = false;
        const qint64 pid = fields.first().toLongLong(&valid);
        if (!valid || pid <= 0 || fields.last().isEmpty()) return false;
        errno = 0;
        if (::kill(static_cast<pid_t>(pid), 0) != -1 || errno != ESRCH) return false;
        errno = 0;
        return ::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH
            && !QFile::exists(QString::fromUtf8(fields.last()));
    }
private Q_SLOTS:
    void initTestCase() { verifyPrivateTestBus(); }
    void ownedControllerRunnersDieBeforeTheNextCalculatorFixture()
    {
        QList<QPointer<KRunner::AbstractRunner>> previousRunners;
        {
            LauncherControllerTestOwner first;
            previousRunners = first.observedRunners();
            QVERIFY(!previousRunners.isEmpty());
            first.controller().setQuery(QStringLiteral("2+2"));
            QTRY_COMPARE_WITH_TIMEOUT(first.controller().status(), QStringLiteral("ready"), 5000);
            QCOMPARE(first.controller().rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        }
        for (const auto &runner : previousRunners) QVERIFY(runner.isNull());
        LauncherControllerTestOwner second;
        second.controller().setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(second.controller().status(), QStringLiteral("ready"), 5000);
        QCOMPARE(second.controller().rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        second.controller().setQuery(QStringLiteral("3+3"));
        QTRY_COMPARE_WITH_TIMEOUT(second.controller().status(), QStringLiteral("ready"), 5000);
        QCOMPARE(second.controller().rows().first().toMap().value("title").toString(), QStringLiteral("6"));
    }

    void ownWindowRendersResultsWithoutExecuting()
    {
        LauncherControllerTestOwner controllerOwner;
        LauncherController &controller = controllerOwner.controller();
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
    void headerEntryTargetsFitAndKeepKeyboardControl_data()
    {
        QTest::addColumn<int>("width");
        QTest::newRow("narrow") << 440;
        QTest::newRow("standard") << 660;
    }

    void headerEntryTargetsFitAndKeepKeyboardControl()
    {
        QFETCH(int, width);
        LauncherControllerTestOwner controllerOwner;
        LauncherController &controller = controllerOwner.controller();
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
        window->resize(width, 420);
        QVERIFY(QTest::qWaitForWindowExposed(window));
        auto *aiEntry = window->findChild<QQuickItem *>(QStringLiteral("aiEntryButton"));
        auto *steamEntry = window->findChild<QQuickItem *>(QStringLiteral("steamEntryButton"));
        auto *steamBack = window->findChild<QQuickItem *>(QStringLiteral("steamBackButton"));
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        QVERIFY(aiEntry && steamEntry && steamBack && search);
        for (auto *entry : {aiEntry, steamEntry}) {
            QTRY_VERIFY_WITH_TIMEOUT(entry->width() >= 40 && entry->height() >= 40, 1000);
            const QRectF bounds = entry->mapRectToItem(window->contentItem(), QRectF(0, 0, entry->width(), entry->height()));
            QVERIFY(bounds.left() >= 0 && bounds.right() <= window->width());
            QVERIFY(bounds.top() >= 0 && bounds.bottom() <= search->mapToItem(window->contentItem(), QPointF()).y());
        }
        aiEntry->forceActiveFocus();
        QTest::keyClick(window, Qt::Key_Tab);
        QVERIFY(steamEntry->hasActiveFocus());
        QTest::keyClick(window, Qt::Key_Space);
        QCOMPARE(window->property("activePanel").toString(), QStringLiteral("steam"));
        QVERIFY(steamBack->hasActiveFocus());
        QVERIFY(!ai.busy() && !aiText.busy() && !steam.busy());
        QTest::keyClick(window, Qt::Key_Escape);
        QCOMPARE(window->property("activePanel").toString(), QStringLiteral("search"));
        QVERIFY(search->hasActiveFocus());
    }

    void searchKeyboardAndEscape()
    {
        LauncherControllerTestOwner controllerOwner;
        LauncherController &controller = controllerOwner.controller();
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
        const QByteArray presentCaps = R"({"installation":"supported","anonymous_protocol":"unknown","authentication":"unknown","inference":"unknown","cancellation":"unknown","usage_reporting":"unknown"})";
        const QByteArray providers = QByteArray("[")
            + R"({"id":"codex","displayName":"Codex","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"owned_app_server","messageCode":"cli_not_found"},)"
            + R"({"id":"claude","displayName":"Claude Code","enabled":false,"clientVersion":"0.162.1+WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW","capabilities":)" + presentCaps + R"(,"route":"official_terminal_handoff","messageCode":"client_version_recognized"},)"
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

        LauncherControllerTestOwner controllerOwner;
        LauncherController &controller = controllerOwner.controller();
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
        // A valid long version must wrap inside the viewport, not enlarge a hidden horizontal range.
        const auto fitsAiViewport = [&] {
            if (scroll->property("contentWidth").toReal() > scroll->property("availableWidth").toReal() + 1)
                return false;
            QList<QQuickItem *> items{panel};
            for (int i = 0; i < items.size(); ++i) {
                auto *item = items[i];
                if (!item->isVisible()) continue;
                items.append(item->childItems());
                const QRectF bounds = item->mapRectToItem(panel, QRectF(0, 0, item->width(), item->height()));
                if (bounds.left() < -1 || bounds.right() > panel->width() + 1) return false;
            }
            return true;
        };
        QTRY_VERIFY_WITH_TIMEOUT(fitsAiViewport(), 1000);
        window->resize(660, 420);
        QTRY_VERIFY_WITH_TIMEOUT(panel->width() > 500 && fitsAiViewport(), 1000);
        snapshot(QStringLiteral("ai-detected-standard"));
        window->resize(440, 380);
        QTRY_VERIFY_WITH_TIMEOUT(panel->width() < 400 && fitsAiViewport(), 1000);
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
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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

        LauncherControllerTestOwner controllerOwner;
        LauncherController &controller = controllerOwner.controller();
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

    void aiTextUsageLabelReflectsReportedStatus_data()
    {
        QTest::addColumn<QByteArray>("usage");
        QTest::addColumn<QString>("expectedLabel");
        QTest::newRow("empty-running") << QByteArray()
            << QStringLiteral("Uso: desconhecido · Custo: não informado");
        QTest::newRow("unknown-completed")
            << QByteArray(R"({"status":"unknown","inputTokens":null,"outputTokens":null,"totalTokens":null})")
            << QStringLiteral("Uso: desconhecido · Custo: não informado");
        QTest::newRow("reported-completed")
            << QByteArray(R"({"status":"reported","inputTokens":3,"outputTokens":5,"totalTokens":8})")
            << QStringLiteral("Uso: reportado · Custo: não informado");
    }

    void aiTextUsageLabelReflectsReportedStatus()
    {
        QFETCH(QByteArray, usage);
        QFETCH(QString, expectedLabel);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString receipt = directory.filePath(QStringLiteral("text-receipt"));
        const QString helper = directory.filePath(QStringLiteral("usage-helper.py"));
        QFile file(helper);
        QVERIFY(file.open(QIODevice::WriteOnly));
        file.write("import base64,json,os,pathlib,sys,time\npathlib.Path(base64.b64decode('");
        file.write(receipt.toUtf8().toBase64());
        file.write("').decode()).write_text(str(os.getpid())+'\\n'+os.getcwd())\n"
                   "request=json.loads(sys.stdin.buffer.readline())\n"
                   "base={'schemaVersion':1,'requestId':request['requestId']}\n"
                   "events=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='resultado')]\n"
                   "for event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\n");
        if (usage.isEmpty()) {
            file.write("time.sleep(60)\n");
        } else {
            file.write("usage=json.loads(base64.b64decode('");
            file.write(usage.toBase64());
            file.write("'))\nprint(json.dumps(dict(base,sequence=2,type='completed',finishReason='stop',usage=usage,cost={'status':'unknown','currency':None,'amount':None}),separators=(',',':')),flush=True)\n");
        }
        file.close();

        LauncherControllerTestOwner controllerOwner;
        LauncherController &controller = controllerOwner.controller();
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), directory.filePath(QStringLiteral("missing-ai.py")));
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), directory.filePath(QStringLiteral("missing-steam.py")));
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
        QVERIFY(entry);
        QVERIFY(QMetaObject::invokeMethod(entry, "click"));
        aiText.generate(QStringLiteral("usage-request"), QStringLiteral("summarize"), QVariant(),
                        QStringLiteral("texto"), QStringLiteral("modelo:1"), QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("resultado"), 1500);
        if (usage.isEmpty()) {
            QVERIFY(aiText.busy());
            QVERIFY(aiText.usage().isEmpty());
        } else {
            QTRY_COMPARE_WITH_TIMEOUT(aiText.status(), QStringLiteral("completed"), 1500);
            QCOMPARE(aiText.usage().size(), 4);
        }
        QQuickItem *label = nullptr;
        for (auto *item : window->findChildren<QQuickItem *>()) {
            if (item->property("text").toString().startsWith(QStringLiteral("Uso: "))) {
                QVERIFY(!label);
                label = item;
            }
        }
        QVERIFY(label);
        QVERIFY(label->isVisible());
        QCOMPARE(label->property("text").toString(), expectedLabel);
        aiText.cancelAll();
        QTRY_VERIFY_WITH_TIMEOUT(!aiText.busy(), 2500);
        QVERIFY(helperReapedAndRuntimeRemoved(receipt));
    }

    void departingAiPanelCancelsBothOwnersAndPreservesPartialOutput_data()
    {
        QTest::addColumn<QString>("departure");
        QTest::newRow("steam-entry") << QStringLiteral("steam");
        QTest::newRow("back-to-search") << QStringLiteral("back");
        QTest::newRow("escape-to-search") << QStringLiteral("escape");
        QTest::newRow("header-to-search") << QStringLiteral("search");
    }

    void departingAiPanelCancelsBothOwnersAndPreservesPartialOutput()
    {
        QFETCH(QString, departure);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString providerReceipt = directory.filePath(QStringLiteral("provider-receipt"));
        const QString textReceipt = directory.filePath(QStringLiteral("text-receipt"));
        const QString providerHelper = directory.filePath(QStringLiteral("provider-departure.py"));
        const QString textHelper = directory.filePath(QStringLiteral("text-departure.py"));
        for (const auto &pair : {qMakePair(providerHelper, providerReceipt), qMakePair(textHelper, textReceipt)}) {
            QFile file(pair.first);
            QVERIFY(file.open(QIODevice::WriteOnly));
            file.write("import base64,json,os,pathlib,signal,sys,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\n");
            file.write(pair.first == providerHelper
                ? "runtime=sys.argv[sys.argv.index('--runtime-root')+1]\n"
                : "runtime=os.getcwd()\n");
            file.write("pathlib.Path(base64.b64decode('");
            file.write(pair.second.toUtf8().toBase64());
            file.write("').decode()).write_text(str(os.getpid())+'\\n'+runtime)\n");
            if (pair.first == textHelper) {
                file.write("request=json.loads(sys.stdin.buffer.readline())\n"
                           "base={'schemaVersion':1,'requestId':request['requestId']}\n"
                           "events=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='parcial preservado')]\n"
                           "for event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\n");
            }
            file.write("time.sleep(60)\n");
        }

        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), providerHelper, {}, nullptr, {}, 100);
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), textHelper, {}, nullptr, {}, 100);
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), directory.filePath(QStringLiteral("missing-steam.py")));
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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
        auto *discover = window->findChild<QQuickItem *>(QStringLiteral("aiDiscoverButton"));
        auto *text = window->findChild<QQuickItem *>(QStringLiteral("aiTextInput"));
        auto *consent = window->findChild<QQuickItem *>(QStringLiteral("aiTextConsent"));
        auto *generate = window->findChild<QQuickItem *>(QStringLiteral("aiTextGenerate"));
        auto *result = window->findChild<QQuickItem *>(QStringLiteral("aiTextResult"));
        auto *steamEntry = window->findChild<QQuickItem *>(QStringLiteral("steamEntryButton"));
        auto *steamPanel = window->findChild<QQuickItem *>(QStringLiteral("steamSettings"));
        auto *steamBack = window->findChild<QQuickItem *>(QStringLiteral("steamBackButton"));
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        QVERIFY(entry && back && discover && text && consent && generate && result
                && steamEntry && steamPanel && steamBack && search);
        QVERIFY(QMetaObject::invokeMethod(entry, "click"));
        QVERIFY(text->setProperty("text", QStringLiteral("texto da fixture")));
        QVERIFY(consent->setProperty("checked", true));
        QVERIFY(QMetaObject::invokeMethod(discover, "click"));
        QVERIFY(QMetaObject::invokeMethod(generate, "click"));
        QTRY_VERIFY_WITH_TIMEOUT(ai.busy() && aiText.busy() && QFile::exists(providerReceipt), 1500);
        QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("parcial preservado"), 1500);
        QCOMPARE(window->property("activePanel").toString(), QStringLiteral("ai"));

        if (departure == QStringLiteral("steam")) {
            QVERIFY(QMetaObject::invokeMethod(steamEntry, "click"));
            QCOMPARE(window->property("activePanel").toString(), QStringLiteral("steam"));
            QVERIFY(steamPanel->isVisible());
            QVERIFY(steamBack->hasActiveFocus());
            QVERIFY(!steam.busy()); // Entering Steam does not implicitly scan or start a helper.
        } else {
            if (departure == QStringLiteral("escape")) QTest::keyClick(window, Qt::Key_Escape);
            else QVERIFY(QMetaObject::invokeMethod(departure == QStringLiteral("back") ? back : entry, "click"));
            QCOMPARE(window->property("activePanel").toString(), QStringLiteral("search"));
            QVERIFY(search->hasActiveFocus());
        }
        QTRY_VERIFY_WITH_TIMEOUT(!ai.busy() && !aiText.busy(), 2500);
        QCOMPARE(ai.status(), QStringLiteral("disabled"));
        QVERIFY(ai.errorCode().isEmpty());
        QCOMPARE(aiText.status(), QStringLiteral("cancelled_unconfirmed")); // The fake helper sends no remote cancellation acknowledgement.
        QCOMPARE(aiText.output(), QStringLiteral("parcial preservado"));
        QCOMPARE(result->property("text").toString(), QStringLiteral("parcial preservado"));
        QVERIFY(helperReapedAndRuntimeRemoved(providerReceipt));
        QVERIFY(helperReapedAndRuntimeRemoved(textReceipt));
        if (departure == QStringLiteral("steam")) {
            QTest::keyClick(window, Qt::Key_Space); // Steam's focused Back control receives input.
            QCOMPARE(window->property("activePanel").toString(), QStringLiteral("search"));
            QVERIFY(search->hasActiveFocus());
        }
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
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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

    void activeShortcutWaitsForThreeOwnersBeforeHidingExactlyOnce()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString providerReceipt = directory.filePath(QStringLiteral("shortcut-provider-receipt"));
        const QString textReceipt = directory.filePath(QStringLiteral("shortcut-text-receipt"));
        const QString steamReceipt = directory.filePath(QStringLiteral("shortcut-steam-receipt"));
        const QString providerHelper = directory.filePath(QStringLiteral("shortcut-provider.py"));
        const QString textHelper = directory.filePath(QStringLiteral("shortcut-text.py"));
        const QString steamHelper = directory.filePath(QStringLiteral("shortcut-steam.py"));
        for (const auto &pair : {qMakePair(providerHelper, providerReceipt),
                                 qMakePair(textHelper, textReceipt), qMakePair(steamHelper, steamReceipt)}) {
            QFile file(pair.first);
            QVERIFY(file.open(QIODevice::WriteOnly));
            file.write("import base64,json,os,pathlib,signal,sys,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\n");
            file.write(pair.first == providerHelper
                ? "runtime=sys.argv[sys.argv.index('--runtime-root')+1]\n" : "runtime=os.getcwd()\n");
            file.write("pathlib.Path(base64.b64decode('");
            file.write(pair.second.toUtf8().toBase64());
            file.write("').decode()).write_text(str(os.getpid())+'\\n'+runtime)\n");
            if (pair.first == textHelper) {
                file.write("request=json.loads(sys.stdin.buffer.readline())\n"
                           "base={'schemaVersion':1,'requestId':request['requestId']}\n"
                           "events=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='parcial-atalho')]\n"
                           "for event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\n");
            }
            file.write("time.sleep(60)\n");
        }
        const auto steamReaped = [&] {
            QFile file(steamReceipt);
            if (!file.open(QIODevice::ReadOnly)) return false;
            bool valid = false;
            const qint64 pid = file.readAll().split('\n').first().toLongLong(&valid);
            if (!valid || pid <= 0) return false;
            errno = 0;
            if (::kill(static_cast<pid_t>(pid), 0) != -1 || errno != ESRCH) return false;
            errno = 0;
            return ::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH;
        };

        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), providerHelper,
                                {}, nullptr, {}, 500);
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), textHelper,
                                {}, nullptr, {}, 100);
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), steamHelper);
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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
        window->requestActivate(); // Only the owned offscreen Qt window, without a compositor or global shortcut.
        QTRY_VERIFY_WITH_TIMEOUT(window->isActive(), 1000);
        WindowSession session(&controller, window, false, QString());
        QVERIFY(session.shortcutText().isEmpty());
        // Match main.cpp's order: the session's hide slot precedes the cancellation slots.
        connect(&controller, &LauncherController::closeRequested, &ai, &AiProviderController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &aiText, &AiTextController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &steam, &SteamProviderController::cancelAll);

        ai.discover();
        aiText.generate(QStringLiteral("shortcut-request"), QStringLiteral("summarize"),
                        QVariant(), QStringLiteral("texto"), QStringLiteral("modelo:1"),
                        QStringLiteral("127.0.0.1"), 11434, true);
        steam.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_VERIFY_WITH_TIMEOUT(ai.busy() && aiText.busy() && steam.busy()
            && QFile::exists(providerReceipt) && QFile::exists(textReceipt) && QFile::exists(steamReceipt), 1500);
        QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("parcial-atalho"), 1500);
        for (const auto &receipt : {providerReceipt, textReceipt, steamReceipt}) {
            QFile file(receipt);
            QVERIFY(file.open(QIODevice::ReadOnly));
            qInfo().noquote() << "ORLA_SHORTCUT_HELPER" << QFileInfo(receipt).fileName() << file.readAll();
        }
        QSignalSpy dismissed(&controller, &LauncherController::closeRequested);
        QSignalSpy providerReady(&ai, &AiProviderController::closeReady);
        QSignalSpy textReady(&aiText, &AiTextController::closeReady);
        QSignalSpy steamReady(&steam, &SteamProviderController::closeReady);
        QSignalSpy visibility(window, &QWindow::visibleChanged);
        QSignalSpy quitRequested(&engine, &QQmlApplicationEngine::quit);
        bool hiddenAfterCleanup = false;
        connect(window, &QWindow::visibleChanged, &session, [&] {
            if (!window->isVisible()) hiddenAfterCleanup = !ai.busy() && !aiText.busy() && !steam.busy()
                && helperReapedAndRuntimeRemoved(providerReceipt)
                && helperReapedAndRuntimeRemoved(textReceipt) && steamReaped();
        });
        QVERIFY(window->isVisible() && window->isActive());
        session.showFromShortcut(); // Actual QAction target; no registration, native key, or fake activity flag.
        QVERIFY(window->isVisible());
        QCOMPARE(window->property("pendingDismiss").toBool(), true);
        QCOMPARE(window->property("pendingQuit").toBool(), false);
        QCOMPARE(dismissed.count(), 0);
        session.showFromShortcut(); // Repeated activation cannot bypass the pending barrier.
        QVERIFY(window->isVisible());
        QCOMPARE(dismissed.count(), 0);

        QTRY_COMPARE_WITH_TIMEOUT(textReady.count(), 1, 1500);
        QVERIFY(helperReapedAndRuntimeRemoved(textReceipt));
        QVERIFY(ai.busy() && steam.busy());
        QVERIFY(window->isVisible());
        QCOMPARE(dismissed.count(), 0);
        QTRY_COMPARE_WITH_TIMEOUT(providerReady.count(), 1, 2000);
        QVERIFY(helperReapedAndRuntimeRemoved(providerReceipt));
        QVERIFY(steam.busy());
        QVERIFY(window->isVisible());
        QCOMPARE(dismissed.count(), 0);
        QTRY_COMPARE_WITH_TIMEOUT(steamReady.count(), 1, 7000);
        QVERIFY(steamReaped());
        QCOMPARE(dismissed.count(), 1);
        QCOMPARE(visibility.count(), 1);
        QVERIFY(!window->isVisible());
        QVERIFY(hiddenAfterCleanup);
        QCOMPARE(aiText.output(), QStringLiteral("parcial-atalho"));
        QCOMPARE(window->property("pendingDismiss").toBool(), false);
        QCOMPARE(quitRequested.count(), 0);
        QTest::qWait(100);
        QCOMPARE(dismissed.count(), 1);
        QCOMPARE(visibility.count(), 1);
        qInfo() << "ORLA_SHORTCUT_BARRIER_PASS three_helpers_reaped=true owned_ai_runtimes_removed=true hide_exactly_once=true partial_preserved=true";
    }

    void resultExecutionWaitsForOwnerCleanup_data()
    {
        QTest::addColumn<QString>("route");
        QTest::addColumn<QString>("owner");
        QTest::newRow("provider-return") << QStringLiteral("return") << QStringLiteral("provider");
        QTest::newRow("text-enter") << QStringLiteral("enter") << QStringLiteral("text");
        QTest::newRow("text-main") << QStringLiteral("main") << QStringLiteral("text");
        QTest::newRow("text-delegate") << QStringLiteral("delegate") << QStringLiteral("text");
        QTest::newRow("text-held-main") << QStringLiteral("held-main") << QStringLiteral("text");
        QTest::newRow("text-held-delegate") << QStringLiteral("held-delegate") << QStringLiteral("text");
        QTest::newRow("text-action") << QStringLiteral("action") << QStringLiteral("text");
        QTest::newRow("steam-return") << QStringLiteral("return") << QStringLiteral("steam");
        QTest::newRow("pending-return") << QStringLiteral("pending") << QStringLiteral("text");
    }

    void resultExecutionWaitsForOwnerCleanup()
    {
        QFETCH(QString, route);
        QFETCH(QString, owner);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString receipt = directory.filePath(QStringLiteral("cleanup-receipt"));
        const QString providerHelper = directory.filePath(QStringLiteral("execution-provider.py"));
        const QString textHelper = directory.filePath(QStringLiteral("execution-text.py"));
        const QString steamHelper = directory.filePath(QStringLiteral("execution-steam.py"));
        const QString steamLoaded = directory.filePath(QStringLiteral("steam-loaded"));
        const QByteArray steamDocument = R"({"apps":[{"appid":"42","library":"library-0","name":"Synthetic Execution Game","ownership":"unknown","source":"local_manifest","status":"installed_candidate"}],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"available"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"available"}],"schema_version":"0.1-experimental","status":"available"})" "\n";
        for (const auto &helper : {providerHelper, textHelper, steamHelper}) {
            QFile file(helper);
            QVERIFY(file.open(QIODevice::WriteOnly));
            file.write("import base64,json,os,pathlib,signal,sys,time\n");
            if (helper == steamHelper) {
                file.write("marker=pathlib.Path(base64.b64decode('");
                file.write(steamLoaded.toUtf8().toBase64());
                file.write("').decode())\nif not marker.exists():\n marker.touch()\n sys.stdout.buffer.write(base64.b64decode('");
                file.write(steamDocument.toBase64());
                file.write("'))\n raise SystemExit(0)\n");
            }
            file.write("signal.signal(signal.SIGTERM,signal.SIG_IGN)\n");
            file.write(helper == providerHelper
                ? "runtime=sys.argv[sys.argv.index('--runtime-root')+1]\n" : "runtime=os.getcwd()\n");
            file.write("pathlib.Path(base64.b64decode('");
            file.write(receipt.toUtf8().toBase64());
            file.write("').decode()).write_text(str(os.getpid())+'\\n'+runtime)\n");
            if (helper == textHelper) {
                file.write("request=json.loads(sys.stdin.buffer.readline())\n"
                           "base={'schemaVersion':1,'requestId':request['requestId']}\n"
                           "events=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='parcial-execucao')]\n"
                           "for event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\n");
            }
            file.write("time.sleep(60)\n");
        }
        const auto processReaped = [&] {
            QFile file(receipt);
            if (!file.open(QIODevice::ReadOnly)) return false;
            bool valid = false;
            const qint64 pid = file.readAll().split('\n').first().toLongLong(&valid);
            if (!valid || pid <= 0) return false;
            errno = 0;
            if (::kill(static_cast<pid_t>(pid), 0) != -1 || errno != ESRCH) return false;
            errno = 0;
            return ::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH;
        };
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), providerHelper,
                                {}, nullptr, {}, 400);
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), textHelper,
                                {}, nullptr, {}, 400);
        QList<QUrl> opened;
        bool cleanupConfirmedAtOpen = false;
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), steamHelper,
            [&](const QUrl &url) {
                opened.append(url); // Owned callback only: never send a real Steam URI.
                cleanupConfirmedAtOpen = !ai.busy() && !aiText.busy() && !steam.busy()
                    && processReaped() && (owner == QStringLiteral("steam")
                        || helperReapedAndRuntimeRemoved(receipt));
                return true;
            });
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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
        WindowSession session(&controller, window, false, QString());
        connect(&controller, &LauncherController::closeRequested, &ai, &AiProviderController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &aiText, &AiTextController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &steam, &SteamProviderController::cancelAll);
        const auto cleanupOnReturn = qScopeGuard([&] {
            if (!ai.busy() && !aiText.busy() && !steam.busy()) return;
            ai.cancelAll();
            aiText.cancelAll();
            steam.cancelAll();
            QElapsedTimer timer;
            timer.start();
            while ((ai.busy() || aiText.busy() || steam.busy()) && timer.elapsed() < 7000)
                QTest::qWait(10);
            QVERIFY(!ai.busy() && !aiText.busy() && !steam.busy());
            if (QFile::exists(receipt)) {
                QVERIFY(processReaped());
                if (owner != QStringLiteral("steam")) QVERIFY(helperReapedAndRuntimeRemoved(receipt));
            }
        });
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        auto *aiEntry = window->findChild<QQuickItem *>(QStringLiteral("aiEntryButton"));
        auto *aiBack = window->findChild<QQuickItem *>(QStringLiteral("aiBackButton"));
        auto *steamEntry = window->findChild<QQuickItem *>(QStringLiteral("steamEntryButton"));
        auto *steamBack = window->findChild<QQuickItem *>(QStringLiteral("steamBackButton"));
        QVERIFY(search && aiEntry && aiBack && steamEntry && steamBack);
        steam.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_COMPARE_WITH_TIMEOUT(steam.status(), QStringLiteral("available"), 1500);
        const bool calculator = route == QStringLiteral("action") || owner == QStringLiteral("steam");
        const QString query = calculator ? QStringLiteral("2+2") : QStringLiteral("Synthetic Execution Game");
        controller.setQuery(query);
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("ready"), 3000);
        QCOMPARE(controller.rows().size(), 1);
        const QVariantMap originalRow = controller.rows().first().toMap();
        const auto scriptMap = [](const QVariant &value) {
            return value.metaType() == QMetaType::fromType<QJSValue>()
                ? value.value<QJSValue>().toVariant().toMap() : value.toMap();
        };
        const auto findControl = [&](bool delegate, bool action) -> QQuickItem * {
            QVariantMap liveRow;
            for (const QVariant &entry : controller.rows()) {
                const QVariantMap row = entry.toMap();
                if (row.value("id") == originalRow.value("id")) { liveRow = row; break; }
            }
            if ((delegate || action) && liveRow.isEmpty()) return nullptr;
            QList<QQuickItem *> items{window->contentItem()};
            for (int i = 0; i < items.size(); ++i) {
                auto *item = items[i];
                items.append(item->childItems()); // ListView delegates belong to its visual content tree.
                if (!item->isVisible()) continue;
                const QVariantMap row = scriptMap(item->property("rowData"));
                if (delegate && row.value("id") == liveRow.value("id")
                    && row.value("generation") == liveRow.value("generation")) return item;
                const QVariantMap actionData = scriptMap(item->property("modelData"));
                if (action && actionData.value("resultId") == liveRow.value("id")
                    && actionData.value("generation") == liveRow.value("generation")
                    && actionData.value("id") == originalRow.value("actions").toList().first().toMap().value("id")) return item;
                if (!delegate && !action && item->property("executionTicket").isValid()
                    && (item->property("text").toString() == QStringLiteral("Abrir ↵")
                        || item->property("text").toString() == QStringLiteral("Usar ↵"))) return item;
            }
            return nullptr;
        };
        QPointer<QQuickItem> mainButton;
        QPointer<QQuickItem> delegate;
        QPointer<QQuickItem> action;
        const bool actionRoute = route == QStringLiteral("action");
        QTRY_VERIFY_WITH_TIMEOUT((mainButton = findControl(false, false)), 1000);
        QTRY_VERIFY_WITH_TIMEOUT((delegate = findControl(true, false)), 1000);
        if (route == QStringLiteral("action")) QTRY_VERIFY_WITH_TIMEOUT((action = findControl(false, true)), 1000);
        QPointer<QQuickItem> target = route.contains(QStringLiteral("delegate")) ? delegate
            : route == QStringLiteral("action") ? action : mainButton;
        const auto center = [](QQuickItem *item) {
            return item->mapToScene(QPointF(item->width() / 2, item->height() / 2)).toPoint();
        };
        const bool held = route.startsWith(QStringLiteral("held-")) || route == QStringLiteral("action");
        QString ownedClipboardBefore;
        QVariantMap pressedTicket;
        if (actionRoute) {
            QCOMPARE(QGuiApplication::platformName(), QStringLiteral("offscreen"));
            // Offscreen uses Qt's process-local clipboard buffer; no host display or clipboard is accessed.
            ownedClipboardBefore = QGuiApplication::clipboard()->text();
            QVERIFY(ownedClipboardBefore != QStringLiteral("4"));
        }
        if (held) {
            QTRY_VERIFY_WITH_TIMEOUT(target && target->width() > 0 && target->height() > 0, 1000);
            QTest::mousePress(window, Qt::LeftButton, Qt::NoModifier, center(target));
            QVERIFY(target);
            pressedTicket = scriptMap(target->property("executionTicket"));
            QCOMPARE(pressedTicket.value("id"), originalRow.value("id"));
            QVERIFY(pressedTicket.contains(QStringLiteral("row")));
        }
        if (owner == QStringLiteral("steam")) {
            QVERIFY(QMetaObject::invokeMethod(steamEntry, "click"));
            steam.scan({QStringLiteral("native=/synthetic/root")});
        } else {
            QVERIFY(QMetaObject::invokeMethod(aiEntry, "click"));
            if (owner == QStringLiteral("provider")) ai.discover();
            else aiText.generate(QStringLiteral("execution-request"), QStringLiteral("summarize"), QVariant(),
                QStringLiteral("texto"), QStringLiteral("modelo:1"), QStringLiteral("127.0.0.1"), 11434, true);
        }
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(receipt) && (ai.busy() || aiText.busy() || steam.busy()), 1500);
        if (owner == QStringLiteral("text")) QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("parcial-execucao"), 1500);
        QFile receiptFile(receipt);
        QVERIFY(receiptFile.open(QIODevice::ReadOnly));
        qInfo().noquote() << "ORLA_EXECUTION_HELPER" << owner << receiptFile.readAll();
        receiptFile.close();
        QSignalSpy dismissed(&controller, &LauncherController::closeRequested);
        QSignalSpy visibility(window, &QWindow::visibleChanged);
        if (route == QStringLiteral("pending")) {
            QVERIFY(QMetaObject::invokeMethod(aiBack, "click"));
            QVERIFY(QMetaObject::invokeMethod(window, "requestDismiss", Q_ARG(QVariant, QVariant(false))));
            QVERIFY(window->property("pendingDismiss").toBool());
        } else QVERIFY(QMetaObject::invokeMethod(owner == QStringLiteral("steam") ? steamBack : aiBack, "click"));
        QCOMPARE(window->property("activePanel").toString(), QStringLiteral("search"));
        QVERIFY(ai.busy() || aiText.busy() || steam.busy());
        if (held) {
            QVERIFY(target); // Keep the original pressed control, never substitute a rebuilt delegate.
            QCOMPARE(scriptMap(target->property("executionTicket")), pressedTicket);
            QTest::mouseRelease(window, Qt::LeftButton, Qt::NoModifier, center(target));
            // Challenge a delayed delivery using the real stored onPressed ticket and QML handler.
            QVERIFY(target);
            QCOMPARE(scriptMap(target->property("executionTicket")), pressedTicket);
            QVERIFY(QMetaObject::invokeMethod(target, "clicked"));
        } else if (route == QStringLiteral("main") || route == QStringLiteral("delegate")) {
            target = findControl(route == QStringLiteral("delegate"), false);
            QVERIFY(target);
            QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier, center(target));
        } else {
            search->forceActiveFocus();
            QTest::keyClick(window, route == QStringLiteral("enter") ? Qt::Key_Enter : Qt::Key_Return);
        }
        if (!opened.isEmpty() || controller.query() != query || dismissed.count() != 0 || !window->isVisible()
            || (actionRoute && QGuiApplication::clipboard()->text() != ownedClipboardBefore)) {
            // Preserve the causal failure while still reaping the owned fixture before a test assertion returns.
            ai.cancelAll();
            aiText.cancelAll();
            steam.cancelAll();
            QTRY_VERIFY_WITH_TIMEOUT(!ai.busy() && !aiText.busy() && !steam.busy(), 7000);
            QVERIFY(processReaped());
            if (owner != QStringLiteral("steam")) QVERIFY(helperReapedAndRuntimeRemoved(receipt));
        }
        QCOMPARE(opened.size(), 0);
        if (actionRoute) QCOMPARE(QGuiApplication::clipboard()->text(), ownedClipboardBefore);
        QCOMPARE(controller.query(), query);
        QCOMPARE(dismissed.count(), 0);
        QVERIFY(window->isVisible());
        // Scan/cancellation can replace ListView/Repeater objects; observe current identity and generation.
        QTRY_VERIFY_WITH_TIMEOUT((mainButton = findControl(false, false)), 1000);
        QTRY_VERIFY_WITH_TIMEOUT((delegate = findControl(true, false)), 1000);
        QVERIFY(mainButton && !mainButton->isEnabled());
        QVERIFY(delegate && !delegate->isEnabled());
        if (actionRoute) {
            QTRY_VERIFY_WITH_TIMEOUT((action = findControl(false, true)), 1000);
            QVERIFY(action && !action->isEnabled());
        }
        auto *waiting = window->findChild<QQuickItem *>(QStringLiteral("executionWaiting"));
        QVERIFY(waiting && waiting->isVisible());
        QCOMPARE(waiting->property("text").toString(), QStringLiteral("Aguarde o encerramento das operações antes de abrir um resultado."));
        QVERIFY(search->isEnabled());
        // Typing and navigation stay available; restoring the same text returns a fresh valid selection.
        if (route == QStringLiteral("main")) {
            search->forceActiveFocus();
            QTest::keyClick(window, Qt::Key_Space);
            QCOMPARE(controller.query(), query + QLatin1Char(' '));
            QTest::keyClick(window, Qt::Key_Backspace);
            QCOMPARE(controller.query(), query);
            QTest::keyClick(window, Qt::Key_Down);
        }
        QTRY_VERIFY_WITH_TIMEOUT(!ai.busy() && !aiText.busy() && !steam.busy(), 7000);
        QVERIFY(processReaped());
        if (owner != QStringLiteral("steam")) QVERIFY(helperReapedAndRuntimeRemoved(receipt));
        if (owner == QStringLiteral("text")) QCOMPARE(aiText.output(), QStringLiteral("parcial-execucao"));
        if (route == QStringLiteral("pending")) {
            QCOMPARE(dismissed.count(), 1);
            QCOMPARE(visibility.count(), 1);
            QVERIFY(!window->isVisible());
            QCOMPARE(opened.size(), 0);
        } else {
            QVERIFY(window->isVisible());
            QTRY_VERIFY((mainButton = findControl(false, false)) && mainButton->isEnabled());
            if (actionRoute) {
                QTRY_VERIFY_WITH_TIMEOUT((action = findControl(false, true)), 1000);
                QVERIFY(action && action->isEnabled()); // Restore the action affordance without copying to any clipboard.
            }
            QVERIFY(!waiting->isVisible());
            if (calculator) {
                // Actual owned calculator action/Steam cleanup handling above; positive dismissal uses the owned URI callback.
                controller.setQuery(QStringLiteral("Synthetic Execution Game"));
                if (owner == QStringLiteral("steam")) {
                    QFile::remove(steamLoaded);
                    steam.scan({QStringLiteral("native=/synthetic/root")});
                    QTRY_COMPARE_WITH_TIMEOUT(steam.status(), QStringLiteral("available"), 1500);
                }
            }
            QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("ready"), 3000);
            if (!calculator && route != QStringLiteral("main")) {
                QCOMPARE(controller.rows().first().toMap().value("id"), originalRow.value("id"));
                QCOMPARE(controller.rows().first().toMap().value("generation"), originalRow.value("generation"));
            }
            search->forceActiveFocus();
            QTest::keyClick(window, Qt::Key_Return);
            QCOMPARE(opened, QList<QUrl>{QUrl(QStringLiteral("steam://rungameid/42"))});
            QVERIFY(cleanupConfirmedAtOpen);
            QCOMPARE(dismissed.count(), 1);
            QCOMPARE(visibility.count(), 1);
            QVERIFY(!window->isVisible());
        }
        QTest::qWait(20);
        QCOMPARE(dismissed.count(), 1);
        QCOMPARE(visibility.count(), 1);
        qInfo().noquote() << "ORLA_EXECUTION_CLEANUP_PASS" << route << owner
            << "pid_group_reaped=true owned_ai_runtime_removed=true hide_once=true";
    }

    void windowCloseAndQuitWaitForAllThreeOwnersExactlyOnce()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString providerReceipt = directory.filePath(QStringLiteral("quit-provider-receipt"));
        const QString textReceipt = directory.filePath(QStringLiteral("quit-text-receipt"));
        const QString steamReceipt = directory.filePath(QStringLiteral("quit-steam-receipt"));
        const QString providerHelper = directory.filePath(QStringLiteral("quit-provider.py"));
        const QString textHelper = directory.filePath(QStringLiteral("quit-text.py"));
        const QString steamHelper = directory.filePath(QStringLiteral("quit-steam.py"));
        for (const auto &pair : {qMakePair(providerHelper, providerReceipt),
                                 qMakePair(textHelper, textReceipt), qMakePair(steamHelper, steamReceipt)}) {
            QFile file(pair.first);
            QVERIFY(file.open(QIODevice::WriteOnly));
            file.write("import base64,json,os,pathlib,signal,sys,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\n");
            file.write(pair.first == providerHelper
                ? "runtime=sys.argv[sys.argv.index('--runtime-root')+1]\n" : "runtime=os.getcwd()\n");
            file.write("pathlib.Path(base64.b64decode('");
            file.write(pair.second.toUtf8().toBase64());
            file.write("').decode()).write_text(str(os.getpid())+'\\n'+runtime)\n");
            if (pair.first == textHelper) {
                file.write("request=json.loads(sys.stdin.buffer.readline())\n"
                           "base={'schemaVersion':1,'requestId':request['requestId']}\n"
                           "events=[dict(base,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model']),dict(base,sequence=1,type='delta',text='parcial-close')]\n"
                           "for event in events:\n print(json.dumps(event,separators=(',',':')),flush=True)\n");
            }
            file.write("time.sleep(60)\n");
        }
        const auto steamReaped = [&] {
            QFile file(steamReceipt);
            if (!file.open(QIODevice::ReadOnly)) return false;
            bool valid = false;
            const qint64 pid = file.readAll().split('\n').first().toLongLong(&valid);
            if (!valid || pid <= 0) return false;
            errno = 0;
            if (::kill(static_cast<pid_t>(pid), 0) != -1 || errno != ESRCH) return false;
            errno = 0;
            return ::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH;
        };
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), providerHelper,
                                {}, nullptr, {}, 500);
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), textHelper,
                                {}, nullptr, {}, 100);
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), steamHelper);
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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
        window->requestActivate(); // Actual owned offscreen activity; no global registration or native key.
        QTRY_VERIFY_WITH_TIMEOUT(window->isActive(), 1000);
        WindowSession session(&controller, window, false, QString());
        QVERIFY(session.shortcutText().isEmpty());
        connect(&controller, &LauncherController::closeRequested, &ai, &AiProviderController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &aiText, &AiTextController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &steam, &SteamProviderController::cancelAll);
        const auto cleanupOnReturn = qScopeGuard([&] {
            ai.cancelAll();
            aiText.cancelAll();
            steam.cancelAll();
            QElapsedTimer timer;
            timer.start();
            while ((ai.busy() || aiText.busy() || steam.busy()) && timer.elapsed() < 7000)
                QTest::qWait(10);
            QVERIFY(!ai.busy() && !aiText.busy() && !steam.busy());
            if (QFile::exists(providerReceipt)) QVERIFY(helperReapedAndRuntimeRemoved(providerReceipt));
            if (QFile::exists(textReceipt)) QVERIFY(helperReapedAndRuntimeRemoved(textReceipt));
            if (QFile::exists(steamReceipt)) QVERIFY(steamReaped());
        });
        ai.discover();
        aiText.generate(QStringLiteral("window-close-request"), QStringLiteral("summarize"),
                        QVariant(), QStringLiteral("texto"), QStringLiteral("modelo:1"),
                        QStringLiteral("127.0.0.1"), 11434, true);
        steam.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_VERIFY_WITH_TIMEOUT(ai.busy() && aiText.busy() && steam.busy()
            && QFile::exists(providerReceipt) && QFile::exists(textReceipt) && QFile::exists(steamReceipt), 1500);
        QTRY_COMPARE_WITH_TIMEOUT(aiText.output(), QStringLiteral("parcial-close"), 1500);
        for (const auto &receipt : {providerReceipt, textReceipt, steamReceipt}) {
            QFile file(receipt);
            QVERIFY(file.open(QIODevice::ReadOnly));
            qInfo().noquote() << "ORLA_QUIT_HELPER" << QFileInfo(receipt).fileName() << file.readAll();
        }
        QSignalSpy dismissed(&controller, &LauncherController::closeRequested);
        QSignalSpy quitRequested(&engine, &QQmlApplicationEngine::quit);
        QSignalSpy visibility(window, &QWindow::visibleChanged);
        bool hiddenAfterCleanup = false;
        connect(window, &QWindow::visibleChanged, &session, [&] {
            if (!window->isVisible()) hiddenAfterCleanup = !ai.busy() && !aiText.busy() && !steam.busy()
                && helperReapedAndRuntimeRemoved(providerReceipt)
                && helperReapedAndRuntimeRemoved(textReceipt) && steamReaped();
        });
        session.showFromShortcut(); // Actual shortcut target starts a nonquit close.
        QCOMPARE(window->property("pendingDismiss").toBool(), true);
        QCOMPARE(window->property("pendingQuit").toBool(), false);
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(quitRequested.count(), 0);
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
        QVERIFY(window->isActive());
        session.showFromShortcut(); // Repeated nonquit requests must not downgrade the pending quit.
        bool quitIntentStayedLatched = window->property("pendingQuit").toBool();
        QVERIFY(QMetaObject::invokeMethod(window, "requestDismiss", Q_ARG(QVariant, QVariant(false))));
        quitIntentStayedLatched &= window->property("pendingQuit").toBool();

        QTRY_VERIFY_WITH_TIMEOUT(!aiText.busy(), 1500);
        QVERIFY(helperReapedAndRuntimeRemoved(textReceipt));
        QVERIFY(ai.busy() || steam.busy());
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(quitRequested.count(), 0);
        QVERIFY(window->isVisible());
        QVERIFY(window->isActive());
        session.showFromShortcut();
        quitIntentStayedLatched &= window->property("pendingQuit").toBool();

        QTRY_VERIFY_WITH_TIMEOUT(!ai.busy(), 2500);
        QVERIFY(helperReapedAndRuntimeRemoved(providerReceipt));
        QVERIFY(steam.busy());
        QCOMPARE(dismissed.count(), 0);
        QCOMPARE(quitRequested.count(), 0);
        QVERIFY(window->isActive());
        session.showFromShortcut();
        quitIntentStayedLatched &= window->property("pendingQuit").toBool();

        QTRY_VERIFY_WITH_TIMEOUT(!steam.busy(), 7000);
        QVERIFY(steamReaped());
        // Delay the causal regression assertion until all actual helpers have been reaped.
        QVERIFY(quitIntentStayedLatched);
        QTRY_COMPARE_WITH_TIMEOUT(dismissed.count(), 1, 1000);
        QTRY_COMPARE_WITH_TIMEOUT(quitRequested.count(), 1, 1000);
        QCOMPARE(visibility.count(), 1);
        QVERIFY(!window->isVisible());
        QVERIFY(hiddenAfterCleanup);
        QCOMPARE(aiText.output(), QStringLiteral("parcial-close"));
        QCOMPARE(window->property("pendingDismiss").toBool(), false);
        QCOMPARE(window->property("pendingQuit").toBool(), false);
        QTest::qWait(100);
        QCOMPARE(dismissed.count(), 1);
        QCOMPARE(quitRequested.count(), 1);
        QCOMPARE(visibility.count(), 1);

        // A later independent idle close must not inherit the committed quit intent.
        window->show();
        QVERIFY(QTest::qWaitForWindowExposed(window));
        window->requestActivate();
        QTRY_VERIFY_WITH_TIMEOUT(window->isActive(), 1000);
        QVERIFY(window->isVisible());
        session.showFromShortcut();
        QCOMPARE(dismissed.count(), 2);
        QCOMPARE(quitRequested.count(), 1);
        QCOMPARE(visibility.count(), 3);
        QVERIFY(!window->isVisible());
        QCOMPARE(window->property("pendingDismiss").toBool(), false);
        QCOMPARE(window->property("pendingQuit").toBool(), false);
        qInfo() << "ORLA_QUIT_BARRIER_PASS intent_upgraded=true nonquit_downgrade_blocked=true quit_committed_once=true idle_nonquit_immediate=true fresh_nonquit_preserved=true three_helpers_reaped=true";
    }
    void pendingCloseBlocksIdleOwnerStarts_data()
    {
        QTest::addColumn<QString>("blockingOwner");
        QTest::addColumn<QString>("providerStart");
        QTest::newRow("provider-busy-text-idle") << QStringLiteral("provider") << QStringLiteral("probe");
        QTest::newRow("text-busy-provider-idle-discover") << QStringLiteral("text") << QStringLiteral("discover");
        QTest::newRow("text-busy-provider-idle-probe") << QStringLiteral("text") << QStringLiteral("probe");
    }

    void pendingCloseBlocksIdleOwnerStarts()
    {
        QFETCH(QString, blockingOwner);
        QFETCH(QString, providerStart);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QByteArray steamDocument = R"({"apps":[{"appid":"42","library":"library-0","name":"Pending Close Game","ownership":"unknown","source":"local_manifest","status":"installed_candidate"}],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"available"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"available"}],"schema_version":"0.1-experimental","status":"available"})" "\n";
        const QByteArray caps = R"({"installation":"absent","anonymous_protocol":"absent","authentication":"unknown","inference":"absent","cancellation":"absent","usage_reporting":"unknown"})";
        const QByteArray providers = QByteArray("[")
            + R"({"id":"codex","displayName":"Codex","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"owned_app_server","messageCode":"cli_not_found"},)"
            + R"({"id":"claude","displayName":"Claude Code","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"official_terminal_handoff","messageCode":"cli_not_found"},)"
            + R"({"id":"opencode","displayName":"OpenCode","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"selected_local_server","messageCode":"cli_not_found"},)"
            + R"({"id":"ollama","displayName":"Ollama","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"selected_local_server","messageCode":"cli_not_found"},)"
            + R"({"id":"lmstudio","displayName":"LM Studio","enabled":false,"clientVersion":null,"capabilities":)" + caps + R"(,"route":"selected_local_server","messageCode":"cli_not_found"}])";
        const QByteArray providerDocument = "{\"schemaVersion\":1,\"providers\":" + providers + '}';
        const QByteArray codexDocument = "{\"schemaVersion\":1,\"provider\":{\"id\":\"codex\",\"displayName\":\"Codex\",\"enabled\":false,\"clientVersion\":null,\"capabilities\":"
            + caps + ",\"route\":\"owned_app_server\",\"messageCode\":\"cli_not_found\"}}";
        const auto receiptPath = [&](const QString &owner, bool warm) {
            return directory.filePath(owner + (warm ? QStringLiteral("-warm") : QStringLiteral("-later")));
        };
        for (const QString &owner : {QStringLiteral("provider"), QStringLiteral("text"), QStringLiteral("steam")}) {
            QFile file(directory.filePath(owner + QStringLiteral(".py")));
            QVERIFY(file.open(QIODevice::WriteOnly));
            file.write("import base64,json,os,pathlib,signal,sys,time\nowner='");
            file.write(owner.toUtf8());
            file.write("'\nblocking='");
            file.write(blockingOwner.toUtf8());
            file.write("'\nbase=pathlib.Path(base64.b64decode('");
            file.write(directory.path().toUtf8().toBase64());
            file.write("').decode())\ncounter=base/(owner+'-count')\nn=int(counter.read_text())+1 if counter.exists() else 1\ncounter.write_text(str(n))\n"
                       "runtime=sys.argv[sys.argv.index('--runtime-root')+1] if owner=='provider' else os.getcwd()\n"
                       "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                       "(base/(owner+('-warm' if n==1 else '-later'))).write_text(str(os.getpid())+'\\n'+runtime)\n");
            if (owner == QStringLiteral("text")) {
                file.write("request=json.loads(sys.stdin.buffer.readline())\nb={'schemaVersion':1,'requestId':request['requestId']}\n"
                           "print(json.dumps(dict(b,sequence=0,type='started',provider='ollama_local',destination=request['endpoint'],model=request['model'])),flush=True)\n"
                           "print(json.dumps(dict(b,sequence=1,type='delta',text='parcial-pendente')),flush=True)\n");
            }
            file.write("if n>1:\n time.sleep(60 if owner==blocking else 0.65)\n");
            if (owner == QStringLiteral("text")) {
                file.write("print(json.dumps(dict(b,sequence=2,type='completed',finishReason='stop',usage={'status':'unknown','inputTokens':None,'outputTokens':None,'totalTokens':None},cost={'status':'unknown','currency':None,'amount':None})),flush=True)\n");
            } else {
                file.write("sys.stdout.buffer.write(base64.b64decode('");
                file.write((owner == QStringLiteral("steam") ? steamDocument : providerDocument).toBase64());
                if (owner == QStringLiteral("provider")) {
                    file.write("') if sys.argv[1]=='detect' else base64.b64decode('");
                    file.write(codexDocument.toBase64());
                }
                file.write("'))\nsys.stdout.flush()\n");
            }
        }
        const auto reaped = [&](const QString &owner, bool warm) {
            const QString receipt = receiptPath(owner, warm);
            if (owner != QStringLiteral("steam")) return helperReapedAndRuntimeRemoved(receipt);
            QFile file(receipt);
            if (!file.open(QIODevice::ReadOnly)) return false;
            bool valid = false;
            const qint64 pid = file.readAll().split('\n').first().toLongLong(&valid);
            if (!valid || pid <= 0) return false;
            errno = 0;
            if (::kill(static_cast<pid_t>(pid), 0) != -1 || errno != ESRCH) return false;
            errno = 0;
            return ::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH;
        };
        AiProviderController ai(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), directory.filePath(QStringLiteral("provider.py")), {}, nullptr, {}, 400);
        AiTextController aiText(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), directory.filePath(QStringLiteral("text.py")), {}, nullptr, {}, 400);
        QList<QUrl> opened;
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), directory.filePath(QStringLiteral("steam.py")),
            [&](const QUrl &url) { opened.append(url); return true; }); // Owned URI boundary only.
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &controller = controllerOwner.controller();
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
        window->requestActivate();
        QTRY_VERIFY_WITH_TIMEOUT(window->isActive(), 1000);
        WindowSession session(&controller, window, false, QString());
        connect(&controller, &LauncherController::closeRequested, &ai, &AiProviderController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &aiText, &AiTextController::cancelAll);
        connect(&controller, &LauncherController::closeRequested, &steam, &SteamProviderController::cancelAll);
        const auto cleanupOnReturn = qScopeGuard([&] {
            ai.cancelAll(); aiText.cancelAll(); steam.cancelAll();
            QElapsedTimer timer; timer.start();
            while ((ai.busy() || aiText.busy() || steam.busy()) && timer.elapsed() < 7000) QTest::qWait(10);
            QVERIFY(!ai.busy() && !aiText.busy() && !steam.busy());
            for (const QString &owner : {QStringLiteral("provider"), QStringLiteral("text"), QStringLiteral("steam")})
                for (bool warm : {true, false}) if (QFile::exists(receiptPath(owner, warm))) QVERIFY(reaped(owner, warm));
        });
        ai.discover();
        aiText.generate(QStringLiteral("warm-request"), QStringLiteral("summarize"), QVariant(), QStringLiteral("texto"), QStringLiteral("modelo:1"), QStringLiteral("127.0.0.1"), 11434, true);
        steam.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_VERIFY_WITH_TIMEOUT(!ai.busy() && !aiText.busy() && !steam.busy(), 1500);
        QCOMPARE(ai.providers().size(), 5);
        QCOMPARE(aiText.status(), QStringLiteral("completed"));
        QCOMPARE(steam.apps().size(), 1);
        for (const QString &owner : {QStringLiteral("provider"), QStringLiteral("text"), QStringLiteral("steam")}) QVERIFY(reaped(owner, true));
        controller.setQuery(QStringLiteral("Pending Close Game"));
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("ready"), 1500);
        const QVariantMap row = controller.rows().first().toMap();
        const QVariantMap ticket{{"row", 0}, {"generation", row.value("generation")}, {"id", row.value("id")}};
        const auto item = [&](const char *name) { return window->findChild<QQuickItem *>(QString::fromLatin1(name)); };
        auto *panel = item("aiSettings");
        auto *discover = item("aiDiscoverButton"); auto *probe = item("aiProbeButton"); auto *generate = item("aiTextGenerate");
        auto *scan = item("steamScanButton"); auto *downloads = item("steamDownloadsButton");
        auto *aiEntry = item("aiEntryButton"); auto *steamEntry = item("steamEntryButton");
        QVERIFY(panel && discover && probe && generate && scan && downloads && aiEntry && steamEntry);
        QVERIFY(item("aiTextInput")->setProperty("text", QStringLiteral("texto explícito")));
        QVERIFY(item("aiTextConsent")->setProperty("checked", true));
        QVERIFY(item("steamRootInput")->setProperty("text", QStringLiteral("native=/synthetic/root")));
        QVERIFY(QMetaObject::invokeMethod(aiEntry, "click"));
        QVERIFY(QMetaObject::invokeMethod(blockingOwner == QStringLiteral("provider") ? probe : generate, "click"));
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(receiptPath(blockingOwner, false)) && (ai.busy() || aiText.busy()), 1500);
        QSignalSpy dismissed(&controller, &LauncherController::closeRequested);
        QSignalSpy visibility(window, &QWindow::visibleChanged);
        QSignalSpy quitRequested(&engine, &QQmlApplicationEngine::quit);
        QSignalSpy providerReady(&ai, &AiProviderController::closeReady);
        QSignalSpy textReady(&aiText, &AiTextController::closeReady);
        QSignalSpy steamReady(&steam, &SteamProviderController::closeReady);
        bool hiddenAfterReap = false;
        connect(window, &QWindow::visibleChanged, &session, [&] {
            if (!window->isVisible()) hiddenAfterReap = !ai.busy() && !aiText.busy() && !steam.busy() && reaped(blockingOwner, false);
        });
        session.showFromShortcut();
        QVERIFY(window->property("pendingDismiss").toBool());
        QVERIFY(QMetaObject::invokeMethod(window, "requestDismiss", Q_ARG(QVariant, QVariant(true))));
        session.showFromShortcut();
        QVERIFY(window->property("pendingQuit").toBool());
        const int textGeneration = panel->property("textRequestGeneration").toInt();
        const bool startsDisabled = !discover->isEnabled() && !scan->isEnabled() && !downloads->isEnabled()
            && (blockingOwner == QStringLiteral("provider") ? !generate->isEnabled() && probe->isEnabled()
                                                             : !probe->isEnabled() && generate->isEnabled());
        QVERIFY(QMetaObject::invokeMethod(steamEntry, "clicked")); // Opening another panel cannot reopen start routes.
        const bool navigationStayedClosed = window->property("activePanel").toString() == QStringLiteral("ai");
        // Emit actual handlers even when disabled, including queued delivery of a stale click.
        for (auto *button : {providerStart == QStringLiteral("discover") ? discover : probe, generate, scan, downloads}) {
            const bool idleToggle = (button == generate && blockingOwner != QStringLiteral("text"))
                || (button == probe && blockingOwner != QStringLiteral("provider"));
            if (!idleToggle) QVERIFY(QMetaObject::invokeMethod(button, "clicked"));
            QVERIFY(QMetaObject::invokeMethod(button, "clicked", Qt::QueuedConnection));
        }
        QVERIFY(QMetaObject::invokeMethod(window, "executeTicket", Q_ARG(QVariant, QVariant(ticket)), Q_ARG(QVariant, QVariant(false))));
        QTest::qWait(10);
        const bool lateOwnerStarted = steam.busy() || (blockingOwner == QStringLiteral("provider") ? aiText.busy() : ai.busy());
        const bool generationUnchanged = panel->property("textRequestGeneration").toInt() == textGeneration;
        QTRY_VERIFY_WITH_TIMEOUT(!ai.busy() && !aiText.busy() && !steam.busy(), 2500);
        for (const QString &owner : {QStringLiteral("provider"), QStringLiteral("text"), QStringLiteral("steam")}) {
            for (bool warm : {true, false}) if (QFile::exists(receiptPath(owner, warm))) {
                QVERIFY(reaped(owner, warm));
                QFile file(receiptPath(owner, warm)); QVERIFY(file.open(QIODevice::ReadOnly));
                qInfo().noquote() << "ORLA_PENDING_CLOSE_HELPER" << owner << warm << file.readAll();
            }
        }
        qInfo() << "ORLA_PENDING_CLOSE_OBSERVED" << blockingOwner << providerStart << "late_started=" << lateOwnerStarted
            << "pending=" << window->property("pendingDismiss").toBool() << "dismissed=" << dismissed.count();
        // Causal assertions follow actual cleanup, so RED cannot abandon live helpers.
        QVERIFY2(!lateOwnerStarted, "A late operation started after its idle owner had accepted requestClose");
        QVERIFY(generationUnchanged);
        for (const QString &owner : {QStringLiteral("provider"), QStringLiteral("text"), QStringLiteral("steam")}) {
            QFile counter(directory.filePath(owner + QStringLiteral("-count")));
            QVERIFY(counter.open(QIODevice::ReadOnly));
            QCOMPARE(counter.readAll().toInt(), owner == blockingOwner ? 2 : 1);
            QCOMPARE(QFile::exists(receiptPath(owner, false)), owner == blockingOwner);
        }
        QVERIFY(startsDisabled);
        QVERIFY(navigationStayedClosed);
        QCOMPARE(opened.size(), 0);
        QCOMPARE(providerReady.count(), blockingOwner == QStringLiteral("provider") ? 1 : 0);
        QCOMPARE(textReady.count(), blockingOwner == QStringLiteral("text") ? 1 : 0);
        QCOMPARE(steamReady.count(), 0);
        QCOMPARE(dismissed.count(), 1);
        QCOMPARE(visibility.count(), 1);
        QCOMPARE(quitRequested.count(), 1);
        QVERIFY(hiddenAfterReap);
        QVERIFY(!window->isVisible());
        QVERIFY(!window->property("pendingDismiss").toBool() && !window->property("pendingQuit").toBool());
        QCOMPARE(aiText.output(), QStringLiteral("parcial-pendente"));
        QVERIFY(discover->isEnabled() && probe->isEnabled() && generate->isEnabled() && scan->isEnabled() && downloads->isEnabled());
        qInfo() << "ORLA_PENDING_CLOSE_PASS idle_starts_blocked=true queued_handlers_guarded=true quit_once=true helpers_reaped=true";
    }
};
QTEST_MAIN(UiTests)
#include "UiTests.moc"
