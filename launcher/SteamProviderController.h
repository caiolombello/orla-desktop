#pragma once

#include <functional>
#include <QObject>
#include <QProcess>
#include <QStringList>
#include <QTimer>
#include <QUrl>
#include <QVariantList>

// Private C++/QML boundary for explicit, session-only Steam metadata discovery.
class SteamProviderController final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(quint64 inventoryRevision READ inventoryRevision NOTIFY changed)
    Q_PROPERTY(QVariantList apps READ apps NOTIFY changed)
    Q_PROPERTY(int rootsCount READ rootsCount NOTIFY changed)
    Q_PROPERTY(int issueCount READ issueCount NOTIFY changed)
    Q_PROPERTY(QString errorCode READ errorCode NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    using UrlOpener = std::function<bool(const QUrl &)>;
    using RootLocator = std::function<QStringList()>;

    explicit SteamProviderController(const QString &pythonPath, const QString &helperPath,
                                     UrlOpener opener = {}, QObject *parent = nullptr, RootLocator rootLocator = {});
    ~SteamProviderController() override;

    QString status() const { return m_status; }
    bool busy() const { return m_operationActive || m_process.state() != QProcess::NotRunning || m_cleanupActive; }
    quint64 inventoryRevision() const { return m_inventoryRevision; }
    QVariantList apps() const { return m_apps; }
    int rootsCount() const { return m_rootsCount; }
    int issueCount() const { return m_issueCount; }
    QString errorCode() const { return m_errorCode; }
    QString error() const { return m_error; }

    static QStringList discoverLocalRoots(const QString &homeBase, const QString &dataBase);

    Q_INVOKABLE QStringList locateRoots() const;
    Q_INVOKABLE void scan(const QStringList &rootSpecs);
    Q_INVOKABLE void cancelAll();
    Q_INVOKABLE bool requestClose();
    Q_INVOKABLE bool openDownloads();
    bool openGame(const QString &appid, const QString &libraryId, quint64 expectedInventoryRevision);

Q_SIGNALS:
    void changed();
    void closeReady();

private:
    bool validateRoots(const QStringList &rootSpecs) const;
    bool parseDocument(const QByteArray &bytes, int exitCode, QVariantList *apps,
                       QString *status, int *issueCount) const;
    void beginCancellation();
    void killOwnedGroup(int signalNumber);
    bool ownedGroupExists() const;
    void beginGroupCleanup();
    void pollGroupCleanup();
    void finishAfterCleanup(bool cleanupConfirmed);
    void handleFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void fail(const QString &code);

    QString m_pythonPath;
    QString m_helperPath;
    UrlOpener m_opener;
    RootLocator m_rootLocator;
    QProcess m_process;
    QTimer m_deadline;
    QTimer m_killGrace;
    QTimer m_groupPoll;
    QTimer m_cleanupDeadline;
    QByteArray m_stdout;
    QString m_status = QStringLiteral("unconfigured");
    QString m_errorCode;
    QString m_error;
    QVariantList m_apps;
    quint64 m_inventoryRevision = 0;
    quint64 m_processGeneration = 0;
    qint64 m_processGroup = 0;
    int m_rootsCount = 0;
    int m_issueCount = 0;
    int m_pendingExitCode = -1;
    QProcess::ExitStatus m_pendingExitStatus = QProcess::CrashExit;
    bool m_outputOverflow = false;
    bool m_cancelled = false;
    bool m_closePending = false;
    bool m_operationActive = false;
    bool m_cleanupActive = false;
    bool m_killSent = false;
};
