#include <QtTest>
#include <cstdio>
#include <QDBusArgument>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusContext>
#include <QDBusMetaType>
#include <QDBusObjectPath>
#include <QProcess>
#include <QTemporaryDir>
#include <QFileInfo>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <cerrno>
#include <csignal>
#include <unistd.h>
#include <QScopeGuard>
#include <QThread>
#include <KGlobalAccel>
#include <KGlobalShortcutInfo>
#include "BusChecks.h"
#include "LauncherController.h"
#include "LauncherControllerTestOwner.h"
#include "WindowSession.h"

// The daemon is a wire-boundary fixture, not a replacement for KGlobalAccel in the launcher.
struct ShortcutInfo {
    QString action = QStringLiteral("orla-search-open");
    QString component = QStringLiteral("org.orla.Launcher");
    QString context = QStringLiteral("default");
    QList<int> keys;
};
Q_DECLARE_METATYPE(ShortcutInfo)
QDBusArgument &operator<<(QDBusArgument &arg, const ShortcutInfo &info)
{
    arg.beginStructure();
    arg << info.action << info.action << info.component << info.component << info.context << info.context;
    arg << info.keys << QList<int>{};
    arg.endStructure();
    return arg;
}
const QDBusArgument &operator>>(const QDBusArgument &arg, ShortcutInfo &info)
{
    QString ignored;
    QList<int> defaults;
    arg.beginStructure();
    arg >> info.action >> ignored >> info.component >> ignored >> info.context >> ignored >> info.keys >> defaults;
    arg.endStructure();
    return arg;
}

class ShortcutComponent final : public QObject
{
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.kde.kglobalaccel.Component")
public:
    bool exists = false;
    bool present = false;
    QString action = QStringLiteral("orla-search-open");
    QStringList contexts{QStringLiteral("default")};
public Q_SLOTS:
    QStringList getShortcutContexts() const { return contexts; }
    QStringList shortcutNames(const QString &) const { return exists ? QStringList{action} : QStringList{}; }
    bool isActive() const { return present; }
Q_SIGNALS:
    void globalShortcutPressed(const QString &component, const QString &action, qlonglong timestamp);
    void globalShortcutRepeated(const QString &component, const QString &action, qlonglong timestamp);
    void globalShortcutReleased(const QString &component, const QString &action, qlonglong timestamp);
};

class ShortcutDaemon final : public QObject, protected QDBusContext
{
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.kde.KGlobalAccel")
public:
    ShortcutComponent component;
    QList<QKeySequence> keys;
    QList<QKeySequence> defaults;
    QList<ShortcutInfo> competitors;
    QStringList lastAction;
    bool conflictAfterRegistration = false;
    bool failInventory = false;
    bool failReadback = false;
    bool alternateCurrent = false;
    bool alternatePresent = false;
    QList<QKeySequence> alternateKeys;
    QList<QKeySequence> alternateDefaults;
    int registrations = 0;
    int unregisters = 0;
    int inactive = 0;
    QDBusConnection bus{QStringLiteral("orla-shortcut-fixture")};

    bool start()
    {
        bus = QDBusConnection::connectToBus(qEnvironmentVariable("DBUS_SESSION_BUS_ADDRESS"), QStringLiteral("orla-shortcut-fixture"));
        return bus.registerObject(QStringLiteral("/kglobalaccel"), this, QDBusConnection::ExportAllSlots | QDBusConnection::ExportAllSignals)
            && bus.registerObject(QStringLiteral("/component/orla"), &component, QDBusConnection::ExportAllSlots | QDBusConnection::ExportAllSignals)
            && bus.registerService(QStringLiteral("org.kde.kglobalaccel"));
    }
    void reset()
    {
        component.exists = component.present = false;
        component.action = QStringLiteral("orla-search-open");
        component.contexts = {QStringLiteral("default")};
        keys.clear(); defaults.clear(); competitors.clear(); lastAction.clear();
        conflictAfterRegistration = failInventory = failReadback = alternateCurrent = alternatePresent = false;
        alternateKeys.clear(); alternateDefaults.clear();
        registrations = unregisters = inactive = 0;
    }
public Q_SLOTS:
    QDBusObjectPath getComponent(const QString &)
    {
        if (!component.exists) {
            sendErrorReply(QStringLiteral("org.kde.kglobalaccel.NoSuchComponent"), QStringLiteral("No owned component"));
            return QDBusObjectPath(QStringLiteral("/"));
        }
        return QDBusObjectPath(QStringLiteral("/component/orla"));
    }
    void doRegister(const QStringList &action) { component.exists = true; component.action = action.at(1); lastAction = action; ++registrations; }
    QList<QKeySequence> shortcutKeys(const QStringList &)
    {
        if (failReadback) { sendErrorReply(QDBusError::Failed, QStringLiteral("Owned readback failure")); return {}; }
        return keys;
    }
    QList<QKeySequence> setShortcutKeys(const QStringList &action, const QList<QKeySequence> &requested, uint flags)
    {
        const bool wasPresent = component.present;
        lastAction = action;
        if (flags & 8) defaults = requested;
        else if ((flags & 4) || (!wasPresent && keys.isEmpty() && registrations == 1 && !configured)) keys = requested;
        if (flags & 2) component.present = true;
        if (!(flags & 8)) configured = true;
        if (conflictAfterRegistration && (flags & 2)) {
            ShortcutInfo info;
            info.action = QStringLiteral("foreign-action");
            info.component = QStringLiteral("foreign.component");
            info.keys = {requested.first()[0].toCombined()};
            competitors = {info};
        }
        return (flags & 8) ? defaults : keys;
    }
    QList<ShortcutInfo> globalShortcutsByKey(const QKeySequence &key, KGlobalAccel::MatchType)
    {
        if (failInventory) {
            sendErrorReply(QDBusError::Failed, QStringLiteral("Owned inventory failure"));
            return {};
        }
        QList<ShortcutInfo> result;
        if (component.exists && keys.contains(key)) {
            ShortcutInfo info;
            info.action = component.action;
            if (!lastAction.isEmpty()) info.component = lastAction.first();
            info.keys = {key[0].toCombined()}; result.append(info);
        }
        for (const auto &info : competitors) if (info.keys.contains(key[0].toCombined())) result.append(info);
        return result;
    }
    bool isGlobalShortcutAvailable(int, const QString &) const { return competitors.isEmpty(); }
    void setInactive(const QStringList &action)
    {
        if (alternateCurrent && !action.first().endsWith(QStringLiteral("|default"))) alternatePresent = false;
        else component.present = false;
        ++inactive;
    }
    void unregister(const QString &, const QString &) { ++unregisters; component.exists = false; keys.clear(); }
Q_SIGNALS:
    void yourShortcutsChanged(const QStringList &action, const QList<QKeySequence> &keys);
public:
    bool configured = false;
};

class ShortcutTests final : public QObject
{
    Q_OBJECT
    QThread thread;
    ShortcutDaemon *daemon = nullptr;
    void withDaemon(const std::function<void()> &operation)
    {
        QMetaObject::invokeMethod(daemon, operation, Qt::BlockingQueuedConnection);
    }
    bool acquireLease()
    {
        const auto lease = QDBusConnection::sessionBus().interface()->registerService(QStringLiteral("org.orla.Launcher"),
            QDBusConnectionInterface::DontQueueService, QDBusConnectionInterface::DontAllowReplacement);
        return lease.isValid() && lease.value() == QDBusConnectionInterface::ServiceRegistered;
    }
private Q_SLOTS:
    void initTestCase()
    {
        verifyPrivateTestBus();
        KGlobalAccel::self(); // Registers the pinned KF wire types, without activating the daemon.
        qDBusRegisterMetaType<ShortcutInfo>();
        qDBusRegisterMetaType<QList<ShortcutInfo>>();
        daemon = new ShortcutDaemon;
        daemon->component.setParent(daemon);
        daemon->moveToThread(&thread);
        connect(&thread, &QThread::finished, daemon, &QObject::deleteLater);
        thread.start();
        bool started = false;
        withDaemon([&] { started = daemon->start(); });
        QVERIFY(started);
        QTest::qWait(30); // Drain the fixture's initial owner notification before constructing any session.
    }
    void cleanupTestCase() { thread.quit(); QVERIFY(thread.wait(3000)); }
    void init() { withDaemon([&] { daemon->reset(); daemon->configured = false; }); }
    void cleanup()
    {
        QDBusConnection::sessionBus().unregisterService(QStringLiteral("org.orla.Launcher"));
        QCoreApplication::processEvents();
    }

    void managedStartupOwnsOneStableActionAndRefusesADuplicate()
    {
        QProcess first;
        QByteArray output;
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        environment.insert(QStringLiteral("QT_LOGGING_RULES"), QStringLiteral("*.info=true"));
        environment.insert(QStringLiteral("QT_FORCE_STDERR_LOGGING"), QStringLiteral("1"));
        first.setProcessEnvironment(environment);
        first.setProcessChannelMode(QProcess::MergedChannels);
        first.start(QStringLiteral(ORLA_TEST_LAUNCHER), {QStringLiteral("--managed-shortcuts"), QStringLiteral("--start-hidden")});
        const auto cleanup = qScopeGuard([&] { if (!output.contains("Orla Launcher ready;")) qWarning().noquote() << output;
            first.terminate(); if (!first.waitForFinished(3000)) { first.kill(); first.waitForFinished(); } });
        QTRY_VERIFY_WITH_TIMEOUT(([&] { output += first.readAll(); return output.contains("Orla Launcher ready;") || first.state() == QProcess::NotRunning; })(), 5000);
        QVERIFY2(output.contains("Orla Launcher ready;"), output.constData());
        QVERIFY(output.contains("visible= false"));
        QStringList action;
        withDaemon([&] { action = daemon->lastAction; });
        QCOMPARE(action.mid(0, 2), QStringList({QStringLiteral("org.orla.Launcher"), QStringLiteral("orla-search-open")}));
        QProcess second;
        second.setProcessEnvironment(environment);
        second.setProcessChannelMode(QProcess::MergedChannels);
        second.start(QStringLiteral(ORLA_TEST_LAUNCHER), {QStringLiteral("--managed-shortcuts")});
        QVERIFY(second.waitForFinished(5000));
        QCOMPARE(second.exitCode(), 2);
        QVERIFY(second.readAll().contains("já está em execução"));
        int registrations = 0;
        withDaemon([&] { registrations = daemon->registrations; });
        QCOMPARE(registrations, 1);
    }

    void managedSessionRequiresItsOwnBusLeaseBeforeRegistering()
    {
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(session.shortcutText().isEmpty());
        QVERIFY(!session.notice().isEmpty());
        int registrations = 0;
        withDaemon([&] { registrations = daemon->registrations; });
        QCOMPARE(registrations, 0);
    }

    void persistentKeysSurviveDestructionAndAutoloadInANewSession()
    {
        QVERIFY(acquireLease());
        const QKeySequence fallback(QStringLiteral("Ctrl+Alt+Meta+O"));
        const QList<QKeySequence> saved{QKeySequence(QStringLiteral("Meta")), fallback};
        withDaemon([&] { daemon->component.exists = daemon->configured = true; daemon->keys = saved; });
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        {
            WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                                  nullptr, WindowSession::ShortcutMode::Managed);
            QCOMPARE(session.shortcutText(), QStringLiteral("Meta / ") + fallback.toString(QKeySequence::NativeText));
            QList<QKeySequence> observed, defaults;
            withDaemon([&] { observed = daemon->keys; defaults = daemon->defaults; });
            QCOMPARE(observed, saved);
            QCOMPARE(defaults, QList<QKeySequence>{fallback});
        }
        int inactive = 0, unregisters = 0;
        QTRY_VERIFY_WITH_TIMEOUT(([&] { withDaemon([&] { inactive = daemon->inactive; }); return inactive == 1; })(), 1000);
        withDaemon([&] { unregisters = daemon->unregisters; });
        QCOMPARE(unregisters, 0);
        WindowSession restarted(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                                nullptr, WindowSession::ShortcutMode::Managed);
        QCOMPARE(restarted.shortcutText(), QStringLiteral("Meta / ") + fallback.toString(QKeySequence::NativeText));
        QList<QKeySequence> observed;
        withDaemon([&] { observed = daemon->keys; });
        QCOMPARE(observed, saved);
    }

    void customizedOrDisabledSavedKeysAreNeverReplaced_data()
    {
        QTest::addColumn<QString>("saved");
        QTest::newRow("custom") << QStringLiteral("Ctrl+F12");
        QTest::newRow("disabled") << QString();
    }
    void customizedOrDisabledSavedKeysAreNeverReplaced()
    {
        QFETCH(QString, saved);
        QVERIFY(acquireLease());
        const QList<QKeySequence> expected = saved.isEmpty() ? QList<QKeySequence>{} : QList<QKeySequence>{QKeySequence(saved)};
        withDaemon([&] { daemon->component.exists = daemon->configured = true; daemon->keys = expected; });
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QCOMPARE(session.shortcutText(), saved.isEmpty() ? QString() : QKeySequence(saved).toString(QKeySequence::NativeText));
        if (saved.isEmpty()) { QVERIFY(window.isVisible()); QVERIFY(!session.notice().isEmpty()); }
        QList<QKeySequence> observed;
        withDaemon([&] { observed = daemon->keys; });
        QCOMPARE(observed, expected);
    }

    void competingActionsAndContextsRefuseBeforeRegistration_data()
    {
        QTest::addColumn<QString>("component");
        QTest::addColumn<QString>("action");
        QTest::addColumn<QString>("context");
        QTest::newRow("foreign") << QStringLiteral("foreign.component") << QStringLiteral("other") << QStringLiteral("default");
        QTest::newRow("same-component-other-action") << QStringLiteral("org.orla.Launcher") << QStringLiteral("other") << QStringLiteral("default");
        QTest::newRow("same-action-other-context") << QStringLiteral("org.orla.Launcher") << QStringLiteral("orla-search-open") << QStringLiteral("other-context");
    }
    void competingActionsAndContextsRefuseBeforeRegistration()
    {
        QFETCH(QString, component); QFETCH(QString, action); QFETCH(QString, context);
        QVERIFY(acquireLease());
        ShortcutInfo competitor; competitor.component = component; competitor.action = action; competitor.context = context;
        competitor.keys = {QKeySequence(QStringLiteral("Ctrl+Alt+Meta+O"))[0].toCombined()};
        withDaemon([&] { daemon->competitors = {competitor}; });
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(session.shortcutText().isEmpty());
        QVERIFY(window.isVisible());
        int registrations = -1;
        withDaemon([&] { registrations = daemon->registrations; });
        QCOMPARE(registrations, 0);
    }

    void exactKeyReadbackDoesNotAdmitAConflictIntroducedDuringRegistration()
    {
        QVERIFY(acquireLease());
        withDaemon([&] { daemon->conflictAfterRegistration = true; });
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(session.shortcutText().isEmpty());
        QVERIFY(window.isVisible());
        QVERIFY(!session.notice().isEmpty());
        QList<QKeySequence> keys;
        int unregisters = -1;
        withDaemon([&] { keys = daemon->keys; unregisters = daemon->unregisters; });
        QCOMPARE(keys, QList<QKeySequence>{QKeySequence(QStringLiteral("Ctrl+Alt+Meta+O"))});
        QCOMPARE(unregisters, 0);
        bool present = true;
        withDaemon([&] { present = daemon->component.present; });
        QVERIFY(!present);
    }

    void inventoryAndReadbackFailuresRemainVisibleWithoutErasingSavedKeys_data()
    {
        QTest::addColumn<bool>("inventory");
        QTest::newRow("inventory") << true;
        QTest::newRow("readback") << false;
    }
    void inventoryAndReadbackFailuresRemainVisibleWithoutErasingSavedKeys()
    {
        QFETCH(bool, inventory);
        QVERIFY(acquireLease());
        const QList<QKeySequence> saved{QKeySequence(QStringLiteral("Ctrl+Alt+Meta+O"))};
        withDaemon([&] {
            daemon->component.exists = daemon->configured = true; daemon->keys = saved;
            daemon->failInventory = inventory; daemon->failReadback = !inventory;
        });
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        {
            WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                                  nullptr, WindowSession::ShortcutMode::Managed);
            QVERIFY(session.shortcutText().isEmpty());
            QVERIFY(window.isVisible());
        }
        QList<QKeySequence> observed;
        int registrations = -1, unregisters = -1;
        withDaemon([&] { observed = daemon->keys; registrations = daemon->registrations; unregisters = daemon->unregisters; });
        QCOMPARE(observed, saved);
        QCOMPARE(registrations, 0);
        QCOMPARE(unregisters, 0);
    }

    void liveConfigurationChangesNotifyAndDisabledShortcutRevealsHiddenWindow()
    {
        QVERIFY(acquireLease());
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(!session.shortcutText().isEmpty());
        QSignalSpy changes(&session, &WindowSession::shortcutTextChanged);
        const QList<QKeySequence> updated{QKeySequence(QStringLiteral("Ctrl+Alt+Meta+O")), QKeySequence(QStringLiteral("Meta"))};
        withDaemon([&] { daemon->keys = updated; emit daemon->yourShortcutsChanged(daemon->lastAction, updated); });
        QTRY_COMPARE_WITH_TIMEOUT(session.shortcutText(), updated.first().toString(QKeySequence::NativeText) + QStringLiteral(" / Meta"), 1000);
        QCOMPARE(changes.count(), 1);
        window.hide();
        withDaemon([&] { daemon->keys.clear(); emit daemon->yourShortcutsChanged(daemon->lastAction, {}); });
        QTRY_VERIFY_WITH_TIMEOUT(session.shortcutText().isEmpty(), 1000);
        QVERIFY(window.isVisible());
        QVERIFY(!session.notice().isEmpty());
        QCOMPARE(changes.count(), 2);
        bool present = true;
        withDaemon([&] { present = daemon->component.present; });
        QVERIFY(!present);
        withDaemon([&] { daemon->keys = updated; emit daemon->yourShortcutsChanged(daemon->lastAction, updated); });
        QTRY_VERIFY_WITH_TIMEOUT(!session.shortcutText().isEmpty(), 1000);
        withDaemon([&] { present = daemon->component.present; });
        QVERIFY(present);
        QCOMPARE(changes.count(), 3);
    }

    void daemonDisappearanceRevealsWindowAndReturnRevalidatesSavedKeys()
    {
        QVERIFY(acquireLease());
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        const QString initial = session.shortcutText();
        QVERIFY(!initial.isEmpty());
        window.hide();
        withDaemon([&] { daemon->bus.unregisterService(QStringLiteral("org.kde.kglobalaccel")); });
        QTRY_VERIFY_WITH_TIMEOUT(session.shortcutText().isEmpty(), 1000);
        QVERIFY(window.isVisible());
        bool registered = false;
        withDaemon([&] { registered = daemon->bus.registerService(QStringLiteral("org.kde.kglobalaccel")); });
        QVERIFY(registered);
        QTRY_COMPARE_WITH_TIMEOUT(session.shortcutText(), initial, 1000);
        QVERIFY(window.isVisible());
    }

    void foreignConflictWithoutAnOwnerSignalRevealsWindowAndReleasesNativeKeys()
    {
        QVERIFY(acquireLease());
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(!session.shortcutText().isEmpty());
        window.hide();
        ShortcutInfo competitor;
        competitor.component = QStringLiteral("foreign.component");
        competitor.action = QStringLiteral("foreign-action");
        competitor.keys = {QKeySequence(QStringLiteral("Ctrl+Alt+Meta+O"))[0].toCombined()};
        withDaemon([&] { daemon->competitors = {competitor}; });
        QTRY_VERIFY_WITH_TIMEOUT(session.shortcutText().isEmpty(), 1500);
        QVERIFY(window.isVisible());
        bool present = true;
        withDaemon([&] { present = daemon->component.present; });
        QVERIFY(!present);
        withDaemon([&] { daemon->competitors.clear(); });
        QTRY_VERIFY_WITH_TIMEOUT(!session.shortcutText().isEmpty(), 1500);
        withDaemon([&] { present = daemon->component.present; });
        QVERIFY(present);
    }

    void alternateContextsRefuseWithoutChangingSavedDefaults()
    {
        QVERIFY(acquireLease());
        const QList<QKeySequence> active{QKeySequence(QStringLiteral("Ctrl+Alt+Meta+O"))};
        const QList<QKeySequence> defaults{QKeySequence(QStringLiteral("Ctrl+F12"))};
        withDaemon([&] {
            daemon->component.exists = daemon->configured = true;
            daemon->component.contexts = {QStringLiteral("default"), QStringLiteral("alternate")};
            daemon->keys = active; daemon->defaults = defaults;
        });
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(session.shortcutText().isEmpty());
        QVERIFY(window.isVisible());
        QList<QKeySequence> observedDefaults, observedKeys;
        int registrations = -1;
        withDaemon([&] { observedDefaults = daemon->defaults; observedKeys = daemon->keys; registrations = daemon->registrations; });
        QCOMPARE(observedDefaults, defaults);
        QCOMPARE(observedKeys, active);
        QCOMPARE(registrations, 0);
    }

    void temporaryModeStillUnregistersItsOwnSessionAction()
    {
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        {
            WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+F12"));
            QCOMPARE(session.shortcutText(), QKeySequence(QStringLiteral("Ctrl+F12")).toString(QKeySequence::NativeText));
            QStringList action;
            withDaemon([&] { action = daemon->lastAction; });
            QCOMPARE(action.first(), QCoreApplication::applicationName());
            QCOMPARE(action.at(1), QStringLiteral("_k_session:orla-launcher-open"));
        }
        int unregisters = 0;
        QTRY_VERIFY_WITH_TIMEOUT(([&] { withDaemon([&] { unregisters = daemon->unregisters; }); return unregisters == 1; })(), 1000);
        int inactive = -1;
        withDaemon([&] { inactive = daemon->inactive; });
        QCOMPARE(inactive, 0);
    }

    void runtimeAlternateContextReleasesOnlyTheOwnedDefaultAction()
    {
        QVERIFY(acquireLease());
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        auto session = std::make_unique<WindowSession>(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                                                     nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(!session->shortcutText().isEmpty());
        window.hide();
        const QList<QKeySequence> alternateKeys{QKeySequence(QStringLiteral("Ctrl+F12"))};
        const QList<QKeySequence> alternateDefaults{QKeySequence(QStringLiteral("Ctrl+F11"))};
        withDaemon([&] {
            daemon->component.contexts = {QStringLiteral("default"), QStringLiteral("alternate")};
            daemon->alternateCurrent = daemon->alternatePresent = true;
            daemon->alternateKeys = alternateKeys; daemon->alternateDefaults = alternateDefaults;
        });
        QTRY_VERIFY_WITH_TIMEOUT(session->shortcutText().isEmpty(), 1500);
        QVERIFY(window.isVisible());
        bool defaultPresent = true, alternatePresent = false;
        QList<QKeySequence> observedKeys, observedDefaults;
        withDaemon([&] {
            defaultPresent = daemon->component.present; alternatePresent = daemon->alternatePresent;
            observedKeys = daemon->alternateKeys; observedDefaults = daemon->alternateDefaults;
        });
        QVERIFY(!defaultPresent);
        QVERIFY(alternatePresent);
        QCOMPARE(observedKeys, alternateKeys);
        QCOMPARE(observedDefaults, alternateDefaults);
        session.reset();
        QCoreApplication::processEvents();
        withDaemon([&] { alternatePresent = daemon->alternatePresent; });
        QVERIFY(alternatePresent);
    }

    void healthyDaemonShortcutSignalDispatchesToTheOwnedWindow()
    {
        QVERIFY(acquireLease());
        LauncherControllerTestOwner owner;
        QQuickWindow window;
        WindowSession session(&owner.controller(), &window, true, QStringLiteral("Ctrl+Alt+Meta+O"),
                              nullptr, WindowSession::ShortcutMode::Managed);
        QVERIFY(!session.shortcutText().isEmpty());
        QVERIFY(!window.isVisible());
        withDaemon([&] { emit daemon->component.globalShortcutPressed(QStringLiteral("org.orla.Launcher"),
            QStringLiteral("orla-search-open"), 0); });
        QTRY_VERIFY_WITH_TIMEOUT(window.isVisible(), 1000);
        // This proves the D-Bus -> KF -> QAction -> window path, not native key delivery or focus.
    }

    void conflictingManagedOptionsFailBeforeRegistering_data()
    {
        QTest::addColumn<QStringList>("arguments");
        QTest::newRow("temporary-key") << QStringList{QStringLiteral("--managed-shortcuts"), QStringLiteral("--shortcut"), QStringLiteral("Ctrl+F12")};
        QTest::newRow("no-global") << QStringList{QStringLiteral("--managed-shortcuts"), QStringLiteral("--no-global-shortcut")};
    }
    void conflictingManagedOptionsFailBeforeRegistering()
    {
        QFETCH(QStringList, arguments);
        QProcess process;
        process.start(QStringLiteral(ORLA_TEST_LAUNCHER), arguments);
        QVERIFY(process.waitForFinished(3000));
        QCOMPARE(process.exitCode(), 2);
        int registrations = -1;
        withDaemon([&] { registrations = daemon->registrations; });
        QCOMPARE(registrations, 0);
        const QDBusReply<bool> registered = QDBusConnection::sessionBus().interface()->isServiceRegistered(QStringLiteral("org.orla.Launcher"));
        QVERIFY(registered.isValid());
        QVERIFY(!registered.value());
    }

    void relocatedBuiltinsUseOnlyOwnedHelpers_data()
    {
        QTest::addColumn<QString>("mode");
        for (const auto &mode : {"relocated", "empty", "relative", "override", "missing"})
            QTest::newRow(mode) << QString::fromLatin1(mode);
    }
    void relocatedBuiltinsUseOnlyOwnedHelpers()
    {
        QFETCH(QString, mode);
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        const QString original = directory.filePath(QStringLiteral("original tree with spaces"));
        const QString relocated = directory.filePath(QStringLiteral("relocated tree with spaces"));
        const QString receipts = directory.filePath(QStringLiteral("receipts"));
        const QString unrelated = directory.filePath(QStringLiteral("unrelated cwd"));
        QVERIFY(QDir().mkpath(original + QStringLiteral("/bin")));
        QVERIFY(QDir().mkpath(original + QStringLiteral("/libexec")));
        QVERIFY(QDir().mkpath(original + QStringLiteral("/test-root")));
        QVERIFY(QDir().mkpath(receipts));
        QVERIFY(QDir().mkpath(unrelated));
        const QString harness = original + QStringLiteral("/bin/owned-helper-harness");
        QVERIFY(QFile::copy(QStringLiteral(ORLA_TEST_HELPER_HARNESS), harness));
        const QByteArray prelude = QByteArray("import base64,json,os,pathlib,sys\nassert sys.flags.isolated and sys.flags.dont_write_bytecode\n")
            + "receipt=pathlib.Path(base64.b64decode('" + receipts.toUtf8().toBase64() + "').decode())/pathlib.Path(__file__).name\n"
              "receipt.write_text(json.dumps({'helper':str(pathlib.Path(__file__).resolve()),'cwd':os.getcwd(),'pid':os.getpid(),'args':sys.argv[1:]}))\n";
        const QByteArray aiBody = R"PY(assert sys.argv[1]=='detect' and len(sys.argv)==6 and sys.argv[2]=='--runtime-root' and sys.argv[4]=='--runtime-root-id'
record=json.loads(receipt.read_text())
record['runtime_root']=sys.argv[3]
receipt.write_text(json.dumps(record))
caps={'installation':'absent','anonymous_protocol':'absent','authentication':'unknown','inference':'absent','cancellation':'absent','usage_reporting':'unknown'}
items=[('codex','Codex','owned_app_server'),('claude','Claude Code','official_terminal_handoff'),('opencode','OpenCode','selected_local_server'),('ollama','Ollama','selected_local_server'),('lmstudio','LM Studio','selected_local_server')]
print(json.dumps({'schemaVersion':1,'providers':[{'id':i,'displayName':n,'enabled':False,'clientVersion':None,'capabilities':caps,'route':r,'messageCode':'cli_not_found'} for i,n,r in items]}))
)PY";
        const QByteArray steamBody = R"PY(assert sys.argv[1]=='scan'
print(json.dumps({'apps':[],'connection':'unknown','errors':[],'libraries':[],'ownership':'unknown','roots':[{'id':'root-0','kind':'native','status':'absent'}],'schema_version':'0.1-experimental','status':'absent'}))
)PY";
        const QByteArray textBody = R"PY(assert sys.argv[1:]==['run-ollama']
import importlib.util
spec=importlib.util.spec_from_file_location('owned_transport',pathlib.Path(__file__).resolve().with_name('ai_text_transport.py'))
transport=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
r=json.loads(sys.stdin.buffer.read())
b={'schemaVersion':1,'requestId':r['requestId']}
def emit(seq,kind,**extra):
 print(json.dumps(dict(b,sequence=seq,type=kind,**extra)),flush=True)
emit(0,'started',provider='ollama_local',destination=r['endpoint'],model=r['model'])
emit(1,'delta',text=transport.output)
emit(2,'completed',finishReason='stop',usage={'status':'unknown','inputTokens':None,'outputTokens':None,'totalTokens':None},cost={'status':'unknown','currency':None,'amount':None})
)PY";
        const QByteArray transportBody = R"PY(import importlib.util,pathlib
spec=importlib.util.spec_from_file_location('owned_contract',pathlib.Path(__file__).resolve().with_name('ai_text.py'))
contract=importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)
output=contract.output
)PY";
        QMap<QString, QByteArray> files{{QStringLiteral("ai.py"), prelude + aiBody},
            {QStringLiteral("steam.py"), prelude + steamBody},
            {QStringLiteral("ai_text_ollama.py"), prelude + textBody},
            {QStringLiteral("ai_text_transport.py"), transportBody},
            {QStringLiteral("ai_text.py"), QByteArray("output='owned closure'\n")}};
        if (mode == QStringLiteral("override")) {
            files.insert(QStringLiteral("ai-override.py"), prelude + aiBody);
            files.insert(QStringLiteral("text-override.py"), prelude + textBody);
        }
        if (mode == QStringLiteral("missing")) files.clear();
        for (auto it = files.cbegin(); it != files.cend(); ++it) {
            QFile file(original + QStringLiteral("/libexec/") + it.key());
            QVERIFY(file.open(QIODevice::WriteOnly));
            QCOMPARE(file.write(it.value()), it.value().size());
            file.close();
        }
        QVERIFY(QDir().rename(original, relocated));
        QVERIFY(!QFile::exists(original));
        const auto cleanupPermissions = qScopeGuard([&] {
            QFile::setPermissions(relocated, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner);
            QFile::setPermissions(relocated + QStringLiteral("/libexec"), QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner);
        });
        QMap<QString, QFileDevice::Permissions> stagedPermissions;
        for (const auto &name : files.keys()) {
            const QString path = relocated + QStringLiteral("/libexec/") + name;
            QVERIFY(QFile::setPermissions(path, QFileDevice::ReadOwner));
            stagedPermissions.insert(name, QFileInfo(path).permissions());
        }
        QVERIFY(QFile::setPermissions(relocated + QStringLiteral("/libexec"), QFileDevice::ReadOwner | QFileDevice::ExeOwner));
        QVERIFY(QFile::setPermissions(relocated, QFileDevice::ReadOwner | QFileDevice::ExeOwner));
        QProcess process;
        auto environment = QProcessEnvironment::systemEnvironment();
        environment.insert(QStringLiteral("ORLA_TEST_HELPER_ROOT"), relocated);
        environment.insert(QStringLiteral("ORLA_TEST_HELPER_MODE"), mode);
        process.setProcessEnvironment(environment);
        process.setWorkingDirectory(unrelated);
        process.setProcessChannelMode(QProcess::MergedChannels);
        QStringList arguments{QStringLiteral("--no-global-shortcut")};
        if (mode == QStringLiteral("empty")) arguments << QStringLiteral("--ai-helper=") << QStringLiteral("--ai-text-helper=");
        if (mode == QStringLiteral("relative")) arguments << QStringLiteral("--ai-helper=libexec/ai.py") << QStringLiteral("--ai-text-helper=libexec/ai_text_ollama.py");
        if (mode == QStringLiteral("override")) arguments << QStringLiteral("--ai-helper=") + relocated + QStringLiteral("/libexec/ai-override.py")
                                                        << QStringLiteral("--ai-text-helper=") + relocated + QStringLiteral("/libexec/text-override.py");
        QByteArray output;
        const auto cleanupProcess = qScopeGuard([&] {
            if (process.state() != QProcess::NotRunning) { process.kill(); process.waitForFinished(1000); }
            if (QTest::currentTestFailed()) std::fprintf(stderr, "%s\n", output.constData());
        });
        process.start(relocated + QStringLiteral("/bin/owned-helper-harness"), arguments);
        QTRY_VERIFY_WITH_TIMEOUT(([&] { output += process.readAll(); return process.state() == QProcess::NotRunning; })(), 2200);
        output += process.readAll();
        QVERIFY2(output.size() <= 65536, "Owned relocation harness exceeded output budget");
        QCOMPARE(process.exitStatus(), QProcess::NormalExit);
        QVERIFY2(process.exitCode() == 0, output.constData());
        QVERIFY2(output.contains("ORLA_HELPER_RESULTS_SETTLED") && output.contains("ORLA_HELPER_EXIT settled=1"), output.constData());
        QStringList expected;
        if (mode != QStringLiteral("missing")) expected << QStringLiteral("steam.py");
        if (mode == QStringLiteral("relocated")) expected << QStringLiteral("ai.py") << QStringLiteral("ai_text_ollama.py");
        if (mode == QStringLiteral("override")) expected << QStringLiteral("ai-override.py") << QStringLiteral("text-override.py");
        expected.sort();
        QCOMPARE(QDir(receipts).entryList(QDir::Files, QDir::Name), expected);
        for (const auto &name : expected) {
            QFile receipt(receipts + QLatin1Char('/') + name);
            QVERIFY(receipt.open(QIODevice::ReadOnly));
            const QJsonObject record = QJsonDocument::fromJson(receipt.readAll()).object();
            QCOMPARE(record.value(QStringLiteral("helper")).toString(), relocated + QStringLiteral("/libexec/") + name);
            const qint64 pid = record.value(QStringLiteral("pid")).toInteger();
            QVERIFY(pid > 1);
            errno = 0;
            QVERIFY(::kill(static_cast<pid_t>(pid), 0) == -1 && errno == ESRCH);
            if (name == QStringLiteral("ai.py") || name == QStringLiteral("ai-override.py")) {
                // Provider AI carries its private runtime by argument, not by cwd.
                QCOMPARE(record.value(QStringLiteral("cwd")).toString(), unrelated);
                const QString runtime = record.value(QStringLiteral("runtime_root")).toString();
                QVERIFY(runtime.startsWith(qEnvironmentVariable("XDG_RUNTIME_DIR") + QLatin1Char('/')));
                QVERIFY(!QFile::exists(runtime));
            } else if (name == QStringLiteral("steam.py")) {
                QCOMPARE(record.value(QStringLiteral("cwd")).toString(), unrelated);
            } else {
                const QString runtime = record.value(QStringLiteral("cwd")).toString();
                QVERIFY(runtime.startsWith(qEnvironmentVariable("XDG_RUNTIME_DIR") + QLatin1Char('/')));
                QVERIFY(!QFile::exists(runtime));
            }
        }
        QStringList expectedFiles = files.keys();
        expectedFiles.sort();
        QCOMPARE(QDir(relocated + QStringLiteral("/libexec")).entryList(QDir::AllEntries | QDir::NoDotAndDotDot, QDir::Name), expectedFiles);
        for (auto it = files.cbegin(); it != files.cend(); ++it) {
            QFile file(relocated + QStringLiteral("/libexec/") + it.key());
            QVERIFY(file.open(QIODevice::ReadOnly));
            QCOMPARE(file.readAll(), it.value());
            QCOMPARE(QFileInfo(file).permissions(), stagedPermissions.value(it.key()));
        }
    }

    void acceptedWorkSettlesBeforeProductionQuit_data()
    {
        QTest::addColumn<QString>("mode");
        for (const auto &mode : {"idle", "escape", "ctrlq", "close", "escape-secondary-before", "ctrlq-secondary-after", "close-secondary-after"})
            QTest::newRow(mode) << QString::fromLatin1(mode);
    }
    void acceptedWorkSettlesBeforeProductionQuit()
    {
        QFETCH(QString, mode);
        QProcess process;
        auto environment = QProcessEnvironment::systemEnvironment();
        environment.insert(QStringLiteral("ORLA_TEST_QUIT_MODE"), mode);
        process.setProcessEnvironment(environment);
        process.setProcessChannelMode(QProcess::MergedChannels);
        QByteArray output;
        const auto cleanup = qScopeGuard([&] {
            if (process.state() != QProcess::NotRunning) {
                process.terminate();
                if (!process.waitForFinished(1000)) { process.kill(); process.waitForFinished(1000); }
            }
            if (QTest::currentTestFailed()) std::fprintf(stderr, "%s\n", output.constData());
        });
        process.start(QStringLiteral(ORLA_TEST_QUIT_HARNESS), {QStringLiteral("--no-global-shortcut")});
        QTRY_VERIFY_WITH_TIMEOUT(([&] { output += process.readAll(); return process.state() == QProcess::NotRunning; })(), 3000);
        output += process.readAll();
        QVERIFY2(output.size() <= 65536, "Owned harness exceeded the output budget");
        QVERIFY2(!output.contains("ORLA_QUIT_LIFECYCLE_WATCHDOG"), output.constData());
        QCOMPARE(process.exitStatus(), QProcess::NormalExit);
        QCOMPARE(process.exitCode(), 0);
        QVERIFY2(output.contains("ORLA_QUIT_LIFECYCLE_TRIGGERED"), output.constData());
        QVERIFY2(output.contains("ORLA_QUIT_LIFECYCLE_EXIT mode=" + mode.toUtf8()), output.constData());
        QVERIFY2(output.contains("visible=0 secondaryVisible=0 unexpectedHidden=0"), output.constData());
        if (mode != QStringLiteral("idle")) {
            QVERIFY2(output.contains("ORLA_QUIT_LIFECYCLE_SETTLED"), output.constData());
            QVERIFY2(output.contains("settled=1 quitLock=1 lastWindowQuit=1"), output.constData());
        }
    }

    void managedOwnedAppDispatchStaysAliveReopensAndStillQuitsExplicitly()
    {
        const QString receipt = qEnvironmentVariable("ORLA_TEST_RECEIPT");
        QVERIFY2(!receipt.isEmpty(), "Run through the private wrapper with --fixture; only the owned app may execute");
        QFile::remove(receipt);
        QProcess process;
        QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
        environment.insert(QStringLiteral("QT_FORCE_STDERR_LOGGING"), QStringLiteral("1"));
        process.setProcessEnvironment(environment);
        process.setProcessChannelMode(QProcess::MergedChannels);
        process.start(QStringLiteral(ORLA_TEST_DISPATCH_HARNESS), {QStringLiteral("--managed-shortcuts"), QStringLiteral("--start-hidden")});
        QByteArray output;
        const auto cleanup = qScopeGuard([&] { process.terminate(); if (!process.waitForFinished(1000)) { process.kill(); process.waitForFinished(); }
            qInfo().noquote() << output; });
        QTRY_VERIFY_WITH_TIMEOUT(([&] { output += process.readAll(); return output.contains("ORLA_MANAGED_DISPATCH_READY"); })(), 3000);
        withDaemon([&] { emit daemon->component.globalShortcutPressed(QStringLiteral("org.orla.Launcher"), QStringLiteral("orla-search-open"), 0); });
        QTRY_VERIFY_WITH_TIMEOUT(([&] { output += process.readAll(); return output.contains("ORLA_MANAGED_DISPATCH_ENTER"); })(), 3000);
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(receipt), 3000);
        QTest::qWait(500); // A real KIO launch job has completed; the application event loop remains entered.
        output += process.readAll();
        QCOMPARE(process.state(), QProcess::Running);
        QVERIFY2(output.contains("ORLA_MANAGED_DISPATCH_HIDDEN shortcutHealthy=1 pendingQuit=0"), output.constData());
        const QDBusReply<bool> registered = QDBusConnection::sessionBus().interface()->isServiceRegistered(QStringLiteral("org.orla.Launcher"));
        QVERIFY(registered.isValid() && registered.value());
        withDaemon([&] { emit daemon->component.globalShortcutPressed(QStringLiteral("org.orla.Launcher"), QStringLiteral("orla-search-open"), 0); });
        QTRY_VERIFY_WITH_TIMEOUT(([&] { output += process.readAll(); return output.contains("ORLA_MANAGED_DISPATCH_REOPENED"); })(), 2000);
        QTRY_VERIFY_WITH_TIMEOUT(process.state() == QProcess::NotRunning, 3000);
        output += process.readAll();
        QCOMPARE(process.exitCode(), 0);
        QVERIFY(output.contains("ORLA_MANAGED_DISPATCH_EXPLICIT_QUIT"));
        QFile file(receipt);
        QVERIFY(file.open(QIODevice::ReadOnly));
        QCOMPARE(file.readAll(), QByteArray("owned-launcher-fixture\n"));
    }
};
QTEST_MAIN(ShortcutTests)
#include "ShortcutTests.moc"
