#include "AiProviderController.h"

#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QSet>
#include <QTemporaryDir>

#include <utility>

#ifdef Q_OS_UNIX
#include <cerrno>
#include <csignal>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace {
constexpr qsizetype kMaximumResultBytes = 32 * 1024;
constexpr int kOuterDeadlineMs = 22000;
constexpr int kCancellationGraceMs = 3000;
constexpr int kCleanupVerificationMs = 2000;

const QStringList kProviderIds = {QStringLiteral("codex"), QStringLiteral("claude"),
    QStringLiteral("opencode"), QStringLiteral("ollama"), QStringLiteral("lmstudio")};
const QStringList kCapabilityNames = {QStringLiteral("installation"), QStringLiteral("anonymous_protocol"),
    QStringLiteral("authentication"), QStringLiteral("inference"), QStringLiteral("cancellation"),
    QStringLiteral("usage_reporting")};
const QSet<QString> kCapabilityValues = {QStringLiteral("absent"), QStringLiteral("unknown"),
    QStringLiteral("auth_needed"), QStringLiteral("supported")};
const QSet<QString> kMessageCodes = {
    QStringLiteral("anonymous_protocol_supported"), QStringLiteral("cancelled"),
    QStringLiteral("cli_not_found"), QStringLiteral("cli_present_version_not_queried"),
    QStringLiteral("client_version_recognized"), QStringLiteral("helper_failure"),
    QStringLiteral("isolation_unavailable"), QStringLiteral("process_cleanup_failed"),
    QStringLiteral("protocol_invalid"), QStringLiteral("protocol_output_limit"),
    QStringLiteral("protocol_process_failed"), QStringLiteral("protocol_shutdown_failed"),
    QStringLiteral("protocol_timeout"), QStringLiteral("protocol_version_unknown"),
    QStringLiteral("stderr_limit"), QStringLiteral("stdout_limit"), QStringLiteral("timeout"),
    QStringLiteral("version_failed"), QStringLiteral("version_unrecognized")};

bool exactKeys(const QJsonObject &object, const QSet<QString> &expected)
{
    const QStringList keys = object.keys();
    return QSet<QString>(keys.cbegin(), keys.cend()) == expected;
}

QString safeErrorMessage(const QString &code)
{
    if (code == QStringLiteral("helper_unavailable"))
        return AiProviderController::tr("A verificação local não está disponível nesta instalação.");
    if (code == QStringLiteral("operation_timeout"))
        return AiProviderController::tr("A verificação local excedeu o tempo permitido.");
    if (code == QStringLiteral("invalid_request"))
        return AiProviderController::tr("O pedido de verificação não é válido.");
    return AiProviderController::tr("A resposta da verificação local não pôde ser validada.");
}
}

AiProviderController::AiProviderController(const QString &pythonPath, const QString &helperPath,
                                           GroupObserver groupObserver, QObject *parent,
                                           RuntimeRemover runtimeRemover,
                                           int cancellationGraceMs)
    : QObject(parent), m_pythonPath(pythonPath), m_helperPath(helperPath),
      m_groupObserver(std::move(groupObserver)), m_runtimeRemover(std::move(runtimeRemover)),
      m_cancellationGraceMs(cancellationGraceMs > 0 ? cancellationGraceMs : kCancellationGraceMs)
{
    m_deadline.setSingleShot(true);
    m_killGrace.setSingleShot(true);
    m_groupPoll.setInterval(25);
    m_cleanupDeadline.setSingleShot(true);
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        const QByteArray available = m_process.readAllStandardOutput();
        if (m_stdout.size() + available.size() > kMaximumResultBytes) {
            m_outputOverflow = true;
            beginCancellation();
            return;
        }
        m_stdout.append(available);
    });
    connect(&m_process, &QProcess::finished, this, &AiProviderController::handleFinished);
    connect(&m_process, &QProcess::started, this, [this] {
        m_processGroup = m_process.processId();
        if (m_cancelled) beginCancellation();
    });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error != QProcess::FailedToStart) return;
        const quint64 generation = m_generation;
        const quint64 processGeneration = m_processGeneration;
        m_deadline.stop();
        m_pendingExitCode = -1;
        m_pendingExitStatus = QProcess::CrashExit;
        if (m_processGeneration == m_generation && !m_cancelled) {
            fail(QStringLiteral("helper_unavailable"), safeErrorMessage(QStringLiteral("helper_unavailable")));
            if (m_generation != generation || m_processGeneration != processGeneration
                || !m_operationActive) return;
        }
        if (!m_cleanupActive) m_cleanupActive = true;
        finishAfterCleanup(true);
    });
    connect(&m_deadline, &QTimer::timeout, this, [this] {
        if (!busy()) return;
        const quint64 generation = m_generation;
        const quint64 processGeneration = m_processGeneration;
        fail(QStringLiteral("operation_timeout"), safeErrorMessage(QStringLiteral("operation_timeout")));
        if (m_generation != generation || m_processGeneration != processGeneration
            || !m_operationActive) return;
        beginCancellation();
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
    connect(&m_groupPoll, &QTimer::timeout, this, &AiProviderController::pollGroupCleanup);
    connect(&m_cleanupDeadline, &QTimer::timeout, this, [this] {
        finishAfterCleanup(!ownedGroupExists());
    });
}

AiProviderController::~AiProviderController()
{
    if (!busy()) return;
#ifdef Q_OS_UNIX
    killOwnedGroup(SIGKILL);
#endif
    m_process.kill();
    // QProcess destruction may block if this emergency path is reached. Normal
    // UI close defers application teardown until asynchronous cleanup completes.
}

void AiProviderController::discover()
{
    start(QStringLiteral("detect"), QStringLiteral("detect-%1").arg(m_generation + 1),
          ExpectedDocument::Providers);
}

void AiProviderController::probeCodex(const QString &requestId)
{
    static const QRegularExpression requestPattern(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"));
    if (!requestPattern.match(requestId).hasMatch()) {
        fail(QStringLiteral("invalid_request"), safeErrorMessage(QStringLiteral("invalid_request")));
        return;
    }
    start(QStringLiteral("probe-codex-anonymous"), requestId, ExpectedDocument::CodexProvider);
}

void AiProviderController::start(const QString &operation, const QString &requestId, ExpectedDocument expected)
{
    if (busy() || m_closePending) return;
    const QFileInfo python(m_pythonPath);
    const QFileInfo helper(m_helperPath);
    if (!python.isAbsolute() || !python.isFile() || !python.isExecutable()
        || !helper.isAbsolute() || !helper.isFile() || !helper.isReadable()) {
        fail(QStringLiteral("helper_unavailable"), safeErrorMessage(QStringLiteral("helper_unavailable")));
        return;
    }
    if (!prepareRuntime()) {
        fail(QStringLiteral("helper_unavailable"), safeErrorMessage(QStringLiteral("helper_unavailable")));
        return;
    }
    ++m_generation;
    m_processGeneration = m_generation;
    m_expected = expected;
    m_operation = operation;
    m_requestId = requestId;
    m_stdout.clear();
    m_outputOverflow = false;
    m_cancelled = false;
    m_operationActive = true;
    m_cleanupActive = false;
    m_killSent = false;
    m_pendingExitCode = -1;
    m_pendingExitStatus = QProcess::CrashExit;
    m_errorCode.clear();
    m_error.clear();
    m_stableStatus = m_status == QStringLiteral("running") ? QStringLiteral("disabled") : m_status;
    m_status = QStringLiteral("running");
    m_processGroup = 0;
    m_process.setProcessChannelMode(QProcess::SeparateChannels);
    m_process.setStandardErrorFile(QProcess::nullDevice());
    QProcessEnvironment environment;
    for (const QString &name : {QStringLiteral("HOME"), QStringLiteral("PATH"), QStringLiteral("LANG"),
                                QStringLiteral("CODEX_HOME")}) {
        const QString value = qEnvironmentVariable(name.toLocal8Bit().constData());
        if (!value.isNull() && !value.contains(QChar::Null)) environment.insert(name, value);
    }
    m_process.setProcessEnvironment(environment);
#ifdef Q_OS_UNIX
    m_process.setUnixProcessParameters(QProcess::UnixProcessFlag::CreateNewSession
        | QProcess::UnixProcessFlag::CloseFileDescriptors
        | QProcess::UnixProcessFlag::ResetSignalHandlers
        | QProcess::UnixProcessFlag::DisableCoreDumps);
#endif
    const quint64 generation = m_generation;
    const QStringList arguments = {QStringLiteral("-I"), QStringLiteral("-B"), m_helperPath, operation,
        QStringLiteral("--runtime-root"), m_runtimeDirectory->path(), QStringLiteral("--runtime-root-id"),
        QStringLiteral("%1:%2").arg(m_runtimeDevice).arg(m_runtimeInode)};
    emit changed();
    if (m_generation != generation || m_processGeneration != generation
        || !m_operationActive || m_cancelled || m_closePending || m_cleanupActive) return;
    m_deadline.start(kOuterDeadlineMs);
    m_process.start(m_pythonPath, arguments, QIODevice::ReadOnly);
}

void AiProviderController::cancel(const QString &requestId)
{
    if (!busy() || requestId != m_requestId) return;
    cancelAll();
}

void AiProviderController::cancelAll()
{
    if (!busy()) return;
    ++m_generation;
    m_cancelled = true;
    m_status = m_stableStatus;
    beginCancellation();
    emit changed();
}

bool AiProviderController::requestClose()
{
    if (!busy()) return true;
    m_closePending = true;
    cancelAll();
    return false;
}

void AiProviderController::beginCancellation()
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

void AiProviderController::killOwnedGroup(int signalNumber)
{
#ifdef Q_OS_UNIX
    if (m_processGroup > 0) {
        if (::kill(-static_cast<pid_t>(m_processGroup), signalNumber) != 0 && errno != ESRCH)
            m_process.kill();
    } else if (signalNumber == SIGTERM) {
        m_process.terminate();
    }
#else
    Q_UNUSED(signalNumber)
#endif
}

bool AiProviderController::ownedGroupExists() const
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

void AiProviderController::beginGroupCleanup()
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

void AiProviderController::pollGroupCleanup()
{
    if (!m_cleanupActive) return;
    if (m_process.state() != QProcess::NotRunning) return;
    if (!ownedGroupExists()) finishAfterCleanup(true);
}

void AiProviderController::finishAfterCleanup(bool cleanupConfirmed)
{
    if (!m_cleanupActive) return;
    m_killGrace.stop();
    m_cleanupDeadline.stop();
    if (!cleanupConfirmed) {
        const quint64 generation = m_generation;
        const quint64 processGeneration = m_processGeneration;
        fail(QStringLiteral("process_cleanup_failed"),
             tr("A limpeza do processo local não pôde ser confirmada."));
        if (m_generation != generation || m_processGeneration != processGeneration
            || !m_cleanupActive) return;
        if (!m_groupPoll.isActive()) m_groupPoll.start();
        return;
    }
    if (!removeOwnedRuntime()) {
        const quint64 generation = m_generation;
        const quint64 processGeneration = m_processGeneration;
        fail(QStringLiteral("process_cleanup_failed"),
             tr("A limpeza do processo local não pôde ser confirmada."));
        if (m_generation != generation || m_processGeneration != processGeneration
            || !m_cleanupActive) return;
        if (!m_groupPoll.isActive()) m_groupPoll.start();
        return;
    }

    m_groupPoll.stop();
    const bool current = m_processGeneration == m_generation;
    const bool cancelled = m_cancelled;
    if (current && !m_cancelled && m_errorCode.isEmpty()) {
        if (m_outputOverflow) {
            recordFailure(QStringLiteral("invalid_helper_response"),
                          safeErrorMessage(QStringLiteral("invalid_helper_response")));
        } else if (m_pendingExitStatus != QProcess::NormalExit || m_pendingExitCode != 0) {
            recordFailure(QStringLiteral("helper_failed"), safeErrorMessage(QStringLiteral("helper_failed")));
        } else {
            QVariantList providers;
            if (!parseDocument(m_stdout, &providers))
                recordFailure(QStringLiteral("invalid_helper_response"),
                              safeErrorMessage(QStringLiteral("invalid_helper_response")));
            else
                publish(std::move(providers));
        }
    } else if (cancelled) {
        m_status = m_stableStatus;
    }

    const bool closePending = m_closePending;
    m_operationActive = false;
    m_cleanupActive = false;
    m_processGroup = 0;
    m_processGeneration = 0;
    m_operation.clear();
    m_requestId.clear();
    m_stdout.clear();
    m_outputOverflow = false;
    m_cancelled = false;
    m_closePending = false;
    m_killSent = false;
    m_pendingExitCode = -1;
    m_pendingExitStatus = QProcess::CrashExit;

    if (closePending) {
        emit closeReady();
        return;
    }
    emit changed();
}

bool AiProviderController::prepareRuntime()
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

    auto directory = std::make_unique<QTemporaryDir>(requested + QStringLiteral("/orla-ai-XXXXXX"));
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

bool AiProviderController::removeOwnedRuntime()
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

bool AiProviderController::runtimeIdentityMatches() const
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

void AiProviderController::handleFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    m_deadline.stop();
    m_pendingExitCode = exitCode;
    m_pendingExitStatus = exitStatus;
    const QByteArray remaining = m_process.readAllStandardOutput();
    if (m_stdout.size() + remaining.size() > kMaximumResultBytes)
        m_outputOverflow = true;
    else
        m_stdout.append(remaining);
    m_process.readAllStandardError();
    beginGroupCleanup();
}

void AiProviderController::recordFailure(const QString &code, const QString &message)
{
    m_status = QStringLiteral("error");
    m_errorCode = code;
    m_error = message;
}

void AiProviderController::fail(const QString &code, const QString &message)
{
    recordFailure(code, message);
    emit changed();
}

bool AiProviderController::parseDocument(const QByteArray &bytes, QVariantList *providers) const
{
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(bytes, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) return false;
    const QJsonObject root = document.object();
    if (root.value(QStringLiteral("schemaVersion")).toInt(-1) != 1) return false;
    if (m_expected == ExpectedDocument::Providers) {
        if (!exactKeys(root, {QStringLiteral("schemaVersion"), QStringLiteral("providers")})
            || !root.value(QStringLiteral("providers")).isArray()) return false;
        const QJsonArray array = root.value(QStringLiteral("providers")).toArray();
        if (array.size() != kProviderIds.size()) return false;
        for (int index = 0; index < array.size(); ++index) {
            if (!array[index].isObject()) return false;
            QVariantMap provider;
            if (!parseProvider(array[index].toObject(), &provider)
                || provider.value(QStringLiteral("id")).toString() != kProviderIds[index]
                || !validProviderSemantics(provider)) return false;
            providers->append(provider);
        }
        return true;
    }
    if (!exactKeys(root, {QStringLiteral("schemaVersion"), QStringLiteral("provider")})
        || !root.value(QStringLiteral("provider")).isObject()) return false;
    QVariantMap provider;
    if (!parseProvider(root.value(QStringLiteral("provider")).toObject(), &provider)
        || provider.value(QStringLiteral("id")).toString() != QStringLiteral("codex")
        || !validProviderSemantics(provider)) return false;
    providers->append(provider);
    return true;
}

bool AiProviderController::parseProvider(const QJsonObject &object, QVariantMap *provider) const
{
    const QSet<QString> providerKeys = {QStringLiteral("id"), QStringLiteral("displayName"),
        QStringLiteral("enabled"), QStringLiteral("clientVersion"), QStringLiteral("capabilities"),
        QStringLiteral("route"), QStringLiteral("messageCode")};
    if (!exactKeys(object, providerKeys) || !object.value(QStringLiteral("id")).isString()
        || !object.value(QStringLiteral("displayName")).isString()
        || !object.value(QStringLiteral("enabled")).isBool() || object.value(QStringLiteral("enabled")).toBool()
        || !object.value(QStringLiteral("capabilities")).isObject()
        || !object.value(QStringLiteral("route")).isString()
        || !object.value(QStringLiteral("messageCode")).isString()) return false;
    const QString id = object.value(QStringLiteral("id")).toString();
    const int providerIndex = kProviderIds.indexOf(id);
    if (providerIndex < 0) return false;
    const QStringList names = {QStringLiteral("Codex"), QStringLiteral("Claude Code"),
        QStringLiteral("OpenCode"), QStringLiteral("Ollama"), QStringLiteral("LM Studio")};
    const QStringList routes = {QStringLiteral("owned_app_server"), QStringLiteral("official_terminal_handoff"),
        QStringLiteral("selected_local_server"), QStringLiteral("selected_local_server"),
        QStringLiteral("selected_local_server")};
    if (object.value(QStringLiteral("displayName")).toString() != names[providerIndex]
        || object.value(QStringLiteral("route")).toString() != routes[providerIndex]
        || !kMessageCodes.contains(object.value(QStringLiteral("messageCode")).toString())) return false;
    const QJsonValue versionValue = object.value(QStringLiteral("clientVersion"));
    if (!versionValue.isNull() && (!versionValue.isString() || versionValue.toString().size() > 64
        || !QRegularExpression(QStringLiteral("^[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"))
                .match(versionValue.toString()).hasMatch())) return false;
    const QJsonObject capabilities = object.value(QStringLiteral("capabilities")).toObject();
    if (!exactKeys(capabilities, QSet<QString>(kCapabilityNames.cbegin(), kCapabilityNames.cend()))) return false;
    QVariantMap safeCapabilities;
    for (const QString &name : kCapabilityNames) {
        if (!capabilities.value(name).isString() || !kCapabilityValues.contains(capabilities.value(name).toString()))
            return false;
        safeCapabilities.insert(name, capabilities.value(name).toString());
    }
    provider->insert(QStringLiteral("id"), id);
    provider->insert(QStringLiteral("displayName"), names[providerIndex]);
    provider->insert(QStringLiteral("enabled"), false);
    provider->insert(QStringLiteral("clientVersion"), versionValue.isNull() ? QVariant() : versionValue.toString());
    provider->insert(QStringLiteral("capabilities"), safeCapabilities);
    provider->insert(QStringLiteral("route"), routes[providerIndex]);
    provider->insert(QStringLiteral("messageCode"), object.value(QStringLiteral("messageCode")).toString());
    return true;
}

bool AiProviderController::validProviderSemantics(const QVariantMap &provider) const
{
    const QString id = provider.value(QStringLiteral("id")).toString();
    const QString message = provider.value(QStringLiteral("messageCode")).toString();
    const QVariant versionValue = provider.value(QStringLiteral("clientVersion"));
    const bool hasVersion = versionValue.isValid() && !versionValue.isNull();
    const QString version = versionValue.toString();
    const QVariantMap capabilities = provider.value(QStringLiteral("capabilities")).toMap();
    const QString installation = capabilities.value(QStringLiteral("installation")).toString();
    const QString protocol = capabilities.value(QStringLiteral("anonymous_protocol")).toString();

    if (capabilities.value(QStringLiteral("authentication")).toString() != QStringLiteral("unknown")
        || capabilities.value(QStringLiteral("usage_reporting")).toString() != QStringLiteral("unknown")) return false;
    const QString dependent = installation == QStringLiteral("absent")
        ? QStringLiteral("absent") : QStringLiteral("unknown");
    if (capabilities.value(QStringLiteral("inference")).toString() != dependent
        || capabilities.value(QStringLiteral("cancellation")).toString() != dependent) return false;
    if (installation != QStringLiteral("absent") && installation != QStringLiteral("unknown")
        && installation != QStringLiteral("supported")) return false;

    if (m_expected == ExpectedDocument::Providers) {
        if (protocol != dependent) return false;
        if (message == QStringLiteral("cli_not_found"))
            return installation == QStringLiteral("absent") && !hasVersion;
        if (message == QStringLiteral("cli_present_version_not_queried"))
            return id == QStringLiteral("ollama") && installation == QStringLiteral("supported") && !hasVersion;
        if (message == QStringLiteral("client_version_recognized"))
            return id != QStringLiteral("ollama") && installation == QStringLiteral("supported") && hasVersion;
        const QSet<QString> unknownVersionMessages = {QStringLiteral("cancelled"),
            QStringLiteral("isolation_unavailable"), QStringLiteral("process_cleanup_failed"),
            QStringLiteral("stderr_limit"), QStringLiteral("stdout_limit"), QStringLiteral("timeout"),
            QStringLiteral("version_failed"), QStringLiteral("version_unrecognized")};
        if (id == QStringLiteral("ollama"))
            return message == QStringLiteral("cancelled")
                && installation == QStringLiteral("unknown") && !hasVersion;
        return unknownVersionMessages.contains(message)
            && installation == QStringLiteral("unknown") && !hasVersion;
    }

    if (id != QStringLiteral("codex")) return false;
    if (message == QStringLiteral("cli_not_found"))
        return installation == QStringLiteral("absent") && protocol == QStringLiteral("absent") && !hasVersion;
    if (message == QStringLiteral("anonymous_protocol_supported"))
        return installation == QStringLiteral("supported") && protocol == QStringLiteral("supported")
            && version == QStringLiteral("0.162.1");
    if (message == QStringLiteral("protocol_version_unknown"))
        return installation == QStringLiteral("supported") && protocol == QStringLiteral("unknown")
            && hasVersion && version != QStringLiteral("0.162.1");
    const QSet<QString> versionStageMessages = {QStringLiteral("cancelled"),
        QStringLiteral("isolation_unavailable"), QStringLiteral("process_cleanup_failed"),
        QStringLiteral("stderr_limit"), QStringLiteral("stdout_limit"), QStringLiteral("timeout"),
        QStringLiteral("version_failed"), QStringLiteral("version_unrecognized")};
    if (versionStageMessages.contains(message)) {
        const bool versionStage = installation == QStringLiteral("unknown")
            && protocol == QStringLiteral("unknown") && !hasVersion;
        const bool postVersionCleanup = (message == QStringLiteral("cancelled")
            || message == QStringLiteral("isolation_unavailable")
            || message == QStringLiteral("process_cleanup_failed"))
            && installation == QStringLiteral("supported") && protocol == QStringLiteral("unknown")
            && version == QStringLiteral("0.162.1");
        return versionStage || postVersionCleanup;
    }
    const QSet<QString> protocolFailureMessages = {QStringLiteral("protocol_invalid"),
        QStringLiteral("protocol_output_limit"), QStringLiteral("protocol_process_failed"),
        QStringLiteral("protocol_shutdown_failed"), QStringLiteral("protocol_timeout")};
    return protocolFailureMessages.contains(message)
        && installation == QStringLiteral("supported") && protocol == QStringLiteral("unknown")
        && version == QStringLiteral("0.162.1");
}

void AiProviderController::publish(QVariantList providers)
{
    if (m_expected == ExpectedDocument::CodexProvider && m_providers.size() == kProviderIds.size()) {
        m_providers[0] = providers.first();
    } else {
        m_providers = std::move(providers);
    }
    m_status = QStringLiteral("report_available");
    m_stableStatus = m_status;
    m_errorCode.clear();
    m_error.clear();
}
