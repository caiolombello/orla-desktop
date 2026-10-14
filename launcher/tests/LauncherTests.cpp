#include <QtTest>
#include <QStandardPaths>
#include <QDir>
#include <QLockFile>
#include <KService>
#include <KSycoca>
#include <QJsonDocument>
#include <QSemaphore>
#include <QThread>
#include <QThreadStorage>
#include <atomic>
#include <thread>
#include <cstdarg>
#include <fcntl.h>
#include <unistd.h>
#include "LauncherController.h"
#include "LauncherControllerTestOwner.h"
#include "SteamProviderController.h"
#include "BusChecks.h"

namespace {
// The second exact favorite-file read is the Store's own reload, after the
// controller preflight. No runner, production callback or personal path is mocked.
struct FavoriteReloadBoundary {
    QByteArray name;
    QString path;
    QByteArray replacement;
    int reads = 0;
    bool injected = false, written = false;
} favoriteReloadBoundary;
struct ResetFavoriteReloadBoundary { ~ResetFavoriteReloadBoundary() { favoriteReloadBoundary = {}; } };
struct RunnerTlsTail {
    QSemaphore &entered;
    QSemaphore &release;
    std::atomic_bool &complete;
    ~RunnerTlsTail()
    {
        entered.release(2);
        release.tryAcquire(1, 300);
        complete.store(true);
    }
};
QString writeSteamHelper(QTemporaryDir &directory)
{
    const QByteArray document = R"({"apps":[{"appid":"42","library":"library-0","name":"Synthetic Steam Game","ownership":"unknown","source":"local_manifest","status":"installed_candidate"}],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"available"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"available"}],"schema_version":"0.1-experimental","status":"available"})" "\n";
    const QString helper = directory.filePath(QStringLiteral("steam-helper.py"));
    QFile file(helper);
    if (!file.open(QIODevice::WriteOnly)) return {};
    file.write("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('");
    file.write(document.toBase64());
    file.write("'))\n");
    file.close();
    return helper;
}
}

extern "C" int __real_openat(int, const char *, int, ...);
extern "C" int __wrap_openat(int directory, const char *name, int flags, ...)
{
    mode_t permissions = 0;
    if (flags & O_CREAT) {
        va_list args; va_start(args, flags); permissions = va_arg(args, int); va_end(args);
    }
    auto &boundary = favoriteReloadBoundary;
    if (!boundary.name.isEmpty() && QByteArray(name) == boundary.name
        && !(flags & O_CREAT) && (flags & O_ACCMODE) == O_RDONLY && ++boundary.reads == 2) {
        boundary.injected = true;
        QFile writer(boundary.path);
        boundary.written = writer.open(QIODevice::WriteOnly | QIODevice::Truncate)
            && writer.write(boundary.replacement) == boundary.replacement.size();
        writer.close();
    }
    return flags & O_CREAT ? __real_openat(directory, name, flags, permissions) : __real_openat(directory, name, flags);
}

class LauncherTests final : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void initTestCase() { verifyPrivateTestBus(); }
    void ownedRunnerTlsCleanupCompletesBeforeOwnerReturns()
    {
        QSemaphore installed, entered, release, ownerReturned, runnersDestroyed;
        std::atomic_bool complete = false, finished = false;
        bool teardownBoundaryReached = false;
        QThreadStorage<RunnerTlsTail *> tls;
        auto owner = std::make_unique<LauncherControllerTestOwner>();
        const auto runners = owner->observedRunners();
        QVERIFY(!runners.isEmpty());
        for (const auto &ownedRunner : runners)
            connect(ownedRunner, &QObject::destroyed, this, [&] { runnersDestroyed.release(); }, Qt::DirectConnection);
        connect(&owner->controller(), &QObject::destroyed, this, [&, runnerCount = runners.size()] {
            const QDeadlineTimer boundaryDeadline(400, Qt::PreciseTimer);
            teardownBoundaryReached = runnersDestroyed.tryAcquire(runnerCount, boundaryDeadline)
                && entered.tryAcquire(1, boundaryDeadline);
        }, Qt::DirectConnection);
        auto *runner = runners.first().data();
        QVERIFY(runner);
        QVERIFY(runner->thread() != QThread::currentThread());
        const QPointer<QThread> workerThread = runner->thread();
        connect(workerThread, &QThread::finished, this, [&] { finished.store(true); }, Qt::DirectConnection);
        QVERIFY(QMetaObject::invokeMethod(runner, [&] {
            tls.setLocalData(new RunnerTlsTail{entered, release, complete});
            installed.release();
        }, Qt::QueuedConnection));
        QVERIFY(installed.tryAcquire(1, 500));
        // Hold a real owned runner's TLS after finished/deferred runner deletion.
        // Release on owner return (old guard), or within its existing deadline.
        std::thread helper([&] {
            if (entered.tryAcquire(1, 500)) ownerReturned.tryAcquire(1, 100);
            release.release();
        });
        owner.reset();
        const bool cleanupCompleteAtReturn = complete.load();
        const bool finishedAtReturn = finished.load();
        bool runnersDestroyedAtReturn = true;
        for (const auto &ownedRunner : runners) runnersDestroyedAtReturn &= ownedRunner.isNull();
        qInfo() << "ORLA_TEST_TLS_BOUNDARY" << "finished=" << finishedAtReturn
                << "runners_destroyed=" << runnersDestroyedAtReturn
                << "tls_complete_at_owner_return=" << cleanupCompleteAtReturn;
        ownerReturned.release();
        helper.join();
        QVERIFY(!workerThread || workerThread->wait(QDeadlineTimer(500, Qt::PreciseTimer)));
        QVERIFY(complete.load());
        QVERIFY(teardownBoundaryReached);
        QVERIFY(finishedAtReturn);
        QVERIFY(runnersDestroyedAtReturn);
        QVERIFY2(cleanupCompleteAtReturn, "Owner returned before its runner TLS cleanup completed");
    }
    void editingClearsOldResultsBeforeReplacementArrives()
    {
        LauncherControllerTestOwner controllerOwner;
        LauncherController &launcher = controllerOwner.controller();
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_VERIFY_WITH_TIMEOUT(!launcher.rows().isEmpty() && launcher.status() == "ready", 5000);
        QCOMPARE(launcher.rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        launcher.setQuery(QStringLiteral("9*9"));
        QVERIFY2(launcher.rows().isEmpty(), "Old result must disappear synchronously when typing a replacement");
        QTRY_VERIFY_WITH_TIMEOUT(!launcher.rows().isEmpty() && launcher.status() == "ready", 5000);
        QCOMPARE(launcher.rows().first().toMap().value("title").toString(), QStringLiteral("81"));
    }
    void oversizedInputReportsRecoverableErrorWithoutSearching()
    {
        LauncherControllerTestOwner controllerOwner;
        LauncherController &launcher = controllerOwner.controller();
        launcher.setQuery(QString(513, QLatin1Char('x')));
        QCOMPARE(launcher.status(), QStringLiteral("error"));
        QVERIFY(!launcher.error().isEmpty());
        QVERIFY(launcher.rows().isEmpty());
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        QVERIFY(launcher.error().isEmpty());
    }
    void staleExecutionIsRejectedEvenWhenTheSameQueryReturns()
    {
        LauncherControllerTestOwner controllerOwner;
        LauncherController &launcher = controllerOwner.controller();
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        const auto oldGeneration = launcher.generation();
        const auto oldId = launcher.rows().first().toMap().value("id").toString();
        launcher.setQuery(QStringLiteral("9*9"));
        QVERIFY(!launcher.execute(0, oldGeneration, oldId));
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        QVERIFY(!launcher.execute(0, oldGeneration, oldId));
        QCOMPARE(launcher.query(), QStringLiteral("2+2"));
        QVERIFY(!launcher.execute(0, launcher.generation(), QStringLiteral("different-result")));
        QVERIFY(!launcher.execute(0, launcher.generation(), oldId, QStringLiteral("nonexistent-action")));
    }
    void escapeCancelsBothDebouncedAndInFlightResults()
    {
        LauncherControllerTestOwner controllerOwner;
        LauncherController &launcher = controllerOwner.controller();
        QSignalSpy closed(&launcher, &LauncherController::closeRequested);
        launcher.setQuery(QStringLiteral("2+2"));
        launcher.dismiss();
        QTest::qWait(150);
        QCOMPARE(closed.count(), 1);
        QCOMPARE(launcher.status(), QStringLiteral("idle"));
        QVERIFY(launcher.rows().isEmpty());
        launcher.setQuery(QStringLiteral("9*9"));
        QTest::qWait(65);
        launcher.dismiss();
        QTest::qWait(250);
        QCOMPARE(closed.count(), 2);
        QVERIFY(launcher.rows().isEmpty());
        QVERIFY(!launcher.executeSelected());
    }
    void aliasPresentationIsPassiveFriendlyAndRefusesHiddenCurrentDescriptors()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString absent = root.filePath("no-preferences/aliases.json");
        {
            LauncherControllerTestOwner owner(nullptr, absent);
            auto &launcher = owner.controller();
            for (int n = 0; n < 100; ++n) QVERIFY(launcher.aliases().isEmpty());
            launcher.reloadAliases();
            QVERIFY(!QFile::exists(root.filePath("no-preferences")));
        }
        const QString appId = "org.orla.AliasPresentation.desktop";
        const QString desktopPath = qEnvironmentVariable("XDG_DATA_HOME") + "/applications/" + appId;
        QVERIFY(QDir().mkpath(QFileInfo(desktopPath).absolutePath()));
        QFile script(root.filePath("counter.py"));
        QVERIFY(script.open(QIODevice::WriteOnly));
        script.write("from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('unexpected execution')\n"); script.close();
        const QString receipt = root.filePath("receipt");
        const QByteArray installed = ("[Desktop Entry]\nType=Application\nName=Orla Friendly Alias App\nIcon=org.orla.OwnedAliasIcon\nExec=\""
            + QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE) + "\" \"" + script.fileName() + "\" \"" + receipt + "\"\nTerminal=false\n").toUtf8();
        QFile desktop(desktopPath);
        QVERIFY(desktop.open(QIODevice::WriteOnly)); QCOMPARE(desktop.write(installed), qint64(installed.size())); desktop.close();
        QProcess cache; cache.start("/usr/bin/kbuildsycoca6", {"--noincremental"});
        QVERIFY(cache.waitForFinished(5000)); QCOMPARE(cache.exitCode(),0);
        auto ready = [&] { KSycoca::self()->ensureCacheValid(); return bool(KService::serviceByStorageId(appId)); };
        QTRY_VERIFY_WITH_TIMEOUT(ready(),3000);
        const QString preferences = root.filePath("preferences/aliases.json");
        AliasStore store(preferences);
        QVERIFY(store.save("editor", appId, store.revision()));
        auto bytes = [&] { QFile file(preferences); if (!file.open(QIODevice::ReadOnly)) return QByteArray(); return file.readAll(); };
        const auto persisted = bytes();
        {
            LauncherControllerTestOwner owner(nullptr, preferences);
            auto &launcher = owner.controller();
            const auto entry = launcher.aliases().first().toMap();
            QCOMPARE(entry.value("alias").toString(),QStringLiteral("editor"));
            QCOMPARE(entry.value("appId").toString(),appId);
            QCOMPARE(entry.value("title").toString(),QStringLiteral("Orla Friendly Alias App"));
            QCOMPARE(entry.value("iconName").toString(),QStringLiteral("org.orla.OwnedAliasIcon"));
            QVERIFY(entry.value("available").toBool());
            QSignalSpy notifications(&launcher,&LauncherController::changed);
            const auto generation = launcher.generation();
            for (int n = 0; n < 100; ++n) QCOMPARE(launcher.aliases().first().toMap(),entry);
            QCOMPARE(notifications.count(),0); QCOMPARE(launcher.generation(),generation);
            QCOMPARE(bytes(),persisted); QVERIFY(!QFile::exists(receipt));
            launcher.setQuery("editor");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            for (const auto &flag : {QByteArray("Hidden=true\n"),QByteArray("NoDisplay=true\n"),QByteArray("OnlyShowIn=OrlaMissingDesktop;\n")}) {
                const auto changed = installed + flag;
                QVERIFY(desktop.open(QIODevice::WriteOnly | QIODevice::Truncate));
                QCOMPARE(desktop.write(changed),qint64(changed.size())); desktop.close();
                QVERIFY2(!launcher.executeSelected(),flag.constData()); // Same cache owner; no invalidation wait.
                launcher.reloadAliases();
                QVERIFY(!launcher.aliases().first().toMap().value("available").toBool());
                QCOMPARE(launcher.aliases().first().toMap().value("title").toString(),QStringLiteral("Aplicativo indisponível"));
                QVERIFY(desktop.open(QIODevice::WriteOnly | QIODevice::Truncate));
                QCOMPARE(desktop.write(installed),qint64(installed.size())); desktop.close();
                launcher.reloadAliases();
                QVERIFY(launcher.aliases().first().toMap().value("available").toBool());
            }
            QVERIFY(QFile::remove(desktopPath)); launcher.reloadAliases();
            const auto missing = launcher.aliases().first().toMap();
            QCOMPARE(missing.value("appId").toString(),appId);
            QCOMPARE(missing.value("title").toString(),QStringLiteral("Aplicativo indisponível"));
            QVERIFY(!missing.value("available").toBool());
            QVERIFY(!QFile::exists(receipt)); QCOMPARE(bytes(),persisted);
            QVERIFY(!persisted.contains("title") && !persisted.contains("iconName") && !persisted.contains("available"));
        }
    }
    void aliasStoreWritesOnlyExplicitValidPreferencesAndPersistsRestart()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString path = root.filePath("new/aliases.json");
        AliasStore store(path);
        QVERIFY(store.entries().isEmpty());
        QVERIFY(!QFile::exists(root.filePath("new")));
        QVERIFY(!store.save(QString(33, 'x'), "org.orla.App.desktop", store.revision()));
        QVERIFY(!QFile::exists(root.filePath("new")));
        QVERIFY(store.save("  Texto  ", "org.orla.App.desktop", store.revision()));
        QFile file(path);
        QVERIFY(file.open(QIODevice::ReadOnly));
        const auto original = file.readAll();
        file.close();
        QVERIFY(!original.contains("exec") && !original.contains("query") && !original.contains("generation"));
        AliasStore restart(path);
        QCOMPARE(restart.entries().first().toMap().value("alias").toString(), QStringLiteral("Texto"));
        QCOMPARE(restart.entries().first().toMap().value("appId").toString(), QStringLiteral("org.orla.App.desktop"));
        QVERIFY(!restart.save("TEXTO", "org.orla.Other.desktop", restart.revision()));
        QVERIFY(!restart.error().isEmpty());
        QVERIFY(!restart.save("bad", "../other.desktop", restart.revision()));
        for (int n = 1; n < 16; ++n) QVERIFY(restart.save("alias" + QString::number(n), "org.orla.App.desktop", restart.revision()));
        QCOMPARE(restart.entries().size(), 16);
        const QString fullRevision = restart.revision();
        QVERIFY(!restart.save("seventeenth", "org.orla.App.desktop", fullRevision));
        QCOMPARE(restart.revision(), fullRevision);
        QVERIFY(restart.remove("TEXTO", "org.orla.App.desktop", restart.revision()));
        const QString beforeExternal = restart.revision();
        AliasStore external(path);
        QVERIFY(external.save("outside-change", "org.orla.App.desktop", external.revision()));
        QVERIFY(!restart.save("stale", "org.orla.App.desktop", beforeExternal));
        QVERIFY(restart.reload() == false); // Refusal already adopted the current disk snapshot.
        QCOMPARE(restart.entries(), external.entries());
    }
    void aliasRenameIsAtomicExactAndRecoverableAtCapacity()
    {
        QTemporaryDir root;
        const QString path = root.filePath("aliases.json");
        AliasStore store(path);
        for (int n = 0; n < 16; ++n) QVERIFY(store.save("alias" + QString::number(n), "org.orla.App.desktop", store.revision()));
        auto bytes = [&] { QFile file(path); if (!file.open(QIODevice::ReadOnly)) return QByteArray(); return file.readAll(); };
        const auto full = bytes();
        const auto revision = store.revision();
        QVERIFY(!store.rename("alias0", "org.orla.Other.desktop", "new", revision));
        QVERIFY(!store.rename("alias0", "org.orla.App.desktop", "ALIAS1", revision));
        QVERIFY(!store.rename("alias0", "org.orla.App.desktop", QString(33, 'x'), revision));
        QCOMPARE(bytes(), full);
        QVERIFY(store.writable()); // A correctable command error does not make preferences read-only.
        QVERIFY(store.rename("ALIAS0", "org.orla.App.desktop", "  Novo  ", revision));
        QCOMPARE(store.entries().size(), 16);
        QCOMPARE(store.entries().first().toMap().value("alias").toString(), QStringLiteral("Novo"));
        QVERIFY(store.error().isEmpty());
        const auto renamed = bytes();
        QVERIFY(!store.rename("Novo", "org.orla.App.desktop", "stale", revision));
        QCOMPARE(bytes(), renamed);
        AliasStore restart(path);
        QCOMPARE(restart.entries(), store.entries());
    }
    void aliasStoreRefusesLockedCorruptOversizedAndSymlinkTargets()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString path = root.filePath("aliases.json");
        AliasStore store(path);
        QVERIFY(store.save("texto", "org.orla.App.desktop", store.revision()));
        auto bytes = [](const QString &name) { QFile file(name); if (!file.open(QIODevice::ReadOnly)) return QByteArray(); return file.readAll(); };
        const QByteArray original = bytes(path);
        {
            QLockFile competing(path + ".lock");
            QVERIFY(competing.tryLock(0));
            QVERIFY(!store.save("blocked", "org.orla.App.desktop", store.revision()));
            QCOMPARE(bytes(path), original);
        }
        QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        file.write("{\"formatVersion\":\"future\",\"aliases\":[]}");
        file.close();
        const auto future = bytes(path);
        AliasStore corrupt(path);
        QVERIFY(!corrupt.writable());
        QVERIFY(!corrupt.save("repair", "org.orla.App.desktop", corrupt.revision()));
        QCOMPARE(bytes(path), future);
        QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate));
        file.write(QByteArray(16385, 'x'));
        file.close();
        AliasStore oversized(path);
        QVERIFY(!oversized.writable());
        QVERIFY(!oversized.remove("texto", "org.orla.App.desktop", oversized.revision()));
        QCOMPARE(bytes(path).size(), 16385);
        const QString outside = root.filePath("outside.json");
        QVERIFY(QFile::rename(path, outside));
        QVERIFY(QFile::link(outside, path));
        AliasStore linked(path);
        QVERIFY(!linked.writable());
        QVERIFY(!linked.save("linked", "org.orla.App.desktop", linked.revision()));
        QCOMPARE(bytes(outside), QByteArray(16385, 'x'));
        QVERIFY(QFileInfo(path).isSymLink());
        QVERIFY(QDir(root.path()).entryList({".aliases-*"}, QDir::Files | QDir::Hidden).isEmpty());
    }
    void explicitAliasSaveRestartsAndOnlyDispatchesChosenAppDespiteSameName()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString applications = qEnvironmentVariable("XDG_DATA_HOME") + "/applications";
        QVERIFY(QDir().mkpath(applications));
        const QString script = root.filePath("counter.py");
        QFile helper(script);
        QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("from pathlib import Path\nimport sys\nwith Path(sys.argv[1]).open('a') as receipt: receipt.write(sys.argv[2])\n");
        helper.close();
        const QString appA = "org.orla.AliasCoreA.desktop", appB = "org.orla.AliasCoreB.desktop";
        for (const auto &entry : QList<QPair<QString, QString>>{{appA,"A"},{appB,"B"}}) {
            QFile desktop(applications + "/" + entry.first);
            QVERIFY(desktop.open(QIODevice::WriteOnly));
            desktop.write(("[Desktop Entry]\nType=Application\nName=OrlaAliasCoreCollision\nExec=\""
                + QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE) + "\" \"" + script + "\" \""
                + root.filePath("receipt-" + entry.second) + "\" " + entry.second + "\nTerminal=false\n").toUtf8());
        }
        QProcess cache;
        cache.start("/usr/bin/kbuildsycoca6", {"--noincremental"});
        QVERIFY(cache.waitForFinished(5000));
        QCOMPARE(cache.exitCode(),0);
        auto appsReady = [&] { KSycoca::self()->ensureCacheValid(); return KService::serviceByStorageId(appA) && KService::serviceByStorageId(appB); };
        QTRY_VERIFY_WITH_TIMEOUT(appsReady(),3000);
        const QString storage = root.filePath("preferences/aliases.json");
        {
            LauncherControllerTestOwner owner(nullptr,storage);
            auto &launcher = owner.controller();
            launcher.setQuery("OrlaAliasCoreCollision");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            auto appRow = [&](const QString &id) { for (int row=0;row<launcher.rows().size();++row) if (launcher.rows()[row].toMap().value("appId").toString()==id) return row; return -1; };
            QTRY_VERIFY_WITH_TIMEOUT(appRow(appA)>=0 && appRow(appB)>=0,5000);
            const int a = appRow(appA), b = appRow(appB);
            launcher.select(a);
            const auto selected = launcher.rows()[a].toMap();
            QVERIFY(!launcher.saveAlias(b,launcher.generation(),launcher.rows()[b].toMap().value("id").toString(),"texto",launcher.aliasRevision()));
            QVERIFY(!QFile::exists(storage));
            QVERIFY(launcher.saveAlias(a,launcher.generation(),selected.value("id").toString(),"Texto",launcher.aliasRevision()));
            QVERIFY(!launcher.saveAlias(a,selected.value("generation").toULongLong(),selected.value("id").toString(),"late",launcher.aliasRevision()));
            QCOMPARE(launcher.aliases().size(),1);
            QVERIFY(!QFile::exists(root.filePath("receipt-A")) && !QFile::exists(root.filePath("receipt-B")));
        }
        {
            LauncherControllerTestOwner owner(nullptr,storage);
            auto &launcher = owner.controller();
            QCOMPARE(launcher.aliases().first().toMap().value("appId").toString(),appA);
            launcher.setQuery("TEXTO");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            auto ticket=launcher.rows().first().toMap();
            QCOMPARE(ticket.value("kind").toString(),QStringLiteral("alias"));
            QCOMPARE(ticket.value("appId").toString(),appA);
            launcher.setQuery("2+2");
            QVERIFY(!launcher.execute(0,ticket.value("generation").toULongLong(),ticket.value("id").toString()));
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            launcher.setQuery("texto");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            QVERIFY(launcher.executeSelected());
            QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(root.filePath("receipt-A")),5000);
            QFile observed(root.filePath("receipt-A"));
            QVERIFY(observed.open(QIODevice::ReadOnly));
            QCOMPARE(observed.readAll(),QByteArray("A"));
            QVERIFY(!QFile::exists(root.filePath("receipt-B")));
            launcher.setQuery("texto");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            ticket=launcher.rows().first().toMap();
            const QString staleRevision=launcher.aliasRevision();
            AliasStore other(storage);
            QVERIFY(other.remove("Texto",appA,other.revision()));
            QVERIFY(other.save("Texto",appB,other.revision()));
            QVERIFY(!launcher.execute(0,ticket.value("generation").toULongLong(),ticket.value("id").toString()));
            QVERIFY(!launcher.removeAlias("Texto",appA,ticket.value("generation").toULongLong(),staleRevision));
            QVERIFY(!QFile::exists(root.filePath("receipt-B")));
            launcher.setQuery("texto");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            QCOMPARE(launcher.rows().first().toMap().value("appId").toString(),appB);
            QVERIFY(launcher.removeAlias("texto",appB,launcher.generation(),launcher.aliasRevision()));
            QVERIFY(!QFile::exists(root.filePath("receipt-B")));
            launcher.setQuery("OrlaAliasCoreCollision");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            int a=-1;for(int row=0;row<launcher.rows().size();++row)if(launcher.rows()[row].toMap().value("appId").toString()==appA)a=row;
            QVERIFY(a>=0);launcher.select(a);
            QVERIFY(launcher.saveAlias(a,launcher.generation(),launcher.rows()[a].toMap().value("id").toString(),"texto",launcher.aliasRevision()));
            launcher.setQuery("texto");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            QFile descriptor(applications+"/"+appA);
            QVERIFY(descriptor.open(QIODevice::ReadOnly));
            const auto installed = descriptor.readAll(); descriptor.close();
            for (const auto &changed : QList<QByteArray>{installed + "Terminal=true\n", installed + "Path=/orla-owned-missing-directory\n", installed + "DBusActivatable=true\n", QByteArray(installed).replace(" A\n", " changed\n")}) {
                QVERIFY(descriptor.open(QIODevice::WriteOnly | QIODevice::Truncate));
                QCOMPARE(descriptor.write(changed), qint64(changed.size())); descriptor.close();
                QVERIFY(!launcher.executeSelected());
                QVERIFY(descriptor.open(QIODevice::WriteOnly | QIODevice::Truncate));
                QCOMPARE(descriptor.write(installed), qint64(installed.size())); descriptor.close();
            }
            QVERIFY(QFile::remove(applications+"/"+appA));
            QVERIFY(!launcher.executeSelected()); // No same-name fallback and no stale cached desktop launch.
            QVERIFY(!QFile::exists(root.filePath("receipt-B")));
            launcher.setQuery("2+2");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            launcher.setQuery("texto");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            QVERIFY(!launcher.rows().first().toMap().value("enabled").toBool());
            const auto missingGeneration = launcher.generation();
            const auto missingRevision = launcher.aliasRevision();
            QVERIFY(launcher.renameAlias("texto",appA,"Editor",missingGeneration,missingRevision));
            QVERIFY(!launcher.renameAlias("texto",appA,"late",missingGeneration,missingRevision));
            QCOMPARE(launcher.aliases().first().toMap().value("alias").toString(),QStringLiteral("Editor"));
            QVERIFY(launcher.removeAlias("Editor",appA,launcher.generation(),launcher.aliasRevision()));
            QVERIFY(launcher.aliases().isEmpty());
        }
        QFile::remove(applications+"/"+appB);
    }
    void favoritesMissingReadsStayPassiveAndClearRejectsLateNativeResults()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString aliases = root.filePath("absent/aliases.json");
        const QString favorites = root.filePath("absent/favorites.json");
        LauncherControllerTestOwner owner(nullptr, aliases, favorites);
        auto &launcher = owner.controller();
        QCOMPARE(launcher.favoriteRevision(), QStringLiteral("missing"));
        QVERIFY(launcher.favoritesWritable());
        for (int n = 0; n < 100; ++n) QVERIFY(launcher.favorites().isEmpty());
        launcher.reloadFavorites();
        launcher.setQuery("");
        QCOMPARE(launcher.status(), QStringLiteral("idle"));
        QVERIFY(!QFileInfo(root.filePath("absent")).exists());
        launcher.setQuery("2+2");
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        const auto ticket = launcher.rows().first().toMap();
        QVERIFY(!launcher.pinFavorite(0, launcher.generation(), ticket.value("id").toString(), launcher.favoriteRevision()));
        launcher.setQuery("9*9");
        QTest::qWait(65); // Cancel an actual launched context, not only its debounce.
        launcher.setQuery("");
        QTest::qWait(300);
        QVERIFY(launcher.rows().isEmpty());
        QCOMPARE(launcher.status(), QStringLiteral("idle"));
        QVERIFY(!launcher.execute(0, ticket.value("generation").toULongLong(), ticket.value("id").toString()));
        QVERIFY(!QFileInfo(root.filePath("absent")).exists());
    }
    void favoritesRestartReorderAndEnterRunOnlyTheExactSavedHomonym()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString applications = qEnvironmentVariable("XDG_DATA_HOME") + "/applications";
        QVERIFY(QDir().mkpath(applications));
        const QString script = root.filePath("favorite-counter.py");
        QFile helper(script);
        QVERIFY(helper.open(QIODevice::WriteOnly));
        helper.write("from pathlib import Path\nimport sys\nwith Path(sys.argv[1]).open('a') as receipt: receipt.write(sys.argv[2])\n");
        helper.close();
        const QString appA = "org.orla.FavoriteCoreA.desktop", appB = "org.orla.FavoriteCoreB.desktop";
        // Remove only these owned descriptors even if a test assertion returns early.
        struct Descriptors {
            QStringList paths;
            ~Descriptors() { for (const auto &path : paths) QFile::remove(path); }
        } descriptors{{applications + "/" + appA, applications + "/" + appB}};
        for (const auto &entry : QList<QPair<QString, QString>>{{appA,"A"},{appB,"B"}}) {
            QFile desktop(applications + "/" + entry.first);
            QVERIFY(desktop.open(QIODevice::WriteOnly));
            desktop.write(("[Desktop Entry]\nType=Application\nName=OrlaFavoriteCoreCollision\nIcon=org.orla.OwnedFavoriteIcon\nExec=\""
                + QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE) + "\" \"" + script + "\" \""
                + root.filePath("receipt-" + entry.second) + "\" " + entry.second + "\nTerminal=false\n").toUtf8());
        }
        QProcess cache;
        cache.start("/usr/bin/kbuildsycoca6", {"--noincremental"});
        QVERIFY(cache.waitForFinished(5000));
        QCOMPARE(cache.exitCode(),0);
        auto appsReady = [&] { KSycoca::self()->ensureCacheValid(); return KService::serviceByStorageId(appA) && KService::serviceByStorageId(appB); };
        QTRY_VERIFY_WITH_TIMEOUT(appsReady(),3000);
        const QString aliases = root.filePath("aliases.json"), favorites = root.filePath("favorites.json");
        AliasStore aliasStore(aliases);
        QVERIFY(aliasStore.save("ownfavoritealias",appA,aliasStore.revision()));
        QFile aliasFile(aliases);
        QVERIFY(aliasFile.open(QIODevice::ReadOnly));
        const QByteArray aliasBytes = aliasFile.readAll(); aliasFile.close();
        const auto aliasMode = QFileInfo(aliases).permissions();
        const auto aliasRevision = aliasStore.revision();
        auto aliasUnchanged = [&] {
            QFile current(aliases);
            if (!current.open(QIODevice::ReadOnly)) return false;
            AliasStore observed(aliases);
            return current.readAll()==aliasBytes && QFileInfo(aliases).permissions()==aliasMode && observed.revision()==aliasRevision;
        };
        {
            LauncherControllerTestOwner owner(nullptr,aliases,favorites);
            auto &launcher = owner.controller();
            launcher.setQuery("OrlaFavoriteCoreCollision");
            auto appRow = [&](const QString &id) { for (int row=0;row<launcher.rows().size();++row) if (launcher.rows()[row].toMap().value("appId").toString()==id) return row; return -1; };
            QTRY_VERIFY_WITH_TIMEOUT(launcher.status()=="ready" && appRow(appA)>=0 && appRow(appB)>=0,5000);
            launcher.select(appRow(appA));
            const auto initialA = launcher.rows()[launcher.selectedIndex()].toMap();
            QFile descriptor(applications+"/"+appA);
            QVERIFY(descriptor.open(QIODevice::ReadOnly)); const auto original=descriptor.readAll(); descriptor.close();
            QVERIFY(descriptor.open(QIODevice::WriteOnly|QIODevice::Truncate)); descriptor.write(original+"NoDisplay=true\n"); descriptor.close();
            QVERIFY(!launcher.pinFavorite(launcher.selectedIndex(),launcher.generation(),initialA.value("id").toString(),launcher.favoriteRevision()));
            QVERIFY(descriptor.open(QIODevice::WriteOnly|QIODevice::Truncate)); descriptor.write(original); descriptor.close();
            launcher.reloadAliases();
            launcher.select(appRow(appA));
            const auto a = launcher.rows()[launcher.selectedIndex()].toMap();
            QVERIFY(!launcher.pinFavorite(appRow(appB),launcher.generation(),launcher.rows()[appRow(appB)].toMap().value("id").toString(),launcher.favoriteRevision()));
            QVERIFY(!launcher.pinFavorite(launcher.selectedIndex(),launcher.generation(),"wrong-id",launcher.favoriteRevision()));
            QVERIFY(!QFile::exists(favorites));
            QVERIFY(launcher.pinFavorite(launcher.selectedIndex(),launcher.generation(),a.value("id").toString(),launcher.favoriteRevision()));
            QVERIFY(!launcher.pinFavorite(launcher.selectedIndex(),a.value("generation").toULongLong(),a.value("id").toString(),launcher.favoriteRevision()));
            launcher.select(appRow(appB));
            const auto b = launcher.rows()[launcher.selectedIndex()].toMap();
            QVERIFY(launcher.pinFavorite(launcher.selectedIndex(),launcher.generation(),b.value("id").toString(),launcher.favoriteRevision()));
            {
                ResetFavoriteReloadBoundary reset;
                const auto generation=launcher.generation();
                const auto revision=launcher.favoriteRevision();
                const auto id=launcher.rows()[launcher.selectedIndex()].toMap().value("id").toString();
                const QByteArray external=("{ \"formatVersion\": \"0.1-experimental\", \"favorites\": [\""+appA+"\",\""+appB+"\"] }\n").toUtf8();
                favoriteReloadBoundary={QFile::encodeName(QFileInfo(favorites).fileName()),favorites,external};
                QVERIFY(!launcher.pinFavorite(launcher.selectedIndex(),generation,id,revision));
                QVERIFY(favoriteReloadBoundary.injected && favoriteReloadBoundary.written);
                QFile readback(favorites); QVERIFY(readback.open(QIODevice::ReadOnly)); QCOMPARE(readback.readAll(),external);
                QVERIFY(launcher.generation()>generation);
                QVERIFY(launcher.favoriteRevision()!=revision);
                QVERIFY(!launcher.favoriteError().isEmpty()); QVERIFY(launcher.favoritesWritable());
                QCOMPARE(launcher.rows()[launcher.selectedIndex()].toMap().value("id").toString(),id);
                QVERIFY(!launcher.pinFavorite(launcher.selectedIndex(),generation,id,revision));
                launcher.setQuery("");
                for (const auto &row : launcher.rows()) QCOMPARE(row.toMap().value("favoriteRevision").toString(),launcher.favoriteRevision());
            }
            QVERIFY(aliasUnchanged());
            QVERIFY(!QFile::exists(root.filePath("receipt-A")) && !QFile::exists(root.filePath("receipt-B")));
        }
        {
            LauncherControllerTestOwner owner(nullptr,aliases,favorites);
            auto &launcher = owner.controller();
            QCOMPARE(launcher.status(),QStringLiteral("ready"));
            QCOMPARE(launcher.rows().size(),2);
            QCOMPARE(launcher.rows()[0].toMap().value("appId").toString(),appA);
            const auto a = launcher.rows()[0].toMap();
            QCOMPARE(a.value("kind").toString(),QStringLiteral("favorite"));
            QCOMPARE(a.value("categoryLabel").toString(),QStringLiteral("FAVORITOS"));
            QCOMPARE(a.value("source").toString(),QStringLiteral("Favorito salvo por você"));
            QCOMPARE(a.value("iconName").toString(),QStringLiteral("org.orla.OwnedFavoriteIcon"));
            QCOMPARE(a.value("favoriteRevision").toString(),launcher.favoriteRevision());
            for (int n=0;n<100;++n) QCOMPARE(launcher.favorites().first().toMap().value("title").toString(),QStringLiteral("OrlaFavoriteCoreCollision"));
            launcher.select(1);
            const auto oldB = launcher.rows()[1].toMap();
            QVERIFY(!launcher.execute(0,launcher.generation(),a.value("id").toString()));
            QVERIFY(!launcher.execute(1,launcher.generation(),oldB.value("id").toString(),"foreign-action"));
            FavoritesStore external(favorites);
            QVERIFY(external.unpin(appA,external.revision()));
            QVERIFY(external.pin(appA,external.revision())); // Exact order is now B,A.
            QVERIFY(!launcher.execute(1,oldB.value("generation").toULongLong(),oldB.value("id").toString()));
            QCOMPARE(launcher.rows()[0].toMap().value("appId").toString(),appB);
            QCOMPARE(launcher.selectedIndex(),0); // Identity B survives moving from index1.
            QVERIFY(!launcher.removeFavorite(appB,oldB.value("generation").toULongLong(),oldB.value("favoriteRevision").toString()));
            launcher.setQuery("2+2");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            launcher.setQuery("");
            QTest::qWait(300);
            QCOMPARE(launcher.rows().size(),2);
            for (const auto &row : launcher.rows()) QCOMPARE(row.toMap().value("kind").toString(),QStringLiteral("favorite"));
            launcher.select(1);
            const auto selected = launcher.rows()[1].toMap();
            QVERIFY(!launcher.execute(1,a.value("generation").toULongLong(),selected.value("id").toString()));
            QFile descriptor(applications+"/"+appA);
            QVERIFY(descriptor.open(QIODevice::ReadOnly));
            const auto installed = descriptor.readAll(); descriptor.close();
            for (const auto &changed : QList<QByteArray>{installed+"NoDisplay=true\n",installed+"Hidden=true\n",installed+"Terminal=true\n",installed+"Path=/orla-owned-missing-directory\n",installed+"DBusActivatable=true\n",QByteArray(installed).replace(" A\n"," changed\n")}) {
                QVERIFY(descriptor.open(QIODevice::WriteOnly|QIODevice::Truncate));
                QCOMPARE(descriptor.write(changed),qint64(changed.size())); descriptor.close();
                QVERIFY(!launcher.executeSelected());
                QVERIFY(descriptor.open(QIODevice::WriteOnly|QIODevice::Truncate));
                QCOMPARE(descriptor.write(installed),qint64(installed.size())); descriptor.close();
            }
            QVERIFY(!QFile::exists(root.filePath("receipt-A")) && !QFile::exists(root.filePath("receipt-B")));
            QVERIFY(launcher.executeSelected()); // The same public Enter path used by the window.
            QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(root.filePath("receipt-A")),5000);
            QFile observed(root.filePath("receipt-A"));
            QVERIFY(observed.open(QIODevice::ReadOnly)); QCOMPARE(observed.readAll(),QByteArray("A"));
            QVERIFY(!QFile::exists(root.filePath("receipt-B")));
            QTest::qWait(100);
            QVERIFY(launcher.rows().isEmpty()); // Late model notifications do not reopen a dismissed surface.
            launcher.setQuery(""); // Reopening refreshes empty-query favorites, without a dummy search.
            QVERIFY(QFile::remove(applications+"/"+appA));
            launcher.reloadFavorites();
            QCOMPARE(launcher.rows()[1].toMap().value("appId").toString(),appA);
            QVERIFY(!launcher.rows()[1].toMap().value("enabled").toBool());
            QVERIFY(!launcher.favorites()[1].toMap().value("available").toBool());
            QVERIFY(launcher.removeFavorite(appA,launcher.generation(),launcher.favoriteRevision()));
            QCOMPARE(launcher.favorites().size(),1);
            QVERIFY(aliasUnchanged());
            QFile corrupt(favorites);
            QVERIFY(corrupt.open(QIODevice::WriteOnly|QIODevice::Truncate)); corrupt.write("{invalid"); corrupt.close();
            launcher.reloadFavorites();
            QVERIFY(!launcher.favoritesWritable()); QVERIFY(!launcher.favoriteError().isEmpty());
            QVERIFY(launcher.aliasesWritable());
            launcher.setQuery("ownfavoritealias");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            QCOMPARE(launcher.rows().first().toMap().value("kind").toString(),QStringLiteral("alias"));
            QVERIFY(aliasUnchanged());
            // A valid native favorite is independent from a corrupt alias file.
            QVERIFY(corrupt.open(QIODevice::WriteOnly|QIODevice::Truncate));
            corrupt.write(("{\"formatVersion\":\"0.1-experimental\",\"favorites\":[\""+appB+"\"]}").toUtf8()); corrupt.close();
            QVERIFY(aliasFile.open(QIODevice::WriteOnly|QIODevice::Truncate)); aliasFile.write("{broken"); aliasFile.close();
            launcher.reloadAliases(); launcher.reloadFavorites(); launcher.setQuery("");
            QVERIFY(!launcher.aliasesWritable()); QVERIFY(launcher.favoritesWritable());
            QCOMPARE(launcher.rows().size(),1); QVERIFY(launcher.rows().first().toMap().value("enabled").toBool());
            launcher.setQuery("OrlaFavoriteCoreCollision");
            QTRY_COMPARE_WITH_TIMEOUT(launcher.status(),QStringLiteral("ready"),5000);
            int b=-1; for(int row=0;row<launcher.rows().size();++row) if(launcher.rows()[row].toMap().value("appId").toString()==appB)b=row;
            QVERIFY(b>=0); launcher.select(b);
            QVERIFY(launcher.pinFavorite(b,launcher.generation(),launcher.rows()[b].toMap().value("id").toString(),launcher.favoriteRevision()));
            QVERIFY(aliasFile.open(QIODevice::ReadOnly)); QCOMPARE(aliasFile.readAll(),QByteArray("{broken")); aliasFile.close();
            QVERIFY(!QFile::exists(root.filePath("receipt-B")));
        }
    }
    void favoritesRemainUsableWithCorruptAliasesAndRemoveMissingWithFreshTickets()
    {
        QTemporaryDir root;
        QVERIFY(root.isValid());
        const QString aliases=root.filePath("aliases.json"), favorites=root.filePath("favorites.json");
        QFile bad(aliases);
        QVERIFY(bad.open(QIODevice::WriteOnly)); bad.write("{broken"); bad.close();
        FavoritesStore saved(favorites);
        const QString appId="org.orla.FavoriteMissing.desktop";
        QVERIFY(saved.pin(appId,saved.revision()));
        LauncherControllerTestOwner owner(nullptr,aliases,favorites);
        auto &launcher=owner.controller();
        QVERIFY(!launcher.aliasesWritable()); QVERIFY(launcher.favoritesWritable());
        QCOMPARE(launcher.rows().size(),1);
        QVERIFY(!launcher.rows().first().toMap().value("enabled").toBool());
        QVERIFY(!launcher.executeSelected());
        {
            ResetFavoriteReloadBoundary reset;
            const auto generation=launcher.generation();
            const auto revision=launcher.favoriteRevision();
            const auto oldRows=launcher.rows();
            const QByteArray external=("{ \"formatVersion\": \"0.1-experimental\", \"favorites\": [\""+appId+"\"] }\n").toUtf8();
            favoriteReloadBoundary={QFile::encodeName(QFileInfo(favorites).fileName()),favorites,external};
            QVERIFY(!launcher.removeFavorite(appId,generation,revision));
            QVERIFY(favoriteReloadBoundary.injected && favoriteReloadBoundary.written);
            QFile readback(favorites); QVERIFY(readback.open(QIODevice::ReadOnly)); QCOMPARE(readback.readAll(),external);
            QVERIFY(launcher.generation()>generation);
            QVERIFY(launcher.favoriteRevision()!=revision);
            QVERIFY(!launcher.favoriteError().isEmpty()); QVERIFY(launcher.favoritesWritable());
            QCOMPARE(launcher.rows().size(),oldRows.size());
            for (const auto &row : launcher.rows()) {
                QCOMPARE(row.toMap().value("favoriteRevision").toString(),launcher.favoriteRevision());
                QCOMPARE(row.toMap().value("generation").toULongLong(),launcher.generation());
            }
            const auto fresh=launcher.generation();
            launcher.reloadFavorites(); launcher.setQuery("");
            QCOMPARE(launcher.generation(),fresh);
            QCOMPARE(launcher.rows().first().toMap().value("favoriteRevision").toString(),launcher.favoriteRevision());
        }
        const auto oldGeneration=launcher.generation();
        const auto oldRevision=launcher.favoriteRevision();
        saved.reload();
        QVERIFY(saved.pin("org.orla.OtherMissing.desktop",saved.revision()));
        QVERIFY(!launcher.removeFavorite(appId,oldGeneration,oldRevision));
        QCOMPARE(launcher.favorites().size(),2);
        QVERIFY(launcher.removeFavorite(appId,launcher.generation(),launcher.favoriteRevision()));
        QVERIFY(!launcher.removeFavorite(appId,oldGeneration,oldRevision));
        QVERIFY(launcher.favoriteError().isEmpty());
        QFile observed(aliases); QVERIFY(observed.open(QIODevice::ReadOnly)); QCOMPARE(observed.readAll(),QByteArray("{broken"));
    }
    void savedAppAliasFindsTheInstalledFixtureAfterAnotherQuery()
    {
        const auto receipt = qEnvironmentVariable("ORLA_TEST_RECEIPT");
        if (receipt.isEmpty()) QSKIP("Owned desktop fixture is required");
        const auto directory = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation) + "/orla";
        QVERIFY(QDir().mkpath(directory));
        QFile aliases(directory + "/launcher-aliases.json");
        QVERIFY(aliases.open(QIODevice::WriteOnly));
        aliases.write(R"({"formatVersion":"0.1-experimental","aliases":[{"alias":"ownalias","appId":"org.orla.OwnedLauncherFixture.desktop"}]})");
        aliases.close();
        LauncherControllerTestOwner owner;
        auto &launcher = owner.controller();
        launcher.setQuery("2+2");
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        launcher.setQuery("ownalias");
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        QVERIFY(!QFile::exists(receipt));
        QCOMPARE(launcher.rows().first().toMap().value("kind").toString(), QStringLiteral("alias"));
        QCOMPARE(launcher.rows().first().toMap().value("appId").toString(), QStringLiteral("org.orla.OwnedLauncherFixture.desktop"));
    }
    void appResultsOnlyRunOwnedFixtureAfterExplicitSelection()
    {
        const auto receipt = qEnvironmentVariable("ORLA_TEST_RECEIPT");
        if (receipt.isEmpty()) QSKIP("Owned desktop fixture was not provided; no installed app is launched");
        QFile::remove(receipt);
        LauncherControllerTestOwner controllerOwner;
        LauncherController &launcher = controllerOwner.controller();
        launcher.setQuery(QStringLiteral("OrlaOwnedLauncherFixture"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        QCOMPARE(launcher.rows().size(), 1);
        const auto row = launcher.rows().first().toMap();
        QCOMPARE(row.value("kind").toString(), QStringLiteral("app"));
        QCOMPARE(row.value("title").toString(), QStringLiteral("OrlaOwnedLauncherFixture"));
        QVERIFY(!QFile::exists(receipt)); // Typing never executes an app.
        QVERIFY(!launcher.execute(1, launcher.generation(), row.value("id").toString()));
        QVERIFY(!QFile::exists(receipt));
        QVERIFY(launcher.executeSelected());
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(receipt), 5000);
        QFile file(receipt);
        QVERIFY(file.open(QIODevice::ReadOnly));
        QCOMPARE(file.readAll(), QByteArray("owned-launcher-fixture\n"));
        QVERIFY(launcher.rows().isEmpty());
    }

    void steamSearchOnlyOpensTheCurrentExplicitSelection()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        QList<QUrl> opened;
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeSteamHelper(directory), [&opened](const QUrl &url) { opened.append(url); return true; });
        LauncherControllerTestOwner controllerOwner(&steam);
        LauncherController &launcher = controllerOwner.controller();
        steam.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_COMPARE_WITH_TIMEOUT(steam.status(), QStringLiteral("available"), 3000);

        launcher.setQuery(QStringLiteral("Synthetic Steam"));
        QTRY_VERIFY_WITH_TIMEOUT(launcher.status() == QStringLiteral("ready")
                                 && !launcher.rows().isEmpty(), 5000);
        int steamRow = -1;
        for (int row = 0; row < launcher.rows().size(); ++row) {
            if (launcher.rows()[row].toMap().value(QStringLiteral("kind")).toString()
                == QStringLiteral("steam")) steamRow = row;
        }
        QVERIFY(steamRow >= 0);
        launcher.select(steamRow);
        const QVariantMap old = launcher.rows()[steamRow].toMap();
        QVERIFY(opened.isEmpty());

        launcher.setQuery(QStringLiteral("different"));
        QVERIFY(!launcher.execute(steamRow, old.value(QStringLiteral("generation")).toULongLong(),
                                  old.value(QStringLiteral("id")).toString()));
        QVERIFY(opened.isEmpty());

        launcher.setQuery(QStringLiteral("Synthetic Steam"));
        QTRY_VERIFY_WITH_TIMEOUT(launcher.status() == QStringLiteral("ready"), 5000);
        for (int row = 0; row < launcher.rows().size(); ++row) {
            const QVariantMap current = launcher.rows()[row].toMap();
            if (current.value(QStringLiteral("kind")).toString() != QStringLiteral("steam")) continue;
            launcher.select(row);
            QVERIFY(launcher.execute(row, current.value(QStringLiteral("generation")).toULongLong(),
                                     current.value(QStringLiteral("id")).toString()));
            break;
        }
        QCOMPARE(opened, QList<QUrl>{QUrl(QStringLiteral("steam://rungameid/42"))});
        launcher.setQuery("");
        QTest::qWait(100);
        QVERIFY(launcher.rows().isEmpty());
        QCOMPARE(launcher.status(),QStringLiteral("idle"));
        QCOMPARE(opened.size(),1);
    }
};
QTEST_MAIN(LauncherTests)
#include "LauncherTests.moc"
