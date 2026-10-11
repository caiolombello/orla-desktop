#include "WindowSession.h"
#include "LauncherController.h"
#include <QGuiApplication>
#include <QKeySequence>
#include <KGlobalAccel>
#include <KWaylandExtras>
#include <KWindowSystem>

WindowSession::WindowSession(LauncherController *controller, QQuickWindow *window, bool useShortcut,
                             const QString &key, QObject *parent)
    : QObject(parent), m_window(window), m_controller(controller)
{
    connect(controller, &LauncherController::closeRequested, this, &WindowSession::dismiss);
    connect(window, &QWindow::activeChanged, this, [this] {
        if (m_window && m_window->isActive() && m_registered) setNotice(QString());
    });
    if (!useShortcut) return;
    const QKeySequence sequence = QKeySequence::fromString(key, QKeySequence::PortableText);
    if (sequence.isEmpty() || sequence.count() != 1 || !KGlobalAccel::isGlobalShortcutAvailable(sequence)) {
        m_notice = tr("Atalho indisponível. Use a janela ou reinicie com outro --shortcut.");
        return;
    }
    m_action.setObjectName(QStringLiteral("_k_session:orla-launcher-open"));
    m_action.setText(tr("Abrir Orla Launcher (sessão temporária)"));
    m_action.setAutoRepeat(false);
    connect(&m_action, &QAction::triggered, this, &WindowSession::showFromShortcut);
    const bool accepted = KGlobalAccel::self()->setShortcut(&m_action, {sequence}, KGlobalAccel::NoAutoloading);
    m_registered = accepted && KGlobalAccel::self()->shortcut(&m_action) == QList<QKeySequence>{sequence};
    if (m_registered) m_shortcutText = sequence.toString(QKeySequence::NativeText);
    else {
        KGlobalAccel::self()->removeAllShortcuts(&m_action);
        m_notice = tr("Atalho não registrado. A janela continua disponível.");
    }
}

WindowSession::~WindowSession()
{
    ++m_activationGeneration;
    if (m_registered) KGlobalAccel::self()->removeAllShortcuts(&m_action);
}

void WindowSession::setNotice(const QString &notice)
{
    if (notice == m_notice) return;
    m_notice = notice;
    emit noticeChanged();
}

void WindowSession::showFromShortcut()
{
    if (!m_window) return;
    if (m_window->isVisible() && m_window->isActive()) { m_controller->dismiss(); return; }
    // QGuiApplication only returns this process's windows. Never inspect another app's window.
    QWindow *origin = QGuiApplication::focusWindow();
    if (origin && !origin->isActive()) origin = nullptr;
    m_returnWindow = origin && origin != m_window ? origin : nullptr;
    const quint64 request = ++m_activationGeneration;
    m_window->show();
    if (QGuiApplication::platformName() != QStringLiteral("wayland")) {
        KWindowSystem::activateWindow(m_window);
        return;
    }
    setNotice(tr("Se o desktop não der foco, clique na busca."));
    KWaylandExtras::xdgActivationToken(origin ? origin : m_window.data(), QStringLiteral("org.orla.Launcher"))
        .then(this, [this, request](const QString &token) {
            if (!m_window || request != m_activationGeneration || !m_window->isVisible()) return;
            if (!token.isEmpty()) {
                KWindowSystem::setCurrentXdgActivationToken(token);
                KWindowSystem::activateWindow(m_window);
            }
            // Token delivery alone does not establish focus. The compositor decides.
            if (m_window->isActive()) setNotice(QString());
        });
}

void WindowSession::dismiss()
{
    if (!m_window) return;
    const quint64 request = ++m_activationGeneration;
    // Hiding lets the compositor restore the previous app. Only owned fixtures may be explicitly activated.
    const auto ownedReturn = m_returnWindow;
    m_returnWindow.clear();
    const auto hide = [this, request] {
        if (!m_window || request != m_activationGeneration) return;
        m_window->hide();
        if (!m_registered) QCoreApplication::quit();
    };
    if (ownedReturn && QGuiApplication::platformName() == QStringLiteral("wayland")) {
        KWaylandExtras::xdgActivationToken(m_window, QStringLiteral("org.orla.Launcher"))
            .then(this, [this, request, ownedReturn, hide](const QString &token) {
                if (request != m_activationGeneration) return;
                hide();
                if (ownedReturn && !token.isEmpty()) {
                    KWindowSystem::setCurrentXdgActivationToken(token);
                    KWindowSystem::activateWindow(ownedReturn);
                }
            });
        QTimer::singleShot(250, this, hide); // Closing never waits indefinitely for a compositor token.
    } else {
        hide();
    }
}
