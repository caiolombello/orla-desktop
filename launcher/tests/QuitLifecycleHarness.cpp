#include <QDBusConnectionInterface>
#include <QDBusReply>
#include <QEventLoopLocker>
#include <QQuickItem>
#include <QRegularExpression>
#include <QTimer>
#include <QtTest>
#include <cstdio>
#include <memory>

#define main orlaLauncherMain
#include "../main.cpp"
#undef main

namespace {
struct QuitState {
    QString mode;
    bool prepared = false, settled = false, closeAuthorized = false, unexpectedHidden = false;
    QPointer<QQuickWindow> secondary;
    std::unique_ptr<QEventLoopLocker> work;
};
QQuickWindow *launcherWindow()
{
    for (QWindow *candidate : QGuiApplication::allWindows())
        if (candidate->objectName() == QStringLiteral("launcherWindow")) return qobject_cast<QQuickWindow *>(candidate);
    return nullptr;
}
void installQuitDriver()
{
    const auto bus = QDBusConnection::sessionBus();
    const QDBusReply<QString> id = bus.interface() ? bus.interface()->call(QStringLiteral("GetId")) : QDBusReply<QString>();
    if (!id.isValid() || id.value() != qEnvironmentVariable("ORLA_EXPECTED_PRIVATE_BUS_ID"))
        qFatal("Quit lifecycle harness requires the verified private test bus");
    auto state = std::make_shared<QuitState>();
    state->mode = qEnvironmentVariable("ORLA_TEST_QUIT_MODE");
    auto *timer = new QTimer(QCoreApplication::instance());
    timer->setInterval(10);
    QObject::connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, [state] {
        const auto *window = launcherWindow();
        std::printf("ORLA_QUIT_LIFECYCLE_EXIT mode=%s settled=%d quitLock=%d lastWindowQuit=%d visible=%d secondaryVisible=%d unexpectedHidden=%d\n",
                    state->mode.toUtf8().constData(), state->settled, QCoreApplication::isQuitLockEnabled(),
                    QGuiApplication::quitOnLastWindowClosed(), window && window->isVisible(),
                    state->secondary && state->secondary->isVisible(), state->unexpectedHidden);
        std::fflush(stdout);
        state->work.reset(); // Cancel only this fixture's unsettled work during teardown.
    });
    QObject::connect(timer, &QTimer::timeout, [timer, state] {
        auto *window = launcherWindow();
        auto *context = window ? QQmlEngine::contextForObject(window) : nullptr;
        auto *session = context ? qobject_cast<WindowSession *>(context->contextProperty(QStringLiteral("windowSession")).value<QObject *>()) : nullptr;
        auto *search = window ? window->findChild<QQuickItem *>(QStringLiteral("searchInput")) : nullptr;
        if (!window || !session || !search || !window->isVisible()) return;
        if (!state->prepared) {
            state->prepared = true;
            if (state->mode.contains(QStringLiteral("secondary"))) {
                state->secondary = new QQuickWindow;
                state->secondary->setObjectName(QStringLiteral("ownedQuitSecondary"));
                state->secondary->QObject::setParent(QCoreApplication::instance());
                state->secondary->show();
                QObject::connect(state->secondary, &QWindow::visibleChanged, [state](bool visible) {
                    if (!visible && !state->closeAuthorized) state->unexpectedHidden = true;
                });
            }
            window->requestActivate();
            search->forceActiveFocus();
            return;
        }
        if (!window->isActive()) { window->requestActivate(); search->forceActiveFocus(); return; }
        timer->stop();
        state->settled = state->mode == QStringLiteral("idle");
        if (!state->settled) {
            state->work = std::make_unique<QEventLoopLocker>();
            QTimer::singleShot(80, QCoreApplication::instance(), [state] {
                state->settled = true;
                std::puts("ORLA_QUIT_LIFECYCLE_SETTLED");
                std::fflush(stdout);
                state->work.reset();
            });
        }
        if (state->secondary) {
            const int delay = state->mode.endsWith(QStringLiteral("before")) ? 40 : 120;
            QTimer::singleShot(delay, QCoreApplication::instance(), [state] {
                if (!state->secondary || !state->secondary->isVisible()) { QCoreApplication::exit(15); return; }
                state->closeAuthorized = true;
                state->secondary->close();
            });
        }
        std::puts("ORLA_QUIT_LIFECYCLE_TRIGGERED");
        std::fflush(stdout);
        if (state->mode.startsWith(QStringLiteral("ctrlq"))) QTest::keyClick(window, Qt::Key_Q, Qt::ControlModifier);
        else if (state->mode.startsWith(QStringLiteral("close"))) window->close();
        else QTest::keyClick(window, Qt::Key_Escape);
    });
    timer->start();
    QTimer::singleShot(2000, QCoreApplication::instance(), [] {
        std::puts("ORLA_QUIT_LIFECYCLE_WATCHDOG");
        std::fflush(stdout);
        QCoreApplication::exit(14);
    });
}
}
Q_COREAPP_STARTUP_FUNCTION(installQuitDriver)
int main(int argc, char **argv)
{
    const QString address = qEnvironmentVariable("DBUS_SESSION_BUS_ADDRESS");
    const QRegularExpression privateAddress(QStringLiteral("^unix:abstract=orla-test-[0-9a-f]{32},guid=[0-9a-f]{32}$"));
    const QStringList modes{QStringLiteral("idle"), QStringLiteral("escape"), QStringLiteral("ctrlq"), QStringLiteral("close"),
        QStringLiteral("escape-secondary-before"), QStringLiteral("ctrlq-secondary-after"), QStringLiteral("close-secondary-after")};
    if (qEnvironmentVariable("QT_QPA_PLATFORM") != QStringLiteral("offscreen")
        || qEnvironmentVariable("QT_QUICK_BACKEND") != QStringLiteral("software") || !privateAddress.match(address).hasMatch() || qEnvironmentVariable("ORLA_EXPECTED_PRIVATE_BUS_ID").isEmpty()
        || !modes.contains(qEnvironmentVariable("ORLA_TEST_QUIT_MODE"))) return 3;
    return orlaLauncherMain(argc, argv);
}
