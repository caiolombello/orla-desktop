#pragma once

#include <functional>
#include <memory>
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QVariantMap>

class QJsonObject;
class QTemporaryDir;

// Private C++/QML boundary for one explicitly consented local text request.
class AiTextController final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString requestId READ requestId NOTIFY changed)
    Q_PROPERTY(QString output READ output NOTIFY changed)
    Q_PROPERTY(QString errorCode READ errorCode NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString destination READ destination NOTIFY changed)
    Q_PROPERTY(QString model READ model NOTIFY changed)
    Q_PROPERTY(QVariantMap usage READ usage NOTIFY changed)
    Q_PROPERTY(QString costStatus READ costStatus NOTIFY changed)
public:
    using GroupObserver = std::function<bool(qint64)>;
    using RuntimeRemover = std::function<bool(const QString &)>;

    explicit AiTextController(const QString &pythonPath, const QString &helperPath,
                              GroupObserver groupObserver = {}, QObject *parent = nullptr,
                              RuntimeRemover runtimeRemover = {},
                              int cancellationGraceMs = 3000, int outerDeadlineMs = 125000);
    ~AiTextController() override;

    QString status() const { return m_status; }
    bool busy() const { return m_operationActive || m_process.state() != QProcess::NotRunning || m_cleanupActive; }
    QString requestId() const { return m_requestId; }
    QString output() const { return m_output; }
    QString errorCode() const { return m_errorCode; }
    QString error() const { return m_error; }
    QString destination() const { return m_destination; }
    QString model() const { return m_model; }
    QVariantMap usage() const { return m_usage; }
    QString costStatus() const { return m_costStatus; }

    Q_INVOKABLE void generate(const QString &requestId, const QString &task,
                              const QVariant &targetLanguage, const QString &text,
                              const QString &model, const QString &numericHost,
                              int port, bool explicitConsent);
    Q_INVOKABLE void cancel(const QString &requestId);
    Q_INVOKABLE void cancelAll();
    Q_INVOKABLE bool requestClose();

Q_SIGNALS:
    void changed();
    void closeReady();

private:
    friend class AiTextControllerTests;
    bool validateRequest(const QString &requestId, const QString &task,
                         const QVariant &targetLanguage, const QString &text,
                         const QString &model, const QString &numericHost,
                         int port, bool explicitConsent) const;
    bool prepareRuntime();
    bool runtimeIdentityMatches() const;
    bool removeOwnedRuntime();
    void consumeStdout();
    bool consumeLine(const QByteArray &line);
    bool validateBase(const QJsonObject &object, const QString &type) const;
    bool validateUsage(const QJsonObject &object, QVariantMap *usage) const;
    void protocolFailure();
    void beginCancellation();
    void killOwnedGroup(int signalNumber);
    bool ownedGroupExists() const;
    void beginGroupCleanup();
    void pollGroupCleanup();
    void finishAfterCleanup(bool cleanupConfirmed);
    void handleFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void recordFailure(const QString &code);
    void resetOperation();

    QString m_pythonPath;
    QString m_helperPath;
    GroupObserver m_groupObserver;
    RuntimeRemover m_runtimeRemover;
    int m_cancellationGraceMs;
    int m_outerDeadlineMs;
    QProcess m_process;
    QTimer m_deadline;
    QTimer m_killGrace;
    QTimer m_groupPoll;
    QTimer m_cleanupDeadline;
    std::unique_ptr<QTemporaryDir> m_runtimeDirectory;
    quint64 m_runtimeDevice = 0;
    quint64 m_runtimeInode = 0;
    qint64 m_processGroup = 0;
    quint64 m_generation = 0;
    quint64 m_processGeneration = 0;
    QString m_status = QStringLiteral("disabled");
    QString m_requestId;
    QString m_output;
    QString m_errorCode;
    QString m_error;
    QString m_destination;
    QString m_model;
    QVariantMap m_usage;
    QVariantMap m_pendingUsage;
    QString m_costStatus = QStringLiteral("unknown");
    QByteArray m_stdout;
    QByteArray m_requestFrame;
    int m_nextSequence = 0;
    int m_eventCount = 0;
    qsizetype m_outputBytes = 0;
    bool m_startedEvent = false;
    bool m_terminalEvent = false;
    QString m_terminalType;
    QString m_terminalCode;
    bool m_operationActive = false;
    bool m_cleanupActive = false;
    bool m_cancelRequested = false;
    bool m_timedOut = false;
    bool m_closePending = false;
    bool m_killSent = false;
    bool m_protocolInvalid = false;
    int m_pendingExitCode = -1;
    QProcess::ExitStatus m_pendingExitStatus = QProcess::CrashExit;
};
