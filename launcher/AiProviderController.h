#pragma once

#include <functional>
#include <memory>
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QVariantList>

class QTemporaryDir;

// Private C++/QML boundary for the disabled-by-default A0.1 provider report.
class AiProviderController final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString operation READ operation NOTIFY changed)
    Q_PROPERTY(QString requestId READ requestId NOTIFY changed)
    Q_PROPERTY(QVariantList providers READ providers NOTIFY changed)
    Q_PROPERTY(QString errorCode READ errorCode NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    using GroupObserver = std::function<bool(qint64)>;
    using RuntimeRemover = std::function<bool(const QString &)>;

    explicit AiProviderController(const QString &pythonPath, const QString &helperPath,
                                  GroupObserver groupObserver = {}, QObject *parent = nullptr,
                                  RuntimeRemover runtimeRemover = {});
    ~AiProviderController() override;

    QString status() const { return m_status; }
    bool busy() const { return m_operationActive || m_process.state() != QProcess::NotRunning || m_cleanupActive; }
    QString operation() const { return m_operation; }
    QString requestId() const { return m_requestId; }
    QVariantList providers() const { return m_providers; }
    QString errorCode() const { return m_errorCode; }
    QString error() const { return m_error; }

    Q_INVOKABLE void discover();
    Q_INVOKABLE void probeCodex(const QString &requestId);
    Q_INVOKABLE void cancel(const QString &requestId);
    Q_INVOKABLE void cancelAll();
    Q_INVOKABLE bool requestClose();

Q_SIGNALS:
    void changed();
    void closeReady();

private:
    enum class ExpectedDocument { Providers, CodexProvider };
    void start(const QString &operation, const QString &requestId, ExpectedDocument expected);
    void beginCancellation();
    void killOwnedGroup(int signalNumber);
    bool ownedGroupExists() const;
    void beginGroupCleanup();
    void pollGroupCleanup();
    void finishAfterCleanup(bool cleanupConfirmed);
    bool prepareRuntime();
    bool removeOwnedRuntime();
    bool runtimeIdentityMatches() const;
    void handleFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void recordFailure(const QString &code, const QString &message);
    void fail(const QString &code, const QString &message);
    bool parseDocument(const QByteArray &bytes, QVariantList *providers) const;
    bool parseProvider(const QJsonObject &object, QVariantMap *provider) const;
    bool validProviderSemantics(const QVariantMap &provider) const;
    void publish(QVariantList providers);

    QString m_pythonPath;
    QString m_helperPath;
    GroupObserver m_groupObserver;
    RuntimeRemover m_runtimeRemover;
    std::unique_ptr<QTemporaryDir> m_runtimeDirectory;
    quint64 m_runtimeDevice = 0;
    quint64 m_runtimeInode = 0;
    QProcess m_process;
    QTimer m_deadline;
    QTimer m_killGrace;
    QTimer m_groupPoll;
    QTimer m_cleanupDeadline;
    QByteArray m_stdout;
    QString m_status = QStringLiteral("disabled");
    QString m_stableStatus = QStringLiteral("disabled");
    QString m_operation;
    QString m_requestId;
    QString m_errorCode;
    QString m_error;
    QVariantList m_providers;
    quint64 m_generation = 0;
    quint64 m_processGeneration = 0;
    qint64 m_processGroup = 0;
    ExpectedDocument m_expected = ExpectedDocument::Providers;
    bool m_outputOverflow = false;
    bool m_cancelled = false;
    bool m_closePending = false;
    bool m_operationActive = false;
    bool m_cleanupActive = false;
    bool m_killSent = false;
    int m_pendingExitCode = -1;
    QProcess::ExitStatus m_pendingExitStatus = QProcess::CrashExit;
};
