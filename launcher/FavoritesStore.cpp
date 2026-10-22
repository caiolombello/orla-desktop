#include "FavoritesStore.h"
#include "AliasStore.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QStandardPaths>
#include <QUuid>
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr int maxBytes = 16384;
QString message(const char *text) { return QCoreApplication::translate("FavoritesStore", text); }
struct Fd {
    explicit Fd(int value) : value(value) {}
    ~Fd() { if (value >= 0) ::close(value); }
    const int value;
};
bool sameParent(int directory, const QByteArray &path)
{
    const Fd current(::open(path.constData(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    struct stat owned{}, live{};
    return current.value >= 0 && ::fstat(directory, &owned) == 0 && ::fstat(current.value, &live) == 0
        && owned.st_dev == live.st_dev && owned.st_ino == live.st_ino;
}
struct Lock {
    Lock(int directory, const QByteArray &parent, const QByteArray &name)
        : directory(directory), parent(parent), name(name), descriptor(::openat(directory, name.constData(),
              O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, S_IRUSR | S_IWUSR))
    {
        ready = descriptor.value >= 0 && ::fchmod(descriptor.value, S_IRUSR | S_IWUSR) == 0
            && ::fstat(descriptor.value, &identity) == 0;
    }
    ~Lock() { if (ownsPath()) ::unlinkat(directory, name.constData(), 0); }
    bool ownsPath() const
    {
        struct stat current{}, opened{};
        return ready && sameParent(directory, parent) && ::fstat(descriptor.value, &opened) == 0
            && ::fstatat(directory, name.constData(), &current, AT_SYMLINK_NOFOLLOW) == 0
            && S_ISREG(current.st_mode) && S_ISREG(opened.st_mode)
            && opened.st_dev == identity.st_dev && opened.st_ino == identity.st_ino
            && current.st_dev == identity.st_dev && current.st_ino == identity.st_ino
            && current.st_uid == ::geteuid() && opened.st_uid == ::geteuid()
            && current.st_nlink == 1 && opened.st_nlink == 1
            && (current.st_mode & 0777) == 0600 && (opened.st_mode & 0777) == 0600;
    }
    const int directory;
    const QByteArray parent, name;
    const Fd descriptor;
    struct stat identity{};
    bool ready = false;
};
struct Snapshot {
    QStringList entries;
    QString revision = QStringLiteral("missing");
    QString error;
};
QString bytesRevision(const QByteArray &bytes)
{
    return QStringLiteral("file:") + QString::fromLatin1(QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}
Snapshot readAt(int directory, const QByteArray &name)
{
    Snapshot result;
    const int descriptor = ::openat(directory, name.constData(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (descriptor < 0) {
        if (errno != ENOENT) result.error = message("Não foi possível ler os favoritos com segurança.");
        return result;
    }
    struct stat stat{};
    if (::fstat(descriptor, &stat) != 0 || !S_ISREG(stat.st_mode) || stat.st_uid != ::geteuid()
        || stat.st_nlink != 1 || stat.st_size > maxBytes) {
        ::close(descriptor);
        result.error = message("O arquivo de favoritos não é próprio ou válido, ou excede 16 KiB.");
        return result;
    }
    QFile file;
    if (!file.open(descriptor, QIODevice::ReadOnly, QFileDevice::AutoCloseHandle)) {
        ::close(descriptor);
        result.error = message("Não foi possível ler os favoritos.");
        return result;
    }
    const QByteArray bytes = file.read(maxBytes + 1);
    result.revision = bytesRevision(bytes);
    const auto document = QJsonDocument::fromJson(bytes);
    const auto object = document.object();
    if (bytes.size() > maxBytes || file.error() != QFileDevice::NoError || !document.isObject()
        || object.keys() != QStringList{QStringLiteral("favorites"), QStringLiteral("formatVersion")}
        || object.value("formatVersion") != QStringLiteral("0.1-experimental") || !object.value("favorites").isArray()) {
        result.error = message("As preferências de favoritos são inválidas ou incompatíveis.");
        return result;
    }
    const auto entries = object.value("favorites").toArray();
    if (entries.size() > 16) result.error = message("Use até 16 favoritos.");
    for (const auto &entry : entries) {
        const QString appId = entry.toString();
        if (!entry.isString() || !AliasStore::validAppId(appId) || result.entries.contains(appId, Qt::CaseSensitive)) {
            result.error = message("As preferências de favoritos são inválidas ou incompatíveis.");
            break;
        }
        result.entries.append(appId);
    }
    if (!result.error.isEmpty()) result.entries.clear();
    return result;
}
}

FavoritesStore::FavoritesStore(const QString &path)
    : m_path(path.isEmpty() ? QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation)
               + QStringLiteral("/orla/launcher-favorites.json") : path)
{
    reload();
}

bool FavoritesStore::reload()
{
    const QFileInfo path(m_path);
    const Fd directory(::open(QFile::encodeName(path.absolutePath()).constData(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    Snapshot snapshot;
    if (directory.value < 0) {
        if (errno != ENOENT) snapshot.error = message("Não foi possível acessar a pasta de favoritos com segurança.");
    } else snapshot = readAt(directory.value, QFile::encodeName(path.fileName()));
    const bool changed = snapshot.revision != m_revision || snapshot.error != m_readError || snapshot.entries != m_entries;
    m_entries = snapshot.entries;
    m_revision = snapshot.revision;
    m_readError = snapshot.error;
    if (changed) m_commandError.clear();
    return changed;
}

bool FavoritesStore::fail(const QString &text) { m_commandError = text; return false; }

bool FavoritesStore::pin(const QString &appId, const QString &expectedRevision)
{
    reload();
    if (!writable() || expectedRevision != m_revision) return fail(message("Os favoritos mudaram. Abra novamente antes de salvar."));
    if (!AliasStore::validAppId(appId)) return fail(message("Escolha um aplicativo válido para os favoritos."));
    QStringList next = m_entries;
    if (!next.contains(appId, Qt::CaseSensitive)) {
        if (next.size() >= 16) return fail(message("Use até 16 favoritos."));
        next.append(appId);
    }
    return publish(next, expectedRevision);
}

bool FavoritesStore::unpin(const QString &appId, const QString &expectedRevision)
{
    reload();
    if (!writable() || expectedRevision != m_revision) return fail(message("Os favoritos mudaram. Abra novamente antes de remover."));
    if (!AliasStore::validAppId(appId) || !m_entries.contains(appId, Qt::CaseSensitive))
        return fail(message("O favorito mudou. Abra novamente antes de remover."));
    QStringList next = m_entries;
    next.removeAll(appId);
    return publish(next, expectedRevision);
}

bool FavoritesStore::publish(const QStringList &entries, const QString &expectedRevision)
{
    if (!writable() || expectedRevision != m_revision) return fail(message("Os favoritos mudaram. Abra novamente antes de salvar."));
    const QFileInfo path(m_path);
    const QByteArray parent = QFile::encodeName(path.absolutePath()), name = QFile::encodeName(path.fileName());
    if (!QDir().mkpath(path.absolutePath())) return fail(message("Não foi possível criar a pasta de favoritos."));
    const Fd directory(::open(parent.constData(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
    if (directory.value < 0) return fail(message("Não foi possível acessar a pasta de favoritos com segurança."));
    // Existing locks are preserved, even after a crash. No stale takeover.
    const Lock lock(directory.value, parent, name + ".lock");
    if (!lock.ready || !lock.ownsPath()) return fail(message("Os favoritos estão bloqueados. Verifique o arquivo de lock antes de tentar novamente."));
    const auto current = readAt(directory.value, name);
    if (!current.error.isEmpty() || current.revision != expectedRevision) {
        reload();
        return fail(message("Os favoritos mudaram. Abra novamente antes de salvar."));
    }
    if (entries == current.entries) { m_commandError.clear(); return true; }
    QJsonArray values;
    for (const auto &id : entries) values.append(id);
    const QByteArray bytes = QJsonDocument(QJsonObject{{"formatVersion", QStringLiteral("0.1-experimental")}, {"favorites", values}}).toJson(QJsonDocument::Compact);
    if (bytes.size() > maxBytes) return fail(message("Os favoritos excedem 16 KiB."));
    const QByteArray staging = QByteArray(".favorites-") + QUuid::createUuid().toByteArray(QUuid::WithoutBraces);
    const Fd reservation(::openat(directory.value, staging.constData(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, S_IRUSR | S_IWUSR));
    if (reservation.value < 0) return fail(message("Não foi possível preparar os favoritos para salvar."));
    const QString anchor = QStringLiteral("/proc/self/fd/%1/").arg(directory.value);
    QSaveFile file(anchor + QString::fromLatin1(staging));
    file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner)
        || file.write(bytes) != bytes.size() || !file.commit()) {
        file.cancelWriting();
        ::unlinkat(directory.value, staging.constData(), 0);
        return fail(message("Não foi possível salvar os favoritos. As preferências anteriores foram preservadas."));
    }
    // QSaveFile commits only our exclusive staging file. The target rename is
    // anchored; cooperative locking does not promise CAS against other writers.
    const auto beforePublish = readAt(directory.value, name);
    if (!sameParent(directory.value, parent) || !lock.ownsPath() || !beforePublish.error.isEmpty()
        || beforePublish.revision != expectedRevision
        || ::renameat(directory.value, staging.constData(), directory.value, name.constData()) != 0) {
        ::unlinkat(directory.value, staging.constData(), 0);
        reload();
        return fail(message("Não foi possível publicar os favoritos. Abra novamente antes de salvar."));
    }
    m_entries = entries;
    m_revision = bytesRevision(bytes);
    m_readError.clear();
    m_commandError.clear();
    return true;
}
