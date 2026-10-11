#include "AiTextController.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QElapsedTimer>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QSet>
#include <QTemporaryDir>
#include <QThread>

#include <cmath>
#include <limits>
#include <utility>

#ifdef Q_OS_UNIX
#include <cerrno>
#include <csignal>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace {
constexpr qsizetype kMaximumLineBytes = 64 * 1024;
constexpr qsizetype kMaximumOutputBytes = 256 * 1024;
constexpr int kMaximumEvents = 4096;
constexpr int kOuterDeadlineMs = 125000;
constexpr int kDefaultCancellationGraceMs = 3000;
constexpr int kCleanupVerificationMs = 2000;
constexpr int kEmergencyReapMs = 2000;
constexpr double kMaximumExactJsonInteger = 9007199254740991.0;

bool exactKeys(const QJsonObject &object, const QSet<QString> &expected)
{
    const QStringList keys = object.keys();
    return QSet<QString>(keys.cbegin(), keys.cend()) == expected;
}

class JsonKeyScanner
{
public:
    explicit JsonKeyScanner(const QByteArray &data) : m_data(data) {}
    bool validWithoutDuplicates()
    {
        skipWhitespace();
        const bool valid = value(0);
        skipWhitespace();
        return valid && !m_duplicate && m_position == m_data.size();
    }

private:
    void skipWhitespace()
    {
        while (m_position < m_data.size() && QByteArray(" \t\r\n").contains(m_data[m_position]))
            ++m_position;
    }
    bool stringToken(QByteArray *token = nullptr)
    {
        if (m_position >= m_data.size() || m_data[m_position] != '"') return false;
        const qsizetype start = m_position++;
        while (m_position < m_data.size()) {
            const char current = m_data[m_position++];
            if (current == '"') {
                if (token) *token = m_data.mid(start, m_position - start);
                return true;
            }
            if (current == '\\') {
                if (m_position >= m_data.size()) return false;
                if (m_data[m_position++] == 'u') {
                    if (m_position + 4 > m_data.size()) return false;
                    m_position += 4;
                }
            }
        }
        return false;
    }
    QString decodedKey(const QByteArray &token) const
    {
        QJsonParseError error;
        const QJsonDocument document = QJsonDocument::fromJson(QByteArray("[") + token + "]", &error);
        return error.error == QJsonParseError::NoError && document.isArray()
            ? document.array().first().toString() : QString();
    }
    bool object(int depth)
    {
        if (depth > 64 || m_data[m_position++] != '{') return false;
        QSet<QString> keys;
        skipWhitespace();
        if (m_position < m_data.size() && m_data[m_position] == '}') { ++m_position; return true; }
        while (m_position < m_data.size()) {
            QByteArray token;
            if (!stringToken(&token)) return false;
            const QString key = decodedKey(token);
            if (key.isNull() || keys.contains(key)) m_duplicate = true;
            keys.insert(key);
            skipWhitespace();
            if (m_position >= m_data.size() || m_data[m_position++] != ':') return false;
            skipWhitespace();
            if (!value(depth + 1)) return false;
            skipWhitespace();
            if (m_position >= m_data.size()) return false;
            const char separator = m_data[m_position++];
            if (separator == '}') return true;
            if (separator != ',') return false;
            skipWhitespace();
        }
        return false;
    }
    bool array(int depth)
    {
        if (depth > 64 || m_data[m_position++] != '[') return false;
        skipWhitespace();
        if (m_position < m_data.size() && m_data[m_position] == ']') { ++m_position; return true; }
        while (m_position < m_data.size()) {
            if (!value(depth + 1)) return false;
            skipWhitespace();
            if (m_position >= m_data.size()) return false;
            const char separator = m_data[m_position++];
            if (separator == ']') return true;
            if (separator != ',') return false;
            skipWhitespace();
        }
        return false;
    }
    bool value(int depth)
    {
        if (m_position >= m_data.size()) return false;
        if (m_data[m_position] == '{') return object(depth);
        if (m_data[m_position] == '[') return array(depth);
        if (m_data[m_position] == '"') return stringToken();
        const qsizetype start = m_position;
        while (m_position < m_data.size()
               && !QByteArray(" \t\r\n,]}").contains(m_data[m_position])) ++m_position;
        return m_position > start;
    }
    const QByteArray &m_data;
    qsizetype m_position = 0;
    bool m_duplicate = false;
};

QString safeMessage(const QString &code)
{
    if (code == QStringLiteral("invalid_request"))
        return AiTextController::tr("O pedido de texto não é válido.");
    if (code == QStringLiteral("helper_unavailable"))
        return AiTextController::tr("A geração local não está disponível nesta instalação.");
    if (code == QStringLiteral("operation_timeout"))
        return AiTextController::tr("A geração local excedeu o tempo permitido.");
    if (code == QStringLiteral("process_cleanup_failed"))
        return AiTextController::tr("A limpeza do processo local não pôde ser confirmada.");
    if (code == QStringLiteral("cancelled_unconfirmed"))
        return AiTextController::tr("O cancelamento local não pôde ser confirmado.");
    return AiTextController::tr("A resposta da geração local não pôde ser validada.");
}

bool boundedCount(const QJsonValue &value, qint64 *result)
{
    if (!value.isDouble()) return false;
    const double number = value.toDouble(-1.0);
    if (!std::isfinite(number) || number < 0.0 || std::floor(number) != number
        || number > kMaximumExactJsonInteger) return false;
    *result = static_cast<qint64>(number);
    return true;
}
}

AiTextController::AiTextController(const QString &pythonPath, const QString &helperPath,
                                   GroupObserver groupObserver, QObject *parent,
                                   RuntimeRemover runtimeRemover, int cancellationGraceMs,
                                   int outerDeadlineMs)
    : QObject(parent), m_pythonPath(pythonPath), m_helperPath(helperPath),
      m_groupObserver(std::move(groupObserver)), m_runtimeRemover(std::move(runtimeRemover)),
      m_cancellationGraceMs(cancellationGraceMs > 0 ? cancellationGraceMs
                                                    : kDefaultCancellationGraceMs),
      m_outerDeadlineMs(outerDeadlineMs > 0 ? outerDeadlineMs : kOuterDeadlineMs)
{
    m_deadline.setSingleShot(true);
    m_killGrace.setSingleShot(true);
    m_groupPoll.setInterval(25);
    m_cleanupDeadline.setSingleShot(true);

    connect(&m_process, &QProcess::readyReadStandardOutput, this, &AiTextController::consumeStdout);
    connect(&m_process, &QProcess::started, this, [this] {
        if (m_processGeneration != m_generation || !m_operationActive) return;
        m_processGroup = m_process.processId();
        if (m_cancelRequested) {
            beginCancellation();
            return;
        }
        const qsizetype frameSize = m_requestFrame.size();
        const qint64 accepted = m_process.write(m_requestFrame);
        m_requestFrame.fill('\0');
        m_requestFrame.clear();
        if (accepted != frameSize) {
            protocolFailure();
            return;
        }
        m_process.closeWriteChannel();
    });
    connect(&m_process, &QProcess::finished, this, &AiTextController::handleFinished);
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error != QProcess::FailedToStart || !m_operationActive) return;
        m_deadline.stop();
        recordFailure(m_timedOut ? QStringLiteral("operation_timeout")
                                 : QStringLiteral("helper_unavailable"));
        m_pendingExitCode = -1;
        m_pendingExitStatus = QProcess::CrashExit;
        m_cleanupActive = true;
        finishAfterCleanup(true);
    });
    connect(&m_deadline, &QTimer::timeout, this, [this] {
        if (!busy() || m_cancelRequested) return;
        m_timedOut = true;
        recordFailure(QStringLiteral("operation_timeout"));
        m_cancelRequested = true;
        beginCancellation();
        emit changed();
    });
    connect(&m_killGrace, &QTimer::timeout, this, [this] {
        if (!busy()) return;
#ifdef Q_OS_UNIX
        killOwnedGroup(SIGKILL);
#endif
        if (m_process.state() != QProcess::NotRunning) m_process.kill();
        m_killSent = true;
        m_cleanupDeadline.start(kCleanupVerificationMs);
    });
    connect(&m_groupPoll, &QTimer::timeout, this, &AiTextController::pollGroupCleanup);
    connect(&m_cleanupDeadline, &QTimer::timeout, this, [this] {
        finishAfterCleanup(!ownedGroupExists());
    });
}

AiTextController::~AiTextController()
{
    if (!busy()) return;

    m_deadline.stop();
    m_killGrace.stop();
    m_groupPoll.stop();
    m_cleanupDeadline.stop();
    disconnect(&m_process, nullptr, this, nullptr);
    disconnect(&m_deadline, nullptr, this, nullptr);
    disconnect(&m_killGrace, nullptr, this, nullptr);
    disconnect(&m_groupPoll, nullptr, this, nullptr);
    disconnect(&m_cleanupDeadline, nullptr, this, nullptr);

    const bool ownsCapturedProcess = m_operationActive && m_processGeneration != 0
        && m_processGeneration == m_generation;
#ifdef Q_OS_UNIX
    if (ownsCapturedProcess) killOwnedGroup(SIGKILL);
#endif
    if (ownsCapturedProcess && m_process.state() != QProcess::NotRunning) {
        m_process.kill();
        m_process.waitForFinished(kEmergencyReapMs);
    }

    if (ownsCapturedProcess && m_processGroup > 0) {
        QElapsedTimer timer;
        timer.start();
        while (ownedGroupExists() && timer.elapsed() < kEmergencyReapMs)
            QThread::msleep(10);
    }
    if (ownsCapturedProcess && m_process.state() == QProcess::NotRunning
        && !ownedGroupExists()) removeOwnedRuntime();
}

bool AiTextController::validateRequest(const QString &requestId, const QString &task,
                                       const QVariant &targetLanguage, const QString &text,
                                       const QString &model, const QString &numericHost,
                                       int port, bool explicitConsent) const
{
    static const QRegularExpression requestPattern(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"));
    static const QRegularExpression modelPattern(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$"));
    static const QRegularExpression languagePattern(QStringLiteral("^[\\p{L}][\\p{L} -]{0,63}$"));
    if (!explicitConsent || !requestPattern.match(requestId).hasMatch()
        || (task != QStringLiteral("rewrite") && task != QStringLiteral("summarize")
            && task != QStringLiteral("translate"))
        || text.isEmpty() || text.size() > 16384 || text.toUtf8().size() > 65536
        || !modelPattern.match(model).hasMatch()
        || (numericHost != QStringLiteral("127.0.0.1") && numericHost != QStringLiteral("::1"))
        || port < 1 || port > 65535) return false;
    if (task == QStringLiteral("translate"))
        return targetLanguage.metaType().id() == QMetaType::QString
            && languagePattern.match(targetLanguage.toString()).hasMatch();
    return !targetLanguage.isValid() || targetLanguage.isNull();
}

void AiTextController::generate(const QString &requestId, const QString &task,
                                const QVariant &targetLanguage, const QString &text,
                                const QString &model, const QString &numericHost,
                                int port, bool explicitConsent)
{
    if (busy() || m_closePending) return;
    m_output.clear();
    m_usage.clear();
    m_costStatus = QStringLiteral("unknown");
    if (!validateRequest(requestId, task, targetLanguage, text, model, numericHost, port,
                         explicitConsent)) {
        recordFailure(QStringLiteral("invalid_request"));
        emit changed();
        return;
    }
    const QFileInfo python(m_pythonPath);
    const QFileInfo helper(m_helperPath);
    if (!python.isAbsolute() || !python.isFile() || !python.isExecutable()
        || !helper.isAbsolute() || !helper.isFile() || !helper.isReadable()
        || !prepareRuntime()) {
        recordFailure(QStringLiteral("helper_unavailable"));
        emit changed();
        return;
    }

    ++m_generation;
    m_processGeneration = m_generation;
    m_requestId = requestId;
    m_destination = numericHost == QStringLiteral("::1")
        ? QStringLiteral("http://[::1]:%1/api/chat").arg(port)
        : QStringLiteral("http://127.0.0.1:%1/api/chat").arg(port);
    m_model = model;
    m_errorCode.clear();
    m_error.clear();
    m_stdout.clear();
    m_nextSequence = 0;
    m_eventCount = 0;
    m_outputBytes = 0;
    m_startedEvent = false;
    m_terminalEvent = false;
    m_terminalType.clear();
    m_terminalCode.clear();
    m_operationActive = true;
    m_cleanupActive = false;
    m_cancelRequested = false;
    m_timedOut = false;
    m_killSent = false;
    m_protocolInvalid = false;
    m_pendingExitCode = -1;
    m_pendingExitStatus = QProcess::CrashExit;
    m_processGroup = 0;
    m_status = QStringLiteral("running");

    QJsonObject frame;
    frame.insert(QStringLiteral("schemaVersion"), 1);
    frame.insert(QStringLiteral("requestId"), requestId);
    frame.insert(QStringLiteral("provider"), QStringLiteral("ollama_local"));
    frame.insert(QStringLiteral("task"), task);
    frame.insert(QStringLiteral("targetLanguage"), task == QStringLiteral("translate")
        ? QJsonValue(targetLanguage.toString()) : QJsonValue(QJsonValue::Null));
    frame.insert(QStringLiteral("text"), text);
    frame.insert(QStringLiteral("model"), model);
    frame.insert(QStringLiteral("endpoint"), m_destination);
    frame.insert(QStringLiteral("credentialBytes"), 0);
    m_requestFrame = QJsonDocument(frame).toJson(QJsonDocument::Compact) + '\n';

    m_process.setProcessChannelMode(QProcess::SeparateChannels);
    m_process.setStandardErrorFile(QProcess::nullDevice());
    m_process.setProcessEnvironment(QProcessEnvironment());
    m_process.setWorkingDirectory(m_runtimeDirectory->path());
#ifdef Q_OS_UNIX
    m_process.setUnixProcessParameters(QProcess::UnixProcessFlag::CreateNewSession
        | QProcess::UnixProcessFlag::CloseFileDescriptors
        | QProcess::UnixProcessFlag::ResetSignalHandlers
        | QProcess::UnixProcessFlag::DisableCoreDumps);
#endif
    emit changed();
    if (!m_operationActive || m_processGeneration != m_generation) return;
    m_deadline.start(m_outerDeadlineMs);
    m_process.start(m_pythonPath,
                    {QStringLiteral("-I"), QStringLiteral("-B"), m_helperPath,
                     QStringLiteral("run-ollama")}, QIODevice::ReadWrite);
}

void AiTextController::cancel(const QString &requestId)
{
    if (busy() && requestId == m_requestId) cancelAll();
}

void AiTextController::cancelAll()
{
    if (!busy()) return;
    m_deadline.stop();
    m_cancelRequested = true;
    beginCancellation();
    emit changed();
}

bool AiTextController::requestClose()
{
    if (!busy()) return true;
    m_closePending = true;
    cancelAll();
    return false;
}

void AiTextController::consumeStdout()
{
    if (!m_operationActive || m_processGeneration != m_generation) {
        m_process.readAllStandardOutput();
        return;
    }
    m_stdout.append(m_process.readAllStandardOutput());
    while (true) {
        const qsizetype newline = m_stdout.indexOf('\n');
        if (newline < 0) break;
        if (newline + 1 > kMaximumLineBytes) {
            protocolFailure();
            return;
        }
        const QByteArray line = m_stdout.left(newline);
        m_stdout.remove(0, newline + 1);
        if (!consumeLine(line)) {
            protocolFailure();
            return;
        }
    }
    if (m_stdout.size() >= kMaximumLineBytes) protocolFailure();
}

bool AiTextController::validateBase(const QJsonObject &object, const QString &type) const
{
    return object.value(QStringLiteral("schemaVersion")).isDouble()
        && object.value(QStringLiteral("schemaVersion")).toInt(-1) == 1
        && object.value(QStringLiteral("requestId")).isString()
        && object.value(QStringLiteral("requestId")).toString() == m_requestId
        && object.value(QStringLiteral("sequence")).isDouble()
        && object.value(QStringLiteral("sequence")).toInt(-1) == m_nextSequence
        && object.value(QStringLiteral("type")).isString()
        && object.value(QStringLiteral("type")).toString() == type;
}

bool AiTextController::validateUsage(const QJsonObject &object, QVariantMap *usage) const
{
    const QSet<QString> keys = {QStringLiteral("status"), QStringLiteral("inputTokens"),
        QStringLiteral("outputTokens"), QStringLiteral("totalTokens")};
    if (!exactKeys(object, keys) || !object.value(QStringLiteral("status")).isString()) return false;
    const QString status = object.value(QStringLiteral("status")).toString();
    if (status == QStringLiteral("unknown")) {
        if (!object.value(QStringLiteral("inputTokens")).isNull()
            || !object.value(QStringLiteral("outputTokens")).isNull()
            || !object.value(QStringLiteral("totalTokens")).isNull()) return false;
        usage->insert(QStringLiteral("status"), status);
        usage->insert(QStringLiteral("inputTokens"), QVariant());
        usage->insert(QStringLiteral("outputTokens"), QVariant());
        usage->insert(QStringLiteral("totalTokens"), QVariant());
        return true;
    }
    qint64 input = 0;
    qint64 output = 0;
    qint64 total = 0;
    if (status != QStringLiteral("reported")
        || !boundedCount(object.value(QStringLiteral("inputTokens")), &input)
        || !boundedCount(object.value(QStringLiteral("outputTokens")), &output)
        || !boundedCount(object.value(QStringLiteral("totalTokens")), &total)
        || input > std::numeric_limits<qint64>::max() - output || input + output != total) return false;
    usage->insert(QStringLiteral("status"), status);
    usage->insert(QStringLiteral("inputTokens"), input);
    usage->insert(QStringLiteral("outputTokens"), output);
    usage->insert(QStringLiteral("totalTokens"), total);
    return true;
}

bool AiTextController::consumeLine(const QByteArray &line)
{
    if (line.isEmpty() || m_terminalEvent || ++m_eventCount > kMaximumEvents) return false;
    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(line, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()
        || !JsonKeyScanner(line).validWithoutDuplicates()) return false;
    const QJsonObject object = document.object();
    const QString type = object.value(QStringLiteral("type")).toString();
    const QSet<QString> base = {QStringLiteral("schemaVersion"), QStringLiteral("requestId"),
        QStringLiteral("sequence"), QStringLiteral("type")};
    if (!validateBase(object, type)) return false;

    if (type == QStringLiteral("started")) {
        if (m_startedEvent || m_nextSequence != 0
            || !exactKeys(object, base | QSet<QString>{QStringLiteral("provider"),
                QStringLiteral("destination"), QStringLiteral("model")})
            || object.value(QStringLiteral("provider")).toString() != QStringLiteral("ollama_local")
            || object.value(QStringLiteral("destination")).toString() != m_destination
            || object.value(QStringLiteral("model")).toString() != m_model) return false;
        m_startedEvent = true;
    } else if (type == QStringLiteral("delta")) {
        if (!m_startedEvent || !exactKeys(object, base | QSet<QString>{QStringLiteral("text")})
            || !object.value(QStringLiteral("text")).isString()
            || object.value(QStringLiteral("text")).toString().isEmpty()) return false;
        const QString delta = object.value(QStringLiteral("text")).toString();
        const qsizetype bytes = delta.toUtf8().size();
        if (bytes > 8 * 1024 || m_outputBytes + bytes > kMaximumOutputBytes) return false;
        m_outputBytes += bytes;
        m_output.append(delta);
        emit changed();
    } else if (type == QStringLiteral("completed")) {
        QVariantMap usage;
        if (!m_startedEvent || !exactKeys(object, base | QSet<QString>{QStringLiteral("finishReason"),
                QStringLiteral("usage"), QStringLiteral("cost")})
            || !object.value(QStringLiteral("finishReason")).isString()
            || !QSet<QString>{QStringLiteral("stop"), QStringLiteral("length"), QStringLiteral("load"),
                QStringLiteral("completed"), QStringLiteral("incomplete")}
                    .contains(object.value(QStringLiteral("finishReason")).toString())
            || !object.value(QStringLiteral("usage")).isObject()
            || !validateUsage(object.value(QStringLiteral("usage")).toObject(), &usage)
            || !object.value(QStringLiteral("cost")).isObject()) return false;
        const QJsonObject cost = object.value(QStringLiteral("cost")).toObject();
        if (!exactKeys(cost, {QStringLiteral("status"), QStringLiteral("currency"), QStringLiteral("amount")})
            || cost.value(QStringLiteral("status")).toString() != QStringLiteral("unknown")
            || !cost.value(QStringLiteral("currency")).isNull()
            || !cost.value(QStringLiteral("amount")).isNull()) return false;
        m_usage = std::move(usage);
        m_terminalEvent = true;
        m_terminalType = type;
    } else if (type == QStringLiteral("failed")) {
        static const QSet<QString> codes = {QStringLiteral("invalid_request"), QStringLiteral("helper_unavailable"),
            QStringLiteral("credential_cancelled"), QStringLiteral("credential_required"),
            QStringLiteral("endpoint_rejected"), QStringLiteral("connection_failed"),
            QStringLiteral("tls_failed"), QStringLiteral("authentication_failed"),
            QStringLiteral("permission_denied"), QStringLiteral("model_unavailable"),
            QStringLiteral("rate_limited"), QStringLiteral("provider_unavailable"),
            QStringLiteral("provider_failed"), QStringLiteral("unsupported_provider_event"),
            QStringLiteral("protocol_invalid"), QStringLiteral("response_limit"),
            QStringLiteral("operation_timeout"), QStringLiteral("process_cleanup_failed"),
            QStringLiteral("unsupported_transport")};
        if (!m_startedEvent || !exactKeys(object, base | QSet<QString>{QStringLiteral("code"),
                QStringLiteral("retryable")})
            || !object.value(QStringLiteral("code")).isString()
            || !codes.contains(object.value(QStringLiteral("code")).toString())
            || !object.value(QStringLiteral("retryable")).isBool()) return false;
        m_terminalEvent = true;
        m_terminalType = type;
        m_terminalCode = object.value(QStringLiteral("code")).toString();
    } else if (type == QStringLiteral("cancelled")) {
        if (!m_startedEvent || !exactKeys(object, base)) return false;
        m_terminalEvent = true;
        m_terminalType = type;
    } else {
        return false;
    }
    ++m_nextSequence;
    return true;
}

void AiTextController::protocolFailure()
{
    if (m_protocolInvalid) return;
    m_protocolInvalid = true;
    if (!m_timedOut) recordFailure(QStringLiteral("invalid_helper_response"));
    beginCancellation();
}

void AiTextController::beginCancellation()
{
    if (!busy()) return;
    m_cleanupActive = true;
#ifdef Q_OS_UNIX
    killOwnedGroup(SIGTERM);
#else
    m_process.terminate();
#endif
    if (!m_groupPoll.isActive()) m_groupPoll.start();
    if (!m_killGrace.isActive() && !m_killSent) m_killGrace.start(m_cancellationGraceMs);
}

void AiTextController::killOwnedGroup(int signalNumber)
{
#ifdef Q_OS_UNIX
    if (!m_operationActive || m_processGeneration == 0
        || m_processGeneration != m_generation) return;
    if (m_processGroup > 0) {
        if (!ownedGroupExists()) {
            m_processGroup = 0;
            return;
        }
        if (::kill(-static_cast<pid_t>(m_processGroup), signalNumber) != 0 && errno != ESRCH)
            m_process.kill();
    } else if (signalNumber == SIGTERM && m_process.state() != QProcess::NotRunning) {
        m_process.terminate();
    }
#else
    Q_UNUSED(signalNumber)
#endif
}

bool AiTextController::ownedGroupExists() const
{
#ifdef Q_OS_UNIX
    if (m_processGroup <= 0) return false;
    if (m_groupObserver) return m_groupObserver(m_processGroup);
    errno = 0;
    return ::kill(-static_cast<pid_t>(m_processGroup), 0) == 0 || errno == EPERM;
#else
    return false;
#endif
}

void AiTextController::beginGroupCleanup()
{
    m_cleanupActive = true;
    if (!ownedGroupExists()) {
        finishAfterCleanup(true);
        return;
    }
#ifdef Q_OS_UNIX
    killOwnedGroup(SIGTERM);
#endif
    if (!m_groupPoll.isActive()) m_groupPoll.start();
    if (!m_killGrace.isActive() && !m_killSent) m_killGrace.start(m_cancellationGraceMs);
}

void AiTextController::pollGroupCleanup()
{
    if (!m_cleanupActive || m_process.state() != QProcess::NotRunning) return;
    if (!ownedGroupExists()) finishAfterCleanup(true);
}

void AiTextController::handleFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    m_deadline.stop();
    consumeStdout();
    m_process.readAllStandardError();
    m_pendingExitCode = exitCode;
    m_pendingExitStatus = exitStatus;
    if (!m_stdout.isEmpty()) m_protocolInvalid = true;
    beginGroupCleanup();
}

void AiTextController::finishAfterCleanup(bool cleanupConfirmed)
{
    if (!m_cleanupActive) return;
    m_killGrace.stop();
    m_cleanupDeadline.stop();
    // Confirmed original-group absence ends signal ownership, even if runtime cleanup retries.
    if (cleanupConfirmed) m_processGroup = 0;
    if (!cleanupConfirmed || !removeOwnedRuntime()) {
        const QString failureCode = QStringLiteral("process_cleanup_failed");
        const bool failureChanged = m_status != QStringLiteral("failed")
            || m_errorCode != failureCode || m_error != safeMessage(failureCode);
        recordFailure(failureCode);
        if (!m_groupPoll.isActive()) m_groupPoll.start();
        if (failureChanged) emit changed();
        return;
    }
    m_groupPoll.stop();
    const bool current = m_processGeneration == m_generation;
    if (current) {
        if (!cleanupConfirmed) {
            recordFailure(QStringLiteral("process_cleanup_failed"));
        } else if (m_timedOut) {
            recordFailure(QStringLiteral("operation_timeout"));
        } else if (m_cancelRequested) {
            if (!m_killSent && m_terminalEvent && m_terminalType == QStringLiteral("cancelled")
                && m_pendingExitStatus == QProcess::NormalExit && m_pendingExitCode == 0) {
                m_status = QStringLiteral("cancelled_confirmed");
                m_errorCode.clear();
                m_error.clear();
            } else {
                m_status = QStringLiteral("cancelled_unconfirmed");
                m_errorCode = QStringLiteral("cancelled_unconfirmed");
                m_error = safeMessage(m_errorCode);
            }
        } else if (m_protocolInvalid || !m_terminalEvent
                   || m_pendingExitStatus != QProcess::NormalExit || m_pendingExitCode != 0) {
            if (m_errorCode.isEmpty()) recordFailure(QStringLiteral("invalid_helper_response"));
        } else if (m_terminalType == QStringLiteral("completed")) {
            m_status = QStringLiteral("completed");
            m_errorCode.clear();
            m_error.clear();
        } else if (m_terminalType == QStringLiteral("failed")) {
            m_status = QStringLiteral("failed");
            m_errorCode = m_terminalCode;
            m_error = safeMessage(m_terminalCode);
        } else {
            m_status = QStringLiteral("cancelled_unconfirmed");
            m_errorCode = QStringLiteral("cancelled_unconfirmed");
            m_error = safeMessage(m_errorCode);
        }
    }
    const bool closePending = m_closePending;
    resetOperation();
    if (closePending) {
        m_closePending = false;
        emit closeReady();
    } else {
        emit changed();
    }
}

void AiTextController::recordFailure(const QString &code)
{
    m_status = QStringLiteral("failed");
    m_errorCode = code;
    m_error = safeMessage(code);
}

void AiTextController::resetOperation()
{
    m_operationActive = false;
    m_cleanupActive = false;
    m_processGroup = 0;
    m_processGeneration = 0;
    m_requestFrame.fill('\0');
    m_requestFrame.clear();
    m_stdout.clear();
    m_cancelRequested = false;
    m_timedOut = false;
    m_killSent = false;
}

bool AiTextController::prepareRuntime()
{
    if (m_runtimeDirectory) return false;
    const QString requested = QDir::cleanPath(qEnvironmentVariable("XDG_RUNTIME_DIR"));
    if (!QDir::isAbsolutePath(requested) || requested == QStringLiteral("/")) return false;
    const QFileInfo root(requested);
    if (!root.exists() || !root.isDir() || root.isSymLink()
        || root.canonicalFilePath() != requested) return false;
#ifdef Q_OS_UNIX
    struct stat info {};
    const QByteArray encoded = QFile::encodeName(requested);
    if (::lstat(encoded.constData(), &info) != 0 || !S_ISDIR(info.st_mode)
        || info.st_uid != ::geteuid() || (info.st_mode & 0777) != 0700) return false;
#endif
    auto directory = std::make_unique<QTemporaryDir>(requested + QStringLiteral("/orla-ai-text-XXXXXX"));
    directory->setAutoRemove(false);
    if (!directory->isValid()) return false;
#ifdef Q_OS_UNIX
    const QByteArray runtimeEncoded = QFile::encodeName(directory->path());
    if (::chmod(runtimeEncoded.constData(), 0700) != 0
        || ::lstat(runtimeEncoded.constData(), &info) != 0 || !S_ISDIR(info.st_mode)
        || S_ISLNK(info.st_mode) || info.st_uid != ::geteuid()
        || (info.st_mode & 0777) != 0700) {
        QDir(directory->path()).removeRecursively();
        return false;
    }
    m_runtimeDevice = static_cast<quint64>(info.st_dev);
    m_runtimeInode = static_cast<quint64>(info.st_ino);
#endif
    m_runtimeDirectory = std::move(directory);
    return true;
}

bool AiTextController::runtimeIdentityMatches() const
{
    if (!m_runtimeDirectory) return false;
#ifdef Q_OS_UNIX
    struct stat info {};
    const QByteArray encoded = QFile::encodeName(m_runtimeDirectory->path());
    return ::lstat(encoded.constData(), &info) == 0 && S_ISDIR(info.st_mode)
        && !S_ISLNK(info.st_mode) && info.st_uid == ::geteuid()
        && (info.st_mode & 0777) == 0700
        && static_cast<quint64>(info.st_dev) == m_runtimeDevice
        && static_cast<quint64>(info.st_ino) == m_runtimeInode;
#else
    return true;
#endif
}

bool AiTextController::removeOwnedRuntime()
{
    if (!m_runtimeDirectory) return true;
    if (!runtimeIdentityMatches()) return false;
    const QString path = m_runtimeDirectory->path();
    const bool removed = m_runtimeRemover ? m_runtimeRemover(path) : QDir(path).removeRecursively();
    if (!removed || QFileInfo::exists(path)) return false;
    m_runtimeDirectory.reset();
    m_runtimeDevice = 0;
    m_runtimeInode = 0;
    return true;
}
