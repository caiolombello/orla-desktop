#include <QtTest>
#include <QEventLoop>
#include <QFile>
#include <QCryptographicHash>
#include <QDir>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTimer>
#include <QElapsedTimer>
#include "AiProviderController.h"

#include <cerrno>
#include <csignal>
#include <unistd.h>

namespace {
QString writeHelper(QTemporaryDir &directory, const QByteArray &body)
{
    const QString path = directory.filePath(QStringLiteral("helper.py"));
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) return {};
    file.write(body);
    file.close();
    return path;
}

QByteArray providerDocument(const QByteArray &operation)
{
    const QByteArray capabilities = R"({"installation":"supported","anonymous_protocol":"unknown","authentication":"unknown","inference":"unknown","cancellation":"unknown","usage_reporting":"unknown"})";
    const QByteArray providers =
        QByteArray("[")
        + R"({"id":"codex","displayName":"Codex","enabled":false,"clientVersion":"0.162.1","capabilities":)" + capabilities + R"(,"route":"owned_app_server","messageCode":"client_version_recognized"},)"
        + R"({"id":"claude","displayName":"Claude Code","enabled":false,"clientVersion":"2.1.287","capabilities":)" + capabilities + R"(,"route":"official_terminal_handoff","messageCode":"client_version_recognized"},)"
        + R"({"id":"opencode","displayName":"OpenCode","enabled":false,"clientVersion":"2.0.24","capabilities":)" + capabilities + R"(,"route":"selected_local_server","messageCode":"client_version_recognized"},)"
        + R"({"id":"ollama","displayName":"Ollama","enabled":false,"clientVersion":null,"capabilities":)" + capabilities + R"(,"route":"selected_local_server","messageCode":"cli_present_version_not_queried"},)"
        + R"({"id":"lmstudio","displayName":"LM Studio","enabled":false,"clientVersion":"0.3.9","capabilities":)" + capabilities + R"(,"route":"selected_local_server","messageCode":"client_version_recognized"}])";
    if (operation == "detect") return QByteArray("{\"schemaVersion\":1,\"providers\":") + providers + "}\n";
    return QByteArray(R"({"schemaVersion":1,"provider":{"id":"codex","displayName":"Codex","enabled":false,"clientVersion":"0.162.1","capabilities":{"installation":"supported","anonymous_protocol":"supported","authentication":"unknown","inference":"unknown","cancellation":"unknown","usage_reporting":"unknown"},"route":"owned_app_server","messageCode":"anonymous_protocol_supported"}})") + "\n";
}

QByteArray capabilities(const QByteArray &installation, const QByteArray &protocol)
{
    const QByteArray dependent = installation == "absent" ? "absent" : "unknown";
    return QByteArray("{\"installation\":\"") + installation
        + "\",\"anonymous_protocol\":\"" + protocol
        + "\",\"authentication\":\"unknown\",\"inference\":\"" + dependent
        + "\",\"cancellation\":\"" + dependent + "\",\"usage_reporting\":\"unknown\"}";
}

QByteArray provider(const QByteArray &id, const QByteArray &installation, const QByteArray &protocol,
                    const QByteArray &message, const QByteArray &version = {})
{
    QByteArray name;
    QByteArray route;
    if (id == "codex") { name = "Codex"; route = "owned_app_server"; }
    else if (id == "claude") { name = "Claude Code"; route = "official_terminal_handoff"; }
    else if (id == "opencode") { name = "OpenCode"; route = "selected_local_server"; }
    else if (id == "ollama") { name = "Ollama"; route = "selected_local_server"; }
    else { name = "LM Studio"; route = "selected_local_server"; }
    const QByteArray encodedVersion = version.isEmpty() ? QByteArray("null")
        : QByteArray("\"") + version + "\"";
    return QByteArray("{\"id\":\"") + id + "\",\"displayName\":\"" + name
        + "\",\"enabled\":false,\"clientVersion\":" + encodedVersion
        + ",\"capabilities\":" + capabilities(installation, protocol)
        + ",\"route\":\"" + route + "\",\"messageCode\":\"" + message + "\"}";
}

QByteArray detectDocument(const QList<QByteArray> &items)
{
    return QByteArray("{\"schemaVersion\":1,\"providers\":[")
        + QByteArrayList(items.cbegin(), items.cend()).join(',') + "]}\n";
}

QByteArray probeDocument(const QByteArray &item)
{
    return QByteArray("{\"schemaVersion\":1,\"provider\":") + item + "}\n";
}

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
    if (!command.open(QIODevice::ReadOnly) || command.readAll().contains(token) == false
        || processStartId(pid) != startId) return false;
    return ::kill(static_cast<pid_t>(pid), SIGKILL) == 0;
}
}

class AiProviderTests final : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void constructionIsDisabledAndDoesNotStartTheHelper()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString helper = writeHelper(directory, QByteArray("from pathlib import Path\nPath(")
            + QByteArray("r'") + marker.toUtf8() + QByteArray("').touch()\n"));
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QCOMPARE(controller.status(), QStringLiteral("disabled"));
        QVERIFY(!controller.busy());
        QVERIFY(controller.providers().isEmpty());
        QVERIFY(!QFile::exists(marker));
    }

    void explicitDiscoveryAcceptsOnlyTheClosedSchema()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory, QByteArray());
        QFile fixture(helper);
        QVERIFY(fixture.open(QIODevice::WriteOnly | QIODevice::Truncate));
        fixture.write("import base64,sys\nassert sys.argv[1] == 'detect' and sys.argv[2] == '--runtime-root' and sys.argv[4] == '--runtime-root-id' and len(sys.argv) == 6\nprint(base64.b64decode('");
        fixture.write(providerDocument("detect").toBase64());
        fixture.write("').decode(), end='')\n");
        fixture.close();
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QSignalSpy changed(&controller, &AiProviderController::changed);
        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("report_available"));
        QCOMPARE(controller.providers().size(), 5);
        QCOMPARE(controller.providers().first().toMap().value("id").toString(), QStringLiteral("codex"));
        QVERIFY(changed.count() > 0);
    }

    void directInitialChangedCancellationDoesNotLaunchAProcessGroup()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory, QByteArray("import time\ntime.sleep(60)\n"));
        bool observedGroup = false;
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            [&](qint64 group) {
                observedGroup = observedGroup || group > 0;
                return false;
            });
        bool cancelled = false;
        connect(&controller, &AiProviderController::changed, &controller, [&] {
            if (!cancelled && controller.status() == QStringLiteral("running")) {
                cancelled = true;
                controller.cancelAll();
            }
        }, Qt::DirectConnection);

        controller.discover();
        QVERIFY(cancelled);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 7000);
        QVERIFY(!observedGroup);
    }

    void directInitialChangedCloseDoesNotLaunchAProcessGroup()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory, QByteArray("import time\ntime.sleep(60)\n"));
        bool observedGroup = false;
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            [&](qint64 group) {
                observedGroup = observedGroup || group > 0;
                return false;
            });
        bool closeRequested = false;
        connect(&controller, &AiProviderController::changed, &controller, [&] {
            if (!closeRequested && controller.status() == QStringLiteral("running")) {
                closeRequested = true;
                QVERIFY(!controller.requestClose());
            }
        }, Qt::DirectConnection);
        QSignalSpy closeReady(&controller, &AiProviderController::closeReady);

        controller.discover();
        QVERIFY(closeRequested);
        QTRY_COMPARE_WITH_TIMEOUT(closeReady.size(), 1, 7000);
        QVERIFY(!controller.busy());
        QVERIFY(!observedGroup);
    }

    void nestedEventLoopDuringInitialCloseCannotInvalidateRuntimeBeforeStart()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory, QByteArray("import time\ntime.sleep(60)\n"));
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        bool closeRequested = false;
        QSignalSpy closeReady(&controller, &AiProviderController::closeReady);
        connect(&controller, &AiProviderController::changed, &controller, [&] {
            if (!closeRequested && controller.status() == QStringLiteral("running")) {
                closeRequested = true;
                QVERIFY(!controller.requestClose());
                QEventLoop nested;
                QTimer::singleShot(100, &nested, &QEventLoop::quit);
                nested.exec();
            }
        }, Qt::DirectConnection);

        controller.discover();
        QVERIFY(closeRequested);
        QCOMPARE(closeReady.size(), 1);
        QVERIFY(!controller.busy());
    }

    void directChangedRestartKeepsTheNewGenerationIdentity()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString counter = directory.filePath(QStringLiteral("counter"));
        const QString helper = writeHelper(directory,
            QByteArray("import base64,pathlib,sys,time\ncounter=pathlib.Path(r'")
            + counter.toUtf8()
            + "')\ncount=int(counter.read_text()) if counter.exists() else 0\n"
              "counter.write_text(str(count+1))\n"
              "if count == 0:\n sys.stdout.buffer.write(base64.b64decode('"
            + providerDocument("detect").toBase64()
            + "'))\nelse:\n time.sleep(60)\n");
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        int restartCount = 0;
        connect(&controller, &AiProviderController::changed, &controller, [&] {
            if (restartCount == 0 && !controller.busy()
                && controller.status() == QStringLiteral("report_available")) {
                ++restartCount;
                controller.discover();
            }
        }, Qt::DirectConnection);

        controller.discover();
        QTRY_COMPARE_WITH_TIMEOUT(restartCount, 1, 3000);
        QTRY_COMPARE_WITH_TIMEOUT([&] {
            QFile observed(counter);
            if (!observed.open(QIODevice::ReadOnly)) return QByteArray();
            return observed.readAll();
        }(), QByteArray("2"), 3000);
        QVERIFY(controller.busy());
        QCOMPARE(controller.operation(), QStringLiteral("detect"));
        QCOMPARE(controller.requestId(), QStringLiteral("detect-2"));

        controller.cancelAll();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 7000);
    }

    void pendingCloseCompletesBeforeDirectChangedCanRestart()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString counter = directory.filePath(QStringLiteral("counter"));
        const QString helper = writeHelper(directory,
            QByteArray("import pathlib,time\ncounter=pathlib.Path(r'") + counter.toUtf8()
            + "')\ncount=int(counter.read_text()) if counter.exists() else 0\n"
              "counter.write_text(str(count+1))\ntime.sleep(60)\n");
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        bool restartArmed = false;
        int restartCount = 0;
        int closeReadyCount = 0;
        bool busyAtCloseReady = true;
        connect(&controller, &AiProviderController::changed, &controller, [&] {
            if (restartArmed && restartCount == 0 && !controller.busy()) {
                ++restartCount;
                controller.discover();
            }
        }, Qt::DirectConnection);
        connect(&controller, &AiProviderController::closeReady, &controller, [&] {
            ++closeReadyCount;
            busyAtCloseReady = controller.busy();
        }, Qt::DirectConnection);

        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(counter), 3000);
        restartArmed = true;
        QVERIFY(!controller.requestClose());
        QTRY_COMPARE_WITH_TIMEOUT(closeReadyCount, 1, 7000);
        QVERIFY(!busyAtCloseReady);
        QCOMPARE(restartCount, 0);
        QVERIFY(!controller.busy());
        QVERIFY(controller.operation().isEmpty());
        QVERIFY(controller.requestId().isEmpty());
    }

    void readonlyStagedHelperUsesUniqueExternalRuntimeAndLeavesStageUnchanged()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString stage = directory.filePath(QStringLiteral("readonly stage"));
        const QString libexec = stage + QStringLiteral("/libexec");
        QVERIFY(QDir().mkpath(libexec));
        const QString observed = directory.filePath(QStringLiteral("observed-runtime"));
        const QString helper = libexec + QStringLiteral("/ai.py");
        QFile fixture(helper);
        QVERIFY(fixture.open(QIODevice::WriteOnly));
        fixture.write("import base64,pathlib,sys\nassert sys.argv[1] == 'detect' and sys.argv[2] == '--runtime-root' and sys.argv[4] == '--runtime-root-id' and len(sys.argv) == 6\nroot=pathlib.Path(sys.argv[3])\n"
                      "assert root.is_absolute() and (root.stat().st_mode & 0o777) == 0o700\n"
                      "pathlib.Path(r'");
        fixture.write(observed.toUtf8());
        fixture.write("').write_text(str(root))\n(root/'owned-child').mkdir()\n"
                      "sys.stdout.buffer.write(base64.b64decode('");
        fixture.write(providerDocument("detect").toBase64());
        fixture.write("'))\n");
        fixture.close();
        QFile beforeFile(helper);
        QVERIFY(beforeFile.open(QIODevice::ReadOnly));
        const QByteArray before = QCryptographicHash::hash(beforeFile.readAll(), QCryptographicHash::Sha256);
        beforeFile.close();
        QVERIFY(QFile::setPermissions(helper, QFileDevice::ReadOwner));
        QVERIFY(QFile::setPermissions(libexec, QFileDevice::ReadOwner | QFileDevice::ExeOwner));
        QVERIFY(QFile::setPermissions(stage, QFileDevice::ReadOwner | QFileDevice::ExeOwner));
        const QFileDevice::Permissions beforePermissions = QFileInfo(helper).permissions();

        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("report_available"));
        QFile observedFile(observed);
        QVERIFY(observedFile.open(QIODevice::ReadOnly));
        const QString runtime = QString::fromUtf8(observedFile.readAll());
        QVERIFY(QDir::isAbsolutePath(runtime));
        QVERIFY(!QFileInfo::exists(runtime));
        observedFile.close();
        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QVERIFY(observedFile.open(QIODevice::ReadOnly));
        const QString secondRuntime = QString::fromUtf8(observedFile.readAll());
        QVERIFY(secondRuntime != runtime);
        QVERIFY(!QFileInfo::exists(secondRuntime));
        QFile afterFile(helper);
        QVERIFY(afterFile.open(QIODevice::ReadOnly));
        QCOMPARE(QCryptographicHash::hash(afterFile.readAll(), QCryptographicHash::Sha256), before);
        QCOMPARE(QFileInfo(helper).permissions(), beforePermissions);
        QCOMPARE(QDir(stage).entryList(QDir::AllEntries | QDir::NoDotAndDotDot), QStringList{QStringLiteral("libexec")});
        QVERIFY(QFile::setPermissions(libexec, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));
        QVERIFY(QFile::setPermissions(stage, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));
    }

    void invalidRuntimeRootsDoNotStartTheHelper()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString helper = writeHelper(directory,
            QByteArray("from pathlib import Path\nPath(r'") + marker.toUtf8() + "').touch()\n");
        const QString target = directory.filePath(QStringLiteral("target"));
        QVERIFY(QDir().mkdir(target));
        QVERIFY(QFile::setPermissions(target, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner));
        const QString link = directory.filePath(QStringLiteral("link"));
        QVERIFY(::symlink(QFile::encodeName(target).constData(), QFile::encodeName(link).constData()) == 0);
        const QString wrongMode = directory.filePath(QStringLiteral("wrong-mode"));
        QVERIFY(QDir().mkdir(wrongMode));
        QVERIFY(QFile::setPermissions(wrongMode, QFileDevice::ReadOwner | QFileDevice::WriteOwner
            | QFileDevice::ExeOwner | QFileDevice::ReadGroup | QFileDevice::ExeGroup));
        const QByteArray original = qgetenv("XDG_RUNTIME_DIR");
        for (const QString &runtime : {QStringLiteral("relative"), link, wrongMode, QStringLiteral("/")}) {
            qputenv("XDG_RUNTIME_DIR", runtime.toUtf8());
            AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            controller.discover();
            QVERIFY(!controller.busy());
            QCOMPARE(controller.errorCode(), QStringLiteral("helper_unavailable"));
            QVERIFY(!QFileInfo::exists(marker));
        }
        qputenv("XDG_RUNTIME_DIR", original);
    }

    void runtimeCleanupFailureRetainsOwnershipAndDefersCloseReady()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory,
            QByteArray("import base64,pathlib,sys\nassert sys.argv[1] == 'detect' and sys.argv[2] == '--runtime-root' and sys.argv[4] == '--runtime-root-id' and len(sys.argv) == 6\nroot=pathlib.Path(sys.argv[3])\n"
                       "(root/'resistant').mkdir()\nprint(base64.b64decode('")
            + providerDocument("detect").toBase64() + "').decode(),end='')\n");
        bool allowRemoval = false;
        QString retained;
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper, {}, nullptr,
            [&](const QString &path) {
                retained = path;
                return allowRemoval && QDir(path).removeRecursively();
            });
        QSignalSpy closeReady(&controller, &AiProviderController::closeReady);
        controller.discover();
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        QVERIFY(controller.busy());
        QVERIFY(QFileInfo::exists(retained + QStringLiteral("/resistant")));
        QVERIFY(!controller.requestClose());
        QCOMPARE(closeReady.size(), 0);
        controller.discover();
        allowRemoval = true;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 1000);
        QVERIFY(!QFileInfo::exists(retained));
        QCOMPARE(closeReady.size(), 1);
        QCOMPARE(controller.status(), QStringLiteral("disabled"));
    }

    void substitutedRuntimeIsNeverRemovedAndCloseWaitsForOriginalIdentity()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString observed = directory.filePath(QStringLiteral("substituted-runtime"));
        const QString helper = writeHelper(directory,
            QByteArray("import base64,pathlib,sys\nroot=pathlib.Path(sys.argv[3])\noriginal=pathlib.Path(str(root)+'.original')\n"
                       "root.rename(original)\nroot.mkdir(mode=0o700)\npathlib.Path(r'")
            + observed.toUtf8() + "').write_text(str(root))\nprint(base64.b64decode('"
            + providerDocument("detect").toBase64() + "').decode(),end='')\n");
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QSignalSpy closeReady(&controller, &AiProviderController::closeReady);
        controller.discover();
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        QVERIFY(controller.busy());
        QFile observedFile(observed);
        QVERIFY(observedFile.open(QIODevice::ReadOnly));
        const QString runtime = QString::fromUtf8(observedFile.readAll());
        const QString original = runtime + QStringLiteral(".original");
        const QString foreign = runtime + QStringLiteral(".foreign");
        QVERIFY(QFileInfo::exists(runtime));
        QVERIFY(QFileInfo::exists(original));
        QVERIFY(!controller.requestClose());
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(QDir().rename(runtime, foreign));
        QVERIFY(QDir().rename(original, runtime));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 1000);
        QVERIFY(!QFileInfo::exists(runtime));
        QVERIFY(QFileInfo::exists(foreign));
        QCOMPARE(closeReady.size(), 1);
        QVERIFY(QDir(foreign).removeRecursively());
    }

    void invalidOrOversizedOutputIsRedactedAndNeverPublished()
    {
        for (const QByteArray &output : {QByteArray("{\"schemaVersion\":2}\n"), QByteArray(33 * 1024, 's')}) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + output.toBase64() + "'))\n");
            AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            controller.discover();
            QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
            QCOMPARE(controller.status(), QStringLiteral("error"));
            QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
            QVERIFY(controller.providers().isEmpty());
            QVERIFY(!controller.error().contains(QString(16, QLatin1Char('s'))));
        }
    }

    void cancellationDiscardsLateOutputAndKeepsTheLastStableReport()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString mode = directory.filePath(QStringLiteral("mode"));
        const QString identityPath = directory.filePath(QStringLiteral("cancel-descendant.identity"));
        const QString readyPath = directory.filePath(QStringLiteral("cancel-descendant.ready"));
        const QByteArray token = QByteArray("orla-ai-cancel-") + QByteArray::number(QCoreApplication::applicationPid());
        const QByteArray childCode = "import pathlib,signal,sys,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(sys.argv[2]).touch();time.sleep(60)";
        QFile modeFile(mode);
        QVERIFY(modeFile.open(QIODevice::WriteOnly));
        modeFile.write("fast");
        modeFile.close();
        const QString helper = writeHelper(directory,
            QByteArray("import base64,pathlib,signal,subprocess,sys,time\n")
            + "doc=base64.b64decode('" + providerDocument("detect").toBase64() + "')\n"
            + "mode=pathlib.Path(r'" + mode.toUtf8() + "').read_text()\n"
            + "if mode == 'slow':\n"
            + " child=subprocess.Popen(['/usr/bin/python3','-c',r'" + childCode + "',r'" + token
            + "',r'" + readyPath.toUtf8() + "'])\n"
            + " stat=pathlib.Path(f'/proc/{child.pid}/stat').read_text();tail=stat[stat.rfind(') ')+2:].split()\n"
            + " pathlib.Path(r'" + identityPath.toUtf8() + "').write_text(f'{child.pid} {tail[19]}')\n"
            + " def stop(*_):\n  child.wait(timeout=2)\n  raise SystemExit(0)\n"
            + " signal.signal(signal.SIGTERM, stop)\n time.sleep(60)\n"
            + "sys.stdout.buffer.write(doc)\n");
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
                                        {}, nullptr, {}, 100);
        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.providers().size(), 5);
        QVERIFY(modeFile.open(QIODevice::WriteOnly | QIODevice::Truncate));
        modeFile.write("slow");
        modeFile.close();
        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(controller.busy(), 1000);
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(identityPath) && QFile::exists(readyPath), 3000);
        const QString request = controller.requestId();
        controller.cancel(request);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 7000);
        QCOMPARE(controller.status(), QStringLiteral("report_available"));
        QCOMPARE(controller.providers().size(), 5);
        QFile identity(identityPath);
        QVERIFY(identity.open(QIODevice::ReadOnly));
        const QList<QByteArray> parts = identity.readAll().trimmed().split(' ');
        QCOMPARE(parts.size(), 2);
        const qint64 pid = parts[0].toLongLong();
        if (processExists(pid)) {
            QVERIFY2(killValidatedFixture(pid, parts[1], token), "refused to signal an unvalidated fixture process");
            QFAIL("cancel returned while its validated TERM-ignoring descendant survived");
        }
    }

    void probeRequiresTheCurrentRequestIdAndPublishesOnlyCodex()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory,
            QByteArray("import base64,sys\nassert sys.argv[1] == 'probe-codex-anonymous' and sys.argv[2] == '--runtime-root' and sys.argv[4] == '--runtime-root-id' and len(sys.argv) == 6\n")
            + "sys.stdout.buffer.write(base64.b64decode('" + providerDocument("probe").toBase64() + "'))\n");
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        controller.probeCodex(QStringLiteral("consent-1"));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("report_available"));
        QCOMPARE(controller.providers().size(), 1);
        QCOMPARE(controller.providers().first().toMap().value("messageCode").toString(),
                 QStringLiteral("anonymous_protocol_supported"));
        controller.probeCodex(QString());
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_request"));
    }

    void normalLeaderExitCleansTermIgnoringOwnedDescendantBeforePublishing()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("descendant.identity"));
        const QString readyPath = directory.filePath(QStringLiteral("descendant.ready"));
        const QByteArray token = QByteArray("orla-ai-owned-") + QByteArray::number(QCoreApplication::applicationPid());
        const QByteArray document = providerDocument("detect");
        const QByteArray childCode = "import pathlib,signal,sys,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);pathlib.Path(sys.argv[2]).touch();time.sleep(60)";
        const QString helper = writeHelper(directory,
            QByteArray("import base64,pathlib,subprocess,sys,time\n")
            + "child=subprocess.Popen(['/usr/bin/python3','-c',r'" + childCode + "',r'" + token
            + "',r'" + readyPath.toUtf8()
            + "'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
            + "stat=pathlib.Path(f'/proc/{child.pid}/stat').read_text();tail=stat[stat.rfind(') ')+2:].split()\n"
            + "pathlib.Path(r'" + marker.toUtf8() + "').write_text(f'{child.pid} {tail[19]}')\n"
            + "ready=pathlib.Path(r'" + readyPath.toUtf8() + "');deadline=time.monotonic()+2\n"
            + "while not ready.exists() and time.monotonic() < deadline: time.sleep(.01)\n"
            + "assert ready.exists()\n"
            + "sys.stdout.buffer.write(base64.b64decode('" + document.toBase64() + "'))\n");
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
                                        {}, nullptr, {}, 100);
        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(marker) && QFile::exists(readyPath), 3000);
        QVERIFY(controller.busy());
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("report_available"), 7000);
        QVERIFY(!controller.busy());
        QFile identity(marker);
        QVERIFY(identity.open(QIODevice::ReadOnly));
        const QList<QByteArray> parts = identity.readAll().trimmed().split(' ');
        QCOMPARE(parts.size(), 2);
        const qint64 pid = parts[0].toLongLong();
        const QByteArray startId = parts[1];
        if (processExists(pid)) {
            QVERIFY2(killValidatedFixture(pid, startId, token), "refused to signal an unvalidated fixture process");
            QFAIL("controller published while its validated owned descendant survived");
        }
    }

    void unconfirmedCleanupRetainsCustodyAndDefersCloseReady()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("ai-started"));
        const QString helper = writeHelper(directory,
            QByteArray("import pathlib,time\npathlib.Path(r'") + marker.toUtf8()
            + "').touch()\ntime.sleep(60)\n");
        bool reportGroupExists = true;
        qint64 observedGroup = 0;
        int observerCalls = 0;
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            [&](qint64 group) {
                observedGroup = group;
                ++observerCalls;
                return reportGroupExists;
            }, nullptr, {}, 100);
        QSignalSpy closeReady(&controller, &AiProviderController::closeReady);

        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(controller.busy() && QFile::exists(marker), 3000);
        QVERIFY(!controller.requestClose());
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 7000);
        QVERIFY(controller.busy());
        QVERIFY(observedGroup > 0);
        QCOMPARE(closeReady.size(), 0);

        const int callsBeforeRelease = observerCalls;
        reportGroupExists = false;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 1000);
        QVERIFY(observerCalls > callsBeforeRelease);
        QCOMPARE(closeReady.size(), 1);
    }

    void impossibleCapabilityClaimsAreRejectedWithoutReplacingTheStableReport()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString mode = directory.filePath(QStringLiteral("mode"));
        QFile modeFile(mode);
        QVERIFY(modeFile.open(QIODevice::WriteOnly));
        modeFile.write("valid");
        modeFile.close();
        const QByteArray impossibleCaps = R"({"installation":"supported","anonymous_protocol":"supported","authentication":"supported","inference":"supported","cancellation":"supported","usage_reporting":"supported"})";
        QByteArray impossible = providerDocument("detect");
        const QByteArray validCaps = R"({"installation":"supported","anonymous_protocol":"unknown","authentication":"unknown","inference":"unknown","cancellation":"unknown","usage_reporting":"unknown"})";
        impossible.replace(validCaps, impossibleCaps);
        const QString helper = writeHelper(directory,
            QByteArray("import base64,pathlib,sys\n")
            + "valid=base64.b64decode('" + providerDocument("detect").toBase64() + "')\n"
            + "invalid=base64.b64decode('" + impossible.toBase64() + "')\n"
            + "sys.stdout.buffer.write(valid if pathlib.Path(r'" + mode.toUtf8()
            + "').read_text() == 'valid' else invalid)\n");
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        controller.discover();
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("report_available"), 3000);
        const QVariantList stable = controller.providers();
        QVERIFY(modeFile.open(QIODevice::WriteOnly | QIODevice::Truncate));
        modeFile.write("invalid");
        modeFile.close();
        controller.discover();
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("error"), 3000);
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
        QCOMPARE(controller.providers(), stable);
    }

    void acceptsOnlyLegitimateA01DetectionAndProbeStates()
    {
        const QList<QByteArray> absent = {
            provider("codex", "absent", "absent", "cli_not_found"),
            provider("claude", "absent", "absent", "cli_not_found"),
            provider("opencode", "absent", "absent", "cli_not_found"),
            provider("ollama", "absent", "absent", "cli_not_found"),
            provider("lmstudio", "absent", "absent", "cli_not_found")};
        QList<QByteArray> ollamaPresent = absent;
        ollamaPresent[3] = provider("ollama", "supported", "unknown", "cli_present_version_not_queried");
        const QList<QByteArray> cancelled = {
            provider("codex", "unknown", "unknown", "cancelled"),
            provider("claude", "unknown", "unknown", "cancelled"),
            provider("opencode", "unknown", "unknown", "cancelled"),
            provider("ollama", "unknown", "unknown", "cancelled"),
            provider("lmstudio", "unknown", "unknown", "cancelled")};
        QList<QByteArray> detectDocuments = {detectDocument(absent), detectDocument(ollamaPresent),
            detectDocument(cancelled), providerDocument("detect")};
        for (const char *message : {"isolation_unavailable", "process_cleanup_failed", "stderr_limit",
                                    "stdout_limit", "timeout", "version_failed", "version_unrecognized"}) {
            QList<QByteArray> state = absent;
            state[0] = provider("codex", "unknown", "unknown", message);
            detectDocuments.append(detectDocument(state));
        }
        for (const QByteArray &document : detectDocuments) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + document.toBase64() + "'))\n");
            AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            controller.discover();
            QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("report_available"), 3000);
            QCOMPARE(controller.providers().size(), 5);
        }

        QList<QByteArray> probeDocuments = {
            probeDocument(provider("codex", "absent", "absent", "cli_not_found")),
            probeDocument(provider("codex", "supported", "unknown", "cancelled", "0.162.1")),
            probeDocument(provider("codex", "supported", "unknown", "isolation_unavailable", "0.162.1")),
            probeDocument(provider("codex", "supported", "unknown", "process_cleanup_failed", "0.162.1")),
            probeDocument(provider("codex", "supported", "unknown", "protocol_version_unknown", "0.163.0")),
            probeDocument(provider("codex", "supported", "supported", "anonymous_protocol_supported", "0.162.1"))};
        for (const char *message : {"cancelled", "isolation_unavailable", "process_cleanup_failed",
                                    "stderr_limit", "stdout_limit", "timeout", "version_failed",
                                    "version_unrecognized"})
            probeDocuments.append(probeDocument(provider("codex", "unknown", "unknown", message)));
        for (const char *message : {"protocol_invalid", "protocol_output_limit", "protocol_process_failed",
                                    "protocol_shutdown_failed", "protocol_timeout"})
            probeDocuments.append(probeDocument(provider("codex", "supported", "unknown", message, "0.162.1")));
        int request = 0;
        for (const QByteArray &document : probeDocuments) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + document.toBase64() + "'))\n");
            AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            controller.probeCodex(QStringLiteral("matrix-%1").arg(++request));
            QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("report_available"), 3000);
            QCOMPARE(controller.providers().size(), 1);
        }
    }

    void rejectsOperationMessageVersionAndCapabilityMismatches()
    {
        const QList<QByteArray> absent = {
            provider("codex", "absent", "absent", "cli_not_found"),
            provider("claude", "absent", "absent", "cli_not_found"),
            provider("opencode", "absent", "absent", "cli_not_found"),
            provider("ollama", "absent", "absent", "cli_not_found"),
            provider("lmstudio", "absent", "absent", "cli_not_found")};
        QList<QByteArray> detectProtocolClaim = absent;
        detectProtocolClaim[0] = provider("codex", "supported", "unknown", "protocol_timeout", "0.162.1");
        QList<QByteArray> impossibleOllama = absent;
        impossibleOllama[3] = provider("ollama", "unknown", "unknown", "isolation_unavailable");
        const QList<QByteArray> documents = {
            detectDocument(detectProtocolClaim), detectDocument(impossibleOllama),
            probeDocument(provider("codex", "supported", "supported", "anonymous_protocol_supported", "0.163.0")),
            QByteArray(R"({"schemaVersion":1,"provider":{"id":"codex","displayName":"Codex","enabled":false,"clientVersion":"0.162.1","capabilities":{"installation":"supported","anonymous_protocol":"unknown","authentication":"auth_needed","inference":"unknown","cancellation":"unknown","usage_reporting":"unknown"},"route":"owned_app_server","messageCode":"protocol_timeout"}})") + "\n"};
        for (int index = 0; index < documents.size(); ++index) {
            QTemporaryDir directory;
            QVERIFY(directory.isValid());
            const QString helper = writeHelper(directory,
                QByteArray("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('")
                + documents[index].toBase64() + "'))\n");
            AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
            if (index < 2) controller.discover();
            else controller.probeCodex(QStringLiteral("invalid-%1").arg(index));
            QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("error"), 3000);
            QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
            QVERIFY(controller.providers().isEmpty());
        }
    }

    void productDeadlineWinsBeforeTheIsolatedWrapperDeadline()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString helper = writeHelper(directory, QByteArray("import time\ntime.sleep(60)\n"));
        AiProviderController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QElapsedTimer elapsed;
        elapsed.start();
        controller.discover();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 30000);
        QVERIFY(elapsed.elapsed() >= 21000);
        QVERIFY(elapsed.elapsed() < 30000);
        QCOMPARE(controller.status(), QStringLiteral("error"));
        QCOMPARE(controller.errorCode(), QStringLiteral("operation_timeout"));
    }
};

QTEST_MAIN(AiProviderTests)
#include "AiProviderTests.moc"
