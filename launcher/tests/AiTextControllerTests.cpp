#include <QtTest>

#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QScopeGuard>
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

QByteArray reportedResultHelper(const QString &marker, bool holdAfterCompleted = false)
{
    return QByteArray(R"PY(import json,os,pathlib,sys,time
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as record:
 record.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text=r['text'])
usage={'status':'reported','inputTokens':2,'outputTokens':3,'totalTokens':5}
if r['requestId'].endswith('.retry'):
 usage={'status':'reported','inputTokens':4,'outputTokens':5,'totalTokens':9}
emit(2,'completed',finishReason='stop',usage=usage,cost={'status':'unknown','currency':None,'amount':None})
)PY") + (holdAfterCompleted ? QByteArray("time.sleep(60)\n") : QByteArray());
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
    void acceptedFailureMessagesAreTruthfulAfterCleanup_data()
    {
        QTest::addColumn<QString>("boundary");
        QTest::addColumn<QString>("code");
        QTest::addColumn<QString>("message");
        QTest::addColumn<bool>("lateCancel");
        QTest::newRow("invalid_request") << QStringLiteral("clean-failed")
            << QStringLiteral("invalid_request") << QStringLiteral("O pedido de texto não é válido.") << false;
        QTest::newRow("helper_unavailable") << QStringLiteral("clean-failed")
            << QStringLiteral("helper_unavailable") << QStringLiteral("A geração local não está disponível nesta instalação.") << false;
        QTest::newRow("credential_cancelled") << QStringLiteral("clean-failed")
            << QStringLiteral("credential_cancelled") << QStringLiteral("A autorização para a geração local foi cancelada. Autorize novamente para tentar.") << false;
        QTest::newRow("credential_required") << QStringLiteral("clean-failed")
            << QStringLiteral("credential_required") << QStringLiteral("A geração local requer uma credencial. Configure a autorização para tentar novamente.") << false;
        QTest::newRow("endpoint_rejected") << QStringLiteral("clean-failed")
            << QStringLiteral("endpoint_rejected") << QStringLiteral("O endereço da geração local foi recusado. Verifique a configuração do provedor.") << false;
        QTest::newRow("connection_failed") << QStringLiteral("clean-failed")
            << QStringLiteral("connection_failed") << QStringLiteral("Não foi possível conectar ao provedor local. Verifique se ele está em execução e tente novamente.") << false;
        QTest::newRow("tls_failed") << QStringLiteral("clean-failed")
            << QStringLiteral("tls_failed") << QStringLiteral("A conexão segura com o provedor local falhou. Verifique a configuração de segurança.") << false;
        QTest::newRow("authentication_failed") << QStringLiteral("clean-failed")
            << QStringLiteral("authentication_failed") << QStringLiteral("A autenticação no provedor local falhou. Verifique a credencial configurada.") << false;
        QTest::newRow("permission_denied") << QStringLiteral("clean-failed")
            << QStringLiteral("permission_denied") << QStringLiteral("O provedor local recusou a permissão para gerar texto. Verifique as permissões configuradas.") << false;
        QTest::newRow("model_unavailable") << QStringLiteral("clean-failed")
            << QStringLiteral("model_unavailable") << QStringLiteral("O modelo selecionado não está disponível no provedor local. Verifique se ele está instalado ou escolha outro modelo.") << false;
        QTest::newRow("rate_limited") << QStringLiteral("clean-failed")
            << QStringLiteral("rate_limited") << QStringLiteral("O provedor local atingiu o limite de solicitações. Aguarde e tente novamente.") << false;
        QTest::newRow("provider_unavailable") << QStringLiteral("clean-failed")
            << QStringLiteral("provider_unavailable") << QStringLiteral("O provedor local está indisponível. Verifique se ele está em execução e tente novamente.") << false;
        QTest::newRow("provider_failed") << QStringLiteral("clean-failed")
            << QStringLiteral("provider_failed") << QStringLiteral("O provedor local falhou ao gerar texto. Tente novamente.") << false;
        QTest::newRow("unsupported_provider_event") << QStringLiteral("clean-failed")
            << QStringLiteral("unsupported_provider_event") << QStringLiteral("O provedor local enviou um evento não suportado. Verifique a compatibilidade do provedor.") << false;
        QTest::newRow("protocol_invalid") << QStringLiteral("clean-failed")
            << QStringLiteral("protocol_invalid") << QStringLiteral("A resposta da geração local não pôde ser validada.") << false;
        QTest::newRow("response_limit") << QStringLiteral("clean-failed")
            << QStringLiteral("response_limit") << QStringLiteral("A resposta da geração local excedeu o limite permitido. Reduza o pedido e tente novamente.") << false;
        QTest::newRow("operation_timeout") << QStringLiteral("clean-failed")
            << QStringLiteral("operation_timeout") << QStringLiteral("A geração local excedeu o tempo permitido.") << false;
        QTest::newRow("process_cleanup_failed") << QStringLiteral("clean-failed")
            << QStringLiteral("process_cleanup_failed") << QStringLiteral("A limpeza do processo local não pôde ser confirmada.") << false;
        QTest::newRow("unsupported_transport") << QStringLiteral("clean-failed")
            << QStringLiteral("unsupported_transport") << QStringLiteral("O transporte da geração local não é suportado nesta instalação. Verifique a configuração do provedor.") << false;
        QTest::newRow("connection_failed-late-cancel") << QStringLiteral("clean-failed")
            << QStringLiteral("connection_failed") << QStringLiteral("Não foi possível conectar ao provedor local. Verifique se ele está em execução e tente novamente.") << true;
        QTest::newRow("model_unavailable-late-cancel") << QStringLiteral("clean-failed")
            << QStringLiteral("model_unavailable") << QStringLiteral("O modelo selecionado não está disponível no provedor local. Verifique se ele está instalado ou escolha outro modelo.") << true;
        QTest::newRow("rate_limited-late-cancel") << QStringLiteral("clean-failed")
            << QStringLiteral("rate_limited") << QStringLiteral("O provedor local atingiu o limite de solicitações. Aguarde e tente novamente.") << true;
        QTest::newRow("provider_unavailable-late-cancel") << QStringLiteral("clean-failed")
            << QStringLiteral("provider_unavailable") << QStringLiteral("O provedor local está indisponível. Verifique se ele está em execução e tente novamente.") << true;
        QTest::newRow("extra-event") << QStringLiteral("extra-event")
            << QStringLiteral("rate_limited") << QStringLiteral("A resposta da geração local não pôde ser validada.") << false;
        QTest::newRow("unterminated-bytes") << QStringLiteral("unterminated-bytes")
            << QStringLiteral("rate_limited") << QStringLiteral("A resposta da geração local não pôde ser validada.") << false;
        QTest::newRow("nonzero-exit") << QStringLiteral("nonzero-exit")
            << QStringLiteral("rate_limited") << QStringLiteral("A resposta da geração local não pôde ser validada.") << false;
    }

    void acceptedFailureMessagesAreTruthfulAfterCleanup()
    {
#ifndef Q_OS_UNIX
        QSKIP("Captured PID/group cleanup checks are Unix-specific");
#else
        QFETCH(QString, boundary);
        QFETCH(QString, code);
        QFETCH(QString, message);
        QFETCH(bool, lateCancel);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString gate = directory.filePath(QStringLiteral("allow-eof"));
        const QByteArray script = QByteArray(R"PY(import json,os,pathlib,sys,time
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as record:
 record.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
retry=r['requestId'].endswith('.retry')
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='fresh' if retry else 'retained')
if retry:
 emit(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':4,'outputTokens':5,'totalTokens':9},cost={'status':'unknown','currency':None,'amount':None})
 sys.exit(0)
emit(2,'failed',code=')PY") + code.toUtf8() + QByteArray(R"PY(',retryable=True)
while not pathlib.Path(r')PY") + gate.toUtf8() + QByteArray(R"PY(').exists(): time.sleep(.005)
boundary=')PY") + boundary.toUtf8() + QByteArray(R"PY('
if boundary=='extra-event': emit(3,'delta',text='rejected')
if boundary=='unterminated-bytes':
 sys.stdout.write('unterminated')
 sys.stdout.flush()
sys.exit(7 if boundary=='nonzero-exit' else 0)
)PY");
        bool allowCleanup = false;
        QStringList runtimePaths;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeHelper(directory, script), {}, nullptr, [&](const QString &path) {
                runtimePaths.append(path);
                return allowCleanup && QDir(path).removeRecursively();
            });
        const auto cleanupGuard = qScopeGuard([&] { allowCleanup = true; });
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        QStringList order;
        QVariantMap notifiedFinal;
        bool originalPhase = true;
        connect(&controller, &AiTextController::changed, this, [&] {
            if (!originalPhase) return;
            if (controller.busy() && controller.errorCode() == QStringLiteral("process_cleanup_failed")) {
                order.append(QStringLiteral("cleanup-failed"));
            } else if (!controller.busy()) {
                order.append(QStringLiteral("finished"));
                notifiedFinal = QVariantMap{{QStringLiteral("status"), controller.status()},
                    {QStringLiteral("errorCode"), controller.errorCode()},
                    {QStringLiteral("error"), controller.error()},
                    {QStringLiteral("output"), controller.output()},
                    {QStringLiteral("usage"), controller.usage()}};
            }
        });
        controller.generate(QStringLiteral("request.failed-validation"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("prompt-canary"), QStringLiteral("model-canary"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        // Read-only witness: the syntactic failed line was parsed while the real helper holds EOF.
        QTRY_VERIFY_WITH_TIMEOUT(controller.m_terminalEvent
            && controller.m_terminalType == QStringLiteral("failed")
            && controller.m_process.state() == QProcess::Running, 3000);
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QCOMPARE(controller.status(), QStringLiteral("running"));
        QVERIFY(controller.errorCode().isEmpty());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(closeReady.size(), 0);
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identity = record.readAll();
        record.close();
        QCOMPARE(identity.count('\n'), 1);
        const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
        QVERIFY(pid > 0);
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == 0);
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == 0);
        QFile release(gate);
        QVERIFY(release.open(QIODevice::WriteOnly));
        QCOMPARE(release.write("allow"), qint64(5));
        release.close();
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        QVERIFY(controller.busy());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(!runtimePaths.isEmpty());
        QVERIFY(QFileInfo::exists(runtimePaths.first()));
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        const bool protocolObserved = controller.m_protocolInvalid;
        const int actualExitCode = controller.m_pendingExitCode;
        if (lateCancel) controller.cancelAll();
        allowCleanup = true;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        qInfo() << "OWNED_STABLE_FAILURE_MESSAGE_CLEANUP" << code << boundary << lateCancel << pid
                << "protocol" << protocolObserved << "actualExit" << actualExitCode
                << "runtimeGone" << runtimePaths << "order" << order
                << "finalNotified" << notifiedFinal;
        // Final-cause oracles only run after real PID/group/runtime absence.
        if (boundary == QStringLiteral("extra-event") || boundary == QStringLiteral("unterminated-bytes"))
            QVERIFY(protocolObserved);
        if (boundary == QStringLiteral("nonzero-exit")) QCOMPARE(actualExitCode, 7);
        const QString expected = boundary == QStringLiteral("clean-failed")
            ? code : QStringLiteral("invalid_helper_response");
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), expected);
        QCOMPARE(order, lateCancel
            ? QStringList({QStringLiteral("cleanup-failed"), QStringLiteral("cleanup-failed"), QStringLiteral("finished")})
            : QStringList({QStringLiteral("cleanup-failed"), QStringLiteral("finished")}));
        QCOMPARE(notifiedFinal.value(QStringLiteral("status")).toString(), QStringLiteral("failed"));
        QCOMPARE(notifiedFinal.value(QStringLiteral("errorCode")).toString(), expected);
        QCOMPARE(notifiedFinal.value(QStringLiteral("error")).toString(), controller.error());
        QCOMPARE(controller.error(), message);
        QCOMPARE(notifiedFinal.value(QStringLiteral("error")).toString(), message);
        QCOMPARE(controller.m_pendingExitStatus, QProcess::NormalExit);
        QCOMPARE(actualExitCode, boundary == QStringLiteral("nonzero-exit") ? 7 : 0);
        QVERIFY(!controller.error().contains(QStringLiteral("model-canary")));
        QVERIFY(!controller.error().contains(QStringLiteral("127.0.0.1")));
        QVERIFY(!controller.error().contains(QStringLiteral("prompt-canary")));
        QCOMPARE(notifiedFinal.value(QStringLiteral("output")).toString(), QStringLiteral("retained"));
        QVERIFY(notifiedFinal.value(QStringLiteral("usage")).toMap().isEmpty());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        QCOMPARE(closeReady.size(), 0);
        originalPhase = false;
        controller.generate(QStringLiteral("request.failed-validation.retry"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("prompt-canary"), QStringLiteral("model-canary"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identities = record.readAll();
        QCOMPARE(identities.count('\n'), 2);
        for (const QByteArray &line : identities.split('\n')) {
            if (line.isEmpty()) continue;
            const qint64 captured = line.left(line.indexOf(' ')).toLongLong();
            QVERIFY(captured > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
        }
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
#endif
    }

    void failedTerminalIsValidatedBeforePublishingItsCause_data()
    {
        QTest::addColumn<QString>("boundary");
        QTest::newRow("failed-followed-by-extra-event") << QStringLiteral("extra-event");
        QTest::newRow("failed-followed-by-unterminated-bytes") << QStringLiteral("unterminated-bytes");
        QTest::newRow("failed-followed-by-real-exit7") << QStringLiteral("nonzero-exit");
        QTest::newRow("clean-failed-after-runtime-recovery") << QStringLiteral("clean-failed");
    }

    void failedTerminalIsValidatedBeforePublishingItsCause()
    {
#ifndef Q_OS_UNIX
        QSKIP("Captured PID/group cleanup checks are Unix-specific");
#else
        QFETCH(QString, boundary);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString gate = directory.filePath(QStringLiteral("allow-eof"));
        const QByteArray script = QByteArray(R"PY(import json,os,pathlib,sys,time
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as record:
 record.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
retry=r['requestId'].endswith('.retry')
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='fresh' if retry else 'retained')
if retry:
 emit(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':4,'outputTokens':5,'totalTokens':9},cost={'status':'unknown','currency':None,'amount':None})
 sys.exit(0)
emit(2,'failed',code='rate_limited',retryable=True)
while not pathlib.Path(r')PY") + gate.toUtf8() + QByteArray(R"PY(').exists(): time.sleep(.005)
boundary=')PY") + boundary.toUtf8() + QByteArray(R"PY('
if boundary=='extra-event': emit(3,'delta',text='rejected')
if boundary=='unterminated-bytes':
 sys.stdout.write('unterminated')
 sys.stdout.flush()
sys.exit(7 if boundary=='nonzero-exit' else 0)
)PY");
        bool allowCleanup = false;
        QStringList runtimePaths;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeHelper(directory, script), {}, nullptr, [&](const QString &path) {
                runtimePaths.append(path);
                return allowCleanup && QDir(path).removeRecursively();
            });
        const auto cleanupGuard = qScopeGuard([&] { allowCleanup = true; });
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        QStringList order;
        QVariantMap notifiedFinal;
        bool originalPhase = true;
        connect(&controller, &AiTextController::changed, this, [&] {
            if (!originalPhase) return;
            if (controller.busy() && controller.errorCode() == QStringLiteral("process_cleanup_failed")) {
                order.append(QStringLiteral("cleanup-failed"));
            } else if (!controller.busy()) {
                order.append(QStringLiteral("finished"));
                notifiedFinal = QVariantMap{{QStringLiteral("status"), controller.status()},
                    {QStringLiteral("errorCode"), controller.errorCode()},
                    {QStringLiteral("error"), controller.error()},
                    {QStringLiteral("output"), controller.output()},
                    {QStringLiteral("usage"), controller.usage()}};
            }
        });
        controller.generate(QStringLiteral("request.failed-validation"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        // Read-only witness: the syntactic failed line was parsed while the real helper holds EOF.
        QTRY_VERIFY_WITH_TIMEOUT(controller.m_terminalEvent
            && controller.m_terminalType == QStringLiteral("failed")
            && controller.m_process.state() == QProcess::Running, 3000);
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QCOMPARE(controller.status(), QStringLiteral("running"));
        QVERIFY(controller.errorCode().isEmpty());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(closeReady.size(), 0);
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identity = record.readAll();
        record.close();
        QCOMPARE(identity.count('\n'), 1);
        const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
        QVERIFY(pid > 0);
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == 0);
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == 0);
        QFile release(gate);
        QVERIFY(release.open(QIODevice::WriteOnly));
        QCOMPARE(release.write("allow"), qint64(5));
        release.close();
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        QVERIFY(controller.busy());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(!runtimePaths.isEmpty());
        QVERIFY(QFileInfo::exists(runtimePaths.first()));
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        const bool protocolObserved = controller.m_protocolInvalid;
        const int actualExitCode = controller.m_pendingExitCode;
        // An explicit cancel here would use a different precedence path and conceal the bug.
        allowCleanup = true;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        qInfo() << "OWNED_FAILED_TERMINAL_VALIDATION_CLEANUP" << boundary << pid
                << "protocol" << protocolObserved << "actualExit" << actualExitCode
                << "runtimeGone" << runtimePaths << "order" << order
                << "finalNotified" << notifiedFinal;
        // Final-cause oracles only run after real PID/group/runtime absence.
        if (boundary == QStringLiteral("extra-event") || boundary == QStringLiteral("unterminated-bytes"))
            QVERIFY(protocolObserved);
        if (boundary == QStringLiteral("nonzero-exit")) QCOMPARE(actualExitCode, 7);
        const QString expected = boundary == QStringLiteral("clean-failed")
            ? QStringLiteral("rate_limited") : QStringLiteral("invalid_helper_response");
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), expected);
        QCOMPARE(order, QStringList({QStringLiteral("cleanup-failed"), QStringLiteral("finished")}));
        QCOMPARE(notifiedFinal.value(QStringLiteral("status")).toString(), QStringLiteral("failed"));
        QCOMPARE(notifiedFinal.value(QStringLiteral("errorCode")).toString(), expected);
        QCOMPARE(notifiedFinal.value(QStringLiteral("error")).toString(), controller.error());
        QVERIFY(!controller.error().isEmpty());
        QCOMPARE(notifiedFinal.value(QStringLiteral("output")).toString(), QStringLiteral("retained"));
        QVERIFY(notifiedFinal.value(QStringLiteral("usage")).toMap().isEmpty());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        QCOMPARE(closeReady.size(), 0);
        originalPhase = false;
        controller.generate(QStringLiteral("request.failed-validation.retry"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identities = record.readAll();
        QCOMPARE(identities.count('\n'), 2);
        for (const QByteArray &line : identities.split('\n')) {
            if (line.isEmpty()) continue;
            const qint64 captured = line.left(line.indexOf(' ')).toLongLong();
            QVERIFY(captured > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
        }
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
#endif
    }

    void recoveredRuntimeCleanupRestoresTheOriginalFailureAndNotifies_data()
    {
        QTest::addColumn<bool>("malformed");
        QTest::newRow("protocol-failure-after-runtime-recovery") << true;
        QTest::newRow("nonzero-exit-after-runtime-recovery") << false;
    }

    void recoveredRuntimeCleanupRestoresTheOriginalFailureAndNotifies()
    {
#ifndef Q_OS_UNIX
        QSKIP("Captured PID/group cleanup checks are Unix-specific");
#else
        QFETCH(bool, malformed);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QByteArray script = QByteArray(R"PY(import json,os,pathlib,sys
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as record:
 record.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
retry=r['requestId'].endswith('.retry')
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='fresh' if retry else 'retained')
if not retry and )PY") + (malformed ? QByteArray("True") : QByteArray("False"))
            + QByteArray(R"PY(:
 print('{broken}',flush=True)
else:
 emit(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':4 if retry else 2,'outputTokens':5 if retry else 3,'totalTokens':9 if retry else 5},cost={'status':'unknown','currency':None,'amount':None})
sys.exit(0 if retry else 7)
)PY");
        bool allowCleanup = false;
        int removalAttempts = 0;
        QStringList runtimePaths;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeHelper(directory, script), {}, nullptr, [&](const QString &path) {
                ++removalAttempts;
                runtimePaths.append(path);
                return allowCleanup && QDir(path).removeRecursively();
            });
        const auto cleanupGuard = qScopeGuard([&] { allowCleanup = true; });
        QSignalSpy changed(&controller, &AiTextController::changed);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        QStringList order;
        QVariantMap blockedState;
        QVariantMap finalState;
        int finalNotifications = 0;
        bool originalPhase = true;
        const auto snapshot = [&] {
            return QVariantMap{{QStringLiteral("busy"), controller.busy()},
                {QStringLiteral("status"), controller.status()},
                {QStringLiteral("errorCode"), controller.errorCode()},
                {QStringLiteral("error"), controller.error()},
                {QStringLiteral("output"), controller.output()},
                {QStringLiteral("usage"), controller.usage()}};
        };
        connect(&controller, &AiTextController::changed, this, [&] {
            if (!originalPhase) return;
            if (controller.busy() && controller.errorCode() == QStringLiteral("process_cleanup_failed")) {
                order.append(QStringLiteral("cleanup-failed"));
                blockedState = snapshot();
            } else if (!controller.busy()) {
                ++finalNotifications;
                order.append(QStringLiteral("finished"));
                finalState = snapshot();
            }
        });
        controller.generate(QStringLiteral("request.recovered-failure"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        QVERIFY(controller.busy());
        QVERIFY(removalAttempts > 0);
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(closeReady.size(), 0);
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identity = record.readAll();
        record.close();
        QCOMPARE(identity.count('\n'), 1);
        const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
        QVERIFY(pid > 0);
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        QVERIFY(!runtimePaths.isEmpty());
        QVERIFY(QFileInfo::exists(runtimePaths.first()));
        // Observe the real parsed violation or actual finished exit, without writing private state.
        const bool protocolObserved = controller.m_protocolInvalid;
        const int actualExitCode = controller.m_pendingExitCode;
        const qsizetype previousSignals = changed.size();
        const int previousAttempts = removalAttempts;
        QTest::qWait(125);
        QVERIFY(removalAttempts > previousAttempts);
        QCOMPARE(changed.size(), previousSignals);
        QCOMPARE(finalNotifications, 0);
        QCOMPARE(closeReady.size(), 0);
        // No explicit cancel/close here: a late-cancel latch would conceal this recovery bug.
        allowCleanup = true;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        qInfo() << "OWNED_RECOVERED_FAILURE_CLEANUP" << malformed << pid
                << "protocol" << protocolObserved << "actualExit" << actualExitCode
                << "runtimeGone" << runtimePaths << "order" << order
                << "finalNotified" << finalState;
        // The causal oracles run after genuine owned PID/group/runtime cleanup.
        if (malformed) QVERIFY(protocolObserved);
        else QCOMPARE(actualExitCode, 7);
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
        QCOMPARE(order, QStringList({QStringLiteral("cleanup-failed"), QStringLiteral("finished")}));
        QCOMPARE(finalNotifications, 1);
        QVERIFY(blockedState.value(QStringLiteral("busy")).toBool());
        QCOMPARE(blockedState.value(QStringLiteral("errorCode")).toString(), QStringLiteral("process_cleanup_failed"));
        QVERIFY(!finalState.value(QStringLiteral("busy")).toBool());
        QCOMPARE(finalState.value(QStringLiteral("status")).toString(), QStringLiteral("failed"));
        QCOMPARE(finalState.value(QStringLiteral("errorCode")).toString(), QStringLiteral("invalid_helper_response"));
        QCOMPARE(finalState.value(QStringLiteral("error")).toString(), controller.error());
        QVERIFY(!controller.error().isEmpty());
        QVERIFY(controller.error() != blockedState.value(QStringLiteral("error")).toString());
        QCOMPARE(finalState.value(QStringLiteral("output")).toString(), QStringLiteral("retained"));
        QVERIFY(finalState.value(QStringLiteral("usage")).toMap().isEmpty());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(controller.requestClose());
        QCOMPARE(closeReady.size(), 0);
        originalPhase = false;
        controller.generate(QStringLiteral("request.recovered-failure.retry"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identities = record.readAll();
        QCOMPARE(identities.count('\n'), 2);
        for (const QByteArray &line : identities.split('\n')) {
            if (line.isEmpty()) continue;
            const qint64 captured = line.left(line.indexOf(' ')).toLongLong();
            QVERIFY(captured > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
        }
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
#endif
    }

    void lateCancellationPreservesAlreadyObservedFailure_data()
    {
        QTest::addColumn<QString>("cause");
        QTest::addColumn<bool>("close");
        for (const char *cause : {"malformed", "provider", "provider-held", "nonzero", "runtime", "failed-start"}) {
            QTest::newRow((QByteArray(cause) + "-cancel").constData()) << QString::fromLatin1(cause) << false;
            QTest::newRow((QByteArray(cause) + "-close").constData()) << QString::fromLatin1(cause) << true;
        }
    }

    void lateCancellationPreservesAlreadyObservedFailure()
    {
#ifndef Q_OS_UNIX
        QSKIP("Owned PID/group checks are Unix-specific");
#else
        QFETCH(QString, cause);
        QFETCH(bool, close);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString gate = directory.filePath(QStringLiteral("allow-eof"));
        const QByteArray body = QByteArray(R"PY(import json,os,pathlib,sys,time
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as f: f.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra): print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
retry=r['requestId'].endswith('.retry')
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='fresh' if retry else 'retained')
cause=')PY") + cause.toUtf8() + QByteArray(R"PY('
if retry or cause in ('nonzero','runtime'):
 emit(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':4 if retry else 2,'outputTokens':5 if retry else 3,'totalTokens':9 if retry else 5},cost={'status':'unknown','currency':None,'amount':None})
else:
 if cause=='malformed': print('{broken}',flush=True)
 else: emit(2,'failed',code='provider_failed',retryable=False)
if not retry and cause=='provider-held':
 while not pathlib.Path(r')PY") + gate.toUtf8() + QByteArray(R"PY(').exists(): time.sleep(.005)
sys.exit(7 if not retry and cause=='nonzero' else 0)
)PY");
        const QString helper = writeHelper(directory, body);
        QString python = QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE);
        if (cause == QStringLiteral("failed-start")) {
            python = directory.filePath(QStringLiteral("broken-python"));
            QFile broken(python);
            QVERIFY(broken.open(QIODevice::WriteOnly));
            const QByteArray shebang = "#!" + directory.filePath(QStringLiteral("missing-interpreter")).toUtf8() + "\n";
            QCOMPARE(broken.write(shebang), qint64(shebang.size()));
            broken.close();
            QVERIFY(QFile::setPermissions(python, QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner));
        }
        bool allowCleanup = false;
        QStringList runtimePaths;
        AiTextController controller(python, helper, {}, nullptr, [&](const QString &path) {
            runtimePaths.append(path);
            return allowCleanup && QDir(path).removeRecursively();
        }, 100);
        const auto cleanupGuard = qScopeGuard([&] { allowCleanup = true; });
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        controller.generate(QStringLiteral("request.failure"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"), QStringLiteral("127.0.0.1"), 11434, true);
        bool failureParsedBeforeEof = false;
        if (cause == QStringLiteral("provider-held")) {
            QTRY_VERIFY_WITH_TIMEOUT(controller.m_terminalEvent
                && controller.m_terminalType == QStringLiteral("failed")
                && controller.m_process.state() == QProcess::Running, 3000);
            failureParsedBeforeEof = true;
        } else {
            QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        }
        const bool protocolObserved = controller.m_protocolInvalid;
        const QString terminalBeforeCancel = controller.m_terminalType;
        const int exitBeforeCancel = controller.m_pendingExitCode;
        const bool startFailed = controller.m_process.error() == QProcess::FailedToStart;
        if (close) QVERIFY(!controller.requestClose());
        else controller.cancelAll();
        if (failureParsedBeforeEof)
            QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        allowCleanup = true;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QByteArray identities;
        if (cause == QStringLiteral("failed-start")) {
            QVERIFY(!QFileInfo::exists(marker));
            QCOMPARE(controller.m_process.state(), QProcess::NotRunning);
        } else {
            QFile record(marker);
            QVERIFY(record.open(QIODevice::ReadOnly));
            identities = record.readAll();
            QCOMPARE(identities.count('\n'), 1);
            const qint64 pid = identities.left(identities.indexOf(' ')).toLongLong();
            QVERIFY(pid > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        }
        QVERIFY(!runtimePaths.isEmpty());
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        qInfo() << "OWNED_FAILURE_CLEANUP" << cause << close << identities.trimmed()
                << "protocol" << protocolObserved << "terminal" << terminalBeforeCancel
                << "exit" << exitBeforeCancel << "failedStart" << startFailed
                << "beforeEof" << failureParsedBeforeEof << "runtimeGone" << runtimePaths;
        // All failure-precedence oracles below run after genuine owned cleanup.
        if (cause == QStringLiteral("malformed")) QVERIFY(protocolObserved);
        if (cause == QStringLiteral("provider")) QCOMPARE(terminalBeforeCancel, QStringLiteral("failed"));
        if (cause == QStringLiteral("provider-held")) QVERIFY(failureParsedBeforeEof);
        if (cause == QStringLiteral("nonzero")) QCOMPARE(exitBeforeCancel, 7);
        if (cause == QStringLiteral("failed-start")) QVERIFY(startFailed);
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        const QString expected = cause == QStringLiteral("runtime") ? QStringLiteral("process_cleanup_failed")
            : cause == QStringLiteral("failed-start") ? QStringLiteral("helper_unavailable")
            : cause.startsWith(QStringLiteral("provider")) ? QStringLiteral("provider_failed")
            : QStringLiteral("invalid_helper_response");
        QCOMPARE(controller.errorCode(), expected);
        QVERIFY(!controller.error().isEmpty());
        QCOMPARE(controller.output(), cause == QStringLiteral("failed-start") ? QString() : QStringLiteral("retained"));
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(closeReady.size(), close ? 1 : 0);
        if (cause == QStringLiteral("failed-start")) {
            QVERIFY(QFile::remove(python));
            QVERIFY(::symlink(QFile::encodeName(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE)).constData(),
                              QFile::encodeName(python).constData()) == 0);
        }
        controller.generate(QStringLiteral("request.failure.retry"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"), QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QCOMPARE(closeReady.size(), close ? 1 : 0);
        QFile retryRecord(marker);
        QVERIFY(retryRecord.open(QIODevice::ReadOnly));
        const QByteArray allIdentities = retryRecord.readAll();
        QCOMPARE(allIdentities.count('\n'), cause == QStringLiteral("failed-start") ? 1 : 2);
        for (const QByteArray &identity : allIdentities.split('\n')) {
            if (identity.isEmpty()) continue;
            const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
            QVERIFY(pid > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        }
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
#endif
    }

    void cancellationBeforeStartDoesNotInventAnExitFailure_data()
    {
        QTest::addColumn<bool>("close");
        QTest::newRow("cancel-before-start") << false;
        QTest::newRow("close-before-start") << true;
    }

    void cancellationBeforeStartDoesNotInventAnExitFailure()
    {
#ifndef Q_OS_UNIX
        QSKIP("Owned PID/group checks are Unix-specific");
#else
        QFETCH(bool, close);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        QStringList runtimePaths;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeHelper(directory, reportedResultHelper(marker)), {}, nullptr, [&](const QString &path) {
                runtimePaths.append(path);
                return QDir(path).removeRecursively();
            }, 100);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        qint64 capturedPid = 0;
        connect(&controller.m_process, &QProcess::started, this, [&] { capturedPid = controller.m_process.processId(); });
        bool requested = false;
        bool observedBeforeStart = false;
        connect(&controller, &AiTextController::changed, this, [&] {
            if (requested || controller.status() != QStringLiteral("running")) return;
            requested = true;
            observedBeforeStart = controller.m_process.state() == QProcess::NotRunning;
            if (close) controller.requestClose();
            else controller.cancelAll();
        });
        controller.generate(QStringLiteral("request.prestart"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"), QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        if (capturedPid > 0) {
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(capturedPid), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(capturedPid), 0) == -1 && errno == ESRCH);
        }
        QVERIFY(!runtimePaths.isEmpty());
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        qInfo() << "OWNED_PRESTART_CLEANUP" << close << capturedPid << observedBeforeStart << runtimePaths;
        QVERIFY(requested);
        QVERIFY(observedBeforeStart);
        QCOMPARE(controller.status(), QStringLiteral("cancelled_unconfirmed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("cancelled_unconfirmed"));
        QVERIFY(controller.output().isEmpty());
        QVERIFY(controller.usage().isEmpty());
        QVERIFY(!QFileInfo::exists(marker));
        QCOMPARE(closeReady.size(), close ? 1 : 0);
#endif
    }

    void rejectedProtocolDrainsBufferedAndLaterStdout_data()
    {
        QTest::addColumn<QString>("delivery");
        QTest::newRow("buffered-residual-next-read") << QStringLiteral("buffered");
        QTest::newRow("later-ready-read-event") << QStringLiteral("later");
        QTest::newRow("finished-consumes-residual") << QStringLiteral("finished");
    }

    void rejectedProtocolDrainsBufferedAndLaterStdout()
    {
#ifndef Q_OS_UNIX
        QSKIP("Owned PID/group checks are Unix-specific");
#else
        QFETCH(QString, delivery);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString gate = directory.filePath(QStringLiteral("send-late"));
        const QString exitGate = directory.filePath(QStringLiteral("allow-exit"));
        const QByteArray body = QByteArray(R"PY(import json,os,pathlib,signal,sys,time
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as f: f.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def line(sequence,kind,**extra): return (json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':'))+'\n').encode()
if r['requestId'].endswith('.retry'):
 os.write(1,line(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])+line(1,'delta',text='fresh')+line(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':4,'outputTokens':5,'totalTokens':9},cost={'status':'unknown','currency':None,'amount':None}))
 sys.exit(0)
signal.signal(signal.SIGTERM,signal.SIG_IGN)
delivery=')PY") + delivery.toUtf8() + QByteArray(R"PY('
late=line(2,'delta',text='rejected')
initial=line(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])+line(1,'delta',text='partial')+b'{broken}\n'
os.write(1,initial+(late if delivery!='later' else b''))
if delivery=='finished': sys.exit(0)
while not pathlib.Path(r')PY") + gate.toUtf8() + QByteArray(R"PY(').exists(): time.sleep(.005)
os.write(1,late if delivery=='later' else b'\n')
while not pathlib.Path(r')PY") + exitGate.toUtf8() + QByteArray(R"PY(').exists(): time.sleep(.005)
)PY");
        QStringList runtimePaths;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeHelper(directory, body), {}, nullptr, [&](const QString &path) {
                runtimePaths.append(path);
                return QDir(path).removeRecursively();
            });
        int lateOutputProcessState = -1;
        int rejectedReadyReads = 0;
        connect(&controller.m_process, &QProcess::readyReadStandardOutput, this, [&] {
            if (controller.m_protocolInvalid) ++rejectedReadyReads;
        });
        connect(&controller, &AiTextController::changed, this, [&] {
            if (controller.m_protocolInvalid && controller.output().contains(QStringLiteral("rejected")))
                lateOutputProcessState = controller.m_process.state();
        });
        controller.generate(QStringLiteral("request.drain"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"), QStringLiteral("127.0.0.1"), 11434, true);
        bool residualWitness = false;
        if (delivery != QStringLiteral("finished")) {
            QTRY_VERIFY_WITH_TIMEOUT(controller.m_protocolInvalid, 3000);
            residualWitness = controller.m_stdout.contains("rejected");
            const int readsBeforeRelease = rejectedReadyReads;
            QFile release(gate);
            QVERIFY(release.open(QIODevice::WriteOnly));
            QCOMPARE(release.write("send"), qint64(4));
            release.close();
            QTRY_VERIFY_WITH_TIMEOUT(rejectedReadyReads > readsBeforeRelease, 3000);
            QFile finish(exitGate);
            QVERIFY(finish.open(QIODevice::WriteOnly));
            QCOMPARE(finish.write("exit"), qint64(4));
            finish.close();
        }
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 4000);
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identity = record.readAll();
        record.close();
        const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
        QVERIFY(pid > 0);
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        QVERIFY(!runtimePaths.isEmpty());
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        qInfo() << "OWNED_DRAIN_CLEANUP" << delivery << pid << "residualWitness" << residualWitness
                << "lateOutputProcessState" << lateOutputProcessState << "rejectedReadyReads" << rejectedReadyReads
                << "runtimeGone" << runtimePaths;
        // Compare the accepted output only after real PID/group/runtime cleanup.
        QCOMPARE(controller.output(), QStringLiteral("partial"));
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(lateOutputProcessState, -1);
        controller.generate(QStringLiteral("request.drain.retry"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"), QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identities = record.readAll();
        QCOMPARE(identities.count('\n'), 2);
        for (const QByteArray &line : identities.split('\n')) {
            if (line.isEmpty()) continue;
            const qint64 captured = line.left(line.indexOf(' ')).toLongLong();
            QVERIFY(captured > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
        }
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
#endif
    }

    void reportedUsageWaitsForValidatedEofExitAndCleanup_data()
    {
        QTest::addColumn<QString>("boundary");
        for (const char *name : {"extra-event", "unterminated-bytes", "nonzero-exit",
                                 "clean-eof", "cancel", "timeout", "runtime-cleanup"})
            QTest::newRow(name) << QString::fromLatin1(name);
    }

    void reportedUsageWaitsForValidatedEofExitAndCleanup()
    {
#ifndef Q_OS_UNIX
        QSKIP("Captured PID/group cleanup checks are Unix-specific");
#else
        QFETCH(QString, boundary);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString gate = directory.filePath(QStringLiteral("allow-eof"));
        const QByteArray script = QByteArray(R"PY(import json,os,pathlib,sys,time
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as record:
 record.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
retry=r['requestId'].endswith('.retry')
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='fresh' if retry else 'retained')
emit(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':4 if retry else 2,'outputTokens':5 if retry else 3,'totalTokens':9 if retry else 5},cost={'status':'unknown','currency':None,'amount':None})
if retry: sys.exit(0)
while not pathlib.Path(r')PY") + gate.toUtf8() + QByteArray(R"PY(').exists(): time.sleep(.005)
boundary=')PY") + boundary.toUtf8() + QByteArray(R"PY('
if boundary=='extra-event': emit(3,'delta',text='unexpected')
if boundary=='unterminated-bytes':
 sys.stdout.write('unterminated')
 sys.stdout.flush()
sys.exit(7 if boundary=='nonzero-exit' else 0)
)PY");
        bool allowCleanup = boundary != QStringLiteral("runtime-cleanup");
        QStringList runtimePaths;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeHelper(directory, script), {}, nullptr, [&](const QString &path) {
                runtimePaths.append(path);
                return allowCleanup && QDir(path).removeRecursively();
            }, 100, boundary == QStringLiteral("timeout") ? 2000 : 125000);
        bool usagePublishedWhileBusy = false;
        QVariantMap notifiedFinalUsage;
        connect(&controller, &AiTextController::changed, this, [&] {
            if (controller.busy()) usagePublishedWhileBusy |= !controller.usage().isEmpty();
            else notifiedFinalUsage = controller.usage();
        });
        controller.generate(QStringLiteral("request.eof-boundary"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(controller.output() == QStringLiteral("retained")
                                 && controller.m_terminalEvent, 3000);
        // Read-only witness that the real stdout completed line was parsed, without fabricating events.
        const QVariantMap beforeEofUsage = controller.usage();
        const bool busyBeforeEof = controller.busy();
        if (boundary == QStringLiteral("cancel")) controller.cancelAll();
        else if (boundary != QStringLiteral("timeout")) {
            QFile release(gate);
            QVERIFY(release.open(QIODevice::WriteOnly));
            QCOMPARE(release.write("allow"), qint64(5));
            release.close();
        }
        QVariantMap cleanupBlockedUsage;
        bool cleanupWasBusy = false;
        if (!allowCleanup) {
            QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
            cleanupBlockedUsage = controller.usage();
            cleanupWasBusy = controller.busy();
            allowCleanup = true;
        }
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 4000);
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identity = record.readAll();
        record.close();
        const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
        QVERIFY(pid > 0);
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        QVERIFY(!runtimePaths.isEmpty());
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        qInfo() << "OWNED_HELPER_CLEANUP" << boundary << "pid/group absent" << pid
                << "runtime paths absent" << runtimePaths;
        // Causal metadata assertions run only after the owned helper/group/runtime have gone.
        QVERIFY(busyBeforeEof);
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        const bool validCompletion = boundary == QStringLiteral("clean-eof")
            || boundary == QStringLiteral("runtime-cleanup");
        if (validCompletion) {
            QCOMPARE(controller.status(), QStringLiteral("completed"));
            QVERIFY(controller.errorCode().isEmpty());
            QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 5);
            QCOMPARE(notifiedFinalUsage, controller.usage());
        } else {
            QCOMPARE(controller.status(), boundary == QStringLiteral("cancel")
                ? QStringLiteral("cancelled_unconfirmed") : QStringLiteral("failed"));
            QCOMPARE(controller.errorCode(), boundary == QStringLiteral("cancel")
                ? QStringLiteral("cancelled_unconfirmed") : boundary == QStringLiteral("timeout")
                ? QStringLiteral("operation_timeout") : QStringLiteral("invalid_helper_response"));
            QVERIFY(controller.usage().isEmpty());
            QVERIFY(notifiedFinalUsage.isEmpty());
        }
        if (boundary == QStringLiteral("runtime-cleanup")) {
            QVERIFY(cleanupWasBusy);
            QVERIFY(cleanupBlockedUsage.isEmpty());
        }
        QVERIFY(beforeEofUsage.isEmpty());
        QVERIFY(!usagePublishedWhileBusy);
        controller.generate(QStringLiteral("request.eof-boundary.retry"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QCOMPARE(notifiedFinalUsage, controller.usage());
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray allIdentities = record.readAll();
        QCOMPARE(allIdentities.count('\n'), 2);
        for (const QByteArray &line : allIdentities.split('\n')) {
            if (line.isEmpty()) continue;
            const qint64 captured = line.left(line.indexOf(' ')).toLongLong();
            QVERIFY(captured > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(captured), 0) == -1 && errno == ESRCH);
        }
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
#endif
    }

    void closingPublishesFinalStateBeforeReadyAndRejectsReentrantGenerate_data()
    {
        QTest::addColumn<bool>("cooperative");
        QTest::newRow("cooperative-cancellation") << true;
        QTest::newRow("forced-cancellation") << false;
    }

    void closingPublishesFinalStateBeforeReadyAndRejectsReentrantGenerate()
    {
#ifndef Q_OS_UNIX
        QSKIP("Captured PID/group cleanup checks are Unix-specific");
#else
        QFETCH(bool, cooperative);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QByteArray script = QByteArray(R"PY(import json,os,pathlib,signal,sys,time
r=json.loads(sys.stdin.buffer.read())
with pathlib.Path(r')PY") + marker.toUtf8() + QByteArray(R"PY(').open('a') as record:
 record.write(str(os.getpid())+' '+r['requestId']+'\n')
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
def terminated(signum,frame):
 emit(2,'cancelled')
 sys.exit(0)
if r['requestId'] != 'request.close-original':
 emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
 emit(1,'delta',text='fresh')
 emit(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':4,'outputTokens':5,'totalTokens':9},cost={'status':'unknown','currency':None,'amount':None})
 sys.exit(0)
signal.signal(signal.SIGTERM,)PY")
            + (cooperative ? QByteArray("terminated") : QByteArray("signal.SIG_IGN"))
            + QByteArray(R"PY()
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='retained')
time.sleep(60)
)PY");
        QStringList runtimePaths;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeHelper(directory, script), {}, nullptr, [&](const QString &path) {
                runtimePaths.append(path);
                return QDir(path).removeRecursively();
            }, 100);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        QStringList order;
        QVariantMap notifiedFinal;
        QVariantMap readyFinal;
        bool closePhase = false;
        bool reentrantAttempted = false;
        bool reentrantIgnored = false;
        const auto snapshot = [&] {
            return QVariantMap{{QStringLiteral("busy"), controller.busy()},
                {QStringLiteral("status"), controller.status()},
                {QStringLiteral("errorCode"), controller.errorCode()},
                {QStringLiteral("error"), controller.error()},
                {QStringLiteral("output"), controller.output()},
                {QStringLiteral("requestId"), controller.requestId()}};
        };
        connect(&controller, &AiTextController::changed, this, [&] {
            if (!closePhase || controller.busy()) return;
            order.append(QStringLiteral("changed"));
            notifiedFinal = snapshot();
            if (reentrantAttempted) return;
            reentrantAttempted = true;
            controller.generate(QStringLiteral("request.close-reentrant"), QStringLiteral("summarize"),
                                QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                                QStringLiteral("127.0.0.1"), 11434, true);
            reentrantIgnored = !controller.busy()
                && controller.requestId() == QStringLiteral("request.close-original")
                && controller.output() == QStringLiteral("retained");
        });
        connect(&controller, &AiTextController::closeReady, this, [&] {
            if (!closePhase) return;
            order.append(QStringLiteral("closeReady"));
            readyFinal = snapshot();
        });
        controller.generate(QStringLiteral("request.close-original"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(controller.output(), QStringLiteral("retained"), 3000);
        closePhase = true;
        QVERIFY(!controller.requestClose());
        // Any wrongly admitted reentrant helper also exits promptly, so causal assertions follow cleanup.
        QTRY_VERIFY_WITH_TIMEOUT(closeReady.size() == 1 && !controller.busy(), 5000);
        closePhase = false;
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identities = record.readAll();
        record.close();
        for (const QByteArray &identity : identities.split('\n')) {
            if (identity.isEmpty()) continue;
            const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
            QVERIFY(pid > 0);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
            errno = 0;
            QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        }
        QVERIFY(!runtimePaths.isEmpty());
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
        // These ordinary failures occur only after all captured helpers/groups/runtime paths are gone.
        QCOMPARE(order, QStringList({QStringLiteral("changed"), QStringLiteral("closeReady")}));
        QVERIFY(reentrantAttempted);
        QVERIFY(reentrantIgnored);
        QCOMPARE(identities.count('\n'), 1);
        QCOMPARE(notifiedFinal, readyFinal);
        QVERIFY(!notifiedFinal.value(QStringLiteral("busy")).toBool());
        QCOMPARE(notifiedFinal.value(QStringLiteral("status")).toString(), cooperative
            ? QStringLiteral("cancelled_confirmed") : QStringLiteral("cancelled_unconfirmed"));
        QCOMPARE(notifiedFinal.value(QStringLiteral("errorCode")).toString(), cooperative
            ? QString() : QStringLiteral("cancelled_unconfirmed"));
        QCOMPARE(notifiedFinal.value(QStringLiteral("error")).toString().isEmpty(), cooperative);
        QCOMPARE(notifiedFinal.value(QStringLiteral("output")).toString(), QStringLiteral("retained"));
        QCOMPARE(notifiedFinal.value(QStringLiteral("requestId")).toString(), QStringLiteral("request.close-original"));

        controller.generate(QStringLiteral("request.close.retry"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QCOMPARE(closeReady.size(), 1);
        QVERIFY(record.open(QIODevice::ReadOnly));
        QCOMPARE(record.readAll().count('\n'), 2);
        for (const QString &path : runtimePaths) QVERIFY(!QFileInfo::exists(path));
#endif
    }

    void cleanupFailureNotifiesOnceAndKeepsTheCloseBarrier_data()
    {
        QTest::addColumn<bool>("unconfirmedGroup");
        QTest::newRow("runtime-removal-failure") << false;
#if defined(Q_OS_UNIX) && defined(ORLA_TEST_WRAP_KILL)
        QTest::newRow("synthetic-unconfirmed-group-with-kill-interception") << true;
#endif
    }

    void cleanupFailureNotifiesOnceAndKeepsTheCloseBarrier()
    {
        QFETCH(bool, unconfirmedGroup);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QString helper = writeHelper(directory, reportedResultHelper(marker));
        bool allowCleanup = false;
        bool syntheticGroupExists = true;
        int groupChecks = 0;
        int removalAttempts = 0;
        QString runtimePath;
        AiTextController::GroupObserver observer;
#if defined(Q_OS_UNIX) && defined(ORLA_TEST_WRAP_KILL)
        std::unique_ptr<KillInterception> interception;
        if (unconfirmedGroup) {
            // Synthetic observation only: intercepted group signals never reach the kernel.
            interception = std::make_unique<KillInterception>();
            observer = [&](qint64) { ++groupChecks; return syntheticGroupExists; };
        }
#endif
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            observer, nullptr, [&](const QString &path) {
                ++removalAttempts;
                runtimePath = path;
                return allowCleanup && QDir(path).removeRecursively();
            }, 100);
        QSignalSpy changed(&controller, &AiTextController::changed);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        int failureNotifications = 0;
        QString notifiedStatus;
        QString notifiedError;
        QString notifiedOutput;
        bool notifiedBusy = false;
        qsizetype notifiedCloseCount = -1;
        connect(&controller, &AiTextController::changed, this, [&] {
            if (controller.errorCode() != QStringLiteral("process_cleanup_failed")) return;
            ++failureNotifications;
            notifiedStatus = controller.status();
            notifiedError = controller.error();
            notifiedOutput = controller.output();
            notifiedBusy = controller.busy();
            notifiedCloseCount = closeReady.size();
        });
        controller.generate(QStringLiteral("request.cleanup-notify"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("retained"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 4000);
        QVERIFY(controller.busy());
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QCOMPARE(closeReady.size(), 0);
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identity = record.readAll();
        const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
        QVERIFY(pid > 0);
#ifdef Q_OS_UNIX
        const auto observeAbsence = [](pid_t captured) {
            errno = 0;
#if defined(ORLA_TEST_WRAP_KILL)
            return __real_kill(captured, 0) == -1 && errno == ESRCH;
#else
            return ::kill(captured, 0) == -1 && errno == ESRCH;
#endif
        };
        QVERIFY(observeAbsence(static_cast<pid_t>(pid)));
        QVERIFY(observeAbsence(-static_cast<pid_t>(pid)));
#endif
        QCOMPARE(failureNotifications, 1);
        QCOMPARE(notifiedStatus, QStringLiteral("failed"));
        QVERIFY(!notifiedError.isEmpty());
        QCOMPARE(notifiedOutput, QStringLiteral("retained"));
        QVERIFY(notifiedBusy);
        QCOMPARE(notifiedCloseCount, 0);
        const int previousRetries = unconfirmedGroup ? groupChecks : removalAttempts;
        const qsizetype previousSignals = changed.size();
        QTest::qWait(150); // Includes multiple real 25ms cleanup polls.
        QVERIFY((unconfirmedGroup ? groupChecks : removalAttempts) > previousRetries);
        QCOMPARE(failureNotifications, 1);
        QCOMPARE(changed.size(), previousSignals);
        QVERIFY(controller.busy());
        if (!unconfirmedGroup) QVERIFY(QFileInfo::exists(runtimePath));
        QVERIFY(!controller.requestClose());
        const qsizetype closeSignals = changed.size(); // Explicit cancellation may notify separately.
        const int closeFailureNotifications = failureNotifications;
        QTest::qWait(150);
        QCOMPARE(changed.size(), closeSignals);
        QCOMPARE(failureNotifications, closeFailureNotifications);
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(controller.busy());
        allowCleanup = true;
        syntheticGroupExists = false;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(closeReady.size(), 1);
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("process_cleanup_failed"));
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QVERIFY(removalAttempts > 0);
        QVERIFY(!QFileInfo::exists(runtimePath));
        QVERIFY(controller.requestClose());
        QTest::qWait(100);
        QCOMPARE(closeReady.size(), 1);
#if defined(Q_OS_UNIX) && defined(ORLA_TEST_WRAP_KILL)
        if (unconfirmedGroup) {
            QVERIFY(!interceptedKills.empty());
            for (const auto &attempt : interceptedKills) {
                QCOMPARE(attempt.first, -static_cast<pid_t>(pid));
                QVERIFY(attempt.second == SIGTERM || attempt.second == SIGKILL);
            }
        }
#endif
    }

    void newAttemptPreflightFailureClearsPreviousResultWithoutStartingHelper_data()
    {
        QTest::addColumn<QString>("failure");
        QTest::newRow("nonempty-model-with-space") << QStringLiteral("model");
        QTest::newRow("invalid-translation-language") << QStringLiteral("language");
        QTest::newRow("owned-helper-unavailable") << QStringLiteral("helper");
    }

    void newAttemptPreflightFailureClearsPreviousResultWithoutStartingHelper()
    {
        QFETCH(QString, failure);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        const QByteArray script = reportedResultHelper(marker);
        const QString helper = writeHelper(directory, script);
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QSignalSpy changed(&controller, &AiTextController::changed);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        controller.generate(QStringLiteral("request.previous"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("previous result"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QCOMPARE(controller.output(), QStringLiteral("previous result"));
        QCOMPARE(controller.usage().value(QStringLiteral("status")).toString(), QStringLiteral("reported"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 5);
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray previousRecord = record.readAll();
        record.close();
        QCOMPARE(previousRecord.count('\n'), 1);
        const QString runtimeRoot = qEnvironmentVariable("XDG_RUNTIME_DIR");
        const QStringList previousRuntime = QDir(runtimeRoot).entryList(QDir::Dirs | QDir::NoDotAndDotDot);
        if (failure == QStringLiteral("helper")) QVERIFY(QFile::remove(helper));
        const qsizetype changedBeforeFailure = changed.size();
        bool staleResultNotified = false;
        connect(&controller, &AiTextController::changed, this, [&] {
            if (controller.status() == QStringLiteral("failed"))
                staleResultNotified = staleResultNotified || !controller.output().isEmpty()
                    || !controller.usage().isEmpty();
        });
        controller.generate(QStringLiteral("request.new-attempt"),
                            failure == QStringLiteral("language") ? QStringLiteral("translate")
                                                                  : QStringLiteral("summarize"),
                            failure == QStringLiteral("language") ? QVariant(QStringLiteral("123invalid"))
                                                                  : QVariant(),
                            QStringLiteral("new input"),
                            failure == QStringLiteral("model") ? QStringLiteral("model with space")
                                                               : QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), failure == QStringLiteral("helper")
            ? QStringLiteral("helper_unavailable") : QStringLiteral("invalid_request"));
        QVERIFY(!controller.busy());
        QCOMPARE(changed.size(), changedBeforeFailure + 1);
        QCOMPARE(closeReady.size(), 0);
        QVERIFY(record.open(QIODevice::ReadOnly));
        QCOMPARE(record.readAll(), previousRecord);
        record.close();
        QCOMPARE(QDir(runtimeRoot).entryList(QDir::Dirs | QDir::NoDotAndDotDot), previousRuntime);
        QVERIFY(controller.output().isEmpty());
        QVERIFY(controller.usage().isEmpty());
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        QVERIFY(!staleResultNotified);

        if (failure == QStringLiteral("helper")) QCOMPARE(writeHelper(directory, script), helper);
        controller.generate(QStringLiteral("request.new-attempt.retry"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("fresh result"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh result"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 9);
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        QVERIFY(record.open(QIODevice::ReadOnly));
        QCOMPARE(record.readAll().count('\n'), 2);
        QCOMPARE(QDir(runtimeRoot).entryList(QDir::Dirs | QDir::NoDotAndDotDot), previousRuntime);
    }

    void ignoredGeneratePreservesResultWhileBusyOrClosePending_data()
    {
        QTest::addColumn<bool>("closePending");
        QTest::newRow("busy") << false;
        QTest::newRow("close-pending") << true;
    }

    void ignoredGeneratePreservesResultWhileBusyOrClosePending()
    {
#ifndef Q_OS_UNIX
        QSKIP("Captured group absence checks are Unix-specific");
#else
        QFETCH(bool, closePending);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("started"));
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                    writeHelper(directory, reportedResultHelper(marker, true)));
        QSignalSpy changed(&controller, &AiTextController::changed);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        controller.generate(QStringLiteral("request.held-result"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("live result"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(controller.output() == QStringLiteral("live result")
                                 && controller.m_terminalEvent, 3000);
        QVERIFY(controller.usage().isEmpty());
        QVERIFY(controller.busy());
        const QVariantMap liveUsage = controller.usage();
        if (closePending) QVERIFY(!controller.requestClose());
        QVERIFY(controller.busy());
        const qsizetype previousSignals = changed.size();
        controller.generate(QStringLiteral("request.ignored"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("ignored input"), QStringLiteral("model with space"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QCOMPARE(controller.requestId(), QStringLiteral("request.held-result"));
        QCOMPARE(controller.output(), QStringLiteral("live result"));
        QCOMPARE(controller.usage(), liveUsage);
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(changed.size(), previousSignals);
        QCOMPARE(closeReady.size(), 0);
        QFile record(marker);
        QVERIFY(record.open(QIODevice::ReadOnly));
        const QByteArray identity = record.readAll();
        QCOMPARE(identity.count('\n'), 1);
        const qint64 pid = identity.left(identity.indexOf(' ')).toLongLong();
        QVERIFY(pid > 0);
        if (!closePending) controller.cancelAll();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("cancelled_unconfirmed"));
        QCOMPARE(controller.output(), QStringLiteral("live result"));
        QCOMPARE(controller.usage(), liveUsage);
        QCOMPARE(closeReady.size(), closePending ? 1 : 0);
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
#endif
    }

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

    void invalidCostDoesNotPublishOtherwiseValidUsage_data()
    {
        QTest::addColumn<QJsonObject>("cost");
        QTest::newRow("wrong-status") << QJsonObject{{"status", "reported"},
            {"currency", QJsonValue(QJsonValue::Null)}, {"amount", QJsonValue(QJsonValue::Null)}};
        QTest::newRow("unexpected-currency") << QJsonObject{{"status", "unknown"},
            {"currency", "USD"}, {"amount", QJsonValue(QJsonValue::Null)}};
    }

    void invalidCostDoesNotPublishOtherwiseValidUsage()
    {
        QFETCH(QJsonObject, cost);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString requestId = QStringLiteral("request.invalid-cost");
        QJsonObject terminal = QJsonDocument::fromJson(completed(requestId, 2)).object();
        terminal.insert(QStringLiteral("cost"), cost);
        const QByteArray events = started(requestId, 11434, QStringLiteral("model"))
            + eventLine(requestId, 1, QStringLiteral("delta"), {{"text", "retained"}})
            + QJsonDocument(terminal).toJson(QJsonDocument::Compact) + '\n';
        const QString helper = writeHelper(directory,
            QByteArray("import base64,sys\nsys.stdin.buffer.read()\n")
            + "sys.stdout.buffer.write(base64.b64decode(b'" + events.toBase64()
            + "'));sys.stdout.flush()\n");
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        bool usageWasPublished = false;
        connect(&controller, &AiTextController::changed, this, [&] {
            usageWasPublished = usageWasPublished || !controller.usage().isEmpty();
        });
        controller.generate(requestId, QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("invalid_helper_response"));
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QVERIFY(controller.usage().isEmpty());
        QVERIFY(!usageWasPublished);
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
    }

    void outerTimeoutRetainsCauseThroughCleanupAndAllowsNewRequest_data()
    {
        QTest::addColumn<QString>("termination");
        QTest::addColumn<bool>("closeAfterTimeout");
        QTest::newRow("cooperative-cancelled") << QStringLiteral("cancelled") << false;
        QTest::newRow("cooperative-late-completed") << QStringLiteral("completed") << false;
        QTest::newRow("forced-kill") << QStringLiteral("ignore") << true;
    }

    void outerTimeoutRetainsCauseThroughCleanupAndAllowsNewRequest()
    {
#ifndef Q_OS_UNIX
        QSKIP("Process-group timeout cleanup is Unix-specific");
#else
        QFETCH(QString, termination);
        QFETCH(bool, closeAfterTimeout);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString identity = directory.filePath(QStringLiteral("identity"));
        const QByteArray script = QByteArray(R"PY(import json,os,pathlib,signal,sys,time
r=json.loads(sys.stdin.buffer.read())
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
def completed():
 emit(2,'completed',finishReason='stop',usage={'status':'reported','inputTokens':2,'outputTokens':3,'totalTokens':5},cost={'status':'unknown','currency':None,'amount':None})
if r['requestId'].endswith('.retry'):
 emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
 emit(1,'delta',text='fresh')
 completed()
 sys.exit(0)
def terminated(signum,frame):
 if ')PY") + termination.toUtf8() + QByteArray(R"PY(' == 'completed': completed()
 else: emit(2,'cancelled')
 sys.exit(0)
signal.signal(signal.SIGTERM,signal.SIG_IGN if ')PY") + termination.toUtf8()
            + QByteArray(R"PY(' == 'ignore' else terminated)
pathlib.Path(r')PY") + identity.toUtf8() + QByteArray(R"PY(').write_text(str(os.getpid()))
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='retained')
time.sleep(60)
)PY");
        const QString helper = writeHelper(directory, script);
        int removalAttempts = 0;
        bool allowRemoval = false;
        QString runtimePath;
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper,
            {}, nullptr, [&](const QString &path) {
                ++removalAttempts;
                runtimePath = path;
                return allowRemoval && QDir(path).removeRecursively();
            }, 100, 400);
        QSignalSpy closeReady(&controller, &AiTextController::closeReady);
        bool timeoutNotified = false;
        connect(&controller, &AiTextController::changed, this, [&] {
            timeoutNotified = timeoutNotified || controller.errorCode() == QStringLiteral("operation_timeout");
        });
        controller.generate(QStringLiteral("request.timeout"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(controller.output(), QStringLiteral("retained"), 3000);
        QTRY_COMPARE_WITH_TIMEOUT(controller.errorCode(), QStringLiteral("process_cleanup_failed"), 3000);
        QVERIFY(controller.busy());
        QVERIFY(timeoutNotified);
        QVERIFY(removalAttempts > 0);
        QVERIFY(QFileInfo::exists(runtimePath));
        QFile identityFile(identity);
        QVERIFY(identityFile.open(QIODevice::ReadOnly));
        const qint64 pid = identityFile.readAll().trimmed().toLongLong();
        QVERIFY(pid > 0);
        errno = 0;
        QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        errno = 0;
        QVERIFY(::kill(-static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
        if (closeAfterTimeout) QVERIFY(!controller.requestClose());
        else controller.cancel(QStringLiteral("request.timeout"));
        QCOMPARE(closeReady.size(), 0);
        allowRemoval = true;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("operation_timeout"));
        QCOMPARE(closeReady.size(), closeAfterTimeout ? 1 : 0);
        QCOMPARE(controller.output(), QStringLiteral("retained"));
        QVERIFY(!QFileInfo::exists(runtimePath));

        controller.generate(QStringLiteral("request.timeout.retry"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("completed"));
        QVERIFY(controller.errorCode().isEmpty());
        QCOMPARE(controller.output(), QStringLiteral("fresh"));
        QCOMPARE(controller.usage().value(QStringLiteral("totalTokens")).toLongLong(), 5);
        QCOMPARE(controller.costStatus(), QStringLiteral("unknown"));
#endif
    }

    void actualDeadlineBeforeProcessStartFinishesWithoutLaunchingAHelper()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString marker = directory.filePath(QStringLiteral("unexpected-start"));
        const QString helper = writeHelper(directory,
            QByteArray("import pathlib\npathlib.Path(r'") + marker.toUtf8() + "').touch()\n");
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE), helper);
        QSignalSpy processStarted(&controller.m_process, &QProcess::started);
        bool armed = false;
        bool deadlineObserved = false;
        bool processWasNotRunning = false;
        QEventLoop beforeStart;
        connect(&controller, &AiTextController::changed, this, [&] {
            if (armed) {
                deadlineObserved = deadlineObserved || controller.errorCode() == QStringLiteral("operation_timeout");
                if (!controller.busy()) beforeStart.quit();
                return;
            }
            if (controller.status() != QStringLiteral("running")) return;
            armed = true;
            processWasNotRunning = controller.m_process.state() == QProcess::NotRunning;
            // The real timer callback runs while generate's changed signal is still on the stack.
            controller.m_deadline.start(1);
            QTimer::singleShot(1000, &beforeStart, &QEventLoop::quit);
            beforeStart.exec();
        });
        controller.generate(QStringLiteral("request.before-start-timeout"), QStringLiteral("summarize"),
                            QVariant(), QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QVERIFY(armed);
        QVERIFY(processWasNotRunning);
        QVERIFY(!controller.busy());
        QCOMPARE(controller.status(), QStringLiteral("failed"));
        QCOMPARE(controller.errorCode(), QStringLiteral("operation_timeout"));
        QVERIFY(deadlineObserved);
        QCOMPARE(processStarted.size(), 0);
        QVERIFY(!QFileInfo::exists(marker));
        QVERIFY(controller.usage().isEmpty());
    }

    void explicitCancellationKeepsItsCauseBeyondTheOuterDeadline()
    {
#ifndef Q_OS_UNIX
        QSKIP("Process-group cancellation is Unix-specific");
#else
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QByteArray script = R"PY(import json,signal,sys,time
r=json.loads(sys.stdin.buffer.read())
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(sequence,kind,**extra):
 print(json.dumps(dict(b,sequence=sequence,type=kind,**extra),separators=(',',':')),flush=True)
def terminated(signum,frame):
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 time.sleep(.5)
 emit(2,'cancelled')
 sys.exit(0)
signal.signal(signal.SIGTERM,terminated)
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text='retained')
time.sleep(60)
)PY";
        AiTextController controller(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
                                    writeHelper(directory, script), {}, nullptr, {}, 1000, 300);
        bool timeoutNotified = false;
        connect(&controller, &AiTextController::changed, this, [&] {
            timeoutNotified = timeoutNotified || controller.errorCode() == QStringLiteral("operation_timeout");
        });
        controller.generate(QStringLiteral("request.explicit-cancel"), QStringLiteral("summarize"), QVariant(),
                            QStringLiteral("input"), QStringLiteral("model"),
                            QStringLiteral("127.0.0.1"), 11434, true);
        QTRY_COMPARE_WITH_TIMEOUT(controller.output(), QStringLiteral("retained"), 3000);
        controller.cancel(QStringLiteral("request.explicit-cancel"));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.busy(), 3000);
        QCOMPARE(controller.status(), QStringLiteral("cancelled_confirmed"));
        QVERIFY(controller.errorCode().isEmpty());
        QVERIFY(!timeoutNotified);
        QCOMPARE(controller.output(), QStringLiteral("retained"));
#endif
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
