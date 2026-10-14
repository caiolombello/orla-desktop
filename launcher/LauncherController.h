#pragma once

#include <QObject>
#include <QTimer>
#include <QVariantList>
#include <KConfig>
#include "AliasStore.h"
#include "FavoritesStore.h"
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
    Q_PROPERTY(QString aliasRevision READ aliasRevision NOTIFY changed)
    Q_PROPERTY(bool aliasesWritable READ aliasesWritable NOTIFY changed)
    Q_PROPERTY(QString aliasError READ aliasError NOTIFY changed)
    Q_PROPERTY(QVariantList aliases READ aliases NOTIFY changed)
    Q_PROPERTY(QString favoriteRevision READ favoriteRevision NOTIFY changed)
    Q_PROPERTY(bool favoritesWritable READ favoritesWritable NOTIFY changed)
    Q_PROPERTY(QString favoriteError READ favoriteError NOTIFY changed)
    Q_PROPERTY(QVariantList favorites READ favorites NOTIFY changed)
public:
    explicit LauncherController(SteamProviderController *steam = nullptr, QObject *parent = nullptr, const QString &aliasPath = QString(), const QString &favoritePath = QString());
    QString query() const { return m_query; }
    quint64 generation() const { return m_generation; }
    QVariantList rows() const { return m_rows; }
    int selectedIndex() const { return m_selected; }
    QString status() const;
    QString error() const { return m_error; }
    QString aliasRevision() const { return m_aliases.revision(); }
    bool aliasesWritable() const { return m_aliases.writable(); }
    QString aliasError() const { return m_aliases.error(); }
    QVariantList aliases() const { return m_aliasPresentation; }
    Q_INVOKABLE bool saveAlias(int row, quint64 generation, const QString &id, const QString &alias, const QString &revision);
    Q_INVOKABLE bool renameAlias(const QString &oldAlias, const QString &appId, const QString &newAlias, quint64 generation, const QString &revision);
    Q_INVOKABLE bool removeAlias(const QString &alias, const QString &appId, quint64 generation, const QString &revision);
    Q_INVOKABLE void reloadAliases();
    QString favoriteRevision() const { return m_favorites.revision(); }
    bool favoritesWritable() const { return m_favorites.writable(); }
    QString favoriteError() const { return m_favorites.error(); }
    QVariantList favorites() const { return m_favoritePresentation; }
    Q_INVOKABLE bool pinFavorite(int row, quint64 generation, const QString &id, const QString &revision);
    Q_INVOKABLE bool removeFavorite(const QString &appId, quint64 generation, const QString &revision);
    Q_INVOKABLE void reloadFavorites();
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
    void restoreSelection();
    void steamChanged();
    void savedAppsChanged();
    bool refreshSavedPresentation();
    QString resultId(const QModelIndex &index) const;
    KConfig m_config;
    KConfig m_state;
    KRunner::ResultsModel m_model;
    AliasStore m_aliases;
    FavoritesStore m_favorites;
    QTimer m_debounce;
    QString m_query;
    QString m_error;
    QString m_selectedId;
    QVariantList m_rows;
    QVariantList m_aliasPresentation;
    QVariantList m_favoritePresentation;
    bool m_collectingSavedPresentation = false;
    bool m_savedRefreshPending = false;
    QList<int> m_backendRows;
    SteamProviderController *m_steam;
    quint64 m_generation = 0;
    quint64 m_launchedGeneration = 0;
    int m_selected = -1;
};
