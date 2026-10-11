#include <QtTest>

#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>

#include "AiTextController.h"

#ifdef Q_OS_UNIX
#include <cerrno>
#include <csignal>
#include <unistd.h>
#endif

#if defined(Q_OS_UNIX) && defined(ORLA_TEST_WRAP_KILL)
#include <utility>
#include <vector>

namespace {
bool interceptKills = false;
std::vector<std::pair<pid_t, int>> interceptedKills;
struct KillInterception
{
    KillInterception() { interceptedKills.clear(); interceptKills = true; }
    ~KillInterception() { interceptKills = false; }
};
}

extern "C" int __real_kill(pid_t pid, int signalNumber);
extern "C" int __wrap_kill(pid_t pid, int signalNumber)
{
    if (!interceptKills) return __real_kill(pid, signalNumber);
    interceptedKills.emplace_back(pid, signalNumber);
    errno = ESRCH;
    return -1;
}
#endif

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

QByteArray eventLine(const QString &requestId, int sequence, const QString &type,
                     const QJsonObject &extra = {})
{
    QJsonObject object = extra;
    object.insert(QStringLiteral("schemaVersion"), 1);
    object.insert(QStringLiteral("requestId"), requestId);
    object.insert(QStringLiteral("sequence"), sequence);
    object.insert(QStringLiteral("type"), type);
    return QJsonDocument(object).toJson(QJsonDocument::Compact) + '\n';
}

QByteArray started(const QString &requestId, quint16 port, const QString &model)
{
    return eventLine(requestId, 0, QStringLiteral("started"), {
        {QStringLiteral("provider"), QStringLiteral("ollama_local")},
        {QStringLiteral("destination"), QStringLiteral("http://127.0.0.1:%1/api/chat").arg(port)},
        {QStringLiteral("model"), model},
    });
}

QByteArray completed(const QString &requestId, int sequence)
{
    return eventLine(requestId, sequence, QStringLiteral("completed"), {
        {QStringLiteral("finishReason"), QStringLiteral("stop")},
        {QStringLiteral("usage"), QJsonObject{
            {QStringLiteral("status"), QStringLiteral("reported")},
            {QStringLiteral("inputTokens"), 2}, {QStringLiteral("outputTokens"), 3},
            {QStringLiteral("totalTokens"), 5}}},
        {QStringLiteral("cost"), QJsonObject{
            {QStringLiteral("status"), QStringLiteral("unknown")},
            {QStringLiteral("currency"), QJsonValue(QJsonValue::Null)},
            {QStringLiteral("amount"), QJsonValue(QJsonValue::Null)}}},
    });
}

void writeChunk(QTcpSocket *socket, const QByteArray &bytes)
{
    socket->write(QByteArray::number(bytes.size(), 16) + "\r\n" + bytes + "\r\n");
    QVERIFY(socket->flush());
}

QByteArray readHttpRequest(QTcpSocket *socket)
{
    QByteArray request;
    int bodyLength = -1;
    while (true) {
        if (socket->bytesAvailable() || socket->waitForReadyRead(50)) request += socket->readAll();
        const qsizetype split = request.indexOf("\r\n\r\n");
        if (split >= 0 && bodyLength < 0) {
            const QRegularExpression expression(QStringLiteral("Content-Length: ([0-9]+)\\r\\n"));
            const auto match = expression.match(QString::fromLatin1(request.left(split + 2)));
            if (match.hasMatch()) bodyLength = match.captured(1).toInt();
        }
        if (split >= 0 && bodyLength >= 0 && request.size() >= split + 4 + bodyLength) return request;
        QCoreApplication::processEvents(QEventLoop::AllEvents, 25);
    }
}
}

class AiTextControllerTests final : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void constructionAndInvalidRequestsNeverStartAProcess()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("unexpected"));
        const QString helper = writeHelper(directory,
            QByteArray("import pathlib\npathlib.Path(r'") + marker.toUtf8() + "').touch()\n");
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QCOMPARE(controller.status(), QStringLiteral("disabled"));
        QVERIFY(!controller.busy());
        QVERIFY(!QFile::exists(marker));

        controller.generate(QStringLiteral("request.1"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("private text"), QStringLiteral("gemma3:4b"),
                            QStringLiteral("127.0.0.1"), 11434, false);
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_request"));
        QVERIFY(!controller.busy());
        QVERIFY(!QFile::exists(marker));

        controller.generate(QStringLiteral("request.1"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("private text"), QStringLiteral("gemma3:4b"),
                            QStringLiteral("localhost"), 11434, true);
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_request"));
        QVERIFY(!QFile::exists(marker));
    }

    void exactPrivateProcessContractStreamsBeforeExitAndHoldsTerminal()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QByteArray script = R"PY(import json,os,stat,sys,time
assert sys.argv[1:] == ['run-ollama']
assert set(os.environ) <= {'LC_CTYPE'}
assert stat.S_IMODE(os.stat('.').st_mode) == 0o700
raw=sys.stdin.buffer.read()
assert raw.endswith(b'\n') and raw.count(b'\n') == 1
r=json.loads(raw)
assert set(r) == {'schemaVersion','requestId','provider','task','targetLanguage','text','model','endpoint','credentialBytes'}
assert r['text'] == 'private stdin canary' and r['credentialBytes'] == 0
base={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 d=dict(base,sequence=sequence,type=kind,**extra)
 sys.stdout.write(json.dumps(d,separators=(',',':'))+'\n');sys.stdout.flush()
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='first ')
time.sleep(.25)
emit(2,'delta',text='second')
emit(3,'completed',finishReason='stop',usage={'status':'unknown','inputTokens':None,'outputTokens':None,'totalTokens':None},cost={'status':'unknown','currency':None,'amount':None})
time.sleep(.25)
)PY";
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                    writeHelper(directory, script));
        controller.generate(QStringLiteral("request.2"), QStringLiteral("rewrite"), QVariant(),
                            QStringLiteral("private stdin canary"), QStringLiteral("gemma3:4b"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.output().isEmpty() || !controller.errorCode().isEmpty(), 3000);
        QVERIFY2(controller.errorCode().isEmpty(), qPrintable(controller.errorCode()));
        QCOMPARE(controller.output(), QStringLiteral("first "));
        QCOMPARE(controller.status(), QStringLiteral("running"));
        QTRY_COMPARE_WITH_TIMEOUT(controller.output(), QStringLiteral("first second"), 3000);
        QCOMPARE(controller.status(), QStringLiteral("running"));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QCOMPARE(controller.usage().value(QStringLiteral("status")).toString(), QStringLiteral("unknown"));
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
    }

    void malformedSequencePreservesPartialOutputAndFailsClosed()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QByteArray start = started(QStringLiteral("request.3"), 11434, QStringLiteral("model"));
        const QByteArray delta = eventLine(QStringLiteral("request.3"), 1, QStringLiteral("delta"),
                                           {{QStringLiteral("text"), QStringLiteral("partial")}});
        const QByteArray wrong = eventLine(QStringLiteral("request.3"), 7, QStringLiteral("cancelled"));
        const QString helper = writeHelper(directory,
            QByteArray("import base64,sys,time\nsys.stdin.buffer.read()\nfor x in [b'")
            + start.toBase64() + "',b'" + delta.toBase64() + "',b'" + wrong.toBase64()
            + "']:\n sys.stdout.buffer.write(base64.b64decode(x));sys.stdout.flush();time.sleep(.02)\n");
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper, {}, nullptr, {}, 100);
        controller.generate(QStringLiteral("request.3"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.output(), QStringLiteral("partial"));
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
    }

    void usageCountsAcceptExactJsonMaximumAndRejectLargerIntegers()
    {
        const auto run = [](quint64 input, const QString &requestId) {
            QTemporaryDir directory;
            if (!directory.isValid()) return QStringLiteral("test_setup_failed");
            const QByteArray number = QByteArray::number(input);
            const QByteArray script = QByteArray(R"PY(import json,sys
r=json.loads(sys.stdin.buffer.read())
b={'schemaVersion':1,'requestId':r['requestId']}
events=[dict(b,sequence=0,type='started',provider='ollama_local',destination=r['endpoint'],model=r['model']),dict(b,sequence=1,type='completed',finishReason='stop',usage={'status':'reported','inputTokens':)PY")
                + number + QByteArray(",'outputTokens':0,'totalTokens':") + number
                + QByteArray(R"PY(},cost={'status':'unknown','currency':None,'amount':None})]
for event in events: print(json.dumps(event,separators=(',',':')),flush=True)
)PY");
            AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                        writeHelper(directory, script));
            controller.generate(requestId, QStringLiteral("summarize"), QVariant(),
                                QStringLiteral("input"), QStringLiteral("model"),
                                QStringLiteral("127.0.0.1"), 11434, true);
            QElapsedTimer timer;
            timer.start();
            while (controller.busy() && timer.elapsed() < 3000)
                QCoreApplication::processEvents(QEventLoop::AllEvents, 20);
            return controller.status() + QLatin1Char(':') + controller.errorCode();
        };

        QCOMPARE(run(9007199254740991ULL, QStringLiteral("request.count.max")),
                 QStringLiteral("completed:"));
        QCOMPARE(run(9007199254740992ULL, QStringLiteral("request.count.plus-one")),
                 QStringLiteral("failed:invalid_helper_response"));
        QCOMPARE(run(9223372036854775808ULL, QStringLiteral("request.count.i64-plus-one")),
                 QStringLiteral("failed:invalid_helper_response"));
    }

    void destroyingRunningHelperReapsItsCapturedGroupAndRemovesOwnedRuntime()
    {
#ifndef Q_OS_UNIX
        QSKIP("Emergency process-group teardown is Unix-specific");
#else
        QTemporaryDir runtimeRoot;
        QTemporaryDir helperDirectory;
        QVERIFY(runtimeRoot.isValid());
        QVERIFY(helperDirectory.isValid());
        QVERIFY(QFile::setPermissions(runtimeRoot.path(), QFileDevice::ReadOwner
                                      | QFileDevice::WriteOwner | QFileDevice::ExeOwner));
        const QByteArray oldRuntime = qgetenv("XDG_RUNTIME_DIR");
        QVERIFY(qputenv("XDG_RUNTIME_DIR", runtimeRoot.path().toUtf8()));
        const QString identity = helperDirectory.filePath(QStringLiteral("identity"));
        const QByteArray script = QByteArray("import os,pathlib,signal,sys,time\n")
            + "sys.stdin.buffer.read()\n"
            + "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            + "pathlib.Path(r'" + identity.toUtf8() + "').write_text(str(os.getpid()))\n"
            + "pathlib.Path('alive').write_text('started')\n"
            + "time.sleep(60)\n";
        auto *controller = new AiTextController(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                                writeHelper(helperDirectory, script));
        controller->generate(QStringLiteral("request.destructor"), QStringLiteral("summarize"),
                             QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                             QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(QFileInfo::exists(identity), 3000);
        QTRY_VERIFY_WITH_TIMEOUT(!QDir(runtimeRoot.path()).entryList(
            QDir::Dirs | QDir::NoDotAndDotDot).isEmpty(), 3000);
        QFile identityFile(identity);
        QVERIFY(identityFile.open(QIODevice::ReadOnly));
        const qint64 pid = identityFile.readAll().trimmed().toLongLong();
        QVERIFY(pid > 0);

        delete controller;

        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        QCOMPARE(QDir(runtimeRoot.path()).entryList(QDir::Dirs | QDir::NoDotAndDotDot),
                 QStringList());
        if (oldRuntime.isNull()) qunsetenv("XDG_RUNTIME_DIR");
        else QVERIFY(qputenv("XDG_RUNTIME_DIR", oldRuntime));
#endif
    }

    void requestCloseWaitsForForcedKillAndReportsUnconfirmedCancellation()
    {
#ifndef Q_OS_UNIX
        QSKIP("Process-group cancellation is Unix-specific");
#else
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QByteArray script = R"PY(import json,signal,sys,time
r=json.loads(sys.stdin.buffer.read())
base={'schemaVersion':1,'requestId':r['requestId']}
for e in [dict(base,sequence=0,type='started',provider='ollama_local',destination=r['endpoint'],model=r['model']),dict(base,sequence=1,type='delta',text='retained')]:
 sys.stdout.write(json.dumps(e,separators=(',',':'))+'\n');sys.stdout.flush()
signal.signal(signal.SIGTERM,signal.SIG_IGN)
time.sleep(60)
)PY";
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                    writeHelper(directory, script), {}, nullptr, {}, 100);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        controller.generate(QStringLiteral("request.kill"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(controller.output(), QStringLiteral("retained"), 3000);
        QVERIFY(!controller.requestClose());
        QCOMPARE(closeReady.size(), 0);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(closeReady.size(), 1);
        QCOMPARE(controller.status(), QStringLiteral("cancelled_unconfirmed"));
        QCOMPARE(controller.output(), QStringLiteral("retained"));
#endif
    }

    void absentGroupIsNotSignalledWhileRuntimeCleanupRetries_data()
    {
        QTest::addColumn<bool>("destroyBeforeRetry");
        QTest::newRow("poll-retry-after-close") << false;
        QTest::newRow("destructor-retry-after-close") << true;
    }

    void absentGroupIsNotSignalledWhileRuntimeCleanupRetries()
    {
#ifndef Q_OS_UNIX
        QSKIP("Process-group ownership is Unix-specific");
#endif
        QFETCH(bool, destroyBeforeRetry);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString requestId = QStringLiteral("request.absent-group");
        const QByteArray events = started(requestId, 11434, QStringLiteral("model"))
            + completed(requestId, 1);
        const QString helper = writeHelper(directory,
            QByteArray("import base64,sys\nsys.stdin.buffer.read()\n")
            + "sys.stdout.buffer.write(base64.b64decode(b'" + events.toBase64()
            + "'));sys.stdout.flush()\n");
        int absenceChecks = 0;
        int removalAttempts = 0;
        bool allowRemoval = false;
        QString runtimePath;
#if defined(Q_OS_UNIX) && defined(ORLA_TEST_WRAP_KILL)
        KillInterception interception;
#endif
        auto controller = std::make_unique<AiTextController>(
            QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            [&absenceChecks](qint64) { ++absenceChecks; return false; }, nullptr,
            [&](const QString &path) {
                ++removalAttempts;
                runtimePath = path;
                return allowRemoval && QDir(path).removeRecursively();
            }, 50);
        QSignalSpy closeReady(controller.get(), &AiTextController::closeReady);
        controller->generate(requestId, QStringLiteral("summarize"), QVariant(),
                             QStringLiteral("input"), QStringLiteral("model"),
                             QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(controller->errorCode(),
                                  QStringLiteral("process_cleanup_failed"), 3000);
        QVERIFY(controller->busy());
        QVERIFY(absenceChecks > 0);
        QVERIFY(removalAttempts > 0);
        QVERIFY(QFileInfo::exists(runtimePath));
        const int confirmedAbsenceChecks = absenceChecks;
        const int failedRemovalAttempts = removalAttempts;

        QVERIFY(!controller->requestClose());
        QCOMPARE(closeReady.size(), 0);
        QTest::qWait(150); // Includes the cancellation grace and multiple cleanup polls.
        QVERIFY(controller->busy());
        QVERIFY(removalAttempts > failedRemovalAttempts);

        allowRemoval = true;
        if (destroyBeforeRetry) {
            controller.reset();
        } else {
            QTRY_VERIFY_WITH_TIMEOUT(!controller->busy(), 3000);
            QCOMPARE(closeReady.size(), 1);
            QVERIFY(controller->requestClose());
        }
        QVERIFY(!QFileInfo::exists(runtimePath));
#if defined(Q_OS_UNIX) && defined(ORLA_TEST_WRAP_KILL)
        QCOMPARE(interceptedKills.size(), std::size_t(0));
#endif
        // Once original absence is confirmed, the numeric group is never observed again.
        QCOMPARE(absenceChecks, confirmedAbsenceChecks);
    }

    void realHelperStreamsThroughActualFragmentedLoopbackAndWaitsForHttpEof()
    {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        const quint16 port = server.serverPort();
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                    QStringLiteral(ORLA_TEST_AI_TEXT_HELPER));
        controller.generate(QStringLiteral("request.real"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("socket prompt canary"), QStringLiteral("gemma3:4b"),
                            QStringLiteral("127.0.0.1"), port, true);
        QTRY_VERIFY_WITH_TIMEOUT(server.hasPendingConnections(), 3000);
        std::unique_ptr<QTcpSocket> socket(server.nextPendingConnection());
        QVERIFY(socket);
        const QByteArray request = readHttpRequest(socket.get());
        QVERIFY(request.startsWith("POST /api/chat HTTP/1.1\r\n"));
        QVERIFY(request.contains("Host: 127.0.0.1:" + QByteArray::number(port) + "\r\n"));
        QVERIFY(request.contains("Accept: application/x-ndjson\r\n"));
        const qsizetype split = request.indexOf("\r\n\r\n");
        const QJsonObject body = QJsonDocument::fromJson(request.mid(split + 4)).object();
        QCOMPARE(body.value(QStringLiteral("model")).toString(), QStringLiteral("gemma3:4b"));
        QVERIFY(body.value(QStringLiteral("stream")).toBool());
        QCOMPARE(body.value(QStringLiteral("messages")).toArray().last().toObject()
                     .value(QStringLiteral("content")).toString(), QStringLiteral("socket prompt canary"));

        socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n");
        writeChunk(socket.get(), QByteArray("{\"message\":{\"role\":\"assistant\",\"content\":\"frag"));
        writeChunk(socket.get(), QByteArray("mented \"},\"done\":false}\n"));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.output().isEmpty() || !controller.errorCode().isEmpty(), 3000);
        QVERIFY2(controller.errorCode().isEmpty(), qPrintable(controller.errorCode()));
        QCOMPARE(controller.output(), QStringLiteral("fragmented "));
        QCOMPARE(controller.status(), QStringLiteral("running"));
        writeChunk(socket.get(), QByteArray("{\"message\":{\"role\":\"assistant\",\"content\":\"done\"},\"done\":true,\"done_reason\":\"stop\",\"prompt_eval_count\":2,\"eval_count\":3}\n"));
        QTest::qWait(150);
        QCOMPARE(controller.output(), QStringLiteral("fragmented "));
        QCOMPARE(controller.status(), QStringLiteral("running"));
        socket->write("0\r\n\r\n");
        QVERIFY(socket->flush());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 5000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QCOMPARE(controller.output(), QStringLiteral("fragmented done"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 5);
    }

    void realHelperCancellationDisconnectsStalledSocketAndRetainsPartialOutput()
    {
        QTcpServer server;
        QVERIFY(server.listen(QHostAddress::LocalHost, 0));
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                    QStringLiteral(ORLA_TEST_AI_TEXT_HELPER));
        controller.generate(QStringLiteral("request.cancel"), QStringLiteral("rewrite"), QVariant(),
                            QStringLiteral("cancel prompt"), QStringLiteral("gemma3:4b"),
                            QStringLiteral("127.0.0.1"), server.serverPort(), true);
        QTRY_VERIFY_WITH_TIMEOUT(server.hasPendingConnections(), 3000);
        std::unique_ptr<QTcpSocket> socket(server.nextPendingConnection());
        QVERIFY(socket);
        readHttpRequest(socket.get());
        socket->write("HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n");
        writeChunk(socket.get(), QByteArray("{\"message\":{\"role\":\"assistant\",\"content\":\"kept\"},\"done\":false}\n"));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.output().isEmpty() || !controller.errorCode().isEmpty(), 3000);
        QVERIFY2(controller.errorCode().isEmpty(), qPrintable(controller.errorCode()));
        QCOMPARE(controller.output(), QStringLiteral("kept"));
        controller.cancel(QStringLiteral("request.cancel"));
        QTRY_VERIFY_WITH_TIMEOUT(socket->state() == QAbstractSocket::UnconnectedState, 2500);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 5000);
        QCOMPARE(controller.output(), QStringLiteral("kept"));
        QCOMPARE(controller.status(), QStringLiteral("cancelled_confirmed"));
    }
};

QTEST_MAIN(AiTextControllerTests)
#include "AiTextControllerTests.moc"
