#include "LauncherController.h"
#include "OrlaCommandController.h"
#include "SteamProviderController.h"
#include <KConfigGroup>
#include <KRunner/AbstractRunner>
#include <KService>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusMessage>
#include <QFileInfo>
#include <QScopedValueRollback>
#include <KSycoca>

namespace {
KService::Ptr aliasService(const QString &appId)
{
    if (!AliasStore::validAppId(appId)) return {};
    KSycoca::self()->ensureCacheValid();
    const auto service = KService::serviceByStorageId(appId);
    if (!service || service->storageId() != appId || !QFileInfo(service->entryPath()).isFile()) return {};
    // Sycoca throttles checks. Refuse removed or changed desktop entries until
    // its cached launch metadata agrees with the current installed descriptor.
    const KService current(service->entryPath());
    if (!current.isValid() || !current.isApplication() || current.noDisplay()
        || !current.showInCurrentDesktop() || !current.showOnCurrentPlatform()
        || current.exec() != service->exec() || current.workingDirectory() != service->workingDirectory()
        || current.terminal() != service->terminal() || current.terminalOptions() != service->terminalOptions()
        || current.substituteUid() != service->substituteUid() || current.username() != service->username()
        || current.runOnDiscreteGpu() != service->runOnDiscreteGpu()
        || current.name() != service->name() || current.icon() != service->icon()
        || current.property<bool>(QStringLiteral("DBusActivatable")) != service->property<bool>(QStringLiteral("DBusActivatable"))) return {};
    return service->isApplication() && !service->noDisplay() && service->showInCurrentDesktop()
        && service->showOnCurrentPlatform() ? service : KService::Ptr{};
}
QString appForMatch(const KRunner::QueryMatch &match)
{
    if (!match.runner() || match.runner()->id() != QStringLiteral("krunner_services")) return {};
    const QUrl data = match.data().toUrl();
    if (data.scheme() != QStringLiteral("applications") || !data.authority().isEmpty() || data.hasQuery() || data.hasFragment()) return {};
    return aliasService(data.path()) ? data.path() : QString();
}

const QString servicesRunner = QStringLiteral("krunner_services");
const QString calculatorRunner = QStringLiteral("calculator");
const QString sessionsRunner = QStringLiteral("krunner_sessions");
const QString logoutPromptService = QStringLiteral("org.kde.LogoutPrompt");
// krunner_sessions match data: 1 logout, 2 shutdown, 3 reboot, 4 lock, 5 save session.
// Its own run() honors the user's "confirm logout" setting, so the launcher asks
// the native prompt instead, like the bar's ForcePrompt. Lock/save run directly.
QString confirmationMethod(const KRunner::QueryMatch &match)
{
    if (!match.runner() || match.runner()->id() != sessionsRunner || match.data().typeId() != QMetaType::Int) return {};
    switch (match.data().toInt()) {
    case 1: return QStringLiteral("promptLogout");
    case 2: return QStringLiteral("promptShutDown");
    case 3: return QStringLiteral("promptReboot");
    default: return {};
    }
}
// Opening a remote URL makes KIO probe the network from this process. Only
// local targets are shown; applications: URLs belong to the services runner.
bool localTargets(const KRunner::QueryMatch &match)
{
    if (!match.runner()) return false;
    const QString runner = match.runner()->id();
    if (runner == servicesRunner) return true;
    if (runner == sessionsRunner && match.data().typeId() == QMetaType::Int) {
        const int action = match.data().toInt();
        if (action < 1 || action > 5) return false; // Unknown session side effect.
    }
    QList<QUrl> urls = match.urls();
    if (match.data().typeId() == QMetaType::QUrl) urls.append(match.data().toUrl());
    for (const QUrl &url : urls) if (!url.isLocalFile()) return false;
    return true;
}
}

QStringList LauncherController::runnerAllowlist()
{
    // Local runners only. unitconverter is out: it fetches ECB currency rates on
    // its first query. webshortcuts, bookmarks, dictionary and shell stay out too.
    return {servicesRunner, calculatorRunner, QStringLiteral("org.kde.datetime"),
            QStringLiteral("krunner_systemsettings"), sessionsRunner, QStringLiteral("krunner_powerdevil"),
            QStringLiteral("windows"), QStringLiteral("locations"),
            QStringLiteral("krunner_recentdocuments"), QStringLiteral("baloosearch")};
}

QStringList LauncherController::selectRunners(const QStringList &installed, const KConfigGroup &userPlugins)
{
    QStringList selected;
    for (const QString &id : runnerAllowlist()) {
        if (!installed.contains(id)) continue; // A missing runner is simply absent.
        // Respect a runner the user turned off in KRunner; apps/calculator stay the launcher's core.
        const bool core = id == servicesRunner || id == calculatorRunner;
        if (!core && !userPlugins.readEntry(id + QStringLiteral("Enabled"), true)) continue;
        selected.append(id);
    }
    return selected;
}


LauncherController::LauncherController(SteamProviderController *steam, QObject *parent, const QString &aliasPath, const QString &favoritePath, OrlaCommandController *commands)
    : QObject(parent), m_config(QString(), KConfig::SimpleConfig), m_state(QString(), KConfig::SimpleConfig),
      m_model(m_config.group("Plugins"), m_state.group("General"), nullptr), m_aliases(aliasPath), m_favorites(favoritePath), m_steam(steam), m_commands(commands)
{
    // Supply anonymous groups to ResultsModel as well: its default constructor opens KRunner's user state.
    m_model.runnerManager()->setHistoryEnabled(false);
    QStringList installed;
    for (const auto &metadata : KRunner::RunnerManager::runnerMetaDataList()) installed.append(metadata.pluginId());
    // Read-only: the launcher never writes KRunner's own configuration.
    const KConfig krunnerConfig(QStringLiteral("krunnerrc"), KConfig::NoGlobals);
    m_runnerIds = selectRunners(installed, krunnerConfig.group(QStringLiteral("Plugins")));
    // An empty KRunner allowlist means "every runner"; never let it fall open.
    m_model.runnerManager()->setAllowedRunners(m_runnerIds.isEmpty() ? QStringList{QStringLiteral("orla_no_local_runner")} : m_runnerIds);
    m_model.setLimit(32);
    connect(&m_model, &QAbstractItemModel::rowsInserted, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::rowsRemoved, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::modelReset, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::dataChanged, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::layoutChanged, this, &LauncherController::refresh);
    connect(&m_model, &KRunner::ResultsModel::queryingChanged, this, &LauncherController::refresh);
    connect(&m_model, &KRunner::ResultsModel::queryStringChangeRequested, this,
            [this](const QString &query, int) { setQuery(query); });
    m_debounce.setSingleShot(true);
    m_debounce.setInterval(60);
    connect(&m_debounce, &QTimer::timeout, this, [this] {
        m_launchedGeneration = m_generation;
        m_model.setQueryString(m_query.trimmed());
        if (m_model.runnerManager()->runners().isEmpty()) {
            m_error = tr("Os runners locais não estão disponíveis. Confira a instalação do Plasma.");
        }
        refresh();
    });
    if (m_steam) connect(m_steam, &SteamProviderController::changed, this, &LauncherController::steamChanged);
    connect(KSycoca::self(), &KSycoca::databaseChanged, this, [this] {
        if (m_aliases.entries().isEmpty() && m_favorites.entries().isEmpty()) return;
        if (!m_collectingSavedPresentation) { savedAppsChanged(); return; }
        // Sycoca may notify synchronously while collecting the view snapshot.
        // Keep notification outside collection; a property read never resolves services.
        if (m_savedRefreshPending) return;
        m_savedRefreshPending = true;
        QMetaObject::invokeMethod(this, [this] {
            m_savedRefreshPending = false;
            savedAppsChanged();
        }, Qt::QueuedConnection);
    });
    ++m_generation;
    m_launchedGeneration = m_generation;
    refresh();
}

QObject *LauncherController::commands() const
{
    return m_commands;
}

QString LauncherController::status() const
{
    if (!m_error.isEmpty()) return QStringLiteral("error");
    if (m_query.trimmed().isEmpty()) return m_rows.isEmpty() ? QStringLiteral("idle") : QStringLiteral("ready");
    if (m_debounce.isActive() || m_model.querying()) return QStringLiteral("loading");
    return m_rows.isEmpty() ? QStringLiteral("empty") : QStringLiteral("ready");
}

QString LauncherController::resultId(const QModelIndex &index) const
{
    const auto match = m_model.getQueryMatch(index);
    return match.runner() ? match.runner()->id() + QLatin1Char(':') + match.id() : QString();
}

void LauncherController::refresh()
{
    refreshSavedPresentation();
    m_rows.clear();
    m_backendRows.clear();
    if (m_launchedGeneration != m_generation) {
        emit changed();
        return;
    }
    if (m_query.trimmed().isEmpty()) {
        // The empty surface is preferences, never a synthetic KRunner/Steam query.
        const bool runnerReady = !m_favoritePresentation.isEmpty()
            && m_model.runnerManager()->runner(QStringLiteral("krunner_services")) != nullptr;
        for (const auto &entry : m_favoritePresentation) {
            const auto item = entry.toMap();
            const QString appId = item.value("appId").toString();
            m_rows.append(QVariantMap{{"id", QStringLiteral("favorite:") + appId}, {"generation", m_generation},
                {"title", item.value("title")}, {"iconName", item.value("iconName")},
                {"description", !runnerReady ? tr("O provedor de aplicativos está indisponível.")
                    : !item.value("available").toBool() ? tr("Aplicativo indisponível") : QString()},
                {"enabled", m_favorites.writable() && item.value("available").toBool() && runnerReady},
                {"kind", QStringLiteral("favorite")}, {"category", QStringLiteral("favorite")},
                {"categoryLabel", tr("FAVORITOS")}, {"source", tr("Favorito salvo por você")},
                {"appId", appId}, {"favoriteRevision", m_favorites.revision()}, {"actions", QVariantList{}}});
            m_backendRows.append(-1);
        }
        restoreSelection();
        emit changed();
        return;
    }
    if (m_model.queryString() != m_query.trimmed()) {
        emit changed();
        return;
    }
    QVariantList applicationRows;
    QList<int> applicationBackends;
    for (const auto &entry : m_aliases.entries()) {
        const auto alias = entry.toMap();
        if (AliasStore::key(alias.value("alias").toString()) != AliasStore::key(m_query)) continue;
        const QString appId = alias.value("appId").toString();
        const auto service = aliasService(appId);
        const bool runnerReady = m_model.runnerManager()->runner(QStringLiteral("krunner_services")) != nullptr;
        applicationRows.append(QVariantMap{{"id", QStringLiteral("alias:") + AliasStore::key(alias.value("alias").toString())},
            {"generation", m_generation}, {"title", service ? service->name() : alias.value("alias").toString()},
            {"description", !runnerReady ? tr("O provedor de aplicativos está indisponível.")
                : !service ? tr("Aplicativo indisponível") : tr("Alias: %1").arg(alias.value("alias").toString())},
            {"iconName", service ? service->icon() : QStringLiteral("application-x-executable")},
            {"enabled", m_aliases.writable() && service && runnerReady}, {"kind", QStringLiteral("alias")},
            {"category", QStringLiteral("aliases")}, {"categoryLabel", tr("ALIASES")},
            {"source", tr("Alias salvo por você")}, {"alias", alias.value("alias")}, {"appId", appId},
            {"aliasRevision", m_aliases.revision()}, {"actions", QVariantList{}}});
        applicationBackends.append(-1);
    }
    // Spotlight-like grouping: one contiguous section per source, in this order.
    const QStringList extraOrder{QStringLiteral("calculator"), QStringLiteral("datetime"), QStringLiteral("settings"),
        QStringLiteral("system"), QStringLiteral("windows"), QStringLiteral("locations"),
        QStringLiteral("documents"), QStringLiteral("files")};
    QHash<QString, QVariantList> extraRows;
    QHash<QString, QList<int>> extraBackends;
    bool promptChecked = false, promptAvailable = false;
    for (int row = 0; row < m_model.rowCount() && row < 40; ++row) {
        const auto index = m_model.index(row, 0);
        const auto match = m_model.getQueryMatch(index);
        if (!match.runner() || !m_runnerIds.contains(match.runner()->id()) || !localTargets(match)) continue;
        const QString runnerId = match.runner()->id();
        const auto presentation = presentationFor(runnerId);
        const QString category = presentation.value(QStringLiteral("category")).toString();
        // Other sources stay short so apps keep the top of the list.
        if (category != QStringLiteral("applications") && extraRows.value(category).size() >= 6) continue;
        QVariantList actions;
        const QString prompt = confirmationMethod(match);
        if (prompt.isEmpty()) {
            for (const auto &action : match.actions()) {
                actions.append(QVariantMap{{"id", action.id()}, {"text", action.text()},
                                          {"resultId", resultId(index)}, {"generation", m_generation}, {"row", row}});
            }
        }
        bool enabled = m_model.data(index, KRunner::ResultsModel::EnabledRole).toBool();
        QVariant description = m_model.data(index, KRunner::ResultsModel::SubtextRole);
        if (!prompt.isEmpty()) {
            if (!promptChecked) { promptAvailable = logoutPromptAvailable(); promptChecked = true; }
            enabled = enabled && promptAvailable;
            description = promptAvailable ? tr("O KDE pede confirmação antes de continuar.")
                                          : tr("A confirmação do KDE está indisponível nesta sessão.");
        }
        const QString appId = appForMatch(match);
        const QString iconName = match.iconName().isEmpty() ? match.runner()->metadata().iconName() : match.iconName();
        QVariantMap result{{"id", resultId(index)}, {"generation", m_generation},
            {"title", m_model.data(index, Qt::DisplayRole)}, {"description", description},
            {"iconName", iconName}, {"enabled", enabled}, {"runnerId", runnerId},
            {"confirmation", !prompt.isEmpty()}, {"actions", actions}, {"appId", appId},
            {"aliasEligible", !appId.isEmpty()}};
        result.insert(presentation);
        if (category == QStringLiteral("applications")) { applicationRows.append(result); applicationBackends.append(row); }
        else { extraRows[category].append(result); extraBackends[category].append(row); }
    }
    m_rows = applicationRows;
    m_backendRows = applicationBackends;
    for (const QString &category : extraOrder) {
        m_rows.append(extraRows.value(category));
        m_backendRows.append(extraBackends.value(category));
    }
    if (m_commands) {
        // Matching lists only; the provider is not called until Enter/click on this row.
        const QVariantList commands = m_commands->matches(m_query);
        const bool available = !commands.isEmpty() && m_commands->available();
        for (const QVariant &entry : commands) {
            const QVariantMap command = entry.toMap();
            const QString commandId = command.value(QStringLiteral("id")).toString();
            m_rows.append(QVariantMap{{"id", QStringLiteral("command:") + commandId}, {"generation", m_generation},
                {"title", command.value(QStringLiteral("title"))},
                {"description", available ? command.value(QStringLiteral("description")).toString()
                    : tr("Serviço de complementos indisponível nesta sessão.")},
                {"iconName", QString()}, {"enabled", available}, {"kind", QStringLiteral("command")},
                {"category", QStringLiteral("orla")}, {"categoryLabel", tr("ORLA")},
                {"source", tr("Orla · leitura local")}, {"commandId", commandId}, {"actions", QVariantList{}}});
            m_backendRows.append(-1);
        }
    }
    if (m_steam) {
        const QString needle = m_query.trimmed();
        int matches = 0;
        for (const QVariant &entry : m_steam->apps()) {
            const QVariantMap app = entry.toMap();
            const QString appid = app.value(QStringLiteral("appid")).toString();
            const QString title = app.value(QStringLiteral("name")).toString();
            if (needle != appid && !title.contains(needle, Qt::CaseInsensitive)) continue;
            const QString state = app.value(QStringLiteral("status")).toString();
            const QString library = app.value(QStringLiteral("library")).toString();
            m_rows.append(QVariantMap{{"id", QStringLiteral("steam:%1:%2").arg(appid, library)},
                {"generation", m_generation}, {"inventoryRevision", m_steam->inventoryRevision()},
                {"appid", appid}, {"libraryId", library}, {"title", title},
                {"description", state == QStringLiteral("installed_candidate")
                    ? tr("Presença local detectada") : tr("Estado local incerto")},
                {"enabled", state == QStringLiteral("installed_candidate")},
                {"kind", QStringLiteral("steam")}, {"category", QStringLiteral("steam")},
                {"categoryLabel", tr("STEAM")}, {"source", tr("Steam · metadado local")},
                {"actions", QVariantList{}}});
            m_backendRows.append(-1);
            if (++matches >= 16) break;
        }
    }
    for (int row = 0; row < m_rows.size(); ++row) {
        QVariantMap result = m_rows[row].toMap();
        QVariantList actions = result.value(QStringLiteral("actions")).toList();
        for (QVariant &entry : actions) {
            QVariantMap action = entry.toMap();
            action[QStringLiteral("row")] = row;
            entry = action;
        }
        result[QStringLiteral("actions")] = actions;
        m_rows[row] = result;
    }
    restoreSelection();
    emit changed();
}

QVariantMap LauncherController::presentationFor(const QString &runnerId) const
{
    // kind drives the QML tile/verb, category keeps sections contiguous, source names the origin.
    const auto row = [](const char *kind, const char *category, const QString &label, const QString &source) {
        return QVariantMap{{"kind", QString::fromLatin1(kind)}, {"category", QString::fromLatin1(category)},
                           {"categoryLabel", label}, {"source", source}};
    };
    if (runnerId == calculatorRunner) return row("calculator", "calculator", tr("CALCULADORA"), tr("KRunner · Calculadora"));
    if (runnerId == QStringLiteral("org.kde.datetime")) return row("datetime", "datetime", tr("DATA E HORA"), tr("KRunner · Data e hora"));
    if (runnerId == QStringLiteral("krunner_systemsettings"))
        return row("setting", "settings", tr("AJUSTES DO SISTEMA"), tr("KRunner · Ajustes do Sistema"));
    if (runnerId == sessionsRunner) return row("system", "system", tr("SESSÃO E ENERGIA"), tr("KRunner · Sessão"));
    if (runnerId == QStringLiteral("krunner_powerdevil")) return row("system", "system", tr("SESSÃO E ENERGIA"), tr("KRunner · Energia"));
    if (runnerId == QStringLiteral("windows")) return row("window", "windows", tr("JANELAS"), tr("KWin · Janelas abertas"));
    if (runnerId == QStringLiteral("locations")) return row("location", "locations", tr("LOCAIS"), tr("KRunner · Locais"));
    if (runnerId == QStringLiteral("krunner_recentdocuments"))
        return row("document", "documents", tr("DOCUMENTOS RECENTES"), tr("KRunner · Documentos recentes"));
    if (runnerId == QStringLiteral("baloosearch")) return row("file", "files", tr("ARQUIVOS"), tr("Baloo · Arquivos"));
    return row("app", "applications", tr("APLICATIVOS"), tr("KRunner · Aplicativos"));
}

bool LauncherController::logoutPromptAvailable() const
{
    // The prompt is D-Bus activatable; a missing service must never fall back to an unconfirmed action.
    const auto bus = QDBusConnection::sessionBus();
    if (!bus.isConnected() || !bus.interface()) return false;
    if (bus.interface()->isServiceRegistered(logoutPromptService).value()) return true;
    return bus.interface()->activatableServiceNames().value().contains(logoutPromptService);
}

void LauncherController::restoreSelection()
{
    // Sorting/batches may move rows. Preserve the selected identity, never its old index.
    m_selected = -1;
    for (int row = 0; row < m_rows.size(); ++row) {
        if (m_rows[row].toMap().value("id").toString() == m_selectedId) m_selected = row;
    }
    if (m_selected < 0) {
        m_selectedId.clear();
        for (int row = 0; row < m_rows.size(); ++row) {
            if (m_rows[row].toMap().value("enabled").toBool()) {
                m_selected = row;
                m_selectedId = m_rows[row].toMap().value("id").toString();
                break;
            }
        }
    }
}

void LauncherController::steamChanged()
{
    const bool emptyReady = m_query.trimmed().isEmpty() && m_launchedGeneration == m_generation;
    ++m_generation;
    if (emptyReady || (!m_query.trimmed().isEmpty() && !m_debounce.isActive()
        && m_model.queryString() == m_query.trimmed())) m_launchedGeneration = m_generation;
    refresh();
}

void LauncherController::savedAppsChanged()
{
    const bool emptyReady = m_query.trimmed().isEmpty() && m_launchedGeneration == m_generation;
    ++m_generation;
    if (emptyReady || (!m_query.trimmed().isEmpty() && !m_debounce.isActive()
        && m_model.queryString() == m_query.trimmed())) m_launchedGeneration = m_generation;
    refresh();
}

bool LauncherController::refreshSavedPresentation()
{
    QScopedValueRollback<bool> collecting(m_collectingSavedPresentation, true);
    QVariantList snapshot;
    for (const auto &entry : m_aliases.entries()) {
        auto item = entry.toMap();
        const auto service = aliasService(item.value("appId").toString());
        item.insert("title", service ? service->name() : tr("Aplicativo indisponível"));
        item.insert("iconName", service && !service->icon().isEmpty() ? service->icon() : QStringLiteral("application-x-executable"));
        item.insert("available", bool(service));
        snapshot.append(item);
    }
    QVariantList favorites;
    for (const auto &appId : m_favorites.entries()) {
        const auto service = aliasService(appId);
        favorites.append(QVariantMap{{"appId", appId},
            {"title", service ? service->name() : tr("Aplicativo indisponível")},
            {"iconName", service && !service->icon().isEmpty() ? service->icon() : QStringLiteral("application-x-executable")},
            {"available", bool(service)}});
    }
    if (snapshot == m_aliasPresentation && favorites == m_favoritePresentation) return false;
    m_aliasPresentation = snapshot;
    m_favoritePresentation = favorites;
    return true;
}

void LauncherController::reloadAliases()
{
    const bool preferencesChanged = m_aliases.reload();
    const bool presentationChanged = refreshSavedPresentation();
    if (preferencesChanged || presentationChanged) savedAppsChanged();
}

bool LauncherController::saveAlias(int row, quint64 generation, const QString &id, const QString &alias, const QString &revision)
{
    reloadAliases();
    if (generation != m_generation || m_launchedGeneration != m_generation || status() != QStringLiteral("ready")
        || row != m_selected || row < 0 || row >= m_rows.size() || id != m_selectedId
        || !m_rows[row].toMap().value("enabled").toBool() || m_backendRows.value(row, -1) < 0) return false;
    const auto index = m_model.index(m_backendRows[row], 0);
    if (!index.isValid() || resultId(index) != id) return false;
    const QString appId = appForMatch(m_model.getQueryMatch(index));
    if (appId.isEmpty() || generation != m_generation || id != m_selectedId) return false;
    const bool saved = m_aliases.save(alias, appId, revision);
    if (saved) savedAppsChanged();
    else { reloadAliases(); emit changed(); }
    return saved;
}

bool LauncherController::renameAlias(const QString &oldAlias, const QString &appId, const QString &newAlias, quint64 generation, const QString &revision)
{
    reloadAliases();
    if (generation != m_generation) return false;
    const bool renamed = m_aliases.rename(oldAlias, appId, newAlias, revision);
    if (renamed) savedAppsChanged();
    else { reloadAliases(); emit changed(); }
    return renamed;
}

bool LauncherController::removeAlias(const QString &alias, const QString &appId, quint64 generation, const QString &revision)
{
    reloadAliases();
    if (generation != m_generation) return false;
    const bool removed = m_aliases.remove(alias, appId, revision);
    if (removed) savedAppsChanged();
    else { reloadAliases(); emit changed(); }
    return removed;
}

void LauncherController::reloadFavorites()
{
    const bool preferencesChanged = m_favorites.reload();
    const bool presentationChanged = refreshSavedPresentation();
    if (preferencesChanged || presentationChanged) savedAppsChanged();
}

bool LauncherController::pinFavorite(int row, quint64 generation, const QString &id, const QString &revision)
{
    reloadFavorites();
    if (generation != m_generation || m_launchedGeneration != m_generation || status() != QStringLiteral("ready")
        || row != m_selected || row < 0 || row >= m_rows.size() || id != m_selectedId
        || !m_rows[row].toMap().value("enabled").toBool() || m_backendRows.value(row, -1) < 0) return false;
    const auto index = m_model.index(m_backendRows[row], 0);
    if (!index.isValid() || resultId(index) != id) return false;
    const QString appId = appForMatch(m_model.getQueryMatch(index));
    if (appId.isEmpty() || generation != m_generation || id != m_selectedId) return false;
    const QString beforeRevision = m_favorites.revision();
    const bool saved = m_favorites.pin(appId, revision);
    if (saved || m_favorites.revision() != beforeRevision) savedAppsChanged();
    else { reloadFavorites(); emit changed(); }
    return saved;
}

bool LauncherController::removeFavorite(const QString &appId, quint64 generation, const QString &revision)
{
    reloadFavorites();
    if (generation != m_generation) return false;
    const QString beforeRevision = m_favorites.revision();
    const bool removed = m_favorites.unpin(appId, revision);
    if (removed || m_favorites.revision() != beforeRevision) savedAppsChanged();
    else { reloadFavorites(); emit changed(); }
    return removed;
}

void LauncherController::setQuery(const QString &query)
{
    reloadAliases();
    reloadFavorites();
    if (query == m_query) {
        // A fresh empty opening after dismiss must build its own current ticket.
        if (query.trimmed().isEmpty() && m_launchedGeneration != m_generation) {
            m_launchedGeneration = m_generation;
            refresh();
        }
        return;
    }
    m_debounce.stop();
    m_query = query;
    ++m_generation;
    m_launchedGeneration = 0;
    m_error.clear();
    m_selected = -1;
    m_selectedId.clear();
    m_rows.clear();
    m_backendRows.clear();
    m_model.clear(); // Cancel the native context before starting another query.
    if (query.size() > 512) m_error = tr("Use uma busca com até 512 caracteres.");
    else if (!query.trimmed().isEmpty()) m_debounce.start();
    else {
        m_launchedGeneration = m_generation;
        refresh();
        return;
    }
    emit changed();
}

void LauncherController::select(int row)
{
    if (row < 0 || row >= m_rows.size() || !m_rows[row].toMap().value("enabled").toBool()) return;
    m_selected = row;
    m_selectedId = m_rows[row].toMap().value("id").toString();
    emit changed();
}

void LauncherController::moveSelection(int delta)
{
    if (delta == 0 || m_rows.isEmpty()) return;
    const int direction = delta > 0 ? 1 : -1;
    int row = m_selected;
    for (int tries = 0; tries < m_rows.size(); ++tries) {
        row = (row + direction + m_rows.size()) % m_rows.size();
        if (m_rows[row].toMap().value("enabled").toBool()) { select(row); return; }
    }
}

bool LauncherController::execute(int row, quint64 generation, const QString &id, const QString &actionId)
{
    // Resolve the live index only at the execution boundary. Old QML delegates/callbacks cannot run.
    if (generation != m_generation || m_launchedGeneration != m_generation || status() != QStringLiteral("ready")
        || row < 0 || row >= m_rows.size() || row != m_selected || id.isEmpty() || id != m_selectedId) return false;
    const QVariantMap selected = m_rows[row].toMap();
    if (selected.value("kind").toString() == QStringLiteral("favorite")) {
        if (!actionId.isEmpty()) return false;
        if (m_favorites.reload()) { savedAppsChanged(); return false; }
        const QString appId = selected.value("appId").toString();
        if (!m_favorites.writable() || selected.value("favoriteRevision").toString() != m_favorites.revision()
            || !m_favorites.entries().contains(appId)) return false;
        const auto service = aliasService(appId);
        auto *runner = m_model.runnerManager()->runner(QStringLiteral("krunner_services"));
        if (!service || !runner || runner->id() != QStringLiteral("krunner_services")
            || generation != m_generation || row != m_selected || id != m_selectedId) return false;
        KRunner::QueryMatch match(runner);
        QUrl data;
        data.setScheme(QStringLiteral("applications"));
        data.setPath(appId);
        match.setData(data);
        match.setText(service->name());
        const bool close = m_model.runnerManager()->run(match);
        if (close && generation == m_generation) dismiss();
        return close;
    }
    if (selected.value("kind").toString() == QStringLiteral("alias")) {
        if (!actionId.isEmpty()) return false;
        if (m_aliases.reload()) { savedAppsChanged(); return false; }
        if (!m_aliases.writable() || selected.value("aliasRevision").toString() != m_aliases.revision()) return false;
        const QString appId = selected.value("appId").toString();
        const auto service = aliasService(appId);
        auto *runner = m_model.runnerManager()->runner(QStringLiteral("krunner_services"));
        if (!service || !runner || generation != m_generation || row != m_selected || id != m_selectedId) return false;
        KRunner::QueryMatch match(runner);
        QUrl data;
        data.setScheme(QStringLiteral("applications"));
        data.setPath(appId);
        match.setData(data);
        match.setText(service->name());
        const bool close = m_model.runnerManager()->run(match);
        if (close && generation == m_generation) dismiss();
        return close;
    }
    if (selected.value(QStringLiteral("kind")).toString() == QStringLiteral("command")) {
        // A read never closes the launcher; its panel shows the provider's answer.
        if (!actionId.isEmpty() || !m_commands || !selected.value(QStringLiteral("enabled")).toBool()) return false;
        return m_commands->read(selected.value(QStringLiteral("commandId")).toString());
    }
    if (selected.value(QStringLiteral("kind")).toString() == QStringLiteral("steam")) {
        if (!actionId.isEmpty() || !m_steam) return false;
        const bool opened = m_steam->openGame(selected.value(QStringLiteral("appid")).toString(),
            selected.value(QStringLiteral("libraryId")).toString(),
            selected.value(QStringLiteral("inventoryRevision")).toULongLong());
        if (opened && generation == m_generation) dismiss();
        return opened;
    }
    if (row >= m_backendRows.size() || m_backendRows[row] < 0) return false;
    const auto index = m_model.index(m_backendRows[row], 0);
    if (!index.isValid() || resultId(index) != id || !m_model.data(index, KRunner::ResultsModel::EnabledRole).toBool()) return false;
    const auto match = m_model.getQueryMatch(index);
    if (!match.runner() || !m_runnerIds.contains(match.runner()->id()) || !localTargets(match)) return false;
    const QString prompt = confirmationMethod(match);
    if (!prompt.isEmpty()) {
        // Only the native prompt is contacted; logout/shutdown/reboot wait for the user there.
        if (!actionId.isEmpty() || !logoutPromptAvailable()) return false;
        const auto message = QDBusMessage::createMethodCall(logoutPromptService, QStringLiteral("/LogoutPrompt"),
                                                            logoutPromptService, prompt);
        if (!QDBusConnection::sessionBus().send(message)) return false;
        if (generation == m_generation) dismiss();
        return true;
    }
    int actionIndex = -1;
    if (!actionId.isEmpty()) {
        const auto actions = match.actions();
        for (int i = 0; i < actions.size(); ++i) if (actions[i].id() == actionId) actionIndex = i;
        if (actionIndex < 0) return false;
    }
    const bool close = actionIndex < 0 ? m_model.run(index) : m_model.runAction(index, actionIndex);
    if (close && generation == m_generation) dismiss();
    return true;
}

bool LauncherController::executeSelected()
{
    return execute(m_selected, m_generation, m_selectedId);
}

void LauncherController::dismiss()
{
    // Invalidate outstanding executions even when the input was already empty.
    m_debounce.stop();
    ++m_generation;
    m_launchedGeneration = 0;
    m_query.clear();
    m_rows.clear();
    m_backendRows.clear();
    m_selectedId.clear();
    m_selected = -1;
    m_error.clear();
    m_model.clear();
    if (m_commands) {
        m_commands->cancelAll();
        m_commands->resetAvailability();
    }
    emit changed();
    emit closeRequested();
}
