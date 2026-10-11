#include "SteamProviderController.h"

#include <QDesktopServices>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QSet>

#ifdef Q_OS_UNIX
#include <cerrno>
#include <csignal>
#include <unistd.h>
#endif

namespace {
constexpr qsizetype kMaximumResultBytes = 512 * 1024 + 1;
constexpr int kOuterDeadlineMs = 8000;
constexpr int kCancellationGraceMs = 3000;
constexpr int kCleanupVerificationMs = 2000;

const QRegularExpression kAppId(QStringLiteral("^[1-9][0-9]{0,9}$"));
const QRegularExpression kRootId(QStringLiteral("^root-(0|[1-9][0-9]*)$"));
const QRegularExpression kLibraryId(QStringLiteral("^library-(0|[1-9][0-9]*)$"));
const QSet<QString> kInventoryStatuses = {QStringLiteral("available"), QStringLiteral("absent"),
    QStringLiteral("partial"), QStringLiteral("unknown")};
const QSet<QString> kRootStatuses = {QStringLiteral("available"), QStringLiteral("absent"),
    QStringLiteral("missing"), QStringLiteral("partial"), QStringLiteral("unknown")};
const QSet<QString> kLibraryStatuses = {QStringLiteral("available"), QStringLiteral("missing"),
    QStringLiteral("partial"), QStringLiteral("unknown")};
const QSet<QString> kAppStatuses = {QStringLiteral("installed_candidate"),
    QStringLiteral("partial"), QStringLiteral("unknown")};
const QSet<QString> kIssueCodes = {QStringLiteral("changed_during_read"),
    QStringLiteral("deadline"), QStringLiteral("directory_entry_limit"),
    QStringLiteral("duplicate_key"), QStringLiteral("file_byte_limit"),
    QStringLiteral("invalid_encoding"), QStringLiteral("invalid_input"),
    QStringLiteral("library_limit"), QStringLiteral("malformed_vdf"),
    QStringLiteral("manifest_limit"), QStringLiteral("missing"),
    QStringLiteral("nesting_limit"), QStringLiteral("pathlike_name_redacted"),
    QStringLiteral("permission_denied"), QStringLiteral("read_error"),
    QStringLiteral("result_byte_limit"), QStringLiteral("token_limit"),
    QStringLiteral("total_byte_limit"), QStringLiteral("truncated_vdf"),
    QStringLiteral("unqualified_state_flags"), QStringLiteral("unknown_state_flags"),
    QStringLiteral("unsafe_installdir"), QStringLiteral("unsafe_path"),
    QStringLiteral("unsafe_target"), QStringLiteral("unsupported_escape"),
    QStringLiteral("unsupported_library_index"), QStringLiteral("unsupported_manifest"),
    QStringLiteral("unsupported_manifest_name"), QStringLiteral("unsupported_vdf"),
    QStringLiteral("worker_error")};

bool exactKeys(const QJsonObject &object, const QSet<QString> &expected)
{
    const QStringList keys = object.keys();
    return QSet<QString>(keys.cbegin(), keys.cend()) == expected;
}

bool validAppId(const QString &appid)
{
    bool ok = false;
    const quint64 value = appid.toULongLong(&ok, 10);
    return ok && value <= 4294967295ULL && kAppId.match(appid).hasMatch();
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
                const char escaped = m_data[m_position++];
                if (escaped == 'u') {
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

QString safeErrorMessage(const QString &code)
{
    if (code == QStringLiteral("invalid_roots"))
        return SteamProviderController::tr("Informe de uma a oito raízes Steam absolutas e válidas.");
    if (code == QStringLiteral("helper_unavailable"))
        return SteamProviderController::tr("A leitura local da Steam não está disponível nesta instalação.");
    if (code == QStringLiteral("operation_timeout"))
        return SteamProviderController::tr("A leitura local da Steam excedeu o tempo permitido.");
    if (code == QStringLiteral("process_cleanup_failed"))
        return SteamProviderController::tr("A limpeza do processo local não pôde ser confirmada.");
    if (code == QStringLiteral("open_failed"))
        return SteamProviderController::tr("O desktop não aceitou o pedido de abertura.");
    return SteamProviderController::tr("A resposta local da Steam não pôde ser validada.");
}
}

SteamProviderController::SteamProviderController(const QString &pythonPath, const QString &helperPath,
                                                 UrlOpener opener, QObject *parent)
    : QObject(parent), m_pythonPath(pythonPath), m_helperPath(helperPath),
      m_opener(opener ? std::move(opener) : UrlOpener(QDesktopServices::openUrl))
{
    m_deadline.setSingleShot(true);
    m_killGrace.setSingleShot(true);
    m_groupPoll.setInterval(25);
    m_cleanupDeadline.setSingleShot(true);
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        const QByteArray available = m_process.readAllStandardOutput();
        if (m_stdout.size() + available.size() > kMaximumResultBytes) {
            m_outputOverflow = true;
            fail(QStringLiteral("invalid_helper_response"));
            beginCancellation();
            return;
        }
        m_stdout.append(available);
    });
    connect(&m_process, &QProcess::finished, this, &SteamProviderController::handleFinished);
    connect(&m_process, &QProcess::started, this, [this] {
        m_processGroup = m_process.processId();
        if (m_cancelled) beginCancellation();
    });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error != QProcess::FailedToStart) return;
        m_deadline.stop();
        if (m_processGeneration == m_inventoryRevision && !m_cancelled)
            fail(QStringLiteral("helper_unavailable"));
        if (!m_cleanupActive) m_cleanupActive = true;
        finishAfterCleanup(true);
    });
    connect(&m_deadline, &QTimer::timeout, this, [this] {
        if (!busy()) return;
        fail(QStringLiteral("operation_timeout"));
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
    connect(&m_groupPoll, &QTimer::timeout, this, &SteamProviderController::pollGroupCleanup);
    connect(&m_cleanupDeadline, &QTimer::timeout, this, [this] {
        finishAfterCleanup(!ownedGroupExists());
    });
}

SteamProviderController::~SteamProviderController()
{
    if (!busy()) return;
    m_closePending = false;
    cancelAll();
    if (m_process.state() != QProcess::NotRunning) m_process.waitForFinished(kCancellationGraceMs);
#ifdef Q_OS_UNIX
    if (ownedGroupExists()) killOwnedGroup(SIGKILL);
#endif
    if (m_process.state() != QProcess::NotRunning) {
        m_process.kill();
        m_process.waitForFinished(kCleanupVerificationMs);
    }
}

bool SteamProviderController::validateRoots(const QStringList &rootSpecs) const
{
    if (rootSpecs.isEmpty() || rootSpecs.size() > 8) return false;
    for (const QString &spec : rootSpecs) {
        if (spec.size() > 4110 || spec.contains(QChar::Null)) return false;
        for (const QChar character : spec) if (character.category() == QChar::Other_Control) return false;
        const qsizetype separator = spec.indexOf(QLatin1Char('='));
        const QString kind = spec.left(separator);
        const QString path = separator < 0 ? QString() : spec.mid(separator + 1);
        if ((kind != QStringLiteral("native") && kind != QStringLiteral("flatpak"))
            || !path.startsWith(QLatin1Char('/')) || path.size() > 4096) return false;
    }
    return true;
}

void SteamProviderController::scan(const QStringList &rootSpecs)
{
    if (busy()) return;
    ++m_inventoryRevision;
    m_apps.clear();
    m_issueCount = 0;
    m_errorCode.clear();
    m_error.clear();
    m_rootsCount = 0;
    if (!validateRoots(rootSpecs)) {
        m_status = QStringLiteral("error");
        fail(QStringLiteral("invalid_roots"));
        return;
    }
    const QFileInfo python(m_pythonPath);
    const QFileInfo helper(m_helperPath);
    if (!python.isAbsolute() || !python.isFile() || !python.isExecutable()
        || !helper.isAbsolute() || !helper.isFile() || !helper.isReadable()) {
        m_status = QStringLiteral("error");
        fail(QStringLiteral("helper_unavailable"));
        return;
    }
    m_rootsCount = rootSpecs.size();
    m_processGeneration = m_inventoryRevision;
    m_stdout.clear();
    m_outputOverflow = false;
    m_cancelled = false;
    m_operationActive = true;
    m_cleanupActive = false;
    m_killSent = false;
    m_pendingExitCode = -1;
    m_pendingExitStatus = QProcess::CrashExit;
    m_status = QStringLiteral("running");
    m_processGroup = 0;
    m_process.setProcessChannelMode(QProcess::SeparateChannels);
    m_process.setStandardInputFile(QProcess::nullDevice());
    m_process.setStandardErrorFile(QProcess::nullDevice());
    QProcessEnvironment environment;
    for (const QString &name : {QStringLiteral("LANG"), QStringLiteral("LC_ALL")}) {
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
    QStringList arguments = {QStringLiteral("-I"), QStringLiteral("-B"), m_helperPath,
                             QStringLiteral("scan")};
    for (const QString &root : rootSpecs) arguments << QStringLiteral("--root") << root;
    emit changed();
    m_process.start(m_pythonPath, arguments, QIODevice::ReadOnly);
    m_deadline.start(kOuterDeadlineMs);
}

void SteamProviderController::cancelAll()
{
    if (!busy()) return;
    ++m_inventoryRevision;
    m_apps.clear();
    m_issueCount = 0;
    m_cancelled = true;
    m_status = m_rootsCount > 0 ? QStringLiteral("idle") : QStringLiteral("unconfigured");
    beginCancellation();
    emit changed();
}

bool SteamProviderController::requestClose()
{
    if (!busy()) return true;
    m_closePending = true;
    cancelAll();
    return false;
}

bool SteamProviderController::openDownloads()
{
    if (busy()) return false;
    const bool opened = m_opener(QUrl(QStringLiteral("steam://open/downloads")));
    if (!opened) fail(QStringLiteral("open_failed"));
    return opened;
}

bool SteamProviderController::openGame(const QString &appid, const QString &libraryId,
                                       quint64 expectedInventoryRevision)
{
    if (expectedInventoryRevision != m_inventoryRevision || !validAppId(appid)
        || !kLibraryId.match(libraryId).hasMatch()) return false;
    bool current = false;
    for (const QVariant &entry : m_apps) {
        const QVariantMap app = entry.toMap();
        if (app.value(QStringLiteral("appid")).toString() == appid
            && app.value(QStringLiteral("library")).toString() == libraryId
            && app.value(QStringLiteral("status")).toString() == QStringLiteral("installed_candidate")) {
            current = true;
            break;
        }
    }
    if (!current) return false;
    const bool opened = m_opener(QUrl(QStringLiteral("steam://rungameid/%1").arg(appid)));
    if (!opened) fail(QStringLiteral("open_failed"));
    return opened;
}

void SteamProviderController::beginCancellation()
{
    if (!busy()) return;
    m_cleanupActive = true;
#ifdef Q_OS_UNIX
    killOwnedGroup(SIGTERM);
#else
    m_process.terminate();
#endif
    if (!m_groupPoll.isActive()) m_groupPoll.start();
    if (!m_killGrace.isActive() && !m_killSent) m_killGrace.start(kCancellationGraceMs);
}

void SteamProviderController::killOwnedGroup(int signalNumber)
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

bool SteamProviderController::ownedGroupExists() const
{
#ifdef Q_OS_UNIX
    if (m_processGroup <= 0) return false;
    errno = 0;
    return ::kill(-static_cast<pid_t>(m_processGroup), 0) == 0 || errno == EPERM;
#else
    return false;
#endif
}

void SteamProviderController::beginGroupCleanup()
{
    m_cleanupActive = true;
    if (!ownedGroupExists()) { finishAfterCleanup(true); return; }
#ifdef Q_OS_UNIX
    killOwnedGroup(SIGTERM);
#endif
    if (!m_groupPoll.isActive()) m_groupPoll.start();
    if (!m_killGrace.isActive() && !m_killSent) m_killGrace.start(kCancellationGraceMs);
}

void SteamProviderController::pollGroupCleanup()
{
    if (m_cleanupActive && m_process.state() == QProcess::NotRunning && !ownedGroupExists())
        finishAfterCleanup(true);
}

void SteamProviderController::finishAfterCleanup(bool cleanupConfirmed)
{
    if (!m_cleanupActive) return;
    m_killGrace.stop();
    m_cleanupDeadline.stop();
    if (!cleanupConfirmed) {
        // Keep custody of the process group and keep polling.  In particular,
        // requestClose() must not let the application disappear while an
        // owned descendant is still observable after the bounded TERM/KILL
        // sequence.
        fail(QStringLiteral("process_cleanup_failed"));
        if (!m_groupPoll.isActive()) m_groupPoll.start();
        return;
    }

    m_groupPoll.stop();
    m_operationActive = false;
    m_cleanupActive = false;
    m_processGroup = 0;
    const bool current = m_processGeneration == m_inventoryRevision;
    if (current && !m_cancelled && m_errorCode.isEmpty()) {
        QVariantList apps;
        QString status;
        int issueCount = 0;
        if (m_outputOverflow || m_pendingExitStatus != QProcess::NormalExit
            || !parseDocument(m_stdout, m_pendingExitCode, &apps, &status, &issueCount)) {
            fail(QStringLiteral("invalid_helper_response"));
        } else {
            m_apps = std::move(apps);
            m_status = status;
            m_issueCount = issueCount;
            emit changed();
        }
    }
    if (m_closePending) {
        m_closePending = false;
        emit closeReady();
    }
    emit changed();
}

void SteamProviderController::handleFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    m_deadline.stop();
    m_pendingExitCode = exitCode;
    m_pendingExitStatus = exitStatus;
    const QByteArray remaining = m_process.readAllStandardOutput();
    if (m_stdout.size() + remaining.size() > kMaximumResultBytes) m_outputOverflow = true;
    else m_stdout.append(remaining);
    m_process.readAllStandardError();
    beginGroupCleanup();
}

void SteamProviderController::fail(const QString &code)
{
    m_status = QStringLiteral("error");
    m_errorCode = code;
    m_error = safeErrorMessage(code);
    emit changed();
}

bool SteamProviderController::parseDocument(const QByteArray &bytes, int exitCode, QVariantList *apps,
                                            QString *status, int *issueCount) const
{
    if (bytes.isEmpty() || bytes.size() > kMaximumResultBytes || !bytes.endsWith('\n')) return false;
    for (const char byte : bytes) if (static_cast<unsigned char>(byte) > 0x7f) return false;
    const QByteArray body = bytes.first(bytes.size() - 1);
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(body, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()
        || !JsonKeyScanner(body).validWithoutDuplicates()) return false;
    const QJsonObject root = document.object();
    if (!exactKeys(root, {QStringLiteral("schema_version"), QStringLiteral("status"),
                         QStringLiteral("connection"), QStringLiteral("ownership"),
                         QStringLiteral("roots"), QStringLiteral("libraries"),
                         QStringLiteral("apps"), QStringLiteral("errors")})
        || root.value(QStringLiteral("schema_version")).toString() != QStringLiteral("0.1-experimental")
        || root.value(QStringLiteral("connection")).toString() != QStringLiteral("unknown")
        || root.value(QStringLiteral("ownership")).toString() != QStringLiteral("unknown")
        || !root.value(QStringLiteral("roots")).isArray()
        || !root.value(QStringLiteral("libraries")).isArray()
        || !root.value(QStringLiteral("apps")).isArray()
        || !root.value(QStringLiteral("errors")).isArray()) return false;
    const QString inventoryStatus = root.value(QStringLiteral("status")).toString();
    if (!kInventoryStatuses.contains(inventoryStatus)
        || (exitCode == 0 && inventoryStatus != QStringLiteral("available")
            && inventoryStatus != QStringLiteral("absent"))
        || (exitCode == 2 && inventoryStatus != QStringLiteral("partial")
            && inventoryStatus != QStringLiteral("unknown"))
        || (exitCode != 0 && exitCode != 2)) return false;

    const QJsonArray roots = root.value(QStringLiteral("roots")).toArray();
    const QJsonArray libraries = root.value(QStringLiteral("libraries")).toArray();
    const QJsonArray appArray = root.value(QStringLiteral("apps")).toArray();
    const QJsonArray errors = root.value(QStringLiteral("errors")).toArray();
    if (roots.isEmpty() || roots.size() != m_rootsCount || roots.size() > 8
        || libraries.size() > 32 || appArray.size() > 512 || errors.size() > 2048) return false;
    QSet<QString> rootIds;
    QHash<QString, QString> rootStatuses;
    QHash<QString, QString> rootKinds;
    for (const QJsonValue &value : roots) {
        if (!value.isObject()) return false;
        const QJsonObject item = value.toObject();
        if (!exactKeys(item, {QStringLiteral("id"), QStringLiteral("kind"), QStringLiteral("status")})) return false;
        const QString id = item.value(QStringLiteral("id")).toString();
        const QString kind = item.value(QStringLiteral("kind")).toString();
        const QString itemStatus = item.value(QStringLiteral("status")).toString();
        if (!kRootId.match(id).hasMatch() || rootIds.contains(id)
            || (kind != QStringLiteral("native") && kind != QStringLiteral("flatpak"))
            || !kRootStatuses.contains(itemStatus)) return false;
        rootIds.insert(id);
        rootStatuses.insert(id, itemStatus);
        rootKinds.insert(id, kind);
    }
    QSet<QString> libraryIds;
    QHash<QString, QString> libraryStatuses;
    QHash<QString, QString> firstLibraryStatuses;
    for (const QJsonValue &value : libraries) {
        if (!value.isObject()) return false;
        const QJsonObject item = value.toObject();
        if (!exactKeys(item, {QStringLiteral("id"), QStringLiteral("root"),
                              QStringLiteral("kind"), QStringLiteral("status")})) return false;
        const QString id = item.value(QStringLiteral("id")).toString();
        const QString rootId = item.value(QStringLiteral("root")).toString();
        const QString kind = item.value(QStringLiteral("kind")).toString();
        const QString libraryStatus = item.value(QStringLiteral("status")).toString();
        if (!kLibraryId.match(id).hasMatch() || libraryIds.contains(id) || !rootIds.contains(rootId)
            || (kind != QStringLiteral("native") && kind != QStringLiteral("flatpak"))
            || !kLibraryStatuses.contains(libraryStatus)
            || rootStatuses.value(rootId) == QStringLiteral("absent")
            || rootKinds.value(rootId) != kind) return false;
        libraryIds.insert(id);
        libraryStatuses.insert(id, libraryStatus);
        if (!firstLibraryStatuses.contains(rootId)) firstLibraryStatuses.insert(rootId, libraryStatus);
    }
    for (auto iterator = firstLibraryStatuses.cbegin(); iterator != firstLibraryStatuses.cend(); ++iterator)
        if (rootStatuses.value(iterator.key()) != iterator.value()) return false;
    QVariantList parsedApps;
    QSet<QString> appIdentities;
    for (const QJsonValue &value : appArray) {
        if (!value.isObject()) return false;
        const QJsonObject item = value.toObject();
        QSet<QString> keys = {QStringLiteral("appid"), QStringLiteral("name"),
            QStringLiteral("library"), QStringLiteral("status"), QStringLiteral("ownership"),
            QStringLiteral("source")};
        if (item.contains(QStringLiteral("name_redacted"))) keys.insert(QStringLiteral("name_redacted"));
        const QString appid = item.value(QStringLiteral("appid")).toString();
        const QString name = item.value(QStringLiteral("name")).toString();
        const QString library = item.value(QStringLiteral("library")).toString();
        const QString appStatus = item.value(QStringLiteral("status")).toString();
        bool unsafeName = name.trimmed().isEmpty();
        for (const QChar character : name) {
            const auto category = character.category();
            if (category == QChar::Other_Control || category == QChar::Other_Format
                || category == QChar::Other_Surrogate || category == QChar::Other_PrivateUse
                || category == QChar::Other_NotAssigned) unsafeName = true;
        }
        const QString identity = appid + QLatin1Char(':') + library;
        if (!exactKeys(item, keys) || !validAppId(appid) || unsafeName || name.size() > 160
            || !libraryIds.contains(library) || !kAppStatuses.contains(appStatus)
            || (libraryStatuses.value(library) != QStringLiteral("available")
                && libraryStatuses.value(library) != QStringLiteral("partial"))
            || ((appStatus == QStringLiteral("partial") || appStatus == QStringLiteral("unknown"))
                && libraryStatuses.value(library) != QStringLiteral("partial"))
            || appIdentities.contains(identity)
            || item.value(QStringLiteral("ownership")).toString() != QStringLiteral("unknown")
            || item.value(QStringLiteral("source")).toString() != QStringLiteral("local_manifest")
            || (item.contains(QStringLiteral("name_redacted"))
                && (!item.value(QStringLiteral("name_redacted")).isBool()
                    || !item.value(QStringLiteral("name_redacted")).toBool()))) return false;
        appIdentities.insert(identity);
        parsedApps.append(item.toVariantMap());
    }
    for (const QJsonValue &value : errors) {
        if (!value.isObject()) return false;
        const QJsonObject item = value.toObject();
        QSet<QString> keys = {QStringLiteral("code")};
        for (const QString &optional : {QStringLiteral("root"), QStringLiteral("library"),
                                        QStringLiteral("appid")})
            if (item.contains(optional)) keys.insert(optional);
        if (!exactKeys(item, keys) || !kIssueCodes.contains(item.value(QStringLiteral("code")).toString())) return false;
        if (item.contains(QStringLiteral("root")) && !rootIds.contains(item.value(QStringLiteral("root")).toString())) return false;
        if (item.contains(QStringLiteral("library")) && !libraryIds.contains(item.value(QStringLiteral("library")).toString())) return false;
        if (item.contains(QStringLiteral("appid"))
            && !validAppId(item.value(QStringLiteral("appid")).toString())) return false;
    }
    if ((inventoryStatus == QStringLiteral("available") || inventoryStatus == QStringLiteral("absent"))
        && !errors.isEmpty()) return false;
    if ((inventoryStatus == QStringLiteral("partial") || inventoryStatus == QStringLiteral("unknown"))
        && errors.isEmpty()) return false;
    if ((inventoryStatus == QStringLiteral("absent") || inventoryStatus == QStringLiteral("unknown"))
        && !appArray.isEmpty()) return false;
    const auto anyRootStatus = [&rootStatuses](const QSet<QString> &statuses) {
        for (const QString &value : rootStatuses) if (statuses.contains(value)) return true;
        return false;
    };
    const auto anyLibraryStatus = [&libraryStatuses](const QSet<QString> &statuses) {
        for (const QString &value : libraryStatuses) if (statuses.contains(value)) return true;
        return false;
    };
    if (inventoryStatus == QStringLiteral("available")) {
        if (!anyRootStatus({QStringLiteral("available")})
            || !anyLibraryStatus({QStringLiteral("available")})
            || anyRootStatus({QStringLiteral("missing"), QStringLiteral("partial"), QStringLiteral("unknown")})
            || anyLibraryStatus({QStringLiteral("missing"), QStringLiteral("partial"), QStringLiteral("unknown")}))
            return false;
        for (const QJsonValue &value : appArray)
            if (value.toObject().value(QStringLiteral("status")).toString()
                != QStringLiteral("installed_candidate")) return false;
    } else if (inventoryStatus == QStringLiteral("absent")) {
        if (!libraries.isEmpty() || !appArray.isEmpty()) return false;
        for (const QString &value : rootStatuses) if (value != QStringLiteral("absent")) return false;
    } else if (inventoryStatus == QStringLiteral("partial")) {
        if (!anyLibraryStatus({QStringLiteral("available"), QStringLiteral("partial")})) return false;
    } else if (anyRootStatus({QStringLiteral("available"), QStringLiteral("partial")})
               || anyLibraryStatus({QStringLiteral("available"), QStringLiteral("partial")})) {
        return false;
    }
    *apps = std::move(parsedApps);
    *status = inventoryStatus;
    *issueCount = errors.size();
    return true;
}
