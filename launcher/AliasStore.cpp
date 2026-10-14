#include "AliasStore.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLockFile>
#include <QRegularExpression>
#include <QSaveFile>
#include <QStandardPaths>
#include <QUuid>
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr int maxBytes = 16384;
QString message(const char *text) { return QCoreApplication::translate("AliasStore", text); }
struct Fd {
    explicit Fd(int value) : value(value) {}
    ~Fd() { if (value >= 0) ::close(value); }
    const int value;
};
struct Snapshot {
    QVariantList entries;
    QString revision = QStringLiteral("missing");
    QString error;
};
QString bytesRevision(const QByteArray &bytes)
{
    return QStringLiteral("file:") + QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}
bool validAlias(const QString &alias)
{
    if (alias.isEmpty() || alias != alias.trimmed().normalized(QString::NormalizationForm_C) || alias.toUcs4().size() > 32) return false;
    if (QString::fromUtf8(alias.toUtf8()) != alias) return false;
    for (char32_t c : alias.toUcs4()) if (!QChar::isPrint(c)) return false;
    return true;
}
Snapshot readAt(int directory, const QByteArray &name)
{
    Snapshot result;
    const int descriptor = ::openat(directory, name.constData(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (descriptor < 0) {
        if (errno != ENOENT) result.error = message("Não foi possível ler os aliases com segurança.");
        return result;
    }
    struct stat stat{};
    if (::fstat(descriptor, &stat) != 0 || !S_ISREG(stat.st_mode) || stat.st_size > maxBytes) {
        ::close(descriptor);
        result.error = message("O arquivo de aliases não é válido ou excede 16 KiB.");
        return result;
    }
    QFile file;
    if (!file.open(descriptor, QIODevice::ReadOnly, QFileDevice::AutoCloseHandle)) {
        ::close(descriptor);
        result.error = message("Não foi possível ler os aliases.");
        return result;
    }
    const QByteArray bytes = file.read(maxBytes + 1);
    result.revision = bytesRevision(bytes);
    const auto document = QJsonDocument::fromJson(bytes);
    const auto object = document.object();
    if (bytes.size() > maxBytes || file.error() != QFileDevice::NoError || !document.isObject()
        || object.keys() != QStringList{QStringLiteral("aliases"), QStringLiteral("formatVersion")}
        || object.value("formatVersion") != QStringLiteral("0.1-experimental") || !object.value("aliases").isArray()) {
        result.error = message("As preferências de aliases são inválidas ou incompatíveis.");
        return result;
    }
    const auto entries = object.value("aliases").toArray();
    QStringList keys;
    if (entries.size() > 16) result.error = message("Use até 16 aliases.");
    for (const auto &entry : entries) {
        const auto item = entry.toObject();
        const QString alias = item.value("alias").toString(), appId = item.value("appId").toString();
        if (!entry.isObject() || item.keys() != QStringList{QStringLiteral("alias"), QStringLiteral("appId")}
            || !item.value("alias").isString() || !item.value("appId").isString()
            || !validAlias(alias) || !AliasStore::validAppId(appId) || keys.contains(AliasStore::key(alias))) {
            result.error = message("As preferências de aliases são inválidas ou incompatíveis.");
            break;
        }
        keys.append(AliasStore::key(alias));
        result.entries.append(QVariantMap{{"alias", alias}, {"appId", appId}});
    }
    if (!result.error.isEmpty()) result.entries.clear();
    return result;
}
}

AliasStore::AliasStore(const QString &path)
    : m_path(path.isEmpty() ? QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation)
               + QStringLiteral("/orla/launcher-aliases.json") : path)
{
    reload();
}

QString AliasStore::key(const QString &alias)
{
    return alias.trimmed().normalized(QString::NormalizationForm_C).toCaseFolded();
}

bool AliasStore::validAppId(const QString &appId)
{
    static const QRegularExpression allowed(QStringLiteral("^[A-Za-z0-9][A-Za-z0-9_.-]*\\.desktop$"));
    return appId.size() <= 128 && allowed.match(appId).hasMatch();
}

bool AliasStore::reload()
{
    const QFileInfo path(m_path);
    const Fd directory(::open(QFile::encodeName(path.absolutePath()).constData(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    Snapshot snapshot;
    if (directory.value < 0) {
        if (errno != ENOENT) snapshot.error = message("Não foi possível acessar a pasta de aliases com segurança.");
    } else snapshot = readAt(directory.value, QFile::encodeName(path.fileName()));
    const bool changed = snapshot.revision != m_revision || snapshot.error != m_readError || snapshot.entries != m_entries;
    m_entries = snapshot.entries;
    m_revision = snapshot.revision;
    m_readError = snapshot.error;
    if (changed) m_commandError.clear();
    return changed;
}

bool AliasStore::fail(const QString &text) { m_commandError = text; return false; }

bool AliasStore::save(const QString &rawAlias, const QString &appId, const QString &expectedRevision)
{
    const QString alias = rawAlias.trimmed().normalized(QString::NormalizationForm_C);
    if (!validAlias(alias) || !validAppId(appId)) return fail(message("Escolha um alias de 1 a 32 caracteres e um aplicativo instalado válido."));
    QVariantList next = m_entries;
    bool found = false;
    for (QVariant &entry : next) {
        auto item = entry.toMap();
        if (key(item.value("alias").toString()) != key(alias)) continue;
        if (item.value("appId").toString() != appId) return fail(message("Esse alias já pertence a outro aplicativo."));
        entry = QVariantMap{{"alias", alias}, {"appId", appId}};
        found = true;
    }
    if (!found) {
        if (next.size() >= 16) return fail(message("Use até 16 aliases."));
        next.append(QVariantMap{{"alias", alias}, {"appId", appId}});
    }
    return publish(next, expectedRevision);
}

bool AliasStore::rename(const QString &oldAlias, const QString &appId, const QString &rawAlias, const QString &expectedRevision)
{
    const QString alias = rawAlias.trimmed().normalized(QString::NormalizationForm_C);
    if (!validAlias(alias) || !validAppId(appId)) return fail(message("Escolha um alias de 1 a 32 caracteres e um aplicativo válido."));
    QVariantList next = m_entries;
    int target = -1;
    for (int row = 0; row < next.size(); ++row) {
        const auto item = next[row].toMap();
        const QString existing = key(item.value("alias").toString());
        if (existing == key(oldAlias) && item.value("appId").toString() == appId) target = row;
        else if (existing == key(alias)) return fail(message("Esse alias já está em uso."));
    }
    if (target < 0) return fail(message("O alias mudou. Abra novamente antes de editar."));
    next[target] = QVariantMap{{"alias", alias}, {"appId", appId}};
    return publish(next, expectedRevision);
}

bool AliasStore::remove(const QString &alias, const QString &appId, const QString &expectedRevision)
{
    QVariantList next;
    bool found = false;
    for (const auto &entry : m_entries) {
        const auto item = entry.toMap();
        if (key(item.value("alias").toString()) == key(alias) && item.value("appId").toString() == appId) found = true;
        else next.append(entry);
    }
    if (!found) return fail(message("O alias mudou. Abra novamente antes de remover."));
    return publish(next, expectedRevision);
}

bool AliasStore::publish(const QVariantList &entries, const QString &expectedRevision)
{
    if (!writable() || expectedRevision != m_revision) return fail(message("Os aliases mudaram. Abra novamente antes de salvar."));
    const QFileInfo path(m_path);
    if (!QDir().mkpath(path.absolutePath())) return fail(message("Não foi possível criar a pasta de aliases."));
    const Fd directory(::open(QFile::encodeName(path.absolutePath()).constData(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    if (directory.value < 0) return fail(message("Não foi possível acessar a pasta de aliases com segurança."));
    const QString anchor = QStringLiteral("/proc/self/fd/%1/").arg(directory.value);
    QLockFile lock(anchor + path.fileName() + QStringLiteral(".lock"));
    lock.setStaleLockTime(0);
    if (!lock.tryLock(0)) return fail(message("Outro processo está alterando os aliases. Tente novamente."));
    const QByteArray name = QFile::encodeName(path.fileName());
    const auto current = readAt(directory.value, name);
    if (!current.error.isEmpty() || current.revision != expectedRevision) {
        reload();
        return fail(message("Os aliases mudaram. Abra novamente antes de salvar."));
    }
    const QByteArray bytes = QJsonDocument(QJsonObject{{"formatVersion", QStringLiteral("0.1-experimental")},
        {"aliases", QJsonArray::fromVariantList(entries)}}).toJson(QJsonDocument::Compact);
    if (bytes.size() > maxBytes) return fail(message("Os aliases excedem 16 KiB."));
    if (entries == current.entries) { m_commandError.clear(); return true; }
    const QByteArray staging = QByteArray(".aliases-") + QUuid::createUuid().toByteArray(QUuid::WithoutBraces);
    QSaveFile file(anchor + QString::fromLatin1(staging));
    file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly)) return fail(message("Não foi possível salvar os aliases."));
    if (!file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner) || file.write(bytes) != bytes.size() || !file.commit()) {
        file.cancelWriting();
        ::unlinkat(directory.value, staging.constData(), 0);
        return fail(message("Não foi possível salvar os aliases. As preferências anteriores foram preservadas."));
    }
    // QSaveFile follows a target symlink. It writes only our unique staging file;
    // the final rename is anchored to the opened parent and never follows a link.
    const auto beforePublish = readAt(directory.value, name);
    const Fd liveDirectory(::open(QFile::encodeName(path.absolutePath()).constData(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    struct stat owned{}, live{};
    const bool sameParent = liveDirectory.value >= 0 && ::fstat(directory.value, &owned) == 0
        && ::fstat(liveDirectory.value, &live) == 0 && owned.st_dev == live.st_dev && owned.st_ino == live.st_ino;
    if (!sameParent || !beforePublish.error.isEmpty() || beforePublish.revision != expectedRevision
        || ::renameat(directory.value, staging.constData(), directory.value, name.constData()) != 0) {
        ::unlinkat(directory.value, staging.constData(), 0);
        reload();
        return fail(message("Não foi possível publicar os aliases. Abra novamente antes de salvar."));
    }
    m_entries = entries;
    m_revision = bytesRevision(bytes);
    m_readError.clear();
    m_commandError.clear();
    return true;
}
