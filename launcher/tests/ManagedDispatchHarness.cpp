#include <QDBusConnectionInterface>
#include <QDBusReply>
#include <QQuickItem>
#include <QTimer>
#include <QtTest>
#include <cstdio>
#include <memory>

// Execute the actual production entry point; the driver exists only in this test executable.
#define main orlaLauncherMain
#include "../main.cpp"
#undef main

namespace {
void mark(const char *message)
{
    std::puts(message);
    std::fflush(stdout);
}

void installDispatchDriver()
{
    const auto bus = QDBusConnection::sessionBus();
    const QDBusReply<QString> id = bus.interface() ? bus.interface()->call(QStringLiteral("GetId")) : QDBusReply<QString>();
    if (!id.isValid() || id.value() != qEnvironmentVariable("ORLA_EXPECTED_PRIVATE_BUS_ID"))
        qFatal("Managed dispatch harness requires the verified private test bus");
    auto *timer = new QTimer(QCoreApplication::instance());
    timer->setInterval(20);
    auto stage = std::make_shared<int>(0);
    QObject::connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, [stage] {
        bool visible = false, healthy = false, pendingQuit = false;
        for (QWindow *candidate : QGuiApplication::allWindows()) {
            if (candidate->objectName() != QStringLiteral("launcherWindow")) continue;
            visible = candidate->isVisible();
            pendingQuit = candidate->property("pendingQuit").toBool();
            auto *context = QQmlEngine::contextForObject(candidate);
            auto *session = context ? qobject_cast<WindowSession *>(context->contextProperty(QStringLiteral("windowSession")).value<QObject *>()) : nullptr;
            healthy = session && !session->shortcutText().isEmpty();
        }
        std::printf("ORLA_MANAGED_DISPATCH_EXIT stage=%d quitLock=%d visible=%d shortcutHealthy=%d pendingQuit=%d\n",
                    *stage, QCoreApplication::isQuitLockEnabled(), visible, healthy, pendingQuit);
        std::fflush(stdout);
    });
    QObject::connect(timer, &QTimer::timeout, [timer, stage] {
        QQuickWindow *window = nullptr;
        for (QWindow *candidate : QGuiApplication::allWindows()) {
            if (candidate->objectName() == QStringLiteral("launcherWindow")) window = qobject_cast<QQuickWindow *>(candidate);
        }
        if (!window) return;
        auto *context = QQmlEngine::contextForObject(window);
        if (!context) return;
        auto *controller = qobject_cast<LauncherController *>(context->contextProperty(QStringLiteral("launcher")).value<QObject *>());
        auto *session = qobject_cast<WindowSession *>(context->contextProperty(QStringLiteral("windowSession")).value<QObject *>());
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        if (!controller || !session || !search) return;
        if (*stage == 0) {
            if (session->shortcutText().isEmpty()) { QCoreApplication::exit(10); return; }
            *stage = 1;
            mark("ORLA_MANAGED_DISPATCH_READY");
        } else if (*stage == 1 && window->isVisible()) {
            *stage = 2;
            window->requestActivate();
            search->forceActiveFocus();
            for (const char key : QByteArrayLiteral("OrlaOwnedLauncherFixture")) QTest::keyClick(window, key);
        } else if (*stage == 2 && controller->status() == QStringLiteral("ready")) {
            if (controller->rows().size() != 1 || controller->rows().first().toMap().value("title") != QStringLiteral("OrlaOwnedLauncherFixture")) {
                QCoreApplication::exit(11); return;
            }
            *stage = 3;
            mark("ORLA_MANAGED_DISPATCH_ENTER");
            QTest::keyClick(window, Qt::Key_Return);
        } else if (*stage == 3 && !window->isVisible()) {
            *stage = 4;
            std::printf("ORLA_MANAGED_DISPATCH_HIDDEN shortcutHealthy=%d pendingQuit=%d\n",
                        !session->shortcutText().isEmpty(), window->property("pendingQuit").toBool());
            std::fflush(stdout);
        } else if (*stage == 4 && window->isVisible()) {
            *stage = 5;
            mark("ORLA_MANAGED_DISPATCH_REOPENED");
            window->requestActivate();
            search->forceActiveFocus();
            QTimer::singleShot(50, window, [window] {
                mark("ORLA_MANAGED_DISPATCH_EXPLICIT_QUIT");
                QTest::keyClick(window, Qt::Key_Q, Qt::ControlModifier);
            });
            timer->stop();
        }
    });
    timer->start();
    QTimer::singleShot(8000, QCoreApplication::instance(), [] { QCoreApplication::exit(12); });
}
}

Q_COREAPP_STARTUP_FUNCTION(installDispatchDriver)

int main(int argc, char **argv)
{
    // Refuse before entering production code unless the parent supplied the verified private bus.
    if (!qEnvironmentVariable("DBUS_SESSION_BUS_ADDRESS").startsWith(QStringLiteral("unix:abstract=orla-test-"))) return 3;
    if (qEnvironmentVariable("ORLA_EXPECTED_PRIVATE_BUS_ID").isEmpty()) return 3;
    return orlaLauncherMain(argc, argv);
}
