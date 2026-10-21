#pragma once

#include <functional>
#include <QObject>
#include <QString>
#include <QVariantList>

// Internal, experimental catalog of Orla commands (L1). Searching only lists
// entries; a read starts only from an explicit execute of the current row.
// The owner of the state is the provider (org.orla.Addons), never the launcher.
class OrlaCommandController final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QString commandId READ commandId NOTIFY changed)
    Q_PROPERTY(QString title READ title NOTIFY changed)
    Q_PROPERTY(QString reply READ reply NOTIFY changed)
    Q_PROPERTY(QString errorCode READ errorCode NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(quint64 revision READ revision NOTIFY changed)
public:
    using Done = std::function<void(bool ok, const QString &reply, const QString &errorCode)>;
    // Starts one bounded read; may call done synchronously. `context` owns any pending call.
    using Transport = std::function<void(QObject *context, Done done)>;
    using Availability = std::function<bool()>;

    static const QString batteryCommand;

    explicit OrlaCommandController(Transport transport = {}, Availability availability = {}, QObject *parent = nullptr);

    QString status() const { return m_status; }
    QString commandId() const { return m_commandId; }
    QString title() const { return m_title; }
    QString reply() const { return m_reply; }
    QString errorCode() const { return m_errorCode; }
    bool busy() const { return m_busy; }
    quint64 revision() const { return m_revision; }

    // Catalog entries ({id, title, description}) whose names or PT/EN aliases match.
    QVariantList matches(const QString &query) const;
    // Cached until resetAvailability(): one bus check per launcher session at most.
    bool available();
    void resetAvailability() { m_availabilityKnown = false; }

    Q_INVOKABLE bool read(const QString &commandId);
    Q_INVOKABLE void cancelAll();
    Q_INVOKABLE bool requestClose();

    static void dbusSnapshot(QObject *context, Done done);
    static bool dbusAvailable();

Q_SIGNALS:
    void changed();

private:
    Transport m_transport;
    Availability m_availability;
    QString m_status = QStringLiteral("idle");
    QString m_commandId;
    QString m_title;
    QString m_reply;
    QString m_errorCode;
    quint64 m_token = 0;
    quint64 m_revision = 0;
    bool m_busy = false;
    bool m_available = false;
    bool m_availabilityKnown = false;
};
