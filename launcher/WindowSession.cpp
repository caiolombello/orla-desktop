#include "WindowSession.h"
#include "LauncherController.h"
#include <QGuiApplication>
#include <QEventLoopLocker>
#include <QKeySequence>
#include <QVariant>
#include <QPainterPath>
#include <QRegion>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusMessage>
#include <QDBusObjectPath>
#include <QDBusReply>
#include <QDBusServiceWatcher>
#include <QSet>
#include <KGlobalAccel>
#include <KGlobalShortcutInfo>
#include <KWaylandExtras>
#include <KWindowEffects>
#include <KWindowSystem>

namespace {
const QString shortcutService = QStringLiteral("org.kde.kglobalaccel");

bool ownsManagedLease()
{
    const auto bus = QDBusConnection::sessionBus();
    if (!bus.isConnected() || !bus.interface()) return false;
    const QDBusReply<QString> owner = bus.interface()->serviceOwner(QStringLiteral("org.orla.Launcher"));
    return owner.isValid() && owner.value() == bus.baseService();
}

QDBusMessage shortcutCall(const QString &method, const QList<QVariant> &arguments,
                         const QString &path = QStringLiteral("/kglobalaccel"),
                         const QString &interface = QStringLiteral("org.kde.KGlobalAccel"))
{
    auto message = QDBusMessage::createMethodCall(shortcutService, path, interface, method);
    message.setArguments(arguments);
    message.setAutoStartService(false);
    return QDBusConnection::sessionBus().call(message, QDBus::Block, 1500);
}

bool configuredShortcut(const QString &component, const QString &action, bool &exists, QList<QKeySequence> &keys)
{
    exists = false;
    const QDBusReply<QDBusObjectPath> path = shortcutCall(QStringLiteral("getComponent"), {component});
    if (!path.isValid()) return path.error().name() == QStringLiteral("org.kde.kglobalaccel.NoSuchComponent");
    const QDBusReply<QStringList> contexts = shortcutCall(QStringLiteral("getShortcutContexts"), {},
        path.value().path(), QStringLiteral("org.kde.kglobalaccel.Component"));
    if (!contexts.isValid() || contexts.value() != QStringList{QStringLiteral("default")}) return false;
    const QDBusReply<QStringList> names = shortcutCall(QStringLiteral("shortcutNames"), {QStringLiteral("default")},
                                                      path.value().path(), QStringLiteral("org.kde.kglobalaccel.Component"));
    if (!names.isValid()) return false;
    exists = names.value().contains(action);
    if (!exists) return true;
    const QDBusReply<QList<QKeySequence>> result = shortcutCall(QStringLiteral("shortcutKeys"),
        {QStringList{component, action, QString(), QString()}});
    if (!result.isValid()) return false;
    keys = result.value();
    return true;
}

QSet<QKeySequence> keySet(const QList<QKeySequence> &keys)
{
    return QSet<QKeySequence>(keys.cbegin(), keys.cend());
}

bool shortcutUncontested(const QList<QKeySequence> &keys, const QString &component, const QString &action)
{
    for (const auto &key : keys) {
        if (key.isEmpty()) return false;
        for (const auto match : {KGlobalAccel::Equal, KGlobalAccel::Shadows, KGlobalAccel::Shadowed}) {
            const QDBusReply<QList<KGlobalShortcutInfo>> owners = shortcutCall(QStringLiteral("globalShortcutsByKey"),
                {QVariant::fromValue(key), QVariant::fromValue(match)});
            if (!owners.isValid()) return false;
            for (const auto &owner : owners.value()) {
                // Same component is not enough: another action or context can win native delivery.
                if (owner.componentUniqueName() != component || owner.uniqueName() != action
                    || owner.contextUniqueName() != QStringLiteral("default")) return false;
            }
        }
    }
    return true;
}
}

WindowSession::WindowSession(LauncherController *controller, QQuickWindow *window, bool useShortcut,
                             const QString &key, QObject *parent, ShortcutMode mode)
    : QObject(parent), m_window(window), m_controller(controller), m_mode(mode)
{
    connect(controller, &LauncherController::closeRequested, this, &WindowSession::dismiss);
    connect(window, &QWindow::activeChanged, this, [this] {
        if (m_window && m_window->isActive() && m_registered) setNotice(QString());
    });
    if (!useShortcut) return;
    if (mode == ShortcutMode::Managed && !ownsManagedLease()) {
        shortcutUnavailable(tr("A identidade gerenciada está indisponível. A janela continua disponível."));
        return;
    }
    const QKeySequence sequence = QKeySequence::fromString(key, QKeySequence::PortableText);
    auto *accel = KGlobalAccel::self();
    const bool managed = mode == ShortcutMode::Managed;
    const QString component = managed ? QStringLiteral("org.orla.Launcher") : QCoreApplication::applicationName();
    const QString action = managed ? QStringLiteral("orla-search-open") : QStringLiteral("_k_session:orla-launcher-open");
    QList<QKeySequence> configured{sequence};
    bool exists = false;
    if (sequence.isEmpty() || sequence.count() != 1
        || (managed && !configuredShortcut(component, action, exists, configured))) {
        shortcutUnavailable(tr("Atalho indisponível. A janela continua disponível."));
        return;
    }
    // A disabled saved action is distinct from an action never registered before.
    if (!exists) configured = {sequence};
    if (!shortcutUncontested(configured, component, action)) {
        shortcutUnavailable(tr("Atalho em conflito ou inventário indisponível. A janela continua disponível."));
        return;
    }
    if (managed) {
        m_action.setProperty("componentName", component);
        m_action.setProperty("componentDisplayName", QStringLiteral("Orla Launcher"));
    }
    m_action.setObjectName(action);
    m_action.setText(managed ? tr("Abrir busca Orla") : tr("Abrir Orla Launcher (sessão temporária)"));
    m_action.setAutoRepeat(false);
    connect(&m_action, &QAction::triggered, this, &WindowSession::showFromShortcut);
    connect(accel, &KGlobalAccel::globalShortcutChanged, this, [this](QAction *changed, const QKeySequence &) {
        if (changed == &m_action) refreshShortcut();
    });
    const bool accepted = (!managed || accel->setDefaultShortcut(&m_action, {sequence}))
        && accel->setShortcut(&m_action, {sequence}, managed ? KGlobalAccel::Autoloading : KGlobalAccel::NoAutoloading);
    QList<QKeySequence> observed;
    if (!accepted || !configuredShortcut(component, action, exists, observed) || !exists
        || keySet(observed) != keySet(configured) || keySet(accel->shortcut(&m_action)) != keySet(observed)) {
        shortcutUnavailable(tr("Atalho não registrado. A janela continua disponível."));
    } else {
        refreshShortcut();
    }
    auto *watcher = new QDBusServiceWatcher(shortcutService, QDBusConnection::sessionBus(),
                                          QDBusServiceWatcher::WatchForOwnerChange, this);
    connect(watcher, &QDBusServiceWatcher::serviceOwnerChanged, this,
            [this](const QString &, const QString &, const QString &) {
        shortcutUnavailable(tr("O serviço de atalhos mudou. A janela continua disponível."));
        // KF re-registers with Autoloading on daemon return; verify only after its callback.
        QTimer::singleShot(0, this, &WindowSession::refreshShortcut);
    });
    auto *busHealth = new QTimer(this);
    busHealth->setInterval(1000);
    // Foreign conflicts and unregister operations need not emit this QAction's change signal.
    connect(busHealth, &QTimer::timeout, this, &WindowSession::refreshShortcut);
    busHealth->start();
}

WindowSession::~WindowSession()
{
    ++m_activationGeneration;
    if (m_action.objectName().isEmpty()) return;
    if (m_mode == ShortcutMode::Temporary) {
        KGlobalAccel::self()->removeAllShortcuts(&m_action);
    } else {
        deactivateShortcut();
        // KF 6.30 still clears its local maps on destruction, but this property skips its
        // unqualified setInactive call, which could target a newly selected foreign context.
        m_action.setProperty("isConfigurationAction", true);
    }
}

void WindowSession::deactivateShortcut()
{
    if (!m_action.objectName().isEmpty() && KGlobalAccel::self()->hasShortcut(&m_action)
        && (m_mode == ShortcutMode::Temporary || ownsManagedLease())) {
        const QString component = m_mode == ShortcutMode::Managed ? QStringLiteral("org.orla.Launcher") : QCoreApplication::applicationName();
        // Keep settings, but release this exact callback's native keys while it is unhealthy.
        shortcutCall(QStringLiteral("setInactive"),
            {QStringList{component + QStringLiteral("|default"), m_action.objectName(), QStringLiteral("Orla Launcher"), m_action.text()}});
        m_deactivated = true;
    }
}

void WindowSession::shortcutUnavailable(const QString &notice)
{
    if (m_quitRequested) return;
    m_registered = false;
    m_action.setEnabled(false);
    deactivateShortcut();
    if (!m_shortcutText.isEmpty()) {
        m_shortcutText.clear();
        emit shortcutTextChanged();
    }
    setNotice(notice);
    if (m_window && !m_window->isVisible()) {
        ++m_activationGeneration;
        m_window->show();
    }
}

void WindowSession::refreshShortcut()
{
    if (m_quitRequested) return;
    if (!QDBusConnection::sessionBus().isConnected() || (m_mode == ShortcutMode::Managed && !ownsManagedLease())) {
        shortcutUnavailable(tr("O D-Bus ou a identidade gerenciada está indisponível. A janela continua disponível."));
        return;
    }
    const bool wasRegistered = m_registered;
    const QString component = m_mode == ShortcutMode::Managed ? QStringLiteral("org.orla.Launcher") : QCoreApplication::applicationName();
    bool exists = false;
    QList<QKeySequence> keys;
    if (!configuredShortcut(component, m_action.objectName(), exists, keys) || !exists || keys.isEmpty()
        || keySet(KGlobalAccel::self()->shortcut(&m_action)) != keySet(keys)
        || !shortcutUncontested(keys, component, m_action.objectName())) {
        shortcutUnavailable(tr("Atalho desativado ou indisponível. A janela continua disponível."));
        return;
    }
    if (m_deactivated) {
        const bool accepted = KGlobalAccel::self()->setShortcut(&m_action, keys, KGlobalAccel::Autoloading);
        QList<QKeySequence> observed;
        if (!accepted || !configuredShortcut(component, m_action.objectName(), exists, observed) || !exists
            || keySet(observed) != keySet(keys) || !shortcutUncontested(observed, component, m_action.objectName())) {
            shortcutUnavailable(tr("Atalho não reativado. A janela continua disponível."));
            return;
        }
        m_deactivated = false;
    }
    m_registered = true;
    m_action.setEnabled(true);
    QStringList labels;
    for (const auto &key : keys) labels.append(key.toString(QKeySequence::NativeText));
    const QString text = labels.join(QStringLiteral(" / "));
    if (text != m_shortcutText) {
        m_shortcutText = text;
        emit shortcutTextChanged();
    }
    if (!wasRegistered) setNotice(QString());
}

void WindowSession::setBlurRegion(const QRectF &rect, qreal radius)
{
    if (!m_window) return;
    if (rect.isEmpty()) {
        KWindowEffects::enableBlurBehind(m_window, false);
        return;
    }
    QPainterPath path;
    path.addRoundedRect(rect, radius, radius);
    KWindowEffects::enableBlurBehind(m_window, true, QRegion(path.toFillPolygon().toPolygon()));
}

void WindowSession::setNotice(const QString &notice)
{
    if (notice == m_notice) return;
    m_notice = notice;
    emit noticeChanged();
}

void WindowSession::showFromShortcut()
{
    if (m_quitRequested || !m_window) return;
    if (m_window->isVisible() && m_window->isActive()) {
        ++m_activationGeneration; // A pending compositor token must not reactivate a closing window.
        // Reuse the QML three-owner close barrier. A missing method leaves the window visible.
        QMetaObject::invokeMethod(m_window.data(), "requestDismiss", Q_ARG(QVariant, QVariant(false)));
        return;
    }
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
            if (m_quitRequested || !m_window || request != m_activationGeneration || !m_window->isVisible()) return;
            if (!token.isEmpty()) {
                KWindowSystem::setCurrentXdgActivationToken(token);
                KWindowSystem::activateWindow(m_window);
            }
            // Token delivery alone does not establish focus. The compositor decides.
            if (m_window->isActive()) setNotice(QString());
        });
}

void WindowSession::requestQuit()
{
    if (m_quitRequested) return;
    m_quitRequested = true;
    m_action.setEnabled(false);
    // Keep the first dismiss/focus request intact. Automatic quit waits for
    // existing KJob lockers; the temporary locker also covers the no-job case.
    const QEventLoopLocker locker;
    QCoreApplication::setQuitLockEnabled(true);
    QGuiApplication::setQuitOnLastWindowClosed(true);
    if (m_window) m_window->hide();
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
        if (!m_registered) requestQuit();
        else m_window->hide();
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
