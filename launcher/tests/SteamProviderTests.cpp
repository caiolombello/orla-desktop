#include <QtTest>
#include <QFile>
#include <QDir>
#include <QJsonDocument>
#include <QTemporaryDir>
#include <QUrl>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQuickItem>
#include <QJSValue>
#include <QQuickWindow>
#include <memory>

#ifdef Q_OS_UNIX
#include <cerrno>
#include <csignal>
#include <unistd.h>
#endif

#include "SteamProviderController.h"

namespace {
QString writeHelper(QTemporaryDir &directory, const QByteArray &body)
{
    const QString path = directory.filePath(QStringLiteral("helper.py"));
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly)) return {};
    file.write(body);
    file.close();
    return path;
}

QByteArray availableDocument()
{
    return QByteArray(R"({"apps":[{"appid":"42","library":"library-0","name":"Synthetic Game","ownership":"unknown","source":"local_manifest","status":"installed_candidate"}],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"available"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"available"}],"schema_version":"0.1-experimental","status":"available"})") + "\n";
}

QByteArray partialDocument()
{
    return QByteArray(R"({"apps":[{"appid":"42","library":"library-0","name":"Synthetic Game","ownership":"unknown","source":"local_manifest","status":"installed_candidate"}],"connection":"unknown","errors":[{"code":"pathlike_name_redacted","library":"library-0","appid":"42"}],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"partial"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"partial"}],"schema_version":"0.1-experimental","status":"partial"})") + "\n";
}

#ifdef Q_OS_UNIX
bool processExists(qint64 pid)
{
    errno = 0;
    return ::kill(static_cast<pid_t>(pid), 0) == 0 || errno == EPERM;
}

QByteArray processStartId(qint64 pid)
{
    QFile file(QStringLiteral("/proc/%1/stat").arg(pid));
    if (!file.open(QIODevice::ReadOnly)) return {};
    const QByteArray stat = file.readAll();
    const qsizetype close = stat.lastIndexOf(") ");
    if (close < 0) return {};
    const QList<QByteArray> fields = stat.mid(close + 2).split(' ');
    return fields.size() > 19 ? fields[19] : QByteArray();
}

bool killValidatedFixture(qint64 pid, const QByteArray &startId, const QByteArray &token)
{
    if (!processExists(pid)) return true;
    QFile command(QStringLiteral("/proc/%1/cmdline").arg(pid));
    if (!command.open(QIODevice::ReadOnly) || !command.readAll().contains(token)
        || processStartId(pid) != startId) return false;
    return ::kill(static_cast<pid_t>(pid), SIGKILL) == 0;
}
#endif
}

class SteamProviderTests final : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void locatesNativeRootOnlyFromTheExplicitDataBase()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString home = directory.filePath(QStringLiteral("home"));
        const QString data = directory.filePath(QStringLiteral("data"));
        QVERIFY(QDir().mkpath(home));
        QVERIFY(QDir().mkpath(data + QStringLiteral("/Steam")));
        QCOMPARE(SteamProviderController::discoverLocalRoots(home, data),
                 QStringList{QStringLiteral("native=") + data + QStringLiteral("/Steam")});
    }

    void knownRootsAreCanonicalAndDeduplicated_data()
    {
        QTest::addColumn<QString>("scenario");
        for (const QString &scenario : {QStringLiteral("absent"), QStringLiteral("flatpak"),
                QStringLiteral("root-alias"), QStringLiteral("steam-alias"),
                QStringLiteral("deduplicated"), QStringLiteral("both-kinds"),
                QStringLiteral("file-and-broken-link"), QStringLiteral("invalid-bases"),
                QStringLiteral("unsafe-canonical-target")})
            QTest::newRow(qPrintable(scenario)) << scenario;
    }

    void knownRootsAreCanonicalAndDeduplicated()
    {
        QFETCH(QString, scenario);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        QString home = directory.filePath(QStringLiteral("home"));
        QString data = directory.filePath(QStringLiteral("data"));
        const QString native = data + QStringLiteral("/Steam");
        const QString flatpak = home + QStringLiteral("/.var/app/com.valvesoftware.Steam/data/Steam");
        const QString target = directory.filePath(QStringLiteral("alias target"));
        QStringList expected;
        QVERIFY(QDir().mkpath(home + QStringLiteral("/.steam")));
        QVERIFY(QDir().mkpath(data));
        if (scenario == QStringLiteral("flatpak")) {
            QVERIFY(QDir().mkpath(flatpak));
            expected = {QStringLiteral("flatpak=") + flatpak};
        } else if (scenario == QStringLiteral("root-alias") || scenario == QStringLiteral("steam-alias")) {
            QVERIFY(QDir().mkpath(target));
            const QString alias = scenario == QStringLiteral("root-alias") ? QStringLiteral("root") : QStringLiteral("steam");
            QVERIFY(QFile::link(target, home + QStringLiteral("/.steam/") + alias));
            expected = {QStringLiteral("native=") + target};
        } else if (scenario == QStringLiteral("deduplicated")) {
            QVERIFY(QDir().mkpath(native));
            QVERIFY(QFile::link(native, home + QStringLiteral("/.steam/root")));
            QVERIFY(QFile::link(native, home + QStringLiteral("/.steam/steam")));
            QVERIFY(QDir().mkpath(QFileInfo(flatpak).path()));
            QVERIFY(QFile::link(native, flatpak));
            expected = {QStringLiteral("native=") + native};
        } else if (scenario == QStringLiteral("both-kinds")) {
            QVERIFY(QDir().mkpath(native));
            QVERIFY(QDir().mkpath(flatpak));
            expected = {QStringLiteral("native=") + native, QStringLiteral("flatpak=") + flatpak};
        } else if (scenario == QStringLiteral("file-and-broken-link")) {
            QFile file(native);
            QVERIFY(file.open(QIODevice::WriteOnly));
            file.close();
            QVERIFY(QFile::link(target, home + QStringLiteral("/.steam/root")));
        } else if (scenario == QStringLiteral("invalid-bases")) {
            QVERIFY(QDir().mkpath(native));
            QVERIFY(QDir().mkpath(home + QStringLiteral("/Steam")));
            for (const QString &invalid : {QString(), QStringLiteral("relative"), QStringLiteral(":/resource"),
                    home + QStringLiteral("/../home"), home + QStringLiteral("/"),
                    home + QChar::Null, home + QStringLiteral("\n"),
                    home + QChar(0x202e), QStringLiteral("/")})
                QVERIFY(SteamProviderController::discoverLocalRoots(invalid, invalid).isEmpty());
            return;
        } else if (scenario == QStringLiteral("unsafe-canonical-target")) {
            const QString unsafe = directory.filePath(QStringLiteral("bad\nroot"));
            QVERIFY(QDir().mkpath(unsafe));
            QVERIFY(QFile::link(unsafe, native));
        }
        QCOMPARE(SteamProviderController::discoverLocalRoots(home, data), expected);
    }

    void locatingRootsFillsThePanelWithoutScanning_data()
    {
        QTest::addColumn<int>("width");
        QTest::newRow("narrow") << 440;
        QTest::newRow("standard") << 660;
    }

    void locatingRootsFillsThePanelWithoutScanning()
    {
        QFETCH(int, width);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString home = directory.filePath(QStringLiteral("home"));
        const QString data = directory.filePath(QStringLiteral("data"));
        const QString native = data + QStringLiteral("/Steam");
        QVERIFY(QDir().mkpath(home));
        QVERIFY(QDir().mkpath(native));
        const QString marker = directory.filePath(QStringLiteral("scan-started"));
        const QString helper = writeHelper(directory, QByteArray("import base64,pathlib,sys\n")
            + "pathlib.Path(r'" + marker.toUtf8() + "').touch()\n"
            + "sys.stdout.buffer.write(base64.b64decode('" + availableDocument().toBase64() + "'))\n");
        int locates = 0;
        QList<QUrl> opened;
        SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            [&opened](const QUrl &url) { opened.append(url); return true; }, nullptr,
            [&] { ++locates; return SteamProviderController::discoverLocalRoots(home, data); });
        QQmlEngine engine;
        const QUrl panelUrl = QUrl::fromLocalFile(QFileInfo(QStringLiteral(ORLA_TEST_STEAM_HELPER)).dir()
            .filePath(QStringLiteral("../launcher/SteamSettings.qml")));
        QQmlComponent component(&engine, panelUrl);
        QVERIFY2(component.isReady(), qPrintable(component.errorString()));
        QQuickWindow window;
        window.resize(width, 420);
        std::unique_ptr<QObject> object(component.createWithInitialProperties(
            {{QStringLiteral("controller"), QVariant::fromValue(&controller)}}));
        auto *panel = qobject_cast<QQuickItem *>(object.get());
        QVERIFY(panel);
        panel->setParentItem(window.contentItem());
        panel->setSize(QSizeF(width, 420));
        window.setColor(QColor(panel->property("ui").value<QJSValue>().property("canvas").toString()));
        window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        auto *locate = panel->findChild<QQuickItem *>(QStringLiteral("steamLocateRootsButton"));
        auto *input = panel->findChild<QQuickItem *>(QStringLiteral("steamRootInput"));
        auto *message = panel->findChild<QQuickItem *>(QStringLiteral("steamRootDiscoveryMessage"));
        auto *scan = panel->findChild<QQuickItem *>(QStringLiteral("steamScanButton"));
        QVERIFY(locate && input && message && scan);
        QVERIFY(locate->mapToItem(panel, QPointF(locate->width(), 0)).x() <= width);
        QCOMPARE(locates, 0);
        QVERIFY(!QFile::exists(marker));
        QVERIFY(input->setProperty("text", QStringLiteral("native=/manual/synthetic")));
        locate->forceActiveFocus();
        QTest::keyClick(&window, Qt::Key_Space);
        QCOMPARE(locates, 1);
        QCOMPARE(input->property("text").toString(), QStringLiteral("native=") + native);
        QVERIFY(!message->property("text").toString().isEmpty());
        QCOMPARE(controller.status(), QStringLiteral("unconfigured"));
        QCOMPARE(controller.inventoryRevision(), quint64(0));
        QVERIFY(controller.apps().isEmpty());
        QVERIFY(!controller.busy());
        QVERIFY(!QFile::exists(marker));
        QVERIFY(opened.isEmpty());

        QVERIFY(QMetaObject::invokeMethod(scan, "click"));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("available"));
        QCOMPARE(controller.apps().size(), 1);
        const quint64 revision = controller.inventoryRevision();
        QVERIFY(QFile::exists(marker));
        QVERIFY(QFile::remove(marker));
        QVERIFY(QMetaObject::invokeMethod(locate, "click"));
        QCOMPARE(controller.status(), QStringLiteral("available"));
        QCOMPARE(controller.inventoryRevision(), revision);
        QCOMPARE(controller.apps().size(), 1);
        QVERIFY(!QFile::exists(marker));
        QVERIFY(opened.isEmpty());

        QVERIFY(QDir(native).removeRecursively());
        const QString manual = QStringLiteral("native=/manual/synthetic");
        QVERIFY(input->setProperty("text", manual));
        QVERIFY(QMetaObject::invokeMethod(locate, "click"));
        QCOMPARE(input->property("text").toString(), manual);
        QVERIFY(message->property("text").toString().contains(QStringLiteral("locais conhecidos")));
        QCOMPARE(controller.status(), QStringLiteral("available"));
        QCOMPARE(controller.inventoryRevision(), revision);
        QCOMPARE(controller.apps().size(), 1);
        QVERIFY(!QFile::exists(marker));

        const int beforeBlock = locates;
        QVERIFY(panel->setProperty("operationStartBlocked", true));
        QVERIFY(!locate->isEnabled());
        QVERIFY(QMetaObject::invokeMethod(locate, "clicked"));
        QCOMPARE(locates, beforeBlock);
        QCOMPARE(input->property("text").toString(), manual);
        QVERIFY(panel->setProperty("operationStartBlocked", false));
        controller.scan({manual});
        QVERIFY(controller.busy());
        QVERIFY(!locate->isEnabled());
        QVERIFY(QMetaObject::invokeMethod(locate, "clicked"));
        QCOMPARE(locates, beforeBlock);
        QCOMPARE(input->property("text").toString(), manual);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QVERIFY(QFile::exists(marker));
        QVERIFY(opened.isEmpty());
        const QString capture = qEnvironmentVariable("ORLA_UI_CAPTURE_DIR");
        if (!capture.isEmpty()) {
            QTest::qWait(100);
            const QImage image = window.grabWindow();
            QVERIFY(!image.isNull());
            QVERIFY(image.save(QDir(capture).filePath(QStringLiteral("steam-discovery-empty-%1.png").arg(width))));
        }
    }

    void constructionDoesNothingAndExplicitScanPublishesOnlyValidatedInventory()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString helper = writeHelper(directory,
            QByteArray("import base64,pathlib,sys\n")
            + "pathlib.Path(r'" + marker.toUtf8() + "').touch()\n"
            + "assert sys.argv[1:] == ['scan','--root','native=/synthetic/root with spaces']\n"
            + "sys.stdout.buffer.write(base64.b64decode('" + availableDocument().toBase64() + "'))\n");
        QList<QUrl> opened;
        SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            [&opened](const QUrl &url) { opened.append(url); return true; });

        QCOMPARE(controller.status(), QStringLiteral("unconfigured"));
        QVERIFY(!controller.busy());
        QVERIFY(controller.apps().isEmpty());
        QVERIFY(!QFile::exists(marker));

        controller.scan({QStringLiteral("native=/synthetic/root with spaces")});
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("available"));
        QCOMPARE(controller.apps().size(), 1);
        QVERIFY(QFile::exists(marker));
        QVERIFY(opened.isEmpty());

        const quint64 revision = controller.inventoryRevision();
        QVERIFY(controller.openGame(QStringLiteral("42"), QStringLiteral("library-0"), revision));
        QCOMPARE(opened, QList<QUrl>{QUrl(QStringLiteral("steam://rungameid/42"))});

        controller.scan({QStringLiteral("native=/synthetic/root with spaces")});
        QVERIFY(controller.apps().isEmpty());
        QCOMPARE(opened.size(), 1); // Reload is discovery only; it cannot replay the old action.
        controller.cancelAll();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
    }

    void rejectsControlCharactersAndDuplicateAppIdentity()
    {
        const QList<QByteArray> invalidDocuments = {
            QByteArray(availableDocument()).replace("Synthetic Game", "Synthetic\\nGame"),
            QByteArray(availableDocument()).replace(
                "}],\"connection\"", "},{\"appid\":\"42\",\"library\":\"library-0\",\"name\":\"Duplicate\",\"ownership\":\"unknown\",\"source\":\"local_manifest\",\"status\":\"installed_candidate\"}],\"connection\"")};
        for (const QByteArray &document : invalidDocuments) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + document.toBase64() + "'))\n");
            SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            controller.scan({QStringLiteral("native=/synthetic/root")});
            QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
            QCOMPARE(controller.status(), QStringLiteral("error"));
            QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
            QVERIFY(controller.apps().isEmpty());
        }
    }

    void rejectsInvalidRootsAndDuplicateJsonKeysBeforePublishing()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString helper = writeHelper(directory,
            QByteArray("import pathlib\npathlib.Path(r'") + marker.toUtf8() + "').touch()\n");
        SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        for (const QStringList &roots : {QStringList{}, {QStringLiteral("garbage=/absolute")},
                                        {QStringLiteral("native=relative")},
                                        {QStringLiteral("native=/bad\npath")},
                                        QStringList(9, QStringLiteral("native=/synthetic/root"))}) {
            controller.scan(roots);
            QCOMPARE(controller.errorCode(), QStringLiteral("invalid_roots"));
            QVERIFY(!QFile::exists(marker));
        }

        QByteArray duplicate = availableDocument();
        duplicate.replace("\"status\":\"available\"}",
                          "\"status\":\"available\",\"status\":\"available\"}");
        const QString duplicateHelper = writeHelper(directory,
            QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
            + duplicate.toBase64() + "'))\n");
        SteamProviderController duplicateController(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), duplicateHelper);
        duplicateController.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_VERIFY_WITH_TIMEOUT(!duplicateController.busy(), 3000);
        QCOMPARE(duplicateController.errorCode(), QStringLiteral("invalid_helper_response"));
        QVERIFY(duplicateController.apps().isEmpty());

        SteamProviderController missingController(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                                   directory.filePath(QStringLiteral("missing-helper.py")));
        missingController.scan({QStringLiteral("native=/synthetic/root")});
        QCOMPARE(missingController.errorCode(), QStringLiteral("helper_unavailable"));
        QVERIFY(!missingController.busy());
    }

    void rejectsMissingNewlineNonAsciiAndOversizedOutput()
    {
        const QList<QByteArray> invalidDocuments = {
            QByteArray(availableDocument()).chopped(1),
            QByteArray(availableDocument()).replace("Synthetic Game", "Synthetic \xc3\xa9 Game"),
            QByteArray(512 * 1024 + 2, 'x')};
        for (const QByteArray &document : invalidDocuments) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + document.toBase64() + "'))\n");
            SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            controller.scan({QStringLiteral("native=/synthetic/root")});
            QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 5000);
            QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
            QVERIFY(controller.apps().isEmpty());
        }
    }

    void fixedDownloadsUriReportsAnInjectedOpenFailure()
    {
        QList<QUrl> attempted;
        SteamProviderController controller(QStringLiteral("/missing/python"),
            QStringLiteral("/missing/helper"), [&attempted](const QUrl &url) {
                attempted.append(url);
                return false;
            });
        QVERIFY(!controller.openDownloads());
        QCOMPARE(attempted, QList<QUrl>{QUrl(QStringLiteral("steam://open/downloads"))});
        QCOMPARE(controller.errorCode(), QStringLiteral("open_failed"));
        QVERIFY(!controller.openGame(QStringLiteral("42"), QStringLiteral("library-0"), 0));
        QCOMPARE(attempted.size(), 1);
    }

    void deadlineFailsClosedAndReapsTheDirectHelper()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory,
            QByteArray("import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(60)\n"));
        SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        controller.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 14000);
        QCOMPARE(controller.status(), QStringLiteral("error"));
        QCOMPARE(controller.errorCode(), QStringLiteral("operation_timeout"));
        QVERIFY(controller.apps().isEmpty());
    }

    void exitCodeMustMatchTheValidatedInventoryStatus()
    {
        for (const int exitCode : {2, 0}) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + partialDocument().toBase64() + "'))\nraise SystemExit(" + QByteArray::number(exitCode) + ")\n");
            SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            controller.scan({QStringLiteral("native=/synthetic/root")});
            QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
            if (exitCode == 2) {
                QCOMPARE(controller.status(), QStringLiteral("partial"));
                QCOMPARE(controller.issueCount(), 1);
                QCOMPARE(controller.apps().size(), 1);
            } else {
                QCOMPARE(controller.status(), QStringLiteral("error"));
                QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
                QVERIFY(controller.apps().isEmpty());
            }
        }
    }

    void rejectsImpossibleInventoryGraphsWithoutMakingThemExecutable()
    {
        const QList<QPair<QByteArray, int>> invalidDocuments = {
            {QByteArray(R"({"apps":[{"appid":"42","library":"library-0","name":"Impossible Game","ownership":"unknown","source":"local_manifest","status":"installed_candidate"}],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"missing"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"absent"}],"schema_version":"0.1-experimental","status":"available"})") + "\n", 0},
            {QByteArray(R"({"apps":[],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"partial"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"partial"}],"schema_version":"0.1-experimental","status":"available"})") + "\n", 0},
            {QByteArray(R"({"apps":[],"connection":"unknown","errors":[{"code":"missing","library":"library-0"}],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"missing"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"unknown"}],"schema_version":"0.1-experimental","status":"partial"})") + "\n", 2},
            {QByteArray(R"({"apps":[{"appid":"42","library":"library-0","name":"Uncertain Game","ownership":"unknown","source":"local_manifest","status":"partial"}],"connection":"unknown","errors":[{"appid":"42","code":"missing","library":"library-0"}],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"available"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"available"}],"schema_version":"0.1-experimental","status":"partial"})") + "\n", 2}};
        for (const auto &[document, exitCode] : invalidDocuments) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + document.toBase64() + "'))\nraise SystemExit(" + QByteArray::number(exitCode) + ")\n");
            QList<QUrl> opened;
            SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
                [&opened](const QUrl &url) { opened.append(url); return true; });
            controller.scan({QStringLiteral("native=/synthetic/root")});
            QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
            QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
            QVERIFY(controller.apps().isEmpty());
            QVERIFY(!controller.openGame(QStringLiteral("42"), QStringLiteral("library-0"),
                                         controller.inventoryRevision()));
            QVERIFY(opened.isEmpty());
        }
    }

    void closeWaitsUntilATermIgnoringOwnedDescendantIsReaped()
    {
#ifndef Q_OS_UNIX
        QSKIP("Process-group cleanup is Unix-specific");
#else
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString identityPath = directory.filePath(QStringLiteral("descendant.identity"));
        const QByteArray token = QByteArray("orla-steam-owned-") + QByteArray::number(QCoreApplication::applicationPid());
        const QByteArray childCode = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)";
        const QString helper = writeHelper(directory,
            QByteArray("import pathlib,subprocess,time\n")
            + "child=subprocess.Popen(['/usr/bin/python3','-c',r'" + childCode + "',r'" + token
            + "'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
            + "stat=pathlib.Path(f'/proc/{child.pid}/stat').read_text();tail=stat[stat.rfind(') ')+2:].split()\n"
            + "pathlib.Path(r'" + identityPath.toUtf8() + "').write_text(f'{child.pid} {tail[19]}')\n"
            + "time.sleep(60)\n");
        SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QSignalSpy closeReady(&controller, &SteamProviderController::closeReady);
        controller.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(identityPath), 3000);
        QVERIFY(controller.busy());
        QVERIFY(!controller.requestClose());
        QCOMPARE(closeReady.size(), 0);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 7000);
        QCOMPARE(closeReady.size(), 1);
        QFile identity(identityPath);
        QVERIFY(identity.open(QIODevice::ReadOnly));
        const QList<QByteArray> parts = identity.readAll().trimmed().split(' ');
        QCOMPARE(parts.size(), 2);
        const qint64 pid = parts[0].toLongLong();
        if (processExists(pid)) {
            QVERIFY2(killValidatedFixture(pid, parts[1], token), "refused to signal an unvalidated fixture process");
            QFAIL("close became ready while its validated TERM-ignoring descendant survived");
        }
        QCOMPARE(controller.status(), QStringLiteral("idle"));
        QVERIFY(controller.apps().isEmpty());
#endif
    }

    void realHelperReadsOnlyTheOwnedSyntheticRoot()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString root = directory.filePath(QStringLiteral("native"));
        QVERIFY(QDir().mkpath(root + QStringLiteral("/steamapps/common/Synthetic Game")));
        QFile libraries(root + QStringLiteral("/steamapps/libraryfolders.vdf"));
        QVERIFY(libraries.open(QIODevice::WriteOnly));
        libraries.write(QByteArray("\"libraryfolders\" { \"0\" { \"path\" \"")
                        + root.toUtf8() + "\" } }");
        libraries.close();
        QFile manifest(root + QStringLiteral("/steamapps/appmanifest_42.acf"));
        QVERIFY(manifest.open(QIODevice::WriteOnly));
        manifest.write("\"AppState\" { \"appid\" \"42\" \"name\" \"Synthetic Game\" "
                       "\"StateFlags\" \"4\" \"installdir\" \"Synthetic Game\" }");
        manifest.close();

        SteamProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                           QStringLiteral(ORLA_TEST_STEAM_HELPER));
        controller.scan({QStringLiteral("native=") + root});
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 5000);
        QCOMPARE(controller.status(), QStringLiteral("available"));
        QCOMPARE(controller.apps().size(), 1);
        const QVariantMap app = controller.apps().first().toMap();
        QCOMPARE(app.value(QStringLiteral("appid")).toString(), QStringLiteral("42"));
        QCOMPARE(app.value(QStringLiteral("ownership")).toString(), QStringLiteral("unknown"));
        QVERIFY(!QString::fromUtf8(QJsonDocument::fromVariant(controller.apps()).toJson()).contains(directory.path()));

        controller.scan({QStringLiteral("native=") + root, QStringLiteral("native=") + root});
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 5000);
        QCOMPARE(controller.status(), QStringLiteral("available"));
        QCOMPARE(controller.apps().size(), 1); // The pinned helper deduplicates the repeated library path.
    }
};

QTEST_MAIN(SteamProviderTests)
#include "SteamProviderTests.moc"
