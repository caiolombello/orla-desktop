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
#include <QTemporaryDir>
#include <QtTest>
#include <cerrno>
#include <cstdarg>
#include <fcntl.h>
#include <functional>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>

namespace {
const QString appA = QStringLiteral("org.orla.FavoriteFixtureA.desktop");
const QString appB = QStringLiteral("org.orla.FavoriteFixtureB.desktop");
const QString appC = QStringLiteral("org.orla.FavoriteFixtureC.desktop");
QByteArray bytes(const QString &path)
{
    QFile file(path);
    return file.open(QIODevice::ReadOnly) ? file.readAll() : QByteArray();
}
bool write(const QString &path, const QByteArray &data, mode_t mode = 0600)
{
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate) || file.write(data) != data.size()) return false;
    file.close();
    return ::chmod(QFile::encodeName(path).constData(), mode) == 0;
}
QByteArray document(const QStringList &ids)
{
    QJsonArray values;
    for (const auto &id : ids) values.append(id);
    return QJsonDocument(QJsonObject{{"formatVersion", "0.1-experimental"}, {"favorites", values}}).toJson(QJsonDocument::Compact);
}
mode_t mode(const QString &path)
{
    struct stat value{};
    return ::lstat(QFile::encodeName(path).constData(), &value) == 0 ? value.st_mode & 0777 : 0;
}
struct AliasGuard {
    QString path;
    QByteArray original;
    QString revision;
    mode_t permissions = 0;
    explicit AliasGuard(const QString &path) : path(path)
    {
        original = bytes(path); permissions = mode(path); revision = AliasStore(path).revision();
    }
    bool intact() const
    {
        return bytes(path) == original && mode(path) == permissions && AliasStore(path).revision() == revision;
    }
};
const QByteArray aliasFixture = R"({"formatVersion":"0.1-experimental","aliases":[{"alias":"editor","appId":"org.orla.FavoriteFixtureA.desktop"}]})";
struct Boundary {
    QString parent;
    std::function<void()> beforePublish;
    bool injected = false, failStaging = false, failRename = false;
} boundary;
struct ResetBoundary { ~ResetBoundary() { boundary = {}; } };
}

// Only the static store object's POSIX references are wrapped; no processes,
// timers, private store methods or production test hooks are involved.
extern "C" int __real_fstat(int, struct stat *);
extern "C" int __wrap_fstat(int fd, struct stat *value)
{
    if (boundary.beforePublish && !QDir(boundary.parent).entryList({".favorites-*"}, QDir::Files | QDir::Hidden).isEmpty()) {
        auto action = std::exchange(boundary.beforePublish, {});
        boundary.injected = true;
        action();
    }
    return __real_fstat(fd, value);
}
extern "C" int __real_openat(int, const char *, int, ...);
extern "C" int __wrap_openat(int directory, const char *name, int flags, ...)
{
    mode_t permissions = 0;
    if (flags & O_CREAT) {
        va_list args; va_start(args, flags); permissions = va_arg(args, int); va_end(args);
    }
    if (boundary.failStaging && QByteArray(name).startsWith(".favorites-") && (flags & O_EXCL)) {
        boundary.failStaging = false; errno = EACCES; return -1;
    }
    return flags & O_CREAT ? __real_openat(directory, name, flags, permissions) : __real_openat(directory, name, flags);
}
extern "C" int __real_renameat(int, const char *, int, const char *);
extern "C" int __wrap_renameat(int oldDirectory, const char *oldName, int newDirectory, const char *newName)
{
    if (boundary.failRename && QByteArray(oldName).startsWith(".favorites-")) {
        boundary.failRename = false; errno = EIO; return -1;
    }
    return __real_renameat(oldDirectory, oldName, newDirectory, newName);
}

class FavoritesStoreTests final : public QObject
{
    Q_OBJECT
private slots:
    void cleanup() { boundary = {}; }
    void missingReadsAndInvalidCommandsNeverCreatePreferences()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString path = root.filePath("missing/favorites.json");
        FavoritesStore store(path);
        QCOMPARE(store.revision(), QStringLiteral("missing"));
        QVERIFY(store.writable()); QVERIFY(store.error().isEmpty());
        for (int n = 0; n < 100; ++n) {
            QVERIFY(store.entries().isEmpty()); QVERIFY(!store.reload());
        }
        QVERIFY(!store.pin("../unsafe.desktop", store.revision()));
        QVERIFY(!store.unpin(appA, store.revision()));
        QVERIFY(!QFile::exists(root.filePath("missing")));
    }
    void defaultPathDoesNotReuseOrRewriteAliases()
    {
        QTemporaryDir root;
        const QByteArray original = qgetenv("XDG_CONFIG_HOME");
        const bool wasSet = qEnvironmentVariableIsSet("XDG_CONFIG_HOME");
        struct Restore { QByteArray value; bool set; ~Restore() { if (set) qputenv("XDG_CONFIG_HOME", value); else qunsetenv("XDG_CONFIG_HOME"); } } restore{original, wasSet};
        qputenv("XDG_CONFIG_HOME", root.path().toUtf8());
        QVERIFY(QDir().mkdir(root.filePath("orla")));
        const QString alias = root.filePath("orla/launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store;
        QVERIFY(store.entries().isEmpty()); QVERIFY(store.pin(appA, store.revision()));
        QCOMPARE(bytes(root.filePath("orla/launcher-favorites.json")), document({appA}));
        QCOMPARE(mode(root.filePath("orla/launcher-favorites.json")), mode_t(0600));
        QVERIFY(guard.intact());
    }
    void pinPersistsOnlyOrderedExactIdsAndLastUnpinPublishesEmpty()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path);
        QVERIFY(store.pin(appA, "missing")); QVERIFY(store.pin(appB, store.revision()));
        const QString lower = QStringLiteral("org.orla.favoritefixturea.desktop");
        QVERIFY(store.pin(lower, store.revision()));
        QCOMPARE(store.entries(), QStringList({appA, appB, lower}));
        QCOMPARE(bytes(path), document({appA, appB, lower}));
        QCOMPARE(mode(path), mode_t(0600)); QVERIFY(guard.intact());
        FavoritesStore restart(path); QCOMPARE(restart.entries(), store.entries());
        QVERIFY(restart.unpin(appB, restart.revision()));
        QVERIFY(restart.unpin(appA, restart.revision()));
        QVERIFY(restart.unpin(lower, restart.revision()));
        QVERIFY(QFile::exists(path)); QCOMPARE(bytes(path), document({}));
        QVERIFY(!restart.unpin(lower, restart.revision())); QVERIFY(guard.intact());
    }
    void duplicateAtCapacityChecksLiveRevisionWithoutRewriting()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path);
        for (int n = 0; n < 16; ++n) QVERIFY(store.pin(QStringLiteral("org.orla.App%1.desktop").arg(n), store.revision()));
        const auto full = bytes(path); const auto revision = store.revision();
        struct stat before{}, after{}; QVERIFY(::lstat(QFile::encodeName(path).constData(), &before) == 0);
        QVERIFY(store.pin("org.orla.App0.desktop", revision));
        QVERIFY(::lstat(QFile::encodeName(path).constData(), &after) == 0);
        QCOMPARE(bytes(path), full); QCOMPARE(store.revision(), revision);
        QCOMPARE(after.st_ino, before.st_ino); QCOMPARE(after.st_mtim.tv_sec, before.st_mtim.tv_sec); QCOMPARE(after.st_mtim.tv_nsec, before.st_mtim.tv_nsec);
        QVERIFY(!store.pin("org.orla.App16.desktop", revision));
        QVERIFY(store.writable()); QVERIFY(!store.error().isEmpty()); QCOMPARE(bytes(path), full);
        QVERIFY(store.unpin("org.orla.App0.desktop", revision));
        QVERIFY(store.pin("org.orla.App16.desktop", store.revision()));
        QCOMPARE(store.entries().size(), 16); QVERIFY(guard.intact());
    }
    void exactByteLimitReadsAndDuplicateKeepsExternalFormatting()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        QByteArray input = document({appA}); input.append(QByteArray(16384 - input.size(), ' '));
        QVERIFY(write(path, input, 0640)); FavoritesStore store(path);
        QVERIFY(store.writable()); QCOMPARE(store.entries(), QStringList({appA}));
        QVERIFY(store.pin(appA, store.revision())); QCOMPARE(bytes(path), input); QCOMPARE(mode(path), mode_t(0640));
        QVERIFY(store.pin(appB, store.revision())); QCOMPARE(bytes(path), document({appA, appB}));
        QCOMPARE(mode(path), mode_t(0600)); QVERIFY(guard.intact());
    }
    void hardLinkedFavoritesArePreservedReadOnly()
    {
        QTemporaryDir root;
        const QString original = root.filePath("original.json"), path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        QVERIFY(write(original, document({appA}), 0640));
        QVERIFY(::link(QFile::encodeName(original).constData(), QFile::encodeName(path).constData()) == 0);
        FavoritesStore store(path); QVERIFY(!store.writable());
        QVERIFY(!store.pin(appB, store.revision())); QCOMPARE(bytes(original), document({appA}));
        QCOMPARE(bytes(path), document({appA})); QCOMPARE(mode(path), mode_t(0640)); QVERIFY(guard.intact());
    }
    void externalRevisionIsAdoptedBeforeDuplicateAndRemoval()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision()));
        const auto stale = store.revision();
        FavoritesStore other(path); QVERIFY(other.pin(appB, other.revision()));
        const auto external = bytes(path);
        QVERIFY(!store.pin(appA, stale)); QCOMPARE(store.entries(), QStringList({appA, appB}));
        QCOMPARE(store.revision(), other.revision()); QCOMPARE(bytes(path), external);
        QVERIFY(!store.unpin(appA, stale)); QCOMPARE(bytes(path), external);
        QVERIFY(store.pin(appA, store.revision())); QVERIFY(store.error().isEmpty());
        QVERIFY(!store.unpin(appC, store.revision())); QCOMPARE(bytes(path), external);
        QVERIFY(store.writable()); QVERIFY(guard.intact());
    }
    void invalidDataIsPreserved_data()
    {
        QTest::addColumn<QByteArray>("input");
        QTest::newRow("malformed") << QByteArray("{");
        QTest::newRow("wrong-object") << QByteArray("[]");
        QTest::newRow("future") << QByteArray(R"({"formatVersion":"0.2","favorites":[]})");
        QTest::newRow("extra-field") << QByteArray(R"({"formatVersion":"0.1-experimental","favorites":[],"query":"never"})");
        QTest::newRow("non-array") << QByteArray(R"({"formatVersion":"0.1-experimental","favorites":{}})");
        QTest::newRow("non-string") << QByteArray(R"({"formatVersion":"0.1-experimental","favorites":[3]})");
        QTest::newRow("duplicate") << document({appA, appA});
        QTest::newRow("unsafe-id") << document({"../unsafe.desktop"});
        QStringList excess; for (int n = 0; n < 17; ++n) excess.append(QStringLiteral("org.orla.App%1.desktop").arg(n));
        QTest::newRow("17-entries") << document(excess);
        QTest::newRow("oversized") << QByteArray(16385, 'x');
        QTest::newRow("alias-schema") << aliasFixture;
    }
    void invalidDataIsPreserved()
    {
        QFETCH(QByteArray, input); QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        QVERIFY(write(path, input, 0640)); FavoritesStore store(path);
        QVERIFY(!store.writable()); QVERIFY(!store.error().isEmpty()); QVERIFY(store.entries().isEmpty());
        const auto revision = store.revision();
        QVERIFY(!store.pin(appA, revision)); QVERIFY(!store.unpin(appA, revision));
        QCOMPARE(bytes(path), input); QCOMPARE(mode(path), mode_t(0640));
        QVERIFY(QDir(root.path()).entryList({".favorites-*", "*.lock"}, QDir::AllEntries | QDir::Hidden | QDir::NoDotAndDotDot).isEmpty());
        QVERIFY(guard.intact());
    }
    void corruptAliasesDoNotBlockSeparateValidFavorites()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, "{corrupt aliases", 0640)); AliasGuard guard(alias);
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision()));
        QVERIFY(store.unpin(appA, store.revision())); QVERIFY(guard.intact());
        QVERIFY(write(path, "{corrupt favorites"));
        AliasStore aliases(alias); QVERIFY(!aliases.writable()); QVERIFY(guard.intact());
        const QString healthyAlias = root.filePath("healthy-aliases.json");
        AliasStore healthy(healthyAlias); QVERIFY(healthy.save("editor", appA, healthy.revision()));
        QCOMPARE(bytes(path), QByteArray("{corrupt favorites"));
    }
    void targetParentAndLockSymlinksNeverTouchTheirReferents()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        QVERIFY(QFile::link(alias, path)); FavoritesStore linked(path);
        QVERIFY(!linked.writable()); QVERIFY(!linked.pin(appA, linked.revision()));
        QVERIFY(QFileInfo(path).isSymLink()); QVERIFY(guard.intact()); QVERIFY(QFile::remove(path));
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision())); const auto original = bytes(path);
        QVERIFY(QFile::link(alias, path + ".lock"));
        QVERIFY(!store.pin(appB, store.revision())); QVERIFY(QFileInfo(path + ".lock").isSymLink());
        QCOMPARE(bytes(path), original); QVERIFY(guard.intact());
        QVERIFY(QDir().mkdir(root.filePath("actual"))); QVERIFY(QFile::link(root.filePath("actual"), root.filePath("linked-parent")));
        FavoritesStore parent(root.filePath("linked-parent/favorites.json"));
        QVERIFY(!parent.writable()); QVERIFY(!parent.pin(appA, parent.revision()));
        QVERIFY(!QFile::exists(root.filePath("actual/favorites.json"))); QVERIFY(guard.intact());
    }
    void existingStaleLockAndConcurrentWriterAreNeverTakenOver()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision())); const auto original = bytes(path);
        const QByteArray stale = "2147483647\nstale fixture\nnot a current owner\n";
        QVERIFY(write(path + ".lock", stale, 0640));
        QVERIFY(!store.pin(appB, store.revision())); QCOMPARE(bytes(path + ".lock"), stale);
        QCOMPARE(bytes(path), original); QVERIFY(store.writable()); QVERIFY(guard.intact());
        QVERIFY(QFile::remove(path + ".lock"));
        ResetBoundary reset; bool secondAccepted = true; FavoritesStore second(path);
        boundary.parent = root.path(); boundary.beforePublish = [&] { secondAccepted = second.pin(appC, second.revision()); };
        QVERIFY(store.pin(appB, store.revision())); QVERIFY(boundary.injected); QVERIFY(!secondAccepted);
        QCOMPARE(store.entries(), QStringList({appA, appB})); QVERIFY(!QFile::exists(path + ".lock")); QVERIFY(guard.intact());
    }
    void replacementLockIsPreservedAndAbortsPublication_data()
    {
        QTest::addColumn<int>("kind");
        QTest::newRow("regular") << 0; QTest::newRow("symlink") << 1; QTest::newRow("directory") << 2;
    }
    void replacementLockIsPreservedAndAbortsPublication()
    {
        QFETCH(int, kind); QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision())); const auto original = bytes(path);
        ResetBoundary reset; bool replaced = false;
        boundary.parent = root.path(); boundary.beforePublish = [&] {
            if (!QFile::remove(path + ".lock")) return;
            replaced = kind == 0 ? write(path + ".lock", "foreign replacement", 0640)
                : kind == 1 ? QFile::link(alias, path + ".lock") : QDir().mkdir(path + ".lock");
        };
        QVERIFY(!store.pin(appB, store.revision())); QVERIFY(boundary.injected); QVERIFY(replaced);
        QCOMPARE(bytes(path), original); QVERIFY(guard.intact());
        if (kind == 0) { QCOMPARE(bytes(path + ".lock"), QByteArray("foreign replacement")); QCOMPARE(mode(path + ".lock"), mode_t(0640)); }
        if (kind == 1) QVERIFY(QFileInfo(path + ".lock").isSymLink());
        if (kind == 2) QVERIFY(QFileInfo(path + ".lock").isDir());
        QVERIFY(QDir(root.path()).entryList({".favorites-*"}, QDir::Files | QDir::Hidden).isEmpty());
    }
    void externalWriteDuringPublicationIsPreservedAndAdopted()
    {
        QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision()));
        ResetBoundary reset; bool changed = false;
        boundary.parent = root.path(); boundary.beforePublish = [&] { changed = write(path, document({appC})); };
        QVERIFY(!store.pin(appB, store.revision())); QVERIFY(changed); QVERIFY(boundary.injected);
        QCOMPARE(bytes(path), document({appC})); QCOMPARE(store.entries(), QStringList({appC}));
        QVERIFY(!QFile::exists(path + ".lock")); QVERIFY(guard.intact());
    }
    void parentReplacementPreservesBothTreesAndTheDisplacedLock()
    {
        QTemporaryDir root;
        const QString parent = root.filePath("preferences"), moved = root.filePath("moved"); QVERIFY(QDir().mkdir(parent));
        const QString path = parent + "/favorites.json", alias = parent + "/launcher-aliases.json";
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision())); const auto original = bytes(path);
        ResetBoundary reset; bool changed = false;
        boundary.parent = parent; boundary.beforePublish = [&] {
            changed = QDir().rename(parent, moved) && QDir().mkdir(parent)
                && write(path, document({appC})) && write(path + ".lock", "new parent lock", 0640);
        };
        QVERIFY(!store.pin(appB, store.revision())); QVERIFY(changed); QVERIFY(boundary.injected);
        QCOMPARE(bytes(moved + "/favorites.json"), original); QCOMPARE(bytes(path), document({appC}));
        QCOMPARE(bytes(path + ".lock"), QByteArray("new parent lock"));
        QVERIFY(QFile::exists(moved + "/favorites.json.lock"));
        guard.path = moved + "/launcher-aliases.json"; QVERIFY(guard.intact());
        QVERIFY(QDir(moved).entryList({".favorites-*"}, QDir::Files | QDir::Hidden).isEmpty());
    }
    void atomicFailurePreservesBytesAndOnlyReleasesOwnLock_data()
    {
        QTest::addColumn<bool>("staging"); QTest::newRow("staging-open") << true; QTest::newRow("rename") << false;
    }
    void atomicFailurePreservesBytesAndOnlyReleasesOwnLock()
    {
        QFETCH(bool, staging); QTemporaryDir root;
        const QString path = root.filePath("favorites.json"), alias = root.filePath("launcher-aliases.json");
        QVERIFY(write(alias, aliasFixture, 0640)); AliasGuard guard(alias);
        FavoritesStore store(path); QVERIFY(store.pin(appA, store.revision())); const auto original = bytes(path);
        ResetBoundary reset; boundary.failStaging = staging; boundary.failRename = !staging;
        QVERIFY(!store.pin(appB, store.revision())); QCOMPARE(bytes(path), original);
        QVERIFY(!QFile::exists(path + ".lock")); QVERIFY(guard.intact()); QVERIFY(store.writable());
        QVERIFY(QDir(root.path()).entryList({".favorites-*"}, QDir::Files | QDir::Hidden).isEmpty());
        QVERIFY(store.pin(appB, store.revision()));
    }
};
QTEST_GUILESS_MAIN(FavoritesStoreTests)
#include "FavoritesStoreTests.moc"
