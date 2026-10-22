#include "OrlaCommandController.h"
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QPointer>
#include <QStringList>

namespace {
constexpr int replyLimit = 262144;
constexpr int readTimeoutMs = 3000;

struct Command {
    QString id;
    QString title;
    QString description;
    QStringList terms;
};

QString fold(const QString &text)
{
    // Case- and accent-insensitive: "periféricos" and "perifericos" match alike.
    const QString decomposed = text.normalized(QString::NormalizationForm_D).toCaseFolded();
    QString folded;
    folded.reserve(decomposed.size());
    for (const QChar c : decomposed)
        if (c.category() != QChar::Mark_NonSpacing) folded.append(c);
    return folded.simplified();
}

QList<Command> catalog()
{
    return {
        {OrlaCommandController::batteryCommand, OrlaCommandController::tr("Bateria de periféricos"),
         OrlaCommandController::tr("Lê a última bateria compartilhada com a dock. Não inicia coleta."),
         {QStringLiteral("bateria"), QStringLiteral("baterias"), QStringLiteral("battery"), QStringLiteral("batteries"),
          QStringLiteral("periféricos"), QStringLiteral("peripherals"), QStringLiteral("mouse"), QStringLiteral("teclado"),
          QStringLiteral("keyboard"), QStringLiteral("fones"), QStringLiteral("earbuds"), QStringLiteral("headset")}},
    };
}
}

const QString OrlaCommandController::batteryCommand = QStringLiteral("orla.peripherals.battery");

OrlaCommandController::OrlaCommandController(Transport transport, Availability availability, QObject *parent)
    : QObject(parent), m_transport(transport ? transport : Transport(&OrlaCommandController::dbusSnapshot)),
      m_availability(availability ? availability : Availability(&OrlaCommandController::dbusAvailable))
{
}

QVariantList OrlaCommandController::matches(const QString &query) const
{
    const QString needle = fold(query);
    QVariantList found;
    if (needle.size() < 2 || needle.size() > 64) return found;
    for (const auto &command : catalog()) {
        bool match = fold(command.title).contains(needle);
        for (const auto &term : command.terms) match = match || fold(term).startsWith(needle);
        if (match)
            found.append(QVariantMap{{"id", command.id}, {"title", command.title}, {"description", command.description}});
    }
    return found;
}

bool OrlaCommandController::available()
{
    if (!m_availabilityKnown) {
        m_available = m_availability();
        m_availabilityKnown = true;
    }
    return m_available;
}

bool OrlaCommandController::read(const QString &commandId)
{
    if (commandId != batteryCommand || m_busy || !available()) return false;
    const quint64 token = ++m_token;
    m_busy = true;
    m_status = QStringLiteral("reading");
    m_commandId = commandId;
    m_title = tr("Bateria de periféricos");
    m_reply.clear();
    m_errorCode.clear();
    ++m_revision;
    emit changed();
    QPointer<OrlaCommandController> self(this);
    m_transport(this, [self, token](bool ok, const QString &reply, const QString &errorCode) {
        // Cancelled, replaced or destroyed reads never publish.
        if (!self || token != self->m_token || !self->m_busy) return;
        self->m_busy = false;
        if (ok && reply.size() <= replyLimit) {
            self->m_status = QStringLiteral("ready");
            self->m_reply = reply;
        } else {
            static const QStringList known{QStringLiteral("unavailable"), QStringLiteral("timeout"), QStringLiteral("invalid_response")};
            self->m_status = QStringLiteral("error");
            self->m_errorCode = ok ? QStringLiteral("invalid_response")
                : known.contains(errorCode) ? errorCode : QStringLiteral("unavailable");
        }
        ++self->m_revision;
        emit self->changed();
    });
    return true;
}

void OrlaCommandController::cancelAll()
{
    ++m_token;
    if (!m_busy && m_status == QStringLiteral("idle")) return;
    m_busy = false;
    m_status = QStringLiteral("idle");
    m_commandId.clear();
    m_title.clear();
    m_reply.clear();
    m_errorCode.clear();
    ++m_revision;
    emit changed();
}

bool OrlaCommandController::requestClose()
{
    // No owned process: dropping the pending reply is a complete close.
    cancelAll();
    return true;
}

void OrlaCommandController::dbusSnapshot(QObject *context, Done done)
{
    auto bus = QDBusConnection::sessionBus();
    if (!bus.isConnected()) {
        done(false, {}, QStringLiteral("unavailable"));
        return;
    }
    auto message = QDBusMessage::createMethodCall(QStringLiteral("org.orla.Addons"), QStringLiteral("/org/orla/Addons"),
                                                  QStringLiteral("org.orla.Addons1"), QStringLiteral("SnapshotFor"));
    message << QStringList{QStringLiteral("peripherals")};
    auto *watcher = new QDBusPendingCallWatcher(bus.asyncCall(message, readTimeoutMs), context);
    QObject::connect(watcher, &QDBusPendingCallWatcher::finished, context, [done](QDBusPendingCallWatcher *call) {
        const QDBusMessage reply = call->reply();
        call->deleteLater();
        if (reply.type() != QDBusMessage::ReplyMessage) {
            const QString name = reply.errorName();
            done(false, {}, name == QStringLiteral("org.freedesktop.DBus.Error.NoReply")
                    || name == QStringLiteral("org.freedesktop.DBus.Error.Timeout")
                ? QStringLiteral("timeout") : QStringLiteral("unavailable"));
            return;
        }
        const auto arguments = reply.arguments();
        if (arguments.size() != 1 || arguments.first().metaType() != QMetaType::fromType<QString>()) {
            done(false, {}, QStringLiteral("invalid_response"));
            return;
        }
        done(true, arguments.first().toString(), {});
    });
}

bool OrlaCommandController::dbusAvailable()
{
    auto bus = QDBusConnection::sessionBus();
    if (!bus.isConnected() || !bus.interface()) return false;
    const QString name = QStringLiteral("org.orla.Addons");
    const auto registered = bus.interface()->isServiceRegistered(name);
    if (registered.isValid() && registered.value()) return true;
    const auto activatable = bus.interface()->activatableServiceNames();
    return activatable.isValid() && activatable.value().contains(name);
}
