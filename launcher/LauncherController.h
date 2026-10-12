#pragma once

#include <QObject>
#include <QTimer>
#include <QVariantList>
#include <KConfig>
#include <KRunner/ResultsModel>
#include <KRunner/RunnerManager>

class SteamProviderController;

// Private C++/QML boundary, experimental with this optional executable.
class LauncherController final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString query READ query WRITE setQuery NOTIFY changed)
    Q_PROPERTY(quint64 generation READ generation NOTIFY changed)
    Q_PROPERTY(QVariantList rows READ rows NOTIFY changed)
    Q_PROPERTY(int selectedIndex READ selectedIndex NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    explicit LauncherController(SteamProviderController *steam = nullptr, QObject *parent = nullptr);
    QString query() const { return m_query; }
    quint64 generation() const { return m_generation; }
    QVariantList rows() const { return m_rows; }
    int selectedIndex() const { return m_selected; }
    QString status() const;
    QString error() const { return m_error; }
    void setQuery(const QString &query);
    Q_INVOKABLE void select(int row);
    Q_INVOKABLE void moveSelection(int delta);
    Q_INVOKABLE bool execute(int row, quint64 generation, const QString &id, const QString &actionId = QString());
    bool executeSelected();
    Q_INVOKABLE void dismiss();
Q_SIGNALS:
    void changed();
    void closeRequested();
private:
    friend class LauncherControllerTestOwner;
    void refresh();
    void steamChanged();
    QString resultId(const QModelIndex &index) const;
    KConfig m_config;
    KConfig m_state;
    KRunner::ResultsModel m_model;
    QTimer m_debounce;
    QString m_query;
    QString m_error;
    QString m_selectedId;
    QVariantList m_rows;
    QList<int> m_backendRows;
    SteamProviderController *m_steam;
    quint64 m_generation = 0;
    quint64 m_launchedGeneration = 0;
    int m_selected = -1;
};
